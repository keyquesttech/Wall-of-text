"""Phase 2/3 HTTP checks: preview, print, queue, history, printer, fonts, settings."""
import io
import time

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from walloftext.app import create_app
from walloftext.services import build

DOC = {"blocks": [{"type": "text", "text": "Hello", "size": "L"}]}


@pytest.fixture
def c(settings, fake_nm):
    fake_nm.profiles["wot-client"] = {"ssid": "HomeWiFi", "password": "correct-horse"}
    fake_nm.simulate_boot_autoconnect()
    svc = build(settings, nm=fake_nm)
    with TestClient(create_app(services=svc), base_url="http://walloftext.local") as client:
        for _ in range(50):
            client.portal.call(svc.wifi.tick)
            if svc.wifi.status.mode == "online":
                break
            time.sleep(0.02)
        assert client.post("/api/auth/login", json={"password": "root"}).status_code == 200
        client.svc = svc
        yield client


def wait(cond, t=5):
    end = time.time() + t
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.03)
    return False


def test_preview_png_matches_printed_bitmap(c):
    r = c.post("/api/preview", json={"document": DOC})
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"
    assert int(r.headers["x-wot-rows"]) > 20
    preview = Image.open(io.BytesIO(r.content)).convert("1")
    j = c.post("/api/print", json={"document": DOC}).json()["job"]
    assert j["title"] == "Hello" and j["source"] == "Manual"
    assert wait(lambda: c.get(f"/api/history/{j['id']}").json()["state"] == "done")
    stored = Image.open(io.BytesIO(c.get(f"/api/history/{j['id']}/image").content)).convert("1")
    assert stored.tobytes() == preview.tobytes()
    printed = Image.open(c.svc.printer.printed[-1]).convert("1")
    assert printed.tobytes() == preview.tobytes()


def test_bad_document_is_422(c):
    r = c.post("/api/preview", json={"document": {"blocks": "nope"}})
    assert r.status_code == 422


def test_history_filter_and_reprint(c):
    j = c.post("/api/print", json={"document": DOC, "copies": 2}).json()["job"]
    assert wait(lambda: c.get(f"/api/history/{j['id']}").json()["state"] == "done")
    items = c.get("/api/history?source=Manual").json()["items"]
    assert [i["id"] for i in items][:1] == [j["id"]]
    assert c.get("/api/history?source=Remote").json()["items"] == []
    assert c.get("/api/history?source=Bogus").status_code == 400
    r = c.post(f"/api/history/{j['id']}/reprint").json()["job"]
    assert r["id"] != j["id"] and r["copies"] == 2
    assert wait(lambda: c.get(f"/api/history/{r['id']}").json()["state"] == "done")
    assert c.delete(f"/api/history/{j['id']}").json()["ok"]


def test_paper_out_holds_queue_and_new_roll_releases(c):
    assert c.post("/api/printer/paper-out", json={"out": True}).json()["state"] == "paper_out"
    j = c.post("/api/print", json={"document": DOC}).json()["job"]
    time.sleep(0.3)
    assert c.get("/api/queue").json()["jobs"][0]["id"] == j["id"]
    st = c.post("/api/printer/new-roll").json()
    assert st["paper_percent"] == 100
    assert wait(lambda: c.get(f"/api/history/{j['id']}").json()["state"] == "done")


def test_cancel_all(c):
    c.svc.printer.offline = True
    for _ in range(3):
        c.post("/api/print", json={"document": DOC})
    assert c.post("/api/queue/cancel-all").json()["cancelled"] == 3
    assert c.get("/api/queue").json()["jobs"] == []


def test_test_page_and_fonts(c):
    assert c.post("/api/printer/test-page").status_code == 201
    fonts = c.get("/api/fonts").json()
    assert {f["id"] for f in fonts} >= {"mono", "pixel", "silk", "sans"}
    data = (c.svc.settings.fonts_dir / "VT323-Regular.ttf").read_bytes()
    r = c.post("/api/fonts", files={"file": ("Mine.ttf", data, "font/ttf")}, data={"name": "Mine"})
    assert r.status_code == 201
    fid = r.json()["id"]
    assert c.get(f"/api/fonts/{fid}/file").status_code == 200
    assert c.delete(f"/api/fonts/{fid}").json()["ok"]
    bad = c.post("/api/fonts", files={"file": ("x.ttf", b"nope", "font/ttf")})
    assert bad.status_code == 422


def test_settings_patch_drops_unknown_keys(c):
    s = c.patch("/api/settings", json={"printer": {"darkness": 90, "bogus": 1}, "nope": {}}).json()
    assert s["printer"]["darkness"] == 90 and "bogus" not in s["printer"] and "nope" not in s
    assert c.get("/api/settings").json()["printer"]["darkness"] == 90


def test_spa_fallback_and_assets_need_sign_in(c, settings, tmp_path):
    # with no frontend build in the test settings, / serves the placeholder
    assert c.get("/").status_code == 200
    c.post("/api/auth/logout", json={})
    assert c.get("/history", follow_redirects=False).status_code == 302
