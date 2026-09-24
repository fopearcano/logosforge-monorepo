"""Exercise the frozen Whiteboard backend and MCP companion together.

Usage::

    python smoke-frozen-mcp.py <backend-executable> <mcp-executable>
"""

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

EXPECTED_SERVER_NAME = "logosforge-whiteboard"
EXPECTED_TOOL_COUNT = 9
TOOL_PREFIX = "logosforge_whiteboard_"


def _available_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def _health(base_url: str) -> dict | None:
    try:
        with urllib.request.urlopen(f"{base_url}/health", timeout=2) as response:
            value = json.load(response)
            return value if isinstance(value, dict) else None
    except (urllib.error.URLError, OSError, json.JSONDecodeError):
        return None


def _structured(result: object) -> dict | None:
    value = getattr(result, "structuredContent", None)
    if value is None:
        value = getattr(result, "structured_content", None)
    return value if isinstance(value, dict) else None


async def _exercise_mcp(executable: Path, descriptor: Path) -> None:
    env = os.environ.copy()
    env["LOGOSFORGE_WHITEBOARD_MCP_CONNECTION_FILE"] = str(descriptor)
    params = mcp.StdioServerParameters(
        command=str(executable),
        args=[],
        cwd=str(executable.parent),
        env=env,
    )
    async with (
        stdio_client(params) as streams,
        mcp.ClientSession(*streams) as session,
    ):
        initialized = await session.initialize()
        if initialized.serverInfo.name != EXPECTED_SERVER_NAME:
            raise RuntimeError(f"unexpected MCP server: {initialized.serverInfo.name!r}")
        listed = await session.list_tools()
        if len(listed.tools) != EXPECTED_TOOL_COUNT:
            raise RuntimeError(
                f"expected {EXPECTED_TOOL_COUNT} Whiteboard MCP tools, received {len(listed.tools)}"
            )
        if any(not tool.name.startswith(TOOL_PREFIX) for tool in listed.tools):
            raise RuntimeError("Whiteboard MCP advertised a tool outside its stable prefix")
        for tool in listed.tools:
            annotations = tool.annotations
            if not (
                annotations
                and annotations.readOnlyHint is True
                and annotations.destructiveHint is False
                and annotations.idempotentHint is True
                and annotations.openWorldHint is False
            ):
                raise RuntimeError(f"unsafe MCP annotations on {tool.name}")

        capabilities = await session.call_tool(
            "logosforge_whiteboard_get_capabilities", {}
        )
        capabilities_value = _structured(capabilities)
        if (
            capabilities.isError
            or not capabilities_value
            or capabilities_value.get("ok") is not True
            or capabilities_value.get("result", {}).get("read_only") is not True
        ):
            raise RuntimeError("Whiteboard MCP capabilities read failed")

        documents = await session.call_tool(
            "logosforge_whiteboard_list_documents", {"limit": 10}
        )
        documents_value = _structured(documents)
        if (
            documents.isError
            or not documents_value
            or documents_value.get("ok") is not True
            or not documents_value.get("result", {}).get("documents")
        ):
            raise RuntimeError("authenticated Whiteboard document read failed")


def smoke(backend_executable: Path, mcp_executable: Path) -> None:
    backend_executable = backend_executable.resolve()
    mcp_executable = mcp_executable.resolve()
    if not backend_executable.is_file():
        raise RuntimeError(f"frozen Whiteboard backend is missing: {backend_executable}")
    if not mcp_executable.is_file():
        raise RuntimeError(f"frozen Whiteboard MCP companion is missing: {mcp_executable}")

    with tempfile.TemporaryDirectory(prefix="logosforge-whiteboard-mcp-") as temp:
        work = Path(temp).resolve()
        port = _available_port()
        base_url = f"http://127.0.0.1:{port}"
        token = secrets.token_urlsafe(32)
        nonce = secrets.token_urlsafe(24)
        descriptor_path = work / "mcp-runtime-v1.json"
        log_path = work / "whiteboard-backend.log"
        env = os.environ.copy()
        env.update(
            {
                "HOME": str(work),
                "USERPROFILE": str(work),
                "LOGOSFORGE_DATA_DIR": str(work / "data"),
                "LOGOSFORGE_DB_PATH": str(work / "whiteboard.db"),
                "LOGOSFORGE_WHITEBOARD_AUTH_TOKEN": token,
                "LOGOSFORGE_WHITEBOARD_INSTANCE_NONCE": nonce,
            }
        )
        command = [
            str(backend_executable),
            "--host", "127.0.0.1",
            "--port", str(port),
        ]
        process: subprocess.Popen | None = None
        try:
            with log_path.open("wb") as log:
                process = subprocess.Popen(
                    command,
                    cwd=backend_executable.parent,
                    env=env,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                )
                health = None
                for _attempt in range(60):
                    if process.poll() is not None:
                        break
                    health = _health(base_url)
                    if health is not None:
                        break
                    time.sleep(1)
                if (
                    not health
                    or health.get("status") != "ok"
                    or health.get("service") != "logosforge-whiteboard-backend"
                    or health.get("instance_nonce") != nonce
                ):
                    raise RuntimeError(
                        "frozen Whiteboard backend did not present the expected identity "
                        f"(exit={process.poll()})"
                    )
                descriptor = {
                    "schema_version": 1,
                    "base_url": base_url,
                    "auth_token": token,
                    "instance_nonce": nonce,
                    "app_pid": os.getpid(),
                    "backend_pid": process.pid,
                    "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                }
                descriptor_path.write_text(json.dumps(descriptor), encoding="utf-8")
                if os.name != "nt":
                    descriptor_path.chmod(0o600)
                asyncio.run(
                    asyncio.wait_for(
                        _exercise_mcp(mcp_executable, descriptor_path),
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
        "Frozen Whiteboard MCP initialized, advertised 9 read-only tools, "
        "and completed an authenticated document read."
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("backend_executable", type=Path)
    parser.add_argument("mcp_executable", type=Path)
    args = parser.parse_args()
    smoke(args.backend_executable, args.mcp_executable)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
