"""Deterministic Logos action handlers (Phase 10C).

Some Logos actions are *diagnostic* and must run without an LLM — they compute a
rule-based result and return it directly. ``LogosController.run`` consults this
registry first; if an action has a handler here, the controller never resolves a
provider or calls the chat backend. Handlers are read-only (no DB writes) and
return a :class:`LogosResult` (preview-only — never auto-applies).
"""

from __future__ import annotations

from collections.abc import Callable

from logosforge.logos.context import LogosContext
from logosforge.logos.result import LogosResult

# action_name -> handler(db, context) -> LogosResult
_HANDLERS: dict[str, Callable[[object, LogosContext], LogosResult]] = {}


def register(action_name: str, handler: Callable[[object, LogosContext], LogosResult]) -> None:
    _HANDLERS[action_name] = handler


def get_handler(action_name: str):
    return _HANDLERS.get(action_name)


def is_deterministic(action_name: str) -> bool:
    return action_name in _HANDLERS


# -- Handlers ----------------------------------------------------------------


def _diagnose_scene_economy(db, context: LogosContext) -> LogosResult:
    """Run the deterministic screenplay scene-economy diagnostics for the scene."""
    action = "sp_diagnose_scene_economy"
    scene_id = context.current_scene_id
    if scene_id is None:
        return LogosResult(
            ok=True, action=action, title="Diagnose Scene Economy",
            message="Open a scene in the Manuscript to run screenplay diagnostics.",
            suggestions=[], proposed_operations=[],
        )
    try:
        from logosforge.screenplay_diagnostics import analyze_scene_by_id
        report = analyze_scene_by_id(db, context.project_id, scene_id)
    except Exception as exc:  # never crash the UI
        return LogosResult.failure(action, f"Diagnostics failed: {exc}")

    lines = [report.summary, ""]
    lines.append(
        f"Blocks: {report.block_count}  ·  Action: {report.action_block_count}  ·  "
        f"Dialogue: {report.dialogue_block_count}  ·  Characters: "
        f"{', '.join(report.unique_characters) or '—'}"
    )
    if report.estimated_minutes:
        lines.append(f"Approx. length: ~{report.estimated_minutes} min (rough).")
    suggestions: list[str] = []
    if report.issues:
        lines.append("")
        lines.append("Issues:")
        for i in report.top_issues(8):
            lines.append(f"- [{i.severity}] {i.label} — {i.evidence}")
            if i.suggested_action:
                suggestions.append(f"{i.label}: {i.suggested_action}")
    if report.strengths:
        lines.append("")
        lines.append("Strengths: " + "; ".join(report.strengths))

    return LogosResult(
        ok=True, action=action, title="Diagnose Scene Economy",
        message="\n".join(lines), suggestions=suggestions,
        proposed_operations=[],  # diagnostic only — no mutation
    )


register("sp_diagnose_scene_economy", _diagnose_scene_economy)


def _scene_health(db, context: LogosContext) -> LogosResult:
    """Unified deterministic screenplay scene health (Phase 3).

    Groups every deterministic finding by category (Format / Visual Writing /
    Dialogue Economy / Dramatic Function / Beat Plan Alignment / Continuity) and
    reports transparent metrics. Diagnostic only — never mutates."""
    action = "sp_scene_health"
    scene_id = context.current_scene_id
    if scene_id is None:
        return LogosResult(
            ok=True, action=action, title="Screenplay Check",
            message="Open a scene in the Manuscript to run a screenplay check.",
            suggestions=[], proposed_operations=[],
        )
    try:
        from logosforge.screenplay_diagnostics import (
            analyze_scene_by_id, group_issues_by_category,
        )
        report = analyze_scene_by_id(db, context.project_id, scene_id)
    except Exception as exc:  # never crash the UI
        return LogosResult.failure(action, f"Screenplay check failed: {exc}")

    lines = [report.summary, ""]
    lines.append(
        f"Metrics — Blocks: {report.block_count} · Action: {report.action_block_count}"
        f" · Dialogue: {report.dialogue_block_count} · Parentheticals: "
        f"{report.parenthetical_block_count} · Empty: {report.empty_block_count}"
    )
    lines.append(
        f"Characters: {', '.join(report.unique_characters) or '—'} · "
        f"Action/Dialogue ratio: {report.action_dialogue_ratio} · "
        f"Dialogue avg/longest: {report.average_dialogue_words}/"
        f"{report.longest_dialogue_words} w · Internal-state phrases: "
        f"{report.internal_state_phrase_count}"
    )
    if report.estimated_minutes:
        lines.append(f"Approx. length: ~{report.estimated_minutes} min (rough).")
    if report.beat_plan_aligned is not None:
        lines.append("Beat plan: "
                     + ("reflected in the body."
                        if report.beat_plan_aligned
                        else "some planned elements are not yet evident."))

    suggestions: list[str] = []
    for category, items in group_issues_by_category(report).items():
        ordered = sorted(items, key=lambda i: (i.severity_rank, i.confidence),
                         reverse=True)
        lines.append("")
        lines.append(f"{category}:")
        for i in ordered:
            target = (f" (block {i.target_block_index + 1})"
                      if i.target_block_index is not None else "")
            lines.append(f"- [{i.severity}] {i.label}{target} — {i.evidence}")
            if i.suggested_action:
                suggestions.append(f"{i.label}: {i.suggested_action}")
    if report.strengths:
        lines.append("")
        lines.append("Strengths: " + "; ".join(report.strengths))

    return LogosResult(
        ok=True, action=action, title="Screenplay Check",
        message="\n".join(lines).strip(), suggestions=suggestions,
        proposed_operations=[],  # diagnostic only — no mutation
    )


def _beat_plan_alignment(db, context: LogosContext) -> LogosResult:
    """Deterministic beat-plan ↔ body alignment for the current scene (Phase 3)."""
    action = "sp_beat_plan_alignment"
    scene_id = context.current_scene_id
    if scene_id is None:
        return LogosResult(
            ok=True, action=action, title="Beat Plan Alignment",
            message="Open a scene in the Manuscript to check beat-plan alignment.",
            suggestions=[], proposed_operations=[],
        )
    try:
        from logosforge import screenplay_pipeline as spp
        from logosforge.screenplay_blocks import parse_screenplay_text
        from logosforge.screenplay_diagnostics import analyze_beat_plan_alignment
        plan = spp.get_beat_plan(db, context.project_id, scene_id)
        if plan is None or plan.is_empty():
            return LogosResult(
                ok=True, action=action, title="Beat Plan Alignment",
                message=("This scene has no beat plan yet. In Outline, open the "
                         "scene's ⋯ menu and choose “Generate Beat Plan” first."),
                suggestions=[], proposed_operations=[],
            )
        scene = db.get_scene_by_id(scene_id)
        blocks = parse_screenplay_text(getattr(scene, "content", "") or "",
                                       scene_id=scene_id)
        issues = analyze_beat_plan_alignment(blocks, plan)
    except Exception as exc:
        return LogosResult.failure(action, f"Alignment check failed: {exc}")

    if not issues:
        return LogosResult(
            ok=True, action=action, title="Beat Plan Alignment",
            message=("The scene body reflects its beat plan "
                     "(deterministic keyword check)."),
            suggestions=[], proposed_operations=[],
        )
    lines = ["Some planned elements are not yet evident in the scene body:", ""]
    suggestions: list[str] = []
    for i in issues:
        lines.append(f"- [{i.severity}] {i.label} — {i.evidence}")
        if i.suggested_action:
            suggestions.append(f"{i.label}: {i.suggested_action}")
    return LogosResult(
        ok=True, action=action, title="Beat Plan Alignment",
        message="\n".join(lines), suggestions=suggestions, proposed_operations=[],
    )


def _counterpart_reflection(db, context: LogosContext) -> LogosResult:
    """Deterministic two-stance scene reflection (Phase 5).

    Re-projects the Phase 3 diagnostics + Phase 2 beat plan + PSYKE into an
    internal-character / external-audience reflection with revision questions.
    Diagnostic only — never rewrites or mutates."""
    action = "sp_counterpart_reflection"
    scene_id = context.current_scene_id
    if scene_id is None:
        return LogosResult(
            ok=True, action=action, title="Counterpart Reflection",
            message="Open a scene in the Manuscript to reflect on it.",
            suggestions=[], proposed_operations=[],
        )
    try:
        from logosforge.screenplay_reflection import build_scene_reflection
        report = build_scene_reflection(db, context.project_id, scene_id)
    except Exception as exc:  # never crash the UI
        return LogosResult.failure(action, f"Reflection failed: {exc}")

    suggestions = list(report.revision_suggestions) + [
        f"Q: {q}" for q in report.questions]
    return LogosResult(
        ok=True, action=action, title="Counterpart Reflection",
        message=report.to_text(), suggestions=suggestions,
        proposed_operations=[],  # reflection only — no mutation
    )


register("sp_scene_health", _scene_health)
register("sp_beat_plan_alignment", _beat_plan_alignment)
register("sp_counterpart_reflection", _counterpart_reflection)


def _continuity_check(db, context: LogosContext) -> LogosResult:
    """Deterministic multi-scene screenplay continuity report (Phase 7).

    Project-level (no selection / current scene needed). Read-only — consolidates
    the existing continuity, setup/payoff, story-link, Timeline and PSYKE engines
    into one cross-scene report. Never mutates or rewrites."""
    action = "sp_continuity_check"
    try:
        from logosforge.screenplay_continuity import (
            build_screenplay_continuity_report,
        )
        report = build_screenplay_continuity_report(db, context.project_id)
    except Exception as exc:  # never crash the UI
        return LogosResult.failure(action, f"Continuity check failed: {exc}")

    suggestions = list(report.recommended_fixes)
    return LogosResult(
        ok=True, action=action, title="Screenplay Continuity Check",
        message=report.to_text(), suggestions=suggestions,
        proposed_operations=[],  # report only — no mutation
    )


register("sp_continuity_check", _continuity_check)


def _review_dashboard(db, context: LogosContext) -> LogosResult:
    """Deterministic project-level Screenplay Review Dashboard (Phase 8).

    Read-only roll-up rendered as a Markdown report in the result area. Never
    mutates and never auto-applies."""
    action = "sp_review_dashboard"
    try:
        from logosforge.screenplay_review import build_screenplay_review
        report = build_screenplay_review(db, context.project_id)
    except Exception as exc:
        return LogosResult.failure(action, f"Review failed: {exc}")
    suggestions = [f"{r.title or 'Scene'}: {r.next_action}"
                   for r in report.rows if r.overall_status != "OK"][:10]
    return LogosResult(
        ok=True, action=action, title="Screenplay Review Dashboard",
        message=report.to_markdown(), suggestions=suggestions,
        proposed_operations=[])  # report only — no mutation


register("sp_review_dashboard", _review_dashboard)


def _gn_panel_check(db, context: LogosContext) -> LogosResult:
    """Deterministic Graphic Novel page/panel check for the current scene (Phase 1).
    Report-only — never mutates or auto-applies."""
    action = "gn_panel_check"
    scene_id = context.current_scene_id
    if scene_id is None:
        return LogosResult(
            ok=True, action=action, title="Panel Check",
            message="Open a Graphic Novel scene in the Manuscript to check its panels.",
            suggestions=[], proposed_operations=[],
        )
    try:
        from logosforge.graphic_novel_blocks import (
            load_scene_script, validate_graphic_novel_script,
        )
        script = load_scene_script(db, scene_id)
        report = validate_graphic_novel_script(script)
    except Exception as exc:
        return LogosResult.failure(action, f"Panel check failed: {exc}")

    head = (f"{len(script.pages)} page(s), {script.panel_count()} panel(s).")
    if not report.warnings:
        msg = head + "\n\nNo panel issues detected."
    else:
        msg = head + "\n\nWarnings:\n" + "\n".join(f"- {w}" for w in report.warnings)
    return LogosResult(
        ok=True, action=action, title="Panel Check",
        message=msg, suggestions=list(report.warnings), proposed_operations=[])


register("gn_panel_check", _gn_panel_check)


