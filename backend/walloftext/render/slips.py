"""Setup slip and "Connected" slip (section 5.4). 384-px, 1-bit, no anti-aliasing.

The full block renderer arrives in Phase 2; these two slips are simple enough
to lay out by hand and share its font loading.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import segno
from PIL import Image, ImageDraw, ImageFont

from ..config import AP_ADDRESS, LOCAL_ADDRESS, PRODUCT_NAME, SETUP_SSID
from ..printer.base import WIDTH
from .kit.slip import with_end_mark

MARGIN = 8


def wifi_qr_payload(ssid: str, password: str) -> str:
    def esc(s: str) -> str:
        for ch in "\\;,\":":
            s = s.replace(ch, "\\" + ch)
        return s

    return f"WIFI:T:WPA;S:{esc(ssid)};P:{esc(password)};;"


@lru_cache(maxsize=32)
def _font(fonts_dir: str, name: str, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    path = Path(fonts_dir) / name
    try:
        return ImageFont.truetype(str(path), size)
    except OSError:
        return ImageFont.load_default(size)


class _Canvas:
    def __init__(self, fonts_dir: Path):
        self.fonts_dir = str(fonts_dir)
        self.img = Image.new("1", (WIDTH, 2000), 1)
        self.d = ImageDraw.Draw(self.img)
        self.d.fontmode = "1"  # anti-aliasing off: crisp dots
        self.y = MARGIN

    def font(self, size: int, bold: bool = False):
        return _font(self.fonts_dir, "SpaceMono-Bold.ttf" if bold else "SpaceMono-Regular.ttf", size)

    def text(self, s: str, size: int = 22, bold: bool = False, center: bool = False, gap: int = 6) -> None:
        f = self.font(size, bold)
        for line in self._wrap(s, f):
            w = self.d.textlength(line, font=f)
            x = (WIDTH - w) / 2 if center else MARGIN
            self.d.text((x, self.y), line, font=f, fill=0)
            self.y += size + gap

    def bar(self, s: str, size: int = 22) -> None:
        f = self.font(size, True)
        h = size + 14
        self.d.rectangle([0, self.y, WIDTH - 1, self.y + h], fill=0)
        w = self.d.textlength(s, font=f)
        self.d.text(((WIDTH - w) / 2, self.y + 4), s, font=f, fill=1)
        self.y += h + 10

    def rule(self) -> None:
        self.y += 6
        for x in range(MARGIN, WIDTH - MARGIN, 8):
            self.d.line([(x, self.y), (x + 3, self.y)], fill=0)
        self.y += 12

    def qr(self, payload: str, target: int = 240) -> None:
        q = segno.make(payload, error="m")
        modules = q.symbol_size(scale=1, border=2)[0]
        scale = max(1, target // modules)
        mat = [list(row) for row in q.matrix_iter(scale=scale, border=2)]
        size = len(mat)
        x0 = (WIDTH - size) // 2
        for yy, row in enumerate(mat):
            for xx, dark in enumerate(row):
                if dark:
                    self.img.putpixel((x0 + xx, self.y + yy), 0)
        self.y += size + 8

    def space(self, n: int) -> None:
        self.y += n

    def _wrap(self, s: str, f) -> list[str]:
        out: list[str] = []
        for para in s.split("\n"):
            words, line = para.split(" "), ""
            for w in words:
                cand = (line + " " + w).strip()
                if self.d.textlength(cand, font=f) <= WIDTH - 2 * MARGIN:
                    line = cand
                else:
                    if line:
                        out.append(line)
                    line = w
            out.append(line)
        return out

    def done(self) -> Image.Image:
        return with_end_mark(self.img.crop((0, 0, WIDTH, self.y + MARGIN)), 14)


def setup_slip(fonts_dir: Path, setup_wifi_password: str) -> Image.Image:
    """Network name, address and a Wi-Fi QR. No readable password (assumption 15)."""
    c = _Canvas(fonts_dir)
    c.bar(f"{PRODUCT_NAME} setup")
    c.text("1. Scan to join the setup Wi-Fi:", 20)
    c.space(4)
    c.qr(wifi_qr_payload(SETUP_SSID, setup_wifi_password))
    c.text(SETUP_SSID, 22, bold=True, center=True)
    c.rule()
    c.text("2. A setup page should open by itself. If it doesn't, open:", 20)
    c.text(f"http://{LOCAL_ADDRESS}", 22, bold=True)
    c.text(f"or http://{AP_ADDRESS}", 22, bold=True)
    c.rule()
    c.text("3. Pick your home Wi-Fi and enter its password.", 20)
    c.space(30)
    return c.done()


def connected_slip(fonts_dir: Path, ssid: str, ip: str | None) -> Image.Image:
    c = _Canvas(fonts_dir)
    c.bar("Connected")
    c.text(f"Connected to {ssid}.", 22)
    c.text("Open:", 20)
    c.text(f"http://{LOCAL_ADDRESS}", 24, bold=True)
    if ip:
        c.text(f"IP {ip}", 22)
        c.text(f"If that address doesn't open, use http://{ip}", 18)
    c.space(30)
    return c.done()
