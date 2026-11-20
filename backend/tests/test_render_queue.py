"""Phase 2: renderer, golden equality of preview and print path, queue worker."""
import base64
import hashlib
import io
import time

import pytest
from PIL import Image

from walloftext.events import EventBus
from walloftext.printer.base import WIDTH, raster_bytes
from walloftext.printer.drivers import MockPrinter
from walloftext.queue.worker import ROWS_PER_ROLL, PrintQueue
from walloftext.render.document import DocumentError, Renderer, process_image
from walloftext.render.fonts import FontRegistry
from walloftext.store.db import Store
from walloftext.store.settings import AppSettings

GOLDEN_DOCS = {
    "text": {"blocks": [{"type": "text", "text": "Hello wall", "size": "L", "align": "center"}]},
    "mixed": {"blocks": [
        {"type": "heading", "text": "Shopping"},
        {"type": "checklist", "items": [{"text": "Milk", "done": True}, {"text": "Bread"}]},
        {"type": "divider", "style": "dashed"},
        {"type": "banner", "text": "from Sam · via Email · 18:42"},
        {"type": "qr", "data": "https://example.com", "size": "S", "caption": "scan me"},
        {"type": "spacer", "height": 10},
        {"type": "text", "text": "A very long word: Pneumonoultramicroscopicsilicovolcanoconiosis and more",
         "size": "M", "font": "pixel"},
    ]},
}


@pytest.fixture
def renderer(settings):
    return Renderer(FontRegistry(settings.fonts_dir, settings.data_dir / "fonts"))


def _png_data_url(img: Image.Image) -> str:
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


@pytest.mark.parametrize("name", list(GOLDEN_DOCS))
def test_render_is_384_wide_1bit_and_deterministic(renderer, name):
    a = renderer.render(GOLDEN_DOCS[name])
    b = renderer.render(GOLDEN_DOCS[name])
    assert a.image.mode == "1" and a.image.width == WIDTH
    assert a.image.tobytes() == b.image.tobytes()
    assert 0 < a.coverage < 0.5


@pytest.mark.parametrize("name", list(GOLDEN_DOCS))
def test_preview_equals_print_path(renderer, tmp_path, name):
    """The PNG the preview shows decodes to exactly the bitmap bytes sent to the printer."""
    res = renderer.render(GOLDEN_DOCS[name])
    preview = Image.open(io.BytesIO(res.png())).convert("1")
    p = MockPrinter(tmp_path)
    p.print_bitmap(preview)
    sent = (sorted(tmp_path.glob("*.bin"))[0]).read_bytes()
    expected = b"".join(raster_bytes(res.image))
    assert expected in sent
    assert hashlib.sha256(preview.tobytes()).digest() == hashlib.sha256(res.image.tobytes()).digest()


def test_missing_glyph_becomes_box(renderer):
    plain = renderer.render({"blocks": [{"type": "text", "text": "ab", "font": "pixel"}]})
    emoji = renderer.render({"blocks": [{"type": "text", "text": "a😀", "font": "pixel"}]})
    assert renderer._clean("a😀", "pixel") == "a\u25a1"
    assert plain.image.tobytes() != emoji.image.tobytes()


def test_dense_print_warns(renderer):
    black = Image.new("L", (200, 200), 0)
    res = renderer.render({"blocks": [{"type": "image", "src": _png_data_url(black), "style": "sharp"}]})
    assert res.coverage > 0.5 and any("half black" in w for w in res.warnings)
    light = renderer.render({"blocks": [{"type": "image", "src": _png_data_url(black), "lighten": True}]})
    assert light.coverage < res.coverage


@pytest.mark.parametrize("style,dither", [("photo", "floyd"), ("photo", "atkinson"), ("photo", "ordered"),
                                          ("sharp", None), ("halftone", None)])
def test_image_styles(style, dither):
    grad = Image.linear_gradient("L").resize((120, 60))
    out = process_image(grad, style=style, dither=dither or "floyd")
    assert out.mode == "1" and out.width == WIDTH
    assert out.height == round(60 * WIDTH / 120)


def test_bad_documents(renderer):
    with pytest.raises(DocumentError):
        renderer.render({"nope": 1})
    res = renderer.render({"blocks": [{"type": "martian"}]})
    assert res.warnings and res.image.height > 10


