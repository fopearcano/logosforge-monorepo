"""First-class transactional Progressions endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Response
from fastapi.responses import JSONResponse

from logosforge.api import schemas, serializers
from logosforge.api.deps import get_broker, get_db, get_project
from logosforge.api.errors import ApiError, bad_request, conflict, not_found
from logosforge.api.events import ApiEventBroker
from logosforge.db import (
    Database,
    ProgressionBeatNotFound,
    ProgressionCommandError,
    ProgressionIdempotencyKeyConflict,
    ProgressionProjectNotFound,
    ProgressionPsykeEntryNotFound,
    ProgressionRevisionConflict,
    ProgressionSceneNotFound,
    ProgressionStateCorrupt,
    ProgressionTrackNotFound,
)

router = APIRouter(tags=["progressions"])

_RECEIPT_RESPONSE_HEADERS = {
    "Cache-Control": "no-store",
    "Vary": "Authorization, Idempotency-Key",
}


def _state_corrupt_error() -> ApiError:
    return ApiError(
        500,
        "Progressions state is inconsistent. Repair it before editing.",
        code="progression_state_corrupt",
    )


def _receipt_error(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message}},
        headers=_RECEIPT_RESPONSE_HEADERS,
    )


@router.get(
    "/projects/{project_id}/progressions",
    response_model=schemas.ProgressionSnapshotDTO,
)
def get_progressions(
    project=Depends(get_project),
    db: Database = Depends(get_db),
):
    try:
        snapshot = db.read_progression_snapshot(project.id)
    except ProgressionStateCorrupt as exc:
        raise _state_corrupt_error() from exc
    if snapshot is None:
        raise not_found(f"Project {project.id} not found")
    return serializers.progression_snapshot_to_dto(snapshot)


@router.post(
    "/projects/{project_id}/progressions/commands",
    response_model=schemas.ProgressionCommandResultDTO,
)
def execute_progression_command(
    body: schemas.ProgressionCommandDTO,
    idempotency_key: Annotated[
        str | None,
        Header(alias="Idempotency-Key"),
    ] = None,
    project=Depends(get_project),
    db: Database = Depends(get_db),
    broker: ApiEventBroker = Depends(get_broker),
):
    command = body.root
    payload = command.model_dump(exclude_unset=True)
    kind = payload.pop("kind")
    try:
        result = db.execute_progression_command(
            project.id,
            kind=kind,
            idempotency_key=idempotency_key,
            **payload,
        )
    except ProgressionIdempotencyKeyConflict as exc:
        raise conflict(
            "This Idempotency-Key was already used for a different "
            "Progressions command.",
            code="idempotency_key_conflict",
        ) from exc
    except ProgressionRevisionConflict as exc:
        raise conflict(
            "Progressions changed after they were loaded. Reload and retry.",
            code="progression_conflict",
        ) from exc
    except ProgressionProjectNotFound as exc:
        raise not_found(f"Project {project.id} not found") from exc
    except ProgressionTrackNotFound as exc:
        missing = exc.args[0] if exc.args else payload.get("track_id")
        raise ApiError(
            404,
            f"Progression track {missing} not found",
            code="progression_track_not_found",
        ) from exc
    except ProgressionBeatNotFound as exc:
        missing = exc.args[0] if exc.args else payload.get("beat_id")
        raise ApiError(
            404,
            f"Progression beat {missing} not found",
            code="progression_beat_not_found",
        ) from exc
    except ProgressionSceneNotFound as exc:
        missing = exc.args[0] if exc.args else payload.get("scene_id")
        raise ApiError(
            404,
            f"Scene {missing} not found",
            code="progression_scene_not_found",
        ) from exc
    except ProgressionPsykeEntryNotFound as exc:
        missing = exc.args[0] if exc.args else None
        raise ApiError(
            404,
            f"PSYKE entry {missing} not found",
            code="progression_psyke_entry_not_found",
        ) from exc
    except ProgressionStateCorrupt as exc:
        raise _state_corrupt_error() from exc
    except ProgressionCommandError as exc:
        raise bad_request(str(exc)) from exc

    broker.reconcile()
    return schemas.ProgressionCommandResultDTO(
        progressions=serializers.progression_snapshot_to_dto(result.snapshot),
        changed=result.changed,
        affected_track_ids=list(result.affected_track_ids),
        affected_beat_ids=list(result.affected_beat_ids),
        created_track_id=result.created_track_id,
        created_beat_id=result.created_beat_id,
        replayed=result.replayed,
        applied_revision=result.applied_revision or result.snapshot.revision,
    )


@router.get(
    "/projects/{project_id}/progressions/command-receipt",
    response_model=schemas.ProgressionCommandReceiptDTO,
)
def get_progression_command_receipt(
    response: Response,
    idempotency_key: Annotated[
        str | None,
        Header(alias="Idempotency-Key"),
    ] = None,
    project=Depends(get_project),
    db: Database = Depends(get_db),
):
    if idempotency_key is None:
        return _receipt_error(400, "bad_request", "Idempotency-Key is required")
    try:
        receipt = db.get_progression_command_receipt(
            project.id, idempotency_key,
        )
    except ProgressionCommandError as exc:
        return _receipt_error(400, "bad_request", str(exc))
    if receipt is None:
        return _receipt_error(
            404,
            "progression_receipt_not_found",
            "No committed Progressions command exists for this Idempotency-Key.",
        )
    response.headers.update(_RECEIPT_RESPONSE_HEADERS)
    return schemas.ProgressionCommandReceiptDTO(
        project_id=receipt.project_id,
        request_digest=receipt.request_digest,
        command_kind=receipt.kind,
        expected_revision=receipt.expected_revision,
        applied_revision=receipt.applied_revision,
        original_changed=receipt.original_changed,
        original_affected_track_ids=list(receipt.original_affected_track_ids),
        original_affected_beat_ids=list(receipt.original_affected_beat_ids),
        original_created_track_id=receipt.original_created_track_id,
        original_created_beat_id=receipt.original_created_beat_id,
        committed_at=receipt.created_at,
    )
