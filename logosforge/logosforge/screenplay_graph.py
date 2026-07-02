"""Screenplay story-link graph (Phase 10E).

Turns the existing screenplay data — scene structure, parsed blocks, PSYKE
entries, setup/payoff candidates, subtext signals — plus user-confirmed
``StoryLink`` rows into a lightweight node/edge graph for visualization and
reporting.

Source-of-truth rule: the graph **references** existing entities (by id), never
copies scene/PSYKE text. Generated edges are *candidates*; only links the user
explicitly confirms are persisted (via :func:`confirm_candidate`). Building is
read-only, deterministic, no LLM, no DB mutation.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

# -- Node / edge / status vocab ----------------------------------------------
NODE_TYPES = (
    "scene", "act", "sequence", "character", "psyke_entry", "setup", "payoff",
    "motif", "object", "promise", "threat", "subtext", "objective", "diagnostic",
)
EDGE_TYPES = (
    "setup_to_payoff", "motif_recurrence", "promise_to_consequence",
    "threat_to_consequence", "object_plant_to_use", "character_in_scene",
    "objective_to_turn", "subtext_to_character", "psyke_to_scene",
    "scene_to_sequence", "sequence_to_act", "diagnostic_to_scene",
)
STATUSES = ("candidate", "confirmed", "dismissed", "resolved", "inferred")

SCHEMA_VERSION = 1


@dataclass
class ScreenplayGraphNode:
    id: str
    node_type: str
    label: str
    source_type: str = ""
    source_id: str = ""
    scene_id: int | None = None
    confidence: float | None = None
    status: str = "inferred"
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "node_type": self.node_type, "label": self.label,
            "source_type": self.source_type, "source_id": self.source_id,
            "scene_id": self.scene_id,
            "confidence": (round(self.confidence, 2) if self.confidence is not None else None),
            "status": self.status, "metadata": dict(self.metadata),
        }


@dataclass
class ScreenplayGraphEdge:
    id: str
    edge_type: str
    source_node_id: str
    target_node_id: str
    label: str = ""
    confidence: float | None = None
    status: str = "candidate"
    evidence: str = ""
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "edge_type": self.edge_type,
            "source_node_id": self.source_node_id,
            "target_node_id": self.target_node_id, "label": self.label,
            "confidence": (round(self.confidence, 2) if self.confidence is not None else None),
            "status": self.status, "evidence": self.evidence,
            "metadata": dict(self.metadata),
        }


@dataclass
class ScreenplayGraph:
    project_id: int
    nodes: list[ScreenplayGraphNode] = field(default_factory=list)
    edges: list[ScreenplayGraphEdge] = field(default_factory=list)
    summary: str = ""
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "project_id": self.project_id,
            "nodes": [n.to_dict() for n in self.nodes],
            "edges": [e.to_dict() for e in self.edges],
            "summary": self.summary,
            "warnings": list(self.warnings),
        }


def is_valid_edge_type(edge_type: str) -> bool:
    return edge_type in EDGE_TYPES


def _eid(*parts) -> str:
    import hashlib
    raw = ":".join(str(p) for p in parts)
    return "e_" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------


def build_screenplay_graph(
    db, project_id: int, *, scene_id: int | None = None,
    include_candidates: bool = True, include_confirmed: bool = True,
) -> ScreenplayGraph:
    """Build the screenplay story-link graph (read-only, deterministic).

    *scene_id* scopes structural/character/subtext nodes to one scene when given
    (setup/payoff are inherently cross-scene and always project-wide). No DB
    mutation, no LLM, no stale leak (everything is read from the passed project).
    """
    graph = ScreenplayGraph(project_id=project_id)
    nodes: dict[str, ScreenplayGraphNode] = {}
    edges: dict[str, ScreenplayGraphEdge] = {}

    def add_node(node: ScreenplayGraphNode) -> str:
        nodes.setdefault(node.id, node)        # dedupe by id
        return node.id

    def add_edge(edge: ScreenplayGraphEdge) -> None:
        if not is_valid_edge_type(edge.edge_type):
            return
        edges.setdefault(edge.id, edge)

    try:
        scenes = db.get_all_scenes(project_id)
    except Exception:
        scenes = []
    if scene_id is not None:
        scenes = [s for s in scenes if s.id == scene_id]

    from logosforge import screenplay_blocks as sb

    # --- Structure + characters + subtext (scene-scoped when scene_id set) ---
    for scene in scenes:
        snode = ScreenplayGraphNode(
            id=f"scene:{scene.id}", node_type="scene",
            label=(getattr(scene, "title", "") or f"Scene {scene.id}"),
            source_type="scene", source_id=str(scene.id), scene_id=scene.id,
        )
        add_node(snode)
        act = (getattr(scene, "act", "") or "").strip()
        if act:
            anode = ScreenplayGraphNode(
                id=f"act:{act}", node_type="act", label=act,
                source_type="outline", source_id=act,
            )
            add_node(anode)
            add_edge(ScreenplayGraphEdge(
                id=_eid("scene_to_act", scene.id, act),
                edge_type="sequence_to_act", source_node_id=snode.id,
                target_node_id=anode.id, label="in act", status="inferred",
            ))
        if include_candidates:
            blocks = sb.parse_screenplay_text(getattr(scene, "content", "") or "",
                                              scene_id=scene.id)
            for cue in sb.character_cues(blocks):
                cnode = ScreenplayGraphNode(
                    id=f"character:{cue}", node_type="character", label=cue,
                    source_type="scene", source_id=cue,
                )
                add_node(cnode)
                add_edge(ScreenplayGraphEdge(
                    id=_eid("char_in", cue, scene.id), edge_type="character_in_scene",
                    source_node_id=cnode.id, target_node_id=snode.id,
                    label="appears in", status="inferred",
                ))

    # --- Subtext links (scene-scoped) ---
    if include_candidates:
        try:
            from logosforge.screenplay_subtext import analyze_subtext_project
            for rep in analyze_subtext_project(db, project_id):
                if scene_id is not None and rep.scene_id != scene_id:
                    continue
                for s in rep.top_signals(5):
                    sub_node = ScreenplayGraphNode(
                        id=f"subtext:{rep.scene_id}:{s.signal_type}",
                        node_type="subtext", label=s.signal_type,
                        source_type="subtext", source_id=str(rep.scene_id),
                        scene_id=rep.scene_id, confidence=s.confidence,
                        status="candidate",
                    )
                    add_node(sub_node)
                    if s.character_name:
                        cnode_id = add_node(ScreenplayGraphNode(
                            id=f"character:{s.character_name}", node_type="character",
                            label=s.character_name, source_type="subtext",
                            source_id=s.character_name))
                        add_edge(ScreenplayGraphEdge(
                            id=_eid("subtext_char", rep.scene_id, s.signal_type, s.character_name),
                            edge_type="subtext_to_character", source_node_id=sub_node.id,
                            target_node_id=cnode_id, label=s.signal_type,
                            confidence=s.confidence, status="candidate", evidence=s.evidence))
        except Exception:
            pass

    # --- Setup/payoff + motif (always project-wide; inherently cross-scene) ---
    if include_candidates:
        try:
            from logosforge.screenplay_setup_payoff import analyze_setup_payoff
            sp = analyze_setup_payoff(db, project_id)
            for c in sp.recurring_motifs:
                mid = add_node(ScreenplayGraphNode(
                    id=f"motif:{c.label}", node_type="motif", label=c.label,
                    source_type="setup_payoff", source_id=c.id, scene_id=c.scene_id,
                    confidence=c.confidence, status="candidate"))
            for c in sp.possible_payoffs:
                pid_node = add_node(ScreenplayGraphNode(
                    id=f"payoff:{c.id}", node_type="payoff", label=c.label,
                    source_type="setup_payoff", source_id=c.id, scene_id=c.scene_id,
                    confidence=c.confidence, status="candidate"))
                if c.linked_scene_id is not None:
                    src = add_node(ScreenplayGraphNode(
                        id=f"scene:{c.linked_scene_id}", node_type="scene",
                        label=f"Scene {c.linked_scene_id}", source_type="scene",
                        source_id=str(c.linked_scene_id), scene_id=c.linked_scene_id))
                    add_edge(ScreenplayGraphEdge(
                        id=_eid("setup_payoff", c.linked_scene_id, c.id),
                        edge_type="setup_to_payoff", source_node_id=src,
                        target_node_id=pid_node, label="possible payoff",
                        confidence=c.confidence, status="candidate", evidence=c.evidence))
            for c in sp.unresolved_setups:
                add_node(ScreenplayGraphNode(
                    id=f"setup:{c.id}", node_type="setup", label=c.label,
                    source_type="setup_payoff", source_id=c.id, scene_id=c.scene_id,
                    confidence=c.confidence, status="candidate"))
                if c.linked_psyke_entry_id is not None:
                    pnode = add_node(ScreenplayGraphNode(
                        id=f"psyke:{c.linked_psyke_entry_id}", node_type="psyke_entry",
                        label=f"PSYKE {c.linked_psyke_entry_id}", source_type="psyke",
                        source_id=str(c.linked_psyke_entry_id)))
                    if c.scene_id is not None:
                        add_node(ScreenplayGraphNode(
                            id=f"scene:{c.scene_id}", node_type="scene",
                            label=f"Scene {c.scene_id}", source_type="scene",
                            source_id=str(c.scene_id), scene_id=c.scene_id))
                        add_edge(ScreenplayGraphEdge(
                            id=_eid("psyke_scene", c.linked_psyke_entry_id, c.scene_id),
                            edge_type="psyke_to_scene", source_node_id=pnode,
                            target_node_id=f"scene:{c.scene_id}", label="referenced in",
                            status="inferred", evidence=c.evidence))
        except Exception:
            pass

    # --- Confirmed user links (persisted StoryLinks) ---
    if include_confirmed:
        try:
            for link in db.get_story_links(project_id):
                if link.status == "dismissed":
                    continue
                src = add_node(ScreenplayGraphNode(
                    id=f"{link.source_type}:{link.source_id}",
                    node_type=link.source_type if link.source_type in NODE_TYPES else "scene",
                    label=link.source_type or "source", source_type="confirmed_link",
                    source_id=link.source_id, scene_id=link.source_scene_id,
                    status=link.status))
                tgt = add_node(ScreenplayGraphNode(
                    id=f"{link.target_type}:{link.target_id}",
                    node_type=link.target_type if link.target_type in NODE_TYPES else "scene",
                    label=link.target_type or "target", source_type="confirmed_link",
                    source_id=link.target_id, scene_id=link.target_scene_id,
                    status=link.status))
                if is_valid_edge_type(link.link_type):
                    add_edge(ScreenplayGraphEdge(
                        id=f"link:{link.id}", edge_type=link.link_type,
                        source_node_id=src, target_node_id=tgt,
                        label=link.label or link.link_type, confidence=link.confidence,
                        status=link.status, evidence=link.evidence,
                        metadata={"story_link_id": link.id}))
        except Exception:
            pass

    graph.nodes = list(nodes.values())
    graph.edges = list(edges.values())
    n_conf = sum(1 for e in graph.edges if e.status in ("confirmed", "resolved"))
    n_cand = sum(1 for e in graph.edges if e.status == "candidate")
    graph.summary = (
        f"{len(graph.nodes)} node(s), {len(graph.edges)} edge(s) "
        f"({n_conf} confirmed, {n_cand} candidate)."
    )
    return graph


# ---------------------------------------------------------------------------
# Confirmation service (explicit user actions only — never automatic)
# ---------------------------------------------------------------------------


def confirm_candidate(db, project_id: int, *, link_type: str, label: str,
                      source_type: str, source_id: str, target_type: str,
                      target_id: str, source_scene_id: int | None = None,
                      target_scene_id: int | None = None, evidence: str = "",
                      confidence: float = 0.0, metadata: dict | None = None):
    """Persist a user-confirmed story link. Caller must have obtained explicit
    user confirmation first — this is never invoked by analysis code."""
    return db.create_story_link(
        project_id, link_type=link_type, label=label, source_type=source_type,
        source_id=source_id, target_type=target_type, target_id=target_id,
        source_scene_id=source_scene_id, target_scene_id=target_scene_id,
        evidence=evidence, confidence=confidence, status="confirmed",
        metadata_json=json.dumps(metadata or {}),
    )


def dismiss_link(db, link_id: int):
    return db.update_story_link_status(link_id, "dismissed")


def resolve_link(db, link_id: int):
    return db.update_story_link_status(link_id, "resolved")
