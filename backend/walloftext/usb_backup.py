"""Scheduled backups to a USB drive (Settings › Backup › Backup to USB).

The same zip as Settings › Backup › Download (settings, schedules, templates, lists, fonts; never
passwords or secrets) is written to `WallOfText-backups/` on the first USB drive found. The drive
is mounted through udisks2 (polkit lets the service user do this, see deploy/polkit) and, if this
code mounted it, unmounted again afterwards so it is safe to pull out.

For tests and dev machines, WOT_USB_DIR names a folder that stands in for a mounted drive.
"""
from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .services import Services

log = logging.getLogger(__name__)

FOLDER = "WallOfText-backups"
FILESYSTEMS = {"vfat", "exfat", "ntfs", "ntfs3", "ext4", "ext3", "ext2", "btrfs", "f2fs", "hfsplus"}
RETRY_S = 15 * 60
STATE_KEY = "usb_backup_state"


class UsbError(Exception):
    pass


def _run(cmd: list[str], timeout: int = 30) -> str:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise UsbError(str(exc)) from exc
    if r.returncode != 0:
        raise UsbError((r.stderr or r.stdout).strip()[:200] or f"{cmd[0]} failed")
    return r.stdout


def drives() -> list[dict]:
    """USB storage with a filesystem: [{path, label, size, mountpoint, fstype}]."""
    fake = os.environ.get("WOT_USB_DIR")
    if fake:
        return [{"path": "fake", "label": "Test drive", "size": 0, "mountpoint": fake, "fstype": "vfat"}] \
            if Path(fake).is_dir() else []
    try:
        out = json.loads(_run(["lsblk", "-J", "-b", "-o", "NAME,PATH,TRAN,HOTPLUG,FSTYPE,LABEL,MOUNTPOINT,SIZE,TYPE"]))
    except (UsbError, ValueError):
        return []
    found = []
    for disk in out.get("blockdevices", []):
        if disk.get("tran") != "usb":
            continue
        for part in [disk] + (disk.get("children") or []):
            if (part.get("fstype") or "") in FILESYSTEMS:
                found.append({"path": part["path"], "label": part.get("label") or Path(part["path"]).name,
                              "size": int(part.get("size") or 0), "mountpoint": part.get("mountpoint"),
                              "fstype": part.get("fstype")})
    return found


def _mount(d: dict) -> tuple[str, bool]:
    if d.get("mountpoint"):
        return d["mountpoint"], False
    out = _run(["udisksctl", "mount", "-b", d["path"], "--no-user-interaction"])
    m = re.search(r" at (.+?)\.?\s*$", out.strip())
    if not m:
        raise UsbError("The drive didn't mount.")
    return m.group(1), True


def _unmount(d: dict) -> None:
    try:
        _run(["udisksctl", "unmount", "-b", d["path"], "--no-user-interaction"])
    except UsbError as exc:
        log.warning("unmount %s failed: %s", d["path"], exc)


def write_backup(name: str, data: bytes, keep: int = 10) -> dict:
    """Write one backup to the first USB drive. Returns {drive, file}; raises UsbError."""
    ds = drives()
    if not ds:
        raise UsbError("No USB drive found. Plug one into the Pi.")
    d = ds[0]
    mp, mounted_here = _mount(d)
    try:
        folder = Path(mp) / FOLDER
        try:
            folder.mkdir(exist_ok=True)
            tmp = folder / (name + ".part")
            with open(tmp, "wb") as f:
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
            tmp.replace(folder / name)
        except OSError as exc:
            raise UsbError(f"Can't write to the drive ({exc.strerror or exc}).") from exc
        olds = sorted(folder.glob("walloftext-backup-*.zip"))
        for p in olds[:-max(1, keep)]:
            try:
                p.unlink()
            except OSError:
                pass
        os.sync()
    finally:
        if mounted_here:
            _unmount(d)
    return {"drive": d["label"], "file": f"{FOLDER}/{name}"}


class UsbBackup:
    def __init__(self, svc: "Services", clock=time.time):
        self.svc = svc
        self.clock = clock
        self._running = False

    # -------------------------------------------------------------- state --
    def state(self) -> dict:
        try:
            return json.loads(self.svc.store.get(STATE_KEY, "{}") or "{}")
        except ValueError:
            return {}

    def _save(self, st: dict) -> None:
        self.svc.store.set(STATE_KEY, json.dumps(st))

    def cfg(self) -> dict:
        return self.svc.app_settings.get("backup")

    def _tz(self):
        return self.svc.extras["scheduler"].tz() if "scheduler" in self.svc.extras else None

    def last_due(self, now: datetime) -> datetime:
        """The most recent scheduled time at or before `now`."""
        c = self.cfg()
        try:
            hh, mm = (int(x) for x in str(c.get("time") or "03:00").split(":"))
            datetime(2000, 1, 1, hh, mm)
        except (TypeError, ValueError):
            hh, mm = 3, 0
        due = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if due > now:
            due -= timedelta(days=1)
        if c.get("frequency") == "weekly":
            wd = int(c.get("weekday", 6))
            while due.weekday() != wd:
                due -= timedelta(days=1)
        elif c.get("frequency") == "monthly":
            while due.day != 1:
                due -= timedelta(days=1)
        return due

    def next_due(self, now: datetime) -> datetime:
        for d in range(1, 40):  # last_due() only moves forward as time does
            cand = self.last_due(now + timedelta(days=d))
            if cand > now:
                return cand
        return now

    def status(self) -> dict:
        now = datetime.fromtimestamp(self.clock(), self._tz())
        st = self.state()
        return {"drives": [{k: d[k] for k in ("label", "size", "fstype")} for d in drives()],
                "last": st.get("last"), "next": self.next_due(now).isoformat(timespec="minutes")
                if self.cfg().get("usb_enabled") else None}

    # ---------------------------------------------------------------- run --
    def run_now(self) -> dict:
        from .api.backup import build_zip

        self._running = True
        try:
            name, data = build_zip(self.svc)
            res = write_backup(name, data, int(self.cfg().get("keep", 10)))
            last = {"ok": True, "at": self.clock(), "message": f"Saved to {res['drive']}", **res}
        except UsbError as exc:
            last = {"ok": False, "at": self.clock(), "message": str(exc)}
        except Exception as exc:  # pragma: no cover - defensive
            log.exception("usb backup failed")
            last = {"ok": False, "at": self.clock(), "message": f"Backup failed: {exc}"[:200]}
        finally:
            self._running = False
        st = self.state()
        st["last"] = last
        self._save(st)
        self.svc.events.publish("usb_backup", last)
        return last

    def due_now(self) -> bool:
        """Called every scheduler tick. True when a backup should run now: once per scheduled time,
        retried every 15 min (until the next scheduled time) while no drive could be written."""
        if not self.cfg().get("usb_enabled") or self._running:
            return False
        now = datetime.fromtimestamp(self.clock(), self._tz())
        due = self.last_due(now).timestamp()
        st = self.state()
        if st.get("done_for", 0) >= due:
            return False
        if self.clock() < st.get("retry_at", 0) and st.get("retry_for") == due:
            return False
        return True

    async def tick(self) -> None:
        import asyncio

        if not self.due_now():
            return
        now = datetime.fromtimestamp(self.clock(), self._tz())
        due = self.last_due(now).timestamp()
        last = await asyncio.to_thread(self.run_now)
        st = self.state()
        if last["ok"]:
            st["done_for"] = due
        else:
            st["retry_for"], st["retry_at"] = due, self.clock() + RETRY_S
        self._save(st)
