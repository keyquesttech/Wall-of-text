"""Itinerary from the calendars (PRINT_TEMPLATES 8): a timeline, each event a ticket."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from urllib.parse import quote

from . import tokens as T
from .nodes import (Band, Box, Canvas, Col, Custom, Cut, Node, Pad, QR, Row, Rule, Text)
from .slip import Header, d_label

DAY_NUM = T.Style(T.SG_BOLD, 80, 68, -0.05)
MONO_13 = T.MONO(size=13, lh=17)
MONO_B13 = T.MONO_B(size=13, lh=17)


def maps_url(location: str) -> str:
    return "https://www.google.com/maps/search/?api=1&query=" + quote(location, safe="")


def fmt_len(mins: int, total: bool = False) -> str:
    mins = max(0, int(mins))
    h, m = divmod(mins, 60)
    if h == 0:
        return f"{m} min"
    if m == 0:
        return f"{h} h"
    return f"{h} h {m} min" if total else f"{h} h {m:02d}" if m < 10 else f"{h} h {m}"


def _dt(day: date, hm: str | None, d: str | None = None) -> datetime | None:
    if not hm:
        return None
    try:
        dd = date.fromisoformat(d) if d else day
        hh, mm = hm[-5:].split(":")
        return datetime.combine(dd, time(int(hh), int(mm)))
    except ValueError:
        return None


def attendees_line(names: list[str]) -> str:
    names = [n for n in names if n]
    if len(names) <= 1:
        return names[0] if names else ""
    if len(names) == 2:
        return f"{names[0]} and {names[1]}"
    rest = len(names) - 2
    return f"{names[0]}, {names[1]} and {rest} other{'s' if rest != 1 else ''}"


def service_name(url: str) -> str:
    u = url.lower()
    if "meet.google" in u:
        return "Google Meet"
    if "zoom." in u:
        return "Zoom"
    if "teams." in u:
        return "Microsoft Teams"
    return "Online"


def prepare(data: dict, now: datetime) -> dict:
    day = date.fromisoformat(data["date"])
    evs = []
    for e in data.get("events") or []:
        s = _dt(day, e.get("start"), e.get("startDate"))
        en = _dt(day, e.get("end"), e.get("endDate")) or s
        if s is None:
            continue
        if en < s:  # an end time before the start means it ends the next day
            en += timedelta(days=1)
        evs.append(dict(e, _s=s, _e=en))
    evs.sort(key=lambda e: (e["_s"], e["_e"]))
    n = now.replace(tzinfo=None)
    nxt = next((e for e in evs if e["_e"] > n), None)
    items: list[tuple[str, object]] = []
    latest_end, latest = None, None
    busy = 0
    for e in evs:
        if latest_end is not None:
            if e["_s"] < latest_end:
                e["_overlap"] = latest["title"]
            elif e["_s"] - latest_end >= timedelta(minutes=15):
                items.append(("gap", int((e["_s"] - latest_end).total_seconds() // 60)))
        if latest_end is None or e["_s"] >= latest_end:
            busy += int((e["_e"] - e["_s"]).total_seconds() // 60)
        elif e["_e"] > latest_end:
            busy += int((e["_e"] - latest_end).total_seconds() // 60)
        items.append(("event", e))
        if latest_end is None or e["_e"] > latest_end:
            latest_end, latest = e["_e"], e
    span = int((latest_end - evs[0]["_s"]).total_seconds() // 60) if evs else 0
    return {"day": day, "events": evs, "next": nxt, "items": items, "busy": busy, "free": max(0, span - busy),
            "last_end": latest_end}


class KVGrid(Node):
    """3 cells, 2-dot border and dividers: px label over a t-m bold value."""

    def __init__(self, cells: list[tuple[str, str]]):
        self.cells = [Pad(Col(Text(k, T.PX), Text(v, T.T_MB, max_lines=2)), 4, 6, 4, 6) for k, v in cells]

    def _ws(self, w):
        inner = w - 4 - 2 * (len(self.cells) - 1)
        n = len(self.cells)
        return [inner // n + (1 if i < inner % n else 0) for i in range(n)]

    def height(self, w):
        return 4 + max(c.height(cw) for c, cw in zip(self.cells, self._ws(w)))

    def draw(self, c: Canvas, x, y, w, h, ink=0):
        c.frame(x, y, w, h, 2, ink)
        cx = x + 2
        for i, (cell, cw) in enumerate(zip(self.cells, self._ws(w))):
            if i:
                c.rect(cx, y, cx + 2, y + h, ink)
                cx += 2
            cell.draw(c, cx, y + 2, cw, h - 4, ink)
            cx += cw


def _label(label: str, *body: Node | None) -> Col:
    return Col(Text(label, T.PX), *body, gap=1)


def ticket(e: dict, idx: int, total: int, p: dict, now: datetime) -> Box:
    n = now.replace(tzinfo=None)
    if e is p["next"]:
        if e["_s"] <= n:
            right = "NOW"
        else:
            right = "IN " + fmt_len(int((e["_s"] - n).total_seconds() // 60 + 0.999)).upper()
        head = Band(Row((Text("NEXT UP", T.PX_B), "auto"), (Text(right, T.PX_B, align="right"), "flex")), (6, 8, 6, 8))
    else:
        head = Pad(Row((Text(f"EVENT {idx} OF {total}", T.PX_B), "auto"),
                       (Text(f"{e['_s']:%H:%M}–{e['_e']:%H:%M}", T.PX_B, align="right"), "flex")), 6, 8, 6, 8)
    day = p["day"]
    starts = f"{e['_s']:%H:%M}" if e["_s"].date() == day else f"{e['_s']:%a %H:%M}".upper()
    ends = f"{e['_e']:%H:%M}" if e["_e"].date() == day else f"→ {e['_e']:%a}".upper() + f" {e['_e']:%H:%M}"
    body: list = [Text(e.get("title") or "(no title)", T.T_L, max_lines=2),
                  KVGrid([("STARTS", starts), ("ENDS", ends),
                          ("LENGTH", fmt_len(int((e["_e"] - e["_s"]).total_seconds() // 60)))])]
    loc = (e.get("location") or "").strip()
    conf = (e.get("conferenceUrl") or "").strip()
    if loc:
        place, _, addr = loc.partition(",")
        body.append(_label("WHERE", Text(place.strip(), T.MONO_B, max_lines=2),
                           Text(addr.strip(), T.MONO, max_lines=2) if addr.strip() else None))
    elif conf:
        body.append(_label("WHERE", Text(service_name(conf), T.MONO_B), Text("Online", T.MONO)))
    who = attendees_line(e.get("attendees") or [])
    if who:
        body.append(_label("WITH", Text(who, T.MONO, max_lines=2)))
    notes = (e.get("description") or "").strip()
    if notes:
        body.append(_label("NOTES", Text(notes, T.MONO, max_lines=3)))
    if e.get("_overlap"):
        body.append(Text(f"Overlaps with {e['_overlap']}", T.T_S, max_lines=2))
    if loc:
        body += [Cut("MAP"), Row(QR(maps_url(loc)), (Text("Scan for directions on your phone.", MONO_13), "flex"),
                                 gap=10)]
    elif conf:
        link = conf.split("://", 1)[-1].rstrip("/")
        body.append(Box(Col(Text("JOIN ONLINE", T.PX), Text(link, MONO_B13, max_lines=3)), border=3, pad=(6, 8, 6, 8)))
    return Box(Col(head, Pad(Col(*body, gap=8), 8, 10, 10, 10)), border=3, pad=0)


class TimelineRow(Node):
    """3 columns (50 | 20 | rest): start time, rail (solid or dashed 4/5, an 18-dot square per event),
    then the ticket or the gap label."""

    def __init__(self, time_text: str, content: Node, event: bool):
        self.time = Text(time_text, T.T_MB) if time_text else None
        self.content = content
        self.event = event

    def height(self, w):
        return self.content.height(w - 70)

    def draw(self, c, x, y, w, h, ink=0):
        if self.time:
            self.time.draw(c, x, y + 6, 50, T.T_MB.lh, ink)
        rx = x + 50 + 8
        if self.event:
            c.rect(rx, y, rx + 4, y + h, ink)
            c.rect(x + 51, y + 8, x + 69, y + 26, ink)
        else:
            c.vdash(rx, y, y + h, 4, 4, 5, ink)
        self.content.draw(c, x + 70, y, w - 70, h, ink)


def itinerary(data: dict, now: datetime) -> list:
    p = prepare(data, now)
    if not p["events"] and not data.get("allDay"):
        return free_day(data, now)
    day = p["day"]
    blocks: list = [
        Header("GOOGLE CALENDAR", f"PRINTED {now:%H:%M}"),
        Row(Text(str(day.day), DAY_NUM),
            Pad(Col(Text(f"{day:%A}".upper(), T.T_L), Text(f"{day:%B}".upper(), T.T_L)), b=8), gap=12, align="bottom"),
    ]
    evs = p["events"]
    if evs:
        le = p["last_end"]
        done = f"{le:%H:%M}" if le.date() == day else f"{le:%a %H:%M}"
        blocks.append(Text(f"{len(evs)} event{'s' if len(evs) != 1 else ''} · first at {evs[0]['_s']:%H:%M} · "
                           f"done by {done}", T.T_M))
    else:
        blocks.append(Text("No timed events today.", T.T_M))
    for err in data.get("errors") or []:
        blocks.append(Text(err, T.T_S))
    all_day = data.get("allDay") or []
    for a in all_day[:3]:
        blocks.append(Band(Row((Text("ALL DAY", T.PX_B), "auto"), (Text(a.get("title", ""), T.T_M, align="right",
                                                                         max_lines=2), "flex"), gap=10), (6, 10, 6, 10)))
    if len(all_day) > 3:
        blocks.append(Text(f"+{len(all_day) - 3} more", T.T_S))
    blocks.append(Rule("hr2"))
    if evs:
        rows = []
        k = 0
        for kind, it in p["items"]:
            if kind == "gap":
                rows.append(TimelineRow("", Pad(Text(fmt_len(it).upper() + " FREE", T.PX), 12, 0, 12, 8), False))
            else:
                k += 1
                start = f"{it['_s']:%H:%M}" if it["_s"].date() == day else "…"
                rows.append(TimelineRow(start, Pad(ticket(it, k, len(evs), p, now), 0, 0, 4, 6), True))
        blocks.append(Col(*rows))
        blocks.append(Rule("hr2"))
        blocks.append(Row((Text(f"Busy {fmt_len(p['busy'], True)}", T.T_M), "auto"),
                          (Text(f"Free {fmt_len(p['free'], True)}", T.T_M, align="right"), "flex")))
    return blocks


def calendar_drawing(size: int = 140) -> Custom:
    k = size / 120

    def draw(c, x, y, w, h, ink):
        ox = x + (w - size) // 2
        s = lambda v: round(v * k)  # noqa: E731
        c.frame(ox + s(8.5), y + s(16.5), s(103) + 1, s(95) + 1, s(7), ink)
        c.rect(ox + s(12), y + s(20), ox + s(108), y + s(42), ink)
        for px in (34, 86):
            c.rect(ox + s(px - 4), y + s(10), ox + s(px + 4), y + s(30), ink)
        for (lx, ly) in ((30, 62), (54, 62), (78, 62), (30, 84), (54, 84)):
            c.hdash(ox + s(lx), ox + s(lx + 12), y + s(ly - 2), s(4), s(3), s(4), ink)

    return Custom(size, draw)


def free_day(data: dict, now: datetime) -> list:
    """8.3: nothing on today; the next event within 14 days."""
    nxt = data.get("nextEvent")
    if nxt:
        try:
            wd = f"{date.fromisoformat(nxt['date']):%a}"
        except (KeyError, ValueError):
            wd = ""
        box = Box(Row((Col(Text("NEXT EVENT", T.PX), Text(nxt.get("title") or "(no title)", T.T_L, max_lines=2)), "flex"),
                      (Col(Text(wd, T.PX), Text(nxt.get("start") or "ALL DAY", T.T_L), align="right"), "auto"),
                      gap=10))
    else:
        box = Box(Col(Text("NEXT EVENT", T.PX), Text("Nothing in the next 2 weeks", T.T_L)))
    return [
        Header("GOOGLE CALENDAR", d_label(now)),
        Rule("hr2"),
        Pad(calendar_drawing(140), t=8),
        Text("NOTHING ON", T.T_XL, align="center"),
        Text("No events today. The whole day is yours.", T.T_M, align="center").m(-4),
        Rule("hr"),
        box,
    ]
