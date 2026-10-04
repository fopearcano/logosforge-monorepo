"""Stateful, revision-safe orchestration gateway for LogosForge Pro.

The gateway is transport-agnostic: :mod:`mcp_server` exposes these operations
over MCP, while tests can exercise them without installing the optional MCP
SDK.  Reads use the canonical FastAPI DTO endpoints.  Writes are deliberately
two-phase:

1. a focused ``propose_*`` tool validates the request and stores the exact HTTP
   method/path/body in an in-memory, expiring proposal;
2. ``apply_proposal`` may execute only that stored request, once, when writes
   were explicitly enabled for the server process.

Scene patches additionally require the API's optimistic-concurrency revision.
Other resource updates carry a digest guard so a proposal is rejected if the
resource changed after review.  There is no arbitrary action or arbitrary URL
escape hatch.
"""

from __future__ import annotations

import base64
import copy
import difflib
import hashlib
import json
import logging
import secrets
import threading
import time
from dataclasses import dataclass, field
from typing import Any

from logosforge.librechat.api_client import LogosForgeApiClient, LogosForgeApiError

LOGGER = logging.getLogger(__name__)


class GatewayError(RuntimeError):
    """A safe error that may be returned to an MCP client."""


def _digest(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _content_review(before: str, after: str) -> dict[str, Any]:
    diff = "\n".join(
        difflib.unified_diff(
            before.splitlines(), after.splitlines(),
            fromfile="current", tofile="proposed", lineterm="", n=3,
        )
    )
    if len(diff) > 12_000:
        diff = diff[:12_000] + "\n… diff truncated …"
    return {
        "before_length": len(before),
        "after_length": len(after),
        "before_sha256": hashlib.sha256(before.encode("utf-8")).hexdigest(),
        "after_sha256": hashlib.sha256(after.encode("utf-8")).hexdigest(),
        "diff": diff,
    }


def _compact_body(body: dict[str, Any]) -> dict[str, Any]:
    """Return a review-safe body without echoing an entire manuscript."""
    out: dict[str, Any] = {}
    for key, value in body.items():
        if key == "content" and isinstance(value, str):
            out[key] = {
                "length": len(value),
                "sha256": hashlib.sha256(value.encode("utf-8")).hexdigest(),
                "preview": value[:500],
            }
        elif key == "content_base64" and isinstance(value, str):
            out[key] = {"base64_length": len(value)}
        else:
            out[key] = value
    return out


def _preview(value: Any, limit: int) -> str:
    text = str(value or "")
    return text if len(text) <= limit else text[:limit] + "…"


def _bounded_sequence(values: list[Any], limit: int = 50) -> dict[str, Any]:
    """Return a deterministic bounded review of a potentially large id list."""
    return {
        "items": values[:limit],
        "total": len(values),
        "truncated": max(0, len(values) - limit),
    }


_TIMELINE_COMMAND_FIELDS: dict[str, set[str]] = {
    "create_lane": {
        "kind", "expected_revision", "name", "color_label", "index",
    },
    "update_lane": {
        "kind", "expected_revision", "lane_id", "name", "color_label",
        "collapsed", "index",
    },
    "delete_lane": {"kind", "expected_revision", "lane_id"},
    "place_event": {
        "kind", "expected_revision", "scene_id", "lane_id", "index",
    },
    "remove_event": {"kind", "expected_revision", "scene_id"},
    "set_order_mode": {"kind", "expected_revision", "mode"},
}


def _timeline_revision(value: Any) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(char not in "0123456789abcdef" for char in value)
    ):
        raise GatewayError(
            "expected_revision must be the exact 64-character lowercase "
            "revision returned by logosforge_get_timeline."
        )
    return value


def _timeline_integer(
    value: Any,
    name: str,
    *,
    minimum: int,
    nullable: bool = False,
) -> int | None:
    if nullable and value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        qualifier = "positive " if minimum == 1 else "non-negative "
        null_note = " or null" if nullable else ""
        raise GatewayError(f"{name} must be a {qualifier}integer{null_note}.")
    return value


def _timeline_string(
    value: Any,
    name: str,
    *,
    maximum: int,
    nonempty: bool = False,
) -> str:
    if not isinstance(value, str) or (nonempty and not value.strip()):
        qualifier = "non-empty " if nonempty else ""
        raise GatewayError(f"{name} must be a {qualifier}string.")
    if len(value) > maximum:
        raise GatewayError(f"{name} may contain at most {maximum} characters.")
    return value.strip() if nonempty else value


