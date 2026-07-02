"""Document library — list / create / delete whiteboard documents.

A whiteboard 'document' is one core project (for its ISOLATED PSYKE bible) plus a
local blocks file + outline file keyed by that project id. These routes manage the
SET of documents; the per-document blocks/outline/psyke are served by the scoped
routes via the ``?doc=<id>`` query param.
"""
from __future__ import annotations

import httpx
from fastapi import APIRouter, HTTPException, Request

from app.local_state import (
    WhiteboardCreate,
    comments_store,
    outline_items_store,
    whiteboard_store,
)

router = APIRouter()


@router.get("/api/documents")
async def list_documents() -> dict:
    """List every document (summary only — no blocks), most-recently-edited first."""
    return {"documents": [s.model_dump() for s in whiteboard_store.list_summaries()]}


@router.post("/api/documents", status_code=201)
async def create_document(request: Request, body: WhiteboardCreate) -> dict:
    """Create a new document: a fresh core project (its own PSYKE bible) + an empty
    local blocks file keyed by that project id. Returns the new document."""
    core = request.app.state.core
    title = (body.title or "Untitled").strip() or "Untitled"
    proj = await core.create_project(title)
    doc_id = str(proj["id"])
    doc = whiteboard_store.create(
        doc_id, WhiteboardCreate(title=title, mode=body.mode, blocks=body.blocks)
    )
    return {"ok": True, "document": doc.model_dump()}


@router.delete("/api/documents/{doc_id}")
async def delete_document(request: Request, doc_id: int) -> dict:
    """Delete a document: its core project (cascades the PSYKE bible) + its local
    blocks and outline files. Tolerant of an already-deleted core project."""
    core = request.app.state.core
    try:
        await core.delete_project(doc_id)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code != 404:
            raise HTTPException(status_code=502, detail="core project delete failed")
    whiteboard_store.delete(str(doc_id))
    outline_items_store.delete(str(doc_id))
    comments_store.delete(str(doc_id))
    return {"ok": True, "deleted": str(doc_id)}
