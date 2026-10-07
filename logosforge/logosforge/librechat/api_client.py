"""HTTP client for the canonical LogosForge Pro API.

Used by the MCP gateway and out-of-process bridge consumers.  It never touches
SQLite directly: reads and revision-aware proposals target the typed REST
routes, while legacy live-editor operations use the connector action endpoint.
Localhost is the default; an optional bearer token is sent when configured.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

DEFAULT_BASE_URL = "http://127.0.0.1:8765"


class LogosForgeApiError(RuntimeError):
    """Raised when the LogosForge API is unreachable or returns an error."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        error_code: str = "",
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.error_code = error_code


class LogosForgeApiClient:
    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        project_id: int | None = None,
        timeout: float = 15.0,
        auth_token: str = "",
        api_prefix: str = "/api",
    ) -> None:
        self._base = (base_url or DEFAULT_BASE_URL).rstrip("/")
        self._project_id = int(project_id) if project_id is not None else None
        self._timeout = float(timeout)
        self._auth = auth_token or ""
        # All Logosforge data routers mount under this prefix (API_PREFIX).
        self._prefix = "/" + (api_prefix or "").strip("/") if api_prefix else ""

    @property
    def project_id(self) -> int | None:
        return self._project_id

    @property
    def base_url(self) -> str:
        return self._base

    @property
    def has_auth_token(self) -> bool:
        return bool(self._auth)

    @property
    def api_prefix(self) -> str:
        return self._prefix

    def api_path(self, suffix: str) -> str:
        return f"{self._prefix}/{suffix.lstrip('/')}"

    def project_path(self, suffix: str = "", project_id: int | None = None) -> str:
        pid = int(project_id) if project_id is not None else self.require_project_id()
        base = self.api_path(f"projects/{pid}")
        return f"{base}/{suffix.lstrip('/')}" if suffix else base

    def select_project(self, project_id: int) -> dict:
        """Validate and select the project used by project-scoped helpers."""
        project = self.get_project(project_id)
        self._project_id = int(project_id)
        return project

    def require_project_id(self) -> int:
        if self._project_id is None:
            raise LogosForgeApiError(
                "No LogosForge project is selected. Call logosforge_list_projects "
                "and logosforge_select_project first."
            )
        return self._project_id

    # -- Transport ---------------------------------------------------------

    def request(
        self,
        method: str,
        path: str,
        body: dict | None = None,
        query: dict[str, Any] | None = None,
        *,
        idempotency_key: str = "",
    ) -> Any:
        """Issue one authenticated API request.

        ``path`` is always supplied by the gateway itself, never copied from an
        MCP argument.  Keeping this transport helper public avoids duplicating
        HTTP/auth/error handling while the gateway retains a strict route
        allow-list.
        """
        url = f"{self._base}{path}"
        if query:
            encoded = urllib.parse.urlencode(
                {key: value for key, value in query.items() if value is not None}
            )
            if encoded:
                url = f"{url}?{encoded}"
        data = None
        headers = {"Accept": "application/json", "User-Agent": "LogosForge-MCP"}
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if idempotency_key:
            # Idempotency keys are capabilities. Keep them out of URLs and
            # query strings, which are commonly retained in access logs.
            headers["Idempotency-Key"] = idempotency_key
        if self._auth:
            headers["Authorization"] = f"Bearer {self._auth}"
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                raw = resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = ""
            error_code = ""
            try:
                detail = exc.read().decode("utf-8", "replace")[:500]
            except (OSError, UnicodeError):
                pass
            if detail:
                try:
                    parsed = json.loads(detail)
                    envelope = parsed.get("error", parsed.get("detail", parsed))
                    if isinstance(envelope, dict):
                        raw_code = envelope.get("code")
                        if isinstance(raw_code, str):
                            error_code = raw_code
                        detail = str(envelope.get("message") or envelope.get("detail") or envelope)
                    elif envelope:
                        detail = str(envelope)
                except (json.JSONDecodeError, AttributeError):
                    pass
            raise LogosForgeApiError(
                f"HTTP {exc.code} for {method} {path}: {detail}",
                status_code=int(exc.code),
                error_code=error_code,
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

    # Backward-compatible private spelling used by older callers/tests.
    def _request(self, method: str, path: str, body: dict | None = None) -> Any:
        return self.request(method, path, body)

    # -- Connector endpoints ----------------------------------------------

    def list_projects(self) -> list[dict]:
        return self.request("GET", f"{self._prefix}/projects")

    def get_project(self, project_id: int | None = None) -> dict:
        pid = int(project_id) if project_id is not None else self.require_project_id()
        return self.request("GET", f"{self._prefix}/projects/{pid}")

    def search_project(self, query: str, project_id: int | None = None) -> dict:
        pid = int(project_id) if project_id is not None else self.require_project_id()
        return self.request(
            "GET",
            f"{self._prefix}/projects/{pid}/search",
            query={"q": query},
        )

    def create_project(self, body: dict) -> dict:
        return self.request("POST", f"{self._prefix}/projects", body)

    def list_scenes(self, project_id: int | None = None) -> list[dict]:
        pid = int(project_id) if project_id is not None else self.require_project_id()
        return self.request("GET", f"{self._prefix}/projects/{pid}/scenes")

    def get_scene(self, scene_id: int, project_id: int | None = None) -> dict:
        pid = int(project_id) if project_id is not None else self.require_project_id()
        return self.request("GET", f"{self._prefix}/projects/{pid}/scenes/{int(scene_id)}")

    def get_outline(self, project_id: int | None = None) -> list[dict]:
        pid = int(project_id) if project_id is not None else self.require_project_id()
        return self.request("GET", f"{self._prefix}/projects/{pid}/outline")

    def get_timeline(self, project_id: int | None = None) -> dict:
        """Return the canonical revisioned Timeline projection."""
        pid = int(project_id) if project_id is not None else self.require_project_id()
        return self.request("GET", f"{self._prefix}/projects/{pid}/timeline")

    def get_canvas_plot(self, project_id: int | None = None) -> dict:
        """Return the canonical revisioned Canvas Plot board."""
        pid = int(project_id) if project_id is not None else self.require_project_id()
        return self.request("GET", f"{self._prefix}/projects/{pid}/canvas-plot")

    def get_continuity(self, project_id: int | None = None) -> dict:
        """Return the canonical revisioned Semantic Continuity report."""
        pid = int(project_id) if project_id is not None else self.require_project_id()
        return self.request("GET", f"{self._prefix}/projects/{pid}/continuity")

    def get_knowledge_graph(
        self,
        project_id: int | None = None,
        *,
        focus_key: str | None = None,
        depth: int = 1,
        limit: int = 100,
        include_inferred: bool = True,
        view_mode: str = "project_map",
    ) -> dict:
        """Return one bounded, revisioned Narrative Knowledge Graph view."""
        pid = int(project_id) if project_id is not None else self.require_project_id()
        return self.request(
            "GET",
            f"{self._prefix}/projects/{pid}/knowledge-graph",
            query={
                "focus_key": focus_key,
                "depth": depth,
                "limit": limit,
                "include_inferred": include_inferred,
                "view_mode": view_mode,
            },
        )

    def get_knowledge_graph_hidden_edges(
        self,
        project_id: int | None = None,
        *,
        offset: int = 0,
        limit: int = 25,
    ) -> dict:
        """Return one page from the complete hidden-edge review queue."""
        pid = int(project_id) if project_id is not None else self.require_project_id()
        return self.request(
            "GET",
            f"{self._prefix}/projects/{pid}/knowledge-graph/hidden-edges",
            query={"offset": offset, "limit": limit},
        )

    def get_timeline_command_receipt(
        self,
        idempotency_key: str,
        project_id: int | None = None,
    ) -> dict:
        """Return one durable project-scoped Timeline command receipt.

        The opaque key is deliberately sent only in the request header.  A
        ``timeline_receipt_not_found`` API error is meaningful to recovery
        callers; other 404 responses may come from an older Core API that does
        not implement the receipt endpoint.
        """
        pid = int(project_id) if project_id is not None else self.require_project_id()
        return self.request(
            "GET",
            f"{self._prefix}/projects/{pid}/timeline/command-receipt",
            idempotency_key=idempotency_key,
        )

    def get_canvas_plot_command_receipt(
        self,
        idempotency_key: str,
        project_id: int | None = None,
    ) -> dict:
        """Return one durable project-scoped Canvas Plot command receipt.

        The opaque key is deliberately sent only in the request header.  A
        ``canvas_plot_receipt_not_found`` API error is meaningful to recovery
        callers; other 404 responses may come from an older Core API that does
        not implement the receipt endpoint.
        """
        pid = int(project_id) if project_id is not None else self.require_project_id()
        return self.request(
            "GET",
            f"{self._prefix}/projects/{pid}/canvas-plot/command-receipt",
            idempotency_key=idempotency_key,
        )

    def get_knowledge_graph_command_receipt(
        self,
        idempotency_key: str,
        project_id: int | None = None,
    ) -> dict:
        """Return one durable project-scoped Knowledge Graph receipt.

        The opaque retry capability is sent only in ``Idempotency-Key``.  A
        ``knowledge_graph_receipt_not_found`` response proves receipt support
        and a clean miss; any other 404 may come from an older Core API.
        """
        pid = int(project_id) if project_id is not None else self.require_project_id()
        return self.request(
            "GET",
            f"{self._prefix}/projects/{pid}/knowledge-graph/command-receipt",
            idempotency_key=idempotency_key,
        )

    def get_continuity_command_receipt(
        self,
        idempotency_key: str,
        project_id: int | None = None,
    ) -> dict:
        """Return one durable project-scoped Continuity command receipt.

        The opaque retry capability is sent only in ``Idempotency-Key``.  A
        ``continuity_receipt_not_found`` response proves receipt support and a
        clean miss; any other 404 may come from an older Core API.
        """
        pid = int(project_id) if project_id is not None else self.require_project_id()
        return self.request(
            "GET",
            f"{self._prefix}/projects/{pid}/continuity/command-receipt",
            idempotency_key=idempotency_key,
        )

    def list_characters(self, project_id: int | None = None) -> list[dict]:
        pid = int(project_id) if project_id is not None else self.require_project_id()
        return self.request("GET", f"{self._prefix}/projects/{pid}/characters")

    def list_psyke_entries(self, project_id: int | None = None) -> list[dict]:
        pid = int(project_id) if project_id is not None else self.require_project_id()
        return self.request("GET", f"{self._prefix}/projects/{pid}/psyke/entries")

    def get_psyke_entry(self, entry_id: int, project_id: int | None = None) -> dict:
        pid = int(project_id) if project_id is not None else self.require_project_id()
        return self.request(
            "GET", f"{self._prefix}/projects/{pid}/psyke/entries/{int(entry_id)}"
        )

    def list_psyke_relations(self, project_id: int | None = None) -> list[dict]:
        pid = int(project_id) if project_id is not None else self.require_project_id()
        return self.request("GET", f"{self._prefix}/projects/{pid}/psyke/relations")

    def list_psyke_progressions(self, project_id: int | None = None) -> list[dict]:
        pid = int(project_id) if project_id is not None else self.require_project_id()
        return self.request("GET", f"{self._prefix}/projects/{pid}/psyke/progressions")

    def list_notes(self, project_id: int | None = None) -> list[dict]:
        pid = int(project_id) if project_id is not None else self.require_project_id()
        return self.request("GET", f"{self._prefix}/projects/{pid}/notes")

    def list_comments(self, project_id: int | None = None) -> list[dict]:
        pid = int(project_id) if project_id is not None else self.require_project_id()
        return self.request("GET", f"{self._prefix}/projects/{pid}/comments")

    def get_comment(
        self, comment_id: int, project_id: int | None = None,
    ) -> dict:
        pid = int(project_id) if project_id is not None else self.require_project_id()
        return self.request(
            "GET", f"{self._prefix}/projects/{pid}/comments/{int(comment_id)}",
        )

    def poll_events(self, since: int = 0, project_id: int | None = None) -> dict:
        pid = int(project_id) if project_id is not None else self.require_project_id()
        return self.request(
            "GET", f"{self._prefix}/projects/{pid}/events/poll", query={"since": int(since)}
        )

    def export_project(self, body: dict, project_id: int | None = None) -> dict:
        pid = int(project_id) if project_id is not None else self.require_project_id()
        return self.request("POST", f"{self._prefix}/projects/{pid}/export", body)

    def list_actions(self) -> list[dict]:
        pid = self.require_project_id()
        return self.request(
            "GET", f"{self._prefix}/projects/{pid}/connector/actions"
        )

    def execute(self, action: str, args: dict | None = None) -> dict:
        """Run a registered connector action. Returns the ConnectorResultDTO
        shape: ``{ok, action, result, error}``. Writes are still gated by the
        desktop connector settings on the API side."""
        pid = self.require_project_id()
        return self.request(
            "POST",
            f"{self._prefix}/projects/{pid}/connector/execute",
            {"action": action, "args": args or {}},
        )
