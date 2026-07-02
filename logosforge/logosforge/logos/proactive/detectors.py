"""Rule-based proactive detectors (Phase 4).

Each detector is a pure function ``detect_<section>(db, project_id, context)
-> list[LogosSuggestion]``. They:

* read only (never mutate the DB);
* never call an LLM (fast, deterministic);
* attach concrete *evidence* and an explainable *confidence*;
* map to existing Logos action names so the user can act with one click.

Detectors prefer the *current* selection in the context (cheap) but fall back to
a light project-level scan where that is the natural granularity (e.g. an
isolated graph node, a relationless PSYKE entry).
"""

from __future__ import annotations

from logosforge.logos.proactive import scoring
from logosforge.logos.proactive.suggestion import (
    SEVERITY_IMPORTANT,
    SEVERITY_INFO,
    SEVERITY_WARNING,
    TYPE_CHARACTER,
    TYPE_CONFLICT,
    TYPE_GRAPH,
    TYPE_PACING,
    TYPE_PSYKE,
    TYPE_STRUCTURE,
    TYPE_TIMELINE,
    LogosSuggestion,
)

# Light caps so a single scan never floods the UI.
_MAX_PER_DETECTOR = 6


def _short(text: str, n: int = 60) -> str:
    text = (text or "").strip().replace("\n", " ")
    return (text[:n] + "…") if len(text) > n else text


# ---------------------------------------------------------------------------
# Manuscript
# ---------------------------------------------------------------------------


def detect_manuscript(db, project_id: int, context) -> list[LogosSuggestion]:
    out: list[LogosSuggestion] = []
    scene_id = getattr(context, "current_scene_id", None)
    if scene_id is None:
        return out
    scene = db.get_scene_by_id(scene_id)
    if scene is None or scene.project_id != project_id:
        return out

    content_len = len((scene.content or "").strip())
    has_summary = bool((scene.summary or "").strip())
    char_ids = db.get_scene_character_ids(scene_id)

    # Very short scene with no stated purpose.
    if content_len < 200 and not has_summary and not (scene.goal or "").strip():
        out.append(LogosSuggestion(
            type=TYPE_STRUCTURE, section_name="Manuscript",
            title="Scene may lack a clear purpose",
            message="This scene is short and has no summary, goal, or stated purpose.",
            evidence=f"{content_len} chars of content; no summary/goal set.",
            confidence=scoring.BASE_MEDIUM, severity=SEVERITY_WARNING,
            target_type="scene", target_id=str(scene_id),
            suggested_actions=["identify_weakness", "explain_selection"],
        ))

    # Scene has no linked characters.
    if not char_ids and content_len > 0:
        out.append(LogosSuggestion(
            type=TYPE_CHARACTER, section_name="Manuscript",
            title="Scene has no linked characters",
            message="No characters are linked to this scene.",
            evidence="0 characters linked.",
            confidence=scoring.BASE_MEDIUM, severity=SEVERITY_INFO,
            target_type="scene", target_id=str(scene_id),
            suggested_actions=["explain_selection"],
        ))

    # Scene that may not turn — opening and closing states described the same.
    goal = (scene.goal or "").strip().lower()
    outcome = (scene.outcome or "").strip().lower()
    if goal and outcome and goal == outcome:
        out.append(LogosSuggestion(
            type=TYPE_CONFLICT, section_name="Manuscript",
            title="Scene may not turn",
            message="The scene's goal and outcome read as the same state.",
            evidence="Goal and outcome fields are identical.",
            confidence=scoring.BASE_MEDIUM, severity=SEVERITY_WARNING,
            target_type="scene", target_id=str(scene_id),
            suggested_actions=["identify_weakness", "suggest_revision"],
        ))
    return out[:_MAX_PER_DETECTOR]


# ---------------------------------------------------------------------------
# Outline (scene-derived: act → chapter → scenes)
# ---------------------------------------------------------------------------


