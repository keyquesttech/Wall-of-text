"""GET/POST /api/backup: zip of settings, schedules, templates, lists and uploaded fonts.

Excludes the password file, channel secrets and Google tokens (BUILD_PLAN 11).
Restore reads only known member names, so a crafted zip can't write elsewhere.
"""
from __future__ import annotations

import io
import json
import re
import sqlite3
import time
import zipfile

from fastapi import APIRouter, File, Request, UploadFile
from fastapi.responses import JSONResponse, Response

from .. import __version__

router = APIRouter(prefix="/api")

MAX_ZIP = 20 * 1024 * 1024
SECRET_KEYS = {"remote_secrets"}


def _table(conn, name: str) -> list[dict]:
    try:
        return [dict(r) for r in conn.execute(f"SELECT * FROM {name}").fetchall()]
    except sqlite3.OperationalError:
        return []


def build_zip(svc) -> tuple[str, bytes]:
    """(file name, zip bytes) of settings, schedules, templates, lists, fortunes, senders and fonts."""
    conn = svc.store.conn()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("manifest.json", json.dumps({"app": "walloftext", "version": __version__, "created": time.time()}))
        settings = svc.app_settings.all()
        z.writestr("settings.json", json.dumps(settings, indent=1))
        sched = _table(conn, "schedules")
        for s in sched:
            s.pop("last_due", None)
            s.pop("last_result", None)
            s.pop("last_run_at", None)
        z.writestr("schedules.json", json.dumps(sched, indent=1))
        z.writestr("templates.json", json.dumps(_table(conn, "templates"), indent=1))
        z.writestr("lists.json", json.dumps(_table(conn, "list_items"), indent=1))
        z.writestr("fortunes.json", svc.store.get("custom_fortunes", "[]") or "[]")
        senders = _table(conn, "remote_senders")
        z.writestr("remote_senders.json", json.dumps(senders, indent=1))
        fdir = svc.fonts.upload_dir
        if (fdir / "fonts.json").exists():
            z.write(fdir / "fonts.json", "fonts/fonts.json")
            for meta in json.loads((fdir / "fonts.json").read_text()).values():
                p = fdir / meta["file"]
                if p.exists():
                    z.write(p, f"fonts/{p.name}")
    return f"walloftext-backup-{time.strftime('%Y%m%d-%H%M')}.zip", buf.getvalue()


@router.get("/backup")
async def backup(request: Request):
    name, data = build_zip(request.app.state.svc)
    return Response(data, media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="{name}"', "Cache-Control": "no-store"})


@router.get("/backup/usb")
async def usb_status(request: Request):
    import asyncio
    return await asyncio.to_thread(request.app.state.svc.extras["usb_backup"].status)


@router.post("/backup/usb/run")
async def usb_run(request: Request):
    import asyncio
    return await asyncio.to_thread(request.app.state.svc.extras["usb_backup"].run_now)


@router.post("/backup")
async def restore(request: Request, file: UploadFile = File(...)):
    svc = request.app.state.svc
    raw = await file.read(MAX_ZIP + 1)
    if len(raw) > MAX_ZIP:
        return JSONResponse({"error": "too_big", "message": "Backups must be under 20 MB."}, status_code=413)
    try:
        z = zipfile.ZipFile(io.BytesIO(raw))
        manifest = json.loads(z.read("manifest.json"))
        if manifest.get("app") != "walloftext":
            raise ValueError
    except Exception:
        return JSONResponse({"error": "bad_backup", "message": "That file isn't a Wall Printer backup."}, status_code=422)
    names = set(z.namelist())
    conn = svc.store.conn()
    restored = []
    if "settings.json" in names:
        svc.app_settings.patch(json.loads(z.read("settings.json")))
        restored.append("settings")
    if "schedules.json" in names:
        rows = json.loads(z.read("schedules.json"))
        conn.execute("DELETE FROM schedules")
        for r in rows:
            conn.execute("INSERT INTO schedules(id,name,enabled,time,days,sections,conditions,icon,created_at,last_due) "
                         "VALUES(?,?,?,?,?,?,?,?,?,?)",
                         (r["id"], r["name"], r.get("enabled", 1), r.get("time"), r.get("days", "[]"),
                          r.get("sections", "[]"), r.get("conditions", "[]"), r.get("icon"), time.time(), time.time()))
        restored.append("schedules")
    for table, member in (("templates", "templates.json"), ("list_items", "lists.json"),
                          ("remote_senders", "remote_senders.json")):
        if member not in names:
            continue
        rows = json.loads(z.read(member))
        try:
            cols = [c[1] for c in conn.execute(f"PRAGMA table_info({table})").fetchall()]
            if not cols:
                continue
            conn.execute(f"DELETE FROM {table}")
            for r in rows:
                keys = [k for k in r if k in cols]
                conn.execute(f"INSERT INTO {table}({','.join(keys)}) VALUES({','.join('?' * len(keys))})",
                             [r[k] for k in keys])
            restored.append(table)
        except sqlite3.OperationalError:
            pass
    if "fortunes.json" in names:
        svc.store.set("custom_fortunes", z.read("fortunes.json").decode("utf-8"))
    if "fonts/fonts.json" in names:
        meta = json.loads(z.read("fonts/fonts.json"))
        fdir = svc.fonts.upload_dir
        fdir.mkdir(parents=True, exist_ok=True)
        clean = {}
        for fid, m in meta.items():
            fname = m.get("file", "")
            if not re.fullmatch(r"u-[a-z0-9-]+\.(ttf|otf)", fname) or f"fonts/{fname}" not in names:
                continue
            (fdir / fname).write_bytes(z.read(f"fonts/{fname}"))
            clean[fid] = m
        existing = {}
        if (fdir / "fonts.json").exists():
            existing = json.loads((fdir / "fonts.json").read_text())
        (fdir / "fonts.json").write_text(json.dumps({**existing, **clean}, indent=1))
        restored.append("fonts")
    return {"ok": True, "restored": restored}
