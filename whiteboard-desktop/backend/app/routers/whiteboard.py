"""Whiteboard document endpoints (GET/POST/PUT /api/whiteboard) — local store.

Desktop-only board state (no core equivalent), served from the per-document
atomic-JSON store. Each call is scoped to a document via the optional ``doc``
query param (the document/core-project id); omitting it targets the default
document (back-compat).
"""
from __future__ import annotations

from fastapi import APIRouter, Query, Request, status

from app.document_lifecycle import locked_document_request
from app.local_state import (
    WhiteboardCreate,
    WhiteboardDocument,
    WhiteboardUpdate,
    whiteboard_store,
)
from app.persistence_order import accept_persistence_write, request_persistence_order

router = APIRouter()


@router.get("/api/whiteboard", response_model=WhiteboardDocument)
async def get_whiteboard(request: Request, doc: int | None = Query(None)) -> WhiteboardDocument:
    async with locked_document_request(request, doc) as locked:
        return whiteboard_store.get(locked.document_id)


@router.post(
    "/api/whiteboard", response_model=WhiteboardDocument,
    status_code=status.HTTP_201_CREATED,
)
async def create_whiteboard(
    request: Request, payload: WhiteboardCreate, doc: int | None = Query(None)
) -> WhiteboardDocument:
    async with locked_document_request(request, doc, mutation=True) as locked:
        return whiteboard_store.create(locked.document_id, payload)


@router.put("/api/whiteboard", response_model=WhiteboardDocument)
async def update_whiteboard(
    request: Request, payload: WhiteboardUpdate, doc: int | None = Query(None)
) -> WhiteboardDocument:
    async with locked_document_request(request, doc, mutation=True) as locked:
        order = request_persistence_order(request)
        with accept_persistence_write("whiteboard", locked.document_id, order) as accepted:
            if not accepted:
                return whiteboard_store.get(locked.document_id)
            return whiteboard_store.update(locked.document_id, payload)
