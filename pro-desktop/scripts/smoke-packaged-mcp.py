"""End-to-end smoke for an installed/unpacked Pro application's MCP mode."""

from __future__ import annotations

import argparse
import asyncio
import ctypes
import json
import os
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

import mcp
from mcp.client.stdio import stdio_client


def _available_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def _api_json(
    base_url: str,
    token: str,
    method: str,
    path: str,
    body: dict | None = None,
) -> dict:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(
        f"{base_url}{path}",
        data=data,
        method=method,
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
            **({"Content-Type": "application/json"} if data is not None else {}),
        },
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        return json.load(response)


def _seed_comment(base_url: str, token: str) -> tuple[int, int, str]:
    project = _api_json(
        base_url, token, "POST", "/api/projects", {"title": "MCP smoke"},
    )
    project_id = int(project["id"])
    scene = _api_json(
        base_url,
        token,
        "POST",
        f"/api/projects/{project_id}/scenes",
        {
            "title": "Opening",
            "content": "Packaged comment anchor",
            "act": "Act I",
            "chapter": "One",
        },
    )
    crossing = _api_json(
        base_url,
        token,
        "POST",
        f"/api/projects/{project_id}/scenes",
        {
            "title": "Crossing",
            "content": "A second scene for graph and continuity review.",
            "act": "Act I",
            "chapter": "Two",
        },
    )
    _api_json(
        base_url,
        token,
        "PATCH",
        f"/api/projects/{project_id}/scenes/{int(scene['id'])}",
        {"location": "Kitchen"},
    )
    _api_json(
        base_url,
        token,
        "PATCH",
        f"/api/projects/{project_id}/scenes/{int(crossing['id'])}",
        {"location": "Castle"},
    )
    comment = _api_json(
        base_url,
        token,
        "POST",
        f"/api/projects/{project_id}/comments",
        {
            "anchor": {
                "start_scene_id": int(scene["id"]),
                "start_field": "content",
                "from_offset": 0,
                "end_scene_id": int(scene["id"]),
                "end_field": "content",
                "to_offset": 8,
                "suffix": " comment anchor",
            },
            "quote": "Packaged",
            "body": "Inspect this packaged thread.",
        },
    )
    return project_id, int(comment["id"]), str(comment["revision"])


def _structured(result, label: str) -> dict:
    if result.isError:
        raise RuntimeError(f"{label} failed")
    structured = getattr(result, "structuredContent", None)
    if structured is None:
        structured = getattr(result, "structured_content", None)
    if not isinstance(structured, dict) or structured.get("ok") is not True:
        raise RuntimeError(f"{label} returned an invalid result envelope")
    return structured["result"]


def _expected_tool_error(result, label: str, *expected: str) -> str:
    if not result.isError:
        raise RuntimeError(f"{label} unexpectedly succeeded")
    structured = getattr(result, "structuredContent", None)
    if structured is None:
        structured = getattr(result, "structured_content", None)
    if not isinstance(structured, dict) or structured.get("ok") is not False:
        raise RuntimeError(f"{label} returned an invalid error envelope")
    error = structured.get("error")
    if not isinstance(error, str) or not error:
        raise RuntimeError(f"{label} returned an empty error")
    missing = [fragment for fragment in expected if fragment not in error]
    if missing:
        raise RuntimeError(
            f"{label} returned an unexpected error: {error!r} "
            f"(missing {missing!r})"
        )
    return error


def _comment_from_page(page: dict, comment_id: int, label: str) -> dict:
    comments = page.get("comments")
    if not isinstance(comments, list):
        raise RuntimeError(f"{label} returned no comment list")
    matches = [item for item in comments if item.get("id") == comment_id]
    if len(matches) != 1:
        raise RuntimeError(f"{label} did not return the seeded comment exactly once")
    return matches[0]


def _validate_descriptor(
    descriptor: dict, expected_port: int,
) -> tuple[str, str, str, int, int]:
    """Validate the package-owned connection before any authenticated write."""
    if type(descriptor.get("schema_version")) is not int or descriptor["schema_version"] != 1:
        raise RuntimeError("packaged app published an unsupported MCP descriptor schema")

    base_url = descriptor.get("base_url")
    if not isinstance(base_url, str) or not base_url:
        raise RuntimeError("packaged app published an invalid core URL")
    parsed = urllib.parse.urlparse(base_url)
    try:
        descriptor_port = parsed.port
    except ValueError as exc:
        raise RuntimeError("packaged app published an invalid core port") from exc
    expected_base_url = f"http://127.0.0.1:{expected_port}"
    if (
        parsed.scheme != "http"
        or parsed.hostname != "127.0.0.1"
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
        or descriptor_port != expected_port
        or base_url.rstrip("/") != expected_base_url
    ):
        raise RuntimeError(
            "packaged app MCP descriptor is not the expected loopback endpoint"
        )

    auth_token = descriptor.get("auth_token")
    nonce = descriptor.get("instance_nonce")
    if (
        not isinstance(auth_token, str)
        or auth_token != auth_token.strip()
        or len(auth_token) < 32
    ):
        raise RuntimeError("packaged app published an invalid MCP bearer token")
    if not isinstance(nonce, str) or nonce != nonce.strip() or len(nonce) < 16:
        raise RuntimeError("packaged app published an invalid core nonce")

    created_at = descriptor.get("created_at")
    if not isinstance(created_at, str) or not created_at:
        raise RuntimeError("packaged app published an invalid descriptor timestamp")
    try:
        parsed_created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise RuntimeError("packaged app published an invalid descriptor timestamp") from exc
    if parsed_created_at.tzinfo is None or parsed_created_at.utcoffset() != timedelta(0):
        raise RuntimeError("packaged app descriptor timestamp is not UTC")

    def required_pid(name: str) -> int:
        value = descriptor.get(name)
        if type(value) is not int or value <= 0:
            raise RuntimeError(f"packaged app published an invalid {name}")
        return value

    return (
        expected_base_url,
        auth_token,
        nonce,
        required_pid("app_pid"),
        required_pid("core_pid"),
    )