def detect_outline(db, project_id: int, context) -> list[LogosSuggestion]:
    out: list[LogosSuggestion] = []
    scenes = db.get_all_scenes(project_id)
    if not scenes:
        return out

    # Group by act → chapters.
    acts: dict[str, dict[str, list]] = {}
    for s in scenes:
        act = (s.act or "").strip() or "Untitled Act"
        chap = (s.chapter or "").strip() or "Untitled Chapter"
        acts.setdefault(act, {}).setdefault(chap, []).append(s)

    for act, chapters in acts.items():
        scene_count = sum(len(v) for v in chapters.values())
        # Act with no real scenes (only placeholders).
        real = [s for cs in chapters.values() for s in cs
                if (s.title or "").strip().lower() not in ("", "untitled scene")]
        if scene_count and not real:
            out.append(LogosSuggestion(
                type=TYPE_STRUCTURE, section_name="Outline",
                title=f"Act '{act}' has no developed scenes",
                message="This act only contains placeholder scenes.",
                evidence=f"{scene_count} scene(s), all untitled/placeholder.",
                confidence=scoring.BASE_MEDIUM, severity=SEVERITY_WARNING,
                target_type="act", target_id=act,
                suggested_actions=["identify_structure_problem", "suggest_next_beat"],
            ))

    # Scenes with empty summaries (lacking dramatic function).
    empty = [s for s in scenes if not (s.summary or "").strip()
             and not (s.goal or "").strip()]
    for s in empty[:_MAX_PER_DETECTOR]:
        out.append(LogosSuggestion(
            type=TYPE_STRUCTURE, section_name="Outline",
            title="Outline node lacks dramatic function",
            message=f"'{_short(s.title) or 'Untitled'}' has no summary or goal.",
            evidence="No summary and no goal set.",
            confidence=scoring.BASE_MEDIUM, severity=SEVERITY_INFO,
            target_type="scene", target_id=str(s.id),
            suggested_actions=["summarize_node", "identify_structure_problem"],
        ))
    return out[:_MAX_PER_DETECTOR]


# ---------------------------------------------------------------------------
# Plot (scene-derived by plotline)
# ---------------------------------------------------------------------------


def detect_plot(db, project_id: int, context) -> list[LogosSuggestion]:
    out: list[LogosSuggestion] = []
    scenes = db.get_all_scenes(project_id)
    if not scenes:
        return out
    # Plot block = plotline group; flag blocks where most scenes lack conflict.
    blocks: dict[str, list] = {}
    for s in scenes:
        blocks.setdefault((s.plotline or "").strip() or "Unassigned", []).append(s)

    for plotline, block in blocks.items():
        no_conflict = [s for s in block if not (s.conflict or "").strip()
                       and not (s.summary or "").strip()]
        if len(block) >= 2 and len(no_conflict) == len(block):
            out.append(LogosSuggestion(
                type=TYPE_CONFLICT, section_name="Plot",
                title=f"Plotline '{plotline}' has no stated conflict",
                message="None of this plotline's scenes describe conflict or summary.",
                evidence=f"{len(block)} scene(s); 0 with conflict/summary.",
                confidence=scoring.scale_by_prevalence(scoring.BASE_MEDIUM, len(block)),
                severity=SEVERITY_WARNING,
                target_type="plotline", target_id=plotline,
                suggested_actions=["identify_weak_conflict", "suggest_conflict_upgrade"],
            ))
    return out[:_MAX_PER_DETECTOR]


# ---------------------------------------------------------------------------
# Timeline (ordered scenes; gaps via sort_order/act jumps)
# ---------------------------------------------------------------------------


def detect_timeline(db, project_id: int, context) -> list[LogosSuggestion]:
    out: list[LogosSuggestion] = []
    scenes = sorted(db.get_all_scenes(project_id), key=lambda s: (s.sort_order, s.id))
    if len(scenes) < 2:
        return out
    # Adjacent scenes that jump act without any bridging — a possible gap.
    for prev, cur in zip(scenes, scenes[1:]):
        pa, ca = (prev.act or "").strip(), (cur.act or "").strip()
        if pa and ca and pa != ca:
            # Heuristic: both endpoints lack a summary -> the transition is opaque.
            if not (prev.summary or "").strip() and not (cur.summary or "").strip():
                out.append(LogosSuggestion(
                    type=TYPE_TIMELINE, section_name="Timeline",
                    title="Possible timeline gap between acts",
                    message=f"Jump from '{pa}' to '{ca}' with no bridging summary.",
                    evidence=f"'{_short(prev.title)}' → '{_short(cur.title)}'; "
                             "neither has a summary.",
                    confidence=scoring.BASE_MEDIUM, severity=SEVERITY_INFO,
                    target_type="scene", target_id=str(cur.id),
                    suggested_actions=["check_gap", "suggest_bridge_scene"],
                ))
    return out[:_MAX_PER_DETECTOR]


# ---------------------------------------------------------------------------
# Graph (isolated nodes from the link graph)
# ---------------------------------------------------------------------------


