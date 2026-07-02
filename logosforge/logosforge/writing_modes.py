"""Project Writing Mode — the unified, project-level source of truth (Phase 9).

A project declares *what kind of work it is* (Novel / Screenplay / Graphic Novel
/ Stage Script / Series) and every section adapts to that declaration. This
module is the single API every feature should use instead of scattering mode
strings.

Design note — no duplicate column:
    The project's writing mode is **the existing ``Project.narrative_engine``
    field**, not a new column. Its allowed values already match the five modes
    exactly, it already migrates safely (``db/database.py::_migrate`` backfills
    legacy ``format_mode`` → engine, defaulting to ``novel``), and
    ``project_compat`` already validates it. Adding a second ``writing_mode``
    column would duplicate that field and risk the two diverging, so this module
    is a thin facade over ``narrative_engine`` plus the one piece that did not
    exist yet: per-mode **display structural vocabulary** and a short
    **medium-constraints** summary for the Assistant.

Pure data/logic: no Qt, no LLM, no DB mutation (except the explicit
``set_project_writing_mode`` helper, which writes the canonical field).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from logosforge.project_compat import (
    ENGINE_GRAPHIC_NOVEL,
    ENGINE_NOVEL,
    ENGINE_SCREENPLAY,
    ENGINE_SERIES,
    ENGINE_STAGE_SCRIPT,
    ENGINE_LABELS,
    FORMAT_GRAPHIC_NOVEL,
    FORMAT_PROSE,
    FORMAT_SCREENPLAY,
    FORMAT_STAGE_SCRIPT,
    get_project_narrative_engine,
)

if TYPE_CHECKING:
    from logosforge.models.models import Project

# -- Mode identity -----------------------------------------------------------
# Mode names are the same canonical strings as the narrative engine, so the
# Strategy Layer / Logos / engines all keep working unchanged.
NOVEL = ENGINE_NOVEL
SCREENPLAY = ENGINE_SCREENPLAY
GRAPHIC_NOVEL = ENGINE_GRAPHIC_NOVEL
STAGE_SCRIPT = ENGINE_STAGE_SCRIPT
SERIES = ENGINE_SERIES

DEFAULT_MODE = NOVEL

ALL_MODES: tuple[str, ...] = (
    NOVEL, SCREENPLAY, GRAPHIC_NOVEL, STAGE_SCRIPT, SERIES,
)

# Human-readable names (re-exported from the engine labels — one source).
MODE_LABELS: dict[str, str] = dict(ENGINE_LABELS)


def is_valid_mode(mode: str | None) -> bool:
    """True if *mode* is one of the five supported writing modes."""
    return (mode or "").strip() in ALL_MODES


def normalize_mode(mode: str | None) -> str:
    """Return a valid mode, falling back safely to ``novel``."""
    candidate = (mode or "").strip()
    return candidate if candidate in ALL_MODES else DEFAULT_MODE


def mode_label(mode: str | None) -> str:
    """Display name for a mode (``novel`` fallback)."""
    return MODE_LABELS.get(normalize_mode(mode), MODE_LABELS[DEFAULT_MODE])


# -- Structural vocabulary (Dashboard / section display layer) ---------------
# A curated, friendly display vocabulary per mode. This is the *presentation*
# layer; the generation-level structural units live on each NarrativeEngine
# (``narrative_engines`` / ``engine_structural_units``) and are intentionally
# finer-grained. These match the Phase 9 spec's Dashboard examples.
_STRUCTURAL_UNITS: dict[str, tuple[str, ...]] = {
    NOVEL: ("Acts", "Chapters", "Scenes"),
    SCREENPLAY: ("Acts", "Sequences", "Scenes"),
    GRAPHIC_NOVEL: ("Chapters", "Pages", "Panels"),
    STAGE_SCRIPT: ("Acts", "Scenes", "Beats", "Stage Directions"),
    SERIES: ("Seasons", "Episodes", "A/B/C Plots", "Scenes"),
}


def structural_units(mode: str | None) -> tuple[str, ...]:
    """Ordered display labels for a mode's structural hierarchy."""
    return _STRUCTURAL_UNITS[normalize_mode(mode)]


def structural_vocabulary(mode: str | None) -> str:
    """One-line vocabulary string, e.g. ``"Acts / Chapters / Scenes"``."""
    return " / ".join(structural_units(mode))


