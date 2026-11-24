"""Preview, print, queue, history, printer and fonts (HANDOFF section 12 + BUILD_PLAN 6)."""
from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from ..render.document import DocumentError

router = APIRouter(prefix="/api")

SOURCES = ("Manual", "Schedule", "Button", "Guest", "Remote", "System")


class DocBody(BaseModel):
    document: dict[str, Any]
    copies: int = Field(default=1, ge=1, le=10)
    title: str | None = Field(default=None, max_length=120)
    extra_feed: int = Field(default=0, ge=0, le=20)


class PaperOutBody(BaseModel):
    out: bool


def _title(doc: dict, given: str | None) -> str:
    if given:
        return given
    for b in doc.get("blocks", []):
        t = b.get("text") or b.get("caption")
        if isinstance(t, str) and t.strip():
            return t.strip().splitlines()[0][:60]
        if b.get("type") in ("image", "drawing"):
            return "Picture"
        if b.get("type") == "checklist":
            return "List"
    return "Print"


@router.post("/preview")
async def preview(body: DocBody, request: Request):
    svc = request.app.state.svc
    try:
        result = await asyncio.to_thread(svc.renderer.render, body.document)
    except DocumentError as exc:
        return JSONResponse({"error": "bad_document", "message": str(exc)}, status_code=422)
    png = await asyncio.to_thread(result.png)
    return Response(png, media_type="image/png", headers={
        "X-Wot-Rows": str(result.rows),
        "X-Wot-Length-Mm": f"{result.rows / 8:.0f}",
        "X-Wot-Coverage": f"{result.coverage:.3f}",
        "X-Wot-Warnings": " | ".join(result.warnings)[:1000].encode("ascii", "replace").decode(),
        "Cache-Control": "no-store",
    })


@router.post("/print", status_code=201)
async def print_doc(body: DocBody, request: Request):
    svc = request.app.state.svc
    try:
        result = await asyncio.to_thread(svc.renderer.render, body.document)
    except DocumentError as exc:
        return JSONResponse({"error": "bad_document", "message": str(exc)}, status_code=422)
    job_id = svc.print_image(result.image, "Manual", _title(body.document, body.title), body.document,
                             body.copies, meta={"extra_feed": body.extra_feed} if body.extra_feed else None)
    return {"job": svc.queue.get(job_id), "warnings": result.warnings, "printer": svc.queue.status()}


# ------------------------------------------------------------ queue --
@router.get("/queue")
async def queue(request: Request):
    svc = request.app.state.svc
    return {"jobs": svc.queue.pending(), "printer": svc.queue.status()}


@router.post("/queue/{job_id}/cancel")
async def cancel(job_id: int, request: Request):
    ok = request.app.state.svc.queue.cancel(job_id)
    return JSONResponse({"ok": ok}, status_code=200 if ok else 409)


@router.post("/queue/cancel-all")
async def cancel_all(request: Request):
    return {"cancelled": request.app.state.svc.queue.cancel_all()}


# ---------------------------------------------------------- history --
@router.get("/history")
async def history(request: Request, source: str | None = None, limit: int = 50, before: int | None = None,
                  q: str | None = None):
    svc = request.app.state.svc
    if source and source not in SOURCES:
        return JSONResponse({"error": "bad_source"}, status_code=400)
    states = ("done", "failed", "cancelled", "missed", "printing", "queued", "held")
    return {"items": svc.queue.list(states, source, limit, before, (q or "").strip()[:60] or None)}


@router.get("/history/{job_id}")
async def history_item(job_id: int, request: Request):
    job = request.app.state.svc.queue.get(job_id, with_blobs=True)
    if not job:
        return JSONResponse({"error": "not_found"}, status_code=404)
    job.pop("bitmap", None)
    return job


@router.get("/history/{job_id}/image")
async def history_image(job_id: int, request: Request):
    png = request.app.state.svc.queue.image_png(job_id)
    if not png:
        return JSONResponse({"error": "not_found"}, status_code=404)
    return Response(png, media_type="image/png", headers={"Cache-Control": "private, max-age=86400"})


@router.post("/history/{job_id}/reprint", status_code=201)
async def reprint(job_id: int, request: Request):
    svc = request.app.state.svc
    new_id = svc.queue.retry(job_id, source="Manual")
    if not new_id:
        return JSONResponse({"error": "not_found"}, status_code=404)
    return {"job": svc.queue.get(new_id)}