def _gn_scene_health(db, context: LogosContext) -> LogosResult:
    """Unified deterministic Graphic Novel scene-script check (Phase 3).

    Groups every finding by category and reports transparent metrics. Report-only
    — never mutates, never generates images/prompts."""
    action = "gn_scene_health"
    scene_id = context.current_scene_id
    if scene_id is None:
        return LogosResult(
            ok=True, action=action, title="Graphic Novel Check",
            message="Open a Graphic Novel scene in the Manuscript to run a check.",
            suggestions=[], proposed_operations=[],
        )
    try:
        from logosforge.graphic_novel_diagnostics import (
            analyze_scene_by_id, group_issues_by_category,
        )
        report = analyze_scene_by_id(db, context.project_id, scene_id)
    except Exception as exc:  # never crash the UI
        return LogosResult.failure(action, f"Graphic Novel check failed: {exc}")

    lines = [report.summary, ""]
    lines.append(
        f"Metrics — Pages: {report.total_pages} · Panels: {report.total_panels} · "
        f"Avg/page: {report.avg_panels_per_page} · No-visual: "
        f"{report.panels_without_visual} · Empty: {report.empty_panels} · "
        f"Dialogue-heavy: {report.dialogue_heavy_panels} · SFX: {report.sfx_count}")
    suggestions: list[str] = []
    for category, items in group_issues_by_category(report).items():
        ordered = sorted(items, key=lambda i: i.severity_rank, reverse=True)
        lines.append("")
        lines.append(f"{category}:")
        for i in ordered:
            where = ""
            if i.page_number is not None:
                where = f" (page {i.page_number}"
                where += f", panel {i.panel_number})" if i.panel_number else ")"
            lines.append(f"- [{i.severity}] {i.label}{where} — {i.evidence}")
            if i.suggested_action:
                suggestions.append(f"{i.label}: {i.suggested_action}")
    if report.strengths:
        lines.append("")
        lines.append("Strengths: " + "; ".join(report.strengths))
    return LogosResult(
        ok=True, action=action, title="Graphic Novel Check",
        message="\n".join(lines).strip(), suggestions=suggestions,
        proposed_operations=[])  # report only — no mutation


register("gn_scene_health", _gn_scene_health)


def _gn_reflection(db, context: LogosContext) -> LogosResult:
    """Deterministic Graphic Novel Counterpart / Reflection (Phase 4).

    Re-projects the Phase 3 GN diagnostics + Phase 2 breakdown/plan + PSYKE into a
    reader / artist / story / dialogue reflection with revision questions.
    Reflection only — never rewrites, never mutates, never generates images."""
    action = "gn_reflection"
    scene_id = context.current_scene_id
    if scene_id is None:
        return LogosResult(
            ok=True, action=action, title="Graphic Novel Reflection",
            message="Open a Graphic Novel scene in the Manuscript to reflect on it.",
            suggestions=[], proposed_operations=[],
        )
    try:
        from logosforge.graphic_novel_reflection import build_scene_reflection
        report = build_scene_reflection(db, context.project_id, scene_id)
    except Exception as exc:  # never crash the UI
        return LogosResult.failure(action, f"Reflection failed: {exc}")

    suggestions = list(report.suggested_actions) + [
        f"Q: {q}" for q in report.questions]
    return LogosResult(
        ok=True, action=action, title="Graphic Novel Reflection",
        message=report.to_text(), suggestions=suggestions,
        proposed_operations=[],  # reflection only — no mutation
    )


register("gn_reflection", _gn_reflection)


def _gn_continuity_check(db, context: LogosContext) -> LogosResult:
    """Deterministic cross-scene Graphic Novel continuity report (Phase 6).

    Project-level (no selection / current scene needed). Read-only — consolidates
    visual flow, character/object/place continuity, motifs, setup/payoff, Timeline
    alignment, and PSYKE/Notes consistency. Never mutates or generates images."""
    action = "gn_continuity_check"
    try:
        from logosforge.graphic_novel_continuity import (
            build_graphic_novel_continuity_report,
        )
        report = build_graphic_novel_continuity_report(db, context.project_id)
    except Exception as exc:  # never crash the UI
        return LogosResult.failure(action, f"Continuity check failed: {exc}")

    return LogosResult(
        ok=True, action=action, title="Graphic Novel Continuity Check",
        message=report.to_text(), suggestions=list(report.recommended_fixes),
        proposed_operations=[],  # report only — no mutation
    )


register("gn_continuity_check", _gn_continuity_check)


def _gn_review_dashboard(db, context: LogosContext) -> LogosResult:
    """Deterministic project-level Graphic Novel Review Dashboard (Phase 7).

    Read-only roll-up rendered as Markdown in the result area: per-scene page
    breakdown / panel plan / body / health / flow / continuity / Timeline / PSYKE
    / export status, with a recommended next action. Never mutates, never auto-
    applies, and has no image-generation surface."""
    action = "gn_review_dashboard"
    try:
        from logosforge.graphic_novel_dashboard import build_graphic_novel_review
        report = build_graphic_novel_review(db, context.project_id)
    except Exception as exc:  # never crash the UI
        return LogosResult.failure(action, f"Review failed: {exc}")
    suggestions = [f"{r.title or 'Scene'}: {r.next_action}"
                   for r in report.rows if r.overall_status != "OK"][:10]
    return LogosResult(
        ok=True, action=action, title="Graphic Novel Review Dashboard",
        message=report.to_markdown(), suggestions=suggestions,
        proposed_operations=[])  # report only — no mutation


register("gn_review_dashboard", _gn_review_dashboard)


def _stage_check(db, context: LogosContext) -> LogosResult:
    """Deterministic Stage Script scene intelligence check (Phase 3).

    Report-only — never mutates, never generates, never calls the LLM. Groups every
    finding by category (format / blocking / playability / dialogue / cues /
    dramatic function / plan alignment / continuity) with transparent metrics."""
    action = "stage_check"
    scene_id = context.current_scene_id
    if scene_id is None:
        return LogosResult(
            ok=True, action=action, title="Stage Script Check",
            message="Open a Stage Script scene in the Manuscript to check it.",
            suggestions=[], proposed_operations=[],
        )
    try:
        from logosforge.stage_script_diagnostics import (
            analyze_scene_by_id, group_issues_by_category,
        )
        report = analyze_scene_by_id(db, context.project_id, scene_id)
    except Exception as exc:  # never crash the UI
        return LogosResult.failure(action, f"Stage Script check failed: {exc}")

    lines = [report.summary, ""]
    lines.append(
        f"Metrics — Blocks: {report.total_blocks} · Character: "
        f"{report.character_count} · Dialogue: {report.dialogue_count} · Stage "
        f"directions: {report.stage_direction_count} · Entrances/Exits: "
        f"{report.entrance_count}/{report.exit_count} · Cues (L/S): "
        f"{report.lighting_count}/{report.sound_count} · Dialogue:action ratio: "
        f"{report.dialogue_stage_ratio}")
    suggestions: list[str] = []
    for category, items in group_issues_by_category(report).items():
        ordered = sorted(items, key=lambda i: i.severity_rank, reverse=True)
        lines.append("")
        lines.append(f"{category}:")
        for i in ordered:
            where = f" (block {i.block_number})" if i.block_number else ""
            lines.append(f"- [{i.severity}] {i.label}{where} — {i.evidence}")
            if i.suggested_action:
                suggestions.append(f"{i.label}: {i.suggested_action}")
    if report.strengths:
        lines.append("")
        lines.append("Strengths: " + "; ".join(report.strengths))
    return LogosResult(
        ok=True, action=action, title="Stage Script Check",
        message="\n".join(lines).strip(), suggestions=suggestions,
        proposed_operations=[])  # report only — no mutation


register("stage_check", _stage_check)


def _stage_reflection(db, context: LogosContext) -> LogosResult:
    """Deterministic Stage Script Counterpart / Reflection (Phase 4).

    Re-projects the Phase 3 diagnostics + Phase 2 beat/blocking plans + PSYKE into
    audience / actor / director / dramaturg perspectives with revision questions.
    Reflection only — never rewrites, never mutates, never calls the LLM."""
    action = "stage_reflection"
    scene_id = context.current_scene_id
    if scene_id is None:
        return LogosResult(
            ok=True, action=action, title="Stage Script Reflection",
            message="Open a Stage Script scene in the Manuscript to reflect on it.",
            suggestions=[], proposed_operations=[],
        )
    try:
        from logosforge.stage_script_reflection import build_scene_reflection
        report = build_scene_reflection(db, context.project_id, scene_id)
    except Exception as exc:  # never crash the UI
        return LogosResult.failure(action, f"Reflection failed: {exc}")

    suggestions = list(report.suggested_actions) + [
        f"Q: {q}" for q in report.questions]
    return LogosResult(
        ok=True, action=action, title="Stage Script Reflection",
        message=report.to_text(), suggestions=suggestions,
        proposed_operations=[],  # reflection only — no mutation
    )


register("stage_reflection", _stage_reflection)


def _stage_continuity_check(db, context: LogosContext) -> LogosResult:
    """Deterministic cross-scene Stage Script continuity report (Phase 6).

    Project-level (no selection / current scene needed). Read-only — consolidates
    character entrance/exit, blocking, props/set, lighting/sound cue continuity,
    setup/payoff, Timeline alignment, and PSYKE/Notes. Never mutates."""
    action = "stage_continuity_check"
    try:
        from logosforge.stage_script_continuity import (
            build_stage_script_continuity_report,
        )
        report = build_stage_script_continuity_report(db, context.project_id)
    except Exception as exc:  # never crash the UI
        return LogosResult.failure(action, f"Continuity check failed: {exc}")

    return LogosResult(
        ok=True, action=action, title="Stage Continuity Check",
        message=report.to_text(), suggestions=list(report.recommended_fixes),
        proposed_operations=[],  # report only — no mutation
    )


register("stage_continuity_check", _stage_continuity_check)


def _stage_review_dashboard(db, context: LogosContext) -> LogosResult:
    """Deterministic project-level Stage Script Review Dashboard (Phase 7).

    Read-only roll-up rendered as Markdown: per-scene beat/blocking plan, body,
    dialogue/stage-action/entrance-exit/cue/continuity status, Timeline link, and
    a recommended next action. Never mutates, never auto-applies."""
    action = "stage_review_dashboard"
    try:
        from logosforge.stage_script_dashboard import build_stage_script_review
        report = build_stage_script_review(db, context.project_id)
    except Exception as exc:  # never crash the UI
        return LogosResult.failure(action, f"Review failed: {exc}")
    suggestions = [f"{r.title or 'Scene'}: {r.next_action}"
                   for r in report.rows if r.overall_status != "OK"][:10]
    return LogosResult(
        ok=True, action=action, title="Stage Script Review Dashboard",
        message=report.to_markdown(), suggestions=suggestions,
        proposed_operations=[])  # report only — no mutation


register("stage_review_dashboard", _stage_review_dashboard)


def _series_check(db, context: LogosContext) -> LogosResult:
    """Deterministic Series scene health check (Phases 1 + 3).

    Report-only — never mutates, never generates, never calls the LLM. Runs the
    deterministic Series scene diagnostics (format / block order, scene function,
    dialogue-action balance, plan alignment, PSYKE continuity) on the current
    scene and renders metrics + categorized issues."""
    action = "series_check"
    scene_id = context.current_scene_id
    if scene_id is None:
        return LogosResult(
            ok=True, action=action, title="Series Scene Check",
            message="Open a Series scene in the Manuscript to check it.",
            suggestions=[], proposed_operations=[],
        )
    try:
        from logosforge import series_diagnostics as sd
        report = sd.analyze_scene_by_id(db, context.project_id, scene_id)
    except Exception as exc:  # never crash the UI
        return LogosResult.failure(action, f"Series check failed: {exc}")

    if not report.issues:
        msg = report.summary + "\n\nNo series-script issues detected."
    else:
        msg = report.summary + "\n\n" + sd.render_issues(report.issues)
    return LogosResult(
        ok=True, action=action, title="Series Scene Check",
        message=msg, suggestions=[i.label for i in report.top_issues(8)],
        proposed_operations=[])


register("series_check", _series_check)


