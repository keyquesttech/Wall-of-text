"""Google sign-in (pasted-address flow), Calendar API and Tasks API, all against a fake Google."""
import base64
import json
import time
from datetime import date, datetime
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

import httpx
import pytest
from fastapi.testclient import TestClient

from walloftext.app import create_app
from walloftext.remote.secrets import Secrets
from walloftext.services import build
from walloftext.sources.google import (REDIRECT_URI, GoogleAuth, GoogleCalendar, GoogleError, GoogleTasks,
                                       code_from_paste, event_from_api)

LDN = ZoneInfo("Europe/London")
CID = "123-abc.apps.googleusercontent.com"


def id_token(email):
    body = base64.urlsafe_b64encode(json.dumps({"email": email}).encode()).decode().rstrip("=")
    return f"x.{body}.y"


class FakeGoogle:
    """Token endpoint, Calendar and Tasks, enough for the app's calls."""

    def __init__(self):
        self.calls: list[httpx.Request] = []
        self.refresh_ok = True
        self.verifier = None
        self.calendar_fail = set()

    def __call__(self, req: httpx.Request) -> httpx.Response:
        self.calls.append(req)
        u = req.url
        if u.host == "oauth2.googleapis.com" and u.path == "/token":
            f = parse_qs(req.content.decode())
            if f["grant_type"] == ["authorization_code"]:
                if f["code"] != ["good-code"]:
                    return httpx.Response(400, json={"error": "invalid_grant"})
                assert f["redirect_uri"] == [REDIRECT_URI] and f["client_secret"] == ["s3cret-value"]
                self.verifier = f["code_verifier"][0]
                return httpx.Response(200, json={
                    "access_token": "AT1", "expires_in": 3600, "refresh_token": "RT",
                    "scope": "openid https://www.googleapis.com/auth/userinfo.email "
                             "https://www.googleapis.com/auth/calendar.readonly https://www.googleapis.com/auth/tasks.readonly",
                    "id_token": id_token("flat@example.com")})
            if not self.refresh_ok:
                return httpx.Response(400, json={"error": "invalid_grant"})
            return httpx.Response(200, json={"access_token": "AT2", "expires_in": 3600})
        if u.path == "/revoke":
            return httpx.Response(200)
        assert req.headers["authorization"].startswith("Bearer AT")
        if u.path == "/calendar/v3/users/me/calendarList":
            return httpx.Response(200, json={"items": [
                {"id": "work@group.calendar.google.com", "summary": "Work"},
                {"id": "flat@example.com", "summary": "flat@example.com", "summaryOverride": "Me", "primary": True}]})
        if u.path.startswith("/calendar/v3/calendars/"):
            cal = u.path.split("/")[4]
            if cal in self.calendar_fail:
                return httpx.Response(500)
            q = parse_qs(u.query.decode())
            assert q["singleEvents"] == ["true"] and q["orderBy"] == ["startTime"]
            return httpx.Response(200, json={"items": [
                {"id": "1", "summary": "Dentist", "location": "High St",
                 "start": {"dateTime": "2026-11-20T09:00:00Z"}, "end": {"dateTime": "2026-11-20T10:00:00Z"},
                 "attendees": [{"email": "flat@example.com", "self": True, "responseStatus": "accepted"},
                               {"email": "sam@x.com", "displayName": "Sam"},
                               {"email": "room@resource.calendar.google.com", "resource": True}],
                 "hangoutLink": "https://meet.google.com/abc-defg-hij"},
                {"id": "2", "summary": "Bin day", "start": {"date": "2026-11-20"}, "end": {"date": "2026-11-21"}},
                {"id": "3", "summary": "Cancelled", "status": "cancelled",
                 "start": {"dateTime": "2026-11-20T11:00:00Z"}},
                {"id": "4", "summary": "Declined", "start": {"dateTime": "2026-11-20T12:00:00Z"},
                 "attendees": [{"email": "flat@example.com", "self": True, "responseStatus": "declined"}]},
            ]})
        if u.path == "/tasks/v1/users/@me/lists":
            return httpx.Response(200, json={"items": [{"id": "L1", "title": "My Tasks"}, {"id": "L2", "title": "Errands"}]})
        if u.path.startswith("/tasks/v1/lists/"):
            lid = u.path.split("/")[4]
            items = {"L1": [{"id": "a", "title": "Later", "position": "2"},
                            {"id": "b", "title": "Soon", "due": "2026-11-21T00:00:00.000Z", "position": "1"}],
                     "L2": [{"id": "c", "title": "Buy bin bags", "position": "1"}]}[lid]
            return httpx.Response(200, json={"items": items})
        return httpx.Response(404)


