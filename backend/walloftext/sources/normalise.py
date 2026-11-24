"""Source data → the normalised shapes the print kit reads (print-templates/samples/*.json)."""
from __future__ import annotations

from datetime import date, datetime

from .calendar import Event


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
