"""Complete-project snapshot boundary for Pro cloud-folder synchronization."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends

from logosforge.api import schemas
from logosforge.api.deps import get_broker, get_db, get_project
from logosforge.api.errors import bad_request, conflict, not_found
from logosforge.api.events import ApiEventBroker
from logosforge.db import Database
from logosforge.project_cloud_snapshot import (
    ProjectCloudSnapshotConflict,
    ProjectCloudSnapshotError,
    ProjectCloudSnapshotNotFound,
    apply_project_cloud_snapshot,
    build_project_cloud_snapshot,
)

router = APIRouter(tags=["cloud-sync"])

ProjectDependency = Annotated[Any, Depends(get_project)]
DatabaseDependency = Annotated[Database, Depends(get_db)]
BrokerDependency = Annotated[ApiEventBroker, Depends(get_broker)]


def _snapshot_or_api_error(db: Database, project_id: int) -> dict:
    try:
        return build_project_cloud_snapshot(db, project_id)
    except ProjectCloudSnapshotNotFound as exc:
        raise not_found(str(exc)) from exc
    except ProjectCloudSnapshotError as exc:
        raise bad_request(str(exc)) from exc


@router.get(
    "/projects/{project_id}/cloud-sync/snapshot",
    response_model=schemas.CloudProjectSnapshotDTO,
)
def get_cloud_snapshot(
    project: ProjectDependency,
    db: DatabaseDependency,
):
    return _snapshot_or_api_error(db, project.id)


@router.post(
    "/cloud-sync/projects/import",
    response_model=schemas.CloudProjectApplyResultDTO,
    status_code=201,
)
def import_cloud_snapshot(
    body: schemas.CloudProjectImportDTO,
    db: DatabaseDependency,
    broker: BrokerDependency,
):
    try:
        result = apply_project_cloud_snapshot(
            db,
            body.snapshot.model_dump(mode="json"),
            mode=body.mode,
            restore_id=body.restore_id,
        )
    except ProjectCloudSnapshotConflict as exc:
        raise conflict(str(exc), code="cloud_sync_conflict") from exc
    except ProjectCloudSnapshotError as exc:
        raise bad_request(str(exc)) from exc
    snapshot = _snapshot_or_api_error(db, result.project_id)
    broker.publish("project_data_changed", project_id=result.project_id)
    return schemas.CloudProjectApplyResultDTO(
        project_id=result.project_id,
        project_identity=result.project_identity,
        digest=snapshot["digest"],
        mode=result.mode,
    )

@router.post(
    "/projects/{project_id}/cloud-sync/restore",
    response_model=schemas.CloudProjectApplyResultDTO,
)
def restore_cloud_snapshot(
    body: schemas.CloudProjectRestoreDTO,
    project: ProjectDependency,
    db: DatabaseDependency,
    broker: BrokerDependency,
):
    try:
        result = apply_project_cloud_snapshot(
            db,
            body.snapshot.model_dump(mode="json"),
            mode="replace",
            target_project_id=project.id,
            expected_current_digest=body.expected_current_digest,
            restore_id=body.restore_id,
        )
    except ProjectCloudSnapshotNotFound as exc:
        raise not_found(str(exc)) from exc
    except ProjectCloudSnapshotConflict as exc:
        raise conflict(str(exc), code="cloud_sync_conflict") from exc
    except ProjectCloudSnapshotError as exc:
        raise bad_request(str(exc)) from exc
    snapshot = _snapshot_or_api_error(db, result.project_id)
    broker.publish("project_data_changed", project_id=result.project_id)
    broker.publish("project_loaded", project_id=result.project_id)
    return schemas.CloudProjectApplyResultDTO(
        project_id=result.project_id,
        project_identity=result.project_identity,
        digest=snapshot["digest"],
        mode=result.mode,
    )

