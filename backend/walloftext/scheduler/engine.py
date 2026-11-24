"""Schedules, routines and their run policy (BUILD_PLAN 7).

* Nothing runs until the clock is NTP-synced (the Pi has no RTC).
* Times are local wall-clock + zone; due times are computed with zoneinfo so
  DST changes keep "07:00" at 07:00.
* Missed runs (Pi off or clock unsynced): `late_60` prints late within 60 min,
  otherwise skips and logs "Missed"; `skip` never prints late; `always` always does;
  `notice` skips them all and prints one short slip saying how many were missed.
* Quiet hours hold a scheduled print until they end ("Held"), subject to the
  same 60-minute rule.
* Holiday mode pauses every schedule. The daily limit counts Schedule, Guest
  and Remote prints.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from datetime import date, datetime, timedelta
from datetime import time as dtime
from typing import TYPE_CHECKING, Any, Callable
from zoneinfo import ZoneInfo

if TYPE_CHECKING:
    from ..services import Services

log = logging.getLogger(__name__)

LATE_GRACE_S = 120  # a tick can be this late and still count as on time
LATE_WINDOW_S = 3600
LIMITED_SOURCES = ("Schedule", "Guest", "Remote")

CONDITIONS = {
    "rain_above": "Chance of rain is at least",
    "temp_below": "Temperature is below",
    "temp_above": "Temperature is above",
    "has_events": "There's something in the calendar",
    "has_tasks": "There are tasks to do",
}


def parse_hm(s: str) -> dtime:
    h, m = s.split(":")
    return dtime(int(h), int(m))


def in_quiet(now: datetime, start: str, end: str) -> bool:
    s, e, t = parse_hm(start), parse_hm(end), now.time().replace(second=0, microsecond=0)
    if s == e:
        return False
    return s <= t < e if s < e else (t >= s or t < e)


def quiet_end_after(now: datetime, end: str) -> datetime:
    e = parse_hm(end)
    cand = datetime.combine(now.date(), e, now.tzinfo)
    if cand <= now:
        cand = datetime.combine(now.date() + timedelta(days=1), e, now.tzinfo)
    return cand


class Scheduler:
    def __init__(self, svc: "Services", clock: Callable[[], float] = time.time,
                 synced: Callable[[], bool] | None = None):
        self.svc = svc
        self.clock = clock
        self.synced = synced or self._clock_ok
        self.waiting_for_clock = False
        self._task: asyncio.Task | None = None
        self._lock = asyncio.Lock()

    def _clock_ok(self) -> bool:
        """Set from the internet, or set by hand since this boot (Settings › Date & time). A time
        set by hand before a power cut is stale: the Pi has no battery clock."""
        if self.svc.system.clock_synced():
            return True
        boot = self.svc.system.boot_id()
        return bool(boot) and self.svc.store.get("manual_clock_boot") == boot

    # ------------------------------------------------------------ store --
    def tz(self) -> ZoneInfo:
        try:
            return ZoneInfo(self.svc.app_settings.get("schedules").get("timezone", "Europe/London"))
        except Exception:
            return ZoneInfo("Europe/London")

    def _row(self, r) -> dict:
        d = dict(r)
        for k in ("days", "sections", "conditions"):
            d[k] = json.loads(d[k] or "[]")
        d["enabled"] = bool(d["enabled"])
        d["once"] = d.pop("once_on", None)
        d["next_run"] = self.next_run_ts(d)
        return d

    def list(self) -> list[dict]:
        rows = self.svc.store.conn().execute("SELECT * FROM schedules ORDER BY time IS NULL, time, name").fetchall()
        return [self._row(r) for r in rows]

    def routines(self) -> list[dict]:
        return self.list()

    def get(self, sid: str) -> dict | None:
        r = self.svc.store.conn().execute("SELECT * FROM schedules WHERE id=?", (sid,)).fetchone()
        return self._row(r) if r else None

    def save(self, data: dict, sid: str | None = None) -> dict:
        c = self.svc.store.conn()
        cur = self.get(sid) if sid else None
        merged = {**(cur or {}), **data}
        today = datetime.fromtimestamp(self.clock()).date().isoformat()
        for sec in merged.get("sections") or []:
            if isinstance(sec, dict) and sec.get("type") == "countdown" and not sec.get("set_on"):
                sec["set_on"] = today  # the countdown meter runs from the day it was set
        tm = merged.get("time")
        if tm:
            parse_hm(tm)  # validates
        days = sorted({int(d) for d in merged.get("days", list(range(7))) if 0 <= int(d) <= 6})
        once = merged.get("once") or None
        if once:
            date.fromisoformat(once)  # validates
        vals = (
            (merged.get("name") or "Untitled")[:60], 1 if merged.get("enabled", True) else 0, tm or None,
            json.dumps(days), json.dumps(merged.get("sections") or []), json.dumps(merged.get("conditions") or []),
            merged.get("icon") or None, once,
        )
        if cur:
            c.execute("UPDATE schedules SET name=?, enabled=?, time=?, days=?, sections=?, conditions=?, icon=?, once_on=? "
                      "WHERE id=?", (*vals, sid))
            if (data.get("time") and data.get("time") != cur.get("time")) or ("once" in data and data["once"] != cur.get("once")):
                # moved: don't fire for a time that already passed today
                c.execute("UPDATE schedules SET last_due=? WHERE id=?", (self.clock(), sid))
        else:
            sid = uuid.uuid4().hex[:10]
            c.execute("INSERT INTO schedules(id,name,enabled,time,days,sections,conditions,icon,once_on,created_at,last_due) "
                      "VALUES(?,?,?,?,?,?,?,?,?,?,?)", (sid, *vals, self.clock(), self.clock()))
        return self.get(sid)

    def delete(self, sid: str) -> bool:
        return self.svc.store.conn().execute("DELETE FROM schedules WHERE id=?", (sid,)).rowcount > 0

    # ------------------------------------------------------------ times --
    def _dues(self, s: dict, start: datetime, end: datetime):
        if not s.get("time"):
            return
        tz = self.tz()
        t = parse_hm(s["time"])
        day = start.astimezone(tz).date() - timedelta(days=1)
        last = end.astimezone(tz).date()
        once = date.fromisoformat(s["once"]) if s.get("once") else None
        while day <= last:
            if (day == once) if once else (day.weekday() in s["days"]):
                dt = datetime.combine(day, t, tz)
                # nonexistent local time (spring forward) → zoneinfo shifts it; normalise via UTC round trip
                dt = dt.astimezone(ZoneInfo("UTC")).astimezone(tz)
                if start < dt <= end:
                    yield dt
            day += timedelta(days=1)

    def latest_due(self, s: dict, now: datetime) -> datetime | None:
        dues = list(self._dues(s, now - timedelta(days=8), now))
        return dues[-1] if dues else None

    def next_run_ts(self, s: dict) -> float | None:
        if not s.get("enabled") or not s.get("time") or not (s.get("days") or s.get("once")):
            return None
        now = datetime.fromtimestamp(self.clock(), self.tz())
        nxt = next(iter(self._dues(s, now, now + timedelta(days=8))), None)
        return nxt.timestamp() if nxt else None

    # ------------------------------------------------------------- loop --
    def start(self) -> None:
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass

    async def _loop(self) -> None:
        while True:
            try:
                await self.tick()
                usb = self.svc.extras.get("usb_backup")
                if usb is not None and not self.waiting_for_clock:
                    await usb.tick()
                rst = self.svc.extras.get("restart")
                if rst is not None and not self.waiting_for_clock:
                    await asyncio.to_thread(rst.tick)
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("scheduler tick failed")
            await asyncio.sleep(20)

    def status(self) -> dict:
        sch = self.svc.app_settings.get("schedules")
        now = datetime.fromtimestamp(self.clock(), self.tz())
        q = sch.get("quiet_hours", {})
        return {
            "clock_synced": not self.waiting_for_clock,
            "holiday_mode": bool(sch.get("holiday_mode")),
            "quiet_now": bool(q.get("enabled")) and in_quiet(now, q.get("start", "22:00"), q.get("end", "07:00")),
            "timezone": str(self.tz()),
            "now": now.isoformat(timespec="minutes"),
        }

    async def tick(self) -> int:
        """Run whatever is due. Returns how many schedules were handled."""
        synced = await asyncio.to_thread(self.synced)
        if not synced:
            if not self.waiting_for_clock:
                self.waiting_for_clock = True
                self.svc.events.publish("scheduler", self.status())
            return 0
        if self.waiting_for_clock:
            self.waiting_for_clock = False
            self.svc.events.publish("scheduler", self.status())
        handled = 0
        missed: list[str] = []  # for the "notice" policy: one name per missed print
        async with self._lock:
            now = datetime.fromtimestamp(self.clock(), self.tz())
            sch = self.svc.app_settings.get("schedules")
            policy = sch.get("missed_policy", "late_60")
            for s in self.list():
                if not s["enabled"]:
                    continue
                due = self.latest_due(s, now)
                last_due = s.get("last_due") or 0
                if due is None or due.timestamp() <= last_due:
                    continue
                self.svc.store.conn().execute("UPDATE schedules SET last_due=? WHERE id=?", (due.timestamp(), s["id"]))
                if s.get("once"):
                    self.svc.store.conn().execute("UPDATE schedules SET enabled=0 WHERE id=?", (s["id"],))
                handled += 1
                if sch.get("holiday_mode"):
                    continue
                lateness = now.timestamp() - due.timestamp()
                if policy == "notice":
                    # every time this schedule was due while the printer was off, not just the latest
                    since = datetime.fromtimestamp(max(last_due, (now - timedelta(days=7)).timestamp()), self.tz())
                    earlier = [d for d in self._dues(s, since, now) if d < due]
                    for d in earlier:
                        self._missed(s, f"The printer was off or its clock wasn't set at {d:%a %H:%M}.")
                        missed.append(s["name"])
                    if lateness > LATE_GRACE_S:
                        self._missed(s, f"The printer was off or its clock wasn't set at {due:%H:%M}.")
                        missed.append(s["name"])
                        continue
                elif lateness > LATE_GRACE_S:
                    ok_late = policy == "always" or (policy == "late_60" and lateness <= LATE_WINDOW_S)
                    if not ok_late:
                        self._missed(s, f"The printer was off or its clock wasn't set at {due:%H:%M}.")
                        continue
                await self._run(s, due, late=lateness > LATE_GRACE_S)
            if missed:
                self._missed_notice(missed)
        return handled

    def _missed_notice(self, names: list[str]) -> None:
        """One short slip when the printer is back: how many scheduled prints were missed."""
        n = len(names)
        counts: dict[str, int] = {}
        for x in names:
            counts[x] = counts.get(x, 0) + 1
        what = ", ".join(f"{k} ×{v}" if v > 1 else k for k, v in list(counts.items())[:4])
        if len(counts) > 4:
            what += f" and {len(counts) - 4} more"
        doc = {"blocks": [{"type": "slip", "template": "note", "data": {
            "source": "MISSED", "text": f"{n} scheduled print{'s' if n != 1 else ''} missed\n"
                                        f"While the printer was off: {what}."}}]}
        self.svc.print_document(doc, "Schedule", f"Missed {n} print{'s' if n != 1 else ''}",
                                held_until=self.hold_until())

    def _missed(self, s: dict, reason: str) -> None:
        self.svc.queue.log_missed("Schedule", s["name"], reason, {"schedule_id": s["id"]})
        self._result(s["id"], "missed", reason)

    def _result(self, sid: str, state: str, msg: str = "") -> None:
        self.svc.store.conn().execute("UPDATE schedules SET last_result=?, last_run_at=? WHERE id=?",
                                      (json.dumps({"state": state, "message": msg}), self.clock(), sid))

    def hold_until(self, now: datetime | None = None) -> float | None:
        """If quiet hours are on now, the epoch they end; else None. Used by guest and remote prints too."""
        q = self.svc.app_settings.get("schedules").get("quiet_hours", {})
        now = now or datetime.fromtimestamp(self.clock(), self.tz())
        if q.get("enabled") and in_quiet(now, q.get("start", "22:00"), q.get("end", "07:00")):
            return quiet_end_after(now, q.get("end", "07:00")).timestamp()
        return None

    def over_daily_limit(self) -> bool:
        limit = int(self.svc.app_settings.get("schedules").get("daily_limit", 30) or 0)
        return limit > 0 and self.svc.queue.count_today(LIMITED_SOURCES) >= limit

    async def _gather(self, s: dict) -> dict:
        """Fetch each source a schedule needs once; shared by conditions and sections."""
        src = self.svc.extras["sources"]
        types = {sec.get("type") for sec in s["sections"]} | {c.get("type") for c in s["conditions"]}
        ctx: dict[str, Any] = {}
        if types & {"weather", "rain_above", "temp_below", "temp_above"}:
            ctx["weather"] = await src.weather()
        if types & {"agenda", "has_events"}:
            ctx["events"] = await src.events()
        if types & {"tasks", "has_tasks"}:
            ctx["tasks"] = await src.tasks()
        return ctx

    def check_conditions(self, s: dict, ctx: dict) -> str | None:
        """None when every condition passes (or its data is unavailable), else the reason it didn't."""
        for c in s["conditions"]:
            t, v = c.get("type"), c.get("value")
            f = (ctx.get("weather") or (None, None))[0]
            if t in ("rain_above", "temp_below", "temp_above") and f is None:
                continue  # data unavailable: print what's available
            if t == "rain_above" and f.rain_chance < float(v or 0):
                return f"Chance of rain was {f.rain_chance}%, below {v}%."
            if t == "temp_below" and f.now_temp >= float(v or 0):
                return f"It was {round(f.now_temp)}°, not below {v}°."
            if t == "temp_above" and f.now_temp <= float(v or 0):
                return f"It was {round(f.now_temp)}°, not above {v}°."
            if t == "has_events":
                ev, errs = ctx.get("events") or ([], [])
                if not ev and not errs:
                    return "Nothing in the calendar."
            if t == "has_tasks":
                res = ctx.get("tasks") or ([], None)
                if not res[1] and not self.svc.extras["sources"].has_due_tasks(res):
                    return "No tasks due today or late."
        return None

    async def _run(self, s: dict, due: datetime, late: bool) -> int | None:
        ctx = await self._gather(s)
        why = self.check_conditions(s, ctx)
        if why:
            self.svc.queue.log_missed("Schedule", s["name"], f"Skipped: {why}", {"schedule_id": s["id"], "skipped": True})
            self._result(s["id"], "skipped", why)
            return None
        if self.over_daily_limit():
            self._missed(s, "The daily print limit was reached.")
            return None
        held = self.hold_until()
        if held and held - due.timestamp() > LATE_WINDOW_S:
            self._missed(s, f"It was due at {due:%H:%M}, during quiet hours.")
            return None
        doc = await self.svc.extras["sources"].routine_doc(s["sections"], ctx)
        jid = self.svc.print_document(doc, "Schedule", s["name"], held_until=held,
                                      meta={"schedule_id": s["id"], "late": late, "due": due.isoformat()})
        self._result(s["id"], "held" if held else "printed", "Late" if late else "")
        return jid

    async def run_now(self, sid: str, source: str = "Manual") -> str:
        s = self.get(sid)
        if not s:
            return "That routine no longer exists."
        ctx = await self._gather(s)
        doc = await self.svc.extras["sources"].routine_doc(s["sections"], ctx)
        self.svc.print_document(doc, source, s["name"], meta={"schedule_id": sid, "manual": True})
        return f"Printing “{s['name']}”."

    async def preview_doc(self, s: dict) -> dict:
        ctx = await self._gather(s)
        return await self.svc.extras["sources"].routine_doc(s["sections"], ctx)
