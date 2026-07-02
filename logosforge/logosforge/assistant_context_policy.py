"""Controlled Assistant context injection (Phase 8B).

Decides — conservatively and deterministically — whether the Strategy Layer,
Narrative Health, and PSYKE Diagnostics should contribute short, labelled blocks
to the Assistant prompt. It reads settings flags and hard caps so the Assistant
benefits from the intelligence layers without ever receiving a bloated dump.

Pure logic: no Qt, no LLM call, no DB mutation. Each builder is invoked through
the existing read-only gatherers. Returns one combined string (possibly empty)
the caller prepends to its structural context block.
"""

from __future__ import annotations

# Settings keys + conservative defaults.
_KEY_PROJECT_MODE = "include_project_mode_in_assistant_context"
_KEY_SCREENPLAY_DIAG = "include_screenplay_diagnostics_in_assistant_context"
_KEY_SCREENPLAY_TRACK = "include_screenplay_tracking_in_assistant_context"
_KEY_SCREENPLAY_LINKS = "include_screenplay_links_in_assistant_context"
_KEY_SCREENPLAY_EXPORT = "include_screenplay_export_in_assistant_context"
_KEY_PROFESSIONAL_OUTPUT = "include_professional_output_in_assistant_context"
_KEY_PRODUCTION_DRAFT = "include_production_draft_in_assistant_context"
_KEY_REVISION_IMPACT = "include_revision_impact_in_assistant_context"
_KEY_REWRITE_SANDBOX = "include_rewrite_sandbox_in_assistant_context"
_KEY_CONTROLLED_APPLY = "include_controlled_apply_in_assistant_context"
_KEY_PROJECT_INTEL = "include_project_intelligence_in_assistant_context"
_KEY_GUIDED_WORKFLOW = "include_guided_workflow_in_assistant_context"
_KEY_KNOWLEDGE_GRAPH = "include_knowledge_graph_in_assistant_context"
_KEY_CONTINUITY = "include_continuity_in_assistant_context"
_KEY_STRATEGY = "include_strategy_in_assistant_context"
_KEY_HEALTH = "include_health_in_assistant_context"
_KEY_DIAGNOSTICS = "include_diagnostics_in_assistant_context"
_KEY_MAX_HEALTH = "max_health_risks_in_context"
_KEY_MAX_DIAG = "max_diagnostics_in_context"

_DEFAULTS = {
    _KEY_PROJECT_MODE: True,   # on by default — tiny, deterministic, always relevant
    _KEY_SCREENPLAY_DIAG: True,  # screenplay-only; concise top-issues summary
    _KEY_SCREENPLAY_TRACK: True,  # screenplay-only; setup/payoff + subtext summaries
    _KEY_SCREENPLAY_LINKS: True,  # screenplay-only; confirmed + candidate story links
    _KEY_SCREENPLAY_EXPORT: True,  # screenplay-only; export readiness summary
    _KEY_PROFESSIONAL_OUTPUT: False,  # opt-in; DOCX/PDF/FDX readiness
    _KEY_PRODUCTION_DRAFT: True,  # only emits when production mode is active
    _KEY_REVISION_IMPACT: True,  # only emits when a saved impact report exists
    _KEY_REWRITE_SANDBOX: True,  # only emits when an open rewrite session exists
    _KEY_CONTROLLED_APPLY: True,  # only emits when a pending apply preview exists
    _KEY_PROJECT_INTEL: True,  # concise dashboard state (light report)
    _KEY_GUIDED_WORKFLOW: True,  # only emits when a guided workflow is active
    _KEY_KNOWLEDGE_GRAPH: True,  # only emits when a scene is open (cheap, scene-scoped)
    _KEY_CONTINUITY: True,  # only emits when there are open continuity issues
    _KEY_STRATEGY: True,
    _KEY_HEALTH: False,        # off by default — health is expensive/broad
    _KEY_DIAGNOSTICS: True,
    _KEY_MAX_HEALTH: 3,
    _KEY_MAX_DIAG: 5,
}


def _flag(key: str) -> bool:
    try:
        from logosforge.settings import get_manager
        val = get_manager().get(key)
        return _DEFAULTS[key] if val is None else bool(val)
    except Exception:
        return bool(_DEFAULTS.get(key, False))


