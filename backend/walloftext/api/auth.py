"""/api/auth/* (section 10.2)."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ..auth.passwords import validate_gui, validate_wifi
from ..auth.sessions import COOKIE_NAME, passwords_match

router = APIRouter(prefix="/api/auth")


def _client(request: Request) -> str:
    return request.client.host if request.client else "?"


def _set_cookie(resp: Response, token: str, ttl: int, remember: bool) -> None:
    resp.set_cookie(COOKIE_NAME, token, max_age=ttl if remember else None, httponly=True,
                    samesite="lax", secure=False, path="/")


class LoginBody(BaseModel):
    password: str = Field(max_length=200)
    remember: bool = True


class PasswordBody(BaseModel):
    current: str = Field(max_length=200)
    new: str = Field(max_length=200)


class WifiPasswordBody(BaseModel):
    current_password: str = Field(max_length=200)
    new: str = Field(max_length=200)


class AskBody(BaseModel):
    ask_for_password: bool


@router.get("/status")
async def status(request: Request):
    svc = request.app.state.svc
    st = svc.passwords.state
    out = {
        "signed_in": bool(request.state.signed_in),
        "ask_for_password": svc.store.get("ask_for_password", "1") == "1",
        "default_password_in_use": st.default_gui,
        "default_setup_wifi_password_in_use": st.default_wifi,
    }
    if st.warnings and request.state.signed_in:
        out["password_file_warning"] = " ".join(st.warnings)
    return out


@router.post("/login")
async def login(body: LoginBody, request: Request):
    svc = request.app.state.svc
    client = _client(request)
    wait = svc.limiter.retry_after(client)
    if wait > 0:
        return JSONResponse(
            {"error": "locked", "retry_after": int(wait) + 1,
             "message": f"Too many wrong tries. Try again in {int(wait) + 1} seconds."},
            status_code=429, headers={"Retry-After": str(int(wait) + 1)},
        )
    svc.passwords.refresh()
    if not passwords_match(body.password, svc.passwords.state.gui_password):
        lock = svc.limiter.failure(client)
        await asyncio.sleep(0.4)
        msg = "That password isn't right." + (f" Try again in {int(lock)} seconds." if lock else "")
        return JSONResponse({"error": "wrong_password", "message": msg}, status_code=401)
    svc.limiter.success(client)
    token, ttl = svc.sessions.create(body.remember, request.headers.get("user-agent"))
    resp = JSONResponse({"ok": True})
    _set_cookie(resp, token, ttl, body.remember)
    return resp


@router.post("/logout")
async def logout(request: Request):
    svc = request.app.state.svc
    tok = request.cookies.get(COOKIE_NAME)
    if tok:
        svc.sessions.revoke(tok)
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(COOKIE_NAME, path="/")
    return resp


@router.post("/password")
async def change_password(body: PasswordBody, request: Request):
    svc = request.app.state.svc
    if not passwords_match(body.current, svc.passwords.state.gui_password):
        return JSONResponse({"error": "wrong_password", "message": "Your current password isn't right."},
                            status_code=403)
    err = validate_gui(body.new)
    if err:
        return JSONResponse({"error": "invalid", "message": err}, status_code=422)
    svc.passwords.set_gui(body.new)  # signs everyone out via the on_gui_change hook
    token, ttl = svc.sessions.create(True, request.headers.get("user-agent"))  # keep this device in
    resp = JSONResponse({"ok": True})
    _set_cookie(resp, token, ttl, True)
    return resp


@router.post("/setup-wifi-password")
async def change_setup_wifi_password(body: WifiPasswordBody, request: Request):
    svc = request.app.state.svc
    if not passwords_match(body.current_password, svc.passwords.state.gui_password):
        return JSONResponse({"error": "wrong_password", "message": "Your site password isn't right."},
                            status_code=403)
    err = validate_wifi(body.new)
    if err:
        return JSONResponse({"error": "invalid", "message": err}, status_code=422)
    svc.passwords.set_wifi(body.new)  # re-keys the AP via the on_wifi_change hook
    return {"ok": True}


@router.post("/ask-for-password")
async def set_ask(body: AskBody, request: Request):
    svc = request.app.state.svc
    svc.store.set("ask_for_password", "1" if body.ask_for_password else "0")
    return {"ok": True, "ask_for_password": body.ask_for_password}
