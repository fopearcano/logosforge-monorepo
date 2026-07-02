"""Professional screenplay output validation (Phase 10H).

Deterministic readiness check across output targets (fountain / docx / pdf /
preview / fdx) with a compatibility level. No LLM, no DB mutation. Output/format
problems are reported as warnings/levels, never as story-health failures.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Compatibility levels.
LEVEL_STABLE = "stable"
LEVEL_PREVIEW = "preview"
LEVEL_EXPERIMENTAL = "experimental"
LEVEL_DEFERRED = "deferred"

_TARGET_LEVEL = {
    "fountain": LEVEL_STABLE,
    "docx": LEVEL_STABLE,
    "preview": LEVEL_PREVIEW,
    "html": LEVEL_PREVIEW,
    "pdf": LEVEL_PREVIEW,        # approximate pagination
    "fdx": LEVEL_EXPERIMENTAL,
}


@dataclass
class ScreenplayOutputValidationReport:
    project_id: int = 0
    target_format: str = "docx"
    blocking_errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    is_export_safe: bool = True
    compatibility_level: str = LEVEL_STABLE
    available_formats: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id, "target_format": self.target_format,
            "blocking_errors": list(self.blocking_errors),
            "warnings": list(self.warnings), "suggestions": list(self.suggestions),
            "is_export_safe": self.is_export_safe,
            "compatibility_level": self.compatibility_level,
            "available_formats": list(self.available_formats),
        }


def available_output_formats() -> list[str]:
    """Formats currently producible in this environment."""
    formats = ["fountain", "preview", "html", "pdf", "fdx"]
    try:
        from logosforge.screenplay_docx_export import docx_available
        if docx_available():
            formats.insert(1, "docx")
    except Exception:
        pass
    return formats


def validate_professional_output(
    db, project_id: int, *, target_format: str = "docx",
) -> ScreenplayOutputValidationReport:
    """Deterministically validate readiness for a professional output target."""
    report = ScreenplayOutputValidationReport(
        project_id=project_id, target_format=target_format,
        available_formats=available_output_formats(),
        compatibility_level=_TARGET_LEVEL.get(target_format, LEVEL_DEFERRED))

    # Writing mode.
    try:
        from logosforge.writing_modes import get_project_writing_mode_by_id
        if get_project_writing_mode_by_id(db, project_id) != "screenplay":
            report.warnings.append("Project is not in screenplay mode.")
    except Exception:
        pass

    # Dependency / target availability.
    if target_format == "docx" and "docx" not in report.available_formats:
        report.blocking_errors.append("python-docx unavailable — DOCX not producible.")
    if target_format == "pdf":
        report.warnings.append("PDF pagination is approximate (not page-accurate).")
        report.suggestions.append("For best fidelity, print to PDF from the HTML preview.")
    if target_format == "fdx":
        report.warnings.append(
            "FDX is experimental and unverified with Final Draft; prefer .fountain.")
    if target_format not in _TARGET_LEVEL:
        report.blocking_errors.append(f"Unsupported output target '{target_format}'.")

    # Reuse the deterministic Fountain validator for content-level checks.
    try:
        from logosforge.export import export_screenplay_fountain_result
        from logosforge.screenplay_fountain import validate_fountain_export
        res = export_screenplay_fountain_result(db, project_id)
        fval = validate_fountain_export(res.text)
        report.warnings.extend(fval.warnings)
        report.blocking_errors.extend(fval.blocking_errors)
        if any("forced" in w.lower() for w in res.warnings):
            report.warnings.append("Some elements needed forcing to map cleanly.")
    except Exception as exc:
        report.warnings.append(f"Content validation skipped: {exc}")

    # Title page.
    try:
        from logosforge.screenplay_render import get_title_page
        if not (get_title_page(db, project_id).get("title") or "").strip():
            report.warnings.append("No title page / title set.")
    except Exception:
        pass

    report.is_export_safe = not report.blocking_errors
    return report