def _series_episode(db, context: LogosContext):
    """Resolve the current Episode (the current Scene's Chapter) and its ordered
    scenes. Returns ``(chapter_name, scenes)`` or ``(None, [])``."""
    scene_id = context.current_scene_id
    if scene_id is None:
        return None, []
    scene = db.get_scene_by_id(scene_id)
    chapter = (getattr(scene, "chapter", "") or "").strip() if scene else ""
    if not chapter:
        return None, []
    try:
        from logosforge import story_structure as ss
        scenes = ss.list_scenes(db, context.project_id, chapter=chapter)
    except Exception:
        scenes = []
    return chapter, scenes


def _series_episode_check(db, context: LogosContext) -> LogosResult:
    """Deterministic Episode (serial) structure check (Phase 2).

    Report-only — never mutates, never generates, never calls the LLM. Examines
    the current Episode: scene count, beat-plan presence, and teaser / act-break /
    climax / tag coverage across the episode's scenes."""
    action = "series_episode_check"
    chapter, scenes = _series_episode(db, context)
    if chapter is None:
        return LogosResult(
            ok=True, action=action, title="Episode Structure Check",
            message="Open a Series scene in the Manuscript to check its Episode.",
            suggestions=[], proposed_operations=[])
    try:
        from logosforge import series_blocks as sbk
        from logosforge import series_pipeline as spp
        label = sbk.episode_label(chapter)
        plan = spp.get_episode_plan(db, context.project_id, chapter)
        markers: set[str] = set()
        headings = 0
        for s in scenes:
            script = sbk.load_scene_script(db, s.id)
            for b in script.blocks:
                if b.block_type in sbk._SERIES_MARKERS:
                    markers.add(b.block_type)
                if b.block_type == sbk.BT_SCENE_HEADING:
                    headings += 1
    except Exception as exc:  # never crash the UI
        return LogosResult.failure(action, f"Episode check failed: {exc}")

    warnings: list[str] = []
    if not scenes:
        warnings.append("This Episode has no scenes.")
    if headings == 0 and scenes:
        warnings.append("No scene headings across the Episode.")
    if plan is None or plan.is_empty():
        warnings.append("No Episode beat plan — generate one to guide structure.")
    else:
        if plan.teaser_or_cold_open.strip() and sbk.BT_TEASER not in markers:
            warnings.append("Beat plan defines a Teaser / Cold Open, but no Teaser "
                            "marker appears in the Episode's scenes.")
        if plan.act_breaks and sbk.BT_ACT_BREAK not in markers:
            warnings.append("Beat plan defines Act Breaks, but no Act Break marker "
                            "appears in the Episode's scenes.")
        if plan.tag_or_button.strip() and sbk.BT_TAG not in markers:
            warnings.append("Beat plan defines a Tag / Button, but no Tag marker "
                            "appears in the Episode's scenes.")
        if not plan.climax.strip():
            warnings.append("Beat plan has no climax defined.")

    head = (f"{label} ({chapter}): {len(scenes)} scene(s); "
            f"{headings} scene heading(s); "
            f"markers: {', '.join(sorted(markers)) or 'none'}; "
            f"beat plan: {'yes' if (plan and not plan.is_empty()) else 'no'}.")
    if not warnings:
        msg = head + "\n\nNo episode-structure issues detected."
    else:
        msg = head + "\n\nWarnings:\n" + "\n".join(f"- {w}" for w in warnings)
    return LogosResult(ok=True, action=action, title="Episode Structure Check",
                       message=msg, suggestions=warnings, proposed_operations=[])


register("series_episode_check", _series_episode_check)


def _series_abc_check(db, context: LogosContext) -> LogosResult:
    """Deterministic A/B/C story-coverage check (Phase 2).

    Report-only — never mutates, never generates, never calls the LLM. Reports
    which of the A/B/C stories the current Episode's beat plan defines and flags
    a thin scene count for a multi-thread episode."""
    action = "series_abc_check"
    chapter, scenes = _series_episode(db, context)
    if chapter is None:
        return LogosResult(
            ok=True, action=action, title="A/B/C Story Check",
            message="Open a Series scene in the Manuscript to check its Episode.",
            suggestions=[], proposed_operations=[])
    try:
        from logosforge import series_blocks as sbk
        from logosforge import series_pipeline as spp
        label = sbk.episode_label(chapter)
        plan = spp.get_episode_plan(db, context.project_id, chapter)
    except Exception as exc:
        return LogosResult.failure(action, f"A/B/C check failed: {exc}")

    if plan is None or plan.is_empty():
        return LogosResult(
            ok=True, action=action, title="A/B/C Story Check",
            message=f"{label} ({chapter}) has no Episode beat plan yet — generate "
                    "one to define its A/B/C stories.",
            suggestions=[], proposed_operations=[])

    abc = plan.has_abc()
    defined = [k for k, v in abc.items() if v]
    warnings: list[str] = []
    if not defined:
        warnings.append("The beat plan defines no A/B/C story — at least an A story "
                        "is expected.")
    elif "A" not in defined:
        warnings.append("The beat plan defines a B/C story but no A story.")
    if len(defined) >= 2 and len(scenes) < len(defined):
        warnings.append(f"{len(defined)} storylines ({'/'.join(defined)}) but only "
                        f"{len(scenes)} scene(s) — they may be under-served.")

    head = (f"{label} ({chapter}): stories defined: "
            f"{'/'.join(defined) or 'none'}; {len(scenes)} scene(s).")
    if not warnings:
        msg = head + "\n\nA/B/C coverage looks consistent with the scene count."
    else:
        msg = head + "\n\nWarnings:\n" + "\n".join(f"- {w}" for w in warnings)
    return LogosResult(ok=True, action=action, title="A/B/C Story Check",
                       message=msg, suggestions=warnings, proposed_operations=[])


register("series_abc_check", _series_abc_check)


def _series_reports(db, context: LogosContext):
    """Return ``(scene_report_or_None, episode_report_or_None, chapter)`` for the
    current Series scene/episode, using the deterministic diagnostics engine."""
    from logosforge import series_diagnostics as sd
    scene_report = None
    if context.current_scene_id is not None:
        scene_report = sd.analyze_scene_by_id(db, context.project_id,
                                              context.current_scene_id)
    chapter, _scenes = _series_episode(db, context)
    episode_report = (sd.analyze_episode(db, context.project_id, chapter)
                      if chapter else None)
    return scene_report, episode_report, chapter


def _series_act_break_check(db, context: LogosContext) -> LogosResult:
    """Deterministic Act Break check (Phase 3) — scene-level placement + the
    Episode plan's act-break coverage. Report-only, never calls the LLM."""
    action = "series_act_break_check"
    if context.current_scene_id is None:
        return LogosResult(ok=True, action=action, title="Act Break Check",
            message="Open a Series scene in the Manuscript to check act breaks.",
            suggestions=[], proposed_operations=[])
    try:
        from logosforge import series_diagnostics as sd
        scene_r, ep_r, _chapter = _series_reports(db, context)
        issues = [i for i in (scene_r.issues if scene_r else []) if "act_break" in i.id]
        issues += [i for i in (ep_r.issues if ep_r else []) if "act_break" in i.id]
    except Exception as exc:
        return LogosResult.failure(action, f"Act Break check failed: {exc}")
    count = scene_r.metrics.act_break_count if scene_r else 0
    head = f"Act Break markers in this scene: {count}."
    msg = head + ("\n\nNo act-break issues detected." if not issues
                  else "\n\n" + sd.render_issues(issues))
    return LogosResult(ok=True, action=action, title="Act Break Check",
        message=msg, suggestions=[i.label for i in issues], proposed_operations=[])


register("series_act_break_check", _series_act_break_check)


def _series_cold_open_tag_check(db, context: LogosContext) -> LogosResult:
    """Deterministic Cold Open / Tag check (Phase 3) — teaser & tag placement plus
    the Episode plan's teaser/tag coverage. Report-only, never calls the LLM."""
    action = "series_cold_open_tag_check"
    if context.current_scene_id is None:
        return LogosResult(ok=True, action=action, title="Cold Open / Tag Check",
            message="Open a Series scene in the Manuscript to check cold open / tag.",
            suggestions=[], proposed_operations=[])
    try:
        from logosforge import series_diagnostics as sd
        scene_r, ep_r, _chapter = _series_reports(db, context)

        def _pick(issues):
            return [i for i in issues
                    if "teaser" in i.id or "tag" in i.id or "cold_open" in i.id]
        issues = _pick(scene_r.issues if scene_r else [])
        issues += _pick(ep_r.issues if ep_r else [])
    except Exception as exc:
        return LogosResult.failure(action, f"Cold Open / Tag check failed: {exc}")
    teaser = scene_r.metrics.teaser_count if scene_r else 0
    tag = scene_r.metrics.tag_count if scene_r else 0
    head = f"Cold Open / Teaser markers: {teaser}; Tag markers: {tag}."
    msg = head + ("\n\nNo cold open / tag issues detected." if not issues
                  else "\n\n" + sd.render_issues(issues))
    return LogosResult(ok=True, action=action, title="Cold Open / Tag Check",
        message=msg, suggestions=[i.label for i in issues], proposed_operations=[])


register("series_cold_open_tag_check", _series_cold_open_tag_check)


def _series_arc_alignment(db, context: LogosContext) -> LogosResult:
    """Deterministic Season / Arc alignment check (Phase 3) — whether the current
    Episode reflects the Season / Arc plan. Report-only, never calls the LLM."""
    action = "series_arc_alignment"
    chapter, _scenes = _series_episode(db, context)
    if chapter is None:
        return LogosResult(ok=True, action=action, title="Season Arc Alignment",
            message="Open a Series scene in the Manuscript to check season-arc "
                    "alignment.", suggestions=[], proposed_operations=[])
    try:
        from logosforge import series_diagnostics as sd
        ep = sd.analyze_episode(db, context.project_id, chapter)
        issues = ep.issues_in(sd.CAT_SERIAL)
    except Exception as exc:
        return LogosResult.failure(action, f"Season arc alignment failed: {exc}")
    head = (f"{ep.episode_label} ({chapter}): Season / Arc plan: "
            f"{'yes' if ep.has_season_plan else 'no'}.")
    msg = head + ("\n\nNo season-arc alignment issues detected." if not issues
                  else "\n\n" + sd.render_issues(issues))
    return LogosResult(ok=True, action=action, title="Season Arc Alignment",
        message=msg, suggestions=[i.label for i in issues], proposed_operations=[])


register("series_arc_alignment", _series_arc_alignment)


def _series_dialogue_balance(db, context: LogosContext) -> LogosResult:
    """Deterministic Dialogue / Action balance check (Phase 3) for the current
    scene. Report-only, never calls the LLM."""
    action = "series_dialogue_balance"
    scene_id = context.current_scene_id
    if scene_id is None:
        return LogosResult(ok=True, action=action, title="Dialogue / Action Balance",
            message="Open a Series scene in the Manuscript to check balance.",
            suggestions=[], proposed_operations=[])
    try:
        from logosforge import series_diagnostics as sd
        r = sd.analyze_scene_by_id(db, context.project_id, scene_id)
        issues = r.issues_in(sd.CAT_BALANCE)
        m = r.metrics
    except Exception as exc:
        return LogosResult.failure(action, f"Dialogue / Action balance failed: {exc}")
    head = (f"{m.dialogue_count} dialogue / {m.action_count} action "
            f"(ratio {m.dialogue_action_ratio}); longest speech "
            f"{m.longest_dialogue_words} words; longest dialogue run "
            f"{m.max_consecutive_dialogue}.")
    msg = head + ("\n\nDialogue / action balance looks healthy." if not issues
                  else "\n\n" + sd.render_issues(issues))
    return LogosResult(ok=True, action=action, title="Dialogue / Action Balance",
        message=msg, suggestions=[i.label for i in issues], proposed_operations=[])


register("series_dialogue_balance", _series_dialogue_balance)


