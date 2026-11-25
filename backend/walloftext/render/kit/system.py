"""Every other slip, built from the design system (PRINT_TEMPLATES 8b, reference/System.dc.html).

Skeleton: header row → title → hr2 → body → (end mark, added by the pipeline).
"""
from __future__ import annotations

import random
from datetime import date, datetime

from . import tokens as T
from .nodes import Band, Bitmap, Box, Checkbox, Col, Custom, Fill, Grid, Meter, Pad, Row, Rule, SectionRule, Text
from .slip import Header, d_label, dt_label

NOTE = T.Style(T.SG_BOLD, 28, 32)
FORTUNE = T.Style(T.SG_BOLD, 30, 34)
QUOTE_MARK = T.Style(T.SG_BOLD, 92, 60)


def _split(text: str) -> tuple[str, str]:
    text = (text or "").strip()
    first, _, rest = text.partition("\n")
    return first.strip(), rest.strip()


def note(data: dict, now: datetime) -> list:
    """Note: message in Space Grotesk bold 28/32, extra lines in t-m."""
    first, rest = _split(data.get("text", ""))
    return [Header(data.get("source") or "NOTE", data.get("right") or dt_label(now)), Rule("hr2"),
            Text(first, NOTE) if first else None, Text(rest, T.T_M) if rest else None,
            *(_pictures(data))]


def _pictures(data: dict) -> list:
    out = []
    if data.get("sticker"):
        from ..stickers import sticker_image
        out.append(Col(Bitmap(sticker_image(data["sticker"], 120)), align="center"))
    if data.get("image") is not None:
        out.append(Bitmap(data["image"]))
    return out


def guest_note(data: dict, now: datetime) -> list:
    name = (data.get("name") or "a guest").strip()
    return note(dict(data, source="GUEST NOTE", right=f"from {name} · {now:%H:%M}".upper()), now)


def message(data: dict, now: datetime) -> list:
    """Remote message: subject in t-l, body in t-m. No from/via band."""
    sender = (data.get("sender") or "").strip()
    right = (f"from {sender} · " if sender else "") + f"{d_label(now)} · {now:%H:%M}"
    return [Header("MESSAGE", right.upper()),
            Text(data.get("subject", ""), T.T_L, max_lines=3) if data.get("subject") else None,
            Text(data.get("body", ""), {"S": T.T_S, "L": T.T_L, "XL": T.T_XL}.get(data.get("size"), T.T_M))
            if data.get("body") else None,
            *_pictures(data)]


def shopping(data: dict, now: datetime) -> list:
    """The List (Create › List): a one-off checklist, every item with a box to tick."""
    items = [i for i in data.get("items") or [] if str(i).strip()]
    sections = data.get("sections") or ([("", items)] if items else [])
    n = sum(len(s[1]) for s in sections)
    blocks = [Header("LIST", dt_label(now)),
              Band(Text("LIST", T.T_XL, align="center"), (10, 8, 8, 8)),
              Row((Text(f"{n} item{'s' if n != 1 else ''}", T.T_L), "flex")),
              Rule("hr2")]
    if not n:
        blocks.append(Text("Nothing on the list.", T.T_M))
    for name, its in sections:
        rows = [Row(Checkbox(), (Text(str(i), T.T_M, max_lines=2), "flex")) for i in its]
        blocks.append(Col(SectionRule(name), *rows, gap=8) if name else Col(*rows, gap=8))
    return blocks


def fortune(data: dict, now: datetime) -> list:
    """Fortune or quote: a big quote mark, the text in bold 30/34, then the lucky number."""
    label = data.get("label") or "FORTUNE"
    blocks = [Header(label, dt_label(now)), Rule("hr2"),
              Custom(52, lambda c, x, y, w, h, ink: Text("“", QUOTE_MARK).draw(c, x, y, w, 60, ink)),
              Text(data.get("text", ""), FORTUNE)]
    if label == "FORTUNE":
        lucky = data.get("lucky")
        if lucky is None:
            lucky = random.randint(1, 99)
        blocks += [Rule("hr"), Row((Text("LUCKY NUMBER", T.PX), "flex"), Box(Text(str(lucky), T.T_L), pad=(2, 12, 2, 12)))]
    return blocks


def countdown(data: dict, now: datetime) -> list:
    target = date.fromisoformat(data["date"])
    today = now.date()
    days = (target - today).days
    label = data.get("label") or f"{target:%-d %B}"
    if days > 1:
        big, unit, line = str(days), "DAYS", f"until {label}"
    elif days == 1:
        big, unit, line = "1", "DAY", f"until {label}"
    elif days == 0:
        big, unit, line = "0", "DAYS", f"{label} is today"
    else:
        big, unit, line = str(-days), "DAYS", f"since {label}"
    blocks = [Header("COUNTDOWN", dt_label(now)), Rule("hr2"),
              Row(Text(big, T.T_XXL), Pad(Text(unit, T.T_XL), b=6), gap=12, align="bottom"),
              Text(line, T.T_M, max_lines=2).m(-4)]
    try:
        set_on = date.fromisoformat(data.get("set_on") or "")
    except ValueError:
        set_on = None
    if set_on and set_on < target:
        pct = max(0, min(100, (today - set_on).days * 100 / (target - set_on).days))
        blocks.append(Col(Meter(pct),
                          Row((Text(f"SET {set_on.day} {set_on:%b}", T.PX), "flex"),
                              Text(f"{target:%a} {target.day} {target:%b}", T.PX)), gap=4))
    tip = data.get("tip")
    if not tip:
        tip = "TODAY'S THE DAY" if days == 0 else "TOMORROW!" if days == 1 else \
            f"ON {target:%A} {target.day} {target:%B}".upper() if days > 1 else f"WAS {target:%a} {target.day} {target:%b}".upper()
    blocks.append(Band(Text(tip, T.T_L, align="center", max_lines=2), (8, 8, 8, 8)))
    return blocks


