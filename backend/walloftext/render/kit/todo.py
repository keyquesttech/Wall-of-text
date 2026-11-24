"""To do from Google Tasks (PRINT_TEMPLATES 7): Big 3 + groups, every task in a ticket box."""
from __future__ import annotations

import re
from datetime import date, datetime

from . import tokens as T
from .nodes import (Band, Canvas, Checkbox, Col, Custom, Fill, Grid, Node, Pad, Row, Rule, SectionRule, Tag,
                    Text)
from .slip import Header, d_label, dt_label

NUM_L = T.Style(T.SG_BOLD, 52, 47, -0.04)
NUM_S = T.Style(T.SG_BOLD, 24, 28, -0.03)
TIME_L = T.Style(T.SG_BOLD, 20, 22)

_NOTE_TIME = re.compile(r"^\s*(\d{1,2})[:.](\d{2})\b\s*[-–·:]?\s*")
_TITLE_TIME = re.compile(r"\s*@\s*(\d{1,2})[:.](\d{2})\b")


def split_time(title: str, notes: str) -> tuple[str, str, str | None]:
    """A time at the start of the notes ("10:00 Ask for Thursday") or after @ in the title
    ("Call landlord @10:00"). Returns (title, notes, "HH:MM" or None) with the time stripped."""
    found = None
    m = _TITLE_TIME.search(title or "")
    if m and int(m.group(1)) < 24 and int(m.group(2)) < 60:
        found = f"{int(m.group(1)):02d}:{m.group(2)}"
        title = (title[:m.start()] + title[m.end():]).strip()
    m = _NOTE_TIME.match(notes or "")
    if m and int(m.group(1)) < 24 and int(m.group(2)) < 60:
        found = found or f"{int(m.group(1)):02d}:{m.group(2)}"
        notes = notes[m.end():]
    return (title or "").strip(), (notes or "").strip(), found


def _due(t: dict) -> date | None:
    try:
        return date.fromisoformat((t.get("due") or "")[:10])
    except ValueError:
        return None


def status(t: dict, today: date) -> str:
    d = _due(t)
    if d is None:
        return "nodate"
    return "late" if d < today else "today" if d == today else "future"


def prepare(data: dict) -> dict:
    """Big 3, groups and counts (7.1)."""
    today = date.fromisoformat(data["today"])
    tasks = sorted(data.get("tasks") or [], key=lambda t: (t.get("order") or 0))
    for t in tasks:
        title, notes, tm = split_time(t.get("title", ""), t.get("notes", ""))
        t["_title"], t["_notes"], t["_time"] = title, notes, t.get("dueTime") or tm
    top = [t for t in tasks if not t.get("parent")]
    subs: dict[str, list[dict]] = {}
    for t in tasks:
        if t.get("parent"):
            subs.setdefault(t["parent"], []).append(t)
    due_now = [t for t in top if status(t, today) in ("late", "today")]
    big = due_now[:3]
    rest = [t for t in top if t not in big]
    groups = [
        ("! OVERDUE", True, [t for t in rest if status(t, today) == "late"], 0),
        ("DUE TODAY", False, [t for t in rest if status(t, today) == "today"], 0),
    ]
    nodate = [t for t in rest if status(t, today) == "nodate"]
    groups.append(("NO DATE", False, nodate[:5], max(0, len(nodate) - 5)))
    printed = big + [t for _, _, ts, _ in groups for t in ts]
    coming = sorted([t for t in top if status(t, today) == "future"], key=lambda t: (_due(t), t.get("order") or 0))
    return {"today": today, "big": big, "groups": [g for g in groups if g[2]], "subs": subs,
            "count": len(printed), "late": sum(1 for t in printed if status(t, today) == "late"),
            "coming": coming[:3], "any_due": bool(due_now)}


def due_bits(t: dict, today: date, big: bool) -> Node:
    st = status(t, today)
    tm = t.get("_time")
    if st == "late":
        n = (today - _due(t)).days
        tag = Tag("1 DAY LATE" if n == 1 else f"{n} DAYS LATE", "inv")
        if tm:
            tm = f"{_due(t):%a}".upper() + " " + tm
    elif st == "today":
        tag = Text("TODAY", T.PX_B)
    elif st == "future":
        tag = Text(short_date(_due(t), today).upper(), T.PX_B)
    else:
        tag, tm = Text("ANY TIME", T.PX_B), None
    if not tm:
        return tag
    return Row(Text(tm, TIME_L if big else T.T_MB), tag, gap=8)


