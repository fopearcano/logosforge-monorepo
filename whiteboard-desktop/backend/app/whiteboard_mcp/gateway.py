"""Bounded Whiteboard orchestration over the authenticated wrapper API.

Reads execute immediately.  Persistent changes are deliberately two phase: a
focused proposal stores one exact conditional request in this process, and the
single apply operation can execute that request once only when writes were
explicitly enabled for the MCP server.
"""

from __future__ import annotations

import copy
import hashlib
import json
import logging
import math
import re
import secrets
import threading
import time
import urllib.parse
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .client import MAX_REQUEST_BYTES, WhiteboardApiClient, WhiteboardApiError

LOGGER = logging.getLogger(__name__)
MCP_SERVER_VERSION = "1.4.0"
MAX_PAGE_SIZE = 500
MAX_SNAPSHOT_BLOCKS = 200
MAX_SNAPSHOT_CHARACTERS = 250_000
MAX_SEARCH_RESULTS = 50
MAX_SEARCH_SNIPPET = 240
MAX_SEARCH_TITLE = 240
MAX_SEARCH_ID = 160
MAX_RESULT_BYTES = 256 * 1024
MAX_PAGE_PAYLOAD_BYTES = 220 * 1024
MAX_SNAPSHOT_METADATA_BYTES = 32 * 1024
MAX_PROPOSAL_ITEMS = 20_000
MAX_PROPOSALS = 100
MAX_PROPOSAL_REVIEW_BYTES = 48 * 1024
MAX_PROPOSAL_BODY_PAGE_BYTES = 64 * 1024
MAX_PROPOSAL_ID_SAMPLE_BYTES = 8 * 1024
MAX_PROPOSAL_CHANGE_SAMPLES = 6
MAX_PROPOSAL_CHANGE_SIDE_BYTES = 3 * 1024
MAX_PSYKE_NAME_CHARACTERS = 1_000
MAX_PSYKE_TEXT_CHARACTERS = 250_000
MAX_PSYKE_REVIEW_FIELD_BYTES = 8 * 1024
MAX_PSYKE_RELATION_TYPE_CHARACTERS = 1_000
MAX_PSYKE_SCENE_TITLE_CHARACTERS = 1_000
MAX_PSYKE_INTEGER_ID = 9_007_199_254_740_991
MAX_COMMENT_ID_CHARACTERS = 128
MAX_COMMENT_BODY_CHARACTERS = 100_000
MAX_COMMENT_REVIEW_FIELD_BYTES = 8 * 1024
MAX_OUTLINE_DEPTH = 512
MAX_MARKS_PER_BLOCK = 100_000
_FINAL_RESULT_METADATA_RESERVE = 2 * 1024
_TRUNCATION_MARKER = "…"
_WRITING_MODES = {"novel", "screenplay", "graphic_novel", "stage_script"}
_SCREENPLAY_TYPES = {
    "scene_heading",
    "action",
    "character",
    "dialogue",
    "parenthetical",
    "transition",
    "section",
    "synopsis",
    "note",
    "centered",
    "lyrics",
    "page_break",
    "empty",
}
_OUTLINE_TYPES = {"act", "part", "chapter", "sequence", "scene", "beat", "custom"}
_OUTLINE_STATUSES = {"none", "todo", "drafting", "revised", "done"}
_OUTLINE_COLORS = {"none", "red", "orange", "yellow", "green", "blue", "purple", "gray"}
_PSYKE_TYPES = {"character", "place", "object", "lore", "theme", "other"}
_COMMENT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_COMMENT_AI_MENTION_RE = re.compile(r"@(billy|logos)\b", re.IGNORECASE)
_OUTLINE_REQUIRED_FIELDS = {
    "id",
    "parentId",
    "type",
    "title",
    "summary",
    "order",
    "collapsed",
    "completed",
    "status",
    "tags",
    "colorLabel",
    "createdAt",
    "updatedAt",
}
_OUTLINE_OPTIONAL_FIELDS = {"linkedLineId", "link"}
_STABLE_ID_RE = re.compile(r"^[^\s\x00-\x1f\x7f]{1,256}$")
_ISO_TIMESTAMP_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}"
    r"(?:\.\d{1,9})?(?:Z|[+-]\d{2}:\d{2})$"
)


class GatewayError(RuntimeError):
    """A validation or state error safe to return to an MCP client."""


def _json_bytes(value: Any) -> int:
    return len(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
    )


def _clip_string(value: str, budget: int) -> tuple[Any, int]:
    if _json_bytes(value) <= budget:
        return value, 0
    if _json_bytes("") > budget:
        return None, 1
    if _json_bytes(_TRUNCATION_MARKER) > budget:
        return "", 1
    low = 0
    high = len(value)
    while low < high:
        middle = (low + high + 1) // 2
        candidate = value[:middle] + _TRUNCATION_MARKER
        if _json_bytes(candidate) <= budget:
            low = middle
        else:
            high = middle - 1
    return value[:low] + _TRUNCATION_MARKER, 1


_KEY_PRIORITY = {
    "id": 0,
    "document_id": 1,
    "incarnation": 2,
    "revision": 3,
    "title": 4,
    "name": 5,
    "type": 6,
    "entry_type": 7,
    "mode": 8,
    "text": 9,
}


def _clip_json_value(value: Any, budget: int, depth: int = 0) -> tuple[Any, int]:
    """Return deterministic JSON-compatible data no larger than ``budget`` bytes."""
    if budget < 4:
        return None, 1
    try:
        if _json_bytes(value) <= budget:
            return value, 0
    except (TypeError, ValueError, OverflowError):
        value = str(value)
        if _json_bytes(value) <= budget:
            return value, 1
    if depth >= 24:
        return None, 1
    if isinstance(value, str):
        return _clip_string(value, budget)
    if isinstance(value, list):
        clipped: list[Any] = []
        truncated = 0
        for index, item in enumerate(value):
            separator = 1 if clipped else 0
            available = budget - _json_bytes(clipped) - separator
            if available < 4:
                truncated += len(value) - index
                break
            child, child_truncated = _clip_json_value(item, available, depth + 1)
            candidate = [*clipped, child]
            if _json_bytes(candidate) > budget:
                truncated += len(value) - index
                break
            clipped = candidate
            truncated += child_truncated
        return clipped, max(1, truncated)
    if isinstance(value, dict):
        clipped_dict: dict[str, Any] = {}
        truncated = 0
        entries = sorted(
            ((str(key), key) for key in value),
            key=lambda entry: (_KEY_PRIORITY.get(entry[0], 100), entry[0]),
        )
        for position, (key, original_key) in enumerate(entries):
            separator = 1 if clipped_dict else 0
            key_cost = _json_bytes(key) + 1
            available = budget - _json_bytes(clipped_dict) - separator - key_cost
            if available < 4:
                truncated += len(entries) - position
                break
            child, child_truncated = _clip_json_value(
                value[original_key], available, depth + 1
            )
            candidate = {**clipped_dict, key: child}
            if _json_bytes(candidate) > budget:
                truncated += 1 + child_truncated
                continue
            clipped_dict = candidate
            truncated += child_truncated
        return clipped_dict, max(1, truncated)
    return (None if budget >= 4 else ""), 1


def _bounded_items(
    candidates: list[Any],
    *,
    offset: int,
    limit: int,
    total: int,
    payload_budget: int = MAX_PAGE_PAYLOAD_BYTES,
) -> tuple[list[Any], dict[str, Any]]:
    selected: list[Any] = []
    truncated_offsets: list[int] = []
    truncated_values = 0
    consumed = 0
    for item in candidates[:limit]:
        separator = 1 if selected else 0
        available = payload_budget - _json_bytes(selected) - separator
        if available < 4:
            break
        clipped, item_truncated = _clip_json_value(item, available)
        candidate = [*selected, clipped]
        if _json_bytes(candidate) > payload_budget:
            break
        if item_truncated:
            truncated_offsets.append(offset + consumed)
            truncated_values += item_truncated
        selected = candidate
        consumed += 1

    requested = min(limit, len(candidates))
    byte_limited = bool(truncated_offsets) or consumed < requested
    next_offset = offset + consumed
    return selected, {
        "offset": offset,
        "limit": limit,
        "returned": len(selected),
        "total": total,
        "next_offset": next_offset if next_offset < total else None,
        "byte_limited": byte_limited,
        "max_payload_bytes": payload_budget,
        "payload_bytes": _json_bytes(selected),
        "truncated_item_offsets": truncated_offsets,
        "truncated_value_count": truncated_values,
    }


def _page(values: list[Any], offset: int, limit: int) -> tuple[list[Any], dict[str, Any]]:
    total = len(values)
    return _bounded_items(
        values[offset : offset + limit],
        offset=offset,
        limit=limit,
        total=total,
    )


def _bounded_success(value: Any) -> dict[str, Any]:
    response = {"ok": True, "result": value}
    original_bytes = _json_bytes(response)
    if original_bytes <= MAX_RESULT_BYTES:
        return response

    content_budget = MAX_RESULT_BYTES - _FINAL_RESULT_METADATA_RESERVE
    for _attempt in range(4):
        clipped, truncated = _clip_json_value(value, content_budget)
        metadata = {
            "byte_limited": True,
            "max_result_bytes": MAX_RESULT_BYTES,
            "original_bytes": original_bytes,
            "truncated_value_count": max(1, truncated),
        }
        if isinstance(clipped, dict):
            result = {**clipped, "_mcp_output": metadata}
        else:
            result = {"data": clipped, "_mcp_output": metadata}
        response = {"ok": True, "result": result}
        response_bytes = _json_bytes(response)
        if response_bytes <= MAX_RESULT_BYTES:
            return response
        content_budget = max(
            4,
            content_budget - (response_bytes - MAX_RESULT_BYTES) - 128,
        )

    return {
        "ok": True,
        "result": {
            "_mcp_output": {
                "byte_limited": True,
                "max_result_bytes": MAX_RESULT_BYTES,
                "original_bytes": original_bytes,
                "truncated_value_count": 1,
            }
        },
    }


