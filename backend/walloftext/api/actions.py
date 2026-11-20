"""/api/actions: quick actions (the same functions the button gestures use)."""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from .. import actions

router = APIRouter(prefix="/api/actions")


@router.get("")
async def list_actions(request: Request):
    svc = request.app.state.svc
    out = [{"id": k, "label": v} for k, v in actions.ACTIONS.items()]
    sched = svc.extras.get("scheduler")
    if sched:
        out += [{"id": f"routine:{r['id']}", "label": f"Run routine: {r['name']}"} for r in sched.routines()]
    return out


@router.post("/{action}")
async def run_action(action: str, request: Request):
    svc = request.app.state.svc
    if action not in actions.ACTIONS and not action.startswith("routine:"):
        return JSONResponse({"error": "unknown_action"}, status_code=404)
    msg = await actions.run(svc, action, source="Manual")
    return {"ok": True, "message": msg}
