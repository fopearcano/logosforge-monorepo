"""Revisioned, scene-backed Timeline endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Response
from fastapi.responses import JSONResponse

from logosforge.api import schemas, serializers
from logosforge.api.deps import get_broker, get_db, get_project
from logosforge.api.errors import bad_request, conflict, not_found
from logosforge.api.events import ApiEventBroker
from logosforge.db import (
    Database,
    TimelineCommandError,
    TimelineIdempotencyKeyConflict,
    TimelineLaneNotFound,
    TimelineProjectNotFound,
    TimelineRevisionConflict,
    TimelineSceneNotFound,
)

router = APIRouter(tags=["timeline"])

_RECEIPT_RESPONSE_HEADERS = {
    "Cache-Control": "no-store",
    "Vary": "Authorization, Idempotency-Key",
}


def _receipt_error(status_code: int, code: str, message: str) -> JSONResponse:
    """Return capability-bound receipt errors without cacheable misses."""
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message}},
        headers=_RECEIPT_RESPONSE_HEADERS,
    )


@router.get(
    "/projects/{project_id}/timeline",
    response_model=schemas.TimelineSnapshotDTO,
)
def get_timeline(project=Depends(get_project), db: Database = Depends(get_db)):
    snapshot = db.read_timeline_snapshot(project.id)
    if snapshot is None:
        raise not_found(f"Project {project.id} not found")
    return serializers.timeline_snapshot_to_dto(snapshot)


@router.post(
    "/projects/{project_id}/timeline/commands",
    response_model=schemas.TimelineCommandResultDTO,
)
def execute_timeline_command(
    body: schemas.TimelineCommandDTO,
    idempotency_key: Annotated[
        str | None,
        Header(alias="Idempotency-Key"),
    ] = None,
    project=Depends(get_project),
    db: Database = Depends(get_db),
    broker: ApiEventBroker = Depends(get_broker),
):
    """Run one optimistic-concurrency guarded Timeline command atomically."""
    command = body.root
    payload = command.model_dump(exclude_unset=True)
    kind = payload.pop("kind")
    try:
        result = db.execute_timeline_command(
            project.id,
            kind=kind,
            idempotency_key=idempotency_key,
            **payload,
        )
    except TimelineIdempotencyKeyConflict as exc:
        raise conflict(
            "This Idempotency-Key was already used for a different Timeline command.",
            code="idempotency_key_conflict",
        ) from exc
    except TimelineRevisionConflict as exc:
        raise conflict(
            "The Timeline changed after it was loaded. Reload it and retry the command.",
            code="timeline_conflict",
        ) from exc
    except TimelineProjectNotFound as exc:
        raise not_found(f"Project {project.id} not found") from exc
    except TimelineSceneNotFound as exc:
        missing = exc.args[0] if exc.args else payload.get("scene_id")
        raise not_found(f"Scene {missing} not found") from exc
    except TimelineLaneNotFound as exc:
        missing = exc.args[0] if exc.args else payload.get("lane_id")
        raise not_found(f"Timeline lane {missing} not found") from exc
    except TimelineCommandError as exc:
        raise bad_request(str(exc)) from exc

    if result.changed and not result.replayed:
        for scene_id in result.affected_scene_ids:
            broker.publish(
                "scene_changed", project_id=project.id, scene_id=scene_id,
            )
        if result.affected_scene_ids:
            broker.publish("plot_changed", project_id=project.id)
        broker.publish("timeline_changed", project_id=project.id)

    return schemas.TimelineCommandResultDTO(
        timeline=serializers.timeline_snapshot_to_dto(result.snapshot),
        changed=result.changed,
        affected_scene_ids=list(result.affected_scene_ids),
        replayed=result.replayed,
        applied_revision=result.applied_revision or result.snapshot.revision,
    )


@router.get(
    "/projects/{project_id}/timeline/command-receipt",
    response_model=schemas.TimelineCommandReceiptDTO,
)
def get_timeline_command_receipt(
    response: Response,
    idempotency_key: Annotated[
        str | None,
        Header(alias="Idempotency-Key"),
    ] = None,
    project=Depends(get_project),
    db: Database = Depends(get_db),
):
    """Resolve one successfully committed Timeline command by capability."""
    if idempotency_key is None:
        return _receipt_error(
            400,
            "bad_request",
            "Idempotency-Key is required",
        )
    try:
        receipt = db.get_timeline_command_receipt(project.id, idempotency_key)
    except TimelineCommandError as exc:
        return _receipt_error(400, "bad_request", str(exc))
    if receipt is None:
        return _receipt_error(
            404,
            "timeline_receipt_not_found",
            "No committed Timeline command exists for this Idempotency-Key.",
        )
    response.headers.update(_RECEIPT_RESPONSE_HEADERS)
    return schemas.TimelineCommandReceiptDTO(
        project_id=receipt.project_id,
        request_digest=receipt.request_digest,
        command_kind=receipt.kind,
        expected_revision=receipt.expected_revision,
        applied_revision=receipt.applied_revision,
        original_changed=receipt.original_changed,
        original_affected_scene_ids=list(
            receipt.original_affected_scene_ids,
        ),
        committed_at=receipt.created_at,
    )
