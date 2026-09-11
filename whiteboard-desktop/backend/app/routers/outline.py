"""Manual story-outliner endpoints (GET/PUT /api/outline/items) — local store.

The node shape is owned by the frontend (stored opaquely). Scoped per document
via the optional ``doc`` query param (omitting it targets the default document).
"""
from __future__ import annotations

from fastapi import APIRouter, Query, Request

from app.document_lifecycle import locked_document_request
from app.local_state import OutlineItemsDocument, outline_items_store
from app.persistence_order import accept_persistence_write, request_persistence_order

router = APIRouter()


@router.get("/api/outline/items", response_model=OutlineItemsDocument)
async def get_outline_items(request: Request, doc: int | None = Query(None)) -> OutlineItemsDocument:
    async with locked_document_request(request, doc) as locked:
        return OutlineItemsDocument(items=outline_items_store.get(locked.document_id))


@router.put("/api/outline/items", response_model=OutlineItemsDocument)
async def put_outline_items(
    request: Request, payload: OutlineItemsDocument, doc: int | None = Query(None)
) -> OutlineItemsDocument:
    async with locked_document_request(request, doc, mutation=True) as locked:
        order = request_persistence_order(request)
        with accept_persistence_write("outline", locked.document_id, order) as accepted:
            if not accepted:
                return OutlineItemsDocument(items=outline_items_store.get(locked.document_id))
            return OutlineItemsDocument(
                items=outline_items_store.replace(locked.document_id, payload.items),
            )
