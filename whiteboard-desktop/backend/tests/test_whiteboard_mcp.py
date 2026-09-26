"""Focused contract and real-stdio tests for the Whiteboard MCP companion."""

from __future__ import annotations

import asyncio
import hashlib
import io
import json
import os
import sys
import threading
import urllib.error
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

import pytest

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

import app.whiteboard_mcp.server as whiteboard_mcp_server
from app.whiteboard_mcp.client import (
    MAX_COMMENT_BODY_CHARACTERS,
    MAX_COMMENTS,
    MAX_PSYKE_ALIASES,
    MAX_PSYKE_ALIAS_CHARACTERS,
    MAX_PSYKE_ALIAS_TOTAL_CHARACTERS,
    MAX_PSYKE_ID_CHARACTERS,
    MAX_PSYKE_INTEGER_ID,
    MAX_PSYKE_NAME_CHARACTERS,
    MAX_PSYKE_RELATION_TYPE_CHARACTERS,
    MAX_PSYKE_SCENE_TITLE_CHARACTERS,
    MAX_PSYKE_TEXT_CHARACTERS,
    MAX_REQUEST_BYTES,
    WhiteboardApiClient,
    WhiteboardApiError,
)
from app.whiteboard_mcp.gateway import (
    MAX_PROPOSALS,
    MAX_PROPOSAL_ID_SAMPLE_BYTES,
    MAX_RESULT_BYTES,
    MAX_SEARCH_ID,
    MAX_SEARCH_TITLE,
    WhiteboardMcpGateway,
)
from app.whiteboard_mcp.server import (
    HANDLERS,
    SERVER_NAME,
    SERVER_VERSION,
    TOOL_PREFIX,
    TOOL_SPECS,
    McpConfig,
    McpToolError,
    call_tool,
)


def _comment_dto(
    comment_id: str,
    quote: str,
    body: str,
    *,
    resolved: bool = False,
    replies: list[dict] | None = None,
) -> dict:
    return {
        "id": comment_id,
        "anchor": {
            "block_index": 0,
            "block_id": "b1",
            "from_offset": 2,
            "to_offset": 9,
            "end_block_index": None,
            "end_block_id": None,
            "prefix": "A ",
            "suffix": " burns",
        },
        "quote": quote,
        "body": body,
        "resolved": resolved,
        "replies": list(replies or []),
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
    }


class FakeClient:
    def __init__(self) -> None:
        self.documents = [
            {"id": "1", "incarnation": "a" * 32, "revision": "3" * 32, "title": "Alpha", "mode": "prose", "updated_at": "2026-01-02T00:00:00Z"},
            {"id": "2", "incarnation": "b" * 32, "revision": "4" * 32, "title": "Beta", "mode": "screenplay", "updated_at": "2026-01-01T00:00:00Z"},
        ]
        self.blocks = {
            1: [
                {"id": "b1", "type": "paragraph", "text": "A lantern burns beside Mara."},
                {"id": "b2", "type": "paragraph", "text": "The rain answers the glass."},
                {"id": "b3", "type": "paragraph", "text": "Mara closes the book."},
            ],
            2: [],
        }
        self.outline = {1: [{"id": "o1", "title": "Mara arrives"}], 2: []}
        self.outline_revision = {1: "1" * 32, 2: "2" * 32}
        self.comments = {
            1: [
                _comment_dto("c1", "lantern", "Track this image"),
                _comment_dto("c2", "rain", "Resolved note", resolved=True),
            ],
            2: [],
        }
        self.comments_revision = {1: "c" * 32, 2: "d" * 32}
        self.entries = {
            1: [
                {"id": "10", "name": "Mara", "entry_type": "character", "aliases": [], "description": "Keeper of the lantern", "notes": ""},
                {"id": "11", "name": "North House", "entry_type": "place", "aliases": [], "description": "Rain-dark manor", "notes": ""},
            ],
            2: [],
        }
        self.relations = {
            1: [
                {
                    "id": "10:11",
                    "source_id": 10,
                    "target_id": 11,
                    "source": "Mara",
                    "target": "North House",
                    "relation_type": "haunts",
                }
            ],
            2: [],
        }
        self.progressions = {
            1: [
                {
                    "id": 21,
                    "entry_id": 10,
                    "text": "Mara still guards the lantern.",
                    "scene_id": None,
                    "scene_title": "",
                    "sort_order": 1,
                }
            ],
            2: [],
        }
        self.psyke_revision = {1: "7" * 32, 2: "8" * 32}
        self.settings = {1: {}, 2: {}}
        self.write_calls: list[dict[str, object]] = []

    def list_documents(self):
        return list(self.documents)

    def get_document(self, document_id):
        doc = next(item for item in self.documents if int(item["id"]) == document_id)
        return {
            **doc,
            "settings": self.settings[document_id],
            "blocks": list(self.blocks[document_id]),
        }

    def get_outline(self, document_id):
        return {
            "items": list(self.outline[document_id]),
            "revision": self.outline_revision[document_id],
        }

    def get_comments(self, document_id):
        return {
            "comments": json.loads(json.dumps(self.comments[document_id])),
            "revision": self.comments_revision[document_id],
        }

    def reply_to_comment(
        self,
        document_id,
        comment_id,
        *,
        incarnation,
        expected_revision,
        mutation_id,
        body,
    ):
        document = self.get_document(document_id)
        if (
            document["incarnation"] != incarnation
            or self.comments_revision[document_id] != expected_revision
        ):
            raise WhiteboardApiError("revision_conflict: comments changed")
        comment = next(
            item for item in self.comments[document_id] if item["id"] == comment_id
        )
        comment["replies"].append(
            {
                "id": mutation_id,
                "body": body,
                "author": "MCP assistant",
                "created_at": "2026-01-03T00:00:00+00:00",
            }
        )
        comment["updated_at"] = "2026-01-03T00:00:00+00:00"
        self.write_calls.append(
            {
                "operation": "reply_to_comment",
                "document_id": document_id,
                "comment_id": comment_id,
                "incarnation": incarnation,
                "expected_revision": expected_revision,
                "mutation_id": mutation_id,
                "body": body,
            }
        )
        self.comments_revision[document_id] = "d" * 32
        return {
            "comment": json.loads(json.dumps(comment)),
            "revision": self.comments_revision[document_id],
        }

    def set_comment_resolution(
        self,
        document_id,
        comment_id,
        *,
        incarnation,
        expected_revision,
        mutation_id,
        resolved,
    ):
        document = self.get_document(document_id)
        if (
            document["incarnation"] != incarnation
            or self.comments_revision[document_id] != expected_revision
        ):
            raise WhiteboardApiError("revision_conflict: comments changed")
        comment = next(
            item for item in self.comments[document_id] if item["id"] == comment_id
        )
        comment["resolved"] = resolved
        comment["updated_at"] = "2026-01-04T00:00:00+00:00"
        self.write_calls.append(
            {
                "operation": "set_comment_resolution",
                "document_id": document_id,
                "comment_id": comment_id,
                "incarnation": incarnation,
                "expected_revision": expected_revision,
                "mutation_id": mutation_id,
                "resolved": resolved,
            }
        )
        self.comments_revision[document_id] = "e" * 32
        return {
            "comment": json.loads(json.dumps(comment)),
            "revision": self.comments_revision[document_id],
        }

    def get_psyke(self, document_id, query=""):
        values = list(self.entries[document_id])
        needle = query.casefold().strip()
        return {
            "results": [
                item
                for item in values
                if not needle or needle in json.dumps(item).casefold()
            ],
            "revision": self.psyke_revision[document_id],
        }

    def create_psyke_entry(
        self,
        document_id,
        *,
        incarnation,
        expected_revision,
        mutation_id,
        entry,
    ):
        document = self.get_document(document_id)
        if (
            document["incarnation"] != incarnation
            or self.psyke_revision[document_id] != expected_revision
        ):
            raise WhiteboardApiError("revision_conflict: PSYKE changed")
        next_id = max((int(item["id"]) for item in self.entries[document_id]), default=0) + 1
        created = {
            "id": str(next_id),
            "name": entry["name"],
            "entry_type": entry["type"],
            "aliases": [],
            "description": entry.get("description", ""),
            "notes": entry.get("notes", ""),
            "created_at": None,
            "updated_at": None,
        }
        self.write_calls.append(
            {
                "operation": "create_psyke_entry",
                "document_id": document_id,
                "incarnation": incarnation,
                "expected_revision": expected_revision,
                "mutation_id": mutation_id,
                "entry": json.loads(json.dumps(entry)),
            }
        )
        self.entries[document_id].append(created)
        self.psyke_revision[document_id] = "8" * 32
        return {"element": created, "revision": self.psyke_revision[document_id]}

    def patch_psyke_entry(
        self,
        document_id,
        element_id,
        *,
        incarnation,
        expected_revision,
        mutation_id,
        patch,
    ):
        document = self.get_document(document_id)
        if (
            document["incarnation"] != incarnation
            or self.psyke_revision[document_id] != expected_revision
        ):
            raise WhiteboardApiError("revision_conflict: PSYKE changed")
        current = next(
            item for item in self.entries[document_id] if int(item["id"]) == element_id
        )
        frontend_patch = {
            ("entry_type" if key == "type" else key): value
            for key, value in patch.items()
        }
        current.update(frontend_patch)
        self.write_calls.append(
            {
                "operation": "patch_psyke_entry",
                "document_id": document_id,
                "element_id": element_id,
                "incarnation": incarnation,
                "expected_revision": expected_revision,
                "mutation_id": mutation_id,
                "patch": json.loads(json.dumps(patch)),
            }
        )
        self.psyke_revision[document_id] = "9" * 32
        return {"element": dict(current), "revision": self.psyke_revision[document_id]}

    def get_psyke_relations(self, document_id):
        return {
            "relations": json.loads(json.dumps(self.relations[document_id])),
            "revision": self.psyke_revision[document_id],
        }

    def get_psyke_progressions(self, document_id):
        return {
            "progressions": json.loads(json.dumps(self.progressions[document_id])),
            "revision": self.psyke_revision[document_id],
        }

    def create_psyke_relation(
        self,
        document_id,
        *,
        incarnation,
        expected_revision,
        mutation_id,
        relation,
    ):
        document = self.get_document(document_id)
        if (
            document["incarnation"] != incarnation
            or self.psyke_revision[document_id] != expected_revision
        ):
            raise WhiteboardApiError("revision_conflict: PSYKE changed")
        by_id = {int(entry["id"]): entry for entry in self.entries[document_id]}
        created = {
            "id": f"{relation['source_id']}:{relation['target_id']}",
            "source_id": relation["source_id"],
            "target_id": relation["target_id"],
            "source": by_id[relation["source_id"]]["name"],
            "target": by_id[relation["target_id"]]["name"],
            "relation_type": relation["relation_type"],
        }
        self.relations[document_id].append(created)
        self.write_calls.append(
            {
                "operation": "create_psyke_relation",
                "document_id": document_id,
                "incarnation": incarnation,
                "expected_revision": expected_revision,
                "mutation_id": mutation_id,
                "relation": json.loads(json.dumps(relation)),
            }
        )
        self.psyke_revision[document_id] = "a" * 32
        return {"relation": dict(created), "revision": self.psyke_revision[document_id]}

    def create_psyke_progression(
        self,
        document_id,
        *,
        incarnation,
        expected_revision,
        mutation_id,
        progression,
    ):
        document = self.get_document(document_id)
        if (
            document["incarnation"] != incarnation
            or self.psyke_revision[document_id] != expected_revision
        ):
            raise WhiteboardApiError("revision_conflict: PSYKE changed")
        next_id = max(
            (item["id"] for item in self.progressions[document_id]), default=0
        ) + 1
        owner_count = sum(
            item["entry_id"] == progression["entry_id"]
            for item in self.progressions[document_id]
        )
        created = {
            "id": next_id,
            "entry_id": progression["entry_id"],
            "text": progression["text"],
            "scene_id": progression["scene_id"],
            "scene_title": "",
            "sort_order": owner_count + 1,
        }
        self.progressions[document_id].append(created)
        self.write_calls.append(
            {
                "operation": "create_psyke_progression",
                "document_id": document_id,
                "incarnation": incarnation,
                "expected_revision": expected_revision,
                "mutation_id": mutation_id,
                "progression": json.loads(json.dumps(progression)),
            }
        )
        self.psyke_revision[document_id] = "b" * 32
        return {
            "progression": dict(created),
            "revision": self.psyke_revision[document_id],
        }

    def patch_psyke_progression(
        self,
        document_id,
        progression_id,
        *,
        incarnation,
        expected_revision,
        mutation_id,
        patch,
    ):
        document = self.get_document(document_id)
        if (
            document["incarnation"] != incarnation
            or self.psyke_revision[document_id] != expected_revision
        ):
            raise WhiteboardApiError("revision_conflict: PSYKE changed")
        current = next(
            item
            for item in self.progressions[document_id]
            if item["id"] == progression_id
        )
        current.update(patch)
        if patch["scene_id"] is None:
            current["scene_title"] = ""
        self.write_calls.append(
            {
                "operation": "patch_psyke_progression",
                "document_id": document_id,
                "progression_id": progression_id,
                "incarnation": incarnation,
                "expected_revision": expected_revision,
                "mutation_id": mutation_id,
                "patch": json.loads(json.dumps(patch)),
            }
        )
        self.psyke_revision[document_id] = "c" * 32
        return {
            "progression": dict(current),
            "revision": self.psyke_revision[document_id],
        }

    def update_document(
        self,
        document_id,
        *,
        incarnation,
        expected_revision,
        mutation_id,
        patch,
    ):
        current = self.get_document(document_id)
        if current["incarnation"] != incarnation or current["revision"] != expected_revision:
            raise WhiteboardApiError("revision_conflict: manuscript changed")
        self.write_calls.append(
            {
                "operation": "patch_manuscript",
                "document_id": document_id,
                "incarnation": incarnation,
                "expected_revision": expected_revision,
                "mutation_id": mutation_id,
                "patch": json.loads(json.dumps(patch)),
            }
        )
        document = next(item for item in self.documents if int(item["id"]) == document_id)
        for key in ("title", "mode"):
            if key in patch:
                document[key] = patch[key]
        if "blocks" in patch:
            self.blocks[document_id] = list(patch["blocks"])
        if "settings" in patch:
            self.settings[document_id] = dict(patch["settings"])
        document["revision"] = "5" * 32
        document["updated_at"] = "2026-01-03T00:00:00Z"
        return self.get_document(document_id)

    def replace_outline(
        self,
        document_id,
        *,
        incarnation,
        expected_revision,
        mutation_id,
        items,
    ):
        document = self.get_document(document_id)
        if (
            document["incarnation"] != incarnation
            or self.outline_revision[document_id] != expected_revision
        ):
            raise WhiteboardApiError("revision_conflict: outline changed")
        self.write_calls.append(
            {
                "operation": "replace_outline",
                "document_id": document_id,
                "incarnation": incarnation,
                "expected_revision": expected_revision,
                "mutation_id": mutation_id,
                "items": json.loads(json.dumps(items)),
            }
        )
        self.outline[document_id] = list(items)
        self.outline_revision[document_id] = "6" * 32
        return self.get_outline(document_id)


