"""Settings › Fortunes: upload your own fortunes as a CSV, download them, or go back to the built-in ones."""
from __future__ import annotations

import csv
import io
import json

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse, Response

from .. import actions

router = APIRouter(prefix="/api/fortunes")


def _summary(svc) -> dict:
    custom = actions.custom_fortunes(svc)
    return {"builtin_count": len(actions.builtin_fortunes()), "custom_count": len(custom),
            "use_builtin": bool(svc.app_settings.get("fortunes").get("use_builtin", True)),
            "in_play": len(actions.fortunes(svc)), "sample": custom[:5]}


@router.get("")
async def summary(request: Request):
    return _summary(request.app.state.svc)


@router.post("/csv")
async def upload(request: Request, file: UploadFile = File(...), mode: str = Form("replace")):
    svc = request.app.state.svc
    raw = await file.read(2 * 1024 * 1024 + 1)
    if len(raw) > 2 * 1024 * 1024:
        return JSONResponse({"error": "too_big", "message": "That file is over 2 MB."}, status_code=413)
    items, skipped = actions.parse_fortunes_csv(raw)
    if not items:
        return JSONResponse({"error": "empty", "message": "No fortunes found. Put one fortune per row in the first column."},
                            status_code=422)
    if mode == "add":
        cur = actions.custom_fortunes(svc)
        seen = set(cur)
        new = [x for x in items if x not in seen]
        items = (cur + new)[: actions.MAX_FORTUNES]
        added = len(new)
    else:
        added = len(items)
    svc.store.set("custom_fortunes", json.dumps(items, ensure_ascii=False))
    return {**_summary(svc), "added": added, "skipped": skipped}


@router.get("/csv")
async def download(request: Request):
    svc = request.app.state.svc
    items = actions.custom_fortunes(svc) or actions.builtin_fortunes()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["fortune"])
    for x in items:
        w.writerow([x])
    return Response(buf.getvalue().encode("utf-8-sig"), media_type="text/csv",
                    headers={"Content-Disposition": 'attachment; filename="walloftext-fortunes.csv"'})


@router.delete("/custom")
async def clear(request: Request):
    svc = request.app.state.svc
    svc.store.set("custom_fortunes", "[]")
    return _summary(svc)
