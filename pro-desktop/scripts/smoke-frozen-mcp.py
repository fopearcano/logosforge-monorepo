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
        if len(listed.tools) != 38:
            raise RuntimeError(f"expected 38 MCP tools, received {len(listed.tools)}")
        tool_names = {tool.name for tool in listed.tools}
        expected_comment_tools = {
            "logosforge_list_comments",
            "logosforge_propose_comment_reply",
            "logosforge_propose_comment_resolution",
        }
        missing_comment_tools = expected_comment_tools - tool_names
        if missing_comment_tools:
            raise RuntimeError(
                "missing Phase 5C MCP tools: "
                + ", ".join(sorted(missing_comment_tools))
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
            "Frozen LogosForge MCP initialized, advertised 38 tools including the "
            "Phase 5C comment tools, read a seeded thread, and created both "
            "non-mutating comment proposal types."
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
