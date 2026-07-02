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
    return schemas.ThemeScenesDTO(entry_id=entry_id, scene_ids=db.get_theme_scene_ids(entry_id))


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
    """Replace the full set of scenes this theme is tagged in. Scene ids not in this
    project are ignored (never cross-project links)."""
    _theme_or_404(db, project.id, entry_id)
    valid = {s.id for s in db.get_all_scenes(project.id)}
    scene_ids = [sid for sid in body.scene_ids if sid in valid]
    db.set_theme_scenes(entry_id, scene_ids)
    broker.publish("psyke_changed", project_id=project.id)
    broker.publish("project_data_changed", project_id=project.id)
    return schemas.ThemeScenesDTO(entry_id=entry_id, scene_ids=db.get_theme_scene_ids(entry_id))
