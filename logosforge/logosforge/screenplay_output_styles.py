"""Screenplay professional-output style profiles (Phase 10H).

Deterministic, pure-data style model shared by the DOCX / PDF / HTML / FDX
output layers. No Qt, no LLM, no DB. Fonts degrade safely (Courier Prime →
Courier New → Courier → monospace) — no platform-specific assumptions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Font fallback chain (first available wins at render time).
FONT_FALLBACKS = ("Courier Prime", "Courier New", "Courier", "monospace")


@dataclass
class ElementStyle:
    uppercase: bool = False
    bold: bool = False
    italic: bool = False
    align: str = "left"            # left | right | center
    left_indent_in: float = 0.0
    right_indent_in: float = 0.0
    space_before_pt: int = 0


@dataclass
class ScreenplayOutputStyle:
    name: str = "Standard Screenplay"
    page_size: str = "Letter"      # Letter | A4
    font_family: str = FONT_FALLBACKS[0]
    font_fallbacks: tuple[str, ...] = FONT_FALLBACKS
    font_size: int = 12
    line_spacing: float = 1.0
    margins_in: dict = field(default_factory=lambda: {
        "top": 1.0, "bottom": 1.0, "left": 1.5, "right": 1.0})
    # Per-element styling (industry-ish approximations, not page-accurate).
    scene_heading_style: ElementStyle = field(default_factory=lambda: ElementStyle(
        uppercase=True, bold=True, space_before_pt=12))
    action_style: ElementStyle = field(default_factory=ElementStyle)
    character_style: ElementStyle = field(default_factory=lambda: ElementStyle(
        uppercase=True, left_indent_in=2.2, space_before_pt=12))
    parenthetical_style: ElementStyle = field(default_factory=lambda: ElementStyle(
        italic=True, left_indent_in=1.6, right_indent_in=2.0))
    dialogue_style: ElementStyle = field(default_factory=lambda: ElementStyle(
        left_indent_in=1.0, right_indent_in=1.5))
    transition_style: ElementStyle = field(default_factory=lambda: ElementStyle(
        uppercase=True, align="right", space_before_pt=12))
    note_style: ElementStyle = field(default_factory=lambda: ElementStyle(italic=True))
    title_page_style: ElementStyle = field(default_factory=lambda: ElementStyle(
        align="center"))
    include_page_numbers: bool = True
    include_scene_numbers: bool = False
    include_title_page: bool = True
    include_notes: bool = False
    include_sections: bool = False
    include_synopses: bool = False
    metadata: dict = field(default_factory=dict)

    def style_for(self, element_type: str) -> ElementStyle:
        return {
            "scene_heading": self.scene_heading_style,
            "action": self.action_style,
            "character": self.character_style,
            "parenthetical": self.parenthetical_style,
            "dialogue": self.dialogue_style,
            "transition": self.transition_style,
            "note": self.note_style,
            "shot": self.scene_heading_style,
        }.get(element_type, self.action_style)

    def resolve_font(self, available: set[str] | None = None) -> tuple[str, bool]:
        """Return (font_name, fell_back?). With no availability info, the first
        fallback is used and not considered a fallback event."""
        if not available:
            return self.font_fallbacks[0], False
        for i, f in enumerate(self.font_fallbacks):
            if f in available:
                return f, i > 0
        return "monospace", True

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name, "page_size": self.page_size,
            "font_family": self.font_family,
            "font_fallbacks": list(self.font_fallbacks),
            "font_size": self.font_size, "line_spacing": self.line_spacing,
            "margins_in": dict(self.margins_in),
            "include_page_numbers": self.include_page_numbers,
            "include_scene_numbers": self.include_scene_numbers,
            "include_title_page": self.include_title_page,
            "include_notes": self.include_notes,
            "include_sections": self.include_sections,
            "include_synopses": self.include_synopses,
            "metadata": dict(self.metadata),
        }


DEFAULT_STYLE = ScreenplayOutputStyle()

_PROFILES = {
    "standard": DEFAULT_STYLE,
    "compact": ScreenplayOutputStyle(name="Compact", font_size=11, line_spacing=1.0),
}


def get_style(name: str | None = None) -> ScreenplayOutputStyle:
    return _PROFILES.get((name or "standard").lower(), DEFAULT_STYLE)


def list_styles() -> list[str]:
    return list(_PROFILES.keys())
