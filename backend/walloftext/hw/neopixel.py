"""WS2812 ("NeoPixel") LED strips: what they show, and how the colours reach them.

Driven from an SPI data pin (GPIO10 = SPI0, GPIO20 = SPI1) at 2.4 MHz: every WS2812 bit
becomes 3 SPI bits (1 → 110, 0 → 100), which gives the 0.4/0.8 µs pulses the LEDs expect.
This needs no root (unlike the PWM/PCM drivers), only SPI switched on (deploy/enable_spi.sh)
and the service user in the `spi` group.

Each status event (idle, printing, message waiting, paper out, error, setup) picks an effect
and up to three colours. Effects are pure functions of time, so the mock shows exactly what
a real strip would.
"""
from __future__ import annotations

import colorsys
import logging
import math
import random
import threading
import time
from typing import Callable

import numpy as np

log = logging.getLogger(__name__)

EFFECTS = ("off", "solid", "breathe", "blink", "chase", "wipe", "rainbow", "sparkle", "progress")
EVENTS = ("idle", "printing", "message_waiting", "paper_out", "error", "setup")
SPI_HZ = 2_400_000
MAX_LEDS = 450  # 9 SPI bytes per LED in one 4096-byte spidev transfer
RESET_BYTES = 15  # > 50 µs low at 2.4 MHz
FPS = 30

# byte → 3 SPI bytes: each of the 8 bits becomes 1→110 or 0→100 (24 bits)
_LUT = np.zeros((256, 3), dtype=np.uint8)
for _b in range(256):
    bits = 0
    for _i in range(7, -1, -1):
        bits = (bits << 3) | (0b110 if (_b >> _i) & 1 else 0b100)
    _LUT[_b] = [(bits >> 16) & 0xFF, (bits >> 8) & 0xFF, bits & 0xFF]


def hex_rgb(h: str) -> tuple[int, int, int]:
    h = (h or "#000000").lstrip("#")
    try:
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    except (ValueError, IndexError):
        return 0, 0, 0


def encode(pixels: np.ndarray, order: str = "GRB") -> bytes:
    """(n, 3) RGB uint8 → the SPI byte stream, in the strip's colour order."""
    idx = ["RGB".index(c) for c in order.upper() if c in "RGB"][:3] or [1, 0, 2]
    ordered = pixels[:, idx].astype(np.uint8).reshape(-1)
    return bytes(RESET_BYTES) + _LUT[ordered].reshape(-1).tobytes() + bytes(RESET_BYTES)


def _scale(c: tuple[int, int, int], k: float) -> tuple[int, int, int]:
    k = max(0.0, min(1.0, k))
    return (int(c[0] * k), int(c[1] * k), int(c[2] * k))


