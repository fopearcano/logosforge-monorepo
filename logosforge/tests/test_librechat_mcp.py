"""Focused unit tests for the Pro MCP gateway safety boundary.

These tests deliberately use a deterministic fake API client.  They verify
that the gateway reads the canonical DTOs and that its proposal lifecycle does
not turn into an alternate, less-safe write API.  No MCP SDK, server process,
database, or desktop session is required.
"""

from __future__ import annotations

import asyncio
import copy
import io
import json
import os
import sys
import time
from pathlib import Path
from unittest import mock

import pytest
from logosforge.librechat import api_client as ac
from logosforge.librechat.api_client import LogosForgeApiClient, LogosForgeApiError
from logosforge.librechat.mcp_gateway import GatewayError, LogosForgeMcpGateway


class _Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


def _response(payload):
    return _Response(json.dumps(payload).encode("utf-8"))


def test_api_client_get_scene_uses_full_scene_endpoint_and_keeps_revision():
    client = LogosForgeApiClient(
        base_url="http://127.0.0.1:8765", project_id=7, auth_token="secret",
    )
    captured = {}
    scene = {
        "id": 31,
        "project_id": 7,
        "title": "The Crossing",
        "content": "Full manuscript prose.",
        "revision": "rev-scene-31",
    }

    def fake_urlopen(request, timeout=None):
        captured.update(
            url=request.full_url,
            method=request.get_method(),
            authorization=request.headers.get("Authorization"),
            timeout=timeout,
        )
        return _response(scene)

    with mock.patch.object(ac.urllib.request, "urlopen", fake_urlopen):
        result = client.get_scene(31)

    assert captured == {
        "url": "http://127.0.0.1:8765/api/projects/7/scenes/31",
        "method": "GET",
        "authorization": "Bearer secret",
        "timeout": 15.0,
    }
    assert result["content"] == "Full manuscript prose."
    assert result["revision"] == "rev-scene-31"


def test_api_client_requires_an_explicit_project_for_scoped_calls():
    client = LogosForgeApiClient(project_id=None)

    with pytest.raises(LogosForgeApiError, match="No LogosForge project is selected"):
        client.get_scene(1)


