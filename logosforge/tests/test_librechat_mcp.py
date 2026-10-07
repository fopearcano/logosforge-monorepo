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
from logosforge.db.database import (
    KnowledgeGraphEdgeIdentity,
    _canvas_plot_command_request_digest,
    _continuity_command_request_digest,
    _knowledge_graph_command_request_digest,
    _timeline_command_request_digest,
)
from logosforge.librechat import api_client as ac
from logosforge.librechat.api_client import LogosForgeApiClient, LogosForgeApiError
from logosforge.librechat.mcp_gateway import (
    GatewayError,
    LogosForgeMcpGateway,
    _canvas_plot_receipt_request_digest,
    _continuity_receipt_request_digest,
    _knowledge_graph_receipt_request_digest,
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
        "story_flow": {
            "points": [],
            "warnings": [],
        },
        "mode_projection": {"kind": "novel"},
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
    assert result["story_flow"] == {"points": [], "warnings": []}
    assert result["mode_projection"] == {"kind": "novel"}


def test_api_client_get_canvas_plot_uses_authoritative_project_endpoint():
    client = LogosForgeApiClient(
        base_url="http://127.0.0.1:8765", project_id=7, auth_token="secret",
    )
    captured = {}
    canvas_plot = {
        "project_id": 7,
        "revision": "c" * 64,
        "nodes": [],
        "links": [],
        "frames": [],
    }

    def fake_urlopen(request, timeout=None):
        captured.update(
            url=request.full_url,
            method=request.get_method(),
            authorization=request.headers.get("Authorization"),
            timeout=timeout,
        )
        return _response(canvas_plot)

    with mock.patch.object(ac.urllib.request, "urlopen", fake_urlopen):
        result = client.get_canvas_plot()

    assert captured == {
        "url": "http://127.0.0.1:8765/api/projects/7/canvas-plot",
        "method": "GET",
        "authorization": "Bearer secret",
        "timeout": 15.0,
    }
    assert result == canvas_plot


def test_api_client_knowledge_graph_reads_preserve_bounded_queries():
    client = LogosForgeApiClient(
        base_url="http://127.0.0.1:8765", project_id=7, auth_token="secret",
    )
    captured: list[dict] = []

    def fake_urlopen(request, timeout=None):
        captured.append({
            "url": request.full_url,
            "method": request.get_method(),
            "authorization": request.headers.get("Authorization"),
            "timeout": timeout,
        })
        return _response({"project_id": 7})

    with mock.patch.object(ac.urllib.request, "urlopen", fake_urlopen):
        client.get_knowledge_graph(
            focus_key="scene:1",
            depth=2,
            limit=25,
            include_inferred=False,
            view_mode="revision_impact",
        )
        client.get_knowledge_graph_hidden_edges(offset=100, limit=50)

    graph_url = ac.urllib.parse.urlparse(captured[0]["url"])
    assert graph_url.path == "/api/projects/7/knowledge-graph"
    assert ac.urllib.parse.parse_qs(graph_url.query) == {
        "focus_key": ["scene:1"],
        "depth": ["2"],
        "limit": ["25"],
        "include_inferred": ["False"],
        "view_mode": ["revision_impact"],
    }
    hidden_url = ac.urllib.parse.urlparse(captured[1]["url"])
    assert hidden_url.path == "/api/projects/7/knowledge-graph/hidden-edges"
    assert ac.urllib.parse.parse_qs(hidden_url.query) == {
        "offset": ["100"],
        "limit": ["50"],
    }
    assert all(item["method"] == "GET" for item in captured)
    assert all(item["authorization"] == "Bearer secret" for item in captured)
    assert all(item["timeout"] == 15.0 for item in captured)


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


def test_api_client_canvas_receipt_keeps_idempotency_key_out_of_url():
    client = LogosForgeApiClient(
        base_url="http://127.0.0.1:8765", project_id=7, auth_token="secret",
    )
    proposal_id = "lfp_abcdefghijklmnopqrstuvwx"
    captured = {}
    receipt = {
        "project_id": 7,
        "request_digest": "a" * 64,
        "command_kind": "create_node",
        "expected_revision": "b" * 64,
        "applied_revision": "c" * 64,
        "original_changed": True,
        "original_affected_node_ids": [81],
        "original_affected_link_ids": [],
        "original_affected_frame_ids": [],
        "original_created_node_id": 81,
        "original_created_link_id": None,
        "original_created_frame_id": None,
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
        result = client.get_canvas_plot_command_receipt(proposal_id)

    assert captured["url"] == (
        "http://127.0.0.1:8765/api/projects/7/canvas-plot/command-receipt"
    )
    assert proposal_id not in captured["url"]
    assert captured["method"] == "GET"
    assert captured["headers"]["idempotency-key"] == proposal_id
    assert captured["headers"]["authorization"] == "Bearer secret"
    assert result == receipt


def test_api_client_graph_receipt_keeps_idempotency_key_out_of_url():
    client = LogosForgeApiClient(
        base_url="http://127.0.0.1:8765", project_id=7, auth_token="secret",
    )
    proposal_id = "lfp_abcdefghijklmnopqrstuvwx"
    captured = {}
    receipt = {
        "project_id": 7,
        "request_digest": "a" * 64,
        "command_kind": "hide_edge",
        "expected_revision": "b" * 64,
        "applied_revision": "c" * 64,
        "original_changed": True,
        "original_affected_edge": {
            "source": "scene:1",
            "target": "scene:2",
            "edge_type": "precedes",
        },
        "committed_at": "2026-10-06T10:00:00Z",
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
        result = client.get_knowledge_graph_command_receipt(proposal_id)

    assert captured["url"] == (
        "http://127.0.0.1:8765/api/projects/7/knowledge-graph/command-receipt"
    )
    assert proposal_id not in captured["url"]
    assert captured["method"] == "GET"
    assert captured["headers"]["idempotency-key"] == proposal_id
    assert captured["headers"]["authorization"] == "Bearer secret"
    assert result == receipt


def test_api_client_continuity_read_and_receipt_use_canonical_endpoints():
    client = LogosForgeApiClient(
        base_url="http://127.0.0.1:8765", project_id=7, auth_token="secret",
    )
    proposal_id = "lfp_abcdefghijklmnopqrstuvwx"
    captured: list[dict] = []
    report = {
        "project_id": 7,
        "review_revision": "a" * 64,
        "issues": [],
    }
    receipt = {
        "project_id": 7,
        "request_digest": "b" * 64,
        "command_kind": "resolve_issue",
        "expected_revision": "a" * 64,
        "applied_revision": "c" * 64,
        "original_changed": True,
        "original_affected_issue_id": "0123456789abcdef",
        "expected_issue_fingerprint": "d" * 64,
        "previous_status": "open",
        "status": "resolved",
        "committed_at": "2026-10-07T10:00:00Z",
    }

    def fake_urlopen(request, timeout=None):
        captured.append({
            "url": request.full_url,
            "method": request.get_method(),
            "headers": {
                key.lower(): value for key, value in request.header_items()
            },
            "timeout": timeout,
        })
        return _response(receipt if "command-receipt" in request.full_url else report)

    with mock.patch.object(ac.urllib.request, "urlopen", fake_urlopen):
        assert client.get_continuity() == report
        assert client.get_continuity_command_receipt(proposal_id) == receipt

    assert captured[0]["url"] == (
        "http://127.0.0.1:8765/api/projects/7/continuity"
    )
    assert "idempotency-key" not in captured[0]["headers"]
    assert captured[1]["url"] == (
        "http://127.0.0.1:8765/api/projects/7/continuity/command-receipt"
    )
    assert proposal_id not in captured[1]["url"]
    assert captured[1]["headers"]["idempotency-key"] == proposal_id
    assert all(item["method"] == "GET" for item in captured)
    assert all(item["headers"]["authorization"] == "Bearer secret" for item in captured)


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


def _canvas_request_digest(project_id: int, body: dict) -> str:
    geometry = {"x", "y", "width", "height"}
    raw = json.dumps(
        {
            "scope": "canvas-plot-command-v1",
            "project_id": project_id,
            "kind": body["kind"],
            "expected_revision": body["expected_revision"],
            "fields": {
                key: (
                    float(value)
                    if key in geometry
                    and isinstance(value, (int, float))
                    and not isinstance(value, bool)
                    else value
                )
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
        {
            "kind": "create_link",
            "expected_revision": "1" * 64,
            "source_scene_id": 11,
            "target_scene_id": 12,
            "link_type": "causality",
            "label": "therefore",
        },
        {
            "kind": "update_structure_link",
            "expected_revision": "2" * 64,
            "structure_link_id": 41,
            "target_type": "chapter",
            "target_ref": "Capitolo ∞",
        },
    ],
    ids=[
        "create-unicode-omitted-optionals",
        "update",
        "delete",
        "place-explicit-null-lane",
        "remove",
        "order-mode",
        "create-event-link",
        "update-structure-link",
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


@pytest.mark.parametrize(
    "body",
    [
        {
            "kind": "create_node",
            "expected_revision": "a" * 64,
            "title": "Card café ∞",
            "x": 1,
            "y": -2.5,
            "width": 180,
            "height": 110.0,
        },
        {
            "kind": "update_node",
            "expected_revision": "b" * 64,
            "node_id": 7,
            "x": 0.0,
            "scene_id": None,
        },
        {
            "kind": "create_frame",
            "expected_revision": "c" * 64,
            "x": -10,
            "y": 20,
            "width": 500,
            "height": 320,
        },
        {
            "kind": "delete_link",
            "expected_revision": "d" * 64,
            "link_id": 19,
        },
    ],
    ids=["create-node-float-wire", "update-node", "create-frame", "delete-link"],
)
def test_canvas_receipt_request_digest_matches_core_canonical_wire(body):
    fields = {
        key: (
            float(value)
            if key in {"x", "y", "width", "height"}
            and isinstance(value, (int, float))
            and not isinstance(value, bool)
            else value
        )
        for key, value in body.items()
        if key not in {"kind", "expected_revision"}
    }
    expected = _canvas_plot_command_request_digest(
        7,
        body["kind"],
        body["expected_revision"],
        fields,
    )
    assert _canvas_plot_receipt_request_digest(7, body) == expected
    assert _canvas_request_digest(7, body) == expected


@pytest.mark.parametrize("kind", ["confirm_edge", "hide_edge", "unhide_edge"])
def test_knowledge_graph_receipt_digest_matches_core_canonical_wire(kind):
    body = {
        "kind": kind,
        "expected_revision": "e" * 64,
        "source": "scene:1:café",
        "target": "scene:2:∞",
        "edge_type": "precedes",
    }
    expected = _knowledge_graph_command_request_digest(
        7,
        body["kind"],
        body["expected_revision"],
        KnowledgeGraphEdgeIdentity(
            source=body["source"],
            target=body["target"],
            edge_type=body["edge_type"],
        ),
    )
    assert _knowledge_graph_receipt_request_digest(7, body) == expected


@pytest.mark.parametrize(
    "kind",
    ["defer_issue", "dismiss_issue", "resolve_issue"],
)
def test_continuity_receipt_digest_matches_core_canonical_wire(kind):
    body = {
        "kind": kind,
        "expected_revision": "e" * 64,
        "issue_id": "0123456789abcdef",
        "expected_issue_fingerprint": "f" * 64,
    }
    expected = _continuity_command_request_digest(
        7,
        body["kind"],
        body["expected_revision"],
        body["issue_id"],
        body["expected_issue_fingerprint"],
    )
    assert _continuity_receipt_request_digest(7, body) == expected


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
                "links": [],
                "structure_links": [],
                "story_flow": {
                    "points": [],
                    "warnings": [],
                },
                "mode_projection": {"kind": "novel"},
            },
            2: {
                "project_id": 2,
                "revision": "2" * 64,
                "order_mode": "structural",
                "lanes": [],
                "events": [],
                "off_timeline": [],
                "links": [],
                "structure_links": [],
                "story_flow": {
                    "points": [],
                    "warnings": [],
                },
                "mode_projection": {"kind": "novel"},
            },
        }
        self._timeline_revision_sequence = 3
        self.timeline_receipts: dict[tuple[int, str], dict] = {}
        self.canvas_plots = {
            1: {
                "project_id": 1,
                "revision": "4" * 64,
                "nodes": [
                    {
                        "id": 501,
                        "title": "Opening beat",
                        "body": "A storm gathers.",
                        "x": 20.0,
                        "y": 30.0,
                        "width": 180.0,
                        "height": 110.0,
                        "color_label": "blue",
                        "group_label": "Act I",
                        "scene_id": 11,
                        "sort_order": 0,
                        "created_at": "2026-09-01T10:00:00Z",
                    },
                    {
                        "id": 502,
                        "title": "Decision",
                        "body": "Ada crosses the threshold.",
                        "x": 240.0,
                        "y": 30.0,
                        "width": 200.0,
                        "height": 120.0,
                        "color_label": "amber",
                        "group_label": "Act I",
                        "scene_id": None,
                        "sort_order": 1,
                        "created_at": "2026-09-01T10:01:00Z",
                    },
                    {
                        "id": 503,
                        "title": "Aftermath",
                        "body": "The cost becomes visible.",
                        "x": 460.0,
                        "y": 30.0,
                        "width": 180.0,
                        "height": 110.0,
                        "color_label": "red",
                        "group_label": "Act I",
                        "scene_id": None,
                        "sort_order": 2,
                        "created_at": "2026-09-01T10:01:30Z",
                    },
                ],
                "links": [{
                    "id": 601,
                    "source_node_id": 501,
                    "target_node_id": 502,
                    "label": "causes",
                    "color_label": "gray",
                    "link_type": "causal",
                    "created_at": "2026-09-01T10:02:00Z",
                }],
                "frames": [{
                    "id": 701,
                    "title": "Opening sequence",
                    "color_label": "violet",
                    "x": 0.0,
                    "y": 0.0,
                    "width": 480.0,
                    "height": 300.0,
                    "created_at": "2026-09-01T10:03:00Z",
                }],
            },
            2: {
                "project_id": 2,
                "revision": "5" * 64,
                "nodes": [],
                "links": [],
                "frames": [],
            },
        }
        self._canvas_plot_revision_sequence = 6
        self.canvas_plot_receipts: dict[tuple[int, str], dict] = {}
        graph_nodes = [
            {
                "key": "scene:scene:11",
                "node_type": "scene",
                "source_type": "scene",
                "source_id": "11",
                "label": "Opening",
                "summary": "Opening scene",
                "metadata": {},
                "degree": 1,
                "story_gravity": 0.6,
            },
            {
                "key": "scene:scene:12",
                "node_type": "scene",
                "source_type": "scene",
                "source_id": "12",
                "label": "Crossing",
                "summary": "Crossing scene",
                "metadata": {},
                "degree": 1,
                "story_gravity": 0.4,
            },
        ]
        graph_edge = {
            "source": "scene:scene:11",
            "target": "scene:scene:12",
            "edge_type": "precedes",
            "confidence": "likely",
            "provenance": "scene order",
            "source_system": "structure",
            "explanation": "The scenes are adjacent in manuscript order.",
            "is_user_confirmed": False,
            "is_inferred": True,
            "is_hidden": False,
            "metadata": {
                "story_order_index": 0,
                "story_order_total": 2,
                "story_order_band": "beginning",
                "act_boundary": False,
            },
        }
        self.knowledge_graphs = {
            1: {
                "project_id": 1,
                "revision": "7" * 64,
                "writing_mode": "novel",
                "focus_key": None,
                "depth": 1,
                "include_inferred": True,
                "view_mode": "project_map",
                "story_gravity_available": True,
                "story_diagnostics_available": True,
                "nodes": graph_nodes,
                "edges": [graph_edge],
                "node_count": 2,
                "edge_count": 1,
                "returned_node_count": 2,
                "returned_edge_count": 1,
                "truncated": False,
                "orphan_keys": [],
                "orphan_count": 0,
                "weak_links": [copy.deepcopy(graph_edge)],
                "weak_link_count": 1,
                "hidden_edges": [],
                "hidden_edge_count": 0,
                "warnings": [],
                "unavailable": [],
            },
            2: {
                "project_id": 2,
                "revision": "8" * 64,
                "writing_mode": "novel",
                "focus_key": None,
                "depth": 1,
                "include_inferred": True,
                "view_mode": "project_map",
                "story_gravity_available": True,
                "story_diagnostics_available": True,
                "nodes": [],
                "edges": [],
                "node_count": 0,
                "edge_count": 0,
                "returned_node_count": 0,
                "returned_edge_count": 0,
                "truncated": False,
                "orphan_keys": [],
                "orphan_count": 0,
                "weak_links": [],
                "weak_link_count": 0,
                "hidden_edges": [],
                "hidden_edge_count": 0,
                "warnings": [],
                "unavailable": [],
            },
        }
        self._knowledge_graph_revision_sequence = 9
        self.knowledge_graph_receipts: dict[tuple[int, str], dict] = {}
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

    def get_canvas_plot(self, project_id: int | None = None) -> dict:
        pid = int(project_id) if project_id is not None else self.require_project_id()
        return copy.deepcopy(self.canvas_plots[pid])

    def get_knowledge_graph(
        self,
        project_id: int | None = None,
        *,
        focus_key: str | None = None,
        depth: int = 1,
        limit: int = 100,
        include_inferred: bool = True,
        view_mode: str = "project_map",
    ) -> dict:
        del limit
        pid = int(project_id) if project_id is not None else self.require_project_id()
        graph = copy.deepcopy(self.knowledge_graphs[pid])
        graph["focus_key"] = focus_key
        graph["depth"] = depth
        graph["include_inferred"] = include_inferred
        graph["view_mode"] = view_mode
        if not include_inferred:
            graph["edges"] = [
                edge for edge in graph["edges"] if not edge["is_inferred"]
            ]
            graph["returned_edge_count"] = len(graph["edges"])
            graph["edge_count"] = len(graph["edges"])
            graph["weak_links"] = []
            graph["weak_link_count"] = 0
        return graph

    def get_knowledge_graph_hidden_edges(
        self,
        project_id: int | None = None,
        *,
        offset: int = 0,
        limit: int = 25,
    ) -> dict:
        pid = int(project_id) if project_id is not None else self.require_project_id()
        graph = self.knowledge_graphs[pid]
        edges = copy.deepcopy(graph["hidden_edges"][offset:offset + limit])
        endpoints = {
            key for edge in edges for key in (edge["source"], edge["target"])
        }
        nodes = [
            copy.deepcopy(node) for node in graph["nodes"]
            if node["key"] in endpoints
        ]
        return {
            "project_id": pid,
            "revision": graph["revision"],
            "offset": offset,
            "limit": limit,
            "hidden_edge_count": len(graph["hidden_edges"]),
            "returned_edge_count": len(edges),
            "nodes": nodes,
            "edges": edges,
        }

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

    def get_canvas_plot_command_receipt(
        self,
        idempotency_key: str,
        project_id: int | None = None,
    ) -> dict:
        pid = int(project_id) if project_id is not None else self.require_project_id()
        return self.request(
            "GET",
            self.project_path("canvas-plot/command-receipt", pid),
            idempotency_key=idempotency_key,
        )

    def get_knowledge_graph_command_receipt(
        self,
        idempotency_key: str,
        project_id: int | None = None,
    ) -> dict:
        pid = int(project_id) if project_id is not None else self.require_project_id()
        return self.request(
            "GET",
            self.project_path("knowledge-graph/command-receipt", pid),
            idempotency_key=idempotency_key,
        )

    def get_continuity_command_receipt(
        self,
        idempotency_key: str,
        project_id: int | None = None,
    ) -> dict:
        pid = int(project_id) if project_id is not None else self.require_project_id()
        return self.request(
            "GET",
            self.project_path("continuity/command-receipt", pid),
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
            if path.endswith("/canvas-plot/command-receipt"):
                project_id = int(path.split("/")[3])
                receipt = self.canvas_plot_receipts.get(
                    (project_id, idempotency_key)
                )
                if receipt is None:
                    raise LogosForgeApiError(
                        "Canvas Plot command receipt not found",
                        status_code=404,
                        error_code="canvas_plot_receipt_not_found",
                    )
                return copy.deepcopy(receipt)
            if path.endswith("/knowledge-graph/command-receipt"):
                project_id = int(path.split("/")[3])
                receipt = self.knowledge_graph_receipts.get(
                    (project_id, idempotency_key)
                )
                if receipt is None:
                    raise LogosForgeApiError(
                        "Knowledge Graph command receipt not found",
                        status_code=404,
                        error_code="knowledge_graph_receipt_not_found",
                    )
                return copy.deepcopy(receipt)
            if path.endswith("/continuity/command-receipt"):
                raise LogosForgeApiError(
                    "Continuity command receipt not found",
                    status_code=404,
                    error_code="continuity_receipt_not_found",
                )
            if path == "/api/projects/1/timeline":
                return self.get_timeline(1)
            if path == "/api/projects/1/canvas-plot":
                return self.get_canvas_plot(1)
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
                    "affected_link_ids": [],
                    "affected_structure_link_ids": [],
                    "created_link_id": None,
                    "created_structure_link_id": None,
                }
            if body.get("expected_revision") != timeline["revision"]:
                raise LogosForgeApiError(
                    "HTTP 409: The Timeline changed.",
                    status_code=409,
                    error_code="timeline_conflict",
                )
            affected_link_ids: list[int] = []
            created_link_id: int | None = None
            if body.get("kind") == "create_lane":
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
            elif body.get("kind") == "create_link":
                created_link_id = 401 + len(timeline["links"])
                timeline["links"].append({
                    "id": created_link_id,
                    "source_scene_id": body["source_scene_id"],
                    "target_scene_id": body["target_scene_id"],
                    "link_type": body.get("link_type", "custom"),
                    "color_label": body.get("color_label", "gray"),
                    "label": body.get("label", ""),
                    "created_at": "2026-10-07T10:00:00Z",
                })
                affected_link_ids.append(created_link_id)
            else:
                raise LogosForgeApiError("unsupported fake Timeline command")
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
                    "original_affected_link_ids": affected_link_ids,
                    "original_affected_structure_link_ids": [],
                    "original_created_link_id": created_link_id,
                    "original_created_structure_link_id": None,
                    "committed_at": "2026-10-04T10:00:00Z",
                }
            return {
                "timeline": copy.deepcopy(timeline),
                "replayed": False,
                "applied_revision": timeline["revision"],
                "changed": True,
                "affected_scene_ids": [],
                "affected_link_ids": affected_link_ids,
                "affected_structure_link_ids": [],
                "created_link_id": created_link_id,
                "created_structure_link_id": None,
            }

        if method == "POST" and path == "/api/projects/1/canvas-plot/commands":
            canvas_plot = self.canvas_plots[1]
            assert body is not None
            receipt_key = (1, idempotency_key)
            if idempotency_key and receipt_key in self.canvas_plot_receipts:
                receipt = self.canvas_plot_receipts[receipt_key]
                if receipt["request_digest"] != _canvas_request_digest(1, body):
                    raise LogosForgeApiError(
                        "Idempotency-Key was reused",
                        status_code=409,
                        error_code="idempotency_key_conflict",
                    )
                return {
                    "canvas_plot": copy.deepcopy(canvas_plot),
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
            if body.get("expected_revision") != canvas_plot["revision"]:
                raise LogosForgeApiError(
                    "HTTP 409: The Canvas Plot changed.",
                    status_code=409,
                    error_code="canvas_plot_conflict",
                )
            if body.get("kind") != "create_node":
                raise LogosForgeApiError("unsupported fake Canvas Plot command")
            created_node_id = 504 + max(0, len(canvas_plot["nodes"]) - 3)
            node = {
                "id": created_node_id,
                "title": body.get("title", ""),
                "body": body.get("body", ""),
                "x": body.get("x", 0.0),
                "y": body.get("y", 0.0),
                "width": body.get("width", 180.0),
                "height": body.get("height", 110.0),
                "color_label": body.get("color_label", ""),
                "group_label": body.get("group_label", ""),
                "scene_id": body.get("scene_id"),
                "sort_order": len(canvas_plot["nodes"]),
                "created_at": "2026-09-01T11:00:00Z",
            }
            index = body.get("index")
            if index is None:
                index = len(canvas_plot["nodes"])
            canvas_plot["nodes"].insert(index, node)
            for sort_order, row in enumerate(canvas_plot["nodes"]):
                row["sort_order"] = sort_order
            canvas_plot["revision"] = (
                f"{self._canvas_plot_revision_sequence:064x}"
            )
            self._canvas_plot_revision_sequence += 1
            if idempotency_key:
                self.canvas_plot_receipts[receipt_key] = {
                    "project_id": 1,
                    "request_digest": _canvas_request_digest(1, body),
                    "command_kind": body["kind"],
                    "expected_revision": body["expected_revision"],
                    "applied_revision": canvas_plot["revision"],
                    "original_changed": True,
                    "original_affected_node_ids": [created_node_id],
                    "original_affected_link_ids": [],
                    "original_affected_frame_ids": [],
                    "original_created_node_id": created_node_id,
                    "original_created_link_id": None,
                    "original_created_frame_id": None,
                    "committed_at": "2026-10-04T10:00:00Z",
                }
            return {
                "canvas_plot": copy.deepcopy(canvas_plot),
                "replayed": False,
                "applied_revision": canvas_plot["revision"],
                "changed": True,
                "affected_node_ids": [created_node_id],
                "affected_link_ids": [],
                "affected_frame_ids": [],
                "created_node_id": created_node_id,
                "created_link_id": None,
                "created_frame_id": None,
            }

        if method == "POST" and path == "/api/projects/1/knowledge-graph/commands":
            graph = self.knowledge_graphs[1]
            assert body is not None
            receipt_key = (1, idempotency_key)
            request_digest = _knowledge_graph_receipt_request_digest(1, body)
            if idempotency_key and receipt_key in self.knowledge_graph_receipts:
                receipt = self.knowledge_graph_receipts[receipt_key]
                if receipt["request_digest"] != request_digest:
                    raise LogosForgeApiError(
                        "Idempotency-Key was reused",
                        status_code=409,
                        error_code="idempotency_key_conflict",
                    )
                return {
                    "knowledge_graph": copy.deepcopy(graph),
                    "replayed": True,
                    "applied_revision": receipt["applied_revision"],
                    "changed": False,
                    "affected_edge": copy.deepcopy(
                        receipt["original_affected_edge"]
                    ),
                }
            if body.get("expected_revision") != graph["revision"]:
                raise LogosForgeApiError(
                    "HTTP 409: Knowledge Graph review state changed",
                    status_code=409,
                    error_code="knowledge_graph_conflict",
                )
            identity = {
                key: body[key] for key in ("source", "target", "edge_type")
            }

            def matches(edge):
                return all(edge.get(key) == value for key, value in identity.items())

            kind = body.get("kind")
            if kind in {"confirm_edge", "hide_edge"}:
                edge = next((row for row in graph["edges"] if matches(row)), None)
                if edge is None:
                    raise LogosForgeApiError(
                        "Knowledge Graph edge not found",
                        status_code=404,
                        error_code="not_found",
                    )
                if kind == "confirm_edge":
                    edge.update({
                        "confidence": "confirmed",
                        "is_user_confirmed": True,
                        "is_inferred": False,
                    })
                    graph["weak_links"] = [
                        row for row in graph["weak_links"] if not matches(row)
                    ]
                else:
                    graph["edges"] = [
                        row for row in graph["edges"] if not matches(row)
                    ]
                    graph["weak_links"] = [
                        row for row in graph["weak_links"] if not matches(row)
                    ]
                    hidden = copy.deepcopy(edge)
                    hidden["is_hidden"] = True
                    graph["hidden_edges"].append(hidden)
            elif kind == "unhide_edge":
                edge = next(
                    (row for row in graph["hidden_edges"] if matches(row)), None,
                )
                if edge is None:
                    raise LogosForgeApiError(
                        "Knowledge Graph edge not found",
                        status_code=404,
                        error_code="not_found",
                    )
                graph["hidden_edges"] = [
                    row for row in graph["hidden_edges"] if not matches(row)
                ]
                visible = copy.deepcopy(edge)
                visible["is_hidden"] = False
                graph["edges"].append(visible)
                if visible["is_inferred"]:
                    graph["weak_links"].append(copy.deepcopy(visible))
            else:
                raise LogosForgeApiError("unsupported fake Knowledge Graph command")

            graph["revision"] = (
                f"{self._knowledge_graph_revision_sequence:064x}"
            )
            self._knowledge_graph_revision_sequence += 1
            graph["edge_count"] = len(graph["edges"])
            graph["returned_edge_count"] = len(graph["edges"])
            graph["hidden_edge_count"] = len(graph["hidden_edges"])
            graph["weak_link_count"] = len(graph["weak_links"])
            if idempotency_key:
                self.knowledge_graph_receipts[receipt_key] = {
                    "project_id": 1,
                    "request_digest": request_digest,
                    "command_kind": kind,
                    "expected_revision": body["expected_revision"],
                    "applied_revision": graph["revision"],
                    "original_changed": True,
                    "original_affected_edge": identity,
                    "committed_at": "2026-10-06T10:00:00Z",
                }
            return {
                "knowledge_graph": copy.deepcopy(graph),
                "replayed": False,
                "applied_revision": graph["revision"],
                "changed": True,
                "affected_edge": identity,
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


def test_canvas_plot_read_and_proposal_apply_are_revision_bound_and_single_use():
    gateway, fake = _gateway(allow_writes=True)
    compact = gateway.get_canvas_plot()
    compact_node = compact["nodes"][0]
    assert "body" not in compact_node
    assert compact_node["body_length"] == len("A storm gathers.")
    assert compact_node["body_preview"] == "A storm gathers."
    assert len(compact_node["body_sha256"]) == 64

    current = gateway.get_canvas_plot(include_bodies=True)
    assert current == fake.canvas_plots[1]

    command = {
        "kind": "create_node",
        "expected_revision": current["revision"],
        "title": "Hidden motive",
        "body": "Ada withholds the letter.",
        "x": 120.5,
        "y": -30.0,
        "width": 210.0,
        "height": 140.0,
        "color_label": "indigo",
        "group_label": "Act II",
        "scene_id": 11,
        "index": 1,
    }
    first = gateway.propose_canvas_plot_command(command)
    stale_sibling = gateway.propose_canvas_plot_command({
        "kind": "create_node",
        "expected_revision": current["revision"],
        "title": "Stale sibling",
    })

    assert first["state"] == stale_sibling["state"] == "pending"
    assert first["request"] == {
        "method": "POST",
        "path": "/api/projects/1/canvas-plot/commands",
        "body": command,
    }
    assert first["review"]["canvas_plot_revision"] == "4" * 64
    assert first["review"]["command_kind"] == "create_node"
    assert first["review"]["destructive"] is False
    assert [node["id"] for node in fake.canvas_plots[1]["nodes"]] == [
        501, 502, 503,
    ]
    assert not any(
        method == "POST" and path.endswith("/canvas-plot/commands")
        for method, path, _body in fake.requests
    )

    applied = gateway.apply_proposal(first["proposal_id"])
    assert applied["state"] == "applied"
    assert [node["title"] for node in fake.canvas_plots[1]["nodes"]] == [
        "Opening beat", "Hidden motive", "Decision", "Aftermath",
    ]
    assert applied["result"]["changed"] is True
    assert applied["result"]["created_node_id"] == 504
    assert fake.requests[-1] == (
        "POST",
        "/api/projects/1/canvas-plot/commands",
        command,
    )
    assert fake.request_idempotency_keys[-1] == (
        "POST",
        "/api/projects/1/canvas-plot/commands",
        first["proposal_id"],
    )

    with pytest.raises(GatewayError, match="canvas_plot_conflict.*will not be retried"):
        gateway.apply_proposal(stale_sibling["proposal_id"])
    assert gateway.get_proposal(stale_sibling["proposal_id"])["state"] == "failed"
    assert [node["title"] for node in fake.canvas_plots[1]["nodes"]] == [
        "Opening beat", "Hidden motive", "Decision", "Aftermath",
    ]

    with pytest.raises(GatewayError, match="applied, not pending"):
        gateway.apply_proposal(first["proposal_id"])


def test_canvas_plot_all_nine_commands_preserve_the_exact_reviewed_payload():
    gateway, fake = _gateway()
    revision = fake.canvas_plots[1]["revision"]
    commands = [
        {
            "kind": "create_node",
            "expected_revision": revision,
            "title": "New card",
            "body": "Draft text",
            "x": 1.25,
            "y": -2.5,
            "width": 181.0,
            "height": 111.0,
            "color_label": "green",
            "group_label": "Act II",
            "scene_id": 11,
            "index": 3,
        },
        {
            "kind": "update_node",
            "expected_revision": revision,
            "node_id": 501,
            "title": "Opening image",
            "body": "Rain needles the empty road.",
            "x": 21.0,
            "y": 31.0,
            "width": 190.0,
            "height": 115.0,
            "color_label": "cyan",
            "group_label": "Act One",
            "scene_id": None,
            "index": 1,
        },
        {
            "kind": "delete_node",
            "expected_revision": revision,
            "node_id": 502,
        },
        {
            "kind": "create_link",
            "expected_revision": revision,
            "source_node_id": 501,
            "target_node_id": 503,
            "label": "foreshadows",
            "color_label": "orange",
            "link_type": "thematic",
        },
        {
            "kind": "update_link",
            "expected_revision": revision,
            "link_id": 601,
            "label": "forces",
            "color_label": "black",
            "link_type": "conflict",
        },
        {
            "kind": "delete_link",
            "expected_revision": revision,
            "link_id": 601,
        },
        {
            "kind": "create_frame",
            "expected_revision": revision,
            "title": "Act II",
            "color_label": "green",
            "x": 10.0,
            "y": 20.0,
            "width": 500.0,
            "height": 320.0,
        },
        {
            "kind": "update_frame",
            "expected_revision": revision,
            "frame_id": 701,
            "title": "Opening movement",
            "color_label": "purple",
            "x": -10.0,
            "y": -20.0,
            "width": 520.0,
            "height": 340.0,
        },
        {
            "kind": "delete_frame",
            "expected_revision": revision,
            "frame_id": 701,
        },
    ]

    proposals = [gateway.propose_canvas_plot_command(command) for command in commands]

    assert [proposal["operation"] for proposal in proposals] == [
        f"canvas_plot_{command['kind']}" for command in commands
    ]
    assert [proposal["request"]["body"] for proposal in proposals] == commands
    assert all(
        proposal["request"]["path"]
        == "/api/projects/1/canvas-plot/commands"
        for proposal in proposals
    )
    assert all(proposal["state"] == "pending" for proposal in proposals)
    assert fake.canvas_plots[1]["revision"] == revision
    assert len(fake.canvas_plots[1]["nodes"]) == 3
    assert len(fake.canvas_plots[1]["links"]) == 1
    assert len(fake.canvas_plots[1]["frames"]) == 1
    assert not any(method == "POST" for method, _path, _body in fake.requests)


def test_canvas_plot_destructive_reviews_name_the_exact_blast_radius():
    gateway, fake = _gateway()
    revision = fake.canvas_plots[1]["revision"]

    deleted_node = gateway.propose_canvas_plot_command({
        "kind": "delete_node",
        "expected_revision": revision,
        "node_id": 501,
    })
    deleted_link = gateway.propose_canvas_plot_command({
        "kind": "delete_link",
        "expected_revision": revision,
        "link_id": 601,
    })
    deleted_frame = gateway.propose_canvas_plot_command({
        "kind": "delete_frame",
        "expected_revision": revision,
        "frame_id": 701,
    })

    assert deleted_node["review"]["destructive"] is True
    assert deleted_node["review"]["requires_destructive_confirmation"] is True
    assert deleted_node["review"]["node"] == {
        "id": 501,
        "title": "Opening beat",
        "scene_id": 11,
    }
    assert deleted_node["review"]["incident_link_ids"] == {
        "items": [601], "total": 1, "truncated": 0,
    }
    assert "scene remains unchanged" in deleted_node["review"]["effect"]

    assert deleted_link["review"]["destructive"] is True
    assert deleted_link["review"]["link"] == {
        "id": 601,
        "source_node_id": 501,
        "target_node_id": 502,
        "label": "causes",
    }
    assert "legacy reverse or duplicate rows" in deleted_link["review"]["effect"]
    assert "Nodes and manuscript scenes remain unchanged" in (
        deleted_link["review"]["effect"]
    )

    assert deleted_frame["review"]["destructive"] is True
    assert deleted_frame["review"]["frame"] == {
        "id": 701,
        "title": "Opening sequence",
    }
    assert "nodes, links" in deleted_frame["review"]["effect"]
    assert "manuscript scenes remain unchanged" in deleted_frame["review"]["effect"]

    assert len(fake.canvas_plots[1]["nodes"]) == 3
    assert len(fake.canvas_plots[1]["links"]) == 1
    assert len(fake.canvas_plots[1]["frames"]) == 1


@pytest.mark.parametrize(
    ("command", "message"),
    [
        (
            {
                "kind": "update_node",
                "expected_revision": "4" * 64,
                "node_id": 501,
                "title": "Opening beat",
            },
            "node update would not change",
        ),
        (
            {
                "kind": "update_link",
                "expected_revision": "4" * 64,
                "link_id": 601,
                "color_label": "gray",
            },
            "link update would not change",
        ),
        (
            {
                "kind": "update_frame",
                "expected_revision": "4" * 64,
                "frame_id": 701,
                "title": "Opening sequence",
            },
            "frame update would not change",
        ),
        (
            {
                "kind": "create_link",
                "expected_revision": "4" * 64,
                "source_node_id": 502,
                "target_node_id": 501,
            },
            "already linked",
        ),
        (
            {
                "kind": "create_link",
                "expected_revision": "4" * 64,
                "source_node_id": 501,
                "target_node_id": 501,
            },
            "cannot connect a node to itself",
        ),
    ],
    ids=[
        "node-update", "link-update", "frame-update", "duplicate-link",
        "self-link",
    ],
)
def test_canvas_plot_noop_commands_are_rejected_before_proposal(command, message):
    gateway, fake = _gateway()

    with pytest.raises(GatewayError, match=message):
        gateway.propose_canvas_plot_command(command)
    assert gateway.list_proposals() == {"proposals": []}
    assert not any(method == "POST" for method, _path, _body in fake.requests)


def test_knowledge_graph_all_review_actions_are_revision_bound_and_single_use():
    gateway, fake = _gateway(allow_writes=True)
    initial = gateway.get_knowledge_graph()
    edge = initial["edges"][0]
    identity = {
        key: edge[key] for key in ("source", "target", "edge_type")
    }
    hide_command = {
        "kind": "hide_edge",
        "expected_revision": initial["revision"],
        **identity,
    }
    hide = gateway.propose_knowledge_graph_command(hide_command)
    stale_confirm = gateway.propose_knowledge_graph_command({
        **hide_command,
        "kind": "confirm_edge",
    })

    assert hide["state"] == "pending"
    assert hide["request"] == {
        "method": "POST",
        "path": "/api/projects/1/knowledge-graph/commands",
        "body": hide_command,
    }
    assert hide["review"]["command_kind"] == "hide_edge"
    assert hide["review"]["destructive"] is True
    assert hide["review"]["source"]["key"] == identity["source"]
    assert hide["review"]["target"]["key"] == identity["target"]
    assert fake.knowledge_graphs[1]["hidden_edges"] == []

    hidden = gateway.apply_proposal(hide["proposal_id"])
    assert hidden["state"] == "applied"
    assert hidden["result"]["changed"] is True
    assert hidden["result"]["replayed"] is False
    assert hidden["result"]["affected_edge"] == identity
    assert hidden["result"]["knowledge_graph"]["hidden_edge_count"] == 1
    assert fake.request_idempotency_keys[-1] == (
        "POST",
        "/api/projects/1/knowledge-graph/commands",
        hide["proposal_id"],
    )

    with pytest.raises(GatewayError, match="HTTP 409.*Knowledge Graph"):
        gateway.apply_proposal(stale_confirm["proposal_id"])
    assert gateway.get_proposal(stale_confirm["proposal_id"])["state"] == "failed"
    with pytest.raises(GatewayError, match="not pending"):
        gateway.apply_proposal(hide["proposal_id"])

    hidden_page = gateway.get_knowledge_graph_hidden_edges(offset=0, limit=100)
    unhide_command = {
        "kind": "unhide_edge",
        "expected_revision": hidden_page["revision"],
        **identity,
    }
    with pytest.raises(GatewayError, match="requires.*hidden_edge_offset"):
        gateway.propose_knowledge_graph_command(unhide_command)
    restored_proposal = gateway.propose_knowledge_graph_command(
        unhide_command,
        hidden_edge_offset=0,
    )
    assert restored_proposal["review"]["hidden_edge_offset"] == 0
    restored = gateway.apply_proposal(restored_proposal["proposal_id"])
    assert restored["result"]["affected_edge"] == identity
    assert restored["result"]["knowledge_graph"]["hidden_edge_count"] == 0

    restored_graph = restored["result"]["knowledge_graph"]
    confirm_command = {
        "kind": "confirm_edge",
        "expected_revision": restored_graph["revision"],
        **identity,
    }
    with pytest.raises(GatewayError, match="only for unhide_edge"):
        gateway.propose_knowledge_graph_command(
            confirm_command,
            hidden_edge_offset=0,
        )
    confirm_proposal = gateway.propose_knowledge_graph_command(confirm_command)
    confirmed = gateway.apply_proposal(confirm_proposal["proposal_id"])
    confirmed_edge = next(
        row for row in confirmed["result"]["knowledge_graph"]["edges"]
        if all(row[key] == value for key, value in identity.items())
    )
    assert confirmed_edge["is_user_confirmed"] is True
    assert confirmed_edge["is_inferred"] is False
    assert confirmed_edge["confidence"] == "confirmed"
    assert {
        receipt["command_kind"]
        for receipt in fake.knowledge_graph_receipts.values()
    } == {"hide_edge", "unhide_edge", "confirm_edge"}


@pytest.mark.parametrize("status_code", [None, 500], ids=["no-response", "server-error"])
def test_knowledge_graph_ambiguous_apply_recovers_committed_receipt(status_code):
    gateway, fake = _gateway(allow_writes=True)
    current = gateway.get_knowledge_graph()
    edge = current["edges"][0]
    proposal = gateway.propose_knowledge_graph_command({
        "kind": "hide_edge",
        "expected_revision": current["revision"],
        "source": edge["source"],
        "target": edge["target"],
        "edge_type": edge["edge_type"],
    })
    request = fake.request
    post_keys = []

    def commit_then_lose_response(
        method, path, body=None, query=None, *, idempotency_key="",
    ):
        result = request(
            method, path, body, query, idempotency_key=idempotency_key,
        )
        if method == "POST" and path.endswith("/knowledge-graph/commands"):
            post_keys.append(idempotency_key)
            del result
            raise LogosForgeApiError(
                "connection reset after request",
                status_code=status_code,
            )
        return result

    fake.request = commit_then_lose_response
    applied = gateway.apply_proposal(proposal["proposal_id"])

    assert applied["state"] == "applied"
    assert applied["recovered_from_core"] is True
    assert applied["result"]["replayed"] is True
    assert applied["result"]["changed"] is False
    assert applied["result"]["affected_edge"] == {
        key: edge[key] for key in ("source", "target", "edge_type")
    }
    assert applied["result"]["knowledge_graph"] == fake.knowledge_graphs[1]
    assert applied["receipt"]["command_kind"] == "hide_edge"
    assert post_keys == [proposal["proposal_id"]]
    assert fake.knowledge_graphs[1]["hidden_edge_count"] == 1


def test_knowledge_graph_receipt_miss_allows_one_same_key_resend():
    gateway, fake = _gateway(allow_writes=True)
    current = gateway.get_knowledge_graph()
    edge = current["edges"][0]
    proposal = gateway.propose_knowledge_graph_command({
        "kind": "hide_edge",
        "expected_revision": current["revision"],
        "source": edge["source"],
        "target": edge["target"],
        "edge_type": edge["edge_type"],
    })
    request = fake.request
    post_keys = []

    def lose_first_before_commit(
        method, path, body=None, query=None, *, idempotency_key="",
    ):
        if method == "POST" and path.endswith("/knowledge-graph/commands"):
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
    assert fake.knowledge_graphs[1]["hidden_edge_count"] == 1


@pytest.mark.parametrize(
    ("family", "command_suffix", "receipt_suffix"),
    [
        ("timeline", "/timeline/commands", "/timeline/command-receipt"),
        ("canvas", "/canvas-plot/commands", "/canvas-plot/command-receipt"),
        (
            "knowledge_graph",
            "/knowledge-graph/commands",
            "/knowledge-graph/command-receipt",
        ),
    ],
)
def test_successful_null_receipt_never_authorizes_a_resend(
    family,
    command_suffix,
    receipt_suffix,
):
    gateway, fake = _gateway(allow_writes=True)
    if family == "timeline":
        proposal = gateway.propose_timeline_command({
            "kind": "create_lane",
            "expected_revision": fake.timelines[1]["revision"],
            "name": "Null receipt",
        })
    elif family == "canvas":
        proposal = gateway.propose_canvas_plot_command({
            "kind": "create_node",
            "expected_revision": fake.canvas_plots[1]["revision"],
            "title": "Null receipt",
        })
    else:
        current = gateway.get_knowledge_graph()
        edge = current["edges"][0]
        proposal = gateway.propose_knowledge_graph_command({
            "kind": "hide_edge",
            "expected_revision": current["revision"],
            "source": edge["source"],
            "target": edge["target"],
            "edge_type": edge["edge_type"],
        })

    request = fake.request
    post_count = 0

    def return_null_receipt_after_ambiguous_post(
        method, path, body=None, query=None, *, idempotency_key="",
    ):
        nonlocal post_count
        if method == "POST" and path.endswith(command_suffix):
            post_count += 1
            raise LogosForgeApiError("connection reset before commit")
        if method == "GET" and path.endswith(receipt_suffix):
            return None
        return request(
            method, path, body, query, idempotency_key=idempotency_key,
        )

    fake.request = return_null_receipt_after_ambiguous_post
    with pytest.raises(GatewayError, match="indeterminate"):
        gateway.apply_proposal(proposal["proposal_id"])

    assert post_count == 1
    assert gateway.get_proposal(proposal["proposal_id"])["state"] == "indeterminate"


def test_knowledge_graph_recovery_pending_never_resends_more_than_once():
    gateway, fake = _gateway(allow_writes=True)
    current = gateway.get_knowledge_graph()
    edge = current["edges"][0]
    proposal = gateway.propose_knowledge_graph_command({
        "kind": "hide_edge",
        "expected_revision": current["revision"],
        "source": edge["source"],
        "target": edge["target"],
        "edge_type": edge["edge_type"],
    })
    request = fake.request
    post_keys = []

    def lose_all_posts(
        method, path, body=None, query=None, *, idempotency_key="",
    ):
        if method == "POST" and path.endswith("/knowledge-graph/commands"):
            post_keys.append(idempotency_key)
            raise LogosForgeApiError("connection reset before commit")
        return request(
            method, path, body, query, idempotency_key=idempotency_key,
        )

    fake.request = lose_all_posts
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
    assert fake.knowledge_graphs[1]["hidden_edge_count"] == 0


def test_graph_observed_receipt_blocks_resend_after_fresh_map_failure():
    gateway, fake = _gateway(allow_writes=True)
    current = gateway.get_knowledge_graph()
    edge = current["edges"][0]
    proposal = gateway.propose_knowledge_graph_command({
        "kind": "hide_edge",
        "expected_revision": current["revision"],
        "source": edge["source"],
        "target": edge["target"],
        "edge_type": edge["edge_type"],
    })
    request = fake.request
    get_graph = fake.get_knowledge_graph
    post_count = 0

    def commit_then_lose_response(
        method, path, body=None, query=None, *, idempotency_key="",
    ):
        nonlocal post_count
        result = request(
            method, path, body, query, idempotency_key=idempotency_key,
        )
        if method == "POST" and path.endswith("/knowledge-graph/commands"):
            post_count += 1
            del result
            raise LogosForgeApiError("response lost")
        return result

    def map_read_fails(*_args, **_kwargs):
        raise LogosForgeApiError("fresh graph unavailable")

    fake.request = commit_then_lose_response
    fake.get_knowledge_graph = map_read_fails
    with pytest.raises(GatewayError, match="awaiting durable recovery"):
        gateway.apply_proposal(proposal["proposal_id"])
    assert post_count == 1

    fake.request = request
    fake.get_knowledge_graph = get_graph
    applied = gateway.apply_proposal(proposal["proposal_id"])
    assert applied["state"] == "applied"
    assert applied["recovered_from_core"] is True
    assert post_count == 1
    assert fake.knowledge_graphs[1]["hidden_edge_count"] == 1


@pytest.mark.parametrize(
    "tamper",
    ["request_digest", "affected_edge"],
)
def test_knowledge_graph_receipt_integrity_mismatch_fails_closed(tamper):
    gateway, fake = _gateway(allow_writes=True)
    current = gateway.get_knowledge_graph()
    edge = current["edges"][0]
    proposal = gateway.propose_knowledge_graph_command({
        "kind": "hide_edge",
        "expected_revision": current["revision"],
        "source": edge["source"],
        "target": edge["target"],
        "edge_type": edge["edge_type"],
    })
    request = fake.request

    def commit_then_tamper(
        method, path, body=None, query=None, *, idempotency_key="",
    ):
        result = request(
            method, path, body, query, idempotency_key=idempotency_key,
        )
        if method == "POST" and path.endswith("/knowledge-graph/commands"):
            receipt = fake.knowledge_graph_receipts[(1, idempotency_key)]
            if tamper == "request_digest":
                receipt["request_digest"] = "f" * 64
            else:
                receipt["original_affected_edge"]["target"] = edge["source"]
            del result
            raise LogosForgeApiError("response lost")
        return result

    fake.request = commit_then_tamper
    with pytest.raises(
        GatewayError,
        match="invalid Knowledge Graph receipt|receipt integrity check failed",
    ):
        gateway.apply_proposal(proposal["proposal_id"])
    assert gateway.get_proposal(proposal["proposal_id"])["state"] == "failed"


def test_graph_preflight_is_directional_paged_and_review_bounded():
    gateway, fake = _gateway()
    current = gateway.get_knowledge_graph()
    edge = current["edges"][0]
    reverse = {
        "kind": "hide_edge",
        "expected_revision": current["revision"],
        "source": edge["target"],
        "target": edge["source"],
        "edge_type": edge["edge_type"],
    }
    with pytest.raises(GatewayError, match="exact directional edge"):
        gateway.propose_knowledge_graph_command(reverse)

    fake.knowledge_graphs[1]["nodes"][0]["label"] = "L" * 2_000
    fake.knowledge_graphs[1]["nodes"][0]["summary"] = "S" * 4_000
    fake.knowledge_graphs[1]["edges"][0]["explanation"] = "E" * 4_000
    proposal = gateway.propose_knowledge_graph_command({
        "kind": "hide_edge",
        "expected_revision": current["revision"],
        "source": edge["source"],
        "target": edge["target"],
        "edge_type": edge["edge_type"],
    })
    assert len(proposal["review"]["source"]["label"]) <= 513
    assert len(proposal["review"]["source"]["summary"]) <= 1_001
    assert len(proposal["review"]["edge"]["explanation"]) <= 1_001

    writable, _ = _gateway(fake, allow_writes=True)
    hidden = writable.apply_proposal(
        writable.propose_knowledge_graph_command({
            "kind": "hide_edge",
            "expected_revision": current["revision"],
            "source": edge["source"],
            "target": edge["target"],
            "edge_type": edge["edge_type"],
        })["proposal_id"]
    )["result"]["knowledge_graph"]
    with pytest.raises(GatewayError, match="exact hidden edge is not present"):
        writable.propose_knowledge_graph_command(
            {
                "kind": "unhide_edge",
                "expected_revision": hidden["revision"],
                "source": edge["source"],
                "target": edge["target"],
                "edge_type": edge["edge_type"],
            },
            hidden_edge_offset=100,
        )


def test_unknown_graph_proposal_recovers_from_selected_project_after_restart():
    gateway, fake = _gateway(allow_writes=True)
    current = gateway.get_knowledge_graph()
    edge = current["edges"][0]
    identity = {key: edge[key] for key in ("source", "target", "edge_type")}
    proposal = gateway.propose_knowledge_graph_command({
        "kind": "hide_edge",
        "expected_revision": current["revision"],
        **identity,
    })
    applied = gateway.apply_proposal(proposal["proposal_id"])

    restarted, _ = _gateway(fake)
    recovered = restarted.get_proposal(proposal["proposal_id"])

    assert recovered["state"] == "applied"
    assert recovered["recovered_from_core"] is True
    assert recovered["request"] is None
    assert recovered["receipt"]["command_kind"] == "hide_edge"
    assert recovered["receipt"]["original_affected_edge"] == identity
    assert recovered["result"] == {
        "knowledge_graph": fake.knowledge_graphs[1],
        "replayed": True,
        "applied_revision": applied["result"]["applied_revision"],
        "changed": False,
        "affected_edge": identity,
    }

    fake.project_id = 2
    wrong_project, _ = _gateway(fake)
    with pytest.raises(GatewayError, match="Unknown proposal id"):
        wrong_project.get_proposal(proposal["proposal_id"])


@pytest.mark.parametrize("receipt_change", ["disappear", "mutate"])
def test_graph_restart_recovery_brackets_map_with_same_receipt(receipt_change):
    gateway, fake = _gateway(allow_writes=True)
    current = gateway.get_knowledge_graph()
    edge = current["edges"][0]
    proposal = gateway.propose_knowledge_graph_command({
        "kind": "hide_edge",
        "expected_revision": current["revision"],
        "source": edge["source"],
        "target": edge["target"],
        "edge_type": edge["edge_type"],
    })
    gateway.apply_proposal(proposal["proposal_id"])

    restarted, _ = _gateway(fake)
    replacement = copy.deepcopy(fake.knowledge_graphs[1])
    replacement["revision"] = "f" * 64
    replacement["hidden_edges"] = []
    replacement["hidden_edge_count"] = 0

    def replace_project_during_graph_read(*_args, **_kwargs):
        key = (1, proposal["proposal_id"])
        if receipt_change == "disappear":
            fake.knowledge_graph_receipts.pop(key, None)
        else:
            fake.knowledge_graph_receipts[key]["committed_at"] = (
                "2026-10-06T10:00:01Z"
            )
        fake.knowledge_graphs[1] = copy.deepcopy(replacement)
        return copy.deepcopy(replacement)

    fake.get_knowledge_graph = replace_project_during_graph_read
    with pytest.raises(
        GatewayError,
        match="receipt (disappeared|changed).*project lifetime may have changed",
    ):
        restarted.get_proposal(proposal["proposal_id"])


def test_restart_recovery_fails_closed_on_canvas_graph_receipt_collision():
    gateway, fake = _gateway(allow_writes=True)
    proposal = gateway.propose_canvas_plot_command({
        "kind": "create_node",
        "expected_revision": fake.canvas_plots[1]["revision"],
        "title": "Canvas/graph collision",
    })
    gateway.apply_proposal(proposal["proposal_id"])
    fake.knowledge_graph_receipts[(1, proposal["proposal_id"])] = {
        "project_id": 1,
        "request_digest": "a" * 64,
        "command_kind": "hide_edge",
        "expected_revision": "b" * 64,
        "applied_revision": "c" * 64,
        "original_changed": True,
        "original_affected_edge": {
            "source": "scene:scene:11",
            "target": "scene:scene:12",
            "edge_type": "precedes",
        },
        "committed_at": "2026-10-06T10:00:00Z",
    }

    restarted, _ = _gateway(fake)
    with pytest.raises(GatewayError, match="capability collision.*failed closed"):
        restarted.get_proposal(proposal["proposal_id"])

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


@pytest.mark.parametrize("status_code", [None, 500], ids=["no-response", "server-error"])
def test_canvas_ambiguous_apply_recovers_a_committed_receipt(status_code):
    gateway, fake = _gateway(allow_writes=True)
    proposal = gateway.propose_canvas_plot_command({
        "kind": "create_node",
        "expected_revision": fake.canvas_plots[1]["revision"],
        "title": "Possibly committed",
        "x": 12,
        "y": -5,
    })
    request = fake.request
    post_keys = []

    def lose_response(
        method, path, body=None, query=None, *, idempotency_key="",
    ):
        result = request(
            method, path, body, query, idempotency_key=idempotency_key,
        )
        if method == "POST" and path.endswith("/canvas-plot/commands"):
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
    assert applied["result"] == {
        "canvas_plot": fake.canvas_plots[1],
        "replayed": True,
        "applied_revision": applied["receipt"]["applied_revision"],
        "changed": False,
        "affected_node_ids": [],
        "affected_link_ids": [],
        "affected_frame_ids": [],
        "created_node_id": None,
        "created_link_id": None,
        "created_frame_id": None,
    }
    assert applied["receipt"]["command_kind"] == "create_node"
    assert applied["receipt"]["original_created_node_id"] == 504
    assert [node["title"] for node in fake.canvas_plots[1]["nodes"]].count(
        "Possibly committed"
    ) == 1
    assert post_keys == [proposal["proposal_id"]]


def test_canvas_supported_receipt_miss_allows_one_bounded_same_key_resend():
    gateway, fake = _gateway(allow_writes=True)
    proposal = gateway.propose_canvas_plot_command({
        "kind": "create_node",
        "expected_revision": fake.canvas_plots[1]["revision"],
        "title": "Retry exactly once",
    })
    request = fake.request
    post_keys = []

    def lose_first_before_commit(
        method, path, body=None, query=None, *, idempotency_key="",
    ):
        if method == "POST" and path.endswith("/canvas-plot/commands"):
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
    assert [node["title"] for node in fake.canvas_plots[1]["nodes"]].count(
        "Retry exactly once"
    ) == 1


def test_canvas_recovery_pending_never_resends_more_than_once_total():
    gateway, fake = _gateway(allow_writes=True)
    proposal = gateway.propose_canvas_plot_command({
        "kind": "create_node",
        "expected_revision": fake.canvas_plots[1]["revision"],
        "title": "No unbounded retries",
    })
    request = fake.request
    post_keys = []

    def lose_both_before_commit(
        method, path, body=None, query=None, *, idempotency_key="",
    ):
        if method == "POST" and path.endswith("/canvas-plot/commands"):
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
    assert all(
        node["title"] != "No unbounded retries"
        for node in fake.canvas_plots[1]["nodes"]
    )


def test_canvas_observed_receipt_blocks_resend_after_fresh_board_failure():
    gateway, fake = _gateway(allow_writes=True)
    proposal = gateway.propose_canvas_plot_command({
        "kind": "create_node",
        "expected_revision": fake.canvas_plots[1]["revision"],
        "title": "Committed before read failure",
    })
    request = fake.request
    get_canvas_plot = fake.get_canvas_plot
    post_count = 0

    def lose_response(
        method, path, body=None, query=None, *, idempotency_key="",
    ):
        nonlocal post_count
        result = request(
            method, path, body, query, idempotency_key=idempotency_key,
        )
        if method == "POST" and path.endswith("/canvas-plot/commands"):
            post_count += 1
            del result
            raise LogosForgeApiError("response lost")
        return result

    def board_read_fails(_project_id=None):
        raise LogosForgeApiError("fresh board unavailable")

    fake.request = lose_response
    fake.get_canvas_plot = board_read_fails
    with pytest.raises(GatewayError, match="awaiting durable recovery"):
        gateway.apply_proposal(proposal["proposal_id"])
    assert post_count == 1

    fake.request = request
    fake.get_canvas_plot = get_canvas_plot
    applied = gateway.apply_proposal(proposal["proposal_id"])
    assert applied["state"] == "applied"
    assert applied["recovered_from_core"] is True
    assert post_count == 1
    assert [node["title"] for node in fake.canvas_plots[1]["nodes"]].count(
        "Committed before read failure"
    ) == 1


def test_canvas_receipt_integrity_mismatch_fails_closed():
    gateway, fake = _gateway(allow_writes=True)
    proposal = gateway.propose_canvas_plot_command({
        "kind": "create_node",
        "expected_revision": fake.canvas_plots[1]["revision"],
        "title": "Tampered receipt",
    })
    request = fake.request

    def commit_then_tamper(
        method, path, body=None, query=None, *, idempotency_key="",
    ):
        result = request(
            method, path, body, query, idempotency_key=idempotency_key,
        )
        if method == "POST" and path.endswith("/canvas-plot/commands"):
            fake.canvas_plot_receipts[(1, idempotency_key)][
                "request_digest"
            ] = "f" * 64
            del result
            raise LogosForgeApiError("response lost")
        return result

    fake.request = commit_then_tamper
    with pytest.raises(GatewayError, match="receipt integrity check failed"):
        gateway.apply_proposal(proposal["proposal_id"])
    assert gateway.get_proposal(proposal["proposal_id"])["state"] == "failed"


def _valid_canvas_update_receipt(**overrides):
    receipt = {
        "project_id": 1,
        "request_digest": "d" * 64,
        "command_kind": "update_node",
        "expected_revision": "a" * 64,
        "applied_revision": "b" * 64,
        "original_changed": True,
        "original_affected_node_ids": [501],
        "original_affected_link_ids": [],
        "original_affected_frame_ids": [],
        "original_created_node_id": None,
        "original_created_link_id": None,
        "original_created_frame_id": None,
        "committed_at": "2026-10-05T10:00:00Z",
    }
    receipt.update(overrides)
    return receipt


@pytest.mark.parametrize(
    "receipt",
    [
        _valid_canvas_update_receipt(applied_revision="a" * 64),
        _valid_canvas_update_receipt(original_affected_node_ids=[]),
        _valid_canvas_update_receipt(
            original_affected_node_ids=[],
            original_affected_link_ids=[601],
        ),
        _valid_canvas_update_receipt(
            command_kind="delete_node",
            original_affected_frame_ids=[701],
        ),
    ],
    ids=[
        "changed-same-revision",
        "changed-empty-command-family",
        "changed-cross-family-only",
        "delete-node-frame-cross-family",
    ],
)
def test_canvas_receipt_shape_rejects_impossible_changed_effects(receipt):
    with pytest.raises(GatewayError, match="invalid Canvas Plot receipt"):
        LogosForgeMcpGateway._validate_canvas_plot_receipt_shape(receipt, 1)


@pytest.mark.parametrize(
    "kind",
    [
        "create_node",
        "delete_node",
        "delete_link",
        "create_frame",
        "delete_frame",
    ],
)
def test_canvas_receipt_shape_rejects_impossible_noop_kinds(kind):
    receipt = _valid_canvas_update_receipt(
        command_kind=kind,
        applied_revision="a" * 64,
        original_changed=False,
        original_affected_node_ids=[],
    )

    with pytest.raises(GatewayError, match="invalid Canvas Plot receipt"):
        LogosForgeMcpGateway._validate_canvas_plot_receipt_shape(receipt, 1)


@pytest.mark.parametrize(
    "kind",
    ["update_node", "update_link", "update_frame", "create_link"],
)
def test_canvas_receipt_shape_accepts_only_protocol_permitted_noops(kind):
    receipt = _valid_canvas_update_receipt(
        command_kind=kind,
        applied_revision="a" * 64,
        original_changed=False,
        original_affected_node_ids=[],
    )

    canonical = LogosForgeMcpGateway._validate_canvas_plot_receipt_shape(
        receipt,
        1,
    )
    assert canonical["command_kind"] == kind
    assert canonical["original_changed"] is False


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
        "affected_link_ids": [],
        "affected_structure_link_ids": [],
        "created_link_id": None,
        "created_structure_link_id": None,
    }

    fake.project_id = 2
    wrong_project, _ = _gateway(fake)
    with pytest.raises(GatewayError, match="Unknown proposal id"):
        wrong_project.get_proposal(proposal["proposal_id"])


def test_unknown_canvas_proposal_recovers_from_selected_project_after_restart():
    gateway, fake = _gateway(allow_writes=True)
    proposal = gateway.propose_canvas_plot_command({
        "kind": "create_node",
        "expected_revision": fake.canvas_plots[1]["revision"],
        "title": "Survives gateway restart",
    })
    gateway.apply_proposal(proposal["proposal_id"])

    restarted, _ = _gateway(fake)
    recovered = restarted.get_proposal(proposal["proposal_id"])

    assert recovered["state"] == "applied"
    assert recovered["recovered_from_core"] is True
    assert recovered["request"] is None
    assert recovered["receipt"]["command_kind"] == "create_node"
    assert recovered["review"]["recovered_receipt"] == recovered["receipt"]
    assert recovered["result"] == {
        "canvas_plot": fake.canvas_plots[1],
        "replayed": True,
        "applied_revision": recovered["receipt"]["applied_revision"],
        "changed": False,
        "affected_node_ids": [],
        "affected_link_ids": [],
        "affected_frame_ids": [],
        "created_node_id": None,
        "created_link_id": None,
        "created_frame_id": None,
    }

    fake.project_id = 2
    wrong_project, _ = _gateway(fake)
    with pytest.raises(GatewayError, match="Unknown proposal id"):
        wrong_project.get_proposal(proposal["proposal_id"])


def test_restart_recovery_fails_closed_on_cross_family_receipt_collision():
    gateway, fake = _gateway(allow_writes=True)
    proposal = gateway.propose_canvas_plot_command({
        "kind": "create_node",
        "expected_revision": fake.canvas_plots[1]["revision"],
        "title": "Canvas receipt",
    })
    gateway.apply_proposal(proposal["proposal_id"])
    fake.timeline_receipts[(1, proposal["proposal_id"])] = {
        "project_id": 1,
        "request_digest": "a" * 64,
        "command_kind": "create_lane",
        "expected_revision": "b" * 64,
        "applied_revision": "c" * 64,
        "original_changed": True,
        "original_affected_scene_ids": [],
        "committed_at": "2026-10-04T10:00:00Z",
    }

    restarted, _ = _gateway(fake)
    with pytest.raises(GatewayError, match="capability collision.*failed closed"):
        restarted.get_proposal(proposal["proposal_id"])


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


def test_canvas_restart_recovery_brackets_board_with_same_receipt():
    gateway, fake = _gateway(allow_writes=True)
    proposal = gateway.propose_canvas_plot_command({
        "kind": "create_node",
        "expected_revision": fake.canvas_plots[1]["revision"],
        "title": "Old project card",
    })
    gateway.apply_proposal(proposal["proposal_id"])

    restarted, _ = _gateway(fake)
    replacement = {
        "project_id": 1,
        "revision": "9" * 64,
        "nodes": [{
            "id": 1,
            "title": "Replacement project card",
            "body": "",
            "x": 0.0,
            "y": 0.0,
            "width": 180.0,
            "height": 110.0,
            "color_label": "",
            "group_label": "",
            "scene_id": None,
            "sort_order": 0,
            "created_at": "2026-10-04T10:00:00Z",
        }],
        "links": [],
        "frames": [],
    }

    def replace_project_during_canvas_read(project_id=None):
        assert int(project_id or fake.require_project_id()) == 1
        fake.canvas_plot_receipts.clear()
        fake.canvas_plots[1] = copy.deepcopy(replacement)
        return copy.deepcopy(replacement)

    fake.get_canvas_plot = replace_project_during_canvas_read
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
    assert fake.requests[-4][0:2] == (
        "GET",
        "/api/projects/1/timeline/command-receipt",
    )
    assert fake.requests[-3][0:2] == (
        "GET",
        "/api/projects/1/canvas-plot/command-receipt",
    )
    assert fake.requests[-2][0:2] == (
        "GET",
        "/api/projects/1/knowledge-graph/command-receipt",
    )
    assert fake.requests[-1][0:2] == (
        "GET",
        "/api/projects/1/continuity/command-receipt",
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


def test_timeline_relationship_proposals_are_exact_reviewable_and_non_mutating():
    gateway, fake = _gateway()
    fake.timelines[1].update({
        "events": [
            {
                "id": 11, "order_index": 1, "title": "Cause",
                "structural_number": "1", "act": "Act I", "chapter": "Ch1",
                "plotline": "Main", "color_label": "", "lane_id": 301,
                "time_of_day": "", "location": "", "duration_minutes": 0,
                "character_states": [],
            },
            {
                "id": 12, "order_index": 2, "title": "Effect",
                "structural_number": "2", "act": "Act I", "chapter": "Ch1",
                "plotline": "Main", "color_label": "", "lane_id": 301,
                "time_of_day": "", "location": "", "duration_minutes": 0,
                "character_states": [],
            },
            {
                "id": 13, "order_index": 3, "title": "Aftermath",
                "structural_number": "3", "act": "Act II", "chapter": "Ch2",
                "plotline": "Sub", "color_label": "", "lane_id": 302,
                "time_of_day": "", "location": "", "duration_minutes": 0,
                "character_states": [],
            },
        ],
        "off_timeline": [],
        "links": [{
            "id": 401,
            "source_scene_id": 11,
            "target_scene_id": 12,
            "link_type": "causality",
            "color_label": "amber",
            "label": "forces",
            "created_at": "2026-10-07T10:00:00Z",
        }],
        "structure_links": [{
            "id": 501,
            "source_scene_id": 11,
            "target_type": "act",
            "target_ref": "Old Act",
            "target_exists": False,
            "created_at": "2026-10-07T10:00:00Z",
        }],
    })
    revision = fake.timelines[1]["revision"]
    commands = [
        {
            "kind": "create_link",
            "expected_revision": revision,
            "source_scene_id": 12,
            "target_scene_id": 13,
            "link_type": "setup_payoff",
            "color_label": "cyan",
            "label": "plants",
        },
        {
            "kind": "update_link",
            "expected_revision": revision,
            "link_id": 401,
            "link_type": "dependency",
            "label": "requires",
        },
        {
            "kind": "delete_link",
            "expected_revision": revision,
            "link_id": 401,
        },
        {
            "kind": "create_structure_link",
            "expected_revision": revision,
            "source_scene_id": 12,
            "target_type": "chapter",
            "target_ref": "Ch2",
        },
        {
            "kind": "update_structure_link",
            "expected_revision": revision,
            "structure_link_id": 501,
            "target_type": "act",
            "target_ref": "Act II",
        },
        {
            "kind": "delete_structure_link",
            "expected_revision": revision,
            "structure_link_id": 501,
        },
    ]

    proposals = [gateway.propose_timeline_command(command) for command in commands]

    assert [proposal["request"]["body"] for proposal in proposals] == commands
    assert proposals[0]["review"]["after_intent"]["direction"] == "source_to_target"
    assert proposals[1]["review"]["changes"]["link_type"] == {
        "before": "causality", "after": "dependency",
    }
    assert proposals[2]["review"]["destructive"] is True
    assert "manuscript scenes remain" in proposals[2]["review"]["effect"]
    assert proposals[3]["review"]["after_intent"]["target_exists"] is True
    assert proposals[4]["review"]["structure_link"]["target_exists"] is False
    assert proposals[5]["review"]["destructive"] is True
    assert fake.timelines[1]["links"][0]["link_type"] == "causality"
    assert fake.timelines[1]["structure_links"][0]["target_ref"] == "Old Act"
    assert not any(method == "POST" for method, _path, _body in fake.requests)


def test_timeline_link_proposal_apply_stale_sibling_and_restart_receipt_recovery():
    gateway, fake = _gateway(allow_writes=True)
    fake.timelines[1].update({
        "events": [
            {
                "id": scene_id, "order_index": index, "title": title,
                "structural_number": str(index), "act": "Act I",
                "chapter": "Ch1", "plotline": "Main", "color_label": "",
                "lane_id": None, "time_of_day": "", "location": "",
                "duration_minutes": 0, "character_states": [],
            }
            for index, (scene_id, title) in enumerate(
                ((11, "Cause"), (12, "Effect"), (13, "Aftermath")), start=1,
            )
        ],
        "off_timeline": [],
        "links": [],
        "structure_links": [],
    })
    revision = fake.timelines[1]["revision"]
    proposal = gateway.propose_timeline_command({
        "kind": "create_link",
        "expected_revision": revision,
        "source_scene_id": 11,
        "target_scene_id": 12,
        "link_type": "causality",
        "label": "forces",
    })
    stale = gateway.propose_timeline_command({
        "kind": "create_link",
        "expected_revision": revision,
        "source_scene_id": 12,
        "target_scene_id": 13,
        "link_type": "dependency",
    })
    assert fake.timelines[1]["links"] == []

    applied = gateway.apply_proposal(proposal["proposal_id"])
    assert applied["state"] == "applied"
    assert applied["result"]["created_link_id"] == 401
    assert applied["result"]["affected_link_ids"] == [401]
    assert fake.timelines[1]["links"] == [{
        "id": 401,
        "source_scene_id": 11,
        "target_scene_id": 12,
        "link_type": "causality",
        "color_label": "gray",
        "label": "forces",
        "created_at": "2026-10-07T10:00:00Z",
    }]
    with pytest.raises(GatewayError, match="rejected.*Timeline changed"):
        gateway.apply_proposal(stale["proposal_id"])

    restarted, _ = _gateway(fake)
    recovered = restarted.get_proposal(proposal["proposal_id"])
    assert recovered["state"] == "applied"
    assert recovered["receipt"]["original_affected_link_ids"] == [401]
    assert recovered["receipt"]["original_created_link_id"] == 401
    assert recovered["result"]["replayed"] is True
    assert recovered["result"]["created_link_id"] is None
    assert len(fake.timelines[1]["links"]) == 1


@pytest.mark.parametrize(
    ("command", "message"),
    [
        (
            {
                "kind": "create_link", "expected_revision": "1" * 64,
                "source_scene_id": 11, "target_scene_id": 11,
            },
            "cannot link to itself",
        ),
        (
            {
                "kind": "create_link", "expected_revision": "1" * 64,
                "source_scene_id": 11, "target_scene_id": 12,
                "link_type": "unknown",
            },
            "link_type must be one of",
        ),
        (
            {
                "kind": "update_link", "expected_revision": "1" * 64,
                "link_id": 401,
            },
            "must change at least one field",
        ),
        (
            {
                "kind": "create_structure_link", "expected_revision": "1" * 64,
                "source_scene_id": 11, "target_type": "scene",
                "target_ref": "Opening",
            },
            "target_type must be 'act' or 'chapter'",
        ),
        (
            {
                "kind": "update_structure_link", "expected_revision": "1" * 64,
                "structure_link_id": 501,
            },
            "must change at least one field",
        ),
    ],
)
def test_timeline_relationship_command_normalization_rejects_unsafe_shapes(
    command, message,
):
    gateway, fake = _gateway()
    with pytest.raises(GatewayError, match=message):
        gateway.propose_timeline_command(command)
    assert gateway.list_proposals() == {"proposals": []}
    assert not any(method == "POST" for method, _path, _body in fake.requests)


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


@pytest.mark.parametrize(
    ("command", "message"),
    [
        (
            {
                "kind": "create_node",
                "expected_revision": "A" * 64,
            },
            "exact 64-character lowercase revision",
        ),
        (
            {
                "kind": "create_node",
                "expected_revision": "0" * 64,
            },
            "expected_revision does not match the current Canvas Plot",
        ),
        (
            {
                "kind": "delete_frame",
                "expected_revision": "4" * 64,
                "frame_id": 701,
                "confirmed": True,
            },
            "Unexpected Canvas Plot command field",
        ),
        (
            {
                "kind": "update_node",
                "expected_revision": "4" * 64,
                "node_id": 501,
            },
            "must change at least one field",
        ),
        (
            {
                "kind": "update_node",
                "expected_revision": "4" * 64,
                "node_id": 501,
                "title": None,
            },
            "title must not be null",
        ),
        (
            {
                "kind": "create_node",
                "expected_revision": "4" * 64,
                "index": True,
            },
            "index must be a non-negative integer",
        ),
        (
            {
                "kind": "create_node",
                "expected_revision": "4" * 64,
                "width": 0,
            },
            "width must be greater than zero",
        ),
        (
            {
                "kind": "create_link",
                "expected_revision": "4" * 64,
                "source_node_id": 501,
            },
            "requires source_node_id and target_node_id",
        ),
        (
            {
                "kind": "update_link",
                "expected_revision": "4" * 64,
                "link_id": 601,
            },
            "must change at least one field",
        ),
        (
            {
                "kind": "update_frame",
                "expected_revision": "4" * 64,
                "frame_id": 701,
                "height": None,
            },
            "height must not be null",
        ),
        (
            {
                "kind": "delete_node",
                "expected_revision": "4" * 64,
                "node_id": False,
            },
            "node_id must be a positive integer",
        ),
        (
            {
                "kind": "teleport_node",
                "expected_revision": "4" * 64,
            },
            "command kind must be one of",
        ),
    ],
)
def test_canvas_plot_tool_rejects_unscoped_or_ambiguous_commands(command, message):
    from logosforge.librechat.mcp_server import call_tool

    gateway, fake = _gateway()
    response = call_tool(
        gateway,
        "logosforge_propose_canvas_plot_command",
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

    assert "mode-lens" in server.SERVER_INSTRUCTIONS
    assert "user-authored project data" in server.SERVER_INSTRUCTIONS
    names = [spec.name for spec in server.TOOL_SPECS]
    assert len(names) == len(set(names)) == 46
    assert {
        "logosforge_get_timeline",
        "logosforge_propose_timeline_command",
        "logosforge_get_canvas_plot",
        "logosforge_propose_canvas_plot_command",
        "logosforge_get_knowledge_graph",
        "logosforge_get_knowledge_graph_hidden_edges",
        "logosforge_propose_knowledge_graph_command",
        "logosforge_propose_continuity_command",
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
    assert "story-flow" in timeline_read.description
    assert "mode-specific" in timeline_read.description
    timeline_proposal = server.HANDLERS[
        "logosforge_propose_timeline_command"
    ]
    assert timeline_proposal.read_only is True
    assert timeline_proposal.destructive is False
    assert timeline_proposal.idempotent is False
    variants = timeline_proposal.input_schema["properties"]["command"]["oneOf"]
    assert {variant["properties"]["kind"]["const"] for variant in variants} == {
        "create_lane", "update_lane", "delete_lane", "place_event",
        "remove_event", "set_order_mode", "create_link", "update_link",
        "delete_link", "create_structure_link", "update_structure_link",
        "delete_structure_link",
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
    canvas_read = server.HANDLERS["logosforge_get_canvas_plot"]
    assert canvas_read.input_schema == server._obj({"include_bodies": server.BOOL})
    assert canvas_read.read_only is True
    assert canvas_read.destructive is False
    assert canvas_read.idempotent is True
    canvas_proposal = server.HANDLERS[
        "logosforge_propose_canvas_plot_command"
    ]
    assert canvas_proposal.read_only is True
    assert canvas_proposal.destructive is False
    assert canvas_proposal.idempotent is False
    canvas_variants = canvas_proposal.input_schema["properties"]["command"][
        "oneOf"
    ]
    assert {variant["properties"]["kind"]["const"] for variant in canvas_variants} == {
        "create_node", "update_node", "delete_node",
        "create_link", "update_link", "delete_link",
        "create_frame", "update_frame", "delete_frame",
    }
    assert all(
        variant["additionalProperties"] is False for variant in canvas_variants
    )
    canvas_by_kind = {
        variant["properties"]["kind"]["const"]: variant
        for variant in canvas_variants
    }
    assert canvas_by_kind["create_node"]["required"] == [
        "kind", "expected_revision",
    ]
    assert canvas_by_kind["create_node"]["properties"]["body"]["maxLength"] == (
        100_000
    )
    assert canvas_by_kind["create_node"]["properties"]["scene_id"] == {
        "type": ["integer", "null"], "minimum": 1,
    }
    assert canvas_by_kind["update_node"]["anyOf"] == [
        {"required": [field]}
        for field in (
            "title", "body", "x", "y", "width", "height",
            "color_label", "group_label", "scene_id", "index",
        )
    ]
    assert canvas_by_kind["update_link"]["anyOf"] == [
        {"required": ["label"]},
        {"required": ["color_label"]},
        {"required": ["link_type"]},
    ]
    assert canvas_by_kind["update_frame"]["anyOf"] == [
        {"required": [field]}
        for field in ("title", "color_label", "x", "y", "width", "height")
    ]
    assert canvas_by_kind["delete_node"]["required"] == [
        "kind", "expected_revision", "node_id",
    ]
    assert canvas_by_kind["delete_link"]["required"] == [
        "kind", "expected_revision", "link_id",
    ]
    assert canvas_by_kind["delete_frame"]["required"] == [
        "kind", "expected_revision", "frame_id",
    ]
    graph_read = server.HANDLERS["logosforge_get_knowledge_graph"]
    assert graph_read.input_schema == server._obj({
        "focus_key": {
            "type": "string", "minLength": 1, "maxLength": 512,
        },
        "depth": {"type": "integer", "minimum": 1, "maximum": 2},
        "limit": {"type": "integer", "minimum": 1, "maximum": 200},
        "include_inferred": server.BOOL,
        "view_mode": {
            "type": "string",
            "enum": [
                "project_map",
                "recorded_risk",
                "revision_impact",
                "structure",
            ],
        },
    })
    assert graph_read.read_only is True
    assert graph_read.destructive is False
    assert graph_read.idempotent is True
    hidden_read = server.HANDLERS[
        "logosforge_get_knowledge_graph_hidden_edges"
    ]
    assert hidden_read.input_schema == server._obj({
        "offset": {"type": "integer", "minimum": 0},
        "limit": {"type": "integer", "minimum": 1, "maximum": 100},
    })
    assert hidden_read.read_only is True
    assert hidden_read.destructive is False
    assert hidden_read.idempotent is True
    graph_proposal = server.HANDLERS[
        "logosforge_propose_knowledge_graph_command"
    ]
    assert graph_proposal.read_only is True
    assert graph_proposal.destructive is False
    assert graph_proposal.idempotent is False
    assert graph_proposal.input_schema["properties"]["hidden_edge_offset"] == {
        "type": "integer", "minimum": 0,
    }
    graph_variants = graph_proposal.input_schema["properties"]["command"][
        "oneOf"
    ]
    assert {
        variant["properties"]["kind"]["const"]
        for variant in graph_variants
    } == {"confirm_edge", "hide_edge", "unhide_edge"}
    assert all(
        variant["required"] == [
            "kind", "expected_revision", "source", "target", "edge_type",
        ]
        and variant["additionalProperties"] is False
        for variant in graph_variants
    )
    continuity_proposal = server.HANDLERS[
        "logosforge_propose_continuity_command"
    ]
    assert continuity_proposal.read_only is True
    assert continuity_proposal.destructive is False
    assert continuity_proposal.idempotent is False
    assert continuity_proposal.input_schema["properties"]["command"] == (
        server.CONTINUITY_COMMAND_SCHEMA
    )
    assert server.CONTINUITY_COMMAND_SCHEMA["additionalProperties"] is False
    assert server.CONTINUITY_COMMAND_SCHEMA["required"] == [
        "kind",
        "expected_revision",
        "issue_id",
        "expected_issue_fingerprint",
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
    assert initialized.serverInfo.version == "1.11.0"
    tools = {tool.name: tool for tool in listed.tools}
    assert len(tools) == 46
    assert {
        "logosforge_get_timeline",
        "logosforge_propose_timeline_command",
        "logosforge_get_canvas_plot",
        "logosforge_propose_canvas_plot_command",
        "logosforge_get_knowledge_graph",
        "logosforge_get_knowledge_graph_hidden_edges",
        "logosforge_propose_knowledge_graph_command",
        "logosforge_propose_continuity_command",
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
    canvas_annotations = tools["logosforge_get_canvas_plot"].annotations
    assert canvas_annotations.readOnlyHint is True
    assert canvas_annotations.destructiveHint is False
    assert canvas_annotations.idempotentHint is True
    canvas_proposal = tools["logosforge_propose_canvas_plot_command"]
    canvas_proposal_annotations = canvas_proposal.annotations
    assert canvas_proposal_annotations.readOnlyHint is True
    assert canvas_proposal_annotations.destructiveHint is False
    assert canvas_proposal_annotations.idempotentHint is False
    advertised_canvas_variants = canvas_proposal.inputSchema["properties"][
        "command"
    ]["oneOf"]
    assert len(advertised_canvas_variants) == 9
    assert all(
        variant["additionalProperties"] is False
        for variant in advertised_canvas_variants
    )
    graph_annotations = tools["logosforge_get_knowledge_graph"].annotations
    assert graph_annotations.readOnlyHint is True
    assert graph_annotations.destructiveHint is False
    assert graph_annotations.idempotentHint is True
    hidden_graph_annotations = tools[
        "logosforge_get_knowledge_graph_hidden_edges"
    ].annotations
    assert hidden_graph_annotations.readOnlyHint is True
    assert hidden_graph_annotations.destructiveHint is False
    assert hidden_graph_annotations.idempotentHint is True
    graph_proposal = tools["logosforge_propose_knowledge_graph_command"]
    graph_proposal_annotations = graph_proposal.annotations
    assert graph_proposal_annotations.readOnlyHint is True
    assert graph_proposal_annotations.destructiveHint is False
    assert graph_proposal_annotations.idempotentHint is False
    assert len(
        graph_proposal.inputSchema["properties"]["command"]["oneOf"]
    ) == 3
    assert graph_proposal.inputSchema["properties"]["hidden_edge_offset"] == {
        "type": "integer", "minimum": 0,
    }
    continuity_proposal = tools["logosforge_propose_continuity_command"]
    continuity_annotations = continuity_proposal.annotations
    assert continuity_annotations.readOnlyHint is True
    assert continuity_annotations.destructiveHint is False
    assert continuity_annotations.idempotentHint is False
    assert continuity_proposal.inputSchema["properties"]["command"] == {
        "type": "object",
        "properties": {
            "kind": {
                "type": "string",
                "enum": ["defer_issue", "dismiss_issue", "resolve_issue"],
            },
            "expected_revision": {
                "type": "string",
                "minLength": 64,
                "maxLength": 64,
                "pattern": "^[0-9a-f]{64}$",
            },
            "issue_id": {
                "type": "string",
                "minLength": 16,
                "maxLength": 16,
                "pattern": "^[0-9a-f]{16}$",
            },
            "expected_issue_fingerprint": {
                "type": "string",
                "minLength": 64,
                "maxLength": 64,
                "pattern": "^[0-9a-f]{64}$",
            },
        },
        "required": [
            "kind",
            "expected_revision",
            "issue_id",
            "expected_issue_fingerprint",
        ],
        "additionalProperties": False,
    }
    annotations = tools["logosforge_apply_proposal"].annotations
    assert annotations.readOnlyHint is False
    assert annotations.destructiveHint is True
    assert annotations.idempotentHint is False
    assert annotations.openWorldHint is False
