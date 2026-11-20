"""/api/remote/* (BUILD_PLAN 11). Credentials are write-only: GET never returns them."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ..remote.base import ChannelError

router = APIRouter(prefix="/api/remote")


def _mgr(request: Request):
    return request.app.state.svc.extras["remote"]


class ChannelPatch(BaseModel):
    enabled: bool | None = None
    credentials: dict[str, str] | None = None

    def __repr__(self) -> str:
        return f"ChannelPatch(enabled={self.enabled})"


ALLOWED_CREDS = {"email": {"address", "app_password", "imap_host"}, "telegram": {"bot_token"}}


@router.get("/channels")
async def channels(request: Request):
    m = _mgr(request)
    return {"channels": m.channels(), "blocked_week": m.pipeline.blocked_count()}


@router.get("/channels/{cid}")
async def channel(cid: str, request: Request):
    m = _mgr(request)
    if cid not in m.adapters:
        return JSONResponse({"error": "not_found"}, status_code=404)
    return m.channel(cid)


@router.patch("/channels/{cid}")
async def patch_channel(cid: str, body: ChannelPatch, request: Request):
    m = _mgr(request)
    svc = request.app.state.svc
    if cid not in m.adapters:
        return JSONResponse({"error": "not_found"}, status_code=404)
    if body.credentials is not None:
        allowed = ALLOWED_CREDS.get(cid, set())
        clean = {k: v.strip() for k, v in body.credentials.items() if k in allowed and isinstance(v, str)}
        if cid == "email" and clean.get("address") and "@" not in clean["address"]:
            return JSONResponse({"error": "invalid", "message": "That email address doesn't look right."}, status_code=422)
        svc.extras["secrets"].set(cid, clean)
    if body.enabled is not None:
        m.set_enabled(cid, body.enabled)
    else:
        m.reconcile()
    m.kick(cid)
    return m.channel(cid)


@router.delete("/channels/{cid}/credentials")
async def forget(cid: str, request: Request):
    m = _mgr(request)
    request.app.state.svc.extras["secrets"].clear(cid)
    m.set_enabled(cid, False)
    return m.channel(cid)


@router.post("/channels/{cid}/test")
async def test(cid: str, request: Request):
    m = _mgr(request)
    if cid not in m.adapters:
        return JSONResponse({"error": "not_found"}, status_code=404)
    try:
        return {"ok": True, "message": await m.adapters[cid].test()}
    except ChannelError as exc:
        return JSONResponse({"error": "reauth" if exc.reauth else "cant_connect", "message": str(exc)}, status_code=502)


@router.post("/pairing/start")
async def pairing_start(request: Request):
    m = _mgr(request)
    tg = m.adapters.get("telegram")
    if not tg or not tg.configured():
        return JSONResponse({"error": "not_ready", "message": "Add the Telegram bot token first."}, status_code=409)
    tg.start_pairing()
    if not m.enabled("telegram"):
        m.set_enabled("telegram", True)
    m.kick("telegram")
    return tg.pairing_state()


@router.get("/pairing")
async def pairing(request: Request):
    tg = _mgr(request).adapters.get("telegram")
    return tg.pairing_state() if tg else {"active": False, "captured": None}


class PairConfirm(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    sender_id: str | None = None  # add to an existing sender


@router.post("/pairing/confirm", status_code=201)
async def pairing_confirm(body: PairConfirm, request: Request):
    m = _mgr(request)
    tg = m.adapters["telegram"]
    cap = tg.paired
    if not cap:
        return JSONResponse({"error": "nothing_paired", "message": "Message the bot first."}, status_code=409)
    senders = m.pipeline.senders
    ident = {"channel": "telegram", "value": cap["user_id"]}
    if body.sender_id and senders.get(body.sender_id):
        cur = senders.get(body.sender_id)
        s = senders.save({"identifiers": cur["identifiers"] + [ident]}, body.sender_id)
    else:
        s = senders.save({"name": body.name, "identifiers": [ident]})
    tg.paired = None
    tg.pairing_until = 0
    return s


class SenderBody(BaseModel):
    name: str | None = Field(default=None, max_length=40)
    identifiers: list[dict[str, str]] | None = Field(default=None, max_length=10)
    approval: str | None = Field(default=None, pattern="^(print|approve)$")


@router.get("/senders")
async def senders(request: Request):
    return {"items": _mgr(request).pipeline.senders.list()}


@router.post("/senders", status_code=201)
async def add_sender(body: SenderBody, request: Request):
    channels = ("email", "telegram", "sms") + (("mock",) if request.app.state.svc.settings.is_mock else ())
    for i in body.identifiers or []:
        if i.get("channel") not in channels or not i.get("value", "").strip():
            return JSONResponse({"error": "invalid", "message": "Each sender needs an email address, Telegram ID or phone number."},
                                status_code=422)
    return _mgr(request).pipeline.senders.save(body.model_dump(exclude_none=True))


@router.patch("/senders/{sid}")
async def patch_sender(sid: str, body: SenderBody, request: Request):
    s = _mgr(request).pipeline.senders
    if not s.get(sid):
        return JSONResponse({"error": "not_found"}, status_code=404)
    return s.save(body.model_dump(exclude_none=True), sid)


@router.delete("/senders/{sid}")
async def delete_sender(sid: str, request: Request):
    return {"ok": _mgr(request).pipeline.senders.delete(sid)}


# dev only (mock hardware): push a message straight into the pipeline
async def dev_inbound(payload: dict[str, Any], request: Request):
    from ..remote.mock import from_dict

    m = _mgr(request)
    try:
        msg = from_dict(payload)
    except (KeyError, ValueError):
        return JSONResponse({"error": "invalid"}, status_code=422)
    outcome = await m.pipeline.handle(msg, m.adapters.get("mock"))
    return {"outcome": outcome}