class _FakeApiClient:
    """Minimal canonical-Pro-API fake with mutable server-side state."""

    def __init__(
        self,
        *,
        project_id: int | None = 1,
        authenticated: bool = True,
        projects: list[dict] | None = None,
    ) -> None:
        self.project_id = project_id
        self._authenticated = authenticated
        self.projects = projects or [
            {"id": 1, "title": "Novel One"},
            {"id": 2, "title": "Novel Two"},
        ]
        self.scenes = {
            1: {
                11: {
                    "id": 11,
                    "project_id": 1,
                    "title": "Opening",
                    "content": "Before.\n",
                    "revision": "rev-1",
                    "status": "draft",
                }
            },
            2: {},
        }
        self.resources = {
            "/api/projects/1/psyke/entries/5": {
                "id": 5,
                "project_id": 1,
                "name": "Ada",
                "type": "character",
                "notes": "Lead",
            },
            "/api/projects/1/outline": [
                {"id": 41, "title": "Act I", "parent_id": None},
            ],
            "/api/projects/1/notes": [
                {"id": 71, "title": "Question", "content": "Why?"},
            ],
            "/api/projects/1/psyke/relations": [],
        }
        self.requests: list[tuple[str, str, dict | None]] = []

    @property
    def has_auth_token(self) -> bool:
        return self._authenticated

    def api_path(self, suffix: str) -> str:
        return f"/api/{suffix.lstrip('/')}"

    def project_path(self, suffix: str = "", project_id: int | None = None) -> str:
        pid = int(project_id) if project_id is not None else self.require_project_id()
        base = f"/api/projects/{pid}"
        return f"{base}/{suffix.lstrip('/')}" if suffix else base

    def require_project_id(self) -> int:
        if self.project_id is None:
            raise LogosForgeApiError("No LogosForge project is selected.")
        return self.project_id

    def list_projects(self) -> list[dict]:
        return copy.deepcopy(self.projects)

    def get_project(self, project_id: int | None = None) -> dict:
        pid = int(project_id) if project_id is not None else self.require_project_id()
        for project in self.projects:
            if project["id"] == pid:
                return copy.deepcopy(project)
        raise LogosForgeApiError(f"Project {pid} not found")

    def select_project(self, project_id: int) -> dict:
        project = self.get_project(project_id)
        self.project_id = int(project_id)
        return project

    def list_scenes(self, project_id: int | None = None) -> list[dict]:
        pid = int(project_id) if project_id is not None else self.require_project_id()
        return copy.deepcopy(list(self.scenes[pid].values()))

    def get_scene(self, scene_id: int, project_id: int | None = None) -> dict:
        pid = int(project_id) if project_id is not None else self.require_project_id()
        return copy.deepcopy(self.scenes[pid][int(scene_id)])

    def get_outline(self, project_id: int | None = None) -> list[dict]:
        pid = int(project_id) if project_id is not None else self.require_project_id()
        return copy.deepcopy(self.resources[f"/api/projects/{pid}/outline"])

    def list_characters(self, project_id: int | None = None) -> list[dict]:
        pid = int(project_id) if project_id is not None else self.require_project_id()
        if pid == 1:
            return [{"id": 91, "name": "Ada", "psyke_entry_id": 5}]
        return []

    def list_psyke_entries(self, project_id: int | None = None) -> list[dict]:
        pid = int(project_id) if project_id is not None else self.require_project_id()
        prefix = f"/api/projects/{pid}/psyke/entries/"
        return copy.deepcopy(
            [value for path, value in self.resources.items() if path.startswith(prefix)]
        )

    def get_psyke_entry(self, entry_id: int, project_id: int | None = None) -> dict:
        return self.request(
            "GET", self.project_path(f"psyke/entries/{int(entry_id)}", project_id),
        )

    def list_psyke_relations(self, project_id: int | None = None) -> list[dict]:
        return self.request("GET", self.project_path("psyke/relations", project_id))

    def list_psyke_progressions(self, project_id: int | None = None) -> list[dict]:
        return []

    def list_notes(self, project_id: int | None = None) -> list[dict]:
        return self.request("GET", self.project_path("notes", project_id))

    def poll_events(self, since: int = 0, project_id: int | None = None) -> dict:
        return {"events": [], "cursor": since}

    def request(
        self,
        method: str,
        path: str,
        body: dict | None = None,
        query: dict | None = None,
    ):
        del query
        method = method.upper()
        stored_body = copy.deepcopy(body)
        self.requests.append((method, path, stored_body))

        if method == "GET":
            return copy.deepcopy(self.resources[path])

        scene_prefix = "/api/projects/1/scenes/"
        if method == "PATCH" and path.startswith(scene_prefix):
            scene_id = int(path.removeprefix(scene_prefix))
            scene = self.scenes[1][scene_id]
            if body is None or body.get("expected_revision") != scene["revision"]:
                raise LogosForgeApiError("revision conflict")
            for key, value in body.items():
                if key != "expected_revision":
                    scene[key] = value
            scene["revision"] = "rev-2"
            return copy.deepcopy(scene)

        if method == "PATCH" and path in self.resources:
            assert body is not None
            self.resources[path].update(body)
            return copy.deepcopy(self.resources[path])

        return {"ok": True, "method": method, "path": path, "body": stored_body}


def _gateway(
    client: _FakeApiClient | None = None,
    *,
    allow_writes: bool = False,
    require_auth_for_writes: bool = True,
) -> tuple[LogosForgeMcpGateway, _FakeApiClient]:
    fake = client or _FakeApiClient()
    return (
        LogosForgeMcpGateway(
            fake,
            allow_writes=allow_writes,
            require_auth_for_writes=require_auth_for_writes,
        ),
        fake,
    )


def test_project_selection_is_explicit_when_ambiguous_and_then_scopes_reads():
    fake = _FakeApiClient(project_id=None)
    gateway, _ = _gateway(fake)

    assert gateway.list_projects() == {
        "projects": fake.projects,
        "selected_project_id": None,
    }
    with pytest.raises(GatewayError, match="No project is selected"):
        gateway.get_project()

    selected = gateway.select_project(2)
    assert selected["selected_project_id"] == 2
    assert gateway.get_project() == {"id": 2, "title": "Novel Two"}


def test_a_single_available_project_is_selected_automatically():
    fake = _FakeApiClient(
        project_id=None, projects=[{"id": 1, "title": "Only Novel"}],
    )
    gateway, _ = _gateway(fake)

    assert gateway.get_project() == {"id": 1, "title": "Only Novel"}
    assert fake.project_id == 1


def test_scene_reads_return_full_content_and_revision_but_lists_are_compact():
    gateway, _ = _gateway()

    scene = gateway.get_scene(11)
    assert scene["content"] == "Before.\n"
    assert scene["revision"] == "rev-1"

    listed = gateway.list_scenes()
    assert listed[0]["revision"] == "rev-1"
    assert listed[0]["content_length"] == len("Before.\n")
    assert "content" not in listed[0]


