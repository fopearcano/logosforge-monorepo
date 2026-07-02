"""Logos (inline / contextual assistant) endpoints.

Exposes the core's existing ``logosforge.logos`` engine over HTTP so every
frontend consumes ONE Logos — the same action registry, prompts, deterministic
handlers, and result model — instead of reinventing a parallel one. Two routes:

* ``GET  …/logos/actions``  — the action catalog (optionally per section/mode);
* ``POST …/logos/run``      — run one action against a built ``LogosContext``.

Behavior lives entirely in ``logosforge.logos``; this module only builds the
context, injects the shared provider (the same one ``assistant/chat`` uses, so
no Qt ``ui`` import), and serializes the result.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from logosforge.api import schemas, serializers
from logosforge.api.deps import get_db, get_project
from logosforge.db import Database

router = APIRouter(tags=["logos"])


def _build_provider():
    # The single shared provider builder — identical to assistant/chat, so Logos
    # rides the same backend and this route never imports the Qt ``ui`` package
    # (the controller's default resolver does, which would break a headless API).
    from logosforge.providers import build_active_provider

    return build_active_provider()


@router.get(
    "/projects/{project_id}/logos/actions",
    response_model=list[schemas.LogosActionDTO],
)
def logos_actions(
    section: str = Query("", description="Filter to a Logos section, e.g. 'Inline'"),
    writing_mode: str = Query("", description="Filter to a project writing mode"),
    project=Depends(get_project),
):
    """The Logos action catalog — name/label/category/generative/needs_selection."""
    from logosforge.logos import actions as logos_actions

    if section:
        items = logos_actions.list_actions_for_section(section, writing_mode=writing_mode)
    else:
        items = [
            a for a in logos_actions.list_actions()
            if a.applies_to_mode(writing_mode)
        ]
    return [serializers.logos_action_to_dto(a) for a in items]


@router.get(
    "/projects/{project_id}/logos/proactive",
    response_model=list[schemas.LogosSuggestionDTO],
)
def logos_proactive(
    section: str = Query("", description="Limit to one section; empty = all sections"),
    project=Depends(get_project),
    db: Database = Depends(get_db),
):
    """Proactive Logos signals — the rule-based detectors scan the project (no LLM,
    read-only) and return non-destructive observations + the actions that address
    them. Each scan is already confidence/severity-filtered + deduped by the engine."""
    from logosforge.logos.proactive.detectors import SECTION_DETECTORS
    from logosforge.logos.proactive.engine import ProactiveEngine

    engine = ProactiveEngine(db, project.id)
    sections = [section] if section else list(SECTION_DETECTORS.keys())
    found = []
    for sec in sections:
        try:
            found.extend(engine.scan_section(sec))
        except Exception:
            continue  # a flaky detector never breaks the scan
    found.sort(key=lambda s: (s.severity_rank, s.confidence), reverse=True)
    return [serializers.logos_suggestion_to_dto(s) for s in found[:40]]


@router.post(
    "/projects/{project_id}/logos/run",
    response_model=schemas.LogosResultDTO,
)
def logos_run(
    body: schemas.LogosRunRequestDTO,
    project=Depends(get_project),
    db: Database = Depends(get_db),
):
    """Run one Logos action. Deterministic actions never touch the provider; LLM
    actions ride the shared backend and degrade to an offline preview when no
    provider is configured (the controller owns all of that)."""
    from logosforge.logos.context import build_logos_context
    from logosforge.logos.controller import LogosController
    from logosforge.logos.actions import get_action, CATEGORY_GENERATIVE

    context = build_logos_context(
        db,
        project.id,
        section_name=body.section,
        selected_text=body.selected_text,
        cursor_text_excerpt=body.nearby_context,
        current_scene_id=body.current_scene_id,
        current_outline_node_id=body.current_outline_node_id,
        current_psyke_entry_id=body.current_psyke_entry_id,
        current_timeline_event_id=body.current_timeline_event_id,
        current_plot_block_id=body.current_plot_block_id,
        current_graph_node_id=body.current_graph_node_id,
    )
    controller = LogosController(db, provider_resolver=_build_provider)
    result = controller.run(context, body.action)

    action = get_action(body.action)
    generative = bool(action and action.category == CATEGORY_GENERATIVE)
    return serializers.logos_result_to_dto(result, generative=generative)
