"""Stateful, revision-safe orchestration gateway for LogosForge Pro.

The gateway is transport-agnostic: :mod:`mcp_server` exposes these operations
over MCP, while tests can exercise them without installing the optional MCP
SDK.  Reads use the canonical FastAPI DTO endpoints.  Writes are deliberately
two-phase:

1. a focused ``propose_*`` tool validates the request and stores the exact HTTP
   method/path/body in an in-memory, expiring proposal;
2. ``apply_proposal`` may execute only that stored request, once, when writes
   were explicitly enabled for the server process.

Scene patches additionally require the API's optimistic-concurrency revision.
Other resource updates carry a digest guard so a proposal is rejected if the
resource changed after review.  There is no arbitrary action or arbitrary URL
escape hatch.
"""

from __future__ import annotations

import base64
import copy
import difflib
import hashlib
import json
import logging
import math
import re
import secrets
import threading
import time
from dataclasses import dataclass, field
from typing import Any

from logosforge.librechat.api_client import LogosForgeApiClient, LogosForgeApiError

LOGGER = logging.getLogger(__name__)


class GatewayError(RuntimeError):
    """A safe error that may be returned to an MCP client."""


def _digest(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


_LOWER_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_IDEMPOTENCY_KEY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{15,127}$")
_TIMELINE_RECEIPT_MISS_CODE = "timeline_receipt_not_found"
_CANVAS_PLOT_RECEIPT_MISS_CODE = "canvas_plot_receipt_not_found"
_KNOWLEDGE_GRAPH_RECEIPT_MISS_CODE = "knowledge_graph_receipt_not_found"
_CONTINUITY_RECEIPT_MISS_CODE = "continuity_receipt_not_found"
_PROGRESSION_RECEIPT_MISS_CODE = "progression_receipt_not_found"
KNOWLEDGE_GRAPH_VIEW_MODES = frozenset({
    "project_map",
    "structure",
    "recorded_risk",
    "revision_impact",
})


def _timeline_receipt_request_digest(
    project_id: int,
    command: dict[str, Any],
) -> str:
    """Match Core's canonical identity for a validated Timeline command."""
    return _digest({
        "scope": "timeline-command-v1",
        "project_id": int(project_id),
        "kind": command["kind"],
        "expected_revision": command["expected_revision"],
        "fields": {
            key: value
            for key, value in command.items()
            if key not in {"kind", "expected_revision"}
        },
    })


_CANVAS_PLOT_GEOMETRY_FIELDS = frozenset({"x", "y", "width", "height"})


def _canvas_plot_receipt_request_digest(
    project_id: int,
    command: dict[str, Any],
) -> str:
    """Match Core's canonical identity for a validated Canvas Plot command.

    Pydantic validates Canvas geometry as finite floats before Core computes
    its receipt digest.  Canonicalising the same fields here prevents JSON's
    distinct ``1`` and ``1.0`` encodings from creating a false mismatch when
    a caller supplied an integral coordinate.
    """
    fields = {
        key: (
            float(value)
            if key in _CANVAS_PLOT_GEOMETRY_FIELDS
            and isinstance(value, (int, float))
            and not isinstance(value, bool)
            else value
        )
        for key, value in command.items()
        if key not in {"kind", "expected_revision"}
    }
    return _digest({
        "scope": "canvas-plot-command-v1",
        "project_id": int(project_id),
        "kind": command["kind"],
        "expected_revision": command["expected_revision"],
        "fields": fields,
    })


def _knowledge_graph_receipt_request_digest(
    project_id: int,
    command: dict[str, Any],
) -> str:
    """Match Core's canonical identity for one graph edge-review command."""
    return _digest({
        "scope": "knowledge-graph-command-v1",
        "project_id": int(project_id),
        "kind": command["kind"],
        "expected_revision": command["expected_revision"],
        "source": command["source"],
        "target": command["target"],
        "edge_type": command["edge_type"],
    })


def _continuity_receipt_request_digest(
    project_id: int,
    command: dict[str, Any],
) -> str:
    """Match Core's canonical identity for one Continuity review command."""
    return _digest({
        "scope": "continuity-command-v1",
        "project_id": int(project_id),
        "kind": command["kind"],
        "expected_revision": command["expected_revision"],
        "issue_key": command["issue_id"],
        "expected_issue_fingerprint": command["expected_issue_fingerprint"],
    })


def _progression_receipt_request_digest(
    project_id: int,
    command: dict[str, Any],
) -> str:
    """Match Core's canonical identity for one Progressions command."""
    return _digest({
        "scope": "progression-command-v1",
        "project_id": int(project_id),
        "kind": command["kind"],
        "expected_revision": command["expected_revision"],
        "fields": {
            key: value
            for key, value in command.items()
            if key not in {"kind", "expected_revision"}
        },
    })


def _content_review(before: str, after: str) -> dict[str, Any]:
    diff = "\n".join(
        difflib.unified_diff(
            before.splitlines(), after.splitlines(),
            fromfile="current", tofile="proposed", lineterm="", n=3,
        )
    )
    if len(diff) > 12_000:
        diff = diff[:12_000] + "\n… diff truncated …"
    return {
        "before_length": len(before),
        "after_length": len(after),
        "before_sha256": hashlib.sha256(before.encode("utf-8")).hexdigest(),
        "after_sha256": hashlib.sha256(after.encode("utf-8")).hexdigest(),
        "diff": diff,
    }


def _compact_body(body: dict[str, Any]) -> dict[str, Any]:
    """Return a review-safe body without echoing an entire manuscript."""
    out: dict[str, Any] = {}
    for key, value in body.items():
        if (
            key == "content"
            or (key == "body" and isinstance(value, str) and len(value) > 2_000)
        ) and isinstance(value, str):
            out[key] = {
                "length": len(value),
                "sha256": hashlib.sha256(value.encode("utf-8")).hexdigest(),
                "preview": value[:500],
            }
        elif key == "content_base64" and isinstance(value, str):
            out[key] = {"base64_length": len(value)}
        else:
            out[key] = value
    return out


def _preview(value: Any, limit: int) -> str:
    text = str(value or "")
    return text if len(text) <= limit else text[:limit] + "…"


def _bounded_sequence(values: list[Any], limit: int = 50) -> dict[str, Any]:
    """Return a deterministic bounded review of a potentially large id list."""
    return {
        "items": values[:limit],
        "total": len(values),
        "truncated": max(0, len(values) - limit),
    }


_TIMELINE_COMMAND_FIELDS: dict[str, set[str]] = {
    "create_lane": {
        "kind", "expected_revision", "name", "color_label", "index",
    },
    "update_lane": {
        "kind", "expected_revision", "lane_id", "name", "color_label",
        "collapsed", "index",
    },
    "delete_lane": {"kind", "expected_revision", "lane_id"},
    "place_event": {
        "kind", "expected_revision", "scene_id", "lane_id", "index",
    },
    "remove_event": {"kind", "expected_revision", "scene_id"},
    "set_order_mode": {"kind", "expected_revision", "mode"},
    "create_link": {
        "kind", "expected_revision", "source_scene_id", "target_scene_id",
        "link_type", "color_label", "label",
    },
    "update_link": {
        "kind", "expected_revision", "link_id", "link_type", "color_label",
        "label",
    },
    "delete_link": {"kind", "expected_revision", "link_id"},
    "create_structure_link": {
        "kind", "expected_revision", "source_scene_id", "target_type",
        "target_ref",
    },
    "update_structure_link": {
        "kind", "expected_revision", "structure_link_id", "target_type",
        "target_ref",
    },
    "delete_structure_link": {
        "kind", "expected_revision", "structure_link_id",
    },
}

_TIMELINE_LINK_TYPES = frozenset({
    "custom",
    "causality",
    "setup_payoff",
    "echo",
    "conflict",
    "dependency",
})
_TIMELINE_STRUCTURE_TARGET_TYPES = frozenset({"act", "chapter"})

_CANVAS_PLOT_COMMAND_FIELDS: dict[str, set[str]] = {
    "create_node": {
        "kind", "expected_revision", "title", "body", "x", "y", "width",
        "height", "color_label", "group_label", "scene_id", "index",
    },
    "update_node": {
        "kind", "expected_revision", "node_id", "title", "body", "x", "y",
        "width", "height", "color_label", "group_label", "scene_id", "index",
    },
    "delete_node": {"kind", "expected_revision", "node_id"},
    "create_link": {
        "kind", "expected_revision", "source_node_id", "target_node_id",
        "label", "color_label", "link_type",
    },
    "update_link": {
        "kind", "expected_revision", "link_id", "label", "color_label",
        "link_type",
    },
    "delete_link": {"kind", "expected_revision", "link_id"},
    "create_frame": {
        "kind", "expected_revision", "title", "color_label", "x", "y",
        "width", "height",
    },
    "update_frame": {
        "kind", "expected_revision", "frame_id", "title", "color_label", "x",
        "y", "width", "height",
    },
    "delete_frame": {"kind", "expected_revision", "frame_id"},
}

_KNOWLEDGE_GRAPH_COMMAND_FIELDS: dict[str, set[str]] = {
    kind: {
        "kind", "expected_revision", "source", "target", "edge_type",
    }
    for kind in ("confirm_edge", "hide_edge", "unhide_edge")
}

_CONTINUITY_COMMAND_FIELDS: dict[str, set[str]] = {
    kind: {
        "kind", "expected_revision", "issue_id", "expected_issue_fingerprint",
    }
    for kind in ("defer_issue", "dismiss_issue", "resolve_issue")
}

_PROGRESSION_COMMAND_FIELDS: dict[str, set[str]] = {
    "create_track": {
        "kind", "expected_revision", "track_kind", "title", "description",
        "color_label", "primary_psyke_entry_id", "secondary_psyke_entry_id",
        "index",
    },
    "update_track": {
        "kind", "expected_revision", "track_id", "track_kind", "title",
        "description", "color_label", "primary_psyke_entry_id",
        "secondary_psyke_entry_id",
    },
    "delete_track": {"kind", "expected_revision", "track_id"},
    "reorder_tracks": {"kind", "expected_revision", "track_ids"},
    "create_beat": {
        "kind", "expected_revision", "track_id", "text", "anchor_kind",
        "scene_id", "anchor_ref", "anchor_label", "index",
    },
    "update_beat": {
        "kind", "expected_revision", "beat_id", "text", "anchor_kind",
        "scene_id", "anchor_ref", "anchor_label",
    },
    "delete_beat": {"kind", "expected_revision", "beat_id"},
    "reorder_beats": {
        "kind", "expected_revision", "track_id", "beat_ids",
    },
}

_PROGRESSION_TRACK_KINDS = frozenset({
    "story", "character", "relationship", "theme", "world", "custom",
})
_PROGRESSION_ANCHOR_KINDS = frozenset({
    "unanchored", "scene", "document_block",
})


def _timeline_revision(value: Any) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(char not in "0123456789abcdef" for char in value)
    ):
        raise GatewayError(
            "expected_revision must be the exact 64-character lowercase "
            "revision returned by logosforge_get_timeline."
        )
    return value


def _timeline_integer(
    value: Any,
    name: str,
    *,
    minimum: int,
    nullable: bool = False,
) -> int | None:
    if nullable and value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        qualifier = "positive " if minimum == 1 else "non-negative "
        null_note = " or null" if nullable else ""
        raise GatewayError(f"{name} must be a {qualifier}integer{null_note}.")
    return value


def _timeline_string(
    value: Any,
    name: str,
    *,
    maximum: int,
    nonempty: bool = False,
) -> str:
    if not isinstance(value, str) or (nonempty and not value.strip()):
        qualifier = "non-empty " if nonempty else ""
        raise GatewayError(f"{name} must be a {qualifier}string.")
    if len(value) > maximum:
        raise GatewayError(f"{name} may contain at most {maximum} characters.")
    return value.strip() if nonempty else value


def _normalize_timeline_command(command: dict[str, Any]) -> dict[str, Any]:
    """Validate and copy the bounded Timeline command vocabulary.

    This intentionally stays independent of ``logosforge.api.schemas``.  The
    packaged MCP companion is a lean HTTP client and must not pull FastAPI,
    SQLModel, or database modules into its frozen dependency graph.
    """
    if not isinstance(command, dict):
        raise GatewayError("Timeline command must be an object.")
    kind = command.get("kind")
    if not isinstance(kind, str) or kind not in _TIMELINE_COMMAND_FIELDS:
        raise GatewayError(
            "Timeline command kind must be one of: "
            + ", ".join(sorted(_TIMELINE_COMMAND_FIELDS))
            + "."
        )
    extra = sorted(set(command) - _TIMELINE_COMMAND_FIELDS[kind])
    if extra:
        raise GatewayError(
            "Unexpected Timeline command field(s): " + ", ".join(extra) + "."
        )
    if "expected_revision" not in command:
        raise GatewayError("Timeline command requires expected_revision.")

    normalized: dict[str, Any] = {
        "kind": kind,
        "expected_revision": _timeline_revision(command["expected_revision"]),
    }
    if kind == "create_lane":
        if "name" not in command:
            raise GatewayError("create_lane requires name.")
        normalized["name"] = _timeline_string(
            command["name"], "name", maximum=500, nonempty=True,
        )
        if "color_label" in command:
            normalized["color_label"] = _timeline_string(
                command["color_label"], "color_label", maximum=100,
            )
        if "index" in command:
            normalized["index"] = _timeline_integer(
                command["index"], "index", minimum=0, nullable=True,
            )
    elif kind == "update_lane":
        if "lane_id" not in command:
            raise GatewayError("update_lane requires lane_id.")
        normalized["lane_id"] = _timeline_integer(
            command["lane_id"], "lane_id", minimum=1,
        )
        updates = {"name", "color_label", "collapsed", "index"}.intersection(command)
        if not updates:
            raise GatewayError("update_lane must change at least one field.")
        if "name" in command:
            normalized["name"] = _timeline_string(
                command["name"], "name", maximum=500, nonempty=True,
            )
        if "color_label" in command:
            normalized["color_label"] = _timeline_string(
                command["color_label"], "color_label", maximum=100,
            )
        if "collapsed" in command:
            if not isinstance(command["collapsed"], bool):
                raise GatewayError("collapsed must be a boolean.")
            normalized["collapsed"] = command["collapsed"]
        if "index" in command:
            normalized["index"] = _timeline_integer(
                command["index"], "index", minimum=0,
            )
    elif kind == "delete_lane":
        if "lane_id" not in command:
            raise GatewayError("delete_lane requires lane_id.")
        normalized["lane_id"] = _timeline_integer(
            command["lane_id"], "lane_id", minimum=1,
        )
    elif kind == "place_event":
        if "scene_id" not in command or "lane_id" not in command:
            raise GatewayError(
                "place_event requires scene_id and lane_id; null lane_id means "
                "the virtual Unassigned lane."
            )
        normalized["scene_id"] = _timeline_integer(
            command["scene_id"], "scene_id", minimum=1,
        )
        normalized["lane_id"] = _timeline_integer(
            command["lane_id"], "lane_id", minimum=1, nullable=True,
        )
        if "index" in command:
            normalized["index"] = _timeline_integer(
                command["index"], "index", minimum=0, nullable=True,
            )
    elif kind == "remove_event":
        if "scene_id" not in command:
            raise GatewayError("remove_event requires scene_id.")
        normalized["scene_id"] = _timeline_integer(
            command["scene_id"], "scene_id", minimum=1,
        )
    elif kind == "set_order_mode":
        mode = command.get("mode")
        if mode not in {"structural", "custom"}:
            raise GatewayError("mode must be 'structural' or 'custom'.")
        normalized["mode"] = mode
    elif kind == "create_link":
        if "source_scene_id" not in command or "target_scene_id" not in command:
            raise GatewayError(
                "create_link requires source_scene_id and target_scene_id."
            )
        normalized["source_scene_id"] = _timeline_integer(
            command["source_scene_id"], "source_scene_id", minimum=1,
        )
        normalized["target_scene_id"] = _timeline_integer(
            command["target_scene_id"], "target_scene_id", minimum=1,
        )
        if normalized["source_scene_id"] == normalized["target_scene_id"]:
            raise GatewayError("A Timeline event cannot link to itself.")
        if "link_type" in command:
            link_type = command["link_type"]
            if link_type not in _TIMELINE_LINK_TYPES:
                raise GatewayError(
                    "link_type must be one of: "
                    + ", ".join(sorted(_TIMELINE_LINK_TYPES))
                    + "."
                )
            normalized["link_type"] = link_type
        if "color_label" in command:
            normalized["color_label"] = _timeline_string(
                command["color_label"], "color_label", maximum=100,
            )
        if "label" in command:
            normalized["label"] = _timeline_string(
                command["label"], "label", maximum=500,
            )
    elif kind == "update_link":
        if "link_id" not in command:
            raise GatewayError("update_link requires link_id.")
        normalized["link_id"] = _timeline_integer(
            command["link_id"], "link_id", minimum=1,
        )
        updates = {"link_type", "color_label", "label"}.intersection(command)
        if not updates:
            raise GatewayError("update_link must change at least one field.")
        if "link_type" in command:
            link_type = command["link_type"]
            if link_type not in _TIMELINE_LINK_TYPES:
                raise GatewayError(
                    "link_type must be one of: "
                    + ", ".join(sorted(_TIMELINE_LINK_TYPES))
                    + "."
                )
            normalized["link_type"] = link_type
        if "color_label" in command:
            normalized["color_label"] = _timeline_string(
                command["color_label"], "color_label", maximum=100,
            )
        if "label" in command:
            normalized["label"] = _timeline_string(
                command["label"], "label", maximum=500,
            )
    elif kind == "delete_link":
        if "link_id" not in command:
            raise GatewayError("delete_link requires link_id.")
        normalized["link_id"] = _timeline_integer(
            command["link_id"], "link_id", minimum=1,
        )
    elif kind == "create_structure_link":
        required = {"source_scene_id", "target_type", "target_ref"}
        if not required.issubset(command):
            raise GatewayError(
                "create_structure_link requires source_scene_id, target_type, "
                "and target_ref."
            )
        normalized["source_scene_id"] = _timeline_integer(
            command["source_scene_id"], "source_scene_id", minimum=1,
        )
        target_type = command["target_type"]
        if target_type not in _TIMELINE_STRUCTURE_TARGET_TYPES:
            raise GatewayError("target_type must be 'act' or 'chapter'.")
        normalized["target_type"] = target_type
        normalized["target_ref"] = _timeline_string(
            command["target_ref"], "target_ref", maximum=500, nonempty=True,
        )
    elif kind == "update_structure_link":
        if "structure_link_id" not in command:
            raise GatewayError(
                "update_structure_link requires structure_link_id."
            )
        normalized["structure_link_id"] = _timeline_integer(
            command["structure_link_id"], "structure_link_id", minimum=1,
        )
        updates = {"target_type", "target_ref"}.intersection(command)
        if not updates:
            raise GatewayError(
                "update_structure_link must change at least one field."
            )
        if "target_type" in command:
            target_type = command["target_type"]
            if target_type not in _TIMELINE_STRUCTURE_TARGET_TYPES:
                raise GatewayError("target_type must be 'act' or 'chapter'.")
            normalized["target_type"] = target_type
        if "target_ref" in command:
            normalized["target_ref"] = _timeline_string(
                command["target_ref"], "target_ref", maximum=500,
                nonempty=True,
            )
    else:
        if "structure_link_id" not in command:
            raise GatewayError(
                "delete_structure_link requires structure_link_id."
            )
        normalized["structure_link_id"] = _timeline_integer(
            command["structure_link_id"], "structure_link_id", minimum=1,
        )
    return normalized


def _canvas_plot_revision(value: Any) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(char not in "0123456789abcdef" for char in value)
    ):
        raise GatewayError(
            "expected_revision must be the exact 64-character lowercase "
            "revision returned by logosforge_get_canvas_plot."
        )
    return value


def _knowledge_graph_revision(value: Any) -> str:
    if (
        not isinstance(value, str)
        or _LOWER_SHA256_RE.fullmatch(value) is None
    ):
        raise GatewayError(
            "expected_revision must be the exact 64-character lowercase "
            "revision returned by logosforge_get_knowledge_graph or "
            "logosforge_get_knowledge_graph_hidden_edges."
        )
    return value


def _canvas_plot_integer(
    value: Any,
    name: str,
    *,
    minimum: int,
    nullable: bool = False,
) -> int | None:
    if nullable and value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        qualifier = "positive " if minimum == 1 else "non-negative "
        null_note = " or null" if nullable else ""
        raise GatewayError(f"{name} must be a {qualifier}integer{null_note}.")
    return value


def _canvas_plot_string(value: Any, name: str, *, maximum: int) -> str:
    if not isinstance(value, str):
        raise GatewayError(f"{name} must be a string.")
    if len(value) > maximum:
        raise GatewayError(f"{name} may contain at most {maximum} characters.")
    return value


def _canvas_plot_number(
    value: Any,
    name: str,
    *,
    positive: bool = False,
) -> int | float:
    try:
        finite = math.isfinite(value)
    except (OverflowError, TypeError):
        finite = False
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not finite:
        raise GatewayError(f"{name} must be a finite number.")
    if positive and value <= 0:
        raise GatewayError(f"{name} must be greater than zero.")
    # Core's strict command DTO and receipt digest both use floats for Canvas
    # geometry. Keep the reviewed wire body and recovery digest identical.
    return float(value)