@pytest.fixture
def g(tmp_path):
    fake = FakeGoogle()
    auth = GoogleAuth(Secrets(tmp_path / "secrets.json"), httpx.AsyncClient(transport=httpx.MockTransport(fake)))
    return auth, fake


async def connect(auth):
    auth.set_client(CID, "s3cret-value")
    url = auth.start()
    state = parse_qs(urlparse(url).query)["state"][0]
    return await auth.finish(f"{REDIRECT_URI}?state={state}&code=good-code&scope=x")


def test_code_from_paste():
    assert code_from_paste("http://127.0.0.1:53682/?state=S&code=4/0Ab-c&scope=a") == ("4/0Ab-c", "S")
    assert code_from_paste("  4/0AbcdefghijKLM  ") == ("4/0AbcdefghijKLM", None)
    with pytest.raises(GoogleError, match="wasn't allowed"):
        code_from_paste("http://127.0.0.1:53682/?error=access_denied&state=S")
    with pytest.raises(GoogleError):
        code_from_paste("hello there")


def test_client_id_is_checked(g):
    auth, _ = g
    with pytest.raises(GoogleError, match="apps.googleusercontent.com"):
        auth.set_client("nope", "s3cret-value")
    with pytest.raises(GoogleError, match="client ID and secret first"):
        auth.start()


async def test_sign_in_flow_stores_refresh_token_not_in_settings(g, tmp_path):
    auth, fake = g
    res = await connect(auth)
    assert res == {"email": "flat@example.com", "missing": []}
    assert auth.connected() and auth.status()["email"] == "flat@example.com"
    url = auth.start()
    q = parse_qs(urlparse(url).query)
    assert q["access_type"] == ["offline"] and q["code_challenge_method"] == ["S256"]
    assert "calendar.readonly" in q["scope"][0] and "tasks.readonly" in q["scope"][0]
    assert fake.verifier and len(fake.verifier) >= 43
    stored = json.loads((tmp_path / "secrets.json").read_text())
    assert stored["google"]["refresh_token"] == "RT"
    assert oct((tmp_path / "secrets.json").stat().st_mode)[-3:] == "600"


async def test_wrong_state_and_bad_code(g):
    auth, _ = g
    auth.set_client(CID, "s3cret-value")
    auth.start()
    with pytest.raises(GoogleError, match="expired"):
        await auth.finish(f"{REDIRECT_URI}?state=other&code=good-code")
    with pytest.raises(GoogleError, match="didn't accept that code"):
        await auth.finish("4/bad-code-123456")
    assert not auth.connected()


async def test_calendar_events_from_api(g):
    auth, _ = g
    await connect(auth)
    cal = GoogleCalendar(auth)
    cals = await cal.calendars()
    assert [c["name"] for c in cals] == ["Me", "Work"] and cals[0]["primary"]
    evs = await cal.events("flat@example.com", "Me", date(2026, 11, 20), LDN)
    assert [e.title for e in evs] == ["Dentist", "Bin day"]  # cancelled and declined left out
    d = evs[0]
    assert d.start == datetime(2026, 11, 20, 9, 0, tzinfo=LDN) and d.label() == "09:00"
    assert d.attendees == ["Sam"] and d.conference == "https://meet.google.com/abc-defg-hij" and d.location == "High St"
    assert evs[1].all_day and evs[1].start == date(2026, 11, 20)


def test_meeting_link_as_location_is_not_a_place():
    e = event_from_api({"summary": "Call", "location": "https://meet.google.com/abc-defg-hij",
                        "start": {"dateTime": "2026-11-20T09:00:00+00:00"}}, "Me", LDN)
    assert e.location is None and e.conference == "https://meet.google.com/abc-defg-hij"


async def test_tasks_from_api(g):
    auth, _ = g
    await connect(auth)
    t = GoogleTasks(auth)
    assert [x["title"] for x in await t.lists()] == ["My Tasks", "Errands"]
    assert [x["title"] for x in await t.tasks()] == ["Soon", "Later"]  # first list by default
    both = await t.tasks(["L1", "L2"])
    assert {x["list"] for x in both} == {"My Tasks", "Errands"} and both[0]["due"] == "2026-11-21"
    assert await t.tasks(["gone"]) and True  # an unknown saved list falls back to the first


