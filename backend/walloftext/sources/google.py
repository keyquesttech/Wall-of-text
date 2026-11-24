"""Google Calendar and Google Tasks through Google's APIs, with one sign-in for both.

Sign-in happens in the Wall of Text app, from any phone or computer:
1. The user creates a free Google Cloud "Desktop app" OAuth client once and pastes its
   client ID and secret into Settings › Connections › Google (docs/GOOGLE_SETUP.md).
2. "Sign in with Google" opens Google's consent page. Google then sends the browser to
   http://127.0.0.1:53682/?code=… . Nothing listens there, so the page fails to load,
   but its address holds the one-time code. The user copies that address back into the app.
3. The Pi swaps the code (with the PKCE verifier it made in step 2) for a refresh token.

Why not a normal redirect to the Pi: Google only allows http redirects to loopback
addresses, never to walloftext.local, and its device flow doesn't allow the Calendar or
Tasks scopes (BUILD_PLAN 9.1).

Secrets (client secret, refresh token) live in `<data_dir>/secrets.json` under "google"
(mode 0600, never in backups or logs). Access tokens stay in memory.
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import re
import secrets as pysecrets
import time
from datetime import date, datetime, timedelta
from datetime import time as dtime
from typing import TYPE_CHECKING, Any
from urllib.parse import parse_qs, quote, urlencode, urlparse
from zoneinfo import ZoneInfo

import httpx

from .calendar import _CONF, Event, clean_description

if TYPE_CHECKING:
    from ..remote.secrets import Secrets

log = logging.getLogger(__name__)

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
CAL_API = "https://www.googleapis.com/calendar/v3"
TASKS_API = "https://tasks.googleapis.com/tasks/v1"
REDIRECT_URI = "http://127.0.0.1:53682/"
SCOPES = ["openid", "email",
          "https://www.googleapis.com/auth/calendar.readonly",
          "https://www.googleapis.com/auth/tasks.readonly"]
CHANNEL = "google"
PENDING_S = 1800  # a sign-in started in the app is good for 30 minutes


class GoogleError(Exception):
    def __init__(self, message: str, reauth: bool = False):
        super().__init__(message)
        self.reauth = reauth


def _email_from_id_token(tok: str | None) -> str | None:
    """The id_token comes straight from Google's token endpoint over TLS, so its payload is read
    as is; it is only used to show which account is connected."""
    try:
        payload = tok.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return json.loads(base64.urlsafe_b64decode(payload)).get("email")
    except Exception:
        return None


def code_from_paste(text: str) -> tuple[str, str | None]:
    """The address Google sent the browser to (or just the code) → (code, state)."""
    t = (text or "").strip()
    if not t:
        raise GoogleError("Paste the address from the page Google opened.")
    if "code=" in t:
        q = parse_qs(urlparse(t if "://" in t else "http://x/?" + t.split("?", 1)[-1]).query)
        if q.get("error"):
            raise GoogleError("Google says access wasn't allowed. Try again and tap Allow.")
        code = (q.get("code") or [""])[0]
        if not code:
            raise GoogleError("That address has no sign-in code in it.")
        return code, (q.get("state") or [None])[0]
    if "error=" in t:
        raise GoogleError("Google says access wasn't allowed. Try again and tap Allow.")
    if re.fullmatch(r"[\w\-/.]{10,}", t):
        return t, None
    raise GoogleError("That doesn't look like the address from Google. Copy the whole address bar.")


class GoogleAuth:
    def __init__(self, secrets: "Secrets", client: httpx.AsyncClient | None = None):
        self.secrets = secrets
        self.client = client
        self._access: str | None = None
        self._expires = 0.0
        self._pending: dict[str, tuple[str, float]] = {}  # state → (PKCE verifier, started at)

    # ----------------------------------------------------------- state --
    def _cfg(self) -> dict:
        return self.secrets.get(CHANNEL)

    def has_client(self) -> bool:
        return self.secrets.has(CHANNEL, "client_id", "client_secret")

    def connected(self) -> bool:
        return self.secrets.has(CHANNEL, "client_id", "client_secret", "refresh_token")

    def status(self) -> dict:
        c = self._cfg()
        cid = c.get("client_id", "")
        return {"client": self.has_client(), "connected": self.connected(), "email": c.get("email"),
                "client_id_hint": (cid[:8] + "…" + cid[-30:]) if len(cid) > 40 else cid,
                "redirect_uri": REDIRECT_URI}

    def set_client(self, client_id: str, client_secret: str) -> None:
        cid, sec = client_id.strip(), client_secret.strip()
        if not cid.endswith(".apps.googleusercontent.com"):
            raise GoogleError("The client ID ends with .apps.googleusercontent.com. Copy it from Google Cloud › Credentials.")
        if len(sec) < 10 or " " in sec:
            raise GoogleError("That client secret doesn't look right. Copy it from the same Credentials page.")
        changed = cid != self._cfg().get("client_id")
        self.secrets.set(CHANNEL, {"client_id": cid, "client_secret": sec,
                                   **({"refresh_token": None, "email": None} if changed else {})})
        self._access = None

    def forget(self, client_too: bool = False) -> None:
        if client_too:
            self.secrets.clear(CHANNEL)
        else:
            self.secrets.set(CHANNEL, {"refresh_token": None, "email": None})
        self._access = None
        self._pending.clear()

    # --------------------------------------------------------- sign-in --
    def start(self) -> str:
        if not self.has_client():
            raise GoogleError("Add the client ID and secret first.")
        now = time.time()
        self._pending = {s: v for s, v in self._pending.items() if now - v[1] < PENDING_S}
        verifier = pysecrets.token_urlsafe(64)
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        state = pysecrets.token_urlsafe(16)
        self._pending[state] = (verifier, now)
        return AUTH_URL + "?" + urlencode({
            "client_id": self._cfg()["client_id"], "redirect_uri": REDIRECT_URI, "response_type": "code",
            "scope": " ".join(SCOPES), "access_type": "offline", "prompt": "consent",
            "code_challenge": challenge, "code_challenge_method": "S256", "state": state})

    async def finish(self, pasted: str) -> dict:
        code, state = code_from_paste(pasted)
        now = time.time()
        live = {s: v for s, v in self._pending.items() if now - v[1] < PENDING_S}
        if state:
            if state not in live:
                raise GoogleError("That sign-in has expired or came from another tab. Tap Sign in with Google again.")
            verifier = live[state][0]
        elif len(live) == 1:
            verifier = next(iter(live.values()))[0]
        else:
            raise GoogleError("Tap Sign in with Google first, then paste the address it ends on.")
        cfg = self._cfg()
        async with self._c() as c:
            r = await c.post(TOKEN_URL, data={
                "client_id": cfg["client_id"], "client_secret": cfg["client_secret"], "code": code,
                "code_verifier": verifier, "redirect_uri": REDIRECT_URI, "grant_type": "authorization_code"})
        if r.status_code >= 400:
            err = (r.json() if r.headers.get("content-type", "").startswith("application/json") else {}).get("error")
            if err == "invalid_client":
                raise GoogleError("Google didn't accept the client ID or secret. Check them in Google Cloud.")
            raise GoogleError("Google didn't accept that code. Codes work once and only for a few minutes: sign in again.")
        d = r.json()
        if not d.get("refresh_token"):
            raise GoogleError("Google didn't send a long-lived sign-in. Remove Wall of Text at "
                              "myaccount.google.com/permissions and try again.")
        granted = set((d.get("scope") or "").split())
        missing = [s.rsplit("/", 1)[-1] for s in SCOPES[2:] if s not in granted]
        if state:
            self._pending.pop(state, None)
        else:
            self._pending.clear()
        email = _email_from_id_token(d.get("id_token"))
        self.secrets.set(CHANNEL, {"refresh_token": d["refresh_token"], "email": email})
        self._access, self._expires = d.get("access_token"), time.time() + int(d.get("expires_in", 3600))
        return {"email": email, "missing": missing}

    # --------------------------------------------------------- tokens --
    def _c(self) -> httpx.AsyncClient:
        if self.client is not None:
            return _Borrowed(self.client)
        return httpx.AsyncClient(timeout=15)

    async def _token(self, c: httpx.AsyncClient) -> str:
        if self._access and time.time() < self._expires - 60:
            return self._access
        cfg = self._cfg()
        if not cfg.get("refresh_token"):
            raise GoogleError("Google isn't connected.", reauth=bool(cfg.get("client_id")))
        r = await c.post(TOKEN_URL, data={"client_id": cfg["client_id"], "client_secret": cfg["client_secret"],
                                          "refresh_token": cfg["refresh_token"], "grant_type": "refresh_token"})
        if r.status_code in (400, 401):
            raise GoogleError("Google stopped accepting the sign-in. Sign in again in Settings › Connections › Google.",
                              reauth=True)
        r.raise_for_status()
        d = r.json()
        self._access = d["access_token"]
        self._expires = time.time() + int(d.get("expires_in", 3600))
        return self._access

    async def get(self, url: str, params: dict | None = None) -> dict:
        async with self._c() as c:
            tok = await self._token(c)
            r = await c.get(url, params=params, headers={"Authorization": f"Bearer {tok}"})
            if r.status_code == 401:  # access token revoked early: refresh once
                self._access = None
                tok = await self._token(c)
                r = await c.get(url, params=params, headers={"Authorization": f"Bearer {tok}"})
            if r.status_code == 403:
                msg = ""
                try:
                    msg = r.json().get("error", {}).get("message", "")
                except ValueError:
                    pass
                if "has not been used" in msg or "is disabled" in msg:
                    api = "Google Tasks API" if "tasks" in url else "Google Calendar API"
                    raise GoogleError(f"Turn on the {api} in your Google Cloud project, then wait a minute.")
                raise GoogleError("Google refused access. Sign in again and allow Calendar and Tasks.", reauth=True)
            if r.status_code == 404:
                raise GoogleError("Not found at Google (it may have been deleted).")
            r.raise_for_status()
            return r.json()

    async def revoke(self) -> None:
        tok = self._cfg().get("refresh_token")
        if not tok:
            return
        try:
            async with self._c() as c:
                await c.post(REVOKE_URL, data={"token": tok})
        except Exception:
            pass  # best effort; the token is forgotten here either way


class _Borrowed:
    """`async with` around a shared client without closing it."""

    def __init__(self, c: httpx.AsyncClient):
        self.c = c

    async def __aenter__(self) -> httpx.AsyncClient:
        return self.c

    async def __aexit__(self, *exc) -> None:
        return None


# -------------------------------------------------------------- Tasks --
class GoogleTasks:
    def __init__(self, auth: GoogleAuth):
        self.auth = auth

    async def lists(self) -> list[dict]:
        d = await self.auth.get(f"{TASKS_API}/users/@me/lists", {"maxResults": 100})
        return [{"id": x["id"], "title": x.get("title", "")} for x in d.get("items", [])]

    async def tasks(self, list_ids: list[str] | None = None, limit: int = 100) -> list[dict]:
        """Open tasks of the chosen lists (the first list when none are chosen): id, title, notes,
        due (date only), parent, position, list name and `order` (list order, then position).
        Sorted by due date for simple callers."""
        names = {x["id"]: x["title"] for x in await self.lists()}
        list_ids = [x for x in (list_ids or []) if x in names] or list(names)[:1]
        out: list[dict] = []
        for li, lid in enumerate(list_ids):
            items: list[dict] = []
            token = None
            for _ in range(5):  # at most 500 tasks per list
                params: dict[str, Any] = {"showCompleted": "false", "showHidden": "false", "maxResults": 100}
                if token:
                    params["pageToken"] = token
                d = await self.auth.get(f"{TASKS_API}/lists/{quote(lid, safe='')}/tasks", params)
                items += [t for t in d.get("items", []) if t.get("title", "").strip()]
                token = d.get("nextPageToken")
                if not token:
                    break
            items.sort(key=lambda t: (t.get("parent") is not None, t.get("position", "")))
            for t in items:
                out.append({"id": t.get("id") or f"{lid}:{len(out)}", "title": t["title"].strip(),
                            "notes": (t.get("notes") or "").strip(), "due": (t.get("due") or "")[:10] or None,
                            "parent": t.get("parent"), "position": t.get("position", ""),
                            "list": names.get(lid, ""), "_li": li})
        out.sort(key=lambda t: (t["_li"], t["position"]))
        for i, t in enumerate(out):
            t["order"] = i + 1
            t.pop("_li")
        out.sort(key=lambda t: (t["due"] is None, t["due"] or ""))
        return out[:limit]


# ----------------------------------------------------------- Calendar --
def _when(v: dict, tz: ZoneInfo) -> tuple[datetime | date | None, bool]:
    if not v:
        return None, False
    if v.get("dateTime"):
        return datetime.fromisoformat(v["dateTime"].replace("Z", "+00:00")).astimezone(tz), False
    if v.get("date"):
        return date.fromisoformat(v["date"]), True
    return None, False


def event_from_api(e: dict, calendar: str, tz: ZoneInfo) -> Event | None:
    """One Calendar API event → Event, or None when it shouldn't print (cancelled, declined)."""
    if e.get("status") == "cancelled":
        return None
    me = next((a for a in e.get("attendees") or [] if a.get("self")), None)
    if me and me.get("responseStatus") == "declined":
        return None
    start, all_day = _when(e.get("start") or {}, tz)
    if start is None:
        return None
    end, _ = _when(e.get("end") or {}, tz)
    desc = e.get("description") or ""
    loc = (e.get("location") or "").strip() or None
    conf = e.get("hangoutLink")
    if not conf:
        for ep in (e.get("conferenceData") or {}).get("entryPoints") or []:
            if ep.get("entryPointType") == "video" and ep.get("uri"):
                conf = ep["uri"]
                break
    if not conf:
        m = _CONF.search(desc) or _CONF.search(loc or "")
        conf = m.group(0) if m else None
    if loc and _CONF.fullmatch(loc):
        loc = None  # a bare meeting link is not a place
    people = []
    for a in e.get("attendees") or []:
        if a.get("self") or a.get("resource"):
            continue
        name = a.get("displayName") or (a.get("email") or "").split("@")[0]
        if name:
            people.append(name)
    return Event((e.get("summary") or "").strip() or "(no title)", start, end, all_day, calendar, loc,
                 e.get("id", ""), people, clean_description(desc), conf)


