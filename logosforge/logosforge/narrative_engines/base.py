"""NarrativeEngine — frozen-dataclass profile for one mode's reasoning."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class NarrativeEngine:
    """Self-contained narrative-reasoning profile for one writing mode."""

    name: str                              # e.g. "novel", "screenplay"
    label: str                             # human-readable
    description: str

    structural_units: tuple[str, ...]      # ("part", "chapter", "scene") etc.
    plot_block_unit: str                   # "chapter" | "scene" | "page" | "episode"
    timeline_semantics: str                # "chronological_chapters" | "screen_time" | ...

    assistant_priorities: tuple[str, ...]
    assistant_terminology: dict[str, str] = field(default_factory=dict)
    psyke_context_rules: tuple[str, ...] = ()
    review_checks: tuple[str, ...] = ()

    default_format: str = "prose"          # WritingFormat name to suggest
    compatible_formats: tuple[str, ...] = ()

    system_prompt_overlay: str = ""
    feedback_patterns: tuple[str, ...] = ()

    # -- Helper accessors (so consumers don't reach into fields) -----------

    def get_structural_units(self) -> tuple[str, ...]:
        return self.structural_units

    def get_plot_block_unit(self) -> str:
        return self.plot_block_unit

    def get_timeline_semantics(self) -> str:
        return self.timeline_semantics

    def get_assistant_priorities(self) -> tuple[str, ...]:
        return self.assistant_priorities

    def get_psyke_context_rules(self) -> tuple[str, ...]:
        return self.psyke_context_rules

    def get_review_checks(self) -> tuple[str, ...]:
        return self.review_checks

    # -- Assistant prompt block --------------------------------------------

    def format_context_block(self) -> str:
        """Compact prompt-ready block describing the engine's reasoning."""
        lines = [
            f"[Narrative Engine: {self.label}]",
            f"Structural units: {', '.join(self.structural_units)}",
            f"Plot block: {self.plot_block_unit}",
            f"Timeline: {self.timeline_semantics}",
        ]
        if self.assistant_priorities:
            lines.append(
                "Priorities: " + ", ".join(self.assistant_priorities[:8])
            )
        if self.review_checks:
            lines.append(
                "Review checks: " + ", ".join(self.review_checks[:8])
            )
        if self.feedback_patterns:
            lines.append(
                "Feedback signals: " + "; ".join(self.feedback_patterns[:8])
            )
        if self.system_prompt_overlay:
            lines.append("")
            lines.append(self.system_prompt_overlay)
        return "\n".join(lines)

    def format_writing_block(self) -> str:
        """Minimal mode block for DIRECT WRITING actions — structural units and
        terminology only, with **no** reasoning/critique overlay, review checks,
        or feedback signals. Those induce analysis/structure output during direct
        manuscript writing (e.g. a "Dialogue" action should yield dialogue, not a
        scene critique), so they are intentionally omitted here."""
        lines = [
            f"[Writing mode: {self.label}]",
            f"Structural units: {', '.join(self.structural_units)}",
        ]
        if self.assistant_terminology:
            terms = ", ".join(f"{k} = {v}"
                              for k, v in self.assistant_terminology.items())
            lines.append(f"Terminology: {terms}")
        return "\n".join(lines)
