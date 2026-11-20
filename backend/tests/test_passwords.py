import os
import stat
import time

from walloftext.auth.passwords import PasswordFile, parse, validate_wifi


def test_missing_file_recreated_with_defaults(tmp_path):
    p = tmp_path / "etc" / "passwords.txt"
    pf = PasswordFile(p)
    assert p.exists()
    assert stat.S_IMODE(p.stat().st_mode) == 0o600
    text = p.read_text()
    assert "gui_password=root\n" in text and "setup_wifi_password=rootroot\n" in text
    assert pf.state.default_gui and pf.state.default_wifi


def _touch_write(p, text):
    p.write_text(text)
    st = p.stat()
    os.utime(p, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000))


def test_edit_applies_without_restart_and_fires_hooks(tmp_path):
    p = tmp_path / "passwords.txt"
    pf = PasswordFile(p)
    gui_events, wifi_events = [], []
    pf.on_gui_change.append(lambda: gui_events.append(1))
    pf.on_wifi_change.append(wifi_events.append)
    _touch_write(p, "gui_password=hunter22\nsetup_wifi_password=newsetup99\n")
    assert pf.refresh() is True
    assert pf.state.gui_password == "hunter22"
    assert pf.state.setup_wifi_password == "newsetup99"
    assert gui_events == [1] and wifi_events == ["newsetup99"]
    assert pf.refresh() is False  # unchanged mtime: no re-read


def test_bad_values_keep_previous_and_warn(tmp_path):
    p = tmp_path / "passwords.txt"
    pf = PasswordFile(p)
    _touch_write(p, "gui_password=\nsetup_wifi_password=short\n")
    pf.refresh()
    assert pf.state.gui_password == "root"
    assert pf.state.setup_wifi_password == "rootroot"
    assert any("too short" in w for w in pf.state.warnings)


def test_gui_write_is_atomic_and_keeps_mode(tmp_path):
    p = tmp_path / "passwords.txt"
    pf = PasswordFile(p)
    pf.set_gui("letmein")
    assert parse(p.read_text())["gui_password"] == "letmein"
    assert stat.S_IMODE(p.stat().st_mode) == 0o600
    assert not [f for f in os.listdir(tmp_path) if f.startswith(".passwords.")]


def test_wpa2_rules():
    assert validate_wifi("root")  # too short for WPA2
    assert validate_wifi("x" * 64)
    assert validate_wifi("rootroot") is None
    assert validate_wifi("cafécafé")  # non-ASCII rejected


def test_value_may_contain_equals_and_hash(tmp_path):
    p = tmp_path / "passwords.txt"
    pf = PasswordFile(p)
    _touch_write(p, "# comment\ngui_password=a=b#c\nsetup_wifi_password=rootroot\n")
    pf.refresh()
    assert pf.state.gui_password == "a=b#c"