def _gateway(*, allow_writes: bool = False) -> WhiteboardMcpGateway:
    return WhiteboardMcpGateway(  # type: ignore[arg-type]
        FakeClient(),
        allow_writes=allow_writes,
    )


def _wire_bytes(value: object) -> int:
    return len(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    )


def _api_psyke_element(**updates) -> dict:
    element = {
        "id": "12",
        "name": "Mara",
        "entry_type": "character",
        "aliases": ["The Keeper"],
        "description": "Keeper of the lantern",
        "notes": "",
        "created_at": None,
        "updated_at": None,
    }
    element.update(updates)
    return element


def _api_psyke_relation(**updates) -> dict:
    relation = {
        "id": "10:11",
        "source_id": 10,
        "target_id": 11,
        "source": "Mara",
        "target": "North House",
        "relation_type": "haunts",
    }
    relation.update(updates)
    return relation


def _api_psyke_progression(**updates) -> dict:
    progression = {
        "id": 21,
        "entry_id": 10,
        "text": "Mara still guards the lantern.",
        "scene_id": None,
        "scene_title": "",
        "sort_order": 1,
    }
    progression.update(updates)
    return progression


def _outline_node(
    item_id: str,
    title: str,
    *,
    parent_id: str | None = None,
    order: int | float = 0,
    node_type: str = "scene",
    summary: str = "",
    **updates,
) -> dict[str, object]:
    node: dict[str, object] = {
        "id": item_id,
        "parentId": parent_id,
        "type": node_type,
        "title": title,
        "summary": summary,
        "order": order,
        "collapsed": False,
        "completed": False,
        "status": "none",
        "tags": [],
        "colorLabel": "none",
        "linkedLineId": None,
        "link": None,
        "createdAt": "2026-09-25T10:00:00Z",
        "updatedAt": "2026-09-25T10:00:00Z",
    }
    node.update(updates)
    return node


def test_registry_is_separate_focused_and_has_one_apply_boundary() -> None:
    names = [spec.name for spec in TOOL_SPECS]
    assert len(names) == len(set(names)) == 24
    assert set(names) == set(HANDLERS)
    assert all(name.startswith(TOOL_PREFIX) for name in names)
    assert all(not any(word in name for word in ("write", "create", "update", "delete")) for name in names)
    apply = HANDLERS["logosforge_whiteboard_apply_proposal"]
    assert apply.read_only is False
    assert apply.destructive is True
    assert apply.idempotent is False
    assert HANDLERS["logosforge_whiteboard_discard_proposal"].read_only is False
    assert HANDLERS["logosforge_whiteboard_propose_manuscript_patch"].idempotent is False
    assert HANDLERS["logosforge_whiteboard_propose_outline_replace"].idempotent is False
    assert HANDLERS["logosforge_whiteboard_propose_comment_reply"].idempotent is False
    assert HANDLERS["logosforge_whiteboard_propose_comment_resolution"].idempotent is False
    assert HANDLERS["logosforge_whiteboard_propose_psyke_entry"].idempotent is False
    assert HANDLERS["logosforge_whiteboard_propose_psyke_patch"].idempotent is False
    assert HANDLERS["logosforge_whiteboard_propose_psyke_relation"].idempotent is False
    assert HANDLERS["logosforge_whiteboard_propose_psyke_progression"].idempotent is False
    assert HANDLERS["logosforge_whiteboard_propose_psyke_progression_patch"].idempotent is False
    assert all(
        spec.read_only is True
        for spec in TOOL_SPECS
        if spec.name not in {
            "logosforge_whiteboard_apply_proposal",
            "logosforge_whiteboard_discard_proposal",
        }
    )
    assert SERVER_NAME == "logosforge-whiteboard"
    assert SERVER_VERSION == "1.4.0"


def test_document_selection_is_process_local_and_reads_native_summary() -> None:
    gateway = _gateway()
    unresolved = call_tool(gateway, "logosforge_whiteboard_get_current_document", {})
    assert unresolved["ok"] is False
    selected = call_tool(
        gateway,
        "logosforge_whiteboard_select_document",
        {"document_id": 1},
    )
    assert selected == {
        "ok": True,
        "result": {"selected_document_id": 1, "document": gateway.client.documents[0]},  # type: ignore[attr-defined]
    }
    current = call_tool(gateway, "logosforge_whiteboard_get_current_document", {})
    assert current["result"]["document"]["incarnation"] == "a" * 32


def test_document_list_and_manuscript_snapshot_are_bounded() -> None:
    gateway = _gateway()
    listed = call_tool(
        gateway,
        "logosforge_whiteboard_list_documents",
        {"offset": 1, "limit": 1},
    )["result"]
    assert [item["id"] for item in listed["documents"]] == ["2"]
    assert listed["page"] | {
        "offset": 1,
        "limit": 1,
        "returned": 1,
        "total": 2,
        "next_offset": None,
    } == listed["page"]
    assert listed["page"]["byte_limited"] is False

    snapshot = call_tool(
        gateway,
        "logosforge_whiteboard_get_document_snapshot",
        {"document_id": 1, "offset": 1, "limit": 1, "max_characters": 1_000},
    )["result"]
    assert [item["id"] for item in snapshot["document"]["blocks"]] == ["b2"]
    assert snapshot["document"]["revision"] == "3" * 32
    assert snapshot["page"]["total"] == 3
    assert snapshot["page"]["next_offset"] == 2


def test_outline_carries_revision_without_changing_items_or_pagination() -> None:
    outline = call_tool(
        _gateway(),
        "logosforge_whiteboard_get_outline",
        {"document_id": 1, "offset": 0, "limit": 1},
    )["result"]
    assert outline["document_id"] == 1
    assert outline["revision"] == "1" * 32
    assert outline["items"] == [{"id": "o1", "title": "Mara arrives"}]
    assert outline["page"]["total"] == 1


def test_large_page_items_are_clipped_with_progress_safe_pagination() -> None:
    cases = [
        (
            "logosforge_whiteboard_get_outline",
            "outline",
            "items",
            {"id": "outline-huge", "title": "Huge outline", "summary": "O" * (MAX_RESULT_BYTES * 2)},
            {"id": "outline-next", "title": "Next outline"},
        ),
        (
            "logosforge_whiteboard_get_comments",
            "comments",
            "comments",
            {"id": "comment-huge", "body": "C" * (MAX_RESULT_BYTES * 2), "resolved": False, "replies": []},
            {"id": "comment-next", "body": "Next comment", "resolved": False, "replies": []},
        ),
        (
            "logosforge_whiteboard_get_psyke",
            "entries",
            "entries",
            {"id": "psyke-huge", "name": "Huge entry", "entry_type": "character", "description": "P" * (MAX_RESULT_BYTES * 2)},
            {"id": "psyke-next", "name": "Next entry", "entry_type": "character", "description": "Small"},
        ),
    ]
    for tool_name, source_name, result_name, huge, following in cases:
        client = FakeClient()
        getattr(client, source_name)[1] = [huge, following]
        gateway = WhiteboardMcpGateway(client)  # type: ignore[arg-type]
        first = call_tool(
            gateway,
            tool_name,
            {"document_id": 1, "offset": 0, "limit": 2},
        )
        assert _wire_bytes(first) <= MAX_RESULT_BYTES
        page = first["result"]["page"]
        assert page["byte_limited"] is True
        assert page["truncated_item_offsets"] == [0]
        assert page["truncated_value_count"] >= 1
        assert page["next_offset"] == 1
        assert first["result"][result_name][0]["id"] == huge["id"]

        resumed = call_tool(
            gateway,
            tool_name,
            {"document_id": 1, "offset": page["next_offset"], "limit": 2},
        )
        assert _wire_bytes(resumed) <= MAX_RESULT_BYTES
        assert resumed["result"][result_name][0]["id"] == following["id"]


def test_snapshot_bounds_metadata_marks_and_other_nested_strings() -> None:
    client = FakeClient()
    client.settings[1] = {
        "editor": {"theme": "S" * (MAX_RESULT_BYTES * 2)},
    }
    client.blocks[1] = [
        {
            "id": "marks-huge",
            "type": "paragraph",
            "text": "short text",
            "marks": [{"attrs": {"comment": "M" * (MAX_RESULT_BYTES * 2)}}],
        },
        {
            "id": "other-huge",
            "type": "paragraph",
            "text": "another short text",
            "other": {"custom": "X" * (MAX_RESULT_BYTES * 2)},
        },
    ]
    gateway = WhiteboardMcpGateway(client)  # type: ignore[arg-type]

    first = call_tool(
        gateway,
        "logosforge_whiteboard_get_document_snapshot",
        {"document_id": 1, "offset": 0, "limit": 2, "max_characters": 1_000},
    )
    assert _wire_bytes(first) <= MAX_RESULT_BYTES
    first_page = first["result"]["page"]
    assert first_page["metadata_byte_limited"] is True
    assert first_page["metadata_truncated_value_count"] >= 1
    assert first_page["byte_limited"] is True
    assert first_page["truncated_item_offsets"] == [0]
    assert first_page["next_offset"] == 1
    assert first["result"]["document"]["blocks"][0]["id"] == "marks-huge"
    assert first["result"]["document"]["revision"] == "3" * 32

    resumed = call_tool(
        gateway,
        "logosforge_whiteboard_get_document_snapshot",
        {"document_id": 1, "offset": 1, "limit": 1, "max_characters": 1_000},
    )
    assert _wire_bytes(resumed) <= MAX_RESULT_BYTES
    assert resumed["result"]["document"]["blocks"][0]["id"] == "other-huge"
    assert resumed["result"]["document"]["revision"] == "3" * 32
    assert resumed["result"]["page"]["truncated_item_offsets"] == [1]


def test_snapshot_preserves_revision_when_a_huge_title_exhausts_metadata() -> None:
    client = FakeClient()
    client.documents[0]["title"] = "T" * (MAX_RESULT_BYTES * 2)
    snapshot = call_tool(
        WhiteboardMcpGateway(client),  # type: ignore[arg-type]
        "logosforge_whiteboard_get_document_snapshot",
        {"document_id": 1, "offset": 0, "limit": 1, "max_characters": 1_000},
    )["result"]
    assert snapshot["document"]["revision"] == "3" * 32
    assert snapshot["page"]["metadata_byte_limited"] is True


def test_common_result_guard_bounds_unpaged_document_summary() -> None:
    client = FakeClient()
    client.documents[0]["title"] = "T" * (MAX_RESULT_BYTES * 2)
    response = call_tool(
        WhiteboardMcpGateway(client),  # type: ignore[arg-type]
        "logosforge_whiteboard_select_document",
        {"document_id": 1},
    )
    assert _wire_bytes(response) <= MAX_RESULT_BYTES
    assert response["result"]["_mcp_output"]["byte_limited"] is True
    assert response["result"]["_mcp_output"]["truncated_value_count"] >= 1


