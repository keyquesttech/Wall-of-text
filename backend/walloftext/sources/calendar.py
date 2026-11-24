"""Calendar events as the print kit reads them, plus helpers that clean up event text.
Events come from the Google Calendar API (sources/google.py)."""
from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from datetime import date, datetime


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
