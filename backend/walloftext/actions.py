"""Quick actions shared by the button gestures and the quick-action chips (BUILD_PLAN 8).

Each action returns a short sentence for the UI and may enqueue a print.
Actions that need data sources (weather, agenda) use `svc.sources`, which
Phase 4 provides; without it they print a plain "unavailable" line.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import logging
import random
import time
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .services import Services

log = logging.getLogger(__name__)

ACTIONS = {
    "none": "Do nothing",
    "reprint_last": "Reprint the last print",
    "weather_now": "Weather now",
    "agenda_today": "Today's agenda",
    "random_fortune": "Random fortune",
    "cancel_queue": "Cancel the queue",
    "shopping_list": "Print the shopping list",
}

FORTUNES = Path(__file__).parent / "sources" / "fortunes.json"


FALLBACK_FORTUNES = [
    "Today is a good day to finish one small thing.",
    "Drink a glass of water. Then another one.",
    "Someone in this house could use a compliment.",
]


def builtin_fortunes() -> list[str]:
    try:
        return [x for x in json.loads(FORTUNES.read_text(encoding="utf-8")) if isinstance(x, str) and x.strip()]
    except (OSError, ValueError):
        log.error("fortunes file missing or unreadable at %s; using the short built-in list", FORTUNES)
        return list(FALLBACK_FORTUNES)


def custom_fortunes(svc: "Services") -> list[str]:
    try:
        return [x for x in json.loads(svc.store.get("custom_fortunes", "[]") or "[]") if isinstance(x, str) and x.strip()]
    except ValueError:
        return []


def fortunes(svc: "Services") -> list[str]:
    """Every fortune in play: the uploaded ones, plus the built-in ones unless switched off
    (they are always used when nothing has been uploaded)."""
    custom = custom_fortunes(svc)
    use_builtin = svc.app_settings.get("fortunes").get("use_builtin", True) or not custom
    items = (builtin_fortunes() if use_builtin else []) + custom
    seen: set[str] = set()
    return [x for x in items if not (x in seen or seen.add(x))]


RECENT_DAYS = 7
RECENT_WEIGHT = 0.05  # a fortune printed in the last week is 20x less likely when a new round starts


def _fid(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]


def pick_fortune(svc: "Services", now: float | None = None, rng: random.Random | None = None) -> str:
    """A random fortune, fair over time: each one prints once before any repeats (a "round").
    When every fortune has been used, a new round starts, and the ones printed in the last
    7 days get a small weight so the same line doesn't come back within a week."""
    items = fortunes(svc)
    now = time.time() if now is None else now
    rng = rng or random
    try:
        state = json.loads(svc.store.get("fortune_state", "{}") or "{}")
    except ValueError:
        state = {}
    used: list[str] = state.get("round", [])
    last: dict[str, float] = state.get("last", {})
    ids = [_fid(x) for x in items]
    pool = [i for i, f in enumerate(ids) if f not in set(used)]
    if not pool:
        used, pool = [], list(range(len(items)))
    weights = [RECENT_WEIGHT if now - last.get(ids[i], 0) < RECENT_DAYS * 86400 else 1.0 for i in pool]
    k = rng.choices(pool, weights=weights)[0]
    used.append(ids[k])
    last[ids[k]] = now
    if len(last) > 2000:  # keep the newest only
        last = dict(sorted(last.items(), key=lambda kv: kv[1])[-2000:])
    svc.store.set("fortune_state", json.dumps({"round": [u for u in used if u in set(ids)], "last": last}))
    return items[k]


MAX_FORTUNE_CHARS = 300
MAX_FORTUNES = 5000
_HEADERS = {"fortune", "fortunes", "text", "quote", "quotes", "message", "line"}


def parse_fortunes_csv(raw: bytes) -> tuple[list[str], int]:
    """A CSV from a spreadsheet, or plain text with one fortune per line → (fortunes, skipped).

    With a header row named fortune/text/quote/message, that column is used; otherwise the
    first column. A file that isn't a consistent table (for example typed sentences with
    commas in them) is read one line per fortune, so a comma never cuts a fortune short.
    Rows that are empty, repeated or longer than 300 characters are skipped."""
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("latin-1")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    first = next((ln for ln in text.split("\n") if ln.strip()), "")
    delim = max(",;\t", key=first.count) if any(d in first for d in ",;\t") else ","
    rows = [r for r in csv.reader(io.StringIO(text), delimiter=delim) if any(c.strip() for c in r)]
    cells: list[str]
    if rows and any(c.strip().lower() in _HEADERS for c in rows[0]):
        col = next(i for i, c in enumerate(rows[0]) if c.strip().lower() in _HEADERS)
        cells = [r[col] if len(r) > col else "" for r in rows[1:]]
    elif all(len(r) == 1 for r in rows):
        cells = [r[0] for r in rows]
    elif len({len(r) for r in rows}) == 1 and '"' in text:
        cells = [r[0] for r in rows]  # a real table: the first column
    else:
        cells = [ln.strip().strip('"') for ln in text.split("\n")]
    out: list[str] = []
    seen: set[str] = set()
    skipped = 0
    for c in cells:
        cell = " ".join(c.split())
        if not cell:
            continue
        if len(cell) > MAX_FORTUNE_CHARS or cell in seen:
            skipped += 1
            continue
        seen.add(cell)
        out.append(cell)
    if len(out) > MAX_FORTUNES:
        skipped += len(out) - MAX_FORTUNES
        out = out[:MAX_FORTUNES]
    return out, skipped


def fortune_doc(text: str) -> dict:
    return {"blocks": [{"type": "slip", "template": "fortune",
                        "data": {"text": text, "now": datetime.now().isoformat(timespec="minutes")}}]}


async def run(svc: "Services", action: str, source: str = "Button") -> str:
    if action.startswith("routine:"):
        sched = svc.extras.get("scheduler")
        if not sched:
            return "Routines aren't available."
        return await sched.run_now(action.split(":", 1)[1], source=source)
    if action == "none":
        return "Nothing to do."
    if action == "reprint_last":
        rows = svc.queue.list(("done",), limit=10)
        rows = [r for r in rows if r["source"] != "System"]
        if not rows:
            return "Nothing printed yet."
        svc.queue.retry(rows[0]["id"], source=source)
        return f"Reprinting “{rows[0]['title']}”."
    if action == "random_fortune":
        text = pick_fortune(svc)
        svc.print_document(fortune_doc(text), source, "Fortune")
        return "Printing a fortune."
    if action == "shopping_list":
        lists = svc.extras.get("lists")
        if lists is None:
            return "Lists aren't available."
        svc.print_document(lists.document("shopping"), source, "Shopping list")
        return "Printing the shopping list."
    if action == "cancel_queue":
        n = svc.queue.cancel_all()
        return f"Cancelled {n} print{'s' if n != 1 else ''}."
    if action in ("weather_now", "agenda_today"):
        sources = svc.extras.get("sources")
        if sources is None:
            doc = {"blocks": [{"type": "text", "text": "Weather unavailable" if action == "weather_now"
                               else "Agenda unavailable", "align": "center"}]}
        else:
            doc = await (sources.weather_doc() if action == "weather_now" else sources.agenda_doc())
        svc.print_document(doc, source, "Weather" if action == "weather_now" else "Today's agenda")
        return "Printing the weather." if action == "weather_now" else "Printing today's agenda."
    return "Unknown action."


def now_label() -> str:
    return datetime.now().strftime("%H:%M")