def _limit(key: str) -> int:
    try:
        from logosforge.settings import get_manager
        val = get_manager().get(key)
        return int(_DEFAULTS[key] if val is None else val)
    except Exception:
        return int(_DEFAULTS.get(key, 3))


def gather_injected_context(
    db,
    project_id: int,
    *,
    section_name: str = "",
    scene_id: int | None = None,
) -> str:
    """Assemble the (possibly empty) injected context for the Assistant prompt.

    Always reads the *current* project/section/scene passed in — never caches —
    so project switching can't leak a previous project's context.
    """
    blocks: list[str] = []

    if _flag(_KEY_PROJECT_MODE):
        blocks.append(_project_mode_block(db, project_id))
        blocks.append(_screenplay_scene_block(db, project_id, scene_id))
    if _flag(_KEY_SCREENPLAY_DIAG):
        blocks.append(_screenplay_diagnostics_block(db, project_id, scene_id))
    if _flag(_KEY_SCREENPLAY_TRACK):
        blocks.append(_screenplay_setup_payoff_block(db, project_id, scene_id))
        blocks.append(_screenplay_subtext_block(db, project_id, scene_id))
    if _flag(_KEY_SCREENPLAY_LINKS):
        blocks.append(_screenplay_links_block(db, project_id, scene_id))
    if _flag(_KEY_SCREENPLAY_EXPORT):
        blocks.append(_screenplay_export_block(db, project_id, scene_id))
    if _flag(_KEY_PROFESSIONAL_OUTPUT):
        blocks.append(_professional_output_block(db, project_id, scene_id))
    if _flag(_KEY_PRODUCTION_DRAFT):
        blocks.append(_production_draft_block(db, project_id))
    if _flag(_KEY_REVISION_IMPACT):
        blocks.append(_revision_impact_block(db, project_id))
    if _flag(_KEY_REWRITE_SANDBOX):
        blocks.append(_rewrite_sandbox_block(db, project_id))
    if _flag(_KEY_CONTROLLED_APPLY):
        blocks.append(_controlled_apply_block(db, project_id))
    if _flag(_KEY_PROJECT_INTEL):
        blocks.append(_project_intelligence_block(db, project_id))
    if _flag(_KEY_GUIDED_WORKFLOW):
        blocks.append(_guided_workflow_block(db, project_id))
    if _flag(_KEY_KNOWLEDGE_GRAPH):
        blocks.append(_knowledge_graph_block(db, project_id, scene_id))
    if _flag(_KEY_CONTINUITY):
        blocks.append(_continuity_block(db, project_id, section_name, scene_id))
    if _flag(_KEY_STRATEGY):
        blocks.append(_strategy_block(db, project_id, section_name))
    if _flag(_KEY_HEALTH):
        blocks.append(_health_block(db, project_id, _limit(_KEY_MAX_HEALTH)))
    if _flag(_KEY_DIAGNOSTICS):
        blocks.append(_diagnostics_block(
            db, project_id, section_name, scene_id, _limit(_KEY_MAX_DIAG),
        ))

    return "\n\n".join(b for b in blocks if b).strip()


# -- Individual blocks (each short, labelled, deterministic) -----------------


def _project_mode_block(db, project_id: int) -> str:
    """Tiny ``[Project Mode]`` block — mode name + primary medium constraints."""
    try:
        from logosforge.writing_modes import (
            get_project_writing_mode_by_id,
            mode_context_block,
        )
        return mode_context_block(get_project_writing_mode_by_id(db, project_id))
    except Exception:
        return ""


def _screenplay_scene_block(db, project_id: int, scene_id: int | None) -> str:
    """Concise ``[Screenplay Scene]`` line — only for screenplay projects with a
    current scene. Lists the character cues actually present in the scene (parsed
    from its text) plus the scene heading. Data-driven, capped, no LLM/DB write.
    """
    if scene_id is None:
        return ""
    try:
        from logosforge.writing_modes import get_project_writing_mode_by_id
        if get_project_writing_mode_by_id(db, project_id) != "screenplay":
            return ""
        scene = db.get_scene_by_id(scene_id)
        if scene is None:
            return ""
        from logosforge.screenplay_blocks import (
            character_cues,
            parse_screenplay_text,
        )
        blocks = parse_screenplay_text(getattr(scene, "content", "") or "")
        cues = character_cues(blocks)[:8]
        lines = ["[Screenplay Scene]"]
        heading = (getattr(scene, "slugline", "") or getattr(scene, "title", "")
                   or "").strip()
        if heading:
            lines.append(f"Heading: {heading.upper()}")
        if cues:
            lines.append("Characters present: " + ", ".join(cues))
        return "\n".join(lines) if len(lines) > 1 else ""
    except Exception:
        return ""