def _normalize_timeline_command(command: dict[str, Any]) -> dict[str, Any]:
    """Validate and copy the bounded Timeline command vocabulary.

    This intentionally stays independent of ``logosforge.api.schemas``.  The
    packaged MCP companion is a lean HTTP client and must not pull FastAPI,
    SQLModel, or database modules into its frozen dependency graph.
    """
    if not isinstance(command, dict):
        raise GatewayError("Timeline command must be an object.")
    kind = command.get("kind")
    if not isinstance(kind, str) or kind not in _TIMELINE_COMMAND_FIELDS:
        raise GatewayError(
            "Timeline command kind must be one of: "
            + ", ".join(sorted(_TIMELINE_COMMAND_FIELDS))
            + "."
        )
    extra = sorted(set(command) - _TIMELINE_COMMAND_FIELDS[kind])
    if extra:
        raise GatewayError(
            "Unexpected Timeline command field(s): " + ", ".join(extra) + "."
        )
    if "expected_revision" not in command:
        raise GatewayError("Timeline command requires expected_revision.")

    normalized: dict[str, Any] = {
        "kind": kind,
        "expected_revision": _timeline_revision(command["expected_revision"]),
    }
    if kind == "create_lane":
        if "name" not in command:
            raise GatewayError("create_lane requires name.")
        normalized["name"] = _timeline_string(
            command["name"], "name", maximum=500, nonempty=True,
        )
        if "color_label" in command:
            normalized["color_label"] = _timeline_string(
                command["color_label"], "color_label", maximum=100,
            )
        if "index" in command:
            normalized["index"] = _timeline_integer(
                command["index"], "index", minimum=0, nullable=True,
            )
    elif kind == "update_lane":
        if "lane_id" not in command:
            raise GatewayError("update_lane requires lane_id.")
        normalized["lane_id"] = _timeline_integer(
            command["lane_id"], "lane_id", minimum=1,
        )
        updates = {"name", "color_label", "collapsed", "index"}.intersection(command)
        if not updates:
            raise GatewayError("update_lane must change at least one field.")
        if "name" in command:
            normalized["name"] = _timeline_string(
                command["name"], "name", maximum=500, nonempty=True,
            )
        if "color_label" in command:
            normalized["color_label"] = _timeline_string(
                command["color_label"], "color_label", maximum=100,
            )
        if "collapsed" in command:
            if not isinstance(command["collapsed"], bool):
                raise GatewayError("collapsed must be a boolean.")
            normalized["collapsed"] = command["collapsed"]
        if "index" in command:
            normalized["index"] = _timeline_integer(
                command["index"], "index", minimum=0,
            )
    elif kind == "delete_lane":
        if "lane_id" not in command:
            raise GatewayError("delete_lane requires lane_id.")
        normalized["lane_id"] = _timeline_integer(
            command["lane_id"], "lane_id", minimum=1,
        )
    elif kind == "place_event":
        if "scene_id" not in command or "lane_id" not in command:
            raise GatewayError(
                "place_event requires scene_id and lane_id; null lane_id means "
                "the virtual Unassigned lane."
            )
        normalized["scene_id"] = _timeline_integer(
            command["scene_id"], "scene_id", minimum=1,
        )
        normalized["lane_id"] = _timeline_integer(
            command["lane_id"], "lane_id", minimum=1, nullable=True,
        )
        if "index" in command:
            normalized["index"] = _timeline_integer(
                command["index"], "index", minimum=0, nullable=True,
            )
    elif kind == "remove_event":
        if "scene_id" not in command:
            raise GatewayError("remove_event requires scene_id.")
        normalized["scene_id"] = _timeline_integer(
            command["scene_id"], "scene_id", minimum=1,
        )
    else:
        mode = command.get("mode")
        if mode not in {"structural", "custom"}:
            raise GatewayError("mode must be 'structural' or 'custom'.")
        normalized["mode"] = mode
    return normalized


@dataclass
class Proposal:
    proposal_id: str
    operation: str
    method: str
    path: str
    body: dict[str, Any]
    summary: str
    project_id: int | None
    created_at: float
    expires_at: float
    request_digest: str = ""
    guard_path: str = ""
    guard_digest: str = ""
    review: dict[str, Any] = field(default_factory=dict)
    # ``indeterminate`` means an attempted apply was not proven rejected (for
    # example, no response or HTTP 5xx); it may have committed and must be
    # inspected, never retried.
    state: str = "pending"  # pending | applying | applied | failed | indeterminate | discarded
    result: Any = None
    error: str = ""

    def public(self, include_result: bool = False) -> dict[str, Any]:
        out = {
            "proposal_id": self.proposal_id,
            "operation": self.operation,
            "summary": self.summary,
            "project_id": self.project_id,
            "state": self.state,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "request_digest": self.request_digest,
            "request": {
                "method": self.method,
                "path": self.path,
                "body": _compact_body(self.body),
            },
            "review": self.review,
            "requires_user_approval": True,
        }
        if self.error:
            out["error"] = self.error
        if include_result and self.result is not None:
            out["result"] = self.result
        return out


