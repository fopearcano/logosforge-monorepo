"""Project-scoped inline-comment endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from logosforge.api import schemas, serializers
from logosforge.api.deps import get_broker, get_db, get_project
from logosforge.api.errors import bad_request, conflict, not_found
from logosforge.api.events import ApiEventBroker
from logosforge.db import CommentRevisionConflict, Database

router = APIRouter(tags=["comments"])


def _utf16_length(value: str) -> int:
    return sum(2 if ord(char) > 0xFFFF else 1 for char in value)


def _reject_surrogate_code_units(**values: str | None) -> None:
    """Reject text that SQLite and the JSON response encoder cannot persist."""
    for field, value in values.items():
        if value is not None and any(
            0xD800 <= ord(char) <= 0xDFFF for char in value
        ):
            raise bad_request(f"{field} contains an unpaired Unicode surrogate")


def _is_utf16_boundary(value: str, offset: int) -> bool:
    current = 0
    if offset == 0:
        return True
    for char in value:
        current += _utf16_length(char)
        if current == offset:
            return True
        if current > offset:
            return False
    return False


def _comment_or_404(db: Database, project_id: int, comment_id: int):
    comment = db.get_comment_by_id(comment_id)
    if comment is None or comment.project_id != project_id:
        raise not_found(f"Comment {comment_id} not found")
    return comment


def _reply_or_404(
    db: Database, project_id: int, comment_id: int, reply_id: int,
):
    reply = db.get_comment_reply_by_id(reply_id)
    if (
        reply is None
        or reply.project_id != project_id
        or reply.comment_id != comment_id
    ):
        raise not_found(f"Comment reply {reply_id} not found")
    return reply


def _validated_anchor(
    db: Database, project_id: int, anchor: schemas.InlineCommentAnchorDTO,
) -> dict:
    start = db.get_scene_by_id(anchor.start_scene_id)
    end = db.get_scene_by_id(anchor.end_scene_id)
    if start is None or start.project_id != project_id:
        raise bad_request("start_scene_id must reference a scene in this project")
    if end is None or end.project_id != project_id:
        raise bad_request("end_scene_id must reference a scene in this project")

    start_text = str(getattr(start, anchor.start_field) or "")
    end_text = str(getattr(end, anchor.end_field) or "")
    if anchor.from_offset > _utf16_length(start_text):
        raise bad_request("from_offset is outside the start field")
    if anchor.to_offset > _utf16_length(end_text):
        raise bad_request("to_offset is outside the end field")
    if not _is_utf16_boundary(start_text, anchor.from_offset):
        raise bad_request("from_offset splits a UTF-16 surrogate pair")
    if not _is_utf16_boundary(end_text, anchor.to_offset):
        raise bad_request("to_offset splits a UTF-16 surrogate pair")

    scene_order = {
        scene.id: index for index, scene in enumerate(db.get_all_scenes(project_id))
    }
    start_key = (scene_order[start.id], 0 if anchor.start_field == "title" else 1)
    end_key = (scene_order[end.id], 0 if anchor.end_field == "title" else 1)
    if start_key > end_key:
        raise bad_request("comment anchor end must not precede its start")
    if start_key == end_key and anchor.to_offset < anchor.from_offset:
        raise bad_request("comment anchor end must not precede its start")
    return anchor.model_dump()


@router.get(
    "/projects/{project_id}/comments",
    response_model=list[schemas.InlineCommentDTO],
)
def list_comments(project=Depends(get_project), db: Database = Depends(get_db)):
    return [
        serializers.comment_to_dto(db, comment)
        for comment in db.get_all_comments(project.id)
    ]


@router.get(
    "/projects/{project_id}/comments/{comment_id}",
    response_model=schemas.InlineCommentDTO,
)
def get_comment(
    comment_id: int,
    project=Depends(get_project),
    db: Database = Depends(get_db),
):
    return serializers.comment_to_dto(
        db, _comment_or_404(db, project.id, comment_id),
    )


@router.post(
    "/projects/{project_id}/comments",
    response_model=schemas.InlineCommentDTO,
    status_code=201,
)
def create_comment(
    body: schemas.InlineCommentCreateDTO,
    project=Depends(get_project),
    db: Database = Depends(get_db),
    broker: ApiEventBroker = Depends(get_broker),
):
    _reject_surrogate_code_units(
        source_id=body.source_id,
        quote=body.quote,
        body=body.body,
        prefix=body.anchor.prefix,
        suffix=body.anchor.suffix,
    )
    for reply in body.replies:
        _reject_surrogate_code_units(
            reply_source_id=reply.source_id,
            reply_body=reply.body,
            reply_author=reply.author,
        )
    anchor = _validated_anchor(db, project.id, body.anchor)
    comment = db.create_comment_with_replies(
        project.id,
        source_id=body.source_id,
        quote=body.quote,
        body=body.body,
        resolved=body.resolved,
        replies=[reply.model_dump() for reply in body.replies],
        created_at=body.created_at,
        updated_at=body.updated_at,
        **anchor,
    )
    broker.publish("comments_changed", project_id=project.id, comment_id=comment.id)
    return serializers.comment_to_dto(db, comment)


@router.patch(
    "/projects/{project_id}/comments/{comment_id}",
    response_model=schemas.InlineCommentDTO,
)
def update_comment(
    comment_id: int,
    body: schemas.InlineCommentUpdateDTO,
    project=Depends(get_project),
    db: Database = Depends(get_db),
    broker: ApiEventBroker = Depends(get_broker),
):
    comment = _comment_or_404(db, project.id, comment_id)
    patch = body.model_dump(exclude_unset=True)
    expected_revision = patch.pop("expected_revision", None)
    anchor = None
    if body.anchor is not None:
        _reject_surrogate_code_units(
            prefix=body.anchor.prefix,
            suffix=body.anchor.suffix,
        )
        anchor = _validated_anchor(db, project.id, body.anchor)
    if body.body is not None:
        _reject_surrogate_code_units(body=body.body)
    if body.quote is not None:
        _reject_surrogate_code_units(quote=body.quote)
    kwargs = {"anchor": anchor}
    if "quote" in patch:
        kwargs["quote"] = patch["quote"]
    if "body" in patch:
        kwargs["body"] = patch["body"]
    if "resolved" in patch:
        kwargs["resolved"] = patch["resolved"]
    try:
        updated = db.update_comment(
            comment.id,
            expected_revision=expected_revision,
            **kwargs,
        )
    except CommentRevisionConflict as exc:
        raise conflict(
            "The comment thread changed after it was loaded. Read it again and create a fresh proposal.",
            code="comment_conflict",
        ) from exc
    if updated is None:
        raise not_found(f"Comment {comment_id} not found")
    broker.publish("comments_changed", project_id=project.id, comment_id=comment.id)
    return serializers.comment_to_dto(db, updated)


@router.delete(
    "/projects/{project_id}/comments/{comment_id}",
    response_model=schemas.DeleteResultDTO,
)
def delete_comment(
    comment_id: int,
    project=Depends(get_project),
    db: Database = Depends(get_db),
    broker: ApiEventBroker = Depends(get_broker),
):
    _comment_or_404(db, project.id, comment_id)
    db.delete_comment(comment_id)
    broker.publish("comments_changed", project_id=project.id, comment_id=comment_id)
    return {"ok": True, "deleted": comment_id}


@router.post(
    "/projects/{project_id}/comments/{comment_id}/replies",
    response_model=schemas.InlineCommentDTO,
    status_code=201,
)
def add_comment_reply(
    comment_id: int,
    body: schemas.CommentReplyCreateDTO,
    project=Depends(get_project),
    db: Database = Depends(get_db),
    broker: ApiEventBroker = Depends(get_broker),
):
    comment = _comment_or_404(db, project.id, comment_id)
    _reject_surrogate_code_units(
        source_id=body.source_id,
        body=body.body,
        author=body.author,
    )
    try:
        db.add_comment_reply(
            project.id,
            comment.id,
            source_id=body.source_id,
            body=body.body,
            author=body.author,
            sort_order=body.sort_order,
            created_at=body.created_at,
            expected_revision=body.expected_revision,
        )
    except CommentRevisionConflict as exc:
        raise conflict(
            "The comment thread changed after it was loaded. Read it again and create a fresh proposal.",
            code="comment_conflict",
        ) from exc
    broker.publish("comments_changed", project_id=project.id, comment_id=comment.id)
    return serializers.comment_to_dto(db, db.get_comment_by_id(comment.id))


@router.delete(
    "/projects/{project_id}/comments/{comment_id}/replies/{reply_id}",
    response_model=schemas.DeleteResultDTO,
)
def delete_comment_reply(
    comment_id: int,
    reply_id: int,
    project=Depends(get_project),
    db: Database = Depends(get_db),
    broker: ApiEventBroker = Depends(get_broker),
):
    _comment_or_404(db, project.id, comment_id)
    _reply_or_404(db, project.id, comment_id, reply_id)
    db.delete_comment_reply(reply_id)
    broker.publish("comments_changed", project_id=project.id, comment_id=comment_id)
    return {"ok": True, "deleted": reply_id}
