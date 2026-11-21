"""Document → 1-bit 384-px bitmap (BUILD_PLAN 6.1).

One function, `render()`, makes both the paper bitmap and the "As printed"
preview, so the preview is exactly what is sent to the printer.

A document is `{"blocks": [...], "options": {...}}`. Block types are listed in
docs/DOCUMENT.md. Unknown block types render as a small "unknown block" line
rather than failing the whole print.
"""
from __future__ import annotations

import base64
import io
import math
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import numpy as np
import segno
from PIL import Image, ImageDraw, ImageEnhance, ImageOps

from ..printer.base import WIDTH
from .fonts import SIZES, FontRegistry, size_px

MARGIN = 6
GAP = 8
MAX_HEIGHT = 8 * 1000 * 2  # 2 m of paper: refuse anything longer
MAX_IMAGE_BYTES = 12 * 1024 * 1024
PLACEHOLDER = "□"


class DocumentError(ValueError):
    pass


@dataclass
class RenderResult:
    image: Image.Image
    coverage: float  # 0..1 share of black dots
    warnings: list[str] = field(default_factory=list)

    @property
    def rows(self) -> int:
        return self.image.height

    def png(self) -> bytes:
        buf = io.BytesIO()
        self.image.save(buf, "PNG", optimize=True)
        return buf.getvalue()


def _blank(h: int) -> Image.Image:
    return Image.new("1", (WIDTH, max(1, h)), 1)