async def _exercise_installed_mcp(
    command: Path,
    command_args: list[str],
    env: dict[str, str],
    project_id: int,
    comment_id: int,
    comment_revision: str,
) -> tuple[
    str, str, str, int, dict, str, str, dict, str, str, dict, str, str, dict, str,
]:
    params = mcp.StdioServerParameters(
        command=str(command),
        args=command_args,
        cwd=str(command.parent),
        env=env,
    )
    async with (
        stdio_client(params) as streams,
        mcp.ClientSession(*streams) as session,
    ):
        initialized = await session.initialize()
        if initialized.serverInfo.name != "logosforge":
            raise RuntimeError(f"unexpected MCP server: {initialized.serverInfo.name!r}")
        listed = await session.list_tools()
        if len(listed.tools) != 46:
            raise RuntimeError(f"expected 46 MCP tools, received {len(listed.tools)}")
        tool_names = {tool.name for tool in listed.tools}
        expected_tools = {
            "logosforge_get_timeline",
            "logosforge_propose_timeline_command",
            "logosforge_get_canvas_plot",
            "logosforge_propose_canvas_plot_command",
            "logosforge_get_knowledge_graph",
            "logosforge_get_knowledge_graph_hidden_edges",
            "logosforge_propose_knowledge_graph_command",
            "logosforge_get_story_diagnostics",
            "logosforge_propose_continuity_command",
            "logosforge_search",
            "logosforge_list_comments",
            "logosforge_propose_comment_reply",
            "logosforge_propose_comment_resolution",
        }
        missing_tools = expected_tools - tool_names
        if missing_tools:
            raise RuntimeError(
                "missing required MCP tools: "
                + ", ".join(sorted(missing_tools))
            )
        _structured(
            await session.call_tool("logosforge_list_projects", {}),
            "installed MCP authenticated read",
        )
        _structured(
            await session.call_tool(
                "logosforge_select_project", {"project_id": project_id},
            ),
            "installed MCP project selection",
        )
        timeline_before = _structured(
            await session.call_tool("logosforge_get_timeline", {}),
            "installed MCP Timeline read",
        )
        timeline_revision = timeline_before.get("revision")
        if not isinstance(timeline_revision, str) or len(timeline_revision) != 64:
            raise RuntimeError("installed MCP Timeline read returned no valid revision")
        off_timeline = timeline_before.get("off_timeline")
        if not isinstance(off_timeline, list):
            raise RuntimeError("installed MCP Timeline read returned no off-Timeline scenes")
        seeded_timeline_scenes = {
            row.get("title"): row
            for row in off_timeline
            if isinstance(row, dict) and isinstance(row.get("title"), str)
        }
        opening_scene_id = seeded_timeline_scenes.get("Opening", {}).get("id")
        crossing_scene_id = seeded_timeline_scenes.get("Crossing", {}).get("id")
        if (
            type(opening_scene_id) is not int
            or opening_scene_id <= 0
            or type(crossing_scene_id) is not int
            or crossing_scene_id <= 0
            or opening_scene_id == crossing_scene_id
        ):
            raise RuntimeError(
                "installed MCP Timeline read did not expose both seeded scenes"
            )
        timeline_proposal = _structured(
            await session.call_tool(
                "logosforge_propose_timeline_command",
                {
                    "command": {
                        "kind": "create_lane",
                        "expected_revision": timeline_revision,
                        "name": "Packaged MCP lane",
                        "color_label": "cyan",
                    },
                },
            ),
            "installed MCP Timeline proposal",
        )
        stale_timeline_sibling = _structured(
            await session.call_tool(
                "logosforge_propose_timeline_command",
                {
                    "command": {
                        "kind": "create_lane",
                        "expected_revision": timeline_revision,
                        "name": "Stale sibling lane",
                    },
                },
            ),
            "installed MCP stale Timeline sibling proposal",
        )
        if timeline_before != _structured(
            await session.call_tool("logosforge_get_timeline", {}),
            "installed MCP post-proposal Timeline read",
        ):
            raise RuntimeError("Timeline proposal creation mutated project data")

        applied_timeline = _structured(
            await session.call_tool(
                "logosforge_apply_proposal",
                {"proposal_id": timeline_proposal["proposal_id"]},
            ),
            "installed MCP Timeline apply",
        )
        applied_result = applied_timeline.get("result")
        if not isinstance(applied_result, dict):
            raise RuntimeError("installed MCP Timeline apply returned no result receipt")
        applied_snapshot = applied_result.get("timeline", {})
        applied_revision = applied_result.get("applied_revision")
        if applied_timeline.get("state") != "applied":
            raise RuntimeError("installed MCP did not mark Timeline proposal applied")
        if (
            not isinstance(applied_revision, str)
            or len(applied_revision) != 64
            or applied_revision != applied_snapshot.get("revision")
        ):
            raise RuntimeError(
                "installed MCP Timeline apply returned no valid applied revision"
            )
        if applied_snapshot.get("revision") == timeline_revision:
            raise RuntimeError("Timeline apply did not rotate the revision")
        if [lane.get("name") for lane in applied_snapshot.get("lanes", [])] != [
            "Packaged MCP lane",
        ]:
            raise RuntimeError("Timeline apply did not create exactly the reviewed lane")

        stale_timeline_result = await session.call_tool(
            "logosforge_apply_proposal",
            {"proposal_id": stale_timeline_sibling["proposal_id"]},
        )
        _expected_tool_error(
            stale_timeline_result,
            "installed MCP stale Timeline sibling apply",
            "HTTP 409",
            "Timeline changed",
        )
        after_stale_timeline = _structured(
            await session.call_tool("logosforge_get_timeline", {}),
            "installed MCP post-stale Timeline read",
        )
        if after_stale_timeline != applied_snapshot:
            raise RuntimeError("stale Timeline apply changed the reviewed board")

        async def apply_timeline_relationship_command(
            command_body: dict,
            label: str,
        ) -> tuple[dict, dict, dict]:
            proposal = _structured(
                await session.call_tool(
                    "logosforge_propose_timeline_command",
                    {"command": command_body},
                ),
                f"{label} proposal",
            )
            request = proposal.get("request")
            if (
                not isinstance(request, dict)
                or request.get("body") != command_body
            ):
                raise RuntimeError(f"{label} proposal did not preserve its exact command")
            applied = _structured(
                await session.call_tool(
                    "logosforge_apply_proposal",
                    {"proposal_id": proposal.get("proposal_id")},
                ),
                f"{label} apply",
            )
            result = applied.get("result")
            if applied.get("state") != "applied" or not isinstance(result, dict):
                raise RuntimeError(f"{label} did not return an applied result")
            snapshot = result.get("timeline")
            if (
                not isinstance(snapshot, dict)
                or result.get("changed") is not True
                or result.get("replayed") is not False
                or result.get("applied_revision") != snapshot.get("revision")
                or snapshot.get("revision") == command_body.get("expected_revision")
            ):
                raise RuntimeError(f"{label} returned an invalid fresh Timeline result")
            return proposal, result, snapshot

        relationship_snapshot = after_stale_timeline
        for scene_id, title in (
            (opening_scene_id, "Opening"),
            (crossing_scene_id, "Crossing"),
        ):
            _, placement_result, relationship_snapshot = (
                await apply_timeline_relationship_command(
                    {
                        "kind": "place_event",
                        "expected_revision": relationship_snapshot["revision"],
                        "scene_id": scene_id,
                        "lane_id": None,
                    },
                    f"installed MCP place {title} on Timeline",
                )
            )
            if (
                placement_result.get("affected_scene_ids") != []
                or placement_result.get("affected_link_ids") != []
                or placement_result.get("affected_structure_link_ids") != []
                or placement_result.get("created_link_id") is not None
                or placement_result.get("created_structure_link_id") is not None
            ):
                raise RuntimeError(
                    f"placing {title} returned relationship outcome ids"
                )
        if {
            event.get("id")
            for event in relationship_snapshot.get("events", [])
            if isinstance(event, dict)
        } != {opening_scene_id, crossing_scene_id}:
            raise RuntimeError("installed MCP did not place both seeded Timeline events")

        _, created_link_result, relationship_snapshot = (
            await apply_timeline_relationship_command(
                {
                    "kind": "create_link",
                    "expected_revision": relationship_snapshot["revision"],
                    "source_scene_id": opening_scene_id,
                    "target_scene_id": crossing_scene_id,
                    "link_type": "causality",
                    "color_label": "amber",
                    "label": "Packaged relationship draft",
                },
                "installed MCP Timeline relationship create",
            )
        )
        created_link_id = created_link_result.get("created_link_id")
        if (
            type(created_link_id) is not int
            or created_link_id <= 0
            or created_link_result.get("affected_scene_ids") != []
            or created_link_result.get("affected_link_ids") != [created_link_id]
            or created_link_result.get("affected_structure_link_ids") != []
            or created_link_result.get("created_structure_link_id") is not None
        ):
            raise RuntimeError(
                "installed MCP Timeline relationship create returned wrong ids"
            )
        created_links = relationship_snapshot.get("links")
        if (
            not isinstance(created_links, list)
            or len(created_links) != 1
            or created_links[0].get("id") != created_link_id
            or created_links[0].get("source_scene_id") != opening_scene_id
            or created_links[0].get("target_scene_id") != crossing_scene_id
            or created_links[0].get("link_type") != "causality"
            or created_links[0].get("color_label") != "amber"
            or created_links[0].get("label") != "Packaged relationship draft"
        ):
            raise RuntimeError(
                "installed MCP Timeline relationship create did not persist"
            )

        _, updated_link_result, relationship_snapshot = (
            await apply_timeline_relationship_command(
                {
                    "kind": "update_link",
                    "expected_revision": relationship_snapshot["revision"],
                    "link_id": created_link_id,
                    "link_type": "setup_payoff",
                    "color_label": "gold",
                    "label": "Packaged relationship updated",
                },
                "installed MCP Timeline relationship update",
            )
        )
        updated_links = relationship_snapshot.get("links")
        if (
            updated_link_result.get("affected_scene_ids") != []
            or updated_link_result.get("affected_link_ids") != [created_link_id]
            or updated_link_result.get("affected_structure_link_ids") != []
            or updated_link_result.get("created_link_id") is not None
            or updated_link_result.get("created_structure_link_id") is not None
            or not isinstance(updated_links, list)
            or len(updated_links) != 1
            or updated_links[0].get("link_type") != "setup_payoff"
            or updated_links[0].get("color_label") != "gold"
            or updated_links[0].get("label") != "Packaged relationship updated"
        ):
            raise RuntimeError(
                "installed MCP Timeline relationship update did not persist"
            )

        _, deleted_link_result, relationship_snapshot = (
            await apply_timeline_relationship_command(
                {
                    "kind": "delete_link",
                    "expected_revision": relationship_snapshot["revision"],
                    "link_id": created_link_id,
                },
                "installed MCP Timeline relationship delete",
            )
        )
        if (
            deleted_link_result.get("affected_scene_ids") != []
            or deleted_link_result.get("affected_link_ids") != [created_link_id]
            or deleted_link_result.get("affected_structure_link_ids") != []
            or deleted_link_result.get("created_link_id") is not None
            or deleted_link_result.get("created_structure_link_id") is not None
            or relationship_snapshot.get("links") != []
        ):
            raise RuntimeError(
                "installed MCP Timeline relationship delete did not persist"
            )

        _, created_structure_result, relationship_snapshot = (
            await apply_timeline_relationship_command(
                {
                    "kind": "create_structure_link",
                    "expected_revision": relationship_snapshot["revision"],
                    "source_scene_id": opening_scene_id,
                    "target_type": "act",
                    "target_ref": "Act I",
                },
                "installed MCP Timeline structure relationship create",
            )
        )
        created_structure_link_id = created_structure_result.get(
            "created_structure_link_id"
        )
        if (
            type(created_structure_link_id) is not int
            or created_structure_link_id <= 0
            or created_structure_result.get("affected_scene_ids") != []
            or created_structure_result.get("affected_structure_link_ids")
            != [created_structure_link_id]
            or created_structure_result.get("affected_link_ids") != []
            or created_structure_result.get("created_link_id") is not None
            or created_structure_result.get("created_structure_link_id")
            != created_structure_link_id
        ):
            raise RuntimeError(
                "installed MCP Timeline structure relationship create returned wrong ids"
            )
        structure_links = relationship_snapshot.get("structure_links")
        if (
            not isinstance(structure_links, list)
            or len(structure_links) != 1
            or structure_links[0].get("id") != created_structure_link_id
            or structure_links[0].get("source_scene_id") != opening_scene_id
            or structure_links[0].get("target_type") != "act"
            or structure_links[0].get("target_ref") != "Act I"
            or structure_links[0].get("target_exists") is not True
        ):
            raise RuntimeError(
                "installed MCP Timeline structure relationship create did not persist"
            )

        _, updated_structure_result, relationship_snapshot = (
            await apply_timeline_relationship_command(
                {
                    "kind": "update_structure_link",
                    "expected_revision": relationship_snapshot["revision"],
                    "structure_link_id": created_structure_link_id,
                    "target_type": "chapter",
                    "target_ref": "Two",
                },
                "installed MCP Timeline structure relationship update",
            )
        )
        structure_links = relationship_snapshot.get("structure_links")
        if (
            updated_structure_result.get("affected_scene_ids") != []
            or updated_structure_result.get("affected_link_ids") != []
            or updated_structure_result.get("affected_structure_link_ids")
            != [created_structure_link_id]
            or updated_structure_result.get("created_link_id") is not None
            or updated_structure_result.get("created_structure_link_id") is not None
            or not isinstance(structure_links, list)
            or len(structure_links) != 1
            or structure_links[0].get("id") != created_structure_link_id
            or structure_links[0].get("source_scene_id") != opening_scene_id
            or structure_links[0].get("target_type") != "chapter"
            or structure_links[0].get("target_ref") != "Two"
            or structure_links[0].get("target_exists") is not True
        ):
            raise RuntimeError(
                "installed MCP Timeline structure relationship update did not persist"
            )

        _, deleted_structure_result, relationship_snapshot = (
            await apply_timeline_relationship_command(
                {
                    "kind": "delete_structure_link",
                    "expected_revision": relationship_snapshot["revision"],
                    "structure_link_id": created_structure_link_id,
                },
                "installed MCP Timeline structure relationship delete",
            )
        )
        if (
            deleted_structure_result.get("affected_scene_ids") != []
            or deleted_structure_result.get("affected_link_ids") != []
            or deleted_structure_result.get("affected_structure_link_ids")
            != [created_structure_link_id]
            or deleted_structure_result.get("created_link_id") is not None
            or deleted_structure_result.get("created_structure_link_id") is not None
            or relationship_snapshot.get("structure_links") != []
        ):
            raise RuntimeError(
                "installed MCP Timeline structure relationship delete did not persist"
            )

        (
            recovery_timeline_proposal,
            recovery_link_result,
            relationship_snapshot,
        ) = await apply_timeline_relationship_command(
            {
                "kind": "create_link",
                "expected_revision": relationship_snapshot["revision"],
                "source_scene_id": crossing_scene_id,
                "target_scene_id": opening_scene_id,
                "link_type": "dependency",
                "color_label": "cyan",
                "label": "Persisted for companion recovery",
            },
            "installed MCP Timeline recovery relationship create",
        )
        recovery_link_id = recovery_link_result.get("created_link_id")
        if (
            type(recovery_link_id) is not int
            or recovery_link_id <= 0
            or recovery_link_result.get("affected_scene_ids") != []
            or recovery_link_result.get("affected_link_ids") != [recovery_link_id]
            or recovery_link_result.get("affected_structure_link_ids") != []
            or recovery_link_result.get("created_structure_link_id") is not None
        ):
            raise RuntimeError(
                "installed MCP Timeline recovery relationship returned wrong ids"
            )
        persisted_links = relationship_snapshot.get("links")
        if (
            not isinstance(persisted_links, list)
            or len(persisted_links) != 1
            or persisted_links[0].get("id") != recovery_link_id
            or persisted_links[0].get("source_scene_id") != crossing_scene_id
            or persisted_links[0].get("target_scene_id") != opening_scene_id
            or persisted_links[0].get("link_type") != "dependency"
            or persisted_links[0].get("color_label") != "cyan"
            or persisted_links[0].get("label") != "Persisted for companion recovery"
        ):
            raise RuntimeError(
                "installed MCP Timeline recovery relationship did not persist"
            )

        canvas_before = _structured(
            await session.call_tool(
                "logosforge_get_canvas_plot", {"include_bodies": True},
            ),
            "installed MCP Canvas Plot read",
        )
        canvas_revision = canvas_before.get("revision")
        if (
            not isinstance(canvas_revision, str)
            or len(canvas_revision) != 64
            or any(char not in "0123456789abcdef" for char in canvas_revision)
            or canvas_before.get("project_id") != project_id
            or canvas_before.get("nodes") != []
            or canvas_before.get("links") != []
            or canvas_before.get("frames") != []
        ):
            raise RuntimeError(
                "installed MCP Canvas Plot read returned an invalid empty snapshot"
            )
        canvas_command = {
            "kind": "create_node",
            "expected_revision": canvas_revision,
            "title": "Packaged MCP Canvas node",
            "body": "Applied by the installed MCP companion.",
            "x": 96.0,
            "y": 128.0,
            "width": 260.0,
            "height": 144.0,
            "color_label": "violet",
            "group_label": "Packaged acceptance",
        }
        stale_canvas_command = {
            **canvas_command,
            "title": "Stale Canvas sibling node",
            "x": 420.0,
        }
        canvas_proposal = _structured(
            await session.call_tool(
                "logosforge_propose_canvas_plot_command",
                {"command": canvas_command},
            ),
            "installed MCP Canvas Plot proposal",
        )
        stale_canvas_sibling = _structured(
            await session.call_tool(
                "logosforge_propose_canvas_plot_command",
                {"command": stale_canvas_command},
            ),
            "installed MCP stale Canvas Plot sibling proposal",
        )
        if canvas_proposal.get("request") != {
            "method": "POST",
            "path": f"/api/projects/{project_id}/canvas-plot/commands",
            "body": canvas_command,
        }:
            raise RuntimeError(
                "installed MCP Canvas Plot proposal did not store the exact command"
            )
        if canvas_before != _structured(
            await session.call_tool(
                "logosforge_get_canvas_plot", {"include_bodies": True},
            ),
            "installed MCP post-proposal Canvas Plot read",
        ):
            raise RuntimeError("Canvas Plot proposal creation mutated project data")

        applied_canvas = _structured(
            await session.call_tool(
                "logosforge_apply_proposal",
                {"proposal_id": canvas_proposal["proposal_id"]},
            ),
            "installed MCP Canvas Plot apply",
        )
        applied_canvas_result = applied_canvas.get("result")
        if not isinstance(applied_canvas_result, dict):
            raise RuntimeError(
                "installed MCP Canvas Plot apply returned no result receipt"
            )
        applied_canvas_snapshot = applied_canvas_result.get("canvas_plot")
        if applied_canvas.get("state") != "applied" or not isinstance(
            applied_canvas_snapshot, dict
        ):
            raise RuntimeError(
                "installed MCP did not mark the Canvas Plot proposal applied"
            )
        applied_canvas_revision = applied_canvas_snapshot.get("revision")
        if (
            not isinstance(applied_canvas_revision, str)
            or len(applied_canvas_revision) != 64
            or any(
                char not in "0123456789abcdef"
                for char in applied_canvas_revision
            )
            or applied_canvas_revision == canvas_revision
        ):
            raise RuntimeError("Canvas Plot apply did not rotate the revision")
        if (
            applied_canvas_result.get("replayed") is not False
            or applied_canvas_result.get("applied_revision")
            != applied_canvas_revision
            or applied_canvas_result.get("changed") is not True
        ):
            raise RuntimeError(
                "Canvas Plot apply returned an invalid fresh command receipt"
            )
        canvas_nodes = applied_canvas_snapshot.get("nodes")
        if not isinstance(canvas_nodes, list) or len(canvas_nodes) != 1:
            raise RuntimeError("Canvas Plot apply did not create exactly one node")
        canvas_node = canvas_nodes[0]
        if not isinstance(canvas_node, dict) or any(
            canvas_node.get(field) != expected
            for field, expected in {
                "title": canvas_command["title"],
                "body": canvas_command["body"],
                "x": canvas_command["x"],
                "y": canvas_command["y"],
                "width": canvas_command["width"],
                "height": canvas_command["height"],
                "color_label": canvas_command["color_label"],
                "group_label": canvas_command["group_label"],
            }.items()
        ):
            raise RuntimeError(
                "Canvas Plot apply did not preserve the reviewed node payload"
            )
        created_node_id = applied_canvas_result.get("created_node_id")
        if (
            not isinstance(created_node_id, int)
            or canvas_node.get("id") != created_node_id
            or applied_canvas_result.get("affected_node_ids") != [created_node_id]
            or applied_canvas_result.get("affected_link_ids") != []
            or applied_canvas_result.get("affected_frame_ids") != []
            or applied_canvas_result.get("created_link_id") is not None
            or applied_canvas_result.get("created_frame_id") is not None
        ):
            raise RuntimeError(
                "Canvas Plot apply returned inconsistent created/affected IDs"
            )

        stale_canvas_result = await session.call_tool(
            "logosforge_apply_proposal",
            {"proposal_id": stale_canvas_sibling["proposal_id"]},
        )
        _expected_tool_error(
            stale_canvas_result,
            "installed MCP stale Canvas Plot sibling apply",
            "HTTP 409",
            "Canvas Plot changed",
        )
        after_stale_canvas = _structured(
            await session.call_tool(
                "logosforge_get_canvas_plot", {"include_bodies": True},
            ),
            "installed MCP post-stale Canvas Plot read",
        )
        if after_stale_canvas != applied_canvas_snapshot:
            raise RuntimeError("stale Canvas Plot apply changed the reviewed board")

        graph_before = _structured(
            await session.call_tool("logosforge_get_knowledge_graph", {}),
            "installed MCP Knowledge Graph read",
        )
        graph_revision = graph_before.get("revision")
        graph_edges = graph_before.get("edges")
        if (
            not isinstance(graph_revision, str)
            or len(graph_revision) != 64
            or any(char not in "0123456789abcdef" for char in graph_revision)
            or graph_before.get("project_id") != project_id
            or not isinstance(graph_edges, list)
        ):
            raise RuntimeError(
                "installed MCP Knowledge Graph read returned an invalid map"
            )
        inferred_edge = next(
            (
                edge for edge in graph_edges
                if isinstance(edge, dict)
                and edge.get("is_inferred") is True
                and edge.get("is_user_confirmed") is False
                and edge.get("is_hidden") is False
            ),
            None,
        )
        if inferred_edge is None:
            raise RuntimeError(
                "installed MCP Knowledge Graph returned no reviewable edge"
            )
        graph_identity = {
            key: inferred_edge[key]
            for key in ("source", "target", "edge_type")
        }
        graph_command = {
            "kind": "hide_edge",
            "expected_revision": graph_revision,
            **graph_identity,
        }
        stale_graph_command = {
            **graph_command,
            "kind": "confirm_edge",
        }
        graph_proposal = _structured(
            await session.call_tool(
                "logosforge_propose_knowledge_graph_command",
                {"command": graph_command},
            ),
            "installed MCP Knowledge Graph proposal",
        )
        stale_graph_sibling = _structured(
            await session.call_tool(
                "logosforge_propose_knowledge_graph_command",
                {"command": stale_graph_command},
            ),
            "installed MCP stale Knowledge Graph sibling proposal",
        )
        if graph_proposal.get("request") != {
            "method": "POST",
            "path": f"/api/projects/{project_id}/knowledge-graph/commands",
            "body": graph_command,
        }:
            raise RuntimeError(
                "installed MCP Knowledge Graph proposal did not store the exact command"
            )
        if graph_before != _structured(
            await session.call_tool("logosforge_get_knowledge_graph", {}),
            "installed MCP post-proposal Knowledge Graph read",
        ):
            raise RuntimeError("Knowledge Graph proposal creation mutated project data")

        applied_graph = _structured(
            await session.call_tool(
                "logosforge_apply_proposal",
                {"proposal_id": graph_proposal["proposal_id"]},
            ),
            "installed MCP Knowledge Graph apply",
        )
        applied_graph_result = applied_graph.get("result")
        if not isinstance(applied_graph_result, dict):
            raise RuntimeError(
                "installed MCP Knowledge Graph apply returned no result receipt"
            )
        applied_graph_snapshot = applied_graph_result.get("knowledge_graph")
        applied_graph_revision = applied_graph_result.get("applied_revision")
        if (
            applied_graph.get("state") != "applied"
            or not isinstance(applied_graph_snapshot, dict)
            or not isinstance(applied_graph_revision, str)
            or len(applied_graph_revision) != 64
            or applied_graph_revision != applied_graph_snapshot.get("revision")
            or applied_graph_revision == graph_revision
            or applied_graph_result.get("replayed") is not False
            or applied_graph_result.get("changed") is not True
            or applied_graph_result.get("affected_edge") != graph_identity
            or applied_graph_snapshot.get("hidden_edge_count") != 1
        ):
            raise RuntimeError(
                "Knowledge Graph apply returned an invalid fresh command receipt"
            )
        hidden_page = _structured(
            await session.call_tool(
                "logosforge_get_knowledge_graph_hidden_edges",
                {"offset": 0, "limit": 100},
            ),
            "installed MCP hidden Knowledge Graph queue",
        )
        if (
            hidden_page.get("revision") != applied_graph_revision
            or hidden_page.get("hidden_edge_count") != 1
            or hidden_page.get("returned_edge_count") != 1
            or not any(
                isinstance(edge, dict)
                and all(edge.get(key) == value for key, value in graph_identity.items())
                and edge.get("is_hidden") is True
                for edge in hidden_page.get("edges", [])
            )
        ):
            raise RuntimeError(
                "installed MCP hidden-edge queue omitted the reviewed edge"
            )

        stale_graph_result = await session.call_tool(
            "logosforge_apply_proposal",
            {"proposal_id": stale_graph_sibling["proposal_id"]},
        )
        _expected_tool_error(
            stale_graph_result,
            "installed MCP stale Knowledge Graph sibling apply",
            "HTTP 409",
            "Knowledge Graph review state changed",
        )
        after_stale_graph = _structured(
            await session.call_tool("logosforge_get_knowledge_graph", {}),
            "installed MCP post-stale Knowledge Graph read",
        )
        if after_stale_graph != applied_graph_snapshot:
            raise RuntimeError("stale Knowledge Graph apply changed the reviewed map")

        continuity_before = _structured(
            await session.call_tool(
                "logosforge_get_story_diagnostics", {"report": "continuity"},
            ),
            "installed MCP Continuity read",
        )
        continuity_revision = continuity_before.get("review_revision")
        continuity_issues = continuity_before.get("issues")
        if (
            not isinstance(continuity_revision, str)
            or len(continuity_revision) != 64
            or any(char not in "0123456789abcdef" for char in continuity_revision)
            or continuity_before.get("project_id") != project_id
            or not isinstance(continuity_issues, list)
        ):
            raise RuntimeError("installed MCP Continuity read returned an invalid report")
        continuity_issue = next(
            (
                issue for issue in continuity_issues
                if isinstance(issue, dict)
                and issue.get("status") == "open"
                and isinstance(issue.get("id"), str)
                and len(issue["id"]) == 16
                and isinstance(issue.get("review_fingerprint"), str)
                and len(issue["review_fingerprint"]) == 64
            ),
            None,
        )
        if continuity_issue is None:
            raise RuntimeError("installed MCP Continuity returned no reviewable issue")
        continuity_issue_id = continuity_issue["id"]
        continuity_fingerprint = continuity_issue["review_fingerprint"]
        continuity_command = {
            "kind": "resolve_issue",
            "expected_revision": continuity_revision,
            "issue_id": continuity_issue_id,
            "expected_issue_fingerprint": continuity_fingerprint,
        }
        stale_continuity_command = {
            **continuity_command,
            "kind": "defer_issue",
        }
        continuity_proposal = _structured(
            await session.call_tool(
                "logosforge_propose_continuity_command",
                {"command": continuity_command},
            ),
            "installed MCP Continuity proposal",
        )
        stale_continuity_sibling = _structured(
            await session.call_tool(
                "logosforge_propose_continuity_command",
                {"command": stale_continuity_command},
            ),
            "installed MCP stale Continuity sibling proposal",
        )
        if continuity_proposal.get("request") != {
            "method": "POST",
            "path": f"/api/projects/{project_id}/continuity/commands",
            "body": continuity_command,
        }:
            raise RuntimeError(
                "installed MCP Continuity proposal did not store the exact command"
            )
        if continuity_before != _structured(
            await session.call_tool(
                "logosforge_get_story_diagnostics", {"report": "continuity"},
            ),
            "installed MCP post-proposal Continuity read",
        ):
            raise RuntimeError("Continuity proposal creation mutated project data")

        applied_continuity = _structured(
            await session.call_tool(
                "logosforge_apply_proposal",
                {"proposal_id": continuity_proposal["proposal_id"]},
            ),
            "installed MCP Continuity apply",
        )
        applied_continuity_result = applied_continuity.get("result")
        applied_continuity_report = (
            applied_continuity_result.get("continuity")
            if isinstance(applied_continuity_result, dict)
            else None
        )
        applied_continuity_revision = (
            applied_continuity_result.get("applied_revision")
            if isinstance(applied_continuity_result, dict)
            else None
        )
        reviewed_continuity_issue = next(
            (
                issue for issue in applied_continuity_report.get("issues", [])
                if isinstance(issue, dict) and issue.get("id") == continuity_issue_id
            ),
            None,
        ) if isinstance(applied_continuity_report, dict) else None
        if (
            applied_continuity.get("state") != "applied"
            or not isinstance(applied_continuity_result, dict)
            or not isinstance(applied_continuity_report, dict)
            or not isinstance(applied_continuity_revision, str)
            or len(applied_continuity_revision) != 64
            or applied_continuity_revision == continuity_revision
            or applied_continuity_revision
            != applied_continuity_report.get("review_revision")
            or applied_continuity_result.get("replayed") is not False
            or applied_continuity_result.get("changed") is not True
            or applied_continuity_result.get("affected_issue_id")
            != continuity_issue_id
            or applied_continuity_result.get("previous_status") != "open"
            or applied_continuity_result.get("status") != "resolved"
            or not isinstance(reviewed_continuity_issue, dict)
            or reviewed_continuity_issue.get("status") != "resolved"
        ):
            raise RuntimeError(
                "Continuity apply returned an invalid fresh command receipt"
            )

        stale_continuity_result = await session.call_tool(
            "logosforge_apply_proposal",
            {"proposal_id": stale_continuity_sibling["proposal_id"]},
        )
        _expected_tool_error(
            stale_continuity_result,
            "installed MCP stale Continuity sibling apply",
            "HTTP 409",
            "Continuity review state changed",
        )
        after_stale_continuity = _structured(
            await session.call_tool(
                "logosforge_get_story_diagnostics", {"report": "continuity"},
            ),
            "installed MCP post-stale Continuity read",
        )
        if after_stale_continuity != applied_continuity_report:
            raise RuntimeError("stale Continuity apply changed the reviewed report")

        search = _structured(
            await session.call_tool(
                "logosforge_search", {"query": "Inspect this packaged thread."},
            ),
            "installed MCP canonical project search",
        )
        search_match = next(
            (
                item for item in search.get("matches", [])
                if item.get("kind") == "comment" and item.get("id") == comment_id
            ),
            None,
        )
        if search_match is None:
            raise RuntimeError("installed MCP search did not return the seeded comment")
        if search_match.get("revision") != comment_revision:
            raise RuntimeError("installed MCP search returned the wrong comment revision")
        if search_match.get("resolved") is not False:
            raise RuntimeError(
                "installed MCP search returned the wrong comment resolution state"
            )
        comment_page = _structured(
            await session.call_tool(
                "logosforge_list_comments", {"include_resolved": True},
            ),
            "installed MCP comment read",
        )
        if [item.get("id") for item in comment_page.get("comments", [])] != [comment_id]:
            raise RuntimeError("installed MCP did not return the seeded comment")
        original = _comment_from_page(
            comment_page, comment_id, "installed MCP comment read",
        )
        if original.get("revision") != comment_revision:
            raise RuntimeError("installed MCP returned the wrong comment revision")
        if original.get("resolved") is not False or original.get("replies") != []:
            raise RuntimeError("seeded comment did not start as an empty open thread")

        reply_body = "Packaged CAS reply smoke."
        reply_proposal = _structured(
            await session.call_tool(
                "logosforge_propose_comment_reply",
                {
                    "comment_id": comment_id,
                    "expected_revision": comment_revision,
                    "body": reply_body,
                },
            ),
            "installed MCP comment reply proposal",
        )
        stale_sibling = _structured(
            await session.call_tool(
                "logosforge_propose_comment_resolution",
                {
                    "comment_id": comment_id,
                    "expected_revision": comment_revision,
                    "resolved": True,
                },
            ),
            "installed MCP stale sibling resolution proposal",
        )

        applied_reply = _structured(
            await session.call_tool(
                "logosforge_apply_proposal",
                {"proposal_id": reply_proposal["proposal_id"]},
            ),
            "installed MCP comment reply apply",
        )
        if applied_reply.get("state") != "applied":
            raise RuntimeError("installed MCP did not mark the reply proposal applied")

        after_reply_page = _structured(
            await session.call_tool(
                "logosforge_list_comments", {"include_resolved": True},
            ),
            "installed MCP post-reply comment read",
        )
        after_reply = _comment_from_page(
            after_reply_page, comment_id, "installed MCP post-reply comment read",
        )
        after_reply_revision = after_reply.get("revision")
        if (
            not isinstance(after_reply_revision, str)
            or after_reply_revision == comment_revision
        ):
            raise RuntimeError("applying the reply did not rotate the comment revision")
        if after_reply.get("resolved") is not False:
            raise RuntimeError("applying the reply unexpectedly resolved the comment")
        replies = after_reply.get("replies")
        if not isinstance(replies, list) or len(replies) != 1:
            raise RuntimeError("applying the reply did not create exactly one reply")
        if replies[0].get("author") != "MCP assistant":
            raise RuntimeError("applied reply attribution was not exactly 'MCP assistant'")
        if replies[0].get("body") != reply_body:
            raise RuntimeError("applied reply body did not match the reviewed proposal")

        stale_result = await session.call_tool(
            "logosforge_apply_proposal",
            {"proposal_id": stale_sibling["proposal_id"]},
        )
        _expected_tool_error(
            stale_result,
            "installed MCP stale sibling apply",
            "HTTP 409",
            "comment thread changed",
        )
        after_stale_page = _structured(
            await session.call_tool(
                "logosforge_list_comments", {"include_resolved": True},
            ),
            "installed MCP post-stale comment read",
        )
        after_stale = _comment_from_page(
            after_stale_page, comment_id, "installed MCP post-stale comment read",
        )
        if after_stale != after_reply:
            raise RuntimeError("stale sibling apply mutated the comment thread")

        resolution_proposal = _structured(
            await session.call_tool(
                "logosforge_propose_comment_resolution",
                {
                    "comment_id": comment_id,
                    "expected_revision": after_reply_revision,
                    "resolved": True,
                },
            ),
            "installed MCP fresh comment resolution proposal",
        )
        applied_resolution = _structured(
            await session.call_tool(
                "logosforge_apply_proposal",
                {"proposal_id": resolution_proposal["proposal_id"]},
            ),
            "installed MCP fresh comment resolution apply",
        )
        if applied_resolution.get("state") != "applied":
            raise RuntimeError(
                "installed MCP did not mark the resolution proposal applied"
            )

        resolved_page = _structured(
            await session.call_tool(
                "logosforge_list_comments", {"include_resolved": True},
            ),
            "installed MCP resolved comment read",
        )
        resolved = _comment_from_page(
            resolved_page, comment_id, "installed MCP resolved comment read",
        )
        resolved_revision = resolved.get("revision")
        if resolved.get("resolved") is not True:
            raise RuntimeError("fresh resolution proposal did not resolve the comment")
        if (
            not isinstance(resolved_revision, str)
            or resolved_revision == after_reply_revision
        ):
            raise RuntimeError("resolving the comment did not rotate its revision")
        if resolved.get("replies") != replies:
            raise RuntimeError("resolving the comment unexpectedly changed its replies")

        replay_result = await session.call_tool(
            "logosforge_apply_proposal",
            {"proposal_id": reply_proposal["proposal_id"]},
        )
        _expected_tool_error(
            replay_result,
            "installed MCP applied proposal replay",
            "applied, not pending",
        )
        after_replay_page = _structured(
            await session.call_tool(
                "logosforge_list_comments", {"include_resolved": True},
            ),
            "installed MCP post-replay comment read",
        )
        if _comment_from_page(
            after_replay_page, comment_id, "installed MCP post-replay comment read",
        ) != resolved:
            raise RuntimeError("replaying an applied proposal mutated the comment thread")
        timeline_proposal_id = recovery_timeline_proposal.get("proposal_id")
        if not isinstance(timeline_proposal_id, str) or not timeline_proposal_id:
            raise RuntimeError(
                "installed MCP Timeline recovery proposal returned no proposal ID"
            )
        applied_timeline_revision = recovery_link_result.get("applied_revision")
        if (
            not isinstance(applied_timeline_revision, str)
            or applied_timeline_revision != relationship_snapshot.get("revision")
        ):
            raise RuntimeError(
                "installed MCP Timeline recovery relationship returned no revision"
            )
        canvas_proposal_id = canvas_proposal.get("proposal_id")
        if not isinstance(canvas_proposal_id, str) or not canvas_proposal_id:
            raise RuntimeError(
                "installed MCP Canvas Plot proposal returned no proposal ID"
            )
        graph_proposal_id = graph_proposal.get("proposal_id")
        if not isinstance(graph_proposal_id, str) or not graph_proposal_id:
            raise RuntimeError(
                "installed MCP Knowledge Graph proposal returned no proposal ID"
            )
        continuity_proposal_id = continuity_proposal.get("proposal_id")
        if not isinstance(continuity_proposal_id, str) or not continuity_proposal_id:
            raise RuntimeError(
                "installed MCP Continuity proposal returned no proposal ID"
            )
        return (
            resolved_revision,
            timeline_proposal_id,
            applied_timeline_revision,
            recovery_link_id,
            relationship_snapshot,
            canvas_proposal_id,
            applied_canvas_revision,
            applied_canvas_snapshot,
            graph_proposal_id,
            applied_graph_revision,
            applied_graph_snapshot,
            continuity_proposal_id,
            applied_continuity_revision,
            applied_continuity_report,
            continuity_issue_id,
        )


