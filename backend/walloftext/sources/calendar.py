"""Calendar from private iCal URLs (Google "Secret address in iCal format" or any .ics).
No OAuth (BUILD_PLAN override 11)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import httpx
import icalendar
import recurring_ical_events


@dataclass
class Event:
    title: str
    start: datetime | date
    end: datetime | date | None
    all_day: bool
    calendar: str
    location: str | None = None

    def label(self) -> str:
        if self.all_day:
            return "All day"
        return self.start.strftime("%H:%M")


def parse_events(ics: bytes | str, day: date, tz: ZoneInfo, calendar: str = "") -> list[Event]:
    cal = icalendar.Calendar.from_ical(ics)
    start = datetime.combine(day, time.min, tz)
    end = start + timedelta(days=1)
    out: list[Event] = []
    for ev in recurring_ical_events.of(cal).between(start, end):
        s = ev.get("DTSTART").dt
        e = ev.get("DTEND").dt if ev.get("DTEND") else None
        all_day = not isinstance(s, datetime)
        if not all_day:
            s = s.astimezone(tz) if s.tzinfo else s.replace(tzinfo=tz)
            if e is not None and isinstance(e, datetime):
                e = e.astimezone(tz) if e.tzinfo else e.replace(tzinfo=tz)
        status = str(ev.get("STATUS", "")).upper()
        if status == "CANCELLED":
            continue
        out.append(Event(str(ev.get("SUMMARY", "(no title)")), s, e, all_day, calendar,
                         str(ev.get("LOCATION")) if ev.get("LOCATION") else None))
    out.sort(key=lambda x: (not x.all_day, x.start if isinstance(x.start, datetime) else start))
    return out


async def fetch_ics(url: str, client: httpx.AsyncClient | None = None) -> bytes:
    if url.startswith("webcal://"):
        url = "https://" + url[len("webcal://"):]
    c = client or httpx.AsyncClient(timeout=15, follow_redirects=True, headers={"User-Agent": "walloftext/0.1"})
    try:
        r = await c.get(url)
        r.raise_for_status()
        if len(r.content) > 10 * 1024 * 1024:
            raise ValueError("calendar too large")
        return r.content
    finally:
        if c is not client:
            await c.aclose()


def agenda_blocks(events: list[Event], day: date, errors: list[str], title: str | None = None) -> list[dict]:
    blocks: list[dict] = [{"type": "banner", "text": title or day.strftime("Agenda · %A %-d %B")}]
    if not events:
        blocks.append({"type": "text", "text": "Nothing in the calendar today.", "size": "M"})
    for e in events[:30]:
        line = f"{e.label():>7}  {e.title}"
        if e.location:
            line += f" ({e.location})"
        blocks.append({"type": "text", "text": line, "size": "M", "font": "mono"})
    for err in errors:
        blocks.append({"type": "text", "text": err, "size": "S"})
    return blocks
