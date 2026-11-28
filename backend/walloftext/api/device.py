"""/api/health, /api/device, power controls, setup slip, SSE."""
from __future__ import annotations

import asyncio
import json
import subprocess
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
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
        "restart": svc.extras["restart"].status() if "restart" in svc.extras else None,
        "printer": svc.queue.status(),
        "hw": svc.settings.hw,
    }


class TimeBody(BaseModel):
    auto: bool | None = None  # True: set the clock from the internet (NTP)
    epoch_ms: float | None = Field(default=None, ge=1_700_000_000_000, le=4_102_444_800_000)  # set it by hand
    timezone: str | None = Field(default=None, max_length=64)


def _time_state(svc) -> dict:
    st = svc.system.time_status()
    boot = svc.system.boot_id()
    sched = svc.extras.get("scheduler")
    return {**st, "timezone": svc.app_settings.get("schedules").get("timezone", "Europe/London"),
            "manual_this_boot": bool(boot) and svc.store.get("manual_clock_boot") == boot,
            "scheduler_waiting": bool(sched and sched.waiting_for_clock)}


@router.get("/device/time")
async def get_time(request: Request):
    return await asyncio.to_thread(_time_state, request.app.state.svc)


@router.put("/device/time")
async def set_time(body: TimeBody, request: Request):
    """Date & time: automatic (internet) or set by hand, and the time zone. The Pi has no
    battery clock, so a time set by hand only lasts until the next power cut."""
    svc = request.app.state.svc
    sysi = svc.system
    try:
        if body.timezone:
            try:
                ZoneInfo(body.timezone)
            except Exception:
                return JSONResponse({"error": "bad_timezone", "message": "Unknown time zone."}, status_code=422)
            svc.app_settings.patch({"schedules": {"timezone": body.timezone}})
            await asyncio.to_thread(sysi.set_timezone, body.timezone)
        if body.auto is True:
            await asyncio.to_thread(sysi.set_ntp, True)
            svc.store.delete("manual_clock_boot")
        elif body.epoch_ms is not None:
            await asyncio.to_thread(sysi.set_ntp, False)
            await asyncio.to_thread(sysi.set_time, body.epoch_ms / 1000)
            svc.store.set("manual_clock_boot", sysi.boot_id())
    except (RuntimeError, OSError) as exc:
        return JSONResponse({"error": "clock", "message": f"The Pi didn't let the app change the clock ({exc}). "
                             "Run the update again so it installs the permission."}, status_code=502)
    return await asyncio.to_thread(_time_state, svc)


# ---------------------------------------------------------------- hardware --
@router.get("/hw")
async def hw_status(request: Request):
    """Button, panel light, fan and LED strips: on/off, problems, live fan speed and strip colours."""
    return await asyncio.to_thread(request.app.state.svc.hw.status)


@router.post("/hw/retry")
async def hw_retry(request: Request):
    hw = request.app.state.svc.hw
    await asyncio.to_thread(hw.apply, True)
    return await asyncio.to_thread(hw.status)


@router.post("/hw/fan/test")
async def fan_test(request: Request):
    hw = request.app.state.svc.hw
    if not hw.fan:
        return JSONResponse({"error": "off", "message": "Switch the fan on first."}, status_code=409)
    hw.fan.test(5)
    return {"ok": True}


class TryBody(BaseModel):
    event: str = Field(pattern="^(idle|printing|message_waiting|paper_out|error|setup)$")


@router.post("/hw/neopixel/try")
async def neopixel_try(body: TryBody, request: Request):
    hw = request.app.state.svc.hw
    if not hw.neo:
        return JSONResponse({"error": "off", "message": "Switch the LED strip on first."}, status_code=409)
    hw.neo.try_event(body.event, 6)
    return {"ok": True}


class ColorBody(BaseModel):
    color: str | None = Field(default=None, pattern="^#[0-9a-fA-F]{6}$")  # None ends the test
    seconds: float = Field(default=30, ge=1, le=120)


@router.post("/hw/neopixel/color")
async def neopixel_color(body: ColorBody, request: Request):
    """Colour-order test: the whole strip in one colour for a while."""
    from ..hw.neopixel import hex_rgb
    hw = request.app.state.svc.hw
    if not hw.neo:
        return JSONResponse({"error": "off", "message": "Switch the LED strip on first."}, status_code=409)
    hw.neo.show_color(hex_rgb(body.color) if body.color else None, body.seconds)
    return {"ok": True}


class OrderTestBody(BaseModel):
    saw_red: str = Field(pattern="^[RGB]$")
    saw_green: str = Field(pattern="^[RGB]$")


@router.post("/hw/neopixel/order")
async def neopixel_order(body: OrderTestBody, request: Request):
    """Set the colour order from what was seen when red and then green were shown."""
    from ..hw.neopixel import order_from_test
    svc = request.app.state.svc
    current = svc.app_settings.get("neopixel").get("order", "GRB")
    try:
        order = order_from_test(current, body.saw_red, body.saw_green)
    except ValueError:
        return JSONResponse({"error": "bad", "message": "Red and green can't look the same. Try again."}, status_code=422)
    svc.app_settings.patch({"neopixel": {"order": order}})
    if svc.hw.neo:
        svc.hw.neo.show_color(None)
    return {"order": order}


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
