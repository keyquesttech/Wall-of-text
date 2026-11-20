"""Phase 3: button gestures → actions, LED patterns, failed jobs and retry over HTTP."""
import time

import pytest
from fastapi.testclient import TestClient

from walloftext.app import create_app
from walloftext.hw.led import MockLed
from walloftext.hw.led_controller import LedController
from walloftext.services import build
from walloftext.store.settings import DEFAULTS


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
    with TestClient(create_app(services=svc), base_url="http://walloftext.local") as client:
        for _ in range(50):
            client.portal.call(svc.wifi.tick)
            if svc.wifi.status.mode == "online":
                break
            time.sleep(0.02)
        client.post("/api/auth/login", json={"password": "root"})
        client.svc = svc
        yield client


def test_led_priorities():
    led = MockLed()
    ctl = LedController(led, lambda: DEFAULTS)
    assert ctl.update() == "off"  # idle
    ctl.on_event("inbox", {"waiting": 2})
    assert led.pattern == "slow_pulse"
    ctl.on_event("printer", {"state": "printing"})
    assert led.pattern == "blink"
    ctl.on_event("printer", {"state": "paper_out"})
    assert led.pattern == "solid"
    ctl.on_event("wifi", {"mode": "setup_ap"})
    assert led.pattern == "slow_pulse"
    ctl.on_event("wifi", {"mode": "online"})
    ctl.on_event("printer", {"state": "offline"})
    assert led.pattern == "blink"
    assert abs(led.brightness - 0.6) < 1e-9


def test_single_press_reprints_last(c):
    j = c.post("/api/print", json={"document": {"blocks": [{"type": "text", "text": "Hi"}]}}).json()["job"]
    assert wait(lambda: c.get(f"/api/history/{j['id']}").json()["state"] == "done")
    c.post("/api/dev/button", json={"gesture": "single"})
    assert wait(lambda: any(i["source"] == "Button" and i["title"] == "Hi"
                            for i in c.get("/api/history?source=Button").json()["items"]))


def test_gesture_mapping_is_configurable(c):
    c.patch("/api/settings", json={"button": {"double": "random_fortune"}})
    c.post("/api/dev/button", json={"gesture": "double"})
    assert wait(lambda: any(i["title"] == "Fortune" for i in c.get("/api/history?source=Button").json()["items"]))


def test_actions_api(c):
    ids = [a["id"] for a in c.get("/api/actions").json()]
    assert "random_fortune" in ids and "cancel_queue" in ids
    r = c.post("/api/actions/random_fortune").json()
    assert r["ok"] and "fortune" in r["message"]
    assert c.post("/api/actions/nope").status_code == 404
    c.svc.printer.offline = True
    c.post("/api/actions/random_fortune")
    assert "Cancelled 1" in c.post("/api/actions/cancel_queue").json()["message"]


def test_offline_failure_then_retry(c):
    # driver vanishes mid-print -> failed (offline) with a retry path
    printer = c.svc.printer
    orig = printer.print_bitmap

    def boom(*a, **k):
        raise FileNotFoundError("gone")

    printer.print_bitmap = boom
    j = c.post("/api/print", json={"document": {"blocks": [{"type": "text", "text": "x"}]}}).json()["job"]
    assert wait(lambda: c.get(f"/api/history/{j['id']}").json()["state"] == "failed")
    assert c.get(f"/api/history/{j['id']}").json()["error"].startswith("offline")
    printer.print_bitmap = orig
    r = c.post(f"/api/jobs/{j['id']}/retry").json()["job"]
    assert wait(lambda: c.get(f"/api/history/{r['id']}").json()["state"] == "done")
