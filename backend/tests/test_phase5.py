"""Phase 5: guest page, shared approval list, backup/restore, paper saver."""
import io
import json
import time
import zipfile

import pytest
from fastapi.testclient import TestClient

from walloftext.app import create_app
from walloftext.services import build


def wait(cond, t=5):
    end = time.time() + t
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.03)
    return False


@pytest.fixture
def c(settings, fake_nm):
    fake_nm.profiles["wot-client"] = {"ssid": "HomeWiFi", "password": "correct-horse"}
    fake_nm.simulate_boot_autoconnect()
    svc = build(settings, nm=fake_nm)
    svc.app_settings.patch({"schedules": {"quiet_hours": {"enabled": False}}})
    with TestClient(create_app(services=svc), base_url="http://walloftext.local") as client:
        for _ in range(50):
            client.portal.call(svc.wifi.tick)
            if svc.wifi.status.mode == "online":
                break
            time.sleep(0.02)
        client.post("/api/auth/login", json={"password": "root"})
        client.svc = svc
        yield client


def guest(c):
    return TestClient(c.app, base_url="http://walloftext.local")


def test_guest_page_closed_by_default(c):
    g = guest(c)
    assert g.get("/note").status_code == 200
    assert g.get("/api/guest").json()["enabled"] is False
    assert g.post("/api/note", json={"text": "hi"}).status_code == 403
    assert g.get("/api/inbox").status_code == 401  # the list itself needs sign-in


def test_guest_note_waits_for_ok_then_prints(c):
    c.patch("/api/settings", json={"guest": {"enabled": True, "mode": "approve"}})
    g = guest(c)
    r = g.post("/api/note", json={"name": "Ann", "text": "Hello from the hallway", "sticker": "heart"})
    assert r.status_code == 201 and r.json()["status"] == "waiting"
    items = c.get("/api/inbox").json()["items"]
    assert len(items) == 1 and items[0]["sender"] == "Ann" and items[0]["source"] == "Guest"
    j = c.post(f"/api/inbox/{items[0]['id']}/approve").json()["job"]
    assert j["source"] == "Guest"
    assert wait(lambda: c.get(f"/api/history/{j['id']}").json()["state"] == "done")
    assert c.get("/api/inbox").json()["items"] == []
    assert c.post(f"/api/inbox/{items[0]['id']}/approve").status_code == 404


def test_guest_decline_and_print_mode_and_limits(c):
    c.patch("/api/settings", json={"guest": {"enabled": True, "mode": "approve", "max_chars": 10, "rate_per_10min": 3}})
    g = guest(c)
    assert g.post("/api/note", json={"text": "x" * 11}).status_code == 422
    assert g.post("/api/note", json={"text": ""}).status_code == 422
    assert g.post("/api/note", json={"text": "hi", "sticker": "bogus"}).status_code == 422
    g.post("/api/note", json={"text": "one"})
    iid = c.get("/api/inbox").json()["items"][0]["id"]
    assert c.post(f"/api/inbox/{iid}/decline").json()["ok"]
    c.patch("/api/settings", json={"guest": {"mode": "print"}})
    r = g.post("/api/note", json={"text": "two"})
    assert r.json()["status"] == "printing"
    assert g.post("/api/note", json={"text": "three"}).status_code == 429  # 3 per 10 min (one rejected earlier)


def test_inbox_led_event(c):
    c.patch("/api/settings", json={"guest": {"enabled": True}})
    guest(c).post("/api/note", json={"text": "hey"})
    assert c.svc.led_ctl.waiting == 1 and c.svc.led.pattern == "slow_pulse"


def test_backup_roundtrip_excludes_secrets(c, settings):
    c.patch("/api/settings", json={"printer": {"darkness": 77}})
    c.post("/api/schedules", json={"name": "Morning", "time": "07:00", "sections": [{"type": "fortune"}]})
    data = (settings.fonts_dir / "VT323-Regular.ttf").read_bytes()
    c.post("/api/fonts", files={"file": ("Mine.ttf", data, "font/ttf")}, data={"name": "Mine"})
    (settings.data_dir / "stray-token.json").write_text('{"refresh_token": "SECRET"}')
    r = c.get("/api/backup")
    assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
    z = zipfile.ZipFile(io.BytesIO(r.content))
    names = set(z.namelist())
    assert {"manifest.json", "settings.json", "schedules.json"} <= names
    assert any(n.startswith("fonts/u-mine") for n in names)
    blob = b"".join(z.read(n) for n in names)
    assert b"SECRET" not in blob and b"gui_password" not in blob and b"rootroot" not in blob
    # wipe and restore
    c.patch("/api/settings", json={"printer": {"darkness": 120}})
    for s in c.get("/api/schedules").json()["items"]:
        c.delete(f"/api/schedules/{s['id']}")
    res = c.post("/api/backup", files={"file": ("b.zip", r.content, "application/zip")}).json()
    assert "settings" in res["restored"] and "schedules" in res["restored"]
    assert c.get("/api/settings").json()["printer"]["darkness"] == 77
    assert [s["name"] for s in c.get("/api/schedules").json()["items"]] == ["Morning"]
    bad = c.post("/api/backup", files={"file": ("x.zip", b"not a zip", "application/zip")})
    assert bad.status_code == 422


def test_backup_rejects_path_tricks(c, settings):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("manifest.json", json.dumps({"app": "walloftext"}))
        z.writestr("fonts/fonts.json", json.dumps({"x": {"name": "x", "file": "../../evil.ttf"}}))
        z.writestr("fonts/../../evil.ttf", b"boom")
    c.post("/api/backup", files={"file": ("b.zip", buf.getvalue(), "application/zip")})
    assert not (settings.data_dir.parent / "evil.ttf").exists()
    assert not (settings.data_dir / "evil.ttf").exists()


def test_paper_saver_shortens_prints(c):
    doc = {"blocks": [{"type": "text", "text": "a"}, {"type": "text", "text": "b"}, {"type": "spacer", "height": 40}]}
    full = int(c.post("/api/preview", json={"document": doc}).headers["x-wot-rows"])
    c.patch("/api/settings", json={"printer": {"paper_saver": True}})
    saved = int(c.post("/api/preview", json={"document": doc}).headers["x-wot-rows"])
    assert saved < full - 40
