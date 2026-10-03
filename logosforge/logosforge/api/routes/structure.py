"""Canonical, scene-derived story-structure endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from logosforge.api import schemas, serializers
from logosforge.api.deps import get_broker, get_db, get_project
from logosforge.api.errors import bad_request, conflict, not_found
from logosforge.api.events import ApiEventBroker
from logosforge.db import (
    Database,
    StoryStructureEpisodeNotFound,
    StoryStructurePlacementError,
    StoryStructureProjectNotFound,
    StoryStructureRevisionConflict,
    StoryStructureSceneNotFound,
)

router = APIRouter(tags=["structure"])


@router.get(
    "/projects/{project_id}/story-structure",
    response_model=schemas.StoryStructureDTO,
)
def get_story_structure(
    project=Depends(get_project),
    db: Database = Depends(get_db),
):
    """Return the core-owned Act -> Chapter -> Scene manuscript hierarchy."""
    snapshot = db.read_story_structure_snapshot(project.id)
    if snapshot is None:
        raise not_found(f"Project {project.id} not found")
    return serializers.story_structure_snapshot_to_dto(snapshot)


@router.put(
    "/projects/{project_id}/story-structure/scenes/{scene_id}/placement",
    response_model=schemas.StoryStructureDTO,
)
def place_scene_in_story_structure(
    scene_id: int,
    body: schemas.StoryStructurePlacementDTO,
    project=Depends(get_project),
    db: Database = Depends(get_db),
    broker: ApiEventBroker = Depends(get_broker),
):
    """Revision-guarded atomic scene reorder/reparent operation."""
    try:
        result = db.place_scene_in_structure(
            project.id,
            scene_id,
            expected_revision=body.expected_revision,
            act=body.act,
            chapter=body.chapter,
            index=body.index,
            episode_id=body.episode_id,
            update_episode="episode_id" in body.model_fields_set,
        )
    except StoryStructureRevisionConflict as exc:
        raise conflict(
            "The story structure changed after it was loaded. Reload it and retry the move.",
            code="structure_conflict",
        ) from exc
    except (StoryStructureSceneNotFound, StoryStructureProjectNotFound) as exc:
        raise not_found(f"Scene {scene_id} not found") from exc
    except StoryStructureEpisodeNotFound as exc:
        episode_id = exc.args[0] if exc.args else body.episode_id
        raise not_found(f"Episode {episode_id} not found") from exc
    except StoryStructurePlacementError as exc:
        raise bad_request(str(exc)) from exc

    if result.changed:
        broker.publish(
            "scene_changed", project_id=project.id, scene_id=scene_id,
        )
        broker.publish("scenes_changed", project_id=project.id)
    return serializers.story_structure_snapshot_to_dto(result.snapshot)
