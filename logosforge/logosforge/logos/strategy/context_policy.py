"""Strategic context-block selection.

Decides which context blocks a strategy decision should include — strategic, not
everything. The medium profile sets the base; the active section and any
plugin/health strategies add their blocks. The result is de-duplicated and
ordered.
"""

from __future__ import annotations

from logosforge.logos.strategy import medium_profiles as mp

# Section -> extra context blocks worth adding regardless of medium.
_SECTION_BLOCKS = {
    "Manuscript": (mp.CTX_SCENE,),
    "Outline": (mp.CTX_OUTLINE,),
    "Plot": (mp.CTX_OUTLINE, mp.CTX_SCENE),
    "Timeline": (mp.CTX_OUTLINE, mp.CTX_SCENE),
    "PSYKE": (mp.CTX_PSYKE,),
    "Graph": (mp.CTX_GRAPH, mp.CTX_PSYKE),
}

_ORDER = (
    mp.CTX_SCENE, mp.CTX_OUTLINE, mp.CTX_PSYKE, mp.CTX_GRAPH,
    mp.CTX_NOTES, mp.CTX_STORY_MEMORY, mp.CTX_HEALTH,
)


def select_context_blocks(
    engine: str,
    section_name: str,
    *,
    extra_blocks: tuple[str, ...] = (),
) -> list[str]:
    """Return the ordered, de-duplicated context blocks to include."""
    profile = mp.get_profile(engine)
    chosen: set[str] = set(profile.context_blocks)
    chosen.update(_SECTION_BLOCKS.get(section_name, ()))
    chosen.update(extra_blocks)
    return [b for b in _ORDER if b in chosen]
