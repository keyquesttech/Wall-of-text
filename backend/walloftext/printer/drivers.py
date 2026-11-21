"""`MockPrinter` writes PNG + raw bytes; `EscposUsbPrinter` writes to the USB node.

The real driver is deliberately small: Phase 0 decides band size, pause and
the density command. Until then it uses conservative defaults: `ESC 7` heat
settings (Adafruit's command set), 24-row bands, 50 ms pause.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Callable

from PIL import Image, ImageDraw

from .base import WIDTH, Cancelled, PrinterStatus, raster_bytes

log = logging.getLogger(__name__)

INIT = b"\x1b@"


def feed(lines: int) -> bytes:
    return b"\x1bd" + bytes([max(0, min(255, lines))])


def heat(density: int) -> bytes:
    """Adafruit thermal: ESC 7 n1 n2 n3 = max heating dots, heat time, heat interval."""
    return b"\x1b7" + bytes([11, max(3, min(255, density)), 40])


def _test_image() -> Image.Image:
    img = Image.new("1", (WIDTH, 200), 1)
    d = ImageDraw.Draw(img)
    for x in range(0, WIDTH, 16):
        d.line([(x, 0), (x, 40)], fill=0)
    d.rectangle([0, 60, WIDTH - 1, 100], outline=0)
    for i in range(8):
        d.rectangle([i * 48, 120, i * 48 + 40, 160], fill=0 if i % 2 == 0 else 1, outline=0)
    d.text((10, 175), "Wall of Text test page", fill=0)
    return img


class MockPrinter:
    def __init__(self, out_dir: Path, band_rows: int = 24, band_delay_s: float | None = None):
        self.out_dir = Path(out_dir)
        self.band_rows = band_rows
        self.band_delay_s = band_delay_s if band_delay_s is not None else float(
            os.environ.get("WOT_MOCK_BAND_DELAY", "0"))
        self.printed: list[Path] = []
        self.offline = False

    def print_bitmap(self, img: Image.Image, copies: int = 1, extra_feed: int = 0,
                     on_progress: Callable[[int], None] | None = None,
                     should_cancel: Callable[[], bool] | None = None, density: int | None = None) -> None:
        if self.offline:
            raise OSError("mock printer offline")
        self.out_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        bands = raster_bytes(img, self.band_rows)
        total = len(bands) * copies
        raw = bytearray(INIT + heat(density or 120))
        done = 0
        for _ in range(copies):
            for band in bands:
                if should_cancel and should_cancel():
                    raw += feed(3)
                    (self.out_dir / f"{stamp}-cancelled.bin").write_bytes(bytes(raw))
                    raise Cancelled()
                raw += band
                done += 1
                if self.band_delay_s:
                    time.sleep(self.band_delay_s)
                if on_progress:
                    on_progress(int(done * 100 / total))
        raw += feed(3 + extra_feed)
        png = self.out_dir / f"{stamp}.png"
        img.convert("1").save(png)
        (self.out_dir / f"{stamp}.bin").write_bytes(bytes(raw))
        self.printed.append(png)
        log.info("mock printed %s (%d rows x %d)", png.name, img.height, copies)

    def test_page(self) -> None:
        self.print_bitmap(_test_image())

    def status(self) -> PrinterStatus:
        return PrinterStatus("offline" if self.offline else "ready")


# Measured motor speed (Phase 0): ~62 dot rows/s at the default heat; a feed line is ~24 dot rows.
ROWS_PER_S = 60.0
FEED_DOT_ROWS = 24

# Status bytes (Phase 0, Gprinter CSN-A4 0fe6:811e): DLE EOT 4 = 0x12 with paper, 0x72 with the lid
# open / no paper. Bits 0x60 = "roll paper end"; bits 0x0C = "near end" (not seen on this printer).
DLE_EOT_PAPER = b"\x10\x04\x04"
PAPER_END_BITS = 0x60
NEAR_END_BITS = 0x0C


def parse_paper_status(byte: int) -> str:
    if byte & PAPER_END_BITS:
        return "paper_out"
    return "ready"


class EscposUsbPrinter:
    """Raw ESC/POS raster over the usblp node.

    Phase 0 on the CSN-A4: `GS v 0` raster works; pausing between bands causes faint streaks
    (the head cools), and the motor limits speed to ~60 dot rows/s anyway, so bands are sent
    back to back (128 rows). "Careful" speed uses smaller bands with a short pause for long, dense
    prints. Both `ESC 7` heat time and `DC2 #` change darkness; darkness uses `ESC 7`.
    The printer answers `DLE EOT 4`, so paper-out is detected, not user-reported.
    """

    detects_paper = True

    def __init__(self, device: str, band_rows: int = 128, band_pause_s: float = 0.0):
        self.device = device
        self.band_rows = band_rows
        self.band_pause_s = band_pause_s
        self._lock = threading.Lock()
        self._cache: tuple[float, PrinterStatus] | None = None

    def set_speed(self, speed: str) -> None:
        if speed == "slow":
            self.band_rows, self.band_pause_s = 48, 0.02
        else:
            self.band_rows, self.band_pause_s = 128, 0.0

    def _node(self) -> str | None:
        for cand in (self.device, "/dev/usb/lp0", "/dev/ttyUSB0"):
            if cand and os.path.exists(cand):
                return cand
        return None

    def query_paper(self, node: str, timeout: float = 0.6) -> str | None:
        """Ask the printer for its paper sensor. None if it doesn't answer."""
        import select

        fd = os.open(node, os.O_RDWR | os.O_NONBLOCK)
        try:
            # drain anything left over from earlier queries
            while select.select([fd], [], [], 0)[0]:
                if not os.read(fd, 64):
                    break
            os.write(fd, DLE_EOT_PAPER)
            r, _, _ = select.select([fd], [], [], timeout)
            if not r:
                return None
            data = os.read(fd, 16)
            return parse_paper_status(data[-1]) if data else None
        except BlockingIOError:
            return None
        finally:
            os.close(fd)

    def print_bitmap(self, img: Image.Image, copies: int = 1, extra_feed: int = 0,
                     on_progress: Callable[[int], None] | None = None,
                     should_cancel: Callable[[], bool] | None = None, density: int | None = None) -> None:
        """Send the raster, then wait until the paper has physically come out.

        The printer buffers about a slip's worth of data, so writes finish long before the paper
        does. Progress (and so the LED's "printing" pattern and the app's progress bar) follows the
        measured motor speed instead of the bytes sent (Phase 0: ~62 dot rows/s)."""
        node = self._node()
        if not node:
            raise FileNotFoundError("printer device node not found")
        bands = raster_bytes(img, self.band_rows)
        total_rows = img.height * copies + FEED_DOT_ROWS * (3 + extra_feed)
        expected = total_rows / ROWS_PER_S
        t0 = time.monotonic()
        last = [-1]

        def report(final: bool = False) -> None:
            if not on_progress:
                return
            p = 100 if final else min(99, int((time.monotonic() - t0) * 100 / expected))
            if p != last[0]:
                last[0] = p
                on_progress(p)

        with self._lock, open(node, "wb", buffering=0) as fh:
            fh.write(INIT)
            if density:
                fh.write(heat(density))
            for _ in range(copies):
                for band in bands:
                    if should_cancel and should_cancel():
                        fh.write(feed(3))
                        raise Cancelled()
                    fh.write(band)
                    report()
                    if self.band_pause_s:
                        time.sleep(self.band_pause_s)
            fh.write(feed(3 + extra_feed))
            # the rest is already in the printer's buffer: wait for the paper, not the bytes
            while time.monotonic() - t0 < expected:
                report()
                time.sleep(0.1)
        report(final=True)
        self._cache = None

    def test_page(self) -> None:
        self.print_bitmap(_test_image())

    def status(self) -> PrinterStatus:
        node = self._node()
        if not node:
            self._cache = None
            return PrinterStatus("offline")
        now = time.monotonic()
        if self._cache and now - self._cache[0] < 2.0:
            return self._cache[1]
        if not self._lock.acquire(blocking=False):  # printing: don't talk over the raster data
            return PrinterStatus("ready")
        try:
            paper = self.query_paper(node)
        except OSError as exc:
            log.warning("printer status query failed: %s", exc)
            paper = None
        finally:
            self._lock.release()
        st = PrinterStatus(paper or "ready", None if paper else "no status reply")
        self._cache = (now, st)
        return st
