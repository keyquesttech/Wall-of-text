"""Source data → the normalised shapes the print kit reads (print-templates/samples/*.json)."""
from __future__ import annotations

from datetime import date, datetime

from ..render.kit.todo import split_time
from .calendar import Event


def tasks_data(items: list[dict], now: datetime, lists: list[str] | None = None) -> dict:
    """Google Tasks items (sources.google_tasks) → samples/tasks.json shape. The due time is read
    from the task text (the API drops it); the printed text is stripped by the template."""
    tasks = []
    for t in sorted(items, key=lambda t: t.get("order") or 0):
        _, _, tm = split_time(t.get("title", ""), t.get("notes", ""))
        tasks.append({"id": t.get("id") or t.get("title"), "list": t.get("list", ""), "order": t.get("order") or 0,
                      "title": t.get("title", ""), "notes": t.get("notes", ""), "due": t.get("due"),
                      "parent": t.get("parent"), "dueTime": tm})
    names = lists or []
    if not names:
        for t in tasks:
            if t["list"] and t["list"] not in names:
                names.append(t["list"])
    return {"today": now.date().isoformat(), "printedAt": f"{now:%H:%M}", "now": now.replace(tzinfo=None).isoformat(),
            "lists": names, "tasks": tasks}


def any_due(items: list[dict], today: date) -> bool:
    """"Only print if any are due": a top-level task that is late or due today."""
    return any(not t.get("parent") and t.get("due") and t["due"] <= today.isoformat() for t in items)


def _hm(dt: datetime) -> str:
    return f"{dt:%H:%M}"


def calendar_data(events: list[Event], errors: list[str], day: date, now: datetime,
                  calendars: list[str], upcoming: list[Event] | None = None) -> dict:
    timed, all_day = [], []
    for e in events:
        if e.all_day:
            all_day.append({"title": e.title, "calendar": e.calendar})
            continue
        end = e.end if isinstance(e.end, datetime) else e.start
        ev = {"uid": e.uid, "title": e.title, "start": _hm(e.start), "end": _hm(end), "location": e.location or "",
              "conferenceUrl": e.conference, "attendees": e.attendees, "description": e.description,
              "calendar": e.calendar}
        if e.start.date() != day:
            ev["startDate"] = e.start.date().isoformat()
        if end.date() != day:
            ev["endDate"] = end.date().isoformat()
        timed.append(ev)
    nxt = None
    for e in upcoming or []:
        d = e.start.date() if isinstance(e.start, datetime) else e.start
        if d > day:
            nxt = {"title": e.title, "date": d.isoformat(), "start": None if e.all_day else _hm(e.start)}
            break
    return {"date": day.isoformat(), "printedAt": f"{now:%H:%M}", "now": now.replace(tzinfo=None).isoformat(),
            "calendars": calendars, "allDay": all_day, "events": timed, "nextEvent": nxt, "errors": errors}
