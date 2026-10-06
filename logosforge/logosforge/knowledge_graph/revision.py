"""Deterministic revisions for persisted Knowledge Graph review state."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from typing import Any


def _canonical_metadata(value: Any) -> str:
    raw = str(value or "")
    try:
        decoded = json.loads(raw or "{}")
        return json.dumps(
            decoded,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (json.JSONDecodeError, TypeError, ValueError):
        # Preserve invalid legacy bytes in the revision so corruption cannot be
        # silently equated with an empty metadata object.
        return f"invalid:{raw}"


def knowledge_graph_review_revision(
    edges: Iterable[Any],
    *,
    nodes: Iterable[Any] = (),
    project_id: int | None = None,
    project_created_at: Any = None,
) -> str:
    """Hash the complete persisted edge-review layer, independent of row ids.

    The live Narrative Knowledge Graph is assembled by legacy extractors that
    open separate read sessions.  Treating that derived build as one atomic
    snapshot would overstate its concurrency guarantee.  Review commands
    therefore guard the smaller canonical layer they actually mutate: all
    persisted confirmed/hidden edge rows for one project.
    """
    records = [
        {
            "source": str(getattr(edge, "source_node_key", "") or ""),
            "target": str(getattr(edge, "target_node_key", "") or ""),
            "edge_type": str(getattr(edge, "edge_type", "") or ""),
            "confidence": str(getattr(edge, "confidence", "") or ""),
            "provenance": str(getattr(edge, "provenance", "") or ""),
            "source_system": str(getattr(edge, "source_system", "") or ""),
            "explanation": str(getattr(edge, "explanation", "") or ""),
            "metadata_json": _canonical_metadata(
                getattr(edge, "metadata_json", "")
            ),
            "is_user_confirmed": bool(
                getattr(edge, "is_user_confirmed", False)
            ),
            "is_hidden": bool(getattr(edge, "is_hidden", False)),
        }
        for edge in edges
    ]
    records.sort(key=lambda row: (
        row["source"],
        row["target"],
        row["edge_type"],
        row["confidence"],
        row["provenance"],
        row["source_system"],
        row["explanation"],
        row["metadata_json"],
        row["is_user_confirmed"],
        row["is_hidden"],
    ))
    node_records = [
        {
            "node_key": str(getattr(node, "node_key", "") or ""),
            "node_type": str(getattr(node, "node_type", "") or ""),
            "source_type": str(getattr(node, "source_type", "") or ""),
            "source_id": (
                None
                if getattr(node, "source_id", None) is None
                else str(getattr(node, "source_id"))
            ),
            "label": str(getattr(node, "label", "") or ""),
            "summary": str(getattr(node, "summary", "") or ""),
            "metadata_json": _canonical_metadata(
                getattr(node, "metadata_json", "")
            ),
        }
        for node in nodes
    ]
    node_records.sort(key=lambda row: (
        row["node_key"],
        row["node_type"],
        row["source_type"],
        "" if row["source_id"] is None else row["source_id"],
        row["label"],
        row["summary"],
        row["metadata_json"],
    ))
    encoded = json.dumps(
        {
            "scope": "knowledge-graph-review-v1",
            "project_id": project_id,
            "project_created_at": (
                project_created_at.isoformat()
                if hasattr(project_created_at, "isoformat")
                else str(project_created_at or "")
            ),
            "nodes": node_records,
            "edges": records,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


EMPTY_KNOWLEDGE_GRAPH_REVIEW_REVISION = knowledge_graph_review_revision(())
