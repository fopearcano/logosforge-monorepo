"""Focused MCP coverage for transactional Semantic Continuity review."""

from __future__ import annotations

import copy
from typing import Any

import pytest
from fastapi.testclient import TestClient

from logosforge.api import create_api
from logosforge.db import Database
from logosforge.db.database import _continuity_command_request_digest
from logosforge.librechat.api_client import LogosForgeApiError
from logosforge.librechat.mcp_gateway import (
    GatewayError,
    LogosForgeMcpGateway,
    _continuity_receipt_request_digest,
)
from logosforge.librechat.mcp_server import (
    HANDLERS,
    SERVER_VERSION,
    TOOL_SPECS,
    call_tool,
)


class _InProcessApiClient:
    """HTTP-compatible adapter over the real FastAPI/Core transaction."""

    def __init__(self, http: TestClient, project_id: int) -> None:
        self.http = http
        self._project_id = project_id
        self.fail_continuity_posts_before_send = 0
        self.drop_continuity_response_after_commit = 0
        self.continuity_post_attempts = 0
        self.continuity_reads = 0

    @property
    def project_id(self) -> int:
        return self._project_id

    @property
    def has_auth_token(self) -> bool:
        return True

    def require_project_id(self) -> int:
        return self._project_id

    def api_path(self, suffix: str) -> str:
        return f"/api/{suffix.lstrip('/')}"

    def project_path(
        self,
        suffix: str = "",
        project_id: int | None = None,
    ) -> str:
        pid = self._project_id if project_id is None else int(project_id)
        base = f"/api/projects/{pid}"
        return f"{base}/{suffix.lstrip('/')}" if suffix else base

    def request(
        self,
        method: str,
        path: str,
        body: dict | None = None,
        query: dict[str, Any] | None = None,
        *,
        idempotency_key: str = "",
    ) -> Any:
        is_continuity_post = (
            method == "POST" and path.endswith("/continuity/commands")
        )
        if is_continuity_post:
            self.continuity_post_attempts += 1
            if self.fail_continuity_posts_before_send > 0:
                self.fail_continuity_posts_before_send -= 1
                raise LogosForgeApiError(
                    "simulated connection loss before send",
                    status_code=500,
                )
        headers = (
            {"Idempotency-Key": idempotency_key}
            if idempotency_key
            else None
        )
        response = self.http.request(
            method,
            path,
            json=body,
            params=query,
            headers=headers,
        )
        if response.status_code >= 400:
            payload = response.json()
            envelope = payload.get("error", payload.get("detail", payload))
            code = envelope.get("code", "") if isinstance(envelope, dict) else ""
            message = (
                envelope.get("message", str(envelope))
                if isinstance(envelope, dict)
                else str(envelope)
            )
            raise LogosForgeApiError(
                f"HTTP {response.status_code} for {method} {path}: {message}",
                status_code=response.status_code,
                error_code=code,
            )
        payload = response.json() if response.content else {}
        if (
            is_continuity_post
            and self.drop_continuity_response_after_commit > 0
        ):
            self.drop_continuity_response_after_commit -= 1
            raise LogosForgeApiError(
                "simulated lost response after commit",
                status_code=500,
            )
        return payload

    def get_continuity(self, project_id: int | None = None) -> dict:
        self.continuity_reads += 1
        return self.request(
            "GET",
            self.project_path("continuity", project_id),
        )

    def get_continuity_command_receipt(
        self,
        idempotency_key: str,
        project_id: int | None = None,
    ) -> dict:
        return self.request(
            "GET",
            self.project_path("continuity/command-receipt", project_id),
            idempotency_key=idempotency_key,
        )

    def get_timeline_command_receipt(
        self,
        idempotency_key: str,
        project_id: int | None = None,
    ) -> dict:
        return self.request(
            "GET",
            self.project_path("timeline/command-receipt", project_id),
            idempotency_key=idempotency_key,
        )

    def get_canvas_plot_command_receipt(
        self,
        idempotency_key: str,
        project_id: int | None = None,
    ) -> dict:
        return self.request(
            "GET",
            self.project_path("canvas-plot/command-receipt", project_id),
            idempotency_key=idempotency_key,
        )

    def get_knowledge_graph_command_receipt(
        self,
        idempotency_key: str,
        project_id: int | None = None,
    ) -> dict:
        return self.request(
            "GET",
            self.project_path("knowledge-graph/command-receipt", project_id),
            idempotency_key=idempotency_key,
        )

    def get_progression_command_receipt(
        self,
        idempotency_key: str,
        project_id: int | None = None,
    ) -> dict:
        return self.request(
            "GET",
            self.project_path("progressions/command-receipt", project_id),
            idempotency_key=idempotency_key,
        )