class LogosForgeMcpGateway:
    """A per-MCP-session gateway over one authenticated LogosForge API."""

    def __init__(
        self,
        client: LogosForgeApiClient,
        *,
        allow_writes: bool = False,
        require_auth_for_writes: bool = True,
        proposal_ttl_seconds: int = 900,
    ) -> None:
        self.client = client
        self.allow_writes = bool(allow_writes)
        self.require_auth_for_writes = bool(require_auth_for_writes)
        self.proposal_ttl_seconds = max(60, min(int(proposal_ttl_seconds), 86_400))
        self._proposals: dict[str, Proposal] = {}
        self._lock = threading.RLock()

    # -- Project selection and reads -------------------------------------

    def _project_id(self) -> int:
        if self.client.project_id is not None:
            return self.client.project_id
        projects = self.client.list_projects()
        if len(projects) == 1:
            self.client.select_project(int(projects[0]["id"]))
            return self.client.require_project_id()
        raise GatewayError(
            "No project is selected. Call logosforge_list_projects and "
            "logosforge_select_project first."
        )

    def list_projects(self) -> dict[str, Any]:
        projects = self.client.list_projects()
        return {"projects": projects, "selected_project_id": self.client.project_id}

    def select_project(self, project_id: int) -> dict[str, Any]:
        project = self.client.select_project(project_id)
        return {"selected_project_id": int(project_id), "project": project}

    def get_project(self) -> dict:
        return self.client.get_project(self._project_id())

    def list_scenes(self, include_content: bool = False) -> list[dict]:
        scenes = self.client.list_scenes(self._project_id())
        if include_content:
            return scenes
        compact = []
        for scene in scenes:
            item = dict(scene)
            content = str(item.pop("content", "") or "")
            item["content_length"] = len(content)
            compact.append(item)
        return compact

    def get_scene(self, scene_id: int) -> dict:
        return self.client.get_scene(scene_id, self._project_id())

    def get_outline(self) -> list[dict]:
        return self.client.get_outline(self._project_id())

    def get_timeline(self) -> dict[str, Any]:
        return self.client.get_timeline(self._project_id())

    def list_characters(self) -> list[dict]:
        return self.client.list_characters(self._project_id())

    def list_psyke_entries(self, entry_type: str = "") -> list[dict]:
        entries = self.client.list_psyke_entries(self._project_id())
        wanted = (entry_type or "").strip().lower().rstrip("s")
        if not wanted or wanted == "all":
            return entries
        return [e for e in entries if str(e.get("type", "")).lower() == wanted]

    def get_psyke_entry(self, entry_id: int) -> dict:
        return self.client.get_psyke_entry(entry_id, self._project_id())

    def list_psyke_relations(self) -> list[dict]:
        return self.client.list_psyke_relations(self._project_id())

    def list_psyke_progressions(self) -> list[dict]:
        return self.client.list_psyke_progressions(self._project_id())

    def list_notes(self) -> list[dict]:
        return self.client.list_notes(self._project_id())

    def list_comments(
        self,
        include_resolved: bool = True,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        if isinstance(limit, bool) or not 1 <= int(limit) <= 200:
            raise GatewayError("Comment limit must be between 1 and 200.")
        if isinstance(offset, bool) or int(offset) < 0:
            raise GatewayError("Comment offset must be zero or greater.")
        pid = self._project_id()
        comments = self.client.list_comments(pid)
        if not include_resolved:
            comments = [comment for comment in comments if not comment.get("resolved")]
        total = len(comments)
        start = int(offset)
        page = comments[start:start + int(limit)]
        next_offset = start + len(page)
        return {
            "project_id": pid,
            "comments": page,
            "include_resolved": bool(include_resolved),
            "offset": start,
            "limit": int(limit),
            "returned": len(page),
            "total": total,
            "next_offset": next_offset if next_offset < total else None,
            "has_more": next_offset < total,
        }

    def poll_changes(self, since: int = 0) -> dict:
        return self.client.poll_events(since, self._project_id())

    def search(self, query: str) -> dict:
        pid = self._project_id()
        if not (query or "").strip():
            raise GatewayError("Search query must not be empty.")
        return self.client.search_project(query, pid)

    def live_context(self, action: str) -> dict:
        self._project_id()
        if action not in {"get_live_context", "get_active_scene", "get_current_selection"}:
            raise GatewayError("Unsupported live-context operation.")
        response = self.client.execute(action)
        if not response.get("ok"):
            raise GatewayError(str(response.get("error") or "Live context is unavailable."))
        return response.get("result") or {}

    def snapshot(self) -> dict[str, Any]:
        pid = self._project_id()
        events = self.client.poll_events(0, pid)
        notes = self.client.list_notes(pid)
        comments = self.client.list_comments(pid)
        comment_limit = 100
        return {
            "project": self.client.get_project(pid),
            "scenes": self.list_scenes(include_content=False),
            "outline": self.client.get_outline(pid),
            "characters": self.client.list_characters(pid),
            "psyke_entries": self.client.list_psyke_entries(pid),
            "psyke_relations": self.client.list_psyke_relations(pid),
            "psyke_progressions": self.client.list_psyke_progressions(pid),
            "notes": [
                {
                    "id": note.get("id"), "title": note.get("title", ""),
                    "tags": note.get("tags", []), "pinned": note.get("pinned", False),
                    "content_length": len(str(note.get("content", "") or "")),
                    "scene_links": note.get("scene_links", []),
                    "psyke_links": note.get("psyke_links", []),
                }
                for note in notes
            ],
            "comment_counts": {
                "total": len(comments),
                "open": sum(1 for comment in comments if not comment.get("resolved")),
                "resolved": sum(1 for comment in comments if comment.get("resolved")),
            },
            "comments": [
                {
                    "id": comment.get("id"),
                    "revision": comment.get("revision", ""),
                    "anchor": comment.get("anchor", {}),
                    "quote_preview": _preview(comment.get("quote"), 240),
                    "body_preview": _preview(comment.get("body"), 500),
                    "body_length": len(str(comment.get("body", "") or "")),
                    "resolved": bool(comment.get("resolved")),
                    "reply_count": len(comment.get("replies", [])),
                    "created_at": comment.get("created_at"),
                    "updated_at": comment.get("updated_at"),
                }
                for comment in comments[:comment_limit]
            ],
            "comments_truncated": max(0, len(comments) - comment_limit),
            "event_cursor": events.get("cursor", 0),
        }

    def export_project(self, options: dict[str, Any]) -> dict:
        return self.client.export_project(options, self._project_id())

    def diagnostics(self, report: str) -> Any:
        allowed = {
            "continuity", "pacing", "balance", "health", "structure-analysis",
            "decision-radar", "plot", "timeline",
        }
        if report not in allowed:
            raise GatewayError(f"Unknown diagnostic report: {report!r}")
        return self.client.request(
            "GET", self.client.project_path(report, self._project_id())
        )

    # -- Proposal lifecycle ----------------------------------------------

    def propose_request(
        self,
        *,
        operation: str,
        method: str,
        path: str,
        body: dict[str, Any],
        summary: str,
        project_id: int | None,
        guard_path: str = "",
        review: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        guard_digest = ""
        if guard_path:
            guard_digest = _digest(self.client.request("GET", guard_path))
        stored_method = method.upper()
        stored_body = copy.deepcopy(body)
        request_digest = _digest({
            "method": stored_method,
            "path": path,
            "body": stored_body,
            "project_id": project_id,
        })
        now = time.time()
        proposal = Proposal(
            proposal_id="lfp_" + secrets.token_urlsafe(18),
            operation=operation,
            method=stored_method,
            path=path,
            body=stored_body,
            summary=summary,
            project_id=project_id,
            created_at=now,
            expires_at=now + self.proposal_ttl_seconds,
            request_digest=request_digest,
            guard_path=guard_path,
            guard_digest=guard_digest,
            review=review or {},
        )
        with self._lock:
            self._prune_expired(now)
            self._proposals[proposal.proposal_id] = proposal
        return proposal.public()

    def get_proposal(self, proposal_id: str) -> dict[str, Any]:
        with self._lock:
            proposal = self._proposal(proposal_id)
            self._expire(proposal)
            return proposal.public(include_result=True)

    def list_proposals(self, include_finished: bool = False) -> dict[str, Any]:
        now = time.time()
        with self._lock:
            self._prune_expired(now)
            proposals = list(self._proposals.values())
            if not include_finished:
                proposals = [p for p in proposals if p.state == "pending"]
            proposals.sort(key=lambda p: p.created_at)
            return {"proposals": [p.public() for p in proposals]}

    def discard_proposal(self, proposal_id: str) -> dict[str, Any]:
        with self._lock:
            proposal = self._proposal(proposal_id)
            self._expire(proposal)
            if proposal.state != "pending":
                raise GatewayError(f"Proposal is {proposal.state}, not pending.")
            proposal.state = "discarded"
            return proposal.public()

    def apply_proposal(self, proposal_id: str) -> dict[str, Any]:
        if not self.allow_writes:
            raise GatewayError(
                "Writes are disabled for this MCP server. Restart it with "
                "LOGOSFORGE_MCP_ALLOW_WRITES=1 after reviewing the security boundary."
            )
        if self.require_auth_for_writes and not self.client.has_auth_token:
            raise GatewayError(
                "Writes require an authenticated LogosForge API. Set "
                "LOGOSFORGE_API_TOKEN for both the API and MCP server."
            )

        with self._lock:
            proposal = self._proposal(proposal_id)
            self._expire(proposal)
            if proposal.state != "pending":
                raise GatewayError(f"Proposal is {proposal.state}, not pending.")
            if (
                proposal.project_id is not None
                and self.client.project_id != proposal.project_id
            ):
                raise GatewayError(
                    "The selected project differs from this proposal's project. "
                    "Select the original project before applying it."
                )
            current_request_digest = _digest({
                "method": proposal.method,
                "path": proposal.path,
                "body": proposal.body,
                "project_id": proposal.project_id,
            })
            if current_request_digest != proposal.request_digest:
                proposal.state = "failed"
                proposal.error = "Proposal integrity check failed; create a fresh proposal."
                raise GatewayError(proposal.error)
            if proposal.guard_path:
                current = self.client.request("GET", proposal.guard_path)
                if _digest(current) != proposal.guard_digest:
                    proposal.state = "failed"
                    proposal.error = (
                        "The target changed after this proposal was created. "
                        "Read the current state and create a new proposal."
                    )
                    raise GatewayError(proposal.error)
            # Mark before the request: a lost HTTP response is ambiguous, so an
            # automatic retry must never duplicate a create operation.
            proposal.state = "applying"

        try:
            result = self.client.request(proposal.method, proposal.path, proposal.body)
        except Exception as exc:
            definite_http_rejection = (
                isinstance(exc, LogosForgeApiError)
                and exc.status_code is not None
                and 400 <= exc.status_code < 500
            )
            if definite_http_rejection:
                code = f" [{exc.error_code}]" if exc.error_code else ""
                public_error = (
                    f"The apply attempt was rejected{code} and will not be "
                    f"retried automatically: {exc}"
                )
                state = "failed"
            else:
                public_error = (
                    "The apply outcome is indeterminate because the response does "
                    "not prove that the mutation was rejected. Inspect current "
                    "project state and do not retry this proposal: "
                    f"{exc}"
                )
                state = "indeterminate"
            with self._lock:
                proposal.state = state
                proposal.error = public_error
            raise GatewayError(public_error) from exc

        with self._lock:
            proposal.state = "applied"
            proposal.result = result
            return proposal.public(include_result=True)

    def _proposal(self, proposal_id: str) -> Proposal:
        proposal = self._proposals.get(proposal_id)
        if proposal is None:
            raise GatewayError("Unknown proposal id.")
        return proposal

    def _expire(
        self,
        proposal: Proposal,
        now: float | None = None,
        *,
        raise_error: bool = True,
    ) -> None:
        if proposal.state == "pending" and proposal.expires_at <= (now or time.time()):
            proposal.state = "failed"
            proposal.error = "Proposal expired; create a fresh proposal from current state."
        if (
            raise_error
            and proposal.state == "failed"
            and proposal.error.startswith("Proposal expired")
        ):
            raise GatewayError(proposal.error)

    def _prune_expired(self, now: float) -> None:
        for proposal in self._proposals.values():
            # Listing or creating proposals must not fail merely because an old
            # proposal crossed its TTL. Mark it failed; direct access/apply will
            # still surface the expiry error.
            self._expire(proposal, now, raise_error=False)

    # -- Focused proposal builders ---------------------------------------

    def propose_timeline_command(
        self, command: dict[str, Any],
    ) -> dict[str, Any]:
        """Store one exact Timeline command after a revisioned preflight.

        The command endpoint performs the authoritative revision comparison in
        the same database transaction as its mutation.  Do not add a generic
        snapshot digest guard here: the Timeline revision intentionally ignores
        unrelated prose edits, while the rendered snapshot may still include
        fields that changed outside Timeline topology.
        """
        pid = self._project_id()
        normalized = _normalize_timeline_command(command)
        current = self.client.get_timeline(pid)
        if not isinstance(current, dict):
            raise GatewayError("The LogosForge API returned an invalid Timeline snapshot.")
        revision = current.get("revision")
        if revision != normalized["expected_revision"]:
            raise GatewayError(
                "expected_revision does not match the current Timeline. Read it "
                "again with logosforge_get_timeline and create a fresh proposal."
            )

        lanes = [row for row in current.get("lanes", []) if isinstance(row, dict)]
        events = [row for row in current.get("events", []) if isinstance(row, dict)]
        off_timeline = [
            row for row in current.get("off_timeline", []) if isinstance(row, dict)
        ]
        lane_order = [int(row["id"]) for row in lanes if isinstance(row.get("id"), int)]
        event_order = [
            int(row["id"]) for row in events if isinstance(row.get("id"), int)
        ]

        def lane_by_id(lane_id: int) -> dict[str, Any]:
            lane = next((row for row in lanes if row.get("id") == lane_id), None)
            if lane is None:
                raise GatewayError(
                    f"Timeline lane {lane_id} is not present in the current snapshot."
                )
            return lane

        def scene_by_id(scene_id: int) -> tuple[dict[str, Any], bool]:
            event = next((row for row in events if row.get("id") == scene_id), None)
            if event is not None:
                return event, True
            scene = next(
                (row for row in off_timeline if row.get("id") == scene_id), None,
            )
            if scene is None:
                raise GatewayError(
                    f"Scene {scene_id} is not present in the current Timeline snapshot."
                )
            return scene, False

        kind = normalized["kind"]
        destructive = kind in {"delete_lane", "remove_event"}
        review: dict[str, Any] = {
            "timeline_revision": revision,
            "command_kind": kind,
            "destructive": destructive,
            "requires_destructive_confirmation": destructive,
        }

        if kind == "create_lane":
            name = normalized["name"]
            duplicate = next(
                (
                    row for row in lanes
                    if str(row.get("name", "")).strip().casefold() == name.casefold()
                ),
                None,
            )
            if duplicate is not None:
                raise GatewayError(f"A Timeline lane named {name!r} already exists.")
            requested_index = normalized.get("index")
            index = len(lanes) if requested_index is None else requested_index
            if index > len(lanes):
                raise GatewayError("index is outside the available lane range.")
            after_order = list(lane_order)
            after_order.insert(index, "new")
            summary = f"Create Timeline lane {name!r} at index {index}."
            review.update({
                "before": {"lane_order": _bounded_sequence(lane_order)},
                "after_intent": {
                    "name": name,
                    "color_label": normalized.get("color_label", ""),
                    "index": index,
                    "lane_order": _bounded_sequence(after_order),
                },
            })

        elif kind == "update_lane":
            lane_id = normalized["lane_id"]
            lane = lane_by_id(lane_id)
            if "name" in normalized:
                wanted = normalized["name"].casefold()
                duplicate = next(
                    (
                        row for row in lanes
                        if row.get("id") != lane_id
                        and str(row.get("name", "")).strip().casefold() == wanted
                    ),
                    None,
                )
                if duplicate is not None:
                    raise GatewayError(
                        f"A Timeline lane named {normalized['name']!r} already exists."
                    )
            if "index" in normalized and normalized["index"] >= len(lanes):
                raise GatewayError("index is outside the available lane range.")
            changes: dict[str, Any] = {}
            for key in ("name", "color_label", "collapsed"):
                if key in normalized:
                    before_value = lane.get(
                        key, "" if key != "collapsed" else False,
                    )
                    if key in {"name", "color_label"}:
                        before_value = _preview(before_value, 500)
                    changes[key] = {
                        "before": before_value,
                        "after": normalized[key],
                    }
            if "index" in normalized:
                changes["index"] = {
                    "before": lane.get("order_index", lane_order.index(lane_id)),
                    "after": normalized["index"],
                }
            if all(change["before"] == change["after"] for change in changes.values()):
                raise GatewayError("The requested lane update would not change the Timeline.")
            members = [row["id"] for row in events if row.get("lane_id") == lane_id]
            summary = (
                f"Update Timeline lane {lane_id} "
                f"({_preview(lane.get('name'), 200)!r})."
            )
            review.update({
                "lane": {
                    "id": lane_id,
                    "name": _preview(lane.get("name"), 500),
                    "member_scene_ids": _bounded_sequence(members),
                },
                "changes": changes,
                "rename_updates_member_plotlines": "name" in normalized,
            })

        elif kind == "delete_lane":
            lane_id = normalized["lane_id"]
            lane = lane_by_id(lane_id)
            members = [row["id"] for row in events if row.get("lane_id") == lane_id]
            summary = (
                f"Delete Timeline lane {lane_id} "
                f"({_preview(lane.get('name'), 200)!r}); "
                f"keep its {len(members)} event(s) as Unassigned."
            )
            review.update({
                "lane": {
                    "id": lane_id,
                    "name": _preview(lane.get("name"), 500),
                    "member_scene_ids": _bounded_sequence(members),
                },
                "effect": (
                    "The lane is deleted. Its events remain on the Timeline in "
                    "Unassigned, and their manuscript scenes are not deleted."
                ),
            })

        elif kind == "place_event":
            scene_id = normalized["scene_id"]
            scene, on_timeline = scene_by_id(scene_id)
            lane_id = normalized["lane_id"]
            lane = lane_by_id(lane_id) if lane_id is not None else None
            current_event = scene if on_timeline else None
            requested_index = normalized.get("index")
            remaining = [value for value in event_order if value != scene_id]
            if requested_index is not None and requested_index > len(remaining):
                raise GatewayError("index is outside the available event range.")
            desired_order = None
            if requested_index is not None:
                desired_order = list(remaining)
                desired_order.insert(requested_index, scene_id)
            same_lane = on_timeline and current_event.get("lane_id") == lane_id
            if same_lane and requested_index is None:
                raise GatewayError(
                    "The scene is already in that Timeline lane; provide an index "
                    "only when an explicit custom-order move is intended."
                )
            if (
                same_lane
                and current.get("order_mode") == "custom"
                and desired_order == event_order
            ):
                raise GatewayError("The requested event placement would not change the Timeline.")
            target_name = (
                str(lane.get("name", "")) if lane is not None else "Unassigned"
            )
            before_plotline = (
                str(current_event.get("plotline", "")) if current_event else ""
            )
            after_plotline = str(lane.get("name", "")) if lane is not None else ""
            summary = (
                f"Place scene {scene_id} ({_preview(scene.get('title'), 200)!r}) "
                f"in Timeline lane {_preview(target_name, 200)!r}."
            )
            review.update({
                "scene": {
                    "id": scene_id,
                    "title": _preview(scene.get("title"), 500),
                },
                "before": {
                    "on_timeline": on_timeline,
                    "lane_id": current_event.get("lane_id") if current_event else None,
                    "one_based_display_order_index": (
                        current_event.get("order_index") if current_event else None
                    ),
                    "plotline": _preview(before_plotline, 500),
                },
                "after_intent": {
                    "lane_id": lane_id,
                    "lane_name": _preview(target_name, 500),
                    "zero_based_command_index": requested_index,
                    "order_mode": (
                        "custom" if requested_index is not None
                        else current.get("order_mode", "structural")
                    ),
                    "event_order": (
                        _bounded_sequence(desired_order)
                        if desired_order is not None else None
                    ),
                    "plotline": _preview(after_plotline, 500),
                },
                "changes_plotline": before_plotline != after_plotline,
            })

        elif kind == "remove_event":
            scene_id = normalized["scene_id"]
            scene = next((row for row in events if row.get("id") == scene_id), None)
            if scene is None:
                raise GatewayError(
                    f"Scene {scene_id} is not currently a Timeline event."
                )
            summary = (
                f"Remove scene {scene_id} ({_preview(scene.get('title'), 200)!r}) "
                "from the Timeline without deleting the manuscript scene."
            )
            review.update({
                "scene": {
                    "id": scene_id,
                    "title": _preview(scene.get("title"), 500),
                    "lane_id": scene.get("lane_id"),
                    "one_based_display_order_index": scene.get("order_index"),
                },
                "effect": (
                    "Timeline membership and lane assignment are removed. The "
                    "underlying manuscript scene remains and becomes off-Timeline."
                ),
            })

        else:
            mode = normalized["mode"]
            before = current.get("order_mode", "structural")
            if before == mode:
                raise GatewayError(f"Timeline order is already {mode!r}.")
            summary = f"Switch Timeline order from {before!r} to {mode!r}."
            review.update({
                "before": {
                    "order_mode": before,
                    "event_order": _bounded_sequence(event_order),
                },
                "after_intent": {
                    "order_mode": mode,
                    "structural_mode_recomputes_effective_order": mode == "structural",
                },
            })

        return self.propose_request(
            operation=f"timeline_{kind}",
            method="POST",
            path=self.client.project_path("timeline/commands", pid),
            body=normalized,
            summary=summary,
            project_id=pid,
            review=review,
        )

    def propose_create_project(self, body: dict[str, Any]) -> dict[str, Any]:
        return self.propose_request(
            operation="create_project", method="POST",
            path=self.client.api_path("projects"), body=body,
            summary=f"Create project {body['title']!r}.", project_id=None,
        )

    def propose_create_scene(self, body: dict[str, Any]) -> dict[str, Any]:
        pid = self._project_id()
        return self.propose_request(
            operation="create_scene", method="POST",
            path=self.client.project_path("scenes", pid), body=body,
            summary=f"Create scene {body['title']!r} in project {pid}.", project_id=pid,
        )

    def propose_scene_patch(
        self, scene_id: int, expected_revision: str, patch: dict[str, Any],
    ) -> dict[str, Any]:
        pid = self._project_id()
        current = self.client.get_scene(scene_id, pid)
        actual_revision = str(current.get("revision", ""))
        if not expected_revision or expected_revision != actual_revision:
            raise GatewayError(
                "expected_revision does not match the current scene. Read the "
                "scene again and propose against its returned revision."
            )
        if not patch:
            raise GatewayError("A scene patch must change at least one field.")
        body = dict(patch)
        body["expected_revision"] = expected_revision
        review: dict[str, Any] = {"changes": {}}
        for key, value in patch.items():
            if key == "content":
                review["changes"][key] = _content_review(
                    str(current.get("content", "") or ""), str(value or ""),
                )
            else:
                review["changes"][key] = {"before": current.get(key), "after": value}
        return self.propose_request(
            operation="patch_scene", method="PATCH",
            path=self.client.project_path(f"scenes/{int(scene_id)}", pid), body=body,
            summary=f"Patch scene {scene_id} ({current.get('title', '')!r}).",
            project_id=pid, review=review,
        )

    def propose_create_outline_node(self, body: dict[str, Any]) -> dict[str, Any]:
        pid = self._project_id()
        outline_path = self.client.project_path("outline", pid)
        return self.propose_request(
            operation="create_outline_node", method="POST",
            path=self.client.project_path("outline/nodes", pid), body=body,
            summary=f"Create outline node {body['title']!r}.", project_id=pid,
            guard_path=outline_path,
        )

    def propose_patch_outline_node(self, node_id: int, patch: dict[str, Any]) -> dict[str, Any]:
        pid = self._project_id()
        if not patch:
            raise GatewayError("An outline patch must change at least one field.")
        outline_path = self.client.project_path("outline", pid)
        return self.propose_request(
            operation="patch_outline_node", method="PATCH",
            path=self.client.project_path(f"outline/nodes/{int(node_id)}", pid), body=patch,
            summary=f"Patch outline node {node_id}.", project_id=pid,
            guard_path=outline_path,
        )

    def propose_create_psyke_entry(self, body: dict[str, Any]) -> dict[str, Any]:
        pid = self._project_id()
        return self.propose_request(
            operation="create_psyke_entry", method="POST",
            path=self.client.project_path("psyke/entries", pid), body=body,
            summary=f"Create PSYKE entry {body['name']!r}.", project_id=pid,
        )

    def propose_patch_psyke_entry(self, entry_id: int, patch: dict[str, Any]) -> dict[str, Any]:
        pid = self._project_id()
        if not patch:
            raise GatewayError("A PSYKE patch must change at least one field.")
        path = self.client.project_path(f"psyke/entries/{int(entry_id)}", pid)
        return self.propose_request(
            operation="patch_psyke_entry", method="PATCH", path=path, body=patch,
            summary=f"Patch PSYKE entry {entry_id}.", project_id=pid, guard_path=path,
        )

    def propose_create_psyke_relation(self, body: dict[str, Any]) -> dict[str, Any]:
        pid = self._project_id()
        if int(body["source_id"]) == int(body["target_id"]):
            raise GatewayError("A relation requires two distinct PSYKE entries.")
        return self.propose_request(
            operation="create_psyke_relation", method="POST",
            path=self.client.project_path("psyke/relations", pid), body=body,
            summary=(f"Relate PSYKE entries {body['source_id']} and "
                     f"{body['target_id']} as {body.get('relation_type', '')!r}."),
            project_id=pid,
            guard_path=self.client.project_path("psyke/relations", pid),
        )

    def propose_create_psyke_progression(self, body: dict[str, Any]) -> dict[str, Any]:
        pid = self._project_id()
        return self.propose_request(
            operation="create_psyke_progression", method="POST",
            path=self.client.project_path("psyke/progressions", pid), body=body,
            summary=f"Add progression to PSYKE entry {body['entry_id']}.", project_id=pid,
        )

    def propose_create_note(self, body: dict[str, Any]) -> dict[str, Any]:
        pid = self._project_id()
        return self.propose_request(
            operation="create_note", method="POST",
            path=self.client.project_path("notes", pid), body=body,
            summary=f"Create note {body['title']!r}.", project_id=pid,
        )

    def propose_patch_note(self, note_id: int, patch: dict[str, Any]) -> dict[str, Any]:
        pid = self._project_id()
        if not patch:
            raise GatewayError("A note patch must change at least one field.")
        notes_path = self.client.project_path("notes", pid)
        return self.propose_request(
            operation="patch_note", method="PATCH",
            path=self.client.project_path(f"notes/{int(note_id)}", pid), body=patch,
            summary=f"Patch note {note_id}.", project_id=pid, guard_path=notes_path,
        )

    def _comment_proposal_context(
        self, comment_id: int, expected_revision: str,
    ) -> tuple[int, dict[str, Any]]:
        pid = self._project_id()
        if (
            not isinstance(expected_revision, str)
            or len(expected_revision) != 64
            or any(char not in "0123456789abcdef" for char in expected_revision)
        ):
            raise GatewayError(
                "expected_revision must be the exact 64-character revision "
                "returned by logosforge_list_comments or logosforge_search."
            )
        current = self.client.get_comment(int(comment_id), pid)
        if current.get("revision") != expected_revision:
            raise GatewayError(
                "expected_revision does not match the current comment thread. "
                "Read the thread again and create a fresh proposal."
            )
        return pid, current

    def propose_comment_reply(
        self, comment_id: int, expected_revision: str, body: str,
    ) -> dict[str, Any]:
        if not isinstance(body, str) or not body.strip():
            raise GatewayError("A comment reply must not be empty.")
        if len(body) > 20_000:
            raise GatewayError("A comment reply may contain at most 20000 characters.")
        pid, current = self._comment_proposal_context(
            comment_id, expected_revision,
        )
        return self.propose_request(
            operation="reply_to_comment",
            method="POST",
            path=self.client.project_path(
                f"comments/{int(comment_id)}/replies", pid,
            ),
            body={
                "body": body,
                "author": "MCP assistant",
                "expected_revision": expected_revision,
            },
            summary=f"Reply to comment {comment_id} as MCP assistant.",
            project_id=pid,
            review={
                "comment_id": int(comment_id),
                "expected_revision": expected_revision,
                "quote": _preview(current.get("quote"), 500),
                "root_body": _preview(current.get("body"), 1_000),
                "reply_count_before": len(current.get("replies", [])),
                "proposed_author": "MCP assistant",
                "proposed_reply": body,
            },
        )

    def propose_comment_resolution(
        self, comment_id: int, expected_revision: str, resolved: bool,
    ) -> dict[str, Any]:
        if not isinstance(resolved, bool):
            raise GatewayError("resolved must be a boolean.")
        pid, current = self._comment_proposal_context(
            comment_id, expected_revision,
        )
        before = bool(current.get("resolved"))
        if before == resolved:
            state = "resolved" if resolved else "open"
            raise GatewayError(f"Comment {comment_id} is already {state}.")
        return self.propose_request(
            operation="set_comment_resolution",
            method="PATCH",
            path=self.client.project_path(f"comments/{int(comment_id)}", pid),
            body={
                "resolved": resolved,
                "expected_revision": expected_revision,
            },
            summary=(
                f"{'Resolve' if resolved else 'Reopen'} comment {comment_id}."
            ),
            project_id=pid,
            review={
                "comment_id": int(comment_id),
                "expected_revision": expected_revision,
                "quote": _preview(current.get("quote"), 500),
                "before": {"resolved": before},
                "after": {"resolved": resolved},
            },
        )

    def propose_import_manuscript(
        self, *, title: str, content: str, mode: str, strategy: str, filename: str,
    ) -> dict[str, Any]:
        raw = content.encode("utf-8")
        body = {
            "title": title,
            "mode": mode,
            "strategy": strategy,
            "filename": filename,
            "content_base64": base64.b64encode(raw).decode("ascii"),
        }
        return self.propose_request(
            operation="import_manuscript", method="POST",
            path=self.client.api_path("import/manuscript"), body=body,
            summary=f"Import {len(content)} characters as project {title!r}.",
            project_id=None,
            review={
                "title": title, "mode": mode, "strategy": strategy,
                "filename": filename, "content_length": len(content),
                "content_sha256": hashlib.sha256(raw).hexdigest(),
            },
        )


def call_gateway(
    gateway: LogosForgeMcpGateway,
    operation,
) -> dict[str, Any]:
    """Return a stable MCP result envelope and never leak a traceback."""
    try:
        return {"ok": True, "result": operation()}
    except (GatewayError, LogosForgeApiError, ValueError, TypeError) as exc:
        return {"ok": False, "error": str(exc)}
    except Exception:  # pragma: no cover - final transport safety net
        # MCP stdio uses stdout as its protocol stream. Log diagnostics to the
        # normal logging sink (stderr) and return a stable, non-traceback error.
        LOGGER.exception("Unexpected LogosForge MCP gateway failure")
        return {
            "ok": False,
            "error": "Unexpected gateway failure; inspect the MCP server log.",
        }