def test_search_directly_caps_large_user_authored_titles_and_ids() -> None:
    client = FakeClient()
    client.outline[1] = [
        {
            "id": "I" * (MAX_RESULT_BYTES * 2),
            "title": "needle " + "T" * (MAX_RESULT_BYTES * 2),
        }
    ]
    response = call_tool(
        WhiteboardMcpGateway(client),  # type: ignore[arg-type]
        "logosforge_whiteboard_search",
        {"document_id": 1, "query": "needle", "scope": "outline", "limit": 1},
    )
    assert _wire_bytes(response) <= MAX_RESULT_BYTES
    match = response["result"]["matches"][0]
    assert match["scope"] == "outline"
    assert len(match["id"]) == MAX_SEARCH_ID
    assert len(match["title"]) == MAX_SEARCH_TITLE
    assert match["id"].endswith("…")
    assert match["title"].endswith("…")
    assert len(match["snippet"]) <= 242


def test_comment_psyke_filters_and_search_output_bounds() -> None:
    gateway = _gateway()
    comments = call_tool(
        gateway,
        "logosforge_whiteboard_get_comments",
        {"document_id": 1, "include_resolved": False},
    )["result"]
    assert [item["id"] for item in comments["comments"]] == ["c1"]
    assert comments["revision"] == "c" * 32

    psyke = call_tool(
        gateway,
        "logosforge_whiteboard_get_psyke",
        {"document_id": 1, "entry_type": "character"},
    )["result"]
    assert [item["name"] for item in psyke["entries"]] == ["Mara"]
    assert psyke["revision"] == "7" * 32

    search = call_tool(
        gateway,
        "logosforge_whiteboard_search",
        {"document_id": 1, "query": "Mara", "limit": 2},
    )["result"]
    assert search["total_matches"] >= 3
    assert len(search["matches"]) == 2
    assert search["truncated"] is True
    assert all(len(item["snippet"]) <= 242 for item in search["matches"])


def test_psyke_relation_and_progression_reads_are_filtered_bounded_and_revisioned() -> None:
    gateway = _gateway()
    relation = call_tool(
        gateway,
        "logosforge_whiteboard_get_psyke_relations",
        {"document_id": 1, "entry_id": 11, "offset": 0, "limit": 1},
    )["result"]
    assert relation["revision"] == "7" * 32
    assert relation["entry_id"] == 11
    assert relation["relations"] == gateway.client.relations[1]  # type: ignore[attr-defined]
    assert relation["page"]["returned"] == 1

    no_relations = call_tool(
        gateway,
        "logosforge_whiteboard_get_psyke_relations",
        {"document_id": 1, "entry_id": 999},
    )["result"]
    assert no_relations["relations"] == []
    assert no_relations["revision"] == relation["revision"]

    progression = call_tool(
        gateway,
        "logosforge_whiteboard_get_psyke_progressions",
        {"document_id": 1, "entry_id": 10},
    )["result"]
    assert progression["revision"] == "7" * 32
    assert progression["entry_id"] == 10
    assert progression["progressions"] == gateway.client.progressions[1]  # type: ignore[attr-defined]
    assert progression["page"]["returned"] == 1


def test_tool_validation_rejects_extra_wrong_and_overlarge_arguments() -> None:
    gateway = _gateway()
    assert call_tool(
        gateway, "logosforge_whiteboard_get_capabilities", {"write": True}
    )["ok"] is False
    assert call_tool(
        gateway, "logosforge_whiteboard_get_outline", {"limit": 501}
    )["ok"] is False
    assert call_tool(
        gateway, "logosforge_whiteboard_search", {"query": ""}
    )["ok"] is False
    assert call_tool(gateway, "not_a_tool", {})["ok"] is False


def test_capabilities_report_write_gate_and_proposal_limits() -> None:
    disabled = call_tool(
        _gateway(), "logosforge_whiteboard_get_capabilities", {}
    )["result"]
    assert disabled["read_only"] is True
    assert disabled["writes_available"] is False
    assert disabled["write_mode"] == "reviewed_revision_bound_proposals"
    assert disabled["limits"]["maximum_proposal_request_bytes"] == MAX_REQUEST_BYTES
    assert disabled["limits"]["maximum_proposal_review_bytes"] == 48 * 1024
    assert disabled["limits"]["maximum_outline_depth"] == 512

    enabled = call_tool(
        _gateway(allow_writes=True),
        "logosforge_whiteboard_get_capabilities",
        {},
    )["result"]
    assert enabled["read_only"] is False
    assert enabled["writes_available"] is True


def test_manuscript_proposal_is_immutable_reviewable_and_gate_protected() -> None:
    gateway = _gateway()
    patch = {"title": "A revised title"}
    proposed = call_tool(
        gateway,
        "logosforge_whiteboard_propose_manuscript_patch",
        {
            "document_id": 1,
            "expected_revision": "3" * 32,
            "patch": patch,
        },
    )
    assert proposed["ok"] is True
    proposal = proposed["result"]
    assert proposal["state"] == "pending"
    assert proposal["request"]["method"] == "PUT"
    assert proposal["request"]["path"] == "/api/whiteboard?doc=1"
    assert proposal["request"]["body"] == {"title": "A revised title"}
    assert proposal["request"]["if_match"] == (
        f'"lfwb:whiteboard:{"a" * 32}:{"3" * 32}"'
    )
    assert proposal["request"]["document_incarnation"] == "a" * 32
    assert proposal["review"]["changed_fields"] == ["title"]
    assert proposal["review"]["before"]["blocks"]["count"] == 3

    patch["title"] = "caller mutation"
    reread = call_tool(
        gateway,
        "logosforge_whiteboard_get_proposal",
        {"proposal_id": proposal["proposal_id"]},
    )["result"]
    assert reread["request"]["body"] == {"title": "A revised title"}
    assert reread["request"]["body_page"]["complete"] is True
    assert json.loads(reread["request"]["body_page"]["content"]) == {
        "title": "A revised title"
    }

    denied = call_tool(
        gateway,
        "logosforge_whiteboard_apply_proposal",
        {"proposal_id": proposal["proposal_id"]},
    )
    assert denied["ok"] is False
    assert "LOGOSFORGE_WHITEBOARD_MCP_ALLOW_WRITES=1" in denied["error"]
    assert gateway.client.write_calls == []  # type: ignore[attr-defined]
    assert call_tool(
        gateway,
        "logosforge_whiteboard_discard_proposal",
        {"proposal_id": proposal["proposal_id"]},
    )["result"]["state"] == "discarded"


def test_manuscript_proposal_applies_once_with_exact_precondition() -> None:
    gateway = _gateway(allow_writes=True)
    gateway.select_document(1)
    blocks = [
        {"id": "new-1", "type": "paragraph", "text": "Revised opening."},
        {"id": "new-2", "type": "paragraph", "text": "Second paragraph."},
    ]
    proposal = call_tool(
        gateway,
        "logosforge_whiteboard_propose_manuscript_patch",
        {
            "expected_revision": "3" * 32,
            "patch": {"blocks": blocks},
        },
    )["result"]
    assert proposal["request"]["body"]["blocks"]["count"] == 2
    assert "Revised opening." not in json.dumps(proposal["request"]["body"])
    assert "Revised opening." in json.dumps(proposal["review"])
    assert proposal["review"]["block_changes"]["change_count"] == 5
    assert proposal["review"]["block_changes"]["preview_truncated"] is False

    applied = call_tool(
        gateway,
        "logosforge_whiteboard_apply_proposal",
        {"proposal_id": proposal["proposal_id"]},
    )
    assert applied["ok"] is True
    assert applied["result"]["state"] == "applied"
    assert applied["result"]["result"] == {
        "resource": "manuscript",
        "document_id": 1,
        "revision": "5" * 32,
        "incarnation": "a" * 32,
        "title": "Alpha",
        "mode": "prose",
        "block_count": 2,
        "updated_at": "2026-01-03T00:00:00Z",
    }
    write = gateway.client.write_calls[0]  # type: ignore[attr-defined]
    assert write["incarnation"] == "a" * 32
    assert write["expected_revision"] == "3" * 32
    assert write["mutation_id"] == proposal["proposal_id"]
    assert write["patch"] == {"blocks": blocks}
    repeated = call_tool(
        gateway,
        "logosforge_whiteboard_apply_proposal",
        {"proposal_id": proposal["proposal_id"]},
    )
    assert repeated["ok"] is False
    assert "not pending" in repeated["error"]
    assert len(gateway.client.write_calls) == 1  # type: ignore[attr-defined]


def test_manuscript_proposal_content_review_is_useful_and_bounded() -> None:
    gateway = _gateway()
    opening = "Dramatic revised opening. " + ("detail " * 80_000)
    response = call_tool(
        gateway,
        "logosforge_whiteboard_propose_manuscript_patch",
        {
            "document_id": 1,
            "expected_revision": "3" * 32,
            "patch": {
                "blocks": [
                    {"id": "b1", "type": "paragraph", "text": opening}
                ]
            },
        },
    )
    assert response["ok"] is True
    assert _wire_bytes(response) <= MAX_RESULT_BYTES
    changes = response["result"]["review"]["block_changes"]
    assert changes["preview_truncated"] is True
    assert "Dramatic revised opening." in json.dumps(changes["preview"])
    modified = next(item for item in changes["preview"] if item["id"] == "b1")
    assert modified["change"] == "modified"
    assert modified["before"]["text"] == "A lantern burns beside Mara."
    assert modified["after"]["text"].startswith("Dramatic revised opening.")
    assert modified["after_truncated"] is True


