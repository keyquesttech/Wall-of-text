"""Print kit layout primitives (PRINT_TEMPLATES 4).

Every node can say how tall it is at a given width (`height(w)`), how wide it
wants to be (`natural(w)`) and draw itself onto a shared 1-bit canvas
(`draw(c, x, y, w, h, ink)`). `ink` is 0 for black on paper and 1 for paper
white inside an inverted band. Text renders with anti-aliasing off.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Callable, Iterable

import numpy as np
import segno
from PIL import Image, ImageDraw, ImageOps

from ..fonts import _cmap
from . import tokens as T
from .tokens import Style

PLACEHOLDER = "\u0001"  # a character the font lacks: drawn as an empty box the width of a "0"


class Canvas:
    def __init__(self, w: int, h: int):
        self.img = Image.new("1", (w, max(1, h)), 1)
        self.d = ImageDraw.Draw(self.img)
        self.d.fontmode = "1"

    def rect(self, x0, y0, x1, y1, ink=0):
        """Filled rectangle, inclusive-exclusive box (x1, y1 not drawn)."""
        if x1 > x0 and y1 > y0:
            self.d.rectangle([x0, y0, x1 - 1, y1 - 1], fill=ink)

    def frame(self, x, y, w, h, b, ink=0):
        self.rect(x, y, x + w, y + b, ink)
        self.rect(x, y + h - b, x + w, y + h, ink)
        self.rect(x, y, x + b, y + h, ink)
        self.rect(x + w - b, y, x + w, y + h, ink)

    def hdash(self, x0, x1, y, thick, on, off, ink=0):
        x = x0
        while x < x1:
            self.rect(x, y, min(x + on, x1), y + thick, ink)
            x += on + off

    def vdash(self, x, y0, y1, thick, on, off, ink=0):
        y = y0
        while y < y1:
            self.rect(x, y, x + thick, min(y + on, y1), ink)
            y += on + off

    def tone(self, tone, x, y, w, h, ink=0):
        if w <= 0 or h <= 0:
            return
        m = T.tone_mask(tone, x, y, w, h)
        mask = Image.fromarray((m * 255).astype(np.uint8), "L")
        self.img.paste(ink, (x, y, x + w, y + h), mask)

    def bitmap(self, img: Image.Image, x, y, ink=0):
        """Paste the black dots of a 1-bit image in `ink`; white stays transparent."""
        mask = ImageOps.invert(img.convert("L"))
        self.img.paste(ink, (x, y, x + img.width, y + img.height), mask)


class Node:
    mt = 0  # extra space above this node inside a Col (may be negative)

    def height(self, w: int) -> int:
        raise NotImplementedError

    def natural(self, w: int) -> int:
        return w

    def draw(self, c: Canvas, x: int, y: int, w: int, h: int, ink: int = 0) -> None:
        raise NotImplementedError

    def m(self, top: int) -> "Node":
        self.mt = top
        return self


# ------------------------------------------------------------------ text --
@lru_cache(maxsize=16)
def _covers(file: str) -> frozenset[int]:
    return _cmap(str(T.fonts_dir() / file))


def clean(text: str, style: Style) -> str:
    from ..document import _EMOJI_DROP, is_emoji

    text = _EMOJI_DROP.sub("", str(text).replace("\r\n", "\n").replace("\t", " "))
    if style.upper:
        text = text.upper()
    cov = _covers(style.file)
    if not cov:
        return text
    return "".join(ch if ch == "\n" or ord(ch) in cov or is_emoji(ch) else PLACEHOLDER for ch in text)


def _has_emoji(s: str) -> bool:
    from ..document import is_emoji

    return any(is_emoji(c) for c in s)


def _char_len(ch: str, st: Style) -> float:
    from ..document import emoji_font, is_emoji

    if ch == PLACEHOLDER:
        return st.font.getlength("0")
    return (emoji_font(st.size) if is_emoji(ch) else st.font).getlength(ch)


def measure(s: str, st: Style) -> float:
    if not s:
        return 0.0
    if _has_emoji(s):
        return sum(_char_len(c, st) for c in s) + st.tracking * (len(s) - 1)
    f = st.font
    return f.getlength(s.replace(PLACEHOLDER, "0")) + st.tracking * (len(s) - 1)


def wrap(text: str, st: Style, width: int) -> list[str]:
    lines: list[str] = []
    for para in text.split("\n"):
        words = para.split(" ")
        line = ""
        for word in words:
            cand = f"{line} {word}" if line else word
            if measure(cand, st) <= width:
                line = cand
                continue
            if line:
                lines.append(line)
            line = word
            while measure(line, st) > width and len(line) > 1:  # a word longer than the line
                cut = len(line) - 1
                while cut > 1 and measure(line[:cut], st) > width:
                    cut -= 1
                lines.append(line[:cut])
                line = line[cut:]
        lines.append(line)
    return lines


def _ellipsis(line: str, st: Style, width: int) -> str:
    words = line.split(" ")
    while words:
        cand = " ".join(words).rstrip(" ,.;:·-") + "…"
        if measure(cand, st) <= width:
            return cand
        if len(words) == 1:
            w = words[0]
            while w and measure(w + "…", st) > width:
                w = w[:-1]
            return w + "…"
        words.pop()
    return "…"


def draw_line(c: Canvas, s: str, st: Style, x: float, baseline: float, ink: int) -> None:
    f = st.font
    emoji = _has_emoji(s)
    if not st.tracking and PLACEHOLDER not in s and not emoji:
        c.d.text((round(x), round(baseline)), s, font=f, fill=ink, anchor="ls")
        return
    if emoji:
        from ..document import emoji_font, is_emoji

        cx = x
        for ch in s:
            if is_emoji(ch):
                for dx in (0, 1):
                    c.d.text((round(cx) + dx, round(baseline)), ch, font=emoji_font(st.size), fill=ink, anchor="ls")
            elif ch == PLACEHOLDER:
                c.d.rectangle([round(cx + 1), round(baseline - f.getmetrics()[0] * 0.7), round(cx + f.getlength("0") - 2),
                               round(baseline - 1)], outline=ink, width=2)
            elif ch != " ":
                c.d.text((round(cx), round(baseline)), ch, font=f, fill=ink, anchor="ls")
            cx += _char_len(ch, st) + st.tracking
        return
    for i, ch in enumerate(s):
        cx = x + f.getlength(s[:i].replace(PLACEHOLDER, "0")) + i * st.tracking
        if ch == PLACEHOLDER:
            bw = f.getlength("0")
            asc = f.getmetrics()[0]
            top = baseline - asc * 0.7
            c.d.rectangle([round(cx + 1), round(top), round(cx + bw - 2), round(baseline - 1)], outline=ink, width=2)
        elif ch != " ":
            c.d.text((round(cx), round(baseline)), ch, font=f, fill=ink, anchor="ls")


class Text(Node):
    def __init__(self, text: str, style: Style = T.T_M, align: str = "left", max_lines: int | None = None,
                 ellipsis: bool = True):
        self.st = style
        self.text = clean(text, style)
        self.align = align
        self.max_lines = max_lines
        self.ellipsis = ellipsis
        self._cache: dict[int, list[str]] = {}

    def lines(self, w: int) -> list[str]:
        if w not in self._cache:
            ls = wrap(self.text, self.st, w)
            if self.max_lines and len(ls) > self.max_lines:
                ls = ls[: self.max_lines]
                if self.ellipsis:
                    ls[-1] = _ellipsis(ls[-1], self.st, w)
            self._cache[w] = ls
        return self._cache[w]

    def height(self, w):
        return len(self.lines(w)) * self.st.lh

    def natural(self, w):
        return min(w, int(np.ceil(max((measure(s, self.st) for s in self.lines(w)), default=0))))

    def draw(self, c, x, y, w, h, ink=0):
        f = self.st.font
        asc, desc = f.getmetrics()
        lh = self.st.lh
        for i, s in enumerate(self.lines(w)):
            lw = measure(s, self.st)
            if self.align == "center":
                lx = x + (w - lw) / 2
            elif self.align == "right":
                lx = x + w - lw
            else:
                lx = x
            base = y + i * lh + (lh - (asc + desc)) / 2 + asc
            draw_line(c, s, self.st, lx, base, ink)


# ---------------------------------------------------------------- layout --
class Spacer(Node):
    def __init__(self, h: int, w: int = 0):
        self.h, self.w = h, w

    def height(self, w):
        return self.h

    def natural(self, w):
        return min(w, self.w)

    def draw(self, c, x, y, w, h, ink=0):
        pass


class Col(Node):
    def __init__(self, *children: Node | None, gap: int = 0, align: str = "stretch"):
        self.children = [ch for ch in children if ch is not None]
        self.gap = gap
        self.align = align

    def height(self, w):
        if not self.children:
            return 0
        return sum(ch.height(w) for ch in self.children) + sum(ch.mt for ch in self.children[1:]) \
            + self.gap * (len(self.children) - 1)

    def natural(self, w):
        return max((ch.natural(w) for ch in self.children), default=0)

    def draw(self, c, x, y, w, h, ink=0):
        cy = y
        for i, ch in enumerate(self.children):
            if i:
                cy += self.gap + ch.mt
            ch_h = ch.height(w)
            if self.align == "stretch":
                ch.draw(c, x, cy, w, ch_h, ink)
            else:
                nw = ch.natural(w)
                cx = x + (w - nw) // 2 if self.align == "center" else x + w - nw if self.align == "right" else x
                ch.draw(c, cx, cy, nw, ch.height(nw), ink)
            cy += ch_h


class Row(Node):
    """Items are nodes or (node, spec): spec is an int width, "auto" (natural width) or "flex"."""

    def __init__(self, *items, gap: int = 10, align: str = "center", justify: str = "start"):
        self.items = [(it, "auto") if isinstance(it, Node) else it for it in items if it is not None]
        self.items = [(n, s) for n, s in self.items if n is not None]
        self.gap = gap
        self.align = align
        self.justify = justify

    def _widths(self, w: int) -> list[int]:
        avail = w - self.gap * (len(self.items) - 1)
        widths: list[int | None] = []
        for n, s in self.items:
            if isinstance(s, int):
                widths.append(s)
                avail -= s
            else:
                widths.append(None)
        for i, (n, s) in enumerate(self.items):
            if s == "auto":
                widths[i] = n.natural(max(0, avail))
                avail -= widths[i]
        flex = [i for i, (n, s) in enumerate(self.items) if s == "flex"]
        for k, i in enumerate(flex):
            share = max(0, avail) // len(flex) + (1 if k < max(0, avail) % len(flex) else 0)
            widths[i] = share
        return [int(x or 0) for x in widths]

    def height(self, w):
        return max((n.height(cw) for (n, _), cw in zip(self.items, self._widths(w))), default=0)

    def natural(self, w):
        if any(s == "flex" for _, s in self.items):
            return w
        return min(w, sum(self._widths(w)) + self.gap * (len(self.items) - 1))

    def draw(self, c, x, y, w, h, ink=0):
        widths = self._widths(w)
        used = sum(widths) + self.gap * (len(widths) - 1)
        extra = max(0, w - used)
        gap = self.gap
        cx = x
        if self.justify == "between" and len(widths) > 1:
            gap = self.gap + extra / (len(widths) - 1)
        elif self.justify == "center":
            cx = x + extra // 2
        elif self.justify == "end":
            cx = x + extra
        rh = h
        for (n, _), cw in zip(self.items, widths):
            nh = n.height(cw)
            if self.align == "stretch":
                cy, nh = y, rh
            elif self.align == "center":
                cy = y + (rh - nh) // 2
            elif self.align == "bottom":
                cy = y + rh - nh
            else:
                cy = y
            n.draw(c, round(cx), cy, cw, nh, ink)
            cx += cw + gap


class Grid(Node):
    def __init__(self, children: Iterable[Node], cols: int, colgap: int = 0, rowgap: int = 0):
        self.children = list(children)
        self.cols = cols
        self.colgap = colgap
        self.rowgap = rowgap

    def _cols(self, w: int) -> list[int]:
        avail = w - self.colgap * (self.cols - 1)
        return [avail // self.cols + (1 if i < avail % self.cols else 0) for i in range(self.cols)]

    def _rows(self, w):
        cws = self._cols(w)
        rows = [self.children[i:i + self.cols] for i in range(0, len(self.children), self.cols)]
        return cws, rows, [max(ch.height(cws[k]) for k, ch in enumerate(r)) for r in rows]

    def height(self, w):
        if not self.children:
            return 0
        _, rows, hs = self._rows(w)
        return sum(hs) + self.rowgap * (len(rows) - 1)

    def draw(self, c, x, y, w, h, ink=0):
        cws, rows, hs = self._rows(w)
        cy = y
        for r, rh in zip(rows, hs):
            cx = x
            for k, ch in enumerate(r):
                ch.draw(c, cx, cy, cws[k], rh, ink)
                cx += cws[k] + self.colgap
            cy += rh + self.rowgap


class Box(Node):
    """Border and padding around one child. `fill` is a tone name, "solid" makes an inverted band."""

    def __init__(self, child: Node | None, border: int = 3, pad=(8, 10, 8, 10), fill: str | None = None,
                 sides: str = "trbl"):
        self.child = child or Spacer(0)
        self.b = border
        self.pad = pad if isinstance(pad, tuple) else (pad, pad, pad, pad)
        self.fill = fill
        self.sides = sides

    def _bx(self):
        t, r, b, l = self.pad
        bt = self.b if "t" in self.sides else 0
        bb = self.b if "b" in self.sides else 0
        bl = self.b if "l" in self.sides else 0
        br = self.b if "r" in self.sides else 0
        return bt + t, br + r, bb + b, bl + l

    def height(self, w):
        t, r, b, l = self._bx()
        return t + b + self.child.height(w - l - r)

    def natural(self, w):
        t, r, b, l = self._bx()
        return min(w, l + r + self.child.natural(w - l - r))

    def draw(self, c, x, y, w, h, ink=0):
        t, r, b, l = self._bx()
        inner_ink = ink
        if self.fill == "solid":
            c.rect(x, y, x + w, y + h, ink)
            inner_ink = 1 - ink
        elif self.fill:
            c.tone(self.fill, x, y, w, h, ink)
        if self.b:
            if "t" in self.sides:
                c.rect(x, y, x + w, y + self.b, ink)
            if "b" in self.sides:
                c.rect(x, y + h - self.b, x + w, y + h, ink)
            if "l" in self.sides:
                c.rect(x, y, x + self.b, y + h, ink)
            if "r" in self.sides:
                c.rect(x + w - self.b, y, x + w, y + h, ink)
        cw = w - l - r
        ch = self.child.height(cw)
        self.child.draw(c, x + l, y + t, cw, max(ch, h - t - b), inner_ink)


def Band(child: Node, pad=(8, 8, 8, 8)) -> Box:
    """Inverted band: solid black, content in paper white (4.4)."""
    return Box(child, border=0, pad=pad, fill="solid")


def Pad(child: Node, t=0, r=0, b=0, l=0) -> Box:
    return Box(child, border=0, pad=(t, r, b, l))


class Fixed(Node):
    """A child forced to a width and/or height (centred inside)."""

    def __init__(self, child: Node | None = None, w: int | None = None, h: int | None = None):
        self.child = child or Spacer(0)
        self.w, self.h = w, h

    def height(self, w):
        return self.h if self.h is not None else self.child.height(self.w or w)

    def natural(self, w):
        return min(w, self.w) if self.w is not None else self.child.natural(w)

    def draw(self, c, x, y, w, h, ink=0):
        cw = self.w or w
        self.child.draw(c, x + (w - cw) // 2, y, cw, h, ink)


class Custom(Node):
    def __init__(self, h: int | Callable[[int], int], fn: Callable, natural: int | None = None):
        self.h = h
        self.fn = fn
        self.nat = natural

    def height(self, w):
        return self.h(w) if callable(self.h) else self.h

    def natural(self, w):
        return min(w, self.nat) if self.nat is not None else w

    def draw(self, c, x, y, w, h, ink=0):
        self.fn(c, x, y, w, h, ink)


# ----------------------------------------------------------------- rules --
class Rule(Node):
    """hr (2-dot dashed 6/4), hr2 (3 solid, 2 space, 2 solid), hrd (3-dot dotted 3/3), solid (n dots)."""

    H = {"hr": 2, "hr2": 7, "hrd": 3}

    def __init__(self, kind: str = "hr", thick: int = 3):
        self.kind = kind
        self.thick = thick

    def height(self, w):
        return self.H.get(self.kind, self.thick)

    def draw(self, c, x, y, w, h, ink=0):
        if self.kind == "hr":
            c.hdash(x, x + w, y, 2, 6, 4, ink)
        elif self.kind == "hr2":
            c.rect(x, y, x + w, y + 3, ink)
            c.rect(x, y + 5, x + w, y + 7, ink)
        elif self.kind == "hrd":
            c.hdash(x, x + w, y, 3, 3, 3, ink)
        else:
            c.rect(x, y, x + w, y + self.thick, ink)


class Cut(Node):
    """A `px` label centred between two 2-dot dashed lines."""

    def __init__(self, label: str = "CUT"):
        self.t = Text(label, T.PX)

    def height(self, w):
        return T.PX.lh

    def draw(self, c, x, y, w, h, ink=0):
        tw = self.t.natural(w)
        tx = x + (w - tw) // 2
        ly = y + (T.PX.lh - 2) // 2
        c.hdash(x, tx - 8, ly, 2, 6, 4, ink)
        c.hdash(tx + tw + 8, x + w, ly, 2, 6, 4, ink)
        self.t.draw(c, tx, y, tw, T.PX.lh, ink)


class SectionRule(Node):
    """`px b` label (or an inverted tag), then a dashed line filling the row."""

    def __init__(self, label: str, inverted: bool = False):
        self.label = Tag(label, "inv") if inverted else Text(label, T.PX_B)

    def height(self, w):
        return self.label.height(w)

    def draw(self, c, x, y, w, h, ink=0):
        lw = self.label.natural(w)
        self.label.draw(c, x, y, lw, h, ink)
        c.hdash(x + lw + 8, x + w, y + (h - 2) // 2, 2, 6, 4, ink)


# ------------------------------------------------------------ small parts --
def Tag(text: str, mode: str = "inv", style: Style = T.PX_B, pad=(3, 6, 3, 6)) -> Node:
    """inv: white on black; outline: 2-dot border; plain: just the label."""
    t = Text(text, style)
    if mode == "inv":
        return Band(t, pad)
    if mode == "outline":
        return Box(t, border=2, pad=(pad[0] - 1, pad[1], pad[2] - 1, pad[3]))
    return t


class Checkbox(Node):
    def __init__(self, large: bool = False):
        self.s, self.b = (30, 4) if large else (20, 3)

    def height(self, w):
        return self.s

    def natural(self, w):
        return self.s

    def draw(self, c, x, y, w, h, ink=0):
        c.frame(x, y, self.s, self.s, self.b, ink)


class Meter(Node):
    """16 dots tall, 2-dot border, d50 fill from the left to `pct`."""

    def __init__(self, pct: float, h: int = 16):
        self.pct = max(0.0, min(100.0, float(pct or 0)))
        self.h = h

    def height(self, w):
        return self.h

    def draw(self, c, x, y, w, h, ink=0):
        fw = round((w - 4) * self.pct / 100)
        c.tone("d50", x + 2, y + 2, fw, self.h - 4, ink)
        c.frame(x, y, w, self.h, 2, ink)


class Fill(Node):
    def __init__(self, tone: str, h: int, border: int = 0):
        self.tone, self.h, self.b = tone, h, border

    def height(self, w):
        return self.h

    def draw(self, c, x, y, w, h, ink=0):
        if self.tone == "solid":
            c.rect(x, y, x + w, y + self.h, ink)
        elif self.tone != "none":
            c.tone(self.tone, x, y, w, self.h, ink)
        if self.b:
            c.frame(x, y, w, self.h, self.b, ink)


class Bitmap(Node):
    def __init__(self, img: Image.Image):
        self.img = img.convert("1")

    def height(self, w):
        return self.img.height

    def natural(self, w):
        return min(w, self.img.width)

    def draw(self, c, x, y, w, h, ink=0):
        c.bitmap(self.img, x + max(0, (w - self.img.width) // 2), y, ink)


def qr_image(data: str, scale: int = 3, border: int = 4) -> Image.Image:
    """Real QR code, error level M, 3 dots per module, 4-module quiet zone (4.5)."""
    q = segno.make(data, error="m")
    rows = list(q.matrix_iter(scale=scale, border=border))
    arr = np.array([[0 if v else 255 for v in r] for r in rows], dtype=np.uint8)
    return Image.fromarray(arr, "L").convert("1", dither=Image.Dither.NONE)


def QR(data: str) -> Bitmap:
    return Bitmap(qr_image(data))
