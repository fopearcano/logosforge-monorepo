"""Live editing context + in-process (embedded) API hosting.

Covers the thread-safe live-context store, the connector read-actions that
expose it, the optional embedded FastAPI server (started in-process, sharing the
live Database, read end-to-end and stopped cleanly), and the MCP live tools.
No Qt, no LibreChat, no MCP SDK required.
"""

from __future__ import annotations

import socket
import time
import urllib.request

import pytest

from logosforge.api.actions import run_action
from logosforge.db import Database
from logosforge.live_context import (
    clear_live_context,
    get_live_context,
    set_live_context,
)


@pytest.fixture(autouse=True)
def _clean_store():
    clear_live_context()
    yield
    clear_live_context()


# -- Store -------------------------------------------------------------------

def test_store_empty_by_default():
    ctx = get_live_context()
    assert ctx.available is False
    assert ctx.project_id is None and ctx.active_scene_id is None
    assert ctx.has_selection is False


def test_store_set_get_and_normalizes_paragraph_sep():
    set_live_context(project_id=4, active_scene_id=9,
                     selection="a" + chr(0x2029) + "b")
    ctx = get_live_context()
    assert ctx.available is True
    assert ctx.project_id == 4 and ctx.active_scene_id == 9
    assert ctx.selection == "a\nb"   # U+2029 → \n
    assert ctx.has_selection is True


def test_store_clear():
    set_live_context(project_id=1, active_scene_id=1, selection="x")
    clear_live_context()
    assert get_live_context().available is False


def test_store_is_thread_safe_to_read():
    import threading
    set_live_context(project_id=2, active_scene_id=3, selection="hi")
    seen = []
    t = threading.Thread(target=lambda: seen.append(get_live_context().project_id))
    t.start(); t.join()
    assert seen == [2]


# -- Connector read-actions (read path = run_action) -------------------------

def _db_with_scene():
    db = Database()
    proj = db.create_project("Live")
    scene = db.create_scene(proj.id, "Opening", chapter="1")
    return db, proj, scene


def test_action_get_live_context_reports_unavailable_when_empty():
    db, proj, _ = _db_with_scene()
    res = run_action(db, proj.id, "get_live_context", {})
    assert res["ok"] and res["result"]["available"] is False


def test_action_get_live_context_when_set():
    db, proj, scene = _db_with_scene()
    set_live_context(project_id=proj.id, active_scene_id=scene.id, selection="sel")
    res = run_action(db, proj.id, "get_live_context", {})["result"]
    assert res["available"] and res["active_scene_id"] == scene.id
    assert res["has_selection"] is True


def test_action_get_current_selection():
    db, proj, scene = _db_with_scene()
    set_live_context(project_id=proj.id, active_scene_id=scene.id, selection="hello")
    res = run_action(db, proj.id, "get_current_selection", {})["result"]
    assert res["selection"] == "hello" and res["length"] == 5


def test_action_get_active_scene_returns_scene():
    db, proj, scene = _db_with_scene()
    set_live_context(project_id=proj.id, active_scene_id=scene.id, selection="")
    res = run_action(db, proj.id, "get_active_scene", {})
    assert res["ok"] and res["result"]["title"] == "Opening"


def test_action_get_active_scene_graceful_when_none():
    db, proj, _ = _db_with_scene()
    res = run_action(db, proj.id, "get_active_scene", {})
    assert res["ok"] is False and "active scene" in res["error"].lower()


def test_live_actions_are_read_category():
    import logosforge.connector_actions  # noqa: F401
    from logosforge.connector_registry import get_action
    for name in ("get_live_context", "get_current_selection", "get_active_scene"):
        assert get_action(name).category == "read"


# -- Embedded server (in-process, shares the live DB) ------------------------

def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _wait_health(url: str, tries: int = 60) -> bool:
    for _ in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=1) as r:
                if r.status == 200:
                    return True
        except Exception:
            time.sleep(0.1)
    return False


def test_embedded_server_serves_live_db_and_context():
    from logosforge.api.embedded import EmbeddedApiServer
    from logosforge.librechat.api_client import LogosForgeApiClient

    db, proj, scene = _db_with_scene()
    server = EmbeddedApiServer(db, port=_free_port())
    server.start()
    try:
        assert server.wait_until_serving(timeout=5.0) is True
        assert _wait_health(f"{server.url}/api/health"), "embedded API never came up"
        client = LogosForgeApiClient(base_url=server.url, project_id=proj.id)

        # Live persisted data via the SHARED Database (no second connection):
        assert client.execute("get_project")["result"]["title"] == "Live"

        # Live UI context pushed from "the GUI thread", read by the API thread:
        set_live_context(project_id=proj.id, active_scene_id=scene.id,
                         selection="the rain")
        assert client.execute("get_live_context")["result"]["available"] is True
        assert client.execute("get_current_selection")["result"]["selection"] == "the rain"
        assert client.execute("get_active_scene")["result"]["title"] == "Opening"
    finally:
        server.stop()
    assert server.is_running() is False


def test_embedded_server_double_start_is_idempotent():
    from logosforge.api.embedded import EmbeddedApiServer
    db, proj, _ = _db_with_scene()
    server = EmbeddedApiServer(db, port=_free_port())
    server.start()
    try:
        thread1 = server._thread
        server.start()  # no duplicate
        assert server._thread is thread1
    finally:
        server.stop()


# -- MCP live tools ----------------------------------------------------------

def test_mcp_live_tools_map_to_actions():
    from logosforge.librechat import mcp_server as M

    class _C:
        def __init__(self): self.calls = []
        def execute(self, action, args=None):
            self.calls.append(action)
            return {"ok": True, "result": {"action": action}}

    c = _C()
    M.call_tool(c, "logosforge_get_live_context", {})
    M.call_tool(c, "logosforge_get_current_scene", {})
    M.call_tool(c, "logosforge_get_current_selection", {})
    assert c.calls == ["get_live_context", "get_active_scene", "get_current_selection"]


def test_settings_defaults_present():
    from logosforge.settings import DEFAULTS
    assert DEFAULTS["api_embedded_enabled"] is False
    assert DEFAULTS["api_embedded_port"] == 8765