def render(effect: str, colors: list[tuple[int, int, int]], n: int, t: float,
           speed: float = 50, progress: float = 0.0, seed: int = 0) -> list[tuple[int, int, int]]:
    """One frame: n RGB tuples for `effect` at time t (seconds). speed 1-100."""
    if n <= 0:
        return []
    c0 = colors[0] if colors else (255, 255, 255)
    c1 = colors[1] if len(colors) > 1 else (0, 0, 0)
    rate = 0.2 + 2.8 * (max(1.0, min(100.0, speed)) / 100)  # cycles per second-ish
    off = (0, 0, 0)
    if effect == "off":
        return [off] * n
    if effect == "solid":
        return [c0] * n
    if effect == "breathe":
        k = 0.08 + 0.92 * (0.5 - 0.5 * math.cos(2 * math.pi * t * rate / 4))
        return [_scale(c0, k)] * n
    if effect == "blink":
        return [c0 if (t * rate) % 1 < 0.5 else c1] * n
    if effect == "chase":
        step = int(t * rate * 6)
        cols = colors or [c0]
        return [cols[((i + step) // 3) % len(cols)] if (i + step) % 3 == 0 else off for i in range(n)]
    if effect == "wipe":
        cols = colors or [c0]
        pos = int(t * rate * n / 2)
        lap, at = divmod(pos, n)
        cur, prev = cols[lap % len(cols)], cols[(lap - 1) % len(cols)] if lap else off
        return [cur if i <= at else prev for i in range(n)]
    if effect == "rainbow":
        out = []
        for i in range(n):
            r, g, b = colorsys.hsv_to_rgb((i / n + t * rate / 5) % 1.0, 1.0, 1.0)
            out.append((int(r * 255), int(g * 255), int(b * 255)))
        return out
    if effect == "sparkle":
        rng = random.Random(int(t * rate * 8) * 7919 + seed)
        base = _scale(c1, 0.25)
        cols = colors[:1] + colors[2:] if len(colors) > 2 else [c0]
        return [rng.choice(cols) if rng.random() < 0.08 else base for _ in range(n)]
    if effect == "progress":
        lit = progress * n
        out = []
        for i in range(n):
            if i + 1 <= lit:
                out.append(c0)
            elif i < lit:
                out.append(_scale(c0, lit - i))
            else:
                out.append(_scale(c1, 0.3))
        return out
    return [off] * n


class Strip:
    """Mock strip: keeps the last frame so the settings page can show it."""

    def __init__(self, pin: int, count: int, order: str = "GRB"):
        self.pin, self.count, self.order = pin, min(int(count), MAX_LEDS), order
        self.frame: list[tuple[int, int, int]] = [(0, 0, 0)] * self.count

    def show(self, pixels: list[tuple[int, int, int]]) -> None:
        self.frame = pixels

    def close(self) -> None:
        self.frame = [(0, 0, 0)] * self.count


class SpiStrip(Strip):
    def __init__(self, pin: int, count: int, order: str = "GRB"):
        super().__init__(pin, count, order)
        import spidev  # type: ignore

        from .pins import STRIP_PINS
        bus = STRIP_PINS[pin]["bus"]
        self._spi = spidev.SpiDev()
        try:
            self._spi.open(bus, 0)
        except FileNotFoundError:
            raise RuntimeError("SPI is off. On the Pi run: sudo bash deploy/enable_spi.sh, then restart.") from None
        except PermissionError:
            raise RuntimeError("The app can't use SPI yet. Run the update again, then restart the Pi.") from None
        self._spi.max_speed_hz = SPI_HZ
        self._spi.mode = 0

    def show(self, pixels: list[tuple[int, int, int]]) -> None:
        super().show(pixels)
        self._spi.writebytes2(encode(np.array(pixels, dtype=np.uint8).reshape(-1, 3), self.order))

    def close(self) -> None:
        try:
            self.show([(0, 0, 0)] * self.count)
            self._spi.close()
        except Exception:
            pass


class NeoPixelController:
    """Picks the effect from the printer's state and animates every strip at ~30 fps."""

    def __init__(self, strips: list[Strip], cfg: Callable[[], dict], quiet: Callable[[], bool] = lambda: False,
                 clock: Callable[[], float] = time.monotonic):
        self.strips, self.cfg, self.quiet, self.clock = strips, cfg, quiet, clock
        self.event = "idle"
        self.progress = 0.0
        self.preview: tuple[str, float] | None = None  # (event, until): the settings page's Try button
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._quiet_cache = (0.0, False)

    def _is_quiet(self) -> bool:
        now = self.clock()
        if now - self._quiet_cache[0] > 10:
            try:
                self._quiet_cache = (now, bool(self.quiet()))
            except Exception:
                self._quiet_cache = (now, False)
        return self._quiet_cache[1]

    def current(self) -> tuple[str, dict]:
        ev = self.event
        if self.preview and self.clock() < self.preview[1]:
            ev = self.preview[0]
        c = self.cfg()
        return ev, (c.get("events") or {}).get(ev) or {"effect": "off", "colors": []}

    def frame(self, t: float | None = None) -> list[list[tuple[int, int, int]]]:
        t = self.clock() if t is None else t
        c = self.cfg()
        ev, e = self.current()
        bright = max(0, min(100, int(c.get("brightness", 40)))) / 100
        previewing = bool(self.preview and self.clock() < self.preview[1])
        if self._is_quiet() and not previewing:
            bright *= max(0, min(100, int(c.get("quiet_brightness", 10)))) / 100
        colors = [_scale(hex_rgb(x), bright) for x in (e.get("colors") or ["#ffffff"])][:3]
        scfg = c.get("strips") or []
        out = []
        for i, s in enumerate(self.strips):
            px = render(e.get("effect", "off"), colors, s.count, t, float(c.get("speed", 50)), self.progress, seed=i)
            reverse = bool(scfg[i].get("reverse")) if i < len(scfg) else False
            out.append(px[::-1] if reverse else px)
        return out

    def tick(self) -> None:
        for s, px in zip(self.strips, self.frame()):
            if px == s.frame:
                continue  # nothing changed: don't resend
            try:
                s.show(px)
            except Exception:
                log.exception("LED strip write failed")

    def on_event(self, name: str, data: dict, led_event: Callable[[], str]) -> None:
        if name == "progress":
            self.progress = max(0.0, min(1.0, float(data.get("progress", 0)) / 100))
        elif name == "printer" and data.get("state") != "printing":
            self.progress = 0.0
        self.event = led_event()

    def try_event(self, event: str, seconds: float = 6) -> None:
        self.preview = (event, self.clock() + seconds)

    def start(self) -> None:
        def loop():
            while not self._stop.wait(1 / FPS):
                self.tick()
        self.tick()
        self._thread = threading.Thread(target=loop, daemon=True, name="neopixel")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=1)
        for s in self.strips:
            s.close()