def bounded_gateway_response(response: dict[str, Any]) -> dict[str, Any]:
    """Apply the wire-size contract to responses created outside call_gateway."""
    if _json_bytes(response) <= MAX_RESULT_BYTES:
        return response
    if response.get("ok") is True:
        return _bounded_success(response.get("result"))
    error, _ = _clip_string(_text(response.get("error")), MAX_RESULT_BYTES // 2)
    return {"ok": False, "error": error}


def _text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if value is None:
        return ""
    return str(value)


def _json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _snippet(text: str, needle: str) -> str:
    compact = " ".join(text.split())
    folded = compact.casefold()
    index = folded.find(needle)
    if index < 0:
        return compact[:MAX_SEARCH_SNIPPET]
    half = MAX_SEARCH_SNIPPET // 2
    start = max(0, index - half)
    end = min(len(compact), start + MAX_SEARCH_SNIPPET)
    start = max(0, end - MAX_SEARCH_SNIPPET)
    prefix = "…" if start else ""
    suffix = "…" if end < len(compact) else ""
    return f"{prefix}{compact[start:end]}{suffix}"


def _short_search_field(value: Any, maximum: int) -> Any:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    rendered = value if isinstance(value, str) else _json_text(value)
    if len(rendered) <= maximum:
        return rendered
    return rendered[: maximum - 1] + _TRUNCATION_MARKER


def _canonical_json(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError, RecursionError, UnicodeError):
        raise GatewayError("Proposal data must be finite, bounded JSON.") from None


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _valid_token(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 32
        and all(character in "0123456789abcdef" for character in value)
    )


def _valid_stable_id(value: Any) -> bool:
    return isinstance(value, str) and _STABLE_ID_RE.fullmatch(value) is not None


def _valid_timestamp(value: Any) -> bool:
    if not isinstance(value, str) or _ISO_TIMESTAMP_RE.fullmatch(value) is None:
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None


def _collection_review(values: list[dict[str, Any]]) -> dict[str, Any]:
    characters = sum(len(_text(value.get("text"))) for value in values)
    identifiers = [_text(value.get("id")) for value in values]
    return {
        "count": len(values),
        "text_characters": characters,
        "sha256": _digest(values),
        "first_ids": identifiers[:5],
        "last_ids": identifiers[-5:] if len(identifiers) > 5 else [],
    }


def _manuscript_review(document: dict[str, Any]) -> dict[str, Any]:
    blocks = document.get("blocks")
    if not isinstance(blocks, list) or any(
        not isinstance(block, dict) for block in blocks
    ):
        raise GatewayError("The current Whiteboard manuscript has invalid blocks.")
    return {
        "title": _text(document.get("title")),
        "mode": _text(document.get("mode")),
        "blocks": _collection_review(blocks),
    }


def _outline_collection_review(values: list[dict[str, Any]]) -> dict[str, Any]:
    identifiers = [_text(value.get("id")) for value in values]
    return {
        "count": len(values),
        "title_characters": sum(len(_text(value.get("title"))) for value in values),
        "summary_characters": sum(len(_text(value.get("summary"))) for value in values),
        "sha256": _digest(values),
        "first_ids": identifiers[:5],
        "last_ids": identifiers[-5:] if len(identifiers) > 5 else [],
    }


def _bounded_identifier_sample(values: set[str]) -> tuple[list[str], bool]:
    """Return a deterministic ID sample with both item and UTF-8 byte bounds."""
    ordered = sorted(values)
    sample: list[str] = []
    for identifier in ordered:
        if len(sample) >= 100:
            break
        candidate = [*sample, identifier]
        if _json_bytes(candidate) > MAX_PROPOSAL_ID_SAMPLE_BYTES:
            break
        sample = candidate
    return sample, len(sample) < len(ordered)


def _psyke_entry_review(entry: dict[str, Any]) -> dict[str, Any]:
    """Return useful, bounded story-bible content for human proposal review."""
    review: dict[str, Any] = {
        key: copy.deepcopy(entry[key])
        for key in ("id", "name", "entry_type")
        if key in entry
    }
    aliases, aliases_truncated = _clip_json_value(
        entry.get("aliases", []),
        MAX_PSYKE_REVIEW_FIELD_BYTES,
    )
    review["aliases"] = aliases
    review["aliases_truncated"] = bool(aliases_truncated)
    for field_name in ("description", "notes"):
        value = _text(entry.get(field_name))
        preview, truncated = _clip_string(value, MAX_PSYKE_REVIEW_FIELD_BYTES)
        review[field_name] = preview
        review[f"{field_name}_characters"] = len(value)
        review[f"{field_name}_sha256"] = hashlib.sha256(
            value.encode("utf-8")
        ).hexdigest()
        review[f"{field_name}_truncated"] = bool(truncated)
    return review


def _psyke_text_review(value: Any) -> dict[str, Any]:
    """Return bounded PSYKE prose with enough metadata to verify exact bytes."""
    text = _text(value)
    preview, truncated = _clip_string(text, MAX_PSYKE_REVIEW_FIELD_BYTES)
    return {
        "preview": preview,
        "characters": len(text),
        "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "truncated": bool(truncated),
        "maximum_preview_bytes": MAX_PSYKE_REVIEW_FIELD_BYTES,
    }


def _psyke_relation_review(relation: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": _text(relation.get("id")),
        "source_id": relation.get("source_id"),
        "source": _text(relation.get("source")),
        "target_id": relation.get("target_id"),
        "target": _text(relation.get("target")),
        "relation_type": _psyke_text_review(relation.get("relation_type")),
    }


def _psyke_progression_review(progression: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": progression.get("id"),
        "entry_id": progression.get("entry_id"),
        "scene_id": progression.get("scene_id"),
        "scene_title": _text(progression.get("scene_title")),
        "sort_order": progression.get("sort_order"),
        "text": _psyke_text_review(progression.get("text")),
    }


def _comment_text_review(value: Any) -> dict[str, Any]:
    """Return a bounded preview plus an integrity digest for comment prose."""
    text = _text(value)
    preview, truncated = _clip_string(text, MAX_COMMENT_REVIEW_FIELD_BYTES)
    return {
        "preview": preview,
        "characters": len(text),
        "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "truncated": bool(truncated),
        "maximum_preview_bytes": MAX_COMMENT_REVIEW_FIELD_BYTES,
    }


def _comment_review(comment: dict[str, Any]) -> dict[str, Any]:
    """Bound user-authored thread context before returning proposal review."""
    replies = comment.get("replies")
    if not isinstance(replies, list):
        raise GatewayError("The current Whiteboard comment has invalid replies.")
    return {
        "id": _text(comment.get("id")),
        "resolved": bool(comment.get("resolved")),
        "reply_count": len(replies),
        "quote": _comment_text_review(comment.get("quote")),
        "body": _comment_text_review(comment.get("body")),
    }


def _collection_change_review(
    before: list[dict[str, Any]],
    after: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build bounded head/tail samples; exact proposed bytes are paged separately."""
    before_by_id = {
        _text(item.get("id")): (index, item) for index, item in enumerate(before)
    }
    after_by_id = {
        _text(item.get("id")): (index, item) for index, item in enumerate(after)
    }
    changes: list[dict[str, Any]] = []
    counts = {"added": 0, "removed": 0, "modified": 0, "moved": 0}

    for after_index, after_item in enumerate(after):
        item_id = _text(after_item.get("id"))
        previous = before_by_id.get(item_id)
        if previous is None:
            counts["added"] += 1
            changes.append(
                {
                    "id": item_id,
                    "change": "added",
                    "after_index": after_index,
                    "after": after_item,
                }
            )
            continue
        before_index, before_item = previous
        modified = before_item != after_item
        moved = before_index != after_index
        if not modified and not moved:
            continue
        if modified:
            counts["modified"] += 1
        if moved:
            counts["moved"] += 1
        changes.append(
            {
                "id": item_id,
                "change": (
                    "modified_and_moved" if modified and moved
                    else "modified" if modified
                    else "moved"
                ),
                "before_index": before_index,
                "after_index": after_index,
                "before": before_item,
                "after": after_item,
            }
        )

    for before_index, before_item in enumerate(before):
        item_id = _text(before_item.get("id"))
        if item_id in after_by_id:
            continue
        counts["removed"] += 1
        changes.append(
            {
                "id": item_id,
                "change": "removed",
                "before_index": before_index,
                "before": before_item,
            }
        )

    if len(changes) <= MAX_PROPOSAL_CHANGE_SAMPLES:
        sampled = changes
    else:
        groups = [
            [change for change in changes if change["change"].startswith("modified")],
            [change for change in changes if change["change"] == "added"],
            [change for change in changes if change["change"] == "removed"],
        ]
        groups = [group for group in groups if group]
        move_only = [change for change in changes if change["change"] == "moved"]
        sampled = []
        sampled_ids: set[int] = set()

        def add_sample(change: dict[str, Any]) -> None:
            identity = id(change)
            if (
                identity not in sampled_ids
                and len(sampled) < MAX_PROPOSAL_CHANGE_SAMPLES
            ):
                sampled.append(change)
                sampled_ids.add(identity)

        # Represent each semantic change kind first, then its tail. This keeps
        # late proposed content visible even when removals follow additions.
        for group in groups:
            add_sample(group[0])
        for group in groups:
            add_sample(group[-1])
        for change in changes:
            if change["change"] != "moved":
                add_sample(change)
        if move_only:
            add_sample(move_only[0])
            add_sample(move_only[-1])
        for change in move_only:
            add_sample(change)

    preview_entries: list[dict[str, Any]] = []
    truncated_values = max(0, len(changes) - len(sampled))
    for change in sampled:
        entry = {
            key: change[key]
            for key in ("id", "change", "before_index", "after_index")
            if key in change
        }
        for side in ("before", "after"):
            if side not in change:
                continue
            clipped, side_truncated = _clip_json_value(
                change[side],
                MAX_PROPOSAL_CHANGE_SIDE_BYTES,
            )
            entry[side] = clipped
            entry[f"{side}_truncated"] = bool(side_truncated)
            truncated_values += side_truncated
        preview_entries.append(entry)

    preview, final_truncated = _clip_json_value(
        preview_entries,
        MAX_PROPOSAL_REVIEW_BYTES,
    )
    truncated_values += final_truncated
    return {
        **counts,
        "change_count": len(changes),
        "preview": preview,
        "preview_truncated": bool(truncated_values),
        "preview_sampled": len(changes) > len(sampled),
        "omitted_change_count": max(0, len(changes) - len(sampled)),
        "truncated_value_count": truncated_values,
        "max_preview_bytes": MAX_PROPOSAL_REVIEW_BYTES,
    }


def _request_body_page(
    body: dict[str, Any],
    offset: int,
    maximum_bytes: int,
) -> dict[str, Any]:
    raw = _canonical_json(body)
    if offset < 0 or offset > len(raw):
        raise GatewayError(
            f"request_body_offset must be between 0 and {len(raw)}."
        )
    if offset < len(raw) and raw[offset] & 0xC0 == 0x80:
        raise GatewayError(
            "request_body_offset must use a next_offset returned by this tool."
        )
    end = min(len(raw), offset + maximum_bytes)
    while end < len(raw) and end > offset and raw[end] & 0xC0 == 0x80:
        end -= 1
    content = raw[offset:end].decode("utf-8")
    return {
        "content": content,
        "offset": offset,
        "returned_bytes": end - offset,
        "total_bytes": len(raw),
        "next_offset": end if end < len(raw) else None,
        "complete": end == len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "max_page_bytes": maximum_bytes,
    }


def _compact_proposal_body(operation: str, body: dict[str, Any]) -> dict[str, Any]:
    if operation == "patch_manuscript":
        compact: dict[str, Any] = {}
        for key, value in body.items():
            if key == "blocks" and isinstance(value, list):
                compact[key] = _collection_review(value)
            else:
                compact[key] = value
        return compact
    if operation == "replace_outline":
        items = body.get("items")
        return {
            "items": _outline_collection_review(items if isinstance(items, list) else [])
        }
    return {"bytes": len(_canonical_json(body)), "sha256": _digest(body)}


@dataclass
class Proposal:
    proposal_id: str
    operation: str
    method: str
    path: str
    body: dict[str, Any]
    summary: str
    document_id: int
    resource_kind: str
    incarnation: str
    expected_revision: str
    mutation_id: str
    created_at: float
    expires_at: float
    request_digest: str
    review: dict[str, Any] = field(default_factory=dict)
    state: str = "pending"  # pending | applying | applied | failed | discarded
    result: Any = None
    error: str = ""

    def public(
        self,
        include_result: bool = False,
        *,
        request_body_offset: int | None = None,
        request_body_max_bytes: int = MAX_PROPOSAL_BODY_PAGE_BYTES,
    ) -> dict[str, Any]:
        canonical_body = _canonical_json(self.body)
        request: dict[str, Any] = {
            "method": self.method,
            "path": self.path,
            "body": _compact_proposal_body(self.operation, self.body),
            "body_bytes": len(canonical_body),
            "body_sha256": hashlib.sha256(canonical_body).hexdigest(),
            "if_match": (
                f'"lfwb:{self.resource_kind}:{self.incarnation}:'
                f'{self.expected_revision}"'
            ),
            "document_incarnation": self.incarnation,
            "mutation_id": self.mutation_id,
        }
        if request_body_offset is not None:
            request["body_page"] = _request_body_page(
                self.body,
                request_body_offset,
                request_body_max_bytes,
            )
        value: dict[str, Any] = {
            "proposal_id": self.proposal_id,
            "operation": self.operation,
            "summary": self.summary,
            "document_id": self.document_id,
            "resource_kind": self.resource_kind,
            "state": self.state,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "request_digest": self.request_digest,
            "request": request,
            "review": self.review,
            "requires_user_approval": True,
        }
        if self.error:
            value["error"] = self.error
        if include_result and self.result is not None:
            value["result"] = self.result
        return value


class WhiteboardMcpGateway:
    """Per-stdio-session reads and revision-safe proposal state."""

    def __init__(
        self,
        client: WhiteboardApiClient,
        *,
        allow_writes: bool = False,
        proposal_ttl_seconds: int = 900,
    ) -> None:
        self.client = client
        self.allow_writes = bool(allow_writes)
        self.proposal_ttl_seconds = max(60, min(int(proposal_ttl_seconds), 86_400))
        self.selected_document_id: int | None = None
        self._proposals: dict[str, Proposal] = {}
        self._lock = threading.RLock()

    def capabilities(self) -> dict[str, Any]:
        return {
            "server": "logosforge-whiteboard",
            "version": MCP_SERVER_VERSION,
            "read_only": not self.allow_writes,
            "tool_prefix": "logosforge_whiteboard_",
            "writes_available": self.allow_writes,
            "write_mode": "reviewed_revision_bound_proposals",
            "data_source": "authenticated Whiteboard API",
            "features": [
                "document_selection",
                "bounded_manuscript_snapshot",
                "outline",
                "comments",
                "psyke",
                "bounded_search",
                "manuscript_patch_proposals",
                "outline_replacement_proposals",
                "comment_collaboration_proposals",
                "psyke_entry_proposals",
                "psyke_relation_progression_reads",
                "psyke_relation_progression_proposals",
                "single_use_proposal_apply",
            ],
            "limits": {
                "maximum_page_size": MAX_PAGE_SIZE,
                "maximum_snapshot_blocks": MAX_SNAPSHOT_BLOCKS,
                "maximum_snapshot_characters": MAX_SNAPSHOT_CHARACTERS,
                "maximum_search_results": MAX_SEARCH_RESULTS,
                "maximum_search_title_characters": MAX_SEARCH_TITLE,
                "maximum_search_id_characters": MAX_SEARCH_ID,
                "maximum_serialized_result_bytes": MAX_RESULT_BYTES,
                "maximum_proposal_request_bytes": MAX_REQUEST_BYTES,
                "maximum_proposal_items": MAX_PROPOSAL_ITEMS,
                "maximum_proposal_review_bytes": MAX_PROPOSAL_REVIEW_BYTES,
                "maximum_proposal_body_page_bytes": MAX_PROPOSAL_BODY_PAGE_BYTES,
                "maximum_inline_marks_per_block": MAX_MARKS_PER_BLOCK,
                "maximum_outline_depth": MAX_OUTLINE_DEPTH,
                "maximum_comment_body_characters": MAX_COMMENT_BODY_CHARACTERS,
                "maximum_comment_review_field_bytes": MAX_COMMENT_REVIEW_FIELD_BYTES,
                "maximum_psyke_relation_type_characters": MAX_PSYKE_RELATION_TYPE_CHARACTERS,
                "maximum_psyke_progression_text_characters": MAX_PSYKE_TEXT_CHARACTERS,
                "maximum_psyke_review_field_bytes": MAX_PSYKE_REVIEW_FIELD_BYTES,
                "maximum_stored_proposals": MAX_PROPOSALS,
                "proposal_ttl_seconds": self.proposal_ttl_seconds,
            },
        }

    def list_documents(self, offset: int, limit: int) -> dict[str, Any]:
        documents = self.client.list_documents()
        live_ids = {int(item["id"]) for item in documents if str(item.get("id", "")).isdigit()}
        if self.selected_document_id not in live_ids:
            self.selected_document_id = None
        values, page = _page(documents, offset, limit)
        return {
            "documents": values,
            "selected_document_id": self.selected_document_id,
            "page": page,
        }

    def select_document(self, document_id: int) -> dict[str, Any]:
        wanted = int(document_id)
        documents = self.client.list_documents()
        selected = next(
            (item for item in documents if str(item.get("id", "")) == str(wanted)),
            None,
        )
        if selected is None:
            raise GatewayError(f"Whiteboard document {wanted} was not found.")
        self.selected_document_id = wanted
        return {"selected_document_id": wanted, "document": selected}

    def _document_id(self, document_id: int | None = None) -> int:
        if document_id is not None:
            return int(document_id)
        if self.selected_document_id is not None:
            return self.selected_document_id
        documents = self.client.list_documents()
        if len(documents) == 1:
            try:
                selected = int(documents[0]["id"])
            except (KeyError, TypeError, ValueError):
                raise WhiteboardApiError("The Whiteboard document list has an invalid id.") from None
            self.selected_document_id = selected
            return selected
        if not documents:
            raise GatewayError("Whiteboard has no documents.")
        raise GatewayError(
            "No Whiteboard document is selected. Call logosforge_whiteboard_list_documents "
            "and logosforge_whiteboard_select_document first."
        )

    def current_document(self) -> dict[str, Any]:
        document_id = self._document_id()
        documents = self.client.list_documents()
        current = next(
            (item for item in documents if str(item.get("id", "")) == str(document_id)),
            None,
        )
        if current is None:
            self.selected_document_id = None
            raise GatewayError("The selected Whiteboard document no longer exists.")
        return {"selected_document_id": document_id, "document": current}

    def document_snapshot(
        self,
        document_id: int | None,
        offset: int,
        limit: int,
        max_characters: int,
    ) -> dict[str, Any]:
        resolved = self._document_id(document_id)
        raw = self.client.get_document(resolved)
        blocks = raw.get("blocks", [])
        if not isinstance(blocks, list):
            raise WhiteboardApiError("The Whiteboard manuscript has invalid blocks.")
        candidates = blocks[offset : offset + limit]
        character_candidates: list[dict[str, Any]] = []
        characters = 0
        character_limited = False
        truncated_block_ids: list[Any] = []
        for block in candidates:
            if not isinstance(block, dict):
                raise WhiteboardApiError("The Whiteboard manuscript contains an invalid block.")
            block_size = len(_text(block.get("text")))
            if character_candidates and characters + block_size > max_characters:
                character_limited = True
                break
            if not character_candidates and block_size > max_characters:
                clipped = dict(block)
                clipped["text"] = _text(block.get("text"))[:max_characters]
                character_candidates.append(clipped)
                truncated_block_ids.append(block.get("id", offset))
                characters = max_characters
                character_limited = True
                break
            character_candidates.append(block)
            characters += block_size

        metadata = dict(raw)
        metadata.pop("blocks", None)
        clipped_metadata, metadata_truncated = _clip_json_value(
            metadata,
            MAX_SNAPSHOT_METADATA_BYTES,
        )
        if not isinstance(clipped_metadata, dict):
            clipped_metadata = {}
            metadata_truncated = max(1, metadata_truncated)
        block_budget = max(
            4,
            MAX_PAGE_PAYLOAD_BYTES - _json_bytes(clipped_metadata) - 512,
        )
        selected, page = _bounded_items(
            character_candidates,
            offset=offset,
            limit=limit,
            total=len(blocks),
            payload_budget=block_budget,
        )
        manuscript = clipped_metadata
        manuscript["blocks"] = selected
        page.update(
            {
                "characters": sum(
                    len(_text(block.get("text")))
                    for block in selected
                    if isinstance(block, dict)
                ),
                "max_characters": max_characters,
                "character_limited": character_limited,
                "truncated_block_ids": truncated_block_ids,
                "metadata_byte_limited": bool(metadata_truncated),
                "metadata_truncated_value_count": metadata_truncated,
                "metadata_bytes": _json_bytes(clipped_metadata),
                "maximum_metadata_bytes": MAX_SNAPSHOT_METADATA_BYTES,
            }
        )
        return {"document": manuscript, "page": page}

    def outline(self, document_id: int | None, offset: int, limit: int) -> dict[str, Any]:
        resolved = self._document_id(document_id)
        outline = self.client.get_outline(resolved)
        values, page = _page(outline["items"], offset, limit)
        return {
            "document_id": resolved,
            "revision": outline["revision"],
            "items": values,
            "page": page,
        }

    def comments(
        self,
        document_id: int | None,
        offset: int,
        limit: int,
        include_resolved: bool,
    ) -> dict[str, Any]:
        resolved = self._document_id(document_id)
        comment_read = self.client.get_comments(resolved)
        comments = comment_read["comments"]
        if not include_resolved:
            comments = [item for item in comments if not bool(item.get("resolved"))]
        values, page = _page(comments, offset, limit)
        return {
            "document_id": resolved,
            "revision": comment_read["revision"],
            "comments": values,
            "page": page,
        }

    def psyke(
        self,
        document_id: int | None,
        query: str,
        entry_type: str,
        offset: int,
        limit: int,
    ) -> dict[str, Any]:
        resolved = self._document_id(document_id)
        psyke = self.client.get_psyke(resolved, query)
        entries = psyke["results"]
        if entry_type and entry_type != "all":
            entries = [item for item in entries if item.get("entry_type") == entry_type]
        values, page = _page(entries, offset, limit)
        return {
            "document_id": resolved,
            "revision": psyke["revision"],
            "query": query,
            "entry_type": entry_type or "all",
            "entries": values,
            "page": page,
        }

    def psyke_relations(
        self,
        document_id: int | None,
        entry_id: int | None,
        offset: int,
        limit: int,
    ) -> dict[str, Any]:
        resolved = self._document_id(document_id)
        relation_read = self.client.get_psyke_relations(resolved)
        relations = relation_read["relations"]
        if entry_id is not None:
            relations = [
                relation
                for relation in relations
                if relation.get("source_id") == entry_id
                or relation.get("target_id") == entry_id
            ]
        values, page = _page(relations, offset, limit)
        return {
            "document_id": resolved,
            "revision": relation_read["revision"],
            "entry_id": entry_id,
            "relations": values,
            "page": page,
        }

    def psyke_progressions(
        self,
        document_id: int | None,
        entry_id: int | None,
        offset: int,
        limit: int,
    ) -> dict[str, Any]:
        resolved = self._document_id(document_id)
        progression_read = self.client.get_psyke_progressions(resolved)
        progressions = progression_read["progressions"]
        if entry_id is not None:
            progressions = [
                progression
                for progression in progressions
                if progression.get("entry_id") == entry_id
            ]
        values, page = _page(progressions, offset, limit)
        return {
            "document_id": resolved,
            "revision": progression_read["revision"],
            "entry_id": entry_id,
            "progressions": values,
            "page": page,
        }

    def search(
        self,
        query: str,
        document_id: int | None,
        scope: str,
        limit: int,
    ) -> dict[str, Any]:
        resolved = self._document_id(document_id)
        needle = query.strip().casefold()
        if not needle:
            raise GatewayError("Search query must not be empty.")

        matches: list[dict[str, Any]] = []
        total = 0

        def add(kind: str, item_id: Any, title: str, haystack: str) -> None:
            nonlocal total
            if needle not in haystack.casefold():
                return
            total += 1
            if len(matches) < limit:
                matches.append(
                    {
                        "scope": kind,
                        "id": _short_search_field(item_id, MAX_SEARCH_ID),
                        "title": _short_search_field(title, MAX_SEARCH_TITLE),
                        "snippet": _snippet(haystack, needle),
                    }
                )

        if scope in {"all", "manuscript"}:
            document = self.client.get_document(resolved)
            add("manuscript", document.get("id"), _text(document.get("title")), _text(document.get("title")))
            for index, block in enumerate(document.get("blocks", [])):
                if isinstance(block, dict):
                    add(
                        "manuscript",
                        block.get("id", index),
                        f"Block {index + 1} ({_text(block.get('type')) or 'paragraph'})",
                        _text(block.get("text")),
                    )

        if scope in {"all", "outline"}:
            for index, item in enumerate(self.client.get_outline(resolved)["items"]):
                add(
                    "outline",
                    item.get("id", index),
                    _text(item.get("title") or item.get("text") or f"Outline item {index + 1}"),
                    _json_text(item),
                )

        if scope in {"all", "comments"}:
            for index, comment in enumerate(
                self.client.get_comments(resolved)["comments"]
            ):
                add(
                    "comments",
                    comment.get("id", index),
                    _text(comment.get("quote") or f"Comment {index + 1}"),
                    _json_text(comment),
                )

        if scope in {"all", "psyke"}:
            # Fetching q="" lets the bounded local search include Whiteboard's
            # description field, which the current backend q route does not index.
            for index, entry in enumerate(
                self.client.get_psyke(resolved, "")["results"]
            ):
                add(
                    "psyke",
                    entry.get("id", index),
                    _text(entry.get("name") or f"PSYKE entry {index + 1}"),
                    _json_text(entry),
                )

        return {
            "document_id": resolved,
            "query": query,
            "scope": scope,
            "matches": matches,
            "returned": len(matches),
            "total_matches": total,
            "truncated": total > len(matches),
            "limit": limit,
        }

    # -- Reviewed proposal lifecycle -----------------------------------

    @staticmethod
    def _validate_expected_revision(expected_revision: str) -> str:
        if not _valid_token(expected_revision):
            raise GatewayError(
                "expected_revision must be the exact 32-character lowercase "
                "revision returned by the corresponding read tool."
            )
        return expected_revision

    @staticmethod
    def _validate_comment_id(comment_id: Any) -> str:
        if not isinstance(comment_id, str) or _COMMENT_ID_RE.fullmatch(comment_id) is None:
            raise GatewayError(
                "comment_id must be a stable 1-128 character identifier containing "
                "only letters, digits, period, underscore, colon, or hyphen."
            )
        return comment_id

    @staticmethod
    def _validate_comment_reply_body(body: Any) -> str:
        if (
            not isinstance(body, str)
            or not body
            or body.strip() != body
            or len(body) > MAX_COMMENT_BODY_CHARACTERS
        ):
            raise GatewayError(
                "Comment reply body must be a non-blank, trimmed string of at most "
                f"{MAX_COMMENT_BODY_CHARACTERS} characters."
            )
        try:
            body.encode("utf-8")
        except UnicodeError:
            raise GatewayError("Comment reply body must be valid UTF-8 text.") from None
        if _COMMENT_AI_MENTION_RE.search(body):
            raise GatewayError(
                "MCP comment replies cannot @mention Billy or Logos because that "
                "would trigger a separate AI request."
            )
        return body

    @staticmethod
    def _validate_manuscript_patch(patch: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(patch, dict) or not patch:
            raise GatewayError("A manuscript patch must change at least one field.")
        allowed = {"title", "mode", "blocks"}
        unexpected = sorted(set(patch) - allowed)
        if unexpected:
            raise GatewayError(
                f"Unsupported manuscript patch field(s): {', '.join(unexpected)}."
            )
        if "title" in patch and (
            not isinstance(patch["title"], str) or len(patch["title"]) > 1_000
        ):
            raise GatewayError("Manuscript title must be a string of at most 1000 characters.")
        if "mode" in patch and patch["mode"] not in _WRITING_MODES:
            raise GatewayError(
                "Manuscript mode must be one of: " + ", ".join(sorted(_WRITING_MODES)) + "."
            )
        if "blocks" in patch:
            blocks = patch["blocks"]
            if not isinstance(blocks, list):
                raise GatewayError("Manuscript blocks must be an array.")
            if len(blocks) > MAX_PROPOSAL_ITEMS:
                raise GatewayError(
                    f"A manuscript proposal may contain at most {MAX_PROPOSAL_ITEMS} blocks."
                )
            seen_ids: set[str] = set()
            allowed_block_fields = {"id", "type", "text", "level", "sp", "marks"}
            for index, block in enumerate(blocks):
                if not isinstance(block, dict):
                    raise GatewayError(f"Manuscript block {index} must be an object.")
                missing = sorted({"id", "type", "text"} - set(block))
                if missing:
                    raise GatewayError(
                        f"Manuscript block {index} is missing required field(s): "
                        + ", ".join(missing)
                        + "."
                    )
                extra = sorted(set(block) - allowed_block_fields)
                if extra:
                    raise GatewayError(
                        f"Manuscript block {index} has unsupported field(s): "
                        + ", ".join(extra)
                        + "."
                    )
                block_id = block.get("id")
                if not _valid_stable_id(block_id):
                    raise GatewayError(
                        f"Manuscript block {index} has an invalid stable id."
                    )
                if block_id in seen_ids:
                    raise GatewayError(f"Manuscript block id {block_id!r} is duplicated.")
                seen_ids.add(block_id)
                block_type = block.get("type")
                if (
                    not isinstance(block_type, str)
                    or not block_type
                    or block_type.strip() != block_type
                    or len(block_type) > 64
                ):
                    raise GatewayError(
                        f"Manuscript block {index} field 'type' is invalid."
                    )
                text = block.get("text")
                if not isinstance(text, str):
                    raise GatewayError(
                        f"Manuscript block {index} field 'text' must be a string."
                    )
                if "level" in block and (
                    block["level"] is not None
                    and (
                        isinstance(block["level"], bool)
                        or not isinstance(block["level"], int)
                        or block["level"] < 1
                        or block["level"] > 6
                    )
                ):
                    raise GatewayError(
                        f"Manuscript block {index} field 'level' must be 1..6 or null."
                    )
                if (
                    "sp" in block
                    and block["sp"] is not None
                    and block["sp"] not in _SCREENPLAY_TYPES
                ):
                    raise GatewayError(
                        f"Manuscript block {index} field 'sp' is invalid."
                    )
                if "marks" in block:
                    marks = block["marks"]
                    if not isinstance(marks, list):
                        raise GatewayError(
                            f"Manuscript block {index} field 'marks' must be an array."
                        )
                    if len(marks) > MAX_MARKS_PER_BLOCK:
                        raise GatewayError(
                            f"Manuscript block {index} has too many inline marks."
                        )
                    utf16_length = len(text.encode("utf-16-le", "surrogatepass")) // 2
                    for mark_index, mark in enumerate(marks):
                        if not isinstance(mark, dict):
                            raise GatewayError(
                                f"Manuscript block {index} mark {mark_index} must be an object."
                            )
                        if set(mark) != {"type", "from", "to"}:
                            raise GatewayError(
                                f"Manuscript block {index} mark {mark_index} must contain only type, from, and to."
                            )
                        if mark.get("type") not in {"bold", "italic"}:
                            raise GatewayError(
                                f"Manuscript block {index} mark {mark_index} has an invalid type."
                            )
                        start = mark.get("from")
                        end = mark.get("to")
                        if (
                            isinstance(start, bool)
                            or not isinstance(start, int)
                            or isinstance(end, bool)
                            or not isinstance(end, int)
                            or start < 0
                            or end <= start
                            or end > utf16_length
                            or start > 9_007_199_254_740_991
                            or end > 9_007_199_254_740_991
                        ):
                            raise GatewayError(
                                f"Manuscript block {index} mark {mark_index} has invalid offsets."
                            )
        stored = copy.deepcopy(patch)
        if len(_canonical_json(stored)) > MAX_REQUEST_BYTES:
            raise GatewayError(
                f"The manuscript proposal exceeds the {MAX_REQUEST_BYTES}-byte request limit."
            )
        return stored

    @staticmethod
    def _validate_outline_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not isinstance(items, list):
            raise GatewayError("Outline items must be an array.")
        if len(items) > MAX_PROPOSAL_ITEMS:
            raise GatewayError(
                f"An outline proposal may contain at most {MAX_PROPOSAL_ITEMS} items."
            )
        seen_ids: set[str] = set()
        allowed_fields = _OUTLINE_REQUIRED_FIELDS | _OUTLINE_OPTIONAL_FIELDS
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                raise GatewayError(f"Outline item {index} must be an object.")
            missing = sorted(_OUTLINE_REQUIRED_FIELDS - set(item))
            if missing:
                raise GatewayError(
                    f"Outline item {index} is missing required field(s): "
                    + ", ".join(missing)
                    + "."
                )
            unexpected = sorted(set(item) - allowed_fields)
            if unexpected:
                raise GatewayError(
                    f"Outline item {index} has unsupported field(s): "
                    + ", ".join(unexpected)
                    + "."
                )
            item_id = item.get("id")
            if not _valid_stable_id(item_id):
                raise GatewayError(
                    f"Outline item {index} has an invalid stable id."
                )
            if item_id in seen_ids:
                raise GatewayError(f"Outline item id {item_id!r} is duplicated.")
            seen_ids.add(item_id)
            parent_id = item.get("parentId")
            if parent_id is not None and not _valid_stable_id(parent_id):
                raise GatewayError(f"Outline item {index} has an invalid parentId.")
            if item.get("type") not in _OUTLINE_TYPES:
                raise GatewayError(f"Outline item {index} has an invalid type.")
            for key in ("title", "summary"):
                if not isinstance(item.get(key), str):
                    raise GatewayError(
                        f"Outline item {index} field {key!r} must be a string."
                    )
            order = item.get("order")
            if (
                isinstance(order, bool)
                or not isinstance(order, (int, float))
                or not math.isfinite(order)
            ):
                raise GatewayError(f"Outline item {index} has an invalid order.")
            if not isinstance(item.get("collapsed"), bool) or not isinstance(
                item.get("completed"), bool
            ):
                raise GatewayError(
                    f"Outline item {index} has invalid collapsed/completed flags."
                )
            if item.get("status") not in _OUTLINE_STATUSES:
                raise GatewayError(f"Outline item {index} has an invalid status.")
            if item.get("colorLabel") not in _OUTLINE_COLORS:
                raise GatewayError(f"Outline item {index} has an invalid colorLabel.")
            tags = item.get("tags")
            if not isinstance(tags, list) or any(
                not isinstance(tag, str) or not tag for tag in tags
            ):
                raise GatewayError(f"Outline item {index} has invalid tags.")
            for key in ("createdAt", "updatedAt"):
                if not _valid_timestamp(item.get(key)):
                    raise GatewayError(
                        f"Outline item {index} field {key!r} must be a valid ISO timestamp."
                    )
            if "linkedLineId" in item and item["linkedLineId"] is not None:
                if not _valid_stable_id(item["linkedLineId"]):
                    raise GatewayError(
                        f"Outline item {index} has an invalid linkedLineId."
                    )
            if "link" in item and item["link"] is not None:
                link = item["link"]
                if not isinstance(link, dict):
                    raise GatewayError(
                        f"Outline item {index} field 'link' must be an object or null."
                    )
                missing_link = sorted({"blockIndex", "quote"} - set(link))
                extra_link = sorted(set(link) - {"blockIndex", "quote", "blockId"})
                if missing_link:
                    raise GatewayError(
                        f"Outline item {index} link is missing required field(s): "
                        + ", ".join(missing_link)
                        + "."
                    )
                if extra_link:
                    raise GatewayError(
                        f"Outline item {index} link has unsupported field(s): "
                        + ", ".join(extra_link)
                        + "."
                    )
                block_index = link.get("blockIndex")
                if (
                    isinstance(block_index, bool)
                    or not isinstance(block_index, int)
                    or block_index < 0
                    or block_index > 9_007_199_254_740_991
                ):
                    raise GatewayError(
                        f"Outline item {index} link has an invalid blockIndex."
                    )
                if not isinstance(link.get("quote"), str):
                    raise GatewayError(
                        f"Outline item {index} link quote must be a string."
                    )
                if "blockId" in link and not _valid_stable_id(link["blockId"]):
                    raise GatewayError(
                        f"Outline item {index} link has an invalid blockId."
                    )

        by_id = {item["id"]: item for item in items}
        for item in items:
            item_id = item["id"]
            parent_id = item["parentId"]
            if parent_id == item_id:
                raise GatewayError(f"Outline item {item_id!r} cannot parent itself.")
            if parent_id is not None and parent_id not in by_id:
                raise GatewayError(f"Outline item {item_id!r} has a missing parent.")
            seen_ancestors: set[str] = set()
            cursor = item
            depth = 0
            while cursor["parentId"] is not None:
                cursor_id = cursor["id"]
                if cursor_id in seen_ancestors:
                    raise GatewayError("The outline contains a parent cycle.")
                seen_ancestors.add(cursor_id)
                depth += 1
                if depth > MAX_OUTLINE_DEPTH:
                    raise GatewayError(
                        f"The outline exceeds the maximum nesting depth of {MAX_OUTLINE_DEPTH}."
                    )
                cursor = by_id[cursor["parentId"]]

        stored = copy.deepcopy(items)
        siblings_by_parent: dict[str | None, list[tuple[int, dict[str, Any]]]] = {}
        for index, item in enumerate(stored):
            siblings_by_parent.setdefault(item["parentId"], []).append((index, item))
        for siblings in siblings_by_parent.values():
            siblings.sort(key=lambda entry: (entry[1]["order"], entry[0]))
            for canonical_order, (_original_index, item) in enumerate(siblings):
                item["order"] = canonical_order

        if len(_canonical_json({"items": stored})) > MAX_REQUEST_BYTES:
            raise GatewayError(
                f"The outline proposal exceeds the {MAX_REQUEST_BYTES}-byte request limit."
            )
        return stored

    @staticmethod
    def _validate_psyke_entry(entry: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(entry, dict):
            raise GatewayError("A PSYKE entry must be an object.")
        allowed = {"name", "entry_type", "description", "notes"}
        unexpected = sorted(set(entry) - allowed)
        if unexpected:
            raise GatewayError(
                f"Unsupported PSYKE entry field(s): {', '.join(unexpected)}."
            )
        name = entry.get("name")
        if (
            not isinstance(name, str)
            or not name
            or name.strip() != name
            or len(name) > MAX_PSYKE_NAME_CHARACTERS
        ):
            raise GatewayError(
                "PSYKE name must be a non-blank, trimmed string of at most "
                f"{MAX_PSYKE_NAME_CHARACTERS} characters."
            )
        entry_type = entry.get("entry_type", "other")
        if entry_type not in _PSYKE_TYPES:
            raise GatewayError(
                "PSYKE entry_type must be one of: "
                + ", ".join(sorted(_PSYKE_TYPES))
                + "."
            )
        body: dict[str, Any] = {"name": name, "type": entry_type}
        for key in ("description", "notes"):
            value = entry.get(key, "")
            if not isinstance(value, str) or len(value) > MAX_PSYKE_TEXT_CHARACTERS:
                raise GatewayError(
                    f"PSYKE {key} must be a string of at most "
                    f"{MAX_PSYKE_TEXT_CHARACTERS} characters."
                )
            body[key] = value
        if len(_canonical_json(body)) > MAX_REQUEST_BYTES:
            raise GatewayError(
                f"The PSYKE proposal exceeds the {MAX_REQUEST_BYTES}-byte request limit."
            )
        return body

    @staticmethod
    def _validate_psyke_patch(patch: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(patch, dict) or not patch:
            raise GatewayError("A PSYKE patch must change at least one field.")
        allowed = {"name", "entry_type", "description", "notes"}
        unexpected = sorted(set(patch) - allowed)
        if unexpected:
            raise GatewayError(
                f"Unsupported PSYKE patch field(s): {', '.join(unexpected)}."
            )
        body: dict[str, Any] = {}
        if "name" in patch:
            name = patch["name"]
            if (
                not isinstance(name, str)
                or not name
                or name.strip() != name
                or len(name) > MAX_PSYKE_NAME_CHARACTERS
            ):
                raise GatewayError(
                    "PSYKE name must be a non-blank, trimmed string of at most "
                    f"{MAX_PSYKE_NAME_CHARACTERS} characters."
                )
            body["name"] = name
        if "entry_type" in patch:
            entry_type = patch["entry_type"]
            if entry_type not in _PSYKE_TYPES:
                raise GatewayError(
                    "PSYKE entry_type must be one of: "
                    + ", ".join(sorted(_PSYKE_TYPES))
                    + "."
                )
            body["type"] = entry_type
        for key in ("description", "notes"):
            if key not in patch:
                continue
            value = patch[key]
            if not isinstance(value, str) or len(value) > MAX_PSYKE_TEXT_CHARACTERS:
                raise GatewayError(
                    f"PSYKE {key} must be a string of at most "
                    f"{MAX_PSYKE_TEXT_CHARACTERS} characters."
                )
            body[key] = value
        if len(_canonical_json(body)) > MAX_REQUEST_BYTES:
            raise GatewayError(
                f"The PSYKE proposal exceeds the {MAX_REQUEST_BYTES}-byte request limit."
            )
        return body

    @staticmethod
    def _validate_positive_psyke_id(value: Any, label: str) -> int:
        if (
            isinstance(value, bool)
            or not isinstance(value, int)
            or not 1 <= value <= MAX_PSYKE_INTEGER_ID
        ):
            raise GatewayError(f"{label} must be a positive integer.")
        return value

    @staticmethod
    def _validate_psyke_relation(
        source_id: Any,
        target_id: Any,
        relation_type: Any,
    ) -> dict[str, Any]:
        source = WhiteboardMcpGateway._validate_positive_psyke_id(
            source_id, "PSYKE source_id"
        )
        target = WhiteboardMcpGateway._validate_positive_psyke_id(
            target_id, "PSYKE target_id"
        )
        if source == target:
            raise GatewayError("A PSYKE relation requires two distinct entries.")
        if (
            not isinstance(relation_type, str)
            or relation_type.strip() != relation_type
            or len(relation_type) > MAX_PSYKE_RELATION_TYPE_CHARACTERS
        ):
            raise GatewayError(
                "PSYKE relation_type must be a trimmed string of at most "
                f"{MAX_PSYKE_RELATION_TYPE_CHARACTERS} characters."
            )
        return {
            "source_id": source,
            "target_id": target,
            "relation_type": relation_type,
        }

    @staticmethod
    def _validate_psyke_progression_text(value: Any) -> str:
        if (
            not isinstance(value, str)
            or not value
            or value.strip() != value
            or len(value) > MAX_PSYKE_TEXT_CHARACTERS
        ):
            raise GatewayError(
                "PSYKE progression text must be a non-blank, trimmed string of "
                f"at most {MAX_PSYKE_TEXT_CHARACTERS} characters."
            )
        return value

    @staticmethod
    def _validate_psyke_scene_id(value: Any) -> int | None:
        if value is None:
            return None
        return WhiteboardMcpGateway._validate_positive_psyke_id(
            value, "PSYKE scene_id"
        )

    @staticmethod
    def _validate_psyke_progression_patch(
        patch: dict[str, Any],
    ) -> dict[str, Any]:
        if not isinstance(patch, dict) or not patch:
            raise GatewayError(
                "A PSYKE progression patch must change at least one field."
            )
        allowed = {"text", "scene_id"}
        unexpected = sorted(set(patch) - allowed)
        if unexpected:
            raise GatewayError(
                "Unsupported PSYKE progression patch field(s): "
                + ", ".join(unexpected)
                + "."
            )
        validated: dict[str, Any] = {}
        if "text" in patch:
            validated["text"] = WhiteboardMcpGateway._validate_psyke_progression_text(
                patch["text"]
            )
        if "scene_id" in patch:
            validated["scene_id"] = WhiteboardMcpGateway._validate_psyke_scene_id(
                patch["scene_id"]
            )
        return validated

    def _psyke_extended_proposal_context(
        self,
        document_id: int,
        expected_revision: str,
        collection: str,
    ) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]]]:
        identity_before = self.client.get_document(document_id)
        entries = self.client.get_psyke(document_id, "")
        if collection == "relations":
            related = self.client.get_psyke_relations(document_id)
            values = related["relations"]
        elif collection == "progressions":
            related = self.client.get_psyke_progressions(document_id)
            values = related["progressions"]
        else:  # Internal callers are fixed and allow-listed.
            raise GatewayError("Unsupported PSYKE proposal collection.")
        identity_after = self.client.get_document(document_id)
        incarnation = identity_before.get("incarnation")
        if (
            not _valid_token(incarnation)
            or identity_after.get("incarnation") != incarnation
        ):
            raise GatewayError(
                "The Whiteboard document identity changed while reading PSYKE. "
                "Read the document again before creating a proposal."
            )
        if (
            entries.get("revision") != expected_revision
            or related.get("revision") != expected_revision
        ):
            raise GatewayError(
                "expected_revision does not match the current PSYKE collection. "
                "Read fresh PSYKE data before creating a proposal."
            )
        return incarnation, entries["results"], values

    @staticmethod
    def _request_digest(proposal: Proposal) -> str:
        return _digest(
            {
                "operation": proposal.operation,
                "method": proposal.method,
                "path": proposal.path,
                "body": proposal.body,
                "document_id": proposal.document_id,
                "resource_kind": proposal.resource_kind,
                "incarnation": proposal.incarnation,
                "expected_revision": proposal.expected_revision,
                "mutation_id": proposal.mutation_id,
            }
        )

    def _store_proposal(
        self,
        *,
        operation: str,
        method: str,
        path: str,
        body: dict[str, Any],
        summary: str,
        document_id: int,
        resource_kind: str,
        incarnation: str,
        expected_revision: str,
        review: dict[str, Any],
    ) -> dict[str, Any]:
        now = time.time()
        proposal_id = "lfwbp_" + secrets.token_urlsafe(18)
        stored_body = copy.deepcopy(body)
        if len(_canonical_json(stored_body)) > MAX_REQUEST_BYTES:
            raise GatewayError(
                f"The proposal exceeds the {MAX_REQUEST_BYTES}-byte request limit."
            )
        proposal = Proposal(
            proposal_id=proposal_id,
            operation=operation,
            method=method,
            path=path,
            body=stored_body,
            summary=summary,
            document_id=int(document_id),
            resource_kind=resource_kind,
            incarnation=incarnation,
            expected_revision=expected_revision,
            mutation_id=proposal_id,
            created_at=now,
            expires_at=now + self.proposal_ttl_seconds,
            request_digest="",
            review=copy.deepcopy(review),
        )
        proposal.request_digest = self._request_digest(proposal)
        with self._lock:
            self._prune_expired(now)
            terminal = sorted(
                (
                    value
                    for value in self._proposals.values()
                    if value.state in {"applied", "failed", "discarded"}
                ),
                key=lambda value: value.created_at,
            )
            while len(self._proposals) >= MAX_PROPOSALS and terminal:
                self._proposals.pop(terminal.pop(0).proposal_id, None)
            if len(self._proposals) >= MAX_PROPOSALS:
                raise GatewayError(
                    "This MCP session already has the maximum number of pending or "
                    "in-flight proposals. Apply or discard one before creating another."
                )
            self._proposals[proposal.proposal_id] = proposal
        return proposal.public(request_body_offset=0)

    def propose_manuscript_patch(
        self,
        document_id: int | None,
        expected_revision: str,
        patch: dict[str, Any],
    ) -> dict[str, Any]:
        resolved = self._document_id(document_id)
        expected = self._validate_expected_revision(expected_revision)
        current = self.client.get_document(resolved)
        actual = current.get("revision")
        incarnation = current.get("incarnation")
        if actual != expected:
            raise GatewayError(
                "expected_revision does not match the current manuscript. "
                "Read a fresh document snapshot before creating a proposal."
            )
        if not _valid_token(incarnation):
            raise GatewayError("The current Whiteboard document has an invalid incarnation.")
        stored_patch = self._validate_manuscript_patch(patch)
        changed_fields = [
            key for key, value in stored_patch.items() if current.get(key) != value
        ]
        if not changed_fields:
            raise GatewayError("The manuscript patch does not change the current document.")
        proposed = copy.deepcopy(current)
        proposed.update(stored_patch)
        return self._store_proposal(
            operation="patch_manuscript",
            method="PUT",
            path=f"/api/whiteboard?doc={resolved}",
            body=stored_patch,
            summary=(
                f"Patch manuscript fields {', '.join(changed_fields)} in Whiteboard "
                f"document {resolved}."
            ),
            document_id=resolved,
            resource_kind="whiteboard",
            incarnation=incarnation,
            expected_revision=expected,
            review={
                "changed_fields": changed_fields,
                "before": _manuscript_review(current),
                "after": _manuscript_review(proposed),
                "block_changes": _collection_change_review(
                    current["blocks"], proposed["blocks"]
                ),
            },
        )

    def propose_outline_replace(
        self,
        document_id: int | None,
        expected_revision: str,
        items: list[dict[str, Any]],
    ) -> dict[str, Any]:
        resolved = self._document_id(document_id)
        expected = self._validate_expected_revision(expected_revision)
        identity_before = self.client.get_document(resolved)
        current = self.client.get_outline(resolved)
        identity_after = self.client.get_document(resolved)
        incarnation = identity_before.get("incarnation")
        if (
            not _valid_token(incarnation)
            or identity_after.get("incarnation") != incarnation
        ):
            raise GatewayError(
                "The Whiteboard document identity changed while reading its outline. "
                "Read the document again before creating a proposal."
            )
        if current.get("revision") != expected:
            raise GatewayError(
                "expected_revision does not match the current outline. "
                "Read a fresh outline before creating a proposal."
            )
        stored_items = self._validate_outline_items(items)
        before_items = current["items"]
        if before_items == stored_items:
            raise GatewayError("The proposed outline is identical to the current outline.")
        before_ids = {_text(item.get("id")) for item in before_items}
        after_ids = {_text(item.get("id")) for item in stored_items}
        added_ids = after_ids - before_ids
        removed_ids = before_ids - after_ids
        added_id_sample, added_ids_truncated = _bounded_identifier_sample(added_ids)
        removed_id_sample, removed_ids_truncated = _bounded_identifier_sample(
            removed_ids
        )
        return self._store_proposal(
            operation="replace_outline",
            method="PUT",
            path=f"/api/outline/items?doc={resolved}",
            body={"items": stored_items},
            summary=f"Replace the outline for Whiteboard document {resolved}.",
            document_id=resolved,
            resource_kind="outline",
            incarnation=incarnation,
            expected_revision=expected,
            review={
                "before": _outline_collection_review(before_items),
                "after": _outline_collection_review(stored_items),
                "added_count": len(added_ids),
                "removed_count": len(removed_ids),
                "added_ids": added_id_sample,
                "removed_ids": removed_id_sample,
                "id_change_list_truncated": (
                    added_ids_truncated or removed_ids_truncated
                ),
                "max_id_list_bytes": MAX_PROPOSAL_ID_SAMPLE_BYTES,
                "item_changes": _collection_change_review(
                    before_items, stored_items
                ),
            },
        )

    def _comment_proposal_context(
        self,
        document_id: int,
        comment_id: str,
        expected_revision: str,
    ) -> tuple[str, dict[str, Any]]:
        identity_before = self.client.get_document(document_id)
        current = self.client.get_comments(document_id)
        identity_after = self.client.get_document(document_id)
        incarnation = identity_before.get("incarnation")
        if (
            not _valid_token(incarnation)
            or identity_after.get("incarnation") != incarnation
        ):
            raise GatewayError(
                "The Whiteboard document identity changed while reading comments. "
                "Read the document again before creating a proposal."
            )
        if current.get("revision") != expected_revision:
            raise GatewayError(
                "expected_revision does not match the current comments collection. "
                "Read fresh comments before creating a proposal."
            )
        comment = next(
            (
                item
                for item in current["comments"]
                if item.get("id") == comment_id
            ),
            None,
        )
        if comment is None:
            raise GatewayError(f"Comment {comment_id!r} does not exist.")
        return incarnation, comment

    def propose_comment_reply(
        self,
        document_id: int | None,
        comment_id: str,
        expected_revision: str,
        body: str,
    ) -> dict[str, Any]:
        resolved = self._document_id(document_id)
        target = self._validate_comment_id(comment_id)
        expected = self._validate_expected_revision(expected_revision)
        reply_body = self._validate_comment_reply_body(body)
        incarnation, current = self._comment_proposal_context(
            resolved,
            target,
            expected,
        )
        return self._store_proposal(
            operation="reply_to_comment",
            method="POST",
            path=(
                "/api/comments/"
                f"{urllib.parse.quote(target, safe='')}/replies?doc={resolved}"
            ),
            body={"body": reply_body},
            summary=(
                f"Reply to comment {target!r} in Whiteboard document {resolved}."
            ),
            document_id=resolved,
            resource_kind="comments",
            incarnation=incarnation,
            expected_revision=expected,
            review={
                "change": "reply",
                "comment": _comment_review(current),
                "reply": _comment_text_review(reply_body),
                "author": "MCP assistant",
            },
        )

    def propose_comment_resolution(
        self,
        document_id: int | None,
        comment_id: str,
        expected_revision: str,
        resolved_state: bool,
    ) -> dict[str, Any]:
        resolved = self._document_id(document_id)
        target = self._validate_comment_id(comment_id)
        expected = self._validate_expected_revision(expected_revision)
        if not isinstance(resolved_state, bool):
            raise GatewayError("resolved must be a boolean.")
        incarnation, current = self._comment_proposal_context(
            resolved,
            target,
            expected,
        )
        current_state = current.get("resolved")
        if current_state is resolved_state:
            state = "resolved" if resolved_state else "open"
            raise GatewayError(f"Comment {target!r} is already {state}.")
        operation = "resolve" if resolved_state else "reopen"
        encoded_target = urllib.parse.quote(target, safe="")
        return self._store_proposal(
            operation="set_comment_resolution",
            method="PUT",
            path=f"/api/comments/{encoded_target}?doc={resolved}",
            body={"resolved": resolved_state},
            summary=(
                f"{operation.capitalize()} comment {target!r} in Whiteboard "
                f"document {resolved}."
            ),
            document_id=resolved,
            resource_kind="comments",
            incarnation=incarnation,
            expected_revision=expected,
            review={
                "change": operation,
                "comment": _comment_review(current),
                "before_resolved": current_state,
                "after_resolved": resolved_state,
            },
        )

    def propose_psyke_entry(
        self,
        document_id: int | None,
        expected_revision: str,
        entry: dict[str, Any],
    ) -> dict[str, Any]:
        resolved = self._document_id(document_id)
        expected = self._validate_expected_revision(expected_revision)
        identity_before = self.client.get_document(resolved)
        current = self.client.get_psyke(resolved, "")
        identity_after = self.client.get_document(resolved)
        incarnation = identity_before.get("incarnation")
        if (
            not _valid_token(incarnation)
            or identity_after.get("incarnation") != incarnation
        ):
            raise GatewayError(
                "The Whiteboard document identity changed while reading PSYKE. "
                "Read the document again before creating a proposal."
            )
        if current.get("revision") != expected:
            raise GatewayError(
                "expected_revision does not match the current PSYKE collection. "
                "Read fresh PSYKE data before creating a proposal."
            )
        body = self._validate_psyke_entry(entry)
        after = {
            "name": body["name"],
            "entry_type": body["type"],
            "aliases": [],
            "description": body["description"],
            "notes": body["notes"],
        }
        return self._store_proposal(
            operation="create_psyke_entry",
            method="POST",
            path=f"/api/psyke/elements?doc={resolved}",
            body=body,
            summary=(
                f"Create PSYKE {body['type']} {body['name']!r} in Whiteboard "
                f"document {resolved}."
            ),
            document_id=resolved,
            resource_kind="psyke",
            incarnation=incarnation,
            expected_revision=expected,
            review={"change": "create", "after": _psyke_entry_review(after)},
        )

    def propose_psyke_patch(
        self,
        document_id: int | None,
        element_id: int,
        expected_revision: str,
        patch: dict[str, Any],
    ) -> dict[str, Any]:
        resolved = self._document_id(document_id)
        if isinstance(element_id, bool) or not isinstance(element_id, int) or element_id < 1:
            raise GatewayError("PSYKE entry_id must be a positive integer.")
        expected = self._validate_expected_revision(expected_revision)
        identity_before = self.client.get_document(resolved)
        current = self.client.get_psyke(resolved, "")
        identity_after = self.client.get_document(resolved)
        incarnation = identity_before.get("incarnation")
        if (
            not _valid_token(incarnation)
            or identity_after.get("incarnation") != incarnation
        ):
            raise GatewayError(
                "The Whiteboard document identity changed while reading PSYKE. "
                "Read the document again before creating a proposal."
            )
        if current.get("revision") != expected:
            raise GatewayError(
                "expected_revision does not match the current PSYKE collection. "
                "Read fresh PSYKE data before creating a proposal."
            )
        current_entry = next(
            (
                item
                for item in current["results"]
                if str(item.get("id", "")) == str(element_id)
            ),
            None,
        )
        if current_entry is None:
            raise GatewayError(f"PSYKE entry {element_id} does not exist.")
        body = self._validate_psyke_patch(patch)
        frontend_patch = {
            ("entry_type" if key == "type" else key): value
            for key, value in body.items()
        }
        changed_fields = [
            key
            for key, value in frontend_patch.items()
            if current_entry.get(key) != value
        ]
        if not changed_fields:
            raise GatewayError("The PSYKE patch does not change the current entry.")
        proposed = copy.deepcopy(current_entry)
        proposed.update(frontend_patch)
        return self._store_proposal(
            operation="patch_psyke_entry",
            method="PATCH",
            path=f"/api/psyke/elements/{element_id}?doc={resolved}",
            body=body,
            summary=(
                f"Patch PSYKE entry {element_id} ({_text(current_entry.get('name'))!r}) "
                f"in Whiteboard document {resolved}."
            ),
            document_id=resolved,
            resource_kind="psyke",
            incarnation=incarnation,
            expected_revision=expected,
            review={
                "change": "patch",
                "entry_id": str(element_id),
                "changed_fields": changed_fields,
                "before": _psyke_entry_review(current_entry),
                "after": _psyke_entry_review(proposed),
            },
        )

    def propose_psyke_relation(
        self,
        document_id: int | None,
        source_id: int,
        target_id: int,
        expected_revision: str,
        relation_type: str,
    ) -> dict[str, Any]:
        resolved = self._document_id(document_id)
        expected = self._validate_expected_revision(expected_revision)
        body = self._validate_psyke_relation(
            source_id, target_id, relation_type
        )
        incarnation, entries, relations = self._psyke_extended_proposal_context(
            resolved, expected, "relations"
        )
        by_id = {int(entry["id"]): entry for entry in entries}
        source = by_id.get(body["source_id"])
        target = by_id.get(body["target_id"])
        if source is None:
            raise GatewayError(f"PSYKE entry {body['source_id']} does not exist.")
        if target is None:
            raise GatewayError(f"PSYKE entry {body['target_id']} does not exist.")
        wanted_pair = frozenset((body["source_id"], body["target_id"]))
        existing = next(
            (
                relation
                for relation in relations
                if frozenset(
                    (relation.get("source_id"), relation.get("target_id"))
                )
                == wanted_pair
            ),
            None,
        )
        if existing is not None:
            raise GatewayError(
                "Those PSYKE entries are already related. Relation editing is not "
                "available through this MCP milestone."
            )
        proposed = {
            "id": f"{body['source_id']}:{body['target_id']}",
            "source_id": body["source_id"],
            "target_id": body["target_id"],
            "source": _text(source.get("name")),
            "target": _text(target.get("name")),
            "relation_type": body["relation_type"],
        }
        return self._store_proposal(
            operation="create_psyke_relation",
            method="POST",
            path=f"/api/psyke/relations?doc={resolved}",
            body=body,
            summary=(
                f"Relate PSYKE entries {body['source_id']} and {body['target_id']} "
                f"in Whiteboard document {resolved}."
            ),
            document_id=resolved,
            resource_kind="psyke",
            incarnation=incarnation,
            expected_revision=expected,
            review={
                "change": "create_relation",
                "source": _psyke_entry_review(source),
                "target": _psyke_entry_review(target),
                "after": _psyke_relation_review(proposed),
            },
        )

    def propose_psyke_progression(
        self,
        document_id: int | None,
        entry_id: int,
        expected_revision: str,
        text: str,
        scene_id: int | None,
    ) -> dict[str, Any]:
        resolved = self._document_id(document_id)
        expected = self._validate_expected_revision(expected_revision)
        owner_id = self._validate_positive_psyke_id(entry_id, "PSYKE entry_id")
        body = {
            "entry_id": owner_id,
            "text": self._validate_psyke_progression_text(text),
            "scene_id": self._validate_psyke_scene_id(scene_id),
        }
        incarnation, entries, progressions = self._psyke_extended_proposal_context(
            resolved, expected, "progressions"
        )
        owner = next(
            (entry for entry in entries if int(entry["id"]) == owner_id),
            None,
        )
        if owner is None:
            raise GatewayError(f"PSYKE entry {owner_id} does not exist.")
        duplicate = next(
            (
                progression
                for progression in progressions
                if progression.get("entry_id") == owner_id
                and progression.get("text") == body["text"]
                and progression.get("scene_id") == body["scene_id"]
            ),
            None,
        )
        if duplicate is not None:
            raise GatewayError(
                "An identical PSYKE progression already exists for that entry and scene."
            )
        proposed = {
            "id": None,
            "entry_id": owner_id,
            "text": body["text"],
            "scene_id": body["scene_id"],
            "scene_title": "",
            "sort_order": None,
        }
        return self._store_proposal(
            operation="create_psyke_progression",
            method="POST",
            path=f"/api/psyke/progressions?doc={resolved}",
            body=body,
            summary=(
                f"Add a progression to PSYKE entry {owner_id} "
                f"({_text(owner.get('name'))!r}) in Whiteboard document {resolved}."
            ),
            document_id=resolved,
            resource_kind="psyke",
            incarnation=incarnation,
            expected_revision=expected,
            review={
                "change": "create_progression",
                "entry": _psyke_entry_review(owner),
                "after": _psyke_progression_review(proposed),
            },
        )

    def propose_psyke_progression_patch(
        self,
        document_id: int | None,
        progression_id: int,
        expected_revision: str,
        patch: dict[str, Any],
    ) -> dict[str, Any]:
        resolved = self._document_id(document_id)
        target_id = self._validate_positive_psyke_id(
            progression_id, "PSYKE progression_id"
        )
        expected = self._validate_expected_revision(expected_revision)
        validated_patch = self._validate_psyke_progression_patch(patch)
        incarnation, entries, progressions = self._psyke_extended_proposal_context(
            resolved, expected, "progressions"
        )
        current = next(
            (
                progression
                for progression in progressions
                if progression.get("id") == target_id
            ),
            None,
        )
        if current is None:
            raise GatewayError(f"PSYKE progression {target_id} does not exist.")
        owner = next(
            (
                entry
                for entry in entries
                if int(entry["id"]) == current.get("entry_id")
            ),
            None,
        )
        if owner is None:
            raise GatewayError(
                f"PSYKE progression {target_id} has no valid owning entry."
            )
        body = {
            "text": validated_patch.get("text", current["text"]),
            "scene_id": validated_patch.get("scene_id", current["scene_id"]),
        }
        if (
            body["text"] == current["text"]
            and body["scene_id"] == current["scene_id"]
        ):
            raise GatewayError(
                "The PSYKE progression patch does not change the current progression."
            )
        proposed = copy.deepcopy(current)
        proposed.update(body)
        if body["scene_id"] != current["scene_id"]:
            proposed["scene_title"] = ""
        changed_fields = [
            field_name
            for field_name in ("text", "scene_id")
            if proposed[field_name] != current[field_name]
        ]
        return self._store_proposal(
            operation="patch_psyke_progression",
            method="PATCH",
            path=f"/api/psyke/progressions/{target_id}?doc={resolved}",
            body=body,
            summary=(
                f"Patch PSYKE progression {target_id} for entry "
                f"{current['entry_id']} ({_text(owner.get('name'))!r}) in "
                f"Whiteboard document {resolved}."
            ),
            document_id=resolved,
            resource_kind="psyke",
            incarnation=incarnation,
            expected_revision=expected,
            review={
                "change": "patch_progression",
                "changed_fields": changed_fields,
                "entry": _psyke_entry_review(owner),
                "before": _psyke_progression_review(current),
                "after": _psyke_progression_review(proposed),
            },
        )

    def get_proposal(
        self,
        proposal_id: str,
        request_body_offset: int = 0,
        request_body_max_bytes: int = MAX_PROPOSAL_BODY_PAGE_BYTES,
    ) -> dict[str, Any]:
        if request_body_offset < 0:
            raise GatewayError("request_body_offset must be at least 0.")
        if not 1_024 <= request_body_max_bytes <= MAX_PROPOSAL_BODY_PAGE_BYTES:
            raise GatewayError(
                "request_body_max_bytes must be between 1024 and "
                f"{MAX_PROPOSAL_BODY_PAGE_BYTES}."
            )
        with self._lock:
            proposal = self._proposal(proposal_id)
            self._expire(proposal)
            return proposal.public(
                include_result=True,
                request_body_offset=request_body_offset,
                request_body_max_bytes=request_body_max_bytes,
            )

    def list_proposals(self, include_finished: bool = False) -> dict[str, Any]:
        now = time.time()
        with self._lock:
            self._prune_expired(now)
            values = list(self._proposals.values())
            if not include_finished:
                values = [value for value in values if value.state == "pending"]
            values.sort(key=lambda value: value.created_at)
            return {"proposals": [value.public() for value in values]}

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
                "LOGOSFORGE_WHITEBOARD_MCP_ALLOW_WRITES=1 after reviewing the "
                "Whiteboard MCP security boundary."
            )
        with self._lock:
            proposal = self._proposal(proposal_id)
            self._expire(proposal)
            if proposal.state != "pending":
                raise GatewayError(f"Proposal is {proposal.state}, not pending.")
            if (
                self.selected_document_id is not None
                and self.selected_document_id != proposal.document_id
            ):
                raise GatewayError(
                    "The selected document differs from this proposal's document. "
                    "Select the original document before applying it."
                )
            if self._request_digest(proposal) != proposal.request_digest:
                proposal.state = "failed"
                proposal.error = "Proposal integrity check failed; create a fresh proposal."
                raise GatewayError(proposal.error)
            # Mark before I/O.  A lost response is ambiguous and must never lead
            # the MCP client to repeat a possibly committed write automatically.
            proposal.state = "applying"

        try:
            if proposal.operation == "patch_manuscript":
                updated = self.client.update_document(
                    proposal.document_id,
                    incarnation=proposal.incarnation,
                    expected_revision=proposal.expected_revision,
                    mutation_id=proposal.mutation_id,
                    patch=proposal.body,
                )
                receipt = {
                    "resource": "manuscript",
                    "document_id": proposal.document_id,
                    "revision": updated.get("revision"),
                    "incarnation": updated.get("incarnation"),
                    "title": updated.get("title"),
                    "mode": updated.get("mode"),
                    "block_count": len(updated.get("blocks", [])),
                    "updated_at": updated.get("updated_at"),
                }
            elif proposal.operation == "replace_outline":
                updated_outline = self.client.replace_outline(
                    proposal.document_id,
                    incarnation=proposal.incarnation,
                    expected_revision=proposal.expected_revision,
                    mutation_id=proposal.mutation_id,
                    items=proposal.body["items"],
                )
                receipt = {
                    "resource": "outline",
                    "document_id": proposal.document_id,
                    "revision": updated_outline.get("revision"),
                    "item_count": len(updated_outline.get("items", [])),
                }
            elif proposal.operation == "reply_to_comment":
                marker = "/api/comments/"
                comment_id = urllib.parse.unquote(
                    proposal.path.split(marker, 1)[1].split("/replies", 1)[0]
                )
                updated_comment = self.client.reply_to_comment(
                    proposal.document_id,
                    comment_id,
                    incarnation=proposal.incarnation,
                    expected_revision=proposal.expected_revision,
                    mutation_id=proposal.mutation_id,
                    body=proposal.body["body"],
                )
                comment = updated_comment["comment"]
                receipt = {
                    "resource": "comments",
                    "operation": "reply",
                    "document_id": proposal.document_id,
                    "revision": updated_comment["revision"],
                    "comment_id": comment["id"],
                    "reply_id": proposal.mutation_id,
                    "reply_count": len(comment["replies"]),
                    "resolved": comment["resolved"],
                    "updated_at": comment["updated_at"],
                }
            elif proposal.operation == "set_comment_resolution":
                marker = "/api/comments/"
                comment_id = urllib.parse.unquote(
                    proposal.path.split(marker, 1)[1].split("?", 1)[0]
                )
                updated_comment = self.client.set_comment_resolution(
                    proposal.document_id,
                    comment_id,
                    incarnation=proposal.incarnation,
                    expected_revision=proposal.expected_revision,
                    mutation_id=proposal.mutation_id,
                    resolved=proposal.body["resolved"],
                )
                comment = updated_comment["comment"]
                receipt = {
                    "resource": "comments",
                    "operation": "resolve" if comment["resolved"] else "reopen",
                    "document_id": proposal.document_id,
                    "revision": updated_comment["revision"],
                    "comment_id": comment["id"],
                    "resolved": comment["resolved"],
                    "reply_count": len(comment["replies"]),
                    "updated_at": comment["updated_at"],
                }
            elif proposal.operation == "create_psyke_entry":
                updated_psyke = self.client.create_psyke_entry(
                    proposal.document_id,
                    incarnation=proposal.incarnation,
                    expected_revision=proposal.expected_revision,
                    mutation_id=proposal.mutation_id,
                    entry=proposal.body,
                )
                receipt = {
                    "resource": "psyke",
                    "operation": "create",
                    "document_id": proposal.document_id,
                    "revision": updated_psyke.get("revision"),
                    "element": updated_psyke.get("element"),
                }
            elif proposal.operation == "patch_psyke_entry":
                marker = "/api/psyke/elements/"
                element_id = int(proposal.path.split(marker, 1)[1].split("?", 1)[0])
                updated_psyke = self.client.patch_psyke_entry(
                    proposal.document_id,
                    element_id,
                    incarnation=proposal.incarnation,
                    expected_revision=proposal.expected_revision,
                    mutation_id=proposal.mutation_id,
                    patch=proposal.body,
                )
                receipt = {
                    "resource": "psyke",
                    "operation": "patch",
                    "document_id": proposal.document_id,
                    "revision": updated_psyke.get("revision"),
                    "element": updated_psyke.get("element"),
                }
            elif proposal.operation == "create_psyke_relation":
                updated_relation = self.client.create_psyke_relation(
                    proposal.document_id,
                    incarnation=proposal.incarnation,
                    expected_revision=proposal.expected_revision,
                    mutation_id=proposal.mutation_id,
                    relation=proposal.body,
                )
                relation = updated_relation["relation"]
                receipt = {
                    "resource": "psyke",
                    "operation": "create_relation",
                    "document_id": proposal.document_id,
                    "revision": updated_relation["revision"],
                    "relation_id": relation["id"],
                    "source_id": relation["source_id"],
                    "target_id": relation["target_id"],
                    "relation_type": relation["relation_type"],
                }
            elif proposal.operation == "create_psyke_progression":
                updated_progression = self.client.create_psyke_progression(
                    proposal.document_id,
                    incarnation=proposal.incarnation,
                    expected_revision=proposal.expected_revision,
                    mutation_id=proposal.mutation_id,
                    progression=proposal.body,
                )
                progression = updated_progression["progression"]
                progression_text = progression["text"]
                receipt = {
                    "resource": "psyke",
                    "operation": "create_progression",
                    "document_id": proposal.document_id,
                    "revision": updated_progression["revision"],
                    "progression_id": progression["id"],
                    "entry_id": progression["entry_id"],
                    "scene_id": progression["scene_id"],
                    "sort_order": progression["sort_order"],
                    "text_characters": len(progression_text),
                    "text_sha256": hashlib.sha256(
                        progression_text.encode("utf-8")
                    ).hexdigest(),
                }
            elif proposal.operation == "patch_psyke_progression":
                marker = "/api/psyke/progressions/"
                progression_id = int(
                    proposal.path.split(marker, 1)[1].split("?", 1)[0]
                )
                updated_progression = self.client.patch_psyke_progression(
                    proposal.document_id,
                    progression_id,
                    incarnation=proposal.incarnation,
                    expected_revision=proposal.expected_revision,
                    mutation_id=proposal.mutation_id,
                    patch=proposal.body,
                )
                progression = updated_progression["progression"]
                progression_text = progression["text"]
                receipt = {
                    "resource": "psyke",
                    "operation": "patch_progression",
                    "document_id": proposal.document_id,
                    "revision": updated_progression["revision"],
                    "progression_id": progression["id"],
                    "entry_id": progression["entry_id"],
                    "scene_id": progression["scene_id"],
                    "sort_order": progression["sort_order"],
                    "text_characters": len(progression_text),
                    "text_sha256": hashlib.sha256(
                        progression_text.encode("utf-8")
                    ).hexdigest(),
                }
            else:
                raise GatewayError("Proposal operation is not allow-listed.")
        except Exception as exc:
            safe_error = str(exc) if isinstance(exc, (GatewayError, WhiteboardApiError)) else "Unexpected apply failure."
            with self._lock:
                proposal.state = "failed"
                proposal.error = safe_error
            raise GatewayError(
                "The apply attempt failed and will not be retried automatically: "
                + safe_error
            ) from exc

        with self._lock:
            proposal.state = "applied"
            proposal.result = receipt
            return proposal.public(include_result=True)

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
        instant = time.time() if now is None else now
        if proposal.state == "pending" and proposal.expires_at <= instant:
            proposal.state = "failed"
            proposal.error = "Proposal expired; read current state and create a fresh proposal."
        if (
            raise_error
            and proposal.state == "failed"
            and proposal.error.startswith("Proposal expired")
        ):
            raise GatewayError(proposal.error)

    def _prune_expired(self, now: float) -> None:
        for proposal in self._proposals.values():
            self._expire(proposal, now, raise_error=False)


def call_gateway(gateway: WhiteboardMcpGateway, action: Callable[[], Any]) -> dict[str, Any]:
    try:
        return _bounded_success(action())
    except (GatewayError, WhiteboardApiError, ValueError, TypeError) as exc:
        return {"ok": False, "error": str(exc)}
    except Exception:
        LOGGER.exception("Unexpected Whiteboard MCP gateway failure")
        return {"ok": False, "error": "Unexpected Whiteboard MCP gateway failure."}