def _normalize_canvas_plot_command(command: dict[str, Any]) -> dict[str, Any]:
    """Validate and copy the complete transactional Canvas Plot vocabulary.

    Keep this independent of the FastAPI/Pydantic models so the frozen MCP
    companion remains a lean HTTP client.
    """
    if not isinstance(command, dict):
        raise GatewayError("Canvas Plot command must be an object.")
    kind = command.get("kind")
    if not isinstance(kind, str) or kind not in _CANVAS_PLOT_COMMAND_FIELDS:
        raise GatewayError(
            "Canvas Plot command kind must be one of: "
            + ", ".join(sorted(_CANVAS_PLOT_COMMAND_FIELDS))
            + "."
        )
    extra = sorted(set(command) - _CANVAS_PLOT_COMMAND_FIELDS[kind])
    if extra:
        raise GatewayError(
            "Unexpected Canvas Plot command field(s): " + ", ".join(extra) + "."
        )
    if "expected_revision" not in command:
        raise GatewayError("Canvas Plot command requires expected_revision.")

    normalized: dict[str, Any] = {
        "kind": kind,
        "expected_revision": _canvas_plot_revision(command["expected_revision"]),
    }

    node_strings = {
        "title": 500,
        "body": 100_000,
        "color_label": 100,
        "group_label": 500,
    }
    node_numbers = {"x": False, "y": False, "width": True, "height": True}
    frame_strings = {"title": 500, "color_label": 100}
    frame_numbers = {"x": False, "y": False, "width": True, "height": True}

    if kind in {"create_node", "update_node"}:
        if kind == "update_node":
            if "node_id" not in command:
                raise GatewayError("update_node requires node_id.")
            normalized["node_id"] = _canvas_plot_integer(
                command["node_id"], "node_id", minimum=1,
            )
            updates = set(node_strings) | set(node_numbers) | {"scene_id", "index"}
            if not updates.intersection(command):
                raise GatewayError("update_node must change at least one field.")
        for field, maximum in node_strings.items():
            if field in command:
                if command[field] is None:
                    raise GatewayError(f"{field} must not be null.")
                normalized[field] = _canvas_plot_string(
                    command[field], field, maximum=maximum,
                )
        for field, positive in node_numbers.items():
            if field in command:
                if command[field] is None:
                    raise GatewayError(f"{field} must not be null.")
                normalized[field] = _canvas_plot_number(
                    command[field], field, positive=positive,
                )
        if "scene_id" in command:
            normalized["scene_id"] = _canvas_plot_integer(
                command["scene_id"], "scene_id", minimum=1, nullable=True,
            )
        if "index" in command:
            normalized["index"] = _canvas_plot_integer(
                command["index"], "index", minimum=0,
                nullable=kind == "create_node",
            )
    elif kind == "delete_node":
        if "node_id" not in command:
            raise GatewayError("delete_node requires node_id.")
        normalized["node_id"] = _canvas_plot_integer(
            command["node_id"], "node_id", minimum=1,
        )
    elif kind == "create_link":
        for field in ("source_node_id", "target_node_id"):
            if field not in command:
                raise GatewayError(
                    "create_link requires source_node_id and target_node_id."
                )
            normalized[field] = _canvas_plot_integer(
                command[field], field, minimum=1,
            )
        for field, maximum in {
            "label": 500, "color_label": 100, "link_type": 100,
        }.items():
            if field in command:
                normalized[field] = _canvas_plot_string(
                    command[field], field, maximum=maximum,
                )
    elif kind == "update_link":
        if "link_id" not in command:
            raise GatewayError("update_link requires link_id.")
        normalized["link_id"] = _canvas_plot_integer(
            command["link_id"], "link_id", minimum=1,
        )
        updates = {"label", "color_label", "link_type"}.intersection(command)
        if not updates:
            raise GatewayError("update_link must change at least one field.")
        for field, maximum in {
            "label": 500, "color_label": 100, "link_type": 100,
        }.items():
            if field in command:
                if command[field] is None:
                    raise GatewayError(f"{field} must not be null.")
                normalized[field] = _canvas_plot_string(
                    command[field], field, maximum=maximum,
                )
    elif kind == "delete_link":
        if "link_id" not in command:
            raise GatewayError("delete_link requires link_id.")
        normalized["link_id"] = _canvas_plot_integer(
            command["link_id"], "link_id", minimum=1,
        )
    elif kind in {"create_frame", "update_frame"}:
        if kind == "update_frame":
            if "frame_id" not in command:
                raise GatewayError("update_frame requires frame_id.")
            normalized["frame_id"] = _canvas_plot_integer(
                command["frame_id"], "frame_id", minimum=1,
            )
            updates = set(frame_strings) | set(frame_numbers)
            if not updates.intersection(command):
                raise GatewayError("update_frame must change at least one field.")
        for field, maximum in frame_strings.items():
            if field in command:
                if command[field] is None:
                    raise GatewayError(f"{field} must not be null.")
                normalized[field] = _canvas_plot_string(
                    command[field], field, maximum=maximum,
                )
        for field, positive in frame_numbers.items():
            if field in command:
                if command[field] is None:
                    raise GatewayError(f"{field} must not be null.")
                normalized[field] = _canvas_plot_number(
                    command[field], field, positive=positive,
                )
    else:
        if "frame_id" not in command:
            raise GatewayError("delete_frame requires frame_id.")
        normalized["frame_id"] = _canvas_plot_integer(
            command["frame_id"], "frame_id", minimum=1,
        )
    return normalized


def _normalize_knowledge_graph_command(
    command: dict[str, Any],
) -> dict[str, Any]:
    """Validate the complete transactional graph review vocabulary."""
    if not isinstance(command, dict):
        raise GatewayError("Knowledge Graph command must be an object.")
    kind = command.get("kind")
    if (
        not isinstance(kind, str)
        or kind not in _KNOWLEDGE_GRAPH_COMMAND_FIELDS
    ):
        raise GatewayError(
            "Knowledge Graph command kind must be one of: "
            + ", ".join(sorted(_KNOWLEDGE_GRAPH_COMMAND_FIELDS))
            + "."
        )
    extra = sorted(set(command) - _KNOWLEDGE_GRAPH_COMMAND_FIELDS[kind])
    if extra:
        raise GatewayError(
            "Unexpected Knowledge Graph command field(s): "
            + ", ".join(extra)
            + "."
        )
    missing = [
        field
        for field in ("expected_revision", "source", "target", "edge_type")
        if field not in command
    ]
    if missing:
        raise GatewayError(
            "Knowledge Graph command requires: " + ", ".join(missing) + "."
        )

    normalized: dict[str, Any] = {
        "kind": kind,
        "expected_revision": _knowledge_graph_revision(
            command["expected_revision"],
        ),
    }
    for field_name, maximum in (
        ("source", 512), ("target", 512), ("edge_type", 128),
    ):
        value = command[field_name]
        if not isinstance(value, str) or not value or len(value) > maximum:
            raise GatewayError(
                f"{field_name} must contain 1-{maximum} characters."
            )
        normalized[field_name] = value
    return normalized


def _normalize_continuity_command(
    command: dict[str, Any],
) -> dict[str, Any]:
    """Validate the complete transactional Continuity review vocabulary."""
    if not isinstance(command, dict):
        raise GatewayError("Continuity command must be an object.")
    kind = command.get("kind")
    if not isinstance(kind, str) or kind not in _CONTINUITY_COMMAND_FIELDS:
        raise GatewayError(
            "Continuity command kind must be one of: "
            + ", ".join(sorted(_CONTINUITY_COMMAND_FIELDS))
            + "."
        )
    extra = sorted(set(command) - _CONTINUITY_COMMAND_FIELDS[kind])
    if extra:
        raise GatewayError(
            "Unexpected Continuity command field(s): "
            + ", ".join(extra)
            + "."
        )
    missing = [
        field
        for field in (
            "expected_revision", "issue_id", "expected_issue_fingerprint",
        )
        if field not in command
    ]
    if missing:
        raise GatewayError(
            "Continuity command requires: " + ", ".join(missing) + "."
        )
    expected_revision = command["expected_revision"]
    if (
        not isinstance(expected_revision, str)
        or _LOWER_SHA256_RE.fullmatch(expected_revision) is None
    ):
        raise GatewayError(
            "expected_revision must be the exact 64-character lowercase "
            "review revision returned by the Continuity report."
        )
    issue_id = command["issue_id"]
    if (
        not isinstance(issue_id, str)
        or re.fullmatch(r"[0-9a-f]{16}", issue_id) is None
    ):
        raise GatewayError("issue_id must be a 16-character lowercase hex id.")
    fingerprint = command["expected_issue_fingerprint"]
    if (
        not isinstance(fingerprint, str)
        or _LOWER_SHA256_RE.fullmatch(fingerprint) is None
    ):
        raise GatewayError(
            "expected_issue_fingerprint must be the exact 64-character "
            "lowercase fingerprint returned for the reviewed issue."
        )
    return {
        "kind": kind,
        "expected_revision": expected_revision,
        "issue_id": issue_id,
        "expected_issue_fingerprint": fingerprint,
    }


def _progression_revision(value: Any) -> str:
    if not isinstance(value, str) or _LOWER_SHA256_RE.fullmatch(value) is None:
        raise GatewayError(
            "expected_revision must be the exact 64-character lowercase "
            "revision returned by logosforge_get_progressions."
        )
    return value


def _progression_integer(
    value: Any,
    name: str,
    *,
    minimum: int = 1,
    nullable: bool = False,
) -> int | None:
    if nullable and value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        qualifier = "positive" if minimum == 1 else "non-negative"
        suffix = " or null" if nullable else ""
        raise GatewayError(f"{name} must be a {qualifier} integer{suffix}.")
    return value


def _progression_string(
    value: Any,
    name: str,
    *,
    maximum: int,
    nonempty: bool = False,
    nullable: bool = False,
) -> str | None:
    if nullable and value is None:
        return None
    if not isinstance(value, str) or (nonempty and not value.strip()):
        qualifier = "non-empty " if nonempty else ""
        suffix = " or null" if nullable else ""
        raise GatewayError(f"{name} must be a {qualifier}string{suffix}.")
    if len(value) > maximum:
        raise GatewayError(f"{name} may contain at most {maximum} characters.")
    # Whitespace is meaningful in beat prose.  Use ``strip`` only to reject an
    # all-whitespace required field; preserve the caller's exact validated
    # value so proposal review, receipt identity, and Core persistence agree.
    return value


def _progression_id_list(value: Any, name: str) -> list[int]:
    if not isinstance(value, list) or any(
        isinstance(item, bool) or not isinstance(item, int) or item < 1
        for item in value
    ):
        raise GatewayError(f"{name} must be an array of positive integers.")
    if len(value) != len(set(value)):
        raise GatewayError(f"{name} must not contain duplicate ids.")
    return list(value)


def _normalize_progression_command(command: dict[str, Any]) -> dict[str, Any]:
    """Validate and copy the complete transactional Progressions vocabulary."""
    if not isinstance(command, dict):
        raise GatewayError("Progressions command must be an object.")
    kind = command.get("kind")
    if not isinstance(kind, str) or kind not in _PROGRESSION_COMMAND_FIELDS:
        raise GatewayError(
            "Progressions command kind must be one of: "
            + ", ".join(sorted(_PROGRESSION_COMMAND_FIELDS))
            + "."
        )
    extra = sorted(set(command) - _PROGRESSION_COMMAND_FIELDS[kind])
    if extra:
        raise GatewayError(
            "Unexpected Progressions command field(s): "
            + ", ".join(extra)
            + "."
        )
    if "expected_revision" not in command:
        raise GatewayError("Progressions command requires expected_revision.")
    normalized: dict[str, Any] = {
        "kind": kind,
        "expected_revision": _progression_revision(command["expected_revision"]),
    }

    if kind in {"create_track", "update_track"}:
        if kind == "update_track":
            if "track_id" not in command:
                raise GatewayError("update_track requires track_id.")
            normalized["track_id"] = _progression_integer(
                command["track_id"], "track_id",
            )
            if not {
                "track_kind", "title", "description", "color_label",
                "primary_psyke_entry_id", "secondary_psyke_entry_id",
            }.intersection(command):
                raise GatewayError("update_track must change at least one field.")
        else:
            if "track_kind" not in command or "title" not in command:
                raise GatewayError("create_track requires track_kind and title.")
            if "index" in command:
                normalized["index"] = _progression_integer(
                    command["index"], "index", minimum=0, nullable=True,
                )
        if "track_kind" in command:
            track_kind = command["track_kind"]
            if track_kind not in _PROGRESSION_TRACK_KINDS:
                raise GatewayError(
                    "track_kind must be one of: "
                    + ", ".join(sorted(_PROGRESSION_TRACK_KINDS))
                    + "."
                )
            normalized["track_kind"] = track_kind
        for field, maximum, nonempty in (
            ("title", 500, True),
            ("description", 10_000, False),
            ("color_label", 100, False),
        ):
            if field in command:
                normalized[field] = _progression_string(
                    command[field], field, maximum=maximum, nonempty=nonempty,
                )
        for field in ("primary_psyke_entry_id", "secondary_psyke_entry_id"):
            if field in command:
                normalized[field] = _progression_integer(
                    command[field], field, nullable=True,
                )
    elif kind == "delete_track":
        if "track_id" not in command:
            raise GatewayError("delete_track requires track_id.")
        normalized["track_id"] = _progression_integer(
            command["track_id"], "track_id",
        )
    elif kind == "reorder_tracks":
        if "track_ids" not in command:
            raise GatewayError("reorder_tracks requires track_ids.")
        normalized["track_ids"] = _progression_id_list(
            command["track_ids"], "track_ids",
        )
    elif kind in {"create_beat", "update_beat"}:
        if kind == "create_beat":
            if "track_id" not in command or "text" not in command:
                raise GatewayError("create_beat requires track_id and text.")
            normalized["track_id"] = _progression_integer(
                command["track_id"], "track_id",
            )
            if "index" in command:
                normalized["index"] = _progression_integer(
                    command["index"], "index", minimum=0, nullable=True,
                )
        else:
            if "beat_id" not in command:
                raise GatewayError("update_beat requires beat_id.")
            normalized["beat_id"] = _progression_integer(
                command["beat_id"], "beat_id",
            )
            if not {
                "text", "anchor_kind", "scene_id", "anchor_ref", "anchor_label",
            }.intersection(command):
                raise GatewayError("update_beat must change at least one field.")
        if "text" in command:
            normalized["text"] = _progression_string(
                command["text"], "text", maximum=50_000, nonempty=True,
            )
        if "anchor_kind" in command:
            anchor_kind = command["anchor_kind"]
            if anchor_kind not in _PROGRESSION_ANCHOR_KINDS:
                raise GatewayError(
                    "anchor_kind must be unanchored, scene, or document_block."
                )
            normalized["anchor_kind"] = anchor_kind
        if "scene_id" in command:
            normalized["scene_id"] = _progression_integer(
                command["scene_id"], "scene_id", nullable=True,
            )
        if "anchor_ref" in command:
            normalized["anchor_ref"] = _progression_string(
                command["anchor_ref"], "anchor_ref", maximum=1_000,
                nullable=True,
            )
        if "anchor_label" in command:
            normalized["anchor_label"] = _progression_string(
                command["anchor_label"], "anchor_label", maximum=500,
            )
    elif kind == "delete_beat":
        if "beat_id" not in command:
            raise GatewayError("delete_beat requires beat_id.")
        normalized["beat_id"] = _progression_integer(
            command["beat_id"], "beat_id",
        )
    else:
        if "track_id" not in command or "beat_ids" not in command:
            raise GatewayError("reorder_beats requires track_id and beat_ids.")
        normalized["track_id"] = _progression_integer(
            command["track_id"], "track_id",
        )
        normalized["beat_ids"] = _progression_id_list(
            command["beat_ids"], "beat_ids",
        )
    return normalized


@dataclass
class Proposal:
    proposal_id: str
    operation: str
    method: str
    path: str
    body: dict[str, Any]
    summary: str
    project_id: int | None
    created_at: float
    expires_at: float
    request_digest: str = ""
    guard_path: str = ""
    guard_digest: str = ""
    review: dict[str, Any] = field(default_factory=dict)
    # ``indeterminate`` is terminal because no durable protocol proved that a
    # retry is safe. ``recovery_pending`` is reserved for Timeline, Canvas Plot,
    # Knowledge Graph, Continuity, and Progressions commands: Core proved receipt support, so
    # the same proposal id may be reconciled or resent later.
    state: str = "pending"  # pending | applying | recovery_pending | applied | failed | indeterminate | discarded
    result: Any = None
    receipt: dict[str, Any] | None = None
    recovered_from_core: bool = False
    timeline_resend_attempted: bool = False
    timeline_receipt_observed: bool = False
    canvas_plot_resend_attempted: bool = False
    canvas_plot_receipt_observed: bool = False
    knowledge_graph_resend_attempted: bool = False
    knowledge_graph_receipt_observed: bool = False
    continuity_resend_attempted: bool = False
    continuity_receipt_observed: bool = False
    progression_resend_attempted: bool = False
    progression_receipt_observed: bool = False
    error: str = ""

    def public(self, include_result: bool = False) -> dict[str, Any]:
        out = {
            "proposal_id": self.proposal_id,
            "operation": self.operation,
            "summary": self.summary,
            "project_id": self.project_id,
            "state": self.state,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "request_digest": self.request_digest,
            "request": {
                "method": self.method,
                "path": self.path,
                "body": _compact_body(self.body),
            },
            "review": self.review,
            "requires_user_approval": True,
        }
        if self.error:
            out["error"] = self.error
        if self.receipt is not None:
            out["receipt"] = copy.deepcopy(self.receipt)
        if self.recovered_from_core:
            out["recovered_from_core"] = True
        if include_result and self.result is not None:
            out["result"] = self.result
        return out