def _series_reflection(db, context: LogosContext) -> LogosResult:
    """Deterministic Series Counterpart / Reflection (Phase 4).

    Re-projects the Phase 3 diagnostics + Phase 2 plans + PSYKE + Timeline into
    audience / showrunner / character-arc / episode-structure / writers-room
    perspectives with revision questions. Reflection only — never rewrites, never
    mutates, never calls the LLM."""
    action = "series_reflection"
    scene_id = context.current_scene_id
    if scene_id is None:
        return LogosResult(
            ok=True, action=action, title="Series Reflection",
            message="Open a Series scene in the Manuscript to reflect on it.",
            suggestions=[], proposed_operations=[])
    try:
        from logosforge.series_reflection import build_scene_reflection
        report = build_scene_reflection(db, context.project_id, scene_id)
    except Exception as exc:  # never crash the UI
        return LogosResult.failure(action, f"Reflection failed: {exc}")
    suggestions = list(report.suggested_actions) + [f"Q: {q}" for q in report.questions]
    return LogosResult(ok=True, action=action, title="Series Reflection",
                       message=report.to_text(), suggestions=suggestions,
                       proposed_operations=[])   # reflection only — no mutation


register("series_reflection", _series_reflection)


def _series_perspective(db, context: LogosContext, *, action: str, title: str,
                        section: str) -> LogosResult:
    """Shared driver: build the Series reflection once and render one perspective."""
    scene_id = context.current_scene_id
    if scene_id is None:
        return LogosResult(ok=True, action=action, title=title,
            message="Open a Series scene in the Manuscript to reflect on it.",
            suggestions=[], proposed_operations=[])
    try:
        from logosforge.series_reflection import build_scene_reflection
        report = build_scene_reflection(db, context.project_id, scene_id)
    except Exception as exc:
        return LogosResult.failure(action, f"Reflection failed: {exc}")
    return LogosResult(ok=True, action=action, title=title,
                       message=report.section_text(section),
                       suggestions=[f"Q: {q}" for q in report.questions],
                       proposed_operations=[])


def _series_audience_reflection(db, context: LogosContext) -> LogosResult:
    from logosforge import series_reflection as sr
    return _series_perspective(db, context, action="series_audience_reflection",
                               title="Audience Perspective", section=sr.SEC_AUDIENCE)


def _series_showrunner_reflection(db, context: LogosContext) -> LogosResult:
    from logosforge import series_reflection as sr
    return _series_perspective(db, context, action="series_showrunner_reflection",
                               title="Showrunner Perspective", section=sr.SEC_SHOWRUNNER)


def _series_character_reflection(db, context: LogosContext) -> LogosResult:
    from logosforge import series_reflection as sr
    return _series_perspective(db, context, action="series_character_reflection",
                               title="Character Arc Perspective", section=sr.SEC_CHARACTER)


def _series_episode_structure_reflection(db, context: LogosContext) -> LogosResult:
    from logosforge import series_reflection as sr
    return _series_perspective(db, context,
                               action="series_episode_structure_reflection",
                               title="Episode Structure Perspective",
                               section=sr.SEC_EPISODE)


def _series_writers_room(db, context: LogosContext) -> LogosResult:
    from logosforge import series_reflection as sr
    return _series_perspective(db, context, action="series_writers_room",
                               title="Writers-Room Notes", section=sr.SEC_WRITERS)


register("series_audience_reflection", _series_audience_reflection)
register("series_showrunner_reflection", _series_showrunner_reflection)
register("series_character_reflection", _series_character_reflection)
register("series_episode_structure_reflection", _series_episode_structure_reflection)
register("series_writers_room", _series_writers_room)


def _series_continuity_check(db, context: LogosContext) -> LogosResult:
    """Deterministic cross-episode Series continuity report (Phase 6).

    Project-level (no selection / current scene needed). Read-only — consolidates
    season/arc coherence, the episode chain, A/B/C story tracking, character arcs,
    setup/payoff, episode structure, Timeline alignment, and PSYKE/Notes. Never
    mutates, never calls the LLM."""
    action = "series_continuity_check"
    try:
        from logosforge.series_continuity import build_series_continuity_report
        report = build_series_continuity_report(db, context.project_id)
    except Exception as exc:  # never crash the UI
        return LogosResult.failure(action, f"Continuity check failed: {exc}")
    return LogosResult(
        ok=True, action=action, title="Series Continuity Check",
        message=report.to_text(), suggestions=list(report.recommended_fixes),
        proposed_operations=[],  # report only — no mutation
    )


register("series_continuity_check", _series_continuity_check)


def _series_review_dashboard(db, context: LogosContext) -> LogosResult:
    """Deterministic project-level Series Review Dashboard (Phase 7).

    Read-only roll-up rendered as Markdown: per-scene plan/body/A-B-C/act-break/
    cold-open-tag/continuity/Timeline/PSYKE status across Season -> Episode -> Scene,
    plus a recommended next action and export readiness. Never mutates, never
    auto-applies, never calls the LLM."""
    action = "series_review_dashboard"
    try:
        from logosforge.series_dashboard import build_series_review
        report = build_series_review(db, context.project_id)
    except Exception as exc:  # never crash the UI
        return LogosResult.failure(action, f"Review failed: {exc}")
    suggestions = [f"{r.episode_label} · {r.title or 'Scene'}: {r.next_action}"
                   for r in report.scenes if r.overall_status != "OK"][:10]
    return LogosResult(
        ok=True, action=action, title="Series Review Dashboard",
        message=report.to_markdown(), suggestions=suggestions,
        proposed_operations=[])  # report only — no mutation


register("series_review_dashboard", _series_review_dashboard)


def _detect_setup_payoff(db, context: LogosContext) -> LogosResult:
    action = "sp_detect_setup_payoff"
    try:
        from logosforge.screenplay_setup_payoff import analyze_setup_payoff
        report = analyze_setup_payoff(db, context.project_id)
    except Exception as exc:
        return LogosResult.failure(action, f"Setup/payoff analysis failed: {exc}")
    lines = [report.summary, ""]
    if report.unresolved_setups:
        lines.append("Unresolved setups:")
        for c in report.unresolved_setups[:5]:
            lines.append(f"- {c.label} — {c.evidence}")
    if report.possible_payoffs:
        lines.append("")
        lines.append("Possible payoffs:")
        for c in report.possible_payoffs[:5]:
            lines.append(f"- {c.label} — {c.evidence}")
    if report.recurring_motifs:
        lines.append("")
        lines.append("Recurring motifs:")
        for c in report.recurring_motifs[:5]:
            lines.append(f"- {c.label} — {c.evidence}")
    suggestions = [f"{c.label}: {c.suggested_action}"
                   for c in report.unresolved_setups[:5]]
    return LogosResult(ok=True, action=action, title="Detect Setup/Payoff Candidates",
                       message="\n".join(lines).strip(), suggestions=suggestions,
                       proposed_operations=[])


def _track_unresolved_setups(db, context: LogosContext) -> LogosResult:
    action = "sp_track_unresolved_setups"
    try:
        from logosforge.screenplay_setup_payoff import analyze_setup_payoff
        report = analyze_setup_payoff(db, context.project_id)
    except Exception as exc:
        return LogosResult.failure(action, f"Setup/payoff analysis failed: {exc}")
    items = report.unresolved_setups
    if not items:
        msg = "No unresolved setup candidates detected."
    else:
        msg = "Unresolved setup candidates:\n" + "\n".join(
            f"- {c.label} (scene {c.scene_id}) — {c.evidence}" for c in items[:10]
        )
    return LogosResult(ok=True, action=action, title="Track Unresolved Setups",
                       message=msg, suggestions=[], proposed_operations=[])


def _find_possible_payoffs(db, context: LogosContext) -> LogosResult:
    action = "sp_find_possible_payoffs"
    try:
        from logosforge.screenplay_setup_payoff import analyze_setup_payoff
        report = analyze_setup_payoff(db, context.project_id)
    except Exception as exc:
        return LogosResult.failure(action, f"Setup/payoff analysis failed: {exc}")
    items = report.possible_payoffs
    if not items:
        msg = "No possible payoffs detected (need a planted element to recur)."
    else:
        msg = "Possible payoffs:\n" + "\n".join(
            f"- {c.label} (scene {c.scene_id}) — {c.evidence}" for c in items[:10]
        )
    return LogosResult(ok=True, action=action, title="Find Possible Payoffs",
                       message=msg, suggestions=[], proposed_operations=[])


def _check_subtext(db, context: LogosContext) -> LogosResult:
    action = "sp_check_subtext"
    scene_id = context.current_scene_id
    if scene_id is None:
        return LogosResult(ok=True, action=action, title="Check Dialogue Subtext",
                           message="Open a scene to check dialogue subtext.",
                           suggestions=[], proposed_operations=[])
    try:
        from logosforge.screenplay_subtext import analyze_subtext_by_id
        report = analyze_subtext_by_id(db, context.project_id, scene_id)
    except Exception as exc:
        return LogosResult.failure(action, f"Subtext analysis failed: {exc}")
    lines = [report.summary]
    if report.signals:
        lines.append("")
        for s in report.top_signals(8):
            lines.append(f"- [{s.signal_type}] {s.evidence}")
    suggestions = [s.suggested_action for s in report.top_signals(5)
                   if s.suggested_action]
    return LogosResult(ok=True, action=action, title="Check Dialogue Subtext",
                       message="\n".join(lines), suggestions=suggestions,
                       proposed_operations=[])


def _find_exposition(db, context: LogosContext) -> LogosResult:
    action = "sp_find_exposition"
    scene_id = context.current_scene_id
    if scene_id is None:
        return LogosResult(ok=True, action=action, title="Find Exposition in Dialogue",
                           message="Open a scene to scan dialogue for exposition.",
                           suggestions=[], proposed_operations=[])
    try:
        from logosforge.screenplay_subtext import (
            analyze_subtext_by_id, S_EXPOSITION_RISK,
        )
        report = analyze_subtext_by_id(db, context.project_id, scene_id)
    except Exception as exc:
        return LogosResult.failure(action, f"Subtext analysis failed: {exc}")
    exp = [s for s in report.signals if s.signal_type == S_EXPOSITION_RISK]
    if not exp:
        msg = "No obvious exposition markers detected in this scene's dialogue."
    else:
        msg = "Possible exposition:\n" + "\n".join(f"- {s.evidence}" for s in exp)
    return LogosResult(ok=True, action=action, title="Find Exposition in Dialogue",
                       message=msg, suggestions=[], proposed_operations=[])


register("sp_detect_setup_payoff", _detect_setup_payoff)
register("sp_track_unresolved_setups", _track_unresolved_setups)
register("sp_find_possible_payoffs", _find_possible_payoffs)
register("sp_check_subtext", _check_subtext)
register("sp_find_exposition", _find_exposition)


def _show_story_links(db, context: LogosContext) -> LogosResult:
    action = "sp_show_story_links"
    try:
        from logosforge.screenplay_graph import build_screenplay_graph
        graph = build_screenplay_graph(db, context.project_id)
    except Exception as exc:
        return LogosResult.failure(action, f"Graph build failed: {exc}")
    lines = [graph.summary]
    confirmed = [e for e in graph.edges if e.status in ("confirmed", "resolved")]
    candidates = [e for e in graph.edges if e.status == "candidate"]
    if confirmed:
        lines.append("")
        lines.append("Confirmed links:")
        for e in confirmed[:8]:
            lines.append(f"- {e.edge_type}: {e.label}")
    if candidates:
        lines.append("")
        lines.append("Candidate links:")
        for e in candidates[:8]:
            lines.append(f"- {e.edge_type}: {e.label} ({e.evidence})")
    return LogosResult(ok=True, action=action, title="Show Story Link Graph",
                       message="\n".join(lines), suggestions=[],
                       proposed_operations=[])


def _explain_link(db, context: LogosContext) -> LogosResult:
    """Deterministic, evidence-first explanation of the current scene's links."""
    action = "sp_explain_link"
    try:
        from logosforge.screenplay_graph import build_screenplay_graph
        graph = build_screenplay_graph(db, context.project_id,
                                       scene_id=context.current_scene_id)
    except Exception as exc:
        return LogosResult.failure(action, f"Graph build failed: {exc}")
    edges = [e for e in graph.edges if e.evidence]
    if not edges:
        msg = "No story links with explicit evidence for the current scope."
    else:
        msg = "Story links (evidence):\n" + "\n".join(
            f"- {e.edge_type}: {e.label} — {e.evidence}" for e in edges[:10]
        )
    return LogosResult(ok=True, action=action, title="Explain This Link",
                       message=msg, suggestions=[], proposed_operations=[])