class GoogleCalendar:
    def __init__(self, auth: GoogleAuth):
        self.auth = auth

    async def calendars(self) -> list[dict]:
        out, token = [], None
        for _ in range(5):
            params: dict[str, Any] = {"maxResults": 250, "minAccessRole": "reader"}
            if token:
                params["pageToken"] = token
            d = await self.auth.get(f"{CAL_API}/users/me/calendarList", params)
            for c in d.get("items", []):
                if c.get("deleted"):
                    continue
                out.append({"id": c["id"], "name": c.get("summaryOverride") or c.get("summary") or c["id"],
                            "primary": bool(c.get("primary")), "color": c.get("backgroundColor")})
            token = d.get("nextPageToken")
            if not token:
                break
        out.sort(key=lambda c: (not c["primary"], c["name"].lower()))
        return out

    async def events(self, cal_id: str, name: str, day: date, tz: ZoneInfo, days: int = 1) -> list[Event]:
        start = datetime.combine(day, dtime.min, tz)
        end = start + timedelta(days=days)
        out: list[Event] = []
        token = None
        for _ in range(4):
            params: dict[str, Any] = {"timeMin": start.isoformat(), "timeMax": end.isoformat(),
                                      "singleEvents": "true", "orderBy": "startTime", "maxResults": 250,
                                      "timeZone": str(tz)}
            if token:
                params["pageToken"] = token
            d = await self.auth.get(f"{CAL_API}/calendars/{quote(cal_id, safe='')}/events", params)
            for e in d.get("items", []):
                ev = event_from_api(e, name, tz)
                if ev is not None:
                    out.append(ev)
            token = d.get("nextPageToken")
            if not token:
                break
        return out
