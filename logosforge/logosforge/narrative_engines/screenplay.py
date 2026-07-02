"""Screenplay narrative engine — film / TV screenplay reasoning."""

from __future__ import annotations

from logosforge.narrative_engines.base import NarrativeEngine


SCREENPLAY_ENGINE = NarrativeEngine(
    name="screenplay",
    label="Screenplay",
    description="Visual, temporal, performative, production-aware storytelling. "
                "Scenes are the unit; pacing is measured in screen time; "
                "subtext, blocking and setup/payoff are first-class concerns.",
    structural_units=("act", "sequence", "scene", "beat"),
    plot_block_unit="scene",
    timeline_semantics="screen_time",
    assistant_priorities=(
        "visual action",
        "cinematic pacing",
        "scene duration",
        "blocking",
        "subtext",
        "setup/payoff",
        "dialogue economy",
        "continuity",
    ),
    assistant_terminology={
        "block": "scene",
        "unit": "beat",
        "chapter": "sequence",
    },
    psyke_context_rules=(
        "subtext state",
        "character knowledge state",
        "continuity",
        "visual motifs",
    ),
    review_checks=(
        "scene turns",
        "dialogue economy",
        "visual conflict",
        "duration",
        "setup/payoff",
        "blocking clarity",
    ),
    default_format="screenplay",
    compatible_formats=("screenplay", "series"),
    system_prompt_overlay=(
        "Reason cinematically. Every scene must be evaluated as a unit of "
        "SCREEN TIME, not page count. Prioritize what the CAMERA SEES and "
        "what the AUDIENCE HEARS.\n"
        "Key questions for every scene:\n"
        "- Does this scene TURN? (emotional state at exit ≠ entry)\n"
        "- Is the conflict VISIBLE? (can you film it?)\n"
        "- Is there subtext? (what is NOT said matters more than what is)\n"
        "- Is the dialogue economical? (characters want things, not explain things)\n"
        "- Does blocking reveal character? (physical action = inner state)\n"
        "- Are setup/payoff links honored? (every gun shown must fire)\n"
        "- Is continuity maintained? (wounds, props, costumes, knowledge)\n"
        "- Does the scene earn its screen time? (cut ruthlessly)"
    ),
    feedback_patterns=(
        "Scene does not turn — entry and exit emotional states are identical",
        "Dialogue is expositional — characters explain instead of want",
        "No visible conflict — nothing the camera can film",
        "Blocking is static — characters talk but don't move or act",
        "Subtext absent — everything is on the surface",
        "Setup without payoff — element introduced but never resolved",
        "Continuity break — state contradicts a prior scene",
        "Scene overstays — content doesn't justify screen time",
    ),
)
