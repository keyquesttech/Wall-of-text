"""Phase 7: templates, shared list, shopping list action and routine section."""
import time

import pytest
from fastapi.testclient import TestClient

from walloftext.app import create_app
from walloftext.services import build
from walloftext.templates_lists import BUILTIN_TEMPLATES, fill


@pytest.fixture
def c(settings, fake_nm):
    fake_nm.profiles["wot-client"] = {"ssid": "HomeWiFi", "password": "correct-horse"}
    fake_nm.simulate_boot_autoconnect()
    svc = build(settings, nm=fake_nm)
    with TestClient(create_app(services=svc), base_url="http://walloftext.local") as client:
        client.post("/api/auth/login", json={"password": "root"})
        client.svc = svc
        yield client


def test_every_builtin_template_renders(c):
    for t in BUILTIN_TEMPLATES:
        values = {f["key"]: "Milk\nEggs" if f.get("list") else "Hello" for f in t["fields"]}
        doc = fill(t, values)
        assert c.svc.renderer.render(doc).image.width == 384, t["id"]


def test_fill_lists_and_drops_empty_blocks():
    t = next(x for x in BUILTIN_TEMPLATES if x["id"] == "b-todo")
    doc = fill(t, {"items": "a\n\n b \n"})
    assert doc["blocks"][0]["text"] == "To do"
    assert doc["blocks"][1]["items"] == [{"text": "a"}, {"text": "b"}]
    sticker = next(x for x in BUILTIN_TEMPLATES if x["id"] == "b-sticker")
    assert [b["type"] for b in fill(sticker, {})["blocks"]] == ["sticker"]


def test_template_api(c):
    items = c.get("/api/templates").json()["items"]
    assert any(t["id"] == "b-wifi" for t in items)
    r = c.post("/api/templates/b-wifi/fill", json={"values": {"ssid": "Home", "password": "pw"}}).json()
    assert "WIFI:T:WPA;S:Home;P:pw;;" == r["document"]["blocks"][1]["data"]
    r = c.post("/api/templates/b-note/fill", json={"values": {"text": "hi"}, "print": True}).json()
    assert r["job"]["title"] == "Note to self"
    mine = c.post("/api/templates", json={"name": "Mine", "document": {"blocks": [{"type": "text", "text": "x"}]}}).json()
    assert mine["id"].startswith("u-") and not mine["builtin"]
    assert c.post(f"/api/templates/{mine['id']}/fill", json={}).json()["document"]["blocks"][0]["text"] == "x"
    assert c.post("/api/templates", json={"name": "Bad", "document": {"blocks": "x"}}).status_code == 422
    assert c.delete(f"/api/templates/{mine['id']}").json()["ok"]


def test_shopping_list_and_section(c):
    a = c.post("/api/lists/shopping", json={"text": "Milk"}).json()
    c.post("/api/lists/shopping", json={"text": "Bread"})
    assert c.patch(f"/api/lists/items/{a['id']}", json={"done": True}).json()["ok"]
    items = c.get("/api/lists/shopping").json()["items"]
    assert [i["text"] for i in items] == ["Bread", "Milk"] and items[1]["done"]
    assert c.post("/api/lists/shopping/clear-done").json()["removed"] == 1
    assert c.post("/api/lists/nope", json={"text": "x"}).status_code == 404
    j = c.post("/api/lists/shopping/print").json()["job"]
    full = c.get(f"/api/history/{j['id']}").json()
    assert full["document"]["blocks"][2]["items"] == [{"text": "Bread"}]
    r = c.post("/api/actions/shopping_list").json()
    assert "shopping" in r["message"]


async def test_shopping_section_skips_when_empty(c):
    src = c.svc.extras["sources"]
    assert await src.section_blocks({"type": "shopping"}, {}) == []
    c.svc.extras["lists"].add("shopping", "Tea")
    blocks = await src.section_blocks({"type": "shopping"}, {})
    assert blocks[1]["items"] == [{"text": "Tea"}]


def test_thumb_search_extra_feed_and_message_section(c):
    r = c.get("/api/templates/b-card/thumb")
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"
    j = c.post("/api/print", json={"document": {"blocks": [{"type": "text", "text": "Find me 50%"}]}, "extra_feed": 3}).json()["job"]
    assert j["meta"]["extra_feed"] == 3
    c.post("/api/print", json={"document": {"blocks": [{"type": "text", "text": "Other"}]}})
    assert [i["id"] for i in c.get("/api/history?q=find me").json()["items"]] == [j["id"]]
    assert c.get("/api/history?q=50%25").json()["items"][0]["id"] == j["id"]
    assert c.get("/api/history?q=zzz").json()["items"] == []
    s = c.post("/api/schedules", json={"name": "Msg", "time": "08:00", "sections": [
        {"type": "message", "document": {"blocks": [{"type": "text", "text": "Bins out"}]}}]}).json()
    r = c.post("/api/schedules/preview", json={"sections": s["sections"]})
    assert r.status_code == 200 and int(r.headers["x-wot-rows"]) > 10
