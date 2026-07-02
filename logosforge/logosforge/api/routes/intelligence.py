"""Read-only narrative intelligence routes — continuity, pacing, balance, health.

Each exposes an existing core analysis engine over the API; all are pure reads
(nothing is written to the database).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from logosforge import character_balance, pacing_insights, story_health, structural_intelligence
from logosforge.api import schemas, serializers
from logosforge.api.deps import get_db, get_project
from logosforge.continuity import collector as continuity_collector
from logosforge.db import Database
from logosforge.guided_workflows import engine as workflow_engine
from logosforge.project_intelligence import build_project_intelligence_report

router = APIRouter(tags=["intelligence"])


@router.get(
    "/projects/{project_id}/continuity",
    response_model=schemas.ContinuityReportDTO,
)
def get_continuity(project=Depends(get_project), db: Database = Depends(get_db)):
    """Continuity issues (contradictions, drift, gaps) by dimension + counts."""
    report = continuity_collector.build_continuity_report(db, project.id)
    return serializers.continuity_report_to_dto(report)


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
    "/projects/{project_id}/workflows",
    response_model=list[schemas.WorkflowRunDTO],
)
def get_workflows(project=Depends(get_project), db: Database = Depends(get_db)):
    """Guided-workflow runs for the project (steps + progress)."""
    return serializers.workflows_to_dtos(
        workflow_engine.get_all_workflows(db, project.id)
    )


@router.get(
    "/projects/{project_id}/decision-radar",
    response_model=schemas.DecisionRadarDTO,
)
def get_decision_radar(project=Depends(get_project), db: Database = Depends(get_db)):
    """Ranked decision cards (blocking→info) from the project intelligence report."""
    report = build_project_intelligence_report(db, project.id)
    return serializers.decision_radar_to_dto(report)


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
