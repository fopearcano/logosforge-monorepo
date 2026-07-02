"""Manuscript Characters — list + Character <-> PSYKE bible link management.

Exposes the manuscript cast and the stable ``Character.psyke_entry_id`` link so a
frontend can read which characters are bound to which bible entries and manage
that binding directly: set/clear the link, or trigger the name-based auto-linker.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from logosforge.api import schemas, serializers
from logosforge.api.deps import get_broker, get_db, get_project
from logosforge.api.errors import bad_request, not_found
from logosforge.api.events import ApiEventBroker
from logosforge.db import Database

router = APIRouter(tags=["characters"])


def _char_or_404(db: Database, project_id: int, character_id: int):
    character = db.get_character_by_id(character_id)
    if character is None or character.project_id != project_id:
        raise not_found(f"Character {character_id} not found")
    return character


@router.get(
    "/projects/{project_id}/characters",
    response_model=list[schemas.CharacterDTO],
)
def list_characters(project=Depends(get_project), db: Database = Depends(get_db)):
    return [serializers.character_to_dto(db, c) for c in db.get_all_characters(project.id)]


@router.patch(
    "/projects/{project_id}/characters/{character_id}",
    response_model=schemas.CharacterDTO,
)
def update_character(
    character_id: int,
    body: schemas.CharacterUpdateDTO,
    project=Depends(get_project),
    db: Database = Depends(get_db),
    broker: ApiEventBroker = Depends(get_broker),
):
    """Update a character's name/description and/or its PSYKE bible link. Sending
    ``psyke_entry_id: null`` explicitly clears the link."""
    character = _char_or_404(db, project.id, character_id)
    patch = body.model_dump(exclude_unset=True)

    # A requested link target must be a 'character' PSYKE entry in this project.
    if patch.get("psyke_entry_id") is not None:
        entry = db.get_psyke_entry_by_id(patch["psyke_entry_id"])
        if entry is None or entry.project_id != project.id:
            raise bad_request("psyke_entry_id must be a PSYKE entry in this project")
        if (entry.entry_type or "").lower() != "character":
            raise bad_request("psyke_entry_id must reference a 'character' PSYKE entry")

    # Treat an explicit null for name/description as "leave unchanged" — name is a
    # NOT NULL column, so a null must never reach the writer (would 500), and a
    # null description should not silently clobber the current value.
    def _merged(field: str, current: str) -> str:
        value = patch.get(field)
        return current if value is None else value

    if "name" in patch or "description" in patch:
        db.update_character(
            character_id,
            name=_merged("name", character.name),
            description=_merged("description", character.description),
        )
    if "psyke_entry_id" in patch:  # present (incl. explicit null) => set / clear
        db.set_character_psyke_entry(character_id, patch["psyke_entry_id"])

    broker.publish("characters_changed", project_id=project.id)
    return serializers.character_to_dto(db, db.get_character_by_id(character_id))


@router.post("/projects/{project_id}/characters/backfill-links")
def backfill_character_links(
    project=Depends(get_project),
    db: Database = Depends(get_db),
    broker: ApiEventBroker = Depends(get_broker),
):
    """Auto-link any still-unlinked Characters to their PSYKE 'character' entry by
    name (idempotent). Returns the number of links newly written."""
    linked = db.backfill_character_psyke_links(project.id)
    if linked:
        broker.publish("characters_changed", project_id=project.id)
    return {"ok": True, "linked": linked}