def test_page(data: dict, now: datetime) -> list:
    def ruler(c, x, y, w, h, ink):
        for tx in range(x, x + w, 8):
            c.rect(tx, y, tx + 2, y + 14, ink)
        c.rect(x, y + 14, x + w, y + 16, ink)

    labels = Custom(T.PX.lh, lambda c, x, y, w, h, ink: [
        Text(f"{mm}" + (" mm" if mm == 40 else ""), T.PX(track=0)).draw(c, x + mm * 8 - (0 if mm == 0 else 6), y, 60, T.PX.lh, ink)
        for mm in (0, 10, 20, 30, 40)])
    cell = lambda k, v, st=T.T_L: Col(Text(k, T.PX), Text(v, st))  # noqa: E731
    return [
        Header("PRINTER", dt_label(now)),
        Band(Text("TEST PAGE", T.T_XL, align="center"), (10, 8, 8, 8)),
        Grid([Fill("d25", 40, 2), Fill("d50", 40, 2), Fill("d75", 40, 2), Fill("solid", 40)], 4, colgap=6),
        Col(Custom(16, ruler), labels),
        Grid([cell("PAPER", data.get("paper", "—")), cell("DARKNESS", data.get("darkness", "—")),
              cell("SPEED", data.get("speed", "—")), cell("ADDRESS", data.get("address", "walloftext.local"), T.MONO_B(size=14))],
             2, colgap=12, rowgap=8),
    ]


CAL_ROWS = 800  # dot rows between the two calibration lines: 100 mm on a perfect 203 dpi printer


def calibration(data: dict, now: datetime) -> list:
    """Paper-length calibration: two full-width lines exactly CAL_ROWS dot rows apart (top edge to
    top edge), with a ruler of nominal millimetres between them. The measured distance gives the
    real paper advance per dot row, used only for the paper-roll estimate."""
    def draw(c, x, y, w, h, ink):
        c.rect(x, y, x + w, y + 3, ink)  # top line
        c.rect(x, y + CAL_ROWS, x + w, y + CAL_ROWS + 3, ink)  # bottom line
        c.rect(x, y, x + 2, y + CAL_ROWS + 3, ink)  # ruler spine
        for r in range(0, CAL_ROWS + 1, 8):  # nominal 1 mm ticks
            ln = 46 if r % 80 == 0 else 26 if r % 40 == 0 else 12
            c.rect(x, y + r, x + ln, y + r + 2, ink)
        for r in range(80, CAL_ROWS, 80):
            Text(f"{r // 8}", T.PX(track=0)).draw(c, x + 54, y + r - 6, 60, T.PX.lh, ink)
        mid = y + CAL_ROWS // 2 - 60
        Text("MEASURE THIS GAP", T.PX_B, align="center").draw(c, x + 70, mid, w - 70, T.PX.lh, ink)
        Text("top edge of the top line", T.T_S, align="center").draw(c, x + 70, mid + 22, w - 70, T.T_S.lh, ink)
        Text("to the top edge of", T.T_S, align="center").draw(c, x + 70, mid + 42, w - 70, T.T_S.lh, ink)
        Text("the bottom line, in mm", T.T_S, align="center").draw(c, x + 70, mid + 62, w - 70, T.T_S.lh, ink)
        Text("About 100 mm", T.T_L, align="center").draw(c, x + 70, mid + 92, w - 70, T.T_L.lh, ink)

    return [
        Header("PRINTER", dt_label(now)),
        Band(Text("CALIBRATE LENGTH", T.T_L, align="center"), (8, 8, 8, 8)),
        Text("Enter the gap in Settings › Paper roll.", T.T_S, align="center"),
        Custom(CAL_ROWS + 3, draw),
    ]


def date_slip(data: dict, now: datetime) -> list:
    return [Header("TODAY", dt_label(now)), Text(f"{now:%A}".upper(), T.T_XL),
            Text(f"{now.day} {now:%B %Y}", T.T_L).m(-6)]


def unavailable(data: dict, now: datetime) -> list:
    """A source that couldn't be read: say so on paper, never fail silently."""
    blocks = [Header(data.get("source", "SOURCE").upper(), dt_label(now)), Rule("hr2"),
              Text(data.get("title", "UNAVAILABLE").upper(), T.T_XL, align="center", max_lines=2)]
    if data.get("text"):
        blocks.append(Text(data["text"], T.T_M, align="center", max_lines=3).m(-6))
    if data.get("last"):
        blocks.append(Text(f"Last good data: {data['last']}", T.T_S, align="center"))
    return blocks

