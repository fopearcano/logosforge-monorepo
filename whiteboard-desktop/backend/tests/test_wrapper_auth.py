"""Per-process Whiteboard wrapper authentication and CORS preflight."""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient


_BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))
_TMP = Path(tempfile.mkdtemp(prefix="lf-wrapper-auth-test-"))
os.environ["HOME"] = str(_TMP)
os.environ["USERPROFILE"] = str(_TMP)
os.environ["LOGOSFORGE_DATA_DIR"] = str(_TMP)
os.environ["LOGOSFORGE_DB_PATH"] = str(_TMP / "whiteboard.db")

from app.core_client import CoreClient  # noqa: E402
from app.main import _authorized, app  # noqa: E402


def test_bearer_parser_is_fail_closed_when_token_configured() -> None:
    assert _authorized("", None) is True  # plain-browser development mode
    assert _authorized("secret", None) is False
    assert _authorized("secret", "Bearer wrong") is False
    assert _authorized("secret", "Basic secret") is False
    assert _authorized("secret", "Bearer secret") is True


def test_api_requires_token_but_health_and_preflight_remain_available() -> None:
    previous = app.state.wrapper_auth_token
    app.state.wrapper_auth_token = "test-session-token"
    try:
        with TestClient(app) as client:
            denied = client.get("/api/recovery/notices")
            assert denied.status_code == 401
            assert denied.json()["error"]["code"] == "unauthorized"

            allowed = client.get(
                "/api/recovery/notices",
                headers={"Authorization": "Bearer test-session-token"},
            )
            assert allowed.status_code == 200

            assert client.get("/health").status_code == 200
            preflight = client.options(
                "/api/recovery/notices",
                headers={
                    "Origin": "null",
                    "Access-Control-Request-Method": "GET",
                    "Access-Control-Request-Headers": "authorization",
                },
            )
            assert preflight.status_code == 200
            assert preflight.headers.get("access-control-allow-origin") == "null"
    finally:
        app.state.wrapper_auth_token = previous


def test_inherited_core_api_token_cannot_lock_out_in_process_wrapper(monkeypatch) -> None:
    monkeypatch.setenv("API_AUTH_TOKEN", "unrelated-parent-token")
    core = CoreClient()
    try:
        health = asyncio.run(core.health())
        assert health["service"] == "logosforge-api"
    finally:
        asyncio.run(core.aclose())


def test_unknown_document_id_cannot_create_orphan_local_state() -> None:
    previous = app.state.wrapper_auth_token
    app.state.wrapper_auth_token = ""
    ghost_id = 987654321
    ghost_path = _TMP / "whiteboards" / f"{ghost_id}.json"
    try:
        with TestClient(app) as client:
            response = client.put(
                f"/api/whiteboard?doc={ghost_id}",
                json={"title": "Ghost project", "blocks": []},
            )
            assert response.status_code == 404
            assert "not found" in response.json()["detail"].lower()
    finally:
        app.state.wrapper_auth_token = previous
    assert not ghost_path.exists()
