"""Knowledge-Graph-derived Decision Radar cards (Phase 10P).

Deterministic, traceable cards built from graph structure — isolated PSYKE
entries, scenes with no PSYKE links, undefined note terms, weakly-connected plot
blocks, many inferred edges needing confirmation, themes not connected to scenes.
No LLM; no automatic fixes; actions route through existing safe systems.
"""

from __future__ import annotations

from logosforge.knowledge_graph import provenance as P
from logosforge.knowledge_graph import scoring
from logosforge.knowledge_graph.builder import build_knowledge_graph
from logosforge.project_intelligence.decision_radar import (
    SEV_OPPORTUNITY,
    SEV_SUGGESTION,
    SEV_WARNING,
    DecisionCard,
    DecisionEvidence,
)

_EVIDENCE_CAP = 5


def _safe_confidence(value: str) -> str:
    return value if value in P.CONFIDENCE_LEVELS else P.CONF_UNKNOWN


def _node_evidence(
    node,
    *,
    detail: str = "",
    related_section: str = "",
    related_target_type: str = "",
    related_target_id: int | None = None,
) -> DecisionEvidence:
    source = ":".join(
        part for part in (str(node.source_type or ""), str(node.source_id or ""))
        if part
    )
    return DecisionEvidence(
        kind="node",
        label=str(node.label or "").strip() or node.key,
        detail=detail or f"{node.node_type} source {source or 'canonical graph'}.",
        graph_focus_key=node.key,
        confidence=P.CONF_CONFIRMED,
        source_system=node.source_type or "knowledge_graph",
        provenance=source,
        related_section=related_section,
        related_target_type=related_target_type,
        related_target_id=related_target_id,
    )


def _edge_evidence(graph, edge, *, focus_key: str = "") -> DecisionEvidence:
    source = graph.get_node(edge.source)
    target = graph.get_node(edge.target)
    if source is None or target is None:
        raise ValueError("decision evidence requires two project-owned endpoints")
    source_label = source.label or edge.source
    target_label = target.label or edge.target
    return DecisionEvidence(
        kind="edge",
        label=f"{source_label} → {target_label} · {edge.edge_type}",
        detail=edge.explanation or "Canonical Knowledge Graph relationship.",
        graph_focus_key=focus_key or edge.source,
        source_key=edge.source,
        target_key=edge.target,
        edge_type=edge.edge_type,
        confidence=_safe_confidence(edge.confidence),
        source_system=edge.source_system,
        provenance=edge.provenance,
    )


def _card(
    card_id: str,
    category: str,
    severity: str,
    confidence: str,
    title: str,
    explanation: str,
    action: str,
    section: str,
    *,
    graph_focus_key: str = "",
    graph_view_mode: str = "project_map",
    evidence: list[DecisionEvidence] | None = None,
    evidence_total: int | None = None,
    related_target_type: str = "",
    related_target_id: int | None = None,
    related_target_key: str = "",
) -> DecisionCard:
    bounded = list(evidence or [])[:_EVIDENCE_CAP]
    return DecisionCard(
        id=card_id,
        category=category,
        severity=severity,
        confidence=confidence,
        title=title,
        explanation=explanation,
        suggested_action=action,
        related_section=section,
        created_from="knowledge_graph",
        graph_focus_key=graph_focus_key,
        graph_view_mode=graph_view_mode,
        graph_include_inferred=True,
        graph_depth=1,
        evidence=bounded,
        evidence_total=max(len(bounded), evidence_total or 0),
        related_target_type=related_target_type,
        related_target_id=related_target_id,
        related_target_key=related_target_key,
    )


