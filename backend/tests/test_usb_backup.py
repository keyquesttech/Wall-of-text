"""Scheduled USB backups (Settings › Backup), with a folder standing in for the drive."""
import io
import zipfile
from datetime import datetime

import pytest

from walloftext.services import build
from walloftext.usb_backup import FOLDER, UsbBackup


@pytest.fixture
def svc(settings, fake_nm, tmp_path, monkeypatch):
    drive = tmp_path / "usb"
    drive.mkdir()
    monkeypatch.setenv("WOT_USB_DIR", str(drive))
    s = build(settings, nm=fake_nm)
    s.drive = drive
    return s


def ts(*a):
    return datetime(*a).timestamp()


def test_backup_writes_a_restorable_zip_and_keeps_the_newest(svc):
    clock = [ts(2026, 11, 22, 3, 0)]
    usb = UsbBackup(svc, clock=lambda: clock[0])
    svc.app_settings.patch({"backup": {"keep": 2}})
    names = []
    for i in range(3):
        import walloftext.api.backup as b
        orig = b.build_zip
        b.build_zip = lambda s, i=i: (f"walloftext-backup-2026112{i}-0300.zip", orig(s)[1])
        try:
            res = usb.run_now()
        finally:
            b.build_zip = orig
        assert res["ok"], res
        names.append(res["file"])
    files = sorted(p.name for p in (svc.drive / FOLDER).iterdir())
    assert files == ["walloftext-backup-20261121-0300.zip", "walloftext-backup-20261122-0300.zip"]
    z = zipfile.ZipFile(io.BytesIO((svc.drive / FOLDER / files[-1]).read_bytes()))
    assert "settings.json" in z.namelist() and "manifest.json" in z.namelist()
    assert usb.state()["last"]["ok"]


def test_schedule_runs_once_per_due_time_and_retries_without_a_drive(svc, monkeypatch):
    clock = [ts(2026, 11, 22, 2, 0)]  # Sunday
    usb = UsbBackup(svc, clock=lambda: clock[0])
    assert not usb.due_now()  # off by default
    svc.app_settings.patch({"backup": {"usb_enabled": True, "frequency": "weekly", "weekday": 6, "time": "03:00"}})
    # last due was Sun 15 Nov 03:00: never done, so it runs now
    assert usb.due_now()
    usb.svc.store.set("usb_backup_state", '{"done_for": %d}' % ts(2026, 11, 15, 3, 0))
    assert not usb.due_now()
    clock[0] = ts(2026, 11, 22, 3, 0, 30)
    assert usb.due_now()
    assert usb.next_due(datetime.fromtimestamp(clock[0])) == datetime(2026, 11, 29, 3, 0)
    # no drive: fails, then waits 15 min before trying again
    monkeypatch.setenv("WOT_USB_DIR", str(svc.drive / "missing"))
    import asyncio
    asyncio.run(usb.tick())
    assert not usb.state()["last"]["ok"] and "No USB drive" in usb.state()["last"]["message"]
    assert not usb.due_now()
    clock[0] += 16 * 60
    assert usb.due_now()
    monkeypatch.setenv("WOT_USB_DIR", str(svc.drive))
    asyncio.run(usb.tick())
    assert usb.state()["last"]["ok"] and not usb.due_now()


def test_daily_and_monthly_times(svc):
    usb = UsbBackup(svc)
    svc.app_settings.patch({"backup": {"frequency": "daily", "time": "21:30"}})
    assert usb.last_due(datetime(2026, 11, 24, 8, 0)) == datetime(2026, 11, 23, 21, 30)
    svc.app_settings.patch({"backup": {"frequency": "monthly", "time": "03:00"}})
    assert usb.last_due(datetime(2026, 11, 24, 8, 0)) == datetime(2026, 11, 1, 3, 0)
    assert usb.next_due(datetime(2026, 11, 24, 8, 0)) == datetime(2026, 12, 1, 3, 0)
