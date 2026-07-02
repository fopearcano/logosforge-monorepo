"""Deterministic screenplay export readiness validation (Phase 10F).

Checks whether a screenplay project is ready to export — distinguishing
*blocking errors* (truly unsafe) from *warnings* (actionable, non-blocking) and
*suggestions*. No LLM, no DB mutation. Format problems are not narrative failures.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from logosforge import screenplay_blocks as sb

_VALID_TARGETS = ("fountain", "plain_text", "preview_html")


@dataclass
class ScreenplayExportValidationReport:
    project_id: int
    target_format: str = "fountain"
    blocking_errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    summary: str = ""
    is_export_safe: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id, "target_format": self.target_format,
            "blocking_errors": list(self.blocking_errors),
            "warnings": list(self.warnings), "suggestions": list(self.suggestions),
            "summary": self.summary, "is_export_safe": self.is_export_safe,
        }


def validate_screenplay_export(
    db, project_id: int, *, target_format: str = "fountain",
    prefs: dict | None = None,
) -> ScreenplayExportValidationReport:
    """Deterministically validate export readiness (read-only)."""
    report = ScreenplayExportValidationReport(
        project_id=project_id, target_format=target_format,
    )

    if target_format not in _VALID_TARGETS:
        report.blocking_errors.append(f"Unsupported export target '{target_format}'.")

    # Title.
    title = ""
    try:
        from logosforge.screenplay_render import get_title_page
        title = (get_title_page(db, project_id).get("title") or "").strip()
    except Exception:
        title = ""
    if not title:
        report.warnings.append("Missing title — add a title page before exporting.")

    try:
        scenes = db.get_all_scenes(project_id)
    except Exception:
        scenes = []

    if not scenes:
        report.blocking_errors.append("Empty screenplay — no scenes to export.")
        report.summary = "Not export-safe: the screenplay is empty."
        report.is_export_safe = False
        return report

    scenes_without_heading = 0
    orphan_dialogue = 0
    orphan_parenthetical = 0
    ambiguous_action_scenes = 0
    total_blocks = 0
    note_blocks = 0

    for scene in scenes:
        blocks = sb.parse_screenplay_text(getattr(scene, "content", "") or "",
                                          scene_id=scene.id)
        total_blocks += len(blocks)
        heading = (getattr(scene, "slugline", "") or "").strip()
        if not heading and not any(b.element_type == "scene_heading" for b in blocks):
            scenes_without_heading += 1
        prev = None
        kinds = {}
        for b in blocks:
            kinds[b.element_type] = kinds.get(b.element_type, 0) + 1
            if b.element_type == "note":
                note_blocks += 1
            if b.element_type == "dialogue" and prev not in (
                    "character", "parenthetical", "dialogue"):
                orphan_dialogue += 1
            if b.element_type == "parenthetical" and prev not in (
                    "character", "dialogue"):
                orphan_parenthetical += 1
            prev = b.element_type
        # A scene that is *only* action with no heading/dialogue is ambiguous.
        if kinds.get("action", 0) == len(blocks) and len(blocks) > 0 and not heading:
            ambiguous_action_scenes += 1

    if scenes_without_heading:
        report.warnings.append(
            f"{scenes_without_heading} scene(s) have no scene heading.")
    if orphan_dialogue:
        report.warnings.append(
            f"{orphan_dialogue} dialogue block(s) without a preceding character cue.")
    if orphan_parenthetical:
        report.warnings.append(
            f"{orphan_parenthetical} parenthetical(s) without dialogue context.")
    if ambiguous_action_scenes:
        report.suggestions.append(
            f"{ambiguous_action_scenes} scene(s) are action-only with no heading — "
            "confirm they parse as intended.")

    prefs = prefs or {}
    if note_blocks:
        if prefs.get("show_notes_in_export", False):
            report.suggestions.append(
                f"{note_blocks} note block(s) WILL be included in this export.")
        else:
            report.suggestions.append(
                f"{note_blocks} note block(s) will be excluded from production export.")

    report.is_export_safe = not report.blocking_errors
    n_w = len(report.warnings)
    report.summary = (
        ("Export-safe" if report.is_export_safe else "Not export-safe")
        + f" for {target_format}: {len(report.blocking_errors)} blocking error(s), "
        + f"{n_w} warning(s)."
    )
    return report