def test_large_proposal_review_samples_tail_and_pages_every_request_byte() -> None:
    gateway = _gateway()
    blocks = [
        {
            "id": f"generated-{index:04d}",
            "type": "paragraph",
            "text": (
                "FINAL SENTINEL PROSE"
                if index == 1_999
                else f"Generated paragraph {index}."
            ),
        }
        for index in range(2_000)
    ]
    created = call_tool(
        gateway,
        "logosforge_whiteboard_propose_manuscript_patch",
        {
            "document_id": 1,
            "expected_revision": "3" * 32,
            "patch": {"blocks": blocks},
        },
    )["result"]
    review = created["review"]["block_changes"]
    assert review["preview_sampled"] is True
    assert review["omitted_change_count"] > 0
    assert "FINAL SENTINEL PROSE" in json.dumps(review["preview"])

    chunks: list[str] = []
    offset = 0
    while True:
        proposal = call_tool(
            gateway,
            "logosforge_whiteboard_get_proposal",
            {
                "proposal_id": created["proposal_id"],
                "request_body_offset": offset,
                "request_body_max_bytes": 32 * 1024,
            },
        )["result"]
        page = proposal["request"]["body_page"]
        assert page["offset"] == offset
        assert page["returned_bytes"] <= 32 * 1024
        assert page["sha256"] == proposal["request"]["body_sha256"]
        chunks.append(page["content"])
        if page["next_offset"] is None:
            assert page["complete"] is True
            break
        offset = page["next_offset"]

    canonical = json.dumps(
        {"blocks": blocks},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    assert "".join(chunks) == canonical
    assert "FINAL SENTINEL PROSE" in canonical


def test_proposal_body_paging_never_splits_utf8_code_points() -> None:
    gateway = _gateway()
    blocks = [
        {"id": "unicode", "type": "paragraph", "text": "😀" * 1_000},
    ]
    created = call_tool(
        gateway,
        "logosforge_whiteboard_propose_manuscript_patch",
        {
            "document_id": 1,
            "expected_revision": "3" * 32,
            "patch": {"blocks": blocks},
        },
    )["result"]
    chunks: list[str] = []
    offset = 0
    while True:
        proposal = call_tool(
            gateway,
            "logosforge_whiteboard_get_proposal",
            {
                "proposal_id": created["proposal_id"],
                "request_body_offset": offset,
                "request_body_max_bytes": 1_024,
            },
        )["result"]
        page = proposal["request"]["body_page"]
        chunks.append(page["content"])
        if page["next_offset"] is None:
            break
        assert page["next_offset"] > offset
        offset = page["next_offset"]
    reconstructed = "".join(chunks)
    assert json.loads(reconstructed) == {"blocks": blocks}
    assert reconstructed.encode("utf-8") == json.dumps(
        {"blocks": blocks},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def test_stale_manuscript_proposal_fails_closed_without_retry() -> None:
    gateway = _gateway(allow_writes=True)
    proposal = call_tool(
        gateway,
        "logosforge_whiteboard_propose_manuscript_patch",
        {
            "document_id": 1,
            "expected_revision": "3" * 32,
            "patch": {"title": "Proposed"},
        },
    )["result"]
    gateway.client.documents[0]["revision"] = "9" * 32  # type: ignore[attr-defined]
    failed = call_tool(
        gateway,
        "logosforge_whiteboard_apply_proposal",
        {"proposal_id": proposal["proposal_id"]},
    )
    assert failed["ok"] is False
    assert "will not be retried" in failed["error"]
    assert "revision_conflict" in failed["error"]
    assert gateway.client.write_calls == []  # type: ignore[attr-defined]
    listed = call_tool(
        gateway,
        "logosforge_whiteboard_list_proposals",
        {"include_finished": True},
    )["result"]["proposals"]
    assert listed[0]["state"] == "failed"


def test_outline_replacement_proposal_is_revision_bound_and_single_use() -> None:
    gateway = _gateway(allow_writes=True)
    items = [
        _outline_node("o2", "New act", node_type="act", summary="The story begins."),
        _outline_node(
            "o3",
            "Opening",
            parent_id="o2",
            summary="Mara enters the rain-dark house.",
        ),
    ]
    proposal = call_tool(
        gateway,
        "logosforge_whiteboard_propose_outline_replace",
        {
            "document_id": 1,
            "expected_revision": "1" * 32,
            "items": items,
        },
    )["result"]
    assert proposal["review"]["before"]["count"] == 1
    assert proposal["review"]["after"]["count"] == 2
    assert proposal["review"]["added_ids"] == ["o2", "o3"]
    assert proposal["review"]["removed_ids"] == ["o1"]
    assert "Mara enters the rain-dark house." in json.dumps(proposal["review"])
    assert proposal["review"]["item_changes"]["change_count"] == 3
    applied = call_tool(
        gateway,
        "logosforge_whiteboard_apply_proposal",
        {"proposal_id": proposal["proposal_id"]},
    )["result"]
    assert applied["result"] == {
        "resource": "outline",
        "document_id": 1,
        "revision": "6" * 32,
        "item_count": 2,
    }
    assert gateway.client.write_calls[0]["items"] == items  # type: ignore[attr-defined]


def test_comment_reply_and_resolution_proposals_are_revision_bound_and_single_use() -> None:
    gateway = _gateway(allow_writes=True)
    gateway.select_document(1)
    reply_proposal = call_tool(
        gateway,
        "logosforge_whiteboard_propose_comment_reply",
        {
            "comment_id": "c1",
            "expected_revision": "c" * 32,
            "body": "I strengthened the lantern motif in the revision.",
        },
    )["result"]
    assert reply_proposal["operation"] == "reply_to_comment"
    assert reply_proposal["request"]["method"] == "POST"
    assert reply_proposal["request"]["path"] == "/api/comments/c1/replies?doc=1"
    assert reply_proposal["request"]["if_match"] == (
        f'"lfwb:comments:{"a" * 32}:{"c" * 32}"'
    )
    assert json.loads(reply_proposal["request"]["body_page"]["content"]) == {
        "body": "I strengthened the lantern motif in the revision."
    }
    assert reply_proposal["review"]["author"] == "MCP assistant"
    assert reply_proposal["review"]["comment"]["quote"]["preview"] == "lantern"
    assert reply_proposal["review"]["reply"]["sha256"] == hashlib.sha256(
        b"I strengthened the lantern motif in the revision."
    ).hexdigest()

    replied = call_tool(
        gateway,
        "logosforge_whiteboard_apply_proposal",
        {"proposal_id": reply_proposal["proposal_id"]},
    )["result"]
    assert replied["result"] == {
        "resource": "comments",
        "operation": "reply",
        "document_id": 1,
        "revision": "d" * 32,
        "comment_id": "c1",
        "reply_id": reply_proposal["proposal_id"],
        "reply_count": 1,
        "resolved": False,
        "updated_at": "2026-01-03T00:00:00+00:00",
    }
    write = gateway.client.write_calls[0]  # type: ignore[attr-defined]
    assert write == {
        "operation": "reply_to_comment",
        "document_id": 1,
        "comment_id": "c1",
        "incarnation": "a" * 32,
        "expected_revision": "c" * 32,
        "mutation_id": reply_proposal["proposal_id"],
        "body": "I strengthened the lantern motif in the revision.",
    }

    resolution_proposal = call_tool(
        gateway,
        "logosforge_whiteboard_propose_comment_resolution",
        {
            "comment_id": "c1",
            "expected_revision": "d" * 32,
            "resolved": True,
        },
    )["result"]
    assert resolution_proposal["operation"] == "set_comment_resolution"
    assert resolution_proposal["request"]["method"] == "PUT"
    assert json.loads(resolution_proposal["request"]["body_page"]["content"]) == {
        "resolved": True
    }
    assert resolution_proposal["review"]["before_resolved"] is False
    assert resolution_proposal["review"]["after_resolved"] is True
    resolved = call_tool(
        gateway,
        "logosforge_whiteboard_apply_proposal",
        {"proposal_id": resolution_proposal["proposal_id"]},
    )["result"]
    assert resolved["result"] == {
        "resource": "comments",
        "operation": "resolve",
        "document_id": 1,
        "revision": "e" * 32,
        "comment_id": "c1",
        "resolved": True,
        "reply_count": 1,
        "updated_at": "2026-01-04T00:00:00+00:00",
    }

    repeated = call_tool(
        gateway,
        "logosforge_whiteboard_apply_proposal",
        {"proposal_id": resolution_proposal["proposal_id"]},
    )
    assert repeated["ok"] is False
    assert "not pending" in repeated["error"]
    assert len(gateway.client.write_calls) == 2  # type: ignore[attr-defined]


def test_comment_proposals_reject_stale_missing_noop_mentions_and_invalid_text() -> None:
    gateway = _gateway()
    gateway.select_document(1)
    cases = [
        (
            "logosforge_whiteboard_propose_comment_reply",
            {"comment_id": "c1", "expected_revision": "f" * 32, "body": "Done."},
            "does not match",
        ),
        (
            "logosforge_whiteboard_propose_comment_reply",
            {"comment_id": "missing", "expected_revision": "c" * 32, "body": "Done."},
            "does not exist",
        ),
        (
            "logosforge_whiteboard_propose_comment_reply",
            {"comment_id": "c1", "expected_revision": "c" * 32, "body": " padded "},
            "trimmed",
        ),
        (
            "logosforge_whiteboard_propose_comment_reply",
            {"comment_id": "c1", "expected_revision": "c" * 32, "body": "Ask @BiLlY now"},
            "separate AI request",
        ),
        (
            "logosforge_whiteboard_propose_comment_reply",
            {
                "comment_id": "c1",
                "expected_revision": "c" * 32,
                "body": "x" * (MAX_COMMENT_BODY_CHARACTERS + 1),
            },
            "too long",
        ),
        (
            "logosforge_whiteboard_propose_comment_resolution",
            {"comment_id": "c1", "expected_revision": "c" * 32, "resolved": False},
            "already open",
        ),
        (
            "logosforge_whiteboard_propose_comment_resolution",
            {"comment_id": "bad/id", "expected_revision": "c" * 32, "resolved": True},
            "comment_id",
        ),
    ]
    for tool, arguments, expected_error in cases:
        response = call_tool(gateway, tool, arguments)
        assert response["ok"] is False
        assert expected_error in response["error"]
    assert gateway.client.write_calls == []  # type: ignore[attr-defined]


def test_stale_comment_proposal_fails_closed_without_write() -> None:
    gateway = _gateway(allow_writes=True)
    proposal = call_tool(
        gateway,
        "logosforge_whiteboard_propose_comment_reply",
        {
            "document_id": 1,
            "comment_id": "c1",
            "expected_revision": "c" * 32,
            "body": "Handled in the revised passage.",
        },
    )["result"]
    gateway.client.comments_revision[1] = "f" * 32  # type: ignore[attr-defined]
    failed = call_tool(
        gateway,
        "logosforge_whiteboard_apply_proposal",
        {"proposal_id": proposal["proposal_id"]},
    )
    assert failed["ok"] is False
    assert "will not be retried" in failed["error"]
    assert "revision_conflict" in failed["error"]
    assert gateway.client.write_calls == []  # type: ignore[attr-defined]


def test_large_comment_reply_review_is_bounded_and_exact_body_is_pageable() -> None:
    gateway = _gateway()
    body = "A" * MAX_COMMENT_BODY_CHARACTERS
    created = call_tool(
        gateway,
        "logosforge_whiteboard_propose_comment_reply",
        {
            "document_id": 1,
            "comment_id": "c1",
            "expected_revision": "c" * 32,
            "body": body,
        },
    )
    assert created["ok"] is True
    assert _wire_bytes(created) <= MAX_RESULT_BYTES
    proposal = created["result"]
    review = proposal["review"]["reply"]
    assert review["characters"] == MAX_COMMENT_BODY_CHARACTERS
    assert review["truncated"] is True
    assert review["sha256"] == hashlib.sha256(body.encode()).hexdigest()

    chunks: list[str] = []
    offset = 0
    while True:
        inspected = call_tool(
            gateway,
            "logosforge_whiteboard_get_proposal",
            {
                "proposal_id": proposal["proposal_id"],
                "request_body_offset": offset,
                "request_body_max_bytes": 8 * 1024,
            },
        )["result"]
        page = inspected["request"]["body_page"]
        chunks.append(page["content"])
        if page["next_offset"] is None:
            break
        offset = page["next_offset"]
    assert json.loads("".join(chunks)) == {"body": body}


def test_psyke_create_and_patch_proposals_are_revision_bound_and_single_use() -> None:
    gateway = _gateway(allow_writes=True)
    gateway.select_document(1)
    created_proposal = call_tool(
        gateway,
        "logosforge_whiteboard_propose_psyke_entry",
        {
            "expected_revision": "7" * 32,
            "entry": {
                "name": "The Ferryman",
                "entry_type": "character",
                "description": "Carries secrets across the flooded city.",
                "notes": "Keep the true name hidden.",
            },
        },
    )["result"]
    assert created_proposal["request"]["method"] == "POST"
    assert created_proposal["request"]["if_match"] == (
        f'"lfwb:psyke:{"a" * 32}:{"7" * 32}"'
    )
    assert created_proposal["review"]["change"] == "create"
    assert created_proposal["review"]["after"]["name"] == "The Ferryman"
    assert json.loads(created_proposal["request"]["body_page"]["content"]) == {
        "description": "Carries secrets across the flooded city.",
        "name": "The Ferryman",
        "notes": "Keep the true name hidden.",
        "type": "character",
    }

    created = call_tool(
        gateway,
        "logosforge_whiteboard_apply_proposal",
        {"proposal_id": created_proposal["proposal_id"]},
    )["result"]
    assert created["result"]["resource"] == "psyke"
    assert created["result"]["operation"] == "create"
    assert created["result"]["revision"] == "8" * 32
    element = created["result"]["element"]
    assert element["name"] == "The Ferryman"
    entry_id = int(element["id"])

    patch_proposal = call_tool(
        gateway,
        "logosforge_whiteboard_propose_psyke_patch",
        {
            "entry_id": entry_id,
            "expected_revision": "8" * 32,
            "patch": {
                "entry_type": "lore",
                "description": "A title inherited by the keeper of crossings.",
            },
        },
    )["result"]
    assert patch_proposal["request"]["method"] == "PATCH"
    assert patch_proposal["review"]["change"] == "patch"
    assert patch_proposal["review"]["before"]["entry_type"] == "character"
    assert patch_proposal["review"]["after"]["entry_type"] == "lore"
    patched = call_tool(
        gateway,
        "logosforge_whiteboard_apply_proposal",
        {"proposal_id": patch_proposal["proposal_id"]},
    )["result"]
    assert patched["result"]["operation"] == "patch"
    assert patched["result"]["revision"] == "9" * 32
    assert patched["result"]["element"]["entry_type"] == "lore"
    assert gateway.client.write_calls[-1]["patch"] == {  # type: ignore[attr-defined]
        "type": "lore",
        "description": "A title inherited by the keeper of crossings.",
    }

    repeated = call_tool(
        gateway,
        "logosforge_whiteboard_apply_proposal",
        {"proposal_id": patch_proposal["proposal_id"]},
    )
    assert repeated["ok"] is False
    assert "not pending" in repeated["error"]


def test_psyke_relation_proposal_rejects_existing_pair_and_applies_new_pair() -> None:
    gateway = _gateway(allow_writes=True)
    existing = call_tool(
        gateway,
        "logosforge_whiteboard_propose_psyke_relation",
        {
            "document_id": 1,
            "source_id": 11,
            "target_id": 10,
            "expected_revision": "7" * 32,
            "relation_type": "haunted_by",
        },
    )
    assert existing["ok"] is False
    assert "already related" in existing["error"]

    gateway.client.entries[1].append(  # type: ignore[attr-defined]
        {
            "id": "12",
            "name": "The Ferryman",
            "entry_type": "character",
            "aliases": [],
            "description": "Keeper of crossings",
            "notes": "",
        }
    )
    proposal = call_tool(
        gateway,
        "logosforge_whiteboard_propose_psyke_relation",
        {
            "document_id": 1,
            "source_id": 10,
            "target_id": 12,
            "expected_revision": "7" * 32,
            "relation_type": "owes_a_debt_to",
        },
    )["result"]
    assert proposal["request"]["method"] == "POST"
    assert proposal["request"]["path"] == "/api/psyke/relations?doc=1"
    assert proposal["review"]["source"]["name"] == "Mara"
    assert proposal["review"]["target"]["name"] == "The Ferryman"
    assert proposal["review"]["after"]["relation_type"]["preview"] == "owes_a_debt_to"
    assert gateway.client.write_calls == []  # type: ignore[attr-defined]

    applied = call_tool(
        gateway,
        "logosforge_whiteboard_apply_proposal",
        {"proposal_id": proposal["proposal_id"]},
    )["result"]["result"]
    assert applied == {
        "resource": "psyke",
        "operation": "create_relation",
        "document_id": 1,
        "revision": "a" * 32,
        "relation_id": "10:12",
        "source_id": 10,
        "target_id": 12,
        "relation_type": "owes_a_debt_to",
    }
    assert gateway.client.write_calls[-1]["relation"] == {  # type: ignore[attr-defined]
        "source_id": 10,
        "target_id": 12,
        "relation_type": "owes_a_debt_to",
    }


def test_psyke_progression_create_and_patch_store_exact_full_requests() -> None:
    gateway = _gateway(allow_writes=True)
    text = "Mara chooses to carry the lantern beyond the city."
    proposal = call_tool(
        gateway,
        "logosforge_whiteboard_propose_psyke_progression",
        {
            "document_id": 1,
            "entry_id": 10,
            "expected_revision": "7" * 32,
            "text": text,
            "scene_id": None,
        },
    )["result"]
    assert proposal["request"]["method"] == "POST"
    assert json.loads(proposal["request"]["body_page"]["content"]) == {
        "entry_id": 10,
        "scene_id": None,
        "text": text,
    }
    assert proposal["review"]["after"]["text"]["sha256"] == hashlib.sha256(
        text.encode()
    ).hexdigest()
    created = call_tool(
        gateway,
        "logosforge_whiteboard_apply_proposal",
        {"proposal_id": proposal["proposal_id"]},
    )["result"]["result"]
    assert created["operation"] == "create_progression"
    assert created["revision"] == "b" * 32
    assert created["text_characters"] == len(text)
    progression_id = created["progression_id"]

    patch = call_tool(
        gateway,
        "logosforge_whiteboard_propose_psyke_progression_patch",
        {
            "document_id": 1,
            "progression_id": progression_id,
            "expected_revision": "b" * 32,
            "patch": {"scene_id": 31},
        },
    )["result"]
    # The core PATCH is replacement-shaped, so unchanged text is retained in
    # the exact stored request even when the tool caller changes only scene_id.
    assert json.loads(patch["request"]["body_page"]["content"]) == {
        "scene_id": 31,
        "text": text,
    }
    assert patch["review"]["changed_fields"] == ["scene_id"]
    patched = call_tool(
        gateway,
        "logosforge_whiteboard_apply_proposal",
        {"proposal_id": patch["proposal_id"]},
    )["result"]["result"]
    assert patched["operation"] == "patch_progression"
    assert patched["revision"] == "c" * 32
    assert patched["progression_id"] == progression_id
    assert patched["scene_id"] == 31
    assert gateway.client.write_calls[-1]["patch"] == {  # type: ignore[attr-defined]
        "text": text,
        "scene_id": 31,
    }


@pytest.mark.parametrize(
    ("tool", "arguments", "message"),
    [
        (
            "logosforge_whiteboard_propose_psyke_relation",
            {
                "document_id": 1,
                "source_id": 10,
                "target_id": 10,
                "expected_revision": "7" * 32,
            },
            "distinct",
        ),
        (
            "logosforge_whiteboard_propose_psyke_relation",
            {
                "document_id": 1,
                "source_id": 10,
                "target_id": 999,
                "expected_revision": "7" * 32,
            },
            "does not exist",
        ),
        (
            "logosforge_whiteboard_propose_psyke_progression",
            {
                "document_id": 1,
                "entry_id": 10,
                "expected_revision": "7" * 32,
                "text": "Mara still guards the lantern.",
            },
            "identical",
        ),
        (
            "logosforge_whiteboard_propose_psyke_progression_patch",
            {
                "document_id": 1,
                "progression_id": 21,
                "expected_revision": "7" * 32,
                "patch": {"text": "Mara still guards the lantern."},
            },
            "does not change",
        ),
        (
            "logosforge_whiteboard_propose_psyke_progression_patch",
            {
                "document_id": 1,
                "progression_id": 21,
                "expected_revision": "7" * 32,
                "patch": {"sort_order": 9},
            },
            "Unsupported PSYKE progression patch",
        ),
    ],
)
def test_psyke_relation_progression_proposals_reject_unsafe_inputs(
    tool, arguments, message
) -> None:
    result = call_tool(_gateway(), tool, arguments)
    assert result["ok"] is False
    assert message in result["error"]


def test_psyke_progression_review_is_bounded_but_exact_body_is_pageable() -> None:
    text = "turn " * 4_000
    gateway = _gateway()
    proposal = call_tool(
        gateway,
        "logosforge_whiteboard_propose_psyke_progression",
        {
            "document_id": 1,
            "entry_id": 10,
            "expected_revision": "7" * 32,
            "text": text.strip(),
        },
    )["result"]
    review = proposal["review"]["after"]["text"]
    assert review["truncated"] is True
    assert review["characters"] == len(text.strip())
    assert review["sha256"] == hashlib.sha256(text.strip().encode()).hexdigest()
    assert _wire_bytes(proposal) <= MAX_RESULT_BYTES
    assert json.loads(proposal["request"]["body_page"]["content"])["text"] == text.strip()


def test_applying_proposal_is_not_evicted_when_session_reaches_capacity() -> None:
    gateway = _gateway(allow_writes=True)
    first = gateway.propose_manuscript_patch(
        1,
        "3" * 32,
        {"title": "Applying proposal"},
    )
    for index in range(MAX_PROPOSALS - 1):
        gateway.propose_manuscript_patch(
            1,
            "3" * 32,
            {"title": f"Queued proposal {index}"},
        )

    started = threading.Event()
    release = threading.Event()
    original_update = gateway.client.update_document

    def blocked_update(*args, **kwargs):
        started.set()
        if not release.wait(5):
            raise RuntimeError("test timed out waiting to release apply")
        return original_update(*args, **kwargs)

    gateway.client.update_document = blocked_update  # type: ignore[method-assign]
    outcome: dict[str, object] = {}

    def apply_first() -> None:
        try:
            outcome["result"] = gateway.apply_proposal(first["proposal_id"])
        except Exception as exc:  # pragma: no cover - surfaced below
            outcome["error"] = exc

    worker = threading.Thread(target=apply_first)
    worker.start()
    assert started.wait(2)
    try:
        overflow = call_tool(
            gateway,
            "logosforge_whiteboard_propose_manuscript_patch",
            {
                "document_id": 1,
                "expected_revision": "3" * 32,
                "patch": {"title": "Must not displace an in-flight write"},
            },
        )
        assert overflow["ok"] is False
        assert "pending or in-flight proposals" in overflow["error"]
        assert gateway.get_proposal(first["proposal_id"])["state"] == "applying"
    finally:
        release.set()
        worker.join(5)

    assert not worker.is_alive()
    assert "error" not in outcome
    assert outcome["result"]["state"] == "applied"  # type: ignore[index]
    assert gateway.get_proposal(first["proposal_id"])["state"] == "applied"


def test_psyke_proposal_rejects_stale_collection_without_writing() -> None:
    gateway = _gateway(allow_writes=True)
    proposal = call_tool(
        gateway,
        "logosforge_whiteboard_propose_psyke_entry",
        {
            "document_id": 1,
            "expected_revision": "7" * 32,
            "entry": {"name": "Transient", "entry_type": "other"},
        },
    )["result"]
    gateway.client.psyke_revision[1] = "f" * 32  # type: ignore[attr-defined]

    failed = call_tool(
        gateway,
        "logosforge_whiteboard_apply_proposal",
        {"proposal_id": proposal["proposal_id"]},
    )

    assert failed["ok"] is False
    assert "revision_conflict" in failed["error"]
    assert gateway.client.write_calls == []  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    ("tool", "arguments", "message"),
    [
        (
            "logosforge_whiteboard_propose_psyke_entry",
            {
                "document_id": 1,
                "expected_revision": "7" * 32,
                "entry": {"name": " ", "entry_type": "character"},
            },
            "non-blank",
        ),
        (
            "logosforge_whiteboard_propose_psyke_entry",
            {
                "document_id": 1,
                "expected_revision": "7" * 32,
                "entry": {"name": "Mara", "entry_type": "villain"},
            },
            "entry_type",
        ),
        (
            "logosforge_whiteboard_propose_psyke_patch",
            {
                "document_id": 1,
                "entry_id": 10,
                "expected_revision": "7" * 32,
                "patch": {"aliases": ["M"]},
            },
            "Unsupported PSYKE patch",
        ),
        (
            "logosforge_whiteboard_propose_psyke_patch",
            {
                "document_id": 1,
                "entry_id": 999,
                "expected_revision": "7" * 32,
                "patch": {"notes": "Changed"},
            },
            "does not exist",
        ),
    ],
)
def test_psyke_proposals_reject_invalid_or_unknown_entries(tool, arguments, message) -> None:
    result = call_tool(_gateway(), tool, arguments)
    assert result["ok"] is False
    assert message in result["error"]


def test_psyke_review_is_bounded_while_exact_body_remains_pageable() -> None:
    gateway = _gateway()
    description = "A very long truth. " + ("memory " * 30_000)
    response = call_tool(
        gateway,
        "logosforge_whiteboard_propose_psyke_entry",
        {
            "document_id": 1,
            "expected_revision": "7" * 32,
            "entry": {
                "name": "Archive",
                "entry_type": "lore",
                "description": description,
                "notes": "",
            },
        },
    )
    assert response["ok"] is True
    assert _wire_bytes(response) <= MAX_RESULT_BYTES
    proposal = response["result"]
    assert proposal["review"]["after"]["description_truncated"] is True
    assert proposal["review"]["after"]["description_characters"] == len(description)
    chunks: list[str] = []
    offset = 0
    while True:
        page_result = call_tool(
            gateway,
            "logosforge_whiteboard_get_proposal",
            {
                "proposal_id": proposal["proposal_id"],
                "request_body_offset": offset,
                "request_body_max_bytes": 16 * 1024,
            },
        )["result"]
        page = page_result["request"]["body_page"]
        chunks.append(page["content"])
        if page["next_offset"] is None:
            break
        offset = page["next_offset"]
    assert json.loads("".join(chunks))["description"] == description


def test_outline_proposal_long_id_samples_preserve_core_response_fields() -> None:
    gateway = _gateway()
    before_items = [
        _outline_node(f"old-{index:03d}" + "😀" * 249, "Old", order=index)
        for index in range(120)
    ]
    items = [
        _outline_node(f"new-{index:03d}" + "🌟" * 249, "New", order=index)
        for index in range(120)
    ]
    gateway.client.outline[1] = before_items  # type: ignore[attr-defined]

    response = call_tool(
        gateway,
        "logosforge_whiteboard_propose_outline_replace",
        {
            "document_id": 1,
            "expected_revision": "1" * 32,
            "items": items,
        },
    )

    assert response["ok"] is True
    assert _wire_bytes(response) <= MAX_RESULT_BYTES
    proposal = response["result"]
    assert "_mcp_output" not in proposal
    assert proposal["state"] == "pending"
    assert proposal["summary"] == "Replace the outline for Whiteboard document 1."
    assert proposal["requires_user_approval"] is True
    review = proposal["review"]
    assert review["added_count"] == 120
    assert review["removed_count"] == 120
    assert review["id_change_list_truncated"] is True
    assert _wire_bytes(review["added_ids"]) <= MAX_PROPOSAL_ID_SAMPLE_BYTES
    assert _wire_bytes(review["removed_ids"]) <= MAX_PROPOSAL_ID_SAMPLE_BYTES


@pytest.mark.parametrize(
    ("tool", "arguments", "message"),
    [
        (
            "logosforge_whiteboard_propose_manuscript_patch",
            {"document_id": 1, "expected_revision": "3" * 31, "patch": {"title": "x"}},
            "expected_revision",
        ),
        (
            "logosforge_whiteboard_propose_manuscript_patch",
            {"document_id": 1, "expected_revision": "3" * 32, "patch": {"unknown": True}},
            "Unsupported manuscript patch",
        ),
        (
            "logosforge_whiteboard_propose_manuscript_patch",
            {"document_id": 1, "expected_revision": "3" * 32, "patch": {"mode": "series"}},
            "Manuscript mode must be one of",
        ),
        (
            "logosforge_whiteboard_propose_manuscript_patch",
            {
                "document_id": 1,
                "expected_revision": "3" * 32,
                "patch": {
                    "blocks": [
                        {"id": "duplicate", "type": "paragraph", "text": "one"},
                        {"id": "duplicate", "type": "paragraph", "text": "two"},
                    ]
                },
            },
            "duplicated",
        ),
        (
            "logosforge_whiteboard_propose_outline_replace",
            {
                "document_id": 1,
                "expected_revision": "1" * 32,
                "items": [
                    _outline_node("same", "First"),
                    _outline_node("same", "Second", order=1),
                ],
            },
            "duplicated",
        ),
    ],
)
def test_proposal_validation_rejects_unsafe_inputs(tool, arguments, message) -> None:
    response = call_tool(_gateway(), tool, arguments)
    assert response["ok"] is False
    assert message in response["error"]


@pytest.mark.parametrize(
    ("block", "message"),
    [
        ({"id": "missing-text", "type": "paragraph"}, "missing required field"),
        ({"id": "bad id", "type": "paragraph", "text": "x"}, "invalid stable id"),
        (
            {"id": "bad-level", "type": "heading", "text": "x", "level": 7},
            "1..6",
        ),
        (
            {"id": "bad-sp", "type": "paragraph", "text": "x", "sp": "aside"},
            "field 'sp' is invalid",
        ),
        (
            {"id": "null-marks", "type": "paragraph", "text": "x", "marks": None},
            "must be an array",
        ),
        (
            {
                "id": "bad-mark",
                "type": "paragraph",
                "text": "short",
                "marks": [{"type": "bold", "from": 0, "to": 20}],
            },
            "invalid offsets",
        ),
    ],
)
def test_manuscript_proposal_rejects_invalid_block_contract(block, message) -> None:
    response = call_tool(
        _gateway(),
        "logosforge_whiteboard_propose_manuscript_patch",
        {
            "document_id": 1,
            "expected_revision": "3" * 32,
            "patch": {"blocks": [block]},
        },
    )
    assert response["ok"] is False
    assert message in response["error"]


def test_manuscript_mark_offsets_follow_renderer_utf16_units() -> None:
    response = call_tool(
        _gateway(),
        "logosforge_whiteboard_propose_manuscript_patch",
        {
            "document_id": 1,
            "expected_revision": "3" * 32,
            "patch": {
                "blocks": [
                    {
                        "id": "emoji",
                        "type": "paragraph",
                        "text": "😀x",
                        "marks": [{"type": "bold", "from": 0, "to": 2}],
                    }
                ]
            },
        },
    )
    assert response["ok"] is True


@pytest.mark.parametrize(
    ("items", "message"),
    [
        ([{"id": "incomplete"}], "missing required field"),
        ([_outline_node("bad type", "Bad")], "invalid stable id"),
        ([_outline_node("child", "Child", parent_id="missing")], "missing parent"),
        (
            [
                _outline_node("one", "One", parent_id="two"),
                _outline_node("two", "Two", parent_id="one"),
            ],
            "parent cycle",
        ),
        ([_outline_node("one", "One", node_type="volume")], "invalid type"),
        (
            [_outline_node("one", "One", link={"blockIndex": -1, "quote": "x"})],
            "invalid blockIndex",
        ),
        (
            [_outline_node("one", "One", createdAt="not-a-timestamp")],
            "valid ISO timestamp",
        ),
    ],
)
def test_outline_proposal_rejects_malformed_or_unsafe_trees(items, message) -> None:
    response = call_tool(
        _gateway(),
        "logosforge_whiteboard_propose_outline_replace",
        {
            "document_id": 1,
            "expected_revision": "1" * 32,
            "items": items,
        },
    )
    assert response["ok"] is False
    assert message in response["error"]


def test_outline_proposal_canonicalizes_legacy_numeric_sibling_order() -> None:
    gateway = _gateway(allow_writes=True)
    items = [
        _outline_node("later", "Later", order=9.5),
        _outline_node("first", "First", order=-10),
        _outline_node("also-later", "Also later", order=9.5),
    ]
    proposal = call_tool(
        gateway,
        "logosforge_whiteboard_propose_outline_replace",
        {
            "document_id": 1,
            "expected_revision": "1" * 32,
            "items": items,
        },
    )["result"]
    applied = call_tool(
        gateway,
        "logosforge_whiteboard_apply_proposal",
        {"proposal_id": proposal["proposal_id"]},
    )
    assert applied["ok"] is True
    written = gateway.client.write_calls[0]["items"]  # type: ignore[attr-defined,index]
    assert {item["id"]: item["order"] for item in written} == {
        "first": 0,
        "later": 1,
        "also-later": 2,
    }


def test_programmatic_config_is_loopback_authenticated_and_bounded() -> None:
    McpConfig("http://127.0.0.1:8777", "x" * 32)
    with pytest.raises(McpToolError, match="loopback"):
        McpConfig("https://example.test:443", "x" * 32)
    with pytest.raises(McpToolError, match="bearer token"):
        McpConfig("http://127.0.0.1:8777", "short")
    with pytest.raises(McpToolError, match="timeout"):
        McpConfig("http://127.0.0.1:8777", "x" * 32, 301)
    with pytest.raises(McpToolError, match="TTL"):
        McpConfig("http://127.0.0.1:8777", "x" * 32, proposal_ttl_seconds=59)


def test_environment_config_keeps_writes_opt_in_and_bounds_ttl(
    monkeypatch, tmp_path: Path
) -> None:
    descriptor = tmp_path / "mcp-runtime-v1.json"

    class Connection:
        base_url = "http://127.0.0.1:8777"
        auth_token = "x" * 32

    monkeypatch.setattr(
        whiteboard_mcp_server,
        "load_runtime_connection",
        lambda *_args, **_kwargs: Connection(),
    )
    base = {"LOGOSFORGE_WHITEBOARD_MCP_CONNECTION_FILE": str(descriptor)}
    assert McpConfig.from_env(base).allow_writes is False
    enabled = McpConfig.from_env(
        {
            **base,
            "LOGOSFORGE_WHITEBOARD_MCP_ALLOW_WRITES": "yes",
            "LOGOSFORGE_WHITEBOARD_MCP_PROPOSAL_TTL_SECONDS": "120",
        }
    )
    assert enabled.allow_writes is True
    assert enabled.proposal_ttl_seconds == 120
    with pytest.raises(McpToolError, match="ALLOW_WRITES"):
        McpConfig.from_env(
            {**base, "LOGOSFORGE_WHITEBOARD_MCP_ALLOW_WRITES": "sometimes"}
        )
    with pytest.raises(McpToolError, match="TTL"):
        McpConfig.from_env(
            {**base, "LOGOSFORGE_WHITEBOARD_MCP_PROPOSAL_TTL_SECONDS": "59"}
        )


def test_api_client_sends_bearer_and_only_uses_get(monkeypatch) -> None:
    seen = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, _size):
            return b'{"documents": []}'

    def urlopen(request, timeout):
        seen["method"] = request.get_method()
        seen["auth"] = request.get_header("Authorization")
        seen["url"] = request.full_url
        seen["timeout"] = timeout
        return Response()

    monkeypatch.setattr("app.whiteboard_mcp.client.urllib.request.urlopen", urlopen)
    client = WhiteboardApiClient("http://127.0.0.1:8777", "s" * 32, 7)
    assert client.list_documents() == []
    assert seen == {
        "method": "GET",
        "auth": f"Bearer {'s' * 32}",
        "url": "http://127.0.0.1:8777/api/documents",
        "timeout": 7.0,
    }


