"""Button/light on-off and pins, the auxiliary fan, and WS2812 strips (mock hardware)."""
import time

import numpy as np
import pytest
from fastapi.testclient import TestClient

from walloftext.app import create_app
from walloftext.hw.fan import FanController, FanOutput, target_speed
from walloftext.hw.neopixel import encode, hex_rgb, render
from walloftext.hw.pins import problems
from walloftext.services import build


# ------------------------------------------------------------------- fan --
def test_fan_curve():
    c = {"mode": "temperature", "start_temp": 50, "full_temp": 70, "min_speed": 30, "max_speed": 90}
    assert target_speed(c, 45, running=False) == 0
    assert target_speed(c, 50, running=False) == 30  # starts at the minimum that spins it
    assert target_speed(c, 60, running=True) == 60
    assert target_speed(c, 75, running=True) == 90
    assert target_speed(c, 48, running=True) == 30  # 3 °C hysteresis before it stops
    assert target_speed(c, 46.9, running=True) == 0
    assert target_speed({**c, "mode": "always"}, 20, running=False) == 90
    assert target_speed(c, None, running=False) == 90  # no temperature: run it


def test_fan_kicks_from_rest_then_settles():
    t = {"now": 0.0}
    out = FanOutput(12)
    temp = {"c": 52.0}
    fc = FanController(out, lambda: {"start_temp": 50, "full_temp": 70, "min_speed": 30, "max_speed": 100},
                       lambda: temp["c"], clock=lambda: t["now"])
    fc.step()
    assert fc.speed == pytest.approx(37) and out.value == 1.0  # full power to get it turning
    t["now"] = 1.5
    fc.step()
    assert out.value == pytest.approx(0.37)
    temp["c"] = 40
    fc.step()
    assert out.value == 0 and fc.speed == 0


# ------------------------------------------------------------------ pins --
def test_pin_clashes_are_explained():
    base = {"button": {"enabled": True, "pin": 17}, "led": {"enabled": True, "pin": 18}}
    assert problems(base) == {}
    assert "already used by the button" in problems({**base, "led": {"enabled": True, "pin": 17}})["led"]
    assert problems({**base, "led": {"enabled": False, "pin": 17}}) == {}
    assert "serial console" in problems({**base, "fan": {"enabled": True, "pin": 14}})["fan"]
    neo = {"enabled": True, "strips": [{"pin": 10}]}
    clash = problems({**base, "fan": {"enabled": True, "pin": 11}, "neopixel": neo})
    assert "GPIO11" in clash["strip0"]  # SPI0 also takes its clock pin
    assert "GPIO10 or" not in problems({**base, "neopixel": {"enabled": True, "strips": [{"pin": 10}, {"pin": 20}]}}).get("strip1", "")
    assert "GPIO10" in problems({**base, "neopixel": {"enabled": True, "strips": [{"pin": 7}]}})["strip0"]
    assert "can't share" in problems({**base, "neopixel": {"enabled": True, "strips": [{"pin": 10}, {"pin": 10}]}})["strip1"]


# --------------------------------------------------------------- strips --
def test_ws2812_encoding():
    data = encode(np.array([[255, 0, 0]], dtype=np.uint8), "GRB")  # red, sent green-red-blue
    body = data[15:-15]
    assert len(body) == 9
    bits = "".join(f"{b:08b}" for b in body)
    g, r, b = bits[:24], bits[24:48], bits[48:]
    assert g == "100" * 8 and r == "110" * 8 and b == "100" * 8


def test_effects():
    red, blue = hex_rgb("#ff0000"), hex_rgb("#0000ff")
    assert render("solid", [red], 4, 0) == [red] * 4
    assert render("off", [red], 3, 0) == [(0, 0, 0)] * 3
    half = render("progress", [red, blue], 10, 0, progress=0.5)
    assert half[:5] == [red] * 5 and half[5] != red
    assert render("chase", [red], 6, 0).count(red) == 2
    assert len(set(render("rainbow", [], 12, 0))) > 6
    b0, b1 = render("breathe", [red], 1, 0), render("breathe", [red], 1, 1.0)
    assert b0 != b1


# --------------------------------------------------------------- manager --
@pytest.fixture
def client(settings, fake_nm):
    svc = build(settings, nm=fake_nm)
    with TestClient(create_app(services=svc), base_url="http://walloftext.local") as c:
        c.post("/api/auth/login", json={"password": "root"})
        c.svc = svc
        yield c


def test_switch_devices_on_and_off_and_move_pins(client):
    st = client.get("/api/hw").json()
    assert st["button"]["on"] and st["led"]["on"] and not st["fan"]["on"] and not st["neopixel"]["on"]
    client.patch("/api/settings", json={"led": {"enabled": False}})
    assert client.get("/api/hw").json()["led"]["on"] is False
    client.patch("/api/settings", json={"led": {"enabled": True, "pin": 17}})  # same pin as the button
    st = client.get("/api/hw").json()
    assert not st["led"]["on"] and "already used" in st["led"]["error"]
    client.patch("/api/settings", json={"led": {"pin": 23}})
    assert client.get("/api/hw").json()["led"]["on"]
    client.patch("/api/settings", json={"button": {"enabled": False}})
    assert client.post("/api/dev/button", json={"gesture": "single"}).status_code == 200  # ignored, no crash
    assert client.get("/api/hw").json()["button"]["on"] is False


