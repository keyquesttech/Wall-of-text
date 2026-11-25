"""Runs every enabled channel: poll, hand to the pipeline, back off on failure
(60 s doubling to 15 min), report state for Settings › Email and Settings › Telegram."""
from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING

from .base import ChannelError

if TYPE_CHECKING:
    from ..services import Services

log = logging.getLogger(__name__)

BASE_S = 60.0
MAX_BACKOFF_S = 15 * 60.0


class RemoteManager:
    def __init__(self, svc: "Services", pipeline, adapters: dict):
        self.svc = svc
        self.pipeline = pipeline
        self.adapters = adapters
        self.state: dict[str, dict] = {k: {"status": "off", "message": None, "last_ok": None} for k in adapters}
        self._tasks: dict[str, asyncio.Task] = {}
        self._wake: dict[str, asyncio.Event] = {}

    def enabled(self, cid: str) -> bool:
        return self.svc.store.get(f"remote_enabled:{cid}", "0") == "1"

    def set_enabled(self, cid: str, on: bool) -> None:
        self.svc.store.set(f"remote_enabled:{cid}", "1" if on else "0")
        self.reconcile()

    def channel(self, cid: str) -> dict:
        a = self.adapters[cid]
        st = self.state[cid]
        return {"id": cid, "label": a.label, "enabled": self.enabled(cid), "configured": a.configured(),
                "status": st["status"] if self.enabled(cid) else "off", "message": st["message"],
                "last_ok": st["last_ok"], "settings": a.public()}

    def channels(self) -> list[dict]:
        return [self.channel(c) for c in self.adapters if c != "mock" or self.svc.settings.is_mock]

    # ---------------------------------------------------------------- run --
    def reconcile(self) -> None:
        """Start loops for enabled + configured channels, stop the rest."""
        if self.svc.loop is None:
            return
        for cid, a in self.adapters.items():
            want = self.enabled(cid) and a.configured()
            t = self._tasks.get(cid)
            if want and (t is None or t.done()):
                self._wake[cid] = asyncio.Event()
                self._tasks[cid] = self.svc.loop.create_task(self._run(cid))
            elif not want and t and not t.done():
                t.cancel()

    def kick(self, cid: str) -> None:
        if cid in self._wake:
            self._wake[cid].set()

    async def stop(self) -> None:
        for t in self._tasks.values():
            t.cancel()
        for t in self._tasks.values():
            try:
                await t
            except (asyncio.CancelledError, Exception):
                pass

    async def poll_once(self, cid: str) -> int:
        a = self.adapters[cid]
        msgs = await a.poll()
        for m in msgs:
            try:
                await self.pipeline.handle(m, a)
            except Exception:
                log.exception("remote pipeline failed on a %s message", cid)
        if hasattr(a, "commit"):
            a.commit()
        if hasattr(a, "send"):  # bot: unanswered "how should this print?" questions, and the "/" menu
            await self.pipeline.bot.expire(a)
            menu = self.pipeline.bot.menu()
            if getattr(a, "_menu", None) != menu:
                try:
                    await a.set_commands(menu)
                    a._menu = menu
                except ChannelError:
                    pass
        return len(msgs)

    async def _run(self, cid: str) -> None:
        delay = BASE_S
        long_poll = cid == "telegram"
        while True:
            try:
                await self.poll_once(cid)
                self.state[cid] = {"status": "ok", "message": None, "last_ok": time.time()}
                delay = BASE_S
                wait = 1.0 if long_poll else BASE_S
            except asyncio.CancelledError:
                raise
            except ChannelError as exc:
                self.state[cid] = {**self.state[cid], "status": "reauth" if exc.reauth else "cant_connect",
                                   "message": str(exc)}
                wait, delay = delay, min(delay * 2, MAX_BACKOFF_S)
            except Exception as exc:
                log.exception("remote channel %s failed", cid)
                self.state[cid] = {**self.state[cid], "status": "cant_connect", "message": str(exc)[:200]}
                wait, delay = delay, min(delay * 2, MAX_BACKOFF_S)
            self.svc.events.publish("remote", {"channel": self.channel(cid)})
            try:
                await asyncio.wait_for(self._wake[cid].wait(), timeout=wait)
                self._wake[cid].clear()
            except asyncio.TimeoutError:
                pass