def _screenplay_diagnostics_block(db, project_id: int, scene_id: int | None) -> str:
    """Concise ``[Screenplay Diagnostics]`` block — economy summary + top 3 issues.

    Screenplay projects with a current scene only. Deterministic (rule-based), no
    LLM, no DB write; capped at three issues so the prompt never bloats.
    """
    if scene_id is None:
        return ""
    try:
        from logosforge.writing_modes import get_project_writing_mode_by_id
        if get_project_writing_mode_by_id(db, project_id) != "screenplay":
            return ""
        from logosforge.screenplay_diagnostics import analyze_scene_by_id
        report = analyze_scene_by_id(db, project_id, scene_id)
        if report.block_count == 0:
            return ""
        lines = ["[Screenplay Diagnostics]",
                 f"Scene economy: {report.economy_label or 'unknown'}."]
        top = report.top_issues(3)
        if top:
            lines.append("Top issues:")
            for n, i in enumerate(top, 1):
                lines.append(f"{n}. {i.label}.")
        return "\n".join(lines)
    except Exception:
        return ""


def _is_screenplay(db, project_id: int) -> bool:
    try:
        from logosforge.writing_modes import get_project_writing_mode_by_id
        return get_project_writing_mode_by_id(db, project_id) == "screenplay"
    except Exception:
        return False


def _screenplay_setup_payoff_block(db, project_id: int, scene_id: int | None) -> str:
    """Capped ``[Screenplay Setup/Payoff]`` — 3 unresolved / 3 payoffs / 3 motifs."""
    if scene_id is None or not _is_screenplay(db, project_id):
        return ""
    try:
        from logosforge.screenplay_setup_payoff import analyze_setup_payoff
        report = analyze_setup_payoff(db, project_id)
        if not (report.unresolved_setups or report.possible_payoffs
                or report.recurring_motifs):
            return ""
        lines = ["[Screenplay Setup/Payoff]"]
        for label, items in (
            ("Unresolved setups", report.unresolved_setups),
            ("Possible payoffs", report.possible_payoffs),
            ("Recurring motifs", report.recurring_motifs),
        ):
            for c in items[:3]:
                lines.append(f"- {label[:-1] if label.endswith('s') else label}: {c.label}")
        return "\n".join(lines)
    except Exception:
        return ""


def _screenplay_subtext_block(db, project_id: int, scene_id: int | None) -> str:
    """Capped ``[Screenplay Subtext]`` — status + top 3 signals for the scene."""
    if scene_id is None or not _is_screenplay(db, project_id):
        return ""
    try:
        from logosforge.screenplay_subtext import analyze_subtext_by_id
        report = analyze_subtext_by_id(db, project_id, scene_id)
        if not report.signals:
            return ""
        lines = ["[Screenplay Subtext]", report.summary]
        for s in report.top_signals(3):
            lines.append(f"- {s.signal_type}: {s.evidence}")
        return "\n".join(lines)
    except Exception:
        return ""


def _screenplay_links_block(db, project_id: int, scene_id: int | None) -> str:
    """Capped ``[Screenplay Story Links]`` — confirmed + candidate links."""
    if scene_id is None or not _is_screenplay(db, project_id):
        return ""
    try:
        from logosforge.screenplay_graph import build_screenplay_graph
        graph = build_screenplay_graph(db, project_id)
        if not graph.edges:
            return ""
        confirmed = [e for e in graph.edges if e.status in ("confirmed", "resolved")]
        setup_cand = [e for e in graph.edges
                      if e.status == "candidate" and e.edge_type == "setup_to_payoff"]
        motif = [e for e in graph.edges if e.edge_type == "motif_recurrence"]
        if not (confirmed or setup_cand or motif):
            return ""
        lines = ["[Screenplay Story Links]"]
        for label, items in (("Confirmed", confirmed),
                             ("Candidate setup/payoff", setup_cand),
                             ("Motif", motif)):
            for e in items[:3]:
                lines.append(f"- {label}: {e.label}")
        return "\n".join(lines)
    except Exception:
        return ""


