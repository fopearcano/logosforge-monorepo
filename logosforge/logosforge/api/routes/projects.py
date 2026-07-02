"""Project lifecycle, listing and settings."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from logosforge.api import schemas, serializers
from logosforge.api.deps import get_broker, get_db, get_project
from logosforge.api.events import ApiEventBroker
from logosforge.db import Database

router = APIRouter(tags=["projects"])


@router.get("/projects", response_model=list[schemas.ProjectDTO])
def list_projects(db: Database = Depends(get_db)):
    return [serializers.project_to_dto(p) for p in db.get_all_projects()]


@router.post("/projects", response_model=schemas.ProjectDTO, status_code=201)
def create_project(
    body: schemas.ProjectCreateDTO,
    db: Database = Depends(get_db),
    broker: ApiEventBroker = Depends(get_broker),
):
    project = db.create_project(
        body.title,
        narrative_engine=body.narrative_engine,
        default_writing_format=body.default_writing_format,
    )
    if body.description:
        db.update_project(project.id, description=body.description)
        project = db.get_project_by_id(project.id)
    broker.publish("project_data_changed", project_id=project.id)
    return serializers.project_to_dto(project)


@router.get("/projects/{project_id}", response_model=schemas.ProjectDTO)
def get_project_detail(project=Depends(get_project)):
    return serializers.project_to_dto(project)


@router.post("/projects/{project_id}/open", response_model=schemas.ProjectDTO)
def open_project(
    project=Depends(get_project),
    broker: ApiEventBroker = Depends(get_broker),
):
    broker.publish("project_loaded", project_id=project.id)
    return serializers.project_to_dto(project)


@router.post("/projects/{project_id}/save")
def save_project(
    project=Depends(get_project),
    broker: ApiEventBroker = Depends(get_broker),
):
    # SQLite changes are committed eagerly, so "save" is a checkpoint signal
    # for clients rather than a flush.  Kept for transport parity with the
    # desktop file-save lifecycle.
    broker.publish("project_data_changed", project_id=project.id)
    return {"ok": True, "project_id": project.id}


@router.post("/projects/{project_id}/close")
def close_project(
    project=Depends(get_project),
    broker: ApiEventBroker = Depends(get_broker),
):
    broker.publish("project_data_changed", project_id=project.id)
    return {"ok": True, "project_id": project.id}


@router.delete("/projects/{project_id}")
def delete_project(
    project=Depends(get_project),
    db: Database = Depends(get_db),
    broker: ApiEventBroker = Depends(get_broker),
):
    """Delete a project and ALL of its data (generic cascade)."""
    pid = project.id
    db.delete_project(pid)
    broker.publish("project_data_changed", project_id=pid)
    return {"ok": True, "deleted": pid}


@router.get("/projects/{project_id}/settings", response_model=schemas.SettingsDTO)
def get_settings(project=Depends(get_project), db: Database = Depends(get_db)):
    return schemas.SettingsDTO(settings=db.get_project_settings(project.id))


@router.patch("/projects/{project_id}/settings", response_model=schemas.SettingsDTO)
def patch_settings(
    body: schemas.SettingsDTO,
    project=Depends(get_project),
    db: Database = Depends(get_db),
    broker: ApiEventBroker = Depends(get_broker),
):
    current = db.get_project_settings(project.id)
    current.update(body.settings)
    db.save_project_settings(project.id, current)
    broker.publish("project_data_changed", project_id=project.id)
    return schemas.SettingsDTO(settings=current)
