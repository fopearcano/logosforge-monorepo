"""Central registry mapping mode names → NarrativeEngine instances."""

from __future__ import annotations

from typing import TYPE_CHECKING

from logosforge.narrative_engines.base import NarrativeEngine
from logosforge.narrative_engines.novel import NOVEL_ENGINE
from logosforge.narrative_engines.screenplay import SCREENPLAY_ENGINE
from logosforge.narrative_engines.graphic_novel import GRAPHIC_NOVEL_ENGINE
from logosforge.narrative_engines.stage_script import STAGE_SCRIPT_ENGINE
from logosforge.narrative_engines.series import SERIES_ENGINE

if TYPE_CHECKING:
    from logosforge.models.models import Project


ALL_ENGINES: dict[str, NarrativeEngine] = {
    NOVEL_ENGINE.name: NOVEL_ENGINE,
    SCREENPLAY_ENGINE.name: SCREENPLAY_ENGINE,
    GRAPHIC_NOVEL_ENGINE.name: GRAPHIC_NOVEL_ENGINE,
    STAGE_SCRIPT_ENGINE.name: STAGE_SCRIPT_ENGINE,
    SERIES_ENGINE.name: SERIES_ENGINE,
}

# Display order in pickers. Every format_mode now has a real engine.
ENGINE_ORDER: tuple[str, ...] = (
    NOVEL_ENGINE.name,
    SCREENPLAY_ENGINE.name,
    GRAPHIC_NOVEL_ENGINE.name,
    STAGE_SCRIPT_ENGINE.name,
    SERIES_ENGINE.name,
)


def get_engine(name: str | None) -> NarrativeEngine:
    """Resolve a mode name to its engine; unknown names fall back to Novel."""
    if not name:
        return NOVEL_ENGINE
    return ALL_ENGINES.get(name, NOVEL_ENGINE)


def engine_for_project(project: "Project | None") -> NarrativeEngine:
    """Pick the engine for a Project.

    Reads `project.narrative_engine` if set (new field), otherwise
    falls back to the legacy `format_mode` mapping via project_compat.
    """
    if project is None:
        return NOVEL_ENGINE
    from logosforge.project_compat import get_project_narrative_engine
    return get_engine(get_project_narrative_engine(project))
