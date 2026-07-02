"""Graphic Novel narrative engine — spatial-sequential comics storytelling.

Graphic novels are not prose and not screenplays: meaning emerges from
how images are arranged in space and revealed in sequence. The unit of
craft is the PANEL on the PAGE; pacing is felt through panel rhythm,
page composition and the page turn; subtext lives in what the art shows
versus what the balloons say.
"""

from __future__ import annotations

from logosforge.narrative_engines.base import NarrativeEngine


GRAPHIC_NOVEL_ENGINE = NarrativeEngine(
    name="graphic_novel",
    label="Graphic Novel",
    description="Spatial-sequential storytelling. Pages and panels are the "
                "unit; pacing is panel rhythm and the page turn; meaning "
                "emerges from composition, reveal timing, image/text balance "
                "and recurring visual motifs.",
    # Issue → Chapter → Sequence → Page → Panel. Not all projects use every
    # level, but the hierarchy is available for those that do.
    structural_units=("issue", "chapter", "sequence", "page", "panel"),
    # Plot defaults to SEQUENCES (a run of pages with one dramatic/visual
    # purpose) — never chapters by default.
    plot_block_unit="sequence",
    # The timeline is the reader's path through the book: page rhythm,
    # visual pacing and reveal timing — not clock time or screen time.
    timeline_semantics="reading_progression",
    assistant_priorities=(
        "panel rhythm",
        "page turns",
        "visual reveal timing",
        "composition",
        "image/text balance",
        "visual continuity",
        "symbolic recurrence",
        "silhouette readability",
        "panel flow",
        "emotional page energy",
    ),
    assistant_terminology={
        "block": "sequence",
        "unit": "panel",
        "chapter": "sequence",
        "scene": "page",
    },
    # PSYKE acts as visual memory for a graphic novel: it tracks how things
    # LOOK and how that look recurs, not just who-knows-what.
    psyke_context_rules=(
        "character visual identity",
        "motif recurrence",
        "object continuity",
        "costume continuity",
        "shape language",
        "symbolic tracking",
    ),
    review_checks=(
        "panel readability",
        "exposition density",
        "page turn impact",
        "visual pacing",
        "balloon overload",
        "image/text balance",
        "symbolic recurrence",
        "panel rhythm variety",
    ),
    default_format="graphic_novel",
    compatible_formats=("graphic_novel",),
    system_prompt_overlay=(
        "Reason as a COMICS author, not a novelist or screenwriter. The page "
        "is a SPATIAL composition and the book is a SEQUENCE of reveals.\n"
        "Key questions for every page/panel:\n"
        "- Does the panel READ clearly? (silhouette + composition guide the eye)\n"
        "- Is the image carrying the story? (show in art; don't narrate what "
        "the picture already says)\n"
        "- Is the balloon/caption load survivable? (don't bury art under text)\n"
        "- Does the page TURN earn a reveal? (the last panel before a turn "
        "sets up; the first panel after pays off)\n"
        "- Does panel rhythm vary with emotion? (size/shape/count = pacing)\n"
        "- Do visual motifs RECUR with meaning? (a symbol seen once is decor; "
        "seen again it is theme)\n"
        "- Is visual continuity intact? (design, costume, props, location state)\n"
        "- Does the page have its own emotional energy? (density: silent → "
        "explosive)"
    ),
    feedback_patterns=(
        "Balloon overload — more text than the panel's art can carry",
        "Talking heads — panels repeat the same shot with no visual action",
        "Page turn wasted — no setup before the turn or no reveal after it",
        "Panel rhythm monotonous — every panel the same size, shape and shot",
        "Exposition dump — captions narrate what the art should show",
        "Motif introduced but never recurs — a visual planted with no payoff",
        "Image/text imbalance — telling in words what belongs in the picture",
        "Silhouette unreadable — composition doesn't guide the eye or stage clearly",
    ),
)
