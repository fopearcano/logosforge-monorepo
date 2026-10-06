"""Exercise the frozen core's API and packaged stdio MCP mode together."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import secrets
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import mcp
from mcp.client.stdio import stdio_client


def _available_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def _health(base_url: str) -> dict | None:
    try:
        with urllib.request.urlopen(f"{base_url}/api/health", timeout=2) as response:
            return json.load(response)
    except (urllib.error.URLError, OSError, json.JSONDecodeError):
        return None


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
        {"title": "Opening", "content": "Frozen comment anchor"},
    )
    _api_json(
        base_url,
        token,
        "POST",
        f"/api/projects/{project_id}/scenes",
        {"title": "Crossing", "content": "A second scene for graph review."},
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
                "to_offset": 6,
            },
            "quote": "Frozen",
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
        raise RuntimeError(f"{label} returned an invalid structured envelope")
    return structured["result"]


async def _exercise_mcp(
    executable: Path,
    descriptor: Path,
    arguments: list[str],
    project_id: int,
    comment_id: int,
    comment_revision: str,
) -> None:
    env = os.environ.copy()
    for name in ("LOGOSFORGE_API_URL", "LOGOSFORGE_API_TOKEN"):
        env.pop(name, None)
    env.update(
        {
            "LOGOSFORGE_MCP_CONNECTION_FILE": str(descriptor),
            "LOGOSFORGE_MCP_REQUIRE_CONNECTION": "1",
            "LOGOSFORGE_MCP_ALLOW_WRITES": "0",
        }
    )
    params = mcp.StdioServerParameters(
        command=str(executable),
        args=arguments,
        cwd=str(executable.parent),
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
        if len(listed.tools) != 45:
            raise RuntimeError(f"expected 45 MCP tools, received {len(listed.tools)}")
        tool_names = {tool.name for tool in listed.tools}
        expected_tools = {
            "logosforge_get_timeline",
            "logosforge_propose_timeline_command",
            "logosforge_get_canvas_plot",
            "logosforge_propose_canvas_plot_command",
            "logosforge_get_knowledge_graph",
            "logosforge_get_knowledge_graph_hidden_edges",
            "logosforge_propose_knowledge_graph_command",
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
            "authenticated MCP project read",
        )
        _structured(
            await session.call_tool(
                "logosforge_select_project", {"project_id": project_id},
            ),
            "MCP project selection",
        )
        timeline_before = _structured(
            await session.call_tool("logosforge_get_timeline", {}),
            "MCP Timeline read",
        )
        timeline_revision = timeline_before.get("revision")
        if not isinstance(timeline_revision, str) or len(timeline_revision) != 64:
            raise RuntimeError("MCP Timeline read returned no valid revision")
        timeline_proposal = _structured(
            await session.call_tool(
                "logosforge_propose_timeline_command",
                {
                    "command": {
                        "kind": "create_lane",
                        "expected_revision": timeline_revision,
                        "name": "Frozen MCP lane",
                        "color_label": "cyan",
                    },
                },
            ),
            "MCP Timeline proposal",
        )
        if timeline_proposal.get("state") != "pending":
            raise RuntimeError("MCP Timeline proposal was not left pending")
        if timeline_proposal.get("request") != {
            "method": "POST",
            "path": f"/api/projects/{project_id}/timeline/commands",
            "body": {
                "kind": "create_lane",
                "expected_revision": timeline_revision,
                "name": "Frozen MCP lane",
                "color_label": "cyan",
            },
        }:
            raise RuntimeError("MCP Timeline proposal did not store the exact command")
        timeline_after = _structured(
            await session.call_tool("logosforge_get_timeline", {}),
            "MCP post-proposal Timeline read",
        )
        if timeline_after != timeline_before:
            raise RuntimeError("creating a Timeline proposal mutated project data")
        canvas_before = _structured(
            await session.call_tool("logosforge_get_canvas_plot", {}),
            "MCP Canvas Plot read",
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
            raise RuntimeError("MCP Canvas Plot read returned an invalid empty snapshot")
        canvas_command = {
            "kind": "create_node",
            "expected_revision": canvas_revision,
            "title": "Frozen MCP Canvas node",
            "body": "Proposed through the frozen companion without mutation.",
            "x": 48.0,
            "y": 72.0,
            "width": 240.0,
            "height": 132.0,
            "color_label": "cyan",
            "group_label": "Frozen acceptance",
        }
        canvas_proposal = _structured(
            await session.call_tool(
                "logosforge_propose_canvas_plot_command",
                {"command": canvas_command},
            ),
            "MCP Canvas Plot proposal",
        )
        if canvas_proposal.get("state") != "pending":
            raise RuntimeError("MCP Canvas Plot proposal was not left pending")
        if canvas_proposal.get("request") != {
            "method": "POST",
            "path": f"/api/projects/{project_id}/canvas-plot/commands",
            "body": canvas_command,
        }:
            raise RuntimeError(
                "MCP Canvas Plot proposal did not store the exact command"
            )
        canvas_after = _structured(
            await session.call_tool("logosforge_get_canvas_plot", {}),
            "MCP post-proposal Canvas Plot read",
        )
        if canvas_after != canvas_before:
            raise RuntimeError("creating a Canvas Plot proposal mutated project data")
        graph_before = _structured(
            await session.call_tool("logosforge_get_knowledge_graph", {}),
            "MCP Knowledge Graph read",
        )
        graph_revision = graph_before.get("revision")
        graph_edges = graph_before.get("edges")
        if (
            not isinstance(graph_revision, str)
            or len(graph_revision) != 64
            or graph_before.get("project_id") != project_id
            or not isinstance(graph_edges, list)
        ):
            raise RuntimeError("MCP Knowledge Graph read returned an invalid map")
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
            raise RuntimeError("MCP Knowledge Graph read returned no reviewable edge")
        graph_command = {
            "kind": "hide_edge",
            "expected_revision": graph_revision,
            "source": inferred_edge["source"],
            "target": inferred_edge["target"],
            "edge_type": inferred_edge["edge_type"],
        }
        graph_proposal = _structured(
            await session.call_tool(
                "logosforge_propose_knowledge_graph_command",
                {"command": graph_command},
            ),
            "MCP Knowledge Graph proposal",
        )
        if graph_proposal.get("state") != "pending":
            raise RuntimeError("MCP Knowledge Graph proposal was not left pending")
        if graph_proposal.get("request") != {
            "method": "POST",
            "path": f"/api/projects/{project_id}/knowledge-graph/commands",
            "body": graph_command,
        }:
            raise RuntimeError(
                "MCP Knowledge Graph proposal did not store the exact command"
            )
        graph_after = _structured(
            await session.call_tool("logosforge_get_knowledge_graph", {}),
            "MCP post-proposal Knowledge Graph read",
        )
        if graph_after != graph_before:
            raise RuntimeError("creating a Knowledge Graph proposal mutated project data")
        search = _structured(
            await session.call_tool(
                "logosforge_search", {"query": "Inspect this packaged thread."},
            ),
            "MCP canonical project search",
        )
        search_match = next(
            (
                item for item in search.get("matches", [])
                if item.get("kind") == "comment" and item.get("id") == comment_id
            ),
            None,
        )
        if search_match is None:
            raise RuntimeError("MCP search did not return the seeded comment")
        if search_match.get("revision") != comment_revision:
            raise RuntimeError("MCP search returned the wrong comment revision")
        if search_match.get("resolved") is not False:
            raise RuntimeError("MCP search returned the wrong comment resolution state")
        comment_page = _structured(
            await session.call_tool(
                "logosforge_list_comments", {"include_resolved": True},
            ),
            "MCP comment read",
        )
        if [item.get("id") for item in comment_page.get("comments", [])] != [comment_id]:
            raise RuntimeError("MCP comment read did not return the seeded thread")
        if comment_page["comments"][0].get("revision") != comment_revision:
            raise RuntimeError("MCP comment read returned the wrong thread revision")
        _structured(
            await session.call_tool(
                "logosforge_propose_comment_reply",
                {
                    "comment_id": comment_id,
                    "expected_revision": comment_revision,
                    "body": "Packaged proposal smoke.",
                },
            ),
            "MCP comment reply proposal",
        )
        _structured(
            await session.call_tool(
                "logosforge_propose_comment_resolution",
                {
                    "comment_id": comment_id,
                    "expected_revision": comment_revision,
                    "resolved": True,
                },
            ),
            "MCP comment resolution proposal",
        )


def smoke(executable: Path, mcp_executable: Path | None = None) -> None:
    executable = executable.resolve()
    if not executable.is_file():
        raise RuntimeError(f"frozen core executable is missing: {executable}")
    mcp_executable = (mcp_executable or executable).resolve()
    if not mcp_executable.is_file():
        raise RuntimeError(f"frozen MCP executable is missing: {mcp_executable}")
    mcp_arguments = [] if mcp_executable != executable else ["--mcp"]
    with tempfile.TemporaryDirectory(
        prefix="logosforge-frozen-mcp-",
        # Windows can retain the just-closed SQLite WAL sidecars briefly after
        # the frozen process exits. Functional verification must not be
        # reported as failed solely by that temporary-directory cleanup race.
        ignore_cleanup_errors=True,
    ) as temp:
        work = Path(temp).resolve()
        port = _available_port()
        base_url = f"http://127.0.0.1:{port}"
        token = secrets.token_urlsafe(32)
        nonce = secrets.token_urlsafe(24)
        log_path = work / "core.log"
        descriptor_path = work / "mcp-runtime-v1.json"
        env = os.environ.copy()
        env.update({"API_AUTH_TOKEN": token, "API_INSTANCE_NONCE": nonce})
        command = [
            str(executable),
            "--host", "127.0.0.1",
            "--port", str(port),
            "--mode", "desktop",
            "--db", str(work / "logosforge.db"),
        ]
        process: subprocess.Popen | None = None
        try:
            with log_path.open("wb") as log:
                process = subprocess.Popen(
                    command,
                    cwd=executable.parent,
                    env=env,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                )
                health = None
                for _attempt in range(45):
                    if process.poll() is not None:
                        break
                    health = _health(base_url)
                    if health is not None:
                        break
                    time.sleep(1)
                if (
                    not health
                    or health.get("status") != "ok"
                    or health.get("service") != "logosforge-api"
                    or health.get("mode") != "desktop"
                    or health.get("instance_nonce") != nonce
                ):
                    raise RuntimeError(
                        f"frozen core did not present the expected identity (exit={process.poll()})"
                    )
                project_id, comment_id, comment_revision = _seed_comment(
                    base_url, token,
                )
                descriptor = {
                    "schema_version": 1,
                    "base_url": base_url,
                    "auth_token": token,
                    "instance_nonce": nonce,
                    "app_pid": os.getpid(),
                    "core_pid": process.pid,
                    "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                }
                descriptor_path.write_text(json.dumps(descriptor), encoding="utf-8")
                if os.name != "nt":
                    descriptor_path.chmod(0o600)
                asyncio.run(
                    asyncio.wait_for(
                        _exercise_mcp(
                            mcp_executable,
                            descriptor_path,
                            mcp_arguments,
                            project_id,
                            comment_id,
                            comment_revision,
                        ),
                        timeout=45,
                    )
                )
        except Exception:
            if log_path.exists():
                print(log_path.read_text(encoding="utf-8", errors="replace")[-4000:])
            raise
        finally:
            if process is not None and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=10)
        print(
            "Frozen LogosForge MCP initialized, advertised 45 tools, read and "
            "proposed against the revisioned Timeline, Canvas Plot, and Knowledge "
            "Graph without mutation, searched and read a seeded thread, and "
            "created both comment proposal types."
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("core_executable", type=Path)
    parser.add_argument("--mcp-executable", type=Path)
    args = parser.parse_args()
    smoke(args.core_executable, args.mcp_executable)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