# -- Medium constraints (Assistant [Project Mode] block) ---------------------
# Short, deterministic phrase naming the craft priorities the medium imposes.
# Kept terse on purpose — the Assistant should never receive a mode manual.
_MEDIUM_CONSTRAINTS: dict[str, str] = {
    NOVEL: ("prose voice, interiority, chapter rhythm, character arc, "
            "thematic recurrence"),
    SCREENPLAY: ("visual action, scene economy, dialogue subtext, "
                 "setup/payoff, cinematic pacing"),
    GRAPHIC_NOVEL: ("page turns, panel rhythm, visual motif, image/text "
                    "balance, dialogue compression"),
    STAGE_SCRIPT: ("playable conflict, blocking, entrances/exits, "
                   "performable dialogue, scene economy"),
    SERIES: ("episode engine, A/B/C plots, season arc, recurring payoff, "
             "long-term continuity"),
}


def medium_constraints(mode: str | None) -> str:
    """Compact primary-constraints phrase for a mode."""
    return _MEDIUM_CONSTRAINTS[normalize_mode(mode)]


# -- Default writing format (block grammar) per mode -------------------------
# The format a new project of this mode defaults to. Series suggests the
# screenplay format. Values are the canonical project_compat FORMAT_* ids.
_DEFAULT_WRITING_FORMATS: dict[str, str] = {
    NOVEL: FORMAT_PROSE,             # "novel"
    SCREENPLAY: FORMAT_SCREENPLAY,
    GRAPHIC_NOVEL: FORMAT_GRAPHIC_NOVEL,
    STAGE_SCRIPT: FORMAT_STAGE_SCRIPT,
    SERIES: FORMAT_SCREENPLAY,
}


def default_writing_format(mode: str | None) -> str:
    """The suggested default writing format (block grammar) for a mode."""
    return _DEFAULT_WRITING_FORMATS[normalize_mode(mode)]


def mode_guidance(mode: str | None) -> str:
    """Optional extra, mode-specific guidance line for the Assistant block.

    Empty for most modes. Screenplay (Phase 10A) adds short cinematic guidance,
    sourced from the canonical ``screenplay`` module (lazy import to avoid any
    cycle). Deterministic; no LLM/DB.
    """
    if normalize_mode(mode) == SCREENPLAY:
        try:
            from logosforge.screenplay import CONTEXT_GUIDANCE
            return CONTEXT_GUIDANCE
        except Exception:
            return ""
    return ""


def mode_context_block(mode: str | None) -> str:
    """The short, labelled ``[Project Mode]`` block for Assistant context.

    Deterministic and tiny — mode name, the medium's primary constraints, and an
    optional one-line mode-specific guidance (e.g. screenplay).
    """
    m = normalize_mode(mode)
    lines = [
        "[Project Mode]",
        f"Mode: {mode_label(m)}",
        f"Primary constraints: {medium_constraints(m)}.",
    ]
    guidance = mode_guidance(m)
    if guidance:
        lines.append(guidance)
    return "\n".join(lines)


# -- Primary writing unit ----------------------------------------------------


def primary_unit_label(mode: str | None) -> str:
    """The primary writing-unit noun for a mode: 'Chapter' in Novel, else 'Scene'."""
    return "Chapter" if normalize_mode(mode) == NOVEL else "Scene"


# -- Project-level primary-unit adapter (single source of truth for the UI) ---
# Small, testable helpers so views never branch on writing_mode themselves.


def current_primary_unit_type(project: "Project | None") -> str:
    """'chapter' for Novel projects, 'scene' otherwise (lowercase type key)."""
    return "chapter" if get_project_writing_mode(project) == NOVEL else "scene"


def current_primary_unit_label(project: "Project | None") -> str:
    """'Chapter' for Novel projects, 'Scene' otherwise (display noun)."""
    return primary_unit_label(get_project_writing_mode(project))


def current_add_button_label(project: "Project | None") -> str:
    """'+ Chapter' for Novel projects, '+ Scene' otherwise."""
    return "+ " + current_primary_unit_label(project)


# -- Project accessors -------------------------------------------------------


def get_project_writing_mode(project: "Project | None") -> str:
    """Return the project's writing mode (the canonical ``narrative_engine``).

    Always a valid mode — unknown / missing values fall back to ``novel`` via
    ``project_compat``.
    """
    return normalize_mode(get_project_narrative_engine(project))


def get_project_writing_mode_by_id(db, project_id: int) -> str:
    """Convenience: resolve a project id straight to its writing mode."""
    try:
        return get_project_writing_mode(db.get_project_by_id(project_id))
    except Exception:
        return DEFAULT_MODE


def set_project_writing_mode(db, project_id: int, mode: str) -> str:
    """Persist *mode* as the project's writing mode (canonical field).

    Normalizes invalid input to ``novel`` and writes via the existing
    ``update_project_narrative_engine`` path so all downstream behavior (manuscript
    format sync, strategy routing, etc.) stays consistent. Returns the stored mode.
    """
    normalized = normalize_mode(mode)
    db.update_project_narrative_engine(project_id, normalized)
    return normalized


