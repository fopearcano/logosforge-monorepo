"""Theme <-> scene links — the structured scene-tagging behind theme presence.

Lets a frontend read and set which scenes a PSYKE ``theme`` entry is tagged in, so
themes can read present in the narrative dashboard the way characters do (via real
``SceneThemeLink`` rows) instead of relying on prose name-matching.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from logosforge.api import schemas
from logosforge.api.deps import get_broker, get_db, get_project
from logosforge.api.errors import bad_request, not_found
from logosforge.api.events import ApiEventBroker
from logosforge.db import Database

router = APIRouter(tags=["themes"])


def _theme_or_404(db: Database, project_id: int, entry_id: int):
    entry = db.get_psyke_entry_by_id(entry_id)
    if entry is None or entry.project_id != project_id:
        raise not_found(f"Theme entry {entry_id} not found")
    if (entry.entry_type or "").lower() != "theme":
        raise bad_request("entry must be a 'theme' PSYKE entry")
    return entry


@router.get(
    "/projects/{project_id}/themes/{entry_id}/scenes",
    response_model=schemas.ThemeScenesDTO,
)
def get_theme_scenes(entry_id: int, project=Depends(get_project), db: Database = Depends(get_db)):
    _theme_or_404(db, project.id, entry_id)
    scene_ids = [
        scene_id
        for scene_id in db.get_theme_scene_ids(entry_id)
        if (
            (scene := db.get_scene_by_id(scene_id)) is not None
            and scene.project_id == project.id
        )
    ]
    return schemas.ThemeScenesDTO(entry_id=entry_id, scene_ids=scene_ids)


@router.put(
    "/projects/{project_id}/themes/{entry_id}/scenes",
    response_model=schemas.ThemeScenesDTO,
)
def set_theme_scenes(
    entry_id: int,
    body: schemas.ThemeScenesUpdateDTO,
    project=Depends(get_project),
    db: Database = Depends(get_db),
    broker: ApiEventBroker = Depends(get_broker),
):
    """Replace the full set of scenes this theme is tagged in.

    Missing ids are ignored for backward compatibility with stale clients;
    existing scenes owned by another project are rejected.
    """
    _theme_or_404(db, project.id, entry_id)
    scene_ids: list[int] = []
    for scene_id in body.scene_ids:
        scene = db.get_scene_by_id(scene_id)
        if scene is None:
            continue
        if scene.project_id != project.id:
            raise not_found(f"Scene {scene_id} not found")
        scene_ids.append(scene_id)
    db.set_theme_scenes(entry_id, scene_ids)
    broker.publish("psyke_changed", project_id=project.id)
    broker.publish("project_data_changed", project_id=project.id)
    return get_theme_scenes(entry_id, project=project, db=db)
