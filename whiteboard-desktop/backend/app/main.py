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

import hmac
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core_client import CoreClient
from app.document_lifecycle import locked_default_project
from app.local_state import (
    LocalStateCorruptionError,
    LocalStateIOError,
    WhiteboardCreate,
    consume_recovery_notices,
    migrate_legacy,
    whiteboard_store,
)
from app.routers import (
    comments,
    documents,
    export,
    littleboy,
    outline,
    psyke,
    settings,
    whiteboard,
    writing_modes,
)

WRAPPER_VERSION = "0.1.0"
_AUTH_TOKEN = os.environ.get("LOGOSFORGE_WHITEBOARD_AUTH_TOKEN", "").strip()
_INSTANCE_NONCE = os.environ.get("LOGOSFORGE_WHITEBOARD_INSTANCE_NONCE", "").strip()

# Dev-only origins: the Vite renderer when the Whiteboard is opened in a plain
# browser (Electron loads the renderer same-origin, so this is unused there).
_DEV_ORIGINS = ["http://127.0.0.1:5173", "http://localhost:5173", "null"]


def _authorized(expected_token: str, authorization: str | None) -> bool:
    """Constant-time Bearer-token validation; blank token keeps browser dev open."""
    if not expected_token:
        return True
    prefix = "Bearer "
    if not authorization or not authorization.startswith(prefix):
        return False
    return hmac.compare_digest(authorization[len(prefix):], expected_token)


@asynccontextmanager
async def lifespan(app: FastAPI):
    client = CoreClient()
    app.state.core = client
    # Seed the DEFAULT document: resolve/create its core project, fold any
    # pre-multi-document singleton files into it, and ensure it has a blocks file
    # so the library is never empty on a fresh or upgraded install.
    async with locked_default_project(client, initialize_created=migrate_legacy) as pid:
        # An existing pre-gate default may still need the one-time legacy fold.
        # Newly allocated defaults run this callback before their fresh identity
        # is published, so a reused numeric id cannot inherit stale local state.
        migrate_legacy(str(pid))
        if not whiteboard_store.exists(str(pid)):
            whiteboard_store.create(str(pid), WhiteboardCreate())
        else:
            whiteboard_store.ensure_incarnation(str(pid))
    try:
        yield
    finally:
        await client.aclose()


app = FastAPI(title="LogosForge Whiteboard backend", lifespan=lifespan)
app.state.wrapper_auth_token = _AUTH_TOKEN
app.state.instance_nonce = _INSTANCE_NONCE


@app.middleware("http")
async def require_wrapper_auth(request: Request, call_next):
    # Health stays public for process discovery. Browser CORS preflights carry
    # no Authorization header and must reach CORSMiddleware; the real request is
    # authenticated immediately afterwards.
    if request.url.path.startswith("/api/") and request.method != "OPTIONS":
        expected = str(getattr(request.app.state, "wrapper_auth_token", "") or "")
        if not _authorized(expected, request.headers.get("authorization")):
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                headers={"WWW-Authenticate": "Bearer"},
                content={
                    "error": {
                        "code": "unauthorized",
                        "message": "Missing or invalid Whiteboard session token.",
                    }
                },
            )
    return await call_next(request)


@app.exception_handler(LocalStateCorruptionError)
async def local_state_corruption_handler(
    _request: Request, exc: LocalStateCorruptionError,
) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={
            "error": {
                "code": "local_state_corrupt",
                "message": str(exc),
            }
        },
    )


@app.exception_handler(LocalStateIOError)
async def local_state_io_handler(_request: Request, exc: LocalStateIOError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": {
                "code": "local_state_io_error",
                "message": str(exc),
            }
        },
    )


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
app.include_router(settings.router)
app.include_router(export.router)


@app.get("/api/recovery/notices")
async def recovery_notices() -> dict:
    """Deliver successful automatic-recovery notices once to the desktop UI."""
    return {"notices": consume_recovery_notices()}


@app.get("/health")
async def health():
    """The Electron backend-manager polls this and only checks status == 'ok'."""
    core: CoreClient = app.state.core
    core_health = await core.health()
    return {
        "status": "ok",
        "service": "logosforge-whiteboard-backend",
        "instance_nonce": str(getattr(app.state, "instance_nonce", "") or ""),
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