class Ticket(Node):
    """Ticket box (4.4): a border, a number column and a dashed vertical divider."""

    def __init__(self, num: Node, content: Node, numw: int, border: int, divider: int):
        self.num, self.content = num, content
        self.numw, self.b, self.div = numw, border, divider

    def _cw(self, w):
        return w - 2 * self.b - self.numw - self.div

    def height(self, w):
        return 2 * self.b + max(self.content.height(self._cw(w)), self.num.height(self.numw))

    def draw(self, c: Canvas, x, y, w, h, ink=0):
        c.frame(x, y, w, h, self.b, ink)
        inner = h - 2 * self.b
        nh = self.num.height(self.numw)
        self.num.draw(c, x + self.b, y + self.b + (inner - nh) // 2, self.numw, nh, ink)
        dx = x + self.b + self.numw
        c.vdash(dx, y + self.b, y + h - self.b, self.div, 6, 4, ink)
        cw = self._cw(w)
        self.content.draw(c, dx + self.div, y + self.b, cw, inner, ink)


def big_box(i: int, t: dict, p: dict) -> Ticket:
    notes = (t.get("_notes") or "")[:80].strip()
    subs = p["subs"].get(t["id"], [])
    content = Pad(Col(
        Row((Text(t["_title"], T.T_L, max_lines=2), "flex"), Checkbox(True), gap=10, align="top"),
        Text(notes, T.T_S, max_lines=2) if notes else None,
        *[Row(Checkbox(), (Text(split_time(s.get("title", ""), "")[0], T.T_M, max_lines=2), "flex"), gap=8)
          for s in subs],
        Row((Text(t.get("list", ""), T.PX, max_lines=1), "flex"), due_bits(t, p["today"], True), gap=8).m(2),
        gap=6), 10, 12, 12, 12)
    num = Pad(Col(Text("NO.", T.PX), Text(str(i), NUM_L), gap=2, align="center"), 10, 4, 10, 4)
    return Ticket(num, content, 64, 4, 3)


def small_box(i: int, t: dict, p: dict) -> Ticket:
    subs = p["subs"].get(t["id"], [])
    lst = t.get("list", "") + (f" · {len(subs)} steps" if subs else "")
    content = Pad(Col(
        Row((Text(t["_title"], T.T_MB, max_lines=2), "flex"), Checkbox(), gap=10, align="top"),
        Row((Text(lst, T.PX, max_lines=1), "flex"), due_bits(t, p["today"], False), gap=8),
        gap=4), 8, 10, 8, 10)
    num = Pad(Col(Text(f"{i:02d}", NUM_S), align="center"), 6, 2, 6, 2)
    return Ticket(num, content, 48, 3, 2)


def short_date(d: date, today: date) -> str:
    if 0 <= (d - today).days <= 6:
        return f"{d:%a}"
    return f"{d:%a} {d.day} {d:%b}"


def tick_drawing(size: int = 150) -> Custom:
    k = size / 120

    def draw(c, x, y, w, h, ink):
        ox = x + (w - size) // 2
        s = lambda v: round(v * k)  # noqa: E731
        c.frame(ox + s(6), y + s(6), s(108) - s(6) + 1, s(108) - s(6) + 1, s(8), ink)
        # inner dashed square (2-dot, 4 on 4 off) at 22..98
        a, b = s(21), s(99)
        c.hdash(ox + a, ox + b, y + a, 2, 5, 5, ink)
        c.hdash(ox + a, ox + b, y + b - 2, 2, 5, 5, ink)
        c.vdash(ox + a, y + a, y + b, 2, 5, 5, ink)
        c.vdash(ox + b - 2, y + a, y + b, 2, 5, 5, ink)
        pts = [(ox + s(28), y + s(60)), (ox + s(50), y + s(82)), (ox + s(94), y + s(34))]
        c.d.line(pts, fill=ink, width=s(12), joint="curve")

    return Custom(size, draw)


def todo(data: dict, now: datetime) -> list:
    p = prepare(data)
    if not p["big"]:
        return all_clear(data, now, p)
    lists = data.get("lists") or sorted({t.get("list", "") for t in data.get("tasks") or []})
    count = f"{p['count']} task{'s' if p['count'] != 1 else ''}" + (f" · {p['late']} late" if p["late"] else "")
    blocks: list = [
        Header("GOOGLE TASKS", dt_label(now)),
        Band(Text("TO DO", T.T_XL, align="center"), (10, 8, 8, 8)),
        Row((Text(" + ".join(lists), T.T_L, max_lines=2), "flex"), (Text(count, T.T_M), "auto"), gap=10),
        Rule("hr2"),
        Col(Text("THE BIG 3", T.T_XL), Text("Do these and the day is a win.", T.T_M), gap=2),
        *[big_box(i + 1, t, p) for i, t in enumerate(p["big"])],
    ]
    n = len(p["big"])
    if p["groups"]:
        blocks.append(Rule("hr2").m(4))
        for name, inv, tasks, more in p["groups"]:
            boxes = []
            for t in tasks:
                n += 1
                boxes.append(small_box(n, t, p))
            if more:
                boxes.append(Text(f"+{more} more", T.T_S))
            blocks.append(Col(SectionRule(name, inverted=inv), *boxes, gap=8))
    total = p["count"]
    prog = [Row((Text("PROGRESS", T.PX), "flex"), Text(f"0 / {total}", T.T_M))]
    if total <= 12:
        prog.append(Grid([Fill("none", 18, 2) for _ in range(total)], max(1, total), colgap=4))
    blocks.append(Col(*prog, gap=6).m(4))
    blocks.append(Text("Big 3 = the first 3 late or due-today tasks, in your list order. "
                       "Drag to reorder in Google Tasks.", T.T_S, align="center"))
    return blocks


def all_clear(data: dict, now: datetime, p: dict | None = None) -> list:
    """7.3: nothing due today and nothing late."""
    p = p or prepare(data)
    blocks: list = [
        Header("GOOGLE TASKS", d_label(now)),
        Rule("hr2"),
        Pad(tick_drawing(150), t=10),
        Text("ALL CLEAR", T.T_XL, align="center"),
        Text("Nothing due today and nothing late.", T.T_M, align="center").m(-6),
        Rule("hr"),
    ]
    if p["coming"]:
        blocks.append(Text("COMING UP", T.PX_B))
        for t in p["coming"]:
            blocks.append(Row((Text(t["_title"], T.T_M, max_lines=2), "flex"),
                              (Text(short_date(_due(t), p["today"]), T.T_S), "auto"), gap=10))
    blocks.append(Band(Text("ENJOY THE DAY", T.T_L, align="center"), (8, 8, 8, 8)))
    return blocks
