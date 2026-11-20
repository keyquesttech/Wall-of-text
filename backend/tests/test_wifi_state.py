"""Wi-Fi state machine against the fake NetworkManager (BUILD_PLAN 5.1, 5.7)."""
import pytest

from walloftext.config import CLIENT_CON_NAME
from walloftext.net.wifi import CONNECTING, FALLBACK_AP, ONLINE, SETUP_AP, WifiManager


def make(settings, nm, clock, psk="rootroot"):
    w = WifiManager(nm=nm, settings=settings, ap_password=lambda: psk, clock=clock)
    events = {"setup": 0, "online": []}
    w.on_setup.append(lambda: events.__setitem__("setup", events["setup"] + 1))
    w.on_online.append(lambda ssid, ip: events["online"].append((ssid, ip)))
    return w, events


async def boot(w):
    await w.start()
    w._task.cancel()  # drive ticks by hand


async def test_first_boot_without_saved_wifi_raises_setup_ap(settings, fake_nm, clock):
    w, ev = make(settings, fake_nm, clock)
    await boot(w)
    assert w.status.mode == SETUP_AP
    assert fake_nm.ap_on and fake_nm.ap_psk == "rootroot"
    assert ev["setup"] == 1
    assert "scan" in fake_nm.calls[: fake_nm.calls.index("ap_up")]  # scanned before the AP went up
    assert [n["ssid"] for n in w.scan_results()] == ["HomeWiFi", "Neighbour"]
    # setup AP stays put however long we wait
    clock.advance(3600)
    await w.tick()
    assert w.status.mode == SETUP_AP


async def test_setup_connect_success(settings, fake_nm, clock):
    w, ev = make(settings, fake_nm, clock)
    await boot(w)
    await w.connect("HomeWiFi", "correct-horse", security="wpa2")
    assert w.status.mode == ONLINE
    assert w.status.ssid == "HomeWiFi" and w.status.ip == "192.168.1.50"
    assert not fake_nm.ap_on
    assert ev["online"] == [("HomeWiFi", "192.168.1.50")]
    assert w.status.last_error is None


@pytest.mark.parametrize("ssid,pw,code", [("HomeWiFi", "wrong-pass", "wrong_password"),
                                          ("Nope", "whatever1", "not_found")])
async def test_setup_connect_failure_returns_to_ap_with_error(settings, fake_nm, clock, ssid, pw, code):
    w, ev = make(settings, fake_nm, clock)
    await boot(w)
    await w.connect(ssid, pw, security="wpa2")
    assert w.status.mode == SETUP_AP
    assert fake_nm.ap_on
    assert w.status.last_error == code
    assert ssid in w.status.last_error_text
    assert CLIENT_CON_NAME not in fake_nm.profiles  # failed profile deleted
    assert ev["online"] == []


async def test_boot_with_saved_wifi_goes_online(settings, fake_nm, clock):
    fake_nm.profiles["netplan-wlan0-Home"] = {"ssid": "HomeWiFi", "password": "correct-horse"}
    fake_nm.simulate_boot_autoconnect()
    w, ev = make(settings, fake_nm, clock)
    await boot(w)
    assert w.status.mode == CONNECTING
    await w.tick()
    assert w.status.mode == ONLINE
    assert ev["setup"] == 0 and not fake_nm.ap_on


async def test_power_cut_router_slower_than_pi(settings, fake_nm, clock):
    """Router off at boot → 120 s CONNECTING → FALLBACK_AP → router back → ONLINE."""
    fake_nm.profiles[CLIENT_CON_NAME] = {"ssid": "HomeWiFi", "password": "correct-horse"}
    fake_nm.router_up = False
    w, _ = make(settings, fake_nm, clock)
    await boot(w)
    clock.advance(119)
    await w.tick()
    assert w.status.mode == CONNECTING and not fake_nm.ap_on
    clock.advance(2)
    await w.tick()
    assert w.status.mode == FALLBACK_AP and fake_nm.ap_on
    # retry after 60 s fails while the router is still down; AP comes back
    clock.advance(61)
    await w.tick()
    assert w.status.mode == FALLBACK_AP and fake_nm.ap_on
    # router back
    fake_nm.router_up = True
    clock.advance(61)
    await w.tick()
    assert w.status.mode == ONLINE and not fake_nm.ap_on
    assert CLIENT_CON_NAME in fake_nm.profiles  # saved network kept