def test_snapshot_uses_canonical_cast_and_search_includes_scene_prose():
    gateway, _ = _gateway()

    snapshot = gateway.snapshot()
    assert snapshot["characters"] == [
        {"id": 91, "name": "Ada", "psyke_entry_id": 5},
    ]

    search = gateway.search("Before")
    assert len(search["matches"]) == 1
    assert search["matches"][0]["kind"] == "scene"
    assert search["matches"][0]["id"] == 11
    assert "Before." in search["matches"][0]["excerpt"]


def test_scene_proposal_does_not_mutate_and_requires_current_revision():
    gateway, fake = _gateway()

    with pytest.raises(GatewayError, match="expected_revision"):
        gateway.propose_scene_patch(11, "", {"title": "New"})
    with pytest.raises(GatewayError, match="expected_revision"):
        gateway.propose_scene_patch(11, "stale", {"title": "New"})

    proposal = gateway.propose_scene_patch(
        11, "rev-1", {"title": "New", "content": "After.\n"},
    )

    assert proposal["state"] == "pending"
    assert proposal["requires_user_approval"] is True
    assert proposal["request"]["body"]["expected_revision"] == "rev-1"
    assert proposal["request"]["body"]["content"]["length"] == len("After.\n")
    assert fake.scenes[1][11]["title"] == "Opening"
    assert not any(method == "PATCH" for method, _path, _body in fake.requests)


@pytest.mark.parametrize(
    ("allow_writes", "authenticated", "message"),
    [
        (False, True, "Writes are disabled"),
        (True, False, "authenticated LogosForge API"),
    ],
)
def test_apply_enforces_write_and_auth_gates(allow_writes, authenticated, message):
    fake = _FakeApiClient(authenticated=authenticated)
    gateway, _ = _gateway(fake, allow_writes=allow_writes)
    proposal = gateway.propose_scene_patch(11, "rev-1", {"title": "New"})

    with pytest.raises(GatewayError, match=message):
        gateway.apply_proposal(proposal["proposal_id"])

    assert fake.scenes[1][11]["title"] == "Opening"
    assert not any(method == "PATCH" for method, _path, _body in fake.requests)


def test_apply_uses_the_exact_stored_payload_once_and_replay_is_rejected():
    gateway, fake = _gateway(allow_writes=True)
    caller_patch = {"title": "Reviewed title", "content": "Reviewed prose.\n"}
    proposal = gateway.propose_scene_patch(11, "rev-1", caller_patch)
    caller_patch["title"] = "Changed after review"
    caller_patch["content"] = "Unreviewed prose.\n"

    applied = gateway.apply_proposal(proposal["proposal_id"])

    assert applied["state"] == "applied"
    assert fake.scenes[1][11]["title"] == "Reviewed title"
    assert fake.scenes[1][11]["content"] == "Reviewed prose.\n"
    patch_calls = [call for call in fake.requests if call[0] == "PATCH"]
    assert patch_calls == [
        (
            "PATCH",
            "/api/projects/1/scenes/11",
            {
                "title": "Reviewed title",
                "content": "Reviewed prose.\n",
                "expected_revision": "rev-1",
            },
        )
    ]

    with pytest.raises(GatewayError, match="applied, not pending"):
        gateway.apply_proposal(proposal["proposal_id"])
    assert len([call for call in fake.requests if call[0] == "PATCH"]) == 1


def test_digest_guard_rejects_a_stale_proposal_without_mutating():
    gateway, fake = _gateway(allow_writes=True)
    proposal = gateway.propose_patch_psyke_entry(5, {"name": "Ada Revised"})
    resource_path = "/api/projects/1/psyke/entries/5"

    # Simulate another client updating the record after the proposal review.
    fake.resources[resource_path]["notes"] = "Changed elsewhere"

    with pytest.raises(GatewayError, match="target changed"):
        gateway.apply_proposal(proposal["proposal_id"])

    assert fake.resources[resource_path]["name"] == "Ada"
    assert not any(
        method == "PATCH" and path == resource_path
        for method, path, _body in fake.requests
    )
    failed = gateway.get_proposal(proposal["proposal_id"])
    assert failed["state"] == "failed"
    assert "changed after" in failed["error"]


def test_expired_proposals_are_marked_failed_and_do_not_break_listing():
    gateway, _ = _gateway()
    proposal = gateway.propose_scene_patch(11, "rev-1", {"title": "Too late"})
    stored = gateway._proposals[proposal["proposal_id"]]
    stored.expires_at = time.time() - 1

    assert gateway.list_proposals() == {"proposals": []}
    finished = gateway.list_proposals(include_finished=True)["proposals"]
    assert len(finished) == 1
    assert finished[0]["state"] == "failed"
    assert "expired" in finished[0]["error"].lower()

    with pytest.raises(GatewayError, match="expired"):
        gateway.get_proposal(proposal["proposal_id"])


