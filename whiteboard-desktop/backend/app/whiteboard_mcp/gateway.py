"""Read-only Whiteboard orchestration over existing wrapper GET routes."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Any

from .client import WhiteboardApiClient, WhiteboardApiError

LOGGER = logging.getLogger(__name__)
MAX_PAGE_SIZE = 500
MAX_SNAPSHOT_BLOCKS = 200
MAX_SNAPSHOT_CHARACTERS = 250_000
MAX_SEARCH_RESULTS = 50
MAX_SEARCH_SNIPPET = 240
MAX_SEARCH_TITLE = 240
MAX_SEARCH_ID = 160
MAX_RESULT_BYTES = 256 * 1024
MAX_PAGE_PAYLOAD_BYTES = 220 * 1024
MAX_SNAPSHOT_METADATA_BYTES = 32 * 1024
_FINAL_RESULT_METADATA_RESERVE = 2 * 1024
_TRUNCATION_MARKER = "…"


class GatewayError(RuntimeError):
    """A validation or state error safe to return to an MCP client."""


def _json_bytes(value: Any) -> int:
    return len(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
    )


def _clip_string(value: str, budget: int) -> tuple[Any, int]:
    if _json_bytes(value) <= budget:
        return value, 0
    if _json_bytes("") > budget:
        return None, 1
    if _json_bytes(_TRUNCATION_MARKER) > budget:
        return "", 1
    low = 0
    high = len(value)
    while low < high:
        middle = (low + high + 1) // 2
        candidate = value[:middle] + _TRUNCATION_MARKER
        if _json_bytes(candidate) <= budget:
            low = middle
        else:
            high = middle - 1
    return value[:low] + _TRUNCATION_MARKER, 1


_KEY_PRIORITY = {
    "id": 0,
    "document_id": 1,
    "incarnation": 2,
    "title": 3,
    "name": 4,
    "type": 5,
    "entry_type": 6,
    "mode": 7,
    "text": 8,
}


def _clip_json_value(value: Any, budget: int, depth: int = 0) -> tuple[Any, int]:
    """Return deterministic JSON-compatible data no larger than ``budget`` bytes."""
    if budget < 4:
        return None, 1
    try:
        if _json_bytes(value) <= budget:
            return value, 0
    except (TypeError, ValueError, OverflowError):
        value = str(value)
        if _json_bytes(value) <= budget:
            return value, 1
    if depth >= 24:
        return None, 1
    if isinstance(value, str):
        return _clip_string(value, budget)
    if isinstance(value, list):
        clipped: list[Any] = []
        truncated = 0
        for index, item in enumerate(value):
            separator = 1 if clipped else 0
            available = budget - _json_bytes(clipped) - separator
            if available < 4:
                truncated += len(value) - index
                break
            child, child_truncated = _clip_json_value(item, available, depth + 1)
            candidate = [*clipped, child]
            if _json_bytes(candidate) > budget:
                truncated += len(value) - index
                break
            clipped = candidate
            truncated += child_truncated
        return clipped, max(1, truncated)
    if isinstance(value, dict):
        clipped_dict: dict[str, Any] = {}
        truncated = 0
        entries = sorted(
            ((str(key), key) for key in value),
            key=lambda entry: (_KEY_PRIORITY.get(entry[0], 100), entry[0]),
        )
        for position, (key, original_key) in enumerate(entries):
            separator = 1 if clipped_dict else 0
            key_cost = _json_bytes(key) + 1
            available = budget - _json_bytes(clipped_dict) - separator - key_cost
            if available < 4:
                truncated += len(entries) - position
                break
            child, child_truncated = _clip_json_value(
                value[original_key], available, depth + 1
            )
            candidate = {**clipped_dict, key: child}
            if _json_bytes(candidate) > budget:
                truncated += 1 + child_truncated
                continue
            clipped_dict = candidate
            truncated += child_truncated
        return clipped_dict, max(1, truncated)
    return (None if budget >= 4 else ""), 1


def _bounded_items(
    candidates: list[Any],
    *,
    offset: int,
    limit: int,
    total: int,
    payload_budget: int = MAX_PAGE_PAYLOAD_BYTES,
) -> tuple[list[Any], dict[str, Any]]:
    selected: list[Any] = []
    truncated_offsets: list[int] = []
    truncated_values = 0
    consumed = 0
    for item in candidates[:limit]:
        separator = 1 if selected else 0
        available = payload_budget - _json_bytes(selected) - separator
        if available < 4:
            break
        clipped, item_truncated = _clip_json_value(item, available)
        candidate = [*selected, clipped]
        if _json_bytes(candidate) > payload_budget:
            break
        if item_truncated:
            truncated_offsets.append(offset + consumed)
            truncated_values += item_truncated
        selected = candidate
        consumed += 1

    requested = min(limit, len(candidates))
    byte_limited = bool(truncated_offsets) or consumed < requested
    next_offset = offset + consumed
    return selected, {
        "offset": offset,
        "limit": limit,
        "returned": len(selected),
        "total": total,
        "next_offset": next_offset if next_offset < total else None,
        "byte_limited": byte_limited,
        "max_payload_bytes": payload_budget,
        "payload_bytes": _json_bytes(selected),
        "truncated_item_offsets": truncated_offsets,
        "truncated_value_count": truncated_values,
    }


def _page(values: list[Any], offset: int, limit: int) -> tuple[list[Any], dict[str, Any]]:
    total = len(values)
    return _bounded_items(
        values[offset : offset + limit],
        offset=offset,
        limit=limit,
        total=total,
    )


def _bounded_success(value: Any) -> dict[str, Any]:
    response = {"ok": True, "result": value}
    original_bytes = _json_bytes(response)
    if original_bytes <= MAX_RESULT_BYTES:
        return response

    content_budget = MAX_RESULT_BYTES - _FINAL_RESULT_METADATA_RESERVE
    for _attempt in range(4):
        clipped, truncated = _clip_json_value(value, content_budget)
        metadata = {
            "byte_limited": True,
            "max_result_bytes": MAX_RESULT_BYTES,
            "original_bytes": original_bytes,
            "truncated_value_count": max(1, truncated),
        }
        if isinstance(clipped, dict):
            result = {**clipped, "_mcp_output": metadata}
        else:
            result = {"data": clipped, "_mcp_output": metadata}
        response = {"ok": True, "result": result}
        response_bytes = _json_bytes(response)
        if response_bytes <= MAX_RESULT_BYTES:
            return response
        content_budget = max(
            4,
            content_budget - (response_bytes - MAX_RESULT_BYTES) - 128,
        )

    return {
        "ok": True,
        "result": {
            "_mcp_output": {
                "byte_limited": True,
                "max_result_bytes": MAX_RESULT_BYTES,
                "original_bytes": original_bytes,
                "truncated_value_count": 1,
            }
        },
    }


def bounded_gateway_response(response: dict[str, Any]) -> dict[str, Any]:
    """Apply the wire-size contract to responses created outside call_gateway."""
    if _json_bytes(response) <= MAX_RESULT_BYTES:
        return response
    if response.get("ok") is True:
        return _bounded_success(response.get("result"))
    error, _ = _clip_string(_text(response.get("error")), MAX_RESULT_BYTES // 2)
    return {"ok": False, "error": error}


def _text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if value is None:
        return ""
    return str(value)


def _json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _snippet(text: str, needle: str) -> str:
    compact = " ".join(text.split())
    folded = compact.casefold()
    index = folded.find(needle)
    if index < 0:
        return compact[:MAX_SEARCH_SNIPPET]
    half = MAX_SEARCH_SNIPPET // 2
    start = max(0, index - half)
    end = min(len(compact), start + MAX_SEARCH_SNIPPET)
    start = max(0, end - MAX_SEARCH_SNIPPET)
    prefix = "…" if start else ""
    suffix = "…" if end < len(compact) else ""
    return f"{prefix}{compact[start:end]}{suffix}"


def _short_search_field(value: Any, maximum: int) -> Any:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    rendered = value if isinstance(value, str) else _json_text(value)
    if len(rendered) <= maximum:
        return rendered
    return rendered[: maximum - 1] + _TRUNCATION_MARKER


class WhiteboardMcpGateway:
    """Per-stdio-session selection state plus bounded, read-only views."""

    def __init__(self, client: WhiteboardApiClient) -> None:
        self.client = client
        self.selected_document_id: int | None = None

    def capabilities(self) -> dict[str, Any]:
        return {
            "server": "logosforge-whiteboard",
            "version": "1.0.0",
            "read_only": True,
            "tool_prefix": "logosforge_whiteboard_",
            "writes_available": False,
            "data_source": "authenticated Whiteboard GET API only",
            "features": [
                "document_selection",
                "bounded_manuscript_snapshot",
                "outline",
                "comments",
                "psyke",
                "bounded_search",
            ],
            "limits": {
                "maximum_page_size": MAX_PAGE_SIZE,
                "maximum_snapshot_blocks": MAX_SNAPSHOT_BLOCKS,
                "maximum_snapshot_characters": MAX_SNAPSHOT_CHARACTERS,
                "maximum_search_results": MAX_SEARCH_RESULTS,
                "maximum_search_title_characters": MAX_SEARCH_TITLE,
                "maximum_search_id_characters": MAX_SEARCH_ID,
                "maximum_serialized_result_bytes": MAX_RESULT_BYTES,
            },
        }

    def list_documents(self, offset: int, limit: int) -> dict[str, Any]:
        documents = self.client.list_documents()
        live_ids = {int(item["id"]) for item in documents if str(item.get("id", "")).isdigit()}
        if self.selected_document_id not in live_ids:
            self.selected_document_id = None
        values, page = _page(documents, offset, limit)
        return {
            "documents": values,
            "selected_document_id": self.selected_document_id,
            "page": page,
        }

    def select_document(self, document_id: int) -> dict[str, Any]:
        wanted = int(document_id)
        documents = self.client.list_documents()
        selected = next(
            (item for item in documents if str(item.get("id", "")) == str(wanted)),
            None,
        )
        if selected is None:
            raise GatewayError(f"Whiteboard document {wanted} was not found.")
        self.selected_document_id = wanted
        return {"selected_document_id": wanted, "document": selected}

    def _document_id(self, document_id: int | None = None) -> int:
        if document_id is not None:
            return int(document_id)
        if self.selected_document_id is not None:
            return self.selected_document_id
        documents = self.client.list_documents()
        if len(documents) == 1:
            try:
                selected = int(documents[0]["id"])
            except (KeyError, TypeError, ValueError):
                raise WhiteboardApiError("The Whiteboard document list has an invalid id.") from None
            self.selected_document_id = selected
            return selected
        if not documents:
            raise GatewayError("Whiteboard has no documents.")
        raise GatewayError(
            "No Whiteboard document is selected. Call logosforge_whiteboard_list_documents "
            "and logosforge_whiteboard_select_document first."
        )

    def current_document(self) -> dict[str, Any]:
        document_id = self._document_id()
        documents = self.client.list_documents()
        current = next(
            (item for item in documents if str(item.get("id", "")) == str(document_id)),
            None,
        )
        if current is None:
            self.selected_document_id = None
            raise GatewayError("The selected Whiteboard document no longer exists.")
        return {"selected_document_id": document_id, "document": current}

    def document_snapshot(
        self,
        document_id: int | None,
        offset: int,
        limit: int,
        max_characters: int,
    ) -> dict[str, Any]:
        resolved = self._document_id(document_id)
        raw = self.client.get_document(resolved)
        blocks = raw.get("blocks", [])
        if not isinstance(blocks, list):
            raise WhiteboardApiError("The Whiteboard manuscript has invalid blocks.")
        candidates = blocks[offset : offset + limit]
        character_candidates: list[dict[str, Any]] = []
        characters = 0
        character_limited = False
        truncated_block_ids: list[Any] = []
        for block in candidates:
            if not isinstance(block, dict):
                raise WhiteboardApiError("The Whiteboard manuscript contains an invalid block.")
            block_size = len(_text(block.get("text")))
            if character_candidates and characters + block_size > max_characters:
                character_limited = True
                break
            if not character_candidates and block_size > max_characters:
                clipped = dict(block)
                clipped["text"] = _text(block.get("text"))[:max_characters]
                character_candidates.append(clipped)
                truncated_block_ids.append(block.get("id", offset))
                characters = max_characters
                character_limited = True
                break
            character_candidates.append(block)
            characters += block_size

        metadata = dict(raw)
        metadata.pop("blocks", None)
        clipped_metadata, metadata_truncated = _clip_json_value(
            metadata,
            MAX_SNAPSHOT_METADATA_BYTES,
        )
        if not isinstance(clipped_metadata, dict):
            clipped_metadata = {}
            metadata_truncated = max(1, metadata_truncated)
        block_budget = max(
            4,
            MAX_PAGE_PAYLOAD_BYTES - _json_bytes(clipped_metadata) - 512,
        )
        selected, page = _bounded_items(
            character_candidates,
            offset=offset,
            limit=limit,
            total=len(blocks),
            payload_budget=block_budget,
        )
        manuscript = clipped_metadata
        manuscript["blocks"] = selected
        page.update(
            {
                "characters": sum(
                    len(_text(block.get("text")))
                    for block in selected
                    if isinstance(block, dict)
                ),
                "max_characters": max_characters,
                "character_limited": character_limited,
                "truncated_block_ids": truncated_block_ids,
                "metadata_byte_limited": bool(metadata_truncated),
                "metadata_truncated_value_count": metadata_truncated,
                "metadata_bytes": _json_bytes(clipped_metadata),
                "maximum_metadata_bytes": MAX_SNAPSHOT_METADATA_BYTES,
            }
        )
        return {"document": manuscript, "page": page}

    def outline(self, document_id: int | None, offset: int, limit: int) -> dict[str, Any]:
        resolved = self._document_id(document_id)
        values, page = _page(self.client.get_outline(resolved), offset, limit)
        return {"document_id": resolved, "items": values, "page": page}

    def comments(
        self,
        document_id: int | None,
        offset: int,
        limit: int,
        include_resolved: bool,
    ) -> dict[str, Any]:
        resolved = self._document_id(document_id)
        comments = self.client.get_comments(resolved)
        if not include_resolved:
            comments = [item for item in comments if not bool(item.get("resolved"))]
        values, page = _page(comments, offset, limit)
        return {"document_id": resolved, "comments": values, "page": page}

    def psyke(
        self,
        document_id: int | None,
        query: str,
        entry_type: str,
        offset: int,
        limit: int,
    ) -> dict[str, Any]:
        resolved = self._document_id(document_id)
        entries = self.client.get_psyke(resolved, query)
        if entry_type and entry_type != "all":
            entries = [item for item in entries if item.get("entry_type") == entry_type]
        values, page = _page(entries, offset, limit)
        return {
            "document_id": resolved,
            "query": query,
            "entry_type": entry_type or "all",
            "entries": values,
            "page": page,
        }

    def search(
        self,
        query: str,
        document_id: int | None,
        scope: str,
        limit: int,
    ) -> dict[str, Any]:
        resolved = self._document_id(document_id)
        needle = query.strip().casefold()
        if not needle:
            raise GatewayError("Search query must not be empty.")

        matches: list[dict[str, Any]] = []
        total = 0

        def add(kind: str, item_id: Any, title: str, haystack: str) -> None:
            nonlocal total
            if needle not in haystack.casefold():
                return
            total += 1
            if len(matches) < limit:
                matches.append(
                    {
                        "scope": kind,
                        "id": _short_search_field(item_id, MAX_SEARCH_ID),
                        "title": _short_search_field(title, MAX_SEARCH_TITLE),
                        "snippet": _snippet(haystack, needle),
                    }
                )

        if scope in {"all", "manuscript"}:
            document = self.client.get_document(resolved)
            add("manuscript", document.get("id"), _text(document.get("title")), _text(document.get("title")))
            for index, block in enumerate(document.get("blocks", [])):
                if isinstance(block, dict):
                    add(
                        "manuscript",
                        block.get("id", index),
                        f"Block {index + 1} ({_text(block.get('type')) or 'paragraph'})",
                        _text(block.get("text")),
                    )

        if scope in {"all", "outline"}:
            for index, item in enumerate(self.client.get_outline(resolved)):
                add(
                    "outline",
                    item.get("id", index),
                    _text(item.get("title") or item.get("text") or f"Outline item {index + 1}"),
                    _json_text(item),
                )

        if scope in {"all", "comments"}:
            for index, comment in enumerate(self.client.get_comments(resolved)):
                add(
                    "comments",
                    comment.get("id", index),
                    _text(comment.get("quote") or f"Comment {index + 1}"),
                    _json_text(comment),
                )

        if scope in {"all", "psyke"}:
            # Fetching q="" lets the bounded local search include Whiteboard's
            # description field, which the current backend q route does not index.
            for index, entry in enumerate(self.client.get_psyke(resolved, "")):
                add(
                    "psyke",
                    entry.get("id", index),
                    _text(entry.get("name") or f"PSYKE entry {index + 1}"),
                    _json_text(entry),
                )

        return {
            "document_id": resolved,
            "query": query,
            "scope": scope,
            "matches": matches,
            "returned": len(matches),
            "total_matches": total,
            "truncated": total > len(matches),
            "limit": limit,
        }


def call_gateway(gateway: WhiteboardMcpGateway, action: Callable[[], Any]) -> dict[str, Any]:
    try:
        return _bounded_success(action())
    except (GatewayError, WhiteboardApiError, ValueError) as exc:
        return {"ok": False, "error": str(exc)}
    except Exception:
        LOGGER.exception("Unexpected Whiteboard MCP gateway failure")
        return {"ok": False, "error": "Unexpected Whiteboard MCP gateway failure."}