register("sp_show_story_links", _show_story_links)
register("sp_explain_link", _explain_link)


def _validation_report(db, project_id: int):
    from logosforge.screenplay_export_validation import validate_screenplay_export
    from logosforge.screenplay_render import get_export_prefs
    prefs = get_export_prefs(db, project_id)
    return validate_screenplay_export(
        db, project_id, target_format=prefs.get("export_target", "fountain"),
        prefs=prefs)


def _validate_export(db, context: LogosContext) -> LogosResult:
    action = "sp_validate_export"
    try:
        rep = _validation_report(db, context.project_id)
    except Exception as exc:
        return LogosResult.failure(action, f"Validation failed: {exc}")
    lines = [rep.summary]
    if rep.blocking_errors:
        lines += ["", "Blocking errors:"] + [f"- {e}" for e in rep.blocking_errors]
    if rep.warnings:
        lines += ["", "Warnings:"] + [f"- {w}" for w in rep.warnings]
    if rep.suggestions:
        lines += ["", "Suggestions:"] + [f"- {s}" for s in rep.suggestions]
    return LogosResult(ok=True, action=action, title="Validate Screenplay Export",
                       message="\n".join(lines),
                       suggestions=list(rep.warnings[:5]), proposed_operations=[])


def _export_readiness_report(db, context: LogosContext) -> LogosResult:
    action = "sp_export_readiness_report"
    try:
        rep = _validation_report(db, context.project_id)
        from logosforge.screenplay_render import build_render_document
        doc = build_render_document(db, context.project_id)
    except Exception as exc:
        return LogosResult.failure(action, f"Report failed: {exc}")
    lines = [
        f"Target: {rep.target_format}",
        f"Export-safe: {'yes' if rep.is_export_safe else 'NO'}",
        f"Title: {doc.title or '(none)'}",
    ]
    if doc.estimated_pages is not None:
        lines.append(f"Approx. length: ~{doc.estimated_pages} pages / "
                     f"~{doc.estimated_minutes} min (approximate)")
    lines.append(rep.summary)
    return LogosResult(ok=True, action=action, title="Export Readiness Report",
                       message="\n".join(lines), suggestions=[],
                       proposed_operations=[])


def _preview_render(db, context: LogosContext) -> LogosResult:
    action = "sp_preview_render"
    try:
        from logosforge.screenplay_render import build_render_document
        doc = build_render_document(db, context.project_id)
    except Exception as exc:
        return LogosResult.failure(action, f"Render prep failed: {exc}")
    msg = (f"Render document: {len(doc.blocks)} block(s); "
           f"title '{doc.title or '(none)'}'.")
    if doc.estimated_pages is not None:
        msg += f" ~{doc.estimated_pages} pages (approximate)."
    if doc.warnings:
        msg += "\nWarnings:\n" + "\n".join(f"- {w}" for w in doc.warnings)
    return LogosResult(ok=True, action=action, title="Preview Screenplay Render",
                       message=msg, suggestions=[], proposed_operations=[])


def _find_orphans(db, context: LogosContext, *, want: str) -> LogosResult:
    action = f"sp_find_orphan_{want}"
    try:
        rep = _validation_report(db, context.project_id)
    except Exception as exc:
        return LogosResult.failure(action, f"Validation failed: {exc}")
    needle = "dialogue block" if want == "dialogue" else "parenthetical"
    hits = [w for w in rep.warnings if needle in w]
    msg = ("\n".join(f"- {h}" for h in hits) if hits
           else f"No orphan {want} detected.")
    title = ("Find Orphan Dialogue" if want == "dialogue"
             else "Find Orphan Parentheticals")
    return LogosResult(ok=True, action=action, title=title, message=msg,
                       suggestions=[], proposed_operations=[])


def _check_production_polish(db, context: LogosContext) -> LogosResult:
    action = "sp_check_production_polish"
    try:
        rep = _validation_report(db, context.project_id)
    except Exception as exc:
        return LogosResult.failure(action, f"Validation failed: {exc}")
    n = len(rep.blocking_errors) + len(rep.warnings)
    head = ("Looks production-clean." if n == 0
            else f"{n} format issue(s) to review before export.")
    lines = [head] + [f"- {w}" for w in (rep.blocking_errors + rep.warnings)[:8]]
    return LogosResult(ok=True, action=action, title="Check Production Polish",
                       message="\n".join(lines), suggestions=[],
                       proposed_operations=[])


register("sp_validate_export", _validate_export)
register("sp_export_readiness_report", _export_readiness_report)
register("sp_preview_render", _preview_render)
register("sp_find_orphan_dialogue", lambda db, c: _find_orphans(db, c, want="dialogue"))
register("sp_find_orphan_parenthetical",
         lambda db, c: _find_orphans(db, c, want="parenthetical"))
register("sp_check_production_polish", _check_production_polish)


def _fountain_text(db, project_id: int) -> str:
    from logosforge.export import export_screenplay_fountain
    return export_screenplay_fountain(db, project_id)


def _fountain_validate(db, context: LogosContext) -> LogosResult:
    action = "sp_validate_fountain_export"
    try:
        from logosforge.screenplay_fountain import validate_fountain_export
        rep = validate_fountain_export(_fountain_text(db, context.project_id))
    except Exception as exc:
        return LogosResult.failure(action, f"Fountain validation failed: {exc}")
    lines = [rep.summary]
    if rep.blocking_errors:
        lines += ["", "Blocking:"] + [f"- {e}" for e in rep.blocking_errors]
    if rep.warnings:
        lines += ["", "Warnings:"] + [f"- {w}" for w in rep.warnings]
    return LogosResult(ok=True, action=action, title="Validate Fountain Export",
                       message="\n".join(lines), suggestions=list(rep.warnings[:5]),
                       proposed_operations=[])


def _fountain_preview(db, context: LogosContext) -> LogosResult:
    action = "sp_preview_fountain"
    try:
        text = _fountain_text(db, context.project_id)
    except Exception as exc:
        return LogosResult.failure(action, f"Fountain export failed: {exc}")
    head = "\n".join(text.splitlines()[:24])
    more = "" if text.count("\n") <= 24 else "\n…(truncated preview)"
    return LogosResult(ok=True, action=action, title="Preview Fountain Output",
                       message=head + more, suggestions=[], proposed_operations=[])


def _fountain_compat(db, context: LogosContext) -> LogosResult:
    action = "sp_check_fountain_compatibility"
    try:
        from logosforge.export import export_screenplay_fountain_result
        res = export_screenplay_fountain_result(db, context.project_id)
    except Exception as exc:
        return LogosResult.failure(action, f"Fountain export failed: {exc}")
    if not res.warnings:
        msg = "Screenplay maps cleanly to Fountain — no compatibility warnings."
    else:
        msg = "Fountain compatibility notes:\n" + "\n".join(
            f"- {w}" for w in res.warnings[:10])
    return LogosResult(ok=True, action=action, title="Check Fountain Compatibility",
                       message=msg, suggestions=[], proposed_operations=[])


def _fountain_ambiguous(db, context: LogosContext) -> LogosResult:
    action = "sp_find_ambiguous_fountain"
    try:
        from logosforge.export import export_screenplay_fountain_result
        res = export_screenplay_fountain_result(db, context.project_id)
    except Exception as exc:
        return LogosResult.failure(action, f"Fountain export failed: {exc}")
    amb = [w for w in res.warnings if "ambiguous" in w.lower() or "forced" in w.lower()]
    msg = ("\n".join(f"- {w}" for w in amb) if amb
           else "No ambiguous Fountain elements detected.")
    return LogosResult(ok=True, action=action, title="Find Ambiguous Fountain Elements",
                       message=msg, suggestions=[], proposed_operations=[])


def _fountain_explain_warning(db, context: LogosContext) -> LogosResult:
    action = "sp_explain_fountain_warning"
    try:
        from logosforge.screenplay_fountain import validate_fountain_export
        rep = validate_fountain_export(_fountain_text(db, context.project_id))
    except Exception as exc:
        return LogosResult.failure(action, f"Fountain validation failed: {exc}")
    if not rep.warnings:
        msg = "No Fountain warnings to explain."
    else:
        msg = ("Fountain warnings (deterministic):\n"
               + "\n".join(f"- {w}" for w in rep.warnings))
    return LogosResult(ok=True, action=action, title="Explain Fountain Warning",
                       message=msg, suggestions=[], proposed_operations=[])


def _fountain_prepare(db, context: LogosContext) -> LogosResult:
    action = "sp_prepare_for_fountain"
    try:
        from logosforge.screenplay_fountain import validate_fountain_export
        from logosforge.screenplay_render import get_title_page
        rep = validate_fountain_export(_fountain_text(db, context.project_id))
        title = (get_title_page(db, context.project_id).get("title") or "").strip()
    except Exception as exc:
        return LogosResult.failure(action, f"Preparation failed: {exc}")
    steps = []
    if not title:
        steps.append("Set a title page (Title/Author).")
    for w in rep.warnings:
        steps.append(f"Review: {w}")
    msg = ("Ready to export as .fountain." if not steps
           else "Before exporting as .fountain:\n" + "\n".join(f"- {s}" for s in steps))
    return LogosResult(ok=True, action=action, title="Prepare Screenplay for Fountain Export",
                       message=msg, suggestions=steps[:5], proposed_operations=[])


register("sp_validate_fountain_export", _fountain_validate)
register("sp_preview_fountain", _fountain_preview)
register("sp_check_fountain_compatibility", _fountain_compat)
register("sp_find_ambiguous_fountain", _fountain_ambiguous)
register("sp_explain_fountain_warning", _fountain_explain_warning)
register("sp_prepare_for_fountain", _fountain_prepare)


# -- Phase 10H — professional output (DOCX / PDF / FDX) -----------------------


def _output_report(db, project_id: int, target: str):
    from logosforge.screenplay_output_validation import validate_professional_output
    return validate_professional_output(db, project_id, target_format=target)


def _validate_professional_output(db, context: LogosContext) -> LogosResult:
    action = "sp_validate_professional_output"
    try:
        rep = _output_report(db, context.project_id, "docx")
    except Exception as exc:
        return LogosResult.failure(action, f"Output validation failed: {exc}")
    lines = [f"Available formats: {', '.join(rep.available_formats)}",
             f"Target: {rep.target_format} ({rep.compatibility_level})",
             f"Export-safe: {'yes' if rep.is_export_safe else 'NO'}"]
    if rep.blocking_errors:
        lines += ["Blocking:"] + [f"- {e}" for e in rep.blocking_errors]
    if rep.warnings:
        lines += ["Warnings:"] + [f"- {w}" for w in rep.warnings[:6]]
    return LogosResult(ok=True, action=action, title="Validate Professional Output",
                       message="\n".join(lines), suggestions=list(rep.suggestions[:5]),
                       proposed_operations=[])


def _output_readiness_report(db, context: LogosContext) -> LogosResult:
    action = "sp_output_readiness_report"
    try:
        from logosforge.screenplay_output_validation import available_output_formats
        from logosforge.screenplay_render import build_render_document, get_title_page
        doc = build_render_document(db, context.project_id)
        title = (get_title_page(db, context.project_id).get("title") or "").strip()
    except Exception as exc:
        return LogosResult.failure(action, f"Report failed: {exc}")
    lines = [f"Formats: {', '.join(available_output_formats())}",
             f"Title page: {title or '(none)'}",
             f"Blocks: {len(doc.blocks)}"]
    if doc.estimated_pages is not None:
        lines.append(f"Approx. length: ~{doc.estimated_pages} pages (approximate)")
    return LogosResult(ok=True, action=action, title="Output Readiness Report",
                       message="\n".join(lines), suggestions=[], proposed_operations=[])