async def test_fallback_never_retries_while_a_phone_is_on_the_ap(settings, fake_nm, clock):
    fake_nm.profiles[CLIENT_CON_NAME] = {"ssid": "HomeWiFi", "password": "correct-horse"}
    fake_nm.router_up = False
    w, _ = make(settings, fake_nm, clock)
    await boot(w)
    clock.advance(121)
    await w.tick()
    assert w.status.mode == FALLBACK_AP
    fake_nm.router_up = True
    fake_nm.phones_on_ap = 1
    activations = sum(c.startswith("activate") for c in fake_nm.calls)
    for _ in range(5):
        clock.advance(61)
        await w.tick()
    assert w.status.mode == FALLBACK_AP
    assert sum(c.startswith("activate") for c in fake_nm.calls) == activations
    assert w.status.ap_clients == 1
    fake_nm.phones_on_ap = 0
    clock.advance(61)
    await w.tick()
    assert w.status.mode == ONLINE


async def test_link_lost_five_minutes_goes_connecting(settings, fake_nm, clock):
    fake_nm.profiles[CLIENT_CON_NAME] = {"ssid": "HomeWiFi", "password": "correct-horse"}
    fake_nm.simulate_boot_autoconnect()
    w, _ = make(settings, fake_nm, clock)
    await boot(w)
    await w.tick()
    assert w.status.mode == ONLINE
    fake_nm.router_up = False
    await w.tick()
    clock.advance(299)
    await w.tick()
    assert w.status.mode == ONLINE
    clock.advance(2)
    await w.tick()
    assert w.status.mode == CONNECTING
    clock.advance(121)
    await w.tick()
    assert w.status.mode == FALLBACK_AP


async def test_short_blip_does_not_change_mode(settings, fake_nm, clock):
    fake_nm.profiles[CLIENT_CON_NAME] = {"ssid": "HomeWiFi", "password": "correct-horse"}
    fake_nm.simulate_boot_autoconnect()
    w, _ = make(settings, fake_nm, clock)
    await boot(w)
    await w.tick()
    fake_nm.router_up = False
    await w.tick()
    clock.advance(100)
    fake_nm.router_up = True
    await w.tick()
    clock.advance(400)
    await w.tick()
    assert w.status.mode == ONLINE


async def test_reset_forgets_every_home_network(settings, fake_nm, clock):
    fake_nm.profiles["netplan-wlan0-Home"] = {"ssid": "HomeWiFi", "password": "correct-horse"}
    fake_nm.simulate_boot_autoconnect()
    w, ev = make(settings, fake_nm, clock)
    await boot(w)
    await w.tick()
    assert w.status.mode == ONLINE
    await w.reset()
    assert w.status.mode == SETUP_AP
    assert fake_nm.profiles == {}
    assert fake_nm.ap_on
    assert ev["setup"] == 1


async def test_new_network_replaces_imager_profile(settings, fake_nm, clock):
    fake_nm.profiles["netplan-wlan0-Old"] = {"ssid": "Gone", "password": "whatever1"}
    fake_nm.router_up = True
    w, _ = make(settings, fake_nm, clock)
    await boot(w)
    clock.advance(121)
    await w.tick()
    assert w.status.mode == FALLBACK_AP
    await w.connect("HomeWiFi", "correct-horse", security="wpa2")
    assert w.status.mode == ONLINE
    assert list(fake_nm.profiles) == [CLIENT_CON_NAME]


async def test_change_network_failure_goes_back_to_old_network(settings, fake_nm, clock):
    fake_nm.profiles["netplan-wlan0-Home"] = {"ssid": "HomeWiFi", "password": "correct-horse"}
    fake_nm.simulate_boot_autoconnect()
    w, _ = make(settings, fake_nm, clock)
    await boot(w)
    await w.tick()
    await w.connect("Neighbour", "not-the-password", security="wpa2")
    assert w.status.mode == ONLINE and w.status.ssid == "HomeWiFi"
    assert w.status.last_error == "wrong_password"


async def test_enterprise_is_refused_with_plain_sentence(settings, fake_nm, clock):
    w, _ = make(settings, fake_nm, clock)
    await boot(w)
    await w.connect("Office", None, security="enterprise")
    assert w.status.mode == SETUP_AP
    assert "username" in w.status.last_error_text


async def test_ap_password_is_rekeyed(settings, fake_nm, clock):
    w, _ = make(settings, fake_nm, clock)
    await boot(w)
    await w.apply_ap_password("brandnew-pass")
    assert fake_nm.ap_psk == "brandnew-pass"