def _screenplay_export_block(db, project_id: int, scene_id: int | None) -> str:
    """Export readiness for the active target.

    Phase 10G — when the target is ``fountain`` (the canonical default) this emits
    a Fountain-specific ``[Fountain Export Readiness]`` block; otherwise it emits
    the generic ``[Screenplay Export Readiness]`` block. Exactly one shows.
    """
    if scene_id is None or not _is_screenplay(db, project_id):
        return ""
    try:
        from logosforge.screenplay_render import get_export_prefs, get_title_page
        prefs = get_export_prefs(db, project_id)
        if prefs.get("export_target", "fountain") == "fountain":
            return _fountain_export_block(db, project_id)
        from logosforge.screenplay_export_validation import (
            validate_screenplay_export,
        )
        rep = validate_screenplay_export(
            db, project_id, target_format=prefs.get("export_target", "fountain"),
            prefs=prefs)
        title = (get_title_page(db, project_id).get("title") or "").strip()
        lines = ["[Screenplay Export Readiness]",
                 f"Target: {rep.target_format}",
                 f"Title page: {'set' if title else 'missing'}"]
        if rep.blocking_errors:
            lines.append("Blocking: " + "; ".join(rep.blocking_errors[:3]))
        if rep.warnings:
            lines.append("Warnings: " + "; ".join(rep.warnings[:3]))
        if len(lines) == 3 and rep.is_export_safe:
            lines.append("No blocking issues.")
        return "\n".join(lines)
    except Exception:
        return ""


def _fountain_export_block(db, project_id: int) -> str:
    """Capped ``[Fountain Export Readiness]`` — target .fountain + top issues."""
    try:
        from logosforge.export import export_screenplay_fountain_result
        from logosforge.screenplay_fountain import validate_fountain_export
        from logosforge.screenplay_render import get_title_page, get_export_prefs
        res = export_screenplay_fountain_result(db, project_id)
        rep = validate_fountain_export(res.text)
        title = (get_title_page(db, project_id).get("title") or "").strip()
        notes_on = bool(get_export_prefs(db, project_id).get("show_notes_in_export"))
        lines = ["[Fountain Export Readiness]",
                 "Export target: .fountain",
                 f"Title page: {'set' if title else 'missing'}",
                 f"Notes: {'included' if notes_on else 'excluded'}"]
        if rep.blocking_errors:
            lines.append("Blocking: " + "; ".join(rep.blocking_errors[:3]))
        if rep.warnings:
            lines.append("Warnings: " + "; ".join(rep.warnings[:3]))
        return "\n".join(lines)
    except Exception:
        return ""


def _professional_output_block(db, project_id: int, scene_id: int | None) -> str:
    """Capped ``[Professional Output Readiness]`` — formats + compatibility + issues."""
    if scene_id is None or not _is_screenplay(db, project_id):
        return ""
    try:
        from logosforge.screenplay_output_validation import (
            validate_professional_output,
        )
        from logosforge.screenplay_render import get_title_page
        rep = validate_professional_output(db, project_id, target_format="docx")
        title = (get_title_page(db, project_id).get("title") or "").strip()
        lines = ["[Professional Output Readiness]",
                 f"Available formats: {', '.join(rep.available_formats)}",
                 f"Target: docx ({rep.compatibility_level})",
                 f"Title page: {'set' if title else 'missing'}"]
        if rep.blocking_errors:
            lines.append("Blocking: " + "; ".join(rep.blocking_errors[:3]))
        if rep.warnings:
            lines.append("Warnings: " + "; ".join(rep.warnings[:3]))
        return "\n".join(lines)
    except Exception:
        return ""


def _production_draft_block(db, project_id: int) -> str:
    """Capped ``[Production Draft Status]`` — only when production mode is active."""
    if not _is_screenplay(db, project_id):
        return ""
    try:
        from logosforge.screenplay_production import production_status
        st = production_status(db, project_id)
        if not st.get("active"):
            return ""
        lines = ["[Production Draft Status]",
                 f"Mode: production — {st.get('draft_label', '')}".rstrip(" —"),
                 f"Scene numbering: {'on' if st.get('scene_numbering_enabled') else 'off'} "
                 f"({st.get('numbered_scenes', 0)} numbered, "
                 f"{st.get('omitted_scenes', 0)} omitted)",
                 f"Revision sets: {st.get('revision_sets', 0)}"
                 + (f" (latest: {st['active_revision_set']})"
                    if st.get('active_revision_set') else ""),
                 f"Page locking: {st.get('page_locking_status', 'disabled')}"]
        if st.get("warnings"):
            lines.append("Warnings: " + "; ".join(st["warnings"][:3]))
        return "\n".join(lines)
    except Exception:
        return ""


