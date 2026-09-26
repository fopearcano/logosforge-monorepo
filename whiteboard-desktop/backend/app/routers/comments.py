"""Comments endpoints (GET/POST/PUT/DELETE /api/comments) — per-document.

Inline notes anchored to block spans, scoped per document via the optional
``doc`` query param (omitting it targets the default document).
"""
from __future__ import annotations

import re
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query, Request, Response, status

from app.document_lifecycle import locked_document_request, request_document_incarnation
from app.local_state import (
    Comment,
    CommentCreate,
    CommentReplyCreate,
    CommentUpdate,
    CommentsDocument,
    MutationIdConflict,
    ResourceRevisionConflict,
    comments_store,
)
from app.resource_revision import (
    IF_MATCH_HEADER,
    MUTATION_ID_HEADER,
    RevisionPrecondition,
    mutation_id_conflict,
    request_mutation_id,
    request_revision_precondition,
    resource_etag,
    revision_conflict,
)
from app.routers.littleboy import maybe_ai_reply

router = APIRouter()
MAX_CONDITIONAL_REPLY_CHARACTERS = 100_000
_AI_MENTION_RE = re.compile(r"@(billy|logos)\b", re.IGNORECASE)


def _conditional_mode(request: Request) -> bool:
    headers = getattr(request, "headers", {})
    return (
        headers.get(IF_MATCH_HEADER) is not None
        or headers.get(IF_MATCH_HEADER.lower()) is not None
        or headers.get(MUTATION_ID_HEADER) is not None
        or headers.get(MUTATION_ID_HEADER.lower()) is not None
    )


def _conditional_preconditions(
    request: Request,
    incarnation: str,
    *,
    conditional: bool,
) -> tuple[RevisionPrecondition | None, str | None]:
    if not conditional:
        return None, None
    precondition = request_revision_precondition(
        request,
        "comments",
        incarnation,
        required=True,
    )
    mutation_id = request_mutation_id(request, required=True)
    assert precondition is not None and mutation_id is not None
    return precondition, mutation_id


def _publish_revision(
    response: Response | None,
    incarnation: str,
    revision: str,
) -> None:
    if response is not None:
        response.headers["ETag"] = resource_etag(
            "comments", incarnation, revision
        )


async def _raw_json_object(request: Request, fallback: dict) -> dict:
    """Read the original object so ignored Pydantic extras cannot evade policy."""
    reader = getattr(request, "json", None)
    if reader is None:
        return fallback
    try:
        raw = await reader()
    except (TypeError, ValueError, RuntimeError):
        raw = None
    if not isinstance(raw, dict):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="The conditional comment request body must be an object.",
        )
    return raw


async def _validate_conditional_resolution(
    request: Request,
    payload: CommentUpdate,
) -> CommentUpdate:
    raw = await _raw_json_object(
        request,
        payload.model_dump(exclude_unset=True, mode="json"),
    )
    if set(raw) != {"resolved"} or type(raw.get("resolved")) is not bool:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                "A conditional comment update must contain exactly one boolean "
                "resolved field."
            ),
        )
    return CommentUpdate(resolved=raw["resolved"])


async def _validate_conditional_reply(
    request: Request,
    payload: CommentReplyCreate,
) -> CommentReplyCreate:
    raw = await _raw_json_object(
        request,
        payload.model_dump(exclude_unset=True, mode="json"),
    )
    body = raw.get("body")
    if set(raw) != {"body"} or not isinstance(body, str):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="A conditional comment reply must contain exactly one body string.",
        )
    if not body or body.strip() != body:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="A conditional comment reply must be non-blank and trimmed.",
        )
    if len(body) > MAX_CONDITIONAL_REPLY_CHARACTERS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                "A conditional comment reply may contain at most "
                f"{MAX_CONDITIONAL_REPLY_CHARACTERS} characters."
            ),
        )
    if _AI_MENTION_RE.search(body):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                "Conditional comment replies cannot invoke @Billy or @Logos."
            ),
        )
    return CommentReplyCreate(body=body, author="MCP assistant")


@router.get("/api/comments", response_model=CommentsDocument)
async def list_comments(
    request: Request,
    doc: int | None = Query(None),
    response: Response = None,
) -> CommentsDocument:
    async with locked_document_request(request, doc) as locked:
        comments = comments_store.get(locked.document_id)
        _publish_revision(response, locked.incarnation, comments.revision)
        return comments


