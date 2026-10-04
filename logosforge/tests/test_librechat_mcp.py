"""Focused unit tests for the Pro MCP gateway safety boundary.

These tests deliberately use a deterministic fake API client.  They verify
that the gateway reads the canonical DTOs and that its proposal lifecycle does
not turn into an alternate, less-safe write API.  No MCP SDK, server process,
database, or desktop session is required.
"""

from __future__ import annotations

import asyncio
import copy
import hashlib
import io
import json
import os
import sys
import time
from pathlib import Path
from unittest import mock

import pytest
from logosforge.db.database import _timeline_command_request_digest
from logosforge.librechat import api_client as ac
from logosforge.librechat.api_client import LogosForgeApiClient, LogosForgeApiError
from logosforge.librechat.mcp_gateway import (
    GatewayError,
    LogosForgeMcpGateway,
    _timeline_receipt_request_digest,
)


class _Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


def _response(payload):
    return _Response(json.dumps(payload).encode("utf-8"))


def test_api_client_get_scene_uses_full_scene_endpoint_and_keeps_revision():
    client = LogosForgeApiClient(
        base_url="http://127.0.0.1:8765", project_id=7, auth_token="secret",
    )
    captured = {}
    scene = {
        "id": 31,
        "project_id": 7,
        "title": "The Crossing",
        "content": "Full manuscript prose.",
        "revision": "rev-scene-31",
    }

    def fake_urlopen(request, timeout=None):
        captured.update(
            url=request.full_url,
            method=request.get_method(),
            authorization=request.headers.get("Authorization"),
            timeout=timeout,
        )
        return _response(scene)

    with mock.patch.object(ac.urllib.request, "urlopen", fake_urlopen):
        result = client.get_scene(31)

    assert captured == {
        "url": "http://127.0.0.1:8765/api/projects/7/scenes/31",
        "method": "GET",
        "authorization": "Bearer secret",
        "timeout": 15.0,
    }
    assert result["content"] == "Full manuscript prose."
    assert result["revision"] == "rev-scene-31"


def test_api_client_get_timeline_uses_authoritative_project_endpoint():
    client = LogosForgeApiClient(
        base_url="http://127.0.0.1:8765", project_id=7, auth_token="secret",
    )
    captured = {}
    timeline = {
        "project_id": 7,
        "revision": "a" * 64,
        "order_mode": "structural",
        "lanes": [],
        "events": [],
        "off_timeline": [],
    }

    def fake_urlopen(request, timeout=None):
        captured.update(
            url=request.full_url,
            method=request.get_method(),
            authorization=request.headers.get("Authorization"),
            timeout=timeout,
        )
        return _response(timeline)

    with mock.patch.object(ac.urllib.request, "urlopen", fake_urlopen):
        result = client.get_timeline()

    assert captured == {
        "url": "http://127.0.0.1:8765/api/projects/7/timeline",
        "method": "GET",
        "authorization": "Bearer secret",
        "timeout": 15.0,
    }
    assert result == timeline


def test_api_client_timeline_receipt_keeps_idempotency_key_out_of_url():
    client = LogosForgeApiClient(
        base_url="http://127.0.0.1:8765", project_id=7, auth_token="secret",
    )
    proposal_id = "lfp_abcdefghijklmnopqrstuvwx"
    captured = {}
    receipt = {
        "project_id": 7,
        "request_digest": "a" * 64,
        "command_kind": "create_lane",
        "expected_revision": "b" * 64,
        "applied_revision": "c" * 64,
        "original_changed": True,
        "original_affected_scene_ids": [],
        "committed_at": "2026-10-04T10:00:00Z",
    }

    def fake_urlopen(request, timeout=None):
        captured.update(
            url=request.full_url,
            method=request.get_method(),
            headers={key.lower(): value for key, value in request.header_items()},
            timeout=timeout,
        )
        return _response(receipt)

    with mock.patch.object(ac.urllib.request, "urlopen", fake_urlopen):
        result = client.get_timeline_command_receipt(proposal_id)

    assert captured["url"] == (
        "http://127.0.0.1:8765/api/projects/7/timeline/command-receipt"
    )
    assert proposal_id not in captured["url"]
    assert captured["method"] == "GET"
    assert captured["headers"]["idempotency-key"] == proposal_id
    assert captured["headers"]["authorization"] == "Bearer secret"
    assert result == receipt


def test_api_client_preserves_http_status_and_machine_error_code():
    client = LogosForgeApiClient(
        base_url="http://127.0.0.1:8765", project_id=7,
    )
    response = _response({
        "error": {
            "code": "timeline_conflict",
            "message": "The Timeline changed.",
        },
    })

    def fake_urlopen(request, timeout=None):
        del timeout
        raise ac.urllib.error.HTTPError(
            request.full_url,
            409,
            "Conflict",
            hdrs=None,
            fp=response,
        )

    with (
        mock.patch.object(ac.urllib.request, "urlopen", fake_urlopen),
        pytest.raises(
            LogosForgeApiError,
            match=r"HTTP 409.*GET /api/projects/7/timeline.*Timeline changed",
        ) as caught,
    ):
        client.get_timeline()

    assert caught.value.status_code == 409
    assert caught.value.error_code == "timeline_conflict"


def test_api_client_search_uses_typed_project_endpoint_and_encodes_query():
    client = LogosForgeApiClient(
        base_url="http://127.0.0.1:8765", project_id=7, auth_token="secret",
    )
    captured = {}
    response = {
        "query": "distant thunder & rain",
        "matches": [{
            "kind": "comment",
            "id": 81,
            "title": "Comment 81: Packaged",
            "excerpt": "Keep the distant thunder & rain.",
            "revision": "a" * 64,
            "resolved": False,
        }],
        "limit": 100,
    }

    def fake_urlopen(request, timeout=None):
        captured.update(
            url=request.full_url,
            method=request.get_method(),
            authorization=request.headers.get("Authorization"),
            timeout=timeout,
        )
        return _response(response)

    with mock.patch.object(ac.urllib.request, "urlopen", fake_urlopen):
        result = client.search_project("distant thunder & rain")

    assert captured == {
        "url": (
            "http://127.0.0.1:8765/api/projects/7/search"
            "?q=distant+thunder+%26+rain"
        ),
        "method": "GET",
        "authorization": "Bearer secret",
        "timeout": 15.0,
    }
    assert result == response


def test_api_client_requires_an_explicit_project_for_scoped_calls():
    client = LogosForgeApiClient(project_id=None)

    with pytest.raises(LogosForgeApiError, match="No LogosForge project is selected"):
        client.get_scene(1)


