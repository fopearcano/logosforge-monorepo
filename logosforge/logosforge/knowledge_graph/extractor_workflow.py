"""Guided Workflows + Setup/Payoff → Knowledge Graph extraction (10P).

Workflow runs (10O) become workflow nodes attached to the project. Setup/Payoff
adds explicit ``confirmed`` links where they exist and inferred ``possible``
candidate links (screenplay analysis), clearly marked. Both degrade cleanly when
the underlying system was deferred.
"""

from __future__ import annotations

from logosforge.knowledge_graph import provenance as P
from logosforge.knowledge_graph.models import KGEdge, KGNode, node_key

_MAX = 100


def extract_workflows(db, project_id: int, graph) -> None:
    try:
        runs = db.get_workflow_runs(project_id)
    except Exception:
        graph.unavailable.append("guided_workflows")
        return
    project_key = node_key(P.NT_PROJECT, "project", project_id)
    for run in runs[:_MAX]:
        if getattr(run, "status", "") in ("cancelled",):
            continue
        rkey = node_key(P.NT_WORKFLOW_RUN, "workflow", run.id)
        graph.add_node(KGNode(
            key=rkey, node_type=P.NT_WORKFLOW_RUN, source_type="workflow",
            source_id=str(run.id), label=(getattr(run, "title", "") or "Workflow"),
            summary=f"status={getattr(run, 'status', '')}",
            metadata={"status": getattr(run, "status", "")}))
        graph.add_edge(KGEdge(
            source=project_key, target=rkey, edge_type=P.ET_SUGGESTED_BY,
            confidence=P.CONF_CONFIRMED, provenance=P.PROV_WORKFLOW,
            source_system=P.SS_WORKFLOW, explanation="Guided workflow run."))


def extract_setup_payoff(db, project_id: int, graph) -> None:
    """Inferred setup/payoff candidate links (screenplay analysis). Explicit
    setup/payoff scene links + confirmed StoryLinks are handled in the structure
    extractor; this adds the *possible* candidate layer only."""
    try:
        from logosforge.writing_modes import get_project_writing_mode_by_id
        if get_project_writing_mode_by_id(db, project_id) != "screenplay":
            graph.unavailable.append("setup_payoff")
            return
        from logosforge.screenplay_setup_payoff import analyze_setup_payoff
        report = analyze_setup_payoff(db, project_id)
    except Exception:
        graph.unavailable.append("setup_payoff")
        return

    count = 0
    for cand in (report.candidates or [])[:_MAX]:
        sid = getattr(cand, "scene_id", None)
        if sid is None:
            continue
        scene_key = node_key(P.NT_SCENE, "scene", sid)
        ctype = getattr(cand, "candidate_type", "") or "setup"
        node_t = P.NT_PAYOFF if "payoff" in ctype else P.NT_SETUP
        ckey = node_key(node_t, "setup_payoff", getattr(cand, "id", f"{sid}:{count}"))
        graph.add_node(KGNode(
            key=ckey, node_type=node_t, source_type="setup_payoff",
            source_id=str(getattr(cand, "id", "")),
            label=(getattr(cand, "label", "") or ctype),
            summary=(getattr(cand, "evidence", "") or "")[:160]))
        graph.add_edge(KGEdge(
            source=scene_key, target=ckey,
            edge_type=(P.ET_PAYS_OFF if node_t == P.NT_PAYOFF else P.ET_SETS_UP),
            confidence=P.CONF_POSSIBLE, provenance=P.PROV_SETUP_PAYOFF,
            source_system=P.SS_SETUP_PAYOFF,
            explanation="Inferred setup/payoff candidate (needs confirmation)."))
        pid_link = getattr(cand, "linked_psyke_entry_id", None)
        if pid_link:
            graph.add_edge(KGEdge(
                source=ckey, target=node_key(P.NT_PSYKE_ENTRY, "psyke", pid_link),
                edge_type=P.ET_RELATES_TO, confidence=P.CONF_POSSIBLE,
                provenance=P.PROV_SETUP_PAYOFF, source_system=P.SS_SETUP_PAYOFF,
                explanation="Candidate involves this PSYKE entry."))
        count += 1