async def test_refresh_rejected_asks_to_sign_in_again(g):
    auth, fake = g
    await connect(auth)
    auth._access = None
    fake.refresh_ok = False
    with pytest.raises(GoogleError) as e:
        await GoogleTasks(auth).lists()
    assert e.value.reauth


async def test_hub_events_tasks_and_failure_line(settings, fake_nm, g):
    auth, fake = g
    svc = build(settings, nm=fake_nm)
    src = svc.extras["sources"]
    src.google = auth
    evs, errs = await src.events(date(2026, 11, 20))
    assert evs == [] and errs == ["Google isn't connected"]
    slip = await src.agenda_slip()
    assert slip["template"] == "unavailable" and "Google isn't connected" in json.dumps(slip)
    await connect(auth)
    evs, errs = await src.events(date(2026, 11, 20))  # nothing chosen → the main calendar
    assert [e.title for e in evs] == ["Bin day", "Dentist"] and errs == []
    svc.app_settings.patch({"google": {"calendars": [{"id": "flat@example.com", "name": "Me"},
                                                     {"id": "work@group.calendar.google.com", "name": "Work"}]}})
    fake.calendar_fail.add("work@group.calendar.google.com")
    evs, errs = await src.events(date(2026, 11, 20))
    assert len(evs) == 2 and errs == ["Calendar “Work” unavailable"]
    svc.app_settings.patch({"google": {"task_lists": ["L2"]}})
    items, err = await src.tasks()
    assert err is None and [x["title"] for x in items] == ["Buy bin bags"]
    assert src.tasks_slip((items, err))["template"] == "todo"


def test_old_ical_links_are_dropped_from_settings(settings, fake_nm):
    svc = build(settings, nm=fake_nm)
    svc.store.set("app_settings", json.dumps({"calendars": [{"id": "a", "name": "Home",
                                                             "url": "https://calendar.google.com/calendar/ical/x/private-abc/basic.ics"}],
                                              "tasks": {"lists": ["L1"]}, "weather": {"place": "Leeds"}}))
    from walloftext.sources.hub import Sources
    Sources(svc)
    raw = svc.store.get("app_settings")
    assert "private-abc" not in raw and "tasks" not in json.loads(raw) and json.loads(raw)["weather"]["place"] == "Leeds"


@pytest.fixture
def client(settings, fake_nm):
    svc = build(settings, nm=fake_nm)
    with TestClient(create_app(services=svc), base_url="http://walloftext.local") as c:
        c.post("/api/auth/login", json={"password": "root"})
        c.svc = svc
        yield c


def test_google_api_endpoints(client, tmp_path):
    fake = FakeGoogle()
    src = client.svc.extras["sources"]
    src.google = GoogleAuth(client.svc.extras["secrets"], httpx.AsyncClient(transport=httpx.MockTransport(fake)))
    st = client.get("/api/google").json()
    assert st["client"] is False and st["connected"] is False and st["redirect_uri"] == REDIRECT_URI
    assert client.post("/api/google/start").status_code == 422
    assert client.put("/api/google/client", json={"client_id": "nope-nope-nope", "client_secret": "s3cret-value"}).status_code == 422
    assert client.put("/api/google/client", json={"client_id": CID, "client_secret": "s3cret-value"}).json() == {"ok": True}
    assert client.get("/api/google/calendars").status_code == 409
    url = client.post("/api/google/start").json()["url"]
    state = parse_qs(urlparse(url).query)["state"][0]
    r = client.post("/api/google/finish", json={"response": f"{REDIRECT_URI}?state={state}&code=good-code"})
    assert r.json()["ok"] and r.json()["email"] == "flat@example.com"
    st = client.get("/api/google").json()
    assert st["connected"] and "s3cret" not in json.dumps(st)
    assert [c["name"] for c in client.get("/api/google/calendars").json()["items"]] == ["Me", "Work"]
    assert [x["title"] for x in client.get("/api/google/tasklists").json()["items"]] == ["My Tasks", "Errands"]
    # the client secret and refresh token never reach settings or backups
    assert "RT" not in json.dumps(client.get("/api/settings").json())
    assert client.delete("/api/google").json() == {"ok": True}
    st = client.get("/api/google").json()
    assert st["client"] and not st["connected"]
    assert any(c.url.path == "/revoke" for c in fake.calls)
