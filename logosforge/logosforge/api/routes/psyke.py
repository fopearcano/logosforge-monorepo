"""PSYKE story-bible endpoints: entries, relations, progressions, search."""

from __future__ import annotations

from dataclasses import dataclass, field

from fastapi import APIRouter, Depends, Query

from logosforge.api import schemas, serializers
from logosforge.api.deps import (
    get_broker,
    get_db,
    get_project,
    get_psyke_command_plans,
)
from logosforge.api.errors import bad_request, conflict, forbidden, not_found
from logosforge.api.events import ApiEventBroker
from logosforge.db import Database, ProgressionCommandError
from logosforge.psyke_command_plans import (
    CommandPlanAmbiguousError,
    CommandPlanConfirmationError,
    CommandPlanConflictError,
    CommandPlanInputError,
    CommandPlanNotFoundError,
    PsykeCommandPlanService,
)
from logosforge.psyke_command_registry import CommandRegistry
from logosforge.psyke_search import PsykeSearchIndex
from logosforge.psyke_suggestions import suggest
from logosforge.psyke_system_commands import SystemCommandHandlers

router = APIRouter(tags=["psyke"])


def _csv(values):
    return ", ".join(values) if values else ""


def _entry_or_404(db: Database, project_id: int, entry_id: int):
    entry = db.get_psyke_entry_by_id(entry_id)
    if entry is None or entry.project_id != project_id:
        raise not_found(f"PSYKE entry {entry_id} not found")
    return entry


def _scene_or_404(db: Database, project_id: int, scene_id: int):
    scene = db.get_scene_by_id(scene_id)
    if scene is None or scene.project_id != project_id:
        raise not_found(f"Scene {scene_id} not found")
    return scene


def _progression_or_404(db: Database, project_id: int, progression_id: int):
    progression = db.get_psyke_progression_by_id(progression_id)
    if progression is None:
        raise not_found(f"PSYKE progression {progression_id} not found")
    _entry_or_404(db, project_id, progression.entry_id)
    return progression


@dataclass
class _SceneTermNode:
    children: dict[str, "_SceneTermNode"] = field(default_factory=dict)
    entry_ids: set[int] = field(default_factory=set)


def _is_word_character(value: str) -> bool:
    return value == "_" or value.isalnum()


def _scene_relevant_entry_ids(scene, entries) -> set[int]:
    """Find exact, case-insensitive name/alias mentions in a scene.

    The lookarounds avoid substring boosts (for example, ``Mary`` must not
    match ``Maryland``) while still supporting multi-word names and aliases.
    Only the three fields surfaced by the console context contract participate.
    """
    scene_text = "\n".join(
        (scene.title or "", scene.summary or "", scene.content or "")
    ).casefold()
    root = _SceneTermNode()
    for entry in entries:
        if entry.id is None:
            continue
        raw_terms = [entry.name, *(entry.aliases.split(",") if entry.aliases else [])]
        for raw_term in raw_terms:
            term = raw_term.strip().casefold()
            if not term:
                continue
            node = root
            for character in term:
                node = node.children.setdefault(character, _SceneTermNode())
            node.entry_ids.add(entry.id)

    relevant: set[int] = set()
    for start in range(len(scene_text)):
        if start > 0 and _is_word_character(scene_text[start - 1]):
            continue
        node = root
        cursor = start
        while cursor < len(scene_text):
            node = node.children.get(scene_text[cursor])
            if node is None:
                break
            cursor += 1
            if node.entry_ids and (
                cursor == len(scene_text)
                or not _is_word_character(scene_text[cursor])
            ):
                relevant.update(node.entry_ids)
    return relevant


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
    try:
        updated = db.update_psyke_entry(
            entry_id,
            name=patch.get("name", entry.name),
            entry_type=patch.get("type", entry.entry_type),
            aliases=_csv(patch["aliases"]) if "aliases" in patch else entry.aliases,
            notes=patch.get("notes", entry.notes),
            is_global=patch.get("is_global", entry.is_global),
            details=patch.get("details", db.get_psyke_entry_details(entry_id)),
        )
    except ProgressionCommandError as exc:
        raise conflict(
            str(exc), code="psyke_progression_subject_conflict",
        ) from exc
    broker.reconcile()
    broker.publish("psyke_changed", project_id=project.id, entry_id=entry_id)
    return serializers.psyke_entry_to_dto(db, updated)


@router.delete(
    "/projects/{project_id}/psyke/entries/{entry_id}",
    response_model=schemas.DeleteResultDTO,
)
def delete_entry(
    entry_id: int,
    project=Depends(get_project),
    db: Database = Depends(get_db),
    broker: ApiEventBroker = Depends(get_broker),
):
    _entry_or_404(db, project.id, entry_id)
    db.delete_psyke_entry(entry_id)
    broker.reconcile()
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