def test_discarded_proposal_cannot_be_applied():
    gateway, fake = _gateway(allow_writes=True)
    proposal = gateway.propose_scene_patch(11, "rev-1", {"title": "Discard me"})

    discarded = gateway.discard_proposal(proposal["proposal_id"])
    assert discarded["state"] == "discarded"
    with pytest.raises(GatewayError, match="discarded, not pending"):
        gateway.apply_proposal(proposal["proposal_id"])
    assert fake.scenes[1][11]["title"] == "Opening"


def test_apply_rejects_project_switch_and_internal_payload_tampering():
    gateway, fake = _gateway(allow_writes=True)
    proposal = gateway.propose_scene_patch(11, "rev-1", {"title": "Reviewed"})

    gateway.select_project(2)
    with pytest.raises(GatewayError, match="selected project differs"):
        gateway.apply_proposal(proposal["proposal_id"])
    assert fake.scenes[1][11]["title"] == "Opening"

    gateway.select_project(1)
    stored = gateway._proposals[proposal["proposal_id"]]
    stored.body["title"] = "Tampered"
    with pytest.raises(GatewayError, match="integrity check failed"):
        gateway.apply_proposal(proposal["proposal_id"])
    assert fake.scenes[1][11]["title"] == "Opening"
    assert gateway.get_proposal(proposal["proposal_id"])["state"] == "failed"


def test_proposal_deep_copies_nested_caller_data():
    gateway, fake = _gateway(allow_writes=True)
    body = {"name": "Nested", "details": {"role": "lead"}}
    proposal = gateway.propose_create_psyke_entry(body)
    body["details"]["role"] = "unreviewed"

    gateway.apply_proposal(proposal["proposal_id"])

    assert fake.requests[-1] == (
        "POST",
        "/api/projects/1/psyke/entries",
        {"name": "Nested", "details": {"role": "lead"}},
    )


def test_mcp_registry_has_unique_focused_tools_and_no_legacy_self_approval():
    from logosforge.librechat import mcp_server as server

    names = [spec.name for spec in server.TOOL_SPECS]
    assert len(names) == len(set(names)) == 35
    assert "logosforge_apply_confirmed_action" not in names
    apply = server.HANDLERS["logosforge_apply_proposal"]
    assert apply.input_schema == server._obj(
        {"proposal_id": {"type": "string"}}, ["proposal_id"],
    )
    assert apply.read_only is False
    assert apply.destructive is True
    assert apply.idempotent is False


def test_mcp_config_defaults_to_loopback_and_rejects_unsafe_remote_urls():
    from logosforge.librechat.mcp_server import McpConfig, McpToolError

    McpConfig().validate()
    with pytest.raises(McpToolError, match="Remote Pro APIs are disabled"):
        McpConfig(base_url="https://example.test").validate()
    with pytest.raises(McpToolError, match="requires HTTPS"):
        McpConfig(
            base_url="http://example.test",
            allow_remote=True,
            auth_token="secret",
        ).validate()
    with pytest.raises(McpToolError, match="requires HTTPS"):
        McpConfig(base_url="https://example.test", allow_remote=True).validate()
    McpConfig(
        base_url="https://example.test",
        allow_remote=True,
        auth_token="secret",
    ).validate()


def test_real_mcp_stdio_initializes_and_advertises_structured_tools():
    mcp = pytest.importorskip("mcp")
    from mcp.client.stdio import stdio_client

    async def exercise():
        params = mcp.StdioServerParameters(
            command=sys.executable,
            args=["-m", "logosforge.librechat.mcp_server"],
            cwd=str(Path(__file__).resolve().parents[1]),
            env={
                **os.environ,
                "LOGOSFORGE_API_URL": "http://127.0.0.1:1",
                "LOGOSFORGE_MCP_ALLOW_WRITES": "0",
            },
        )
        async with (
            stdio_client(params) as streams,
            mcp.ClientSession(*streams) as session,
        ):
            initialized = await session.initialize()
            listed = await session.list_tools()
            return initialized, listed

    initialized, listed = asyncio.run(exercise())
    assert initialized.serverInfo.name == "logosforge"
    assert initialized.serverInfo.version == "1.0.0"
    tools = {tool.name: tool for tool in listed.tools}
    assert len(tools) == 35
    assert tools["logosforge_get_scene"].outputSchema == {
        "type": "object",
        "properties": {
            "ok": {"type": "boolean"},
            "result": {},
            "error": {"type": "string"},
        },
        "required": ["ok"],
        "additionalProperties": False,
    }
    annotations = tools["logosforge_apply_proposal"].annotations
    assert annotations.readOnlyHint is False
    assert annotations.destructiveHint is True
    assert annotations.idempotentHint is False
    assert annotations.openWorldHint is False
