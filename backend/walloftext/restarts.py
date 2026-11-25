"""Scheduled restarts (Settings › Device › Scheduled restart).

A restart clears any slow memory leak or stuck USB/printer state. Rules:
* Daily or weekly at a set time, in the app's time zone.
* Never in the middle of a print: it waits while anything is printing or queued.
* If the Pi was off, its clock wasn't set, or it stayed busy for more than 2 hours after the
  set time, that restart is skipped (no surprise reboots in the afternoon).
* Switching it on never restarts straight away: only times after that moment count.
"""
from __future__ import annotations

import json
import logging
import subprocess
import time
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from .services import Services

log = logging.getLogger(__name__)

WINDOW_S = 2 * 3600  # how late a restart may still happen
MIN_UPTIME_S = 15 * 60  # never restart a Pi that only just started
KEY = "restart_state"


def last_due_at(now: datetime, hm: str, frequency: str, weekday: int) -> datetime:
    """The most recent scheduled time at or before `now`."""
    try:
        hh, mm = (int(x) for x in str(hm or "04:00").split(":"))
        datetime(2000, 1, 1, hh, mm)
    except (TypeError, ValueError):
        hh, mm = 4, 0
    due = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if due > now:
        due -= timedelta(days=1)
    if frequency == "weekly":
        while due.weekday() != int(weekday) % 7:
            due -= timedelta(days=1)
    return due


class ScheduledRestart:
    def __init__(self, svc: "Services", clock: Callable[[], float] = time.time,
                 reboot: Callable[[], None] | None = None):
        self.svc = svc
        self.clock = clock
        self.reboot = reboot or self._reboot

    def cfg(self) -> dict:
        return self.svc.app_settings.get("restart")

    def _tz(self):
        return self.svc.extras["scheduler"].tz() if "scheduler" in self.svc.extras else None

    def _state(self) -> dict:
        try:
            return json.loads(self.svc.store.get(KEY, "{}") or "{}")
        except ValueError:
            return {}

    def _save(self, st: dict) -> None:
        self.svc.store.set(KEY, json.dumps(st))

    def _due(self, now: datetime) -> datetime:
        c = self.cfg()
        return last_due_at(now, c.get("time", "04:00"), c.get("frequency", "weekly"), int(c.get("weekday", 6)))

    def next_due(self, now: datetime) -> datetime:
        for d in range(1, 9):
            cand = self._due(now + timedelta(days=d))
            if cand > now:
                return cand
        return now

    def status(self) -> dict:
        now = datetime.fromtimestamp(self.clock(), self._tz())
        st = self._state()
        return {"next": self.next_due(now).isoformat(timespec="minutes") if self.cfg().get("enabled") else None,
                "last": st.get("last")}

    def _busy(self) -> bool:
        q = self.svc.queue
        # held prints (quiet hours) survive a restart, so only printing or queued ones count
        return q.active_id is not None or any(j["state"] in ("queued", "printing") for j in q.pending())

    def tick(self) -> str | None:
        """Called by the scheduler loop (only while the clock is right). Returns what it did."""
        c = self.cfg()
        st = self._state()
        if not c.get("enabled"):
            st.pop("armed_at", None)
            self._save(st)
            return None
        now_ts = self.clock()
        now = datetime.fromtimestamp(now_ts, self._tz())
        due = self._due(now).timestamp()
        armed = st.setdefault("armed_at", now_ts)  # switched on now: only later times count
        if due <= max(armed, st.get("done_for", 0)):
            self._save(st)
            return None
        if now_ts - due > WINDOW_S:
            st["done_for"] = due
            st["last"] = {"at": now_ts, "ok": False, "message": "Skipped: the printer was off or busy at the set time."}
            self._save(st)
            return "skipped"
        if self._busy() or self.svc.system.uptime_s() < MIN_UPTIME_S:
            self._save(st)
            return "waiting"
        st["done_for"] = due
        st["last"] = {"at": now_ts, "ok": True, "message": "Restarted on schedule."}
        self._save(st)
        log.info("scheduled restart")
        self.reboot()
        return "restarted"

    def _reboot(self) -> None:
        if self.svc.settings.is_mock:
            log.info("mock: would restart now")
            return
        subprocess.Popen(["systemctl", "reboot"])