def _preview_output(db, context: LogosContext) -> LogosResult:
    action = "sp_preview_output"
    try:
        from logosforge.export import export_professional_preview_html
        html = export_professional_preview_html(db, context.project_id)
    except Exception as exc:
        return LogosResult.failure(action, f"Preview failed: {exc}")
    return LogosResult(ok=True, action=action, title="Preview Screenplay Output",
                       message=f"Preview HTML generated ({len(html)} chars). "
                               "Open it in a browser and print to PDF for best fidelity.",
                       suggestions=[], proposed_operations=[])


def _check_pdf_readiness(db, context: LogosContext) -> LogosResult:
    action = "sp_check_pdf_readiness"
    rep = _output_report(db, context.project_id, "pdf")
    msg = (f"PDF target: {rep.compatibility_level}. "
           + ("Export-safe. " if rep.is_export_safe else "NOT safe. ")
           + " ".join(rep.warnings[:3]))
    return LogosResult(ok=True, action=action, title="Check PDF Readiness",
                       message=msg, suggestions=list(rep.suggestions[:3]),
                       proposed_operations=[])


def _check_fdx_feasibility(db, context: LogosContext) -> LogosResult:
    action = "sp_check_fdx_feasibility"
    rep = _output_report(db, context.project_id, "fdx")
    msg = (f"FDX target: {rep.compatibility_level} (experimental, unverified). "
           + " ".join(rep.warnings[:3]))
    return LogosResult(ok=True, action=action, title="Check FDX Feasibility",
                       message=msg, suggestions=["Prefer .fountain for Final Draft."],
                       proposed_operations=[])


def _explain_export_warnings(db, context: LogosContext) -> LogosResult:
    action = "sp_explain_export_warnings"
    rep = _output_report(db, context.project_id, "docx")
    msg = ("No export warnings." if not rep.warnings
           else "Export warnings (deterministic):\n"
           + "\n".join(f"- {w}" for w in rep.warnings))
    return LogosResult(ok=True, action=action, title="Explain Export Warnings",
                       message=msg, suggestions=[], proposed_operations=[])


def _prepare_professional(db, context: LogosContext) -> LogosResult:
    action = "sp_prepare_professional_export"
    rep = _output_report(db, context.project_id, "docx")
    steps = list(rep.blocking_errors) + list(rep.warnings)
    msg = ("Ready for professional export (DOCX stable; PDF preview; FDX experimental)."
           if not steps else "Before professional export:\n"
           + "\n".join(f"- {s}" for s in steps[:8]))
    return LogosResult(ok=True, action=action, title="Prepare Screenplay for Professional Export",
                       message=msg, suggestions=steps[:5], proposed_operations=[])


register("sp_validate_professional_output", _validate_professional_output)
register("sp_output_readiness_report", _output_readiness_report)
register("sp_preview_output", _preview_output)
register("sp_check_pdf_readiness", _check_pdf_readiness)
register("sp_check_fdx_feasibility", _check_fdx_feasibility)
register("sp_explain_export_warnings", _explain_export_warnings)
register("sp_prepare_professional_export", _prepare_professional)


# -- Phase 10J — production draft (read-only status/validation; mutations are a
#    separate, explicit service API) ------------------------------------------


def _production_status(db, context: LogosContext) -> LogosResult:
    action = "sp_production_status"
    try:
        from logosforge.screenplay_production import production_status
        st = production_status(db, context.project_id)
    except Exception as exc:
        return LogosResult.failure(action, f"Status failed: {exc}")
    if not st.get("active"):
        msg = "Spec draft (production mode not enabled)."
    else:
        msg = "\n".join([
            f"Mode: production — {st.get('draft_label', '')}",
            f"Scene numbering: {'on' if st.get('scene_numbering_enabled') else 'off'}",
            f"Numbered scenes: {st.get('numbered_scenes', 0)}; "
            f"omitted: {st.get('omitted_scenes', 0)}",
            f"Revision sets: {st.get('revision_sets', 0)}"
            + (f" (latest: {st['active_revision_set']})" if st.get('active_revision_set') else ""),
            f"Page locking: {st.get('page_locking_status', 'disabled')}",
        ])
        if st.get("warnings"):
            msg += "\nWarnings:\n" + "\n".join(f"- {w}" for w in st["warnings"][:3])
    return LogosResult(ok=True, action=action, title="Production Draft Status",
                       message=msg, suggestions=[], proposed_operations=[])


def _validate_production(db, context: LogosContext) -> LogosResult:
    action = "sp_validate_production"
    try:
        from logosforge.screenplay_production import validate_production_draft
        rep = validate_production_draft(db, context.project_id)
    except Exception as exc:
        return LogosResult.failure(action, f"Validation failed: {exc}")
    lines = [f"Readiness: {rep.readiness_level}"]
    if rep.blocking_errors:
        lines += ["Blocking:"] + [f"- {e}" for e in rep.blocking_errors]
    if rep.warnings:
        lines += ["Warnings:"] + [f"- {w}" for w in rep.warnings[:5]]
    if rep.suggestions:
        lines += ["Suggestions:"] + [f"- {s}" for s in rep.suggestions[:3]]
    return LogosResult(ok=True, action=action, title="Validate Production Draft",
                       message="\n".join(lines), suggestions=list(rep.suggestions[:3]),
                       proposed_operations=[])


def _check_duplicate_scene_numbers(db, context: LogosContext) -> LogosResult:
    action = "sp_check_duplicate_scene_numbers"
    try:
        from logosforge.screenplay_production import validate_scene_numbers
        problems = validate_scene_numbers(db, context.project_id)
    except Exception as exc:
        return LogosResult.failure(action, f"Check failed: {exc}")
    dupes = [p for p in problems if "Duplicate" in p]
    msg = ("No duplicate scene numbers." if not dupes
           else "\n".join(f"- {d}" for d in dupes))
    return LogosResult(ok=True, action=action, title="Check Duplicate Scene Numbers",
                       message=msg, suggestions=[], proposed_operations=[])


def _summarize_revision_set(db, context: LogosContext) -> LogosResult:
    action = "sp_summarize_revision_set"
    try:
        draft = db.get_active_production_draft(context.project_id)
        revs = db.get_revision_sets(draft.id) if draft else []
    except Exception as exc:
        return LogosResult.failure(action, f"Summary failed: {exc}")
    if not revs:
        msg = "No revision sets."
    else:
        changes = db.get_revision_changes(draft.id)
        latest = revs[-1]
        n = sum(1 for c in changes if c.revision_set_id == latest.id)
        msg = (f"Latest revision: {latest.label} ({latest.color_name}, "
               f"{latest.status}) — {n} scene change(s). Total sets: {len(revs)}.")
    return LogosResult(ok=True, action=action, title="Summarize Revision Set",
                       message=msg, suggestions=[], proposed_operations=[])


def _explain_page_locking(db, context: LogosContext) -> LogosResult:
    action = "sp_explain_page_locking"
    msg = ("Page locking is APPROXIMATE: pagination is line-count based, not "
           "page-accurate, so true page locking (stable page labels, 10A inserts) "
           "is deferred. Use scene numbers + revision sets for production tracking.")
    return LogosResult(ok=True, action=action, title="Explain Page Locking Status",
                       message=msg, suggestions=[], proposed_operations=[])


def _check_fountain_production_export(db, context: LogosContext) -> LogosResult:
    action = "sp_check_fountain_production_export"
    try:
        from logosforge.export import export_production_fountain
        text = export_production_fountain(db, context.project_id)
    except Exception as exc:
        return LogosResult.failure(action, f"Export check failed: {exc}")
    has_numbers = "#" in text
    msg = ("Production Fountain export ready"
           + (" (scene numbers present)." if has_numbers
              else " (no scene numbers — assign them first)."))
    return LogosResult(ok=True, action=action, title="Check Fountain Production Export",
                       message=msg, suggestions=[], proposed_operations=[])


def _prepare_production_export(db, context: LogosContext) -> LogosResult:
    action = "sp_prepare_production_export"
    try:
        from logosforge.screenplay_production import validate_production_draft
        rep = validate_production_draft(db, context.project_id)
    except Exception as exc:
        return LogosResult.failure(action, f"Preparation failed: {exc}")
    steps = list(rep.blocking_errors) + list(rep.warnings)
    msg = (f"Readiness: {rep.readiness_level}. "
           + ("Ready for production export." if not steps
              else "Review:\n" + "\n".join(f"- {s}" for s in steps[:6])))
    return LogosResult(ok=True, action=action,
                       title="Prepare Screenplay for Production Export",
                       message=msg, suggestions=steps[:5], proposed_operations=[])


register("sp_production_status", _production_status)
register("sp_validate_production", _validate_production)
register("sp_check_duplicate_scene_numbers", _check_duplicate_scene_numbers)
register("sp_summarize_revision_set", _summarize_revision_set)
register("sp_explain_page_locking", _explain_page_locking)
register("sp_check_fountain_production_export", _check_fountain_production_export)
register("sp_prepare_production_export", _prepare_production_export)


# -- Phase 10K — revision intelligence (read-only; saving a report is a separate
#    explicit service call) -----------------------------------------------------


def _impact_map(db, context: LogosContext):
    from logosforge.revision_intelligence.impact_map import build_revision_impact_map
    return build_revision_impact_map(db, context.project_id,
                                     scene_id=context.current_scene_id)


def _needs_scene(action: str, title: str) -> LogosResult:
    return LogosResult(ok=True, action=action, title=title,
                       message="Open a scene to run revision intelligence.",
                       suggestions=[], proposed_operations=[])


def _revision_impact(db, context: LogosContext) -> LogosResult:
    action = "sp_revision_impact"
    if context.current_scene_id is None:
        return _needs_scene(action, "Revision Impact Map")
    try:
        m = _impact_map(db, context)
    except Exception as exc:
        return LogosResult.failure(action, f"Impact map failed: {exc}")
    lines = [m.summary]
    if m.impacted_scenes:
        lines.append("Impacted scenes: " + ", ".join(
            f"{s['label']} ({s['confidence']})" for s in m.impacted_scenes[:3]))
    if m.impacted_psyke_entries:
        lines.append("PSYKE: " + ", ".join(
            p["name"] for p in m.impacted_psyke_entries[:3]))
    if m.limitations:
        lines.append("Limitations: " + "; ".join(m.limitations))
    return LogosResult(ok=True, action=action, title="Generate Revision Impact Map",
                       message="\n".join(lines), suggestions=[], proposed_operations=[])


def _check_psyke_impact(db, context: LogosContext) -> LogosResult:
    action = "sp_check_psyke_impact"
    if context.current_scene_id is None:
        return _needs_scene(action, "Check PSYKE Impact")
    m = _impact_map(db, context)
    if not m.impacted_psyke_entries:
        msg = "No PSYKE entries detected in this scene."
    else:
        msg = "\n".join(f"- {p['name']} ({p['impact_kind']}, {p['confidence']})"
                        for p in m.impacted_psyke_entries[:10])
    return LogosResult(ok=True, action=action, title="Check PSYKE Impact",
                       message=msg, suggestions=[], proposed_operations=[])


def _check_setup_payoff_impact(db, context: LogosContext) -> LogosResult:
    action = "sp_check_setup_payoff_impact"
    if context.current_scene_id is None:
        return _needs_scene(action, "Check Setup/Payoff Impact")
    m = _impact_map(db, context)
    if not m.setup_payoff_impacts:
        msg = "No setup/payoff chains connected to this scene."
    else:
        msg = "\n".join(f"- {s['label']} ({s['impact_kind']})"
                        for s in m.setup_payoff_impacts[:10])
    return LogosResult(ok=True, action=action, title="Check Setup/Payoff Impact",
                       message=msg, suggestions=[], proposed_operations=[])


def _check_continuity_impact(db, context: LogosContext) -> LogosResult:
    action = "sp_check_continuity_impact"
    if context.current_scene_id is None:
        return _needs_scene(action, "Check Continuity Impact")
    m = _impact_map(db, context)
    msg = "\n".join(f"- {c['label']} ({c['confidence']})"
                    for c in m.continuity_impacts[:10])
    return LogosResult(ok=True, action=action, title="Check Continuity Impact",
                       message=msg, suggestions=[], proposed_operations=[])


