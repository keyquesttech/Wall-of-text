"""Arcade button gestures (section 8) and the reserved 30 s Wi-Fi reset hold.

`GestureDetector` is pure logic fed with press/release timestamps; the GPIO
and mock buttons only feed it. Timings: 50 ms debounce, 300 ms double-press
window, long press at 800 ms, reset at 30 s (fires on release after 30 s).
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Callable

log = logging.getLogger(__name__)

DEBOUNCE_S = 0.05
DOUBLE_WINDOW_S = 0.30
LONG_S = 0.80
RESET_S = 30.0

Gesture = str  # "single" | "double" | "long" | "reset"


class GestureDetector:
    def __init__(self, emit: Callable[[Gesture], None], reset_armed: Callable[[], None] | None = None,
                 clock: Callable[[], float] = time.monotonic):
        self.emit = emit
        self.reset_armed = reset_armed or (lambda: None)
        self.clock = clock
        self._down_at: float | None = None
        self._last_edge = -1.0
        self._pending_single_at: float | None = None
        self._armed = False

    def press(self, t: float | None = None) -> None:
        t = self.clock() if t is None else t
        if t - self._last_edge < DEBOUNCE_S:
            return
        self._last_edge = t
        self._down_at = t
        self._armed = False

    def release(self, t: float | None = None) -> None:
        t = self.clock() if t is None else t
        if self._down_at is None or t - self._last_edge < DEBOUNCE_S:
            return
        self._last_edge = t
        held = t - self._down_at
        self._down_at = None
        if held >= RESET_S:
            self._pending_single_at = None
            self.emit("reset")
        elif held >= LONG_S:
            self._pending_single_at = None
            self.emit("long")
        elif self._pending_single_at is not None and t - self._pending_single_at <= DOUBLE_WINDOW_S:
            self._pending_single_at = None
            self.emit("double")
        else:
            self._pending_single_at = t

    def poll(self, t: float | None = None) -> None:
        """Call often (every ~20 ms). Resolves single presses and arms the reset."""
        t = self.clock() if t is None else t
        if self._pending_single_at is not None and t - self._pending_single_at > DOUBLE_WINDOW_S:
            self._pending_single_at = None
            self.emit("single")
        if self._down_at is not None and not self._armed and t - self._down_at >= RESET_S:
            self._armed = True
            self.reset_armed()  # LED fast triple blink: release now to reset


class GpioButton:
    def __init__(self, pin: int, detector: GestureDetector):
        from gpiozero import Button  # type: ignore

        self.detector = detector
        self._btn = Button(pin, pull_up=True, bounce_time=None)
        self._btn.when_pressed = lambda: detector.press()
        self._btn.when_released = lambda: detector.release()
        self._stop = threading.Event()
        threading.Thread(target=self._poll, daemon=True, name="button-poll").start()

    def _poll(self) -> None:
        while not self._stop.wait(0.02):
            self.detector.poll()

    def close(self) -> None:
        self._stop.set()
        self._btn.close()


class MockButton:
    """Dev endpoint `POST /api/dev/button` fires gestures directly."""

    def __init__(self, detector: GestureDetector):
        self.detector = detector

    def fire(self, gesture: Gesture) -> None:
        self.detector.emit(gesture)

    def close(self) -> None:
        pass
