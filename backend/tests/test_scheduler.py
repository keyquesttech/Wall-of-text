"""Phase 4: scheduler policy (missed runs, quiet hours, DST, conditions, limits) and sources."""
import json
from datetime import date, datetime
from zoneinfo import ZoneInfo

import httpx
import pytest

from walloftext.scheduler.engine import Scheduler, in_quiet
from walloftext.services import build
from walloftext.sources.calendar import parse_events
from walloftext.sources.google_tasks import GoogleTasks, TasksError
from walloftext.sources.hub import Sources
from walloftext.sources.weather import Forecast, OpenMeteo

LDN = ZoneInfo("Europe/London")


def ts(y, mo, d, h, mi):
    return datetime(y, mo, d, h, mi, tzinfo=LDN).timestamp()


class FakeWeather:
    def __init__(self):
        self.rain = 80
        self.temp = 4.0
        self.fail = False

    async def geocode(self, place):
        return {"place": "Leeds, England, GB", "lat": 53.8, "lon": -1.55}

    async def forecast(self, lat, lon, place, units="C"):
        if self.fail:
            raise httpx.ConnectError("down")
        return Forecast(place, self.temp, "Rain", 9, 2, self.rain, "Rain", [("09:00", 5, 60)], units, 0)


class Clock:
    def __init__(self, t):
        self.t = t

    def __call__(self):
        return self.t


@pytest.fixture
def env(settings, fake_nm):
    svc = build(settings, nm=fake_nm)
    clock = Clock(ts(2026, 11, 20, 6, 0))
    svc.queue.clock = clock
    weather = FakeWeather()
    svc.extras["sources"] = Sources(svc, weather=weather)
    svc.app_settings.patch({"weather": {"place": "Leeds", "lat": 53.8, "lon": -1.55},
                            "schedules": {"quiet_hours": {"enabled": False}}})
    synced = {"v": True}
    sch = Scheduler(svc, clock=clock, synced=lambda: synced["v"])
    svc.extras["scheduler"] = sch
    return svc, sch, clock, weather, synced


def jobs(svc, state=None):
    return [j for j in svc.queue.list(limit=100) if state is None or j["state"] == state]


async def test_runs_on_time_once(env):
    svc, sch, clock, *_ = env
    s = sch.save({"name": "Morning", "time": "07:00", "days": list(range(7)), "sections": [{"type": "date"}, {"type": "weather"}]})
    assert datetime.fromtimestamp(s["next_run"], LDN).hour == 7
    clock.t = ts(2026, 11, 20, 6, 59)
    assert await sch.tick() == 0
    clock.t = ts(2026, 11, 20, 7, 0) + 15
    assert await sch.tick() == 1
    assert await sch.tick() == 0  # never twice
    q = jobs(svc, "queued")
    assert len(q) == 1 and q[0]["source"] == "Schedule" and q[0]["title"] == "Morning"
    assert q[0]["meta"]["late"] is False


async def test_new_schedule_does_not_fire_for_past_time(env):
    svc, sch, clock, *_ = env
    clock.t = ts(2026, 11, 20, 9, 0)
    sch.save({"name": "Earlier", "time": "08:00", "sections": [{"type": "fortune"}]})
    assert await sch.tick() == 0


async def test_missed_late_within_60_prints_late_beyond_logs_missed(env):
    svc, sch, clock, *_ = env
    a = sch.save({"name": "A", "time": "07:00", "sections": [{"type": "fortune"}]})
    b = sch.save({"name": "B", "time": "06:10", "sections": [{"type": "fortune"}]})
    clock.t = ts(2026, 11, 20, 7, 40)  # Pi was off from 06:00 to 07:40
    await sch.tick()
    q = {j["title"]: j for j in jobs(svc)}
    assert q["A"]["state"] == "queued" and q["A"]["meta"]["late"] is True
    assert q["B"]["state"] == "missed" and "06:10" in q["B"]["error"]


async def test_policy_skip(env):
    svc, sch, clock, *_ = env
    svc.app_settings.patch({"schedules": {"missed_policy": "skip"}})
    sch.save({"name": "A", "time": "07:00", "sections": [{"type": "fortune"}]})
    clock.t = ts(2026, 11, 20, 7, 10)
    await sch.tick()
    assert jobs(svc)[0]["state"] == "missed"


async def test_waits_for_clock(env):
    svc, sch, clock, _, synced = env
    sch.save({"name": "A", "time": "07:00", "sections": [{"type": "fortune"}]})
    synced["v"] = False
    clock.t = ts(2026, 11, 20, 7, 0) + 5
    assert await sch.tick() == 0 and sch.status()["clock_synced"] is False
    synced["v"] = True
    clock.t = ts(2026, 11, 20, 7, 30)
    assert await sch.tick() == 1
    assert jobs(svc)[0]["meta"]["late"] is True


