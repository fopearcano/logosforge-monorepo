"""Centralized left-panel icon map (flat / terminal / minimal-cyber style).

The sidebar renders each item's icon as a leading glyph inside the button text,
so the icon inherits the button's QSS ``color`` automatically — muted gray when
idle, off-white on hover, and the accent (``SIDEBAR_ACTIVE_TEXT``) when the
section is active. That only works for **monochrome text-presentation** glyphs;
colorful emoji render in their own colors and ignore the theme.

This module replaces the previous scattered colorful-emoji strings with a single
consistent monochrome set: geometric shapes, technical symbols, a terminal
prompt and a lambda — flat, dark-mode friendly, no gradients/3D/texture/emoji.

Where a glyph has an emoji presentation by default, U+FE0E (VARIATION SELECTOR-15)
is appended to force the flat text rendering. For glyphs that are already
text-default it is a harmless no-op, so the set renders consistently across the
Dark / Green / Warm themes without any per-theme work.
"""

from __future__ import annotations

_VS15 = "︎"  # force text (monochrome) presentation

# name -> monochrome glyph. Kept visually consistent (single-cell, similar weight).
SIDEBAR_ICONS: dict[str, str] = {
    "Projects": "▦",          # ▦  orthogonal-fill square (project grid)
    "Dashboard": "▤",         # ▤  horizontal-fill square (dashboard rows)
    "Notes": "✎" + _VS15,     # ✎  pencil
    "Manuscript": "≡",        # ≡  three lines (prose)
    "Chapters": "❏" + _VS15,  # ❏  page/chapter card
    "Outline": "☰" + _VS15,   # ☰  trigram (hierarchy)
    "Scenes": "▣",            # ▣  square with centre (frame)
    "Timeline": "◷",          # ◷  clock-quadrant circle
    "Plot": "⊠",              # ⊠  squared times (plot grid)
    "Structure": "▥",         # ▥  vertical-fill square (blocks)
    "Acts": "▷" + _VS15,      # ▷  play / act
    "Beats": "⋮",             # ⋮  vertical ellipsis (beat list)
    "Tags": "⌗",              # ⌗  viewdata / hash
    "Graph": "⌬",             # ⌬  benzene ring (node graph)
    "Arcs": "⌒",              # ⌒  arc
    "PSYKE": "◉",             # ◉  fisheye (mind/eye)
    "Grid": "⊞",              # ⊞  squared plus
    "Health": "✚" + _VS15,    # ✚  heavy cross
    "Balance": "⚖" + _VS15,   # ⚖  scales
    "Pacing": "♪",            # ♪  eighth note (rhythm)
    "Adapt": "⟳",             # ⟳  clockwise arrow (transform)
    "Narrative": "¶",         # ¶  pilcrow (prose flow)
    "Plugins": "⊕",           # ⊕  circled plus (add-on)
    "Assistant": "❯",         # ❯  terminal prompt
    "Logos": "λ",             # λ  lambda (logic / logos)
    "Chat": "✉" + _VS15,      # ✉  envelope (message)
    "LibreChat": "⛬",          # ⛬  advanced/general chat workspace (sidecar)
    "Stages": "⊟",            # ⊟  squared minus (layered stage)
    "Pages": "▭",             # ▭  rectangle (page)
    # Footer actions (kept centralized so no emoji strings are scattered).
    "Import": "⇣",            # ⇣  download
    "Export": "⇡",            # ⇡  upload
    "Settings": "⚙" + _VS15,  # ⚙  gear
}


# Flat icon colours — each section gets a distinct, medium-saturation flat hue
# (no gradients/3D) so sections are easy to tell apart at a glance. Tuned to read
# on both the dark and the two light sidebar backgrounds. Grouped by family so a
# group's items share a hue range. Used to tint the rendered glyph icon; the
# label text still follows the theme colour.
_DEFAULT_ICON_COLOR = "#9aa4b2"
SIDEBAR_ICON_COLORS: dict[str, str] = {
    # Top-level
    "Projects": "#d08a3c",     # amber
    "Dashboard": "#2fa898",    # teal
    "Notes": "#c79a3e",        # gold
    "Manuscript": "#3b82c4",   # blue
    "Chapters": "#3b82c4",     # blue (same family as Manuscript)
    "Tags": "#caa83a",         # yellow
    "Graph": "#2f9ea8",        # cyan
    # Plan group — greens
    "Outline": "#4a9e4a",
    "Scenes": "#4f9ed8",
    "Timeline": "#9b6fc0",
    "Plot": "#cf7a4a",
    "Pages": "#b06fc0",
    # Structure group — purples/sage
    "Structure": "#8a78c8",
    "Acts": "#a05fb0",
    "Beats": "#cc5b5b",
    "Arcs": "#5a8fd0",
    # Analytics group — warm/green
    "Health": "#4faa5a",
    "Balance": "#c79a3e",
    "Pacing": "#b06fc0",
    "Narrative": "#4f9ed8",
    # Other top-level
    "Adapt": "#5a8fd0",
    "PSYKE": "#cd5c97",        # pink/magenta
    "Stages": "#c79a3e",
    "Plugins": "#9b6fc0",
    "Grid": "#3b82c4",
    # AI cluster
    "Assistant": "#3fa37a",    # accent green
    "Logos": "#3aa856",        # bright green (lambda)
    "Chat": "#4f9ed8",         # blue
    "LibreChat": "#a06fd8",    # purple (advanced chat sidecar)
    # Footer
    "Import": "#5aa86a",
    "Export": "#5a8f9c",
    "Settings": "#9aa4b2",
}


def sidebar_icon(name: str) -> str:
    """Return the monochrome glyph for *name* (empty string if unknown)."""
    return SIDEBAR_ICONS.get(name, "")


def sidebar_icon_color(name: str) -> str:
    """Return the flat icon colour for *name* (a sensible default if unknown)."""
    return SIDEBAR_ICON_COLORS.get(name, _DEFAULT_ICON_COLOR)
