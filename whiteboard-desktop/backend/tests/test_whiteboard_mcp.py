"""Focused contract and real-stdio tests for the Whiteboard MCP companion."""

from __future__ import annotations

import asyncio
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

from app.whiteboard_mcp.client import WhiteboardApiClient, WhiteboardApiError
from app.whiteboard_mcp.gateway import (
    MAX_RESULT_BYTES,
    MAX_SEARCH_ID,
    MAX_SEARCH_TITLE,
    WhiteboardMcpGateway,
)
from app.whiteboard_mcp.server import (
    HANDLERS,
    SERVER_NAME,
    TOOL_PREFIX,
    TOOL_SPECS,
    McpConfig,
    McpToolError,
    call_tool,
)


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
                {"id": "c1", "quote": "lantern", "body": "Track this image", "resolved": False, "replies": []},
                {"id": "c2", "quote": "rain", "body": "Resolved note", "resolved": True, "replies": []},
            ],
            2: [],
        }
        self.entries = {
            1: [
                {"id": "10", "name": "Mara", "entry_type": "character", "aliases": [], "description": "Keeper of the lantern", "notes": ""},
                {"id": "11", "name": "North House", "entry_type": "place", "aliases": [], "description": "Rain-dark manor", "notes": ""},
            ],
            2: [],
        }
        self.settings = {1: {}, 2: {}}

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
        return list(self.comments[document_id])

    def get_psyke(self, document_id, query=""):
        values = list(self.entries[document_id])
        needle = query.casefold().strip()
        return [item for item in values if not needle or needle in json.dumps(item).casefold()]


def _gateway() -> WhiteboardMcpGateway:
    return WhiteboardMcpGateway(FakeClient())  # type: ignore[arg-type]


def _wire_bytes(value: object) -> int:
    return len(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    )


def test_registry_is_separate_focused_and_strictly_read_only() -> None:
    names = [spec.name for spec in TOOL_SPECS]
    assert len(names) == len(set(names)) == 9
    assert set(names) == set(HANDLERS)
    assert all(name.startswith(TOOL_PREFIX) for name in names)
    assert all(not any(word in name for word in ("write", "create", "update", "delete", "apply", "propose")) for name in names)
    assert SERVER_NAME == "logosforge-whiteboard"


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
            {"id": "outline-huge", "title": "Huge outline", "payload": "O" * (MAX_RESULT_BYTES * 2)},
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

    psyke = call_tool(
        gateway,
        "logosforge_whiteboard_get_psyke",
        {"document_id": 1, "entry_type": "character"},
    )["result"]
    assert [item["name"] for item in psyke["entries"]] == ["Mara"]

    search = call_tool(
        gateway,
        "logosforge_whiteboard_search",
        {"document_id": 1, "query": "Mara", "limit": 2},
    )["result"]
    assert search["total_matches"] >= 3
    assert len(search["matches"]) == 2
    assert search["truncated"] is True
    assert all(len(item["snippet"]) <= 242 for item in search["matches"])


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


def test_programmatic_config_is_loopback_authenticated_and_bounded() -> None:
    McpConfig("http://127.0.0.1:8777", "x" * 32)
    with pytest.raises(McpToolError, match="loopback"):
        McpConfig("https://example.test:443", "x" * 32)
    with pytest.raises(McpToolError, match="bearer token"):
        McpConfig("http://127.0.0.1:8777", "short")
    with pytest.raises(McpToolError, match="timeout"):
        McpConfig("http://127.0.0.1:8777", "x" * 32, 301)


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
    assert initialized.serverInfo.version == "1.0.0"
    assert len(listed.tools) == 9
    assert all(tool.annotations.readOnlyHint is True for tool in listed.tools)
    assert all(tool.annotations.destructiveHint is False for tool in listed.tools)
    assert all(tool.annotations.idempotentHint is True for tool in listed.tools)
    assert result.isError is False
    structured = getattr(result, "structuredContent", None)
    if structured is None:
        structured = getattr(result, "structured_content", None)
    assert structured["ok"] is True
    assert structured["result"]["documents"][0]["title"] == "Stdio document"
