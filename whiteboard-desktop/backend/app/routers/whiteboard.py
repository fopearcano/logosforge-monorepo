"""Whiteboard document endpoints (GET/POST/PUT /api/whiteboard) — local store.

Desktop-only board state (no core equivalent), served from the per-document
atomic-JSON store. Each call is scoped to a document via the optional ``doc``
query param (the document/core-project id); omitting it targets the default
document (back-compat).
"""
from __future__ import annotations

from fastapi import APIRouter, Query, Request, status

from app.core_client import resolve_pid
from app.local_state import (
    WhiteboardCreate,
    WhiteboardDocument,
    WhiteboardUpdate,
    whiteboard_store,
)

router = APIRouter()


@router.get("/api/whiteboard", response_model=WhiteboardDocument)
async def get_whiteboard(request: Request, doc: int | None = Query(None)) -> WhiteboardDocument:
    pid = await resolve_pid(request.app.state.core, doc)
    return whiteboard_store.get(str(pid))


@router.post(
    "/api/whiteboard", response_model=WhiteboardDocument,
    status_code=status.HTTP_201_CREATED,
)
async def create_whiteboard(
    request: Request, payload: WhiteboardCreate, doc: int | None = Query(None)
) -> WhiteboardDocument:
    pid = await resolve_pid(request.app.state.core, doc)
    return whiteboard_store.create(str(pid), payload)


@router.put("/api/whiteboard", response_model=WhiteboardDocument)
async def update_whiteboard(
    request: Request, payload: WhiteboardUpdate, doc: int | None = Query(None)
) -> WhiteboardDocument:
    pid = await resolve_pid(request.app.state.core, doc)
    return whiteboard_store.update(str(pid), payload)
