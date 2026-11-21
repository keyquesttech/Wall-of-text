from PIL import Image

from walloftext.hw.button import GestureDetector
from walloftext.hw.system import decode_throttled
from walloftext.net.captive import should_redirect
from walloftext.net.nm import classify_activation_error, classify_security, split_terse
from walloftext.printer.base import raster_bytes
from walloftext.render.slips import connected_slip, setup_slip, wifi_qr_payload


def detector():
    out, armed = [], []
    return GestureDetector(out.append, lambda: armed.append(1), clock=lambda: 0), out, armed


def test_single_resolves_after_double_window():
    d, out, _ = detector()
    d.press(0.0); d.release(0.1)
    d.poll(0.3)
    assert out == []
    d.poll(0.45)
    assert out == ["single"]


def test_double_press():
    d, out, _ = detector()
    d.press(0.0); d.release(0.1); d.press(0.2); d.release(0.3)
    d.poll(1.0)
    assert out == ["double"]


def test_long_press():
    d, out, _ = detector()
    d.press(0.0); d.release(0.9)
    d.poll(2.0)
    assert out == ["long"]


def test_bounce_is_ignored():
    d, out, _ = detector()
    d.press(0.0); d.release(0.01); d.press(0.02); d.release(0.12)
    d.poll(1.0)
    assert out == ["single"]


def test_thirty_second_hold_arms_then_resets_on_release():
    d, out, armed = detector()
    d.press(0.0)
    d.poll(10.0)
    d.poll(29.9)
    assert armed == []
    d.poll(30.0)
    assert armed == [1]
    d.release(30.5)
    assert out == ["reset"]


def test_ten_second_hold_is_just_a_long_press_now():
    d, out, _ = detector()
    d.press(0.0)
    d.release(10.5)
    assert out == ["long"]


def test_nmcli_terse_split():
    assert split_terse(r"My\:Net:72:WPA2:2437 MHz") == ["My:Net", "72", "WPA2", "2437 MHz"]


def test_security_classes():
    assert classify_security("") == "open"
    assert classify_security("WPA1 WPA2") == "wpa2"
    assert classify_security("WPA2 WPA3") == "wpa2/wpa3"
    assert classify_security("WPA3") == "wpa3"
    assert classify_security("WPA2 802.1X") == "enterprise"


def test_activation_errors():
    assert classify_activation_error("Error: Connection activation failed: Secrets were required, but not provided") == "wrong_password"
    assert classify_activation_error("Error: No network with SSID 'x' found.") == "not_found"
    assert classify_activation_error("IP configuration could not be reserved") == "no_ip"


def test_captive_rules():
    own = {"walloftext.local", "10.42.0.1"}
    assert should_redirect("/hotspot-detect.html", "captive.apple.com", own)
    assert should_redirect("/generate_204", "10.42.0.1", own)
    assert should_redirect("/", "example.com", own)
    assert not should_redirect("/setup", "10.42.0.1", own)


def test_wifi_qr_escaping():
    assert wifi_qr_payload("WallOfText-Setup", "root;root") == "WIFI:T:WPA;S:WallOfText-Setup;P:root\\;root;;"


def test_slips_are_384_wide_1bit(settings):
    for img in (setup_slip(settings.fonts_dir, "rootroot"), connected_slip(settings.fonts_dir, "Home", "192.168.1.9")):
        assert img.mode == "1" and img.width == 384 and 200 < img.height < 2000


def test_raster_bands():
    img = Image.new("1", (384, 50), 1)
    img.putpixel((0, 0), 0)
    bands = raster_bytes(img, band_rows=24)
    assert len(bands) == 3
    assert bands[0][:8] == b"\x1dv0\x00\x30\x00\x18\x00"
    assert bands[0][8] == 0x80  # leftmost dot of row 0 is black
    assert bands[2][6] == 2  # last band has 2 rows


def test_throttle_flags():
    assert decode_throttled(0x50005) == ["under_voltage", "throttled", "under_voltage_since_boot",
                                         "throttled_since_boot"]


def test_sd_notify(tmp_path, monkeypatch):
    import socket
    from walloftext import watchdog

    path = str(tmp_path / "n.sock")
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    srv.bind(path)
    monkeypatch.setenv("NOTIFY_SOCKET", path)
    monkeypatch.setenv("WATCHDOG_USEC", "60000000")
    assert watchdog.notify("READY=1")
    assert srv.recv(64) == b"READY=1"
    assert watchdog.interval_s() == 30
    monkeypatch.delenv("NOTIFY_SOCKET")
    assert watchdog.notify("WATCHDOG=1") is False
    srv.close()
