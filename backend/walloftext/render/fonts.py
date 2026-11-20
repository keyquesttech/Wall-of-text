"""Font registry shared by the renderer and the web UI.

Built-in fonts live in `fonts/` (OFL). Uploaded fonts live in
`<data_dir>/fonts/`. Each font knows which code points it covers so the
renderer can swap missing glyphs for a placeholder box instead of leaving a
silent gap on the paper.
"""
from __future__ import annotations

import json
import re
import threading
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

SIZES = {"S": 18, "M": 22, "L": 30, "XL": 40}

BUILTIN = {
    "mono": ("Space Mono", "SpaceMono-Regular.ttf", "SpaceMono-Bold.ttf"),
    "pixel": ("VT323", "VT323-Regular.ttf", None),
    "silk": ("Silkscreen", "Silkscreen-Regular.ttf", "Silkscreen-Bold.ttf"),
    "sans": ("Inter", "Inter-Variable.ttf", None),
}
DEFAULT_FONT = "mono"


@dataclass
class FontInfo:
    id: str
    name: str
    regular: Path
    bold: Path | None
    builtin: bool
    min_readable: str | None = None

    def to_dict(self) -> dict:
        return {"id": self.id, "name": self.name, "builtin": self.builtin, "has_bold": self.bold is not None,
                "min_readable": self.min_readable, "url": None if not self.builtin else f"/fonts/{self.regular.name}"}


@lru_cache(maxsize=64)
def _cmap(path: str) -> frozenset[int]:
    try:
        from fontTools.ttLib import TTFont

        f = TTFont(path, lazy=True)
        return frozenset(f.getBestCmap() or {})
    except Exception:
        return frozenset(range(32, 127))


@lru_cache(maxsize=256)
def _load(path: str, size: int, variation: str | None = None) -> ImageFont.FreeTypeFont:
    f = ImageFont.truetype(path, size)
    if variation:
        try:
            f.set_variation_by_name(variation)
        except Exception:
            pass
    return f


class FontRegistry:
    def __init__(self, builtin_dir: Path, upload_dir: Path):
        self.builtin_dir = Path(builtin_dir)
        self.upload_dir = Path(upload_dir)
        self._lock = threading.Lock()

    def all(self) -> list[FontInfo]:
        out = []
        for fid, (name, reg, bold) in BUILTIN.items():
            p = self.builtin_dir / reg
            if p.exists():
                out.append(FontInfo(fid, name, p, self.builtin_dir / bold if bold else None, True))
        meta = self._meta()
        for fid, m in meta.items():
            p = self.upload_dir / m["file"]
            if p.exists():
                out.append(FontInfo(fid, m["name"], p, None, False, m.get("min_readable")))
        return out

    def get(self, fid: str | None) -> FontInfo:
        fonts = {f.id: f for f in self.all()}
        return fonts.get(fid or DEFAULT_FONT) or fonts.get(DEFAULT_FONT) or next(iter(fonts.values()))

    def font(self, fid: str | None, size: int, bold: bool = False) -> tuple[ImageFont.FreeTypeFont, bool]:
        """Returns (font, synthetic_bold). Variable fonts get their Bold instance."""
        info = self.get(fid)
        if bold and info.bold:
            return _load(str(info.bold), size), False
        if bold and info.id == "sans":
            return _load(str(info.regular), size, "Bold"), False
        variation = "Regular" if info.id == "sans" else None
        return _load(str(info.regular), size, variation), bold

    def covers(self, fid: str | None, ch: str) -> bool:
        if ch in "\n\t ":
            return True
        return ord(ch) in _cmap(str(self.get(fid).regular))

    # ---------------------------------------------------------- uploads --
    def _meta_path(self) -> Path:
        return self.upload_dir / "fonts.json"

    def _meta(self) -> dict:
        try:
            return json.loads(self._meta_path().read_text())
        except (OSError, ValueError):
            return {}

    def add(self, name: str, data: bytes) -> FontInfo:
        if not (data[:4] in (b"\x00\x01\x00\x00", b"OTTO", b"true")):
            raise ValueError("That file isn't a TrueType or OpenType font (.ttf or .otf).")
        if len(data) > 5 * 1024 * 1024:
            raise ValueError("Fonts must be under 5 MB.")
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40] or "font"
        with self._lock:
            meta = self._meta()
            fid = f"u-{slug}"
            n = 2
            while fid in meta or fid in BUILTIN:
                fid = f"u-{slug}-{n}"
                n += 1
            ext = ".otf" if data[:4] == b"OTTO" else ".ttf"
            path = self.upload_dir / f"{fid}{ext}"
            path.write_bytes(data)
            try:
                ImageFont.truetype(str(path), 22)
            except OSError:
                path.unlink(missing_ok=True)
                raise ValueError("That font file couldn't be opened.")
            meta[fid] = {"name": name[:60] or fid, "file": path.name, "min_readable": min_readable_size(path)}
            self._meta_path().write_text(json.dumps(meta, indent=1))
        return self.get(fid)

    def remove(self, fid: str) -> bool:
        with self._lock:
            meta = self._meta()
            m = meta.pop(fid, None)
            if not m:
                return False
            (self.upload_dir / m["file"]).unlink(missing_ok=True)
            self._meta_path().write_text(json.dumps(meta, indent=1))
        return True


def stroke_width(path: Path, size: int) -> float:
    """Median horizontal run of black dots in a test string, in dots."""
    f = ImageFont.truetype(str(path), size)
    img = Image.new("1", (size * 12, size * 2), 1)
    d = ImageDraw.Draw(img)
    d.fontmode = "1"
    d.text((2, 2), "Hlmnoe", font=f, fill=0)
    runs = []
    px = img.load()
    for y in range(img.height):
        run = 0
        for x in range(img.width):
            if px[x, y] == 0:
                run += 1
            elif run:
                runs.append(run)
                run = 0
    if not runs:
        return 0
    runs.sort()
    return runs[len(runs) // 2]


def min_readable_size(path: Path) -> str | None:
    """Smallest S/M/L/XL keeping strokes at least 2 dots wide (BUILD_PLAN 6.1)."""
    for name, px in SIZES.items():
        try:
            if stroke_width(path, px) >= 2:
                return name
        except OSError:
            return None
    return None
