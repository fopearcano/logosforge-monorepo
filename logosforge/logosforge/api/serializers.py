"""Map internal ORM objects onto the stable DTOs.

Keeping the ORM→DTO mapping in one place means routes never leak SQLModel
objects, and the wire contract stays decoupled from the database schema.
"""

from __future__ import annotations

from logosforge.api import schemas
from logosforge.db import Database


def _split_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [p.strip() for p in value.split(",") if p.strip()]


# -- Projects ----------------------------------------------------------------


def project_to_dto(project) -> schemas.ProjectDTO:
    from logosforge.project_compat import (
        get_project_narrative_engine,
        get_project_writing_format,
    )

    return schemas.ProjectDTO(
        id=project.id,
        title=project.title,
        description=project.description or "",
        narrative_engine=get_project_narrative_engine(project),
        default_writing_format=get_project_writing_format(project),
        format_mode=(project.format_mode or "novel"),
    )


# -- Scenes ------------------------------------------------------------------


def scene_to_dto(db: Database, scene, order_index: int = 0) -> schemas.SceneDTO:
    return schemas.SceneDTO(
        id=scene.id,
        title=scene.title,
        summary=scene.summary or "",
        synopsis=scene.synopsis or "",
        goal=scene.goal or "",
        conflict=scene.conflict or "",
        outcome=scene.outcome or "",
        beat=scene.beat or "",
        act=scene.act or "",
        chapter=scene.chapter or "",
        plotline=scene.plotline or "",
        color_label=scene.color_label or "",
        tags=_split_csv(scene.tags),
        content=scene.content or "",
        sort_order=scene.sort_order or 0,
        order_index=order_index,
        character_ids=db.get_scene_character_ids(scene.id),
        place_ids=db.get_scene_place_ids(scene.id),
        who_knows_what=getattr(scene, "who_knows_what", "") or "",
    )


def scenes_to_dtos(db: Database, scenes) -> list[schemas.SceneDTO]:
    return [scene_to_dto(db, s, i + 1) for i, s in enumerate(scenes)]


# -- Outline -----------------------------------------------------------------


def outline_tree(db: Database, project_id: int) -> list[schemas.OutlineNodeDTO]:
    nodes = db.get_outline_nodes(project_id)
    children_map: dict[int | None, list] = {}
    for node in nodes:
        children_map.setdefault(node.parent_id, []).append(node)

    def build(parent_id: int | None) -> list[schemas.OutlineNodeDTO]:
        kids = children_map.get(parent_id, [])
        kids.sort(key=lambda n: (n.sort_order, n.id or 0))
        return [
            schemas.OutlineNodeDTO(
                id=n.id,
                parent_id=n.parent_id,
                title=n.title,
                description=n.description or "",
                sort_order=n.sort_order or 0,
                children=build(n.id),
            )
            for n in kids
        ]

    return build(None)


def outline_node_to_dto(node) -> schemas.OutlineNodeDTO:
    return schemas.OutlineNodeDTO(
        id=node.id,
        parent_id=node.parent_id,
        title=node.title,
        description=node.description or "",
        sort_order=node.sort_order or 0,
        children=[],
    )


# -- Plot --------------------------------------------------------------------


def plot_blocks(db: Database, project_id: int) -> list[schemas.PlotBlockDTO]:
    scenes = db.get_all_scenes(project_id)
    blocks: dict[str, list] = {}
    order: list[str] = []
    for scene in scenes:
        plotline = (scene.plotline or "").strip() or "Unassigned"
        if plotline not in blocks:
            blocks[plotline] = []
            order.append(plotline)
        blocks[plotline].append(
            schemas.PlotSceneDTO(
                scene_id=scene.id,
                title=scene.title,
                act=scene.act or "",
                summary=scene.summary or "",
                beat=scene.beat or "",
                color_label=scene.color_label or "",
                order_index=scene.sort_order or 0,
            )
        )
    return [
        schemas.PlotBlockDTO(id=name, plotline=name, scenes=blocks[name])
        for name in order
    ]


# -- Timeline ----------------------------------------------------------------


