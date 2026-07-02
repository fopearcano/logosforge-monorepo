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
)


def build_graph_decision_cards(db, project_id: int, *, result=None, cap: int = 8,
                               ) -> list[DecisionCard]:
    if result is None:
        result = build_knowledge_graph(db, project_id)
    graph = result.graph
    cards: list[DecisionCard] = []

    # Isolated story nodes.
    for node in result.orphans[:5]:
        if node.node_type in (P.NT_PSYKE_ENTRY, P.NT_CHARACTER, P.NT_PLACE,
                              P.NT_OBJECT, P.NT_LORE, P.NT_THEME, P.NT_MOTIF):
            cards.append(DecisionCard(
                f"kg_isolated_{node.key}", "psyke", SEV_OPPORTUNITY, "likely",
                f"'{node.label}' is isolated in the graph.",
                "It has no connections to scenes or other entries.",
                "Reference it in a scene or relate it in PSYKE.", "Graph"))
        elif node.node_type == P.NT_PLOT_BLOCK:
            cards.append(DecisionCard(
                f"kg_plot_{node.key}", "structure", SEV_SUGGESTION, "likely",
                f"Plot block '{node.label}' has no connected scenes.",
                "", "Assign scenes to this plot block.", "Outline"))

    # Scenes with no PSYKE links.
    no_psyke = scoring.scenes_without_psyke(graph)
    if no_psyke:
        cards.append(DecisionCard(
            "kg_scenes_no_psyke", "psyke", SEV_SUGGESTION, "likely",
            f"{len(no_psyke)} scene(s) have no PSYKE links.",
            "These scenes reference no tracked characters/places/objects.",
            "Link PSYKE entries or check the scene text.", "Manuscript"))

    # Undefined note terms.
    if result.undefined_terms:
        cards.append(DecisionCard(
            "kg_undefined_terms", "notes", SEV_OPPORTUNITY, "possible",
            f"{len(result.undefined_terms)} note term(s) not in PSYKE.",
            "e.g. " + ", ".join(result.undefined_terms[:3]),
            "Create PSYKE entries for recurring terms (review first).", "Notes"))

    # Many inferred edges needing confirmation.
    weak = scoring.weak_link_edges(graph)
    if len(weak) >= 10:
        cards.append(DecisionCard(
            "kg_many_inferred", "graph", SEV_SUGGESTION, "possible",
            f"{len(weak)} inferred edge(s) need review.",
            "Inferred links are not canonical until confirmed.",
            "Confirm or hide important inferred edges.", "Graph"))

    # Themes that exist but connect to no scene.
    for theme in graph.nodes_of_type(P.NT_THEME):
        scene_linked = any(
            (graph.get_node(e.target if e.source == theme.key else e.source) or
             type("X", (), {"node_type": ""})()).node_type == P.NT_SCENE
            for e in graph.neighbors(theme.key))
        if not scene_linked:
            cards.append(DecisionCard(
                f"kg_theme_{theme.key}", "psyke", SEV_OPPORTUNITY, "likely",
                f"Theme '{theme.label}' is not connected to any scene.",
                "", "Tie the theme to the scenes that express it.", "PSYKE"))
            break

    # Rewrite/revision risk touching a central node.
    central_keys = {n.key for n, _ in result.central[:5]}
    for e in graph.visible_edges():
        if e.edge_type in (P.ET_RISKS, P.ET_CONTRADICTS) and (
                e.source in central_keys or e.target in central_keys):
            cards.append(DecisionCard(
                "kg_risk_central", "continuity", SEV_WARNING, "likely",
                "A rewrite/revision risk touches a central story element.",
                e.explanation, "Review the impact before applying.", "Manuscript"))
            break

    cards.sort(key=lambda c: c.rank)
    return cards[:cap]