async def _recover_installed_command_receipts(
    command: Path,
    command_args: list[str],
    env: dict[str, str],
    project_id: int,
    timeline_proposal_id: str,
    applied_timeline_revision: str,
    expected_timeline_link_id: int,
    expected_timeline: dict,
    canvas_proposal_id: str,
    applied_canvas_revision: str,
    expected_canvas_plot: dict,
    graph_proposal_id: str,
    applied_graph_revision: str,
    expected_knowledge_graph: dict,
    continuity_proposal_id: str,
    applied_continuity_revision: str,
    expected_continuity: dict,
    continuity_issue_id: str,
) -> None:
    """Recover all four durable command-family receipts after restart."""
    params = mcp.StdioServerParameters(
        command=str(command),
        args=command_args,
        cwd=str(command.parent),
        env=env,
    )
    async with (
        stdio_client(params) as streams,
        mcp.ClientSession(*streams) as session,
    ):
        initialized = await session.initialize()
        if initialized.serverInfo.name != "logosforge":
            raise RuntimeError(f"unexpected MCP server: {initialized.serverInfo.name!r}")
        _structured(
            await session.call_tool(
                "logosforge_select_project", {"project_id": project_id},
            ),
            "restarted MCP project selection",
        )
        restarted_canvas_plot = _structured(
            await session.call_tool(
                "logosforge_get_canvas_plot", {"include_bodies": True},
            ),
            "restarted MCP Canvas Plot persistence read",
        )
        if restarted_canvas_plot != expected_canvas_plot:
            raise RuntimeError(
                "restarted MCP did not read the persisted Canvas Plot snapshot"
            )
        recovered = _structured(
            await session.call_tool(
                "logosforge_get_proposal",
                {"proposal_id": timeline_proposal_id},
            ),
            "restarted MCP durable Timeline receipt recovery",
        )
        if recovered.get("state") != "applied":
            raise RuntimeError(
                "restarted MCP did not recover the Timeline proposal as applied"
            )
        if (
            recovered.get("recovered_from_core") is not True
            or recovered.get("request") is not None
        ):
            raise RuntimeError(
                "restarted MCP did not identify Core as the durable receipt source"
            )
        recovered_receipt = recovered.get("receipt")
        if (
            not isinstance(recovered_receipt, dict)
            or recovered_receipt.get("applied_revision")
            != applied_timeline_revision
        ):
            raise RuntimeError("restarted MCP returned the wrong canonical receipt")
        if (
            recovered_receipt.get("original_changed") is not True
            or recovered_receipt.get("original_affected_scene_ids") != []
            or recovered_receipt.get("original_affected_link_ids")
            != [expected_timeline_link_id]
            or recovered_receipt.get("original_affected_structure_link_ids") != []
            or recovered_receipt.get("original_created_link_id")
            != expected_timeline_link_id
            or recovered_receipt.get("original_created_structure_link_id") is not None
        ):
            raise RuntimeError(
                "restarted MCP Timeline receipt lost its exact relationship ids"
            )
        recovered_result = recovered.get("result")
        if not isinstance(recovered_result, dict):
            raise RuntimeError("restarted MCP recovered no Timeline result receipt")
        if recovered_result.get("replayed") is not True:
            raise RuntimeError("restarted MCP Timeline receipt was not marked replayed")
        if recovered_result.get("applied_revision") != applied_timeline_revision:
            raise RuntimeError(
                "restarted MCP Timeline receipt returned the wrong applied revision"
            )
        if (
            recovered_result.get("changed") is not False
            or recovered_result.get("affected_scene_ids") != []
            or recovered_result.get("affected_link_ids") != []
            or recovered_result.get("affected_structure_link_ids") != []
            or recovered_result.get("created_link_id") is not None
            or recovered_result.get("created_structure_link_id") is not None
        ):
            raise RuntimeError(
                "restarted MCP Timeline receipt was not a non-mutating replay"
            )

        current_timeline = _structured(
            await session.call_tool("logosforge_get_timeline", {}),
            "restarted MCP Timeline read",
        )
        if current_timeline != expected_timeline:
            raise RuntimeError(
                "restarted MCP did not read the persisted Timeline relationship snapshot"
            )
        if recovered_result.get("timeline") != current_timeline:
            raise RuntimeError(
                "restarted MCP receipt did not return the current Timeline snapshot"
            )
        packaged_lane_count = sum(
            lane.get("name") == "Packaged MCP lane"
            for lane in current_timeline.get("lanes", [])
            if isinstance(lane, dict)
        )
        if packaged_lane_count != 1:
            raise RuntimeError(
                "restarted MCP recovery did not preserve exactly one packaged lane"
            )
        persisted_links = current_timeline.get("links")
        if (
            not isinstance(persisted_links, list)
            or len(persisted_links) != 1
            or persisted_links[0].get("id") != expected_timeline_link_id
            or current_timeline.get("structure_links") != []
        ):
            raise RuntimeError(
                "restarted MCP receipt recovery repeated or lost the Timeline relationship"
            )

        recovered_canvas = _structured(
            await session.call_tool(
                "logosforge_get_proposal",
                {"proposal_id": canvas_proposal_id},
            ),
            "restarted MCP durable Canvas Plot receipt recovery",
        )
        if recovered_canvas.get("state") != "applied":
            raise RuntimeError(
                "restarted MCP did not recover the Canvas Plot proposal as applied"
            )
        if (
            recovered_canvas.get("recovered_from_core") is not True
            or recovered_canvas.get("request") is not None
        ):
            raise RuntimeError(
                "restarted MCP did not identify Core as the Canvas receipt source"
            )
        recovered_canvas_receipt = recovered_canvas.get("receipt")
        expected_canvas_nodes = expected_canvas_plot.get("nodes")
        expected_created_node_id = (
            expected_canvas_nodes[0].get("id")
            if isinstance(expected_canvas_nodes, list)
            and len(expected_canvas_nodes) == 1
            and isinstance(expected_canvas_nodes[0], dict)
            else None
        )
        if (
            not isinstance(recovered_canvas_receipt, dict)
            or not isinstance(expected_created_node_id, int)
            or recovered_canvas_receipt.get("project_id") != project_id
            or recovered_canvas_receipt.get("command_kind") != "create_node"
            or recovered_canvas_receipt.get("applied_revision")
            != applied_canvas_revision
            or recovered_canvas_receipt.get("original_changed") is not True
            or recovered_canvas_receipt.get("original_affected_node_ids")
            != [expected_created_node_id]
            or recovered_canvas_receipt.get("original_affected_link_ids") != []
            or recovered_canvas_receipt.get("original_affected_frame_ids") != []
            or recovered_canvas_receipt.get("original_created_node_id")
            != expected_created_node_id
            or recovered_canvas_receipt.get("original_created_link_id") is not None
            or recovered_canvas_receipt.get("original_created_frame_id") is not None
        ):
            raise RuntimeError(
                "restarted MCP returned the wrong canonical Canvas Plot receipt"
            )
        recovered_canvas_result = recovered_canvas.get("result")
        if not isinstance(recovered_canvas_result, dict):
            raise RuntimeError(
                "restarted MCP recovered no Canvas Plot result receipt"
            )
        if (
            recovered_canvas_result.get("replayed") is not True
            or recovered_canvas_result.get("applied_revision")
            != applied_canvas_revision
            or recovered_canvas_result.get("changed") is not False
            or recovered_canvas_result.get("affected_node_ids") != []
            or recovered_canvas_result.get("affected_link_ids") != []
            or recovered_canvas_result.get("affected_frame_ids") != []
            or recovered_canvas_result.get("created_node_id") is not None
            or recovered_canvas_result.get("created_link_id") is not None
            or recovered_canvas_result.get("created_frame_id") is not None
        ):
            raise RuntimeError(
                "restarted MCP Canvas Plot receipt was not a non-mutating replay"
            )
        if recovered_canvas_result.get("canvas_plot") != restarted_canvas_plot:
            raise RuntimeError(
                "restarted MCP Canvas receipt did not return the current board"
            )

        restarted_knowledge_graph = _structured(
            await session.call_tool("logosforge_get_knowledge_graph", {}),
            "restarted MCP Knowledge Graph persistence read",
        )
        if restarted_knowledge_graph != expected_knowledge_graph:
            raise RuntimeError(
                "restarted MCP did not read the persisted Knowledge Graph review"
            )
        expected_hidden_edges = expected_knowledge_graph.get("hidden_edges")
        if (
            not isinstance(expected_hidden_edges, list)
            or len(expected_hidden_edges) != 1
            or not isinstance(expected_hidden_edges[0], dict)
        ):
            raise RuntimeError(
                "packaged Knowledge Graph did not retain exactly one hidden edge"
            )
        expected_graph_identity = {
            key: expected_hidden_edges[0].get(key)
            for key in ("source", "target", "edge_type")
        }
        recovered_graph = _structured(
            await session.call_tool(
                "logosforge_get_proposal",
                {"proposal_id": graph_proposal_id},
            ),
            "restarted MCP durable Knowledge Graph receipt recovery",
        )
        recovered_graph_receipt = recovered_graph.get("receipt")
        if (
            recovered_graph.get("state") != "applied"
            or recovered_graph.get("recovered_from_core") is not True
            or recovered_graph.get("request") is not None
            or not isinstance(recovered_graph_receipt, dict)
            or recovered_graph_receipt.get("project_id") != project_id
            or recovered_graph_receipt.get("command_kind") != "hide_edge"
            or recovered_graph_receipt.get("applied_revision")
            != applied_graph_revision
            or recovered_graph_receipt.get("original_changed") is not True
            or recovered_graph_receipt.get("original_affected_edge")
            != expected_graph_identity
        ):
            raise RuntimeError(
                "restarted MCP returned the wrong Knowledge Graph receipt"
            )
        recovered_graph_result = recovered_graph.get("result")
        if (
            not isinstance(recovered_graph_result, dict)
            or recovered_graph_result.get("replayed") is not True
            or recovered_graph_result.get("applied_revision")
            != applied_graph_revision
            or recovered_graph_result.get("changed") is not False
            or recovered_graph_result.get("affected_edge")
            != expected_graph_identity
            or recovered_graph_result.get("knowledge_graph")
            != restarted_knowledge_graph
        ):
            raise RuntimeError(
                "restarted MCP Knowledge Graph receipt was not a non-mutating replay"
            )

        restarted_continuity = _structured(
            await session.call_tool(
                "logosforge_get_story_diagnostics", {"report": "continuity"},
            ),
            "restarted MCP Continuity persistence read",
        )
        if restarted_continuity != expected_continuity:
            raise RuntimeError(
                "restarted MCP did not read the persisted Continuity review"
            )
        expected_issue = next(
            (
                issue for issue in expected_continuity.get("issues", [])
                if isinstance(issue, dict) and issue.get("id") == continuity_issue_id
            ),
            None,
        )
        if (
            not isinstance(expected_issue, dict)
            or expected_issue.get("status") != "resolved"
        ):
            raise RuntimeError(
                "packaged Continuity did not retain the reviewed issue status"
            )
        recovered_continuity = _structured(
            await session.call_tool(
                "logosforge_get_proposal",
                {"proposal_id": continuity_proposal_id},
            ),
            "restarted MCP durable Continuity receipt recovery",
        )
        recovered_continuity_receipt = recovered_continuity.get("receipt")
        if (
            recovered_continuity.get("state") != "applied"
            or recovered_continuity.get("recovered_from_core") is not True
            or recovered_continuity.get("request") is not None
            or not isinstance(recovered_continuity_receipt, dict)
            or recovered_continuity_receipt.get("project_id") != project_id
            or recovered_continuity_receipt.get("command_kind") != "resolve_issue"
            or recovered_continuity_receipt.get("applied_revision")
            != applied_continuity_revision
            or recovered_continuity_receipt.get("original_changed") is not True
            or recovered_continuity_receipt.get("original_affected_issue_id")
            != continuity_issue_id
            or recovered_continuity_receipt.get("expected_issue_fingerprint")
            != expected_issue.get("review_fingerprint")
            or recovered_continuity_receipt.get("previous_status") != "open"
            or recovered_continuity_receipt.get("status") != "resolved"
        ):
            raise RuntimeError(
                "restarted MCP returned the wrong Continuity receipt"
            )
        recovered_continuity_result = recovered_continuity.get("result")
        if (
            not isinstance(recovered_continuity_result, dict)
            or recovered_continuity_result.get("replayed") is not True
            or recovered_continuity_result.get("applied_revision")
            != applied_continuity_revision
            or recovered_continuity_result.get("changed") is not False
            or recovered_continuity_result.get("affected_issue_id")
            != continuity_issue_id
            or recovered_continuity_result.get("previous_status") != "open"
            or recovered_continuity_result.get("status") != "resolved"
            or recovered_continuity_result.get("continuity")
            != restarted_continuity
        ):
            raise RuntimeError(
                "restarted MCP Continuity receipt was not a non-mutating replay"
            )


