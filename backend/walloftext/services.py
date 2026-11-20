"""Builds and wires every long-lived object. `WOT_HW=real|mock` picks hardware."""
from __future__ import annotations

import asyncio
import logging
import threading
import time
from dataclasses import dataclass, field

from PIL import Image

from .auth.passwords import PasswordFile
from .auth.sessions import LoginLimiter, SessionStore
from .config import Settings
from .events import EventBus
from .hw.button import GestureDetector, GpioButton, MockButton
from .hw.led import GpioLed, Led, MockLed
from .hw.system import MockSystemInfo, SystemInfo
from .net.nm import FakeNetworkManager, NmcliClient
from .net.wifi import AP_MODES, WifiManager, WifiStatus
from .printer.drivers import EscposUsbPrinter, MockPrinter
from .render.slips import connected_slip, setup_slip
from .store.db import Store

log = logging.getLogger(__name__)


@dataclass
class Services:
    settings: Settings
    store: Store
    passwords: PasswordFile
    sessions: SessionStore
    limiter: LoginLimiter
    events: EventBus
    nm: object
    wifi: WifiManager
    printer: object
    led: Led
    system: SystemInfo
    button: object = None
    loop: asyncio.AbstractEventLoop | None = None
    _print_lock: threading.Lock = field(default_factory=threading.Lock)

    # ----------------------------------------------------------- printing --
    def print_image(self, img: Image.Image, source: str, title: str) -> int:
        """Phase 1: synchronous print with a jobs row. Phase 2 replaces with the queue worker."""
        c = self.store.conn()
        cur = c.execute(
            "INSERT INTO jobs(source,title,state,created_at) VALUES(?,?,?,?)",
            (source, title, "printing", time.time()),
        )
        job_id = cur.lastrowid
        try:
            with self._print_lock:
                self.printer.print_bitmap(img)
            c.execute("UPDATE jobs SET state='done', finished_at=? WHERE id=?", (time.time(), job_id))
        except Exception as exc:
            log.warning("print failed: %s", exc)
            c.execute("UPDATE jobs SET state='failed', error=?, finished_at=? WHERE id=?",
                      (str(exc)[:200], time.time(), job_id))
        return job_id

    async def print_setup_slip(self) -> None:
        if self.printer.status().state != "ready":
            log.info("printer not ready; setup slip skipped")
            return
        img = setup_slip(self.settings.fonts_dir, self.passwords.state.setup_wifi_password)
        await asyncio.to_thread(self.print_image, img, "System", "Setup slip")

    async def print_connected_slip(self, ssid: str, ip: str | None) -> None:
        if self.printer.status().state != "ready":
            return
        img = connected_slip(self.settings.fonts_dir, ssid, ip)
        await asyncio.to_thread(self.print_image, img, "System", "Connected")

    # ------------------------------------------------------------ button --
    def on_gesture(self, gesture: str) -> None:
        """May be called from the GPIO thread."""
        if self.loop is None:
            return
        self.loop.call_soon_threadsafe(lambda: asyncio.ensure_future(self._handle_gesture(gesture)))

    async def _handle_gesture(self, gesture: str) -> None:
        log.info("button: %s", gesture)
        self.events.publish("button", {"gesture": gesture})
        if gesture == "reset":
            await self.wifi.reset()
        # single/double/long map to user actions in Phase 3.

    def on_reset_armed(self) -> None:
        self.led.set("triple_blink")

    # -------------------------------------------------------------- misc --
    def on_wifi_change(self, status: WifiStatus) -> None:
        self.events.publish("wifi", status.to_dict())
        self.led.set("slow_pulse" if status.mode in AP_MODES else "solid")

    def on_setup_wifi_password_change(self, psk: str) -> None:
        if self.loop is None:
            return
        self.loop.call_soon_threadsafe(lambda: asyncio.ensure_future(self.wifi.apply_ap_password(psk)))


def build(settings: Settings | None = None, nm=None) -> Services:
    settings = settings or Settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    store = Store(settings.db_path)
    passwords = PasswordFile(settings.password_file)
    sessions = SessionStore(store)
    events = EventBus()
    real = settings.hw == "real"

    if nm is None:
        nm = NmcliClient() if real else FakeNetworkManager()
    printer = EscposUsbPrinter(settings.printer_device) if real else MockPrinter(settings.mock_printer_dir)
    system = SystemInfo() if real else MockSystemInfo()
    led: Led
    try:
        led = GpioLed(settings.led_pin) if real else MockLed()
    except Exception as exc:  # no GPIO access: keep running
        log.warning("LED unavailable: %s", exc)
        led = MockLed()

    wifi = WifiManager(nm=nm, settings=settings, ap_password=lambda: passwords.state.setup_wifi_password)
    svc = Services(settings=settings, store=store, passwords=passwords, sessions=sessions,
                   limiter=LoginLimiter(), events=events, nm=nm, wifi=wifi, printer=printer,
                   led=led, system=system)

    detector = GestureDetector(svc.on_gesture, svc.on_reset_armed)
    if real:
        try:
            svc.button = GpioButton(settings.button_pin, detector)
        except Exception as exc:
            log.warning("button unavailable: %s", exc)
            svc.button = MockButton(detector)
    else:
        svc.button = MockButton(detector)

    passwords.on_gui_change.append(lambda: sessions.revoke_all())
    passwords.on_wifi_change.append(svc.on_setup_wifi_password_change)
    wifi.on_change.append(svc.on_wifi_change)
    wifi.on_setup.append(svc.print_setup_slip)
    wifi.on_online.append(svc.print_connected_slip)
    return svc
