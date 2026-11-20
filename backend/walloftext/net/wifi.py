"""Wi-Fi state machine (BUILD_PLAN section 5.1).

    BOOT ─ no saved home Wi-Fi ───────────────────────► SETUP_AP
    BOOT ─ saved home Wi-Fi ─► CONNECTING (≤120 s) ───► ONLINE
                                       └─ timeout ────► FALLBACK_AP ─(saved network works)─► ONLINE
    ONLINE ─ link lost for 5 min ─► CONNECTING
    any ─ reset ─► SETUP_AP (home Wi-Fi forgotten)

The app, not NetworkManager, decides when the AP goes up: the AP profile has
`autoconnect no`. `tick()` is pure with respect to an injected clock so the
whole machine is unit-tested against `FakeNetworkManager`.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Awaitable, Callable

from ..config import AP_ADDRESS, CLIENT_CON_NAME, LOCAL_ADDRESS, SETUP_SSID, Settings
from .nm import Network, NetworkManagerClient

log = logging.getLogger(__name__)

SETUP_AP = "setup_ap"
CONNECTING = "connecting"
ONLINE = "online"
FALLBACK_AP = "fallback_ap"
AP_MODES = (SETUP_AP, FALLBACK_AP)

ERROR_TEXT = {
    "wrong_password": "The password for {ssid} was not accepted. Check it and try again.",
    "not_found": "The Pi couldn't find {ssid}. Move closer to the router or check the name.",
    "no_ip": "The Pi joined {ssid} but didn't get an address. Try again, or restart the router.",
    "failed": "The Pi couldn't join {ssid}. Try again.",
    "enterprise": "Networks that ask for a username as well as a password aren't supported yet.",
}

Hook = Callable[..., Awaitable[None] | None]


@dataclass
class WifiStatus:
    mode: str = SETUP_AP
    ssid: str | None = None
    ip: str | None = None
    signal: int | None = None
    last_error: str | None = None
    last_error_text: str | None = None
    pending_ssid: str | None = None
    ap_clients: int = 0
    since: float = 0.0

    def to_dict(self, hostname: str = LOCAL_ADDRESS) -> dict:
        return {
            "mode": self.mode,
            "ssid": self.ssid,
            "ip": self.ip,
            "hostname": hostname,
            "signal": self.signal,
            "last_error": self.last_error,
            "last_error_text": self.last_error_text,
            "pending_ssid": self.pending_ssid,
            "ap": {"ssid": SETUP_SSID, "address": AP_ADDRESS, "clients": self.ap_clients},
        }


@dataclass
class WifiManager:
    nm: NetworkManagerClient
    settings: Settings
    ap_password: Callable[[], str]
    clock: Callable[[], float] = time.monotonic
    on_change: list[Hook] = field(default_factory=list)
    on_online: list[Hook] = field(default_factory=list)  # (ssid, ip) after a user connect
    on_setup: list[Hook] = field(default_factory=list)  # AP raised by reset or first boot
    status: WifiStatus = field(default_factory=WifiStatus)

    def __post_init__(self):
        self._busy = asyncio.Lock()
        self._link_lost_at: float | None = None
        self._last_retry: float = 0.0
        self._scan_cache: list[Network] = self._load_scan_cache()
        self._task: asyncio.Task | None = None

    # ---------------------------------------------------------- helpers --
    async def _call(self, fn, *args):
        return await asyncio.to_thread(fn, *args)

    async def _emit(self, hooks: list[Hook], *args) -> None:
        for h in hooks:
            try:
                r = h(*args)
                if asyncio.iscoroutine(r):
                    await r
            except Exception:  # hooks must never break networking
                log.exception("wifi hook failed")

    async def _set_mode(self, mode: str, **kw) -> None:
        changed = mode != self.status.mode
        self.status.mode = mode
        for k, v in kw.items():
            setattr(self.status, k, v)
        if changed:
            self.status.since = self.clock()
            log.info("wifi mode -> %s", mode)
        self._persist()
        await self._emit(self.on_change, self.status)

    def _persist(self) -> None:
        try:
            self.settings.wifi_state_file.parent.mkdir(parents=True, exist_ok=True)
            self.settings.wifi_state_file.write_text(json.dumps(self.status.to_dict()))
        except OSError:
            pass

    def _load_scan_cache(self) -> list[Network]:
        try:
            data = json.loads(Path(self.settings.wifi_scan_cache).read_text())
            return [Network(**n) for n in data]
        except (OSError, ValueError, TypeError):
            return []

    async def refresh_scan(self) -> None:
        """Scan only while the radio is a client or idle. Cached for the setup page."""
        try:
            nets = await self._call(self.nm.scan)
        except Exception as exc:
            log.warning("scan failed: %s", exc)
            return
        if nets:
            self._scan_cache = nets
            try:
                self.settings.wifi_scan_cache.parent.mkdir(parents=True, exist_ok=True)
                self.settings.wifi_scan_cache.write_text(json.dumps([n.to_dict() for n in nets]))
            except OSError:
                pass

    def scan_results(self) -> list[dict]:
        return [n.to_dict() for n in self._scan_cache]

    async def _raise_ap(self, mode: str) -> None:
        await self.refresh_scan()  # last chance to scan before the radio becomes an AP
        try:
            await self._call(self.nm.ensure_ap_profile, self.ap_password())
        except Exception:
            log.exception("could not prepare the AP profile")
        ok = await self._call(self.nm.ap_up)
        if not ok:
            log.error("AP did not come up")
        await self._set_mode(mode, ssid=None, ip=AP_ADDRESS if ok else None, signal=None, pending_ssid=None)

    # ------------------------------------------------------------- boot --
    async def start(self) -> None:
        saved = await self._call(self.nm.saved_client_profiles)
        if not saved:
            await self._raise_ap(SETUP_AP)
            await self._emit(self.on_setup)
        else:
            if await self._call(self.nm.ap_active):
                await self._call(self.nm.ap_down)  # left over from before a crash
            await self._set_mode(CONNECTING, ssid=None, ip=None)
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass

    async def _loop(self) -> None:
        while True:
            try:
                await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("wifi tick failed")
            await asyncio.sleep(1.0 if self.status.mode == CONNECTING else 5.0)

    # ------------------------------------------------------------- tick --
    async def tick(self) -> None:
        if self._busy.locked():
            return
        async with self._busy:
            now = self.clock()
            mode = self.status.mode
            if mode in AP_MODES:
                clients = await self._call(self.nm.ap_clients)
                if clients != self.status.ap_clients:
                    self.status.ap_clients = clients
                    await self._emit(self.on_change, self.status)
                if mode == SETUP_AP:
                    return
                # FALLBACK_AP: retry the saved network, but never kick a phone off the AP
                if now - self._last_retry < self.settings.fallback_retry_s or clients > 0:
                    return
                self._last_retry = now
                await self._retry_saved()
                return

            link = await self._call(self.nm.client_link)
            if mode == CONNECTING:
                if link and link.ip:
                    self._link_lost_at = None
                    await self._set_mode(ONLINE, ssid=link.ssid, ip=link.ip, signal=link.signal, last_error=None,
                                         last_error_text=None)
                elif now - self.status.since >= self.settings.connect_timeout_s:
                    self._last_retry = now
                    await self._raise_ap(FALLBACK_AP)
                return

            if mode == ONLINE:
                if link and link.ip:
                    self._link_lost_at = None
                    if (link.ssid, link.ip, link.signal) != (self.status.ssid, self.status.ip, self.status.signal):
                        await self._set_mode(ONLINE, ssid=link.ssid, ip=link.ip, signal=link.signal)
                    return
                if self._link_lost_at is None:
                    self._link_lost_at = now
                    log.warning("home Wi-Fi link lost")
                elif now - self._link_lost_at >= self.settings.link_lost_s:
                    self._link_lost_at = None
                    await self._set_mode(CONNECTING, ip=None, signal=None)

    async def _retry_saved(self) -> None:
        saved = await self._call(self.nm.saved_client_profiles)
        if not saved:
            await self._set_mode(SETUP_AP)
            return
        log.info("fallback: retrying saved network %s", saved[0])
        await self._call(self.nm.ap_down)
        res = await self._call(self.nm.activate, saved[0], self.settings.client_ip_wait_s)
        if res.ok:
            link = await self._call(self.nm.client_link)
            await self._set_mode(ONLINE, ssid=link.ssid if link else None, ip=res.ip,
                                 signal=link.signal if link else None, last_error=None, last_error_text=None)
        else:
            await self._call(self.nm.ap_up)
            await self._set_mode(FALLBACK_AP, ip=AP_ADDRESS)

    # ---------------------------------------------------------- actions --
    async def connect(self, ssid: str, password: str | None, hidden: bool = False,
                      security: str | None = None) -> None:
        """Called after the API has replied 202. Never logs the password."""
        if security == "enterprise":
            await self._set_mode(self.status.mode, last_error="enterprise",
                                 last_error_text=ERROR_TEXT["enterprise"])
            return
        async with self._busy:
            await asyncio.sleep(self.settings.connect_reply_delay_s)
            previous_mode = self.status.mode
            before = set(await self._call(self.nm.saved_client_profiles))
            await self._set_mode(CONNECTING, pending_ssid=ssid, last_error=None, last_error_text=None)
            if CLIENT_CON_NAME in before:
                await self._call(self.nm.delete_profile, CLIENT_CON_NAME)
            try:
                name = await self._call(self.nm.add_client, ssid, password, hidden, security)
            except Exception as exc:
                log.error("could not create client profile: %s", str(exc).split("psk")[0])
                await self._fail(ssid, "failed", previous_mode)
                return
            await self._call(self.nm.ap_down)
            res = await self._call(self.nm.activate, name, self.settings.client_ip_wait_s)
            if not res.ok:
                await self._call(self.nm.delete_profile, name)
                await self._fail(ssid, res.error or "failed", previous_mode)
                return
            # The new network replaces any other saved home network (e.g. the one Imager made).
            for other in before - {CLIENT_CON_NAME}:
                await self._call(self.nm.delete_profile, other)
            link = await self._call(self.nm.client_link)
            self._link_lost_at = None
            await self._set_mode(ONLINE, ssid=ssid, ip=res.ip, signal=link.signal if link else None,
                                 pending_ssid=None)
        await self._emit(self.on_online, ssid, res.ip)
        asyncio.create_task(self.refresh_scan())

    async def _fail(self, ssid: str, code: str, previous_mode: str) -> None:
        text = ERROR_TEXT.get(code, ERROR_TEXT["failed"]).format(ssid=ssid)
        self.status.last_error, self.status.last_error_text = code, text
        saved = await self._call(self.nm.saved_client_profiles)
        if saved and previous_mode in (ONLINE, CONNECTING):
            # "Change network" from the home network failed: go back to the old one.
            res = await self._call(self.nm.activate, saved[0], self.settings.client_ip_wait_s)
            if res.ok:
                link = await self._call(self.nm.client_link)
                await self._set_mode(ONLINE, ssid=link.ssid if link else None, ip=res.ip,
                                     signal=link.signal if link else None, pending_ssid=None)
                return
        mode = FALLBACK_AP if (saved and previous_mode != SETUP_AP) else SETUP_AP
        self._last_retry = self.clock()
        ok = await self._call(self.nm.ap_up)
        await self._set_mode(mode, ip=AP_ADDRESS if ok else None, pending_ssid=None, ssid=None)

    async def reset(self) -> None:
        """Forget every home network and go back to setup (web, button, CLI)."""
        async with self._busy:
            for name in await self._call(self.nm.saved_client_profiles):
                await self._call(self.nm.delete_profile, name)
            self.status.last_error = self.status.last_error_text = None
            await self._raise_ap(SETUP_AP)
        await self._emit(self.on_setup)

    async def apply_ap_password(self, psk: str) -> None:
        """New setup Wi-Fi password: re-key the profile. It applies next time the AP comes up."""
        try:
            await self._call(self.nm.set_ap_password, psk)
        except Exception:
            log.exception("could not re-key the setup network")
