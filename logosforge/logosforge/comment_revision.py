"""Content-addressed revisions for Pro inline-comment threads."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from datetime import datetime, timezone
from typing import Any

_COMMENT_FIELDS = (
    "id",
    "project_id",
    "source_id",
    "start_scene_id",
    "start_field",
    "from_offset",
    "end_scene_id",
    "end_field",
    "to_offset",
    "quote",
    "prefix",
    "suffix",
    "body",
    "resolved",
    "created_at",
    "updated_at",
)

_REPLY_FIELDS = (
    "id",
    "project_id",
    "comment_id",
    "source_id",
    "body",
    "author",
    "sort_order",
    "created_at",
)


def _field(value: Any, name: str) -> Any:
    if isinstance(value, Mapping):
        return value.get(name)
    return getattr(value, name, None)


def _canonical_value(value: Any) -> Any:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        else:
            value = value.astimezone(timezone.utc)
        return value.isoformat(timespec="microseconds").replace("+00:00", "Z")
    return value


def comment_revision(comment: Any, replies: Iterable[Any]) -> str:
    """Return a stable SHA-256 revision for a root and its ordered replies.

    The token is derived instead of stored, so existing databases need no
    migration. Every persisted scalar that can affect a thread participates.
    """

    ordered_replies = sorted(
        replies,
        key=lambda reply: (
            int(_field(reply, "sort_order") or 0),
            int(_field(reply, "id") or 0),
        ),
    )
    payload = {
        "comment": {
            name: _canonical_value(_field(comment, name))
            for name in _COMMENT_FIELDS
        },
        "replies": [
            {
                name: _canonical_value(_field(reply, name))
                for name in _REPLY_FIELDS
            }
            for reply in ordered_replies
        ],
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
