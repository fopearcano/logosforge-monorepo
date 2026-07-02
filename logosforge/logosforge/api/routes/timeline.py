"""Timeline endpoints.

Timeline events are scene-derived (ordered by ``sort_order``), matching the
desktop Timeline view.  Creating/updating an event therefore creates/updates a
scene with the relevant chronology fields.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from logosforge.api import schemas, serializers
from logosforge.api.deps import get_broker, get_db, get_project
from logosforge.api.errors import not_found
from logosforge.api.events import ApiEventBroker
from logosforge.db import Database

router = APIRouter(tags=["timeline"])


@router.get(
    "/projects/{project_id}/timeline",
    response_model=list[schemas.TimelineEventDTO],
)
def get_timeline(project=Depends(get_project), db: Database = Depends(get_db)):
    return serializers.timeline_events(db, project.id)


@router.post(
    "/projects/{project_id}/timeline/events",
    response_model=schemas.TimelineEventDTO, status_code=201,
)
def create_event(
    body: schemas.TimelineEventCreateDTO,
    project=Depends(get_project),
    db: Database = Depends(get_db),
    broker: ApiEventBroker = Depends(get_broker),
):
    scene = db.create_scene(
        project.id,
        title=body.title,
        act=body.act,
        chapter=body.chapter,
        time_of_day=body.time_of_day,
        location=body.location,
        estimated_duration_minutes=body.duration_minutes,
    )
    broker.publish("timeline_changed", project_id=project.id)
    broker.publish("scenes_changed", project_id=project.id)
    return _event_dto(db, project.id, scene.id)


@router.patch(
    "/projects/{project_id}/timeline/events/{event_id}",
    response_model=schemas.TimelineEventDTO,
)
def update_event(
    event_id: int,
    body: schemas.TimelineEventUpdateDTO,
    project=Depends(get_project),
    db: Database = Depends(get_db),
    broker: ApiEventBroker = Depends(get_broker),
):
    scene = db.get_scene_by_id(event_id)
    if scene is None or scene.project_id != project.id:
        raise not_found(f"Timeline event {event_id} not found")
    patch = body.model_dump(exclude_unset=True)
    db.update_scene(
        event_id,
        title=patch.get("title", scene.title),
        summary=scene.summary,
        synopsis=scene.synopsis,
        goal=scene.goal,
        conflict=scene.conflict,
        outcome=scene.outcome,
        beat=scene.beat,
        tags=scene.tags,
        act=patch.get("act", scene.act),
        content=scene.content,
        chapter=patch.get("chapter", scene.chapter),
        plotline=scene.plotline,
        time_of_day=patch.get("time_of_day"),
        location=patch.get("location"),
        estimated_duration_minutes=patch.get("duration_minutes"),
        # Preserve associations update_scene would otherwise replace.
        character_ids=db.get_scene_character_ids(event_id),
        place_ids=db.get_scene_place_ids(event_id),
        character_states=db.get_scene_character_states(event_id),
    )
    if patch.get("sort_order") is not None:
        db.reorder_scene(event_id, patch["sort_order"])
    broker.publish("timeline_changed", project_id=project.id)
    return _event_dto(db, project.id, event_id)


def _event_dto(db: Database, project_id: int, scene_id: int):
    for event in serializers.timeline_events(db, project_id):
        if event.id == scene_id:
            return event
    raise not_found(f"Timeline event {scene_id} not found")
