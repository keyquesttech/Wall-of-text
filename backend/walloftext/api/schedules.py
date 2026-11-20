"""/api/schedules, /api/scheduler, /api/sources (BUILD_PLAN 7, 9.1)."""
from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, File, Request, UploadFile
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field, field_validator

from ..scheduler.engine import CONDITIONS, parse_hm
from ..sources.hub import SECTION_TYPES

router = APIRouter(prefix="/api")


class ScheduleBody(BaseModel):
    name: str | None = Field(default=None, max_length=60)
    enabled: bool | None = None
    time: str | None = None
    days: list[int] | None = None
    sections: list[dict[str, Any]] | None = Field(default=None, max_length=20)
    conditions: list[dict[str, Any]] | None = Field(default=None, max_length=5)
    icon: str | None = Field(default=None, max_length=20)

    @field_validator("time")
    @classmethod
    def _time(cls, v):
        if v in (None, ""):
            return None
        parse_hm(v)
        return v

    @field_validator("sections")
    @classmethod
    def _sections(cls, v):
        for s in v or []:
            if s.get("type") not in SECTION_TYPES:
                raise ValueError(f"unknown section {s.get('type')}")
        return v


def _sched(request: Request):
    return request.app.state.svc.extras["scheduler"]


@router.get("/schedules")
async def list_schedules(request: Request):
    return {"items": _sched(request).list(), "status": _sched(request).status(),
            "sections": SECTION_TYPES, "conditions": CONDITIONS}


@router.post("/schedules", status_code=201)
async def create(body: ScheduleBody, request: Request):
    data = body.model_dump(exclude_none=True)
    data.setdefault("time", None)
    return _sched(request).save(data)


@router.get("/schedules/{sid}")
async def get_one(sid: str, request: Request):
    s = _sched(request).get(sid)
    return s or JSONResponse({"error": "not_found"}, status_code=404)


@router.patch("/schedules/{sid}")
async def update(sid: str, body: ScheduleBody, request: Request):
    if not _sched(request).get(sid):
        return JSONResponse({"error": "not_found"}, status_code=404)
    data = body.model_dump(exclude_unset=True)
    return _sched(request).save(data, sid)


@router.delete("/schedules/{sid}")
async def delete(sid: str, request: Request):
    return {"ok": _sched(request).delete(sid)}


@router.post("/schedules/{sid}/run", status_code=201)
async def run_now(sid: str, request: Request):
    return {"message": await _sched(request).run_now(sid)}


@router.post("/schedules/preview")
async def preview(body: ScheduleBody, request: Request):
    svc = request.app.state.svc
    data = {"sections": body.sections or [], "conditions": body.conditions or []}
    doc = await _sched(request).preview_doc(data)
    res = await asyncio.to_thread(svc.renderer.render, doc)
    return Response(await asyncio.to_thread(res.png), media_type="image/png",
                    headers={"X-Wot-Rows": str(res.rows), "X-Wot-Length-Mm": f"{res.rows / 8:.0f}",
                             "X-Wot-Coverage": f"{res.coverage:.3f}", "Cache-Control": "no-store"})


@router.get("/scheduler")
async def status(request: Request):
    return _sched(request).status()


# ----------------------------------------------------------- sources --
class PlaceBody(BaseModel):
    place: str = Field(min_length=2, max_length=80)


@router.post("/sources/weather/place")
async def set_place(body: PlaceBody, request: Request):
    src = request.app.state.svc.extras["sources"]
    try:
        res = await src.set_place(body.place)
    except Exception:
        return JSONResponse({"error": "unreachable", "message": "Can't reach the weather service right now."},
                            status_code=502)
    if not res:
        return JSONResponse({"error": "not_found", "message": "Couldn't find that place. Try a nearby town."},
                            status_code=404)
    return res


@router.get("/sources/weather")
async def weather_now(request: Request):
    f, stale = await request.app.state.svc.extras["sources"].weather()
    return {"forecast": f.to_dict() if f else None, "stale_minutes": stale}


class CalendarBody(BaseModel):
    url: str = Field(min_length=8, max_length=2000)


@router.post("/sources/calendar/test")
async def test_calendar(body: CalendarBody, request: Request):
    from ..sources.calendar import fetch_ics, parse_events

    src = request.app.state.svc.extras["sources"]
    try:
        ics = await fetch_ics(body.url, src.http)
        from datetime import datetime
        evs = await asyncio.to_thread(parse_events, ics, datetime.now(src.tz()).date(), src.tz())
    except Exception:
        return JSONResponse({"error": "bad_calendar",
                             "message": "That link didn't give a calendar. Use the “Secret address in iCal format”."},
                            status_code=422)
    return {"ok": True, "today": [{"title": e.title, "time": e.label()} for e in evs[:10]]}


@router.get("/sources/status")
async def sources_status(request: Request):
    src = request.app.state.svc.extras["sources"]
    return {"sources": src.status(), "tasks_connected": src.tasks_api.configured()}


@router.post("/sources/tasks/token")
async def upload_tasks_token(request: Request, file: UploadFile = File(...)):
    from ..sources.google_tasks import TasksError

    src = request.app.state.svc.extras["sources"]
    try:
        src.tasks_api.save_token(await file.read(64 * 1024))
        lists = await src.tasks_api.lists()
    except TasksError as exc:
        return JSONResponse({"error": "bad_token", "message": str(exc)}, status_code=422)
    except Exception:
        return JSONResponse({"error": "unreachable", "message": "Saved, but Google couldn't be reached to check it."},
                            status_code=502)
    request.app.state.svc.app_settings.patch({"tasks": {"enabled": True}})
    return {"ok": True, "lists": lists}


@router.get("/sources/tasks/lists")
async def tasks_lists(request: Request):
    src = request.app.state.svc.extras["sources"]
    if not src.tasks_api.configured():
        return {"lists": [], "connected": False}
    try:
        return {"lists": await src.tasks_api.lists(), "connected": True}
    except Exception as exc:
        return JSONResponse({"error": "tasks", "message": str(exc)}, status_code=502)


@router.delete("/sources/tasks/token")
async def forget_tasks(request: Request):
    request.app.state.svc.extras["sources"].tasks_api.forget()
    request.app.state.svc.app_settings.patch({"tasks": {"enabled": False}})
    return {"ok": True}
