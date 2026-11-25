"""Owns the GPIO devices (button, panel light, fan, LED strips) and rebuilds them whenever
their settings change, so a pin or an on/off switch takes effect without a restart.

A device that can't start (pin clash, nothing wired, SPI off) is left off with a plain
sentence in `status()`; the rest of the app keeps running.
"""
from __future__ import annotations

import json
import logging
import threading
from typing import TYPE_CHECKING, Any

from .button import GestureDetector, GpioButton, MockButton
from .fan import FanController, FanOutput, GpioFan
from .led import GpioLed, Led, MockLed
from .neopixel import NeoPixelController, SpiStrip, Strip
from .pins import problems

if TYPE_CHECKING:
    from ..services import Services

log = logging.getLogger(__name__)


class SwitchableLed(Led):
    """What the rest of the app talks to; the real LED behind it can be swapped or removed."""

    def __init__(self):
        super().__init__()
        self.impl: Led | None = None

    def _apply(self) -> None:
        if self.impl is not None:
            try:
                self.impl.set(self.pattern, self.brightness)
            except Exception:
                log.exception("LED update failed")

    def swap(self, impl: Led | None) -> None:
        old, self.impl = self.impl, impl
        if old is not None:
            try:
                old.close()
            except Exception:
                pass
        self._apply()


class NoButton:
    """The button is switched off: gestures are ignored."""

    def fire(self, gesture) -> None:
        pass

    def close(self) -> None:
        pass


