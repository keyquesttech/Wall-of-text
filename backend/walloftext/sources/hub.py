"""All data sources behind one object, plus the routine "sections" that turn
them into print blocks. Every source failure becomes a plain line on paper,
never a silent failure (BUILD_PLAN 7)."""
from __future__ import annotations

import asyncio
import json
import logging
import random
import time
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING, Any
from zoneinfo import ZoneInfo

import httpx

from ..actions import fortunes
from .calendar import Event, fetch_ics, owner_from_url, parse_events
from .normalise import calendar_data
from .weather import CACHE_S, Forecast, OpenMeteo, WeatherProvider

if TYPE_CHECKING:
    from ..services import Services

log = logging.getLogger(__name__)

SECTION_TYPES = {
    "date": "Date header",
    "weather": "Weather",
    "agenda": "Today's calendar",
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
        # Google Tasks was removed; don't leave its sign-in token lying around on the Pi.
        (svc.settings.data_dir / "google-token.json").unlink(missing_ok=True)
        self._weather_cache: Forecast | None = None
        self._status: dict[str, dict] = {}
        self._ics: dict[str, tuple[float, bytes]] = {}

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

    def _now(self) -> datetime:
        return datetime.now(self.tz())

    def weather_slip(self, fs: tuple[Forecast | None, int | None], template: str = "weather_briefing") -> dict:
        """The weather briefing (schedules, routines) or Weather now (button, chip) as a kit slip.
        No usable forecast → "Weather unavailable" with the last forecast time."""
        f, stale = fs
        now = self._now()
        if f is None or not f.data:
            last = self._weather_cache or self._stored_forecast()
            when = datetime.fromtimestamp(last.fetched_at, self.tz()).strftime("%a %H:%M") if last and last.fetched_at else None
            return {"type": "slip", "template": "unavailable",
                    "data": {"source": "WEATHER", "title": "Weather unavailable", "now": now.replace(tzinfo=None).isoformat(),
                             "text": "Can't reach the weather service.", "last": when}}
        data = dict(f.data, now=now.replace(tzinfo=None).isoformat())
        th = self.svc.app_settings.get("weather").get("thresholds")
        if isinstance(th, dict):
            data["thresholds"] = th
        if stale:
            data["staleFrom"] = datetime.fromtimestamp(f.fetched_at, self.tz()).strftime("%H:%M")
        return {"type": "slip", "template": template, "data": data}

    def _stored_forecast(self) -> Forecast | None:
        try:
            return Forecast(**json.loads(self.svc.store.get("weather_cache", "") or "{}"))
        except (TypeError, ValueError):
            return None

    async def weather_doc(self, template: str = "weather_now") -> dict:
        return {"blocks": [self.weather_slip(await self.weather(), template)]}

    # ---------------------------------------------------------- calendar --
    async def _fetch_ics(self, url: str) -> bytes:
        hit = self._ics.get(url)
        if hit and time.time() - hit[0] < 600:
            return hit[1]
        ics = await fetch_ics(url, self.http)
        self._ics[url] = (time.time(), ics)
        return ics

    async def events(self, day: date | None = None, days: int = 1) -> tuple[list[Event], list[str]]:
        tz = self.tz()
        day = day or datetime.now(tz).date()
        cals = self.svc.app_settings.get("calendars") or []
        events: list[Event] = []
        errors: list[str] = []
        for cal in cals:
            if not cal.get("url"):
                continue
            try:
                ics = await self._fetch_ics(cal["url"])
                events += await asyncio.to_thread(parse_events, ics, day, tz, cal.get("name", ""), days,
                                                  owner_from_url(cal["url"]))
                self._ok(f"calendar:{cal.get('id')}")
            except Exception as exc:
                log.warning("calendar %s failed: %s", cal.get("name"), exc)
                errors.append(f"Calendar “{cal.get('name') or 'calendar'}” unavailable")
                self._fail(f"calendar:{cal.get('id')}", "Can't read this calendar link.")
        events.sort(key=lambda e: (not e.all_day, e.start if isinstance(e.start, datetime) else datetime.min.replace(tzinfo=tz)))
        return events, errors

    async def agenda_slip(self, evs: tuple[list[Event], list[str]] | None = None) -> dict:
        """The itinerary (or the free-day slip, with the next event in 14 days)."""
        tz = self.tz()
        now = self._now()
        cals = self.svc.app_settings.get("calendars") or []
        if not cals:
            return {"type": "slip", "template": "unavailable",
                    "data": {"source": "GOOGLE CALENDAR", "title": "No calendars yet", "now": now.replace(tzinfo=None).isoformat(),
                             "text": "Add one in Settings › Connections."}}
        ev, errs = evs or await self.events()
        upcoming: list[Event] = []
        if not ev:
            later, _ = await self.events(now.date() + timedelta(days=1), 14)
            upcoming = sorted(later, key=lambda e: (e.start.date() if isinstance(e.start, datetime) else e.start,
                                                    not e.all_day,
                                                    e.start if isinstance(e.start, datetime) else datetime.min.replace(tzinfo=tz)))
        data = calendar_data(ev, errs, now.date(), now, [c.get("name", "") for c in cals], upcoming)
        return {"type": "slip", "template": "itinerary", "data": data}

    async def agenda_doc(self) -> dict:
        return {"blocks": [await self.agenda_slip()]}

    # ---------------------------------------------------------- sections --
    async def section_blocks(self, sec: dict[str, Any], ctx: dict) -> list[dict]:
        """One routine section → kit slip blocks (PRINT_TEMPLATES 1, 8b)."""
        t = sec.get("type")
        now = self._now()
        stamp = now.replace(tzinfo=None).isoformat()
        if t == "date":
            return [{"type": "slip", "template": "date", "data": {"now": stamp}}]
        if t == "weather":
            return [self.weather_slip(ctx.get("weather") or await self.weather(), "weather_briefing")]
        if t == "agenda":
            return [await self.agenda_slip(ctx.get("events"))]
        if t == "fortune":
            return [{"type": "slip", "template": "fortune",
                     "data": {"text": random.choice(fortunes(self.svc)), "now": stamp}}]
        if t == "quote":
            text = (sec.get("text") or "").strip()
            return [{"type": "slip", "template": "fortune", "data": {"label": "QUOTE", "text": text, "now": stamp}}] \
                if text else []
        if t == "countdown":
            try:
                date.fromisoformat(sec.get("date", ""))
            except ValueError:
                return [{"type": "slip", "template": "unavailable",
                         "data": {"source": "COUNTDOWN", "title": "Countdown date missing", "now": stamp}}]
            return [{"type": "slip", "template": "countdown",
                     "data": {"date": sec["date"], "label": sec.get("label"), "set_on": sec.get("set_on"),
                              "tip": sec.get("tip"), "now": stamp}}]
        if t == "shopping":
            lst = self.svc.extras.get("lists")
            items = lst.open_items("shopping") if lst else []
            if not items and sec.get("skip_empty", True):
                return []
            return [{"type": "slip", "template": "shopping", "data": {"items": items, "now": stamp}}]
        if t == "divider":
            return []  # sections are always separated by a cut rule now
        if t == "message":
            doc = sec.get("document") or {}
            blocks = [b for b in doc.get("blocks", []) if isinstance(b, dict)][:60]
            return [{"type": "group", "blocks": blocks}] if blocks else []
        return []

    async def routine_doc(self, sections: list[dict], ctx: dict | None = None) -> dict:
        """Each block's slip one after another, a dashed cut rule between them; the renderer adds the
        single end mark after the last block (PRINT_TEMPLATES 1, 4.7)."""
        ctx = ctx or {}
        parts: list[list[dict]] = []
        for sec in sections:
            try:
                b = await self.section_blocks(sec, ctx)
            except Exception:
                log.exception("section %s failed", sec.get("type"))
                b = [{"type": "slip", "template": "unavailable",
                      "data": {"source": SECTION_TYPES.get(sec.get("type"), "Section"),
                               "title": f"{SECTION_TYPES.get(sec.get('type'), 'Section')} unavailable",
                               "now": self._now().replace(tzinfo=None).isoformat()}}]
            if b:
                parts.append(b)
        if not parts:
            parts = [[{"type": "slip", "template": "unavailable",
                       "data": {"source": "ROUTINE", "title": "Nothing to print",
                                "now": self._now().replace(tzinfo=None).isoformat()}}]]
        blocks: list[dict] = []
        for i, p in enumerate(parts):
            if i:
                blocks.append({"type": "cut"})
            blocks += p
        return {"blocks": blocks}
