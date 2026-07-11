"""Scenes / manuscript endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from logosforge.api import schemas, serializers
from logosforge.api.deps import get_broker, get_db, get_project
from logosforge.api.errors import not_found
from logosforge.api.events import ApiEventBroker
from logosforge.db import Database

router = APIRouter(tags=["scenes"])


def _csv(values):
    return ", ".join(values) if values else ""


@router.get("/projects/{project_id}/scenes", response_model=list[schemas.SceneDTO])
def list_scenes(project=Depends(get_project), db: Database = Depends(get_db)):
    return serializers.scenes_to_dtos(db, db.get_all_scenes(project.id))


@router.post(
    "/projects/{project_id}/scenes",
    response_model=schemas.SceneDTO, status_code=201,
)
def create_scene(
    body: schemas.SceneCreateDTO,
    project=Depends(get_project),
    db: Database = Depends(get_db),
    broker: ApiEventBroker = Depends(get_broker),
):
    scene = db.create_scene(
        project.id,
        title=body.title,
        summary=body.summary,
        synopsis=body.synopsis,
        goal=body.goal,
        conflict=body.conflict,
        outcome=body.outcome,
        beat=body.beat,
        tags=_csv(body.tags),
        act=body.act,
        content=body.content,
        chapter=body.chapter,
        plotline=body.plotline,
        character_ids=body.character_ids or None,
        place_ids=body.place_ids or None,
    )
    broker.publish("scene_changed", project_id=project.id, scene_id=scene.id)
    broker.publish("scenes_changed", project_id=project.id)
    return serializers.scene_to_dto(db, scene)


@router.get(
    "/projects/{project_id}/scenes/{scene_id}",
    response_model=schemas.SceneDTO,
)
def get_scene(scene_id: int, project=Depends(get_project), db: Database = Depends(get_db)):
    scene = db.get_scene_by_id(scene_id)
    if scene is None or scene.project_id != project.id:
        raise not_found(f"Scene {scene_id} not found")
    return serializers.scene_to_dto(db, scene)


@router.patch(
    "/projects/{project_id}/scenes/{scene_id}",
    response_model=schemas.SceneDTO,
)
def update_scene(
    scene_id: int,
    body: schemas.SceneUpdateDTO,
    project=Depends(get_project),
    db: Database = Depends(get_db),
    broker: ApiEventBroker = Depends(get_broker),
):
    scene = db.get_scene_by_id(scene_id)
    if scene is None or scene.project_id != project.id:
        raise not_found(f"Scene {scene_id} not found")

    patch = body.model_dump(exclude_unset=True)

    def merged(field: str, current):
        if field not in patch or patch[field] is None:
            return current
        return patch[field]

    # core text fields default to "" in update_scene, so pass the merged
    # current values to avoid clobbering unspecified fields.
    db.update_scene(
        scene_id,
        title=merged("title", scene.title),
        summary=merged("summary", scene.summary),
        synopsis=merged("synopsis", scene.synopsis),
        goal=merged("goal", scene.goal),
        conflict=merged("conflict", scene.conflict),
        outcome=merged("outcome", scene.outcome),
        beat=merged("beat", scene.beat),
        tags=_csv(patch["tags"]) if "tags" in patch and patch["tags"] is not None else scene.tags,
        act=merged("act", scene.act),
        content=merged("content", scene.content),
        chapter=merged("chapter", scene.chapter),
        plotline=merged("plotline", scene.plotline),
        color_label=patch.get("color_label"),  # None = leave unchanged
        time_of_day=patch.get("time_of_day"),
        location=patch.get("location"),
        estimated_duration_minutes=patch.get("estimated_duration_minutes"),
        who_knows_what=patch.get("who_knows_what"),  # feeds the graph "knowledge" edge
        offstage_events=patch.get("offstage_events"),  # feeds the graph "offstage" edge
        # update_scene unconditionally replaces these associations, so pass the
        # current values to preserve them across a partial PATCH.
        character_ids=db.get_scene_character_ids(scene_id),
        place_ids=db.get_scene_place_ids(scene_id),
        character_states=db.get_scene_character_states(scene_id),
    )
    if patch.get("sort_order") is not None:
        db.reorder_scene(scene_id, patch["sort_order"])

    broker.publish("scene_changed", project_id=project.id, scene_id=scene_id)
    return serializers.scene_to_dto(db, db.get_scene_by_id(scene_id))


@router.delete("/projects/{project_id}/scenes/{scene_id}")
def delete_scene(
    scene_id: int,
    project=Depends(get_project),
    db: Database = Depends(get_db),
    broker: ApiEventBroker = Depends(get_broker),
):
    scene = db.get_scene_by_id(scene_id)
    if scene is None or scene.project_id != project.id:
        raise not_found(f"Scene {scene_id} not found")
    db.delete_scene(scene_id)
    broker.publish("scenes_changed", project_id=project.id)
    return {"ok": True, "deleted": scene_id}


def _scene_or_404(db: Database, project_id: int, scene_id: int):
    scene = db.get_scene_by_id(scene_id)
    if scene is None or scene.project_id != project_id:
        raise not_found(f"Scene {scene_id} not found")
    return scene


def _continuity_dto(m) -> schemas.ContinuityMemoryDTO:
    mt = m.memory_type or ""
    kind = mt[len("continuity_"):] if mt.startswith("continuity_") else "state"
    return schemas.ContinuityMemoryDTO(id=m.id, scene_id=m.scene_id, target=m.target, value=m.value, kind=kind or "state")


@router.get(
    "/projects/{project_id}/scenes/{scene_id}/continuity",
    response_model=list[schemas.ContinuityMemoryDTO],
)
def list_continuity(scene_id: int, project=Depends(get_project), db: Database = Depends(get_db)):
    _scene_or_404(db, project.id, scene_id)
    return [_continuity_dto(m) for m in db.get_memories(project.id, scene_id)
            if (m.memory_type or "").startswith("continuity_")]


@router.post(
    "/projects/{project_id}/scenes/{scene_id}/continuity",
    response_model=schemas.ContinuityMemoryDTO,
)
def add_continuity(
    scene_id: int,
    body: schemas.ContinuityMemoryDTO,
    project=Depends(get_project),
    db: Database = Depends(get_db),
    broker: ApiEventBroker = Depends(get_broker),
):
    """Pin a continuity note to a scene. Stored as memory_type ``continuity_<kind>``;
    consecutive scenes sharing the same (target, kind) form a graph 'continuity' edge."""
    _scene_or_404(db, project.id, scene_id)
    kind = (body.kind or "state").strip() or "state"
    m = db.add_memory(project.id, scene_id, f"continuity_{kind}", body.target, body.value)
    broker.publish("scene_changed", project_id=project.id, scene_id=scene_id)
    return _continuity_dto(m)


@router.patch(
    "/projects/{project_id}/scenes/{scene_id}/continuity/{memory_id}",
    response_model=schemas.ContinuityMemoryDTO,
)
def update_continuity(
    scene_id: int,
    memory_id: int,
    body: schemas.ContinuityMemoryDTO,
    project=Depends(get_project),
    db: Database = Depends(get_db),
    broker: ApiEventBroker = Depends(get_broker),
):
    """Edit a pinned continuity note's target/value (and kind → memory_type)."""
    _scene_or_404(db, project.id, scene_id)
    fields: dict = {"target": body.target, "value": body.value}
    if body.kind:
        fields["memory_type"] = f"continuity_{(body.kind or 'state').strip() or 'state'}"
    db.update_continuity_memory(memory_id, **fields)
    broker.publish("scene_changed", project_id=project.id, scene_id=scene_id)
    for m in db.get_memories(project.id, scene_id):
        if m.id == memory_id:
            return _continuity_dto(m)
    raise not_found(f"Continuity note {memory_id} not found")


@router.delete("/projects/{project_id}/scenes/{scene_id}/continuity/{memory_id}")
def delete_continuity(
    scene_id: int,
    memory_id: int,
    project=Depends(get_project),
    db: Database = Depends(get_db),
    broker: ApiEventBroker = Depends(get_broker),
):
    """Remove a pinned continuity note."""
    _scene_or_404(db, project.id, scene_id)
    db.delete_continuity_memory(memory_id)
    broker.publish("scene_changed", project_id=project.id, scene_id=scene_id)
    return {"ok": True, "deleted": memory_id}
