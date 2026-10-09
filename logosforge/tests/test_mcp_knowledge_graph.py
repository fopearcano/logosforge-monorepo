"""Focused MCP coverage for transactional Narrative Knowledge Graph review."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from logosforge.api import create_api
from logosforge.db import Database
from logosforge.db.database import (
    KnowledgeGraphEdgeIdentity,
    _knowledge_graph_command_request_digest,
)
from logosforge.knowledge_graph import provenance as P
from logosforge.librechat.api_client import LogosForgeApiError
from logosforge.librechat.mcp_gateway import (
    GatewayError,
    KNOWLEDGE_GRAPH_VIEW_MODES,
    LogosForgeMcpGateway,
    _knowledge_graph_receipt_request_digest,
)
from logosforge.librechat.mcp_server import (
    HANDLERS,
    SERVER_VERSION,
    TOOL_SPECS,
    call_tool,
)


class _InProcessApiClient:
    """Small HTTP-compatible adapter over the real FastAPI/Core transaction."""

    def __init__(self, http: TestClient, project_id: int) -> None:
        self.http = http
        self._project_id = project_id
        self.fail_graph_posts_before_send = 0
        self.drop_graph_response_after_commit = 0
        self.graph_post_attempts = 0
        self.graph_read_queries: list[dict[str, Any]] = []

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
        is_graph_post = (
            method == "POST" and path.endswith("/knowledge-graph/commands")
        )
        if is_graph_post:
            self.graph_post_attempts += 1
            if self.fail_graph_posts_before_send > 0:
                self.fail_graph_posts_before_send -= 1
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
            params=(
                None
                if query is None
                else {key: value for key, value in query.items() if value is not None}
            ),
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
        if is_graph_post and self.drop_graph_response_after_commit > 0:
            self.drop_graph_response_after_commit -= 1
            raise LogosForgeApiError(
                "simulated lost response after commit",
                status_code=500,
            )
        return payload

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
        query = {
            "focus_key": focus_key,
            "depth": depth,
            "limit": limit,
            "include_inferred": include_inferred,
            "view_mode": view_mode,
        }
        self.graph_read_queries.append(dict(query))
        return self.request(
            "GET",
            self.project_path("knowledge-graph", project_id),
            query=query,
        )

    def get_knowledge_graph_hidden_edges(
        self,
        project_id: int | None = None,
        *,
        offset: int = 0,
        limit: int = 25,
    ) -> dict:
        return self.request(
            "GET",
            self.project_path("knowledge-graph/hidden-edges", project_id),
            query={"offset": offset, "limit": limit},
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
def graph_gateway(tmp_path):
    db = Database(str(tmp_path / "mcp-graph.db"))
    project = db.create_project("MCP graph", narrative_engine="novel")
    db.create_scene(project.id, "First")
    db.create_scene(project.id, "Second")
    http = TestClient(create_api(db=db))
    client = _InProcessApiClient(http, project.id)
    gateway = LogosForgeMcpGateway(
        client,  # type: ignore[arg-type]
        allow_writes=True,
        require_auth_for_writes=True,
    )
    return db, client, gateway


def _inferred_edge(graph: dict) -> dict:
    return next(
        edge for edge in graph["edges"]
        if edge["is_inferred"] and not edge["is_user_confirmed"]
    )


def _command(kind: str, revision: str, edge: dict) -> dict:
    return {
        "kind": kind,
        "expected_revision": revision,
        "source": edge["source"],
        "target": edge["target"],
        "edge_type": edge["edge_type"],
    }


def test_graph_digest_matches_core_canonical_wire():
    command = {
        "kind": "hide_edge",
        "expected_revision": "a" * 64,
        "source": "scene:1",
        "target": "scene:2",
        "edge_type": "precedes",
    }
    expected = _knowledge_graph_command_request_digest(
        7,
        command["kind"],
        command["expected_revision"],
        KnowledgeGraphEdgeIdentity(
            source=command["source"],
            target=command["target"],
            edge_type=command["edge_type"],
        ),
    )
    assert _knowledge_graph_receipt_request_digest(7, command) == expected


def test_graph_tools_are_versioned_bounded_and_strict(graph_gateway):
    _db, _client, gateway = graph_gateway
    assert SERVER_VERSION == "1.12.0"
    assert len(TOOL_SPECS) == 48
    assert {
        "logosforge_get_knowledge_graph",
        "logosforge_get_knowledge_graph_hidden_edges",
        "logosforge_propose_knowledge_graph_command",
    } <= HANDLERS.keys()

    read = call_tool(
        gateway,
        "logosforge_get_knowledge_graph",
        {
            "depth": 2,
            "limit": 25,
            "include_inferred": True,
            "view_mode": "structure",
        },
    )
    assert read["ok"] is True
    assert read["result"]["depth"] == 2
    assert read["result"]["include_inferred"] is True
    assert read["result"]["view_mode"] == "structure"
    assert read["result"]["story_gravity_available"] is True
    assert all("story_gravity" in node for node in read["result"]["nodes"])


def test_mcp_graph_read_includes_native_progression_nodes(graph_gateway):
    db, _client, gateway = graph_gateway
    project_id = gateway.client.project_id
    scene = db.get_all_scenes(project_id)[0]
    snapshot = db.read_progression_snapshot(project_id)
    assert snapshot is not None
    track_result = db.execute_progression_command(
        project_id,
        kind="create_track",
        expected_revision=snapshot.revision,
        track_kind="story",
        title="MCP-visible arc",
    )
    track_id = track_result.created_track_id
    assert track_id is not None
    beat_result = db.execute_progression_command(
        project_id,
        kind="create_beat",
        expected_revision=track_result.snapshot.revision,
        track_id=track_id,
        text="The arc turns",
        anchor_kind="scene",
        scene_id=scene.id,
    )
    beat_id = beat_result.created_beat_id
    assert beat_id is not None

    response = call_tool(
        gateway,
        "logosforge_get_knowledge_graph",
        {
            "depth": 2,
            "limit": 200,
            "include_inferred": False,
            "view_mode": "project_map",
        },
    )

    assert response["ok"] is True
    keys = {node["key"] for node in response["result"]["nodes"]}
    assert f"progression_track:progressions:{track_id}" in keys
    assert f"progression_beat:progressions:{beat_id}" in keys
    graph_tool = next(
        spec for spec in TOOL_SPECS
        if spec.name == "logosforge_get_knowledge_graph"
    )
    assert graph_tool.input_schema["properties"]["view_mode"] == {
        "type": "string",
        "enum": sorted(KNOWLEDGE_GRAPH_VIEW_MODES),
    }
    invalid_mode = call_tool(
        gateway,
        "logosforge_get_knowledge_graph",
        {"view_mode": "predictive_risk"},
    )
    assert invalid_mode["ok"] is False
    assert "view_mode" in invalid_mode["error"]
    invalid = call_tool(
        gateway,
        "logosforge_get_knowledge_graph_hidden_edges",
        {"offset": -1},
    )
    assert invalid["ok"] is False
    assert "offset" in invalid["error"]


def test_graph_proposal_preflight_apply_and_stale_sibling(graph_gateway):
    _db, client, gateway = graph_gateway
    current = gateway.get_knowledge_graph()
    edge = _inferred_edge(current)
    hidden = gateway.propose_knowledge_graph_command(
        _command("hide_edge", current["revision"], edge),
    )
    sibling = gateway.propose_knowledge_graph_command(
        _command("confirm_edge", current["revision"], edge),
    )

    assert client.graph_read_queries[-2:] == [
        {
            "focus_key": edge["source"],
            "depth": 1,
            "limit": 200,
            "include_inferred": True,
            "view_mode": "project_map",
        },
        {
            "focus_key": edge["source"],
            "depth": 1,
            "limit": 200,
            "include_inferred": True,
            "view_mode": "project_map",
        },
    ]

    assert hidden["operation"] == "knowledge_graph_hide_edge"
    assert hidden["request"] == {
        "method": "POST",
        "path": client.project_path("knowledge-graph/commands"),
        "body": _command("hide_edge", current["revision"], edge),
    }
    assert hidden["review"]["destructive"] is True
    assert hidden["review"]["edge"]["is_inferred"] is True

    applied = gateway.apply_proposal(hidden["proposal_id"])
    assert applied["state"] == "applied"
    assert applied["result"]["changed"] is True
    assert applied["result"]["replayed"] is False
    assert applied["result"]["affected_edge"] == {
        key: edge[key] for key in ("source", "target", "edge_type")
    }
    assert applied["result"]["knowledge_graph"]["story_gravity_available"] is True
    assert all(
        "story_gravity" in node
        for node in applied["result"]["knowledge_graph"]["nodes"]
    )
    with pytest.raises(GatewayError, match="knowledge_graph_conflict.*will not be retried"):
        gateway.apply_proposal(sibling["proposal_id"])
    assert gateway.get_proposal(sibling["proposal_id"])["state"] == "failed"


def test_restore_requires_and_refetches_the_exact_hidden_page(graph_gateway):
    db, _client, gateway = graph_gateway
    for index in range(31):
        source = f"custom:mcp:source-{index:02d}"
        target = f"custom:mcp:target-{index:02d}"
        for key in (source, target):
            db.upsert_kg_node(
                gateway.client.project_id,
                key,
                node_type="custom",
                source_type="mcp-test",
                source_id=key.rsplit(":", 1)[-1],
                label=key,
                summary="",
                metadata_json="{}",
            )
        db.upsert_kg_edge(
            gateway.client.project_id,
            source,
            target,
            "relates_to",
            confidence=P.CONF_POSSIBLE,
            provenance=P.PROV_USER_GRAPH_LINK,
            source_system=P.SS_USER,
            explanation="Hidden MCP test edge.",
            metadata_json="{}",
            is_user_confirmed=False,
            is_hidden=True,
        )

    page = gateway.get_knowledge_graph_hidden_edges(offset=25, limit=5)
    edge = page["edges"][-1]
    command = _command("unhide_edge", page["revision"], edge)
    with pytest.raises(GatewayError, match="requires the non-negative hidden_edge_offset"):
        gateway.propose_knowledge_graph_command(command)
    with pytest.raises(GatewayError, match="exact hidden edge is not present"):
        gateway.propose_knowledge_graph_command(command, hidden_edge_offset=30)

    proposal = gateway.propose_knowledge_graph_command(
        command,
        hidden_edge_offset=25,
    )
    assert proposal["review"]["hidden_edge_offset"] == 25
    assert proposal["review"]["edge"]["is_hidden"] is True
    applied = gateway.apply_proposal(proposal["proposal_id"])
    assert applied["result"]["knowledge_graph"]["hidden_edge_count"] == 30


def test_lost_response_recovers_from_receipt_and_fresh_gateway(graph_gateway):
    _db, client, gateway = graph_gateway
    current = gateway.get_knowledge_graph()
    edge = _inferred_edge(current)
    proposal = gateway.propose_knowledge_graph_command(
        _command("hide_edge", current["revision"], edge),
    )
    client.drop_graph_response_after_commit = 1

    recovered = gateway.apply_proposal(proposal["proposal_id"])
    assert recovered["state"] == "applied"
    assert recovered["recovered_from_core"] is True
    assert recovered["receipt"]["original_changed"] is True
    assert recovered["result"]["changed"] is False
    assert recovered["result"]["replayed"] is True
    assert recovered["result"]["affected_edge"] == {
        key: edge[key] for key in ("source", "target", "edge_type")
    }
    assert (
        recovered["result"]["applied_revision"]
        == recovered["receipt"]["applied_revision"]
    )

    fresh = LogosForgeMcpGateway(
        client,  # type: ignore[arg-type]
        allow_writes=True,
        require_auth_for_writes=True,
    )
    restarted = fresh.get_proposal(proposal["proposal_id"])
    assert restarted["state"] == "applied"
    assert restarted["request"] is None
    assert restarted["operation"] == "knowledge_graph_hide_edge"
    assert restarted["result"]["knowledge_graph"]["revision"] == (
        gateway.get_knowledge_graph()["revision"]
    )
    assert client.graph_post_attempts == 1


def test_receipt_miss_allows_only_one_exact_resend(graph_gateway):
    _db, client, gateway = graph_gateway
    current = gateway.get_knowledge_graph()
    edge = _inferred_edge(current)
    proposal = gateway.propose_knowledge_graph_command(
        _command("hide_edge", current["revision"], edge),
    )
    client.fail_graph_posts_before_send = 1

    applied = gateway.apply_proposal(proposal["proposal_id"])
    assert applied["state"] == "applied"
    assert applied["result"]["changed"] is True
    assert client.graph_post_attempts == 2
    with pytest.raises(GatewayError, match="Proposal is applied"):
        gateway.apply_proposal(proposal["proposal_id"])
    assert client.graph_post_attempts == 2


def test_unknown_recovery_fails_closed_on_cross_family_collision(graph_gateway):
    _db, client, gateway = graph_gateway
    current = gateway.get_knowledge_graph()
    edge = _inferred_edge(current)
    proposal = gateway.propose_knowledge_graph_command(
        _command("hide_edge", current["revision"], edge),
    )
    gateway.apply_proposal(proposal["proposal_id"])

    timeline = client.request(
        "GET",
        client.project_path("timeline"),
    )
    client.request(
        "POST",
        client.project_path("timeline/commands"),
        {
            "kind": "create_lane",
            "expected_revision": timeline["revision"],
            "name": "Collision",
        },
        idempotency_key=proposal["proposal_id"],
    )
    fresh = LogosForgeMcpGateway(
        client,  # type: ignore[arg-type]
        allow_writes=True,
        require_auth_for_writes=True,
    )
    with pytest.raises(GatewayError, match="capability collision.*failed closed"):
        fresh.get_proposal(proposal["proposal_id"])
