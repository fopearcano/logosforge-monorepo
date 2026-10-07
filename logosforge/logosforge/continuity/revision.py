"""Deterministic revisions for persisted Semantic Continuity review state."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from typing import Any


def _canonical_json(value: Any, *, empty: str) -> str:
    raw = str(value or "")
    try:
        decoded = json.loads(raw or empty)
        return json.dumps(
            decoded,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (json.JSONDecodeError, TypeError, ValueError):
        # Invalid legacy bytes remain part of the revision.  Treating them as an
        # empty value could let a corrupt row alias a valid review state.
        return f"invalid:{raw}"


def continuity_review_revision(
    issues: Iterable[Any],
    *,
    project_id: int | None = None,
    project_created_at: Any = None,
) -> str:
    """Hash the complete persisted issue-review layer, independent of row ids."""
    records = [
        {
            "issue_key": str(getattr(issue, "issue_key", "") or ""),
            "issue_type": str(getattr(issue, "issue_type", "") or ""),
            "dimension": str(getattr(issue, "dimension", "") or ""),
            "severity": str(getattr(issue, "severity", "") or ""),
            "confidence": str(getattr(issue, "confidence", "") or ""),
            "title": str(getattr(issue, "title", "") or ""),
            "explanation": str(getattr(issue, "explanation", "") or ""),
            "evidence_json": _canonical_json(
                getattr(issue, "evidence_json", ""), empty="[]"
            ),
            "related_node_ids_json": _canonical_json(
                getattr(issue, "related_node_ids_json", ""), empty="[]"
            ),
            "related_scene_ids_json": _canonical_json(
                getattr(issue, "related_scene_ids_json", ""), empty="[]"
            ),
            "suggested_action": str(
                getattr(issue, "suggested_action", "") or ""
            ),
            "status": str(getattr(issue, "status", "") or ""),
        }
        for issue in issues
    ]
    records.sort(key=lambda row: (
        row["issue_key"],
        row["issue_type"],
        row["dimension"],
        row["severity"],
        row["confidence"],
        row["title"],
        row["explanation"],
        row["evidence_json"],
        row["related_node_ids_json"],
        row["related_scene_ids_json"],
        row["suggested_action"],
        row["status"],
    ))
    encoded = json.dumps(
        {
            "scope": "continuity-review-v1",
            "project_id": project_id,
            "project_created_at": (
                project_created_at.isoformat()
                if hasattr(project_created_at, "isoformat")
                else str(project_created_at or "")
            ),
            "issues": records,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


EMPTY_CONTINUITY_REVIEW_REVISION = continuity_review_revision(())
