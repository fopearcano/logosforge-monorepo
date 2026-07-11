"""Outline (hierarchical) endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from logosforge.api import schemas, serializers
from logosforge.api.deps import get_broker, get_db, get_project
from logosforge.api.errors import bad_request, not_found
from logosforge.api.events import ApiEventBroker
from logosforge.db import Database
from logosforge.db.database import _UNSET

router = APIRouter(tags=["outline"])

_SCOPES = ("full", "act", "chapter", "scene")


@router.get(
    "/projects/{project_id}/outline",
    response_model=list[schemas.OutlineNodeDTO],
)
def get_outline(project=Depends(get_project), db: Database = Depends(get_db)):
    return serializers.outline_tree(db, project.id)


@router.post(
    "/projects/{project_id}/outline/nodes",
    response_model=schemas.OutlineNodeDTO, status_code=201,
)
def create_outline_node(
    body: schemas.OutlineNodeCreateDTO,
    project=Depends(get_project),
    db: Database = Depends(get_db),
    broker: ApiEventBroker = Depends(get_broker),
):
    node = db.create_outline_node(
        project.id,
        title=body.title,
        description=body.description,
        parent_id=body.parent_id,
        sort_order=body.sort_order,
        scene_id=body.scene_id,
    )
    broker.publish("outline_changed", project_id=project.id)
    return serializers.outline_node_to_dto(node)


@router.patch(
    "/projects/{project_id}/outline/nodes/{node_id}",
    response_model=schemas.OutlineNodeDTO,
)
def update_outline_node(
    node_id: int,
    body: schemas.OutlineNodeUpdateDTO,
    project=Depends(get_project),
    db: Database = Depends(get_db),
    broker: ApiEventBroker = Depends(get_broker),
):
    node = db.get_outline_node_by_id(node_id)
    if node is None or node.project_id != project.id:
        raise not_found(f"Outline node {node_id} not found")
    db.update_outline_node(
        node_id,
        title=body.title,
        description=body.description,
        sort_order=body.sort_order,
        # Only touch the link when the client explicitly sent scene_id (present,
        # even null = set/clear); absent = leave the existing link unchanged.
        scene_id=(body.scene_id if "scene_id" in body.model_fields_set else _UNSET),
    )
    broker.publish("outline_changed", project_id=project.id)
    return serializers.outline_node_to_dto(db.get_outline_node_by_id(node_id))


@router.delete("/projects/{project_id}/outline/nodes/{node_id}")
def delete_outline_node(
    node_id: int,
    project=Depends(get_project),
    db: Database = Depends(get_db),
    broker: ApiEventBroker = Depends(get_broker),
):
    node = db.get_outline_node_by_id(node_id)
    if node is None or node.project_id != project.id:
        raise not_found(f"Outline node {node_id} not found")
    db.delete_outline_node(node_id)
    broker.publish("outline_changed", project_id=project.id)
    return {"ok": True, "deleted": node_id}


@router.post(
    "/projects/{project_id}/outline/generate",
    response_model=schemas.OutlineGenerateResultDTO,
)
def generate_outline(
    body: schemas.OutlineGenerateRequestDTO,
    project=Depends(get_project),
    db: Database = Depends(get_db),
    broker: ApiEventBroker = Depends(get_broker),
):
    """AI-generate outline structure and apply it ADDITIVELY to the outline tree.

    Exposes the existing (Qt-free) ``outline_actions`` pipeline — build a
    scope/engine/PSYKE-aware prompt → LLM → parse → repair → validate → apply as
    OutlineNode rows (what the Outline panel reads). ``scope`` picks the tier
    (full | act | chapter | scene); ``parent_id`` nests the result under an
    existing node. Never overwrites — nodes append after existing siblings.
    """
    from logosforge.outline_actions import (
        apply_outline_ops,
        build_outline_generation_prompt,
        outline_messages,
        parse_outline_response,
        repair_outline_ops,
        validate_outline_ops,
    )
    from logosforge.assistant import chat_completion
    from logosforge.context_builder import gather_psyke_context
    from logosforge.project_compat import get_project_narrative_engine
    from logosforge.providers import build_active_provider

    scope = (body.scope or "full").lower()
    if scope not in _SCOPES:
        scope = "full"

    # Scoped generation applies under an existing node; validate ownership and
    # pass its title so the prompt knows what it continues under.
    parent_id = body.parent_id
    target_title = ""
    if parent_id is not None:
        parent = db.get_outline_node_by_id(parent_id)
        if parent is None or parent.project_id != project.id:
            raise not_found(f"Outline node {parent_id} not found")
        target_title = parent.title or ""

    provider = build_active_provider(require_configured=True)
    if provider is None:
        raise bad_request("No AI provider is configured — set one in AI Settings first.")

    # PSYKE bible context makes the outline about THIS story's cast; best-effort.
    try:
        psyke = gather_psyke_context(db, project.id)
    except Exception:
        psyke = ""

    prompt = build_outline_generation_prompt(
        scope,
        engine=get_project_narrative_engine(project),
        psyke_context=psyke,
        target_title=target_title,
        instructions=body.instructions or "",
    )
    try:
        text, _ = chat_completion(outline_messages(prompt), provider=provider)
    except Exception as exc:  # provider/network error → surface, don't 500
        raise bad_request(f"AI provider error: {exc}")

    ops = parse_outline_response(text)
    ops, warnings = repair_outline_ops(ops)
    ok, errors = validate_outline_ops(ops)
    if not ok:
        return schemas.OutlineGenerateResultDTO(
            ok=False, created=0, node_ids=[], warnings=warnings, errors=errors,
        )

    created = apply_outline_ops(db, project.id, ops, parent_id=parent_id)
    broker.publish("outline_changed", project_id=project.id)
    return schemas.OutlineGenerateResultDTO(
        ok=True, created=len(created), node_ids=created, warnings=warnings, errors=[],
    )
