"""Runtime configuration for the Logosforge HTTP API.

The API can run in three modes which differ only in *transport / environment*,
not in product logic:

* ``desktop`` — bundled with Electron; binds to localhost and only accepts
  localhost origins.
* ``lan``     — served on a local network; origins come from configuration.
* ``remote``  — served publicly; origins come from configuration and an auth
  token is strongly recommended.

All values can be overridden with environment variables so the same code path
serves Electron, a LAN server or a hosted deployment.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

DEFAULT_PORT = 8765

# Origins always trusted in desktop mode (Electron / Vite dev server / PWA dev).
_LOCALHOST_ORIGIN_REGEX = r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$"


def _split_origins(raw: str) -> list[str]:
    return [o.strip() for o in raw.split(",") if o.strip()]


@dataclass
class ApiConfig:
    """Resolved API configuration."""

    host: str = "127.0.0.1"
    port: int = DEFAULT_PORT
    mode: str = "desktop"  # desktop | lan | remote
    allowed_origins: list[str] = field(default_factory=list)
    db_path: str | None = None
    auth_token: str = ""

    # -- Derived helpers ---------------------------------------------------

    @property
    def is_desktop(self) -> bool:
        return self.mode == "desktop"

    @property
    def allow_origin_regex(self) -> str | None:
        """In desktop mode any localhost port is allowed (Electron picks a
        free port for the dev server); other modes use the explicit list."""
        return _LOCALHOST_ORIGIN_REGEX if self.is_desktop else None

    @property
    def cors_origins(self) -> list[str]:
        if self.is_desktop:
            # Regex covers localhost; keep an explicit list too for safety.
            return self.allowed_origins or [
                "http://localhost",
                "http://127.0.0.1",
            ]
        return self.allowed_origins

    # -- Construction ------------------------------------------------------

    @classmethod
    def from_env(cls, **overrides) -> "ApiConfig":
        """Build a config from ``API_*`` environment variables.

        Recognised variables:
            API_HOST, API_PORT, API_MODE, API_ALLOWED_ORIGINS (comma list),
            API_AUTH_TOKEN, LOGOSFORGE_DB_PATH.
        Keyword *overrides* win over the environment.
        """
        mode = os.environ.get("API_MODE", "desktop").strip() or "desktop"
        if mode not in ("desktop", "lan", "remote"):
            mode = "desktop"

        try:
            port = int(os.environ.get("API_PORT", str(DEFAULT_PORT)))
        except ValueError:
            port = DEFAULT_PORT

        cfg = cls(
            host=os.environ.get("API_HOST", "127.0.0.1").strip() or "127.0.0.1",
            port=port,
            mode=mode,
            allowed_origins=_split_origins(os.environ.get("API_ALLOWED_ORIGINS", "")),
            db_path=os.environ.get("LOGOSFORGE_DB_PATH") or None,
            auth_token=os.environ.get("API_AUTH_TOKEN", "").strip(),
        )
        for key, value in overrides.items():
            setattr(cfg, key, value)
        return cfg
