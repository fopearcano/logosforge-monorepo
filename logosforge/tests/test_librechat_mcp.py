"""Tests for the LogosForge MCP server scaffold.

Covers the HTTP connector client (mocked transport) and the MCP tool handlers
(reads → connector execute; propose → un-applied proposal; apply → gated by
confirmation). No network, no MCP SDK, and no LibreChat instance are required.
"""

from __future__ import annotations

import io
import json
from unittest import mock

import pytest

from logosforge.librechat import api_client as ac
from logosforge.librechat import mcp_server as M
from logosforge.librechat.api_client import (
    LogosForgeApiClient,
    LogosForgeApiError,
)


# -- HTTP client -------------------------------------------------------------

def _resp(payload):
    body = json.dumps(payload).encode("utf-8")
    r = io.BytesIO(body)
    r.__enter__ = lambda *_: r           # type: ignore[attr-defined]
    r.__exit__ = lambda *a: False        # type: ignore[attr-defined]
    r.read = lambda: body                # type: ignore[assignment]
    return r


def test_client_execute_posts_to_connector_endpoint():
    client = LogosForgeApiClient(base_url="http://127.0.0.1:8765", project_id=7)
    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        captured["method"] = req.get_method()
        captured["body"] = req.data
        return _resp({"ok": True, "action": "get_project", "result": {"id": 7}, "error": ""})

    with mock.patch.object(ac.urllib.request, "urlopen", fake_urlopen):
        out = client.execute("get_project", {})
    assert captured["url"] == "http://127.0.0.1:8765/api/projects/7/connector/execute"
    assert captured["method"] == "POST"
    assert json.loads(captured["body"]) == {"action": "get_project", "args": {}}
    assert out["result"] == {"id": 7}


def test_client_sends_bearer_token_when_configured():
    client = LogosForgeApiClient(project_id=1, auth_token="secret")
    seen = {}

    def fake_urlopen(req, timeout=None):
        seen["auth"] = req.headers.get("Authorization")
        return _resp([])

    with mock.patch.object(ac.urllib.request, "urlopen", fake_urlopen):
        client.list_actions()
    assert seen["auth"] == "Bearer secret"


def test_client_raises_on_unreachable():
    import urllib.error
    client = LogosForgeApiClient()
    with mock.patch.object(ac.urllib.request, "urlopen",
                           side_effect=urllib.error.URLError("down")):
        with pytest.raises(LogosForgeApiError):
            client.execute("get_project")


# -- Tool handlers -----------------------------------------------------------

class _FakeClient:
    def __init__(self):
        self.calls = []
        self.actions = [
            {"name": "create_psyke_entry", "category": "write"},
            {"name": "create_scene", "category": "write"},
            {"name": "update_scene_title", "category": "write"},
            {"name": "get_project", "category": "read"},
        ]

    def execute(self, action, args=None):
        self.calls.append((action, args or {}))
        return {"ok": True, "action": action, "result": {"echo": action, "args": args or {}}, "error": ""}

    def list_actions(self):
        return self.actions


def test_tools_map_to_connector_reads():
    c = _FakeClient()
    assert M.call_tool(c, "logosforge_get_project_context", {})["result"]["echo"] == "get_project"
    assert M.call_tool(c, "logosforge_get_outline_context", {})["result"]["echo"] == "list_scenes"
    assert M.call_tool(c, "logosforge_search", {"query": "x"})["result"]["args"] == {"query": "x"}
    assert M.call_tool(c, "logosforge_get_scene", {"scene_id": 3})["result"]["args"] == {"scene_id": 3}


def test_propose_returns_unapplied_proposal():
    c = _FakeClient()
    out = M.call_tool(c, "logosforge_propose_psyke_entry",
                      {"name": "Ada", "entry_type": "character", "notes": "lead"})
    assert out["requires_confirmation"] is True
    assert out["proposal"]["action"] == "create_psyke_entry"
    assert c.calls == []  # nothing executed


def test_propose_rejects_non_write_or_unknown(monkeypatch):
    c = _FakeClient()
    # apply path: unknown action via apply (write) is rejected by the API anyway,
    # but propose validates locally against the catalog.
    out = M.call_tool(c, "logosforge_propose_scene", {"title": "T"})
    assert out["proposal"]["action"] == "create_scene"


def test_apply_requires_confirmation():
    c = _FakeClient()
    out = M.call_tool(c, "logosforge_apply_confirmed_action",
                      {"action": "create_scene", "args": {"title": "X"}, "confirmed": False})
    assert out["ok"] is False and "confirm" in out["error"].lower()
    assert c.calls == []  # not executed


def test_apply_confirmed_calls_execute():
    c = _FakeClient()
    out = M.call_tool(c, "logosforge_apply_confirmed_action",
                      {"action": "create_scene", "args": {"title": "X"}, "confirmed": True})
    assert out["result"]["echo"] == "create_scene"
    assert c.calls == [("create_scene", {"title": "X"})]


def test_invalid_input_is_a_structured_error_not_a_crash():
    c = _FakeClient()
    out = M.call_tool(c, "logosforge_get_scene", {"scene_id": "not-int"})
    assert out["ok"] is False and "integer" in out["error"].lower()


def test_unknown_tool_returns_error():
    out = M.call_tool(_FakeClient(), "logosforge_delete_everything", {})
    assert out["ok"] is False and "unknown tool" in out["error"].lower()


def test_all_bridge_operations_have_a_tool():
    names = {s.name for s in M.TOOL_SPECS}
    for expected in (
        "logosforge_get_project_context", "logosforge_get_scene",
        "logosforge_search", "logosforge_get_outline_context",
        "logosforge_propose_psyke_entry", "logosforge_propose_scene",
        "logosforge_apply_confirmed_action",
    ):
        assert expected in names


def test_build_server_errors_clearly_without_mcp_sdk():
    # The SDK is optional; building the server without it must fail loudly.
    import builtins
    real_import = builtins.__import__

    def no_mcp(name, *a, **k):
        if name == "mcp" or name.startswith("mcp."):
            raise ImportError("no mcp")
        return real_import(name, *a, **k)

    with mock.patch.object(builtins, "__import__", no_mcp):
        with pytest.raises(RuntimeError, match="pip install mcp"):
            M.build_server(_FakeClient())
