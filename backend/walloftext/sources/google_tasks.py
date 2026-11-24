"""Google Tasks with a token made once on the PC by tools/google_auth.py (BUILD_PLAN 9.1).

The token file holds client_id, client_secret and refresh_token. Access tokens
are refreshed here as needed; nothing is written back except the cached
access token in memory.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import httpx

TOKEN_URL = "https://oauth2.googleapis.com/token"
API = "https://tasks.googleapis.com/tasks/v1"


class TasksError(Exception):
    def __init__(self, message: str, reauth: bool = False):
        super().__init__(message)
        self.reauth = reauth


class GoogleTasks:
    def __init__(self, token_path: Path, client: httpx.AsyncClient | None = None):
        self.token_path = Path(token_path)
        self.client = client
        self._access: str | None = None
        self._expires = 0.0

    def configured(self) -> bool:
        return self.token_path.exists()

    def save_token(self, raw: bytes) -> dict:
        try:
            data = json.loads(raw)
        except ValueError:
            raise TasksError("That file isn't a token file from google_auth.py.")
        need = {"client_id", "client_secret", "refresh_token"}
        if not need <= set(data):
            raise TasksError("The token file is missing client_id, client_secret or refresh_token.")
        self.token_path.parent.mkdir(parents=True, exist_ok=True)
        self.token_path.write_text(json.dumps({k: data[k] for k in need | {"scopes"} if k in data}))
        self.token_path.chmod(0o600)
        self._access = None
        return {"ok": True}

    def forget(self) -> None:
        self.token_path.unlink(missing_ok=True)
        self._access = None

    def _c(self) -> httpx.AsyncClient:
        return self.client or httpx.AsyncClient(timeout=15)

    async def _token(self, c: httpx.AsyncClient) -> str:
        if self._access and time.time() < self._expires - 60:
            return self._access
        tok = json.loads(self.token_path.read_text())
        r = await c.post(TOKEN_URL, data={"client_id": tok["client_id"], "client_secret": tok["client_secret"],
                                          "refresh_token": tok["refresh_token"], "grant_type": "refresh_token"})
        if r.status_code in (400, 401):
            raise TasksError("Google rejected the saved sign-in. Make a new token on the PC.", reauth=True)
        r.raise_for_status()
        d = r.json()
        self._access = d["access_token"]
        self._expires = time.time() + int(d.get("expires_in", 3600))
        return self._access

    async def lists(self) -> list[dict]:
        c = self._c()
        try:
            tok = await self._token(c)
            r = await c.get(f"{API}/users/@me/lists", headers={"Authorization": f"Bearer {tok}"})
            r.raise_for_status()
            return [{"id": x["id"], "title": x["title"]} for x in r.json().get("items", [])]
        finally:
            if c is not self.client:
                await c.aclose()

    async def tasks(self, list_ids: list[str] | None = None, limit: int = 100) -> list[dict]:
        """Open tasks of the chosen lists: id, title, notes, due (date only), parent, position, list name
        and `order` (list order, then position). Sorted by due date for simple callers."""
        c = self._c()
        try:
            tok = await self._token(c)
            hdr = {"Authorization": f"Bearer {tok}"}
            r = await c.get(f"{API}/users/@me/lists", headers=hdr)
            r.raise_for_status()
            names = {x["id"]: x.get("title", "") for x in r.json().get("items", [])}
            if not list_ids:
                list_ids = list(names)[:1]
            out: list[dict] = []
            for li, lid in enumerate(list_ids):
                r = await c.get(f"{API}/lists/{lid}/tasks", headers=hdr,
                                params={"showCompleted": "false", "showHidden": "false", "maxResults": 100})
                r.raise_for_status()
                items = [t for t in r.json().get("items", []) if t.get("title", "").strip()]
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
        finally:
            if c is not self.client:
                await c.aclose()
