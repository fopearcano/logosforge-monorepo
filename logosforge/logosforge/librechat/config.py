"""Configuration for the optional LibreChat integration.

Stored as flat ``librechat_*`` keys in the shared LogosForge settings manager
(``logosforge.settings``). Safe, localhost-first defaults; the integration is
OFF by default, so LogosForge behaves exactly as before until a user enables it.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse

from logosforge.settings import get_manager

# LibreChat serves its web UI on port 3080 by default.
DEFAULT_BASE_URL = "http://localhost:3080"

# Flat settings keys (also declared in logosforge/settings.py DEFAULTS).
KEY_ENABLED = "librechat_enabled"
KEY_BASE_URL = "librechat_base_url"
KEY_MODE = "librechat_mode"                  # "local" | "remote"
KEY_AUTO_CONNECT = "librechat_auto_connect"
KEY_PREFER_EMBEDDED = "librechat_prefer_embedded"
KEY_BROWSER_FALLBACK = "librechat_browser_fallback"
KEY_STARTUP_COMMAND = "librechat_startup_command"
KEY_BUTTON_VISIBLE = "librechat_button_visible"

_PRIVATE_HOSTS = {"localhost", "127.0.0.1", "::1", "0.0.0.0"}


@dataclass
class LibreChatConfig:
    """User-facing LibreChat settings.

    ``enabled`` gates the whole integration. ``button_visible`` controls only
    whether the nav button shows — it is independent of availability, so the
    button is never auto-removed just because LibreChat is unreachable (it must
    be hidden through this explicit setting).
    """

    enabled: bool = False
    base_url: str = DEFAULT_BASE_URL
    mode: str = "local"                 # "local" | "remote"
    auto_connect: bool = False
    prefer_embedded: bool = True
    browser_fallback: bool = True
    startup_command: str = ""
    button_visible: bool = True

    # -- Load / save -------------------------------------------------------

    @classmethod
    def load(cls) -> "LibreChatConfig":
        m = get_manager()
        return cls(
            enabled=bool(m.get(KEY_ENABLED)),
            base_url=str(m.get(KEY_BASE_URL) or DEFAULT_BASE_URL),
            mode=_clean_mode(m.get(KEY_MODE)),
            auto_connect=bool(m.get(KEY_AUTO_CONNECT)),
            prefer_embedded=bool(m.get(KEY_PREFER_EMBEDDED)),
            browser_fallback=bool(m.get(KEY_BROWSER_FALLBACK)),
            startup_command=str(m.get(KEY_STARTUP_COMMAND) or ""),
            button_visible=bool(m.get(KEY_BUTTON_VISIBLE)),
        )

    def save(self) -> None:
        m = get_manager()
        m.set(KEY_ENABLED, bool(self.enabled))
        m.set(KEY_BASE_URL, (self.base_url or "").strip() or DEFAULT_BASE_URL)
        m.set(KEY_MODE, _clean_mode(self.mode))
        m.set(KEY_AUTO_CONNECT, bool(self.auto_connect))
        m.set(KEY_PREFER_EMBEDDED, bool(self.prefer_embedded))
        m.set(KEY_BROWSER_FALLBACK, bool(self.browser_fallback))
        m.set(KEY_STARTUP_COMMAND, (self.startup_command or "").strip())
        m.set(KEY_BUTTON_VISIBLE, bool(self.button_visible))

    # -- URL helpers -------------------------------------------------------

    def normalized_url(self) -> str:
        """Trimmed URL with a scheme and no trailing slash."""
        url = (self.base_url or "").strip()
        if url and "://" not in url:
            url = "http://" + url
        return url.rstrip("/")

    def is_valid_url(self) -> bool:
        url = self.normalized_url()
        if not url or any(ch.isspace() for ch in url):
            return False
        try:
            parsed = urlparse(url)
        except ValueError:
            return False
        return parsed.scheme in ("http", "https") and bool(parsed.hostname)

    @property
    def host(self) -> str:
        try:
            return (urlparse(self.normalized_url()).hostname or "").lower()
        except ValueError:
            return ""

    @property
    def is_localhost(self) -> bool:
        return self.host in _PRIVATE_HOSTS

    def health_url(self) -> str:
        """URL used for a lightweight reachability probe."""
        return self.normalized_url()


def _clean_mode(value: object) -> str:
    return value if value in ("local", "remote") else "local"
