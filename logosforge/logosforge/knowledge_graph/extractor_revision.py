"""Revision / Rewrite / Controlled-Apply → Knowledge Graph extraction (10P).

These produce *risk / workflow* nodes that touch story elements — they never
change the canonical meaning of the graph. Open/unapplied rewrite variants and
pending applies appear as workflow nodes; rejected variants are skipped unless
explicitly requested. All deferred systems degrade cleanly.
"""

from __future__ import annotations

from logosforge.knowledge_graph import provenance as P
from logosforge.knowledge_graph.models import KGEdge, KGNode, node_key

_MAX = 200

# target_type (from impact items / apply ops) -> graph node type + source_type.
_TARGET_NODE = {
    "scene": (P.NT_SCENE, "scene"),
    "psyke_entry": (P.NT_PSYKE_ENTRY, "psyke"),
    "psyke": (P.NT_PSYKE_ENTRY, "psyke"),
    "note": (P.NT_NOTE, "note"),
}


def _target_key(target_type: str, target_id) -> str | None:
    spec = _TARGET_NODE.get((target_type or "").lower())
    if spec is None or target_id in (None, ""):
        return None
    nt, st = spec
    return node_key(nt, st, target_id)


def extract_revision(db, project_id: int, graph) -> None:
    """Revision Intelligence impact reports + items."""
    try:
        reports = db.get_revision_impact_reports(project_id)
    except Exception:
        graph.unavailable.append("revision_intelligence")
        return
    for rep in reports[:_MAX]:
        rkey = node_key(P.NT_REVISION_IMPACT, "revision", rep.id)
        graph.add_node(KGNode(
            key=rkey, node_type=P.NT_REVISION_IMPACT, source_type="revision",
            source_id=str(rep.id), label=(getattr(rep, "title", "") or "Impact report"),
            summary=(getattr(rep, "summary", "") or "")[:160],
            metadata={"impact_level": getattr(rep, "impact_level", "low")}))
        sid = getattr(rep, "scene_id", None)
        if sid:
            graph.add_edge(KGEdge(
                source=rkey, target=node_key(P.NT_SCENE, "scene", sid),
                edge_type=P.ET_REVISES, confidence=getattr(rep, "confidence", "likely"),
                provenance=P.PROV_REVISION_IMPACT, source_system=P.SS_REVISION,
                explanation="Impact report for this scene's change."))
        try:
            items = db.get_revision_impact_items(rep.id)
        except Exception:
            items = []
        for it in items[:_MAX]:
            tkey = _target_key(getattr(it, "target_type", ""),
                               getattr(it, "target_id", ""))
            if tkey is None:
                continue
            graph.add_edge(KGEdge(
                source=rkey, target=tkey, edge_type=P.ET_RISKS,
                confidence=getattr(it, "confidence", "possible"),
                provenance=P.PROV_REVISION_IMPACT, source_system=P.SS_REVISION,
                explanation=(getattr(it, "explanation", "")
                             or "Revision risk touches this element.")))


def extract_rewrite(db, project_id: int, graph) -> None:
    """Rewrite Sandbox sessions + variants (open/preferred only as workflow nodes)."""
    try:
        sessions = db.get_rewrite_sessions(project_id)
    except Exception:
        graph.unavailable.append("rewrite_sandbox")
        return
    for sess in sessions[:_MAX]:
        if getattr(sess, "status", "") in ("discarded", "archived"):
            continue
        src_type = (getattr(sess, "source_type", "") or "scene").lower()
        src_id = getattr(sess, "source_id", None)
        src_key = None
        if src_type in ("scene", "manuscript") and src_id:
            src_key = node_key(P.NT_SCENE, "scene", src_id)
        try:
            variants = db.get_rewrite_variants(sess.id)
        except Exception:
            variants = []
        for v in variants[:_MAX]:
            if getattr(v, "status", "") == "rejected":
                continue  # rejected variants hidden unless explicitly requested
            vkey = node_key(P.NT_REWRITE_VARIANT, "rewrite_variant", v.id)
            graph.add_node(KGNode(
                key=vkey, node_type=P.NT_REWRITE_VARIANT,
                source_type="rewrite_variant", source_id=str(v.id),
                label=(getattr(v, "label", "") or getattr(v, "strategy", "")
                       or "Rewrite variant"),
                summary=(getattr(v, "prompt_summary", "") or "")[:160],
                metadata={"status": getattr(v, "status", "candidate")}))
            if src_key:
                graph.add_edge(KGEdge(
                    source=vkey, target=src_key, edge_type=P.ET_DERIVED_FROM,
                    confidence=P.CONF_CONFIRMED, provenance=P.PROV_REWRITE_TARGET,
                    source_system=P.SS_REWRITE,
                    explanation=f"Rewrite variant ({getattr(v, 'status', '')}) "
                                f"of this source."))


def extract_apply(db, project_id: int, graph) -> None:
    """Controlled Apply operations + conflicts (targets + risks)."""
    try:
        ops = db.get_apply_operations(project_id)
    except Exception:
        graph.unavailable.append("controlled_apply")
        return
    for op in ops[:_MAX]:
        okey = node_key(P.NT_CONTROLLED_APPLY, "apply", op.id)
        graph.add_node(KGNode(
            key=okey, node_type=P.NT_CONTROLLED_APPLY, source_type="apply",
            source_id=str(op.id), label=f"Apply #{op.id} ({getattr(op, 'status', '')})",
            summary=(getattr(op, "after_excerpt", "") or "")[:160],
            metadata={"status": getattr(op, "status", "draft")}))
        tkey = _target_key(getattr(op, "target_type", ""), getattr(op, "target_id", None))
        if tkey is None and (getattr(op, "target_type", "") or "") in ("scene", "manuscript") \
                and getattr(op, "target_id", None):
            tkey = node_key(P.NT_SCENE, "scene", op.target_id)
        if tkey is not None:
            applied = getattr(op, "status", "") == "applied"
            graph.add_edge(KGEdge(
                source=okey, target=tkey,
                edge_type=(P.ET_REVISES if applied else P.ET_RISKS),
                confidence=(P.CONF_CONFIRMED if applied else P.CONF_LIKELY),
                provenance=P.PROV_APPLY_TARGET, source_system=P.SS_CONTROLLED_APPLY,
                is_user_confirmed=applied,
                explanation=("Applied change to this target." if applied
                             else "Pending apply targets this element.")))
        try:
            conflicts = db.get_apply_conflicts(op.id)
        except Exception:
            conflicts = []
        if conflicts and tkey is not None:
            graph.add_edge(KGEdge(
                source=okey, target=tkey, edge_type=P.ET_CONTRADICTS,
                confidence=P.CONF_LIKELY, provenance=P.PROV_APPLY_CONFLICT,
                source_system=P.SS_CONTROLLED_APPLY,
                explanation=f"{len(conflicts)} conflict(s) on this apply."))
