"""Slip builder, header row, icons and the end mark (PRINT_TEMPLATES 4.1, 4.6, 4.7)."""
from __future__ import annotations

from datetime import datetime
from functools import lru_cache
from pathlib import Path

from PIL import Image

from . import tokens as T
from .nodes import Bitmap, Canvas, Col, Node, Row, Text, draw_line, measure

ASSETS = Path(__file__).resolve().parents[2] / "assets" / "wx"


# ----------------------------------------------------------------- icons --
@lru_cache(maxsize=128)
def icon_image(cond: str, size: int) -> Image.Image:
    if cond not in T.CONDITIONS:
        cond = "cloudy"
    if size not in T.ICON_SIZES:
        size = min(T.ICON_SIZES, key=lambda s: abs(s - size))
    return Image.open(ASSETS / f"{cond}-{size}.png").convert("1")


def Icon(cond: str, size: int) -> Bitmap:
    return Bitmap(icon_image(cond, size))


# ------------------------------------------------------------ date words --
def d_label(dt: datetime) -> str:
    """MON 23 NOV"""
    return f"{dt:%a} {dt.day} {dt:%b}".upper()


def dt_label(dt: datetime) -> str:
    """MON 23 NOV · 07:30"""
    return f"{d_label(dt)} · {dt:%H:%M}"


# ---------------------------------------------------------------- header --
def Header(left: str, right: str = "") -> Row:
    """`px b` source on the left, `px` context on the right (no footer anywhere)."""
    return Row((Text(left, T.PX_B), "auto"), (Text(right, T.PX, align="right", max_lines=2), "flex"),
               gap=10, align="top")


# ------------------------------------------------------------------ slip --
def render_slip(blocks: list[Node | None], gap: int = T.GAP) -> Image.Image:
    """384-dot canvas, 20-dot sides, 30 top, 36 bottom; height grows. No end mark here:
    the print pipeline adds it (one per printed copy)."""
    col = Col(*blocks, gap=gap)
    h = col.height(T.CONTENT)
    c = Canvas(T.WIDTH, T.TOP + h + T.BOTTOM)
    col.draw(c, T.SIDE, T.TOP, T.CONTENT, h)
    return c.img


# -------------------------------------------------------------- end mark --
END_H = 63
_END_LABEL = "END · TEAR HERE"


@lru_cache(maxsize=1)
def end_mark() -> Image.Image:
    """Full paper width, 63 dots: 3-dot rule; 17 space; tear line (2-dot dashed 6/5, inset 12) with a
    176 x 23 black tag carrying END · TEAR HERE; 17 space; 3-dot rule."""
    c = Canvas(T.WIDTH, END_H)
    c.rect(0, 0, T.WIDTH, 3)
    tag_y = 3 + 17
    c.hdash(12, T.WIDTH - 12, tag_y + 11 - 1, 2, 6, 5)
    tx = (T.WIDTH - 176) // 2
    c.rect(tx, tag_y, tx + 176, tag_y + 23)
    st = T.Style(T.JB_XBOLD, 12, 23, 0.2, True)
    lw = measure(_END_LABEL, st)
    f = st.font
    asc, desc = f.getmetrics()
    base = tag_y + (23 - (asc + desc)) / 2 + asc
    draw_line(c, _END_LABEL, st, (T.WIDTH - lw) / 2, base, 1)
    c.rect(0, END_H - 3, T.WIDTH, END_H)
    return c.img


def with_end_mark(img: Image.Image, space: int = 0) -> Image.Image:
    """Append `space` blank rows and the end mark under a 384-wide 1-bit image."""
    em = end_mark()
    out = Image.new("1", (T.WIDTH, img.height + space + em.height), 1)
    out.paste(img.convert("1"), (0, 0))
    out.paste(em, (0, img.height + space))
    return out
