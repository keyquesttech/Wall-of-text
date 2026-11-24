"""Guest page (`/note`, open when enabled) and the shared approval list (BUILD_PLAN 10.3)."""
from __future__ import annotations

import time
from collections import defaultdict, deque

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ..render.stickers import STICKERS

router = APIRouter()

_guest_hits: dict[str, deque] = defaultdict(deque)


class NoteBody(BaseModel):
    name: str = Field(default="", max_length=40)
    text: str = Field(default="", max_length=2000)
    sticker: str | None = Field(default=None, max_length=20)


def guest_doc(name: str, text: str, sticker: str | None) -> dict:
    """Guest note slip (PRINT_TEMPLATES 8b): "from {name}" and the time in the header."""
    from datetime import datetime
    return {"blocks": [{"type": "slip", "template": "guest_note",
                        "data": {"name": name or "a guest", "text": text.strip(), "sticker": sticker,
                                 "now": datetime.now().isoformat(timespec="minutes")}}]}


@router.get("/api/guest")
async def guest_info(request: Request):
    g = request.app.state.svc.app_settings.get("guest")
    return {"enabled": g["enabled"], "max_chars": g["max_chars"], "mode": g["mode"], "stickers": list(STICKERS)}


@router.post("/api/note", status_code=201)
async def post_note(body: NoteBody, request: Request):
    svc = request.app.state.svc
    g = svc.app_settings.get("guest")
    if not g["enabled"]:
        return JSONResponse({"error": "closed", "message": "The guest page is switched off."}, status_code=403)
    text = body.text.strip()
    if not text and not body.sticker:
        return JSONResponse({"error": "empty", "message": "Write something or pick a sticker."}, status_code=422)
    if len(text) > int(g["max_chars"]):
        return JSONResponse({"error": "too_long", "message": f"Notes can be up to {g['max_chars']} characters."},
                            status_code=422)
    if body.sticker and body.sticker not in STICKERS:
        return JSONResponse({"error": "bad_sticker"}, status_code=422)
    client = request.client.host if request.client else "?"
    hits = _guest_hits[client]
    now = time.monotonic()
    while hits and now - hits[0] > 600:
        hits.popleft()
    if len(hits) >= int(g["rate_per_10min"]):
        return JSONResponse({"error": "rate", "message": "That's a lot of notes. Try again in a few minutes."},
                            status_code=429)
    hits.append(now)
    doc = guest_doc(body.name.strip(), text, body.sticker)
    title = f"Note from {body.name.strip() or 'a guest'}"
    sched = svc.extras["scheduler"]
    if g["mode"] == "approve":
        svc.extras["inbox"].add("Guest", body.name.strip() or "Guest", "guest", title, doc, text[:200])
        return {"ok": True, "status": "waiting", "message": "Sent. It prints once it's approved."}
    if sched.over_daily_limit():
        return JSONResponse({"error": "limit", "message": "The printer has reached its daily limit. Try tomorrow."},
                            status_code=429)
    held = sched.hold_until()
    svc.print_document(doc, "Guest", title, held_until=held)
    return {"ok": True, "status": "held" if held else "printing",
            "message": "Sent. It prints when quiet hours end." if held else "Printing now."}


@router.get("/api/inbox")
async def inbox(request: Request):
    return {"items": request.app.state.svc.extras["inbox"].waiting()}


@router.post("/api/inbox/{iid}/approve")
async def approve(iid: int, request: Request):
    svc = request.app.state.svc
    jid = svc.extras["inbox"].approve(iid)
    if jid is None:
        return JSONResponse({"error": "not_found"}, status_code=404)
    return {"ok": True, "job": svc.queue.get(jid)}


@router.post("/api/inbox/{iid}/decline")
async def decline(iid: int, request: Request):
    ok = request.app.state.svc.extras["inbox"].decline(iid)
    return JSONResponse({"ok": ok}, status_code=200 if ok else 404)
