"""End-to-end smoke for an installed/unpacked Pro application's MCP mode."""

from __future__ import annotations

import argparse
import asyncio
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
        {"title": "Opening", "content": "Packaged comment anchor"},
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
) -> str:
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
            "installed MCP authenticated read",
        )
        _structured(
            await session.call_tool(
                "logosforge_select_project", {"project_id": project_id},
            ),
            "installed MCP project selection",
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
        return resolved_revision


def _process_is_alive(pid: int | None) -> bool:
    if not pid or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except (OSError, ProcessLookupError):
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
                final_comment_revision = asyncio.run(
                    asyncio.wait_for(
                        _exercise_installed_mcp(
                            installed_mcp_path,
                            [],
                            writable_mcp_env,
                            project_id,
                            comment_id,
                            comment_revision,
                        ),
                        timeout=45,
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
            "Packaged Pro published a verified descriptor, advertised 38 MCP tools "
            "including the Phase 5C comment tools, applied revision-guarded reply "
            "and resolution proposals, and rejected stale and replayed applies."
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
