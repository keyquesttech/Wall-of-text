"""HTTP-level checks: sign-in, captive redirects, cross-site rules, Wi-Fi routes."""
import os
import time

import pytest
from fastapi.testclient import TestClient

from walloftext.app import create_app
from walloftext.services import build

JSON = {"Content-Type": "application/json"}


@pytest.fixture
def svc(settings, fake_nm):
    return build(settings, nm=fake_nm)


@pytest.fixture
def client(svc):
    with TestClient(create_app(services=svc), base_url="http://walloftext.local") as c:
        yield c


@pytest.fixture
def online(svc, fake_nm, settings):
    fake_nm.profiles["wot-client"] = {"ssid": "HomeWiFi", "password": "correct-horse"}
    fake_nm.simulate_boot_autoconnect()
    with TestClient(create_app(services=svc), base_url="http://walloftext.local") as c:
        import asyncio
        for _ in range(50):
            c.portal.call(svc.wifi.tick)
            if svc.wifi.status.mode == "online":
                break
            time.sleep(0.02)
        assert svc.wifi.status.mode == "online"
        yield c


def login(c, pw="root"):
    return c.post("/api/auth/login", json={"password": pw, "remember": True})


def test_root_redirects_to_signin_when_online(online):
    r = online.get("/", follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"].startswith("/signin")
    assert online.get("/api/device").status_code == 401
    assert online.get("/signin").status_code == 200
    assert online.get("/api/health").json() == {"ok": True}


def test_login_good_and_bad(online):
    assert login(online, "nope").status_code == 401
    r = login(online)
    assert r.status_code == 200
    assert "httponly" in r.headers["set-cookie"].lower()
    assert "samesite=lax" in r.headers["set-cookie"].lower()
    assert online.get("/api/device").status_code == 200
    assert online.get("/", follow_redirects=False).status_code == 200


def test_lockout_after_five_wrong(online):
    for _ in range(5):
        assert login(online, "bad").status_code == 401
    r = login(online)
    assert r.status_code == 429 and int(r.headers["retry-after"]) > 0


def test_file_edit_signs_everyone_out(online, settings):
    login(online)
    assert online.get("/api/device").status_code == 200
    p = settings.password_file
    p.write_text("gui_password=changed1\nsetup_wifi_password=rootroot\n")
    st = p.stat()
    os.utime(p, ns=(st.st_atime_ns, st.st_mtime_ns + 5_000_000))
    assert online.get("/api/device").status_code == 401
    assert login(online, "root").status_code == 401
    assert login(online, "changed1").status_code == 200


def test_change_password_keeps_this_device(online, svc):
    login(online)
    r = online.post("/api/auth/password", json={"current": "root", "new": "abc"})
    assert r.status_code == 422
    r = online.post("/api/auth/password", json={"current": "root", "new": "newpass"})
    assert r.status_code == 200
    assert online.get("/api/device").status_code == 200
    assert online.get("/api/auth/status").json()["default_password_in_use"] is False


def test_change_setup_wifi_password_rekeys_ap(online, svc, fake_nm):
    login(online)
    assert online.post("/api/auth/setup-wifi-password",
                       json={"current_password": "root", "new": "root"}).status_code == 422
    r = online.post("/api/auth/setup-wifi-password", json={"current_password": "root", "new": "hello-setup"})
    assert r.status_code == 200
    online.portal.call(lambda: __import__("asyncio").sleep(0.05))
    assert fake_nm.ap_psk == "hello-setup"


def test_cross_site_rules(online):
    login(online)
    r = online.post("/api/auth/logout", content="x", headers={"Content-Type": "text/plain"})
    assert r.status_code == 415
    r = online.post("/api/auth/logout", json={}, headers={"Origin": "http://evil.example"})
    assert r.status_code == 403
    r = online.post("/api/auth/logout", json={}, headers={"Host": "evil.example"})
    assert r.status_code == 403


def test_setup_mode_captive_and_open_wifi_routes(client, svc, fake_nm):
    assert svc.wifi.status.mode == "setup_ap"
    r = client.get("/hotspot-detect.html", headers={"Host": "captive.apple.com"}, follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"] == "http://10.42.0.1/setup"
    r = client.get("/generate_204", headers={"Host": "connectivitycheck.gstatic.com"}, follow_redirects=False)
    assert r.status_code == 302
    r = client.get("/", follow_redirects=False)
    assert r.headers["location"] == "/setup"
    assert client.get("/setup").status_code == 200
    assert client.get("/api/wifi/status").json()["mode"] == "setup_ap"
    assert [n["ssid"] for n in client.get("/api/wifi/scan").json()][0] == "HomeWiFi"
    assert client.get("/api/device").status_code == 401  # rest of the site still needs sign-in
    # reset needs a signed-in session even in AP mode
    assert client.post("/api/wifi/reset", json={"confirm": True}).status_code == 401


def test_setup_connect_flow(client, svc, fake_nm):
    r = client.post("/api/wifi/connect", json={"ssid": "HomeWiFi", "password": "short", "security": "wpa2"})
    assert r.status_code == 422
    r = client.post("/api/wifi/connect", json={"ssid": "HomeWiFi", "password": "correct-horse", "security": "wpa2"})
    assert r.status_code == 202
    client.portal.call(lambda: __import__("asyncio").sleep(0.1))
    assert svc.wifi.status.mode == "online"
    # setup routes are closed again once online
    assert client.get("/api/wifi/scan").status_code == 401
    # setup slip on boot + connected slip were "printed" by the mock printer
    assert len(svc.printer.printed) == 2


def test_wifi_reset_via_site(online, svc, fake_nm):
    login(online)
    assert online.post("/api/wifi/reset", json={"confirm": False}).status_code == 400
    assert online.post("/api/wifi/reset", json={"confirm": True}).status_code == 200
    online.portal.call(lambda: __import__("asyncio").sleep(0.1))
    assert svc.wifi.status.mode == "setup_ap" and fake_nm.profiles == {}


def test_button_reset_via_dev_route(online, svc, fake_nm):
    online.post("/api/dev/button", json={"gesture": "reset"})
    online.portal.call(lambda: __import__("asyncio").sleep(0.1))
    assert svc.wifi.status.mode == "setup_ap"


def test_ask_for_password_off_opens_site(online):
    login(online)
    online.post("/api/auth/ask-for-password", json={"ask_for_password": False})
    online.post("/api/auth/logout", json={})
    assert online.get("/api/device").status_code == 200
