"""AI provider settings — a thin passthrough to the CORE's assistant settings,
plus a lightweight connection test.

The core stores the AI config GLOBALLY (``logosforge.settings``) even though its
route is project-scoped, so we pin the default document's project id. The
``api_key`` is write-only: the core never returns it, and we never forward an
empty one (which would otherwise clobber a stored key).
"""
from __future__ import annotations

from typing import Optional

import httpx
from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.core_client import core_error_message
from app.document_lifecycle import locked_default_project

router = APIRouter()


class AiSettings(BaseModel):
    provider: Optional[str] = None
    model: Optional[str] = None
    base_url: Optional[str] = None
    timeout: Optional[int] = None
    api_key: Optional[str] = None  # write-only; never returned


class AiTestResult(BaseModel):
    ok: bool
    provider: str
    reply: Optional[str] = None
    error: Optional[str] = None


def _settings_path(pid: int) -> str:
    return f"/api/projects/{pid}/assistant/settings"


def _settings_model(data: dict) -> AiSettings:
    return AiSettings(
        provider=data.get("provider") or "",
        model=data.get("model") or "",
        base_url=data.get("base_url") or "",
        timeout=int(data.get("timeout") or 0),
        api_key=None,
    )


@router.get("/api/settings/ai", response_model=AiSettings)
async def get_ai_settings(request: Request) -> AiSettings:
    core = request.app.state.core
    async with locked_default_project(core) as pid:
        data = (await core.request("GET", _settings_path(pid))).json()
        return _settings_model(data)


@router.patch("/api/settings/ai", response_model=AiSettings)
async def patch_ai_settings(request: Request, body: AiSettings) -> AiSettings:
    core = request.app.state.core
    patch = body.model_dump(exclude_unset=True)
    # Never forward an empty/blank api_key — that would wipe a stored key.
    if not (patch.get("api_key") or "").strip():
        patch.pop("api_key", None)
    async with locked_default_project(core) as pid:
        path = _settings_path(pid)
        await core.request("PATCH", path, json=patch)
        data = (await core.request("GET", path)).json()
        return _settings_model(data)


@router.post("/api/settings/ai/test", response_model=AiTestResult)
async def test_ai_connection(request: Request) -> AiTestResult:
    """Round-trip a trivial prompt through the core assistant to verify the
    configured provider actually responds. Returns ok=false + a short error
    (e.g. the core's 502 detail) when no/failed provider."""
    core = request.app.state.core
    async with locked_default_project(core) as pid:
        try:
            s = (await core.request("GET", _settings_path(pid))).json()
            provider = s.get("provider") or "logosforge"
        except Exception:
            provider = "logosforge"

        body = {
            "message": "Reply with the single word: ok",
            "system_prompt": "You are a connection test. Reply with exactly: ok",
            "history": [],
            "selected_text": "",
            "nearby_text": "",
            "document_title": "",
        }
        try:
            r = await core.request("POST", f"/api/projects/{pid}/assistant/chat", json=body)
            reply = (r.json().get("reply") or "").strip()
            return AiTestResult(ok=True, provider=provider, reply=reply[:200])
        except httpx.HTTPStatusError as exc:
            detail = core_error_message(exc, fallback="AI provider test failed")
            return AiTestResult(ok=False, provider=provider, error=detail[:500])
        except Exception as exc:  # transport / unexpected
            return AiTestResult(ok=False, provider=provider, error=str(exc)[:300])
