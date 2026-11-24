"""Calendar from private iCal URLs (Google "Secret address in iCal format" or any .ics).
No OAuth (BUILD_PLAN override 11)."""
from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from urllib.parse import unquote
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
    uid: str = ""
    attendees: list[str] = field(default_factory=list)
    description: str = ""
    conference: str | None = None

    def label(self) -> str:
        if self.all_day:
            return "All day"
        return self.start.strftime("%H:%M")


_CONF = re.compile(r"https?://(?:[\w-]+\.)?(?:meet\.google\.com|zoom\.us|teams\.microsoft\.com|teams\.live\.com)/[^\s<>\"')]+",
                   re.I)
_BOILER = re.compile(r"(join with google meet|join by phone|more phone numbers|learn more about meet|"
                     r"meet\.google\.com|^pin:|join zoom meeting|zoom\.us/|meeting id:|passcode:|"
                     r"microsoft teams meeting|teams\.microsoft|join on your computer|click here to join|"
                     r"please do not edit this section|^-::~)", re.I)


def owner_from_url(url: str) -> str | None:
    """Google's secret iCal address carries the calendar owner's address: /calendar/ical/<email>/private-…"""
    m = re.search(r"/ical/([^/]+)/", url or "")
    owner = unquote(m.group(1)) if m else ""
    return owner.lower() if "@" in owner else None


def clean_description(text: str) -> str:
    """HTML and conference boilerplate out; plain lines kept."""
    t = re.sub(r"<br\s*/?>|</p>|</div>|</li>", "\n", text or "", flags=re.I)
    t = html.unescape(re.sub(r"<[^>]+>", "", t))
    lines = []
    for line in t.replace("\r", "").split("\n"):
        if line.strip().startswith("-::~") or "~:~:~" in line:
            break  # Google's conference section marker: everything after is boilerplate
        if _BOILER.search(line.strip()):
            continue
        lines.append(line.strip())
    return re.sub(r"\n{2,}", "\n", "\n".join(lines)).strip()


def _people(ev, owner: str | None) -> list[str]:
    att = ev.get("ATTENDEE")
    if att is None:
        return []
    out = []
    for a in att if isinstance(att, list) else [att]:
        email = str(a).lower().removeprefix("mailto:")
        if owner and email == owner:
            continue
        cn = a.params.get("CN") if hasattr(a, "params") else None
        name = str(cn) if cn and "@" not in str(cn) else email.split("@")[0]
        if name:
            out.append(name)
    return out


def parse_events(ics: bytes | str, day: date, tz: ZoneInfo, calendar: str = "", days: int = 1,
                 owner: str | None = None) -> list[Event]:
    cal = icalendar.Calendar.from_ical(ics)
    start = datetime.combine(day, time.min, tz)
    end = start + timedelta(days=days)
    out: list[Event] = []
    for ev in recurring_ical_events.of(cal).between(start, end):
        s = ev.get("DTSTART").dt
        e = ev.get("DTEND").dt if ev.get("DTEND") else None
        if e is None and ev.get("DURATION"):
            e = s + ev.get("DURATION").dt
        all_day = not isinstance(s, datetime)
        if not all_day:
            s = s.astimezone(tz) if s.tzinfo else s.replace(tzinfo=tz)
            if e is not None and isinstance(e, datetime):
                e = e.astimezone(tz) if e.tzinfo else e.replace(tzinfo=tz)
        status = str(ev.get("STATUS", "")).upper()
        if status == "CANCELLED":
            continue
        desc = str(ev.get("DESCRIPTION") or "")
        loc = str(ev.get("LOCATION")) if ev.get("LOCATION") else None
        conf = str(ev.get("X-GOOGLE-CONFERENCE") or "") or None
        if not conf:
            m = _CONF.search(desc) or _CONF.search(loc or "")
            conf = m.group(0) if m else None
        if loc and _CONF.fullmatch(loc.strip()):
            loc = None  # a bare meeting link is not a place
        out.append(Event(str(ev.get("SUMMARY", "(no title)")), s, e, all_day, calendar, loc,
                         str(ev.get("UID", "")), _people(ev, owner), clean_description(desc), conf))
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
