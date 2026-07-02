"""Notes endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from logosforge.api import schemas, serializers
from logosforge.api.deps import get_broker, get_db, get_project
from logosforge.api.errors import not_found
from logosforge.api.events import ApiEventBroker
from logosforge.db import Database

router = APIRouter(tags=["notes"])


def _csv(values):
    return ", ".join(values) if values else ""


def _note_or_404(db: Database, project_id: int, note_id: int):
    note = db.get_note_by_id(note_id)
    if note is None or note.project_id != project_id:
        raise not_found(f"Note {note_id} not found")
    return note


@router.get("/projects/{project_id}/notes", response_model=list[schemas.NoteDTO])
def list_notes(project=Depends(get_project), db: Database = Depends(get_db)):
    return [serializers.note_to_dto(db, n) for n in db.get_all_notes(project.id)]


@router.post(
    "/projects/{project_id}/notes",
    response_model=schemas.NoteDTO, status_code=201,
)
def create_note(
    body: schemas.NoteCreateDTO,
    project=Depends(get_project),
    db: Database = Depends(get_db),
    broker: ApiEventBroker = Depends(get_broker),
):
    note = db.create_note(
        project.id,
        title=body.title,
        content=body.content,
        tags=_csv(body.tags),
        pinned=body.pinned,
    )
    broker.publish("notes_changed", project_id=project.id)
    return serializers.note_to_dto(db, note)


@router.patch(
    "/projects/{project_id}/notes/{note_id}",
    response_model=schemas.NoteDTO,
)
def update_note(
    note_id: int,
    body: schemas.NoteUpdateDTO,
    project=Depends(get_project),
    db: Database = Depends(get_db),
    broker: ApiEventBroker = Depends(get_broker),
):
    note = _note_or_404(db, project.id, note_id)
    patch = body.model_dump(exclude_unset=True)
    db.update_note(
        note_id,
        title=patch.get("title", note.title),
        content=patch.get("content", note.content),
        tags=_csv(patch["tags"]) if "tags" in patch else note.tags,
        pinned=patch.get("pinned", note.pinned),
    )
    broker.publish("notes_changed", project_id=project.id)
    return serializers.note_to_dto(db, db.get_note_by_id(note_id))


@router.delete("/projects/{project_id}/notes/{note_id}")
def delete_note(
    note_id: int,
    project=Depends(get_project),
    db: Database = Depends(get_db),
    broker: ApiEventBroker = Depends(get_broker),
):
    _note_or_404(db, project.id, note_id)
    db.delete_note(note_id)
    broker.publish("notes_changed", project_id=project.id)
    return {"ok": True, "deleted": note_id}
