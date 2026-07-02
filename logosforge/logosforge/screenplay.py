"""Screenplay Mode — canonical element taxonomy and editor/AI helpers (Phase 10A).

This is the single source of truth for screenplay element *types* (so the strings
aren't scattered across the UI), plus small, safe helpers the Manuscript editor,
Assistant context, and exporters reuse.

Scope note (Phase 10A foundation):
    The Manuscript editor visually styles and lets the user pick the six core
    elements via ``writing_formats.SCREENPLAY`` (scene_heading / action /
    character / dialogue / parenthetical / transition). ``shot`` and ``note`` are
    part of the *canonical taxonomy* here for Assistant/Logos/export awareness;
    dedicated editor styling for them — and per-block element *persistence* — are
    deferred to Phase 10B (the scene model currently stores flat text, so block
    element types are in-memory only). Nothing here mutates the DB or calls an LLM.
"""

from __future__ import annotations

from dataclasses import dataclass

# -- Element roles -----------------------------------------------------------
ROLE_STRUCTURAL = "structural"   # organizes the page (scene heading, transition)
ROLE_ACTION = "action"           # descriptive prose / stage of visible action
ROLE_DIALOGUE = "dialogue"       # character cue + spoken lines + parentheticals
ROLE_ANNOTATION = "annotation"   # shots, notes — author/camera asides


@dataclass(frozen=True)
class ScreenplayElement:
    """One canonical screenplay element type."""

    key: str
    label: str
    shortcut_hint: str           # informational only (editor owns real bindings)
    role: str
    uppercase: bool = False      # uppercased by default when applied
    dialogue_related: bool = False
    structural: bool = False


# Canonical, ordered taxonomy. Order is the natural toolbar order.
ELEMENTS: tuple[ScreenplayElement, ...] = (
    ScreenplayElement("scene_heading", "Scene Heading", "Ctrl+1",
                      ROLE_STRUCTURAL, uppercase=True, structural=True),
    ScreenplayElement("action", "Action", "Ctrl+2", ROLE_ACTION),
    ScreenplayElement("character", "Character", "Ctrl+3",
                      ROLE_DIALOGUE, uppercase=True, dialogue_related=True),
    ScreenplayElement("parenthetical", "Parenthetical", "Ctrl+5",
                      ROLE_DIALOGUE, dialogue_related=True),
    ScreenplayElement("dialogue", "Dialogue", "Ctrl+4",
                      ROLE_DIALOGUE, dialogue_related=True),
    ScreenplayElement("transition", "Transition", "Ctrl+6",
                      ROLE_STRUCTURAL, uppercase=True, structural=True),
    # Taxonomy-level (editor styling deferred to Phase 10B):
    ScreenplayElement("shot", "Shot", "", ROLE_ANNOTATION, uppercase=True),
    ScreenplayElement("note", "Note", "", ROLE_ANNOTATION),
)

_BY_KEY: dict[str, ScreenplayElement] = {e.key: e for e in ELEMENTS}
ELEMENT_KEYS: tuple[str, ...] = tuple(e.key for e in ELEMENTS)

# Element keys the Manuscript editor currently styles + offers in its selector
# (the rest are taxonomy-only in Phase 10A — see module docstring).
EDITOR_ELEMENT_KEYS: tuple[str, ...] = (
    "scene_heading", "action", "character", "dialogue", "parenthetical",
    "transition",
)

# Scene-heading prefixes used for lightweight autocomplete (no aggressive
# reformatting — the editor only *offers* these).
SCENE_HEADING_PREFIXES: tuple[str, ...] = (
    "INT.", "EXT.", "INT./EXT.", "EST.", "I/E.",
)


def is_valid_element(key: str | None) -> bool:
    return (key or "") in _BY_KEY


def get_element(key: str | None) -> ScreenplayElement | None:
    return _BY_KEY.get(key or "")


def is_uppercase_element(key: str | None) -> bool:
    e = get_element(key)
    return bool(e and e.uppercase)


def dialogue_elements() -> tuple[str, ...]:
    return tuple(e.key for e in ELEMENTS if e.dialogue_related)


def structural_elements() -> tuple[str, ...]:
    return tuple(e.key for e in ELEMENTS if e.structural)


def normalize_caps(key: str | None, text: str) -> str:
    """Uppercase *text* iff the element is uppercase-by-default.

    Pure helper (no side effects). The editor may call this when applying an
    element; it never changes text for non-uppercase elements.
    """
    if not text:
        return text
    return text.upper() if is_uppercase_element(key) else text


def character_suggestions(db, project_id: int, *, limit: int = 50) -> list[str]:
    """PSYKE character names for the Character-element autocomplete (read-only).

    Returns uppercased names (screenplay character cues are uppercase). Never
    mutates the DB; tolerant of any read failure.
    """
    try:
        entries = db.get_all_psyke_entries(project_id)
    except Exception:
        return []
    names: list[str] = []
    for e in entries:
        if (getattr(e, "entry_type", "") or "").lower() == "character":
            name = (getattr(e, "name", "") or "").strip()
            if name:
                names.append(name.upper())
    # Stable, de-duplicated, capped.
    seen: set[str] = set()
    out: list[str] = []
    for n in names:
        if n not in seen:
            seen.add(n)
            out.append(n)
    return out[:limit]


# -- Assistant context guidance ----------------------------------------------
# Short, deterministic screenplay guidance appended to the Assistant's
# [Project Mode] block (via writing_modes.mode_guidance). No manual dump.
CONTEXT_GUIDANCE: str = (
    "Write cinematically: prefer visible action, scene economy, and subtextual "
    "dialogue with clear scene turns and setup/payoff. Avoid novelistic interior "
    "exposition unless explicitly requested."
)