def test_api_client_manuscript_write_is_exact_conditional_put(monkeypatch) -> None:
    seen = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, _size):
            return json.dumps(
                {
                    "id": "1",
                    "incarnation": "a" * 32,
                    "revision": "5" * 32,
                    "title": "Changed",
                    "mode": "novel",
                    "blocks": [],
                    "settings": {},
                    "updated_at": "2026-09-25T00:00:00Z",
                }
            ).encode("utf-8")

    def urlopen(request, timeout):
        seen["method"] = request.get_method()
        seen["url"] = request.full_url
        seen["headers"] = {key.lower(): value for key, value in request.header_items()}
        seen["body"] = json.loads(request.data.decode("utf-8"))
        seen["timeout"] = timeout
        return Response()

    monkeypatch.setattr("app.whiteboard_mcp.client.urllib.request.urlopen", urlopen)
    client = WhiteboardApiClient("http://127.0.0.1:8777", "s" * 32, 7)
    result = client.update_document(
        1,
        incarnation="a" * 32,
        expected_revision="3" * 32,
        mutation_id="lfwbp_safe-id",
        patch={"title": "Changed"},
    )
    assert result["revision"] == "5" * 32
    assert seen["method"] == "PUT"
    assert seen["url"] == "http://127.0.0.1:8777/api/whiteboard?doc=1"
    assert seen["headers"]["authorization"] == f"Bearer {'s' * 32}"
    assert seen["headers"]["if-match"] == (
        f'"lfwb:whiteboard:{"a" * 32}:{"3" * 32}"'
    )
    assert seen["headers"]["x-logosforge-document-incarnation"] == "a" * 32
    assert seen["headers"]["x-logosforge-mutation-id"] == "lfwbp_safe-id"
    assert seen["headers"]["content-type"] == "application/json"
    assert seen["body"] == {"title": "Changed"}
    assert seen["timeout"] == 7.0


