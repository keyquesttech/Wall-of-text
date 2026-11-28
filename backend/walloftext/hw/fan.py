"""Auxiliary fan on a GPIO pin (through a transistor/MOSFET, or a 4-pin PWM fan's control wire).

Modes:
* "always": runs at the maximum speed all the time.
* "temperature": off below the start temperature; at the start temperature it runs at the
  minimum speed (the slowest it reliably spins) and ramps to the maximum speed at the
  full-speed temperature. It stops again 3 °C below the start temperature (no flapping).
A stopped fan is kicked at full power for a moment so it starts from rest at a low speed.

Control:
* "pwm": speed control with software PWM (min/max speed, frequency).
* "onoff": no PWM. The pin is simply on or off (full speed or stopped), for relay modules,
  fans that don't like PWM, and simple transistor switches. Same modes and temperatures.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Callable

log = logging.getLogger(__name__)

HYSTERESIS_C = 3.0
KICK_S = 1.0


def target_speed(cfg: dict, temp: float | None, running: bool) -> float:
    """Fan speed 0-100 for this temperature (pure logic, easy to test)."""
    lo = max(0.0, min(100.0, float(cfg.get("min_speed", 30))))
    hi = max(lo, min(100.0, float(cfg.get("max_speed", 100))))
    if cfg.get("mode", "temperature") == "always":
        return hi
    if temp is None:
        return hi  # can't read the temperature: better loud than hot
    start = float(cfg.get("start_temp", 55))
    full = max(start + 1, float(cfg.get("full_temp", 70)))
    if temp < start - (HYSTERESIS_C if running else 0):
        return 0.0
    if temp >= full:
        return hi
    frac = max(0.0, (temp - start) / (full - start))
    return round(lo + (hi - lo) * frac, 1)


class FanOutput:
    """0-1 duty cycle on a pin (or just on/off without PWM). Mock keeps the value for the
    settings page and tests."""

    def __init__(self, pin: int, frequency: int = 1000, invert: bool = False, pwm: bool = True):
        self.pin, self.frequency, self.invert, self.pwm = pin, frequency, invert, pwm
        self.value = 0.0

    def set(self, duty: float) -> None:
        duty = max(0.0, min(1.0, duty))
        self.value = duty if self.pwm else (1.0 if duty > 0 else 0.0)

    def level(self) -> str:
        """What the pin is doing, for the settings page: high, low or PWM n%."""
        if self.pwm and 0 < self.value < 1:
            return f"PWM {round(self.value * 100)}%" + (" (inverted)" if self.invert else "")
        on = self.value > 0
        return ("high" if on != self.invert else "low") + f" ({'on' if on else 'off'})"

    def close(self) -> None:
        self.value = 0.0


class GpioFan(FanOutput):
    def __init__(self, pin: int, frequency: int = 1000, invert: bool = False, pwm: bool = True):
        super().__init__(pin, frequency, invert, pwm)
        if pwm:
            from gpiozero import PWMOutputDevice  # type: ignore
            self._dev = PWMOutputDevice(pin, active_high=not invert, initial_value=0, frequency=frequency)
        else:
            from gpiozero import DigitalOutputDevice  # type: ignore
            self._dev = DigitalOutputDevice(pin, active_high=not invert, initial_value=False)

    def set(self, duty: float) -> None:
        super().set(duty)
        if self.pwm:
            self._dev.value = self.value
        else:
            self._dev.value = 1 if self.value > 0 else 0

    def close(self) -> None:
        try:
            self._dev.value = 0
            self._dev.close()
        finally:
            super().close()


class FanController:
    """Reads the Pi's temperature every few seconds and sets the fan speed."""

    def __init__(self, out: FanOutput, cfg: Callable[[], dict], temp: Callable[[], float | None],
                 clock: Callable[[], float] = time.monotonic):
        self.out, self.cfg, self.temp, self.clock = out, cfg, temp, clock
        self.speed = 0.0  # what the fan is set to, 0-100
        self.last_temp: float | None = None
        self._kick_until = 0.0
        self._test_until = 0.0
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def step(self) -> float:
        now = self.clock()
        self.last_temp = self.temp()
        c = self.cfg()
        want = 100.0 if now < self._test_until else target_speed(c, self.last_temp, self.speed > 0)
        if not self.out.pwm and want > 0:
            want = 100.0  # on/off: any demand means fully on
        if want > 0 and self.speed == 0 and want < 100:
            self._kick_until = now + KICK_S  # from rest: full power briefly so it starts
        self.speed = want
        self.out.set((100.0 if now < self._kick_until and want > 0 else want) / 100)
        return want

    def test(self, seconds: float = 5) -> None:
        self._test_until = self.clock() + seconds
        self.step()

    def start(self) -> None:
        def loop():
            while not self._stop.wait(0.5 if self.clock() < max(self._kick_until, self._test_until) else 5):
                try:
                    self.step()
                except Exception:
                    log.exception("fan step failed")
        self.step()
        self._thread = threading.Thread(target=loop, daemon=True, name="fan")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self.out.close()

    def status(self) -> dict:
        return {"speed": round(self.speed), "temperature_c": self.last_temp,
                "testing": self.clock() < self._test_until, "pwm": self.out.pwm, "pin": self.out.pin,
                "output": self.out.level()}