@router.delete(
    "/projects/{project_id}/psyke/relations/{relation_id}",
    response_model=schemas.DeleteResultDTO,
)
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
    if body.scene_id is not None:
        _scene_or_404(db, project.id, body.scene_id)
    prog = db.create_psyke_progression(body.entry_id, body.text, scene_id=body.scene_id)
    broker.reconcile()
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
    _progression_or_404(db, project.id, progression_id)
    if body.scene_id is not None:
        _scene_or_404(db, project.id, body.scene_id)
    prog = db.update_psyke_progression(progression_id, body.text, scene_id=body.scene_id)
    broker.reconcile()
    broker.publish("psyke_changed", project_id=project.id, entry_id=prog.entry_id)
    return serializers.progression_to_dto(db, project.id, prog, prog.entry_id)


@router.delete(
    "/projects/{project_id}/psyke/progressions/{progression_id}",
    response_model=schemas.DeleteResultDTO,
)
def delete_progression(
    progression_id: int,
    project=Depends(get_project),
    db: Database = Depends(get_db),
    broker: ApiEventBroker = Depends(get_broker),
):
    """Remove an arc-progression beat."""
    _progression_or_404(db, project.id, progression_id)
    db.delete_psyke_progression(progression_id)
    broker.reconcile()
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


@router.get(
    "/projects/{project_id}/psyke/console/suggestions",
    response_model=list[schemas.PsykeConsoleSuggestionDTO],
)
def psyke_console_suggestions(
    q: str = Query("", max_length=500, description="PSYKE Console input"),
    scene_id: int | None = Query(None, description="Optional in-project scene context"),
    project=Depends(get_project),
    db: Database = Depends(get_db),
):
    """Return ranked, read-only console suggestions for one project.

    ``SystemCommandHandlers`` is used only to populate command metadata in the
    registry. This endpoint never resolves or invokes a handler.
    """
    entries = db.get_all_psyke_entries(project.id)
    search_index = PsykeSearchIndex(db, project.id, lazy=True)
    search_index.rebuild_from(entries)

    registry = CommandRegistry()
    SystemCommandHandlers(db, project.id).register_all(registry)

    scene_entry_ids = None
    if scene_id is not None:
        scene = _scene_or_404(db, project.id, scene_id)
        scene_entry_ids = _scene_relevant_entry_ids(scene, entries)

    return [
        schemas.PsykeConsoleSuggestionDTO(
            text=item.text,
            description=item.description,
            icon=item.icon,
            category=item.category,
            score=item.score,
            entry_id=item.entry_id,
        )
        for item in suggest(
            q,
            search_index,
            registry=registry,
            scene_entry_ids=scene_entry_ids,
        )
    ]


@router.post(
    "/projects/{project_id}/psyke/console/plan",
    response_model=schemas.PsykeConsoleCommandPlanDTO,
)
def plan_psyke_console_command(
    body: schemas.PsykeConsolePlanRequestDTO,
    project=Depends(get_project),
    plans: PsykeCommandPlanService = Depends(get_psyke_command_plans),
):
    """Preview a deterministic project-local command without executing it."""
    try:
        plan = plans.create_plan(
            project.id,
            body.command,
            active_scene_id=body.active_scene_id,
        )
    except CommandPlanAmbiguousError as exc:
        raise conflict(str(exc), code="ambiguous_command_target") from exc
    except CommandPlanInputError as exc:
        raise bad_request(str(exc)) from exc
    return schemas.PsykeConsoleCommandPlanDTO(
        plan_id=plan.plan_id,
        command=plan.command,
        normalized_command=plan.normalized_command,
        action=plan.action,
        summary=plan.summary,
        effects=list(plan.effects),
        requires_confirmation=plan.requires_confirmation,
        mutates=plan.mutates,
        target_type=plan.target_type,
        target_id=plan.target_id,
        expires_at=plan.expires_at,
    )


@router.post(
    "/projects/{project_id}/psyke/console/execute",
    response_model=schemas.PsykeConsoleExecutionDTO,
)
def execute_psyke_console_command(
    body: schemas.PsykeConsoleExecuteRequestDTO,
    project=Depends(get_project),
    plans: PsykeCommandPlanService = Depends(get_psyke_command_plans),
    broker: ApiEventBroker = Depends(get_broker),
):
    """Execute the exact stored plan after any required confirmation."""
    try:
        result = plans.execute_plan(
            project.id,
            body.plan_id,
            confirmed=body.confirmed,
        )
    except CommandPlanNotFoundError as exc:
        raise not_found(str(exc)) from exc
    except CommandPlanConfirmationError as exc:
        raise forbidden(str(exc)) from exc
    except CommandPlanConflictError as exc:
        raise conflict(str(exc), code="stale_command_plan") from exc

    if result.mutated and result.target_type == "psyke_entry":
        broker.publish(
            "psyke_changed",
            project_id=project.id,
            entry_id=result.target_id,
        )
    return schemas.PsykeConsoleExecutionDTO(
        ok=result.ok,
        action=result.action,
        message=result.message,
        mutated=result.mutated,
        target_type=result.target_type,
        target_id=result.target_id,
    )
