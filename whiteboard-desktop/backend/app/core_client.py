"""In-process client for the LogosForge core API.

whiteboard-desktop does NOT reimplement core logic — it wraps the core's HTTP
API. We build the core FastAPI app in-process and call it over ASGI (no second
port, no second process), which preserves the core's DTO contract — the
boundary the core's CLAUDE.md mandates ("frontends consume the core only
through its API layer"). One process, one SQLite database.

The Whiteboard UI is project-agnostic; the core API is project-scoped. This
client pins a single "Whiteboard Session" project so the frontend never has to
know about project ids.
"""
from __future__ import annotations

import os
from pathlib import Path

import httpx
from logosforge.api import ApiConfig, create_api

WHITEBOARD_PROJECT_TITLE = "Whiteboard Session"


def _default_db_path() -> str:
    """Stable per-user DB for the Whiteboard, separate from the Qt app's DB."""
    return os.environ.get("LOGOSFORGE_DB_PATH") or str(
        Path.home() / ".logosforge" / "whiteboard.db"
    )


class CoreClient:
    """Wraps the in-process core API and pins one active project."""

    def __init__(self) -> None:
        db_path = _default_db_path()
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        config = ApiConfig.from_env(mode="desktop", db_path=db_path)
        self.app = create_api(config=config)
        self._client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app),
            base_url="http://logosforge-core",
        )
        self.project_id: int | None = None

    async def aclose(self) -> None:
        await self._client.aclose()

    async def request(self, method: str, path: str, **kwargs) -> httpx.Response:
        resp = await self._client.request(method, path, **kwargs)
        resp.raise_for_status()
        return resp

    async def health(self) -> dict:
        return (await self.request("GET", "/api/health")).json()

    async def ensure_project(self) -> int:
        """Resolve the DEFAULT document's project (the legacy single 'Whiteboard
        Session'), creating it once if absent. Used to seed the first document and
        as the fallback when a request omits an explicit document id (back-compat).
        Does NOT adopt an arbitrary existing project — that would cross-wire a
        document to the wrong PSYKE bible now that multiple projects coexist."""
        if self.project_id is not None:
            return self.project_id
        projects = (await self.request("GET", "/api/projects")).json()
        chosen = next(
            (p for p in projects if p.get("title") == WHITEBOARD_PROJECT_TITLE),
            None,
        )
        if chosen is None:
            chosen = await self.create_project(WHITEBOARD_PROJECT_TITLE)
        self.project_id = int(chosen["id"])
        return self.project_id

    # -- Document <-> project CRUD (each whiteboard document = one core project) --

    async def list_projects(self) -> list[dict]:
        return (await self.request("GET", "/api/projects")).json()

    async def create_project(self, title: str, narrative_engine: str = "") -> dict:
        body: dict = {"title": title or "Untitled"}
        if narrative_engine:
            body["narrative_engine"] = narrative_engine
        return (await self.request("POST", "/api/projects", json=body)).json()

    async def delete_project(self, pid: int) -> None:
        await self.request("DELETE", f"/api/projects/{pid}")
        if self.project_id == pid:
            self.project_id = None  # the cached default was deleted — re-resolve later


async def resolve_pid(core: "CoreClient", doc: int | None) -> int:
    """A whiteboard document id IS its core project id. Fall back to the default
    document's project when a request omits ``doc`` (back-compat)."""
    return doc if doc is not None else await core.ensure_project()