class LogosForgeMcpGateway:
    """A per-MCP-session gateway over one authenticated LogosForge API."""

    def __init__(
        self,
        client: LogosForgeApiClient,
        *,
        allow_writes: bool = False,
        require_auth_for_writes: bool = True,
        proposal_ttl_seconds: int = 900,
    ) -> None:
        self.client = client
        self.allow_writes = bool(allow_writes)
        self.require_auth_for_writes = bool(require_auth_for_writes)
        self.proposal_ttl_seconds = max(60, min(int(proposal_ttl_seconds), 86_400))
        self._proposals: dict[str, Proposal] = {}
        self._lock = threading.RLock()

    # -- Project selection and reads -------------------------------------

    def _project_id(self) -> int:
        if self.client.project_id is not None:
            return self.client.project_id
        projects = self.client.list_projects()
        if len(projects) == 1:
            self.client.select_project(int(projects[0]["id"]))
            return self.client.require_project_id()
        raise GatewayError(
            "No project is selected. Call logosforge_list_projects and "
            "logosforge_select_project first."
        )

    def list_projects(self) -> dict[str, Any]:
        projects = self.client.list_projects()
        return {"projects": projects, "selected_project_id": self.client.project_id}

    def select_project(self, project_id: int) -> dict[str, Any]:
        project = self.client.select_project(project_id)
        return {"selected_project_id": int(project_id), "project": project}

    def get_project(self) -> dict:
        return self.client.get_project(self._project_id())

    def list_scenes(self, include_content: bool = False) -> list[dict]:
        scenes = self.client.list_scenes(self._project_id())
        if include_content:
            return scenes
        compact = []
        for scene in scenes:
            item = dict(scene)
            content = str(item.pop("content", "") or "")
            item["content_length"] = len(content)
            compact.append(item)
        return compact

    def get_scene(self, scene_id: int) -> dict:
        return self.client.get_scene(scene_id, self._project_id())

    def get_outline(self) -> list[dict]:
        return self.client.get_outline(self._project_id())

    def get_timeline(self) -> dict[str, Any]:
        return self.client.get_timeline(self._project_id())

    def get_canvas_plot(self, include_bodies: bool = False) -> dict[str, Any]:
        snapshot = copy.deepcopy(self.client.get_canvas_plot(self._project_id()))
        if include_bodies or not isinstance(snapshot, dict):
            return snapshot
        nodes = snapshot.get("nodes")
        if not isinstance(nodes, list):
            return snapshot
        for node in nodes:
            if not isinstance(node, dict):
                continue
            body = str(node.pop("body", "") or "")
            node["body_length"] = len(body)
            node["body_sha256"] = hashlib.sha256(body.encode("utf-8")).hexdigest()
            node["body_preview"] = _preview(body, 500)
        return snapshot

    def get_continuity(self) -> dict[str, Any]:
        return self.client.get_continuity(self._project_id())

    def get_knowledge_graph(
        self,
        *,
        focus_key: str | None = None,
        depth: int = 1,
        limit: int = 100,
        include_inferred: bool = True,
        view_mode: str = "project_map",
    ) -> dict[str, Any]:
        """Return one bounded canonical graph view or focused neighborhood."""
        if focus_key is not None and (
            not isinstance(focus_key, str)
            or not focus_key
            or len(focus_key) > 512
        ):
            raise GatewayError("focus_key must contain 1-512 characters.")
        if isinstance(depth, bool) or not isinstance(depth, int) or depth not in {1, 2}:
            raise GatewayError("Knowledge Graph depth must be 1 or 2.")
        if (
            isinstance(limit, bool)
            or not isinstance(limit, int)
            or not 1 <= limit <= 200
        ):
            raise GatewayError("Knowledge Graph limit must be between 1 and 200.")
        if not isinstance(include_inferred, bool):
            raise GatewayError("include_inferred must be a boolean.")
        if (
            not isinstance(view_mode, str)
            or view_mode not in KNOWLEDGE_GRAPH_VIEW_MODES
        ):
            raise GatewayError(
                "Knowledge Graph view_mode must be one of: "
                f"{', '.join(sorted(KNOWLEDGE_GRAPH_VIEW_MODES))}."
            )
        return self.client.get_knowledge_graph(
            self._project_id(),
            focus_key=focus_key,
            depth=depth,
            limit=limit,
            include_inferred=include_inferred,
            view_mode=view_mode,
        )

    def get_knowledge_graph_hidden_edges(
        self,
        *,
        offset: int = 0,
        limit: int = 25,
    ) -> dict[str, Any]:
        """Return one bounded page from the complete hidden-edge queue."""
        if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
            raise GatewayError("Hidden-edge offset must be zero or greater.")
        if (
            isinstance(limit, bool)
            or not isinstance(limit, int)
            or not 1 <= limit <= 100
        ):
            raise GatewayError("Hidden-edge limit must be between 1 and 100.")
        return self.client.get_knowledge_graph_hidden_edges(
            self._project_id(),
            offset=offset,
            limit=limit,
        )

    def list_characters(self) -> list[dict]:
        return self.client.list_characters(self._project_id())

    def list_psyke_entries(self, entry_type: str = "") -> list[dict]:
        entries = self.client.list_psyke_entries(self._project_id())
        wanted = (entry_type or "").strip().lower().rstrip("s")
        if not wanted or wanted == "all":
            return entries
        return [e for e in entries if str(e.get("type", "")).lower() == wanted]

    def get_psyke_entry(self, entry_id: int) -> dict:
        return self.client.get_psyke_entry(entry_id, self._project_id())

    def list_psyke_relations(self) -> list[dict]:
        return self.client.list_psyke_relations(self._project_id())

    def list_psyke_progressions(self) -> list[dict]:
        return self.client.list_psyke_progressions(self._project_id())

    def get_progressions(self) -> dict[str, Any]:
        return self.client.get_progressions(self._project_id())

    def list_notes(self) -> list[dict]:
        return self.client.list_notes(self._project_id())

    def list_comments(
        self,
        include_resolved: bool = True,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        if isinstance(limit, bool) or not 1 <= int(limit) <= 200:
            raise GatewayError("Comment limit must be between 1 and 200.")
        if isinstance(offset, bool) or int(offset) < 0:
            raise GatewayError("Comment offset must be zero or greater.")
        pid = self._project_id()
        comments = self.client.list_comments(pid)
        if not include_resolved:
            comments = [comment for comment in comments if not comment.get("resolved")]
        total = len(comments)
        start = int(offset)
        page = comments[start:start + int(limit)]
        next_offset = start + len(page)
        return {
            "project_id": pid,
            "comments": page,
            "include_resolved": bool(include_resolved),
            "offset": start,
            "limit": int(limit),
            "returned": len(page),
            "total": total,
            "next_offset": next_offset if next_offset < total else None,
            "has_more": next_offset < total,
        }

    def poll_changes(self, since: int = 0) -> dict:
        return self.client.poll_events(since, self._project_id())

    def search(self, query: str) -> dict:
        pid = self._project_id()
        if not (query or "").strip():
            raise GatewayError("Search query must not be empty.")
        return self.client.search_project(query, pid)

    def live_context(self, action: str) -> dict:
        self._project_id()
        if action not in {"get_live_context", "get_active_scene", "get_current_selection"}:
            raise GatewayError("Unsupported live-context operation.")
        response = self.client.execute(action)
        if not response.get("ok"):
            raise GatewayError(str(response.get("error") or "Live context is unavailable."))
        return response.get("result") or {}

    def snapshot(self) -> dict[str, Any]:
        pid = self._project_id()
        events = self.client.poll_events(0, pid)
        notes = self.client.list_notes(pid)
        comments = self.client.list_comments(pid)
        comment_limit = 100
        return {
            "project": self.client.get_project(pid),
            "scenes": self.list_scenes(include_content=False),
            "outline": self.client.get_outline(pid),
            "characters": self.client.list_characters(pid),
            "psyke_entries": self.client.list_psyke_entries(pid),
            "psyke_relations": self.client.list_psyke_relations(pid),
            "psyke_progressions": self.client.list_psyke_progressions(pid),
            "progressions": self._progression_snapshot_summary(
                self.client.get_progressions(pid),
            ),
            "notes": [
                {
                    "id": note.get("id"), "title": note.get("title", ""),
                    "tags": note.get("tags", []), "pinned": note.get("pinned", False),
                    "content_length": len(str(note.get("content", "") or "")),
                    "scene_links": note.get("scene_links", []),
                    "psyke_links": note.get("psyke_links", []),
                }
                for note in notes
            ],
            "comment_counts": {
                "total": len(comments),
                "open": sum(1 for comment in comments if not comment.get("resolved")),
                "resolved": sum(1 for comment in comments if comment.get("resolved")),
            },
            "comments": [
                {
                    "id": comment.get("id"),
                    "revision": comment.get("revision", ""),
                    "anchor": comment.get("anchor", {}),
                    "quote_preview": _preview(comment.get("quote"), 240),
                    "body_preview": _preview(comment.get("body"), 500),
                    "body_length": len(str(comment.get("body", "") or "")),
                    "resolved": bool(comment.get("resolved")),
                    "reply_count": len(comment.get("replies", [])),
                    "created_at": comment.get("created_at"),
                    "updated_at": comment.get("updated_at"),
                }
                for comment in comments[:comment_limit]
            ],
            "comments_truncated": max(0, len(comments) - comment_limit),
            "event_cursor": events.get("cursor", 0),
        }

    @staticmethod
    def _progression_snapshot_summary(snapshot: Any) -> dict[str, Any]:
        """Keep project snapshots useful without echoing every progression beat."""
        if not isinstance(snapshot, dict):
            return {"unavailable": True}
        tracks = snapshot.get("tracks", [])
        if not isinstance(tracks, list):
            tracks = []
        return {
            "revision": snapshot.get("revision", ""),
            "summary": copy.deepcopy(snapshot.get("summary", {})),
            "tracks": [
                {
                    "id": track.get("id"),
                    "kind": track.get("kind"),
                    "title": _preview(track.get("title"), 200),
                    "primary_psyke_entry_id": track.get("primary_psyke_entry_id"),
                    "secondary_psyke_entry_id": track.get("secondary_psyke_entry_id"),
                    "coverage": copy.deepcopy(track.get("coverage", {})),
                }
                for track in tracks[:100]
                if isinstance(track, dict)
            ],
            "tracks_truncated": max(0, len(tracks) - 100),
        }

    def export_project(self, options: dict[str, Any]) -> dict:
        return self.client.export_project(options, self._project_id())

    def diagnostics(self, report: str) -> Any:
        allowed = {
            "continuity", "pacing", "balance", "health", "structure-analysis",
            "decision-radar", "plot", "timeline",
        }
        if report not in allowed:
            raise GatewayError(f"Unknown diagnostic report: {report!r}")
        return self.client.request(
            "GET", self.client.project_path(report, self._project_id())
        )

    # -- Proposal lifecycle ----------------------------------------------

    def propose_request(
        self,
        *,
        operation: str,
        method: str,
        path: str,
        body: dict[str, Any],
        summary: str,
        project_id: int | None,
        guard_path: str = "",
        review: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        guard_digest = ""
        if guard_path:
            guard_digest = _digest(self.client.request("GET", guard_path))
        stored_method = method.upper()
        stored_body = copy.deepcopy(body)
        request_digest = _digest({
            "method": stored_method,
            "path": path,
            "body": stored_body,
            "project_id": project_id,
        })
        now = time.time()
        proposal = Proposal(
            proposal_id="lfp_" + secrets.token_urlsafe(18),
            operation=operation,
            method=stored_method,
            path=path,
            body=stored_body,
            summary=summary,
            project_id=project_id,
            created_at=now,
            expires_at=now + self.proposal_ttl_seconds,
            request_digest=request_digest,
            guard_path=guard_path,
            guard_digest=guard_digest,
            review=review or {},
        )
        with self._lock:
            self._prune_expired(now)
            self._proposals[proposal.proposal_id] = proposal
        return proposal.public()

    def get_proposal(self, proposal_id: str) -> dict[str, Any]:
        with self._lock:
            proposal = self._proposals.get(proposal_id)
            if proposal is not None:
                self._expire(proposal)
                return proposal.public(include_result=True)

        # Proposals are intentionally held in memory, but transactional command
        # receipts survive an MCP gateway restart in Core. Recovery is strictly
        # scoped to the selected project; never scan projects with a capability
        # key. Probe every receipt family so a cross-family key collision can
        # never be resolved to whichever endpoint was tried first.
        return self._recover_unknown_durable_proposal(proposal_id)

    def list_proposals(self, include_finished: bool = False) -> dict[str, Any]:
        now = time.time()
        with self._lock:
            self._prune_expired(now)
            proposals = list(self._proposals.values())
            if not include_finished:
                proposals = [
                    p for p in proposals
                    if p.state in {"pending", "recovery_pending"}
                ]
            proposals.sort(key=lambda p: p.created_at)
            return {"proposals": [p.public() for p in proposals]}

    def discard_proposal(self, proposal_id: str) -> dict[str, Any]:
        with self._lock:
            proposal = self._proposal(proposal_id)
            self._expire(proposal)
            if proposal.state != "pending":
                raise GatewayError(f"Proposal is {proposal.state}, not pending.")
            proposal.state = "discarded"
            return proposal.public()

    def apply_proposal(self, proposal_id: str) -> dict[str, Any]:
        if not self.allow_writes:
            raise GatewayError(
                "Writes are disabled for this MCP server. Restart it with "
                "LOGOSFORGE_MCP_ALLOW_WRITES=1 after reviewing the security boundary."
            )
        if self.require_auth_for_writes and not self.client.has_auth_token:
            raise GatewayError(
                "Writes require an authenticated LogosForge API. Set "
                "LOGOSFORGE_API_TOKEN for both the API and MCP server."
            )

        with self._lock:
            proposal = self._proposal(proposal_id)
            if proposal.state == "pending":
                self._expire(proposal)
            recovering = (
                proposal.state == "recovery_pending"
                and (
                    self._is_timeline_proposal(proposal)
                    or self._is_canvas_plot_proposal(proposal)
                    or self._is_knowledge_graph_proposal(proposal)
                    or self._is_continuity_proposal(proposal)
                    or self._is_progression_proposal(proposal)
                )
            )
            if proposal.state != "pending" and not recovering:
                raise GatewayError(f"Proposal is {proposal.state}, not pending.")
            if (
                proposal.project_id is not None
                and self.client.project_id != proposal.project_id
            ):
                raise GatewayError(
                    "The selected project differs from this proposal's project. "
                    "Select the original project before applying it."
                )
            current_request_digest = _digest({
                "method": proposal.method,
                "path": proposal.path,
                "body": proposal.body,
                "project_id": proposal.project_id,
            })
            if current_request_digest != proposal.request_digest:
                proposal.state = "failed"
                proposal.error = "Proposal integrity check failed; create a fresh proposal."
                raise GatewayError(proposal.error)
            if proposal.guard_path and not recovering:
                current = self.client.request("GET", proposal.guard_path)
                if _digest(current) != proposal.guard_digest:
                    proposal.state = "failed"
                    proposal.error = (
                        "The target changed after this proposal was created. "
                        "Read the current state and create a new proposal."
                    )
                    raise GatewayError(proposal.error)
            # Mark before network I/O so a concurrent call cannot race the same
            # proposal. Durable recovery is safe only because the exact proposal
            # id is also Core's idempotency capability.
            proposal.state = "applying"
            proposal.error = ""

        if recovering:
            if self._is_timeline_proposal(proposal):
                return self._resume_timeline_recovery(proposal)
            if self._is_canvas_plot_proposal(proposal):
                return self._resume_canvas_plot_recovery(proposal)
            if self._is_knowledge_graph_proposal(proposal):
                return self._resume_knowledge_graph_recovery(proposal)
            if self._is_continuity_proposal(proposal):
                return self._resume_continuity_recovery(proposal)
            return self._resume_progression_recovery(proposal)

        try:
            result = self._execute_proposal_request(proposal)
        except Exception as exc:  # noqa: BLE001 - transport boundary
            if self._is_definite_http_rejection(exc):
                self._raise_rejected_apply(proposal, exc)
            if self._is_timeline_proposal(proposal):
                return self._recover_ambiguous_timeline_apply(proposal, exc)
            if self._is_canvas_plot_proposal(proposal):
                return self._recover_ambiguous_canvas_plot_apply(proposal, exc)
            if self._is_knowledge_graph_proposal(proposal):
                return self._recover_ambiguous_knowledge_graph_apply(proposal, exc)
            if self._is_continuity_proposal(proposal):
                return self._recover_ambiguous_continuity_apply(proposal, exc)
            if self._is_progression_proposal(proposal):
                return self._recover_ambiguous_progression_apply(proposal, exc)
            self._raise_indeterminate_apply(proposal, exc)

        return self._complete_proposal(proposal, result)

    @staticmethod
    def _is_definite_http_rejection(exc: Exception) -> bool:
        return (
            isinstance(exc, LogosForgeApiError)
            and exc.status_code is not None
            and 400 <= exc.status_code < 500
            and exc.status_code not in {408, 429}
        )

    def _is_timeline_proposal(self, proposal: Proposal) -> bool:
        if proposal.project_id is None or not proposal.operation.startswith("timeline_"):
            return False
        return (
            proposal.method == "POST"
            and proposal.path
            == self.client.project_path("timeline/commands", proposal.project_id)
        )

    def _is_canvas_plot_proposal(self, proposal: Proposal) -> bool:
        if (
            proposal.project_id is None
            or not proposal.operation.startswith("canvas_plot_")
        ):
            return False
        return (
            proposal.method == "POST"
            and proposal.path
            == self.client.project_path(
                "canvas-plot/commands",
                proposal.project_id,
            )
        )

    def _is_knowledge_graph_proposal(self, proposal: Proposal) -> bool:
        if (
            proposal.project_id is None
            or not proposal.operation.startswith("knowledge_graph_")
        ):
            return False
        return (
            proposal.method == "POST"
            and proposal.path
            == self.client.project_path(
                "knowledge-graph/commands",
                proposal.project_id,
            )
        )

    def _is_continuity_proposal(self, proposal: Proposal) -> bool:
        if (
            proposal.project_id is None
            or not proposal.operation.startswith("continuity_")
        ):
            return False
        return (
            proposal.method == "POST"
            and proposal.path
            == self.client.project_path(
                "continuity/commands",
                proposal.project_id,
            )
        )

    def _is_progression_proposal(self, proposal: Proposal) -> bool:
        if (
            proposal.project_id is None
            or not proposal.operation.startswith("progression_")
        ):
            return False
        return (
            proposal.method == "POST"
            and proposal.path
            == self.client.project_path(
                "progressions/commands",
                proposal.project_id,
            )
        )

    def _execute_proposal_request(self, proposal: Proposal) -> Any:
        if (
            self._is_timeline_proposal(proposal)
            or self._is_canvas_plot_proposal(proposal)
            or self._is_knowledge_graph_proposal(proposal)
            or self._is_continuity_proposal(proposal)
            or self._is_progression_proposal(proposal)
        ):
            return self.client.request(
                proposal.method,
                proposal.path,
                proposal.body,
                idempotency_key=proposal.proposal_id,
            )
        return self.client.request(proposal.method, proposal.path, proposal.body)

    def _complete_proposal(self, proposal: Proposal, result: Any) -> dict[str, Any]:
        with self._lock:
            proposal.state = "applied"
            proposal.error = ""
            proposal.result = result
            return proposal.public(include_result=True)

    def _raise_rejected_apply(self, proposal: Proposal, exc: Exception) -> None:
        code = (
            f" [{exc.error_code}]"
            if isinstance(exc, LogosForgeApiError) and exc.error_code
            else ""
        )
        public_error = (
            f"The apply attempt was rejected{code} and will not be "
            f"retried automatically: {exc}"
        )
        with self._lock:
            proposal.state = "failed"
            proposal.error = public_error
        raise GatewayError(public_error) from exc

    def _raise_indeterminate_apply(
        self,
        proposal: Proposal,
        exc: Exception,
        *,
        receipt_error: Exception | None = None,
    ) -> None:
        detail = f"{exc}"
        if receipt_error is not None:
            detail += f"; durable receipt lookup was inconclusive: {receipt_error}"
        public_error = (
            "The apply outcome is indeterminate because the response does "
            "not prove that the mutation was rejected. Inspect current "
            "project state and do not retry this proposal: "
            f"{detail}"
        )
        with self._lock:
            proposal.state = "indeterminate"
            proposal.error = public_error
        raise GatewayError(public_error) from exc

    def _timeline_receipt(
        self,
        proposal_id: str,
        project_id: int,
    ) -> dict[str, Any] | None:
        """Read a receipt, distinguishing a supported miss from legacy 404."""
        try:
            receipt = self.client.get_timeline_command_receipt(
                proposal_id,
                project_id,
            )
        except LogosForgeApiError as exc:
            if (
                exc.status_code == 404
                and exc.error_code == _TIMELINE_RECEIPT_MISS_CODE
            ):
                return None
            raise
        if not isinstance(receipt, dict):
            raise GatewayError("Core returned an invalid Timeline receipt response.")
        return receipt

    @staticmethod
    def _validate_timeline_receipt_shape(
        receipt: Any,
        project_id: int,
    ) -> dict[str, Any]:
        if not isinstance(receipt, dict):
            raise GatewayError("Core returned an invalid Timeline receipt.")
        receipt_project_id = receipt.get("project_id")
        affected_scenes = receipt.get("original_affected_scene_ids", [])
        affected_links = receipt.get("original_affected_link_ids", [])
        affected_structure_links = receipt.get(
            "original_affected_structure_link_ids", []
        )
        created_link_id = receipt.get("original_created_link_id", None)
        created_structure_link_id = receipt.get(
            "original_created_structure_link_id", None
        )
        canonical = {
            "project_id": receipt_project_id,
            "request_digest": receipt.get("request_digest"),
            "command_kind": receipt.get("command_kind"),
            "expected_revision": receipt.get("expected_revision"),
            "applied_revision": receipt.get("applied_revision"),
            "original_changed": receipt.get("original_changed"),
            "original_affected_scene_ids": affected_scenes,
            "original_affected_link_ids": affected_links,
            "original_affected_structure_link_ids": affected_structure_links,
            "original_created_link_id": created_link_id,
            "original_created_structure_link_id": created_structure_link_id,
            "committed_at": receipt.get("committed_at"),
        }

        def valid_ids(value: Any) -> bool:
            return (
                isinstance(value, list)
                and all(
                    not isinstance(item, bool)
                    and isinstance(item, int)
                    and item > 0
                    for item in value
                )
                and len(set(value)) == len(value)
            )

        def valid_optional_id(value: Any) -> bool:
            return value is None or (
                not isinstance(value, bool)
                and isinstance(value, int)
                and value > 0
            )

        valid = (
            isinstance(receipt_project_id, int)
            and not isinstance(receipt_project_id, bool)
            and receipt_project_id == project_id
            and isinstance(canonical["request_digest"], str)
            and _LOWER_SHA256_RE.fullmatch(canonical["request_digest"]) is not None
            and isinstance(canonical["command_kind"], str)
            and canonical["command_kind"] in _TIMELINE_COMMAND_FIELDS
            and isinstance(canonical["expected_revision"], str)
            and _LOWER_SHA256_RE.fullmatch(canonical["expected_revision"]) is not None
            and isinstance(canonical["applied_revision"], str)
            and _LOWER_SHA256_RE.fullmatch(canonical["applied_revision"]) is not None
            and isinstance(canonical["original_changed"], bool)
            and valid_ids(affected_scenes)
            and valid_ids(affected_links)
            and valid_ids(affected_structure_links)
            and valid_optional_id(created_link_id)
            and valid_optional_id(created_structure_link_id)
            and not (
                created_link_id is not None
                and created_structure_link_id is not None
            )
            and (
                created_link_id is None
                or created_link_id in affected_links
            )
            and (
                created_structure_link_id is None
                or created_structure_link_id in affected_structure_links
            )
            and isinstance(canonical["committed_at"], str)
            and bool(canonical["committed_at"])
        )
        if not valid:
            raise GatewayError("Core returned an invalid Timeline receipt.")
        return copy.deepcopy(canonical)

    def _validate_timeline_receipt_for_proposal(
        self,
        proposal: Proposal,
        receipt: Any,
    ) -> dict[str, Any]:
        assert proposal.project_id is not None
        canonical = self._validate_timeline_receipt_shape(
            receipt,
            proposal.project_id,
        )
        expected_digest = _timeline_receipt_request_digest(
            proposal.project_id,
            proposal.body,
        )
        if (
            canonical["command_kind"] != proposal.body.get("kind")
            or canonical["expected_revision"]
            != proposal.body.get("expected_revision")
            or not secrets.compare_digest(
                canonical["request_digest"],
                expected_digest,
            )
        ):
            raise GatewayError(
                "Durable Timeline receipt integrity check failed; do not retry."
            )
        return canonical

    def _recovered_timeline_result(
        self,
        project_id: int,
        proposal_id: str,
        receipt: dict[str, Any],
        *,
        proposal: Proposal | None = None,
    ) -> dict[str, Any]:
        """Read one board bracketed by the same durable project receipt.

        The receipt and Timeline are separate HTTP resources. Re-reading the
        receipt after the board closes the project-delete/SQLite-id-reuse window:
        an old receipt can never be paired with a replacement project's board.
        """
        current = self.client.get_timeline(project_id)
        raw_confirmation = self._timeline_receipt(proposal_id, project_id)
        if raw_confirmation is None:
            raise GatewayError(
                "The durable Timeline receipt disappeared during recovery; "
                "the project lifetime may have changed."
            )
        confirmation = (
            self._validate_timeline_receipt_for_proposal(
                proposal,
                raw_confirmation,
            )
            if proposal is not None
            else self._validate_timeline_receipt_shape(
                raw_confirmation,
                project_id,
            )
        )
        if confirmation != receipt:
            raise GatewayError(
                "The durable Timeline receipt changed during recovery; "
                "the project lifetime may have changed."
            )
        return {
            "timeline": current,
            "replayed": True,
            "applied_revision": receipt["applied_revision"],
            "changed": False,
            "affected_scene_ids": [],
            "affected_link_ids": [],
            "affected_structure_link_ids": [],
            "created_link_id": None,
            "created_structure_link_id": None,
        }

    def _complete_timeline_recovery(
        self,
        proposal: Proposal,
        raw_receipt: Any,
    ) -> dict[str, Any]:
        receipt = self._validate_timeline_receipt_for_proposal(
            proposal,
            raw_receipt,
        )
        assert proposal.project_id is not None
        with self._lock:
            # Remember proof of commit before the fresh-snapshot request. If
            # that read fails, no later recovery call may resend the command.
            proposal.receipt = receipt
            proposal.recovered_from_core = True
            proposal.timeline_receipt_observed = True
        result = self._recovered_timeline_result(
            proposal.project_id,
            proposal.proposal_id,
            receipt,
            proposal=proposal,
        )
        with self._lock:
            proposal.state = "applied"
            proposal.error = ""
            proposal.result = result
            return proposal.public(include_result=True)

    def _mark_receipt_validation_failed(
        self,
        proposal: Proposal,
        exc: GatewayError,
    ) -> None:
        with self._lock:
            proposal.state = "failed"
            proposal.error = str(exc)
        raise exc

    def _mark_recovery_pending(
        self,
        proposal: Proposal,
        exc: Exception,
    ) -> None:
        public_error = (
            "The Timeline apply is still awaiting durable recovery after an "
            "ambiguous retry. Later, call logosforge_apply_proposal again with "
            "this same proposal_id; do not create a replacement proposal: "
            f"{exc}"
        )
        with self._lock:
            proposal.state = "recovery_pending"
            proposal.error = public_error
        raise GatewayError(public_error) from exc

    def _retry_timeline_once(self, proposal: Proposal) -> dict[str, Any]:
        with self._lock:
            if (
                proposal.timeline_resend_attempted
                or proposal.timeline_receipt_observed
            ):
                self._keep_timeline_recovery_pending(
                    proposal,
                    "No durable receipt is currently visible; the single "
                    "bounded resend has already been consumed.",
                )
            # Set before I/O so even an ambiguous response consumes the sole
            # protocol-authorized resend.
            proposal.timeline_resend_attempted = True
        try:
            result = self._execute_proposal_request(proposal)
        except Exception as exc:  # noqa: BLE001 - transport boundary
            if self._is_definite_http_rejection(exc):
                self._raise_rejected_apply(proposal, exc)
            self._mark_recovery_pending(proposal, exc)
        return self._complete_proposal(proposal, result)

    def _keep_timeline_recovery_pending(
        self,
        proposal: Proposal,
        detail: str,
        *,
        cause: Exception | None = None,
    ) -> None:
        public_error = (
            "The Timeline apply remains recovery_pending. No additional "
            "mutation was sent. Later, call logosforge_apply_proposal again "
            "with this same proposal_id to poll its durable receipt: "
            f"{detail}"
        )
        with self._lock:
            proposal.state = "recovery_pending"
            proposal.error = public_error
        if cause is not None:
            raise GatewayError(public_error) from cause
        raise GatewayError(public_error)

    def _recover_ambiguous_timeline_apply(
        self,
        proposal: Proposal,
        original_error: Exception,
    ) -> dict[str, Any]:
        assert proposal.project_id is not None
        try:
            receipt = self._timeline_receipt(
                proposal.proposal_id,
                proposal.project_id,
            )
        except Exception as lookup_error:  # noqa: BLE001 - transport boundary
            self._raise_indeterminate_apply(
                proposal,
                original_error,
                receipt_error=lookup_error,
            )
        if receipt is None:
            # The unique machine code proves the new Core protocol is present
            # and the first transaction did not commit a receipt. One exact
            # same-key resend is therefore bounded and safe.
            return self._retry_timeline_once(proposal)
        try:
            return self._complete_timeline_recovery(proposal, receipt)
        except GatewayError as exc:
            self._mark_receipt_validation_failed(proposal, exc)
        except Exception as exc:  # noqa: BLE001 - fresh snapshot transport
            # The receipt proves a commit, but returning an old stored snapshot
            # would be incoherent. Let a later same-id call fetch a fresh one.
            self._mark_recovery_pending(proposal, exc)

    def _resume_timeline_recovery(
        self,
        proposal: Proposal,
    ) -> dict[str, Any]:
        assert proposal.project_id is not None
        try:
            receipt = self._timeline_receipt(
                proposal.proposal_id,
                proposal.project_id,
            )
        except Exception as lookup_error:  # noqa: BLE001 - transport boundary
            self._keep_timeline_recovery_pending(
                proposal,
                f"Receipt lookup was inconclusive: {lookup_error}",
                cause=lookup_error,
            )
        if receipt is None:
            self._keep_timeline_recovery_pending(
                proposal,
                "Core reported that no receipt is currently available and "
                "the single bounded resend has already been consumed.",
            )
        try:
            return self._complete_timeline_recovery(proposal, receipt)
        except GatewayError as exc:
            self._mark_receipt_validation_failed(proposal, exc)
        except Exception as exc:  # noqa: BLE001 - fresh snapshot transport
            self._mark_recovery_pending(proposal, exc)

    def _canvas_plot_receipt(
        self,
        proposal_id: str,
        project_id: int,
    ) -> dict[str, Any] | None:
        """Read a Canvas receipt, distinguishing a supported miss from 404."""
        try:
            receipt = self.client.get_canvas_plot_command_receipt(
                proposal_id,
                project_id,
            )
        except LogosForgeApiError as exc:
            if (
                exc.status_code == 404
                and exc.error_code == _CANVAS_PLOT_RECEIPT_MISS_CODE
            ):
                return None
            raise
        if not isinstance(receipt, dict):
            raise GatewayError(
                "Core returned an invalid Canvas Plot receipt response."
            )
        return receipt

    @staticmethod
    def _validate_canvas_plot_receipt_shape(
        receipt: Any,
        project_id: int,
    ) -> dict[str, Any]:
        if not isinstance(receipt, dict):
            raise GatewayError("Core returned an invalid Canvas Plot receipt.")
        receipt_project_id = receipt.get("project_id")
        affected_nodes = receipt.get("original_affected_node_ids")
        affected_links = receipt.get("original_affected_link_ids")
        affected_frames = receipt.get("original_affected_frame_ids")
        created_node_id = receipt.get("original_created_node_id")
        created_link_id = receipt.get("original_created_link_id")
        created_frame_id = receipt.get("original_created_frame_id")
        canonical = {
            "project_id": receipt_project_id,
            "request_digest": receipt.get("request_digest"),
            "command_kind": receipt.get("command_kind"),
            "expected_revision": receipt.get("expected_revision"),
            "applied_revision": receipt.get("applied_revision"),
            "original_changed": receipt.get("original_changed"),
            "original_affected_node_ids": affected_nodes,
            "original_affected_link_ids": affected_links,
            "original_affected_frame_ids": affected_frames,
            "original_created_node_id": created_node_id,
            "original_created_link_id": created_link_id,
            "original_created_frame_id": created_frame_id,
            "committed_at": receipt.get("committed_at"),
        }

        def valid_ids(values: Any) -> bool:
            return (
                isinstance(values, list)
                and all(
                    not isinstance(value, bool)
                    and isinstance(value, int)
                    and value > 0
                    for value in values
                )
                and len(set(values)) == len(values)
            )

        def valid_optional_id(value: Any) -> bool:
            return value is None or (
                not isinstance(value, bool)
                and isinstance(value, int)
                and value > 0
            )

        valid = (
            isinstance(receipt_project_id, int)
            and not isinstance(receipt_project_id, bool)
            and receipt_project_id == project_id
            and isinstance(canonical["request_digest"], str)
            and _LOWER_SHA256_RE.fullmatch(canonical["request_digest"]) is not None
            and isinstance(canonical["command_kind"], str)
            and canonical["command_kind"] in _CANVAS_PLOT_COMMAND_FIELDS
            and isinstance(canonical["expected_revision"], str)
            and _LOWER_SHA256_RE.fullmatch(canonical["expected_revision"]) is not None
            and isinstance(canonical["applied_revision"], str)
            and _LOWER_SHA256_RE.fullmatch(canonical["applied_revision"]) is not None
            and isinstance(canonical["original_changed"], bool)
            and valid_ids(affected_nodes)
            and valid_ids(affected_links)
            and valid_ids(affected_frames)
            and valid_optional_id(created_node_id)
            and valid_optional_id(created_link_id)
            and valid_optional_id(created_frame_id)
            and isinstance(canonical["committed_at"], str)
            and bool(canonical["committed_at"])
        )
        if valid:
            created_by_kind = {
                "create_node": created_node_id,
                "create_link": created_link_id,
                "create_frame": created_frame_id,
            }
            created_ids = [
                value
                for value in (created_node_id, created_link_id, created_frame_id)
                if value is not None
            ]
            kind = canonical["command_kind"]
            changed = canonical["original_changed"]
            node_kind = kind in {"create_node", "update_node", "delete_node"}
            link_kind = kind in {"create_link", "update_link", "delete_link"}
            frame_kind = kind in {
                "create_frame", "update_frame", "delete_frame",
            }
            invalid_created_ids = (
                len(created_ids) > 1
                or bool(
                    created_ids
                    and created_by_kind.get(kind) != created_ids[0]
                )
                or (
                    created_node_id is not None
                    and created_node_id not in affected_nodes
                )
                or (
                    created_link_id is not None
                    and created_link_id not in affected_links
                )
                or (
                    created_frame_id is not None
                    and created_frame_id not in affected_frames
                )
                or (
                    changed
                    and kind in created_by_kind
                    and created_by_kind[kind] is None
                )
            )
            invalid_changed_effects = changed and (
                canonical["applied_revision"]
                == canonical["expected_revision"]
                or (
                    node_kind
                    and (
                        not affected_nodes
                        or bool(affected_frames)
                        or (kind != "delete_node" and bool(affected_links))
                    )
                )
                or (
                    link_kind
                    and (
                        not affected_links
                        or bool(affected_nodes)
                        or bool(affected_frames)
                    )
                )
                or (
                    frame_kind
                    and (
                        not affected_frames
                        or bool(affected_nodes)
                        or bool(affected_links)
                    )
                )
            )
            invalid_noop = not changed and (
                canonical["applied_revision"]
                != canonical["expected_revision"]
                or bool(affected_nodes)
                or bool(affected_links)
                or bool(affected_frames)
                or bool(created_ids)
                or kind not in {
                    "update_node",
                    "update_link",
                    "update_frame",
                    "create_link",
                }
            )
            if (
                invalid_created_ids
                or invalid_changed_effects
                or invalid_noop
            ):
                valid = False
        if not valid:
            raise GatewayError("Core returned an invalid Canvas Plot receipt.")
        return copy.deepcopy(canonical)

    def _validate_canvas_plot_receipt_for_proposal(
        self,
        proposal: Proposal,
        receipt: Any,
    ) -> dict[str, Any]:
        assert proposal.project_id is not None
        canonical = self._validate_canvas_plot_receipt_shape(
            receipt,
            proposal.project_id,
        )
        expected_digest = _canvas_plot_receipt_request_digest(
            proposal.project_id,
            proposal.body,
        )
        if (
            canonical["command_kind"] != proposal.body.get("kind")
            or canonical["expected_revision"]
            != proposal.body.get("expected_revision")
            or not secrets.compare_digest(
                canonical["request_digest"],
                expected_digest,
            )
        ):
            raise GatewayError(
                "Durable Canvas Plot receipt integrity check failed; do not retry."
            )
        return canonical

    def _recovered_canvas_plot_result(
        self,
        project_id: int,
        proposal_id: str,
        receipt: dict[str, Any],
        *,
        proposal: Proposal | None = None,
    ) -> dict[str, Any]:
        """Read one Canvas board bracketed by the same durable receipt."""
        current = self.client.get_canvas_plot(project_id)
        raw_confirmation = self._canvas_plot_receipt(proposal_id, project_id)
        if raw_confirmation is None:
            raise GatewayError(
                "The durable Canvas Plot receipt disappeared during recovery; "
                "the project lifetime may have changed."
            )
        confirmation = (
            self._validate_canvas_plot_receipt_for_proposal(
                proposal,
                raw_confirmation,
            )
            if proposal is not None
            else self._validate_canvas_plot_receipt_shape(
                raw_confirmation,
                project_id,
            )
        )
        if confirmation != receipt:
            raise GatewayError(
                "The durable Canvas Plot receipt changed during recovery; "
                "the project lifetime may have changed."
            )
        return {
            "canvas_plot": current,
            "replayed": True,
            "applied_revision": receipt["applied_revision"],
            "changed": False,
            "affected_node_ids": [],
            "affected_link_ids": [],
            "affected_frame_ids": [],
            "created_node_id": None,
            "created_link_id": None,
            "created_frame_id": None,
        }

    def _complete_canvas_plot_recovery(
        self,
        proposal: Proposal,
        raw_receipt: Any,
    ) -> dict[str, Any]:
        receipt = self._validate_canvas_plot_receipt_for_proposal(
            proposal,
            raw_receipt,
        )
        assert proposal.project_id is not None
        with self._lock:
            # Once commit proof is visible no later snapshot failure may make
            # another mutation attempt safe.
            proposal.receipt = receipt
            proposal.recovered_from_core = True
            proposal.canvas_plot_receipt_observed = True
        result = self._recovered_canvas_plot_result(
            proposal.project_id,
            proposal.proposal_id,
            receipt,
            proposal=proposal,
        )
        with self._lock:
            proposal.state = "applied"
            proposal.error = ""
            proposal.result = result
            return proposal.public(include_result=True)

    def _mark_canvas_plot_recovery_pending(
        self,
        proposal: Proposal,
        exc: Exception,
    ) -> None:
        public_error = (
            "The Canvas Plot apply is still awaiting durable recovery after "
            "an ambiguous retry. Later, call logosforge_apply_proposal again "
            "with this same proposal_id; do not create a replacement proposal: "
            f"{exc}"
        )
        with self._lock:
            proposal.state = "recovery_pending"
            proposal.error = public_error
        raise GatewayError(public_error) from exc

    def _keep_canvas_plot_recovery_pending(
        self,
        proposal: Proposal,
        detail: str,
        *,
        cause: Exception | None = None,
    ) -> None:
        public_error = (
            "The Canvas Plot apply remains recovery_pending. No additional "
            "mutation was sent. Later, call logosforge_apply_proposal again "
            "with this same proposal_id to poll its durable receipt: "
            f"{detail}"
        )
        with self._lock:
            proposal.state = "recovery_pending"
            proposal.error = public_error
        if cause is not None:
            raise GatewayError(public_error) from cause
        raise GatewayError(public_error)

    def _retry_canvas_plot_once(self, proposal: Proposal) -> dict[str, Any]:
        with self._lock:
            if (
                proposal.canvas_plot_resend_attempted
                or proposal.canvas_plot_receipt_observed
            ):
                self._keep_canvas_plot_recovery_pending(
                    proposal,
                    "No durable receipt is currently visible; the single "
                    "bounded resend has already been consumed.",
                )
            proposal.canvas_plot_resend_attempted = True
        try:
            result = self._execute_proposal_request(proposal)
        except Exception as exc:  # noqa: BLE001 - transport boundary
            if self._is_definite_http_rejection(exc):
                self._raise_rejected_apply(proposal, exc)
            self._mark_canvas_plot_recovery_pending(proposal, exc)
        return self._complete_proposal(proposal, result)

    def _recover_ambiguous_canvas_plot_apply(
        self,
        proposal: Proposal,
        original_error: Exception,
    ) -> dict[str, Any]:
        assert proposal.project_id is not None
        try:
            receipt = self._canvas_plot_receipt(
                proposal.proposal_id,
                proposal.project_id,
            )
        except Exception as lookup_error:  # noqa: BLE001 - transport boundary
            self._raise_indeterminate_apply(
                proposal,
                original_error,
                receipt_error=lookup_error,
            )
        if receipt is None:
            return self._retry_canvas_plot_once(proposal)
        try:
            return self._complete_canvas_plot_recovery(proposal, receipt)
        except GatewayError as exc:
            self._mark_receipt_validation_failed(proposal, exc)
        except Exception as exc:  # noqa: BLE001 - fresh snapshot transport
            self._mark_canvas_plot_recovery_pending(proposal, exc)

    def _resume_canvas_plot_recovery(
        self,
        proposal: Proposal,
    ) -> dict[str, Any]:
        assert proposal.project_id is not None
        try:
            receipt = self._canvas_plot_receipt(
                proposal.proposal_id,
                proposal.project_id,
            )
        except Exception as lookup_error:  # noqa: BLE001 - transport boundary
            self._keep_canvas_plot_recovery_pending(
                proposal,
                f"Receipt lookup was inconclusive: {lookup_error}",
                cause=lookup_error,
            )
        if receipt is None:
            self._keep_canvas_plot_recovery_pending(
                proposal,
                "Core reported that no receipt is currently available and "
                "the single bounded resend has already been consumed.",
            )
        try:
            return self._complete_canvas_plot_recovery(proposal, receipt)
        except GatewayError as exc:
            self._mark_receipt_validation_failed(proposal, exc)
        except Exception as exc:  # noqa: BLE001 - fresh snapshot transport
            self._mark_canvas_plot_recovery_pending(proposal, exc)

    def _knowledge_graph_receipt(
        self,
        proposal_id: str,
        project_id: int,
    ) -> dict[str, Any] | None:
        """Read a graph receipt, distinguishing a supported miss from 404."""
        try:
            receipt = self.client.get_knowledge_graph_command_receipt(
                proposal_id,
                project_id,
            )
        except LogosForgeApiError as exc:
            if (
                exc.status_code == 404
                and exc.error_code == _KNOWLEDGE_GRAPH_RECEIPT_MISS_CODE
            ):
                return None
            raise
        if not isinstance(receipt, dict):
            raise GatewayError(
                "Core returned an invalid Knowledge Graph receipt response."
            )
        return receipt

    @staticmethod
    def _validate_knowledge_graph_receipt_shape(
        receipt: Any,
        project_id: int,
    ) -> dict[str, Any]:
        if not isinstance(receipt, dict):
            raise GatewayError("Core returned an invalid Knowledge Graph receipt.")
        receipt_project_id = receipt.get("project_id")
        raw_edge = receipt.get("original_affected_edge")
        affected_edge = {
            "source": raw_edge.get("source") if isinstance(raw_edge, dict) else None,
            "target": raw_edge.get("target") if isinstance(raw_edge, dict) else None,
            "edge_type": (
                raw_edge.get("edge_type") if isinstance(raw_edge, dict) else None
            ),
        }
        canonical = {
            "project_id": receipt_project_id,
            "request_digest": receipt.get("request_digest"),
            "command_kind": receipt.get("command_kind"),
            "expected_revision": receipt.get("expected_revision"),
            "applied_revision": receipt.get("applied_revision"),
            "original_changed": receipt.get("original_changed"),
            "original_affected_edge": affected_edge,
            "committed_at": receipt.get("committed_at"),
        }

        def valid_text(value: Any, maximum: int) -> bool:
            return isinstance(value, str) and 1 <= len(value) <= maximum

        valid = (
            isinstance(receipt_project_id, int)
            and not isinstance(receipt_project_id, bool)
            and receipt_project_id == project_id
            and isinstance(canonical["request_digest"], str)
            and _LOWER_SHA256_RE.fullmatch(canonical["request_digest"]) is not None
            and isinstance(canonical["command_kind"], str)
            and canonical["command_kind"] in _KNOWLEDGE_GRAPH_COMMAND_FIELDS
            and isinstance(canonical["expected_revision"], str)
            and _LOWER_SHA256_RE.fullmatch(canonical["expected_revision"]) is not None
            and isinstance(canonical["applied_revision"], str)
            and _LOWER_SHA256_RE.fullmatch(canonical["applied_revision"]) is not None
            and canonical["original_changed"] is True
            and canonical["applied_revision"] != canonical["expected_revision"]
            and valid_text(affected_edge["source"], 512)
            and valid_text(affected_edge["target"], 512)
            and valid_text(affected_edge["edge_type"], 128)
            and isinstance(canonical["committed_at"], str)
            and bool(canonical["committed_at"])
        )
        if valid:
            canonical_request = {
                "kind": canonical["command_kind"],
                "expected_revision": canonical["expected_revision"],
                **affected_edge,
            }
            valid = secrets.compare_digest(
                canonical["request_digest"],
                _knowledge_graph_receipt_request_digest(
                    project_id,
                    canonical_request,
                ),
            )
        if not valid:
            raise GatewayError("Core returned an invalid Knowledge Graph receipt.")
        return copy.deepcopy(canonical)

    def _validate_knowledge_graph_receipt_for_proposal(
        self,
        proposal: Proposal,
        receipt: Any,
    ) -> dict[str, Any]:
        assert proposal.project_id is not None
        canonical = self._validate_knowledge_graph_receipt_shape(
            receipt,
            proposal.project_id,
        )
        expected_digest = _knowledge_graph_receipt_request_digest(
            proposal.project_id,
            proposal.body,
        )
        expected_edge = {
            key: proposal.body.get(key)
            for key in ("source", "target", "edge_type")
        }
        if (
            canonical["command_kind"] != proposal.body.get("kind")
            or canonical["expected_revision"]
            != proposal.body.get("expected_revision")
            or canonical["original_affected_edge"] != expected_edge
            or not secrets.compare_digest(
                canonical["request_digest"],
                expected_digest,
            )
        ):
            raise GatewayError(
                "Durable Knowledge Graph receipt integrity check failed; do not retry."
            )
        return canonical

    def _recovered_knowledge_graph_result(
        self,
        project_id: int,
        proposal_id: str,
        receipt: dict[str, Any],
        *,
        proposal: Proposal | None = None,
    ) -> dict[str, Any]:
        """Read one Project Map bracketed by the same durable receipt."""
        current = self.client.get_knowledge_graph(
            project_id,
            view_mode="project_map",
        )
        raw_confirmation = self._knowledge_graph_receipt(
            proposal_id,
            project_id,
        )
        if raw_confirmation is None:
            raise GatewayError(
                "The durable Knowledge Graph receipt disappeared during recovery; "
                "the project lifetime may have changed."
            )
        confirmation = (
            self._validate_knowledge_graph_receipt_for_proposal(
                proposal,
                raw_confirmation,
            )
            if proposal is not None
            else self._validate_knowledge_graph_receipt_shape(
                raw_confirmation,
                project_id,
            )
        )
        if confirmation != receipt:
            raise GatewayError(
                "The durable Knowledge Graph receipt changed during recovery; "
                "the project lifetime may have changed."
            )
        return {
            "knowledge_graph": current,
            "changed": False,
            "affected_edge": copy.deepcopy(receipt["original_affected_edge"]),
            "replayed": True,
            "applied_revision": receipt["applied_revision"],
        }

    def _complete_knowledge_graph_recovery(
        self,
        proposal: Proposal,
        raw_receipt: Any,
    ) -> dict[str, Any]:
        receipt = self._validate_knowledge_graph_receipt_for_proposal(
            proposal,
            raw_receipt,
        )
        assert proposal.project_id is not None
        with self._lock:
            proposal.receipt = receipt
            proposal.recovered_from_core = True
            proposal.knowledge_graph_receipt_observed = True
        result = self._recovered_knowledge_graph_result(
            proposal.project_id,
            proposal.proposal_id,
            receipt,
            proposal=proposal,
        )
        with self._lock:
            proposal.state = "applied"
            proposal.error = ""
            proposal.result = result
            return proposal.public(include_result=True)

    def _mark_knowledge_graph_recovery_pending(
        self,
        proposal: Proposal,
        exc: Exception,
    ) -> None:
        public_error = (
            "The Knowledge Graph apply is still awaiting durable recovery after "
            "an ambiguous retry. Later, call logosforge_apply_proposal again "
            "with this same proposal_id; do not create a replacement proposal: "
            f"{exc}"
        )
        with self._lock:
            proposal.state = "recovery_pending"
            proposal.error = public_error
        raise GatewayError(public_error) from exc

    def _keep_knowledge_graph_recovery_pending(
        self,
        proposal: Proposal,
        detail: str,
        *,
        cause: Exception | None = None,
    ) -> None:
        public_error = (
            "The Knowledge Graph apply remains recovery_pending. No additional "
            "mutation was sent. Later, call logosforge_apply_proposal again "
            "with this same proposal_id to poll its durable receipt: "
            f"{detail}"
        )
        with self._lock:
            proposal.state = "recovery_pending"
            proposal.error = public_error
        if cause is not None:
            raise GatewayError(public_error) from cause
        raise GatewayError(public_error)

    def _retry_knowledge_graph_once(
        self,
        proposal: Proposal,
    ) -> dict[str, Any]:
        with self._lock:
            if (
                proposal.knowledge_graph_resend_attempted
                or proposal.knowledge_graph_receipt_observed
            ):
                self._keep_knowledge_graph_recovery_pending(
                    proposal,
                    "No durable receipt is currently visible; the single "
                    "bounded resend has already been consumed.",
                )
            proposal.knowledge_graph_resend_attempted = True
        try:
            result = self._execute_proposal_request(proposal)
        except Exception as exc:  # noqa: BLE001 - transport boundary
            if self._is_definite_http_rejection(exc):
                self._raise_rejected_apply(proposal, exc)
            self._mark_knowledge_graph_recovery_pending(proposal, exc)
        return self._complete_proposal(proposal, result)

    def _recover_ambiguous_knowledge_graph_apply(
        self,
        proposal: Proposal,
        original_error: Exception,
    ) -> dict[str, Any]:
        assert proposal.project_id is not None
        try:
            receipt = self._knowledge_graph_receipt(
                proposal.proposal_id,
                proposal.project_id,
            )
        except Exception as lookup_error:  # noqa: BLE001 - transport boundary
            self._raise_indeterminate_apply(
                proposal,
                original_error,
                receipt_error=lookup_error,
            )
        if receipt is None:
            return self._retry_knowledge_graph_once(proposal)
        try:
            return self._complete_knowledge_graph_recovery(proposal, receipt)
        except GatewayError as exc:
            self._mark_receipt_validation_failed(proposal, exc)
        except Exception as exc:  # noqa: BLE001 - fresh snapshot transport
            self._mark_knowledge_graph_recovery_pending(proposal, exc)

    def _resume_knowledge_graph_recovery(
        self,
        proposal: Proposal,
    ) -> dict[str, Any]:
        assert proposal.project_id is not None
        try:
            receipt = self._knowledge_graph_receipt(
                proposal.proposal_id,
                proposal.project_id,
            )
        except Exception as lookup_error:  # noqa: BLE001 - transport boundary
            self._keep_knowledge_graph_recovery_pending(
                proposal,
                f"Receipt lookup was inconclusive: {lookup_error}",
                cause=lookup_error,
            )
        if receipt is None:
            self._keep_knowledge_graph_recovery_pending(
                proposal,
                "Core reported that no receipt is currently available and "
                "the single bounded resend has already been consumed.",
            )
        try:
            return self._complete_knowledge_graph_recovery(proposal, receipt)
        except GatewayError as exc:
            self._mark_receipt_validation_failed(proposal, exc)
        except Exception as exc:  # noqa: BLE001 - fresh snapshot transport
            self._mark_knowledge_graph_recovery_pending(proposal, exc)

    def _continuity_receipt(
        self,
        proposal_id: str,
        project_id: int,
    ) -> dict[str, Any] | None:
        """Read a Continuity receipt, distinguishing a supported miss."""
        try:
            receipt = self.client.get_continuity_command_receipt(
                proposal_id,
                project_id,
            )
        except LogosForgeApiError as exc:
            if (
                exc.status_code == 404
                and exc.error_code == _CONTINUITY_RECEIPT_MISS_CODE
            ):
                return None
            raise
        if not isinstance(receipt, dict):
            raise GatewayError(
                "Core returned an invalid Continuity receipt response."
            )
        return receipt

    @staticmethod
    def _validate_continuity_receipt_shape(
        receipt: Any,
        project_id: int,
    ) -> dict[str, Any]:
        if not isinstance(receipt, dict):
            raise GatewayError("Core returned an invalid Continuity receipt.")
        canonical = {
            "project_id": receipt.get("project_id"),
            "request_digest": receipt.get("request_digest"),
            "command_kind": receipt.get("command_kind"),
            "expected_revision": receipt.get("expected_revision"),
            "applied_revision": receipt.get("applied_revision"),
            "original_changed": receipt.get("original_changed"),
            "original_affected_issue_id": receipt.get(
                "original_affected_issue_id"
            ),
            "expected_issue_fingerprint": receipt.get(
                "expected_issue_fingerprint"
            ),
            "previous_status": receipt.get("previous_status"),
            "status": receipt.get("status"),
            "committed_at": receipt.get("committed_at"),
        }
        expected_status = {
            "defer_issue": "deferred",
            "dismiss_issue": "dismissed",
            "resolve_issue": "resolved",
        }
        receipt_project_id = canonical["project_id"]
        valid = (
            isinstance(receipt_project_id, int)
            and not isinstance(receipt_project_id, bool)
            and receipt_project_id == project_id
            and isinstance(canonical["request_digest"], str)
            and _LOWER_SHA256_RE.fullmatch(canonical["request_digest"])
            is not None
            and isinstance(canonical["command_kind"], str)
            and canonical["command_kind"] in _CONTINUITY_COMMAND_FIELDS
            and isinstance(canonical["expected_revision"], str)
            and _LOWER_SHA256_RE.fullmatch(canonical["expected_revision"])
            is not None
            and isinstance(canonical["applied_revision"], str)
            and _LOWER_SHA256_RE.fullmatch(canonical["applied_revision"])
            is not None
            and canonical["original_changed"] is True
            and canonical["applied_revision"] != canonical["expected_revision"]
            and isinstance(canonical["original_affected_issue_id"], str)
            and re.fullmatch(
                r"[0-9a-f]{16}", canonical["original_affected_issue_id"]
            )
            is not None
            and isinstance(canonical["expected_issue_fingerprint"], str)
            and _LOWER_SHA256_RE.fullmatch(
                canonical["expected_issue_fingerprint"]
            )
            is not None
            and canonical["previous_status"] == "open"
            and canonical["status"]
            == expected_status.get(canonical["command_kind"])
            and isinstance(canonical["committed_at"], str)
            and bool(canonical["committed_at"])
        )
        if valid:
            canonical_request = {
                "kind": canonical["command_kind"],
                "expected_revision": canonical["expected_revision"],
                "issue_id": canonical["original_affected_issue_id"],
                "expected_issue_fingerprint": canonical[
                    "expected_issue_fingerprint"
                ],
            }
            valid = secrets.compare_digest(
                canonical["request_digest"],
                _continuity_receipt_request_digest(
                    project_id,
                    canonical_request,
                ),
            )
        if not valid:
            raise GatewayError("Core returned an invalid Continuity receipt.")
        return copy.deepcopy(canonical)

    def _validate_continuity_receipt_for_proposal(
        self,
        proposal: Proposal,
        receipt: Any,
    ) -> dict[str, Any]:
        assert proposal.project_id is not None
        canonical = self._validate_continuity_receipt_shape(
            receipt,
            proposal.project_id,
        )
        expected_status = {
            "defer_issue": "deferred",
            "dismiss_issue": "dismissed",
            "resolve_issue": "resolved",
        }.get(proposal.body.get("kind"))
        expected_digest = _continuity_receipt_request_digest(
            proposal.project_id,
            proposal.body,
        )
        if (
            canonical["command_kind"] != proposal.body.get("kind")
            or canonical["expected_revision"]
            != proposal.body.get("expected_revision")
            or canonical["original_affected_issue_id"]
            != proposal.body.get("issue_id")
            or canonical["expected_issue_fingerprint"]
            != proposal.body.get("expected_issue_fingerprint")
            or canonical["status"] != expected_status
            or not secrets.compare_digest(
                canonical["request_digest"],
                expected_digest,
            )
        ):
            raise GatewayError(
                "Durable Continuity receipt integrity check failed; do not retry."
            )
        return canonical

    def _recovered_continuity_result(
        self,
        project_id: int,
        proposal_id: str,
        receipt: dict[str, Any],
        *,
        proposal: Proposal | None = None,
    ) -> dict[str, Any]:
        """Read one Continuity report bracketed by the same receipt."""
        current = self.client.get_continuity(project_id)
        current_project_id = (
            current.get("project_id") if isinstance(current, dict) else None
        )
        if (
            not isinstance(current, dict)
            or isinstance(current_project_id, bool)
            or not isinstance(current_project_id, int)
            or current_project_id != project_id
            or not isinstance(current.get("review_revision"), str)
            or _LOWER_SHA256_RE.fullmatch(current["review_revision"]) is None
        ):
            raise GatewayError(
                "Core returned an invalid Continuity report during recovery."
            )
        raw_confirmation = self._continuity_receipt(proposal_id, project_id)
        if raw_confirmation is None:
            raise GatewayError(
                "The durable Continuity receipt disappeared during recovery; "
                "the project lifetime may have changed."
            )
        confirmation = (
            self._validate_continuity_receipt_for_proposal(
                proposal,
                raw_confirmation,
            )
            if proposal is not None
            else self._validate_continuity_receipt_shape(
                raw_confirmation,
                project_id,
            )
        )
        if confirmation != receipt:
            raise GatewayError(
                "The durable Continuity receipt changed during recovery; "
                "the project lifetime may have changed."
            )
        return {
            "continuity": current,
            "changed": False,
            "affected_issue_id": receipt["original_affected_issue_id"],
            "previous_status": receipt["previous_status"],
            "status": receipt["status"],
            "replayed": True,
            "applied_revision": receipt["applied_revision"],
        }

    def _complete_continuity_recovery(
        self,
        proposal: Proposal,
        raw_receipt: Any,
    ) -> dict[str, Any]:
        receipt = self._validate_continuity_receipt_for_proposal(
            proposal,
            raw_receipt,
        )
        assert proposal.project_id is not None
        with self._lock:
            proposal.receipt = receipt
            proposal.recovered_from_core = True
            proposal.continuity_receipt_observed = True
        result = self._recovered_continuity_result(
            proposal.project_id,
            proposal.proposal_id,
            receipt,
            proposal=proposal,
        )
        with self._lock:
            proposal.state = "applied"
            proposal.error = ""
            proposal.result = result
            return proposal.public(include_result=True)

    def _mark_continuity_recovery_pending(
        self,
        proposal: Proposal,
        exc: Exception,
    ) -> None:
        public_error = (
            "The Continuity apply is still awaiting durable recovery after "
            "an ambiguous retry. Later, call logosforge_apply_proposal again "
            "with this same proposal_id; do not create a replacement proposal: "
            f"{exc}"
        )
        with self._lock:
            proposal.state = "recovery_pending"
            proposal.error = public_error
        raise GatewayError(public_error) from exc

    def _keep_continuity_recovery_pending(
        self,
        proposal: Proposal,
        detail: str,
        *,
        cause: Exception | None = None,
    ) -> None:
        public_error = (
            "The Continuity apply remains recovery_pending. No additional "
            "mutation was sent. Later, call logosforge_apply_proposal again "
            "with this same proposal_id to poll its durable receipt: "
            f"{detail}"
        )
        with self._lock:
            proposal.state = "recovery_pending"
            proposal.error = public_error
        if cause is not None:
            raise GatewayError(public_error) from cause
        raise GatewayError(public_error)

    def _retry_continuity_once(
        self,
        proposal: Proposal,
    ) -> dict[str, Any]:
        with self._lock:
            if (
                proposal.continuity_resend_attempted
                or proposal.continuity_receipt_observed
            ):
                self._keep_continuity_recovery_pending(
                    proposal,
                    "No durable receipt is currently visible; the single "
                    "bounded resend has already been consumed.",
                )
            proposal.continuity_resend_attempted = True
        try:
            result = self._execute_proposal_request(proposal)
        except Exception as exc:  # noqa: BLE001 - transport boundary
            if self._is_definite_http_rejection(exc):
                self._raise_rejected_apply(proposal, exc)
            self._mark_continuity_recovery_pending(proposal, exc)
        return self._complete_proposal(proposal, result)

    def _recover_ambiguous_continuity_apply(
        self,
        proposal: Proposal,
        original_error: Exception,
    ) -> dict[str, Any]:
        assert proposal.project_id is not None
        try:
            receipt = self._continuity_receipt(
                proposal.proposal_id,
                proposal.project_id,
            )
        except Exception as lookup_error:  # noqa: BLE001 - transport boundary
            self._raise_indeterminate_apply(
                proposal,
                original_error,
                receipt_error=lookup_error,
            )
        if receipt is None:
            return self._retry_continuity_once(proposal)
        try:
            return self._complete_continuity_recovery(proposal, receipt)
        except GatewayError as exc:
            self._mark_receipt_validation_failed(proposal, exc)
        except Exception as exc:  # noqa: BLE001 - fresh snapshot transport
            self._mark_continuity_recovery_pending(proposal, exc)

    def _resume_continuity_recovery(
        self,
        proposal: Proposal,
    ) -> dict[str, Any]:
        assert proposal.project_id is not None
        try:
            receipt = self._continuity_receipt(
                proposal.proposal_id,
                proposal.project_id,
            )
        except Exception as lookup_error:  # noqa: BLE001 - transport boundary
            self._keep_continuity_recovery_pending(
                proposal,
                f"Receipt lookup was inconclusive: {lookup_error}",
                cause=lookup_error,
            )
        if receipt is None:
            self._keep_continuity_recovery_pending(
                proposal,
                "Core reported that no receipt is currently available and "
                "the single bounded resend has already been consumed.",
            )
        try:
            return self._complete_continuity_recovery(proposal, receipt)
        except GatewayError as exc:
            self._mark_receipt_validation_failed(proposal, exc)
        except Exception as exc:  # noqa: BLE001 - fresh snapshot transport
            self._mark_continuity_recovery_pending(proposal, exc)

    def _progression_receipt(
        self,
        proposal_id: str,
        project_id: int,
    ) -> dict[str, Any] | None:
        """Read a Progressions receipt, distinguishing a supported miss."""
        try:
            receipt = self.client.get_progression_command_receipt(
                proposal_id,
                project_id,
            )
        except LogosForgeApiError as exc:
            if (
                exc.status_code == 404
                and exc.error_code == _PROGRESSION_RECEIPT_MISS_CODE
            ):
                return None
            raise
        if not isinstance(receipt, dict):
            raise GatewayError(
                "Core returned an invalid Progressions receipt response."
            )
        return receipt

    @staticmethod
    def _validate_progression_receipt_shape(
        receipt: Any,
        project_id: int,
    ) -> dict[str, Any]:
        if not isinstance(receipt, dict):
            raise GatewayError("Core returned an invalid Progressions receipt.")
        canonical = {
            "project_id": receipt.get("project_id"),
            "request_digest": receipt.get("request_digest"),
            "command_kind": receipt.get("command_kind"),
            "expected_revision": receipt.get("expected_revision"),
            "applied_revision": receipt.get("applied_revision"),
            "original_changed": receipt.get("original_changed"),
            "original_affected_track_ids": receipt.get(
                "original_affected_track_ids", []
            ),
            "original_affected_beat_ids": receipt.get(
                "original_affected_beat_ids", []
            ),
            "original_created_track_id": receipt.get(
                "original_created_track_id"
            ),
            "original_created_beat_id": receipt.get(
                "original_created_beat_id"
            ),
            "committed_at": receipt.get("committed_at"),
        }

        def valid_ids(value: Any) -> bool:
            return (
                isinstance(value, list)
                and all(
                    isinstance(item, int)
                    and not isinstance(item, bool)
                    and item > 0
                    for item in value
                )
                and len(value) == len(set(value))
            )

        def valid_optional_id(value: Any) -> bool:
            return value is None or (
                isinstance(value, int)
                and not isinstance(value, bool)
                and value > 0
            )

        changed = canonical["original_changed"]
        kind = canonical["command_kind"]
        track_ids = canonical["original_affected_track_ids"]
        beat_ids = canonical["original_affected_beat_ids"]
        created_track_id = canonical["original_created_track_id"]
        created_beat_id = canonical["original_created_beat_id"]
        no_op_kinds = {
            "update_track", "reorder_tracks", "update_beat", "reorder_beats",
        }
        track_only_kinds = {
            "create_track", "update_track", "reorder_tracks",
        }
        beat_kinds = {
            "create_beat", "update_beat", "delete_beat", "reorder_beats",
        }
        valid = (
            isinstance(canonical["project_id"], int)
            and not isinstance(canonical["project_id"], bool)
            and canonical["project_id"] == project_id
            and isinstance(canonical["request_digest"], str)
            and _LOWER_SHA256_RE.fullmatch(canonical["request_digest"])
            is not None
            and kind in _PROGRESSION_COMMAND_FIELDS
            and isinstance(canonical["expected_revision"], str)
            and _LOWER_SHA256_RE.fullmatch(canonical["expected_revision"])
            is not None
            and isinstance(canonical["applied_revision"], str)
            and _LOWER_SHA256_RE.fullmatch(canonical["applied_revision"])
            is not None
            and isinstance(changed, bool)
            and (
                (changed and canonical["applied_revision"] != canonical["expected_revision"])
                or (
                    not changed
                    and canonical["applied_revision"] == canonical["expected_revision"]
                )
            )
            and valid_ids(track_ids)
            and valid_ids(beat_ids)
            and valid_optional_id(created_track_id)
            and valid_optional_id(created_beat_id)
            and not (created_track_id is not None and kind != "create_track")
            and not (created_beat_id is not None and kind != "create_beat")
            and not (changed and kind == "create_track" and created_track_id is None)
            and not (changed and kind == "create_beat" and created_beat_id is None)
            and not (
                created_track_id is not None and created_track_id not in track_ids
            )
            and not (created_beat_id is not None and created_beat_id not in beat_ids)
            and not (not changed and kind not in no_op_kinds)
            and not (
                not changed
                and (track_ids or beat_ids or created_track_id or created_beat_id)
            )
            and not (changed and not track_ids)
            and not (changed and kind in track_only_kinds and beat_ids)
            and not (changed and kind in beat_kinds and not beat_ids)
            and isinstance(canonical["committed_at"], str)
            and bool(canonical["committed_at"])
        )
        if not valid:
            raise GatewayError("Core returned an invalid Progressions receipt.")
        return copy.deepcopy(canonical)

    def _validate_progression_receipt_for_proposal(
        self,
        proposal: Proposal,
        receipt: Any,
    ) -> dict[str, Any]:
        assert proposal.project_id is not None
        canonical = self._validate_progression_receipt_shape(
            receipt,
            proposal.project_id,
        )
        expected_digest = _progression_receipt_request_digest(
            proposal.project_id,
            proposal.body,
        )
        if (
            canonical["command_kind"] != proposal.body.get("kind")
            or canonical["expected_revision"]
            != proposal.body.get("expected_revision")
            or not secrets.compare_digest(
                canonical["request_digest"],
                expected_digest,
            )
        ):
            raise GatewayError(
                "Durable Progressions receipt integrity check failed; do not retry."
            )
        return canonical

    def _recovered_progression_result(
        self,
        project_id: int,
        proposal_id: str,
        receipt: dict[str, Any],
        *,
        proposal: Proposal | None = None,
    ) -> dict[str, Any]:
        current = self.client.get_progressions(project_id)
        if (
            not isinstance(current, dict)
            or current.get("project_id") != project_id
            or not isinstance(current.get("revision"), str)
            or _LOWER_SHA256_RE.fullmatch(current["revision"]) is None
        ):
            raise GatewayError(
                "Core returned an invalid Progressions snapshot during recovery."
            )
        raw_confirmation = self._progression_receipt(proposal_id, project_id)
        if raw_confirmation is None:
            raise GatewayError(
                "The durable Progressions receipt disappeared during recovery; "
                "the project lifetime may have changed."
            )
        confirmation = (
            self._validate_progression_receipt_for_proposal(
                proposal,
                raw_confirmation,
            )
            if proposal is not None
            else self._validate_progression_receipt_shape(
                raw_confirmation,
                project_id,
            )
        )
        if confirmation != receipt:
            raise GatewayError(
                "The durable Progressions receipt changed during recovery; "
                "the project lifetime may have changed."
            )
        return {
            "progressions": current,
            "changed": False,
            "affected_track_ids": [],
            "affected_beat_ids": [],
            # Core's direct idempotent replay preserves the ids created by the
            # original command. Receipt recovery must expose the same result
            # so callers can keep working with the newly-created object.
            "created_track_id": receipt["original_created_track_id"],
            "created_beat_id": receipt["original_created_beat_id"],
            "replayed": True,
            "applied_revision": receipt["applied_revision"],
        }

    def _complete_progression_recovery(
        self,
        proposal: Proposal,
        raw_receipt: Any,
    ) -> dict[str, Any]:
        receipt = self._validate_progression_receipt_for_proposal(
            proposal,
            raw_receipt,
        )
        assert proposal.project_id is not None
        with self._lock:
            proposal.receipt = receipt
            proposal.recovered_from_core = True
            proposal.progression_receipt_observed = True
        result = self._recovered_progression_result(
            proposal.project_id,
            proposal.proposal_id,
            receipt,
            proposal=proposal,
        )
        with self._lock:
            proposal.state = "applied"
            proposal.error = ""
            proposal.result = result
            return proposal.public(include_result=True)

    def _mark_progression_recovery_pending(
        self,
        proposal: Proposal,
        exc: Exception,
    ) -> None:
        public_error = (
            "The Progressions apply is still awaiting durable recovery after "
            "an ambiguous write. Later, call logosforge_apply_proposal again "
            "with this same proposal_id; do not create a replacement proposal: "
            f"{exc}"
        )
        with self._lock:
            proposal.state = "recovery_pending"
            proposal.error = public_error
        raise GatewayError(public_error) from exc

    def _keep_progression_recovery_pending(
        self,
        proposal: Proposal,
        detail: str,
        *,
        cause: Exception | None = None,
    ) -> None:
        public_error = (
            "The Progressions apply remains recovery_pending. No additional "
            "mutation was sent. Later, call logosforge_apply_proposal again "
            "with this same proposal_id to poll its durable receipt: "
            f"{detail}"
        )
        with self._lock:
            proposal.state = "recovery_pending"
            proposal.error = public_error
        if cause is not None:
            raise GatewayError(public_error) from cause
        raise GatewayError(public_error)

    def _retry_progression_once(
        self,
        proposal: Proposal,
    ) -> dict[str, Any]:
        with self._lock:
            if (
                proposal.progression_resend_attempted
                or proposal.progression_receipt_observed
            ):
                self._keep_progression_recovery_pending(
                    proposal,
                    "No durable receipt is currently visible; the single "
                    "bounded resend has already been consumed.",
                )
            proposal.progression_resend_attempted = True
        try:
            result = self._execute_proposal_request(proposal)
        except Exception as exc:  # noqa: BLE001 - transport boundary
            if self._is_definite_http_rejection(exc):
                self._raise_rejected_apply(proposal, exc)
            self._mark_progression_recovery_pending(proposal, exc)
        return self._complete_proposal(proposal, result)

    def _recover_ambiguous_progression_apply(
        self,
        proposal: Proposal,
        original_error: Exception,
    ) -> dict[str, Any]:
        assert proposal.project_id is not None
        try:
            receipt = self._progression_receipt(
                proposal.proposal_id,
                proposal.project_id,
            )
        except Exception as lookup_error:  # noqa: BLE001 - transport boundary
            # Receipt support is part of the Progressions protocol. A
            # transient lookup failure does not revoke the exact command/key,
            # and must not terminalize a proposal that can be reconciled on a
            # later call. No resend has been consumed yet.
            self._mark_progression_recovery_pending(proposal, lookup_error)
        if receipt is None:
            return self._retry_progression_once(proposal)
        try:
            return self._complete_progression_recovery(proposal, receipt)
        except GatewayError as exc:
            self._mark_receipt_validation_failed(proposal, exc)
        except Exception as exc:  # noqa: BLE001 - fresh snapshot transport
            self._mark_progression_recovery_pending(proposal, exc)

    def _resume_progression_recovery(
        self,
        proposal: Proposal,
    ) -> dict[str, Any]:
        assert proposal.project_id is not None
        try:
            receipt = self._progression_receipt(
                proposal.proposal_id,
                proposal.project_id,
            )
        except Exception as lookup_error:  # noqa: BLE001 - transport boundary
            self._keep_progression_recovery_pending(
                proposal,
                f"Receipt lookup was inconclusive: {lookup_error}",
                cause=lookup_error,
            )
        if receipt is None:
            with self._lock:
                may_resend = not (
                    proposal.progression_resend_attempted
                    or proposal.progression_receipt_observed
                )
            if may_resend:
                return self._retry_progression_once(proposal)
            self._keep_progression_recovery_pending(
                proposal,
                "Core reported that no receipt is currently available and "
                "the single bounded resend has already been consumed.",
            )
        try:
            return self._complete_progression_recovery(proposal, receipt)
        except GatewayError as exc:
            self._mark_receipt_validation_failed(proposal, exc)
        except Exception as exc:  # noqa: BLE001 - fresh snapshot transport
            self._mark_progression_recovery_pending(proposal, exc)

    def _recover_unknown_durable_proposal(
        self,
        proposal_id: str,
    ) -> dict[str, Any]:
        if _IDEMPOTENCY_KEY_RE.fullmatch(proposal_id or "") is None:
            raise GatewayError("Unknown proposal id.")
        project_id = self._project_id()
        try:
            timeline_receipt = self._timeline_receipt(proposal_id, project_id)
            canvas_receipt = self._canvas_plot_receipt(proposal_id, project_id)
            graph_receipt = self._knowledge_graph_receipt(
                proposal_id,
                project_id,
            )
            continuity_receipt = self._continuity_receipt(
                proposal_id,
                project_id,
            )
            progression_receipt = self._progression_receipt(
                proposal_id,
                project_id,
            )
        except Exception as exc:
            raise GatewayError(
                "Unknown proposal id; durable command receipt recovery could "
                "not be verified across Timeline, Canvas Plot, and Knowledge "
                f"Graph, Continuity, and Progressions: {exc}"
            ) from exc

        receipts_present = sum(
            receipt is not None
            for receipt in (
                timeline_receipt,
                canvas_receipt,
                graph_receipt,
                continuity_receipt,
                progression_receipt,
            )
        )
        if receipts_present > 1:
            raise GatewayError(
                "Durable receipt capability collision across Timeline, Canvas "
                "Plot, Knowledge Graph, Continuity, and Progressions; recovery "
                "failed closed."
            )
        if timeline_receipt is not None:
            receipt = self._validate_timeline_receipt_shape(
                timeline_receipt,
                project_id,
            )
            result = self._recovered_timeline_result(
                project_id,
                proposal_id,
                receipt,
            )
            return {
                "proposal_id": proposal_id,
                "operation": f"timeline_{receipt['command_kind']}",
                "summary": "Recovered durable Timeline command receipt.",
                "project_id": project_id,
                "state": "applied",
                "recovered_from_core": True,
                "request_digest": receipt["request_digest"],
                "request": None,
                "review": {"recovered_receipt": copy.deepcopy(receipt)},
                "requires_user_approval": True,
                "receipt": receipt,
                "result": result,
            }
        if canvas_receipt is not None:
            receipt = self._validate_canvas_plot_receipt_shape(
                canvas_receipt,
                project_id,
            )
            result = self._recovered_canvas_plot_result(
                project_id,
                proposal_id,
                receipt,
            )
            return {
                "proposal_id": proposal_id,
                "operation": f"canvas_plot_{receipt['command_kind']}",
                "summary": "Recovered durable Canvas Plot command receipt.",
                "project_id": project_id,
                "state": "applied",
                "recovered_from_core": True,
                "request_digest": receipt["request_digest"],
                "request": None,
                "review": {"recovered_receipt": copy.deepcopy(receipt)},
                "requires_user_approval": True,
                "receipt": receipt,
                "result": result,
            }
        if graph_receipt is not None:
            receipt = self._validate_knowledge_graph_receipt_shape(
                graph_receipt,
                project_id,
            )
            result = self._recovered_knowledge_graph_result(
                project_id,
                proposal_id,
                receipt,
            )
            return {
                "proposal_id": proposal_id,
                "operation": f"knowledge_graph_{receipt['command_kind']}",
                "summary": "Recovered durable Knowledge Graph command receipt.",
                "project_id": project_id,
                "state": "applied",
                "recovered_from_core": True,
                "request_digest": receipt["request_digest"],
                "request": None,
                "review": {"recovered_receipt": copy.deepcopy(receipt)},
                "requires_user_approval": True,
                "receipt": receipt,
                "result": result,
            }
        if continuity_receipt is not None:
            receipt = self._validate_continuity_receipt_shape(
                continuity_receipt,
                project_id,
            )
            result = self._recovered_continuity_result(
                project_id,
                proposal_id,
                receipt,
            )
            return {
                "proposal_id": proposal_id,
                "operation": f"continuity_{receipt['command_kind']}",
                "summary": "Recovered durable Continuity command receipt.",
                "project_id": project_id,
                "state": "applied",
                "recovered_from_core": True,
                "request_digest": receipt["request_digest"],
                "request": None,
                "review": {"recovered_receipt": copy.deepcopy(receipt)},
                "requires_user_approval": True,
                "receipt": receipt,
                "result": result,
            }
        if progression_receipt is not None:
            receipt = self._validate_progression_receipt_shape(
                progression_receipt,
                project_id,
            )
            result = self._recovered_progression_result(
                project_id,
                proposal_id,
                receipt,
            )
            return {
                "proposal_id": proposal_id,
                "operation": f"progression_{receipt['command_kind']}",
                "summary": "Recovered durable Progressions command receipt.",
                "project_id": project_id,
                "state": "applied",
                "recovered_from_core": True,
                "request_digest": receipt["request_digest"],
                "request": None,
                "review": {"recovered_receipt": copy.deepcopy(receipt)},
                "requires_user_approval": True,
                "receipt": receipt,
                "result": result,
            }
        raise GatewayError("Unknown proposal id.")

    def _proposal(self, proposal_id: str) -> Proposal:
        proposal = self._proposals.get(proposal_id)
        if proposal is None:
            raise GatewayError("Unknown proposal id.")
        return proposal

    def _expire(
        self,
        proposal: Proposal,
        now: float | None = None,
        *,
        raise_error: bool = True,
    ) -> None:
        if proposal.state == "pending" and proposal.expires_at <= (now or time.time()):
            proposal.state = "failed"
            proposal.error = "Proposal expired; create a fresh proposal from current state."
        if (
            raise_error
            and proposal.state == "failed"
            and proposal.error.startswith("Proposal expired")
        ):
            raise GatewayError(proposal.error)

    def _prune_expired(self, now: float) -> None:
        for proposal in self._proposals.values():
            # Listing or creating proposals must not fail merely because an old
            # proposal crossed its TTL. Mark it failed; direct access/apply will
            # still surface the expiry error.
            self._expire(proposal, now, raise_error=False)

    # -- Focused proposal builders ---------------------------------------

    def propose_continuity_command(
        self,
        command: dict[str, Any],
    ) -> dict[str, Any]:
        """Store one exact Continuity decision after a revisioned preflight."""
        pid = self._project_id()
        normalized = _normalize_continuity_command(command)
        current = self.client.get_continuity(pid)
        current_project_id = (
            current.get("project_id") if isinstance(current, dict) else None
        )
        if (
            not isinstance(current, dict)
            or isinstance(current_project_id, bool)
            or not isinstance(current_project_id, int)
            or current_project_id != pid
        ):
            raise GatewayError(
                "The LogosForge API returned an invalid Continuity report."
            )
        revision = current.get("review_revision")
        if (
            not isinstance(revision, str)
            or _LOWER_SHA256_RE.fullmatch(revision) is None
        ):
            raise GatewayError(
                "The LogosForge API returned an invalid Continuity review revision."
            )
        if revision != normalized["expected_revision"]:
            raise GatewayError(
                "expected_revision does not match the current Continuity report. "
                "Read it again with logosforge_get_story_diagnostics using "
                "report='continuity' and create a fresh proposal."
            )
        raw_issues = current.get("issues")
        if not isinstance(raw_issues, list):
            raise GatewayError(
                "The LogosForge API returned an invalid Continuity issue list."
            )
        matches = [
            issue
            for issue in raw_issues
            if isinstance(issue, dict)
            and issue.get("id") == normalized["issue_id"]
        ]
        if len(matches) != 1 or matches[0].get("status") != "open":
            raise GatewayError(
                "The exact open Continuity issue is not present in the current "
                "report. Read it again and create a fresh proposal."
            )
        issue = matches[0]
        fingerprint = issue.get("review_fingerprint")
        if (
            not isinstance(fingerprint, str)
            or _LOWER_SHA256_RE.fullmatch(fingerprint) is None
        ):
            raise GatewayError(
                "The LogosForge API returned an invalid Continuity issue "
                "fingerprint."
            )
        if not secrets.compare_digest(
            fingerprint,
            normalized["expected_issue_fingerprint"],
        ):
            raise GatewayError(
                "expected_issue_fingerprint does not match the current derived "
                "finding. Read the Continuity report again and create a fresh "
                "proposal."
            )

        kind = normalized["kind"]
        verb = {
            "defer_issue": "Defer",
            "dismiss_issue": "Dismiss",
            "resolve_issue": "Resolve",
        }[kind]
        title = _preview(issue.get("title"), 500)
        summary = f"{verb} Continuity issue {title or normalized['issue_id']!r}."
        effects = {
            "defer_issue": (
                "Persist a deferred review decision so this exact finding no "
                "longer appears in the open queue."
            ),
            "dismiss_issue": (
                "Persist a dismissed review decision so this exact finding no "
                "longer appears in the open queue."
            ),
            "resolve_issue": (
                "Persist a resolved review decision so this exact finding no "
                "longer appears in the open queue."
            ),
        }
        related_scene_ids = issue.get("related_scene_ids")
        if not isinstance(related_scene_ids, list) or any(
            isinstance(scene_id, bool) or not isinstance(scene_id, int)
            for scene_id in related_scene_ids
        ):
            raise GatewayError(
                "The LogosForge API returned invalid Continuity scene evidence."
            )
        review = {
            "continuity_revision": revision,
            "command_kind": kind,
            "destructive": kind == "dismiss_issue",
            "requires_destructive_confirmation": kind == "dismiss_issue",
            "issue": {
                "id": normalized["issue_id"],
                "review_fingerprint": fingerprint,
                "issue_type": _preview(issue.get("issue_type"), 128),
                "dimension": _preview(issue.get("dimension"), 128),
                "severity": _preview(issue.get("severity"), 64),
                "confidence": _preview(issue.get("confidence"), 64),
                "title": title,
                "explanation": _preview(issue.get("explanation"), 2_000),
                "suggested_action": _preview(
                    issue.get("suggested_action"),
                    2_000,
                ),
                "related_scene_ids": _bounded_sequence(
                    related_scene_ids,
                    limit=100,
                ),
                "status": "open",
            },
            "effect": effects[kind],
        }
        return self.propose_request(
            operation=f"continuity_{kind}",
            method="POST",
            path=self.client.project_path("continuity/commands", pid),
            body=normalized,
            summary=summary,
            project_id=pid,
            review=review,
        )

    def propose_knowledge_graph_command(
        self,
        command: dict[str, Any],
        *,
        hidden_edge_offset: int | None = None,
    ) -> dict[str, Any]:
        """Store one exact graph review command after a revisioned preflight.

        Restores are preflighted against a caller-selected page from the
        complete hidden-edge queue.  This avoids both the Project Map's bounded
        hidden diagnostic subset and an unbounded server-side scan.
        """
        pid = self._project_id()
        normalized = _normalize_knowledge_graph_command(command)
        kind = normalized["kind"]

        if kind == "unhide_edge":
            if (
                isinstance(hidden_edge_offset, bool)
                or not isinstance(hidden_edge_offset, int)
                or hidden_edge_offset < 0
            ):
                raise GatewayError(
                    "unhide_edge requires the non-negative hidden_edge_offset "
                    "returned by the reviewed hidden-edge page."
                )
            current = self.client.get_knowledge_graph_hidden_edges(
                pid,
                offset=hidden_edge_offset,
                limit=100,
            )
            source_tool = "logosforge_get_knowledge_graph_hidden_edges"
        else:
            if hidden_edge_offset is not None:
                raise GatewayError(
                    "hidden_edge_offset is accepted only for unhide_edge."
                )
            current = self.client.get_knowledge_graph(
                pid,
                focus_key=normalized["source"],
                depth=1,
                limit=200,
                include_inferred=True,
                view_mode="project_map",
            )
            source_tool = "logosforge_get_knowledge_graph"

        current_project_id = (
            current.get("project_id") if isinstance(current, dict) else None
        )
        if (
            not isinstance(current, dict)
            or isinstance(current_project_id, bool)
            or not isinstance(current_project_id, int)
            or current_project_id != pid
        ):
            raise GatewayError(
                "The LogosForge API returned an invalid Knowledge Graph snapshot."
            )
        revision = current.get("revision")
        if (
            not isinstance(revision, str)
            or _LOWER_SHA256_RE.fullmatch(revision) is None
        ):
            raise GatewayError(
                "The LogosForge API returned an invalid Knowledge Graph revision."
            )
        if revision != normalized["expected_revision"]:
            raise GatewayError(
                "expected_revision does not match the current Knowledge Graph. "
                f"Read it again with {source_tool} and create a fresh proposal."
            )
        if kind == "unhide_edge" and (
            current.get("offset") != hidden_edge_offset
            or current.get("limit") != 100
        ):
            raise GatewayError(
                "The LogosForge API returned the wrong hidden-edge page."
            )

        raw_edges = current.get("edges")
        raw_nodes = current.get("nodes")
        if not isinstance(raw_edges, list) or not isinstance(raw_nodes, list):
            raise GatewayError(
                "The LogosForge API returned an invalid Knowledge Graph snapshot."
            )
        edge = next(
            (
                row for row in raw_edges
                if isinstance(row, dict)
                and row.get("source") == normalized["source"]
                and row.get("target") == normalized["target"]
                and row.get("edge_type") == normalized["edge_type"]
            ),
            None,
        )
        if edge is None:
            if kind == "unhide_edge":
                raise GatewayError(
                    "The exact hidden edge is not present on the reviewed page. "
                    "Read the queue again and pass that page's offset."
                )
            raise GatewayError(
                "The exact directional edge is not present in the current "
                "Knowledge Graph neighborhood."
            )

        state_fields = ("is_inferred", "is_user_confirmed", "is_hidden")
        if any(not isinstance(edge.get(field), bool) for field in state_fields):
            raise GatewayError(
                "The LogosForge API returned invalid Knowledge Graph edge state."
            )
        if kind in {"confirm_edge", "hide_edge"} and not (
            edge["is_inferred"]
            and not edge["is_user_confirmed"]
            and not edge["is_hidden"]
        ):
            raise GatewayError(
                f"{kind} requires a visible, unconfirmed inferred edge."
            )
        if kind == "unhide_edge" and not edge["is_hidden"]:
            raise GatewayError("unhide_edge requires a persisted hidden edge.")

        nodes = [row for row in raw_nodes if isinstance(row, dict)]

        def node_review(key: str) -> dict[str, Any]:
            node = next((row for row in nodes if row.get("key") == key), None)
            if node is None:
                raise GatewayError(
                    "The reviewed edge is missing an endpoint node."
                )
            return {
                "key": key,
                "node_type": _preview(node.get("node_type"), 128),
                "label": _preview(node.get("label"), 512),
                "summary": _preview(node.get("summary"), 1_000),
            }

        source = node_review(normalized["source"])
        target = node_review(normalized["target"])
        verb = {
            "confirm_edge": "Confirm",
            "hide_edge": "Hide",
            "unhide_edge": "Restore",
        }[kind]
        summary = (
            f"{verb} Knowledge Graph edge {normalized['edge_type']!r} from "
            f"{_preview(source['label'] or source['key'], 200)!r} to "
            f"{_preview(target['label'] or target['key'], 200)!r}."
        )
        effects = {
            "confirm_edge": (
                "Persist this inferred directional relationship as an explicit "
                "user-confirmed edge."
            ),
            "hide_edge": (
                "Persist a hidden review decision for this inferred edge. It "
                "remains recoverable through the hidden-edge queue."
            ),
            "unhide_edge": (
                "Remove the hidden decision. A confirmed edge remains explicit; "
                "an unconfirmed edge is visible only while its inferred basis "
                "exists."
            ),
        }
        review: dict[str, Any] = {
            "knowledge_graph_revision": revision,
            "command_kind": kind,
            "destructive": kind == "hide_edge",
            "requires_destructive_confirmation": kind == "hide_edge",
            "source": source,
            "target": target,
            "edge": {
                "source": normalized["source"],
                "target": normalized["target"],
                "edge_type": normalized["edge_type"],
                "confidence": _preview(edge.get("confidence"), 32),
                "provenance": _preview(edge.get("provenance"), 512),
                "source_system": _preview(edge.get("source_system"), 128),
                "explanation": _preview(edge.get("explanation"), 1_000),
                "is_user_confirmed": edge["is_user_confirmed"],
                "is_inferred": edge["is_inferred"],
                "is_hidden": edge["is_hidden"],
            },
            "effect": effects[kind],
        }
        if hidden_edge_offset is not None:
            review["hidden_edge_offset"] = hidden_edge_offset

        return self.propose_request(
            operation=f"knowledge_graph_{kind}",
            method="POST",
            path=self.client.project_path("knowledge-graph/commands", pid),
            body=normalized,
            summary=summary,
            project_id=pid,
            review=review,
        )

    def propose_canvas_plot_command(
        self, command: dict[str, Any],
    ) -> dict[str, Any]:
        """Store one exact Canvas Plot command after a revisioned preflight.

        Core compares the same revision again inside the write transaction.
        A generic digest guard would add a second read without strengthening
        that atomic compare-and-swap boundary, so Canvas proposals rely on the
        canonical board revision just as Timeline proposals do.
        """
        pid = self._project_id()
        normalized = _normalize_canvas_plot_command(command)
        current = self.client.get_canvas_plot(pid)
        if not isinstance(current, dict):
            raise GatewayError(
                "The LogosForge API returned an invalid Canvas Plot snapshot."
            )
        revision = current.get("revision")
        if revision != normalized["expected_revision"]:
            raise GatewayError(
                "expected_revision does not match the current Canvas Plot. Read it "
                "again with logosforge_get_canvas_plot and create a fresh proposal."
            )

        nodes = [row for row in current.get("nodes", []) if isinstance(row, dict)]
        links = [row for row in current.get("links", []) if isinstance(row, dict)]
        frames = [row for row in current.get("frames", []) if isinstance(row, dict)]
        node_order = [
            int(row["id"]) for row in nodes if isinstance(row.get("id"), int)
        ]

        def node_by_id(node_id: int) -> dict[str, Any]:
            node = next((row for row in nodes if row.get("id") == node_id), None)
            if node is None:
                raise GatewayError(
                    f"Canvas Plot node {node_id} is not present in the current snapshot."
                )
            return node

        def link_by_id(link_id: int) -> dict[str, Any]:
            link = next((row for row in links if row.get("id") == link_id), None)
            if link is None:
                raise GatewayError(
                    f"Canvas Plot link {link_id} is not present in the current snapshot."
                )
            return link

        def frame_by_id(frame_id: int) -> dict[str, Any]:
            frame = next((row for row in frames if row.get("id") == frame_id), None)
            if frame is None:
                raise GatewayError(
                    f"Canvas Plot frame {frame_id} is not present in the current snapshot."
                )
            return frame

        def validate_scene(scene_id: int | None) -> dict[str, Any] | None:
            if scene_id is None:
                return None
            scene = self.client.get_scene(scene_id, pid)
            if not isinstance(scene, dict) or scene.get("id") != scene_id:
                raise GatewayError(
                    f"Scene {scene_id} is not present in the selected project."
                )
            return scene

        kind = normalized["kind"]
        destructive = kind in {"delete_node", "delete_link", "delete_frame"}
        review: dict[str, Any] = {
            "canvas_plot_revision": revision,
            "command_kind": kind,
            "destructive": destructive,
            "requires_destructive_confirmation": destructive,
        }

        if kind == "create_node":
            requested_index = normalized.get("index")
            index = len(nodes) if requested_index is None else requested_index
            if index > len(nodes):
                raise GatewayError("index is outside the available node range.")
            scene = validate_scene(normalized.get("scene_id"))
            body = normalized.get("body", "")
            after_order: list[Any] = list(node_order)
            after_order.insert(index, "new")
            title = normalized.get("title", "")
            summary = f"Create Canvas Plot node {_preview(title, 200)!r} at index {index}."
            review.update({
                "before": {"node_order": _bounded_sequence(node_order)},
                "after_intent": {
                    "title": _preview(title, 500),
                    "body": {
                        "length": len(body),
                        "sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
                        "preview": _preview(body, 500),
                    },
                    "x": normalized.get("x", 0.0),
                    "y": normalized.get("y", 0.0),
                    "width": normalized.get("width", 180.0),
                    "height": normalized.get("height", 110.0),
                    "color_label": normalized.get("color_label", ""),
                    "group_label": _preview(normalized.get("group_label", ""), 500),
                    "scene": None if scene is None else {
                        "id": scene.get("id"),
                        "title": _preview(scene.get("title"), 500),
                    },
                    "index": index,
                    "node_order": _bounded_sequence(after_order),
                },
            })

        elif kind == "update_node":
            node_id = normalized["node_id"]
            node = node_by_id(node_id)
            if "index" in normalized and normalized["index"] >= len(nodes):
                raise GatewayError("index is outside the available node range.")
            scene = None
            if "scene_id" in normalized:
                scene = validate_scene(normalized["scene_id"])
            changes: dict[str, Any] = {}
            changed = False
            defaults: dict[str, Any] = {
                "title": "", "body": "", "x": 0.0, "y": 0.0,
                "width": 180.0, "height": 110.0, "color_label": "",
                "group_label": "", "scene_id": None,
            }
            for field in (
                "title", "body", "x", "y", "width", "height", "color_label",
                "group_label", "scene_id",
            ):
                if field not in normalized:
                    continue
                before = node.get(field, defaults[field])
                after = normalized[field]
                if before != after:
                    changed = True
                if field == "body":
                    changes[field] = _content_review(str(before or ""), str(after or ""))
                elif field in {"title", "color_label", "group_label"}:
                    changes[field] = {
                        "before": _preview(before, 500),
                        "after": _preview(after, 500),
                    }
                else:
                    changes[field] = {"before": before, "after": after}
            if "index" in normalized:
                current_index = node_order.index(node_id)
                after_index = normalized["index"]
                if current_index != after_index:
                    changed = True
                changes["index"] = {
                    "before": current_index,
                    "after": after_index,
                }
            if not changed:
                raise GatewayError(
                    "The requested node update would not change the Canvas Plot."
                )
            summary = (
                f"Update Canvas Plot node {node_id} "
                f"({_preview(node.get('title'), 200)!r})."
            )
            review.update({
                "node": {
                    "id": node_id,
                    "title": _preview(node.get("title"), 500),
                    "scene_id": node.get("scene_id"),
                },
                "changes": changes,
            })
            if "scene_id" in normalized:
                review["scene_after"] = None if scene is None else {
                    "id": scene.get("id"),
                    "title": _preview(scene.get("title"), 500),
                }

        elif kind == "delete_node":
            node_id = normalized["node_id"]
            node = node_by_id(node_id)
            incident_ids = [
                row["id"] for row in links
                if row.get("source_node_id") == node_id
                or row.get("target_node_id") == node_id
            ]
            summary = (
                f"Delete Canvas Plot node {node_id} "
                f"({_preview(node.get('title'), 200)!r}) and "
                f"{len(incident_ids)} incident link(s)."
            )
            review.update({
                "node": {
                    "id": node_id,
                    "title": _preview(node.get("title"), 500),
                    "scene_id": node.get("scene_id"),
                },
                "incident_link_ids": _bounded_sequence(incident_ids),
                "effect": (
                    "The node and its incident Canvas Plot links are deleted. "
                    "Any hidden same-project legacy incident link rows are also "
                    "cleaned up. Any linked manuscript scene remains unchanged."
                ),
            })

        elif kind == "create_link":
            source_id = normalized["source_node_id"]
            target_id = normalized["target_node_id"]
            if source_id == target_id:
                raise GatewayError("A Canvas Plot link cannot connect a node to itself.")
            source = node_by_id(source_id)
            target = node_by_id(target_id)
            duplicate = next(
                (
                    row for row in links
                    if {row.get("source_node_id"), row.get("target_node_id")}
                    == {source_id, target_id}
                ),
                None,
            )
            if duplicate is not None:
                raise GatewayError(
                    f"Canvas Plot nodes {source_id} and {target_id} are already linked."
                )
            label = normalized.get("label", "")
            color_label = normalized.get("color_label", "gray") or "gray"
            summary = (
                f"Create Canvas Plot link from node {source_id} to node {target_id}."
            )
            review.update({
                "source": {
                    "id": source_id,
                    "title": _preview(source.get("title"), 500),
                },
                "target": {
                    "id": target_id,
                    "title": _preview(target.get("title"), 500),
                },
                "after_intent": {
                    "label": _preview(label, 500),
                    "color_label": color_label,
                    "link_type": normalized.get("link_type", ""),
                },
            })

        elif kind == "update_link":
            link_id = normalized["link_id"]
            link = link_by_id(link_id)
            changes: dict[str, Any] = {}
            changed = False
            for field, default in (
                ("label", ""), ("color_label", "gray"), ("link_type", ""),
            ):
                if field not in normalized:
                    continue
                before = link.get(field, default)
                after = normalized[field]
                effective_after = after or "gray" if field == "color_label" else after
                if before != effective_after:
                    changed = True
                changes[field] = {
                    "before": _preview(before, 500),
                    "after": _preview(effective_after, 500),
                }
            if not changed:
                raise GatewayError(
                    "The requested link update would not change the Canvas Plot."
                )
            summary = f"Update Canvas Plot link {link_id}."
            review.update({
                "link": {
                    "id": link_id,
                    "source_node_id": link.get("source_node_id"),
                    "target_node_id": link.get("target_node_id"),
                },
                "changes": changes,
            })

        elif kind == "delete_link":
            link_id = normalized["link_id"]
            link = link_by_id(link_id)
            summary = f"Delete Canvas Plot link {link_id}."
            review.update({
                "link": {
                    "id": link_id,
                    "source_node_id": link.get("source_node_id"),
                    "target_node_id": link.get("target_node_id"),
                    "label": _preview(link.get("label"), 500),
                },
                "effect": (
                    "This undirected Canvas Plot link is deleted together with "
                    "any hidden same-project legacy reverse or duplicate rows. "
                    "Nodes and manuscript scenes remain unchanged."
                ),
            })

        elif kind == "create_frame":
            title = normalized.get("title", "")
            summary = f"Create Canvas Plot frame {_preview(title, 200)!r}."
            review["after_intent"] = {
                "title": _preview(title, 500),
                "color_label": normalized.get("color_label", ""),
                "x": normalized.get("x", 0.0),
                "y": normalized.get("y", 0.0),
                "width": normalized.get("width", 360.0),
                "height": normalized.get("height", 260.0),
            }

        elif kind == "update_frame":
            frame_id = normalized["frame_id"]
            frame = frame_by_id(frame_id)
            changes: dict[str, Any] = {}
            changed = False
            defaults = {
                "title": "", "color_label": "", "x": 0.0, "y": 0.0,
                "width": 360.0, "height": 260.0,
            }
            for field in defaults:
                if field not in normalized:
                    continue
                before = frame.get(field, defaults[field])
                after = normalized[field]
                if before != after:
                    changed = True
                changes[field] = {
                    "before": _preview(before, 500) if isinstance(before, str) else before,
                    "after": _preview(after, 500) if isinstance(after, str) else after,
                }
            if not changed:
                raise GatewayError(
                    "The requested frame update would not change the Canvas Plot."
                )
            summary = (
                f"Update Canvas Plot frame {frame_id} "
                f"({_preview(frame.get('title'), 200)!r})."
            )
            review.update({
                "frame": {
                    "id": frame_id,
                    "title": _preview(frame.get("title"), 500),
                },
                "changes": changes,
            })

        else:
            frame_id = normalized["frame_id"]
            frame = frame_by_id(frame_id)
            summary = (
                f"Delete Canvas Plot frame {frame_id} "
                f"({_preview(frame.get('title'), 200)!r})."
            )
            review.update({
                "frame": {
                    "id": frame_id,
                    "title": _preview(frame.get("title"), 500),
                },
                "effect": (
                    "Only this visual Canvas Plot frame is deleted; nodes, links, "
                    "and manuscript scenes remain unchanged."
                ),
            })

        return self.propose_request(
            operation=f"canvas_plot_{kind}",
            method="POST",
            path=self.client.project_path("canvas-plot/commands", pid),
            body=normalized,
            summary=summary,
            project_id=pid,
            review=review,
        )

    def propose_progression_command(
        self,
        command: dict[str, Any],
    ) -> dict[str, Any]:
        """Store one exact Progressions command after a revisioned preflight."""
        pid = self._project_id()
        normalized = _normalize_progression_command(command)
        current = self.client.get_progressions(pid)
        if not isinstance(current, dict):
            raise GatewayError(
                "The LogosForge API returned an invalid Progressions snapshot."
            )
        if current.get("revision") != normalized["expected_revision"]:
            raise GatewayError(
                "expected_revision does not match the current Progressions "
                "workspace. Read it again with logosforge_get_progressions "
                "and create a fresh proposal."
            )
        tracks = [row for row in current.get("tracks", []) if isinstance(row, dict)]
        track_by_id = {
            row.get("id"): row
            for row in tracks
            if isinstance(row.get("id"), int)
        }
        beats = [
            beat
            for track in tracks
            for beat in track.get("beats", [])
            if isinstance(track.get("beats", []), list) and isinstance(beat, dict)
        ]
        beat_by_id = {
            row.get("id"): row
            for row in beats
            if isinstance(row.get("id"), int)
        }
        kind = normalized["kind"]

        def validate_subjects(
            track_kind: Any,
            primary_id: Any,
            secondary_id: Any,
        ) -> None:
            if track_kind in {"story", "custom"}:
                if primary_id is not None or secondary_id is not None:
                    raise GatewayError(
                        "Story and custom tracks cannot have PSYKE subjects."
                    )
                return
            if track_kind == "relationship":
                if (
                    primary_id is None
                    or secondary_id is None
                    or primary_id == secondary_id
                ):
                    raise GatewayError(
                        "Relationship tracks require two distinct PSYKE subjects."
                    )
                required_types: dict[int, set[str] | None] = {
                    primary_id: None,
                    secondary_id: None,
                }
            else:
                if primary_id is None or secondary_id is not None:
                    raise GatewayError(
                        f"{track_kind.capitalize()} tracks require exactly one "
                        "compatible PSYKE subject."
                    )
                required_types = {
                    primary_id: {
                        "character": {"character"},
                        "theme": {"theme"},
                        "world": {"place", "object", "lore"},
                    }[track_kind]
                }
            entries = self.client.list_psyke_entries(pid)
            entry_by_id = {
                row.get("id"): row
                for row in entries
                if isinstance(row, dict) and isinstance(row.get("id"), int)
            }
            for entry_id, allowed_types in required_types.items():
                entry = entry_by_id.get(entry_id)
                if entry is None:
                    raise GatewayError(
                        f"PSYKE subject {entry_id} is not present in this project."
                    )
                if allowed_types is not None and entry.get("type") not in allowed_types:
                    raise GatewayError(
                        f"PSYKE subject {entry_id} is not compatible with a "
                        f"{track_kind} track."
                    )

        def validate_anchor(anchor: dict[str, Any]) -> None:
            anchor_kind = anchor.get("anchor_kind", "unanchored")
            scene_id = anchor.get("scene_id")
            anchor_ref = anchor.get("anchor_ref")
            anchor_label = anchor.get("anchor_label", "")
            if anchor_kind == "unanchored":
                valid = (
                    scene_id is None
                    and anchor_ref is None
                    and anchor_label == ""
                )
            elif anchor_kind == "scene":
                valid = scene_id is not None and anchor_ref is None
            else:
                valid = (
                    scene_id is None
                    and isinstance(anchor_ref, str)
                    and bool(anchor_ref.strip())
                )
            if not valid:
                raise GatewayError(
                    "Progression anchor fields do not match anchor_kind: "
                    "unanchored has no target, scene requires scene_id only, "
                    "and document_block requires anchor_ref only."
                )

        review: dict[str, Any] = {
            "command": copy.deepcopy(normalized),
            "before_summary": copy.deepcopy(current.get("summary", {})),
        }
        destructive = kind in {"delete_track", "delete_beat"}
        if "track_id" in normalized:
            track = track_by_id.get(normalized["track_id"])
            if track is None:
                raise GatewayError(
                    f"Progression track {normalized['track_id']} is not present "
                    "in the current snapshot."
                )
            review["track"] = {
                "id": track.get("id"),
                "kind": track.get("kind"),
                "title": _preview(track.get("title"), 500),
                "beat_count": len(track.get("beats", []))
                if isinstance(track.get("beats", []), list) else 0,
            }
        if "beat_id" in normalized:
            beat = beat_by_id.get(normalized["beat_id"])
            if beat is None:
                raise GatewayError(
                    f"Progression beat {normalized['beat_id']} is not present "
                    "in the current snapshot."
                )
            review["beat"] = {
                "id": beat.get("id"),
                "track_id": beat.get("track_id"),
                "text": _preview(beat.get("text"), 1_000),
                "anchor_kind": beat.get("anchor_kind"),
                "scene_id": beat.get("scene_id"),
                "anchor_ref": beat.get("anchor_ref"),
                "anchor_label": _preview(beat.get("anchor_label"), 500),
            }
        if kind == "create_track":
            validate_subjects(
                normalized["track_kind"],
                normalized.get("primary_psyke_entry_id"),
                normalized.get("secondary_psyke_entry_id"),
            )
            index = normalized.get("index")
            if index is not None and index > len(tracks):
                raise GatewayError("Progression track index is outside the available range.")
        elif kind == "update_track":
            track = track_by_id[normalized["track_id"]]
            # A migrated legacy compatibility track can intentionally carry a
            # generic PSYKE subject that new canonical tracks cannot create.
            # Core permits ordinary title/description/color edits while
            # protecting that legacy subject.  Revalidate only when this
            # proposal actually attempts to change kind or subject fields.
            if {
                "track_kind",
                "primary_psyke_entry_id",
                "secondary_psyke_entry_id",
            }.intersection(normalized):
                validate_subjects(
                    normalized.get("track_kind", track.get("kind")),
                    normalized.get(
                        "primary_psyke_entry_id",
                        track.get("primary_psyke_entry_id"),
                    ),
                    normalized.get(
                        "secondary_psyke_entry_id",
                        track.get("secondary_psyke_entry_id"),
                    ),
                )
        elif kind == "create_beat":
            validate_anchor({
                "anchor_kind": normalized.get("anchor_kind", "unanchored"),
                "scene_id": normalized.get("scene_id"),
                "anchor_ref": normalized.get("anchor_ref"),
                "anchor_label": normalized.get("anchor_label", ""),
            })
            track = track_by_id[normalized["track_id"]]
            track_beats = track.get("beats", [])
            beat_count = len(track_beats) if isinstance(track_beats, list) else 0
            index = normalized.get("index")
            if index is not None and index > beat_count:
                raise GatewayError("Progression beat index is outside the available range.")
        elif kind == "update_beat":
            beat = beat_by_id[normalized["beat_id"]]
            validate_anchor({
                "anchor_kind": normalized.get(
                    "anchor_kind", beat.get("anchor_kind", "unanchored"),
                ),
                "scene_id": normalized.get("scene_id", beat.get("scene_id")),
                "anchor_ref": normalized.get("anchor_ref", beat.get("anchor_ref")),
                "anchor_label": normalized.get(
                    "anchor_label", beat.get("anchor_label", ""),
                ),
            })
        if kind == "reorder_tracks":
            current_ids = [row.get("id") for row in tracks]
            if normalized["track_ids"] != current_ids and set(
                normalized["track_ids"]
            ) != set(current_ids):
                raise GatewayError(
                    "track_ids must contain every current progression track exactly once."
                )
            review["track_order"] = {
                "before": current_ids,
                "after": normalized["track_ids"],
            }
        elif kind == "reorder_beats":
            track = track_by_id.get(normalized["track_id"])
            before = track.get("beats", []) if isinstance(track, dict) else []
            current_ids = [row.get("id") for row in before if isinstance(row, dict)]
            if normalized["beat_ids"] != current_ids and set(
                normalized["beat_ids"]
            ) != set(current_ids):
                raise GatewayError(
                    "beat_ids must contain every current beat in the track exactly once."
                )
            review["beat_order"] = {
                "before": current_ids,
                "after": normalized["beat_ids"],
            }
        summary = kind.replace("_", " ").capitalize() + "."
        if destructive:
            summary = "Delete " + kind.removeprefix("delete_").replace("_", " ") + "."
            review["destructive"] = True
        return self.propose_request(
            operation=f"progression_{kind}",
            method="POST",
            path=self.client.project_path("progressions/commands", pid),
            body=normalized,
            summary=summary,
            project_id=pid,
            review=review,
        )

    def propose_timeline_command(
        self, command: dict[str, Any],
    ) -> dict[str, Any]:
        """Store one exact Timeline command after a revisioned preflight.

        The command endpoint performs the authoritative revision comparison in
        the same database transaction as its mutation.  Do not add a generic
        snapshot digest guard here: the Timeline revision intentionally ignores
        unrelated prose edits, while the rendered snapshot may still include
        fields that changed outside Timeline topology.
        """
        pid = self._project_id()
        normalized = _normalize_timeline_command(command)
        current = self.client.get_timeline(pid)
        if not isinstance(current, dict):
            raise GatewayError("The LogosForge API returned an invalid Timeline snapshot.")
        revision = current.get("revision")
        if revision != normalized["expected_revision"]:
            raise GatewayError(
                "expected_revision does not match the current Timeline. Read it "
                "again with logosforge_get_timeline and create a fresh proposal."
            )

        lanes = [row for row in current.get("lanes", []) if isinstance(row, dict)]
        events = [row for row in current.get("events", []) if isinstance(row, dict)]
        off_timeline = [
            row for row in current.get("off_timeline", []) if isinstance(row, dict)
        ]
        links = [
            row for row in current.get("links", []) if isinstance(row, dict)
        ]
        structure_links = [
            row for row in current.get("structure_links", [])
            if isinstance(row, dict)
        ]
        lane_order = [int(row["id"]) for row in lanes if isinstance(row.get("id"), int)]
        event_order = [
            int(row["id"]) for row in events if isinstance(row.get("id"), int)
        ]

        def lane_by_id(lane_id: int) -> dict[str, Any]:
            lane = next((row for row in lanes if row.get("id") == lane_id), None)
            if lane is None:
                raise GatewayError(
                    f"Timeline lane {lane_id} is not present in the current snapshot."
                )
            return lane

        def scene_by_id(scene_id: int) -> tuple[dict[str, Any], bool]:
            event = next((row for row in events if row.get("id") == scene_id), None)
            if event is not None:
                return event, True
            scene = next(
                (row for row in off_timeline if row.get("id") == scene_id), None,
            )
            if scene is None:
                raise GatewayError(
                    f"Scene {scene_id} is not present in the current Timeline snapshot."
                )
            return scene, False

        def event_by_id(scene_id: int) -> dict[str, Any]:
            event = next(
                (row for row in events if row.get("id") == scene_id), None,
            )
            if event is None:
                raise GatewayError(
                    f"Scene {scene_id} is not currently a Timeline event."
                )
            return event

        def link_by_id(link_id: int) -> dict[str, Any]:
            link = next((row for row in links if row.get("id") == link_id), None)
            if link is None:
                raise GatewayError(
                    f"Timeline link {link_id} is not present in the current snapshot."
                )
            return link

        def structure_link_by_id(structure_link_id: int) -> dict[str, Any]:
            link = next(
                (
                    row for row in structure_links
                    if row.get("id") == structure_link_id
                ),
                None,
            )
            if link is None:
                raise GatewayError(
                    "Timeline structure link "
                    f"{structure_link_id} is not present in the current snapshot."
                )
            return link

        structure_targets = {
            "act": {
                str(row.get("act", "")).strip()
                for row in (*events, *off_timeline)
                if str(row.get("act", "")).strip()
            },
            "chapter": {
                str(row.get("chapter", "")).strip()
                for row in (*events, *off_timeline)
                if str(row.get("chapter", "")).strip()
            },
        }

        kind = normalized["kind"]
        destructive = kind in {
            "delete_lane",
            "remove_event",
            "delete_link",
            "delete_structure_link",
        }
        review: dict[str, Any] = {
            "timeline_revision": revision,
            "command_kind": kind,
            "destructive": destructive,
            "requires_destructive_confirmation": destructive,
        }

        if kind == "create_lane":
            name = normalized["name"]
            duplicate = next(
                (
                    row for row in lanes
                    if str(row.get("name", "")).strip().casefold() == name.casefold()
                ),
                None,
            )
            if duplicate is not None:
                raise GatewayError(f"A Timeline lane named {name!r} already exists.")
            requested_index = normalized.get("index")
            index = len(lanes) if requested_index is None else requested_index
            if index > len(lanes):
                raise GatewayError("index is outside the available lane range.")
            after_order = list(lane_order)
            after_order.insert(index, "new")
            summary = f"Create Timeline lane {name!r} at index {index}."
            review.update({
                "before": {"lane_order": _bounded_sequence(lane_order)},
                "after_intent": {
                    "name": name,
                    "color_label": normalized.get("color_label", ""),
                    "index": index,
                    "lane_order": _bounded_sequence(after_order),
                },
            })

        elif kind == "update_lane":
            lane_id = normalized["lane_id"]
            lane = lane_by_id(lane_id)
            if "name" in normalized:
                wanted = normalized["name"].casefold()
                duplicate = next(
                    (
                        row for row in lanes
                        if row.get("id") != lane_id
                        and str(row.get("name", "")).strip().casefold() == wanted
                    ),
                    None,
                )
                if duplicate is not None:
                    raise GatewayError(
                        f"A Timeline lane named {normalized['name']!r} already exists."
                    )
            if "index" in normalized and normalized["index"] >= len(lanes):
                raise GatewayError("index is outside the available lane range.")
            changes: dict[str, Any] = {}
            for key in ("name", "color_label", "collapsed"):
                if key in normalized:
                    before_value = lane.get(
                        key, "" if key != "collapsed" else False,
                    )
                    if key in {"name", "color_label"}:
                        before_value = _preview(before_value, 500)
                    changes[key] = {
                        "before": before_value,
                        "after": normalized[key],
                    }
            if "index" in normalized:
                changes["index"] = {
                    "before": lane.get("order_index", lane_order.index(lane_id)),
                    "after": normalized["index"],
                }
            if all(change["before"] == change["after"] for change in changes.values()):
                raise GatewayError("The requested lane update would not change the Timeline.")
            members = [row["id"] for row in events if row.get("lane_id") == lane_id]
            summary = (
                f"Update Timeline lane {lane_id} "
                f"({_preview(lane.get('name'), 200)!r})."
            )
            review.update({
                "lane": {
                    "id": lane_id,
                    "name": _preview(lane.get("name"), 500),
                    "member_scene_ids": _bounded_sequence(members),
                },
                "changes": changes,
                "rename_updates_member_plotlines": "name" in normalized,
            })

        elif kind == "delete_lane":
            lane_id = normalized["lane_id"]
            lane = lane_by_id(lane_id)
            members = [row["id"] for row in events if row.get("lane_id") == lane_id]
            summary = (
                f"Delete Timeline lane {lane_id} "
                f"({_preview(lane.get('name'), 200)!r}); "
                f"keep its {len(members)} event(s) as Unassigned."
            )
            review.update({
                "lane": {
                    "id": lane_id,
                    "name": _preview(lane.get("name"), 500),
                    "member_scene_ids": _bounded_sequence(members),
                },
                "effect": (
                    "The lane is deleted. Its events remain on the Timeline in "
                    "Unassigned, and their manuscript scenes are not deleted."
                ),
            })

        elif kind == "place_event":
            scene_id = normalized["scene_id"]
            scene, on_timeline = scene_by_id(scene_id)
            lane_id = normalized["lane_id"]
            lane = lane_by_id(lane_id) if lane_id is not None else None
            current_event = scene if on_timeline else None
            requested_index = normalized.get("index")
            remaining = [value for value in event_order if value != scene_id]
            if requested_index is not None and requested_index > len(remaining):
                raise GatewayError("index is outside the available event range.")
            desired_order = None
            if requested_index is not None:
                desired_order = list(remaining)
                desired_order.insert(requested_index, scene_id)
            same_lane = on_timeline and current_event.get("lane_id") == lane_id
            if same_lane and requested_index is None:
                raise GatewayError(
                    "The scene is already in that Timeline lane; provide an index "
                    "only when an explicit custom-order move is intended."
                )
            if (
                same_lane
                and current.get("order_mode") == "custom"
                and desired_order == event_order
            ):
                raise GatewayError("The requested event placement would not change the Timeline.")
            target_name = (
                str(lane.get("name", "")) if lane is not None else "Unassigned"
            )
            before_plotline = (
                str(current_event.get("plotline", "")) if current_event else ""
            )
            after_plotline = str(lane.get("name", "")) if lane is not None else ""
            summary = (
                f"Place scene {scene_id} ({_preview(scene.get('title'), 200)!r}) "
                f"in Timeline lane {_preview(target_name, 200)!r}."
            )
            review.update({
                "scene": {
                    "id": scene_id,
                    "title": _preview(scene.get("title"), 500),
                },
                "before": {
                    "on_timeline": on_timeline,
                    "lane_id": current_event.get("lane_id") if current_event else None,
                    "one_based_display_order_index": (
                        current_event.get("order_index") if current_event else None
                    ),
                    "plotline": _preview(before_plotline, 500),
                },
                "after_intent": {
                    "lane_id": lane_id,
                    "lane_name": _preview(target_name, 500),
                    "zero_based_command_index": requested_index,
                    "order_mode": (
                        "custom" if requested_index is not None
                        else current.get("order_mode", "structural")
                    ),
                    "event_order": (
                        _bounded_sequence(desired_order)
                        if desired_order is not None else None
                    ),
                    "plotline": _preview(after_plotline, 500),
                },
                "changes_plotline": before_plotline != after_plotline,
            })

        elif kind == "remove_event":
            scene_id = normalized["scene_id"]
            scene = next((row for row in events if row.get("id") == scene_id), None)
            if scene is None:
                raise GatewayError(
                    f"Scene {scene_id} is not currently a Timeline event."
                )
            summary = (
                f"Remove scene {scene_id} ({_preview(scene.get('title'), 200)!r}) "
                "from the Timeline without deleting the manuscript scene."
            )
            review.update({
                "scene": {
                    "id": scene_id,
                    "title": _preview(scene.get("title"), 500),
                    "lane_id": scene.get("lane_id"),
                    "one_based_display_order_index": scene.get("order_index"),
                },
                "effect": (
                    "Timeline membership and lane assignment are removed. The "
                    "underlying manuscript scene remains and becomes off-Timeline."
                ),
            })

        elif kind == "create_link":
            source_id = normalized["source_scene_id"]
            target_id = normalized["target_scene_id"]
            source = event_by_id(source_id)
            target = event_by_id(target_id)
            duplicate = next((
                row for row in links
                if {
                    row.get("source_scene_id"), row.get("target_scene_id"),
                } == {source_id, target_id}
            ), None)
            if duplicate is not None:
                raise GatewayError(
                    "Those Timeline events are already connected by link "
                    f"{duplicate.get('id')}."
                )
            link_type = normalized.get("link_type", "custom")
            summary = (
                f"Create {link_type!r} Timeline link from scene {source_id} "
                f"({_preview(source.get('title'), 120)!r}) to scene {target_id} "
                f"({_preview(target.get('title'), 120)!r})."
            )
            review.update({
                "source": {
                    "scene_id": source_id,
                    "title": _preview(source.get("title"), 500),
                },
                "target": {
                    "scene_id": target_id,
                    "title": _preview(target.get("title"), 500),
                },
                "after_intent": {
                    "link_type": link_type,
                    "color_label": normalized.get("color_label", "gray"),
                    "label": _preview(normalized.get("label", ""), 500),
                    "direction": "source_to_target",
                },
            })

        elif kind == "update_link":
            link_id = normalized["link_id"]
            link = link_by_id(link_id)
            changes: dict[str, Any] = {}
            for key in ("link_type", "color_label", "label"):
                if key in normalized:
                    before_value = link.get(
                        key, "gray" if key == "color_label" else "",
                    )
                    changes[key] = {
                        "before": _preview(before_value, 500),
                        "after": normalized[key],
                    }
            if all(change["before"] == change["after"] for change in changes.values()):
                raise GatewayError(
                    "The requested Timeline link update would not change the link."
                )
            summary = (
                f"Update Timeline link {link_id} from scene "
                f"{link.get('source_scene_id')} to scene "
                f"{link.get('target_scene_id')}."
            )
            review.update({
                "link": {
                    "id": link_id,
                    "source_scene_id": link.get("source_scene_id"),
                    "target_scene_id": link.get("target_scene_id"),
                    "direction": "source_to_target",
                },
                "changes": changes,
            })

        elif kind == "delete_link":
            link_id = normalized["link_id"]
            link = link_by_id(link_id)
            summary = (
                f"Delete Timeline link {link_id} from scene "
                f"{link.get('source_scene_id')} to scene "
                f"{link.get('target_scene_id')}; keep both manuscript scenes."
            )
            review.update({
                "link": {
                    "id": link_id,
                    "source_scene_id": link.get("source_scene_id"),
                    "target_scene_id": link.get("target_scene_id"),
                    "link_type": link.get("link_type", "custom"),
                    "label": _preview(link.get("label"), 500),
                },
                "effect": (
                    "Only the planning relationship is deleted; Timeline events "
                    "and manuscript scenes remain unchanged."
                ),
            })

        elif kind == "create_structure_link":
            source_id = normalized["source_scene_id"]
            source = event_by_id(source_id)
            target_type = normalized["target_type"]
            target_ref = normalized["target_ref"]
            if target_ref not in structure_targets[target_type]:
                raise GatewayError(
                    f"Timeline {target_type} target {target_ref!r} is not present "
                    "in the current manuscript structure."
                )
            duplicate = next((
                row for row in structure_links
                if row.get("source_scene_id") == source_id
                and row.get("target_type") == target_type
                and str(row.get("target_ref", "")).strip() == target_ref
            ), None)
            if duplicate is not None:
                raise GatewayError(
                    "That Timeline structure relationship already exists as link "
                    f"{duplicate.get('id')}."
                )
            summary = (
                f"Link Timeline scene {source_id} "
                f"({_preview(source.get('title'), 120)!r}) to {target_type} "
                f"{target_ref!r}."
            )
            review.update({
                "source": {
                    "scene_id": source_id,
                    "title": _preview(source.get("title"), 500),
                },
                "after_intent": {
                    "target_type": target_type,
                    "target_ref": target_ref,
                    "target_exists": True,
                },
            })

        elif kind == "update_structure_link":
            structure_link_id = normalized["structure_link_id"]
            link = structure_link_by_id(structure_link_id)
            target_type = normalized.get("target_type", link.get("target_type"))
            target_ref = normalized.get(
                "target_ref", str(link.get("target_ref", "")).strip(),
            )
            if target_type not in _TIMELINE_STRUCTURE_TARGET_TYPES:
                raise GatewayError(
                    "The current Timeline structure link has an invalid target type."
                )
            if target_ref not in structure_targets[target_type]:
                raise GatewayError(
                    f"Timeline {target_type} target {target_ref!r} is not present "
                    "in the current manuscript structure."
                )
            duplicate = next((
                row for row in structure_links
                if row.get("id") != structure_link_id
                and row.get("source_scene_id") == link.get("source_scene_id")
                and row.get("target_type") == target_type
                and str(row.get("target_ref", "")).strip() == target_ref
            ), None)
            if duplicate is not None:
                raise GatewayError(
                    "That Timeline structure relationship already exists as link "
                    f"{duplicate.get('id')}."
                )
            changes: dict[str, Any] = {}
            if "target_type" in normalized:
                changes["target_type"] = {
                    "before": link.get("target_type"),
                    "after": target_type,
                }
            if "target_ref" in normalized:
                changes["target_ref"] = {
                    "before": _preview(link.get("target_ref"), 500),
                    "after": target_ref,
                }
            if all(change["before"] == change["after"] for change in changes.values()):
                raise GatewayError(
                    "The requested structure-link update would not change the link."
                )
            summary = (
                f"Update Timeline structure link {structure_link_id} to "
                f"{target_type} {target_ref!r}."
            )
            review.update({
                "structure_link": {
                    "id": structure_link_id,
                    "source_scene_id": link.get("source_scene_id"),
                    "target_exists": link.get("target_exists"),
                },
                "changes": changes,
            })

        elif kind == "delete_structure_link":
            structure_link_id = normalized["structure_link_id"]
            link = structure_link_by_id(structure_link_id)
            summary = (
                f"Delete Timeline structure link {structure_link_id} from scene "
                f"{link.get('source_scene_id')} to "
                f"{link.get('target_type')} {link.get('target_ref')!r}."
            )
            review.update({
                "structure_link": {
                    "id": structure_link_id,
                    "source_scene_id": link.get("source_scene_id"),
                    "target_type": link.get("target_type"),
                    "target_ref": _preview(link.get("target_ref"), 500),
                    "target_exists": link.get("target_exists"),
                },
                "effect": (
                    "Only the structure reference is deleted; the Timeline event, "
                    "Act/Chapter, and manuscript scene remain unchanged."
                ),
            })

        else:
            mode = normalized["mode"]
            before = current.get("order_mode", "structural")
            if before == mode:
                raise GatewayError(f"Timeline order is already {mode!r}.")
            summary = f"Switch Timeline order from {before!r} to {mode!r}."
            review.update({
                "before": {
                    "order_mode": before,
                    "event_order": _bounded_sequence(event_order),
                },
                "after_intent": {
                    "order_mode": mode,
                    "structural_mode_recomputes_effective_order": mode == "structural",
                },
            })

        return self.propose_request(
            operation=f"timeline_{kind}",
            method="POST",
            path=self.client.project_path("timeline/commands", pid),
            body=normalized,
            summary=summary,
            project_id=pid,
            review=review,
        )

    def propose_create_project(self, body: dict[str, Any]) -> dict[str, Any]:
        return self.propose_request(
            operation="create_project", method="POST",
            path=self.client.api_path("projects"), body=body,
            summary=f"Create project {body['title']!r}.", project_id=None,
        )

    def propose_create_scene(self, body: dict[str, Any]) -> dict[str, Any]:
        pid = self._project_id()
        return self.propose_request(
            operation="create_scene", method="POST",
            path=self.client.project_path("scenes", pid), body=body,
            summary=f"Create scene {body['title']!r} in project {pid}.", project_id=pid,
        )

    def propose_scene_patch(
        self, scene_id: int, expected_revision: str, patch: dict[str, Any],
    ) -> dict[str, Any]:
        pid = self._project_id()
        current = self.client.get_scene(scene_id, pid)
        actual_revision = str(current.get("revision", ""))
        if not expected_revision or expected_revision != actual_revision:
            raise GatewayError(
                "expected_revision does not match the current scene. Read the "
                "scene again and propose against its returned revision."
            )
        if not patch:
            raise GatewayError("A scene patch must change at least one field.")
        body = dict(patch)
        body["expected_revision"] = expected_revision
        review: dict[str, Any] = {"changes": {}}
        for key, value in patch.items():
            if key == "content":
                review["changes"][key] = _content_review(
                    str(current.get("content", "") or ""), str(value or ""),
                )
            else:
                review["changes"][key] = {"before": current.get(key), "after": value}
        return self.propose_request(
            operation="patch_scene", method="PATCH",
            path=self.client.project_path(f"scenes/{int(scene_id)}", pid), body=body,
            summary=f"Patch scene {scene_id} ({current.get('title', '')!r}).",
            project_id=pid, review=review,
        )

    def propose_create_outline_node(self, body: dict[str, Any]) -> dict[str, Any]:
        pid = self._project_id()
        outline_path = self.client.project_path("outline", pid)
        return self.propose_request(
            operation="create_outline_node", method="POST",
            path=self.client.project_path("outline/nodes", pid), body=body,
            summary=f"Create outline node {body['title']!r}.", project_id=pid,
            guard_path=outline_path,
        )

    def propose_patch_outline_node(self, node_id: int, patch: dict[str, Any]) -> dict[str, Any]:
        pid = self._project_id()
        if not patch:
            raise GatewayError("An outline patch must change at least one field.")
        outline_path = self.client.project_path("outline", pid)
        return self.propose_request(
            operation="patch_outline_node", method="PATCH",
            path=self.client.project_path(f"outline/nodes/{int(node_id)}", pid), body=patch,
            summary=f"Patch outline node {node_id}.", project_id=pid,
            guard_path=outline_path,
        )

    def propose_create_psyke_entry(self, body: dict[str, Any]) -> dict[str, Any]:
        pid = self._project_id()
        return self.propose_request(
            operation="create_psyke_entry", method="POST",
            path=self.client.project_path("psyke/entries", pid), body=body,
            summary=f"Create PSYKE entry {body['name']!r}.", project_id=pid,
        )

    def propose_patch_psyke_entry(self, entry_id: int, patch: dict[str, Any]) -> dict[str, Any]:
        pid = self._project_id()
        if not patch:
            raise GatewayError("A PSYKE patch must change at least one field.")
        path = self.client.project_path(f"psyke/entries/{int(entry_id)}", pid)
        return self.propose_request(
            operation="patch_psyke_entry", method="PATCH", path=path, body=patch,
            summary=f"Patch PSYKE entry {entry_id}.", project_id=pid, guard_path=path,
        )

    def propose_create_psyke_relation(self, body: dict[str, Any]) -> dict[str, Any]:
        pid = self._project_id()
        if int(body["source_id"]) == int(body["target_id"]):
            raise GatewayError("A relation requires two distinct PSYKE entries.")
        return self.propose_request(
            operation="create_psyke_relation", method="POST",
            path=self.client.project_path("psyke/relations", pid), body=body,
            summary=(f"Relate PSYKE entries {body['source_id']} and "
                     f"{body['target_id']} as {body.get('relation_type', '')!r}."),
            project_id=pid,
            guard_path=self.client.project_path("psyke/relations", pid),
        )

    def propose_create_psyke_progression(self, body: dict[str, Any]) -> dict[str, Any]:
        pid = self._project_id()
        return self.propose_request(
            operation="create_psyke_progression", method="POST",
            path=self.client.project_path("psyke/progressions", pid), body=body,
            summary=f"Add progression to PSYKE entry {body['entry_id']}.", project_id=pid,
        )

    def propose_create_note(self, body: dict[str, Any]) -> dict[str, Any]:
        pid = self._project_id()
        return self.propose_request(
            operation="create_note", method="POST",
            path=self.client.project_path("notes", pid), body=body,
            summary=f"Create note {body['title']!r}.", project_id=pid,
        )

    def propose_patch_note(self, note_id: int, patch: dict[str, Any]) -> dict[str, Any]:
        pid = self._project_id()
        if not patch:
            raise GatewayError("A note patch must change at least one field.")
        notes_path = self.client.project_path("notes", pid)
        return self.propose_request(
            operation="patch_note", method="PATCH",
            path=self.client.project_path(f"notes/{int(note_id)}", pid), body=patch,
            summary=f"Patch note {note_id}.", project_id=pid, guard_path=notes_path,
        )

    def _comment_proposal_context(
        self, comment_id: int, expected_revision: str,
    ) -> tuple[int, dict[str, Any]]:
        pid = self._project_id()
        if (
            not isinstance(expected_revision, str)
            or len(expected_revision) != 64
            or any(char not in "0123456789abcdef" for char in expected_revision)
        ):
            raise GatewayError(
                "expected_revision must be the exact 64-character revision "
                "returned by logosforge_list_comments or logosforge_search."
            )
        current = self.client.get_comment(int(comment_id), pid)
        if current.get("revision") != expected_revision:
            raise GatewayError(
                "expected_revision does not match the current comment thread. "
                "Read the thread again and create a fresh proposal."
            )
        return pid, current

    def propose_comment_reply(
        self, comment_id: int, expected_revision: str, body: str,
    ) -> dict[str, Any]:
        if not isinstance(body, str) or not body.strip():
            raise GatewayError("A comment reply must not be empty.")
        if len(body) > 20_000:
            raise GatewayError("A comment reply may contain at most 20000 characters.")
        pid, current = self._comment_proposal_context(
            comment_id, expected_revision,
        )
        return self.propose_request(
            operation="reply_to_comment",
            method="POST",
            path=self.client.project_path(
                f"comments/{int(comment_id)}/replies", pid,
            ),
            body={
                "body": body,
                "author": "MCP assistant",
                "expected_revision": expected_revision,
            },
            summary=f"Reply to comment {comment_id} as MCP assistant.",
            project_id=pid,
            review={
                "comment_id": int(comment_id),
                "expected_revision": expected_revision,
                "quote": _preview(current.get("quote"), 500),
                "root_body": _preview(current.get("body"), 1_000),
                "reply_count_before": len(current.get("replies", [])),
                "proposed_author": "MCP assistant",
                "proposed_reply": body,
            },
        )

    def propose_comment_resolution(
        self, comment_id: int, expected_revision: str, resolved: bool,
    ) -> dict[str, Any]:
        if not isinstance(resolved, bool):
            raise GatewayError("resolved must be a boolean.")
        pid, current = self._comment_proposal_context(
            comment_id, expected_revision,
        )
        before = bool(current.get("resolved"))
        if before == resolved:
            state = "resolved" if resolved else "open"
            raise GatewayError(f"Comment {comment_id} is already {state}.")
        return self.propose_request(
            operation="set_comment_resolution",
            method="PATCH",
            path=self.client.project_path(f"comments/{int(comment_id)}", pid),
            body={
                "resolved": resolved,
                "expected_revision": expected_revision,
            },
            summary=(
                f"{'Resolve' if resolved else 'Reopen'} comment {comment_id}."
            ),
            project_id=pid,
            review={
                "comment_id": int(comment_id),
                "expected_revision": expected_revision,
                "quote": _preview(current.get("quote"), 500),
                "before": {"resolved": before},
                "after": {"resolved": resolved},
            },
        )

    def propose_import_manuscript(
        self, *, title: str, content: str, mode: str, strategy: str, filename: str,
    ) -> dict[str, Any]:
        raw = content.encode("utf-8")
        body = {
            "title": title,
            "mode": mode,
            "strategy": strategy,
            "filename": filename,
            "content_base64": base64.b64encode(raw).decode("ascii"),
        }
        return self.propose_request(
            operation="import_manuscript", method="POST",
            path=self.client.api_path("import/manuscript"), body=body,
            summary=f"Import {len(content)} characters as project {title!r}.",
            project_id=None,
            review={
                "title": title, "mode": mode, "strategy": strategy,
                "filename": filename, "content_length": len(content),
                "content_sha256": hashlib.sha256(raw).hexdigest(),
            },
        )


def call_gateway(
    gateway: LogosForgeMcpGateway,
    operation,
) -> dict[str, Any]:
    """Return a stable MCP result envelope and never leak a traceback."""
    try:
        return {"ok": True, "result": operation()}
    except (GatewayError, LogosForgeApiError, ValueError, TypeError) as exc:
        return {"ok": False, "error": str(exc)}
    except Exception:  # pragma: no cover - final transport safety net
        # MCP stdio uses stdout as its protocol stream. Log diagnostics to the
        # normal logging sink (stderr) and return a stable, non-traceback error.
        LOGGER.exception("Unexpected LogosForge MCP gateway failure")
        return {
            "ok": False,
            "error": "Unexpected gateway failure; inspect the MCP server log.",
        }
