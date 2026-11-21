"""All data sources behind one object, plus the routine "sections" that turn
them into print blocks. Every source failure becomes a plain line on paper,
never a silent failure (BUILD_PLAN 7)."""
from __future__ import annotations

import asyncio
import json
import logging
import random
import time
from datetime import date, datetime
from typing import TYPE_CHECKING, Any
from zoneinfo import ZoneInfo

import httpx

from ..actions import fortunes
from .calendar import Event, agenda_blocks, fetch_ics, parse_events
from .google_tasks import GoogleTasks, TasksError
from .weather import CACHE_S, Forecast, OpenMeteo, WeatherProvider, weather_blocks

if TYPE_CHECKING:
    from ..services import Services

log = logging.getLogger(__name__)

SECTION_TYPES = {
    "date": "Date header",
    "weather": "Weather",
    "agenda": "Today's calendar",
    "tasks": "Google Tasks",
    "fortune": "Fortune",
    "quote": "Your own line",
    "countdown": "Countdown",
    "shopping": "Shopping list",
    "divider": "Divider",
    "message": "My message",
}


class Sources:
    def __init__(self, svc: "Services", weather: WeatherProvider | None = None,
                 http: httpx.AsyncClient | None = None):
        self.svc = svc
        self.weather_provider = weather or OpenMeteo(http)
        self.http = http
        self.tasks_api = GoogleTasks(svc.settings.data_dir / "google-token.json", http)
        self._weather_cache: Forecast | None = None
        self._status: dict[str, dict] = {}

    def tz(self) -> ZoneInfo:
        try:
            return ZoneInfo(self.svc.app_settings.get("schedules").get("timezone", "Europe/London"))
        except Exception:
            return ZoneInfo("Europe/London")

    def status(self) -> dict:
        return self._status

    def _ok(self, name: str) -> None:
        self._status[name] = {"ok": True, "at": time.time()}

    def _fail(self, name: str, msg: str, reauth: bool = False) -> None:
        self._status[name] = {"ok": False, "at": time.time(), "message": msg, "reauth": reauth}

    # ----------------------------------------------------------- weather --
    async def set_place(self, place: str) -> dict | None:
        res = await self.weather_provider.geocode(place)
        if res:
            self.svc.app_settings.patch({"weather": {"place": res["place"], "lat": res["lat"], "lon": res["lon"]}})
            self._weather_cache = None
        return res

    async def weather(self) -> tuple[Forecast | None, int | None]:
        """(forecast, minutes stale or None)."""
        w = self.svc.app_settings.get("weather")
        if w.get("lat") is None:
            self._fail("weather", "No place set. Add one in Settings › Connections › Weather.")
            return None, None
        try:
            f = await self.weather_provider.forecast(w["lat"], w["lon"], w.get("place") or "Here", w.get("units", "C"))
            self._weather_cache = f
            self.svc.store.set("weather_cache", json.dumps(f.to_dict()))
            self._ok("weather")
            return f, None
        except Exception as exc:
            log.warning("weather failed: %s", exc)
            self._fail("weather", "Can't reach the weather service.")
            cached = self._weather_cache
            if cached is None:
                try:
                    cached = Forecast(**json.loads(self.svc.store.get("weather_cache", "") or "{}"))
                except (TypeError, ValueError):
                    cached = None
            if cached and time.time() - cached.fetched_at < CACHE_S:
                return cached, int((time.time() - cached.fetched_at) / 60)
            return None, None

    async def weather_doc(self) -> dict:
        f, stale = await self.weather()
        return {"blocks": weather_blocks(f, stale)}

    # ---------------------------------------------------------- calendar --
    async def events(self, day: date | None = None) -> tuple[list[Event], list[str]]:
        tz = self.tz()
        day = day or datetime.now(tz).date()
        cals = self.svc.app_settings.get("calendars") or []
        events: list[Event] = []
        errors: list[str] = []
        for cal in cals:
            if not cal.get("url"):
                continue
            try:
                ics = await fetch_ics(cal["url"], self.http)
                events += await asyncio.to_thread(parse_events, ics, day, tz, cal.get("name", ""))
                self._ok(f"calendar:{cal.get('id')}")
            except Exception as exc:
                log.warning("calendar %s failed: %s", cal.get("name"), exc)
                errors.append(f"Calendar “{cal.get('name') or 'calendar'}” unavailable")
                self._fail(f"calendar:{cal.get('id')}", "Can't read this calendar link.")
        events.sort(key=lambda e: (not e.all_day, e.start if isinstance(e.start, datetime) else datetime.min.replace(tzinfo=tz)))
        return events, errors

    async def agenda_doc(self) -> dict:
        tz = self.tz()
        if not self.svc.app_settings.get("calendars"):
            return {"blocks": [{"type": "text", "text": "No calendars yet. Add one in Settings › Connections.", "size": "S"}]}
        ev, errs = await self.events()
        return {"blocks": agenda_blocks(ev, datetime.now(tz).date(), errs)}

    # ------------------------------------------------------------- tasks --
    async def tasks(self) -> tuple[list[dict], str | None]:
        if not self.tasks_api.configured():
            return [], "Google Tasks isn't connected."
        try:
            lists = self.svc.app_settings.get("tasks").get("lists") or None
            items = await self.tasks_api.tasks(lists)
            self._ok("tasks")
            return items, None
        except TasksError as exc:
            self._fail("tasks", str(exc), reauth=exc.reauth)
            return [], "Tasks unavailable"
        except Exception as exc:
            log.warning("tasks failed: %s", exc)
            self._fail("tasks", "Can't reach Google Tasks.")
            return [], "Tasks unavailable"

    # ---------------------------------------------------------- sections --
    async def section_blocks(self, sec: dict[str, Any], ctx: dict) -> list[dict]:
        t = sec.get("type")
        tz = self.tz()
        now = datetime.now(tz)
        if t == "date":
            return [{"type": "heading", "text": now.strftime("%A"), "size": "XL"},
                    {"type": "text", "text": now.strftime("%-d %B %Y"), "align": "center", "size": "M"}]
        if t == "weather":
            f, stale = ctx.get("weather") or await self.weather()
            return weather_blocks(f, stale)
        if t == "agenda":
            ev, errs = ctx.get("events") or await self.events()
            return agenda_blocks(ev, now.date(), errs, sec.get("title"))
        if t == "tasks":
            items, err = ctx.get("tasks") or await self.tasks()
            blocks: list[dict] = [{"type": "banner", "text": sec.get("title") or "To do"}]
            if err:
                blocks.append({"type": "text", "text": err, "size": "S"})
            elif not items:
                blocks.append({"type": "text", "text": "Nothing to do. Nice.", "size": "M"})
            else:
                blocks.append({"type": "checklist", "items": [{"text": i["title"]} for i in items], "size": "M"})
            return blocks
        if t == "fortune":
            return [{"type": "divider", "style": "stars"},
                    {"type": "text", "text": random.choice(fortunes(self.svc)), "align": "center", "size": "M"}]
        if t == "quote":
            text = (sec.get("text") or "").strip()
            return [{"type": "text", "text": text, "align": sec.get("align", "center"), "size": sec.get("size", "M"),
                     "font": sec.get("font")}] if text else []
        if t == "countdown":
            try:
                target = date.fromisoformat(sec.get("date", ""))
            except ValueError:
                return [{"type": "text", "text": "Countdown date missing", "size": "S"}]
            days = (target - now.date()).days
            label = sec.get("label") or target.strftime("%-d %B")
            if days > 1:
                text = f"{days} days until {label}"
            elif days == 1:
                text = f"Tomorrow: {label}"
            elif days == 0:
                text = f"Today: {label}!"
            else:
                text = f"{label} was {-days} days ago"
            return [{"type": "text", "text": text, "size": "L", "align": "center", "bold": True}]
        if t == "shopping":
            lst = self.svc.extras.get("lists")
            items = lst.open_items("shopping") if lst else []
            if not items:
                return [] if sec.get("skip_empty", True) else [{"type": "text", "text": "Shopping list is empty."}]
            return [{"type": "banner", "text": "Shopping"},
                    {"type": "checklist", "items": [{"text": i} for i in items]}]
        if t == "divider":
            return [{"type": "divider", "style": sec.get("style", "dashed")}]
        if t == "message":
            doc = sec.get("document") or {}
            return [b for b in doc.get("blocks", []) if isinstance(b, dict)][:60]
        return []

    async def routine_doc(self, sections: list[dict], ctx: dict | None = None) -> dict:
        ctx = ctx or {}
        blocks: list[dict] = []
        for sec in sections:
            try:
                blocks += await self.section_blocks(sec, ctx)
            except Exception:
                log.exception("section %s failed", sec.get("type"))
                blocks.append({"type": "text", "text": f"{SECTION_TYPES.get(sec.get('type'), 'Section')} unavailable",
                               "size": "S"})
        if not blocks:
            blocks = [{"type": "text", "text": "Nothing to print.", "size": "S"}]
        return {"blocks": blocks}