@pytest.fixture
def continuity_gateway(tmp_path):
    db = Database(str(tmp_path / "mcp-continuity.db"))
    project = db.create_project("MCP continuity", narrative_engine="novel")
    db.create_psyke_entry(project.id, "Alice", "character")
    db.create_psyke_entry(project.id, "Solo", "character")
    db.create_psyke_entry(project.id, "Bob", "character")
    db.create_scene(
        project.id,
        "Open",
        content="Alice stood in the Kitchen.",
        location="Kitchen",
    )
    db.create_scene(
        project.id,
        "Next",
        content="Alice was at the Castle.",
        location="Castle",
    )
    db.create_scene(
        project.id,
        "Solo bit",
        content="Solo waved. Bob waited.",
        location="Castle",
    )
    db.create_scene(project.id, "Quiet", content="The rain fell.")
    db.create_scene(project.id, "Coda", content="Morning returned.")
    http = TestClient(create_api(db=db))
    client = _InProcessApiClient(http, project.id)
    gateway = LogosForgeMcpGateway(
        client,  # type: ignore[arg-type]
        allow_writes=True,
        require_auth_for_writes=True,
    )
    return db, client, gateway


def _command(kind: str, continuity: dict, issue: dict) -> dict:
    return {
        "kind": kind,
        "expected_revision": continuity["review_revision"],
        "issue_id": issue["id"],
        "expected_issue_fingerprint": issue["review_fingerprint"],
    }


def test_continuity_digest_matches_core_canonical_wire():
    command = {
        "kind": "resolve_issue",
        "expected_revision": "a" * 64,
        "issue_id": "0123456789abcdef",
        "expected_issue_fingerprint": "b" * 64,
    }
    expected = _continuity_command_request_digest(
        7,
        command["kind"],
        command["expected_revision"],
        command["issue_id"],
        command["expected_issue_fingerprint"],
    )
    assert _continuity_receipt_request_digest(7, command) == expected


def test_continuity_tool_is_versioned_read_only_and_strict(continuity_gateway):
    _db, _client, gateway = continuity_gateway
    assert SERVER_VERSION == "1.12.0"
    assert len(TOOL_SPECS) == 48
    assert "logosforge_propose_continuity_command" in HANDLERS

    tool = next(
        spec for spec in TOOL_SPECS
        if spec.name == "logosforge_propose_continuity_command"
    )
    assert tool.read_only is True
    assert tool.destructive is False
    assert tool.idempotent is False
    assert tool.input_schema["required"] == ["command"]
    assert tool.input_schema["properties"]["command"]["additionalProperties"] is False

    malformed = call_tool(
        gateway,
        "logosforge_propose_continuity_command",
        {
            "command": {
                "kind": "resolve_issue",
                "expected_revision": "a" * 64,
                "issue_id": "0123456789abcdef",
                "expected_issue_fingerprint": "b" * 64,
                "unexpected": True,
            },
        },
    )
    assert malformed["ok"] is False
    assert "unexpected" in malformed["error"]


