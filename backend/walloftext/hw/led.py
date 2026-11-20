"""Panel LED: single colour, brightness 0-100 %, patterns per event (section 8)."""
from __future__ import annotations

import logging

log = logging.getLogger(__name__)

PATTERNS = ("off", "solid", "slow_pulse", "blink", "triple_blink")


class Led:
    def __init__(self):
        self.pattern = "off"
        self.brightness = 0.6

    def set(self, pattern: str, brightness: float | None = None) -> None:
        if pattern not in PATTERNS:
            raise ValueError(pattern)
        if brightness is not None:
            self.brightness = max(0.0, min(1.0, brightness))
        self.pattern = pattern
        self._apply()

    def _apply(self) -> None:
        log.debug("led %s @ %.0f%%", self.pattern, self.brightness * 100)

    def close(self) -> None:
        pass


class MockLed(Led):
    pass


class GpioLed(Led):
    def __init__(self, pin: int):
        super().__init__()
        from gpiozero import PWMLED  # type: ignore

        self._led = PWMLED(pin)

    def _apply(self) -> None:
        b, led = self.brightness, self._led
        if self.pattern == "off":
            led.off()
        elif self.pattern == "solid":
            led.value = b
        elif self.pattern == "slow_pulse":
            led.pulse(fade_in_time=1.5, fade_out_time=1.5)
        elif self.pattern == "blink":
            led.blink(on_time=0.5, off_time=0.5)
        elif self.pattern == "triple_blink":
            led.blink(on_time=0.08, off_time=0.08, n=3, background=True)

    def close(self) -> None:
        self._led.close()