# -- Writing-mode lock (Alpha safety) ----------------------------------------
# Mode is chosen at project creation. Once a project has meaningful content, its
# writing mode is LOCKED: changing it would make the Manuscript read one mode's
# body as another's (e.g. prose parsed as screenplay blocks) — a corruption risk.
# Automatic conversion is intentionally NOT done; a "Convert Project Mode" wizard
# is a deferred future workflow. This is the single source of truth every UI mode
# selector must consult.

MODE_LOCK_MESSAGE = (
    "Writing mode is locked because this project already contains content. "
    "Changing mode could misread or corrupt Manuscript data. Create a new "
    "project or use a future conversion workflow."
)

# Settings keys that hold user/AI planning data — any non-empty store is content.
_PLANNING_SETTINGS_KEYS: tuple[str, ...] = (
    "act_summaries", "chapter_summaries",
    "screenplay_beat_plans",
    "gn_page_breakdowns", "gn_panel_plans",
    "stage_beat_plans", "stage_blocking_plans",
    "series_season_plans", "series_episode_plans",
)

_DEFAULT_SCENE_TITLES = {"", "untitled", "untitled scene", "untitled chapter"}
_SCENE_CONTENT_FIELDS = ("summary", "synopsis", "goal", "conflict", "outcome", "beat")


def project_has_meaningful_content(db, project_id: int) -> bool:
    """True if the project has any content beyond an empty starter scaffold.

    Meaningful content (any one is enough): a scene with body text, a planning
    summary/field, or a user title; more than one scene or user-created
    Act/Chapter labels; stored beat/plan/outline data; Timeline events; Notes; or
    PSYKE entries. Read-only and defensive — it never raises and never mutates.
    """
    # -- Scenes: body / planning fields / user title / user structure --
    try:
        scenes = list(db.get_all_scenes(project_id) or [])
    except Exception:
        scenes = []
    if len(scenes) > 1:
        return True
    try:
        from logosforge import story_structure as ss
        default_acts = {"", ss.DEFAULT_ACT, ss.UNASSIGNED_ACT}
        default_chapters = {"", ss.DEFAULT_CHAPTER, ss.UNASSIGNED_CHAPTER}
    except Exception:
        default_acts = {"", "Act 1", "Unassigned"}
        default_chapters = {"", "Chapter 1", "Unassigned"}
    for s in scenes:
        if (getattr(s, "content", "") or "").strip():
            return True
        if any((getattr(s, f, "") or "").strip() for f in _SCENE_CONTENT_FIELDS):
            return True
        title = (getattr(s, "title", "") or "").strip().lower()
        if title and title not in _DEFAULT_SCENE_TITLES:
            return True
        if (getattr(s, "act", "") or "").strip() not in default_acts:
            return True
        if (getattr(s, "chapter", "") or "").strip() not in default_chapters:
            return True
    # -- Stored planning / outline data (settings-backed) --
    try:
        settings = db.get_project_settings(project_id) or {}
    except Exception:
        settings = {}
    for key in _PLANNING_SETTINGS_KEYS:
        store = settings.get(key)
        if isinstance(store, dict) and any(store.values()):
            return True
    # -- Timeline events / Notes / PSYKE entries / Series structure --
    for accessor in ("get_timeline_event_ids", "get_all_notes",
                     "get_all_psyke_entries", "get_seasons", "get_episodes"):
        try:
            fn = getattr(db, accessor, None)
            if fn is not None and fn(project_id):
                return True
        except Exception:
            continue
    return False


def can_change_writing_mode(db, project_id: int) -> bool:
    """True only when it is SAFE to change a project's writing mode — i.e. the
    project is still an empty scaffold. Once meaningful content exists the mode is
    locked. On any doubt this returns ``False`` (the unsafe direction is *allowing*
    a change). Single source of truth for every UI mode selector."""
    try:
        return not project_has_meaningful_content(db, project_id)
    except Exception:
        return False


def change_writing_mode(db, project_id: int, mode: str) -> tuple[bool, str]:
    """Guarded mode change. Returns ``(changed, mode)``.

    * Same mode → ``(False, current)`` (no-op, no write).
    * Locked project (meaningful content) → ``(False, current)`` and **writes
      nothing** — the lock is never bypassed.
    * Unlocked project with a different valid target → persists and returns
      ``(True, target)``.

    This is the only guarded path; the low-level :func:`set_project_writing_mode`
    remains the unguarded persistence primitive used at creation time.
    """
    current = get_project_writing_mode_by_id(db, project_id)
    target = normalize_mode(mode)
    if target == current:
        return (False, current)
    if not can_change_writing_mode(db, project_id):
        return (False, current)
    set_project_writing_mode(db, project_id, target)
    return (True, target)
