"""Writing format definitions for the Manuscript editor.

Each format defines element types with their styling rules.
The editor uses these to apply format-specific behavior.

Margin values are in pixels, calibrated for a 720 px text area.
720 px ≈ 6.0 in (standard US-letter text width), so 1 in ≈ 120 px.

Screenplay margins follow industry standard (Final Draft / WGA):
  Scene Heading  — full width, bold, ALL CAPS
  Action         — full width
  Character      — 2.2 in left indent (264 px), ALL CAPS
  Dialogue       — 1.0 in left (120 px), 1.5 in right (180 px)
  Parenthetical  — 1.5 in left (180 px), 2.0 in right (240 px)
  Transition     — right-aligned, ALL CAPS
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ElementStyle:
    """Visual and behavioral rules for one element type."""
    name: str
    shortcut: str = ""
    font_size: int = 15
    bold: bool = False
    italic: bool = False
    all_caps: bool = False
    align: str = "left"
    left_margin: int = 0
    right_margin: int = 0
    top_spacing: int = 0
    bottom_spacing: int = 12
    first_line_indent: int = 0
    line_height: float = 1.5
    color_key: str = "text"          # text | muted | secondary | accent
    background_key: str = ""         # "" | panel | sfx | note  (subtle band)


@dataclass(frozen=True)
class WritingFormat:
    """Complete format definition."""
    name: str
    label: str
    elements: list[ElementStyle] = field(default_factory=list)
    default_element: str = "action"


# ---------------------------------------------------------------------------
# Novel
# Standard prose: generous line height, paragraph spacing, large chapter heads.
# ---------------------------------------------------------------------------
NOVEL = WritingFormat(
    name="novel",
    label="Novel",
    default_element="body",
    elements=[
        ElementStyle(
            name="chapter",
            shortcut="Ctrl+1",
            font_size=26, bold=True,
            top_spacing=48, bottom_spacing=24,
            line_height=1.4,
        ),
        ElementStyle(
            name="scene_break",
            shortcut="Ctrl+2",
            font_size=15, align="center",
            top_spacing=24, bottom_spacing=24,
            line_height=1.0,
        ),
        ElementStyle(
            name="body",
            shortcut="Ctrl+3",
            font_size=18,
            line_height=1.5,
            bottom_spacing=10,
        ),
    ],
)

# ---------------------------------------------------------------------------
# Screenplay  (WGA / Final Draft standard)
#
# All elements use the same font size (industry: Courier 12 pt).
# Differentiation comes from margins, caps, and alignment.
#
# Page text area = 6.0 in  →  720 px at our scale.
#   Scene Heading : left 0,    right 0    — full width
#   Action        : left 0,    right 0    — full width
#   Character     : left 264,  right 0    — 2.2 in indent, left-aligned
#   Dialogue      : left 120,  right 180  — 1.0 in / 1.5 in
#   Parenthetical : left 180,  right 240  — 1.5 in / 2.0 in
#   Transition    : left 0,    right 0    — right-aligned
# ---------------------------------------------------------------------------
SCREENPLAY = WritingFormat(
    name="screenplay",
    label="Screenplay",
    default_element="action",
    elements=[
        ElementStyle(
            name="scene_heading",
            shortcut="Ctrl+1",
            font_size=15, bold=True, all_caps=True,
            top_spacing=24, bottom_spacing=12,
        ),
        ElementStyle(
            name="action",
            shortcut="Ctrl+2",
            font_size=15,
            bottom_spacing=12,
        ),
        ElementStyle(
            name="character",
            shortcut="Ctrl+3",
            font_size=15, all_caps=True,
            left_margin=264,
            top_spacing=12, bottom_spacing=0,
        ),
        ElementStyle(
            name="dialogue",
            shortcut="Ctrl+4",
            font_size=15,
            left_margin=120, right_margin=180,
            bottom_spacing=0,
        ),
        ElementStyle(
            name="parenthetical",
            shortcut="Ctrl+5",
            font_size=15, italic=True,
            left_margin=180, right_margin=240,
            bottom_spacing=0,
        ),
        ElementStyle(
            name="transition",
            shortcut="Ctrl+6",
            font_size=15, all_caps=True, align="right",
            top_spacing=12, bottom_spacing=12,
        ),
    ],
)

# ---------------------------------------------------------------------------
# Graphic Novel  (Dark Horse / DC "full script" style)
#
# Spatial-sequential scripting workspace. Block types are visually distinct:
#   Page          — large, bold, ALL CAPS header; generous top space so pages
#                   read as separated sections.
#   Panel         — bold sub-header beneath its page.
#   Description   — the panel's staging/action, indented + boxed (panel band).
#   Character     — ALL CAPS bold speaker, indented toward the balloon column.
#   Dialogue      — speech, indented under its character.
#   Internal Thought — italic, secondary colour (thought balloon).
#   Caption       — italic narration box, muted.
#   SFX           — stylized: bold ALL CAPS, accent colour on a band.
#   Art Direction — visually muted italic note to the artist.
#   Transition    — ALL CAPS, right-aligned beat between pages/sequences.
#   Note          — small muted aside.
# ---------------------------------------------------------------------------
GRAPHIC_NOVEL = WritingFormat(
    name="graphic_novel",
    label="Graphic Novel",
    default_element="panel",
    elements=[
        ElementStyle(
            name="page",
            shortcut="Ctrl+1",
            font_size=22, bold=True, all_caps=True,
            top_spacing=44, bottom_spacing=14,
        ),
        ElementStyle(
            name="panel",
            shortcut="Ctrl+2",
            font_size=16, bold=True,
            top_spacing=22, bottom_spacing=4,
        ),
        ElementStyle(
            name="description",
            shortcut="Ctrl+3",
            font_size=15,
            left_margin=60, right_margin=24,
            background_key="panel",
            top_spacing=2, bottom_spacing=10,
        ),
        ElementStyle(
            name="character",
            shortcut="Ctrl+4",
            font_size=15, all_caps=True, bold=True,
            left_margin=180,
            top_spacing=8, bottom_spacing=0,
        ),
        ElementStyle(
            name="dialogue",
            shortcut="Ctrl+5",
            font_size=15,
            left_margin=180,
            bottom_spacing=8,
        ),
        ElementStyle(
            name="internal_thought",
            font_size=15, italic=True,
            left_margin=180,
            color_key="secondary",
            bottom_spacing=8,
        ),
        ElementStyle(
            name="caption",
            shortcut="Ctrl+6",
            font_size=15, italic=True,
            left_margin=120,
            color_key="muted",
            bottom_spacing=8,
        ),
        ElementStyle(
            name="sfx",
            font_size=18, bold=True, all_caps=True,
            left_margin=120,
            color_key="accent",
            background_key="sfx",
            top_spacing=4, bottom_spacing=8,
        ),
        ElementStyle(
            name="art_direction",
            font_size=14, italic=True,
            left_margin=60, right_margin=24,
            color_key="muted",
            bottom_spacing=8,
        ),
        ElementStyle(
            name="transition",
            font_size=15, bold=True, all_caps=True, align="right",
            top_spacing=12, bottom_spacing=12,
        ),
        ElementStyle(
            name="note",
            font_size=13, italic=True,
            left_margin=60,
            color_key="muted",
            bottom_spacing=8,
        ),
    ],
)

# ---------------------------------------------------------------------------
# Stage Script  (Samuel French / standard playwriting format)
#
# Dialogue is the WIDEST element (runs full width, margin-to-margin).
# Stage directions are indented and italic.  Character names centered.
# Act/scene headings centered, ALL CAPS, bold.
# ---------------------------------------------------------------------------
STAGE_SCRIPT = WritingFormat(
    name="stage_script",
    label="Stage Script",
    default_element="dialogue",
    elements=[
        ElementStyle(
            name="act_heading",
            shortcut="Ctrl+1",
            font_size=18, bold=True, all_caps=True, align="center",
            top_spacing=44, bottom_spacing=18,
        ),
        ElementStyle(
            name="scene_heading",
            shortcut="Ctrl+2",
            font_size=16, bold=True, all_caps=True, align="center",
            top_spacing=24, bottom_spacing=12,
        ),
        ElementStyle(
            name="character",
            shortcut="Ctrl+3",
            font_size=15, all_caps=True, align="center",
            top_spacing=12, bottom_spacing=0,
        ),
        ElementStyle(
            name="dialogue",
            shortcut="Ctrl+4",
            font_size=15,
            bottom_spacing=8,
        ),
        ElementStyle(
            name="stage_direction",
            shortcut="Ctrl+5",
            font_size=15, italic=True,
            left_margin=120, right_margin=120,
            color_key="muted", background_key="panel",
            bottom_spacing=8,
        ),
        ElementStyle(
            name="parenthetical",
            shortcut="Ctrl+6",
            font_size=15, italic=True,
            left_margin=180, right_margin=120,
            bottom_spacing=0,
        ),
        ElementStyle(
            name="aside",
            font_size=15, italic=True,
            left_margin=60,
            color_key="secondary",
            bottom_spacing=8,
        ),
        ElementStyle(
            name="cue",
            font_size=13, bold=True, all_caps=True,
            color_key="accent",
            top_spacing=2, bottom_spacing=4,
        ),
        ElementStyle(
            name="transition",
            font_size=15, bold=True, all_caps=True, align="right",
            top_spacing=12, bottom_spacing=12,
        ),
        ElementStyle(
            name="note",
            font_size=13, italic=True,
            left_margin=60,
            color_key="muted",
            bottom_spacing=8,
        ),
    ],
)

# ---------------------------------------------------------------------------
# Series  (TV script — single-cam / multi-cam hybrid)
#
# Follows screenplay rules for scene-level elements, adds episode and
# act structural markers.
# ---------------------------------------------------------------------------
SERIES = WritingFormat(
    name="series",
    label="Series",
    default_element="action",
    elements=[
        ElementStyle(
            name="season_heading",
            font_size=22, bold=True, all_caps=True, align="center",
            top_spacing=56, bottom_spacing=18,
        ),
        ElementStyle(
            name="episode_heading",
            shortcut="Ctrl+1",
            font_size=18, bold=True, all_caps=True, align="center",
            top_spacing=44, bottom_spacing=12,
        ),
        ElementStyle(
            name="act_heading",
            shortcut="Ctrl+2",
            font_size=15, bold=True, all_caps=True, align="center",
            top_spacing=24, bottom_spacing=14,
        ),
        ElementStyle(
            name="scene_heading",
            shortcut="Ctrl+3",
            font_size=15, bold=True, all_caps=True,
            top_spacing=24, bottom_spacing=12,
        ),
        ElementStyle(
            name="action",
            shortcut="Ctrl+4",
            font_size=15,
            bottom_spacing=12,
        ),
        ElementStyle(
            name="character",
            shortcut="Ctrl+5",
            font_size=15, all_caps=True,
            left_margin=264,
            top_spacing=12, bottom_spacing=0,
        ),
        ElementStyle(
            name="dialogue",
            shortcut="Ctrl+6",
            font_size=15,
            left_margin=120, right_margin=180,
            bottom_spacing=0,
        ),
        # Transition (e.g. "CUT TO:") — right-aligned, ALL CAPS (screenplay rule).
        ElementStyle(
            name="transition",
            font_size=15, bold=True, all_caps=True, align="right",
            top_spacing=12, bottom_spacing=12,
        ),
        # -- Plot-line labels (colored tags) -------------------------------
        ElementStyle(
            name="a_plot",
            font_size=13, bold=True, all_caps=True,
            color_key="accent", background_key="sfx",
            top_spacing=10, bottom_spacing=4,
        ),
        ElementStyle(
            name="b_plot",
            font_size=13, bold=True, all_caps=True,
            color_key="secondary", background_key="panel",
            top_spacing=10, bottom_spacing=4,
        ),
        ElementStyle(
            name="c_plot",
            font_size=13, bold=True, all_caps=True,
            color_key="muted", background_key="panel",
            top_spacing=10, bottom_spacing=4,
        ),
        # -- Opener blocks (distinctive) -----------------------------------
        ElementStyle(
            name="teaser",
            font_size=15, bold=True, all_caps=True, align="center",
            background_key="panel",
            top_spacing=20, bottom_spacing=12,
        ),
        ElementStyle(
            name="cold_open",
            font_size=15, bold=True, all_caps=True, align="center",
            background_key="panel",
            top_spacing=20, bottom_spacing=12,
        ),
        ElementStyle(
            name="tag",
            font_size=14, bold=True, all_caps=True, align="center",
            color_key="secondary",
            top_spacing=18, bottom_spacing=10,
        ),
        # -- Cliffhanger — marked but not loud -----------------------------
        ElementStyle(
            name="cliffhanger",
            font_size=15, italic=True,
            color_key="accent",
            top_spacing=10, bottom_spacing=10,
        ),
        # -- Editorial notes — muted ---------------------------------------
        ElementStyle(
            name="recap_note",
            font_size=13, italic=True,
            left_margin=60,
            color_key="muted",
            bottom_spacing=8,
        ),
        ElementStyle(
            name="continuity_note",
            font_size=13, italic=True,
            left_margin=60,
            color_key="muted",
            bottom_spacing=8,
        ),
    ],
)

ALL_FORMATS: dict[str, WritingFormat] = {
    "novel": NOVEL,
    "screenplay": SCREENPLAY,
    "graphic_novel": GRAPHIC_NOVEL,
    "stage_script": STAGE_SCRIPT,
    "series": SERIES,
}

FORMAT_ORDER = ["novel", "screenplay", "graphic_novel", "stage_script", "series"]