def _windows_process_is_alive(pid: int) -> bool:
    """Query process state without sending a signal on Windows."""
    from ctypes import wintypes

    process_query_limited_information = 0x1000
    still_active = 259
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, wintypes.LPDWORD]
    kernel32.GetExitCodeProcess.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    handle = kernel32.OpenProcess(process_query_limited_information, False, pid)
    if not handle:
        return False
    try:
        exit_code = wintypes.DWORD()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
            return False
        return exit_code.value == still_active
    finally:
        kernel32.CloseHandle(handle)


def _process_is_alive(pid: int | None) -> bool:
    if not pid or pid <= 0 or pid > 0xFFFFFFFF:
        return False
    if os.name == "nt":
        return _windows_process_is_alive(pid)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _stop_process_tree(
    process: subprocess.Popen,
    app_pid: int | None,
    core_pid: int | None,
) -> None:
    if process.poll() is None:
        if os.name == "nt":
            subprocess.run(
                ["taskkill.exe", "/PID", str(process.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        else:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            if os.name == "nt":
                process.kill()
            else:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            process.wait(timeout=5)
    owned_pids = {pid for pid in (app_pid, core_pid) if pid and pid > 0}
    if os.name == "nt":
        for pid in owned_pids:
            subprocess.run(
                ["taskkill.exe", "/PID", str(pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        return

    # AppImage/xvfb wrappers can exit before Electron and its managed core have
    # completely drained. The descriptor gives us the exact owned PIDs, so
    # terminate and verify them instead of relying only on the wrapper group.
    for pid in owned_pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and any(
        _process_is_alive(pid) for pid in owned_pids
    ):
        time.sleep(0.1)
    for pid in owned_pids:
        if _process_is_alive(pid):
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass


def _exercise_codex(
    codex_command: str,
    mcp_command: Path,
    descriptor_path: Path,
    work: Path,
    project_id: int,
    comment_id: int,
    comment_revision: str,
) -> None:
    output_path = work / "codex-result.txt"
    prompt = (
        "Use only the logosforge MCP server. Call logosforge_select_project with "
        f"project_id={project_id}, then call logosforge_list_comments exactly once. "
        "Do not use shell commands or files. Reply with exactly PACKAGED_MCP_CODEX_OK "
        f"only if the result contains comment id {comment_id} with revision "
        f"{comment_revision}; otherwise report the failure."
    )
    command = [
        codex_command,
        "exec",
        "--ignore-user-config",
        "--ephemeral",
        "--skip-git-repo-check",
        "--sandbox", "read-only",
        "--output-last-message", str(output_path),
        "-c", f"mcp_servers.logosforge.command={json.dumps(str(mcp_command))}",
        "-c", "mcp_servers.logosforge.args=[]",
        "-c", "mcp_servers.logosforge.required=true",
        "-c", (
            "mcp_servers.logosforge.env.LOGOSFORGE_MCP_CONNECTION_FILE="
            f"{json.dumps(str(descriptor_path))}"
        ),
        "-c", "mcp_servers.logosforge.env.LOGOSFORGE_MCP_ALLOW_WRITES=\"0\"",
        prompt,
    ]
    result = subprocess.run(
        command,
        cwd=work,
        env=os.environ.copy(),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=240,
        check=False,
    )
    final = output_path.read_text(encoding="utf-8", errors="replace") if output_path.exists() else ""
    if result.returncode != 0 or final.strip() != "PACKAGED_MCP_CODEX_OK":
        raise RuntimeError(
            "Local Codex did not validate the packaged MCP companion.\n"
            + result.stdout[-4000:]
            + "\nFinal response: "
            + final[-1000:]
        )
    print("Local Codex completed a read through the packaged MCP companion.")


def _smoke_app(app: Path, timeout: int, codex_command: str | None = None) -> None:
    app = app.resolve()
    if not app.is_file():
        raise RuntimeError(f"packaged application is missing: {app}")
    with tempfile.TemporaryDirectory(
        prefix="logosforge-packaged-mcp-",
        # The process tree is explicitly terminated below. Ignore a final
        # rmtree race from a just-exited AppImage/Chromium helper so a verified
        # package is not reported as broken solely by runner-temp cleanup.
        ignore_cleanup_errors=True,
    ) as temp:
        work = Path(temp).resolve()
        descriptor_path = work / "mcp-runtime-v1.json"
        installed_mcp_path = work / (
            "logosforge-mcp.exe" if os.name == "nt" else "logosforge-mcp"
        )
        port = _available_port()
        env = os.environ.copy()
        env.update(
            {
                "HOME": str(work),
                "USERPROFILE": str(work),
                "APPDATA": str(work / "appdata"),
                "LOCALAPPDATA": str(work / "local-appdata"),
                "XDG_CONFIG_HOME": str(work / "config"),
                "LOGOSFORGE_PORT": str(port),
                "LOGOSFORGE_MCP_CONNECTION_FILE": str(descriptor_path),
                "LOGOSFORGE_MCP_LAUNCHER_PATH": str(installed_mcp_path),
                "LOGOSFORGE_VOICE_MODEL": "",
                "LOGOSFORGE_MCP_ALLOW_WRITES": "0",
                "APPIMAGE_EXTRACT_AND_RUN": "1",
                "ELECTRON_ENABLE_LOGGING": "1",
            }
        )
        log_path = work / "app.log"
        args = [str(app), "--disable-gpu", f"--user-data-dir={work / 'electron-user-data'}"]
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
        process: subprocess.Popen | None = None
        app_pid: int | None = None
        core_pid: int | None = None
        try:
            with log_path.open("wb") as log:
                process = subprocess.Popen(
                    args,
                    cwd=app.parent,
                    env=env,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    creationflags=creationflags,
                    start_new_session=os.name != "nt",
                )
                deadline = time.monotonic() + timeout
                descriptor = None
                while time.monotonic() < deadline:
                    if process.poll() is not None:
                        break
                    try:
                        candidate = json.loads(
                            descriptor_path.read_text(encoding="utf-8")
                        )
                    except (FileNotFoundError, OSError, json.JSONDecodeError):
                        time.sleep(0.5)
                        continue
                    if not isinstance(candidate, dict):
                        time.sleep(0.5)
                        continue
                    descriptor = candidate
                    if descriptor.get("schema_version") == 1:
                        break
                    descriptor = None
                    time.sleep(0.5)
                if descriptor is None:
                    raise RuntimeError(
                        f"packaged app did not publish its MCP descriptor (exit={process.poll()})"
                    )
                base_url, auth_token, nonce, app_pid, core_pid = _validate_descriptor(
                    descriptor, port,
                )
                if not _process_is_alive(app_pid) or not _process_is_alive(core_pid):
                    raise RuntimeError("packaged app MCP descriptor names a stale process")
                with urllib.request.urlopen(
                    f"{base_url}/api/health", timeout=3,
                ) as response:
                    health = json.load(response)
                if (
                    health.get("service") != "logosforge-api"
                    or health.get("mode") != "desktop"
                    or health.get("instance_nonce") != nonce
                ):
                    raise RuntimeError("packaged app/core identity does not match its MCP descriptor")
                if not installed_mcp_path.is_file():
                    raise RuntimeError(
                        f"packaged app did not install its MCP companion: {installed_mcp_path}"
                    )
                project_id, comment_id, comment_revision = _seed_comment(
                    base_url, auth_token,
                )
                writable_mcp_env = env.copy()
                writable_mcp_env["LOGOSFORGE_MCP_ALLOW_WRITES"] = "1"
                (
                    final_comment_revision,
                    timeline_proposal_id,
                    applied_timeline_revision,
                    expected_timeline_link_id,
                    applied_timeline,
                    canvas_proposal_id,
                    applied_canvas_revision,
                    applied_canvas_plot,
                    graph_proposal_id,
                    applied_graph_revision,
                    applied_knowledge_graph,
                    continuity_proposal_id,
                    applied_continuity_revision,
                    applied_continuity,
                    continuity_issue_id,
                ) = asyncio.run(
                    asyncio.wait_for(
                        _exercise_installed_mcp(
                            installed_mcp_path,
                            [],
                            writable_mcp_env,
                            project_id,
                            comment_id,
                            comment_revision,
                        ),
                        timeout=90,
                    )
                )
                asyncio.run(
                    asyncio.wait_for(
                        _recover_installed_command_receipts(
                            installed_mcp_path,
                            [],
                            env,
                            project_id,
                            timeline_proposal_id,
                            applied_timeline_revision,
                            expected_timeline_link_id,
                            applied_timeline,
                            canvas_proposal_id,
                            applied_canvas_revision,
                            applied_canvas_plot,
                            graph_proposal_id,
                            applied_graph_revision,
                            applied_knowledge_graph,
                            continuity_proposal_id,
                            applied_continuity_revision,
                            applied_continuity,
                            continuity_issue_id,
                        ),
                        timeout=20,
                    )
                )
                if codex_command:
                    _exercise_codex(
                        codex_command,
                        installed_mcp_path,
                        descriptor_path,
                        work,
                        project_id,
                        comment_id,
                        final_comment_revision,
                    )
        except (urllib.error.URLError, OSError, RuntimeError):
            if log_path.exists():
                print(log_path.read_text(encoding="utf-8", errors="replace")[-4000:])
            raise
        finally:
            if process is not None:
                _stop_process_tree(process, app_pid, core_pid)
        print(
            "Packaged Pro published a verified descriptor, advertised 46 MCP tools "
            "including canonical project search plus revisioned Timeline, Canvas "
            "Plot, Knowledge Graph, and Semantic Continuity orchestration; applied all "
            "four transactional surfaces plus Timeline relationship and structure-link "
            "CRUD plus reply and resolution proposals; recovered their durable receipts "
            "with exact relationship IDs after a companion restart; and rejected stale "
            "and replayed applies."
        )


def smoke(package: Path, timeout: int, codex_command: str | None = None) -> None:
    package = package.resolve()
    if not package.is_file():
        raise RuntimeError(f"packaged application is missing: {package}")
    if package.suffix.lower() != ".dmg":
        _smoke_app(package, timeout, codex_command)
        return
    if sys.platform != "darwin":
        raise RuntimeError("A DMG runtime smoke requires macOS.")
    with tempfile.TemporaryDirectory(prefix="logosforge-mcp-dmg-") as mount:
        mount_path = Path(mount).resolve()
        subprocess.run(
            [
                "hdiutil", "attach", str(package), "-nobrowse", "-readonly",
                "-mountpoint", str(mount_path),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
        )
        try:
            app = mount_path / "LogosForge Pro.app" / "Contents" / "MacOS" / "LogosForge Pro"
            _smoke_app(app, timeout, codex_command)
        finally:
            subprocess.run(
                ["hdiutil", "detach", str(mount_path), "-force"],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("app_executable", type=Path)
    parser.add_argument("--timeout", type=int, default=90)
    parser.add_argument("--codex-command")
    args = parser.parse_args()
    smoke(args.app_executable, args.timeout, args.codex_command)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
