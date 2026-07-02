"""Narrative engines — encode HOW a story is reasoned about.

A `NarrativeEngine` is a frozen-dataclass profile that owns:
  - structural unit terminology (chapter / scene / page / episode)
  - the plot-block unit Plot views default to
  - the timeline semantics (chronological / screen-time / etc.)
  - assistant priorities + per-priority terminology
  - PSYKE context rules
  - review checks

It does NOT own typography, exports or block styling — those live in
``logosforge.writing_formats``.  The two layers are deliberately
orthogonal so a Screenplay engine can be paired with a treatment
format, or a Novel engine with an outline format, without conflating
narrative reasoning and editor rendering.
"""

from logosforge.narrative_engines.base import NarrativeEngine
from logosforge.narrative_engines.novel import NOVEL_ENGINE
from logosforge.narrative_engines.screenplay import SCREENPLAY_ENGINE
from logosforge.narrative_engines.graphic_novel import GRAPHIC_NOVEL_ENGINE
from logosforge.narrative_engines.stage_script import STAGE_SCRIPT_ENGINE
from logosforge.narrative_engines.series import SERIES_ENGINE
from logosforge.narrative_engines.registry import (
    ALL_ENGINES,
    ENGINE_ORDER,
    engine_for_project,
    get_engine,
)

__all__ = [
    "NarrativeEngine",
    "NOVEL_ENGINE",
    "SCREENPLAY_ENGINE",
    "GRAPHIC_NOVEL_ENGINE",
    "STAGE_SCRIPT_ENGINE",
    "SERIES_ENGINE",
    "ALL_ENGINES",
    "ENGINE_ORDER",
    "engine_for_project",
    "get_engine",
]
