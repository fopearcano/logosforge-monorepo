"""Guided Workflow / Project OS reads and atomic lifecycle commands."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Response
from fastapi.responses import JSONResponse

from logosforge.api import schemas, serializers
from logosforge.api.deps import get_broker, get_db, get_project
from logosforge.api.errors import bad_request, conflict, not_found
from logosforge.api.events import ApiEventBroker
from logosforge.db import (
    Database,
    WorkflowCommandError,
    WorkflowIdempotencyKeyConflict,
    WorkflowProjectNotFound,
    WorkflowRevisionConflict,
    WorkflowRunNotFound,
    WorkflowStateConflict,
    WorkflowStepNotFound,
)
from logosforge.guided_workflows import engine
from logosforge.guided_workflows.recommendations import (
    build_workflow_recommendations,
)
from logosforge.guided_workflows.registry import list_workflow_templates
from logosforge.writing_modes import get_project_writing_mode

router = APIRouter(tags=["workflows"])

_RECEIPT_RESPONSE_HEADERS = {
    "Cache-Control": "no-store",
    "Vary": "Authorization, Idempotency-Key",
}


def _receipt_error(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message}},
        headers=_RECEIPT_RESPONSE_HEADERS,
    )


@router.get(
    "/projects/{project_id}/workflow-templates",
    response_model=list[schemas.WorkflowTemplateDTO],
)
def get_workflow_templates(project=Depends(get_project)):
    """Built-in templates available for this project's writing mode."""
    mode = get_project_writing_mode(project)
    return [
        serializers.workflow_template_to_dto(template, mode=mode)
        for template in list_workflow_templates(mode)
    ]


@router.get(
    "/projects/{project_id}/workflow-recommendations",
    response_model=list[schemas.WorkflowRecommendationDTO],
)
def get_workflow_recommendations(
    project=Depends(get_project),
    db: Database = Depends(get_db),
):
    """Deterministic recommendations, excluding already-active templates."""
    return [
        serializers.workflow_recommendation_to_dto(recommendation)
        for recommendation in build_workflow_recommendations(db, project.id)
    ]


@router.get(
    "/projects/{project_id}/workflows",
    response_model=list[schemas.WorkflowRunDTO],
)
def get_workflows(project=Depends(get_project), db: Database = Depends(get_db)):
    snapshots = db.read_workflow_runs_snapshot(project.id)
    if snapshots is None:
        raise not_found(f"Project {project.id} not found")
    return [
        serializers.workflow_run_to_dto(
            engine.workflow_run_view_from_snapshot(snapshot)
        )
        for snapshot in snapshots
    ]


@router.get(
    "/projects/{project_id}/workflows/command-receipt",
    response_model=schemas.WorkflowCommandReceiptDTO,
)
def get_workflow_command_receipt(
    response: Response,
    idempotency_key: Annotated[
        str | None,
        Header(alias="Idempotency-Key"),
    ] = None,
    project=Depends(get_project),
    db: Database = Depends(get_db),
):
    if idempotency_key is None:
        return _receipt_error(
            400, "bad_request", "Idempotency-Key is required",
        )
    try:
        receipt = db.get_workflow_command_receipt(
            project.id, idempotency_key,
        )
    except WorkflowCommandError as exc:
        return _receipt_error(400, "bad_request", str(exc))
    if receipt is None:
        return _receipt_error(
            404,
            "workflow_receipt_not_found",
            "No committed Guided Workflow command exists for this Idempotency-Key.",
        )
    response.headers.update(_RECEIPT_RESPONSE_HEADERS)
    return schemas.WorkflowCommandReceiptDTO(
        project_id=receipt.project_id,
        request_digest=receipt.request_digest,
        command_kind=receipt.kind,
        expected_revision=receipt.expected_revision,
        applied_revision=receipt.applied_revision,
        original_changed=receipt.original_changed,
        original_run_id=receipt.run_id,
        committed_at=receipt.created_at,
    )


@router.get(
    "/projects/{project_id}/workflows/{run_id}",
    response_model=schemas.WorkflowRunDTO,
)
def get_workflow_run(
    run_id: int,
    project=Depends(get_project),
    db: Database = Depends(get_db),
):
    snapshot = db.read_workflow_run_snapshot(project.id, run_id)
    if snapshot is None:
        raise not_found("Workflow run not found")
    return serializers.workflow_run_to_dto(
        engine.workflow_run_view_from_snapshot(snapshot)
    )


@router.get(
    "/projects/{project_id}/workflows/{run_id}/events",
    response_model=list[schemas.WorkflowEventDTO],
)
def get_workflow_events(
    run_id: int,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    project=Depends(get_project),
    db: Database = Depends(get_db),
):
    events = db.get_project_workflow_events(
        project.id, run_id, limit=limit,
    )
    if events is None:
        raise not_found("Workflow run not found")
    return [serializers.workflow_event_to_dto(event) for event in events]


@router.post(
    "/projects/{project_id}/workflows/commands",
    response_model=schemas.WorkflowCommandResultDTO,
)
def execute_workflow_command(
    body: schemas.WorkflowCommandDTO,
    idempotency_key: Annotated[
        str | None,
        Header(alias="Idempotency-Key"),
    ] = None,
    project=Depends(get_project),
    db: Database = Depends(get_db),
    broker: ApiEventBroker = Depends(get_broker),
):
    """Apply one optimistic-concurrency guarded workflow transition."""
    if idempotency_key is None:
        raise bad_request("Idempotency-Key is required")
    payload = body.root.model_dump(exclude_none=True)
    kind = payload.pop("kind")
    expected_revision = payload.pop("expected_revision", "")
    try:
        result = db.execute_workflow_command(
            project.id,
            kind=kind,
            idempotency_key=idempotency_key,
            expected_revision=expected_revision,
            **payload,
        )
    except WorkflowIdempotencyKeyConflict as exc:
        raise conflict(
            "This Idempotency-Key was already used for a different Guided Workflow command.",
            code="idempotency_key_conflict",
        ) from exc
    except WorkflowRevisionConflict as exc:
        raise conflict(
            "The workflow changed after it was loaded. Reload it and retry.",
            code="workflow_conflict",
        ) from exc
    except WorkflowStateConflict as exc:
        raise conflict(str(exc), code="workflow_state_conflict") from exc
    except WorkflowProjectNotFound as exc:
        raise not_found(f"Project {project.id} not found") from exc
    except WorkflowRunNotFound as exc:
        raise not_found("Workflow run not found") from exc
    except WorkflowStepNotFound as exc:
        raise not_found("Workflow step not found") from exc
    except WorkflowCommandError as exc:
        raise bad_request(str(exc)) from exc

    if result.changed and not result.replayed:
        broker.publish(
            "workflow_changed",
            project_id=project.id,
            run_id=int(result.snapshot.run.id),
            command_kind=kind,
            revision=result.snapshot.revision,
        )
    view = engine.workflow_run_view_from_snapshot(result.snapshot)
    return schemas.WorkflowCommandResultDTO(
        workflow=serializers.workflow_run_to_dto(view),
        changed=result.changed,
        replayed=result.replayed,
        applied_revision=result.applied_revision,
    )
