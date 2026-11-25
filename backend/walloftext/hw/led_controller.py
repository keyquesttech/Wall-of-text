"""Drives the panel LED from the same status events as the UI (BUILD_PLAN 8).

Priority (highest first): reset armed (fast triple blink, handled by the
button) > setup network up > error/offline > paper out > printing >
message waiting > idle. Each event maps to a pattern in Settings › Panel light.
"""
from __future__ import annotations

import logging
from typing import Callable

from .led import PATTERNS, Led

log = logging.getLogger(__name__)


class LedController:
    def __init__(self, led: Led, settings_get: Callable[[], dict]):
        self.led = led
        self.settings_get = settings_get
        self.printer_state = "ready"
        self.wifi_mode = "online"
        self.waiting = 0
        self.current: tuple[str, float] | None = None

    def event(self) -> str:
        if self.wifi_mode in ("setup_ap", "fallback_ap"):
            return "setup"
        if self.printer_state == "offline":
            return "error"
        if self.printer_state == "paper_out":
            return "paper_out"
        if self.printer_state == "printing":
            return "printing"
        if self.waiting > 0:
            return "message_waiting"
        return "idle"

    def update(self) -> str:
        cfg = self.settings_get().get("led", {})
        ev = self.event()
        pattern = "slow_pulse" if ev == "setup" else cfg.get("patterns", {}).get(ev, "off")
        if pattern not in PATTERNS:
            pattern = "off"
        brightness = max(0, min(100, int(cfg.get("brightness", 60)))) / 100
        if (pattern, brightness) != self.current:
            self.current = (pattern, brightness)
            try:
                self.led.set(pattern, brightness)
            except Exception:
                log.exception("LED update failed")
        return pattern

    def on_event(self, name: str, data: dict) -> None:
        if name == "printer":
            self.printer_state = data.get("state", self.printer_state)
        elif name == "wifi":
            self.wifi_mode = data.get("mode", self.wifi_mode)
        elif name == "inbox":
            self.waiting = int(data.get("waiting", 0))
        elif name != "settings":
            return
        self.update()
