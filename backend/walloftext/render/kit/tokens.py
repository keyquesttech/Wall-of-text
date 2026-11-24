"""Print kit tokens (PRINT_TEMPLATES 2-4): paper, type scale, tones, borders.

1 design px = 1 printer dot. Two fonts only: Space Grotesk (Medium, Bold) and
JetBrains Mono (Regular, Bold, ExtraBold), static TTFs in the repo `fonts/`.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, replace
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import ImageFont

from ...config import REPO_ROOT

# ----------------------------------------------------------------- paper --
WIDTH = 384
SIDE = 20
CONTENT = WIDTH - 2 * SIDE  # 344
TOP = 30
BOTTOM = 36
GAP = 14

# ----------------------------------------------------------------- fonts --
SG_MED = "SpaceGrotesk-Medium.ttf"
SG_BOLD = "SpaceGrotesk-Bold.ttf"
JB_REG = "JetBrainsMono-Regular.ttf"
JB_BOLD = "JetBrainsMono-Bold.ttf"
JB_XBOLD = "JetBrainsMono-ExtraBold.ttf"


def fonts_dir() -> Path:
    return Path(os.environ.get("WOT_FONTS", str(REPO_ROOT / "fonts")))


@lru_cache(maxsize=128)
def font(name: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(fonts_dir() / name), size)


@dataclass(frozen=True)
class Style:
    file: str
    size: int
    lh: int
    track: float = 0.0  # letter spacing in em
    upper: bool = False

    def __call__(self, **kw) -> "Style":
        return replace(self, **kw)

    @property
    def font(self) -> ImageFont.FreeTypeFont:
        return font(self.file, self.size)

    @property
    def tracking(self) -> float:
        return self.track * self.size


# Type scale (section 3). Sizes / line heights in dots.
T_XXL = Style(SG_BOLD, 92, 78, -0.05)
T_XL = Style(SG_BOLD, 36, 36, -0.025)
T_L = Style(SG_BOLD, 23, 25, -0.01)
T_M = Style(SG_MED, 17, 21)
T_MB = Style(SG_BOLD, 17, 21)
T_S = Style(SG_MED, 15, 19)
PX = Style(JB_BOLD, 12, 15, 0.06, True)
PX_B = Style(JB_XBOLD, 12, 15, 0.06, True)
MONO = Style(JB_REG, 15, 20)
MONO_B = Style(JB_BOLD, 15, 20)
CHART = Style(SG_MED, 13, 16)  # one-off: the button slip's chart labels

# ----------------------------------------------------------------- tones --
# 4 x 4 tiles, 1 = black (section 4.2)
_D25 = np.array([[1, 0, 1, 0], [0, 0, 0, 0], [1, 0, 1, 0], [0, 0, 0, 0]], dtype=bool)
_D50 = np.array([[1, 1, 0, 0], [1, 1, 0, 0], [0, 0, 1, 1], [0, 0, 1, 1]], dtype=bool)
TONES = {"d25": _D25, "d50": _D50, "d75": ~_D25, "solid": np.ones((4, 4), dtype=bool)}


def tone_mask(tone: str, x: int, y: int, w: int, h: int) -> np.ndarray:
    """Black mask (True = ink) for a tone filling a w x h box placed at (x, y) on the page.
    The tile is anchored to the page so neighbouring areas line up."""
    tile = TONES[tone]
    yy = (np.arange(h) + y) % 4
    xx = (np.arange(w) + x) % 4
    return tile[yy[:, None], xx[None, :]]


# ---------------------------------------------------------- weather icons --
ICON_SIZES = (168, 104, 96, 52, 44, 40)
CONDITIONS = {
    "sunny": "SUNNY", "night": "CLEAR NIGHT", "partly": "SUNNY SPELLS", "cloudy": "OVERCAST",
    "fog": "FOG", "drizzle": "DRIZZLE", "rain": "RAIN", "heavy": "HEAVY RAIN",
    "thunder": "THUNDERSTORMS", "snow": "SNOW", "sleet": "SLEET & HAIL", "frost": "FROST",
    "wind": "WINDY", "heat": "HEATWAVE",
}
