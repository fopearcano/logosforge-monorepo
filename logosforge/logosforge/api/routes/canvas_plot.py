"""Revisioned, project-owned Canvas Plot endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Response
from fastapi.responses import JSONResponse

from logosforge.api import schemas, serializers
from logosforge.api.deps import get_broker, get_db, get_project
from logosforge.api.errors import bad_request, conflict, not_found
from logosforge.api.events import ApiEventBroker
from logosforge.db import (
    CanvasPlotCommandError,
    CanvasPlotFrameNotFound,
    CanvasPlotIdempotencyKeyConflict,
    CanvasPlotLinkNotFound,
    CanvasPlotNodeNotFound,
    CanvasPlotProjectNotFound,
    CanvasPlotRevisionConflict,
    CanvasPlotSceneNotFound,
    Database,
)

router = APIRouter(tags=["canvas-plot"])

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
    "/projects/{project_id}/canvas-plot",
    response_model=schemas.CanvasPlotSnapshotDTO,
)
def get_canvas_plot(project=Depends(get_project), db: Database = Depends(get_db)):
    snapshot = db.read_canvas_plot_snapshot(project.id)
    if snapshot is None:
        raise not_found(f"Project {project.id} not found")
    return serializers.canvas_plot_snapshot_to_dto(snapshot)


@router.post(
    "/projects/{project_id}/canvas-plot/commands",
    response_model=schemas.CanvasPlotCommandResultDTO,
)
def execute_canvas_plot_command(
    body: schemas.CanvasPlotCommandDTO,
    idempotency_key: Annotated[
        str | None,
        Header(alias="Idempotency-Key"),
    ] = None,
    project=Depends(get_project),
    db: Database = Depends(get_db),
    broker: ApiEventBroker = Depends(get_broker),
):
    """Run one optimistic-concurrency guarded board command atomically."""
    command = body.root
    payload = command.model_dump(exclude_unset=True)
    kind = payload.pop("kind")
    try:
        result = db.execute_canvas_plot_command(
            project.id,
            kind=kind,
            idempotency_key=idempotency_key,
            **payload,
        )
    except CanvasPlotIdempotencyKeyConflict as exc:
        raise conflict(
            "This Idempotency-Key was already used for a different Canvas Plot command.",
            code="idempotency_key_conflict",
        ) from exc
    except CanvasPlotRevisionConflict as exc:
        raise conflict(
            "The Canvas Plot changed after it was loaded. Reload it and retry the command.",
            code="canvas_plot_conflict",
        ) from exc
    except CanvasPlotProjectNotFound as exc:
        raise not_found(f"Project {project.id} not found") from exc
    except CanvasPlotNodeNotFound as exc:
        missing = exc.args[0] if exc.args else payload.get("node_id")
        raise not_found(f"Canvas Plot node {missing} not found") from exc
    except CanvasPlotLinkNotFound as exc:
        missing = exc.args[0] if exc.args else payload.get("link_id")
        raise not_found(f"Canvas Plot link {missing} not found") from exc
    except CanvasPlotFrameNotFound as exc:
        missing = exc.args[0] if exc.args else payload.get("frame_id")
        raise not_found(f"Canvas Plot frame {missing} not found") from exc
    except CanvasPlotSceneNotFound as exc:
        missing = exc.args[0] if exc.args else payload.get("scene_id")
        raise not_found(f"Scene {missing} not found") from exc
    except CanvasPlotCommandError as exc:
        raise bad_request(str(exc)) from exc

    broker.reconcile()

    return schemas.CanvasPlotCommandResultDTO(
        canvas_plot=serializers.canvas_plot_snapshot_to_dto(result.snapshot),
        changed=result.changed,
        affected_node_ids=list(result.affected_node_ids),
        affected_link_ids=list(result.affected_link_ids),
        affected_frame_ids=list(result.affected_frame_ids),
        created_node_id=result.created_node_id,
        created_link_id=result.created_link_id,
        created_frame_id=result.created_frame_id,
        replayed=result.replayed,
        applied_revision=result.applied_revision or result.snapshot.revision,
    )


@router.get(
    "/projects/{project_id}/canvas-plot/command-receipt",
    response_model=schemas.CanvasPlotCommandReceiptDTO,
)
def get_canvas_plot_command_receipt(
    response: Response,
    idempotency_key: Annotated[
        str | None,
        Header(alias="Idempotency-Key"),
    ] = None,
    project=Depends(get_project),
    db: Database = Depends(get_db),
):
    """Resolve one successfully committed Canvas command by capability."""
    if idempotency_key is None:
        return _receipt_error(
            400,
            "bad_request",
            "Idempotency-Key is required",
        )
    try:
        receipt = db.get_canvas_plot_command_receipt(
            project.id,
            idempotency_key,
        )
    except CanvasPlotCommandError as exc:
        return _receipt_error(400, "bad_request", str(exc))
    if receipt is None:
        return _receipt_error(
            404,
            "canvas_plot_receipt_not_found",
            "No committed Canvas Plot command exists for this Idempotency-Key.",
        )
    response.headers.update(_RECEIPT_RESPONSE_HEADERS)
    return schemas.CanvasPlotCommandReceiptDTO(
        project_id=receipt.project_id,
        request_digest=receipt.request_digest,
        command_kind=receipt.kind,
        expected_revision=receipt.expected_revision,
        applied_revision=receipt.applied_revision,
        original_changed=receipt.original_changed,
        original_affected_node_ids=list(receipt.original_affected_node_ids),
        original_affected_link_ids=list(receipt.original_affected_link_ids),
        original_affected_frame_ids=list(receipt.original_affected_frame_ids),
        original_created_node_id=receipt.original_created_node_id,
        original_created_link_id=receipt.original_created_link_id,
        original_created_frame_id=receipt.original_created_frame_id,
        committed_at=receipt.created_at,
    )
