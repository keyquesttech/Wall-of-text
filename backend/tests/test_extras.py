"""Fortunes (fair picks, CSV upload), paper roll estimate and calibration, history retention."""
import json
import random
import time

import pytest
from fastapi.testclient import TestClient

from walloftext import actions
from walloftext.app import create_app
from walloftext.services import build


@pytest.fixture
def svc(settings, fake_nm):
    return build(settings, nm=fake_nm)


@pytest.fixture
def client(svc):
    with TestClient(create_app(services=svc), base_url="http://walloftext.local") as c:
        c.post("/api/auth/login", json={"password": "root"})
        c.svc = svc
        yield c


def test_fortunes_never_repeat_within_a_round(svc):
    svc.store.set("custom_fortunes", json.dumps([f"F{i}" for i in range(10)]))
    svc.app_settings.patch({"fortunes": {"use_builtin": False}})
    rng = random.Random(1)
    t0 = 1_000_000.0
    first = [actions.pick_fortune(svc, t0 + i * 86400, rng) for i in range(10)]
    assert sorted(first) == [f"F{i}" for i in range(10)]  # every one once before any repeat


def test_new_round_avoids_last_weeks_fortunes(svc):
    svc.store.set("custom_fortunes", json.dumps([f"F{i}" for i in range(10)]))
    svc.app_settings.patch({"fortunes": {"use_builtin": False}})
    t0 = 1_000_000.0
    recent_hits = 0
    for seed in range(40):
        svc.store.set("fortune_state", "{}")
        rng = random.Random(seed)
        picks = [actions.pick_fortune(svc, t0 + i * 86400, rng) for i in range(10)]
        nxt = actions.pick_fortune(svc, t0 + 10 * 86400, rng)  # day 11: a new round starts
        recent_hits += nxt in picks[-6:]  # used in the last 7 days
    assert recent_hits <= 9  # expected ~3; without the weighting ~24 of 40 would be (6 of 10 are recent)


def test_builtin_used_when_nothing_uploaded(svc):
    svc.app_settings.patch({"fortunes": {"use_builtin": False}})
    assert actions.fortunes(svc) == actions.builtin_fortunes()


def test_fortunes_csv_api(client):
    r = client.post("/api/fortunes/csv", files={"file": ("f.csv", b'fortune,who\n"Be kind, always.",me\nDrink water,me\n', "text/csv")},
                    data={"mode": "replace"})
    assert r.status_code == 200 and r.json()["custom_count"] == 2 and r.json()["added"] == 2
    r = client.post("/api/fortunes/csv", files={"file": ("f.txt", b"Drink water\nNew one\n", "text/plain")}, data={"mode": "add"})
    assert r.json()["custom_count"] == 3 and r.json()["added"] == 1
    client.patch("/api/settings", json={"fortunes": {"use_builtin": False}})
    assert client.get("/api/fortunes").json()["in_play"] == 3
    csv_text = client.get("/api/fortunes/csv").content.decode("utf-8-sig")
    assert csv_text.splitlines()[0] == "fortune" and '"Be kind, always."' in csv_text
    assert client.post("/api/fortunes/csv", files={"file": ("e.csv", b"\n\n", "text/csv")}).status_code == 422
    assert client.delete("/api/fortunes/custom").json()["custom_count"] == 0


def test_paper_estimate_uses_roll_length_and_calibration(client):
    q = client.svc.queue
    time.sleep(0.5)  # let the start-up slip finish
    client.svc.store.set("rows_since_new_roll", "40000")  # 5 m at the nominal 0.125 mm/row
    client.patch("/api/settings", json={"printer": {"roll_length_m": 20}})
    assert q.paper_percent() == 75 and q.paper_left_m() == 15.0
    r = client.post("/api/printer/calibration", json={"measured_mm": 104}).json()
    assert r["mm_per_row"] == 0.13 and r["paper_percent"] == 74  # 40000 × 0.13 = 5.2 m of 20 m
    assert client.post("/api/printer/calibration", json={"measured_mm": 20}).status_code == 422
    assert client.post("/api/printer/calibration", json={}).json()["mm_per_row"] == 0.125
    assert client.post("/api/printer/calibration-print").status_code == 201


def test_history_kept_forever_when_limits_are_zero(svc):
    q = svc.queue
    q.log_missed("Schedule", "old", "x")
    svc.store.conn().execute("UPDATE jobs SET created_at=?", (time.time() - 400 * 86400,))
    svc.app_settings.patch({"history": {"max_days": 0, "max_items": 0}})
    assert q.prune() == 0
    svc.app_settings.patch({"history": {"max_days": 30}})
    assert q.prune() == 1


def test_date_and_time_api(client):
    t = client.get("/api/device/time").json()
    assert t["ntp"] is True and t["timezone"] == "Europe/London" and t["manual_this_boot"] is False
    target = (time.time() + 3600) * 1000
    t = client.put("/api/device/time", json={"epoch_ms": target}).json()
    assert t["ntp"] is False and t["manual_this_boot"] is True and abs(t["epoch"] * 1000 - target) < 5000
    t = client.put("/api/device/time", json={"timezone": "Europe/Madrid"}).json()
    assert t["timezone"] == "Europe/Madrid" and t["system_timezone"] == "Europe/Madrid"
    assert client.put("/api/device/time", json={"timezone": "Mars/Base"}).status_code == 422
    t = client.put("/api/device/time", json={"auto": True}).json()
    assert t["ntp"] is True and t["manual_this_boot"] is False


def test_scheduler_trusts_a_clock_set_by_hand_this_boot(svc):
    from walloftext.scheduler.engine import Scheduler
    svc.system.clock_synced = lambda: False
    sch = Scheduler(svc)
    assert sch.synced() is False
    svc.store.set("manual_clock_boot", svc.system.boot_id())
    assert sch.synced() is True
    svc.store.set("manual_clock_boot", "an-earlier-boot")  # set before a power cut: stale
    assert sch.synced() is False
