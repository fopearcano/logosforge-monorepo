"""Controlled Apply service (Phase 10M).

The single gate every canonical mutation passes through: build a preview (diff +
conflicts) with NO mutation, then ``apply_operation(confirmed=True)`` mutates the
target through a validated adapter, after a STAGE checkpoint when available, and
emits ``project_data_changed``. Deterministic; no LLM; no Qt; current project only.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from logosforge.controlled_apply.conflicts import (
    detect_apply_conflicts, has_blocking,
)
from logosforge.controlled_apply.diff import build_apply_diff
from logosforge.controlled_apply.targets import get_adapter


def _hash(text: str) -> str:
    return hashlib.sha1((text or "").encode("utf-8")).hexdigest()[:16]


def _excerpt(text: str, n: int = 280) -> str:
    t = (text or "").strip()
    return t if len(t) <= n else t[:n] + "…"


@dataclass
class ApplyPreview:
    operation_id: int | None = None
    target_type: str = ""
    target_id: int | None = None
    before_text: str = ""
    proposed_text: str = ""
    after_text: str = ""
    diff: dict = field(default_factory=dict)
    conflicts: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    can_apply: bool = True
    can_apply_partially: bool = True
    rollback_available: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "operation_id": self.operation_id, "target_type": self.target_type,
            "target_id": self.target_id, "before_text": _excerpt(self.before_text, 600),
            "proposed_text": _excerpt(self.proposed_text, 600),
            "after_text": _excerpt(self.after_text, 600), "diff": dict(self.diff),
            "conflicts": list(self.conflicts), "warnings": list(self.warnings),
            "can_apply": self.can_apply,
            "can_apply_partially": self.can_apply_partially,
            "rollback_available": self.rollback_available,
        }


def _rollback_available(db) -> bool:
    return hasattr(db, "create_stage")


def build_apply_preview(
    db, project_id: int, *, target_type: str, target_id, proposed_text: str,
    apply_mode: str = "replace", source_type: str = "manual",
    source_id: int | None = None, save: bool = False,
) -> ApplyPreview:
    """Build a preview (diff + conflicts). **No mutation.** Optionally persist a
    draft ``ControlledApplyOperation`` (``save=True``)."""
    adapter = get_adapter(db, project_id, target_type, target_id)
    preview = ApplyPreview(target_type=target_type, target_id=target_id,
                           proposed_text=proposed_text,
                           rollback_available=_rollback_available(db))
    if adapter is None:
        preview.conflicts = [{"conflict_type": "format_mismatch",
                              "severity": "blocking",
                              "message": f"Apply for '{target_type}' is deferred.",
                              "suggested_resolution": "Use manual copy."}]
        preview.can_apply = preview.can_apply_partially = False
        return preview

    mode_err = adapter.validate_mode(apply_mode)
    state = adapter.read()
    preview.before_text = state.text

    from logosforge.controlled_apply.targets import _compose
    preview.after_text = (_compose(state.text, proposed_text, apply_mode)
                          if state.exists else proposed_text)
    preview.diff = build_apply_diff(state.text, preview.after_text).to_dict()

    conflicts = detect_apply_conflicts(
        db, project_id, target_type=target_type, target_state=state,
        proposed_text=proposed_text, expected_before_hash=_hash(state.text))
    conflict_dicts = [c.to_dict() for c in conflicts]
    if mode_err:
        conflict_dicts.insert(0, {"conflict_type": "format_mismatch",
                                  "severity": "blocking", "message": mode_err,
                                  "suggested_resolution": "Choose an allowed mode."})
    preview.conflicts = conflict_dicts
    preview.warnings = [c["message"] for c in conflict_dicts
                        if c["severity"] == "warning"]
    blocking = any(c["severity"] in ("blocking", "error") for c in conflict_dicts)
    preview.can_apply = not blocking
    preview.can_apply_partially = not blocking

    if save:
        op = db.create_apply_operation(
            project_id, source_type=source_type, source_id=source_id,
            target_type=target_type, target_id=target_id, apply_mode=apply_mode,
            status="previewed", before_hash=_hash(state.text),
            after_hash=_hash(preview.after_text),
            before_excerpt=_excerpt(state.text), after_excerpt=_excerpt(preview.after_text),
            diff_json=json.dumps(preview.diff), conflict_json=json.dumps(conflict_dicts),
            conflicts=[{"conflict_type": c["conflict_type"], "severity": c["severity"],
                        "message": c["message"],
                        "suggested_resolution": c.get("suggested_resolution", "")}
                       for c in conflict_dicts])
        preview.operation_id = op.id
    return preview


def create_apply_operation(db, project_id: int, *, target_type: str, target_id,
                           proposed_text: str, apply_mode: str = "replace",
                           source_type: str = "manual", source_id: int | None = None):
    """Persist a draft operation with its computed preview/conflicts (no mutation)."""
    return build_apply_preview(
        db, project_id, target_type=target_type, target_id=target_id,
        proposed_text=proposed_text, apply_mode=apply_mode,
        source_type=source_type, source_id=source_id, save=True)


def apply_operation(db, project_id: int, *, target_type: str, target_id,
                    proposed_text: str, apply_mode: str = "replace",
                    confirmed: bool = False, force: bool = False,
                    source_type: str = "manual", source_id: int | None = None,
                    operation_id: int | None = None,
                    create_checkpoint: bool = True) -> dict:
    """Apply a proposal to its target. Requires ``confirmed=True``; blocking
    conflicts (incl. stale source) require ``force=True``."""
    if not confirmed:
        return {"ok": False, "error": "Apply requires explicit confirmation."}
    adapter = get_adapter(db, project_id, target_type, target_id)
    if adapter is None:
        return {"ok": False, "error": f"Apply for '{target_type}' is deferred."}

    state = adapter.read()
    conflicts = detect_apply_conflicts(
        db, project_id, target_type=target_type, target_state=state,
        proposed_text=proposed_text, expected_before_hash=_hash(state.text))
    if has_blocking(conflicts) and not force:
        blockers = [c.to_dict() for c in conflicts if c.is_blocking]
        return {"ok": False, "error": "Blocking conflict(s) — confirm with force.",
                "conflicts": blockers,
                "stale": any(c.conflict_type == "stale_source" for c in conflicts
                             if c.is_blocking)}

    before = state.text
    stage_id = None
    if create_checkpoint and hasattr(db, "create_stage"):
        try:
            stage = db.create_stage(
                project_id, f"Before controlled apply ({target_type} {target_id})",
                description="Auto checkpoint before a controlled apply.")
            stage_id = getattr(stage, "id", None)
        except Exception:
            stage_id = None

    try:
        adapter.apply(proposed_text, apply_mode)
    except Exception as exc:
        if operation_id is not None:
            db.update_apply_operation(operation_id, status="failed")
        return {"ok": False, "error": f"Apply failed: {exc}"}

    from logosforge.controlled_apply.targets import _compose
    after = _compose(before, proposed_text, apply_mode) if state.exists else proposed_text
    if operation_id is not None:
        op = db.update_apply_operation(
            operation_id, status="applied", before_hash=_hash(before),
            after_hash=_hash(after), created_stage_id=stage_id)
    else:
        op = db.create_apply_operation(
            project_id, source_type=source_type, source_id=source_id,
            target_type=target_type, target_id=target_id, apply_mode=apply_mode,
            status="applied", before_hash=_hash(before), after_hash=_hash(after),
            before_excerpt=_excerpt(before), after_excerpt=_excerpt(after),
            created_stage_id=stage_id)
    try:
        from logosforge.project_events import emit_project_data_changed
        emit_project_data_changed()
    except Exception:
        pass
    return {"ok": True, "operation_id": getattr(op, "id", operation_id),
            "target_type": target_type, "target_id": target_id, "stage_id": stage_id}


def cancel_operation(db, operation_id: int) -> None:
    db.update_apply_operation(operation_id, status="cancelled")


def get_apply_history(db, project_id: int) -> list:
    return db.get_apply_operations(project_id)
