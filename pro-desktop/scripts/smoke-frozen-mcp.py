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


async def _exercise_mcp(
    executable: Path,
    descriptor: Path,
    arguments: list[str],
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
        if len(listed.tools) != 35:
            raise RuntimeError(f"expected 35 MCP tools, received {len(listed.tools)}")
        result = await session.call_tool("logosforge_list_projects", {})
        if result.isError:
            raise RuntimeError("authenticated MCP project read failed")
        structured = getattr(result, "structuredContent", None)
        if structured is None:
            structured = getattr(result, "structured_content", None)
        if not isinstance(structured, dict) or structured.get("ok") is not True:
            raise RuntimeError("MCP read did not return the structured success envelope")


def smoke(executable: Path, mcp_executable: Path | None = None) -> None:
    executable = executable.resolve()
    if not executable.is_file():
        raise RuntimeError(f"frozen core executable is missing: {executable}")
    mcp_executable = (mcp_executable or executable).resolve()
    if not mcp_executable.is_file():
        raise RuntimeError(f"frozen MCP executable is missing: {mcp_executable}")
    mcp_arguments = [] if mcp_executable != executable else ["--mcp"]
    with tempfile.TemporaryDirectory(prefix="logosforge-frozen-mcp-") as temp:
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
                        _exercise_mcp(mcp_executable, descriptor_path, mcp_arguments),
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
        print("Frozen LogosForge MCP initialized, advertised 35 tools, and completed an authenticated read.")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("core_executable", type=Path)
    parser.add_argument("--mcp-executable", type=Path)
    args = parser.parse_args()
    smoke(args.core_executable, args.mcp_executable)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
