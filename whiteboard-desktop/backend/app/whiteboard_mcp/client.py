"""Authenticated GET-only client for the Whiteboard wrapper API."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, TypedDict

MAX_RESPONSE_BYTES = 8 * 1024 * 1024


class WhiteboardApiError(RuntimeError):
    """A safe Whiteboard API failure suitable for an MCP result."""


class OutlineRead(TypedDict):
    """Validated outline payload returned by the Whiteboard backend."""

    items: list[dict[str, Any]]
    revision: str


def _valid_revision(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 32
        and all(character in "0123456789abcdef" for character in value)
    )


class WhiteboardApiClient:
    """Small allow-listed client; it intentionally exposes no generic write call."""

    def __init__(self, base_url: str, auth_token: str, timeout: float = 15.0) -> None:
        self._base = base_url.rstrip("/")
        self._auth = auth_token
        self._timeout = float(timeout)

    def _get(self, path: str, query: dict[str, Any] | None = None) -> Any:
        url = f"{self._base}{path}"
        if query:
            encoded = urllib.parse.urlencode(
                {key: value for key, value in query.items() if value is not None}
            )
            if encoded:
                url = f"{url}?{encoded}"
        request = urllib.request.Request(
            url,
            method="GET",
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {self._auth}",
                "User-Agent": "LogosForge-Whiteboard-MCP",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:
                raw = response.read(MAX_RESPONSE_BYTES + 1)
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                body = exc.read(4096).decode("utf-8", "replace")
                parsed = json.loads(body)
                value = parsed.get("error", parsed.get("detail", ""))
                if isinstance(value, dict):
                    detail = str(value.get("message") or value.get("detail") or "")
                elif isinstance(value, str):
                    detail = value
            except (OSError, UnicodeError, json.JSONDecodeError, AttributeError):
                pass
            if self._auth and self._auth in detail:
                detail = detail.replace(self._auth, "[redacted]")
            suffix = f": {detail[:500]}" if detail else ""
            raise WhiteboardApiError(f"Whiteboard API returned HTTP {exc.code}{suffix}") from None
        except (urllib.error.URLError, OSError):
            # Never include the URL or exception: lower layers can echo request
            # headers, including the bearer credential, in diagnostics.
            raise WhiteboardApiError("Cannot reach the LogosForge Whiteboard backend.") from None
        if len(raw) > MAX_RESPONSE_BYTES:
            raise WhiteboardApiError("The Whiteboard API response exceeded the safe size limit.")
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError):
            raise WhiteboardApiError("The Whiteboard API returned invalid JSON.") from None

    @staticmethod
    def _document_query(document_id: int) -> dict[str, int]:
        return {"doc": int(document_id)}

    def list_documents(self) -> list[dict[str, Any]]:
        value = self._get("/api/documents")
        documents = value.get("documents") if isinstance(value, dict) else None
        if not isinstance(documents, list) or any(not isinstance(item, dict) for item in documents):
            raise WhiteboardApiError("The Whiteboard document list has an invalid shape.")
        return documents

    def get_document(self, document_id: int) -> dict[str, Any]:
        value = self._get("/api/whiteboard", self._document_query(document_id))
        if (
            not isinstance(value, dict)
            or not isinstance(value.get("blocks"), list)
            or not _valid_revision(value.get("revision"))
        ):
            raise WhiteboardApiError("The Whiteboard manuscript has an invalid shape.")
        return value

    def get_outline(self, document_id: int) -> OutlineRead:
        value = self._get("/api/outline/items", self._document_query(document_id))
        items = value.get("items") if isinstance(value, dict) else None
        revision = value.get("revision") if isinstance(value, dict) else None
        if (
            not isinstance(items, list)
            or any(not isinstance(item, dict) for item in items)
            or not _valid_revision(revision)
        ):
            raise WhiteboardApiError("The Whiteboard outline has an invalid shape.")
        return {"items": items, "revision": revision}

    def get_comments(self, document_id: int) -> list[dict[str, Any]]:
        value = self._get("/api/comments", self._document_query(document_id))
        comments = value.get("comments") if isinstance(value, dict) else None
        if not isinstance(comments, list) or any(not isinstance(item, dict) for item in comments):
            raise WhiteboardApiError("The Whiteboard comments response has an invalid shape.")
        return comments

    def get_psyke(self, document_id: int, query: str = "") -> list[dict[str, Any]]:
        value = self._get(
            "/api/psyke/search",
            {"doc": int(document_id), "q": query},
        )
        results = value.get("results") if isinstance(value, dict) else None
        if not isinstance(results, list) or any(not isinstance(item, dict) for item in results):
            raise WhiteboardApiError("The Whiteboard PSYKE response has an invalid shape.")
        return results