@router.post("/api/comments", response_model=Comment, status_code=status.HTTP_201_CREATED)
async def create_comment(
    request: Request,
    payload: CommentCreate,
    doc: int | None = Query(None),
    response: Response = None,
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
        current = comments_store.get(locked.document_id)
        _publish_revision(response, locked.incarnation, current.revision)
        return ai or created


@router.put("/api/comments/{comment_id}", response_model=Comment)
async def update_comment(
    request: Request,
    comment_id: str,
    payload: CommentUpdate,
    doc: int | None = Query(None),
    response: Response = None,
) -> Comment:
    conditional = _conditional_mode(request)
    if conditional:
        request_document_incarnation(request, required=True)
    async with locked_document_request(request, doc, mutation=True) as locked:
        precondition, mutation_id = _conditional_preconditions(
            request, locked.incarnation, conditional=conditional
        )
        if precondition is not None and not precondition.matches_resource:
            current = comments_store.get(locked.document_id)
            raise revision_conflict(
                "comments",
                locked.incarnation,
                precondition.revision,
                current.revision,
            )
        if conditional:
            payload = await _validate_conditional_resolution(request, payload)
        try:
            updated = comments_store.update(
                locked.document_id,
                comment_id,
                payload,
                expected_revision=(
                    precondition.revision if precondition is not None else None
                ),
                mutation_id=mutation_id,
            )
        except ResourceRevisionConflict as exc:
            raise revision_conflict(
                "comments",
                locked.incarnation,
                exc.expected_revision,
                exc.current_revision,
            ) from exc
        except MutationIdConflict as exc:
            raise mutation_id_conflict(exc.mutation_id) from exc
        if updated is None:
            raise HTTPException(status_code=404, detail="Comment not found")
        current = comments_store.get(locked.document_id)
        _publish_revision(response, locked.incarnation, current.revision)
        return updated


@router.delete("/api/comments/{comment_id}")
async def delete_comment(
    request: Request,
    comment_id: str,
    doc: int | None = Query(None),
    response: Response = None,
) -> dict:
    async with locked_document_request(request, doc, mutation=True) as locked:
        if not comments_store.delete_comment(locked.document_id, comment_id):
            raise HTTPException(status_code=404, detail="Comment not found")
        current = comments_store.get(locked.document_id)
        _publish_revision(response, locked.incarnation, current.revision)
        return {"ok": True, "deleted": comment_id}


@router.post(
    "/api/comments/{comment_id}/replies",
    response_model=Comment,
    status_code=status.HTTP_201_CREATED,
)
async def add_reply(
    request: Request,
    comment_id: str,
    payload: CommentReplyCreate,
    doc: int | None = Query(None),
    response: Response = None,
) -> Comment:
    conditional = _conditional_mode(request)
    if conditional:
        request_document_incarnation(request, required=True)
    async with locked_document_request(request, doc, mutation=True) as locked:
        precondition, mutation_id = _conditional_preconditions(
            request, locked.incarnation, conditional=conditional
        )
        if precondition is not None and not precondition.matches_resource:
            current = comments_store.get(locked.document_id)
            raise revision_conflict(
                "comments",
                locked.incarnation,
                precondition.revision,
                current.revision,
            )
        if conditional:
            payload = await _validate_conditional_reply(request, payload)
        reply_id = mutation_id or payload.client_id or uuid4().hex
        if conditional:
            try:
                updated = comments_store.add_reply(
                    locked.document_id,
                    comment_id,
                    reply_id,
                    payload,
                    expected_revision=(
                        precondition.revision if precondition is not None else None
                    ),
                    mutation_id=mutation_id,
                )
            except ResourceRevisionConflict as exc:
                raise revision_conflict(
                    "comments",
                    locked.incarnation,
                    exc.expected_revision,
                    exc.current_revision,
                ) from exc
            except MutationIdConflict as exc:
                raise mutation_id_conflict(exc.mutation_id) from exc
        else:
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
        result = updated
        if not conditional:
            ai = await maybe_ai_reply(
                request.app.state.core,
                locked.project_id,
                comment_id,
                payload.body,
                trigger_reply_id=reply_id,
            )
            result = ai or updated
        committed = comments_store.get(locked.document_id)
        _publish_revision(response, locked.incarnation, committed.revision)
        return result


@router.delete("/api/comments/{comment_id}/replies/{reply_id}", response_model=Comment)
async def delete_reply(
    request: Request,
    comment_id: str,
    reply_id: str,
    doc: int | None = Query(None),
    response: Response = None,
) -> Comment:
    async with locked_document_request(request, doc, mutation=True) as locked:
        updated = comments_store.delete_reply(locked.document_id, comment_id, reply_id)
        if updated is None:
            raise HTTPException(status_code=404, detail="Comment or reply not found")
        current = comments_store.get(locked.document_id)
        _publish_revision(response, locked.incarnation, current.revision)
        return updated
