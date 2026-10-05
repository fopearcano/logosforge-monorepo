"""Pure helpers for the canonical project-owned Canvas Plot board.

Canvas Plot is an independent spatial planning surface.  It is not derived
from Scenes or Timeline state: a node may optionally reference a Scene, but
the board's nodes, links, frames, geometry, text, colours, and z-order are its
own persisted state.

Revision calculation stays database-free so coherent reads and guarded writes
can derive the same token from rows loaded inside one SQLite transaction.
Viewport zoom/pan deliberately does not participate; that is a local UI
preference stored in ``Project.settings_json["canvas_plot_view"]``.
"""

from __future__ import annotations

from collections.abc import Sequence
import hashlib
import json
from typing import Any


def _creation_identity(value: Any) -> str:
    """Serialize an entity's immutable creation marker for ABA protection."""
    created_at = getattr(value, "created_at", None)
    isoformat = getattr(created_at, "isoformat", None)
    return str(isoformat()) if callable(isoformat) else str(created_at or "")


def canvas_plot_revision(
    project: Any,
    nodes: Sequence[Any],
    links: Sequence[Any],
    frames: Sequence[Any],
    *,
    valid_scene_ids: frozenset[int] | set[int] | None = None,
) -> str:
    """Content-address every persisted field visible on the Canvas Plot.

    Numeric ids alone are insufficient because SQLite can reuse an integer
    primary key after deletion.  Immutable creation identities bind a stale
    proposal to the exact Project and board entities it originally observed.
    """
    payload = {
        "project_id": int(getattr(project, "id", 0) or 0),
        "project_created_at": _creation_identity(project),
        "nodes": [
            [
                int(node.id),
                _creation_identity(node),
                node.title or "",
                node.body or "",
                float(node.x),
                float(node.y),
                float(node.width),
                float(node.height),
                node.color_label or "",
                node.group_label or "",
                (
                    int(node.scene_id)
                    if node.scene_id is not None
                    and (
                        valid_scene_ids is None
                        or int(node.scene_id) in valid_scene_ids
                    )
                    else None
                ),
                int(node.sort_order or 0),
            ]
            for node in nodes
        ],
        "links": [
            [
                int(link.id),
                _creation_identity(link),
                int(link.source_node_id),
                int(link.target_node_id),
                link.label or "",
                link.color_label or "",
                link.link_type or "",
            ]
            for link in links
        ],
        "frames": [
            [
                int(frame.id),
                _creation_identity(frame),
                frame.title or "",
                frame.color_label or "",
                float(frame.x),
                float(frame.y),
                float(frame.width),
                float(frame.height),
            ]
            for frame in frames
        ],
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
