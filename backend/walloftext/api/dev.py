"""Dev-only routes, mounted only with WOT_HW=mock (section 11)."""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/dev")


class ButtonBody(BaseModel):
    gesture: str = Field(pattern="^(single|double|long|reset)$")


class NetStateBody(BaseModel):
    router_up: bool | None = None
    phones_on_ap: int | None = Field(default=None, ge=0, le=10)
    networks: dict[str, str | None] | None = None
    printer_offline: bool | None = None


@router.post("/button")
async def button(body: ButtonBody, request: Request):
    request.app.state.svc.hw.button.fire(body.gesture)
    return {"ok": True}


@router.get("/net-state")
async def get_net_state(request: Request):
    nm = request.app.state.svc.nm
    return {"router_up": nm.router_up, "phones_on_ap": nm.phones_on_ap, "ap_on": nm.ap_on,
            "networks": list(nm.networks), "profiles": list(nm.profiles), "active": nm.active_client}


@router.post("/net-state")
async def net_state(body: NetStateBody, request: Request):
    svc = request.app.state.svc
    nm = svc.nm
    if body.router_up is not None:
        nm.router_up = body.router_up
        if body.router_up and not nm.ap_on:
            nm.simulate_boot_autoconnect()
    if body.phones_on_ap is not None:
        nm.phones_on_ap = body.phones_on_ap
    if body.networks is not None:
        nm.networks = body.networks
    if body.printer_offline is not None and hasattr(svc.printer, "offline"):
        svc.printer.offline = body.printer_offline
    await svc.wifi.tick()
    return await get_net_state(request)


@router.post("/inbound")
async def inbound(payload: dict, request: Request):
    from .remote import dev_inbound

    return await dev_inbound(payload, request)