def _revision_impact_block(db, project_id: int) -> str:
    """Capped ``[Revision Impact]`` from the last saved report (cheap read).

    Never computes a fresh project-wide impact map during context assembly — it
    only summarizes the most recent persisted report, so it's bounded and fast.
    """
    if not _is_screenplay(db, project_id):
        return ""
    try:
        report = db.get_latest_revision_impact_report(project_id)
        if report is None:
            return ""
        items = db.get_revision_impact_items(report.id)
        scenes = [i for i in items if i.target_type == "scene"][:3]
        psyke = [i for i in items if i.target_type == "psyke_entry"][:3]
        sp = [i for i in items if i.target_type == "setup_payoff"][:3]
        lines = ["[Revision Impact]",
                 f"Scene {report.scene_id}: {report.impact_level} "
                 f"({report.confidence})"]
        if scenes:
            lines.append("Impacted scenes: " + ", ".join(i.label for i in scenes))
        if psyke:
            lines.append("PSYKE: " + ", ".join(i.label for i in psyke))
        if sp:
            lines.append("Setup/payoff risks: " + ", ".join(i.label for i in sp))
        return "\n".join(lines)
    except Exception:
        return ""


def _rewrite_sandbox_block(db, project_id: int) -> str:
    """Capped ``[Rewrite Sandbox]`` — only when an open rewrite session exists.

    Writing-mode-aware (not screenplay-only). Cheap read of session status; never
    dumps variant text; no LLM/DB during assembly.
    """
    try:
        from logosforge.rewrite_sandbox.engine import session_status
        st = session_status(db, project_id)
        if not st.get("active"):
            return ""
        lines = ["[Rewrite Sandbox]",
                 f"Source: {st['source_type']} ({st['writing_mode']})",
                 f"Variants: {st['variant_count']}"
                 + (f"; preferred: {st['preferred']}" if st.get("preferred") else "")]
        if st.get("stale"):
            lines.append("Stale source: variants generated before a source edit.")
        if st.get("psyke_terms_removed"):
            lines.append(f"PSYKE references removed across variants: "
                         f"{st['psyke_terms_removed']}")
        if st.get("warnings"):
            lines.append("Warnings: " + "; ".join(st["warnings"][:3]))
        return "\n".join(lines)
    except Exception:
        return ""


def _controlled_apply_block(db, project_id: int) -> str:
    """Capped ``[Controlled Apply]`` — only when a pending apply preview exists.

    Summarizes the latest draft/previewed operation + its conflicts. Cheap read;
    never dumps proposed text; no LLM/DB during assembly; no cross-project leak.
    """
    import json
    try:
        ops = [o for o in db.get_apply_operations(project_id)
               if o.status in ("draft", "previewed")]
        if not ops:
            return ""
        op = ops[-1]
        try:
            conflicts = json.loads(op.conflict_json or "[]")
        except Exception:
            conflicts = []
        blocking = [c for c in conflicts if c.get("severity") in ("blocking", "error")]
        warns = [c for c in conflicts if c.get("severity") == "warning"]
        lines = ["[Controlled Apply]",
                 f"Pending: {op.source_type} → {op.target_type} ({op.apply_mode})",
                 f"Apply blocked: {'yes' if blocking else 'no'}"]
        if blocking:
            lines.append("Blocking: " + "; ".join(c["conflict_type"] for c in blocking[:3]))
        if warns:
            lines.append("Warnings: " + "; ".join(c["message"] for c in warns[:3]))
        return "\n".join(lines)
    except Exception:
        return ""


def _project_intelligence_block(db, project_id: int) -> str:
    """Capped ``[Project Intelligence]`` — light dashboard state + top decisions.

    Uses the *light* report (skips expensive Health/export passes) so it stays
    cheap during context assembly. No full dashboard dump; no LLM/DB; no leak.
    """
    try:
        from logosforge.project_intelligence import build_project_intelligence_report
        rep = build_project_intelligence_report(db, project_id, light=True)
        ov = rep.overview
        lines = ["[Project Intelligence]",
                 f"Mode: {ov.get('writing_mode', 'novel')}; "
                 f"{ov.get('total_scenes', 0)} scenes, "
                 f"{ov.get('total_psyke_entries', 0)} PSYKE"]
        top = rep.top_cards(3)
        if top:
            lines.append("Top decisions:")
            for c in top:
                lines.append(f"- [{c.severity}] {c.title}")
        return "\n".join(lines)
    except Exception:
        return ""


