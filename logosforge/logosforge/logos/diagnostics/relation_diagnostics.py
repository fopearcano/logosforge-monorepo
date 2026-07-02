"""Relationship / graph-structure diagnostics (PSYKE relations + link graph)."""

from __future__ import annotations

from logosforge.logos.diagnostics.diagnostic import (
    CAT_GRAPH,
    CAT_RELATIONSHIP,
    SEVERITY_INFO,
    SEVERITY_WARNING,
    NarrativeDiagnostic,
)
from logosforge.logos.diagnostics.model import ProjectFacts

_OVERCONNECTED = 6  # neighbours above which a node looks like a hub


def detect_relations(facts: ProjectFacts) -> list[NarrativeDiagnostic]:
    out: list[NarrativeDiagnostic] = []
    name_to_appears = {e.name.lower(): facts.appearances.get(e.id, []) for e in facts.entries}

    for e in facts.entries:
        relations = facts.relations.get(e.id, [])
        appears = facts.appearances.get(e.id, [])
        n_app = len(appears)
        neighbours = facts.adjacency.get(e.name.lower(), set())

        # Important (recurring) entry with no relations.
        if not relations and n_app >= 2 and e.entry_type in ("character", "theme"):
            out.append(NarrativeDiagnostic(
                category=CAT_RELATIONSHIP, section_name="PSYKE",
                title=f"'{e.name}' has no relations",
                message="A recurring entry that is not related to anything.",
                evidence=f"0 relations; appears in {n_app} scene(s).",
                confidence=min(0.9, 0.7 + 0.04 * n_app), severity=SEVERITY_WARNING,
                target_type="psyke_entry", target_id=str(e.id),
                related_psyke_entry_ids=[e.id],
                suggested_actions=["check_relationships", "suggest_relations"],
            ))

        # Relation with no shared scene (no scene references both entities).
        for related, rtype in relations:
            shared = _shared_scene(facts, e.id, related.id)
            if not shared and e.id < related.id:  # report each pair once
                out.append(NarrativeDiagnostic(
                    category=CAT_RELATIONSHIP, section_name="PSYKE",
                    title=f"'{e.name}' ↔ '{related.name}' never share a scene",
                    message="These entries are related but co-occur in no scene.",
                    evidence=f"Relation '{rtype or 'generic'}' but 0 scenes "
                             "reference both.",
                    confidence=0.68, severity=SEVERITY_INFO,
                    target_type="psyke_relation",
                    target_id=f"{e.id}:{related.id}",
                    related_psyke_entry_ids=[e.id, related.id],
                    suggested_actions=["explain_relationship_cluster",
                                       "suggest_psyke_relation"],
                ))

        # Isolated important node: no relations and no graph links.
        if (not relations and not neighbours
                and e.entry_type in ("character", "theme")):
            out.append(NarrativeDiagnostic(
                category=CAT_GRAPH, section_name="Graph",
                title=f"'{e.name}' is isolated in the graph",
                message="This entry has no relationships or graph links.",
                evidence=f"0 PSYKE relations; 0 graph links; type={e.entry_type}.",
                confidence=0.8, severity=SEVERITY_WARNING,
                target_type="graph_node", target_id=f"PSYKE:{e.id}",
                related_psyke_entry_ids=[e.id],
                suggested_actions=["identify_isolated_node", "suggest_psyke_relation"],
            ))

        # Over-connected hub with many weak (generic) links.
        if len(neighbours) >= _OVERCONNECTED:
            generic = sum(1 for _r, rt in relations if not (rt or "").strip())
            if generic >= 3 or not relations:
                out.append(NarrativeDiagnostic(
                    category=CAT_GRAPH, section_name="Graph",
                    title=f"'{e.name}' is over-connected with weak links",
                    message="This node has many links but little typed structure.",
                    evidence=f"{len(neighbours)} graph neighbours; "
                             f"{generic} generic/empty relation type(s).",
                    confidence=0.66, severity=SEVERITY_INFO,
                    target_type="graph_node", target_id=f"PSYKE:{e.id}",
                    related_psyke_entry_ids=[e.id],
                    suggested_actions=["explain_relationship_cluster",
                                       "check_thematic_cluster"],
                ))
    return out


def _shared_scene(facts: ProjectFacts, a_id: int, b_id: int) -> bool:
    a = set(facts.appearances.get(a_id, []))
    b = set(facts.appearances.get(b_id, []))
    return bool(a & b)
