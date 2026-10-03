"""Revisioned, scene-backed Timeline endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from logosforge.api import schemas, serializers
from logosforge.api.deps import get_broker, get_db, get_project
from logosforge.api.errors import bad_request, conflict, not_found
from logosforge.api.events import ApiEventBroker
from logosforge.db import (
    Database,
    TimelineCommandError,
    TimelineLaneNotFound,
    TimelineProjectNotFound,
    TimelineRevisionConflict,
    TimelineSceneNotFound,
)

router = APIRouter(tags=["timeline"])


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
    project=Depends(get_project),
    db: Database = Depends(get_db),
    broker: ApiEventBroker = Depends(get_broker),
):
    """Run one optimistic-concurrency guarded Timeline command atomically."""
    command = body.root
    payload = command.model_dump(exclude_unset=True)
    kind = payload.pop("kind")
    try:
        result = db.execute_timeline_command(project.id, kind=kind, **payload)
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

    if result.changed:
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
    )