def _guided_workflow_block(db, project_id: int) -> str:
    """Capped ``[Guided Workflow]`` block — only when a workflow is active.

    Names the active workflow(s), progress and current step so the Assistant can
    help with *this* step. Deterministic; no LLM/DB write; capped; no cross-
    project leak. The Assistant must never mark steps done — that's the user's.
    """
    try:
        from logosforge.guided_workflows import get_active_workflows
        views = get_active_workflows(db, project_id)
        if not views:
            return ""
        lines = ["[Guided Workflow]"]
        for v in views[:2]:
            lines.append(v.progress_line())
            cur = v.current_step
            if cur is not None:
                lines.append(f"Current step: {cur.title}"
                             + (f" (open {cur.section_name})" if cur.section_name else ""))
        lines.append("Help with the current step; never mark steps done — "
                     "that is the user's decision.")
        return "\n".join(lines)
    except Exception:
        return ""


def _knowledge_graph_block(db, project_id: int, scene_id: int | None) -> str:
    """Capped ``[Narrative Knowledge Graph]`` — current scene's neighborhood.

    Only emits when a scene is open (scene-scoped keeps it cheap). Concise: top
    related PSYKE, connected scenes, risks. Deterministic; no LLM/DB write; no
    cross-project leak; no full graph dump.
    """
    if scene_id is None:
        return ""
    try:
        from logosforge.knowledge_graph import get_graph_summary_for_assistant
        return get_graph_summary_for_assistant(
            db, project_id, scene_id=scene_id)
    except Exception:
        return ""


def _continuity_block(db, project_id: int, section_name: str,
                      scene_id: int | None) -> str:
    """Capped ``[Continuity]`` block — top open issues (scene-scoped if a scene
    is open). Only emits when issues exist. Deterministic; no LLM/DB write; no
    cross-project leak; advisory (never auto-fix/dismiss)."""
    try:
        from logosforge.continuity import get_continuity_summary_for_assistant
        return get_continuity_summary_for_assistant(
            db, project_id, section_name=section_name, scene_id=scene_id)
    except Exception:
        return ""


def _strategy_block(db, project_id: int, section_name: str) -> str:
    try:
        from logosforge.logos.strategy.strategy_context import (
            gather_strategy_context,
        )
        return gather_strategy_context(db, project_id, section_name)
    except Exception:
        return ""


def _health_block(db, project_id: int, max_risks: int) -> str:
    try:
        from logosforge.logos.health import HealthEngine, top_risks_text
        report = HealthEngine(db, project_id).generate_report()
        return top_risks_text(report, max_risks=max(0, max_risks))
    except Exception:
        return ""


def _diagnostics_block(
    db, project_id: int, section_name: str, scene_id: int | None, max_items: int,
) -> str:
    """Current-target diagnostics only (scene/entry), capped — never a full dump."""
    if max_items <= 0:
        return ""
    try:
        from logosforge.logos.diagnostics import DiagnosticsEngine
        engine = DiagnosticsEngine(db, project_id)
        diags = engine.scan_project()
    except Exception:
        return ""
    if not diags:
        return ""

    # Prefer diagnostics tied to the current scene, else the section's, else the
    # most severe project-wide ones.
    def _relevant(d) -> bool:
        if scene_id is not None:
            if str(scene_id) == str(d.target_id):
                return True
            if scene_id in (d.related_scene_ids or []):
                return True
        if section_name and d.section_name == section_name:
            return True
        return False

    focused = [d for d in diags if _relevant(d)]
    pool = focused or diags  # fall back to top project-wide findings
    pool = sorted(pool, key=lambda d: (d.severity_rank, d.confidence), reverse=True)
    chosen = pool[:max_items]
    if not chosen:
        return ""

    lines = ["[Diagnostics]"]
    for d in chosen:
        lines.append(f"- {d.title} ({d.severity}) — {d.evidence}")
    return "\n".join(lines)
