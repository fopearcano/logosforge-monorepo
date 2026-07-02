"""Series narrative engine — episodic / multi-episode storytelling.

Series storytelling is built on recurrence, continuity, escalation,
delayed payoff and multi-layer arcs across episodes and seasons. The
unit of craft is the EPISODE (within seasons); meaning accrues over the
long arc through callbacks, cliffhangers and A/B/C plot interplay.
"""

from __future__ import annotations

from logosforge.narrative_engines.base import NarrativeEngine


SERIES_ENGINE = NarrativeEngine(
    name="series",
    label="Series",
    description="Episodic, multi-episode storytelling. Episodes are the "
                "unit, grouped into seasons; meaning accrues through "
                "recurrence, continuity, escalation, delayed payoff and "
                "A/B/C plot interplay across the long arc.",
    # Series → Season → Episode → Act → Scene, plus A/B/C plotlines and
    # long arcs. Not every project uses every level.
    structural_units=("series", "season", "episode", "act", "scene",
                      "plotline", "arc"),
    plot_block_unit="episode",                   # episodes (§4)
    timeline_semantics="episode_season_progression",  # §5
    assistant_priorities=(
        "episode engine",
        "season arc",
        "series arc",
        "A/B/C plot balance",
        "continuity",
        "recurring motifs",
        "cliffhangers",
        "callbacks",
        "delayed payoff",
        "character progression across episodes",
        "unresolved threads",
        "serialized vs procedural balance",
    ),
    assistant_terminology={
        "block": "episode",
        "unit": "scene",
        "chapter": "season",
    },
    # PSYKE as long-form memory: states and arcs that persist and evolve
    # across many episodes, plus the continuity ledger.
    psyke_context_rules=(
        "long-running character states",
        "relationship evolution across episodes",
        "unresolved arcs",
        "mystery boxes",
        "recurring motifs",
        "continuity ledger",
        "episode memory",
        "season-level stakes",
    ),
    review_checks=(
        "episode function",
        "season arc movement",
        "A/B/C plot interaction",
        "cliffhanger effectiveness",
        "continuity integrity",
        "long arc progression",
        "payoff timing",
    ),
    default_format="series",
    compatible_formats=("series", "screenplay"),
    system_prompt_overlay=(
        "Reason as a SHOWRUNNER, not a novelist or feature writer. Every "
        "episode is both a unit AND a movement in larger season and series "
        "arcs.\n"
        "Key questions for every episode:\n"
        "- What is this episode's FUNCTION? (does it stand on its own AND "
        "move the serialized arc?)\n"
        "- Does the SEASON ARC advance here? (escalation, not treading water)\n"
        "- Are the A/B/C plots BALANCED and do they interact/contrast?\n"
        "- Does it end on a CLIFFHANGER or hook that pulls into the next "
        "episode?\n"
        "- Are CALLBACKS and delayed PAYOFFS landing at the right time? "
        "(a setup three episodes back should pay off when it lands hardest)\n"
        "- Is CONTINUITY intact across episodes? (states, relationships, "
        "open threads, the ledger)\n"
        "- Does each character PROGRESS across episodes (not reset each week)?\n"
        "- Are unresolved threads / mystery boxes advanced, not just teased?\n"
        "- Is the serialized vs procedural balance right for this show?"
    ),
    feedback_patterns=(
        "Episode has no function in the season arc — it treads water",
        "A/B/C plots don't interact or balance — one swamps the others",
        "Weak cliffhanger — nothing pulls the audience into the next episode",
        "Setup planted but never paid off across episodes",
        "Continuity break — a state contradicts an earlier episode",
        "Character resets each episode — no progression across the season",
        "Mystery box teased but never advanced — string without payoff",
        "Too procedural (no serialized thread) or too serialized (no "
        "standalone satisfaction)",
    ),
)
