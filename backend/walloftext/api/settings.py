"""/api/settings: every settings group as one document."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

router = APIRouter(prefix="/api")


@router.get("/settings")
async def get_settings(request: Request):
    return request.app.state.svc.app_settings.all()


@router.patch("/settings")
async def patch_settings(changes: dict[str, Any], request: Request):
    return request.app.state.svc.app_settings.patch(changes)
