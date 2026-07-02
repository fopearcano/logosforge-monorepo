"""Manual story-outliner endpoints (GET/PUT /api/outline/items) — local store.

The node shape is owned by the frontend (stored opaquely). Scoped per document
via the optional ``doc`` query param (omitting it targets the default document).
"""
from __future__ import annotations

from fastapi import APIRouter, Query, Request

from app.core_client import resolve_pid
from app.local_state import OutlineItemsDocument, outline_items_store

router = APIRouter()


@router.get("/api/outline/items", response_model=OutlineItemsDocument)
async def get_outline_items(request: Request, doc: int | None = Query(None)) -> OutlineItemsDocument:
    pid = await resolve_pid(request.app.state.core, doc)
    return OutlineItemsDocument(items=outline_items_store.get(str(pid)))


@router.put("/api/outline/items", response_model=OutlineItemsDocument)
async def put_outline_items(
    request: Request, payload: OutlineItemsDocument, doc: int | None = Query(None)
) -> OutlineItemsDocument:
    pid = await resolve_pid(request.app.state.core, doc)
    return OutlineItemsDocument(items=outline_items_store.replace(str(pid), payload.items))
