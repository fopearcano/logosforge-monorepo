"""Deterministic optimistic-concurrency revision for one workflow run."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime


def _timestamp(value: datetime | None) -> str:
    return value.isoformat() if value is not None else ""


def workflow_run_revision(run, steps) -> str:
    """Hash every logical field that can affect a workflow command.

    Creation timestamps are included as row-incarnation tokens so deleting and
    recreating an otherwise-identical run/step cannot revive a stale revision.
    Update timestamps are deliberately excluded: revisions describe logical
    state and therefore remain stable across exact no-ops.
    """

    from logosforge.guided_workflows.registry import get_template

    template = get_template(str(getattr(run, "template_id", "") or ""))
    if template is None:
        template_descriptor = {"missing": True}
    else:
        mode = str(getattr(run, "writing_mode", "") or "")
        template_descriptor = {
            "id": template.id,
            "title": template.title,
            "description": template.description,
            "category": template.category,
            "modes": list(template.modes),
            "steps": [
                step.to_dict() for step in template.steps_for_mode(mode)
            ],
        }

    payload = {
        "run": {
            "id": int(getattr(run, "id", 0) or 0),
            "project_id": int(getattr(run, "project_id", 0) or 0),
            "template_id": str(getattr(run, "template_id", "") or ""),
            "title": str(getattr(run, "title", "") or ""),
            "writing_mode": str(getattr(run, "writing_mode", "") or ""),
            "status": str(getattr(run, "status", "") or ""),
            "current_step_id": str(
                getattr(run, "current_step_id", "") or ""
            ),
            "source_type": str(getattr(run, "source_type", "") or ""),
            "source_id": getattr(run, "source_id", None),
            "context_json": str(getattr(run, "context_json", "") or ""),
            "created_at": _timestamp(getattr(run, "created_at", None)),
            "completed_at": _timestamp(getattr(run, "completed_at", None)),
        },
        "steps": [
            {
                "id": int(getattr(step, "id", 0) or 0),
                "step_id": str(getattr(step, "step_id", "") or ""),
                "title": str(getattr(step, "title", "") or ""),
                "status": str(getattr(step, "status", "") or ""),
                "section_name": str(
                    getattr(step, "section_name", "") or ""
                ),
                "action_id": str(getattr(step, "action_id", "") or ""),
                "target_type": str(
                    getattr(step, "target_type", "") or ""
                ),
                "target_id": getattr(step, "target_id", None),
                "result_json": str(getattr(step, "result_json", "") or ""),
                "notes": str(getattr(step, "notes", "") or ""),
                "sort_index": int(getattr(step, "sort_index", 0) or 0),
                "created_at": _timestamp(getattr(step, "created_at", None)),
            }
            for step in sorted(
                steps,
                key=lambda item: (
                    int(getattr(item, "sort_index", 0) or 0),
                    int(getattr(item, "id", 0) or 0),
                ),
            )
        ],
        "template": template_descriptor,
    }
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


__all__ = ["workflow_run_revision"]