def timeline_events(db: Database, project_id: int) -> list[schemas.TimelineEventDTO]:
    scenes = db.get_all_scenes(project_id)
    char_name_by_id = {c.id: c.name for c in db.get_all_characters(project_id)}
    events = []
    for index, scene in enumerate(scenes):
        duration = (
            scene.estimated_duration_minutes
            or getattr(scene, "performance_duration_minutes", 0)
        )
        states = [
            schemas.TimelineCharacterStateDTO(
                character=char_name_by_id.get(cid, str(cid)), state=state,
            )
            for cid, state in db.get_scene_character_states(scene.id)
        ]
        events.append(
            schemas.TimelineEventDTO(
                id=scene.id,
                order_index=index + 1,
                title=scene.title,
                act=scene.act or "",
                chapter=scene.chapter or "",
                time_of_day=scene.time_of_day or "",
                location=scene.location or scene.slugline or "",
                duration_minutes=duration or 0,
                character_states=states,
            )
        )
    return events


# -- PSYKE -------------------------------------------------------------------


def psyke_entry_to_dto(db: Database, entry) -> schemas.PsykeEntryDTO:
    return schemas.PsykeEntryDTO(
        id=entry.id,
        name=entry.name,
        type=entry.entry_type,
        aliases=_split_csv(entry.aliases),
        notes=entry.notes or "",
        is_global=bool(entry.is_global),
        details=db.get_psyke_entry_details(entry.id),
    )


def logos_action_to_dto(action) -> schemas.LogosActionDTO:
    """Serialize a logosforge.logos.actions.LogosAction for the catalog."""
    from logosforge.logos.actions import CATEGORY_GENERATIVE

    return schemas.LogosActionDTO(
        name=action.name,
        label=action.label,
        description=action.description,
        category=action.category,
        sections=list(action.sections),
        needs_selection=action.needs_selection,
        deterministic=action.deterministic,
        generative=(action.category == CATEGORY_GENERATIVE),
    )


def logos_suggestion_to_dto(s) -> schemas.LogosSuggestionDTO:
    """Serialize a logosforge.logos.proactive.LogosSuggestion."""
    return schemas.LogosSuggestionDTO(
        id=s.id,
        type=s.type,
        title=s.title,
        message=s.message,
        section_name=s.section_name,
        evidence=s.evidence,
        confidence=s.confidence,
        severity=s.severity,
        target_type=s.target_type,
        target_id=s.target_id,
        suggested_actions=list(s.suggested_actions),
    )


def logos_result_to_dto(result, *, generative: bool = False) -> schemas.LogosResultDTO:
    """Serialize a logosforge.logos.result.LogosResult (+ a generative flag)."""
    d = result.to_dict()
    return schemas.LogosResultDTO(
        ok=d["ok"],
        action=d["action"],
        title=d["title"],
        message=d["message"],
        suggestions=list(d["suggestions"]),
        proposed_operations=list(d["proposed_operations"]),
        generative=generative,
        error=d["error"],
    )


def psyke_relations(db: Database, project_id: int) -> list[schemas.PsykeRelationDTO]:
    entries = db.get_all_psyke_entries(project_id)
    name_by_id = {e.id: e.name for e in entries}
    out: list[schemas.PsykeRelationDTO] = []
    seen: set[tuple] = set()
    for e in entries:
        for related, rtype in db.get_typed_related_psyke_entries(e.id):
            key = (min(e.id, related.id), max(e.id, related.id), rtype)
            if key in seen:
                continue
            seen.add(key)
            out.append(
                schemas.PsykeRelationDTO(
                    id=f"{e.id}:{related.id}",
                    source_id=e.id,
                    target_id=related.id,
                    source=name_by_id.get(e.id, ""),
                    target=name_by_id.get(related.id, ""),
                    relation_type=rtype,
                )
            )
    return out


def psyke_progressions(db: Database, project_id: int) -> list[schemas.PsykeProgressionDTO]:
    entries = db.get_all_psyke_entries(project_id)
    scene_title_by_id = {s.id: s.title for s in db.get_all_scenes(project_id)}
    out = []
    for e in entries:
        for prog in db.get_psyke_progressions(e.id):
            out.append(
                schemas.PsykeProgressionDTO(
                    id=prog.id,
                    entry_id=e.id,
                    text=prog.text,
                    scene_id=prog.scene_id,
                    scene_title=scene_title_by_id.get(prog.scene_id, "")
                    if prog.scene_id else "",
                    sort_order=prog.sort_order or 0,
                )
            )
    return out


def progression_to_dto(db: Database, project_id: int, prog, entry_id: int) -> schemas.PsykeProgressionDTO:
    scene_title = ""
    if prog.scene_id:
        scene = db.get_scene_by_id(prog.scene_id)
        scene_title = scene.title if scene else ""
    return schemas.PsykeProgressionDTO(
        id=prog.id,
        entry_id=entry_id,
        text=prog.text,
        scene_id=prog.scene_id,
        scene_title=scene_title,
        sort_order=prog.sort_order or 0,
    )


