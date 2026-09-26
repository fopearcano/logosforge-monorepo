"""Authenticated, allow-listed client for the Whiteboard wrapper API.

Reads are immediate.  The only write methods are focused conditional resource
updates used by the MCP proposal gateway; there is deliberately no public
generic request or arbitrary-URL escape hatch.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, TypedDict

MAX_RESPONSE_BYTES = 8 * 1024 * 1024
MAX_REQUEST_BYTES = 2 * 1024 * 1024
_MUTATION_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_COMMENT_STABLE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_COMMENTS_ETAG_RE = re.compile(
    r'^"lfwb:comments:([0-9a-f]{32}):([0-9a-f]{32})"$'
)
_PSYKE_ID_RE = re.compile(r"^[1-9][0-9]*$")
_PSYKE_TYPES = {"character", "place", "object", "lore", "theme", "other"}
MAX_COMMENTS = 20_000
MAX_COMMENT_REPLIES = 20_000
MAX_COMMENT_ID_CHARACTERS = 128
MAX_COMMENT_BLOCK_ID_CHARACTERS = 256
MAX_COMMENT_BODY_CHARACTERS = 100_000
MAX_COMMENT_QUOTE_CHARACTERS = 250_000
MAX_COMMENT_CONTEXT_CHARACTERS = 10_000
MAX_COMMENT_AUTHOR_CHARACTERS = 1_000
MAX_COMMENT_TIMESTAMP_CHARACTERS = 100
MAX_PSYKE_ID_CHARACTERS = 20
MAX_PSYKE_NAME_CHARACTERS = 1_000
MAX_PSYKE_TEXT_CHARACTERS = 250_000
MAX_PSYKE_ALIASES = 1_000
MAX_PSYKE_ALIAS_CHARACTERS = 1_000
MAX_PSYKE_ALIAS_TOTAL_CHARACTERS = 250_000
MAX_PSYKE_TIMESTAMP_CHARACTERS = 100
MAX_PSYKE_RELATION_TYPE_CHARACTERS = 1_000
MAX_PSYKE_SCENE_TITLE_CHARACTERS = 1_000
MAX_PSYKE_INTEGER_ID = 9_007_199_254_740_991


class WhiteboardApiError(RuntimeError):
    """A safe Whiteboard API failure suitable for an MCP result."""


class OutlineRead(TypedDict):
    """Validated outline payload returned by the Whiteboard backend."""

    items: list[dict[str, Any]]
    revision: str


class PsykeRead(TypedDict):
    """Validated story-bible collection returned by the Whiteboard backend."""

    results: list[dict[str, Any]]
    revision: str


class PsykeMutationResult(TypedDict):
    """Validated result of one conditional PSYKE create or patch."""

    element: dict[str, Any]
    revision: str


class PsykeRelationsRead(TypedDict):
    """Validated PSYKE relationship collection returned by Whiteboard."""

    relations: list[dict[str, Any]]
    revision: str


class PsykeProgressionsRead(TypedDict):
    """Validated PSYKE progression collection returned by Whiteboard."""

    progressions: list[dict[str, Any]]
    revision: str


class PsykeRelationMutationResult(TypedDict):
    """Validated result of one conditional PSYKE relationship creation."""

    relation: dict[str, Any]
    revision: str


class PsykeProgressionMutationResult(TypedDict):
    """Validated result of one conditional PSYKE progression mutation."""

    progression: dict[str, Any]
    revision: str


class CommentRead(TypedDict):
    """Validated full comment-thread collection returned by Whiteboard."""

    comments: list[dict[str, Any]]
    revision: str


class CommentMutationResult(TypedDict):
    """Validated result of one conditional comment mutation."""

    comment: dict[str, Any]
    revision: str


def _valid_revision(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 32
        and all(character in "0123456789abcdef" for character in value)
    )


class WhiteboardApiClient:
    """Small allow-listed client with no caller-controlled method or URL."""

    def __init__(self, base_url: str, auth_token: str, timeout: float = 15.0) -> None:
        self._base = base_url.rstrip("/")
        self._auth = auth_token
        self._timeout = float(timeout)

    def _request_json_with_headers(
        self,
        method: str,
        path: str,
        query: dict[str, Any] | None = None,
        *,
        body: dict[str, Any] | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> tuple[Any, dict[str, str]]:
        url = f"{self._base}{path}"
        if query:
            encoded = urllib.parse.urlencode(
                {key: value for key, value in query.items() if value is not None}
            )
            if encoded:
                url = f"{url}?{encoded}"
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self._auth}",
            "User-Agent": "LogosForge-Whiteboard-MCP",
        }
        if extra_headers:
            headers.update(extra_headers)
        data: bytes | None = None
        if body is not None:
            try:
                data = json.dumps(
                    body,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                    allow_nan=False,
                ).encode("utf-8")
            except (TypeError, ValueError, OverflowError, UnicodeError):
                raise WhiteboardApiError("The Whiteboard write payload is not valid JSON.") from None
            if len(data) > MAX_REQUEST_BYTES:
                raise WhiteboardApiError(
                    "The Whiteboard write payload exceeded the safe size limit."
                )
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            url,
            data=data,
            method=method,
            headers=headers,
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:
                raw = response.read(MAX_RESPONSE_BYTES + 1)
                source_headers = getattr(response, "headers", None)
                try:
                    response_headers = {
                        str(key).lower(): str(value)
                        for key, value in source_headers.items()
                    } if source_headers is not None else {}
                except (AttributeError, TypeError, ValueError):
                    response_headers = {}
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                body = exc.read(4096).decode("utf-8", "replace")
                parsed = json.loads(body)
                value = parsed.get("error", parsed.get("detail", ""))
                if isinstance(value, dict):
                    message = str(value.get("message") or value.get("detail") or "")
                    code = value.get("code")
                    current_revision = value.get("current_revision")
                    detail = message
                    if isinstance(code, str) and code:
                        detail = f"{code}: {detail}" if detail else code
                    if _valid_revision(current_revision):
                        detail = f"{detail} (current revision {current_revision})"
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
            return json.loads(raw.decode("utf-8")), response_headers
        except (UnicodeError, json.JSONDecodeError):
            raise WhiteboardApiError("The Whiteboard API returned invalid JSON.") from None

    def _request_json(
        self,
        method: str,
        path: str,
        query: dict[str, Any] | None = None,
        *,
        body: dict[str, Any] | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> Any:
        value, _headers = self._request_json_with_headers(
            method,
            path,
            query,
            body=body,
            extra_headers=extra_headers,
        )
        return value

    def _get(self, path: str, query: dict[str, Any] | None = None) -> Any:
        return self._request_json("GET", path, query)

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
        return self._validated_document(value)

    @staticmethod
    def _validated_document(value: Any) -> dict[str, Any]:
        if (
            not isinstance(value, dict)
            or not isinstance(value.get("blocks"), list)
            or not _valid_revision(value.get("revision"))
            or not _valid_revision(value.get("incarnation"))
        ):
            raise WhiteboardApiError("The Whiteboard manuscript has an invalid shape.")
        return value

    def get_outline(self, document_id: int) -> OutlineRead:
        value = self._get("/api/outline/items", self._document_query(document_id))
        return self._validated_outline(value)

    @staticmethod
    def _validated_outline(value: Any) -> OutlineRead:
        items = value.get("items") if isinstance(value, dict) else None
        revision = value.get("revision") if isinstance(value, dict) else None
        if (
            not isinstance(items, list)
            or any(not isinstance(item, dict) for item in items)
            or not _valid_revision(revision)
        ):
            raise WhiteboardApiError("The Whiteboard outline has an invalid shape.")
        return {"items": items, "revision": revision}

    @staticmethod
    def _conditional_headers(
        kind: str,
        incarnation: str,
        expected_revision: str,
        mutation_id: str,
    ) -> dict[str, str]:
        if kind not in {"whiteboard", "outline", "comments", "psyke"}:
            raise WhiteboardApiError("The Whiteboard resource kind is invalid.")
        if not _valid_revision(incarnation) or not _valid_revision(expected_revision):
            raise WhiteboardApiError("The Whiteboard write precondition is invalid.")
        if _MUTATION_ID_RE.fullmatch(mutation_id) is None:
            raise WhiteboardApiError("The Whiteboard mutation id is invalid.")
        return {
            "If-Match": f'"lfwb:{kind}:{incarnation}:{expected_revision}"',
            "X-LogosForge-Document-Incarnation": incarnation,
            "X-LogosForge-Mutation-Id": mutation_id,
        }

    def update_document(
        self,
        document_id: int,
        *,
        incarnation: str,
        expected_revision: str,
        mutation_id: str,
        patch: dict[str, Any],
    ) -> dict[str, Any]:
        value = self._request_json(
            "PUT",
            "/api/whiteboard",
            self._document_query(document_id),
            body=patch,
            extra_headers=self._conditional_headers(
                "whiteboard", incarnation, expected_revision, mutation_id
            ),
        )
        return self._validated_document(value)

    def replace_outline(
        self,
        document_id: int,
        *,
        incarnation: str,
        expected_revision: str,
        mutation_id: str,
        items: list[dict[str, Any]],
    ) -> OutlineRead:
        value = self._request_json(
            "PUT",
            "/api/outline/items",
            self._document_query(document_id),
            body={"items": items},
            extra_headers=self._conditional_headers(
                "outline", incarnation, expected_revision, mutation_id
            ),
        )
        return self._validated_outline(value)

    @staticmethod
    def _bounded_utf8_string(
        value: Any,
        maximum_characters: int,
        *,
        allow_empty: bool = True,
    ) -> bool:
        if (
            not isinstance(value, str)
            or len(value) > maximum_characters
            or (not allow_empty and not value)
        ):
            return False
        try:
            value.encode("utf-8")
        except UnicodeError:
            return False
        return True

    @staticmethod
    def _validated_comment_anchor(value: Any) -> dict[str, Any]:
        required = {"block_index", "from_offset", "to_offset"}
        optional = {
            "block_id",
            "end_block_index",
            "end_block_id",
            "prefix",
            "suffix",
        }
        if (
            not isinstance(value, dict)
            or not required.issubset(value)
            or not set(value).issubset(required | optional)
        ):
            raise WhiteboardApiError(
                "The Whiteboard comment response has an invalid shape."
            )
        for key in ("block_index", "from_offset", "to_offset"):
            item = value[key]
            if isinstance(item, bool) or not isinstance(item, int) or not 0 <= item <= 2**31 - 1:
                raise WhiteboardApiError(
                    "The Whiteboard comment response has an invalid shape."
                )
        end_index = value.get("end_block_index")
        if end_index is not None and (
            isinstance(end_index, bool)
            or not isinstance(end_index, int)
            or not 0 <= end_index <= 2**31 - 1
        ):
            raise WhiteboardApiError(
                "The Whiteboard comment response has an invalid shape."
            )
        for key in ("block_id", "end_block_id"):
            identifier = value.get(key)
            if identifier is not None and not WhiteboardApiClient._bounded_utf8_string(
                identifier,
                MAX_COMMENT_BLOCK_ID_CHARACTERS,
                allow_empty=False,
            ):
                raise WhiteboardApiError(
                    "The Whiteboard comment response has an invalid shape."
                )
        for key in ("prefix", "suffix"):
            context = value.get(key, "")
            if not WhiteboardApiClient._bounded_utf8_string(
                context, MAX_COMMENT_CONTEXT_CHARACTERS
            ):
                raise WhiteboardApiError(
                    "The Whiteboard comment response has an invalid shape."
                )
        return dict(value)

    @staticmethod
    def _validated_comment_reply(value: Any) -> dict[str, Any]:
        expected = {"id", "body", "author", "created_at"}
        if not isinstance(value, dict) or set(value) != expected:
            raise WhiteboardApiError(
                "The Whiteboard comment response has an invalid shape."
            )
        if (
            not isinstance(value.get("id"), str)
            or _COMMENT_STABLE_ID_RE.fullmatch(value["id"]) is None
            or not WhiteboardApiClient._bounded_utf8_string(
                value.get("body"), MAX_COMMENT_BODY_CHARACTERS
            )
            or not WhiteboardApiClient._bounded_utf8_string(
                value.get("author"),
                MAX_COMMENT_AUTHOR_CHARACTERS,
                allow_empty=False,
            )
            or not WhiteboardApiClient._bounded_utf8_string(
                value.get("created_at"),
                MAX_COMMENT_TIMESTAMP_CHARACTERS,
                allow_empty=False,
            )
        ):
            raise WhiteboardApiError(
                "The Whiteboard comment response has an invalid shape."
            )
        return dict(value)

    @staticmethod
    def _validated_comment(value: Any) -> dict[str, Any]:
        expected = {
            "id",
            "anchor",
            "quote",
            "body",
            "resolved",
            "replies",
            "created_at",
            "updated_at",
        }
        if not isinstance(value, dict) or set(value) != expected:
            raise WhiteboardApiError(
                "The Whiteboard comment response has an invalid shape."
            )
        comment_id = value.get("id")
        replies = value.get("replies")
        if (
            not isinstance(comment_id, str)
            or _COMMENT_STABLE_ID_RE.fullmatch(comment_id) is None
            or not WhiteboardApiClient._bounded_utf8_string(
                value.get("quote"), MAX_COMMENT_QUOTE_CHARACTERS
            )
            or not WhiteboardApiClient._bounded_utf8_string(
                value.get("body"), MAX_COMMENT_BODY_CHARACTERS
            )
            or not isinstance(value.get("resolved"), bool)
            or not isinstance(replies, list)
            or len(replies) > MAX_COMMENT_REPLIES
            or not WhiteboardApiClient._bounded_utf8_string(
                value.get("created_at"),
                MAX_COMMENT_TIMESTAMP_CHARACTERS,
                allow_empty=False,
            )
            or not WhiteboardApiClient._bounded_utf8_string(
                value.get("updated_at"),
                MAX_COMMENT_TIMESTAMP_CHARACTERS,
                allow_empty=False,
            )
        ):
            raise WhiteboardApiError(
                "The Whiteboard comment response has an invalid shape."
            )
        anchor = WhiteboardApiClient._validated_comment_anchor(value.get("anchor"))
        validated_replies = [
            WhiteboardApiClient._validated_comment_reply(reply) for reply in replies
        ]
        reply_ids = [reply["id"] for reply in validated_replies]
        if len(reply_ids) != len(set(reply_ids)):
            raise WhiteboardApiError(
                "The Whiteboard comment response has an invalid shape."
            )
        return {
            "id": comment_id,
            "anchor": anchor,
            "quote": value["quote"],
            "body": value["body"],
            "resolved": value["resolved"],
            "replies": validated_replies,
            "created_at": value["created_at"],
            "updated_at": value["updated_at"],
        }

    @staticmethod
    def _validated_comment_id(comment_id: Any) -> str:
        if (
            not isinstance(comment_id, str)
            or _COMMENT_STABLE_ID_RE.fullmatch(comment_id) is None
        ):
            raise WhiteboardApiError("The Whiteboard comment id is invalid.")
        return comment_id

    @staticmethod
    def _comment_revision_from_headers(
        headers: dict[str, str], incarnation: str
    ) -> str:
        etag = headers.get("etag")
        match = _COMMENTS_ETAG_RE.fullmatch(etag) if isinstance(etag, str) else None
        if match is None or match.group(1) != incarnation:
            raise WhiteboardApiError(
                "The Whiteboard comment mutation response has an invalid ETag."
            )
        return match.group(2)

    def get_comments(self, document_id: int) -> CommentRead:
        value = self._get("/api/comments", self._document_query(document_id))
        comments = value.get("comments") if isinstance(value, dict) else None
        revision = value.get("revision") if isinstance(value, dict) else None
        if (
            not isinstance(comments, list)
            or len(comments) > MAX_COMMENTS
            or not _valid_revision(revision)
        ):
            raise WhiteboardApiError("The Whiteboard comments response has an invalid shape.")
        try:
            validated = [self._validated_comment(item) for item in comments]
        except WhiteboardApiError:
            raise WhiteboardApiError(
                "The Whiteboard comments response has an invalid shape."
            ) from None
        comment_ids = [comment["id"] for comment in validated]
        if len(comment_ids) != len(set(comment_ids)):
            raise WhiteboardApiError(
                "The Whiteboard comments response has an invalid shape."
            )
        return {"comments": validated, "revision": revision}

    def set_comment_resolution(
        self,
        document_id: int,
        comment_id: str,
        *,
        incarnation: str,
        expected_revision: str,
        mutation_id: str,
        resolved: bool,
    ) -> CommentMutationResult:
        target = self._validated_comment_id(comment_id)
        if not isinstance(resolved, bool):
            raise WhiteboardApiError("The Whiteboard comment resolution is invalid.")
        value, headers = self._request_json_with_headers(
            "PUT",
            f"/api/comments/{urllib.parse.quote(target, safe='')}",
            self._document_query(document_id),
            body={"resolved": resolved},
            extra_headers=self._conditional_headers(
                "comments", incarnation, expected_revision, mutation_id
            ),
        )
        comment = self._validated_comment(value)
        if comment["id"] != target or comment["resolved"] is not resolved:
            raise WhiteboardApiError(
                "The Whiteboard comment mutation response has an invalid target."
            )
        revision = self._comment_revision_from_headers(headers, incarnation)
        return {"comment": comment, "revision": revision}

    def reply_to_comment(
        self,
        document_id: int,
        comment_id: str,
        *,
        incarnation: str,
        expected_revision: str,
        mutation_id: str,
        body: str,
    ) -> CommentMutationResult:
        target = self._validated_comment_id(comment_id)
        if _MUTATION_ID_RE.fullmatch(mutation_id) is None:
            raise WhiteboardApiError(
                "The Whiteboard comment reply mutation id is invalid."
            )
        if not self._bounded_utf8_string(
            body, MAX_COMMENT_BODY_CHARACTERS, allow_empty=False
        ):
            raise WhiteboardApiError("The Whiteboard comment reply is invalid.")
        value, headers = self._request_json_with_headers(
            "POST",
            f"/api/comments/{urllib.parse.quote(target, safe='')}/replies",
            self._document_query(document_id),
            body={"body": body},
            extra_headers=self._conditional_headers(
                "comments", incarnation, expected_revision, mutation_id
            ),
        )
        comment = self._validated_comment(value)
        matching_replies = [
            reply for reply in comment["replies"] if reply["id"] == mutation_id
        ]
        if (
            comment["id"] != target
            or len(matching_replies) != 1
            or matching_replies[0]["body"] != body
            or matching_replies[0]["author"] != "MCP assistant"
        ):
            raise WhiteboardApiError(
                "The Whiteboard comment mutation response has an invalid reply."
            )
        revision = self._comment_revision_from_headers(headers, incarnation)
        return {"comment": comment, "revision": revision}

    def get_psyke(self, document_id: int, query: str = "") -> PsykeRead:
        value = self._get(
            "/api/psyke/search",
            {"doc": int(document_id), "q": query},
        )
        results = value.get("results") if isinstance(value, dict) else None
        revision = value.get("revision") if isinstance(value, dict) else None
        if (
            not isinstance(results, list)
            or any(not isinstance(item, dict) for item in results)
            or not _valid_revision(revision)
        ):
            raise WhiteboardApiError("The Whiteboard PSYKE response has an invalid shape.")
        try:
            validated = [self._validated_psyke_element(item) for item in results]
        except WhiteboardApiError:
            raise WhiteboardApiError(
                "The Whiteboard PSYKE response has an invalid shape."
            ) from None
        return {"results": validated, "revision": revision}

    @staticmethod
    def _validated_psyke_element(value: Any) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise WhiteboardApiError(
                "The Whiteboard PSYKE element response has an invalid shape."
            )

        element_id = value.get("id")
        name = value.get("name")
        entry_type = value.get("entry_type")
        aliases = value.get("aliases")
        description = value.get("description")
        notes = value.get("notes")
        if (
            not isinstance(element_id, str)
            or _PSYKE_ID_RE.fullmatch(element_id) is None
            or len(element_id) > MAX_PSYKE_ID_CHARACTERS
            or not isinstance(name, str)
            or not name
            or name.strip() != name
            or len(name) > MAX_PSYKE_NAME_CHARACTERS
            or not isinstance(entry_type, str)
            or entry_type not in _PSYKE_TYPES
            or not isinstance(aliases, list)
            or len(aliases) > MAX_PSYKE_ALIASES
            or any(
                not isinstance(alias, str)
                or len(alias) > MAX_PSYKE_ALIAS_CHARACTERS
                for alias in aliases
            )
            or sum(len(alias) for alias in aliases) > MAX_PSYKE_ALIAS_TOTAL_CHARACTERS
            or not isinstance(description, str)
            or len(description) > MAX_PSYKE_TEXT_CHARACTERS
            or not isinstance(notes, str)
            or len(notes) > MAX_PSYKE_TEXT_CHARACTERS
        ):
            raise WhiteboardApiError(
                "The Whiteboard PSYKE element response has an invalid shape."
            )

        validated: dict[str, Any] = {
            "id": element_id,
            "name": name,
            "entry_type": entry_type,
            "aliases": list(aliases),
            "description": description,
            "notes": notes,
        }
        for timestamp_key in ("created_at", "updated_at"):
            if timestamp_key not in value:
                continue
            timestamp = value[timestamp_key]
            if (
                timestamp is not None
                and (
                    not isinstance(timestamp, str)
                    or len(timestamp) > MAX_PSYKE_TIMESTAMP_CHARACTERS
                )
            ):
                raise WhiteboardApiError(
                    "The Whiteboard PSYKE element response has an invalid shape."
                )
            validated[timestamp_key] = timestamp
        return validated

    @staticmethod
    def _validated_psyke_mutation(value: Any) -> PsykeMutationResult:
        if not isinstance(value, dict) or value.get("ok") is not True:
            raise WhiteboardApiError(
                "The Whiteboard PSYKE mutation response has an invalid shape."
            )
        revision = value.get("revision")
        if not _valid_revision(revision):
            raise WhiteboardApiError(
                "The Whiteboard PSYKE mutation response has an invalid shape."
            )
        try:
            element = WhiteboardApiClient._validated_psyke_element(
                value.get("element")
            )
        except WhiteboardApiError:
            raise WhiteboardApiError(
                "The Whiteboard PSYKE mutation response has an invalid shape."
            ) from None
        return {"element": element, "revision": revision}

    @staticmethod
    def _valid_psyke_integer_id(value: Any) -> bool:
        return (
            not isinstance(value, bool)
            and isinstance(value, int)
            and 1 <= value <= MAX_PSYKE_INTEGER_ID
        )

    @staticmethod
    def _validated_psyke_relation(value: Any) -> dict[str, Any]:
        expected = {
            "id",
            "source_id",
            "target_id",
            "source",
            "target",
            "relation_type",
        }
        if not isinstance(value, dict) or set(value) != expected:
            raise WhiteboardApiError(
                "The Whiteboard PSYKE relation response has an invalid shape."
            )
        source_id = value.get("source_id")
        target_id = value.get("target_id")
        if (
            not WhiteboardApiClient._valid_psyke_integer_id(source_id)
            or not WhiteboardApiClient._valid_psyke_integer_id(target_id)
            or source_id == target_id
            or value.get("id") != f"{source_id}:{target_id}"
            or not WhiteboardApiClient._bounded_utf8_string(
                value.get("source"), MAX_PSYKE_NAME_CHARACTERS
            )
            or not WhiteboardApiClient._bounded_utf8_string(
                value.get("target"), MAX_PSYKE_NAME_CHARACTERS
            )
            or not WhiteboardApiClient._bounded_utf8_string(
                value.get("relation_type"),
                MAX_PSYKE_RELATION_TYPE_CHARACTERS,
            )
        ):
            raise WhiteboardApiError(
                "The Whiteboard PSYKE relation response has an invalid shape."
            )
        return {key: value[key] for key in expected}

    @staticmethod
    def _validated_psyke_progression(value: Any) -> dict[str, Any]:
        expected = {
            "id",
            "entry_id",
            "text",
            "scene_id",
            "scene_title",
            "sort_order",
        }
        if not isinstance(value, dict) or set(value) != expected:
            raise WhiteboardApiError(
                "The Whiteboard PSYKE progression response has an invalid shape."
            )
        scene_id = value.get("scene_id")
        sort_order = value.get("sort_order")
        if (
            not WhiteboardApiClient._valid_psyke_integer_id(value.get("id"))
            or not WhiteboardApiClient._valid_psyke_integer_id(value.get("entry_id"))
            or (
                scene_id is not None
                and not WhiteboardApiClient._valid_psyke_integer_id(scene_id)
            )
            or not isinstance(sort_order, int)
            or isinstance(sort_order, bool)
            or not 0 <= sort_order <= MAX_PSYKE_INTEGER_ID
            or not WhiteboardApiClient._bounded_utf8_string(
                value.get("text"), MAX_PSYKE_TEXT_CHARACTERS
            )
            or not WhiteboardApiClient._bounded_utf8_string(
                value.get("scene_title"), MAX_PSYKE_SCENE_TITLE_CHARACTERS
            )
        ):
            raise WhiteboardApiError(
                "The Whiteboard PSYKE progression response has an invalid shape."
            )
        return {key: value[key] for key in expected}

    def get_psyke_relations(self, document_id: int) -> PsykeRelationsRead:
        value = self._get(
            "/api/psyke/relations", self._document_query(document_id)
        )
        relations = value.get("relations") if isinstance(value, dict) else None
        revision = value.get("revision") if isinstance(value, dict) else None
        if not isinstance(relations, list) or not _valid_revision(revision):
            raise WhiteboardApiError(
                "The Whiteboard PSYKE relations response has an invalid shape."
            )
        try:
            validated = [self._validated_psyke_relation(item) for item in relations]
        except WhiteboardApiError:
            raise WhiteboardApiError(
                "The Whiteboard PSYKE relations response has an invalid shape."
            ) from None
        identifiers = [relation["id"] for relation in validated]
        if len(identifiers) != len(set(identifiers)):
            raise WhiteboardApiError(
                "The Whiteboard PSYKE relations response has an invalid shape."
            )
        return {"relations": validated, "revision": revision}

    def get_psyke_progressions(self, document_id: int) -> PsykeProgressionsRead:
        value = self._get(
            "/api/psyke/progressions", self._document_query(document_id)
        )
        progressions = value.get("progressions") if isinstance(value, dict) else None
        revision = value.get("revision") if isinstance(value, dict) else None
        if not isinstance(progressions, list) or not _valid_revision(revision):
            raise WhiteboardApiError(
                "The Whiteboard PSYKE progressions response has an invalid shape."
            )
        try:
            validated = [
                self._validated_psyke_progression(item) for item in progressions
            ]
        except WhiteboardApiError:
            raise WhiteboardApiError(
                "The Whiteboard PSYKE progressions response has an invalid shape."
            ) from None
        identifiers = [progression["id"] for progression in validated]
        if len(identifiers) != len(set(identifiers)):
            raise WhiteboardApiError(
                "The Whiteboard PSYKE progressions response has an invalid shape."
            )
        return {"progressions": validated, "revision": revision}

    @staticmethod
    def _validated_psyke_relation_mutation(
        value: Any,
    ) -> PsykeRelationMutationResult:
        if not isinstance(value, dict) or value.get("ok") is not True:
            raise WhiteboardApiError(
                "The Whiteboard PSYKE relation mutation response has an invalid shape."
            )
        revision = value.get("revision")
        if not _valid_revision(revision):
            raise WhiteboardApiError(
                "The Whiteboard PSYKE relation mutation response has an invalid shape."
            )
        try:
            relation = WhiteboardApiClient._validated_psyke_relation(
                value.get("relation")
            )
        except WhiteboardApiError:
            raise WhiteboardApiError(
                "The Whiteboard PSYKE relation mutation response has an invalid shape."
            ) from None
        return {"relation": relation, "revision": revision}

    @staticmethod
    def _validated_psyke_progression_mutation(
        value: Any,
    ) -> PsykeProgressionMutationResult:
        if not isinstance(value, dict) or value.get("ok") is not True:
            raise WhiteboardApiError(
                "The Whiteboard PSYKE progression mutation response has an invalid shape."
            )
        revision = value.get("revision")
        if not _valid_revision(revision):
            raise WhiteboardApiError(
                "The Whiteboard PSYKE progression mutation response has an invalid shape."
            )
        try:
            progression = WhiteboardApiClient._validated_psyke_progression(
                value.get("progression")
            )
        except WhiteboardApiError:
            raise WhiteboardApiError(
                "The Whiteboard PSYKE progression mutation response has an invalid shape."
            ) from None
        return {"progression": progression, "revision": revision}

    def create_psyke_entry(
        self,
        document_id: int,
        *,
        incarnation: str,
        expected_revision: str,
        mutation_id: str,
        entry: dict[str, Any],
    ) -> PsykeMutationResult:
        value = self._request_json(
            "POST",
            "/api/psyke/elements",
            self._document_query(document_id),
            body=entry,
            extra_headers=self._conditional_headers(
                "psyke", incarnation, expected_revision, mutation_id
            ),
        )
        return self._validated_psyke_mutation(value)

    def patch_psyke_entry(
        self,
        document_id: int,
        element_id: int,
        *,
        incarnation: str,
        expected_revision: str,
        mutation_id: str,
        patch: dict[str, Any],
    ) -> PsykeMutationResult:
        if (
            isinstance(element_id, bool)
            or not isinstance(element_id, int)
            or element_id < 1
            or len(str(element_id)) > MAX_PSYKE_ID_CHARACTERS
        ):
            raise WhiteboardApiError("The Whiteboard PSYKE element id is invalid.")
        value = self._request_json(
            "PATCH",
            f"/api/psyke/elements/{element_id}",
            self._document_query(document_id),
            body=patch,
            extra_headers=self._conditional_headers(
                "psyke", incarnation, expected_revision, mutation_id
            ),
        )
        result = self._validated_psyke_mutation(value)
        if result["element"]["id"] != str(element_id):
            raise WhiteboardApiError(
                "The Whiteboard PSYKE mutation response has an invalid shape."
            )
        return result

    def create_psyke_relation(
        self,
        document_id: int,
        *,
        incarnation: str,
        expected_revision: str,
        mutation_id: str,
        relation: dict[str, Any],
    ) -> PsykeRelationMutationResult:
        if not isinstance(relation, dict) or set(relation) != {
            "source_id",
            "target_id",
            "relation_type",
        }:
            raise WhiteboardApiError("The Whiteboard PSYKE relation is invalid.")
        source_id = relation.get("source_id")
        target_id = relation.get("target_id")
        relation_type = relation.get("relation_type")
        if (
            not self._valid_psyke_integer_id(source_id)
            or not self._valid_psyke_integer_id(target_id)
            or source_id == target_id
            or not self._bounded_utf8_string(
                relation_type, MAX_PSYKE_RELATION_TYPE_CHARACTERS
            )
            or relation_type.strip() != relation_type
        ):
            raise WhiteboardApiError("The Whiteboard PSYKE relation is invalid.")
        value = self._request_json(
            "POST",
            "/api/psyke/relations",
            self._document_query(document_id),
            body=dict(relation),
            extra_headers=self._conditional_headers(
                "psyke", incarnation, expected_revision, mutation_id
            ),
        )
        result = self._validated_psyke_relation_mutation(value)
        created = result["relation"]
        if (
            created["source_id"] != source_id
            or created["target_id"] != target_id
            or created["relation_type"] != relation_type
        ):
            raise WhiteboardApiError(
                "The Whiteboard PSYKE relation mutation response has an invalid target."
            )
        return result

    def create_psyke_progression(
        self,
        document_id: int,
        *,
        incarnation: str,
        expected_revision: str,
        mutation_id: str,
        progression: dict[str, Any],
    ) -> PsykeProgressionMutationResult:
        if not isinstance(progression, dict) or set(progression) != {
            "entry_id",
            "text",
            "scene_id",
        }:
            raise WhiteboardApiError("The Whiteboard PSYKE progression is invalid.")
        entry_id = progression.get("entry_id")
        text = progression.get("text")
        scene_id = progression.get("scene_id")
        if (
            not self._valid_psyke_integer_id(entry_id)
            or not self._bounded_utf8_string(
                text, MAX_PSYKE_TEXT_CHARACTERS, allow_empty=False
            )
            or text.strip() != text
            or (scene_id is not None and not self._valid_psyke_integer_id(scene_id))
        ):
            raise WhiteboardApiError("The Whiteboard PSYKE progression is invalid.")
        value = self._request_json(
            "POST",
            "/api/psyke/progressions",
            self._document_query(document_id),
            body=dict(progression),
            extra_headers=self._conditional_headers(
                "psyke", incarnation, expected_revision, mutation_id
            ),
        )
        result = self._validated_psyke_progression_mutation(value)
        created = result["progression"]
        if (
            created["entry_id"] != entry_id
            or created["text"] != text
            or created["scene_id"] != scene_id
        ):
            raise WhiteboardApiError(
                "The Whiteboard PSYKE progression mutation response has an invalid target."
            )
        return result

    def patch_psyke_progression(
        self,
        document_id: int,
        progression_id: int,
        *,
        incarnation: str,
        expected_revision: str,
        mutation_id: str,
        patch: dict[str, Any],
    ) -> PsykeProgressionMutationResult:
        if not self._valid_psyke_integer_id(progression_id):
            raise WhiteboardApiError(
                "The Whiteboard PSYKE progression id is invalid."
            )
        # The core progression PATCH contract is a complete replacement of
        # these two editable fields.  The gateway merges a user patch with the
        # current DTO before it reaches this allow-listed client method.
        if not isinstance(patch, dict) or set(patch) != {"text", "scene_id"}:
            raise WhiteboardApiError(
                "The Whiteboard PSYKE progression patch is invalid."
            )
        text = patch.get("text")
        scene_id = patch.get("scene_id")
        if (
            not self._bounded_utf8_string(
                text, MAX_PSYKE_TEXT_CHARACTERS, allow_empty=False
            )
            or text.strip() != text
            or (scene_id is not None and not self._valid_psyke_integer_id(scene_id))
        ):
            raise WhiteboardApiError(
                "The Whiteboard PSYKE progression patch is invalid."
            )
        value = self._request_json(
            "PATCH",
            f"/api/psyke/progressions/{progression_id}",
            self._document_query(document_id),
            body=dict(patch),
            extra_headers=self._conditional_headers(
                "psyke", incarnation, expected_revision, mutation_id
            ),
        )
        result = self._validated_psyke_progression_mutation(value)
        updated = result["progression"]
        if (
            updated["id"] != progression_id
            or updated["text"] != text
            or updated["scene_id"] != scene_id
        ):
            raise WhiteboardApiError(
                "The Whiteboard PSYKE progression mutation response has an invalid target."
            )
        return result