async def test_quiet_hours_hold_and_60_minute_rule(env):
    svc, sch, clock, *_ = env
    svc.app_settings.patch({"schedules": {"quiet_hours": {"enabled": True, "start": "22:00", "end": "07:30"}}})
    clock.t = ts(2026, 11, 20, 5, 0)
    sch.save({"name": "Early", "time": "07:00", "sections": [{"type": "fortune"}]})
    sch.save({"name": "TooEarly", "time": "06:00", "sections": [{"type": "fortune"}]})
    clock.t = ts(2026, 11, 20, 6, 0) + 10
    await sch.tick()
    clock.t = ts(2026, 11, 20, 7, 0) + 10
    await sch.tick()
    q = {j["title"]: j for j in jobs(svc)}
    assert q["Early"]["state"] == "held"
    assert q["Early"]["held_until"] == ts(2026, 11, 20, 7, 30)
    assert q["TooEarly"]["state"] == "missed" and "quiet hours" in q["TooEarly"]["error"]
    assert svc.queue.release_held(ts(2026, 11, 20, 7, 30)) == 1


def test_quiet_window_across_midnight():
    t = lambda h, m: datetime(2026, 1, 1, h, m, tzinfo=LDN)
    assert in_quiet(t(23, 0), "22:00", "07:00") and in_quiet(t(3, 0), "22:00", "07:00")
    assert not in_quiet(t(7, 0), "22:00", "07:00") and not in_quiet(t(12, 0), "22:00", "07:00")
    assert in_quiet(t(13, 0), "12:00", "14:00") and not in_quiet(t(14, 0), "12:00", "14:00")


async def test_conditions(env):
    svc, sch, clock, weather, _ = env
    sch.save({"name": "Umbrella", "time": "07:00", "sections": [{"type": "weather"}],
              "conditions": [{"type": "rain_above", "value": 50}]})
    weather.rain = 30
    clock.t = ts(2026, 11, 20, 7, 0) + 10
    await sch.tick()
    j = jobs(svc)[0]
    assert j["state"] == "missed" and j["error"].startswith("Skipped") and "30%" in j["error"]
    weather.rain = 90
    clock.t = ts(2026, 11, 21, 7, 0) + 10
    await sch.tick()
    assert jobs(svc)[0]["state"] == "queued"


async def test_condition_with_unavailable_data_prints_anyway(env):
    svc, sch, clock, weather, _ = env
    weather.fail = True
    sch.save({"name": "Cold", "time": "07:00", "sections": [{"type": "weather"}],
              "conditions": [{"type": "temp_below", "value": 0}]})
    clock.t = ts(2026, 11, 20, 7, 0) + 10
    await sch.tick()
    j = svc.queue.get(jobs(svc)[0]["id"], with_blobs=True)
    assert j["state"] == "queued"
    assert any("Weather unavailable" in b.get("text", "") for b in j["document"]["blocks"])


async def test_weather_cache_used_when_down(env):
    svc, sch, clock, weather, _ = env
    src = svc.extras["sources"]
    f, stale = await src.weather()
    assert f and stale is None
    weather.fail = True
    import time as _t
    src._weather_cache.fetched_at = _t.time() - 600
    f2, stale2 = await src.weather()
    assert f2 is not None and stale2 == 10
    src._weather_cache.fetched_at = _t.time() - 4 * 3600
    f3, _ = await src.weather()
    assert f3 is None


async def test_holiday_mode_and_daily_limit(env):
    svc, sch, clock, *_ = env
    svc.app_settings.patch({"schedules": {"holiday_mode": True}})
    sch.save({"name": "A", "time": "07:00", "sections": [{"type": "fortune"}]})
    clock.t = ts(2026, 11, 20, 7, 0) + 10
    await sch.tick()
    assert jobs(svc) == []
    svc.app_settings.patch({"schedules": {"holiday_mode": False, "daily_limit": 1}})
    sch.save({"name": "B", "time": "08:00", "sections": [{"type": "fortune"}]})
    sch.save({"name": "C", "time": "09:00", "sections": [{"type": "fortune"}]})
    clock.t = ts(2026, 11, 20, 8, 0) + 10
    await sch.tick()
    clock.t = ts(2026, 11, 20, 9, 0) + 10
    await sch.tick()
    q = {j["title"]: j["state"] for j in jobs(svc)}
    assert q == {"B": "queued", "C": "missed"}


async def test_dst_keeps_wall_clock(env):
    svc, sch, clock, *_ = env
    clock.t = ts(2026, 3, 28, 12, 0)  # day before clocks go forward in the UK
    sch.save({"name": "A", "time": "07:00", "sections": [{"type": "fortune"}]})
    clock.t = ts(2026, 3, 29, 7, 0) + 10
    await sch.tick()
    j = jobs(svc)[0]
    assert j["state"] == "queued" and "07:00:00+01:00" in j["meta"]["due"]


async def test_days_of_week(env):
    svc, sch, clock, *_ = env
    clock.t = ts(2026, 11, 21, 6, 0)  # Saturday morning
    sch.save({"name": "Weekdays", "time": "07:00", "days": [0, 1, 2, 3, 4], "sections": [{"type": "fortune"}]})
    clock.t = ts(2026, 11, 21, 7, 0) + 10  # Saturday
    assert await sch.tick() == 0
    clock.t = ts(2026, 11, 23, 7, 0) + 10  # Monday
    assert await sch.tick() == 1


