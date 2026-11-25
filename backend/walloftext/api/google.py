"""Settings › Google Calendar & Tasks: one sign-in for Google Calendar and Google Tasks
(sources/google.py explains the flow)."""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ..sources.google import GoogleError

router = APIRouter(prefix="/api/google")


def _src(request: Request):
    return request.app.state.svc.extras["sources"]


def _err(exc: GoogleError, status: int = 422) -> JSONResponse:
    return JSONResponse({"error": "google", "message": str(exc), "reauth": exc.reauth}, status_code=status)


@router.get("")
async def status(request: Request):
    src = _src(request)
    st = src.google.status()
    health = {k: v for k, v in src.status().items() if k in ("calendar", "tasks")}
    return {**st, "health": health, "settings": request.app.state.svc.app_settings.get("google")}


class ClientBody(BaseModel):
    client_id: str = Field(min_length=10, max_length=200)
    client_secret: str = Field(min_length=10, max_length=200)


@router.put("/client")
async def set_client(body: ClientBody, request: Request):
    try:
        _src(request).google.set_client(body.client_id, body.client_secret)
    except GoogleError as exc:
        return _err(exc)
    return {"ok": True}


@router.post("/start")
async def start(request: Request):
    try:
        return {"url": _src(request).google.start()}
    except GoogleError as exc:
        return _err(exc)


class FinishBody(BaseModel):
    response: str = Field(min_length=4, max_length=4000)


@router.post("/finish")
async def finish(body: FinishBody, request: Request):
    try:
        res = await _src(request).google.finish(body.response)
    except GoogleError as exc:
        return _err(exc)
    except Exception:
        return JSONResponse({"error": "unreachable", "message": "Can't reach Google right now. Try again."},
                            status_code=502)
    return {"ok": True, **res}


@router.delete("")
async def disconnect(request: Request, forget_client: bool = False):
    g = _src(request).google
    await g.revoke()
    g.forget(client_too=forget_client)
    return {"ok": True}


async def _list(request: Request, fn):
    if not _src(request).google.connected():
        return JSONResponse({"error": "not_connected", "message": "Google isn't connected."}, status_code=409)
    try:
        return {"items": await fn()}
    except GoogleError as exc:
        return _err(exc, 502)
    except Exception:
        return JSONResponse({"error": "unreachable", "message": "Can't reach Google right now."}, status_code=502)


@router.get("/calendars")
async def calendars(request: Request):
    return await _list(request, _src(request).calendar_api.calendars)


@router.get("/tasklists")
async def tasklists(request: Request):
    return await _list(request, _src(request).tasks_api.lists)