def test_api_client_comment_reply_is_exact_conditional_post_and_validates_etag(
    monkeypatch,
) -> None:
    seen = {}
    mutation_id = "reply.id:one"
    comment = _comment_dto(
        "c1",
        "lantern",
        "Track this image",
        replies=[
            {
                "id": mutation_id,
                "body": "Handled in the revised scene.",
                "author": "MCP assistant",
                "created_at": "2026-01-03T00:00:00+00:00",
            }
        ],
    )

    class Response:
        headers = {
            "ETag": f'"lfwb:comments:{"a" * 32}:{"d" * 32}"'
        }

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, _size):
            return json.dumps(comment).encode("utf-8")

    def urlopen(request, timeout):
        seen["method"] = request.get_method()
        seen["url"] = request.full_url
        seen["headers"] = {key.lower(): value for key, value in request.header_items()}
        seen["body"] = json.loads(request.data.decode("utf-8"))
        seen["timeout"] = timeout
        return Response()

    monkeypatch.setattr("app.whiteboard_mcp.client.urllib.request.urlopen", urlopen)
    client = WhiteboardApiClient("http://127.0.0.1:8777", "s" * 32, 7)
    result = client.reply_to_comment(
        1,
        "c1",
        incarnation="a" * 32,
        expected_revision="c" * 32,
        mutation_id=mutation_id,
        body="Handled in the revised scene.",
    )
    assert result == {"comment": comment, "revision": "d" * 32}
    assert seen["method"] == "POST"
    assert seen["url"] == "http://127.0.0.1:8777/api/comments/c1/replies?doc=1"
    assert seen["headers"]["authorization"] == f"Bearer {'s' * 32}"
    assert seen["headers"]["if-match"] == (
        f'"lfwb:comments:{"a" * 32}:{"c" * 32}"'
    )
    assert seen["headers"]["x-logosforge-document-incarnation"] == "a" * 32
    assert seen["headers"]["x-logosforge-mutation-id"] == mutation_id
    assert seen["body"] == {"body": "Handled in the revised scene."}
    assert seen["timeout"] == 7.0


def test_api_client_comment_resolution_is_exact_conditional_put(monkeypatch) -> None:
    seen = {}
    comment = _comment_dto(
        "c1", "lantern", "Track this image", resolved=True
    )

    class Response:
        headers = {
            "etag": f'"lfwb:comments:{"a" * 32}:{"e" * 32}"'
        }

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, _size):
            return json.dumps(comment).encode("utf-8")

    def urlopen(request, timeout):
        seen["method"] = request.get_method()
        seen["url"] = request.full_url
        seen["headers"] = {key.lower(): value for key, value in request.header_items()}
        seen["body"] = json.loads(request.data.decode("utf-8"))
        return Response()

    monkeypatch.setattr("app.whiteboard_mcp.client.urllib.request.urlopen", urlopen)
    client = WhiteboardApiClient("http://127.0.0.1:8777", "s" * 32)
    result = client.set_comment_resolution(
        1,
        "c1",
        incarnation="a" * 32,
        expected_revision="c" * 32,
        mutation_id="resolve-one",
        resolved=True,
    )
    assert result == {"comment": comment, "revision": "e" * 32}
    assert seen["method"] == "PUT"
    assert seen["url"] == "http://127.0.0.1:8777/api/comments/c1?doc=1"
    assert seen["headers"]["if-match"] == (
        f'"lfwb:comments:{"a" * 32}:{"c" * 32}"'
    )
    assert seen["body"] == {"resolved": True}


@pytest.mark.parametrize(
    "etag",
    [
        None,
        'W/"lfwb:comments:' + "a" * 32 + ":" + "d" * 32 + '"',
        '"lfwb:outline:' + "a" * 32 + ":" + "d" * 32 + '"',
        '"lfwb:comments:' + "b" * 32 + ":" + "d" * 32 + '"',
        '"lfwb:comments:' + "a" * 32 + ":" + "D" * 32 + '"',
    ],
)
def test_api_client_comment_mutation_fails_closed_on_invalid_etag(
    monkeypatch, etag
) -> None:
    comment = _comment_dto("c1", "lantern", "Track this image", resolved=True)

    class Response:
        headers = {} if etag is None else {"ETag": etag}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, _size):
            return json.dumps(comment).encode("utf-8")

    monkeypatch.setattr(
        "app.whiteboard_mcp.client.urllib.request.urlopen",
        lambda _request, timeout: Response(),
    )
    client = WhiteboardApiClient("http://127.0.0.1:8777", "s" * 32)
    with pytest.raises(WhiteboardApiError, match="invalid ETag"):
        client.set_comment_resolution(
            1,
            "c1",
            incarnation="a" * 32,
            expected_revision="c" * 32,
            mutation_id="resolve-one",
            resolved=True,
        )