@router.post("/jobs/{job_id}/retry", status_code=201)
async def retry(job_id: int, request: Request):
    svc = request.app.state.svc
    new_id = svc.queue.retry(job_id)
    if not new_id:
        return JSONResponse({"error": "not_found"}, status_code=404)
    return {"job": svc.queue.get(new_id)}


@router.delete("/history/{job_id}")
async def delete_item(job_id: int, request: Request):
    ok = request.app.state.svc.queue.delete(job_id)
    return JSONResponse({"ok": ok}, status_code=200 if ok else 409)


@router.delete("/history")
async def clear(request: Request):
    return {"deleted": request.app.state.svc.queue.clear_history()}


# ---------------------------------------------------------- printer --
@router.get("/printer")
async def printer(request: Request):
    return request.app.state.svc.queue.status()


@router.post("/printer/test-page", status_code=201)
async def test_page(request: Request):
    svc = request.app.state.svc
    from datetime import datetime

    from ..config import LOCAL_ADDRESS
    p = svc.app_settings.get("printer")
    dark = int(p.get("darkness", 120))
    st = svc.queue.status()
    doc = {"blocks": [{"type": "slip", "template": "test_page", "data": {
        "now": datetime.now().isoformat(timespec="minutes"),
        "paper": f"About {st['paper_percent']}%",
        "darkness": "Light" if dark < 100 else "Dark" if dark > 140 else "Normal",
        "speed": str(p.get("speed", "normal")).capitalize(),
        "address": LOCAL_ADDRESS}}]}
    job_id = svc.print_document(doc, "System", "Test page")
    return {"job": svc.queue.get(job_id)}


@router.post("/printer/calibration-print", status_code=201)
async def calibration_print(request: Request):
    """Print the length-calibration slip (two lines 800 dot rows apart)."""
    from datetime import datetime
    svc = request.app.state.svc
    doc = {"blocks": [{"type": "slip", "template": "calibration", "data": {"now": datetime.now().isoformat(timespec="minutes")}}]}
    job_id = svc.print_document(doc, "System", "Length calibration")
    return {"job": svc.queue.get(job_id)}


class CalibrationBody(BaseModel):
    measured_mm: float | None = Field(default=None, ge=60, le=140)  # None = back to the nominal 203 dpi


@router.post("/printer/calibration")
async def set_calibration(body: CalibrationBody, request: Request):
    from ..render.kit.system import CAL_ROWS
    from ..queue.worker import NOMINAL_MM_PER_ROW
    svc = request.app.state.svc
    mm_per_row = round(body.measured_mm / CAL_ROWS, 6) if body.measured_mm else NOMINAL_MM_PER_ROW
    svc.app_settings.patch({"printer": {"mm_per_row": mm_per_row}})
    return {"mm_per_row": mm_per_row, **svc.queue.status()}


@router.post("/printer/new-roll")
async def new_roll(request: Request):
    svc = request.app.state.svc
    svc.queue.new_roll()
    return svc.queue.status()


@router.post("/printer/paper-out")
async def paper_out(body: PaperOutBody, request: Request):
    svc = request.app.state.svc
    svc.queue.set_paper_out(body.out)
    return svc.queue.status()


# ------------------------------------------------------------ fonts --
@router.get("/fonts")
async def fonts(request: Request):
    return [f.to_dict() for f in request.app.state.svc.fonts.all()]


@router.post("/fonts", status_code=201)
async def upload_font(request: Request, file: UploadFile = File(...), name: str = Form("")):
    svc = request.app.state.svc
    data = await file.read(6 * 1024 * 1024)
    try:
        info = await asyncio.to_thread(svc.fonts.add, name or (file.filename or "Font").rsplit(".", 1)[0], data)
    except ValueError as exc:
        return JSONResponse({"error": "bad_font", "message": str(exc)}, status_code=422)
    return info.to_dict()


@router.delete("/fonts/{font_id}")
async def delete_font(font_id: str, request: Request):
    ok = request.app.state.svc.fonts.remove(font_id)
    return JSONResponse({"ok": ok}, status_code=200 if ok else 404)


@router.get("/fonts/{font_id}/file")
async def font_file(font_id: str, request: Request):
    info = request.app.state.svc.fonts.get(font_id)
    if info.id != font_id:
        return JSONResponse({"error": "not_found"}, status_code=404)
    return Response(info.regular.read_bytes(), media_type="font/ttf",
                    headers={"Cache-Control": "private, max-age=604800"})