# -- Notes -------------------------------------------------------------------


def note_to_dto(db: Database, note) -> schemas.NoteDTO:
    return schemas.NoteDTO(
        id=note.id,
        title=note.title,
        content=note.content or "",
        tags=_split_csv(note.tags),
        pinned=bool(note.pinned),
        psyke_links=db.get_note_psyke_links(note.id),
        scene_links=db.get_note_scene_links(note.id),
    )


def character_to_dto(db: Database, character) -> schemas.CharacterDTO:
    return schemas.CharacterDTO(
        id=character.id,
        name=character.name,
        description=character.description or "",
        color=character.color or "#3498db",
        psyke_entry_id=character.psyke_entry_id,
    )


# -- Narrative dashboard -----------------------------------------------------


def dashboard_to_dto(data) -> schemas.NarrativeDashboardDTO:
    """Map ``narrative_dashboard.NarrativeDashboardData`` onto its DTO."""
    return schemas.NarrativeDashboardDTO(
        tension=schemas.TensionCurveDTO(
            points=[
                schemas.SceneTensionDTO(
                    scene_id=p.scene_id,
                    scene_order=p.scene_order,
                    scene_title=p.scene_title,
                    score=p.score,
                    char_count=p.char_count,
                    relation_pairs=p.relation_pairs,
                    keyword_hits=p.keyword_hits,
                    progression_count=p.progression_count,
                )
                for p in data.tension.points
            ],
            flags=list(data.tension.flags),
        ),
        characters=[
            schemas.CharacterPresenceDTO(
                entry_id=c.entry_id,
                name=c.name,
                present_scenes=list(c.present_scenes),
                total_scenes=c.total_scenes,
                flags=list(c.flags),
            )
            for c in data.characters
        ],
        structure=schemas.StructureDistributionDTO(
            segments=[
                schemas.ActSegmentDTO(
                    label=s.label,
                    scene_count=s.scene_count,
                    word_count=s.word_count,
                )
                for s in data.structure.segments
            ],
            total_scenes=data.structure.total_scenes,
            total_words=data.structure.total_words,
            flags=list(data.structure.flags),
            inferred=data.structure.inferred,
        ),
        themes=[
            schemas.ThemePresenceDTO(
                entry_id=t.entry_id,
                name=t.name,
                present_scenes=list(t.present_scenes),
                total_scenes=t.total_scenes,
                flags=list(t.flags),
                presence_source=getattr(t, "presence_source", "prose"),
            )
            for t in data.themes
        ],
    )


# -- Continuity / pacing / balance / health ----------------------------------


def continuity_report_to_dto(report) -> schemas.ContinuityReportDTO:
    """Map ``continuity.models.ContinuityReport`` onto its DTO (issues + counts)."""
    return schemas.ContinuityReportDTO(
        writing_mode=report.writing_mode,
        issues=[
            schemas.ContinuityIssueDTO(
                id=i.issue_key,
                issue_type=i.issue_type,
                dimension=i.dimension,
                severity=i.severity,
                confidence=i.confidence,
                title=i.title,
                explanation=i.explanation,
                suggested_action=i.suggested_action,
                related_scene_ids=[int(s) for s in i.related_scene_ids],
                status=i.status,
            )
            for i in report.issues
        ],
        blocking_count=report.blocking_count,
        warning_count=report.warning_count,
        unavailable=list(report.unavailable),
    )


def pacing_insights_to_dtos(insights) -> list[schemas.PacingInsightDTO]:
    return [
        schemas.PacingInsightDTO(text=i.text, severity=i.severity, category=i.category)
        for i in insights
    ]


def balance_to_dto(data) -> schemas.BalanceDataDTO:
    """Map ``character_balance.BalanceData`` onto its DTO."""
    return schemas.BalanceDataDTO(
        characters=[
            schemas.CharacterBalanceDTO(
                char_id=c.char_id,
                name=c.name,
                scene_count=c.scene_count,
                total_scenes=c.total_scenes,
                flag=c.flag,
            )
            for c in data.characters
        ],
        arcs=[
            schemas.ArcBalanceDTO(
                plotline=a.plotline,
                scene_count=a.scene_count,
                acts_spanned=a.acts_spanned,
                flag=a.flag,
            )
            for a in data.arcs
        ],
        total_scenes=data.total_scenes,
    )


