"""Comments endpoints (GET/POST/PUT/DELETE /api/comments) — per-document.

Inline notes anchored to block spans, scoped per document via the optional
``doc`` query param (omitting it targets the default document).
"""
from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query, Request, status

from app.core_client import resolve_pid
from app.local_state import (
    Comment,
    CommentCreate,
    CommentReplyCreate,
    CommentUpdate,
    CommentsDocument,
    comments_store,
)
from app.routers.littleboy import maybe_ai_reply

router = APIRouter()


@router.get("/api/comments", response_model=CommentsDocument)
async def list_comments(request: Request, doc: int | None = Query(None)) -> CommentsDocument:
    pid = await resolve_pid(request.app.state.core, doc)
    return comments_store.get(str(pid))


@router.post("/api/comments", response_model=Comment, status_code=status.HTTP_201_CREATED)
async def create_comment(
    request: Request, payload: CommentCreate, doc: int | None = Query(None)
) -> Comment:
    # A comment must anchor to selected text — the quote is what re-locates the
    # span after edits. An empty quote (only possible from a malformed client)
    # would store a comment that can never re-anchor, so reject it up front.
    if not payload.quote.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="A comment must anchor to selected text (quote must not be empty).",
        )
    pid = await resolve_pid(request.app.state.core, doc)
    created = comments_store.create(str(pid), uuid4().hex, payload)
    ai = await maybe_ai_reply(request.app.state.core, pid, created.id, payload.body)
    return ai or created


@router.put("/api/comments/{comment_id}", response_model=Comment)
async def update_comment(
    request: Request, comment_id: str, payload: CommentUpdate, doc: int | None = Query(None)
) -> Comment:
    pid = await resolve_pid(request.app.state.core, doc)
    updated = comments_store.update(str(pid), comment_id, payload)
    if updated is None:
        raise HTTPException(status_code=404, detail="Comment not found")
    return updated


@router.delete("/api/comments/{comment_id}")
async def delete_comment(
    request: Request, comment_id: str, doc: int | None = Query(None)
) -> dict:
    pid = await resolve_pid(request.app.state.core, doc)
    if not comments_store.delete_comment(str(pid), comment_id):
        raise HTTPException(status_code=404, detail="Comment not found")
    return {"ok": True, "deleted": comment_id}


@router.post(
    "/api/comments/{comment_id}/replies",
    response_model=Comment,
    status_code=status.HTTP_201_CREATED,
)
async def add_reply(
    request: Request, comment_id: str, payload: CommentReplyCreate, doc: int | None = Query(None)
) -> Comment:
    pid = await resolve_pid(request.app.state.core, doc)
    updated = comments_store.add_reply(str(pid), comment_id, uuid4().hex, payload)
    if updated is None:
        raise HTTPException(status_code=404, detail="Comment not found")
    ai = await maybe_ai_reply(request.app.state.core, pid, comment_id, payload.body)
    return ai or updated


@router.delete("/api/comments/{comment_id}/replies/{reply_id}", response_model=Comment)
async def delete_reply(
    request: Request, comment_id: str, reply_id: str, doc: int | None = Query(None)
) -> Comment:
    pid = await resolve_pid(request.app.state.core, doc)
    updated = comments_store.delete_reply(str(pid), comment_id, reply_id)
    if updated is None:
        raise HTTPException(status_code=404, detail="Comment or reply not found")
    return updated
