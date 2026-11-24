"""All data sources behind one object, plus the routine "sections" that turn
them into print blocks. Every source failure becomes a plain line on paper,
never a silent failure (BUILD_PLAN 7)."""
from __future__ import annotations

import json
import logging
import time
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING, Any
from zoneinfo import ZoneInfo

import httpx

from ..actions import pick_fortune
from .calendar import Event
from .google import GoogleAuth, GoogleCalendar, GoogleError, GoogleTasks
from .normalise import any_due, calendar_data, tasks_data
from .weather import CACHE_S, Forecast, OpenMeteo, WeatherProvider

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
    "divider": "Divider",
    "message": "My message",
}


class Sources:
    def __init__(self, svc: "Services", weather: WeatherProvider | None = None,
                 http: httpx.AsyncClient | None = None):
        self.svc = svc
        self.weather_provider = weather or OpenMeteo(http)
        self.http = http
        self._google: GoogleAuth | None = None
        # The old PC-made Tasks token is replaced by the in-app Google sign-in.
        (svc.settings.data_dir / "google-token.json").unlink(missing_ok=True)
        self._weather_cache: Forecast | None = None
        self._status: dict[str, dict] = {}
        self._drop_ical_links()

    def _drop_ical_links(self) -> None:
        """Calendars used to be private iCal links in the settings. They are secrets and no longer
        used, so rewrite the stored settings without them."""
        try:
            raw = json.loads(self.svc.store.get(self.svc.app_settings.KEY, "{}") or "{}")
        except ValueError:
            return
        if "calendars" in raw or "tasks" in raw:
            raw.pop("calendars", None)
            raw.pop("tasks", None)
            self.svc.store.set(self.svc.app_settings.KEY, json.dumps(raw))

    @property
    def google(self) -> GoogleAuth:
        if self._google is None:
            from ..remote.secrets import Secrets
            sec = self.svc.extras.get("secrets") or Secrets(self.svc.settings.data_dir / "secrets.json")
            self._google = GoogleAuth(sec, self.http)
        return self._google

    @google.setter
    def google(self, auth: GoogleAuth) -> None:
        self._google = auth

    @property
    def tasks_api(self) -> GoogleTasks:
        return GoogleTasks(self.google)

    @property
    def calendar_api(self) -> GoogleCalendar:
        return GoogleCalendar(self.google)

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
    async def chosen_calendars(self) -> list[dict]:
        """[{id, name}] from Settings, or the account's main calendar when none are chosen."""
        chosen = [c for c in self.svc.app_settings.get("google").get("calendars") or [] if c.get("id")]
        if chosen:
            return chosen
        return [{"id": "primary", "name": self.google.status().get("email") or "Calendar"}]

    async def events(self, day: date | None = None, days: int = 1) -> tuple[list[Event], list[str]]:
        tz = self.tz()
        day = day or datetime.now(tz).date()
        if not self.google.connected():
            return [], ["Google isn't connected"]
        events: list[Event] = []
        errors: list[str] = []
        for cal in await self.chosen_calendars():
            try:
                events += await self.calendar_api.events(cal["id"], cal.get("name", ""), day, tz, days)
                self._ok("calendar")
            except GoogleError as exc:
                errors.append(f"Calendar “{cal.get('name') or 'calendar'}” unavailable")
                self._fail("calendar", str(exc), reauth=exc.reauth)
            except Exception as exc:
                log.warning("calendar %s failed: %s", cal.get("name"), exc)
                errors.append(f"Calendar “{cal.get('name') or 'calendar'}” unavailable")
                self._fail("calendar", "Can't reach Google Calendar.")
        events.sort(key=lambda e: (not e.all_day, e.start if isinstance(e.start, datetime) else datetime.min.replace(tzinfo=tz)))
        return events, errors

    async def agenda_slip(self, evs: tuple[list[Event], list[str]] | None = None) -> dict:
        """The itinerary (or the free-day slip, with the next event in 14 days)."""
        tz = self.tz()
        now = self._now()
        if not self.google.connected():
            return {"type": "slip", "template": "unavailable",
                    "data": {"source": "GOOGLE CALENDAR", "title": "Google isn't connected",
                             "now": now.replace(tzinfo=None).isoformat(),
                             "text": "Sign in in Settings › Connections › Google."}}
        ev, errs = evs or await self.events()
        upcoming: list[Event] = []
        if not ev:
            later, _ = await self.events(now.date() + timedelta(days=1), 14)
            upcoming = sorted(later, key=lambda e: (e.start.date() if isinstance(e.start, datetime) else e.start,
                                                    not e.all_day,
                                                    e.start if isinstance(e.start, datetime) else datetime.min.replace(tzinfo=tz)))
        cals = await self.chosen_calendars()
        data = calendar_data(ev, errs, now.date(), now, [c.get("name", "") for c in cals], upcoming)
        return {"type": "slip", "template": "itinerary", "data": data}

    async def agenda_doc(self) -> dict:
        return {"blocks": [await self.agenda_slip()]}

    # ------------------------------------------------------------- tasks --
    async def tasks(self) -> tuple[list[dict], str | None]:
        if not self.google.connected():
            return [], "Google isn't connected."
        try:
            lists = self.svc.app_settings.get("google").get("task_lists") or None
            items = await self.tasks_api.tasks(lists)
            self._ok("tasks")
            return items, None
        except GoogleError as exc:
            self._fail("tasks", str(exc), reauth=exc.reauth)
            return [], "Tasks unavailable"
        except Exception as exc:
            log.warning("tasks failed: %s", exc)
            self._fail("tasks", "Can't reach Google Tasks.")
            return [], "Tasks unavailable"

    # ---------------------------------------------------------- sections --
    def tasks_slip(self, res: tuple[list[dict], str | None], title: str | None = None) -> dict:
        items, err = res
        now = self._now()
        if err:
            return {"type": "slip", "template": "unavailable",
                    "data": {"source": "GOOGLE TASKS", "title": err, "now": now.replace(tzinfo=None).isoformat()}}
        return {"type": "slip", "template": "todo", "data": tasks_data(items, now)}

    def has_due_tasks(self, res: tuple[list[dict], str | None]) -> bool:
        return any_due(res[0], self._now().date())

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
        if t == "tasks":
            return [self.tasks_slip(ctx.get("tasks") or await self.tasks(), sec.get("title"))]
        if t == "fortune":
            return [{"type": "slip", "template": "fortune",
                     "data": {"text": pick_fortune(self.svc), "now": stamp}}]
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
