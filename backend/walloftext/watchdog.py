"""systemd notify + watchdog without extra dependencies (BUILD_PLAN Phase 8).

The service unit is Type=notify with WatchdogSec. We send READY=1 once the app is
up, then WATCHDOG=1 from the asyncio loop, but only while the print worker thread
is alive, so a hung loop or a dead worker gets the service restarted.
"""
from __future__ import annotations

import asyncio
import logging
import os
import socket
from typing import Callable

log = logging.getLogger(__name__)


def notify(msg: str) -> bool:
    addr = os.environ.get("NOTIFY_SOCKET")
    if not addr:
        return False
    if addr.startswith("@"):
        addr = "\0" + addr[1:]
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as s:
            s.connect(addr)
            s.sendall(msg.encode())
        return True
    except OSError as exc:
        log.warning("sd_notify failed: %s", exc)
        return False


def interval_s() -> float | None:
    usec = os.environ.get("WATCHDOG_USEC")
    if not usec:
        return None
    try:
        return max(1.0, int(usec) / 1e6 / 2)  # ping at half the timeout
    except ValueError:
        return None


async def run(healthy: Callable[[], bool]) -> None:
    notify("READY=1")
    every = interval_s()
    if not every:
        return
    while True:
        await asyncio.sleep(every)
        if healthy():
            notify("WATCHDOG=1")
        else:
            log.error("watchdog: unhealthy, not pinging (systemd will restart us)")