def _health_signal_to_dto(s) -> schemas.HealthSignalDTO:
    return schemas.HealthSignalDTO(label=s.label, level=s.level, score=s.score)


def story_health_to_dto(health) -> schemas.StoryHealthDTO:
    """Map ``story_health.StoryHealth`` onto its DTO (four signals)."""
    return schemas.StoryHealthDTO(
        structure=_health_signal_to_dto(health.structure),
        characters=_health_signal_to_dto(health.characters),
        arcs=_health_signal_to_dto(health.arcs),
        density=_health_signal_to_dto(health.density),
    )


def structural_analysis_to_dto(analysis) -> schemas.StructuralAnalysisDTO:
    """Map ``structural_intelligence.StructuralAnalysis`` onto its DTO."""
    return schemas.StructuralAnalysisDTO(
        issues=[
            schemas.StructuralIssueDTO(
                issue_type=i.issue_type,
                category=i.category,
                severity=i.severity,
                message=i.message,
                suggestion=i.suggestion,
            )
            for i in analysis.issues
        ],
        suggestions=list(analysis.suggestions),
    )


def workflow_run_to_dto(view) -> schemas.WorkflowRunDTO:
    """Map a ``guided_workflows.engine.WorkflowRunView`` onto its DTO."""
    run = view.run
    return schemas.WorkflowRunDTO(
        id=getattr(run, "id", 0),
        title=getattr(run, "title", "") or "",
        status=getattr(run, "status", "") or "",
        writing_mode=getattr(run, "writing_mode", "") or "",
        template_id=getattr(run, "template_id", "") or "",
        current_step_id=getattr(run, "current_step_id", "") or "",
        total_steps=view.total_steps,
        completed_steps=view.completed_steps,
        steps=[
            schemas.WorkflowStepDTO(
                step_id=getattr(s, "step_id", "") or "",
                title=getattr(s, "title", "") or "",
                status=getattr(s, "status", "") or "",
                sort_index=getattr(s, "sort_index", 0) or 0,
                section_name=getattr(s, "section_name", "") or "",
                action_id=getattr(s, "action_id", "") or "",
            )
            for s in view.steps
        ],
    )


def workflows_to_dtos(views) -> list[schemas.WorkflowRunDTO]:
    return [workflow_run_to_dto(v) for v in views]


def decision_card_to_dto(card) -> schemas.DecisionCardDTO:
    return schemas.DecisionCardDTO(
        id=card.id,
        category=card.category,
        severity=card.severity,
        confidence=card.confidence,
        title=card.title,
        explanation=card.explanation,
        suggested_action=card.suggested_action,
        related_section=card.related_section,
        related_target_type=card.related_target_type,
        related_target_id=card.related_target_id,
        created_from=card.created_from,
    )


def decision_radar_to_dto(report) -> schemas.DecisionRadarDTO:
    """Map a ``project_intelligence.ProjectIntelligenceReport`` onto the radar DTO."""
    return schemas.DecisionRadarDTO(
        project_id=report.project_id,
        generated_light=bool(getattr(report, "light", False)),
        summary_line=report.summary_line(),
        radar=[decision_card_to_dto(c) for c in report.radar],
    )


def quantum_result_to_dto(result) -> schemas.QuantumResultDTO:
    """Map a ``quantum_outliner.QuantumResult`` onto its DTO (payload is JSON-ready)."""
    payload = result.payload if isinstance(result.payload, dict) else {}
    return schemas.QuantumResultDTO(
        kind=result.kind,
        title=result.title,
        body=result.body,
        payload=payload,
    )


def gravity_to_dto(gravity_map, data) -> schemas.GraphGravityDTO:
    """Map ``graph_gravity.compute_gravity`` output (+ GraphData) onto the DTO."""
    nodes = []
    for node_id, g in gravity_map.items():
        node = data.nodes.get(node_id) if data is not None else None
        nodes.append(schemas.StoryGravityNodeDTO(
            node_id=node_id,
            etype=getattr(node, "etype", "") if node is not None else "",
            name=getattr(node, "name", "") if node is not None else "",
            narrative=g.narrative,
            thematic=g.thematic,
            structural=g.structural,
            total=g.total,
        ))
    nodes.sort(key=lambda n: n.total, reverse=True)
    return schemas.GraphGravityDTO(available=True, nodes=nodes)
