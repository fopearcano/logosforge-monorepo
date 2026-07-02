"""Read-only collectors for the Project Intelligence Dashboard (Phase 10N).

Each collector reads an existing subsystem and returns a small, serializable
summary. No DB mutation, no LLM, no Qt, no new narrative data. Tolerant of
deferred/unavailable systems (returns a clean "available: False").
"""

from __future__ import annotations

import re
from typing import Any


def _writing_mode(db, project_id: int) -> str:
    try:
        from logosforge.writing_modes import get_project_writing_mode_by_id
        return get_project_writing_mode_by_id(db, project_id)
    except Exception:
        return "novel"


def _words(text: str) -> int:
    return len(re.findall(r"\S+", text or ""))


def collect_overview(db, project_id: int) -> dict[str, Any]:
    project = None
    try:
        project = db.get_project_by_id(project_id)
    except Exception:
        project = None
    try:
        scenes = db.get_all_scenes(project_id)
    except Exception:
        scenes = []
    try:
        notes = db.get_all_notes(project_id)
    except Exception:
        notes = []
    try:
        psyke = db.get_all_psyke_entries(project_id)
    except Exception:
        psyke = []
    acts = {(getattr(s, "act", "") or "").strip() for s in scenes if (getattr(s, "act", "") or "").strip()}
    chapters = {(getattr(s, "chapter", "") or "").strip() for s in scenes if (getattr(s, "chapter", "") or "").strip()}
    total_words = sum(_words(getattr(s, "content", "") or "") for s in scenes)
    return {
        "title": getattr(project, "title", "") or "Untitled",
        "writing_mode": _writing_mode(db, project_id),
        "description_present": bool((getattr(project, "description", "") or "").strip()),
        "total_words": total_words,
        "total_scenes": len(scenes),
        "total_chapters": len(chapters),
        "total_acts": len(acts),
        "total_notes": len(notes),
        "total_psyke_entries": len(psyke),
    }


def collect_psyke_summary(db, project_id: int) -> dict[str, Any]:
    try:
        entries = db.get_all_psyke_entries(project_id)
    except Exception:
        return {"available": False}
    by_type: dict[str, int] = {}
    empty_notes = no_relations = global_count = 0
    for e in entries:
        et = (getattr(e, "entry_type", "") or "other").lower()
        by_type[et] = by_type.get(et, 0) + 1
        if not (getattr(e, "notes", "") or "").strip():
            empty_notes += 1
        if getattr(e, "is_global", False):
            global_count += 1
        try:
            if not db.get_related_psyke_entries(e.id):
                no_relations += 1
        except Exception:
            pass
    return {
        "available": True, "total": len(entries), "by_type": by_type,
        "global_count": global_count, "empty_notes": empty_notes,
        "no_relations": no_relations,
    }


def collect_structure_summary(db, project_id: int) -> dict[str, Any]:
    try:
        scenes = db.get_all_scenes(project_id)
    except Exception:
        scenes = []
    scenes_no_chapter = sum(1 for s in scenes if not (getattr(s, "chapter", "") or "").strip())
    scenes_no_summary = sum(1 for s in scenes if not (getattr(s, "summary", "") or "").strip())
    try:
        outline = db.get_outline_nodes(project_id)
    except Exception:
        outline = []
    isolated_graph = graph_nodes = graph_edges = 0
    graph_available = False
    try:
        nodes, edges = db.build_link_graph(project_id)
        graph_available = True
        graph_nodes, graph_edges = len(nodes), len(edges)
        linked = set()
        for e in edges:
            # edges are tuples; collect any int/str endpoints defensively.
            for part in (e if isinstance(e, (list, tuple)) else []):
                linked.add(part)
        isolated_graph = sum(
            1 for n in nodes
            if not any(str(n[2] if isinstance(n, (list, tuple)) and len(n) > 2 else n) in str(x)
                       for x in linked))
    except Exception:
        graph_available = False
    return {
        "total_scenes": len(scenes),
        "scenes_without_chapter": scenes_no_chapter,
        "scenes_without_summary": scenes_no_summary,
        "outline_nodes": len(outline),
        "graph_available": graph_available,
        "graph_nodes": graph_nodes, "graph_edges": graph_edges,
        "graph_isolated_nodes": isolated_graph,
    }


def collect_workflow_status(db, project_id: int) -> dict[str, Any]:
    out: dict[str, Any] = {}
    # Rewrite sandbox.
    try:
        from logosforge.rewrite_sandbox.engine import session_status
        out["rewrite"] = session_status(db, project_id)
    except Exception:
        out["rewrite"] = {"active": False}
    # Controlled apply.
    try:
        ops = db.get_apply_operations(project_id)
        pending = [o for o in ops if o.status in ("draft", "previewed")]
        out["controlled_apply"] = {
            "available": True, "pending": len(pending),
            "applied": sum(1 for o in ops if o.status == "applied"),
        }
    except Exception:
        out["controlled_apply"] = {"available": False}
    # Revision intelligence.
    try:
        reports = db.get_revision_impact_reports(project_id)
        high = sum(1 for r in reports if r.impact_level in ("high", "critical"))
        out["revision"] = {"available": True, "reports": len(reports),
                           "high_impact": high}
    except Exception:
        out["revision"] = {"available": False}
    # Production draft.
    try:
        from logosforge.screenplay_production import production_status
        out["production"] = production_status(db, project_id)
    except Exception:
        out["production"] = {"active": False}
    return out


def collect_export_readiness(db, project_id: int, *, light: bool = False) -> dict[str, Any]:
    mode = _writing_mode(db, project_id)
    if mode != "screenplay":
        return {"available": True, "mode": mode,
                "note": "Standard JSON/Markdown export available."}
    if light:
        return {"available": True, "mode": "screenplay", "checked": False}
    try:
        from logosforge.screenplay_output_validation import (
            validate_professional_output,
        )
        rep = validate_professional_output(db, project_id, target_format="fountain")
        return {
            "available": True, "mode": "screenplay", "checked": True,
            "is_export_safe": rep.is_export_safe,
            "compatibility_level": rep.compatibility_level,
            "formats": rep.available_formats,
            "blocking": list(rep.blocking_errors), "warnings": list(rep.warnings),
        }
    except Exception:
        return {"available": False, "mode": "screenplay"}


def collect_health_summary(db, project_id: int) -> dict[str, Any]:
    """Top narrative-health risks (expensive — skipped in light mode)."""
    try:
        from logosforge.logos.health import HealthEngine
        report = HealthEngine(db, project_id).generate_report()
        return {
            "available": True,
            "overall": report.overall_status,
            "top_risks": list(report.top_risks)[:3],
        }
    except Exception:
        return {"available": False}
