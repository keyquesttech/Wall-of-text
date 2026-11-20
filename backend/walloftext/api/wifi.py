"""/api/wifi/* (sections 5.4, 5.5, 11). Request bodies here are never logged."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ..net.wifi import AP_MODES

router = APIRouter(prefix="/api/wifi")


class ConnectBody(BaseModel):
    ssid: str = Field(min_length=1, max_length=32)
    password: str | None = Field(default=None, max_length=64)
    hidden: bool = False
    security: str | None = Field(default=None, pattern="^(open|wpa2|wpa3|wpa2/wpa3|wep|enterprise)$")

    def __repr__(self) -> str:  # keep the password out of any accidental repr
        return f"ConnectBody(ssid={self.ssid!r}, hidden={self.hidden})"


class ResetBody(BaseModel):
    confirm: bool


@router.get("/status")
async def status(request: Request):
    return request.app.state.svc.wifi.status.to_dict()


@router.get("/scan")
async def scan(request: Request):
    return request.app.state.svc.wifi.scan_results()


@router.post("/connect", status_code=202)
async def connect(body: ConnectBody, request: Request):
    svc = request.app.state.svc
    if svc.wifi.status.mode == "connecting" and svc.wifi.status.pending_ssid:
        return JSONResponse({"error": "busy", "message": "Already connecting. Wait a minute."}, status_code=409)
    if body.security in ("wpa2", "wpa3", "wpa2/wpa3"):
        if not body.password or not 8 <= len(body.password) <= 63:
            return JSONResponse({"error": "invalid", "message": "Wi-Fi passwords are 8 to 63 characters."},
                                status_code=422)
    asyncio.create_task(svc.wifi.connect(body.ssid, body.password, body.hidden, body.security))
    return {"ok": True, "ssid": body.ssid, "ap_mode": svc.wifi.status.mode in AP_MODES}


@router.post("/reset")
async def reset(body: ResetBody, request: Request):
    if not request.state.signed_in:
        return JSONResponse({"error": "sign_in_required"}, status_code=401)
    if not body.confirm:
        return JSONResponse({"error": "confirm_required"}, status_code=400)
    svc = request.app.state.svc
    asyncio.create_task(_delayed_reset(svc))
    return {"ok": True}


async def _delayed_reset(svc) -> None:
    await asyncio.sleep(svc.settings.connect_reply_delay_s)  # let the reply reach the phone
    await svc.wifi.reset()
