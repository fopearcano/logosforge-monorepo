"""Comments endpoints (GET/POST/PUT/DELETE /api/comments) — per-document.

Inline notes anchored to block spans, scoped per document via the optional
``doc`` query param (omitting it targets the default document).
"""
from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query, Request, status

from app.document_lifecycle import locked_document_request
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
    async with locked_document_request(request, doc) as locked:
        return comments_store.get(locked.document_id)


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
    async with locked_document_request(request, doc, mutation=True) as locked:
        created = comments_store.create(locked.document_id, uuid4().hex, payload)
        ai = await maybe_ai_reply(
            request.app.state.core,
            locked.project_id,
            created.id,
            payload.body,
        )
        return ai or created


@router.put("/api/comments/{comment_id}", response_model=Comment)
async def update_comment(
    request: Request, comment_id: str, payload: CommentUpdate, doc: int | None = Query(None)
) -> Comment:
    async with locked_document_request(request, doc, mutation=True) as locked:
        updated = comments_store.update(locked.document_id, comment_id, payload)
        if updated is None:
            raise HTTPException(status_code=404, detail="Comment not found")
        return updated


@router.delete("/api/comments/{comment_id}")
async def delete_comment(
    request: Request, comment_id: str, doc: int | None = Query(None)
) -> dict:
    async with locked_document_request(request, doc, mutation=True) as locked:
        if not comments_store.delete_comment(locked.document_id, comment_id):
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
    async with locked_document_request(request, doc, mutation=True) as locked:
        reply_id = payload.client_id or uuid4().hex
        current = comments_store.get(locked.document_id)
        existing_comment = next(
            (comment for comment in current.comments if comment.id == comment_id),
            None,
        )
        if existing_comment is not None:
            existing_reply = next(
                (reply for reply in existing_comment.replies if reply.id == reply_id),
                None,
            )
            if existing_reply is not None:
                if (
                    existing_reply.body != payload.body
                    or existing_reply.author != (payload.author or "you")
                ):
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="Reply id already belongs to different content",
                    )
                updated = existing_comment
            else:
                updated = comments_store.add_reply(
                    locked.document_id,
                    comment_id,
                    reply_id,
                    payload,
                )
        else:
            updated = comments_store.add_reply(
                locked.document_id,
                comment_id,
                reply_id,
                payload,
            )
        if updated is None:
            raise HTTPException(status_code=404, detail="Comment not found")
        ai = await maybe_ai_reply(
            request.app.state.core,
            locked.project_id,
            comment_id,
            payload.body,
            trigger_reply_id=reply_id,
        )
        return ai or updated


@router.delete("/api/comments/{comment_id}/replies/{reply_id}", response_model=Comment)
async def delete_reply(
    request: Request, comment_id: str, reply_id: str, doc: int | None = Query(None)
) -> Comment:
    async with locked_document_request(request, doc, mutation=True) as locked:
        updated = comments_store.delete_reply(locked.document_id, comment_id, reply_id)
        if updated is None:
            raise HTTPException(status_code=404, detail="Comment or reply not found")
        return updated