def test_font_min_readable(settings):
    reg = FontRegistry(settings.fonts_dir, settings.data_dir / "fonts")
    data = (settings.fonts_dir / "SpaceMono-Regular.ttf").read_bytes()
    info = reg.add("My Mono", data)
    assert info.id.startswith("u-my-mono") and info.min_readable in ("S", "M", "L", "XL")
    with pytest.raises(ValueError):
        reg.add("junk", b"hello")
    assert reg.remove(info.id)


# ----------------------------------------------------------------- queue --

@pytest.fixture
def q(tmp_path):
    store = Store(tmp_path / "db.sqlite")
    printer = MockPrinter(tmp_path / "out")
    queue = PrintQueue(store, printer, EventBus(), AppSettings(store).all)
    yield queue, printer, store
    queue.stop()


def wait_for(cond, timeout=5.0):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.02)
    return False


def test_queue_prints_in_order_and_counts_paper(q):
    queue, printer, _ = q
    img = Image.new("1", (WIDTH, 80), 1)
    a = queue.enqueue(img, "Manual", "a")
    b = queue.enqueue(img, "Manual", "b", copies=2)
    queue.start()
    assert wait_for(lambda: queue.get(b)["state"] == "done")
    assert queue.get(a)["state"] == "done" and queue.get(a)["finished_at"] <= queue.get(b)["finished_at"]
    assert len(printer.printed) == 2
    assert queue.paper_percent() == round(100 - (80 + 160 + 2 * 72) * 100 / ROWS_PER_ROLL)


def test_crash_leaves_failed_interrupted_never_reprints(q):
    queue, printer, store = q
    jid = queue.enqueue(Image.new("1", (WIDTH, 10), 1), "Manual", "x")
    store.conn().execute("UPDATE jobs SET state='printing' WHERE id=?", (jid,))
    queue.start()
    time.sleep(0.3)
    j = queue.get(jid)
    assert j["state"] == "failed" and j["error"] == "interrupted"
    assert printer.printed == []
    new = queue.retry(jid)
    assert wait_for(lambda: queue.get(new)["state"] == "done")


def test_offline_and_paper_out_hold_jobs(q):
    queue, printer, _ = q
    printer.offline = True
    queue.start()
    jid = queue.enqueue(Image.new("1", (WIDTH, 10), 1), "Manual", "x")
    time.sleep(0.3)
    assert queue.get(jid)["state"] == "queued" and queue.status()["state"] == "offline"
    printer.offline = False
    queue.set_paper_out(True)
    queue.kick()
    time.sleep(0.3)
    assert queue.get(jid)["state"] == "queued" and queue.status()["state"] == "paper_out"
    queue.new_roll()
    assert wait_for(lambda: queue.get(jid)["state"] == "done")
    assert queue.paper_percent() == 100 or queue.paper_percent() == 99


def test_cancel_queued_and_active(q):
    queue, printer, _ = q
    printer.band_delay_s = 0.05
    big = Image.new("1", (WIDTH, 24 * 40), 1)
    a = queue.enqueue(big, "Manual", "a")
    b = queue.enqueue(big, "Manual", "b")
    assert queue.cancel(b)
    queue.start()
    assert wait_for(lambda: queue.get(a)["state"] == "printing")
    assert wait_for(lambda: queue.active_progress > 5)
    assert queue.cancel(a)
    assert wait_for(lambda: queue.get(a)["state"] == "cancelled")
    assert queue.get(b)["state"] == "cancelled"
    assert printer.printed == []


def test_held_jobs_release(q):
    queue, printer, _ = q
    queue.start()
    jid = queue.enqueue(Image.new("1", (WIDTH, 10), 1), "Schedule", "x", held_until=time.time() + 0.3)
    assert queue.get(jid)["state"] == "held"
    time.sleep(0.1)
    queue.kick()
    assert wait_for(lambda: queue.get(jid)["state"] == "done", timeout=8)


def test_retention_prunes(q):
    queue, _, store = q
    store.set("app_settings", '{"history": {"max_items": 3, "max_days": 30}}')
    for i in range(6):
        jid = queue.enqueue(Image.new("1", (WIDTH, 5), 1), "Manual", str(i))
        store.conn().execute("UPDATE jobs SET state='done' WHERE id=?", (jid,))
    old = queue.log_missed("Schedule", "old", "off")
    store.conn().execute("UPDATE jobs SET created_at=0 WHERE id=?", (old,))
    queue.prune()
    assert len(queue.list(limit=100)) == 3
