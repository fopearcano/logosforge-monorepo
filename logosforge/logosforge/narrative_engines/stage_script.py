"""Stage Script narrative engine — theatre / drama reasoning.

Theatre is live, spatial, performative and actor-driven. Meaning emerges
from spoken conflict, the use of stage space, entrances and exits,
blocking, subtext, scene objectives, what the audience can see, and the
continuity of props on stage. The unit of craft is the SCENE (grouped by
ACTS); everything must be playable live by an actor.
"""

from __future__ import annotations

from logosforge.narrative_engines.base import NarrativeEngine


STAGE_SCRIPT_ENGINE = NarrativeEngine(
    name="stage_script",
    label="Stage Script",
    description="Live, spatial, performative, actor-driven storytelling. "
                "Scenes are the unit, grouped by acts; conflict is spoken "
                "and played; entrances/exits, blocking, subtext, scene "
                "objectives and prop continuity are first-class concerns.",
    # Acts → Scenes → Beats → Entrances/Exits → Cues. Not every project
    # uses every level.
    structural_units=("act", "scene", "beat", "entrance_exit", "cue"),
    plot_block_unit="scene",                 # scenes, grouped by acts (§4)
    timeline_semantics="performance_order",  # §5
    assistant_priorities=(
        "playable conflict",
        "spoken pressure",
        "subtext",
        "actor motivation",
        "entrances/exits",
        "stage blocking",
        "physical business",
        "stageable action",
        "audience visibility",
        "prop continuity",
        "act breaks",
        "scene objective",
    ),
    assistant_terminology={
        "block": "scene",
        "unit": "beat",
        "chapter": "act",
    },
    # PSYKE as theatrical memory: what a character wants on stage, how they
    # pursue it in speech, what they hide, who owns which prop, etc.
    psyke_context_rules=(
        "character stage objective",
        "spoken strategy",
        "subtext",
        "relationship pressure",
        "entrances/exits",
        "prop ownership",
        "offstage knowledge",
        "stage position",
    ),
    review_checks=(
        "dialogue tension",
        "playable action",
        "actor motivation",
        "blocking clarity",
        "stage feasibility",
        "dramatic pressure",
        "actorial subtext",
        "prop continuity",
        "scene objective",
        "act break",
    ),
    default_format="stage_script",
    compatible_formats=("stage_script",),
    system_prompt_overlay=(
        "Reason as a PLAYWRIGHT and director, not a novelist or filmmaker. "
        "Everything must be PLAYABLE LIVE by an actor on a stage in front of "
        "an audience.\n"
        "Key questions for every scene:\n"
        "- Is the conflict PLAYABLE? (it is fought in speech and action, not "
        "narrated)\n"
        "- Does each character have a SCENE OBJECTIVE? (what do they want, "
        "from whom, right now?)\n"
        "- Is there SUBTEXT? (what is pursued under the line, not on it)\n"
        "- Can it be STAGED? (no camera, no cut — space, bodies, props only)\n"
        "- Do ENTRANCES/EXITS and blocking carry meaning? (who is on stage, "
        "where, and why)\n"
        "- Is there physical BUSINESS? (actors need something to do)\n"
        "- Is prop CONTINUITY honored? (a prop placed must be accounted for)\n"
        "- Does the ACT BREAK land on a strong, unresolved beat?\n"
        "- Can the AUDIENCE see/hear what matters? (stage visibility)"
    ),
    feedback_patterns=(
        "Dialogue has no conflict — characters agree or merely inform",
        "No scene objective — no one on stage wants anything",
        "Action is not stageable — it can't be performed live without a camera",
        "Subtext absent — everything is stated outright on the line",
        "Static blocking — no entrances, exits, or stage movement",
        "Talking heads — no physical business for the actors",
        "Prop introduced but continuity not tracked",
        "Act break lands on a weak, resolved beat — no pull into the next act",
    ),
)
