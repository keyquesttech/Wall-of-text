"""Printer driver interface (section 6.2). Phase 2 adds the queue worker."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol

from PIL import Image

WIDTH = 384


class Cancelled(Exception):
    """Raised by a driver between bands when the job was cancelled."""


@dataclass
class PrinterStatus:
    state: str  # "ready" | "offline" | "paper_out" | "printing"
    detail: str | None = None

    def to_dict(self) -> dict:
        return {"state": self.state, "detail": self.detail}


class Printer(Protocol):
    def print_bitmap(self, img: Image.Image, copies: int = 1, extra_feed: int = 0,
                     on_progress: Callable[[int], None] | None = None,
                     should_cancel: Callable[[], bool] | None = None, density: int | None = None) -> None: ...
    def test_page(self) -> None: ...
    def status(self) -> PrinterStatus: ...


def raster_bytes(img: Image.Image, band_rows: int = 24) -> list[bytes]:
    """1-bit image → list of `GS v 0` raster bands. Black pixels print."""
    if img.mode != "1":
        img = img.convert("1")
    if img.width != WIDTH:
        raise ValueError(f"bitmap must be {WIDTH} px wide, got {img.width}")
    width_bytes = WIDTH // 8
    # PIL mode "1": 0 = black. Printer: bit 1 = dot. Invert.
    data = bytes(b ^ 0xFF for b in img.tobytes())
    bands = []
    for top in range(0, img.height, band_rows):
        rows = min(band_rows, img.height - top)
        chunk = data[top * width_bytes:(top + rows) * width_bytes]
        header = b"\x1dv0\x00" + bytes([width_bytes & 0xFF, width_bytes >> 8, rows & 0xFF, rows >> 8])
        bands.append(header + chunk)
    return bands