def detect_graph(db, project_id: int, context) -> list[LogosSuggestion]:
    out: list[LogosSuggestion] = []
    adjacency = _graph_adjacency(db, project_id)

    # PSYKE entries that are important-by-type (character/theme) but isolated.
    entries = db.get_all_psyke_entries(project_id)
    for e in entries:
        node = f"PSYKE:{e.id}"
        related = db.get_typed_related_psyke_entries(e.id)
        graph_links = adjacency.get(e.name.lower(), set())
        if not related and not graph_links and e.entry_type in ("character", "theme"):
            out.append(LogosSuggestion(
                type=TYPE_GRAPH, section_name="Graph",
                title=f"'{_short(e.name)}' is isolated in the graph",
                message="This entry has no relationships or graph links.",
                evidence=f"0 PSYKE relations; 0 graph links; type={e.entry_type}.",
                confidence=scoring.BASE_HIGH, severity=SEVERITY_WARNING,
                target_type="graph_node", target_id=node,
                suggested_actions=["identify_isolated_node", "suggest_psyke_relation"],
            ))
    return out[:_MAX_PER_DETECTOR]


# ---------------------------------------------------------------------------
# PSYKE
# ---------------------------------------------------------------------------


def detect_psyke(db, project_id: int, context) -> list[LogosSuggestion]:
    out: list[LogosSuggestion] = []
    entries = db.get_all_psyke_entries(project_id)
    # Count scene appearances for prevalence (mention by name in scene fields).
    appearances = _psyke_appearances(db, project_id, entries)

    for e in entries:
        details = db.get_psyke_entry_details(e.id)
        has_details = bool(details) or bool((e.notes or "").strip())
        related = db.get_typed_related_psyke_entries(e.id)
        appears = appearances.get(e.id, 0)

        # No details at all — confidence rises with how often the entry appears.
        if not has_details:
            conf = scoring.scale_by_prevalence(scoring.BASE_HIGH, appears)
            sev = SEVERITY_IMPORTANT if appears >= 3 else SEVERITY_WARNING
            out.append(LogosSuggestion(
                type=TYPE_PSYKE, section_name="PSYKE",
                title=f"'{_short(e.name)}' has no details",
                message="This entry has no notes or detail fields filled in.",
                evidence=f"Empty details/notes; appears in {appears} scene(s).",
                confidence=conf, severity=sev,
                target_type="psyke_entry", target_id=str(e.id),
                suggested_actions=["find_missing_details", "suggest_details"],
            ))
        # Important entry with no relationships.
        elif not related and appears >= 2:
            out.append(LogosSuggestion(
                type=TYPE_PSYKE, section_name="PSYKE",
                title=f"'{_short(e.name)}' has no relationships",
                message="This recurring entry is not related to anything yet.",
                evidence=f"0 relations; appears in {appears} scene(s).",
                confidence=scoring.scale_by_prevalence(scoring.BASE_MEDIUM, appears),
                severity=SEVERITY_WARNING,
                target_type="psyke_entry", target_id=str(e.id),
                suggested_actions=["check_relationships", "suggest_relations"],
            ))
    return out[:_MAX_PER_DETECTOR]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _graph_adjacency(db, project_id: int) -> dict[str, set[str]]:
    """Lowercased name → set of connected names, from the DB link graph.

    Built directly from the DB (no UI/Qt import) so detectors stay pure-logic.
    """
    try:
        _nodes, edges = db.build_link_graph(project_id)
    except Exception:
        return {}
    adj: dict[str, set[str]] = {}
    for src, tgt in edges:
        adj.setdefault(src.lower(), set()).add(tgt.lower())
        adj.setdefault(tgt.lower(), set()).add(src.lower())
    return adj


def _psyke_appearances(db, project_id: int, entries) -> dict[int, int]:
    """Count how many scenes mention each PSYKE entry by name (cheap text scan)."""
    scenes = db.get_all_scenes(project_id)
    counts: dict[int, int] = {}
    blobs = []
    for s in scenes:
        blob = " ".join(filter(None, [
            s.title, s.summary, s.synopsis, s.goal, s.conflict, s.outcome, s.content,
        ])).lower()
        blobs.append(blob)
    for e in entries:
        name = (e.name or "").strip().lower()
        if not name:
            continue
        counts[e.id] = sum(1 for blob in blobs if name in blob)
    return counts


# Registry: section name → ordered list of detector callables.
SECTION_DETECTORS = {
    "Manuscript": [detect_manuscript],
    "Outline": [detect_outline],
    "Plot": [detect_plot],
    "Timeline": [detect_timeline],
    "Graph": [detect_graph],
    "PSYKE": [detect_psyke],
}