def _check_impacted_scenes(db, context: LogosContext) -> LogosResult:
    action = "sp_check_impacted_scenes"
    if context.current_scene_id is None:
        return _needs_scene(action, "Check Impacted Scenes")
    m = _impact_map(db, context)
    if not m.impacted_scenes:
        msg = "No dependent scenes detected."
    else:
        msg = "\n".join(f"- {s['label']}: {s['impact_kind']} "
                        f"({s['confidence']}) — {s['explanation']}"
                        for s in m.impacted_scenes[:12])
    return LogosResult(ok=True, action=action, title="Check Impacted Scenes",
                       message=msg, suggestions=[], proposed_operations=[])


def _prepare_revision_followup(db, context: LogosContext) -> LogosResult:
    action = "sp_prepare_revision_followup"
    if context.current_scene_id is None:
        return _needs_scene(action, "Prepare Revision Follow-up Checklist")
    m = _impact_map(db, context)
    checks = []
    for s in m.impacted_scenes[:5]:
        if s.get("suggested_action"):
            checks.append(f"{s['label']}: {s['suggested_action']}")
    for sp in m.setup_payoff_impacts[:3]:
        if sp.get("suggested_action"):
            checks.append(sp["suggested_action"])
    if not checks:
        checks = ["No follow-up checks flagged by deterministic analysis."]
    return LogosResult(ok=True, action=action,
                       title="Prepare Revision Follow-up Checklist",
                       message="\n".join(f"- {c}" for c in checks),
                       suggestions=checks[:5], proposed_operations=[])


register("sp_revision_impact", _revision_impact)
register("sp_check_psyke_impact", _check_psyke_impact)
register("sp_check_setup_payoff_impact", _check_setup_payoff_impact)
register("sp_check_continuity_impact", _check_continuity_impact)
register("sp_check_impacted_scenes", _check_impacted_scenes)
register("sp_prepare_revision_followup", _prepare_revision_followup)


# -- Phase 10L — rewrite sandbox (writing-mode-aware, read-only status/score;
#    generation + apply are the explicit engine API) ---------------------------


def _rw_status(db, context: LogosContext) -> LogosResult:
    action = "rw_sandbox_status"
    try:
        from logosforge.rewrite_sandbox.engine import session_status
        st = session_status(db, context.project_id)
    except Exception as exc:
        return LogosResult.failure(action, f"Sandbox status failed: {exc}")
    if not st.get("active"):
        msg = ("No open rewrite session. Use the Rewrite Sandbox to generate "
               "variants for a selection/scene — nothing is applied automatically.")
    else:
        lines = [f"Source: {st['source_type']} ({st['writing_mode']})",
                 f"Variants: {st['variant_count']}"
                 + (f"; preferred: {st['preferred']}" if st.get("preferred") else ""),
                 f"Stale source: {'yes' if st['stale'] else 'no'}"]
        if st.get("psyke_terms_removed"):
            lines.append(f"PSYKE references removed across variants: "
                         f"{st['psyke_terms_removed']}")
        if st.get("warnings"):
            lines.append("Warnings: " + "; ".join(st["warnings"]))
        msg = "\n".join(lines)
    return LogosResult(ok=True, action=action, title="Rewrite Sandbox",
                       message=msg, suggestions=[], proposed_operations=[])


def _rw_explain_tradeoffs(db, context: LogosContext) -> LogosResult:
    action = "rw_explain_tradeoffs"
    import json
    try:
        sess = db.get_latest_rewrite_session(context.project_id, status="open")
        variants = db.get_rewrite_variants(sess.id) if sess else []
    except Exception as exc:
        return LogosResult.failure(action, f"Tradeoffs failed: {exc}")
    if not variants:
        msg = "No variants to compare. Generate rewrite variants first."
    else:
        lines = []
        for v in variants[:6]:
            try:
                s = json.loads(v.score_json or "{}")
            except Exception:
                s = {}
            lines.append(f"- {v.label}: {s.get('summary', 'no score')}")
        msg = "Variant tradeoffs:\n" + "\n".join(lines)
    return LogosResult(ok=True, action=action, title="Explain Rewrite Tradeoffs",
                       message=msg, suggestions=[], proposed_operations=[])


def _rw_score_variants(db, context: LogosContext) -> LogosResult:
    action = "rw_score_variants"
    try:
        from logosforge.rewrite_sandbox.engine import score_rewrite_variant
        sess = db.get_latest_rewrite_session(context.project_id, status="open")
        variants = db.get_rewrite_variants(sess.id) if sess else []
        for v in variants:
            score_rewrite_variant(db, context.project_id, v.id)
    except Exception as exc:
        return LogosResult.failure(action, f"Scoring failed: {exc}")
    return LogosResult(ok=True, action=action, title="Score Rewrite Variants",
                       message=f"Re-scored {len(variants)} variant(s) "
                               "(deterministic).", suggestions=[],
                       proposed_operations=[])


def _rw_check_psyke_preservation(db, context: LogosContext) -> LogosResult:
    action = "rw_check_psyke_preservation"
    import json
    try:
        sess = db.get_latest_rewrite_session(context.project_id, status="open")
        variants = db.get_rewrite_variants(sess.id) if sess else []
    except Exception as exc:
        return LogosResult.failure(action, f"Check failed: {exc}")
    if not variants:
        msg = "No variants to check."
    else:
        lines = []
        for v in variants[:6]:
            try:
                s = json.loads(v.score_json or "{}")
            except Exception:
                s = {}
            lines.append(f"- {v.label}: preserved {s.get('psyke_terms_preserved', 0)}, "
                         f"removed {s.get('psyke_terms_removed', 0)}, "
                         f"added {s.get('psyke_terms_added', 0)}")
        msg = "PSYKE preservation per variant:\n" + "\n".join(lines)
    return LogosResult(ok=True, action=action, title="Check PSYKE Preservation",
                       message=msg, suggestions=[], proposed_operations=[])


register("rw_sandbox_status", _rw_status)
register("rw_explain_tradeoffs", _rw_explain_tradeoffs)
register("rw_score_variants", _rw_score_variants)
register("rw_check_psyke_preservation", _rw_check_psyke_preservation)


# -- Phase 10M — controlled apply (read-only status/conflict explainers) -------


def _ca_history(db, context: LogosContext) -> LogosResult:
    action = "ca_apply_history"
    try:
        from logosforge.controlled_apply.service import get_apply_history
        ops = get_apply_history(db, context.project_id)
    except Exception as exc:
        return LogosResult.failure(action, f"History failed: {exc}")
    if not ops:
        msg = "No controlled-apply operations yet."
    else:
        lines = [f"- {o.source_type} → {o.target_type} ({o.status})"
                 for o in ops[-8:]]
        msg = "Recent apply operations:\n" + "\n".join(lines)
    return LogosResult(ok=True, action=action, title="Apply History",
                       message=msg, suggestions=[], proposed_operations=[])


def _ca_explain_conflicts(db, context: LogosContext) -> LogosResult:
    action = "ca_explain_conflicts"
    import json
    try:
        from logosforge.controlled_apply.service import get_apply_history
        ops = [o for o in get_apply_history(db, context.project_id)
               if o.status in ("draft", "previewed")]
    except Exception as exc:
        return LogosResult.failure(action, f"Explain failed: {exc}")
    if not ops:
        msg = "No pending apply previews to explain."
    else:
        op = ops[-1]
        try:
            conflicts = json.loads(op.conflict_json or "[]")
        except Exception:
            conflicts = []
        if not conflicts:
            msg = f"Pending apply to {op.target_type}: no conflicts."
        else:
            lines = [f"- [{c['severity']}] {c['conflict_type']}: {c['message']}"
                     for c in conflicts]
            msg = (f"Pending apply to {op.target_type} — conflicts:\n"
                   + "\n".join(lines))
    return LogosResult(ok=True, action=action, title="Explain Apply Conflicts",
                       message=msg, suggestions=[], proposed_operations=[])


register("ca_apply_history", _ca_history)
register("ca_explain_conflicts", _ca_explain_conflicts)


# -- Phase 10N — project intelligence dashboard (read-only summaries) ----------


def _pi_dashboard_status(db, context: LogosContext) -> LogosResult:
    action = "pi_dashboard_status"
    try:
        from logosforge.project_intelligence import build_project_intelligence_report
        rep = build_project_intelligence_report(db, context.project_id)
    except Exception as exc:
        return LogosResult.failure(action, f"Dashboard failed: {exc}")
    ov, st, pk = rep.overview, rep.structure, rep.psyke
    lines = [rep.summary_line(),
             f"Words: {ov.get('total_words', 0)}; chapters: {ov.get('total_chapters', 0)}; "
             f"acts: {ov.get('total_acts', 0)}; notes: {ov.get('total_notes', 0)}",
             f"Scenes without summary: {st.get('scenes_without_summary', 0)}"]
    if pk.get("available"):
        lines.append(f"PSYKE: {pk.get('total', 0)} entries, "
                     f"{pk.get('empty_notes', 0)} with empty notes")
    if rep.health.get("available"):
        lines.append(f"Health: {rep.health.get('overall', 'unknown')}")
    return LogosResult(ok=True, action=action, title="Project Intelligence",
                       message="\n".join(lines), suggestions=[], proposed_operations=[])


def _pi_decision_radar(db, context: LogosContext) -> LogosResult:
    action = "pi_decision_radar"
    try:
        from logosforge.project_intelligence import build_project_intelligence_report
        rep = build_project_intelligence_report(db, context.project_id)
    except Exception as exc:
        return LogosResult.failure(action, f"Radar failed: {exc}")
    if not rep.radar:
        msg = "Decision Radar is clear — no flagged decisions."
    else:
        lines = [f"- [{c.severity}] {c.title}"
                 + (f" → {c.suggested_action}" if c.suggested_action else "")
                 for c in rep.radar[:10]]
        msg = "Decision Radar:\n" + "\n".join(lines)
    return LogosResult(ok=True, action=action, title="Decision Radar",
                       message=msg,
                       suggestions=[c.suggested_action for c in rep.top_cards(5)
                                    if c.suggested_action],
                       proposed_operations=[])


register("pi_dashboard_status", _pi_dashboard_status)
register("pi_decision_radar", _pi_decision_radar)


# -- Guided workflows (Phase 10O) -------------------------------------------

def _wf_active_workflows(db, context: LogosContext) -> LogosResult:
    action = "wf_active_workflows"
    try:
        from logosforge.guided_workflows import get_active_workflows
        views = get_active_workflows(db, context.project_id)
    except Exception as exc:
        return LogosResult.failure(action, f"Workflows failed: {exc}")
    if not views:
        return LogosResult(ok=True, action=action, title="Active Workflows",
                           message="No active guided workflows.",
                           suggestions=[], proposed_operations=[])
    lines: list[str] = []
    for v in views:
        lines.append(v.progress_line())
        cur = v.current_step
        if cur is not None:
            lines.append(f"  Current: {cur.title}"
                         + (f" (open {cur.section_name})" if cur.section_name else ""))
    return LogosResult(ok=True, action=action, title="Active Workflows",
                       message="\n".join(lines), suggestions=[],
                       proposed_operations=[])


def _wf_recommend_workflows(db, context: LogosContext) -> LogosResult:
    action = "wf_recommend_workflows"
    try:
        from logosforge.guided_workflows import build_workflow_recommendations
        recs = build_workflow_recommendations(db, context.project_id)
    except Exception as exc:
        return LogosResult.failure(action, f"Recommendations failed: {exc}")
    if not recs:
        return LogosResult(ok=True, action=action, title="Recommend Workflows",
                           message="No workflow recommendations right now.",
                           suggestions=[], proposed_operations=[])
    lines = [f"- {r.title}: {r.reason}" for r in recs]
    return LogosResult(ok=True, action=action, title="Recommend Workflows",
                       message="Suggested workflows:\n" + "\n".join(lines),
                       suggestions=[r.title for r in recs], proposed_operations=[])


register("wf_active_workflows", _wf_active_workflows)
register("wf_recommend_workflows", _wf_recommend_workflows)


# -- Narrative Knowledge Graph (Phase 10P) ----------------------------------

