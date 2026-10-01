"""Live editing context, packaged publication, and embedded API hosting.

Covers the thread-safe live-context store, the connector read-actions that
expose it, the authenticated packaged-desktop publisher, the optional embedded
FastAPI server (started in-process, sharing the live Database, read end-to-end
and stopped cleanly), and the MCP live tools. No Qt, LibreChat, or MCP SDK is
required.
"""

from __future__ import annotations

import socket
import time
import urllib.request

import pytest
from fastapi.testclient import TestClient
from logosforge.api.actions import run_action
from logosforge.api.app import create_api
from logosforge.api.config import ApiConfig
from logosforge.db import Database
from logosforge.live_context import (
    MAX_SELECTION_CHARS,
    StaleLiveContextRevision,
    clear_live_context,
    get_live_context,
    publish_live_context,
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


def test_legacy_store_caps_selection_and_accepts_richer_context():
    set_live_context(
        project_id=2,
        active_panel_id="manuscript",
        active_scene_id=3,
        selection_section="body",
        selection="x" * (MAX_SELECTION_CHARS + 10),
    )
    ctx = get_live_context()
    assert ctx.active_panel_id == "manuscript"
    assert ctx.selection_section == "body"
    assert len(ctx.selection) == MAX_SELECTION_CHARS
    assert ctx.revision is None


def test_ordered_publish_clear_retains_revision_ledger():
    publish_live_context(
        source_id="desktop-a",
        revision=10,
        project_id=2,
        active_panel_id="manuscript",
        active_scene_id=3,
        selection_section="body",
        selection="selected",
    )
    assert get_live_context().revision == 10

    cleared = publish_live_context(
        source_id="desktop-a",
        revision=11,
        project_id=None,
    )
    assert cleared.available is False
    assert get_live_context().available is False

    with pytest.raises(StaleLiveContextRevision) as exc_info:
        publish_live_context(
            source_id="desktop-a",
            revision=10,
            project_id=2,
        )
    assert exc_info.value.current_revision == 11
    assert get_live_context().available is False


def test_live_context_expires_on_monotonic_ttl_without_resetting_revision(
    monkeypatch,
):
    import logosforge.live_context as live_context_module

    now = [100.0]
    monkeypatch.setattr(live_context_module.time, "monotonic", lambda: now[0])
    publish_live_context(
        source_id="desktop-a", revision=4, project_id=2, selection="fresh",
    )
    now[0] += 29.999
    assert get_live_context().available is True
    now[0] += 0.001
    assert get_live_context().available is False

    with pytest.raises(StaleLiveContextRevision):
        publish_live_context(
            source_id="desktop-a", revision=4, project_id=2, selection="late",
        )
    publish_live_context(
        source_id="desktop-a", revision=5, project_id=2, selection="new",
    )
    assert get_live_context().selection == "new"


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


def test_live_context_actions_do_not_expose_another_project():
    db, live_project, live_scene = _db_with_scene()
    other_project = db.create_project("Other")
    set_live_context(
        project_id=live_project.id,
        active_scene_id=live_scene.id,
        selection="private draft text",
    )

    context = run_action(db, other_project.id, "get_live_context", {})["result"]
    assert context == {
        "available": False,
        "project_id": None,
        "active_panel_id": None,
        "active_scene_id": None,
        "has_selection": False,
        "selection_length": 0,
        "selection_section": None,
        "revision": None,
    }

    selection = run_action(
        db, other_project.id, "get_current_selection", {},
    )["result"]
    assert selection == {
        "available": False,
        "selection": "",
        "length": 0,
        "selection_section": None,
        "active_panel_id": None,
        "revision": None,
    }


def test_live_actions_fail_closed_for_foreign_scene_and_expired_context(
    monkeypatch,
):
    import logosforge.live_context as live_context_module

    db, project, _ = _db_with_scene()
    other = db.create_project("Other")
    foreign_scene = db.create_scene(other.id, "Foreign")
    set_live_context(project_id=project.id, active_scene_id=foreign_scene.id,
                     selection="must not leak")
    context = run_action(db, project.id, "get_live_context", {})["result"]
    assert context["available"] is False
    selection = run_action(
        db, project.id, "get_current_selection", {},
    )["result"]
    assert selection["selection"] == ""

    now = [100.0]
    monkeypatch.setattr(live_context_module.time, "monotonic", lambda: now[0])
    set_live_context(project_id=project.id, selection="briefly visible")
    now[0] += 30.0
    expired = run_action(db, project.id, "get_live_context", {})["result"]
    assert expired["available"] is False


# -- Packaged desktop publication route -------------------------------------

_TOKEN = "desktop-test-token"
_NONCE = "desktop-instance-nonce"
_LIVE_TOKEN = "desktop-live-context-capability"


def _push_client(
    *,
    mode: str = "desktop",
    token: str = _TOKEN,
    live_token: str = _LIVE_TOKEN,
):
    db, project, scene = _db_with_scene()
    client = TestClient(create_api(
        db=db,
        config=ApiConfig(
            mode=mode,
            auth_token=token,
            instance_nonce=_NONCE,
            live_context_token=live_token,
        ),
    ))
    return client, db, project, scene


def _push_payload(project_id: int | None, revision: int = 1, **overrides):
    payload = {
        "source_id": _NONCE,
        "revision": revision,
        "project_id": project_id,
        "active_panel_id": "manuscript" if project_id is not None else None,
        "active_scene_id": None,
        "selection_section": "body" if project_id is not None else None,
        "selection": "selected prose" if project_id is not None else "",
    }
    payload.update(overrides)
    return payload


def _auth_headers(token: str = _TOKEN):
    return {
        "Authorization": f"Bearer {token}",
        "X-LogosForge-Live-Context": _LIVE_TOKEN,
    }


def test_desktop_route_publishes_owned_context():
    client, db, project, scene = _push_client()
    payload = _push_payload(
        project.id, revision=7, active_scene_id=scene.id,
    )
    response = client.put(
        "/api/live-context", json=payload, headers=_auth_headers(),
    )
    assert response.status_code == 200
    assert response.json() == {
        "ok": True,
        "revision": 7,
        "available": True,
        "project_id": project.id,
        "active_panel_id": "manuscript",
        "active_scene_id": scene.id,
        "selection_length": len("selected prose"),
    }

    live = run_action(db, project.id, "get_live_context", {})["result"]
    assert live["active_panel_id"] == "manuscript"
    assert live["selection_section"] == "body"
    assert live["revision"] == 7
    selected = run_action(
        db, project.id, "get_current_selection", {},
    )["result"]
    assert selected["selection"] == "selected prose"


def test_desktop_route_requires_bearer_token_mode_and_instance_nonce():
    client, _, project, _ = _push_client()
    payload = _push_payload(project.id)
    assert client.put("/api/live-context", json=payload).status_code == 403
    assert client.put(
        "/api/live-context",
        json=payload,
        headers={"Authorization": f"Bearer {_TOKEN}"},
    ).status_code == 403

    wrong_bearer = {
        **_auth_headers("wrong-desktop-bearer"),
    }
    assert client.put(
        "/api/live-context", json=payload, headers=wrong_bearer,
    ).status_code == 403

    wrong_capability = {
        **_auth_headers(),
        "X-LogosForge-Live-Context": "wrong-live-context-capability",
    }
    assert client.put(
        "/api/live-context", json=payload, headers=wrong_capability,
    ).status_code == 403

    wrong_source = {**payload, "source_id": "another-instance"}
    assert client.put(
        "/api/live-context", json=wrong_source, headers=_auth_headers(),
    ).status_code == 403

    tokenless, _, tokenless_project, _ = _push_client(token="")
    assert tokenless.put(
        "/api/live-context", json=_push_payload(tokenless_project.id),
    ).status_code == 403

    capabilityless, _, capabilityless_project, _ = _push_client(live_token="")
    assert capabilityless.put(
        "/api/live-context",
        json=_push_payload(capabilityless_project.id),
        headers=_auth_headers(),
    ).status_code == 403

    lan, _, lan_project, _ = _push_client(mode="lan")
    assert lan.put(
        "/api/live-context",
        json=_push_payload(lan_project.id),
        headers=_auth_headers(),
    ).status_code == 403


def test_desktop_route_validates_project_scene_and_selection_bound():
    client, _, project, _ = _push_client()
    missing_project = client.put(
        "/api/live-context",
        json=_push_payload(999_999),
        headers=_auth_headers(),
    )
    assert missing_project.status_code == 404

    other_project_response = client.post(
        "/api/projects", json={"title": "Other"}, headers=_auth_headers(),
    )
    other_project_id = other_project_response.json()["id"]
    other_scene_response = client.post(
        f"/api/projects/{other_project_id}/scenes",
        json={"title": "Foreign"},
        headers=_auth_headers(),
    )
    foreign_scene_id = other_scene_response.json()["id"]
    foreign_scene = client.put(
        "/api/live-context",
        json=_push_payload(project.id, active_scene_id=foreign_scene_id),
        headers=_auth_headers(),
    )
    assert foreign_scene.status_code == 404
    assert get_live_context().available is False

    too_large = client.put(
        "/api/live-context",
        json=_push_payload(project.id, selection="x" * (MAX_SELECTION_CHARS + 1)),
        headers=_auth_headers(),
    )
    assert too_large.status_code == 422
    assert get_live_context().available is False


def test_desktop_route_ordered_clear_blocks_delayed_resurrection():
    client, _, project, _ = _push_client()
    assert client.put(
        "/api/live-context",
        json=_push_payload(project.id, revision=20),
        headers=_auth_headers(),
    ).status_code == 200
    cleared = client.put(
        "/api/live-context",
        json=_push_payload(None, revision=21),
        headers=_auth_headers(),
    )
    assert cleared.status_code == 200
    assert cleared.json()["available"] is False

    delayed = client.put(
        "/api/live-context",
        json=_push_payload(project.id, revision=20),
        headers=_auth_headers(),
    )
    assert delayed.status_code == 409
    assert delayed.json()["error"]["code"] == "stale_live_context_revision"
    assert get_live_context().available is False


def test_desktop_route_rejects_malformed_clear():
    client, _, _, _ = _push_client()
    response = client.put(
        "/api/live-context",
        json={
            **_push_payload(None),
            "selection": "must not survive close",
        },
        headers=_auth_headers(),
    )
    assert response.status_code == 422
    missing_project = client.put(
        "/api/live-context",
        json={"source_id": _NONCE, "revision": 2},
        headers=_auth_headers(),
    )
    assert missing_project.status_code == 422


def test_action_get_active_scene_returns_scene():
    db, proj, scene = _db_with_scene()
    set_live_context(project_id=proj.id, active_scene_id=scene.id, selection="")
    res = run_action(db, proj.id, "get_active_scene", {})
    assert res["ok"] and res["result"]["title"] == "Opening"


def test_action_get_active_scene_graceful_when_none():
    db, proj, _ = _db_with_scene()
    res = run_action(db, proj.id, "get_active_scene", {})
    assert res["ok"] is False and "active scene" in res["error"].lower()


def test_action_get_active_scene_fails_closed_for_another_project():
    db, live_project, live_scene = _db_with_scene()
    other_project = db.create_project("Other")
    set_live_context(
        project_id=live_project.id,
        active_scene_id=live_scene.id,
        selection="private draft text",
    )

    res = run_action(db, other_project.id, "get_active_scene", {})
    assert res["ok"] is False
    assert "active scene" in res["error"].lower()
    assert "Opening" not in res["error"]


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
        except (OSError, urllib.error.URLError):
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
    db, _proj, _ = _db_with_scene()
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
        def __init__(self):
            self.calls = []
            self.project_id = 1

        def execute(self, action, args=None):
            self.calls.append(action)
            return {"ok": True, "result": {"action": action}}

    c = _C()
    gateway = M.LogosForgeMcpGateway(c)
    M.call_tool(gateway, "logosforge_get_live_context", {})
    M.call_tool(gateway, "logosforge_get_current_scene", {})
    M.call_tool(gateway, "logosforge_get_current_selection", {})
    assert c.calls == ["get_live_context", "get_active_scene", "get_current_selection"]


def test_settings_defaults_present():
    from logosforge.settings import DEFAULTS
    assert DEFAULTS["api_embedded_enabled"] is False
    assert DEFAULTS["api_embedded_port"] == 8765
