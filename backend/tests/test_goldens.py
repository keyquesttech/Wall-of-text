"""Print kit: golden images, print-safety rules, end marks and preview/printer parity (WP7).

Regenerate on purpose with `tools/update_goldens.py`, then look at the PNGs.
"""
import io
import time
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from golden.cases import cases
from walloftext.app import create_app
from walloftext.render.document import Renderer
from walloftext.render.fonts import FontRegistry
from walloftext.render.kit import TEMPLATES
from walloftext.render.kit import nodes as N
from walloftext.render.kit import tokens as T
from walloftext.render.kit.slip import END_H, end_mark, icon_image, render_slip
from walloftext.services import build

GOLDEN = Path(__file__).parent / "golden"
CASES = cases()


@pytest.fixture(scope="module")
def renderer(tmp_path_factory):
    from walloftext.config import Settings
    s = Settings()
    return Renderer(FontRegistry(s.fonts_dir, tmp_path_factory.mktemp("fonts")))


@pytest.mark.parametrize("name", sorted(CASES))
def test_golden(renderer, name):
    img = renderer.render(CASES[name]).image
    assert img.mode == "1" and img.width == 384
    ref = Image.open(GOLDEN / f"{name}.png").convert("1")
    assert img.size == ref.size, f"{name}: size changed; run tools/update_goldens.py if intended"
    diff = int((np.asarray(img) != np.asarray(ref)).sum())
    assert diff == 0, f"{name}: {diff} dots differ from the golden"


@pytest.mark.parametrize("name", sorted(CASES))
def test_exactly_one_end_mark_at_the_bottom(renderer, name):
    img = renderer.render(CASES[name]).image
    arr = np.asarray(img)
    em = np.asarray(end_mark())
    assert (arr[-END_H:] == em).all()
    # and no second end mark anywhere above it
    others = [y for y in range(arr.shape[0] - END_H) if (arr[y:y + END_H] == em).all()]
    assert others == []


def test_two_copies_two_end_marks(renderer):
    """Copies reprint the whole bitmap, so each copy carries its own end mark."""
    img = renderer.render(CASES["note"]).image
    two = np.vstack([np.asarray(img)] * 2)
    em = np.asarray(end_mark())
    starts = [y for y in range(two.shape[0] - END_H + 1) if (two[y:y + END_H] == em).all()]
    assert len(starts) == 2


def test_routine_has_cut_rules_and_one_end_mark(renderer):
    doc = CASES["routine"]
    assert [b["type"] for b in doc["blocks"]].count("cut") == 2
    test_exactly_one_end_mark_at_the_bottom(renderer, "routine")


def test_every_template_has_a_golden():
    used = {b.get("template") for d in CASES.values() for b in d["blocks"] if b["type"] == "slip"}
    assert set(TEMPLATES) - {"date"} <= used


# ------------------------------------------------------------ primitives --
def _render(node, w=T.CONTENT):
    return render_slip([node])


@pytest.mark.parametrize("node", [
    N.Text("Hello world", T.T_M), N.Rule("hr"), N.Rule("hr2"), N.Rule("hrd"), N.Cut("MAP"), N.SectionRule("DUE TODAY"),
    N.SectionRule("! OVERDUE", True), N.Checkbox(), N.Checkbox(True), N.Meter(70), N.Fill("d50", 20, 2),
    N.Band(N.Text("TIP", T.T_L)), N.Box(N.Text("BOX", T.T_S)), N.QR("https://example.com"),
    N.Row(N.Text("a"), N.Text("b"), justify="between"), N.Grid([N.Text(str(i)) for i in range(4)], 2),
])
def test_primitive_is_pure_1bit_within_margins(node):
    img = _render(node)
    assert img.mode == "1" and img.width == 384
    arr = ~np.asarray(img)
    assert arr.any()
    cols = np.where(arr.any(axis=0))[0]
    assert cols.min() >= T.SIDE and cols.max() < 384 - T.SIDE
    rows = np.where(arr.any(axis=1))[0]
    assert rows.min() >= T.TOP and rows.max() < img.height - T.BOTTOM


def test_rule_sizes():
    assert N.Rule("hr").height(344) == 2 and N.Rule("hr2").height(344) == 7 and N.Rule("hrd").height(344) == 3
    assert N.Checkbox().height(0) == 20 and N.Checkbox(True).height(0) == 30 and N.Meter(50).height(0) == 16
    assert end_mark().size == (384, 63)


def test_text_wraps_caps_lines_and_never_shrinks():
    t = N.Text("word " * 60, T.T_L, max_lines=2)
    assert len(t.lines(344)) == 2 and t.lines(344)[-1].endswith("…") and t.height(344) == 2 * T.T_L.lh


def test_tones_are_the_spec_tiles():
    assert T.tone_mask("d50", 0, 0, 4, 4).astype(int).tolist() == [[1, 1, 0, 0], [1, 1, 0, 0], [0, 0, 1, 1], [0, 0, 1, 1]]
    assert T.tone_mask("d25", 0, 0, 4, 4).sum() == 4 and T.tone_mask("d75", 0, 0, 4, 4).sum() == 12


def test_every_icon_exists_at_every_size():
    for cond in T.CONDITIONS:
        for size in T.ICON_SIZES:
            im = icon_image(cond, size)
            assert im.size == (size, size) and im.mode == "1"


def test_qr_is_real_and_scaled():
    img = N.qr_image("https://www.google.com/maps/search/?api=1&query=14%20Mill%20Lane")
    assert img.width % 3 == 0 and img.width >= (29 + 8) * 3


# --------------------------------------------------------- preview parity --
@pytest.fixture
def client(settings, fake_nm):
    fake_nm.profiles["wot-client"] = {"ssid": "HomeWiFi", "password": "correct-horse"}
    fake_nm.simulate_boot_autoconnect()
    svc = build(settings, nm=fake_nm)
    with TestClient(create_app(services=svc), base_url="http://walloftext.local") as c:
        for _ in range(50):
            c.portal.call(svc.wifi.tick)
            if svc.wifi.status.mode == "online":
                break
            time.sleep(0.02)
        assert c.post("/api/auth/login", json={"password": "root"}).status_code == 200
        c.patch("/api/settings", json={"printer": {"rotate_180": False}})
        c.svc = svc
        yield c


def test_preview_equals_printer_bitmap_for_every_golden(client):
    for name in ("weather_briefing_sample", "weather_now_sample", "itinerary_sample", "routine",
                 "message", "shopping", "test_page"):
        doc = CASES[name]
        r = client.post("/api/preview", json={"document": doc})
        assert r.status_code == 200
        preview = Image.open(io.BytesIO(r.content)).convert("1")
        n = len(client.svc.printer.printed)
        client.post("/api/print", json={"document": doc})
        end = time.time() + 20
        while len(client.svc.printer.printed) <= n and time.time() < end:
            time.sleep(0.05)
        printed = Image.open(client.svc.printer.printed[-1]).convert("1")
        assert printed.tobytes() == preview.tobytes(), name


def test_render_time_is_reasonable(renderer):
    t0 = time.monotonic()
    renderer.render(CASES["itinerary_sample"])
    assert time.monotonic() - t0 < 3.0  # ~1 s target on a Pi 4 once fonts and icons are cached