def test_fan_and_strip_through_the_api(client):
    client.patch("/api/settings", json={"schedules": {"quiet_hours": {"enabled": False}}})  # no dimming at night
    assert client.post("/api/hw/fan/test").status_code == 409
    client.patch("/api/settings", json={"fan": {"enabled": True, "pin": 12, "mode": "always", "max_speed": 80}})
    st = client.get("/api/hw").json()["fan"]
    assert st["on"] and st["speed"] == 80
    assert client.post("/api/hw/fan/test").json()["ok"]
    client.patch("/api/settings", json={"neopixel": {"enabled": True, "strips": [{"pin": 10, "count": 8}],
                                                     "events": {"idle": {"effect": "solid", "colors": ["#ff0000"]},
                                                                "setup": {"effect": "solid", "colors": ["#ff0000"]}},
                                                     "brightness": 100}})
    for _ in range(40):
        live = client.get("/api/hw").json()["neopixel"]["live"]
        if live and live["frames"][0] and live["frames"][0][0] == "#ff0000":
            break
        time.sleep(0.05)
    assert live["frames"][0] == ["#ff0000"] * 8 and live["event"] in ("idle", "setup")  # no Wi-Fi in tests
    assert client.post("/api/hw/neopixel/try", json={"event": "error"}).json()["ok"]
    assert client.get("/api/hw").json()["neopixel"]["live"]["event"] == "error"
    client.patch("/api/settings", json={"neopixel": {"enabled": False}, "fan": {"enabled": False}})
    st = client.get("/api/hw").json()
    assert not st["neopixel"]["on"] and not st["fan"]["on"]


def test_fan_on_off_without_pwm():
    t = {"now": 0.0}
    temp = {"c": 52.0}
    out = FanOutput(12, pwm=False)
    cfg = {"start_temp": 50, "full_temp": 70, "min_speed": 30, "max_speed": 60}
    fc = FanController(out, lambda: cfg, lambda: temp["c"], clock=lambda: t["now"])
    fc.step()
    assert out.value == 1.0 and fc.speed == 100 and out.level() == "high (on)"  # fully on, never part-way
    temp["c"] = 48  # within the 3 °C hysteresis: stays on
    fc.step()
    assert out.value == 1.0
    temp["c"] = 46
    fc.step()
    assert out.value == 0 and out.level() == "low (off)"
    inv = FanOutput(12, pwm=False, invert=True)
    inv.set(1)
    assert inv.level() == "low (on)"  # relay boards that switch on when the pin is low


def test_fan_control_switch_through_the_api(client):
    client.patch("/api/settings", json={"fan": {"enabled": True, "pin": 12, "mode": "always", "control": "onoff", "max_speed": 40}})
    st = client.get("/api/hw").json()["fan"]
    assert st["on"] and st["pwm"] is False and st["speed"] == 100 and st["output"] == "high (on)"
    client.patch("/api/settings", json={"fan": {"control": "pwm"}})
    for _ in range(40):  # first a 1 s full-power kick to start it from rest, then 40 %
        st = client.get("/api/hw").json()["fan"]
        if st["output"] == "PWM 40%":
            break
        time.sleep(0.1)
    assert st["pwm"] is True and st["speed"] == 40 and st["output"] == "PWM 40%"


def test_colour_order_from_what_you_saw():
    from walloftext.hw.neopixel import order_from_test
    # green showed as blue (red was fine) with the default GRB → the strip is BRG
    assert order_from_test("GRB", "R", "B") == "BRG"
    # sending with the order we found shows the right colours
    for real in ("RGB", "GRB", "BRG", "RBG", "GBR", "BGR"):
        for cur in ("RGB", "GRB", "BRG", "RBG", "GBR", "BGR"):
            seen = lambda x: real[cur.index(x)]  # noqa: E731 - what a strip with order `real` shows
            assert order_from_test(cur, seen("R"), seen("G")) == real
    with pytest.raises(ValueError):
        order_from_test("GRB", "R", "R")


def test_colour_order_api(client):
    client.patch("/api/settings", json={"neopixel": {"enabled": True, "order": "GRB", "strips": [{"pin": 10, "count": 4}]}})
    assert client.post("/api/hw/neopixel/color", json={"color": "#00ff00"}).json()["ok"]
    for _ in range(40):
        f = client.get("/api/hw").json()["neopixel"]["live"]["frames"][0]
        if f[0] != "#000000" and f[0][3:5] != "00":
            break
        time.sleep(0.05)
    assert f[0][1:3] == "00" and f[0][5:7] == "00"  # green only
    assert client.post("/api/hw/neopixel/order", json={"saw_red": "R", "saw_green": "B"}).json() == {"order": "BRG"}
    assert client.get("/api/settings").json()["neopixel"]["order"] == "BRG"
    assert client.post("/api/hw/neopixel/order", json={"saw_red": "G", "saw_green": "G"}).status_code == 422
