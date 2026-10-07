"""Narrative intelligence routes — continuity, pacing, balance, health.

Most endpoints are derived reads.  Continuity review decisions use a separate,
revision-guarded command boundary with durable exactly-once receipts.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Response
from fastapi.responses import JSONResponse

from logosforge import (
    character_balance,
    graphic_novel_review,
    mode_suggestions,
    pacing_insights,
    screenplay_review,
    series_review,
    stage_script_review,
    story_health,
    structural_intelligence,
)
from logosforge.api import schemas, serializers
from logosforge.api.deps import get_broker, get_db, get_project
from logosforge.api.errors import ApiError, bad_request, conflict, not_found
from logosforge.api.events import ApiEventBroker
from logosforge.continuity import collector as continuity_collector
from logosforge.continuity.recommendations import build_continuity_decision_cards
from logosforge.db import (
    ContinuityCommandError,
    ContinuityIdempotencyKeyConflict,
    ContinuityIssueNotFound,
    ContinuityProjectNotFound,
    ContinuityReviewStateCorrupt,
    ContinuityRevisionConflict,
    Database,
)
from logosforge.knowledge_graph.builder import build_knowledge_graph
from logosforge.knowledge_graph.decision_cards import build_graph_decision_cards
from logosforge.project_intelligence import build_project_intelligence_report

router = APIRouter(tags=["intelligence"])

_CONTINUITY_RECEIPT_RESPONSE_HEADERS = {
    "Cache-Control": "no-store",
    "Vary": "Authorization, Idempotency-Key",
}
_CORRUPT_CONTINUITY_STATE_MESSAGE = (
    "Semantic Continuity review state is inconsistent. "
    "Repair it before continuing issue review."
)


def _continuity_state_corrupt_error() -> ApiError:
    return ApiError(
        500,
        _CORRUPT_CONTINUITY_STATE_MESSAGE,
        code="continuity_review_state_corrupt",
    )


def _build_continuity_or_500(db: Database, project_id: int):
    try:
        return continuity_collector.build_continuity_report(db, project_id)
    except ContinuityProjectNotFound as exc:
        raise not_found(f"Project {project_id} not found") from exc
    except ContinuityReviewStateCorrupt as exc:
        raise _continuity_state_corrupt_error() from exc


def _continuity_receipt_error(
    status_code: int,
    code: str,
    message: str,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message}},
        headers=_CONTINUITY_RECEIPT_RESPONSE_HEADERS,
    )


@router.get(
    "/projects/{project_id}/continuity",
    response_model=schemas.ContinuityReportDTO,
)
def get_continuity(project=Depends(get_project), db: Database = Depends(get_db)):
    """Continuity issues (contradictions, drift, gaps) by dimension + counts."""
    report = _build_continuity_or_500(db, project.id)
    return serializers.continuity_report_to_dto(report)


@router.post(
    "/projects/{project_id}/continuity/commands",
    response_model=schemas.ContinuityCommandResultDTO,
)
def execute_continuity_command(
    body: schemas.ContinuityCommandDTO,
    project=Depends(get_project),
    db: Database = Depends(get_db),
    broker: ApiEventBroker = Depends(get_broker),
    idempotency_key: Annotated[
        str | None,
        Header(alias="Idempotency-Key"),
    ] = None,
):
    """Atomically defer, dismiss, or resolve one current Continuity issue."""
    if idempotency_key is None:
        raise bad_request("Idempotency-Key is required")
    command = body.root
    payload = command.model_dump()
    kind = payload.pop("kind")
    issue_key = payload.pop("issue_id")
    try:
        result = db.replay_continuity_command(
            project.id,
            kind=kind,
            issue_key=issue_key,
            idempotency_key=idempotency_key,
            **payload,
        )
        if result is None:
            report = _build_continuity_or_500(db, project.id)
            issue = next((
                candidate for candidate in report.issues
                if candidate.issue_key == issue_key
                and candidate.status == "open"
            ), None)
            result = db.execute_continuity_command(
                project.id,
                kind=kind,
                issue_key=issue_key,
                idempotency_key=idempotency_key,
                issue=issue,
                **payload,
            )
    except ContinuityIdempotencyKeyConflict as exc:
        raise conflict(
            "This Idempotency-Key was already used for a different Continuity command.",
            code="idempotency_key_conflict",
        ) from exc
    except ContinuityRevisionConflict as exc:
        raise conflict(
            "Continuity review state changed after it was loaded. Reload and retry.",
            code="continuity_conflict",
        ) from exc
    except ContinuityProjectNotFound as exc:
        raise not_found(f"Project {project.id} not found") from exc
    except ContinuityIssueNotFound as exc:
        # Stale and foreign issue identities are deliberately indistinguishable.
        raise not_found("Continuity issue not found") from exc
    except ContinuityCommandError as exc:
        raise bad_request(str(exc)) from exc
    except ContinuityReviewStateCorrupt as exc:
        raise _continuity_state_corrupt_error() from exc

    if result.changed and not result.replayed:
        broker.publish(
            "continuity_changed",
            project_id=project.id,
            issue_id=result.issue_key,
            status=result.status,
        )
    current = _build_continuity_or_500(db, project.id)
    return schemas.ContinuityCommandResultDTO(
        continuity=serializers.continuity_report_to_dto(current),
        changed=result.changed,
        affected_issue_id=result.issue_key,
        previous_status=result.previous_status,
        status=result.status,
        replayed=result.replayed,
        applied_revision=result.applied_revision,
    )


@router.get(
    "/projects/{project_id}/continuity/command-receipt",
    response_model=schemas.ContinuityCommandReceiptDTO,
)
def get_continuity_command_receipt(
    response: Response,
    project=Depends(get_project),
    db: Database = Depends(get_db),
    idempotency_key: Annotated[
        str | None,
        Header(alias="Idempotency-Key"),
    ] = None,
):
    """Resolve one committed Continuity command by its retry capability."""
    if idempotency_key is None:
        return _continuity_receipt_error(
            400, "bad_request", "Idempotency-Key is required",
        )
    try:
        receipt = db.get_continuity_command_receipt(
            project.id, idempotency_key,
        )
    except ContinuityCommandError as exc:
        return _continuity_receipt_error(400, "bad_request", str(exc))
    if receipt is None:
        return _continuity_receipt_error(
            404,
            "continuity_receipt_not_found",
            "No committed Continuity command exists for this Idempotency-Key.",
        )
    response.headers.update(_CONTINUITY_RECEIPT_RESPONSE_HEADERS)
    return schemas.ContinuityCommandReceiptDTO(
        project_id=receipt.project_id,
        request_digest=receipt.request_digest,
        command_kind=receipt.kind,
        expected_revision=receipt.expected_revision,
        applied_revision=receipt.applied_revision,
        original_changed=receipt.original_changed,
        original_affected_issue_id=receipt.issue_key,
        expected_issue_fingerprint=receipt.expected_issue_fingerprint,
        previous_status=receipt.previous_status,
        status=receipt.status,
        committed_at=receipt.created_at,
    )


@router.get(
    "/projects/{project_id}/pacing",
    response_model=list[schemas.PacingInsightDTO],
)
def get_pacing(project=Depends(get_project), db: Database = Depends(get_db)):
    """Up to 5 pacing insights (monotony, disappearance, stagnation, …)."""
    return serializers.pacing_insights_to_dtos(
        pacing_insights.generate_insights(db, project.id)
    )


@router.get(
    "/projects/{project_id}/balance",
    response_model=schemas.BalanceDataDTO,
)
def get_balance(project=Depends(get_project), db: Database = Depends(get_db)):
    """Per-character and per-arc scene distribution with imbalance flags."""
    return serializers.balance_to_dto(
        character_balance.compute_balance(db, project.id)
    )


@router.get(
    "/projects/{project_id}/health",
    response_model=schemas.StoryHealthDTO,
)
def get_story_health(project=Depends(get_project), db: Database = Depends(get_db)):
    """Four high-level health signals (structure, characters, arcs, density)."""
    return serializers.story_health_to_dto(
        story_health.compute_health(db, project.id)
    )


@router.get(
    "/projects/{project_id}/structure-analysis",
    response_model=schemas.StructuralAnalysisDTO,
)
def get_structure_analysis(project=Depends(get_project), db: Database = Depends(get_db)):
    """Structural weaknesses (act balance, climax prep, beat placement, …)."""
    return serializers.structural_analysis_to_dto(
        structural_intelligence.compute_structural_analysis(db, project.id)
    )


@router.get(
    "/projects/{project_id}/decision-radar",
    response_model=schemas.DecisionRadarDTO,
)
def get_decision_radar(project=Depends(get_project), db: Database = Depends(get_db)):
    """Project decisions plus isolated Graph and Continuity evidence feeds."""
    report = build_project_intelligence_report(db, project.id)
    graph_available = True
    try:
        graph_result = build_knowledge_graph(db, project.id)
        graph_cards = build_graph_decision_cards(
            db,
            project.id,
            result=graph_result,
        )
    except Exception:  # noqa: BLE001 - advisory graph failures must not hide base radar
        # Graph diagnostics are advisory.  A corrupt/unavailable graph review
        # layer must be visible as unavailable, but must not take down the
        # established Project Intelligence radar.
        graph_available = False
        graph_cards = []
    continuity_available = True
    try:
        continuity_report = continuity_collector.build_continuity_report(
            db,
            project.id,
        )
        continuity_cards = build_continuity_decision_cards(
            db,
            project.id,
            report=continuity_report,
        )
    except Exception:  # noqa: BLE001 - advisory failures must not hide base radar
        continuity_available = False
        continuity_cards = []
    return serializers.decision_radar_to_dto(
        report,
        knowledge_graph_available=graph_available,
        knowledge_graph_cards=graph_cards,
        continuity_available=continuity_available,
        continuity_cards=continuity_cards,
    )


@router.get(
    "/projects/{project_id}/adapt",
    response_model=schemas.AdaptDTO,
)
def get_adapt(project=Depends(get_project), db: Database = Depends(get_db)):
    """Adaptive-AI mode (stage × health) + up to 5 actionable suggestions."""
    result, suggestions = mode_suggestions.generate_mode_suggestions(db, project.id)
    from logosforge.settings import get_manager
    return schemas.AdaptDTO(
        mode=str(result.mode.value),
        stage=str(result.stage.value),
        health=str(result.health.value),
        description=result.description,
        suggestions=[schemas.ModeSuggestionDTO(text=s.text, category=s.category) for s in suggestions],
        override=str(get_manager().get("adaptive_mode_override") or ""),
    )


@router.get(
    "/projects/{project_id}/review",
    response_model=schemas.ReviewReportDTO,
)
def get_review(project=Depends(get_project), db: Database = Depends(get_db)):
    """Screenplay review dashboard — per-scene readiness + summary metrics."""
    r = screenplay_review.build_screenplay_review(db, project.id)
    return schemas.ReviewReportDTO(
        format="screenplay",
        project_title=r.project_title,
        total_scenes=r.total_scenes, written=r.written, planned=r.planned, needs_work=r.needs_work,
        with_health_warnings=r.with_health_warnings, with_continuity_warnings=r.with_continuity_warnings,
        with_export_warnings=r.with_export_warnings, timeline_linked=r.timeline_linked,
        with_psyke_links=r.with_psyke_links, export_ready=r.export_ready,
        rows=[schemas.ReviewRowDTO(
            scene_id=row.scene_id, number=row.number, title=row.title, word_count=row.word_count,
            overall_status=row.overall_status, next_action=row.next_action,
            health_severity=row.health_severity, continuity_severity=row.continuity_severity,
            has_rewrite_candidate=row.has_rewrite_candidate,
        ) for row in r.rows],
    )


@router.get(
    "/projects/{project_id}/format-review",
    response_model=schemas.FormatReviewDTO,
)
def get_format_review(project=Depends(get_project), db: Database = Depends(get_db)):
    """Format-specific review checks — graphic novel / stage script / series."""
    fmt = (getattr(project, "narrative_engine", "") or getattr(project, "format_mode", "") or "").lower()
    rows: list[tuple[str, str, str, int | None]] = []
    if fmt == "graphic_novel":
        rows = [(c.check_type, c.message, c.severity, c.page_id) for c in graphic_novel_review.review_graphic_novel(db, project.id)]
    elif fmt == "stage_script":
        rows = [(c.check_type, c.message, c.severity, c.scene_id) for c in stage_script_review.review_stage_script(db, project.id)]
    elif fmt == "series":
        rows = [(c.check_type, c.message, c.severity, c.episode_id) for c in series_review.review_series(db, project.id)]
    return schemas.FormatReviewDTO(
        format=fmt,
        checks=[schemas.FormatReviewCheckDTO(check_type=t, message=m, severity=s, ref_id=r) for (t, m, s, r) in rows],
    )


@router.get("/plugins", response_model=list[schemas.PluginDTO])
def list_plugins():
    """Installed analysis plugins (name / description / category)."""
    try:
        import logosforge.plugins  # noqa: F401 — importing registers the built-ins
    except Exception:
        pass
    from logosforge import plugin_registry
    return [
        schemas.PluginDTO(
            name=p.get("name", ""), description=p.get("description", ""),
            category=p.get("category", ""), requires_scene=str(p.get("requires_scene", "")) == "True",
        )
        for p in plugin_registry.describe_all_plugins()
    ]


@router.get(
    "/projects/{project_id}/graph/gravity",
    response_model=schemas.GraphGravityDTO,
)
def get_graph_gravity(project=Depends(get_project), db: Database = Depends(get_db)):
    """Per-node story-gravity weights (narrative / thematic / structural).

    The graph is enriched with the project's format-specific edges (screenplay
    causality/setup-payoff, GN pages/panels/motifs, stage cues, series arcs) so
    gravity reflects them — now possible headlessly since the enrichers moved to
    the Qt-free ``logosforge.graph_enrichers``.
    """
    from logosforge import graph_enrichers, graph_gravity
    from logosforge.graph_data import build_graph_data

    engine = (getattr(project, "narrative_engine", "") or "").lower()
    _ENRICH = {
        "screenplay": graph_enrichers.enrich_screenplay_edges,
        "graphic_novel": graph_enrichers.enrich_graphic_novel_graph,
        "stage_script": graph_enrichers.enrich_stage_script_graph,
        "series": graph_enrichers.enrich_series_graph,
    }
    try:
        data = build_graph_data(db, project.id)
        enrich = _ENRICH.get(engine)
        if enrich is not None:
            enrich(db, project.id, data)
        gravity = graph_gravity.compute_gravity(
            db, project.id, data,
            screenplay_mode=(engine == "screenplay"),
            graphic_novel_mode=(engine == "graphic_novel"),
        )
    except Exception:
        # Gravity is a non-critical enhancement overlay — degrade gracefully.
        return schemas.GraphGravityDTO(available=False, nodes=[])
    return serializers.gravity_to_dto(gravity, data)
