#!/usr/bin/env python3
"""Render print-templates/icons/*.svg to 1-bit PNGs for the print kit (PRINT_TEMPLATES 4.6).

Run on a dev machine (needs cairosvg); the Pi only loads the PNGs:

    .venv/bin/python tools/build_icons.py

The d50 pattern fill is not scaled with the icon: each SVG is rendered twice (pattern as white,
pattern as black) and the pattern area is refilled with the true 4 x 4-dot d50 tile, so heavy
cloud reads as the same dither at every size.
"""
from __future__ import annotations

import io
import re
import sys
from pathlib import Path

import cairosvg
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "print-templates" / "icons"
OUT = ROOT / "backend" / "walloftext" / "assets" / "wx"
SIZES = (168, 104, 96, 52, 44, 40)


def _render(svg: str, size: int) -> np.ndarray:
    png = cairosvg.svg2png(bytestring=svg.encode(), output_width=size, output_height=size, background_color="white")
    g = np.asarray(Image.open(io.BytesIO(png)).convert("L"))
    return g < 128  # True = ink


def build(path: Path, size: int) -> Image.Image:
    svg = re.sub(r"<metadata>.*?</metadata>", "", path.read_text(), flags=re.S)
    ink = _render(svg.replace("url(#wx50)", "#FFFFFF"), size)
    filled = _render(svg.replace("url(#wx50)", "#000000"), size)
    pattern = filled & ~ink
    yy, xx = np.mgrid[0:size, 0:size]
    d50 = ((yy % 4) < 2) == ((xx % 4) < 2)
    black = ink | (pattern & d50)
    return Image.fromarray(np.where(black, 0, 255).astype(np.uint8)).convert("1", dither=Image.Dither.NONE)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    for svg in sorted(SRC.glob("*.svg")):
        for s in SIZES:
            build(svg, s).save(OUT / f"{svg.stem}-{s}.png", optimize=True)
    print(f"wrote {len(list(OUT.glob('*.png')))} icons to {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
