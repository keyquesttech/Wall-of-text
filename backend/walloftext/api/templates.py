"""/api/templates and /api/lists (Phase 7)."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ..templates_lists import fill

router = APIRouter(prefix="/api")


class FillBody(BaseModel):
    values: dict[str, str] = Field(default_factory=dict)
    print: bool = False
    copies: int = Field(default=1, ge=1, le=10)


class TemplateBody(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    document: dict[str, Any]
    icon: str | None = Field(default=None, max_length=20)


@router.get("/templates")
async def list_templates(request: Request):
    return {"items": request.app.state.svc.extras["templates"].list()}


@router.post("/templates", status_code=201)
async def save_template(body: TemplateBody, request: Request):
    svc = request.app.state.svc
    try:
        svc.renderer.render(body.document)  # validate
    except ValueError as exc:
        return JSONResponse({"error": "bad_document", "message": str(exc)}, status_code=422)
    return svc.extras["templates"].add(body.name, body.document, body.icon)


@router.delete("/templates/{tid}")
async def delete_template(tid: str, request: Request):
    return {"ok": request.app.state.svc.extras["templates"].delete(tid)}


SAMPLE = {"text": "See you at 7!", "title": "Groceries", "items": "Oat milk\nEggs\nCoffee", "ssid": "HomeWiFi",
          "password": "••••••", "to": "Sam", "message": "Happy birthday!", "from": "Matias", "ingredients": "Flour\nEggs",
          "steps": "Mix, then bake.", "who": "Sam", "caption": "Well done"}


@router.get("/templates/{tid}/thumb")
async def template_thumb(tid: str, request: Request):
    """A small 1-bit picture of the template filled with sample words, for the gallery."""
    import asyncio

    from fastapi.responses import Response

    svc = request.app.state.svc
    t = svc.extras["templates"].get(tid)
    if not t:
        return JSONResponse({"error": "not_found"}, status_code=404)
    doc = fill(t, SAMPLE) if t.get("fields") else t["document"]
    res = await asyncio.to_thread(svc.renderer.render, doc)
    img = res.image.crop((0, 0, 384, min(res.image.height, 420)))
    import io
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    return Response(buf.getvalue(), media_type="image/png", headers={"Cache-Control": "private, max-age=3600"})


@router.post("/templates/{tid}/fill")
async def fill_template(tid: str, body: FillBody, request: Request):
    """Returns the filled document; with print=true also queues it."""
    svc = request.app.state.svc
    t = svc.extras["templates"].get(tid)
    if not t:
        return JSONResponse({"error": "not_found"}, status_code=404)
    doc = fill(t, body.values) if t.get("fields") else t["document"]
    out: dict[str, Any] = {"document": doc}
    if body.print:
        jid = svc.print_document(doc, "Manual", t["name"], copies=body.copies)
        out["job"] = svc.queue.get(jid)
    return out


class ItemBody(BaseModel):
    text: str = Field(min_length=1, max_length=120)


class ItemPatch(BaseModel):
    done: bool | None = None
    text: str | None = Field(default=None, max_length=120)


@router.get("/lists/{name}")
async def get_list(name: str, request: Request):
    return {"items": request.app.state.svc.extras["lists"].items(name)}


@router.post("/lists/{name}", status_code=201)
async def add_item(name: str, body: ItemBody, request: Request):
    if name not in ("shopping", "todo"):
        return JSONResponse({"error": "not_found"}, status_code=404)
    return request.app.state.svc.extras["lists"].add(name, body.text)


@router.patch("/lists/items/{iid}")
async def patch_item(iid: int, body: ItemPatch, request: Request):
    ok = request.app.state.svc.extras["lists"].update(iid, body.done, body.text)
    return JSONResponse({"ok": ok}, status_code=200 if ok else 404)


@router.delete("/lists/items/{iid}")
async def delete_item(iid: int, request: Request):
    return {"ok": request.app.state.svc.extras["lists"].delete(iid)}


@router.post("/lists/{name}/clear-done")
async def clear_done(name: str, request: Request):
    return {"removed": request.app.state.svc.extras["lists"].clear_done(name)}


@router.post("/lists/{name}/print", status_code=201)
async def print_list(name: str, request: Request):
    svc = request.app.state.svc
    jid = svc.print_document(svc.extras["lists"].document(name), "Manual", f"{name.capitalize()} list")
    return {"job": svc.queue.get(jid)}