def _kg_build(db, context: LogosContext) -> LogosResult:
    action = "kg_build_graph"
    try:
        from logosforge.knowledge_graph import build_knowledge_graph
        res = build_knowledge_graph(db, context.project_id)
    except Exception as exc:
        return LogosResult.failure(action, f"Graph build failed: {exc}")
    lines = [res.summary_line()]
    if res.central:
        lines.append("Central: " + ", ".join(
            f"{n.label}({d})" for n, d in res.central[:5]))
    if res.graph.unavailable:
        lines.append("Deferred sources: " + ", ".join(sorted(set(res.graph.unavailable))))
    return LogosResult(ok=True, action=action, title="Knowledge Graph",
                       message="\n".join(lines), suggestions=[],
                       proposed_operations=[])


def _kg_refresh(db, context: LogosContext) -> LogosResult:
    action = "kg_refresh_graph"
    try:
        from logosforge.knowledge_graph import build_knowledge_graph, persist_snapshot
        res = build_knowledge_graph(db, context.project_id)
        persist_snapshot(db, context.project_id, res)
    except Exception as exc:
        return LogosResult.failure(action, f"Graph refresh failed: {exc}")
    return LogosResult(ok=True, action=action, title="Knowledge Graph",
                       message="Refreshed. " + res.summary_line(),
                       suggestions=[], proposed_operations=[])


def _kg_scene_neighborhood(db, context: LogosContext) -> LogosResult:
    action = "kg_scene_neighborhood"
    if not context.current_scene_id:
        return LogosResult(ok=True, action=action, title="Scene Neighborhood",
                           message="Open a scene to see its neighborhood.",
                           suggestions=[], proposed_operations=[])
    try:
        from logosforge.knowledge_graph import (
            build_knowledge_graph, get_scene_context_graph)
        from logosforge.knowledge_graph.serializers import explain_node
        from logosforge.knowledge_graph.models import node_key
        from logosforge.knowledge_graph import provenance as P
        graph = build_knowledge_graph(db, context.project_id).graph
        key = node_key(P.NT_SCENE, "scene", context.current_scene_id)
        msg = explain_node(graph, key)
    except Exception as exc:
        return LogosResult.failure(action, f"Neighborhood failed: {exc}")
    return LogosResult(ok=True, action=action, title="Scene Neighborhood",
                       message=msg, suggestions=[], proposed_operations=[])


def _kg_psyke_neighborhood(db, context: LogosContext) -> LogosResult:
    action = "kg_psyke_neighborhood"
    eid = context.current_psyke_entry_id or context.selected_psyke_entry_id
    if not eid:
        return LogosResult(ok=True, action=action, title="PSYKE Neighborhood",
                           message="Select a PSYKE entry to see its neighborhood.",
                           suggestions=[], proposed_operations=[])
    try:
        from logosforge.knowledge_graph import (
            build_knowledge_graph, get_psyke_entry_context_graph)
        graph = build_knowledge_graph(db, context.project_id).graph
        res = get_psyke_entry_context_graph(db, context.project_id, eid, graph=graph)
        lines = [res.explanation]
        for e in res.edges[:10]:
            lines.append(f"- {e.edge_type} [{e.confidence}] ({e.source_system})")
        msg = "\n".join(lines)
    except Exception as exc:
        return LogosResult.failure(action, f"Neighborhood failed: {exc}")
    return LogosResult(ok=True, action=action, title="PSYKE Neighborhood",
                       message=msg, suggestions=[], proposed_operations=[])


def _kg_find_orphans(db, context: LogosContext) -> LogosResult:
    action = "kg_find_orphans"
    try:
        from logosforge.knowledge_graph import get_orphan_nodes
        orphans = get_orphan_nodes(db, context.project_id)
    except Exception as exc:
        return LogosResult.failure(action, f"Orphan scan failed: {exc}")
    if not orphans:
        msg = "No orphan nodes — every story element is connected."
    else:
        msg = "Orphan nodes:\n" + "\n".join(
            f"- {n.node_type}: {n.label}" for n in orphans[:15])
    return LogosResult(ok=True, action=action, title="Orphan Nodes",
                       message=msg, suggestions=[], proposed_operations=[])


def _kg_find_weak_links(db, context: LogosContext) -> LogosResult:
    action = "kg_find_weak_links"
    try:
        from logosforge.knowledge_graph import build_knowledge_graph, get_weak_links
        from logosforge.knowledge_graph.serializers import _label
        graph = build_knowledge_graph(db, context.project_id).graph
        weak = get_weak_links(db, context.project_id, graph=graph)
    except Exception as exc:
        return LogosResult.failure(action, f"Weak-link scan failed: {exc}")
    if not weak:
        msg = "No inferred edges needing review."
    else:
        msg = "Inferred edges (review/confirm):\n" + "\n".join(
            f"- {_label(graph, e.source)} {e.edge_type} {_label(graph, e.target)} "
            f"[{e.confidence}]" for e in weak[:15])
    return LogosResult(ok=True, action=action, title="Weak Links",
                       message=msg, suggestions=[], proposed_operations=[])


def _kg_find_undefined_terms(db, context: LogosContext) -> LogosResult:
    action = "kg_find_undefined_terms"
    try:
        from logosforge.knowledge_graph import build_knowledge_graph
        res = build_knowledge_graph(db, context.project_id)
    except Exception as exc:
        return LogosResult.failure(action, f"Term scan failed: {exc}")
    if not res.undefined_terms:
        msg = "No undefined note terms detected."
    else:
        msg = ("Note terms not defined in PSYKE (review before creating):\n"
               + "\n".join(f"- {t}" for t in res.undefined_terms[:20]))
    return LogosResult(ok=True, action=action, title="Undefined Terms",
                       message=msg,
                       suggestions=res.undefined_terms[:5], proposed_operations=[])


def _kg_decision_cards(db, context: LogosContext) -> LogosResult:
    action = "kg_decision_cards"
    try:
        from logosforge.knowledge_graph import build_graph_decision_cards
        cards = build_graph_decision_cards(db, context.project_id)
    except Exception as exc:
        return LogosResult.failure(action, f"Card generation failed: {exc}")
    if not cards:
        msg = "No graph-derived decisions right now."
    else:
        msg = "Graph decisions:\n" + "\n".join(
            f"- [{c.severity}] {c.title}" for c in cards)
    return LogosResult(ok=True, action=action, title="Graph Decision Cards",
                       message=msg,
                       suggestions=[c.suggested_action for c in cards
                                    if c.suggested_action], proposed_operations=[])


register("kg_build_graph", _kg_build)
register("kg_refresh_graph", _kg_refresh)
register("kg_scene_neighborhood", _kg_scene_neighborhood)
register("kg_psyke_neighborhood", _kg_psyke_neighborhood)
register("kg_find_orphans", _kg_find_orphans)
register("kg_find_weak_links", _kg_find_weak_links)
register("kg_find_undefined_terms", _kg_find_undefined_terms)
register("kg_decision_cards", _kg_decision_cards)


# -- Semantic Continuity Engine (Phase 10Q) ---------------------------------

def _ct_run_check(db, context: LogosContext) -> LogosResult:
    action = "ct_run_check"
    try:
        from logosforge.continuity import build_continuity_report, persist_check_run
        report = build_continuity_report(db, context.project_id)
        persist_check_run(db, context.project_id, report)
    except Exception as exc:
        return LogosResult.failure(action, f"Continuity check failed: {exc}")
    lines = [report.summary_line()]
    for i in report.top_issues(8):
        lines.append(f"- [{i.severity}] {i.title}")
    if report.unavailable:
        lines.append("Deferred: " + ", ".join(sorted(set(report.unavailable))))
    return LogosResult(ok=True, action=action, title="Continuity Check",
                       message="\n".join(lines),
                       suggestions=[i.suggested_action for i in report.top_issues(5)
                                    if i.suggested_action], proposed_operations=[])


def _ct_check_scene(db, context: LogosContext) -> LogosResult:
    action = "ct_check_scene"
    if not context.current_scene_id:
        return LogosResult(ok=True, action=action, title="Scene Continuity",
                           message="Open a scene to check its continuity.",
                           suggestions=[], proposed_operations=[])
    try:
        from logosforge.continuity import check_scene_continuity
        report = check_scene_continuity(db, context.project_id,
                                        context.current_scene_id)
    except Exception as exc:
        return LogosResult.failure(action, f"Scene continuity failed: {exc}")
    top = report.top_issues(8)
    if not top:
        msg = "No continuity issues touch this scene."
    else:
        msg = "Scene continuity:\n" + "\n".join(
            f"- [{i.severity}/{i.confidence}] {i.title}" for i in top)
    return LogosResult(ok=True, action=action, title="Scene Continuity",
                       message=msg, suggestions=[], proposed_operations=[])


def _ct_show_issues(db, context: LogosContext) -> LogosResult:
    action = "ct_show_issues"
    try:
        from logosforge.continuity import get_continuity_issues
        issues = get_continuity_issues(db, context.project_id)
    except Exception as exc:
        return LogosResult.failure(action, f"Continuity failed: {exc}")
    if not issues:
        msg = "No open continuity issues."
    else:
        msg = "Open continuity issues:\n" + "\n".join(
            f"- [{i.severity}] ({i.dimension}) {i.title}" for i in issues[:15])
    return LogosResult(ok=True, action=action, title="Continuity Issues",
                       message=msg, suggestions=[], proposed_operations=[])


def _ct_decision_cards(db, context: LogosContext) -> LogosResult:
    action = "ct_decision_cards"
    try:
        from logosforge.continuity import build_continuity_decision_cards
        cards = build_continuity_decision_cards(db, context.project_id)
    except Exception as exc:
        return LogosResult.failure(action, f"Card generation failed: {exc}")
    if not cards:
        msg = "No continuity decisions right now."
    else:
        msg = "Continuity decisions:\n" + "\n".join(
            f"- [{c.severity}] {c.title}" for c in cards)
    return LogosResult(ok=True, action=action, title="Continuity Decision Cards",
                       message=msg, suggestions=[], proposed_operations=[])


register("ct_run_check", _ct_run_check)
register("ct_check_scene", _ct_check_scene)
register("ct_show_issues", _ct_show_issues)
register("ct_decision_cards", _ct_decision_cards)


def _connect_to_psyke(db, context: LogosContext) -> LogosResult:
    """Find PSYKE bible entries related to the selected/nearby text — deterministic.

    Tokenizes the source text, matches each ≥4-char word against the project's
    PSYKE entries (name / aliases / notes, the same haystack the /psyke/search
    route uses), de-dupes by id, and narrates the hits. Never calls the LLM and
    never mutates. Used by inline assistants (e.g. the Whiteboard Logos) so the
    'connect to entity' heuristic lives in the core, not in a frontend/wrapper."""
    action = "connect_to_psyke"
    source = (context.selected_text or context.cursor_text_excerpt or "").strip()
    words = {w.strip(".,;:!?\"'()[]").lower() for w in source.split()}
    words = {w for w in words if len(w) >= 4}
    if not words:
        return LogosResult(
            ok=True, action=action, title="Connect to PSYKE",
            message="Select some text first, then run this action.",
            suggestions=[], proposed_operations=[],
        )
    try:
        seen: dict[int, object] = {}
        for entry in db.get_all_psyke_entries(context.project_id):
            hay = " ".join(
                [entry.name or "", getattr(entry, "aliases", "") or "",
                 entry.notes or ""]
            ).lower()
            if any(w in hay for w in words):
                seen[entry.id] = entry
    except Exception as exc:  # never crash the caller
        return LogosResult.failure(action, f"PSYKE lookup failed: {exc}")

    if not seen:
        return LogosResult(
            ok=True, action=action, title="Connect to PSYKE",
            message="No PSYKE entries matched the selection.",
            suggestions=[], proposed_operations=[],
        )
    lines = [
        f"- {e.name or ''} ({getattr(e, 'entry_type', '') or 'other'})"
        for e in seen.values()
    ]
    return LogosResult(
        ok=True, action=action, title="Connect to PSYKE",
        message="Related PSYKE entries:\n" + "\n".join(lines),
        suggestions=[(e.name or "") for e in seen.values()],
        proposed_operations=[],
    )


register("connect_to_psyke", _connect_to_psyke)
