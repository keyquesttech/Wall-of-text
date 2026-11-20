"""Built-in stickers for guest notes and Create, drawn as crisp 1-bit shapes."""
from __future__ import annotations

import math

from PIL import Image, ImageDraw

SIZE = 120


def _heart(d: ImageDraw.ImageDraw, s: int) -> None:
    r = s * 0.27
    d.ellipse([s * 0.5 - 2 * r, s * 0.18, s * 0.5, s * 0.18 + 2 * r], fill=0)
    d.ellipse([s * 0.5, s * 0.18, s * 0.5 + 2 * r, s * 0.18 + 2 * r], fill=0)
    d.polygon([(s * 0.5 - 2 * r + 2, s * 0.18 + r * 1.25), (s * 0.5 + 2 * r - 2, s * 0.18 + r * 1.25),
               (s * 0.5, s * 0.92)], fill=0)


def _star(d: ImageDraw.ImageDraw, s: int) -> None:
    pts = []
    for i in range(10):
        a = -math.pi / 2 + i * math.pi / 5
        r = s * 0.46 if i % 2 == 0 else s * 0.19
        pts.append((s / 2 + r * math.cos(a), s / 2 + r * math.sin(a) + 3))
    d.polygon(pts, fill=0)


def _smile(d: ImageDraw.ImageDraw, s: int) -> None:
    d.ellipse([4, 4, s - 4, s - 4], outline=0, width=7)
    d.ellipse([s * 0.32, s * 0.32, s * 0.42, s * 0.44], fill=0)
    d.ellipse([s * 0.58, s * 0.32, s * 0.68, s * 0.44], fill=0)
    d.arc([s * 0.26, s * 0.3, s * 0.74, s * 0.76], 20, 160, fill=0, width=7)


def _sun(d: ImageDraw.ImageDraw, s: int) -> None:
    c = s / 2
    d.ellipse([c - s * 0.2, c - s * 0.2, c + s * 0.2, c + s * 0.2], fill=0)
    for i in range(8):
        a = i * math.pi / 4
        d.line([(c + s * 0.28 * math.cos(a), c + s * 0.28 * math.sin(a)),
                (c + s * 0.45 * math.cos(a), c + s * 0.45 * math.sin(a))], fill=0, width=7)


def _flower(d: ImageDraw.ImageDraw, s: int) -> None:
    c = s / 2
    for i in range(6):
        a = i * math.pi / 3
        x, y = c + s * 0.22 * math.cos(a), c + s * 0.22 * math.sin(a)
        d.ellipse([x - s * 0.16, y - s * 0.16, x + s * 0.16, y + s * 0.16], outline=0, width=5)
    d.ellipse([c - s * 0.11, c - s * 0.11, c + s * 0.11, c + s * 0.11], fill=0)


def _note(d: ImageDraw.ImageDraw, s: int) -> None:
    d.ellipse([s * 0.14, s * 0.66, s * 0.38, s * 0.86], fill=0)
    d.ellipse([s * 0.58, s * 0.56, s * 0.82, s * 0.76], fill=0)
    d.line([(s * 0.36, s * 0.76), (s * 0.36, s * 0.16)], fill=0, width=7)
    d.line([(s * 0.8, s * 0.66), (s * 0.8, s * 0.08)], fill=0, width=7)
    d.polygon([(s * 0.33, s * 0.12), (s * 0.83, s * 0.04), (s * 0.83, s * 0.18), (s * 0.33, s * 0.26)], fill=0)


def _check(d: ImageDraw.ImageDraw, s: int) -> None:
    d.rounded_rectangle([6, 6, s - 6, s - 6], radius=18, outline=0, width=7)
    d.line([(s * 0.25, s * 0.52), (s * 0.43, s * 0.7), (s * 0.77, s * 0.3)], fill=0, width=10)


def _coffee(d: ImageDraw.ImageDraw, s: int) -> None:
    d.rounded_rectangle([s * 0.16, s * 0.38, s * 0.7, s * 0.9], radius=10, fill=0)
    d.arc([s * 0.58, s * 0.46, s * 0.88, s * 0.76], 270, 90, fill=0, width=7)
    for x in (0.3, 0.43, 0.56):
        d.arc([s * (x - 0.05), s * 0.08, s * (x + 0.05), s * 0.32], 90, 270, fill=0, width=4)


STICKERS = {"heart": _heart, "star": _star, "smile": _smile, "sun": _sun, "flower": _flower,
            "note": _note, "check": _check, "coffee": _coffee}


def sticker_image(name: str, size: int = SIZE) -> Image.Image:
    img = Image.new("1", (size, size), 1)
    d = ImageDraw.Draw(img)
    STICKERS.get(name, _star)(d, size)
    return img
