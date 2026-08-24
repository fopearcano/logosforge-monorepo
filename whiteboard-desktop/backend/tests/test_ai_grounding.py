"""Whiteboard AI regression tests — provider transport + grounding + errors.

Standalone (no pytest required):
    cd whiteboard-desktop/backend
    .venv/Scripts/python tests/test_ai_grounding.py

Everything runs against a temporary HOME/data directory and a loopback mock
provider. No real API keys, user settings, projects, or network are touched.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND_ROOT))
_TMP = Path(tempfile.mkdtemp(prefix="lf-ai-test-"))
os.environ["HOME"] = str(_TMP)
os.environ["USERPROFILE"] = str(_TMP)
os.environ["LOGOSFORGE_DATA_DIR"] = str(_TMP)
os.environ["LOGOSFORGE_DB_PATH"] = str(_TMP / "whiteboard.db")

import httpx  # noqa: E402

from app.core_client import CoreClient, core_error_message  # noqa: E402
from app.local_state import outline_items_store  # noqa: E402
from app.routers.littleboy import (  # noqa: E402
    MANUAL_OUTLINE_MAX_CHARS,
    LOGOS_NEARBY_MAX_CHARS,
    _core_chat,
    _logos_nearby_context,
    build_manual_outline_context,
)
from app.routers.settings import test_ai_connection  # noqa: E402

passed = 0
failures: list[str] = []


def check(label: str, cond: bool) -> None:
    global passed
    if cond:
        passed += 1
    else:
        failures.append(label)


# -- structured core-error extraction ---------------------------------------
request = httpx.Request("POST", "http://logosforge-core/api/projects/2/assistant/chat")
response = httpx.Response(
    502,
    request=request,
    json={
        "error": {
            "code": "assistant_error",
            "message": "Assistant request failed: OpenAI returned HTTP 401: Unauthorized",
        }
    },
)
exc = httpx.HTTPStatusError("opaque internal transport error", request=request, response=response)
check(
    "core error parser returns provider detail",
    core_error_message(exc).endswith("OpenAI returned HTTP 401: Unauthorized"),
)
check("core error parser hides internal URL", "logosforge-core" not in core_error_message(exc))


class _ErrorCore:
    project_id = 2

    async def ensure_project(self) -> int:
        return 2

    async def request(self, method: str, path: str, **_kwargs):
        if method == "GET":
            return _JsonResponse({"provider": "OpenAI"})
        raise exc


class _JsonResponse:
    def __init__(self, data: dict) -> None:
        self._data = data

    def json(self) -> dict:
        return self._data


async def _test_settings_error_translation() -> None:
    req = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(core=_ErrorCore())))
    result = await test_ai_connection(req)
    check("settings test reports provider failure", not result.ok and "OpenAI returned HTTP 401" in (result.error or ""))
    check("settings test never reports internal core URL", "logosforge-core" not in (result.error or ""))


asyncio.run(_test_settings_error_translation())


# -- manual outline hierarchy + metadata ------------------------------------
outline = [
    {
        "id": "scene",
        "parentId": "act",
        "type": "scene",
        "title": "The Locked Observatory",
        "order": 1,
        "status": "drafting",
        "tags": ["midpoint"],
        "completed": False,
        "link": {"blockIndex": 12, "quote": "The brass door refuses to move."},
    },
    {
        "id": "act",
        "parentId": None,
        "type": "act",
        "title": "Act Two",
        "order": 0,
        "status": "none",
        "tags": [],
        "completed": False,
    },
    {
        "id": "orphan",
        "parentId": "missing",
        "type": "beat",
        "title": "A clue is lost",
        "order": 2,
        "completed": True,
    },
]
manual = build_manual_outline_context(outline)
check("manual outline is explicitly authoritative", "authoritative planned structure" in manual)
check("manual outline preserves parent before child", manual.index("Act Two") < manual.index("Locked Observatory"))
check("manual outline preserves hierarchy indentation", "\n  - The Locked Observatory" in manual)
check("manual outline includes status/tags/link", "drafting" in manual and "#midpoint" in manual and "linked:" in manual)
check("manual outline keeps malformed orphan once", manual.count("A clue is lost") == 1)
large_outline = [
    {
        "id": f"node-{i}",
        "parentId": None,
        "type": "beat",
        "title": f"A deliberately long planned story beat number {i} with structural detail",
        "order": i,
    }
    for i in range(120)
]
check(
    "manual outline is bounded",
    len(build_manual_outline_context(large_outline)) <= MANUAL_OUTLINE_MAX_CHARS,
)
check("manual outline reports omitted nodes", "items omitted" in build_manual_outline_context(large_outline))


class _FakeResponse:
    def json(self) -> dict:
        return {"reply": "ok"}


class _FakeCore:
    def __init__(self) -> None:
        self.body: dict | None = None

    async def request(self, _method: str, _path: str, **kwargs):
        self.body = kwargs.get("json")
        return _FakeResponse()


async def _test_wrapper_injection() -> None:
    outline_items_store.replace("42", outline)
    fake = _FakeCore()
    result = await _core_chat(fake, 42, "system", "question", nearby_text="cursor paragraph")
    nearby = str((fake.body or {}).get("nearby_text") or "")
    check("core chat still returns reply", result == "ok")
    check("core chat injects manual outline", "The Locked Observatory" in nearby)
    check("core chat keeps cursor context after outline", nearby.index("Locked Observatory") < nearby.index("cursor paragraph"))


asyncio.run(_test_wrapper_injection())

logos_nearby = _logos_nearby_context(
    42,
    "drafted structure " * 60 + "CURSOR PARAGRAPH AT THE END",
    "OPEN COMMENT: preserve the ferryman's secret",
)
check("Logos context stays within core excerpt cap", len(logos_nearby) <= LOGOS_NEARBY_MAX_CHARS)
check("Logos context keeps manual outline", "Locked Observatory" in logos_nearby)
check("Logos context keeps writer comments", "preserve the ferryman's secret" in logos_nearby)
check("Logos context keeps cursor-nearest tail", "CURSOR PARAGRAPH AT THE END" in logos_nearby)


# -- real core route against a local mock OpenAI/Anthropic server ------------
received: list[dict] = []


class _ProviderHandler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802 (stdlib callback name)
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length) or b"{}")
        received.append({"path": self.path, "headers": dict(self.headers), "body": body})
        if self.path == "/v1/messages":
            payload = {"content": [{"type": "text", "text": "anthropic-ok"}]}
        elif self.path == "/v1/chat/completions":
            payload = {"choices": [{"message": {"role": "assistant", "content": "openai-ok"}}]}
        else:
            self.send_response(404)
            self.end_headers()
            return
        raw = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, _format: str, *args) -> None:
        pass


server = ThreadingHTTPServer(("127.0.0.1", 0), _ProviderHandler)
thread = threading.Thread(target=server.serve_forever, daemon=True)
thread.start()
provider_base = f"http://127.0.0.1:{server.server_port}"


async def _test_provider_routes() -> None:
    core = CoreClient()
    try:
        project = await core.create_project("AI transport test")
        pid = int(project["id"])
        settings_path = f"/api/projects/{pid}/assistant/settings"
        chat_path = f"/api/projects/{pid}/assistant/chat"
        chat_body = {"message": "Say ok", "history": []}

        await core.request(
            "POST",
            f"/api/projects/{pid}/psyke/entries",
            json={
                "name": "Mara Venn",
                "type": "character",
                "notes": "Harbour cartographer who distrusts the ferryman.",
                "aliases": [],
                "is_global": False,
                "details": {"description": "Protagonist"},
            },
        )

        await core.request(
            "PATCH",
            settings_path,
            json={
                "provider": "OpenAI",
                "base_url": provider_base + "/v1",
                "model": "gpt-test",
                "api_key": "openai-test-key",
            },
        )
        openai = (await core.request("POST", chat_path, json=chat_body)).json()
        check("OpenAI-compatible route succeeds", openai.get("reply") == "openai-ok")

        await core.request(
            "PATCH",
            settings_path,
            json={
                "provider": "Anthropic",
                "base_url": provider_base,
                "model": "claude-test",
                "api_key": "anthropic-test-key",
            },
        )
        anthropic = (await core.request("POST", chat_path, json=chat_body)).json()
        check("Anthropic route succeeds", anthropic.get("reply") == "anthropic-ok")
    finally:
        await core.aclose()


try:
    asyncio.run(_test_provider_routes())
finally:
    server.shutdown()
    server.server_close()

openai_req = next((r for r in received if r["path"] == "/v1/chat/completions"), None)
anthropic_req = next((r for r in received if r["path"] == "/v1/messages"), None)
check("OpenAI request uses Bearer auth", bool(openai_req and openai_req["headers"].get("Authorization") == "Bearer openai-test-key"))
check("OpenAI request sends selected model", bool(openai_req and openai_req["body"].get("model") == "gpt-test"))
openai_messages = (openai_req or {}).get("body", {}).get("messages", [])
check(
    "core chat automatically grounds Billy in PSYKE",
    any("Mara Venn" in str(message.get("content") or "") for message in openai_messages),
)
anthropic_headers = {k.lower(): v for k, v in (anthropic_req or {}).get("headers", {}).items()}
check("Anthropic request uses x-api-key", anthropic_headers.get("x-api-key") == "anthropic-test-key")
check("Anthropic request sends selected model", bool(anthropic_req and anthropic_req["body"].get("model") == "claude-test"))


print(f"Whiteboard AI tests: {passed} passed, {len(failures)} failed")
for failure in failures:
    print("  FAIL: " + failure)
if failures:
    raise SystemExit(1)
print("WHITEBOARD AI TESTS: PASS")
