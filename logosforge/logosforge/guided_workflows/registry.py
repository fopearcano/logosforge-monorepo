"""Workflow template registry (Phase 10O).

Thin, deterministic lookup over the built-in templates. Mode-aware: templates
whose ``modes`` exclude the project's writing mode are not offered.
"""

from __future__ import annotations

from logosforge.guided_workflows.models import WorkflowTemplate
from logosforge.guided_workflows.templates import ALL_TEMPLATES
from logosforge.writing_modes import normalize_mode

_BY_ID: dict[str, WorkflowTemplate] = {t.id: t for t in ALL_TEMPLATES}


def all_templates() -> list[WorkflowTemplate]:
    return list(ALL_TEMPLATES)


def get_template(template_id: str) -> "WorkflowTemplate | None":
    return _BY_ID.get(template_id)


def list_workflow_templates(mode: str | None = None) -> list[WorkflowTemplate]:
    """Templates offered for *mode* (or all templates when mode is None)."""
    if mode is None:
        return list(ALL_TEMPLATES)
    m = normalize_mode(mode)
    return [t for t in ALL_TEMPLATES if t.applies_to(m)]
