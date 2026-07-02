"""Novel narrative engine — long-form prose fiction."""

from __future__ import annotations

from logosforge.narrative_engines.base import NarrativeEngine


NOVEL_ENGINE = NarrativeEngine(
    name="novel",
    label="Novel",
    description="Long-form prose fiction: interiority, narrative voice, "
                "chapter pacing, character arc, thematic recurrence.",
    structural_units=("part", "chapter", "scene"),
    plot_block_unit="chapter",
    timeline_semantics="chronological_chapters",
    assistant_priorities=(
        "interiority",
        "narrative voice",
        "prose rhythm",
        "chapter pacing",
        "character arc",
        "thematic recurrence",
    ),
    assistant_terminology={
        "block": "chapter",
        "unit": "scene",
    },
    psyke_context_rules=(
        "character interior state",
        "relationships",
        "themes",
        "locations",
        "lore",
    ),
    review_checks=(
        "chapter purpose",
        "scene turn",
        "POV consistency",
        "prose rhythm",
        "character arc movement",
    ),
    default_format="novel",
    compatible_formats=("novel",),
)
