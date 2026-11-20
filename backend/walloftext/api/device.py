"""/api/health, /api/device, power controls, setup slip, SSE."""
from __future__ import annotations

import asyncio
import json
import subprocess

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sse_starlette.sse import EventSourceResponse

from .. import __version__
from ..config import LOCAL_ADDRESS, PRODUCT_NAME

router = APIRouter(prefix="/api")


@router.get("/health")
async def health():
    return {"ok": True}


@router.get("/device")
async def device(request: Request):
    svc = request.app.state.svc
    sysi = svc.system
    return {
        "product": PRODUCT_NAME,
        "version": __version__,
        "hostname": LOCAL_ADDRESS,
        "ips": await asyncio.to_thread(svc.nm.all_ips),
        "temperature_c": sysi.temperature_c(),
        "throttled": await asyncio.to_thread(sysi.throttled),
        "uptime_s": sysi.uptime_s(),
        "disk": sysi.disk(),
        "clock_synced": await asyncio.to_thread(sysi.clock_synced),
        "printer": svc.queue.status(),
        "hw": svc.settings.hw,
    }


@router.post("/print/setup-slip")
async def print_setup_slip(request: Request):
    svc = request.app.state.svc
    if svc.queue.status()["state"] not in ("ready", "printing"):
        return JSONResponse({"error": "printer_offline", "message": "The printer isn't ready."}, status_code=409)
    await svc.print_setup_slip()
    return {"ok": True}


def _power(request: Request, verb: str):
    svc = request.app.state.svc
    if svc.settings.is_mock:
        return {"ok": True, "mock": True}
    subprocess.Popen(["systemctl", verb])
    return {"ok": True}


@router.post("/device/restart")
async def restart(request: Request):
    return _power(request, "reboot")


@router.post("/device/shutdown")
async def shutdown(request: Request):
    return _power(request, "poweroff")


@router.get("/events")
async def events(request: Request):
    svc = request.app.state.svc
    q = svc.events.subscribe()

    async def gen():
        try:
            yield {"event": "wifi", "data": json.dumps(svc.wifi.status.to_dict())}
            yield {"event": "printer", "data": json.dumps(svc.queue.status())}
            while True:
                if await request.is_disconnected():
                    break
                try:
                    yield await asyncio.wait_for(q.get(), timeout=15)
                except asyncio.TimeoutError:
                    yield {"event": "ping", "data": "{}"}
        finally:
            svc.events.unsubscribe(q)

    return EventSourceResponse(gen())
