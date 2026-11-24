#!/usr/bin/env python3
"""Regenerate the golden print images on purpose (backend/tests/golden/*.png).

    .venv/bin/python tools/update_goldens.py            # all
    .venv/bin/python tools/update_goldens.py todo_*     # some (glob)

Look at the changed PNGs before committing them: they are what the paper will show.
"""
from __future__ import annotations

import fnmatch
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "backend"), str(ROOT / "backend" / "tests")]

from golden.cases import cases  # noqa: E402
from walloftext.config import Settings  # noqa: E402
from walloftext.render.document import Renderer  # noqa: E402
from walloftext.render.fonts import FontRegistry  # noqa: E402

OUT = ROOT / "backend" / "tests" / "golden"


def main(argv: list[str]) -> int:
    s = Settings()
    import tempfile
    r = Renderer(FontRegistry(s.fonts_dir, Path(tempfile.mkdtemp()) / "fonts"))
    pats = argv or ["*"]
    n = 0
    for name, doc in cases().items():
        if any(fnmatch.fnmatch(name, p) for p in pats):
            r.render(doc).image.save(OUT / f"{name}.png", optimize=True)
            n += 1
    print(f"wrote {n} goldens to {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
