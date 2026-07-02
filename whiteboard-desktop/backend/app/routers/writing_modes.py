"""GET /api/writing-modes — pass-through to the core writing-modes catalog.

The core route already returns the exact ``WritingModesResponse`` the frontend
expects ({modes:[{id,label,structural_units,default_writing_format,
medium_constraints}], default_mode}), so the wrapper just forwards it — no shape
translation, and (unlike the old standalone backend) no duplicated mode data.
"""
from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/api/writing-modes")
async def writing_modes(request: Request):
    core = request.app.state.core
    return (await core.request("GET", "/api/writing-modes")).json()
