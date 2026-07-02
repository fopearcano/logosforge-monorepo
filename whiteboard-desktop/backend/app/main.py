"""whiteboard-desktop backend — a thin wrapper over the LogosForge core API.

It serves the flat, project-agnostic contract the Whiteboard frontend expects
(localhost:8777) by delegating to the in-process LogosForge core (which is
project-scoped). The Electron backend-manager spawns it exactly like the old
standalone backend — the difference is this one WRAPS the core instead of
reimplementing its logic.

Adapter routers for /api/whiteboard, /api/writing-modes, /api/psyke/*,
/api/littleboy/* and /api/outline/items are added in later phases.
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core_client import CoreClient
from app.local_state import WhiteboardCreate, migrate_legacy, whiteboard_store
from app.routers import comments, documents, littleboy, outline, psyke, whiteboard, writing_modes

WRAPPER_VERSION = "0.1.0"

# Dev-only origins: the Vite renderer when the Whiteboard is opened in a plain
# browser (Electron loads the renderer same-origin, so this is unused there).
_DEV_ORIGINS = ["http://127.0.0.1:5173", "http://localhost:5173"]


@asynccontextmanager
async def lifespan(app: FastAPI):
    client = CoreClient()
    app.state.core = client
    # Seed the DEFAULT document: resolve/create its core project, fold any
    # pre-multi-document singleton files into it, and ensure it has a blocks file
    # so the library is never empty on a fresh or upgraded install.
    pid = await client.ensure_project()
    migrate_legacy(str(pid))
    if not whiteboard_store.exists(str(pid)):
        whiteboard_store.create(str(pid), WhiteboardCreate())
    try:
        yield
    finally:
        await client.aclose()


app = FastAPI(title="LogosForge Whiteboard backend", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_DEV_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(writing_modes.router)
app.include_router(documents.router)
app.include_router(psyke.router)
app.include_router(whiteboard.router)
app.include_router(outline.router)
app.include_router(littleboy.router)
app.include_router(comments.router)


@app.get("/health")
async def health():
    """The Electron backend-manager polls this and only checks status == 'ok'."""
    core: CoreClient = app.state.core
    core_health = await core.health()
    return {
        "status": "ok",
        "service": "logosforge-whiteboard-backend",
        "project_id": core.project_id,
        "api_version": core_health.get("api_version"),
        "core_version": core_health.get("core_version"),
        "core": core_health,
    }


@app.get("/api/version")
async def version():
    core: CoreClient = app.state.core
    core_health = await core.health()
    return {
        "name": "LogosForge Whiteboard",
        "version": WRAPPER_VERSION,
        "api_version": core_health.get("api_version"),
        "core_version": core_health.get("core_version"),
    }
