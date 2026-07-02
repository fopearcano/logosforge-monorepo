"""HTTP client for the LogosForge connector API.

Used by the MCP server (and any out-of-process bridge consumer) to reach
LogosForge **only** through the existing FastAPI connector endpoints
(``/projects/{id}/connector/actions`` and ``/connector/execute``). It therefore
never touches the SQLite database directly and always goes through the safe
action layer (registry allow-list + read/write settings gate). Localhost by
default; an optional bearer token is sent when the API is configured with one.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

DEFAULT_BASE_URL = "http://127.0.0.1:8765"


class LogosForgeApiError(RuntimeError):
    """Raised when the LogosForge API is unreachable or returns an error."""


class LogosForgeApiClient:
    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        project_id: int = 1,
        timeout: float = 15.0,
        auth_token: str = "",
        api_prefix: str = "/api",
    ) -> None:
        self._base = (base_url or DEFAULT_BASE_URL).rstrip("/")
        self._project_id = int(project_id)
        self._timeout = float(timeout)
        self._auth = auth_token or ""
        # All Logosforge data routers mount under this prefix (API_PREFIX).
        self._prefix = "/" + (api_prefix or "").strip("/") if api_prefix else ""

    @property
    def project_id(self) -> int:
        return self._project_id

    # -- Transport ---------------------------------------------------------

    def _request(self, method: str, path: str, body: dict | None = None) -> Any:
        url = f"{self._base}{path}"
        data = None
        headers = {"Accept": "application/json", "User-Agent": "LogosForge-MCP"}
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if self._auth:
            headers["Authorization"] = f"Bearer {self._auth}"
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                raw = resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = exc.read().decode("utf-8", "replace")[:500]
            except Exception:
                pass
            raise LogosForgeApiError(
                f"HTTP {exc.code} for {method} {path}: {detail}"
            ) from exc
        except (urllib.error.URLError, OSError) as exc:
            raise LogosForgeApiError(
                f"Cannot reach the LogosForge API at {url}: {exc}"
            ) from exc
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise LogosForgeApiError(f"Invalid JSON from {path}: {exc}") from exc

    # -- Connector endpoints ----------------------------------------------

    def list_projects(self) -> list[dict]:
        return self._request("GET", f"{self._prefix}/projects")

    def list_actions(self) -> list[dict]:
        return self._request(
            "GET", f"{self._prefix}/projects/{self._project_id}/connector/actions"
        )

    def execute(self, action: str, args: dict | None = None) -> dict:
        """Run a registered connector action. Returns the ConnectorResultDTO
        shape: ``{ok, action, result, error}``. Writes are still gated by the
        desktop connector settings on the API side."""
        return self._request(
            "POST",
            f"{self._prefix}/projects/{self._project_id}/connector/execute",
            {"action": action, "args": args or {}},
        )