def build_graph_decision_cards(db, project_id: int, *, result=None, cap: int = 8,
                               ) -> list[DecisionCard]:
    if result is None:
        result = build_knowledge_graph(db, project_id)
    graph_project_id = getattr(getattr(result, "graph", None), "project_id", None)
    if (
        not isinstance(graph_project_id, int)
        or isinstance(graph_project_id, bool)
        or graph_project_id != project_id
    ):
        raise ValueError("knowledge graph result does not belong to this project")
    graph = result.graph
    cards: list[DecisionCard] = []

    # Isolated story nodes.
    full_orphans = scoring.orphan_nodes(
        graph,
        cap=max(50, graph.node_count),
    )
    full_orphan_keys = {node.key for node in full_orphans}
    eligible_orphans = [
        node for node in full_orphans
        if node.node_type in (
            P.NT_PSYKE_ENTRY, P.NT_CHARACTER, P.NT_PLACE, P.NT_OBJECT,
            P.NT_LORE, P.NT_THEME, P.NT_MOTIF, P.NT_PLOT_BLOCK,
        )
    ]
    for node in sorted(eligible_orphans, key=lambda item: item.key)[:5]:
        if node.node_type in (P.NT_PSYKE_ENTRY, P.NT_CHARACTER, P.NT_PLACE,
                              P.NT_OBJECT, P.NT_LORE, P.NT_THEME, P.NT_MOTIF):
            cards.append(_card(
                f"kg_isolated_{node.key}", "psyke", SEV_OPPORTUNITY, "likely",
                f"'{node.label}' is isolated in the graph.",
                "It has no connections to scenes or other entries.",
                "Reference it in a scene or relate it in PSYKE.", "Graph",
                graph_focus_key=node.key, evidence=[_node_evidence(node)]))
        elif node.node_type == P.NT_PLOT_BLOCK:
            cards.append(_card(
                f"kg_plot_{node.key}", "structure", SEV_SUGGESTION, "likely",
                f"Plot block '{node.label}' has no connected scenes.",
                "", "Assign scenes to this plot block.", "Outline",
                graph_focus_key=node.key, evidence=[_node_evidence(node)]))

    # Scenes with no PSYKE links.
    no_psyke = sorted(
        scoring.scenes_without_psyke(graph, cap=max(50, graph.node_count)),
        key=lambda item: item.key,
    )
    if no_psyke:
        scene_evidence = [
            _node_evidence(
                node,
                detail="Scene has no graph connection to a PSYKE entry.",
            )
            for node in no_psyke[:_EVIDENCE_CAP]
        ]
        cards.append(_card(
            "kg_scenes_no_psyke", "psyke", SEV_SUGGESTION, "likely",
            f"{len(no_psyke)} scene(s) have no PSYKE links.",
            "These scenes reference no tracked characters/places/objects.",
            "Link PSYKE entries or check the scene text.", "Manuscript",
            graph_focus_key=no_psyke[0].key,
            evidence=scene_evidence,
            evidence_total=len(no_psyke)))

    # Undefined note terms.
    if result.undefined_terms:
        undefined_total = max(
            len(result.undefined_terms),
            getattr(result, "undefined_term_total", 0),
        )
        term_evidence: list[DecisionEvidence] = []
        for term in sorted(result.undefined_terms)[:_EVIDENCE_CAP]:
            source_keys = result.undefined_term_sources.get(term, [])
            source_key = source_keys[0] if source_keys else ""
            note = graph.get_node(source_key) if source_key else None
            note_label = (
                note.label if note is not None and note.label else "project note"
            )
            term_evidence.append(DecisionEvidence(
                kind="term",
                label=f"{term} · {note_label}",
                detail="Undefined proper-noun candidate detected in this note.",
                graph_focus_key=source_key,
                confidence=P.CONF_POSSIBLE,
                source_system=P.SS_NOTES,
                provenance=P.PROV_NOTE_REFERENCE,
            ))
        term_focus = next(
            (item.graph_focus_key for item in term_evidence if item.graph_focus_key),
            "",
        )
        cards.append(_card(
            "kg_undefined_terms", "notes", SEV_OPPORTUNITY, "possible",
            f"{undefined_total} note term(s) not in PSYKE.",
            "e.g. " + ", ".join(result.undefined_terms[:3]),
            "Create PSYKE entries for recurring terms (review first).", "Notes",
            graph_focus_key=term_focus,
            evidence=term_evidence,
            evidence_total=undefined_total))

    # Many inferred edges needing confirmation.
    weak = scoring.weak_link_edges(graph, cap=max(50, graph.edge_count))
    if len(weak) >= 10:
        weak_evidence = [
            _edge_evidence(graph, edge) for edge in weak[:_EVIDENCE_CAP]
        ]
        cards.append(_card(
            "kg_many_inferred", "graph", SEV_SUGGESTION, "possible",
            f"{len(weak)} inferred edge(s) need review.",
            "Inferred links are not canonical until confirmed.",
            "Confirm or hide important inferred edges.", "Graph",
            graph_focus_key=weak[0].source,
            evidence=weak_evidence,
            evidence_total=len(weak)))

    # Themes that exist but connect to no scene.
    for theme in sorted(graph.nodes_of_type(P.NT_THEME), key=lambda item: item.key):
        if theme.key in full_orphan_keys:
            continue
        scene_linked = any(
            (graph.get_node(e.target if e.source == theme.key else e.source) or
             type("X", (), {"node_type": ""})()).node_type == P.NT_SCENE
            for e in graph.neighbors(theme.key))
        if not scene_linked:
            cards.append(_card(
                f"kg_theme_{theme.key}", "psyke", SEV_OPPORTUNITY, "likely",
                f"Theme '{theme.label}' is not connected to any scene.",
                "", "Tie the theme to the scenes that express it.", "PSYKE",
                graph_focus_key=theme.key, evidence=[_node_evidence(theme)]))
            break

    # Native Progressions diagnostics.  Emit at most one actionable card for
    # each issue class so Progressions cannot crowd every other Radar signal.
    # Document-block anchors are valid Whiteboard anchors and are deliberately
    # not treated as missing scene links.
    progression_tracks = sorted(
        graph.nodes_of_type(P.NT_PROGRESSION_TRACK),
        key=lambda node: (
            int(node.metadata.get("sort_order", 0)),
            int(node.source_id or 0),
        ),
    )

    def progression_target_id(node) -> int:
        return int(node.source_id or 0)

    def beat_evidence(track, beat_ids: list[int], detail: str):
        evidence = []
        for beat_id in beat_ids[:_EVIDENCE_CAP]:
            beat = graph.get_node(
                f"{P.NT_PROGRESSION_BEAT}:{P.SS_PROGRESSIONS}:{beat_id}"
            )
            if beat is not None:
                evidence.append(_node_evidence(
                    beat,
                    detail=detail,
                    related_section="Progressions",
                    related_target_type="progression_beat",
                    related_target_id=beat_id,
                ))
        if evidence:
            return evidence
        return [_node_evidence(
            track,
            detail=detail,
            related_section="Progressions",
            related_target_type="progression_track",
            related_target_id=progression_target_id(track),
        )]

    track_by_id = {
        progression_target_id(track): track for track in progression_tracks
    }
    diagnostics = dict(getattr(graph, "progression_diagnostics", {}) or {})
    if not diagnostics:
        out_tracks = [
            track for track in progression_tracks
            if track.metadata.get("out_of_order_beat_ids")
        ]
        unanchored_tracks = [
            track for track in progression_tracks
            if int(track.metadata.get("unanchored_beats", 0)) > 0
        ]
        empty_tracks = [
            track for track in progression_tracks
            if int(track.metadata.get("total_beats", 0)) == 0
        ]
        diagnostics = {
            "out_of_order": {
                "track_count": len(out_tracks),
                "beat_count": sum(
                    len(track.metadata.get("out_of_order_beat_ids", []))
                    for track in out_tracks
                ),
                "first_track_id": (
                    progression_target_id(out_tracks[0]) if out_tracks else None
                ),
                "evidence_beat_ids": [
                    int(beat_id)
                    for track in out_tracks
                    for beat_id in track.metadata.get(
                        "out_of_order_beat_ids", [],
                    )
                ][:_EVIDENCE_CAP],
            },
            "unanchored": {
                "track_count": len(unanchored_tracks),
                "beat_count": sum(
                    int(track.metadata.get("unanchored_beats", 0))
                    for track in unanchored_tracks
                ),
                "first_track_id": (
                    progression_target_id(unanchored_tracks[0])
                    if unanchored_tracks else None
                ),
                "evidence_beat_ids": [
                    int(node.source_id or 0)
                    for node in sorted(
                        graph.nodes_of_type(P.NT_PROGRESSION_BEAT),
                        key=lambda item: (
                            int(item.metadata.get("track_id", 0)),
                            int(item.metadata.get("sort_order", 0)),
                            int(item.source_id or 0),
                        ),
                    )
                    if node.metadata.get("anchor_kind") == "unanchored"
                ][:_EVIDENCE_CAP],
            },
            "empty": {
                "track_count": len(empty_tracks),
                "first_track_id": (
                    progression_target_id(empty_tracks[0])
                    if empty_tracks else None
                ),
                "evidence_track_ids": [
                    progression_target_id(track)
                    for track in empty_tracks[:_EVIDENCE_CAP]
                ],
            },
        }

    order_info = diagnostics.get("out_of_order", {})
    order_track_id = order_info.get("first_track_id")
    out_of_order_track = (
        track_by_id.get(int(order_track_id)) if order_track_id else None
    )
    if out_of_order_track is not None:
        track_id = progression_target_id(out_of_order_track)
        beat_ids = [
            int(beat_id)
            for beat_id in order_info.get("evidence_beat_ids", [])
        ]
        beat_total = int(order_info.get("beat_count", len(beat_ids)))
        track_total = int(order_info.get("track_count", 1))
        cards.append(_card(
            f"kg_progression_order_{track_id}",
            "progression", SEV_WARNING, "confirmed",
            (
                f"{beat_total} progression beat(s) across "
                f"{track_total} track(s) have out-of-order scene anchors."
            ),
            "Their explicit beat order moves backward through the manuscript.",
            "Review the beat order or scene anchors.",
            "Progressions",
            graph_focus_key=out_of_order_track.key,
            evidence=beat_evidence(
                out_of_order_track,
                beat_ids,
                "Beat is ordered after a beat anchored to a later scene.",
            ),
            evidence_total=beat_total,
            related_target_type="progression_track",
            related_target_id=track_id,
        ))

    unanchored_info = diagnostics.get("unanchored", {})
    unanchored_track_id = unanchored_info.get("first_track_id")
    unanchored_track = (
        track_by_id.get(int(unanchored_track_id))
        if unanchored_track_id else None
    )
    if unanchored_track is not None:
        track_id = progression_target_id(unanchored_track)
        unanchored_total = int(unanchored_info.get("beat_count", 0))
        unanchored_track_total = int(
            unanchored_info.get("track_count", 1)
        )
        evidence = beat_evidence(
            unanchored_track,
            [
                int(beat_id)
                for beat_id in unanchored_info.get("evidence_beat_ids", [])
            ],
            "Beat has no scene or document-block anchor.",
        )
        cards.append(_card(
            f"kg_progression_unanchored_{track_id}",
            "progression", SEV_SUGGESTION, "confirmed",
            (
                f"{unanchored_total} progression beat(s) across "
                f"{unanchored_track_total} track(s) are unanchored."
            ),
            "Unanchored beats cannot be located in manuscript or Drafter order.",
            "Anchor intentional story states and leave only genuinely global states unanchored.",
            "Progressions",
            graph_focus_key=unanchored_track.key,
            evidence=evidence,
            evidence_total=unanchored_total,
            related_target_type="progression_track",
            related_target_id=track_id,
        ))

    empty_info = diagnostics.get("empty", {})
    empty_track_id = empty_info.get("first_track_id")
    empty_track = (
        track_by_id.get(int(empty_track_id)) if empty_track_id else None
    )
    if empty_track is not None:
        track_id = progression_target_id(empty_track)
        empty_total = int(empty_info.get("track_count", 1))
        evidence_tracks = [
            track_by_id.get(int(evidence_track_id))
            for evidence_track_id in empty_info.get("evidence_track_ids", [])
        ]
        evidence_tracks = [
            track for track in evidence_tracks if track is not None
        ] or [empty_track]
        cards.append(_card(
            f"kg_progression_empty_{track_id}",
            "progression", SEV_OPPORTUNITY, "confirmed",
            f"{empty_total} progression track(s) have no beats.",
            "These tracks define intended arcs but record no state changes yet.",
            "Add their first progression beats or remove unused tracks.",
            "Progressions",
            graph_focus_key=empty_track.key,
            evidence=[_node_evidence(
                track,
                detail="Native progression track has zero beats.",
                related_section="Progressions",
                related_target_type="progression_track",
                related_target_id=progression_target_id(track),
            ) for track in evidence_tracks[:_EVIDENCE_CAP]],
            evidence_total=empty_total,
            related_target_type="progression_track",
            related_target_id=track_id,
        ))

    # Rewrite/revision risk touching a central node.
    story_node_types = {
        P.NT_SCENE, P.NT_CHARACTER, P.NT_PLACE, P.NT_OBJECT, P.NT_LORE,
        P.NT_THEME, P.NT_MOTIF, P.NT_PSYKE_ENTRY, P.NT_NOTE,
        P.NT_PLOT_BLOCK,
    }
    full_central = scoring.high_centrality_nodes(
        graph,
        top=max(10, graph.node_count),
    )
    central_story_nodes = [
        node for node, _ in full_central
        if node.node_type in story_node_types
    ][:5]
    central_keys = {node.key for node in central_story_nodes}
    for e in sorted(graph.visible_edges(), key=lambda item: item.dedupe_key):
        if graph.get_node(e.source) is None or graph.get_node(e.target) is None:
            continue
        if e.edge_type in (P.ET_RISKS, P.ET_CONTRADICTS) and (
                e.source in central_keys or e.target in central_keys):
            focus_key = e.source if e.source in central_keys else e.target
            cards.append(_card(
                "kg_risk_central", "continuity", SEV_WARNING, "likely",
                "A rewrite/revision risk touches a central story element.",
                e.explanation, "Review the impact before applying.", "Manuscript",
                graph_focus_key=focus_key,
                graph_view_mode="recorded_risk",
                evidence=[_edge_evidence(graph, e, focus_key=focus_key)]))
            break

    cards.sort(key=lambda card: (card.rank, card.id))
    return cards[:max(0, cap)]