def _timeline_request_digest(project_id: int, body: dict) -> str:
    raw = json.dumps(
        {
            "scope": "timeline-command-v1",
            "project_id": project_id,
            "kind": body["kind"],
            "expected_revision": body["expected_revision"],
            "fields": {
                key: value
                for key, value in body.items()
                if key not in {"kind", "expected_revision"}
            },
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@pytest.mark.parametrize(
    "body",
    [
        {
            "kind": "create_lane",
            "expected_revision": "a" * 64,
            "name": "Trama café ∞",
        },
        {
            "kind": "update_lane",
            "expected_revision": "b" * 64,
            "lane_id": 7,
            "collapsed": False,
            "index": 0,
        },
        {
            "kind": "delete_lane",
            "expected_revision": "c" * 64,
            "lane_id": 7,
        },
        {
            "kind": "place_event",
            "expected_revision": "d" * 64,
            "scene_id": 11,
            "lane_id": None,
        },
        {
            "kind": "remove_event",
            "expected_revision": "e" * 64,
            "scene_id": 11,
        },
        {
            "kind": "set_order_mode",
            "expected_revision": "f" * 64,
            "mode": "custom",
        },
    ],
    ids=[
        "create-unicode-omitted-optionals",
        "update",
        "delete",
        "place-explicit-null-lane",
        "remove",
        "order-mode",
    ],
)
def test_timeline_receipt_request_digest_matches_core_canonical_wire(body):
    fields = {
        key: value
        for key, value in body.items()
        if key not in {"kind", "expected_revision"}
    }
    assert _timeline_receipt_request_digest(7, body) == (
        _timeline_command_request_digest(
            7,
            body["kind"],
            body["expected_revision"],
            fields,
        )
    )


class _FakeApiClient:
    """Minimal canonical-Pro-API fake with mutable server-side state."""

    def __init__(
        self,
        *,
        project_id: int | None = 1,
        authenticated: bool = True,
        projects: list[dict] | None = None,
    ) -> None:
        self.project_id = project_id
        self._authenticated = authenticated
        self.projects = projects or [
            {"id": 1, "title": "Novel One"},
            {"id": 2, "title": "Novel Two"},
        ]
        self.scenes = {
            1: {
                11: {
                    "id": 11,
                    "project_id": 1,
                    "title": "Opening",
                    "content": "Before.\n",
                    "revision": "rev-1",
                    "status": "draft",
                }
            },
            2: {},
        }
        self.timelines = {
            1: {
                "project_id": 1,
                "revision": "1" * 64,
                "order_mode": "structural",
                "lanes": [],
                "events": [],
                "off_timeline": [{
                    "id": 11,
                    "title": "Opening",
                    "structural_number": "1",
                    "act": "",
                    "chapter": "",
                }],
            },
            2: {
                "project_id": 2,
                "revision": "2" * 64,
                "order_mode": "structural",
                "lanes": [],
                "events": [],
                "off_timeline": [],
            },
        }
        self._timeline_revision_sequence = 3
        self.timeline_receipts: dict[tuple[int, str], dict] = {}
        self.comments = {
            1: [
                {
                    "id": 81,
                    "source_id": "native-thread",
                    "anchor": {
                        "start_scene_id": 11,
                        "start_field": "content",
                        "from_offset": 0,
                        "end_scene_id": 11,
                        "end_field": "content",
                        "to_offset": 6,
                        "prefix": "",
                        "suffix": ".",
                    },
                    "quote": "Before",
                    "body": "Sharpen the opening image.",
                    "resolved": False,
                    "replies": [
                        {
                            "id": 91,
                            "source_id": "",
                            "body": "Keep the distant thunder.",
                            "author": "writer",
                            "sort_order": 0,
                            "created_at": "2026-09-01T10:01:00Z",
                        },
                    ],
                    "created_at": "2026-09-01T10:00:00Z",
                    "updated_at": "2026-09-01T10:01:00Z",
                    "revision": "a" * 64,
                },
                {
                    "id": 82,
                    "source_id": "resolved-thread",
                    "anchor": {
                        "start_scene_id": 11,
                        "start_field": "title",
                        "from_offset": 0,
                        "end_scene_id": 11,
                        "end_field": "title",
                        "to_offset": 7,
                        "prefix": "",
                        "suffix": "",
                    },
                    "quote": "Opening",
                    "body": "Resolved cadence note.",
                    "resolved": True,
                    "replies": [],
                    "created_at": "2026-08-31T09:00:00Z",
                    "updated_at": "2026-08-31T09:00:00Z",
                    "revision": "b" * 64,
                },
            ],
            2: [],
        }
        self._comment_revision_sequence = 12
        self.resources = {
            "/api/projects/1/psyke/entries/5": {
                "id": 5,
                "project_id": 1,
                "name": "Ada",
                "type": "character",
                "notes": "Lead",
            },
            "/api/projects/1/outline": [
                {"id": 41, "title": "Act I", "parent_id": None},
            ],
            "/api/projects/1/notes": [
                {"id": 71, "title": "Question", "content": "Why?"},
            ],
            "/api/projects/1/psyke/relations": [],
        }
        self.requests: list[tuple[str, str, dict | None]] = []
        self.request_idempotency_keys: list[tuple[str, str, str]] = []
        self.search_calls: list[tuple[int, str]] = []

    @property
    def has_auth_token(self) -> bool:
        return self._authenticated

    def api_path(self, suffix: str) -> str:
        return f"/api/{suffix.lstrip('/')}"

    def project_path(self, suffix: str = "", project_id: int | None = None) -> str:
        pid = int(project_id) if project_id is not None else self.require_project_id()
        base = f"/api/projects/{pid}"
        return f"{base}/{suffix.lstrip('/')}" if suffix else base

    def require_project_id(self) -> int:
        if self.project_id is None:
            raise LogosForgeApiError("No LogosForge project is selected.")
        return self.project_id

    def list_projects(self) -> list[dict]:
        return copy.deepcopy(self.projects)

    def get_project(self, project_id: int | None = None) -> dict:
        pid = int(project_id) if project_id is not None else self.require_project_id()
        for project in self.projects:
            if project["id"] == pid:
                return copy.deepcopy(project)
        raise LogosForgeApiError(f"Project {pid} not found")

    def search_project(self, query: str, project_id: int | None = None) -> dict:
        pid = int(project_id) if project_id is not None else self.require_project_id()
        self.search_calls.append((pid, query))
        matches = []
        if pid == 1 and query.casefold() == "distant thunder":
            matches = [{
                "kind": "comment",
                "id": 81,
                "title": "Comment 81: Before",
                "excerpt": "Keep the distant thunder.",
                "revision": "a" * 64,
                "resolved": False,
            }]
        return {"query": query, "matches": matches, "limit": 100}

    def select_project(self, project_id: int) -> dict:
        project = self.get_project(project_id)
        self.project_id = int(project_id)
        return project

    def list_scenes(self, project_id: int | None = None) -> list[dict]:
        pid = int(project_id) if project_id is not None else self.require_project_id()
        return copy.deepcopy(list(self.scenes[pid].values()))

    def get_scene(self, scene_id: int, project_id: int | None = None) -> dict:
        pid = int(project_id) if project_id is not None else self.require_project_id()
        return copy.deepcopy(self.scenes[pid][int(scene_id)])

    def get_outline(self, project_id: int | None = None) -> list[dict]:
        pid = int(project_id) if project_id is not None else self.require_project_id()
        return copy.deepcopy(self.resources[f"/api/projects/{pid}/outline"])

    def get_timeline(self, project_id: int | None = None) -> dict:
        pid = int(project_id) if project_id is not None else self.require_project_id()
        return copy.deepcopy(self.timelines[pid])

    def get_timeline_command_receipt(
        self,
        idempotency_key: str,
        project_id: int | None = None,
    ) -> dict:
        pid = int(project_id) if project_id is not None else self.require_project_id()
        return self.request(
            "GET",
            self.project_path("timeline/command-receipt", pid),
            idempotency_key=idempotency_key,
        )

    def list_characters(self, project_id: int | None = None) -> list[dict]:
        pid = int(project_id) if project_id is not None else self.require_project_id()
        if pid == 1:
            return [{"id": 91, "name": "Ada", "psyke_entry_id": 5}]
        return []

    def list_psyke_entries(self, project_id: int | None = None) -> list[dict]:
        pid = int(project_id) if project_id is not None else self.require_project_id()
        prefix = f"/api/projects/{pid}/psyke/entries/"
        return copy.deepcopy(
            [value for path, value in self.resources.items() if path.startswith(prefix)]
        )

    def get_psyke_entry(self, entry_id: int, project_id: int | None = None) -> dict:
        return self.request(
            "GET", self.project_path(f"psyke/entries/{int(entry_id)}", project_id),
        )

    def list_psyke_relations(self, project_id: int | None = None) -> list[dict]:
        return self.request("GET", self.project_path("psyke/relations", project_id))

    def list_psyke_progressions(self, project_id: int | None = None) -> list[dict]:
        return []

    def list_notes(self, project_id: int | None = None) -> list[dict]:
        return self.request("GET", self.project_path("notes", project_id))

    def list_comments(self, project_id: int | None = None) -> list[dict]:
        pid = int(project_id) if project_id is not None else self.require_project_id()
        return copy.deepcopy(self.comments[pid])

    def get_comment(
        self, comment_id: int, project_id: int | None = None,
    ) -> dict:
        pid = int(project_id) if project_id is not None else self.require_project_id()
        for comment in self.comments[pid]:
            if comment["id"] == int(comment_id):
                return copy.deepcopy(comment)
        raise LogosForgeApiError(f"Comment {comment_id} not found")

    def _next_comment_revision(self) -> str:
        value = f"{self._comment_revision_sequence:064x}"
        self._comment_revision_sequence += 1
        return value

    def poll_events(self, since: int = 0, project_id: int | None = None) -> dict:
        return {"events": [], "cursor": since}

    def request(
        self,
        method: str,
        path: str,
        body: dict | None = None,
        query: dict | None = None,
        *,
        idempotency_key: str = "",
    ):
        del query
        method = method.upper()
        stored_body = copy.deepcopy(body)
        self.requests.append((method, path, stored_body))
        self.request_idempotency_keys.append((method, path, idempotency_key))

        if method == "GET":
            if path.endswith("/timeline/command-receipt"):
                project_id = int(path.split("/")[3])
                receipt = self.timeline_receipts.get((project_id, idempotency_key))
                if receipt is None:
                    raise LogosForgeApiError(
                        "Timeline command receipt not found",
                        status_code=404,
                        error_code="timeline_receipt_not_found",
                    )
                return copy.deepcopy(receipt)
            if path == "/api/projects/1/timeline":
                return self.get_timeline(1)
            comment_prefix = "/api/projects/1/comments/"
            if path.startswith(comment_prefix):
                return self.get_comment(int(path.removeprefix(comment_prefix)), 1)
            return copy.deepcopy(self.resources[path])

        comment_prefix = "/api/projects/1/comments/"
        if path.startswith(comment_prefix):
            suffix = path.removeprefix(comment_prefix)
            if suffix.endswith("/replies") and method == "POST":
                comment_id = int(suffix.removesuffix("/replies"))
                comment = next(
                    item for item in self.comments[1] if item["id"] == comment_id
                )
                assert body is not None
                if body.get("expected_revision") != comment["revision"]:
                    raise LogosForgeApiError(
                        "HTTP 409: comment thread changed",
                        status_code=409,
                        error_code="comment_conflict",
                    )
                comment["replies"].append({
                    "id": 90 + len(comment["replies"]) + 1,
                    "source_id": "",
                    "body": body.get("body", ""),
                    "author": body.get("author", "you"),
                    "sort_order": len(comment["replies"]),
                    "created_at": "2026-09-01T11:00:00Z",
                })
                comment["updated_at"] = "2026-09-01T11:00:00Z"
                comment["revision"] = self._next_comment_revision()
                return copy.deepcopy(comment)
            if method == "PATCH":
                comment_id = int(suffix)
                comment = next(
                    item for item in self.comments[1] if item["id"] == comment_id
                )
                assert body is not None
                if body.get("expected_revision") != comment["revision"]:
                    raise LogosForgeApiError(
                        "HTTP 409: comment thread changed",
                        status_code=409,
                        error_code="comment_conflict",
                    )
                if "resolved" in body:
                    comment["resolved"] = bool(body["resolved"])
                comment["updated_at"] = "2026-09-01T11:00:00Z"
                comment["revision"] = self._next_comment_revision()
                return copy.deepcopy(comment)

        if method == "POST" and path == "/api/projects/1/timeline/commands":
            timeline = self.timelines[1]
            assert body is not None
            receipt_key = (1, idempotency_key)
            if idempotency_key and receipt_key in self.timeline_receipts:
                receipt = self.timeline_receipts[receipt_key]
                if receipt["request_digest"] != _timeline_request_digest(1, body):
                    raise LogosForgeApiError(
                        "Idempotency-Key was reused",
                        status_code=409,
                        error_code="idempotency_key_conflict",
                    )
                return {
                    "timeline": copy.deepcopy(timeline),
                    "replayed": True,
                    "applied_revision": receipt["applied_revision"],
                    "changed": False,
                    "affected_scene_ids": [],
                }
            if body.get("expected_revision") != timeline["revision"]:
                raise LogosForgeApiError(
                    "HTTP 409: The Timeline changed.",
                    status_code=409,
                    error_code="timeline_conflict",
                )
            if body.get("kind") != "create_lane":
                raise LogosForgeApiError("unsupported fake Timeline command")
            lane = {
                "id": 301 + len(timeline["lanes"]),
                "name": body["name"],
                "color_label": body.get("color_label", ""),
                "order_index": len(timeline["lanes"]),
                "collapsed": False,
                "event_count": 0,
            }
            index = body.get("index")
            if index is None:
                index = len(timeline["lanes"])
            timeline["lanes"].insert(index, lane)
            for order_index, row in enumerate(timeline["lanes"]):
                row["order_index"] = order_index
            timeline["revision"] = f"{self._timeline_revision_sequence:064x}"
            self._timeline_revision_sequence += 1
            if idempotency_key:
                self.timeline_receipts[receipt_key] = {
                    "project_id": 1,
                    "request_digest": _timeline_request_digest(1, body),
                    "command_kind": body["kind"],
                    "expected_revision": body["expected_revision"],
                    "applied_revision": timeline["revision"],
                    "original_changed": True,
                    "original_affected_scene_ids": [],
                    "committed_at": "2026-10-04T10:00:00Z",
                }
            return {
                "timeline": copy.deepcopy(timeline),
                "replayed": False,
                "applied_revision": timeline["revision"],
                "changed": True,
                "affected_scene_ids": [],
            }

        scene_prefix = "/api/projects/1/scenes/"
        if method == "PATCH" and path.startswith(scene_prefix):
            scene_id = int(path.removeprefix(scene_prefix))
            scene = self.scenes[1][scene_id]
            if body is None or body.get("expected_revision") != scene["revision"]:
                raise LogosForgeApiError("revision conflict", status_code=409)
            for key, value in body.items():
                if key != "expected_revision":
                    scene[key] = value
            scene["revision"] = "rev-2"
            return copy.deepcopy(scene)

        if method == "PATCH" and path in self.resources:
            assert body is not None
            self.resources[path].update(body)
            return copy.deepcopy(self.resources[path])

        return {"ok": True, "method": method, "path": path, "body": stored_body}


def _gateway(
    client: _FakeApiClient | None = None,
    *,
    allow_writes: bool = False,
    require_auth_for_writes: bool = True,
) -> tuple[LogosForgeMcpGateway, _FakeApiClient]:
    fake = client or _FakeApiClient()
    return (
        LogosForgeMcpGateway(
            fake,
            allow_writes=allow_writes,
            require_auth_for_writes=require_auth_for_writes,
        ),
        fake,
    )


def test_project_selection_is_explicit_when_ambiguous_and_then_scopes_reads():
    fake = _FakeApiClient(project_id=None)
    gateway, _ = _gateway(fake)

    assert gateway.list_projects() == {
        "projects": fake.projects,
        "selected_project_id": None,
    }
    with pytest.raises(GatewayError, match="No project is selected"):
        gateway.get_project()

    selected = gateway.select_project(2)
    assert selected["selected_project_id"] == 2
    assert gateway.get_project() == {"id": 2, "title": "Novel Two"}


def test_a_single_available_project_is_selected_automatically():
    fake = _FakeApiClient(
        project_id=None, projects=[{"id": 1, "title": "Only Novel"}],
    )
    gateway, _ = _gateway(fake)

    assert gateway.get_project() == {"id": 1, "title": "Only Novel"}
    assert fake.project_id == 1


def test_scene_reads_return_full_content_and_revision_but_lists_are_compact():
    gateway, _ = _gateway()

    scene = gateway.get_scene(11)
    assert scene["content"] == "Before.\n"
    assert scene["revision"] == "rev-1"

    listed = gateway.list_scenes()
    assert listed[0]["revision"] == "rev-1"
    assert listed[0]["content_length"] == len("Before.\n")
    assert "content" not in listed[0]


def test_timeline_read_and_proposal_apply_are_exact_revision_bound_and_single_use():
    gateway, fake = _gateway(allow_writes=True)
    current = gateway.get_timeline()
    assert current == fake.timelines[1]

    first = gateway.propose_timeline_command({
        "kind": "create_lane",
        "expected_revision": current["revision"],
        "name": " Main ",
        "color_label": "cyan",
        "index": 0,
    })
    stale_sibling = gateway.propose_timeline_command({
        "kind": "create_lane",
        "expected_revision": current["revision"],
        "name": "Secondary",
    })

    assert first["state"] == stale_sibling["state"] == "pending"
    assert first["request"] == {
        "method": "POST",
        "path": "/api/projects/1/timeline/commands",
        "body": {
            "kind": "create_lane",
            "expected_revision": "1" * 64,
            "name": "Main",
            "color_label": "cyan",
            "index": 0,
        },
    }
    assert first["review"]["before"]["lane_order"] == {
        "items": [], "total": 0, "truncated": 0,
    }
    assert fake.timelines[1]["lanes"] == []
    assert not any(method == "POST" for method, _path, _body in fake.requests)

    applied = gateway.apply_proposal(first["proposal_id"])
    assert applied["state"] == "applied"
    assert [lane["name"] for lane in fake.timelines[1]["lanes"]] == ["Main"]
    assert applied["result"]["timeline"]["revision"] != current["revision"]
    assert fake.requests[-1] == (
        "POST",
        "/api/projects/1/timeline/commands",
        first["request"]["body"],
    )
    assert fake.request_idempotency_keys[-1] == (
        "POST",
        "/api/projects/1/timeline/commands",
        first["proposal_id"],
    )

    with pytest.raises(GatewayError, match="timeline_conflict.*will not be retried"):
        gateway.apply_proposal(stale_sibling["proposal_id"])
    assert gateway.get_proposal(stale_sibling["proposal_id"])["state"] == "failed"
    assert [lane["name"] for lane in fake.timelines[1]["lanes"]] == ["Main"]

    with pytest.raises(GatewayError, match="applied, not pending"):
        gateway.apply_proposal(first["proposal_id"])


@pytest.mark.parametrize("status_code", [None, 500], ids=["no-response", "server-error"])
def test_timeline_ambiguous_apply_recovers_a_committed_receipt(status_code):
    gateway, fake = _gateway(allow_writes=True)
    proposal = gateway.propose_timeline_command({
        "kind": "create_lane",
        "expected_revision": fake.timelines[1]["revision"],
        "name": "Possibly committed",
    })
    request = fake.request
    post_keys = []

    def lose_response(
        method, path, body=None, query=None, *, idempotency_key="",
    ):
        result = request(
            method, path, body, query, idempotency_key=idempotency_key,
        )
        if method == "POST" and path.endswith("/timeline/commands"):
            post_keys.append(idempotency_key)
            del result
            raise LogosForgeApiError(
                "connection reset after request",
                status_code=status_code,
            )
        return result

    fake.request = lose_response
    applied = gateway.apply_proposal(proposal["proposal_id"])

    assert applied["state"] == "applied"
    assert applied["recovered_from_core"] is True
    assert applied["result"]["replayed"] is True
    assert applied["result"]["changed"] is False
    assert applied["result"]["affected_scene_ids"] == []
    assert applied["receipt"]["command_kind"] == "create_lane"
    assert [lane["name"] for lane in fake.timelines[1]["lanes"]] == [
        "Possibly committed",
    ]
    assert post_keys == [proposal["proposal_id"]]
    assert (
        "GET",
        "/api/projects/1/timeline/command-receipt",
        proposal["proposal_id"],
    ) in fake.request_idempotency_keys


def test_timeline_supported_receipt_miss_allows_one_bounded_same_key_resend():
    gateway, fake = _gateway(allow_writes=True)
    proposal = gateway.propose_timeline_command({
        "kind": "create_lane",
        "expected_revision": fake.timelines[1]["revision"],
        "name": "Retry exactly once",
    })
    request = fake.request
    post_keys = []

    def lose_first_before_commit(
        method, path, body=None, query=None, *, idempotency_key="",
    ):
        if method == "POST" and path.endswith("/timeline/commands"):
            post_keys.append(idempotency_key)
            if len(post_keys) == 1:
                raise LogosForgeApiError("connection reset before commit")
        return request(
            method, path, body, query, idempotency_key=idempotency_key,
        )

    fake.request = lose_first_before_commit
    applied = gateway.apply_proposal(proposal["proposal_id"])

    assert applied["state"] == "applied"
    assert post_keys == [proposal["proposal_id"], proposal["proposal_id"]]
    assert [lane["name"] for lane in fake.timelines[1]["lanes"]] == [
        "Retry exactly once",
    ]


def test_timeline_recovery_pending_never_resends_more_than_once_total():
    gateway, fake = _gateway(allow_writes=True)
    proposal = gateway.propose_timeline_command({
        "kind": "create_lane",
        "expected_revision": fake.timelines[1]["revision"],
        "name": "No unbounded retries",
    })
    request = fake.request
    post_keys = []

    def lose_both_before_commit(
        method, path, body=None, query=None, *, idempotency_key="",
    ):
        if method == "POST" and path.endswith("/timeline/commands"):
            post_keys.append(idempotency_key)
            raise LogosForgeApiError("connection reset before commit")
        return request(
            method, path, body, query, idempotency_key=idempotency_key,
        )

    fake.request = lose_both_before_commit
    with pytest.raises(GatewayError, match="awaiting durable recovery"):
        gateway.apply_proposal(proposal["proposal_id"])
    assert gateway.get_proposal(proposal["proposal_id"])["state"] == (
        "recovery_pending"
    )

    fake.request = request
    for _ in range(2):
        with pytest.raises(GatewayError, match="remains recovery_pending"):
            gateway.apply_proposal(proposal["proposal_id"])
    assert post_keys == [proposal["proposal_id"], proposal["proposal_id"]]
    assert fake.timelines[1]["lanes"] == []


def test_timeline_recovery_pending_can_later_observe_the_committed_receipt():
    gateway, fake = _gateway(allow_writes=True)
    proposal = gateway.propose_timeline_command({
        "kind": "create_lane",
        "expected_revision": fake.timelines[1]["revision"],
        "name": "Committed on resend",
    })
    request = fake.request
    post_count = 0

    def ambiguous_twice(
        method, path, body=None, query=None, *, idempotency_key="",
    ):
        nonlocal post_count
        if method == "POST" and path.endswith("/timeline/commands"):
            post_count += 1
            if post_count == 1:
                raise LogosForgeApiError("first request did not arrive")
            result = request(
                method, path, body, query, idempotency_key=idempotency_key,
            )
            del result
            raise LogosForgeApiError("resend committed; response lost")
        return request(
            method, path, body, query, idempotency_key=idempotency_key,
        )

    fake.request = ambiguous_twice
    with pytest.raises(GatewayError, match="awaiting durable recovery"):
        gateway.apply_proposal(proposal["proposal_id"])

    fake.request = request
    applied = gateway.apply_proposal(proposal["proposal_id"])
    assert applied["state"] == "applied"
    assert applied["recovered_from_core"] is True
    assert applied["result"]["replayed"] is True
    assert post_count == 2
    assert [lane["name"] for lane in fake.timelines[1]["lanes"]] == [
        "Committed on resend",
    ]


def test_timeline_legacy_receipt_404_keeps_ambiguous_apply_terminal():
    gateway, fake = _gateway(allow_writes=True)
    proposal = gateway.propose_timeline_command({
        "kind": "create_lane",
        "expected_revision": fake.timelines[1]["revision"],
        "name": "Legacy Core",
    })
    request = fake.request
    post_count = 0

    def legacy_core(
        method, path, body=None, query=None, *, idempotency_key="",
    ):
        nonlocal post_count
        if method == "GET" and path.endswith("/timeline/command-receipt"):
            raise LogosForgeApiError("route not found", status_code=404)
        result = request(
            method, path, body, query, idempotency_key=idempotency_key,
        )
        if method == "POST" and path.endswith("/timeline/commands"):
            post_count += 1
            del result
            raise LogosForgeApiError("response lost")
        return result

    fake.request = legacy_core
    with pytest.raises(GatewayError, match="indeterminate.*do not retry"):
        gateway.apply_proposal(proposal["proposal_id"])

    assert gateway.get_proposal(proposal["proposal_id"])["state"] == "indeterminate"
    assert post_count == 1


def test_non_timeline_ambiguous_apply_remains_terminal_and_has_no_key():
    gateway, fake = _gateway(allow_writes=True)
    proposal = gateway.propose_create_psyke_entry({"name": "Ada"})
    request = fake.request

    def lose_response(method, path, body=None, query=None, *, idempotency_key=""):
        assert idempotency_key == ""
        result = request(method, path, body, query)
        if method == "POST":
            del result
            raise LogosForgeApiError("response lost")
        return result

    fake.request = lose_response
    with pytest.raises(GatewayError, match="indeterminate.*do not retry"):
        gateway.apply_proposal(proposal["proposal_id"])
    assert gateway.get_proposal(proposal["proposal_id"])["state"] == "indeterminate"


def test_timeline_receipt_integrity_mismatch_fails_closed():
    gateway, fake = _gateway(allow_writes=True)
    proposal = gateway.propose_timeline_command({
        "kind": "create_lane",
        "expected_revision": fake.timelines[1]["revision"],
        "name": "Tampered receipt",
    })
    request = fake.request

    def commit_then_tamper(
        method, path, body=None, query=None, *, idempotency_key="",
    ):
        result = request(
            method, path, body, query, idempotency_key=idempotency_key,
        )
        if method == "POST" and path.endswith("/timeline/commands"):
            fake.timeline_receipts[(1, idempotency_key)]["request_digest"] = "f" * 64
            del result
            raise LogosForgeApiError("response lost")
        return result

    fake.request = commit_then_tamper
    with pytest.raises(GatewayError, match="receipt integrity check failed"):
        gateway.apply_proposal(proposal["proposal_id"])
    assert gateway.get_proposal(proposal["proposal_id"])["state"] == "failed"


def test_unknown_timeline_proposal_recovers_from_selected_project_after_restart():
    gateway, fake = _gateway(allow_writes=True)
    proposal = gateway.propose_timeline_command({
        "kind": "create_lane",
        "expected_revision": fake.timelines[1]["revision"],
        "name": "Survives gateway restart",
    })
    gateway.apply_proposal(proposal["proposal_id"])

    restarted, _ = _gateway(fake)
    recovered = restarted.get_proposal(proposal["proposal_id"])

    assert recovered["state"] == "applied"
    assert recovered["recovered_from_core"] is True
    assert recovered["request"] is None
    assert recovered["receipt"]["command_kind"] == "create_lane"
    assert recovered["review"]["recovered_receipt"] == recovered["receipt"]
    assert recovered["result"] == {
        "timeline": fake.timelines[1],
        "replayed": True,
        "applied_revision": recovered["receipt"]["applied_revision"],
        "changed": False,
        "affected_scene_ids": [],
    }

    fake.project_id = 2
    wrong_project, _ = _gateway(fake)
    with pytest.raises(GatewayError, match="Unknown proposal id"):
        wrong_project.get_proposal(proposal["proposal_id"])


def test_restart_recovery_rejects_project_id_reuse_between_receipt_and_board():
    gateway, fake = _gateway(allow_writes=True)
    proposal = gateway.propose_timeline_command({
        "kind": "create_lane",
        "expected_revision": fake.timelines[1]["revision"],
        "name": "Old project lane",
    })
    gateway.apply_proposal(proposal["proposal_id"])

    restarted, _ = _gateway(fake)
    replacement = {
        "project_id": 1,
        "revision": "9" * 64,
        "order_mode": "structural",
        "lanes": [{
            "id": 1,
            "name": "Replacement project lane",
            "color_label": "",
            "order_index": 0,
            "collapsed": False,
            "event_count": 0,
        }],
        "events": [],
        "off_timeline": [],
    }

    def replace_project_during_timeline_read(project_id=None):
        assert int(project_id or fake.require_project_id()) == 1
        fake.timeline_receipts.clear()
        fake.timelines[1] = copy.deepcopy(replacement)
        return copy.deepcopy(replacement)

    fake.get_timeline = replace_project_during_timeline_read
    with pytest.raises(GatewayError, match="project lifetime may have changed"):
        restarted.get_proposal(proposal["proposal_id"])


def test_unknown_proposal_receipt_miss_stays_unknown():
    gateway, fake = _gateway()
    before = len(fake.requests)
    with pytest.raises(GatewayError, match="Unknown proposal id"):
        gateway.get_proposal("not a valid capability")
    assert len(fake.requests) == before

    with pytest.raises(GatewayError, match="Unknown proposal id"):
        gateway.get_proposal("lfp_abcdefghijklmnopqrstuvwx")
    assert fake.requests[-1][:2] == (
        "GET",
        "/api/projects/1/timeline/command-receipt",
    )


def test_timeline_proposal_ignores_display_only_snapshot_changes_but_keeps_cas():
    gateway, fake = _gateway(allow_writes=True)
    proposal = gateway.propose_timeline_command({
        "kind": "create_lane",
        "expected_revision": fake.timelines[1]["revision"],
        "name": "Main",
    })

    # Scene titles are displayed by Timeline but intentionally do not belong
    # to its topology revision. A full-snapshot digest guard would reject this
    # otherwise safe lane command.
    fake.timelines[1]["off_timeline"][0]["title"] = "New display title"

    applied = gateway.apply_proposal(proposal["proposal_id"])
    assert applied["state"] == "applied"
    assert fake.timelines[1]["lanes"][0]["name"] == "Main"


def test_timeline_destructive_proposals_explain_that_scenes_are_preserved():
    gateway, fake = _gateway()
    fake.timelines[1].update({
        "lanes": [{
            "id": 301,
            "name": "Main",
            "color_label": "cyan",
            "order_index": 0,
            "collapsed": False,
            "event_count": 1,
        }],
        "events": [{
            "id": 11,
            "order_index": 1,
            "title": "Opening",
            "structural_number": "1",
            "act": "",
            "chapter": "",
            "plotline": "Main",
            "color_label": "",
            "lane_id": 301,
            "time_of_day": "",
            "location": "",
            "duration_minutes": 0,
            "character_states": [],
        }],
        "off_timeline": [],
    })
    revision = fake.timelines[1]["revision"]

    deleted_lane = gateway.propose_timeline_command({
        "kind": "delete_lane",
        "expected_revision": revision,
        "lane_id": 301,
    })
    removed_event = gateway.propose_timeline_command({
        "kind": "remove_event",
        "expected_revision": revision,
        "scene_id": 11,
    })
    moved_to_unassigned = gateway.propose_timeline_command({
        "kind": "place_event",
        "expected_revision": revision,
        "scene_id": 11,
        "lane_id": None,
    })

    assert deleted_lane["review"]["destructive"] is True
    assert deleted_lane["review"]["lane"]["member_scene_ids"] == {
        "items": [11], "total": 1, "truncated": 0,
    }
    assert "not deleted" in deleted_lane["review"]["effect"]
    assert removed_event["review"]["destructive"] is True
    assert "remains" in removed_event["review"]["effect"]
    assert moved_to_unassigned["review"]["changes_plotline"] is True
    assert moved_to_unassigned["review"]["before"][
        "one_based_display_order_index"
    ] == 1
    assert moved_to_unassigned["review"]["after_intent"][
        "zero_based_command_index"
    ] is None
    assert fake.timelines[1]["events"][0]["lane_id"] == 301


def test_timeline_lane_update_and_order_mode_proposals_preserve_exact_commands():
    gateway, fake = _gateway()
    fake.timelines[1]["lanes"] = [
        {
            "id": 301,
            "name": "Main",
            "color_label": "cyan",
            "order_index": 0,
            "collapsed": False,
            "event_count": 1,
        },
        {
            "id": 302,
            "name": "Secondary",
            "color_label": "",
            "order_index": 1,
            "collapsed": False,
            "event_count": 0,
        },
    ]
    fake.timelines[1]["events"] = [{
        "id": 11,
        "order_index": 1,
        "title": "Opening",
        "structural_number": "1",
        "act": "",
        "chapter": "",
        "plotline": "Main",
        "color_label": "",
        "lane_id": 301,
        "time_of_day": "",
        "location": "",
        "duration_minutes": 0,
        "character_states": [],
    }]
    fake.timelines[1]["off_timeline"] = []
    revision = fake.timelines[1]["revision"]

    update_command = {
        "kind": "update_lane",
        "expected_revision": revision,
        "lane_id": 301,
        "name": "Primary",
        "collapsed": True,
        "index": 1,
    }
    update = gateway.propose_timeline_command(update_command)
    custom = gateway.propose_timeline_command({
        "kind": "set_order_mode",
        "expected_revision": revision,
        "mode": "custom",
    })

    assert update["request"]["body"] == update_command
    assert update["review"]["changes"] == {
        "name": {"before": "Main", "after": "Primary"},
        "collapsed": {"before": False, "after": True},
        "index": {"before": 0, "after": 1},
    }
    assert update["review"]["lane"]["member_scene_ids"] == {
        "items": [11], "total": 1, "truncated": 0,
    }
    assert update["review"]["rename_updates_member_plotlines"] is True
    assert custom["request"]["body"]["mode"] == "custom"
    assert custom["review"]["before"]["order_mode"] == "structural"
    assert custom["review"]["after_intent"] == {
        "order_mode": "custom",
        "structural_mode_recomputes_effective_order": False,
    }
    assert fake.timelines[1]["order_mode"] == "structural"


def test_timeline_reviews_bound_legacy_snapshot_text():
    gateway, fake = _gateway()
    legacy_lane_name = "L" * 800
    legacy_plotline = "P" * 800
    fake.timelines[1].update({
        "lanes": [{
            "id": 301,
            "name": legacy_lane_name,
            "color_label": "cyan",
            "order_index": 0,
            "collapsed": False,
            "event_count": 0,
        }],
        "events": [{
            "id": 11,
            "order_index": 1,
            "title": "Opening",
            "structural_number": "1",
            "act": "",
            "chapter": "",
            "plotline": legacy_plotline,
            "color_label": "",
            "lane_id": None,
            "time_of_day": "",
            "location": "",
            "duration_minutes": 0,
            "character_states": [],
        }],
        "off_timeline": [],
    })
    revision = fake.timelines[1]["revision"]

    updated = gateway.propose_timeline_command({
        "kind": "update_lane",
        "expected_revision": revision,
        "lane_id": 301,
        "name": "Short",
    })
    placed = gateway.propose_timeline_command({
        "kind": "place_event",
        "expected_revision": revision,
        "scene_id": 11,
        "lane_id": 301,
    })

    assert updated["review"]["lane"]["name"] == "L" * 500 + "…"
    assert updated["review"]["changes"]["name"]["before"] == "L" * 500 + "…"
    assert legacy_lane_name not in updated["summary"]
    assert placed["review"]["before"]["plotline"] == "P" * 500 + "…"
    assert placed["review"]["after_intent"]["lane_name"] == "L" * 500 + "…"
    assert placed["review"]["after_intent"]["plotline"] == "L" * 500 + "…"
    assert legacy_lane_name not in placed["summary"]


@pytest.mark.parametrize(
    ("command", "message"),
    [
        (
            {
                "kind": "create_lane",
                "expected_revision": "A" * 64,
                "name": "Lane",
            },
            "exact 64-character lowercase revision",
        ),
        (
            {
                "kind": "create_lane",
                "expected_revision": "0" * 64,
                "name": "Lane",
            },
            "expected_revision does not match the current Timeline",
        ),
        (
            {
                "kind": "set_order_mode",
                "expected_revision": "1" * 64,
                "mode": "custom",
                "confirmed": True,
            },
            "Unexpected Timeline command field",
        ),
        (
            {
                "kind": "create_lane",
                "expected_revision": "1" * 64,
                "name": "Lane",
                "index": True,
            },
            "index must be a non-negative integer",
        ),
        (
            {
                "kind": "update_lane",
                "expected_revision": "1" * 64,
                "lane_id": 301,
                "index": None,
            },
            "index must be a non-negative integer",
        ),
        (
            {
                "kind": "place_event",
                "expected_revision": "1" * 64,
                "scene_id": 11,
            },
            "requires scene_id and lane_id",
        ),
        (
            {
                "kind": "remove_event",
                "expected_revision": "1" * 64,
                "scene_id": False,
            },
            "scene_id must be a positive integer",
        ),
        (
            {
                "kind": "set_order_mode",
                "expected_revision": "1" * 64,
                "mode": "random",
            },
            "mode must be 'structural' or 'custom'",
        ),
    ],
)
def test_timeline_tool_rejects_unscoped_or_ambiguous_commands(command, message):
    from logosforge.librechat.mcp_server import call_tool

    gateway, fake = _gateway()
    response = call_tool(
        gateway,
        "logosforge_propose_timeline_command",
        {"command": command},
    )

    assert response["ok"] is False
    assert message in response["error"]
    assert gateway.list_proposals() == {"proposals": []}
    assert not any(method == "POST" for method, _path, _body in fake.requests)


def test_snapshot_uses_canonical_cast_and_bounded_comment_summaries():
    gateway, _ = _gateway()

    snapshot = gateway.snapshot()
    assert snapshot["characters"] == [
        {"id": 91, "name": "Ada", "psyke_entry_id": 5},
    ]
    assert snapshot["comment_counts"] == {
        "total": 2,
        "open": 1,
        "resolved": 1,
    }
    assert snapshot["comments"][0]["id"] == 81
    assert snapshot["comments"][0]["revision"] == "a" * 64
    assert snapshot["comments"][0]["reply_count"] == 1
    assert "replies" not in snapshot["comments"][0]


def test_search_delegates_once_to_selected_project_and_preserves_comment_metadata():
    gateway, fake = _gateway()

    result = gateway.search("distant thunder")

    assert fake.search_calls == [(1, "distant thunder")]
    assert result == {
        "query": "distant thunder",
        "matches": [{
            "kind": "comment",
            "id": 81,
            "title": "Comment 81: Before",
            "excerpt": "Keep the distant thunder.",
            "revision": "a" * 64,
            "resolved": False,
        }],
        "limit": 100,
    }

    with pytest.raises(GatewayError, match="must not be empty"):
        gateway.search("   ")
    assert fake.search_calls == [(1, "distant thunder")]


def test_comment_reads_are_complete_filtered_and_paged():
    gateway, _ = _gateway()

    all_threads = gateway.list_comments(limit=1)
    assert all_threads["project_id"] == 1
    assert all_threads["total"] == 2
    assert all_threads["returned"] == 1
    assert all_threads["has_more"] is True
    assert all_threads["next_offset"] == 1
    assert all_threads["comments"][0]["replies"][0]["body"] == (
        "Keep the distant thunder."
    )

    open_threads = gateway.list_comments(False, limit=200, offset=0)
    assert open_threads["total"] == 1
    assert [comment["id"] for comment in open_threads["comments"]] == [81]
    assert open_threads["has_more"] is False

    with pytest.raises(GatewayError, match="between 1 and 200"):
        gateway.list_comments(limit=0)
    with pytest.raises(GatewayError, match="zero or greater"):
        gateway.list_comments(offset=-1)


def test_comment_proposals_are_exact_revision_bound_and_single_use():
    gateway, fake = _gateway(allow_writes=True)
    original = fake.comments[1][0]
    original_revision = original["revision"]
    original_reply_count = len(original["replies"])

    reply_proposal = gateway.propose_comment_reply(
        81, original_revision, "Try the image without dialogue.",
    )
    assert reply_proposal["state"] == "pending"
    assert reply_proposal["request"] == {
        "method": "POST",
        "path": "/api/projects/1/comments/81/replies",
        "body": {
            "body": "Try the image without dialogue.",
            "author": "MCP assistant",
            "expected_revision": original_revision,
        },
    }
    assert len(original["replies"]) == original_reply_count
    assert not any(method == "POST" for method, _path, _body in fake.requests)

    applied_reply = gateway.apply_proposal(reply_proposal["proposal_id"])
    assert applied_reply["state"] == "applied"
    assert fake.comments[1][0]["replies"][-1]["author"] == "MCP assistant"
    assert fake.comments[1][0]["replies"][-1]["body"] == (
        "Try the image without dialogue."
    )
    with pytest.raises(GatewayError, match="applied, not pending"):
        gateway.apply_proposal(reply_proposal["proposal_id"])

    current_revision = fake.comments[1][0]["revision"]
    resolution = gateway.propose_comment_resolution(
        81, current_revision, True,
    )
    assert resolution["request"]["body"] == {
        "resolved": True,
        "expected_revision": current_revision,
    }
    assert fake.comments[1][0]["resolved"] is False
    gateway.apply_proposal(resolution["proposal_id"])
    assert fake.comments[1][0]["resolved"] is True


def test_comment_proposals_fail_closed_on_invalid_noop_or_stale_state():
    gateway, fake = _gateway(allow_writes=True)
    revision = fake.comments[1][0]["revision"]

    with pytest.raises(GatewayError, match="must not be empty"):
        gateway.propose_comment_reply(81, revision, "   ")
    with pytest.raises(GatewayError, match="expected_revision"):
        gateway.propose_comment_reply(81, "0" * 64, "Reply")
    with pytest.raises(GatewayError, match="already open"):
        gateway.propose_comment_resolution(81, revision, False)
    with pytest.raises(LogosForgeApiError, match="not found"):
        gateway.propose_comment_reply(999, revision, "Reply")

    proposal = gateway.propose_comment_resolution(81, revision, True)
    # Another writer changes this exact thread after review but before apply.
    fake.comments[1][0]["body"] = "Newer writer edit"
    fake.comments[1][0]["revision"] = "c" * 64

    with pytest.raises(GatewayError, match="will not be retried"):
        gateway.apply_proposal(proposal["proposal_id"])
    assert fake.comments[1][0]["resolved"] is False
    failed = gateway.get_proposal(proposal["proposal_id"])
    assert failed["state"] == "failed"
    assert "comment_conflict" in failed["error"]


def test_comment_tool_handlers_reject_unscoped_fields_and_invalid_pages():
    from logosforge.librechat.mcp_server import call_tool

    gateway, fake = _gateway()
    listed = call_tool(
        gateway,
        "logosforge_list_comments",
        {"include_resolved": False, "limit": 1, "offset": 0},
    )
    assert listed["ok"] is True
    assert [item["id"] for item in listed["result"]["comments"]] == [81]

    invalid_page = call_tool(
        gateway, "logosforge_list_comments", {"limit": 0},
    )
    assert invalid_page == {
        "ok": False,
        "error": "'limit' must be between 1 and 200.",
    }
    unscoped_author = call_tool(
        gateway,
        "logosforge_propose_comment_reply",
        {
            "comment_id": 81,
            "expected_revision": fake.comments[1][0]["revision"],
            "body": "Reply",
            "author": "Impersonated writer",
        },
    )
    assert unscoped_author["ok"] is False
    assert "Unexpected argument" in unscoped_author["error"]


def test_search_tool_is_strict_project_scoped_and_bounded():
    from logosforge.librechat.mcp_server import call_tool

    gateway, fake = _gateway()
    found = call_tool(
        gateway, "logosforge_search", {"query": "distant thunder"},
    )
    assert found["ok"] is True
    assert found["result"]["matches"][0]["revision"] == "a" * 64
    assert fake.search_calls == [(1, "distant thunder")]

    blank = call_tool(gateway, "logosforge_search", {"query": "   "})
    assert blank == {"ok": False, "error": "'query' must be a non-empty string."}

    oversized = call_tool(gateway, "logosforge_search", {"query": "x" * 501})
    assert oversized == {
        "ok": False,
        "error": "'query' is too long (maximum 500 characters).",
    }

    unscoped = call_tool(
        gateway,
        "logosforge_search",
        {"query": "distant thunder", "project_id": 2},
    )
    assert unscoped["ok"] is False
    assert "Unexpected argument" in unscoped["error"]
    assert fake.search_calls == [(1, "distant thunder")]


def test_scene_proposal_does_not_mutate_and_requires_current_revision():
    gateway, fake = _gateway()

    with pytest.raises(GatewayError, match="expected_revision"):
        gateway.propose_scene_patch(11, "", {"title": "New"})
    with pytest.raises(GatewayError, match="expected_revision"):
        gateway.propose_scene_patch(11, "stale", {"title": "New"})

    proposal = gateway.propose_scene_patch(
        11, "rev-1", {"title": "New", "content": "After.\n"},
    )

    assert proposal["state"] == "pending"
    assert proposal["requires_user_approval"] is True
    assert proposal["request"]["body"]["expected_revision"] == "rev-1"
    assert proposal["request"]["body"]["content"]["length"] == len("After.\n")
    assert fake.scenes[1][11]["title"] == "Opening"
    assert not any(method == "PATCH" for method, _path, _body in fake.requests)


@pytest.mark.parametrize(
    ("allow_writes", "authenticated", "message"),
    [
        (False, True, "Writes are disabled"),
        (True, False, "authenticated LogosForge API"),
    ],
)
def test_apply_enforces_write_and_auth_gates(allow_writes, authenticated, message):
    fake = _FakeApiClient(authenticated=authenticated)
    gateway, _ = _gateway(fake, allow_writes=allow_writes)
    proposal = gateway.propose_scene_patch(11, "rev-1", {"title": "New"})

    with pytest.raises(GatewayError, match=message):
        gateway.apply_proposal(proposal["proposal_id"])

    assert fake.scenes[1][11]["title"] == "Opening"
    assert not any(method == "PATCH" for method, _path, _body in fake.requests)


def test_apply_uses_the_exact_stored_payload_once_and_replay_is_rejected():
    gateway, fake = _gateway(allow_writes=True)
    caller_patch = {"title": "Reviewed title", "content": "Reviewed prose.\n"}
    proposal = gateway.propose_scene_patch(11, "rev-1", caller_patch)
    caller_patch["title"] = "Changed after review"
    caller_patch["content"] = "Unreviewed prose.\n"

    applied = gateway.apply_proposal(proposal["proposal_id"])

    assert applied["state"] == "applied"
    assert fake.scenes[1][11]["title"] == "Reviewed title"
    assert fake.scenes[1][11]["content"] == "Reviewed prose.\n"
    patch_calls = [call for call in fake.requests if call[0] == "PATCH"]
    assert patch_calls == [
        (
            "PATCH",
            "/api/projects/1/scenes/11",
            {
                "title": "Reviewed title",
                "content": "Reviewed prose.\n",
                "expected_revision": "rev-1",
            },
        )
    ]

    with pytest.raises(GatewayError, match="applied, not pending"):
        gateway.apply_proposal(proposal["proposal_id"])
    assert len([call for call in fake.requests if call[0] == "PATCH"]) == 1


def test_digest_guard_rejects_a_stale_proposal_without_mutating():
    gateway, fake = _gateway(allow_writes=True)
    proposal = gateway.propose_patch_psyke_entry(5, {"name": "Ada Revised"})
    resource_path = "/api/projects/1/psyke/entries/5"

    # Simulate another client updating the record after the proposal review.
    fake.resources[resource_path]["notes"] = "Changed elsewhere"

    with pytest.raises(GatewayError, match="target changed"):
        gateway.apply_proposal(proposal["proposal_id"])

    assert fake.resources[resource_path]["name"] == "Ada"
    assert not any(
        method == "PATCH" and path == resource_path
        for method, path, _body in fake.requests
    )
    failed = gateway.get_proposal(proposal["proposal_id"])
    assert failed["state"] == "failed"
    assert "changed after" in failed["error"]


def test_expired_proposals_are_marked_failed_and_do_not_break_listing():
    gateway, _ = _gateway()
    proposal = gateway.propose_scene_patch(11, "rev-1", {"title": "Too late"})
    stored = gateway._proposals[proposal["proposal_id"]]
    stored.expires_at = time.time() - 1

    assert gateway.list_proposals() == {"proposals": []}
    finished = gateway.list_proposals(include_finished=True)["proposals"]
    assert len(finished) == 1
    assert finished[0]["state"] == "failed"
    assert "expired" in finished[0]["error"].lower()

    with pytest.raises(GatewayError, match="expired"):
        gateway.get_proposal(proposal["proposal_id"])


def test_discarded_proposal_cannot_be_applied():
    gateway, fake = _gateway(allow_writes=True)
    proposal = gateway.propose_scene_patch(11, "rev-1", {"title": "Discard me"})

    discarded = gateway.discard_proposal(proposal["proposal_id"])
    assert discarded["state"] == "discarded"
    with pytest.raises(GatewayError, match="discarded, not pending"):
        gateway.apply_proposal(proposal["proposal_id"])
    assert fake.scenes[1][11]["title"] == "Opening"


def test_apply_rejects_project_switch_and_internal_payload_tampering():
    gateway, fake = _gateway(allow_writes=True)
    proposal = gateway.propose_scene_patch(11, "rev-1", {"title": "Reviewed"})

    gateway.select_project(2)
    with pytest.raises(GatewayError, match="selected project differs"):
        gateway.apply_proposal(proposal["proposal_id"])
    assert fake.scenes[1][11]["title"] == "Opening"

    gateway.select_project(1)
    stored = gateway._proposals[proposal["proposal_id"]]
    stored.body["title"] = "Tampered"
    with pytest.raises(GatewayError, match="integrity check failed"):
        gateway.apply_proposal(proposal["proposal_id"])
    assert fake.scenes[1][11]["title"] == "Opening"
    assert gateway.get_proposal(proposal["proposal_id"])["state"] == "failed"


def test_proposal_deep_copies_nested_caller_data():
    gateway, fake = _gateway(allow_writes=True)
    body = {"name": "Nested", "details": {"role": "lead"}}
    proposal = gateway.propose_create_psyke_entry(body)
    body["details"]["role"] = "unreviewed"

    gateway.apply_proposal(proposal["proposal_id"])

    assert fake.requests[-1] == (
        "POST",
        "/api/projects/1/psyke/entries",
        {"name": "Nested", "details": {"role": "lead"}},
    )


def test_mcp_registry_has_unique_focused_tools_and_no_legacy_self_approval():
    from logosforge.librechat import mcp_server as server

    names = [spec.name for spec in server.TOOL_SPECS]
    assert len(names) == len(set(names)) == 40
    assert {
        "logosforge_get_timeline",
        "logosforge_propose_timeline_command",
        "logosforge_list_comments",
        "logosforge_propose_comment_reply",
        "logosforge_propose_comment_resolution",
    } <= set(names)
    assert "logosforge_apply_confirmed_action" not in names
    apply = server.HANDLERS["logosforge_apply_proposal"]
    assert apply.input_schema == server._obj(
        {"proposal_id": {"type": "string"}}, ["proposal_id"],
    )
    assert apply.read_only is False
    assert apply.destructive is True
    assert apply.idempotent is False
    assert server.HANDLERS[
        "logosforge_propose_comment_reply"
    ].idempotent is False
    assert server.HANDLERS[
        "logosforge_propose_comment_resolution"
    ].idempotent is False
    timeline_read = server.HANDLERS["logosforge_get_timeline"]
    assert timeline_read.read_only is True
    assert timeline_read.destructive is False
    assert timeline_read.idempotent is True
    timeline_proposal = server.HANDLERS[
        "logosforge_propose_timeline_command"
    ]
    assert timeline_proposal.read_only is True
    assert timeline_proposal.destructive is False
    assert timeline_proposal.idempotent is False
    variants = timeline_proposal.input_schema["properties"]["command"]["oneOf"]
    assert {variant["properties"]["kind"]["const"] for variant in variants} == {
        "create_lane", "update_lane", "delete_lane", "place_event",
        "remove_event", "set_order_mode",
    }
    assert all(variant["additionalProperties"] is False for variant in variants)
    update_variant = next(
        variant for variant in variants
        if variant["properties"]["kind"]["const"] == "update_lane"
    )
    assert update_variant["anyOf"] == [
        {"required": ["name"]},
        {"required": ["color_label"]},
        {"required": ["collapsed"]},
        {"required": ["index"]},
    ]
    search = server.HANDLERS["logosforge_search"]
    assert search.input_schema == server._obj(
        {"query": {"type": "string", "maxLength": 500}}, ["query"],
    )
    assert search.read_only is True
    assert search.destructive is False
    assert search.idempotent is True


def test_mcp_config_defaults_to_loopback_and_rejects_unsafe_remote_urls():
    from logosforge.librechat.mcp_server import McpConfig, McpToolError

    McpConfig().validate()
    with pytest.raises(McpToolError, match="Remote Pro APIs are disabled"):
        McpConfig(base_url="https://example.test").validate()
    with pytest.raises(McpToolError, match="requires HTTPS"):
        McpConfig(
            base_url="http://example.test",
            allow_remote=True,
            auth_token="secret",
        ).validate()
    with pytest.raises(McpToolError, match="requires HTTPS"):
        McpConfig(base_url="https://example.test", allow_remote=True).validate()
    McpConfig(
        base_url="https://example.test",
        allow_remote=True,
        auth_token="secret",
    ).validate()


def test_real_mcp_stdio_initializes_and_advertises_structured_tools():
    mcp = pytest.importorskip("mcp")
    from mcp.client.stdio import stdio_client

    async def exercise():
        params = mcp.StdioServerParameters(
            command=sys.executable,
            args=["-m", "logosforge.librechat.mcp_server"],
            cwd=str(Path(__file__).resolve().parents[1]),
            env={
                **os.environ,
                "LOGOSFORGE_API_URL": "http://127.0.0.1:1",
                "LOGOSFORGE_MCP_ALLOW_WRITES": "0",
            },
        )
        async with (
            stdio_client(params) as streams,
            mcp.ClientSession(*streams) as session,
        ):
            initialized = await session.initialize()
            listed = await session.list_tools()
            return initialized, listed

    initialized, listed = asyncio.run(exercise())
    assert initialized.serverInfo.name == "logosforge"
    assert initialized.serverInfo.version == "1.3.0"
    tools = {tool.name: tool for tool in listed.tools}
    assert len(tools) == 40
    assert {
        "logosforge_get_timeline",
        "logosforge_propose_timeline_command",
        "logosforge_list_comments",
        "logosforge_propose_comment_reply",
        "logosforge_propose_comment_resolution",
    } <= set(tools)
    assert tools["logosforge_get_scene"].outputSchema == {
        "type": "object",
        "properties": {
            "ok": {"type": "boolean"},
            "result": {},
            "error": {"type": "string"},
        },
        "required": ["ok"],
        "additionalProperties": False,
    }
    assert tools["logosforge_search"].inputSchema == {
        "type": "object",
        "properties": {
            "query": {"type": "string", "maxLength": 500},
        },
        "required": ["query"],
        "additionalProperties": False,
    }
    search_annotations = tools["logosforge_search"].annotations
    assert search_annotations.readOnlyHint is True
    assert search_annotations.destructiveHint is False
    assert search_annotations.idempotentHint is True
    assert search_annotations.openWorldHint is False
    timeline_annotations = tools["logosforge_get_timeline"].annotations
    assert timeline_annotations.readOnlyHint is True
    assert timeline_annotations.destructiveHint is False
    assert timeline_annotations.idempotentHint is True
    timeline_proposal_annotations = tools[
        "logosforge_propose_timeline_command"
    ].annotations
    assert timeline_proposal_annotations.readOnlyHint is True
    assert timeline_proposal_annotations.destructiveHint is False
    assert timeline_proposal_annotations.idempotentHint is False
    annotations = tools["logosforge_apply_proposal"].annotations
    assert annotations.readOnlyHint is False
    assert annotations.destructiveHint is True
    assert annotations.idempotentHint is False
    assert annotations.openWorldHint is False
