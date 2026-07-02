"""Writing-mode-aware rewrite strategies (Phase 10L).

Data-driven strategy registry. Each strategy carries a short prompt directive.
``strategies_for_mode`` filters to the strategies relevant for a writing mode
(general + mode-specific). Strategies never change the project's writing mode.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RewriteStrategy:
    key: str
    label: str
    directive: str          # short instruction folded into the prompt


_GENERAL = [
    ("clarify", "Clarify", "Make the meaning clearer without changing intent."),
    ("compress", "Compress", "Tighten — remove redundancy, keep the substance."),
    ("expand", "Expand", "Develop the passage with more depth (no padding)."),
    ("intensify", "Intensify", "Raise tension/stakes/energy."),
    ("simplify", "Simplify", "Use plainer language and structure."),
    ("literary_polish", "Literary Polish", "Improve prose craft and word choice."),
    ("structural_rewrite", "Structural Rewrite", "Reorder/restructure for stronger flow."),
    ("continuity_fix", "Continuity Fix", "Resolve internal inconsistencies."),
    ("voice_preserve", "Preserve Voice", "Rewrite while keeping the existing voice."),
    ("voice_shift", "Shift Voice", "Adjust the narrative/character voice as instructed."),
    ("subtext_increase", "Increase Subtext", "Move intent beneath the surface."),
    ("pacing_increase", "Faster Pacing", "Quicken the rhythm."),
    ("pacing_slowdown", "Slower Pacing", "Slow down for weight/atmosphere."),
]

_BY_MODE = {
    "novel": [
        ("prose_polish", "Prose Polish", "Refine prose rhythm and diction."),
        ("interiority_increase", "Increase Interiority", "Deepen interior experience."),
        ("description_balance", "Balance Description", "Balance description and action."),
        ("paragraph_rhythm", "Paragraph Rhythm", "Vary paragraph/sentence rhythm."),
        ("sensory_detail", "Sensory Detail", "Add grounded sensory detail."),
        ("remove_exposition", "Remove Exposition", "Cut on-the-nose exposition."),
    ],
    "screenplay": [
        ("dialogue_economy", "Dialogue Economy", "Tighten dialogue; cut filler."),
        ("visual_action", "Visual Action", "Externalize into visible action."),
        ("scene_turn_strengthen", "Strengthen Scene Turn", "Sharpen the value shift."),
        ("subtext_dialogue", "Subtext Dialogue", "Put intent under the line."),
        ("reduce_unfilmable_prose", "Reduce Unfilmable Prose", "Cut interior/unfilmable text."),
        ("blocking_clarity", "Blocking Clarity", "Clarify physical staging."),
        ("setup_payoff_reinforce", "Reinforce Setup/Payoff", "Strengthen a setup or payoff."),
    ],
    "stage_script": [
        ("playable_dialogue", "Playable Dialogue", "Make lines speakable/performable."),
        ("stage_direction_clarity", "Stage Direction Clarity", "Clarify stage directions."),
        ("actor_intention", "Actor Intention", "Sharpen the actor's intention."),
        ("entrance_exit_logic", "Entrance/Exit Logic", "Fix entrances/exits."),
        ("subtext_performance", "Performance Subtext", "Add playable subtext."),
    ],
    "graphic_novel": [
        ("panelize", "Panelize", "Break the moment into panels."),
        ("reduce_caption", "Reduce Captions", "Cut captions in favour of image."),
        ("visual_beat_split", "Split Visual Beats", "Separate distinct visual beats."),
        ("speech_bubble_economy", "Bubble Economy", "Trim dialogue for bubbles."),
        ("page_turn_hook", "Page-Turn Hook", "Place a hook at the page turn."),
        ("image_text_balance", "Image/Text Balance", "Balance image and text load."),
    ],
    "series": [
        ("episode_arc_alignment", "Episode Arc Alignment", "Align with the episode arc."),
        ("cold_open_strengthen", "Strengthen Cold Open", "Sharpen the cold open."),
        ("recurring_motif", "Recurring Motif", "Reinforce a recurring motif."),
        ("continuity_across_episode", "Cross-Episode Continuity", "Keep continuity across episodes."),
        ("character_thread_balance", "Character Thread Balance", "Balance character threads."),
    ],
}

_GENERAL_OBJS = [RewriteStrategy(*s) for s in _GENERAL]
_MODE_OBJS = {m: [RewriteStrategy(*s) for s in lst] for m, lst in _BY_MODE.items()}
_ALL = {s.key: s for s in _GENERAL_OBJS}
for _lst in _MODE_OBJS.values():
    for _s in _lst:
        _ALL[_s.key] = _s


def strategies_for_mode(writing_mode: str | None) -> list[RewriteStrategy]:
    """General strategies + the ones specific to *writing_mode* (novel fallback)."""
    mode = (writing_mode or "novel").strip()
    return list(_GENERAL_OBJS) + list(_MODE_OBJS.get(mode, _MODE_OBJS["novel"]))


def get_strategy(key: str | None) -> RewriteStrategy | None:
    return _ALL.get((key or "").strip())


def is_valid_for_mode(key: str | None, writing_mode: str | None) -> bool:
    return get_strategy(key) in strategies_for_mode(writing_mode)