@pytest.mark.parametrize(
    ("mutation", "match"),
    [
        (
            _comment_dto("other", "lantern", "Track this image", resolved=True),
            "invalid target",
        ),
        (
            _comment_dto("c1", "lantern", "Track this image", resolved=False),
            "invalid target",
        ),
    ],
)
def test_api_client_comment_resolution_rejects_wrong_result(
    monkeypatch, mutation, match
) -> None:
    class Response:
        headers = {"ETag": f'"lfwb:comments:{"a" * 32}:{"d" * 32}"'}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, _size):
            return json.dumps(mutation).encode("utf-8")

    monkeypatch.setattr(
        "app.whiteboard_mcp.client.urllib.request.urlopen",
        lambda _request, timeout: Response(),
    )
    client = WhiteboardApiClient("http://127.0.0.1:8777", "s" * 32)
    with pytest.raises(WhiteboardApiError, match=match):
        client.set_comment_resolution(
            1,
            "c1",
            incarnation="a" * 32,
            expected_revision="c" * 32,
            mutation_id="resolve-one",
            resolved=True,
        )


def test_api_client_comment_reply_rejects_wrong_reply_identity(monkeypatch) -> None:
    comment = _comment_dto(
        "c1",
        "lantern",
        "Track this image",
        replies=[
            {
                "id": "different-id",
                "body": "Handled.",
                "author": "MCP assistant",
                "created_at": "2026-01-03T00:00:00+00:00",
            }
        ],
    )

    class Response:
        headers = {"ETag": f'"lfwb:comments:{"a" * 32}:{"d" * 32}"'}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, _size):
            return json.dumps(comment).encode("utf-8")

    monkeypatch.setattr(
        "app.whiteboard_mcp.client.urllib.request.urlopen",
        lambda _request, timeout: Response(),
    )
    client = WhiteboardApiClient("http://127.0.0.1:8777", "s" * 32)
    with pytest.raises(WhiteboardApiError, match="invalid reply"):
        client.reply_to_comment(
            1,
            "c1",
            incarnation="a" * 32,
            expected_revision="c" * 32,
            mutation_id="reply-one",
            body="Handled.",
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("unexpected", True),
        ("id", "bad/id"),
        ("quote", "q" * 250_001),
        ("body", "b" * (MAX_COMMENT_BODY_CHARACTERS + 1)),
        ("resolved", 1),
        ("replies", "not-a-list"),
        ("updated_at", None),
    ],
    ids=[
        "unexpected-field",
        "invalid-id",
        "huge-quote",
        "huge-body",
        "non-boolean-resolved",
        "non-list-replies",
        "invalid-timestamp",
    ],
)
def test_api_client_rejects_malformed_comment_dto(field, value) -> None:
    comment = _comment_dto("c1", "lantern", "Track this image")
    comment[field] = value
    with pytest.raises(WhiteboardApiError, match="comment response"):
        WhiteboardApiClient._validated_comment(comment)


def test_api_client_get_comments_requires_revision_and_bounded_unique_dtos(
    monkeypatch,
) -> None:
    client = WhiteboardApiClient("http://127.0.0.1:8777", "s" * 32)
    comment = _comment_dto("c1", "lantern", "Track this image")
    monkeypatch.setattr(
        client,
        "_get",
        lambda *_args, **_kwargs: {
            "comments": [comment],
            "revision": "c" * 32,
        },
    )
    assert client.get_comments(1) == {
        "comments": [comment],
        "revision": "c" * 32,
    }

    monkeypatch.setattr(
        client,
        "_get",
        lambda *_args, **_kwargs: {
            "comments": [comment, dict(comment)],
            "revision": "c" * 32,
        },
    )
    with pytest.raises(WhiteboardApiError, match="comments response"):
        client.get_comments(1)

    monkeypatch.setattr(
        client,
        "_get",
        lambda *_args, **_kwargs: {
            "comments": [],
            "revision": "bad",
        },
    )
    with pytest.raises(WhiteboardApiError, match="comments response"):
        client.get_comments(1)

    monkeypatch.setattr(
        client,
        "_get",
        lambda *_args, **_kwargs: {
            "comments": [comment] * (MAX_COMMENTS + 1),
            "revision": "c" * 32,
        },
    )
    with pytest.raises(WhiteboardApiError, match="comments response"):
        client.get_comments(1)


def test_api_client_psyke_create_is_exact_conditional_post(monkeypatch) -> None:
    seen = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, _size):
            return json.dumps(
                {
                    "ok": True,
                    "element": {
                        "id": "12",
                        "name": "Mara",
                        "entry_type": "character",
                        "aliases": [],
                        "description": "Keeper",
                        "notes": "",
                    },
                    "revision": "8" * 32,
                }
            ).encode("utf-8")

    def urlopen(request, timeout):
        seen["method"] = request.get_method()
        seen["url"] = request.full_url
        seen["headers"] = {key.lower(): value for key, value in request.header_items()}
        seen["body"] = json.loads(request.data.decode("utf-8"))
        seen["timeout"] = timeout
        return Response()

    monkeypatch.setattr("app.whiteboard_mcp.client.urllib.request.urlopen", urlopen)
    client = WhiteboardApiClient("http://127.0.0.1:8777", "s" * 32, 7)
    result = client.create_psyke_entry(
        1,
        incarnation="a" * 32,
        expected_revision="7" * 32,
        mutation_id="lfwbp-psyke-create",
        entry={
            "name": "Mara",
            "type": "character",
            "description": "Keeper",
            "notes": "",
        },
    )
    assert result["revision"] == "8" * 32
    assert seen["method"] == "POST"
    assert seen["url"] == "http://127.0.0.1:8777/api/psyke/elements?doc=1"
    assert seen["headers"]["if-match"] == (
        f'"lfwb:psyke:{"a" * 32}:{"7" * 32}"'
    )
    assert seen["headers"]["x-logosforge-document-incarnation"] == "a" * 32
    assert seen["headers"]["x-logosforge-mutation-id"] == "lfwbp-psyke-create"
    assert seen["body"]["description"] == "Keeper"
    assert seen["timeout"] == 7.0


def test_api_client_psyke_patch_is_exact_conditional_patch(monkeypatch) -> None:
    seen = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, _size):
            return json.dumps(
                {
                    "ok": True,
                    "element": _api_psyke_element(
                        entry_type="lore",
                        description="A title inherited by the keeper.",
                    ),
                    "revision": "9" * 32,
                }
            ).encode("utf-8")

    def urlopen(request, timeout):
        seen["method"] = request.get_method()
        seen["url"] = request.full_url
        seen["headers"] = {key.lower(): value for key, value in request.header_items()}
        seen["body"] = json.loads(request.data.decode("utf-8"))
        seen["timeout"] = timeout
        return Response()

    monkeypatch.setattr("app.whiteboard_mcp.client.urllib.request.urlopen", urlopen)
    client = WhiteboardApiClient("http://127.0.0.1:8777", "s" * 32, 7)
    patch = {
        "type": "lore",
        "description": "A title inherited by the keeper.",
    }
    result = client.patch_psyke_entry(
        1,
        12,
        incarnation="a" * 32,
        expected_revision="8" * 32,
        mutation_id="lfwbp-psyke-patch",
        patch=patch,
    )

    assert result["revision"] == "9" * 32
    assert result["element"]["id"] == "12"
    assert seen["method"] == "PATCH"
    assert seen["url"] == "http://127.0.0.1:8777/api/psyke/elements/12?doc=1"
    assert seen["headers"]["authorization"] == f"Bearer {'s' * 32}"
    assert seen["headers"]["if-match"] == (
        f'"lfwb:psyke:{"a" * 32}:{"8" * 32}"'
    )
    assert seen["headers"]["x-logosforge-document-incarnation"] == "a" * 32
    assert seen["headers"]["x-logosforge-mutation-id"] == "lfwbp-psyke-patch"
    assert seen["headers"]["content-type"] == "application/json"
    assert seen["body"] == patch
    assert seen["timeout"] == 7.0


@pytest.mark.parametrize("ok", [False, None, 1, "true"])
def test_api_client_psyke_mutation_requires_exact_success_envelope(ok) -> None:
    with pytest.raises(WhiteboardApiError, match="mutation response"):
        WhiteboardApiClient._validated_psyke_mutation(
            {
                "ok": ok,
                "element": _api_psyke_element(),
                "revision": "8" * 32,
            }
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("id", "0"),
        ("id", 12),
        ("id", "1" * (MAX_PSYKE_ID_CHARACTERS + 1)),
        ("name", " "),
        ("name", "N" * (MAX_PSYKE_NAME_CHARACTERS + 1)),
        ("entry_type", "villain"),
        ("entry_type", ["character"]),
        ("aliases", "The Keeper"),
        ("aliases", [""] * (MAX_PSYKE_ALIASES + 1)),
        ("aliases", ["A" * (MAX_PSYKE_ALIAS_CHARACTERS + 1)]),
        (
            "aliases",
            ["A" * MAX_PSYKE_ALIAS_CHARACTERS]
            * (MAX_PSYKE_ALIAS_TOTAL_CHARACTERS // MAX_PSYKE_ALIAS_CHARACTERS + 1),
        ),
        ("description", "D" * (MAX_PSYKE_TEXT_CHARACTERS + 1)),
        ("notes", None),
    ],
    ids=[
        "zero-id",
        "non-string-id",
        "long-id",
        "blank-name",
        "long-name",
        "unknown-entry-type",
        "non-string-entry-type",
        "non-list-aliases",
        "too-many-aliases",
        "long-alias",
        "large-alias-aggregate",
        "long-description",
        "non-string-notes",
    ],
)
def test_api_client_rejects_malformed_psyke_element(field, value) -> None:
    with pytest.raises(WhiteboardApiError, match="element response"):
        WhiteboardApiClient._validated_psyke_element(
            _api_psyke_element(**{field: value})
        )


def test_api_client_psyke_element_validation_returns_detached_known_dto() -> None:
    source = _api_psyke_element(unexpected="not part of the frontend DTO")
    validated = WhiteboardApiClient._validated_psyke_element(source)

    assert validated == {
        key: value for key, value in source.items() if key != "unexpected"
    }
    assert validated is not source
    assert validated["aliases"] is not source["aliases"]


def test_api_client_get_psyke_rejects_huge_current_identity_field(monkeypatch) -> None:
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, _size):
            return json.dumps(
                {
                    "results": [
                        _api_psyke_element(
                            name="N" * (MAX_PSYKE_NAME_CHARACTERS + 1)
                        )
                    ],
                    "revision": "7" * 32,
                }
            ).encode("utf-8")

    monkeypatch.setattr(
        "app.whiteboard_mcp.client.urllib.request.urlopen",
        lambda _request, timeout: Response(),
    )
    client = WhiteboardApiClient("http://127.0.0.1:8777", "s" * 32)
    with pytest.raises(WhiteboardApiError, match="PSYKE response"):
        client.get_psyke(1)


def test_api_client_psyke_mutation_rejects_malformed_or_wrong_element() -> None:
    with pytest.raises(WhiteboardApiError, match="mutation response"):
        WhiteboardApiClient._validated_psyke_mutation(
            {
                "ok": True,
                "element": _api_psyke_element(entry_type="invalid"),
                "revision": "8" * 32,
            }
        )


def test_api_client_psyke_patch_rejects_response_for_different_element(
    monkeypatch,
) -> None:
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, _size):
            return json.dumps(
                {
                    "ok": True,
                    "element": _api_psyke_element(id="13"),
                    "revision": "9" * 32,
                }
            ).encode("utf-8")

    monkeypatch.setattr(
        "app.whiteboard_mcp.client.urllib.request.urlopen",
        lambda _request, timeout: Response(),
    )
    client = WhiteboardApiClient("http://127.0.0.1:8777", "s" * 32)
    with pytest.raises(WhiteboardApiError, match="mutation response"):
        client.patch_psyke_entry(
            1,
            12,
            incarnation="a" * 32,
            expected_revision="8" * 32,
            mutation_id="lfwbp-psyke-patch",
            patch={"notes": "Changed"},
        )


