"""Deterministic controlled-apply conflict detection (Phase 10M). No LLM/DB-write.

Blocking conflicts prevent direct apply; warnings allow apply with explicit
confirmation. Stale source and missing target are blocking; PSYKE reference loss,
invalid screenplay blocks and production risk are warnings.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any

SEV_INFO, SEV_WARNING, SEV_ERROR, SEV_BLOCKING = "info", "warning", "error", "blocking"
_BLOCKING = (SEV_ERROR, SEV_BLOCKING)


def _hash(text: str) -> str:
    return hashlib.sha1((text or "").encode("utf-8")).hexdigest()[:16]


@dataclass
class ApplyConflict:
    conflict_type: str
    severity: str
    message: str
    suggested_resolution: str = ""

    @property
    def is_blocking(self) -> bool:
        return self.severity in _BLOCKING

    def to_dict(self) -> dict[str, Any]:
        return {"conflict_type": self.conflict_type, "severity": self.severity,
                "message": self.message,
                "suggested_resolution": self.suggested_resolution}


def detect_apply_conflicts(db, project_id: int, *, target_type: str, target_state,
                           proposed_text: str, expected_before_hash: str | None = None,
                           ) -> list[ApplyConflict]:
    """Detect conflicts for applying *proposed_text* to a target. Read-only."""
    conflicts: list[ApplyConflict] = []
    current = target_state.text if target_state.exists else ""

    if not target_state.exists:
        conflicts.append(ApplyConflict(
            "target_missing", SEV_BLOCKING,
            "The target no longer exists.",
            "Cancel and re-create the proposal for an existing target."))
        return conflicts

    if expected_before_hash is not None and _hash(current) != expected_before_hash:
        conflicts.append(ApplyConflict(
            "stale_source", SEV_BLOCKING,
            "The target changed since this proposal was created.",
            "Regenerate from current text, or apply with force."))

    if not (proposed_text or "").strip():
        conflicts.append(ApplyConflict(
            "format_mismatch", SEV_BLOCKING, "Proposed text is empty.",
            "Provide non-empty replacement text."))

    # PSYKE reference loss (warning).
    try:
        entries = db.get_all_psyke_entries(project_id)
        low_before, low_after = current.lower(), (proposed_text or "").lower()
        lost = []
        for e in entries:
            name = (getattr(e, "name", "") or "").strip()
            if len(name) < 2:
                continue
            n = name.lower()
            if re.search(rf"\b{re.escape(n)}\b", low_before) and not re.search(
                    rf"\b{re.escape(n)}\b", low_after):
                lost.append(name)
        if lost:
            conflicts.append(ApplyConflict(
                "psyke_reference_loss", SEV_WARNING,
                f"Removes PSYKE reference(s): {', '.join(lost[:6])}.",
                "Confirm these characters/objects are intentionally dropped."))
    except Exception:
        pass

    # Screenplay block validity (warning) — only in screenplay mode.
    if (getattr(target_state, "writing_mode", "") == "screenplay"
            and target_type in ("scene", "manuscript", "screenplay_block")):
        try:
            from logosforge import screenplay_blocks as sb
            blocks = sb.parse_screenplay_text(proposed_text or "")
            prev, orphan = None, 0
            for b in blocks:
                if b.element_type == "dialogue" and prev not in (
                        "character", "parenthetical", "dialogue"):
                    orphan += 1
                prev = b.element_type
            if orphan:
                conflicts.append(ApplyConflict(
                    "screenplay_block_invalid", SEV_WARNING,
                    f"{orphan} dialogue block(s) without a character cue.",
                    "Add character cues, or confirm the formatting."))
        except Exception:
            pass

    # Production risk (warning) — active production draft touching a scene.
    if target_type in ("scene", "manuscript", "screenplay_block"):
        try:
            if db.get_active_production_draft(project_id) is not None:
                conflicts.append(ApplyConflict(
                    "production_risk", SEV_WARNING,
                    "A production draft is active; applying may need a revision set.",
                    "Attach this change to the active revision set after applying."))
        except Exception:
            pass

    return conflicts


def has_blocking(conflicts) -> bool:
    return any(c.is_blocking for c in conflicts)
