"""PSYKE story-bible endpoints: entries, relations, progressions, search."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from logosforge.api import schemas, serializers
from logosforge.api.deps import get_broker, get_db, get_project
from logosforge.api.errors import bad_request, not_found
from logosforge.api.events import ApiEventBroker
from logosforge.db import Database

router = APIRouter(tags=["psyke"])


def _csv(values):
    return ", ".join(values) if values else ""


def _entry_or_404(db: Database, project_id: int, entry_id: int):
    entry = db.get_psyke_entry_by_id(entry_id)
    if entry is None or entry.project_id != project_id:
        raise not_found(f"PSYKE entry {entry_id} not found")
    return entry


# -- Entries -----------------------------------------------------------------


@router.get(
    "/projects/{project_id}/psyke/entries",
    response_model=list[schemas.PsykeEntryDTO],
)
def list_entries(project=Depends(get_project), db: Database = Depends(get_db)):
    return [
        serializers.psyke_entry_to_dto(db, e)
        for e in db.get_all_psyke_entries(project.id)
    ]


@router.post(
    "/projects/{project_id}/psyke/entries",
    response_model=schemas.PsykeEntryDTO, status_code=201,
)
def create_entry(
    body: schemas.PsykeEntryCreateDTO,
    project=Depends(get_project),
    db: Database = Depends(get_db),
    broker: ApiEventBroker = Depends(get_broker),
):
    entry = db.create_psyke_entry(
        project.id,
        name=body.name,
        entry_type=body.type,
        aliases=_csv(body.aliases),
        notes=body.notes,
        is_global=body.is_global,
        details=body.details,
    )
    broker.publish("psyke_changed", project_id=project.id, entry_id=entry.id)
    return serializers.psyke_entry_to_dto(db, entry)


@router.get(
    "/projects/{project_id}/psyke/entries/{entry_id}",
    response_model=schemas.PsykeEntryDTO,
)
def get_entry(entry_id: int, project=Depends(get_project), db: Database = Depends(get_db)):
    return serializers.psyke_entry_to_dto(db, _entry_or_404(db, project.id, entry_id))


@router.patch(
    "/projects/{project_id}/psyke/entries/{entry_id}",
    response_model=schemas.PsykeEntryDTO,
)
def update_entry(
    entry_id: int,
    body: schemas.PsykeEntryUpdateDTO,
    project=Depends(get_project),
    db: Database = Depends(get_db),
    broker: ApiEventBroker = Depends(get_broker),
):
    entry = _entry_or_404(db, project.id, entry_id)
    patch = body.model_dump(exclude_unset=True)
    db.update_psyke_entry(
        entry_id,
        name=patch.get("name", entry.name),
        entry_type=patch.get("type", entry.entry_type),
        aliases=_csv(patch["aliases"]) if "aliases" in patch else entry.aliases,
        notes=patch.get("notes", entry.notes),
        is_global=patch.get("is_global", entry.is_global),
        details=patch.get("details", db.get_psyke_entry_details(entry_id)),
    )
    broker.publish("psyke_changed", project_id=project.id, entry_id=entry_id)
    return serializers.psyke_entry_to_dto(db, db.get_psyke_entry_by_id(entry_id))


@router.delete("/projects/{project_id}/psyke/entries/{entry_id}")
def delete_entry(
    entry_id: int,
    project=Depends(get_project),
    db: Database = Depends(get_db),
    broker: ApiEventBroker = Depends(get_broker),
):
    _entry_or_404(db, project.id, entry_id)
    db.delete_psyke_entry(entry_id)
    broker.publish("psyke_changed", project_id=project.id, entry_id=entry_id)
    return {"ok": True, "deleted": entry_id}


# -- Relations ---------------------------------------------------------------


@router.get(
    "/projects/{project_id}/psyke/relations",
    response_model=list[schemas.PsykeRelationDTO],
)
def list_relations(project=Depends(get_project), db: Database = Depends(get_db)):
    return serializers.psyke_relations(db, project.id)


@router.post(
    "/projects/{project_id}/psyke/relations",
    response_model=schemas.PsykeRelationDTO, status_code=201,
)
def create_relation(
    body: schemas.PsykeRelationCreateDTO,
    project=Depends(get_project),
    db: Database = Depends(get_db),
    broker: ApiEventBroker = Depends(get_broker),
):
    _entry_or_404(db, project.id, body.source_id)
    _entry_or_404(db, project.id, body.target_id)
    if body.source_id == body.target_id:
        raise bad_request("A relation needs two distinct entries")
    db.add_psyke_relation(body.source_id, body.target_id, relation_type=body.relation_type)
    broker.publish("psyke_changed", project_id=project.id, entry_id=body.source_id)
    source = db.get_psyke_entry_by_id(body.source_id)
    target = db.get_psyke_entry_by_id(body.target_id)
    return schemas.PsykeRelationDTO(
        id=f"{body.source_id}:{body.target_id}",
        source_id=body.source_id,
        target_id=body.target_id,
        source=source.name if source else "",
        target=target.name if target else "",
        relation_type=body.relation_type,
    )


@router.delete("/projects/{project_id}/psyke/relations/{relation_id}")
def delete_relation(
    relation_id: str,
    project=Depends(get_project),
    db: Database = Depends(get_db),
    broker: ApiEventBroker = Depends(get_broker),
):
    try:
        source_id, target_id = (int(x) for x in relation_id.split(":", 1))
    except ValueError:
        raise bad_request("relation_id must be '<source_id>:<target_id>'")
    _entry_or_404(db, project.id, source_id)
    _entry_or_404(db, project.id, target_id)
    db.remove_psyke_relation(source_id, target_id)
    broker.publish("psyke_changed", project_id=project.id, entry_id=source_id)
    return {"ok": True, "deleted": relation_id}


# -- Progressions ------------------------------------------------------------


@router.get(
    "/projects/{project_id}/psyke/progressions",
    response_model=list[schemas.PsykeProgressionDTO],
)
def list_progressions(project=Depends(get_project), db: Database = Depends(get_db)):
    return serializers.psyke_progressions(db, project.id)


@router.post(
    "/projects/{project_id}/psyke/progressions",
    response_model=schemas.PsykeProgressionDTO, status_code=201,
)
def create_progression(
    body: schemas.PsykeProgressionCreateDTO,
    project=Depends(get_project),
    db: Database = Depends(get_db),
    broker: ApiEventBroker = Depends(get_broker),
):
    _entry_or_404(db, project.id, body.entry_id)
    prog = db.create_psyke_progression(body.entry_id, body.text, scene_id=body.scene_id)
    broker.publish("psyke_changed", project_id=project.id, entry_id=body.entry_id)
    return serializers.progression_to_dto(db, project.id, prog, body.entry_id)


@router.patch(
    "/projects/{project_id}/psyke/progressions/{progression_id}",
    response_model=schemas.PsykeProgressionDTO,
)
def update_progression(
    progression_id: int,
    body: schemas.PsykeProgressionUpdateDTO,
    project=Depends(get_project),
    db: Database = Depends(get_db),
    broker: ApiEventBroker = Depends(get_broker),
):
    """Edit an arc-progression beat's text and/or the scene it anchors to."""
    prog = db.update_psyke_progression(progression_id, body.text, scene_id=body.scene_id)
    broker.publish("psyke_changed", project_id=project.id, entry_id=prog.entry_id)
    return serializers.progression_to_dto(db, project.id, prog, prog.entry_id)


@router.delete("/projects/{project_id}/psyke/progressions/{progression_id}")
def delete_progression(
    progression_id: int,
    project=Depends(get_project),
    db: Database = Depends(get_db),
    broker: ApiEventBroker = Depends(get_broker),
):
    """Remove an arc-progression beat."""
    db.delete_psyke_progression(progression_id)
    broker.publish("psyke_changed", project_id=project.id)
    return {"ok": True, "deleted": progression_id}


# -- Search ------------------------------------------------------------------


@router.get(
    "/projects/{project_id}/psyke/search",
    response_model=list[schemas.PsykeEntryDTO],
)
def search_psyke(
    q: str = Query("", description="Case-insensitive name/alias/notes match"),
    project=Depends(get_project),
    db: Database = Depends(get_db),
):
    needle = q.strip().lower()
    results = []
    for e in db.get_all_psyke_entries(project.id):
        haystack = " ".join([e.name or "", e.aliases or "", e.notes or ""]).lower()
        if not needle or needle in haystack:
            results.append(serializers.psyke_entry_to_dto(db, e))
    return results
