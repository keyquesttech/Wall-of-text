"""`MockPrinter` writes PNG + raw bytes; `EscposUsbPrinter` writes to the USB node.

The real driver is deliberately small: Phase 0 decides band size, pause and
the density command. Until then it uses conservative defaults.
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

from .base import WIDTH, PrinterStatus, raster_bytes

log = logging.getLogger(__name__)

INIT = b"\x1b@"


def feed(lines: int) -> bytes:
    return b"\x1bd" + bytes([max(0, min(255, lines))])


def _test_image() -> Image.Image:
    img = Image.new("1", (WIDTH, 200), 1)
    d = ImageDraw.Draw(img)
    for x in range(0, WIDTH, 16):
        d.line([(x, 0), (x, 40)], fill=0)
    d.rectangle([0, 60, WIDTH - 1, 100], outline=0)
    d.text((10, 120), "Wall of Text test page", fill=0)
    return img


class MockPrinter:
    def __init__(self, out_dir: Path, band_rows: int = 24):
        self.out_dir = Path(out_dir)
        self.band_rows = band_rows
        self.printed: list[Path] = []
        self.offline = False

    def print_bitmap(self, img: Image.Image, copies: int = 1, extra_feed: int = 0,
                     on_progress: Callable[[int], None] | None = None) -> None:
        if self.offline:
            raise OSError("mock printer offline")
        self.out_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        bands = raster_bytes(img, self.band_rows)
        raw = INIT + b"".join(bands) * copies + feed(3 + extra_feed)
        png = self.out_dir / f"{stamp}.png"
        img.convert("1").save(png)
        (self.out_dir / f"{stamp}.bin").write_bytes(raw)
        self.printed.append(png)
        if on_progress:
            on_progress(100)
        log.info("mock printed %s (%d rows)", png.name, img.height)

    def test_page(self) -> None:
        self.print_bitmap(_test_image())

    def status(self) -> PrinterStatus:
        return PrinterStatus("offline" if self.offline else "ready")


class EscposUsbPrinter:
    def __init__(self, device: str, band_rows: int = 24, band_pause_s: float = 0.05):
        self.device = device
        self.band_rows = band_rows
        self.band_pause_s = band_pause_s
        self._lock = threading.Lock()

    def _node(self) -> str | None:
        for cand in (self.device, "/dev/usb/lp0", "/dev/ttyUSB0"):
            if cand and os.path.exists(cand):
                return cand
        return None

    def print_bitmap(self, img: Image.Image, copies: int = 1, extra_feed: int = 0,
                     on_progress: Callable[[int], None] | None = None) -> None:
        node = self._node()
        if not node:
            raise OSError("printer device node not found")
        bands = raster_bytes(img, self.band_rows)
        total = len(bands) * copies
        with self._lock, open(node, "wb", buffering=0) as fh:
            fh.write(INIT)
            done = 0
            for _ in range(copies):
                for band in bands:
                    fh.write(band)
                    done += 1
                    if on_progress:
                        on_progress(int(done * 100 / total))
                    time.sleep(self.band_pause_s)
            fh.write(feed(3 + extra_feed))

    def test_page(self) -> None:
        self.print_bitmap(_test_image())

    def status(self) -> PrinterStatus:
        # Paper-out readback depends on the Phase 0 spike; until then: node present = ready.
        return PrinterStatus("ready" if self._node() else "offline")
