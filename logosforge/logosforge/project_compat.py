"""Central accessors for a project's narrative engine and writing format.

Projects historically stored only a single `format_mode` string. New
projects carry two distinct fields: `narrative_engine` (which reasoning
behavior to use) and `default_writing_format` (which block grammar the
manuscript editor uses by default).

This module exposes the canonical mapping between the two systems and
the helpers every section should use instead of reading `format_mode`
directly.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from logosforge.models.models import Project


# Canonical engine names. The registry only ships novel + screenplay
# engines today; the other names map onto fallbacks (see
# narrative_engines/registry.py::get_engine).
ENGINE_NOVEL = "novel"
ENGINE_SCREENPLAY = "screenplay"
ENGINE_STAGE_SCRIPT = "stage_script"
ENGINE_GRAPHIC_NOVEL = "graphic_novel"
ENGINE_SERIES = "series"

ALL_ENGINES: tuple[str, ...] = (
    ENGINE_NOVEL, ENGINE_SCREENPLAY, ENGINE_STAGE_SCRIPT,
    ENGINE_GRAPHIC_NOVEL, ENGINE_SERIES,
)

ENGINE_LABELS: dict[str, str] = {
    ENGINE_NOVEL: "Novel",
    ENGINE_SCREENPLAY: "Screenplay",
    ENGINE_STAGE_SCRIPT: "Stage Script",
    ENGINE_GRAPHIC_NOVEL: "Graphic Novel",
    ENGINE_SERIES: "Series",
}

# Canonical writing format names — these match keys in
# logosforge.writing_formats.ALL_FORMATS plus extra abstract formats.
FORMAT_PROSE = "novel"
FORMAT_SCREENPLAY = "screenplay"
FORMAT_STAGE_SCRIPT = "stage_script"
FORMAT_GRAPHIC_NOVEL = "graphic_novel"
FORMAT_TREATMENT = "treatment"
FORMAT_BEAT_SHEET = "beat_sheet"
FORMAT_OUTLINE = "outline"
FORMAT_SERIES = "series"

ALL_FORMATS: tuple[str, ...] = (
    FORMAT_PROSE, FORMAT_SCREENPLAY, FORMAT_STAGE_SCRIPT,
    FORMAT_GRAPHIC_NOVEL, FORMAT_TREATMENT, FORMAT_BEAT_SHEET,
    FORMAT_OUTLINE, FORMAT_SERIES,
)

FORMAT_LABELS: dict[str, str] = {
    FORMAT_PROSE: "Prose",
    FORMAT_SCREENPLAY: "Screenplay",
    FORMAT_STAGE_SCRIPT: "Stage Script",
    FORMAT_GRAPHIC_NOVEL: "Graphic Novel Script",
    FORMAT_TREATMENT: "Treatment",
    FORMAT_BEAT_SHEET: "Beat Sheet",
    FORMAT_OUTLINE: "Outline",
    FORMAT_SERIES: "Series",
}

# Default writing format suggested when the engine changes.
DEFAULT_FORMAT_FOR_ENGINE: dict[str, str] = {
    ENGINE_NOVEL: FORMAT_PROSE,
    ENGINE_SCREENPLAY: FORMAT_SCREENPLAY,
    ENGINE_STAGE_SCRIPT: FORMAT_STAGE_SCRIPT,
    ENGINE_GRAPHIC_NOVEL: FORMAT_GRAPHIC_NOVEL,
    ENGINE_SERIES: FORMAT_SCREENPLAY,
}

# Legacy `format_mode` strings → (engine, default_format) used when migrating
# older project rows that have no narrative_engine / default_writing_format.
_LEGACY_FORMAT_MAP: dict[str, tuple[str, str]] = {
    "novel": (ENGINE_NOVEL, FORMAT_PROSE),
    "book": (ENGINE_NOVEL, FORMAT_PROSE),
    "prose": (ENGINE_NOVEL, FORMAT_PROSE),
    "screenplay": (ENGINE_SCREENPLAY, FORMAT_SCREENPLAY),
    "stage_script": (ENGINE_STAGE_SCRIPT, FORMAT_STAGE_SCRIPT),
    "graphic_novel": (ENGINE_GRAPHIC_NOVEL, FORMAT_GRAPHIC_NOVEL),
    "series": (ENGINE_SERIES, FORMAT_SCREENPLAY),
}


def resolve_legacy_format(format_mode: str) -> tuple[str, str]:
    """Map a legacy `format_mode` string to (engine, default_format)."""
    return _LEGACY_FORMAT_MAP.get(
        (format_mode or "").lower().strip(),
        (ENGINE_NOVEL, FORMAT_PROSE),
    )


def get_project_narrative_engine(project: "Project | None") -> str:
    """Return the narrative-engine name for a project.

    Reads the new `narrative_engine` field if populated; otherwise falls
    back to the legacy `format_mode` string. Always returns a valid
    engine name from ALL_ENGINES (defaults to ENGINE_NOVEL).
    """
    if project is None:
        return ENGINE_NOVEL
    engine = (getattr(project, "narrative_engine", "") or "").strip()
    if engine in ALL_ENGINES:
        return engine
    legacy = getattr(project, "format_mode", "") or ""
    return resolve_legacy_format(legacy)[0]


def get_project_writing_format(project: "Project | None") -> str:
    """Return the default writing format for a project.

    Reads the new `default_writing_format` field if populated; otherwise
    falls back to the legacy `format_mode` mapping.
    """
    if project is None:
        return FORMAT_PROSE
    fmt = (getattr(project, "default_writing_format", "") or "").strip()
    if fmt in ALL_FORMATS:
        return fmt
    legacy = getattr(project, "format_mode", "") or ""
    return resolve_legacy_format(legacy)[1]


def default_format_for_engine(engine: str) -> str:
    """Return the writing format we suggest when the engine changes."""
    return DEFAULT_FORMAT_FOR_ENGINE.get(engine, FORMAT_PROSE)


def is_screenplay_project(project: "Project | None") -> bool:
    """True if the project's engine is screenplay-flavored.

    Convenience for the many UI branches that ask
    `format_mode == "screenplay"`. Use the engine accessor when finer
    discrimination is needed.
    """
    return get_project_narrative_engine(project) == ENGINE_SCREENPLAY