class Renderer:
    def __init__(self, fonts: FontRegistry, settings_get=None):
        self.fonts = fonts
        self.settings_get = settings_get

    # ------------------------------------------------------------ public --
    def render(self, doc: dict[str, Any]) -> RenderResult:
        if not isinstance(doc, dict) or not isinstance(doc.get("blocks"), list):
            raise DocumentError("A document needs a list of blocks.")
        if len(doc["blocks"]) > 200:
            raise DocumentError("Too many blocks (200 at most).")
        opts = dict(doc.get("options") or {})
        saver = False
        if self.settings_get is not None:
            try:
                saver = bool(self.settings_get()["printer"].get("paper_saver"))
            except Exception:
                saver = False
        if saver:  # paper saver: tighter gaps, no top margin, trailing blank rows trimmed
            opts.setdefault("gap", 3)
            opts.setdefault("top_margin", 0)
        warnings: list[str] = []
        parts: list[Image.Image] = []
        for i, b in enumerate(doc["blocks"]):
            if not isinstance(b, dict):
                continue
            fn = getattr(self, f"_b_{b.get('type', '')}", None)
            if fn is None:
                parts.append(self._text_img(f"[unknown block: {b.get('type')}]", "S", None, "left"))
                warnings.append(f"Block {i + 1} has an unknown type and printed as a note.")
                continue
            img = fn(b, warnings)
            if img is not None:
                parts.append(img)
        if not parts:
            parts.append(_blank(1))
        gap = int(opts.get("gap", GAP))
        height = sum(p.height for p in parts) + gap * (len(parts) - 1) + int(opts.get("top_margin", 4))
        if height > MAX_HEIGHT:
            raise DocumentError("This print is longer than 2 m of paper. Make it shorter.")
        out = _blank(height)
        y = int(opts.get("top_margin", 4))
        for p in parts:
            out.paste(p, (0, y))
            y += p.height + gap
        if saver:
            arr0 = np.asarray(out, dtype=bool)
            ink_rows = np.where(~arr0.all(axis=1))[0]
            if len(ink_rows):
                out = out.crop((0, 0, WIDTH, int(ink_rows[-1]) + 3))
        if opts.get("border"):
            d = ImageDraw.Draw(out)
            d.rectangle([0, 0, WIDTH - 1, out.height - 1], outline=0, width=3)
        arr = np.asarray(out, dtype=bool)
        coverage = 1.0 - float(arr.mean()) if arr.size else 0.0
        if coverage > 0.5:
            warnings.append("This print is more than half black. Dense prints can stick or streak; "
                            "try Lighten.")
        return RenderResult(out, coverage, warnings)

    # ------------------------------------------------------------- text --
    def _font(self, fid, size_key, bold=False):
        px = size_px(self.fonts.get(fid).id, size_key)
        return self.fonts.font(fid, px, bold) + (px,)

    def _clean(self, text: str, fid) -> str:
        text = text.replace("\r\n", "\n").replace("\t", "    ")
        return "".join(ch if self.fonts.covers(fid, ch) else PLACEHOLDER for ch in text)

    def _wrap(self, draw, text: str, font, width: int) -> list[str]:
        lines: list[str] = []
        for para in text.split("\n"):
            if para == "":
                lines.append("")
                continue
            words = re.split(r"( +)", para)
            line = ""
            for w in words:
                cand = line + w
                if draw.textlength(cand, font=font) <= width:
                    line = cand
                    continue
                if line.strip():
                    lines.append(line.rstrip())
                    line = w.lstrip()
                else:
                    line = w.lstrip()
                while draw.textlength(line, font=font) > width and len(line) > 1:  # break long words
                    cut = len(line)
                    while cut > 1 and draw.textlength(line[:cut], font=font) > width:
                        cut -= 1
                    lines.append(line[:cut])
                    line = line[cut:]
            lines.append(line.rstrip())
        return lines

    def _text_img(self, text, size="M", fid=None, align="left", bold=False, invert=False,
                  underline=False, line_gap=None, max_lines=None) -> Image.Image:
        font, fake_bold, px = self._font(fid, size, bold)
        thicken = self.fonts.needs_thicken(fid, px, bold)
        text = self._clean(str(text), fid)
        probe = ImageDraw.Draw(_blank(1))
        inner = WIDTH - 2 * MARGIN - (8 if invert else 0)
        lines = self._wrap(probe, text, font, inner)
        if max_lines and len(lines) > max_lines:
            lines = lines[:max_lines]
            lines[-1] = lines[-1][: max(0, len(lines[-1]) - 8)] + "… (cut)"
        asc, desc = font.getmetrics()
        lh = asc + desc + (line_gap if line_gap is not None else 1)
        pad = 6 if invert else 0
        img = _blank(lh * len(lines) + 2 * pad)
        d = ImageDraw.Draw(img)
        d.fontmode = "1"
        ink = 1 if invert else 0
        if invert:
            d.rectangle([0, 0, WIDTH - 1, img.height - 1], fill=0)
        for i, line in enumerate(lines):
            w = d.textlength(line, font=font)
            if align == "center":
                x = (WIDTH - w) / 2
            elif align == "right":
                x = WIDTH - MARGIN - w - (4 if invert else 0)
            else:
                x = MARGIN + (4 if invert else 0)
            y = pad + i * lh
            d.text((x, y), line, font=font, fill=ink)
            # 1-dot strokes print faint on thermal paper: widen thin fonts by a dot
            extra = (1 if fake_bold else 0) + (1 if thicken else 0)
            for dx in range(1, extra + 1):
                d.text((x + dx, y), line, font=font, fill=ink)
            if underline and line:
                uy = y + asc + 2
                d.line([(x, uy), (x + w, uy)], fill=ink, width=max(1, px // 14))
        return img

    def _b_text(self, b, warnings):
        return self._text_img(b.get("text", ""), b.get("size", "M"), b.get("font"), b.get("align", "left"),
                              bool(b.get("bold")), bool(b.get("invert")), bool(b.get("underline")),
                              max_lines=b.get("max_lines"))

    def _b_heading(self, b, warnings):
        return self._text_img(b.get("text", ""), b.get("size", "XL"), b.get("font"), b.get("align", "center"),
                              True, bool(b.get("invert")))

    def _b_banner(self, b, warnings):
        return self._text_img(b.get("text", ""), b.get("size", "S"), b.get("font"), b.get("align", "left"),
                              True, True)

    def _b_datetime(self, b, warnings):
        fmt = b.get("format", "%A %-d %B %Y · %H:%M")
        try:
            text = datetime.now().strftime(fmt)
        except ValueError:
            text = datetime.now().strftime("%Y-%m-%d %H:%M")
        return self._text_img(text, b.get("size", "S"), b.get("font"), b.get("align", "center"))

    def _b_checklist(self, b, warnings):
        size = b.get("size", "M")
        font, _, px = self._font(b.get("font"), size)
        rows = []
        box = max(10, int(px * 0.7))
        for item in (b.get("items") or [])[:100]:
            text = item.get("text", "") if isinstance(item, dict) else str(item)
            done = isinstance(item, dict) and bool(item.get("done"))
            t = self._text_img(text, size, b.get("font"))
            row = _blank(t.height)
            sub = t.crop((0, 0, WIDTH - box - 10, t.height))
            row.paste(sub, (box + 10, 0))
            d = ImageDraw.Draw(row)
            asc, desc = font.getmetrics()
            top = max(0, (asc + desc - box) // 2 + 1)
            d.rectangle([MARGIN, top, MARGIN + box, top + box], outline=0, width=2)
            if done:
                d.line([(MARGIN + 2, top + box // 2), (MARGIN + box // 2, top + box - 2), (MARGIN + box, top - 2)],
                       fill=0, width=3)
            rows.append(row)
        if not rows:
            return None
        out = _blank(sum(r.height for r in rows))
        y = 0
        for r in rows:
            out.paste(r, (0, y))
            y += r.height
        return out

    # --------------------------------------------------------- graphics --
    def _b_divider(self, b, warnings):
        style = b.get("style", "solid")
        img = _blank(14)
        d = ImageDraw.Draw(img)
        y = 7
        if style == "dashed":
            for x in range(MARGIN, WIDTH - MARGIN, 14):
                d.line([(x, y), (x + 7, y)], fill=0, width=2)
        elif style == "dotted":
            for x in range(MARGIN, WIDTH - MARGIN, 8):
                d.rectangle([x, y - 1, x + 2, y + 1], fill=0)
        elif style == "wave":
            pts = [(x, y + int(4 * math.sin(x / 8))) for x in range(MARGIN, WIDTH - MARGIN)]
            d.line(pts, fill=0, width=2)
        elif style == "stars":
            return self._text_img("✱ ✱ ✱", "M", "mono", "center")
        elif style == "double":
            d.line([(MARGIN, y - 3), (WIDTH - MARGIN, y - 3)], fill=0, width=2)
            d.line([(MARGIN, y + 3), (WIDTH - MARGIN, y + 3)], fill=0, width=2)
        else:
            d.line([(MARGIN, y), (WIDTH - MARGIN, y)], fill=0, width=3)
        return img

    def _b_spacer(self, b, warnings):
        return _blank(max(1, min(400, int(b.get("height", 24)))))

    def _b_qr(self, b, warnings):
        data = str(b.get("data", ""))[:1000]
        if not data:
            return None
        target = {"S": 140, "M": 220, "L": 320}.get(b.get("size", "M"), 220)
        q = segno.make(data, error="m")
        modules = q.symbol_size(scale=1, border=2)[0]
        scale = max(1, target // modules)
        buf = io.BytesIO()
        q.save(buf, kind="png", scale=scale, border=2)
        code = Image.open(io.BytesIO(buf.getvalue())).convert("1")
        cap = b.get("caption")
        cap_img = self._text_img(cap, "S", b.get("font"), "center") if cap else None
        out = _blank(code.height + (cap_img.height + 4 if cap_img else 0))
        out.paste(code, ((WIDTH - code.width) // 2, 0))
        if cap_img:
            out.paste(cap_img, (0, code.height + 4))
        return out

    def _b_image(self, b, warnings):
        src = b.get("src") or ""
        try:
            img = decode_image(src)
        except DocumentError as exc:
            warnings.append(str(exc))
            return self._text_img("[image missing]", "S", None, "center")
        return process_image(img, style=b.get("style", "photo"), dither=b.get("dither", "floyd"),
                             brightness=float(b.get("brightness", 1.0)), contrast=float(b.get("contrast", 1.0)),
                             invert=bool(b.get("invert")), width=int(b.get("width", WIDTH)),
                             lighten=bool(b.get("lighten")), rotate=int(b.get("rotate", 0)))

    def _b_drawing(self, b, warnings):
        b = dict(b, style="sharp")
        return self._b_image(b, warnings)

    def _b_sticker(self, b, warnings):
        from .stickers import sticker_image

        size = {"S": 72, "M": 120, "L": 180}.get(b.get("size", "M"), 120)
        st = sticker_image(b.get("name", "star"), size)
        out = _blank(size)
        align = b.get("align", "center")
        x = MARGIN if align == "left" else WIDTH - MARGIN - size if align == "right" else (WIDTH - size) // 2
        out.paste(st, (x, 0))
        return out

    def _b_columns(self, b, warnings):
        """Two short texts side by side, e.g. "Mon 12°" | "Rain 40%"."""
        left = self._text_img(b.get("left", ""), b.get("size", "M"), b.get("font"), "left")
        right = self._text_img(b.get("right", ""), b.get("size", "M"), b.get("font"), "right")
        out = _blank(max(left.height, right.height))
        out.paste(left.crop((0, 0, WIDTH // 2, left.height)), (0, 0))
        out.paste(right.crop((WIDTH // 2, 0, WIDTH, right.height)), (WIDTH // 2, 0))
        return out


# ------------------------------------------------------------------ images --

def decode_image(src: str) -> Image.Image:
    if src.startswith("data:"):
        try:
            raw = base64.b64decode(src.split(",", 1)[1], validate=False)
        except (IndexError, ValueError):
            raise DocumentError("The image data is damaged.")
    else:
        raise DocumentError("Images must be uploaded with the print.")
    if len(raw) > MAX_IMAGE_BYTES:
        raise DocumentError("That image is too large (12 MB at most).")
    try:
        img = Image.open(io.BytesIO(raw))
        img = ImageOps.exif_transpose(img)
        img.load()
    except Exception:
        raise DocumentError("That file isn't an image the printer can use.")
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        bg = Image.new("RGBA", img.size, (255, 255, 255, 255))
        bg.alpha_composite(img)
        img = bg
    return img.convert("L")


def _atkinson(gray: np.ndarray) -> np.ndarray:
    g = gray.astype(np.float32)
    h, w = g.shape
    for y in range(h):
        row = g[y]
        for x in range(w):
            old = row[x]
            new = 255.0 if old >= 128 else 0.0
            err = (old - new) / 8.0
            row[x] = new
            if x + 1 < w:
                row[x + 1] += err
            if x + 2 < w:
                row[x + 2] += err
            if y + 1 < h:
                nxt = g[y + 1]
                if x > 0:
                    nxt[x - 1] += err
                nxt[x] += err
                if x + 1 < w:
                    nxt[x + 1] += err
            if y + 2 < h:
                g[y + 2][x] += err
    return g >= 128


BAYER4 = np.array([[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]], dtype=np.float32)


def _halftone(gray: np.ndarray) -> np.ndarray:
    """Clustered-dot screen: 6-px cells, dot radius from cell darkness."""
    h, w = gray.shape
    cell = 6
    out = np.ones((h, w), dtype=bool)
    yy, xx = np.mgrid[0:cell, 0:cell]
    dist = np.sqrt((yy - (cell - 1) / 2) ** 2 + (xx - (cell - 1) / 2) ** 2)
    for y in range(0, h, cell):
        for x in range(0, w, cell):
            block = gray[y:y + cell, x:x + cell]
            dark = 1 - block.mean() / 255.0
            r = math.sqrt(dark * cell * cell / math.pi)
            mask = dist[: block.shape[0], : block.shape[1]] < r
            out[y:y + cell, x:x + cell] = ~mask
    return out


def process_image(img: Image.Image, style="photo", dither="floyd", brightness=1.0, contrast=1.0,
                  invert=False, width=WIDTH, lighten=False, rotate=0) -> Image.Image:
    img = img.convert("L")
    if rotate in (90, 180, 270):
        img = img.rotate(-rotate, expand=True)
    width = max(32, min(WIDTH, width))
    h = max(1, round(img.height * width / img.width))
    h = min(h, 3000)
    img = img.resize((width, h), Image.LANCZOS)
    if contrast != 1.0:
        img = ImageEnhance.Contrast(img).enhance(max(0.2, min(3.0, contrast)))
    if brightness != 1.0:
        img = ImageEnhance.Brightness(img).enhance(max(0.2, min(3.0, brightness)))
    if invert:
        img = ImageOps.invert(img)
    if lighten:  # paper-safe limiter: compress the dark end so coverage drops below ~50 %
        img = img.point(lambda v: int(90 + v * (255 - 90) / 255))
    if style == "sharp":
        bw = img.point(lambda v: 255 if v >= 128 else 0).convert("1", dither=Image.Dither.NONE)
    elif style == "halftone":
        bw = Image.fromarray(_halftone(np.asarray(img)).astype(np.uint8) * 255).convert("1")
    elif dither == "atkinson":
        bw = Image.fromarray(_atkinson(np.asarray(img)).astype(np.uint8) * 255).convert("1")
    elif dither == "ordered":
        a = np.asarray(img, dtype=np.float32)
        th = (np.tile(BAYER4, (a.shape[0] // 4 + 1, a.shape[1] // 4 + 1))[: a.shape[0], : a.shape[1]] + 0.5) * 16
        bw = Image.fromarray(((a >= th) * 255).astype(np.uint8)).convert("1")
    else:
        bw = img.convert("1", dither=Image.Dither.FLOYDSTEINBERG)
    if width == WIDTH:
        return bw
    out = _blank(bw.height)
    out.paste(bw, ((WIDTH - width) // 2, 0))
    return out


def text_document(text: str, size="M", font=None, align="left", bold=False, title: str | None = None) -> dict:
    blocks = []
    if title:
        blocks.append({"type": "heading", "text": title, "size": "L"})
    blocks.append({"type": "text", "text": text, "size": size, "font": font, "align": align, "bold": bold})
    return {"blocks": blocks}