async def test_routine_doc_sections(env):
    svc, sch, *_ = env
    doc = await svc.extras["sources"].routine_doc([
        {"type": "date"}, {"type": "weather"}, {"type": "countdown", "date": "2026-12-25", "label": "Christmas"},
        {"type": "quote", "text": "Be kind"}, {"type": "agenda"}, {"type": "tasks"}, {"type": "divider"}])
    texts = " ".join(b.get("text", "") + b.get("left", "") for b in doc["blocks"])
    assert "Christmas" in texts and "Be kind" in texts and "Now 4°C" in texts
    assert "Google Tasks isn't connected." in texts
    img = svc.renderer.render(doc).image
    assert img.width == 384


ICS = b"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//test//EN
BEGIN:VEVENT
UID:1
DTSTART:20261120T090000Z
DTEND:20261120T100000Z
SUMMARY:Dentist
LOCATION:High St
END:VEVENT
BEGIN:VEVENT
UID:2
DTSTART;VALUE=DATE:20261120
DTEND;VALUE=DATE:20261121
SUMMARY:Bin day
END:VEVENT
BEGIN:VEVENT
UID:3
DTSTART:20261113T180000Z
DTEND:20261113T190000Z
RRULE:FREQ=WEEKLY
SUMMARY:Football
END:VEVENT
BEGIN:VEVENT
UID:4
DTSTART:20261121T090000Z
SUMMARY:Tomorrow thing
END:VEVENT
END:VCALENDAR
"""


def test_ical_parsing_with_recurrence():
    evs = parse_events(ICS, date(2026, 11, 20), LDN, "Home")
    assert [e.title for e in evs] == ["Bin day", "Dentist", "Football"]
    assert evs[0].all_day and evs[1].label() == "09:00" and evs[2].label() == "18:00"


async def test_calendar_via_http_and_failure_line(env):
    svc, *_ = env

    def handler(req):
        if "good" in str(req.url):
            return httpx.Response(200, content=ICS)
        return httpx.Response(404)

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    src = Sources(svc, weather=FakeWeather(), http=http)
    svc.app_settings.patch({"calendars": [{"id": "a", "name": "Home", "url": "https://x/good.ics"},
                                          {"id": "b", "name": "Work", "url": "https://x/bad.ics"}]})
    evs, errs = await src.events(date(2026, 11, 20))
    assert len(evs) == 3 and errs == ["Calendar “Work” unavailable"]


async def test_google_tasks_refresh_and_list(tmp_path):
    calls = []

    def handler(req):
        calls.append(str(req.url))
        if req.url.path == "/token":
            body = req.content.decode()
            if "refresh_token=bad" in body:
                return httpx.Response(400, json={"error": "invalid_grant"})
            return httpx.Response(200, json={"access_token": "AT", "expires_in": 3600})
        assert req.headers["authorization"] == "Bearer AT"
        if req.url.path.endswith("/users/@me/lists"):
            return httpx.Response(200, json={"items": [{"id": "L1", "title": "My Tasks"}]})
        return httpx.Response(200, json={"items": [{"title": "Later"}, {"title": "Soon", "due": "2026-11-21T00:00:00Z"}]})

    gt = GoogleTasks(tmp_path / "tok.json", httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    with pytest.raises(TasksError):
        gt.save_token(b'{"client_id": "x"}')
    gt.save_token(json.dumps({"client_id": "c", "client_secret": "s", "refresh_token": "r"}).encode())
    assert [t["title"] for t in await gt.tasks()] == ["Soon", "Later"]
    gt.save_token(json.dumps({"client_id": "c", "client_secret": "s", "refresh_token": "bad"}).encode())
    with pytest.raises(TasksError) as e:
        await gt.lists()
    assert e.value.reauth


async def test_open_meteo_parsing():
    def handler(req):
        if "geocoding" in str(req.url):
            return httpx.Response(200, json={"results": [{"name": "Leeds", "admin1": "England", "country_code": "GB",
                                                          "latitude": 53.8, "longitude": -1.5}]})
        return httpx.Response(200, json={
            "current": {"temperature_2m": 6.2, "weather_code": 61},
            "daily": {"temperature_2m_max": [9.1], "temperature_2m_min": [2.4],
                      "precipitation_probability_max": [70], "weather_code": [63]},
            "hourly": {"time": ["2026-11-20T09:00", "2026-11-20T10:00"], "temperature_2m": [5, 6],
                       "precipitation_probability": [40, 50]}})

    om = OpenMeteo(httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    g = await om.geocode("leeds")
    assert g["place"] == "Leeds, England, GB"
    f = await om.forecast(g["lat"], g["lon"], g["place"])
    assert f.now_text == "Light rain" and f.rain_chance == 70 and f.hourly == [("09:00", 5, 40)]
