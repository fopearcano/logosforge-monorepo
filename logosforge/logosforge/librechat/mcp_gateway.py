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
    state: str = "pending"  # pending | applying | applied | failed | discarded
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

    def poll_changes(self, since: int = 0) -> dict:
        return self.client.poll_events(since, self._project_id())

    def search(self, query: str) -> dict:
        pid = self._project_id()
        needle = (query or "").strip().casefold()
        if not needle:
            raise GatewayError("Search query must not be empty.")

        matches: list[dict[str, Any]] = []

        def add(kind: str, item_id: Any, title: str, text: str) -> None:
            haystack = text.casefold()
            offset = haystack.find(needle)
            if offset < 0 or len(matches) >= 100:
                return
            start = max(0, offset - 100)
            end = min(len(text), offset + len(query) + 140)
            excerpt = text[start:end].replace("\n", " ").strip()
            matches.append({
                "kind": kind,
                "id": item_id,
                "title": title,
                "excerpt": ("…" if start else "") + excerpt + ("…" if end < len(text) else ""),
            })

        scenes = self.client.list_scenes(pid)
        for scene in scenes:
            text = "\n".join(str(scene.get(key, "") or "") for key in (
                "title", "summary", "synopsis", "goal", "conflict", "outcome",
                "beat", "act", "chapter", "plotline", "content",
            ))
            add("scene", scene.get("id"), str(scene.get("title", "")), text)

        notes = self.client.list_notes(pid)
        for note in notes:
            text = "\n".join((
                str(note.get("title", "")), str(note.get("content", "")),
                " ".join(str(tag) for tag in note.get("tags", [])),
            ))
            add("note", note.get("id"), str(note.get("title", "")), text)

        entries = self.client.list_psyke_entries(pid)
        for entry in entries:
            text = "\n".join((
                str(entry.get("name", "")), str(entry.get("type", "")),
                " ".join(str(alias) for alias in entry.get("aliases", [])),
                str(entry.get("notes", "")),
                json.dumps(entry.get("details", {}), ensure_ascii=False, default=str),
            ))
            add("psyke", entry.get("id"), str(entry.get("name", "")), text)

        return {"query": query, "matches": matches, "limit": 100}

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
            with self._lock:
                proposal.state = "failed"
                proposal.error = str(exc)
            raise GatewayError(
                "The apply attempt failed and will not be retried automatically: "
                f"{exc}"
            ) from exc

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