def test_api_client_psyke_relation_progression_reads_are_strict_and_allowlisted(
    monkeypatch,
) -> None:
    seen: list[tuple[str, str]] = []

    class Response:
        def __init__(self, value):
            self.value = value

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, _size):
            return json.dumps(self.value).encode("utf-8")

    def urlopen(request, timeout):
        del timeout
        seen.append((request.get_method(), request.full_url))
        if "/relations" in request.full_url:
            return Response(
                {"relations": [_api_psyke_relation()], "revision": "7" * 32}
            )
        return Response(
            {
                "progressions": [_api_psyke_progression()],
                "revision": "7" * 32,
            }
        )

    monkeypatch.setattr("app.whiteboard_mcp.client.urllib.request.urlopen", urlopen)
    client = WhiteboardApiClient("http://127.0.0.1:8777", "s" * 32)
    assert client.get_psyke_relations(1) == {
        "relations": [_api_psyke_relation()],
        "revision": "7" * 32,
    }
    assert client.get_psyke_progressions(1) == {
        "progressions": [_api_psyke_progression()],
        "revision": "7" * 32,
    }
    assert seen == [
        ("GET", "http://127.0.0.1:8777/api/psyke/relations?doc=1"),
        ("GET", "http://127.0.0.1:8777/api/psyke/progressions?doc=1"),
    ]

    monkeypatch.setattr(
        client,
        "_get",
        lambda *_args, **_kwargs: {
            "relations": [_api_psyke_relation(), _api_psyke_relation()],
            "revision": "7" * 32,
        },
    )
    with pytest.raises(WhiteboardApiError, match="relations response"):
        client.get_psyke_relations(1)


def test_api_client_psyke_relation_progression_mutations_are_exact_conditional_requests(
    monkeypatch,
) -> None:
    seen: list[dict[str, object]] = []
    responses = [
        {
            "ok": True,
            "relation": _api_psyke_relation(
                id="10:12",
                target_id=12,
                target="The Ferryman",
                relation_type="owes_a_debt_to",
            ),
            "revision": "a" * 32,
        },
        {
            "ok": True,
            "progression": _api_psyke_progression(
                id=22,
                text="Mara crosses the river.",
            ),
            "revision": "b" * 32,
        },
        {
            "ok": True,
            "progression": _api_psyke_progression(
                id=22,
                text="Mara crosses the river.",
                scene_id=31,
                scene_title="Crossing",
                sort_order=2,
            ),
            "revision": "c" * 32,
        },
    ]

    class Response:
        def __init__(self, value):
            self.value = value

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, _size):
            return json.dumps(self.value).encode("utf-8")

    def urlopen(request, timeout):
        seen.append(
            {
                "method": request.get_method(),
                "url": request.full_url,
                "headers": {
                    key.lower(): value for key, value in request.header_items()
                },
                "body": json.loads(request.data.decode("utf-8")),
                "timeout": timeout,
            }
        )
        return Response(responses.pop(0))

    monkeypatch.setattr("app.whiteboard_mcp.client.urllib.request.urlopen", urlopen)
    client = WhiteboardApiClient("http://127.0.0.1:8777", "s" * 32, 7)
    relation = {"source_id": 10, "target_id": 12, "relation_type": "owes_a_debt_to"}
    created_relation = client.create_psyke_relation(
        1,
        incarnation="a" * 32,
        expected_revision="7" * 32,
        mutation_id="relation-create",
        relation=relation,
    )
    progression = {
        "entry_id": 10,
        "text": "Mara crosses the river.",
        "scene_id": None,
    }
    created_progression = client.create_psyke_progression(
        1,
        incarnation="a" * 32,
        expected_revision="a" * 32,
        mutation_id="progression-create",
        progression=progression,
    )
    patched_progression = client.patch_psyke_progression(
        1,
        22,
        incarnation="a" * 32,
        expected_revision="b" * 32,
        mutation_id="progression-patch",
        patch={"text": "Mara crosses the river.", "scene_id": 31},
    )

    assert created_relation["revision"] == "a" * 32
    assert created_progression["progression"]["id"] == 22
    assert patched_progression["revision"] == "c" * 32
    assert [(item["method"], item["url"], item["body"]) for item in seen] == [
        ("POST", "http://127.0.0.1:8777/api/psyke/relations?doc=1", relation),
        (
            "POST",
            "http://127.0.0.1:8777/api/psyke/progressions?doc=1",
            progression,
        ),
        (
            "PATCH",
            "http://127.0.0.1:8777/api/psyke/progressions/22?doc=1",
            {"text": "Mara crosses the river.", "scene_id": 31},
        ),
    ]
    for index, expected_revision in enumerate(("7" * 32, "a" * 32, "b" * 32)):
        assert seen[index]["headers"]["if-match"] == (  # type: ignore[index]
            f'"lfwb:psyke:{"a" * 32}:{expected_revision}"'
        )
        assert seen[index]["timeout"] == 7.0


@pytest.mark.parametrize(
    ("validator", "value"),
    [
        (WhiteboardApiClient._validated_psyke_relation, _api_psyke_relation(id="11:10")),
        (WhiteboardApiClient._validated_psyke_relation, _api_psyke_relation(source_id=0)),
        (WhiteboardApiClient._validated_psyke_relation, _api_psyke_relation(target_id=10, id="10:10")),
        (
            WhiteboardApiClient._validated_psyke_relation,
            _api_psyke_relation(
                relation_type="r" * (MAX_PSYKE_RELATION_TYPE_CHARACTERS + 1)
            ),
        ),
        (WhiteboardApiClient._validated_psyke_progression, _api_psyke_progression(id=0)),
        (WhiteboardApiClient._validated_psyke_progression, _api_psyke_progression(scene_id=0)),
        (WhiteboardApiClient._validated_psyke_progression, _api_psyke_progression(sort_order=True)),
        (
            WhiteboardApiClient._validated_psyke_progression,
            _api_psyke_progression(text="x" * (MAX_PSYKE_TEXT_CHARACTERS + 1)),
        ),
        (
            WhiteboardApiClient._validated_psyke_progression,
            _api_psyke_progression(
                scene_title="x" * (MAX_PSYKE_SCENE_TITLE_CHARACTERS + 1)
            ),
        ),
        (
            WhiteboardApiClient._validated_psyke_progression,
            _api_psyke_progression(entry_id=MAX_PSYKE_INTEGER_ID + 1),
        ),
    ],
)
def test_api_client_rejects_malformed_psyke_relations_and_progressions(
    validator, value
) -> None:
    with pytest.raises(WhiteboardApiError, match="PSYKE .* response"):
        validator(value)


def test_api_client_preserves_valid_outline_revision(monkeypatch) -> None:
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, _size):
            return json.dumps(
                {
                    "items": [{"id": "o1", "title": "Opening"}],
                    "revision": "abcdef0123456789abcdef0123456789",
                }
            ).encode("utf-8")

    def urlopen(_request, timeout):
        del timeout
        return Response()

    monkeypatch.setattr("app.whiteboard_mcp.client.urllib.request.urlopen", urlopen)
    client = WhiteboardApiClient("http://127.0.0.1:8777", "s" * 32)
    assert client.get_outline(1) == {
        "items": [{"id": "o1", "title": "Opening"}],
        "revision": "abcdef0123456789abcdef0123456789",
    }


@pytest.mark.parametrize(
    "revision",
    [None, "", "a" * 31, "a" * 33, "A" * 32, "g" * 32, 1],
)
def test_api_client_rejects_invalid_manuscript_revision(monkeypatch, revision) -> None:
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, _size):
            return json.dumps({"blocks": [], "revision": revision}).encode("utf-8")

    def urlopen(_request, timeout):
        del timeout
        return Response()

    monkeypatch.setattr("app.whiteboard_mcp.client.urllib.request.urlopen", urlopen)
    client = WhiteboardApiClient("http://127.0.0.1:8777", "s" * 32)
    with pytest.raises(WhiteboardApiError, match="manuscript has an invalid shape"):
        client.get_document(1)


@pytest.mark.parametrize(
    "revision",
    [None, "", "a" * 31, "a" * 33, "A" * 32, "g" * 32, 1],
)
def test_api_client_rejects_invalid_outline_revision(monkeypatch, revision) -> None:
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, _size):
            return json.dumps({"items": [], "revision": revision}).encode("utf-8")

    def urlopen(_request, timeout):
        del timeout
        return Response()

    monkeypatch.setattr("app.whiteboard_mcp.client.urllib.request.urlopen", urlopen)
    client = WhiteboardApiClient("http://127.0.0.1:8777", "s" * 32)
    with pytest.raises(WhiteboardApiError, match="outline has an invalid shape"):
        client.get_outline(1)


def test_api_client_error_never_echoes_bearer_token(monkeypatch) -> None:
    token = "never-echo-this-token-000000000000"

    def urlopen(request, timeout):
        del request, timeout
        body = json.dumps({"error": {"message": f"bad credential {token}"}}).encode()
        raise urllib.error.HTTPError(
            "http://127.0.0.1:8777/api/documents",
            500,
            "failure",
            {},
            io.BytesIO(body),
        )

    monkeypatch.setattr("app.whiteboard_mcp.client.urllib.request.urlopen", urlopen)
    client = WhiteboardApiClient("http://127.0.0.1:8777", token)
    with pytest.raises(WhiteboardApiError) as caught:
        client.list_documents()
    assert token not in str(caught.value)
    assert "[redacted]" in str(caught.value)


def test_real_mcp_stdio_initializes_and_completes_authenticated_read(tmp_path: Path) -> None:
    mcp = pytest.importorskip("mcp")
    from mcp.client.stdio import stdio_client

    token = "stdio-secret-00000000000000000000"
    nonce = "stdio-whiteboard-instance"

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urlparse(self.path)
            if parsed.path == "/health":
                value = {
                    "status": "ok",
                    "service": "logosforge-whiteboard-backend",
                    "instance_nonce": nonce,
                }
                self._send(200, value)
                return
            if self.headers.get("Authorization") != f"Bearer {token}":
                self._send(401, {"error": {"message": "unauthorized"}})
                return
            if parsed.path == "/api/documents":
                self._send(
                    200,
                    {
                        "documents": [
                            {
                                "id": "1",
                                "incarnation": "a" * 32,
                                "title": "Stdio document",
                                "mode": "prose",
                                "updated_at": "2026-09-24T10:00:00Z",
                            }
                        ]
                    },
                )
                return
            self._send(404, {"detail": "not found"})

        def _send(self, status: int, value: object) -> None:
            raw = json.dumps(value).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def log_message(self, _format, *_args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    descriptor = tmp_path / "mcp-runtime-v1.json"
    descriptor.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "base_url": f"http://127.0.0.1:{server.server_port}",
                "auth_token": token,
                "instance_nonce": nonce,
                "app_pid": os.getpid(),
                "backend_pid": os.getpid(),
                "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            }
        ),
        encoding="utf-8",
    )
    if os.name != "nt":
        descriptor.chmod(0o600)

    async def exercise():
        params = mcp.StdioServerParameters(
            command=sys.executable,
            args=["-m", "app.whiteboard_mcp.server"],
            cwd=str(_BACKEND_ROOT),
            env={
                **os.environ,
                "PYTHONPATH": str(_BACKEND_ROOT),
                "LOGOSFORGE_WHITEBOARD_MCP_CONNECTION_FILE": str(descriptor),
            },
        )
        async with (
            stdio_client(params) as streams,
            mcp.ClientSession(*streams) as session,
        ):
            initialized = await session.initialize()
            listed = await session.list_tools()
            result = await session.call_tool(
                "logosforge_whiteboard_list_documents", {"limit": 10}
            )
            return initialized, listed, result

    try:
        initialized, listed, result = asyncio.run(exercise())
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert initialized.serverInfo.name == "logosforge-whiteboard"
    assert initialized.serverInfo.version == "1.4.0"
    assert len(listed.tools) == 24
    by_name = {tool.name: tool for tool in listed.tools}
    apply = by_name["logosforge_whiteboard_apply_proposal"].annotations
    assert apply.readOnlyHint is False
    assert apply.destructiveHint is True
    assert apply.idempotentHint is False
    discard = by_name["logosforge_whiteboard_discard_proposal"].annotations
    assert discard.readOnlyHint is False
    assert discard.destructiveHint is False
    assert discard.idempotentHint is False
    for proposal_name in (
        "logosforge_whiteboard_propose_manuscript_patch",
        "logosforge_whiteboard_propose_outline_replace",
        "logosforge_whiteboard_propose_comment_reply",
        "logosforge_whiteboard_propose_comment_resolution",
        "logosforge_whiteboard_propose_psyke_entry",
        "logosforge_whiteboard_propose_psyke_patch",
        "logosforge_whiteboard_propose_psyke_relation",
        "logosforge_whiteboard_propose_psyke_progression",
        "logosforge_whiteboard_propose_psyke_progression_patch",
    ):
        proposal_annotations = by_name[proposal_name].annotations
        assert proposal_annotations.readOnlyHint is True
        assert proposal_annotations.destructiveHint is False
        assert proposal_annotations.idempotentHint is False
    assert all(
        tool.annotations.openWorldHint is False
        for tool in listed.tools
    )
    assert result.isError is False
    structured = getattr(result, "structuredContent", None)
    if structured is None:
        structured = getattr(result, "structured_content", None)
    assert structured["ok"] is True
    assert structured["result"]["documents"][0]["title"] == "Stdio document"
