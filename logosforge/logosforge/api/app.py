"""FastAPI application factory for the Logosforge HTTP API.

The Python core is the authoritative backend; this app exposes it as stable
DTOs/actions for a shared React UI used by both Electron (desktop, localhost)
and the Web/PWA (LAN/remote).  It does not contain product logic — every route
delegates to the existing core services.
"""

from __future__ import annotations

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from logosforge.api.config import ApiConfig
from logosforge.api.deps import require_auth
from logosforge.api.errors import install_error_handlers
from logosforge.api.events import ApiEventBroker
from logosforge.api.routes import ALL_ROUTERS
from logosforge.db import Database

API_PREFIX = "/api"

# Version of the HTTP DTO/action *contract* (bump when the API shape changes).
# Kept separate from the Logosforge core build version so generated clients have
# a stable contract version while still being able to check the core build.
API_CONTRACT_VERSION = "1.0.0"


def _core_version() -> str:
    try:
        from logosforge import __version__
        return str(__version__)
    except Exception:
        return "unknown"


def create_api(
    db: Database | None = None,
    config: ApiConfig | None = None,
) -> FastAPI:
    """Build the FastAPI app.

    *db* — an existing :class:`Database` to serve (tests pass an in-memory one).
    If ``None``, one is opened from ``config.db_path`` (or the default file).
    *config* — resolved :class:`ApiConfig`; defaults to :meth:`ApiConfig.from_env`.
    """
    config = config or ApiConfig.from_env()
    if db is None:
        db = Database(config.db_path or "logosforge.db")

    app = FastAPI(
        title="Logosforge API",
        version=API_CONTRACT_VERSION,
        description="Authoritative Python core for the shared React UI "
                    "(Electron desktop + Web/PWA).",
    )
    app.state.db = db
    app.state.config = config
    app.state.broker = ApiEventBroker()

    # -- CORS --------------------------------------------------------------
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.cors_origins,
        allow_origin_regex=config.allow_origin_regex,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    install_error_handlers(app)

    @app.get("/api/health", tags=["health"])
    def health():
        # Clients (Electron desktop + Web/PWA) read this to verify they're
        # talking to a compatible backend: ``api_version`` is the stable DTO
        # contract; ``core_version`` is the Logosforge build.
        return {
            "status": "ok",
            "service": "logosforge-api",
            "mode": config.mode,
            "version": app.version,          # = api_version (backward-compat)
            "api_version": API_CONTRACT_VERSION,
            "core_version": _core_version(),
        }

    # Every project/data router sits behind the auth hook (a no-op until a
    # token is configured) under the /api prefix.
    for router in ALL_ROUTERS:
        app.include_router(router, prefix=API_PREFIX, dependencies=[Depends(require_auth)])

    return app
