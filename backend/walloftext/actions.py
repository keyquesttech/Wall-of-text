"""Quick actions shared by the button gestures and the quick-action chips (BUILD_PLAN 8).

Each action returns a short sentence for the UI and may enqueue a print.
Actions that need data sources (weather, agenda) use `svc.sources`, which
Phase 4 provides; without it they print a plain "unavailable" line.
"""
from __future__ import annotations

import json
import logging
import random
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


def fortunes(svc: "Services") -> list[str]:
    try:
        items = json.loads(FORTUNES.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        log.error("fortunes file missing or unreadable at %s; using the short built-in list", FORTUNES)
        items = list(FALLBACK_FORTUNES)
    try:
        extra = json.loads(svc.store.get("custom_fortunes", "[]") or "[]")
        items += [x for x in extra if isinstance(x, str) and x.strip()]
    except ValueError:
        pass
    return items


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
        text = random.choice(fortunes(svc))
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