@pytest.mark.parametrize(
    ("kind", "status"),
    [
        ("defer_issue", "deferred"),
        ("dismiss_issue", "dismissed"),
        ("resolve_issue", "resolved"),
    ],
)
def test_all_review_actions_require_proposal_and_apply_once(
    continuity_gateway,
    kind: str,
    status: str,
):
    _db, client, gateway = continuity_gateway
    current = gateway.get_continuity()
    issue = current["issues"][0]
    command = _command(kind, current, issue)

    proposal = gateway.propose_continuity_command(command)
    assert proposal["operation"] == f"continuity_{kind}"
    assert proposal["state"] == "pending"
    assert proposal["requires_user_approval"] is True
    assert proposal["request"] == {
        "method": "POST",
        "path": client.project_path("continuity/commands"),
        "body": command,
    }
    assert proposal["review"]["continuity_revision"] == current["review_revision"]
    assert proposal["review"]["command_kind"] == kind
    assert proposal["review"]["issue"]["id"] == issue["id"]
    assert proposal["review"]["issue"]["review_fingerprint"] == (
        issue["review_fingerprint"]
    )

    applied = gateway.apply_proposal(proposal["proposal_id"])
    assert applied["state"] == "applied"
    assert applied["result"]["changed"] is True
    assert applied["result"]["replayed"] is False
    assert applied["result"]["affected_issue_id"] == issue["id"]
    assert applied["result"]["previous_status"] == "open"
    assert applied["result"]["status"] == status
    assert next(
        row for row in applied["result"]["continuity"]["issues"]
        if row["id"] == issue["id"]
    )["status"] == status
    with pytest.raises(GatewayError, match="Proposal is applied"):
        gateway.apply_proposal(proposal["proposal_id"])
    assert client.continuity_post_attempts == 1


def test_stale_revision_and_fingerprint_fail_during_preflight(continuity_gateway):
    _db, _client, gateway = continuity_gateway
    current = gateway.get_continuity()
    issue = current["issues"][0]

    stale_revision = _command("resolve_issue", current, issue)
    stale_revision["expected_revision"] = "f" * 64
    with pytest.raises(GatewayError, match="revision"):
        gateway.propose_continuity_command(stale_revision)

    stale_fingerprint = _command("resolve_issue", current, issue)
    stale_fingerprint["expected_issue_fingerprint"] = "f" * 64
    with pytest.raises(GatewayError, match="fingerprint"):
        gateway.propose_continuity_command(stale_fingerprint)


def test_lost_response_recovers_receipt_and_fresh_gateway(continuity_gateway):
    _db, client, gateway = continuity_gateway
    current = gateway.get_continuity()
    issue = current["issues"][0]
    proposal = gateway.propose_continuity_command(
        _command("resolve_issue", current, issue),
    )
    client.drop_continuity_response_after_commit = 1

    recovered = gateway.apply_proposal(proposal["proposal_id"])
    assert recovered["state"] == "applied"
    assert recovered["recovered_from_core"] is True
    assert recovered["receipt"]["expected_issue_fingerprint"] == (
        issue["review_fingerprint"]
    )
    assert recovered["receipt"]["status"] == "resolved"
    assert recovered["result"]["changed"] is False
    assert recovered["result"]["replayed"] is True
    assert recovered["result"]["affected_issue_id"] == issue["id"]
    assert client.continuity_post_attempts == 1

    restarted = LogosForgeMcpGateway(
        client,  # type: ignore[arg-type]
        allow_writes=True,
        require_auth_for_writes=True,
    )
    restored = restarted.get_proposal(proposal["proposal_id"])
    assert restored["state"] == "applied"
    assert restored["request"] is None
    assert restored["operation"] == "continuity_resolve_issue"
    assert restored["receipt"] == recovered["receipt"]
    assert restored["result"]["continuity"]["review_revision"] == (
        gateway.get_continuity()["review_revision"]
    )
    assert client.continuity_post_attempts == 1


def test_receipt_miss_allows_one_resend_and_never_a_third(continuity_gateway):
    _db, client, gateway = continuity_gateway
    current = gateway.get_continuity()
    issue = current["issues"][0]
    proposal = gateway.propose_continuity_command(
        _command("defer_issue", current, issue),
    )
    client.fail_continuity_posts_before_send = 2

    with pytest.raises(GatewayError, match="awaiting durable recovery"):
        gateway.apply_proposal(proposal["proposal_id"])
    assert client.continuity_post_attempts == 2
    assert gateway.get_proposal(proposal["proposal_id"])["state"] == (
        "recovery_pending"
    )

    client.fail_continuity_posts_before_send = 0
    for _ in range(2):
        with pytest.raises(GatewayError, match="remains recovery_pending"):
            gateway.apply_proposal(proposal["proposal_id"])
    assert client.continuity_post_attempts == 2