class Hardware:
    GROUPS = ("button", "led", "fan", "neopixel")

    def __init__(self, svc: "Services", real: bool, detector: GestureDetector):
        self.svc = svc
        self.real = real
        self.detector = detector
        self.led = SwitchableLed()
        self.button: Any = NoButton()
        self.fan: FanController | None = None
        self.neo: NeoPixelController | None = None
        self.errors: dict[str, str] = {}
        self._applied: dict[str, str] = {}
        self._lock = threading.RLock()

    # --------------------------------------------------------------- build --
    def _cfg(self) -> dict:
        all_ = self.svc.app_settings.all()
        return {k: all_.get(k, {}) for k in self.GROUPS}

    def apply(self, force: bool = False) -> None:
        """(Re)build each device whose settings changed."""
        with self._lock:
            cfg = self._cfg()
            bad = problems(cfg)
            for group in self.GROUPS:
                key = json.dumps(self._hw_part(group, cfg[group]), sort_keys=True)
                if not force and self._applied.get(group) == key:
                    continue
                self._applied[group] = key
                getattr(self, f"_build_{group}")(cfg[group], bad)

    @staticmethod
    def _hw_part(group: str, c: dict) -> dict:
        """Only the settings that need the device rebuilt (not colours, speeds or actions)."""
        if group == "button":
            return {k: c.get(k) for k in ("enabled", "pin")}
        if group == "led":
            return {k: c.get(k) for k in ("enabled", "pin")}
        if group == "fan":
            return {k: c.get(k) for k in ("enabled", "pin", "frequency", "invert")}
        return {"enabled": c.get("enabled"), "order": c.get("order"),
                "strips": [{k: s.get(k) for k in ("pin", "count")} for s in c.get("strips") or []]}

    def _build_button(self, c: dict, bad: dict) -> None:
        self.button.close()
        self.button = NoButton()
        self.errors.pop("button", None)
        if not c.get("enabled", True):
            return
        if "button" in bad:
            self.errors["button"] = bad["button"]
            return
        if not self.real:
            self.button = MockButton(self.detector)
            return
        try:
            self.button = GpioButton(int(c.get("pin", 17)), self.detector)
        except Exception as exc:
            log.warning("button unavailable: %s", exc)
            self.errors["button"] = f"Can't use GPIO{c.get('pin', 17)}: {exc}"[:160]

    def _build_led(self, c: dict, bad: dict) -> None:
        self.errors.pop("led", None)
        impl: Led | None = None
        if c.get("enabled", True):
            if "led" in bad:
                self.errors["led"] = bad["led"]
            elif not self.real:
                impl = MockLed()
            else:
                try:
                    impl = GpioLed(int(c.get("pin", 18)))
                except Exception as exc:
                    log.warning("LED unavailable: %s", exc)
                    self.errors["led"] = f"Can't use GPIO{c.get('pin', 18)}: {exc}"[:160]
        self.led.swap(impl)

    def _build_fan(self, c: dict, bad: dict) -> None:
        if self.fan:
            self.fan.stop()
            self.fan = None
        self.errors.pop("fan", None)
        if not c.get("enabled"):
            return
        if "fan" in bad:
            self.errors["fan"] = bad["fan"]
            return
        pin, freq, inv = int(c.get("pin", 12)), int(c.get("frequency", 1000)), bool(c.get("invert"))
        try:
            out = GpioFan(pin, freq, inv) if self.real else FanOutput(pin, freq, inv)
        except Exception as exc:
            log.warning("fan unavailable: %s", exc)
            self.errors["fan"] = f"Can't use GPIO{pin}: {exc}"[:160]
            return
        self.fan = FanController(out, lambda: self.svc.app_settings.get("fan"), self.svc.system.temperature_c)
        self.fan.start()

    def _build_neopixel(self, c: dict, bad: dict) -> None:
        if self.neo:
            self.neo.stop()
            self.neo = None
        for k in [k for k in self.errors if k.startswith("strip") or k == "neopixel"]:
            self.errors.pop(k)
        if not c.get("enabled"):
            return
        strips = []
        for i, s in enumerate(c.get("strips") or []):
            if f"strip{i}" in bad:
                self.errors[f"strip{i}"] = bad[f"strip{i}"]
                continue
            pin, count = int(s.get("pin", 10)), int(s.get("count", 30))
            try:
                strips.append(SpiStrip(pin, count, c.get("order", "GRB")) if self.real else Strip(pin, count, c.get("order", "GRB")))
            except Exception as exc:
                log.warning("LED strip %d unavailable: %s", i + 1, exc)
                self.errors[f"strip{i}"] = str(exc)[:200]
        if not strips:
            if not c.get("strips"):
                self.errors["neopixel"] = "Add a strip first."
            return

        def quiet() -> bool:
            sched = self.svc.extras.get("scheduler")
            return bool(sched and sched.hold_until())

        self.neo = NeoPixelController(strips, lambda: self.svc.app_settings.get("neopixel"), quiet)
        self.neo.on_event("init", {}, self.svc.led_ctl.event)
        self.neo.start()

    # -------------------------------------------------------------- events --
    def on_event(self, name: str, data: dict) -> None:
        if name == "settings":
            try:
                self.apply()
            except Exception:
                log.exception("hardware apply failed")
        if self.neo and name in ("printer", "wifi", "inbox", "progress", "settings"):
            self.neo.on_event(name, data, self.svc.led_ctl.event)

    def close(self) -> None:
        with self._lock:
            self.button.close()
            self.led.swap(None)
            if self.fan:
                self.fan.stop()
            if self.neo:
                self.neo.stop()

    # -------------------------------------------------------------- status --
    def status(self) -> dict:
        cfg = self._cfg()
        neo = None
        if self.neo:
            neo = {"event": self.neo.current()[0], "progress": round(self.neo.progress, 2),
                   "frames": [["#%02x%02x%02x" % p for p in s.frame] for s in self.neo.strips]}
        return {
            "real": self.real,
            "button": {"on": not isinstance(self.button, NoButton), "error": self.errors.get("button")},
            "led": {"on": self.led.impl is not None, "error": self.errors.get("led"), "pattern": self.led.pattern},
            "fan": {"on": self.fan is not None, "error": self.errors.get("fan"), **(self.fan.status() if self.fan else {})},
            "neopixel": {"on": self.neo is not None, "error": self.errors.get("neopixel"),
                         "strip_errors": {k: v for k, v in self.errors.items() if k.startswith("strip")}, "live": neo},
            "spi": _spi_devices(),
            "temperature_c": self.svc.system.temperature_c(),
            "problems": problems(cfg),
        }


def _spi_devices() -> list[str]:
    from pathlib import Path
    return sorted(p.name for p in Path("/dev").glob("spidev*"))