@pytest.mark.parametrize(
    "tamper",
    ["request_digest", "expected_issue_fingerprint", "status"],
)
def test_receipt_integrity_mismatch_fails_closed(
    continuity_gateway,
    tamper: str,
):
    _db, client, gateway = continuity_gateway
    current = gateway.get_continuity()
    issue = current["issues"][0]
    proposal = gateway.propose_continuity_command(
        _command("dismiss_issue", current, issue),
    )
    original_receipt = client.get_continuity_command_receipt
    client.drop_continuity_response_after_commit = 1

    def tampered_receipt(idempotency_key: str, project_id: int | None = None):
        receipt = copy.deepcopy(original_receipt(idempotency_key, project_id))
        if tamper == "request_digest":
            receipt[tamper] = "f" * 64
        elif tamper == "expected_issue_fingerprint":
            receipt[tamper] = "e" * 64
        else:
            receipt[tamper] = "resolved"
        return receipt

    client.get_continuity_command_receipt = tampered_receipt
    with pytest.raises(
        GatewayError,
        match="invalid Continuity receipt|receipt integrity check failed",
    ):
        gateway.apply_proposal(proposal["proposal_id"])
    assert gateway.get_proposal(proposal["proposal_id"])["state"] == "failed"
    assert client.continuity_post_attempts == 1


@pytest.mark.parametrize("receipt_change", ["disappear", "mutate"])
def test_restart_recovery_brackets_report_with_same_receipt(
    continuity_gateway,
    receipt_change: str,
):
    _db, client, gateway = continuity_gateway
    current = gateway.get_continuity()
    issue = current["issues"][0]
    proposal = gateway.propose_continuity_command(
        _command("defer_issue", current, issue),
    )
    gateway.apply_proposal(proposal["proposal_id"])

    restarted = LogosForgeMcpGateway(
        client,  # type: ignore[arg-type]
        allow_writes=True,
        require_auth_for_writes=True,
    )
    original_receipt = client.get_continuity_command_receipt
    receipt_calls = 0

    def changing_receipt(idempotency_key: str, project_id: int | None = None):
        nonlocal receipt_calls
        receipt_calls += 1
        if receipt_calls < 2:
            return original_receipt(idempotency_key, project_id)
        if receipt_change == "disappear":
            raise LogosForgeApiError(
                "Continuity command receipt not found",
                status_code=404,
                error_code="continuity_receipt_not_found",
            )
        receipt = copy.deepcopy(original_receipt(idempotency_key, project_id))
        receipt["committed_at"] = "2099-01-01T00:00:00Z"
        return receipt

    client.get_continuity_command_receipt = changing_receipt
    with pytest.raises(
        GatewayError,
        match="receipt (disappeared|changed).*project lifetime may have changed",
    ):
        restarted.get_proposal(proposal["proposal_id"])


def test_restart_recovery_fails_closed_on_cross_family_collision(
    continuity_gateway,
):
    _db, client, gateway = continuity_gateway
    current = gateway.get_continuity()
    issue = current["issues"][0]
    proposal = gateway.propose_continuity_command(
        _command("resolve_issue", current, issue),
    )
    gateway.apply_proposal(proposal["proposal_id"])

    timeline = client.request("GET", client.project_path("timeline"))
    client.request(
        "POST",
        client.project_path("timeline/commands"),
        {
            "kind": "create_lane",
            "expected_revision": timeline["revision"],
            "name": "Continuity collision",
        },
        idempotency_key=proposal["proposal_id"],
    )
    restarted = LogosForgeMcpGateway(
        client,  # type: ignore[arg-type]
        allow_writes=True,
        require_auth_for_writes=True,
    )
    with pytest.raises(GatewayError, match="capability collision.*failed closed"):
        restarted.get_proposal(proposal["proposal_id"])
