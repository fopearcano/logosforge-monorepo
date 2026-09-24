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
import urllib.request
from pathlib import Path

import mcp
from mcp.client.stdio import stdio_client


def _available_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


async def _exercise_installed_mcp(
    command: Path,
    command_args: list[str],
    env: dict[str, str],
) -> None:
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
        if len(listed.tools) != 35:
            raise RuntimeError(f"expected 35 MCP tools, received {len(listed.tools)}")
        result = await session.call_tool("logosforge_list_projects", {})
        if result.isError:
            raise RuntimeError("installed MCP gateway could not complete an authenticated read")
        structured = getattr(result, "structuredContent", None)
        if structured is None:
            structured = getattr(result, "structured_content", None)
        if not isinstance(structured, dict) or structured.get("ok") is not True:
            raise RuntimeError("installed MCP gateway returned an invalid result envelope")


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
) -> None:
    output_path = work / "codex-result.txt"
    prompt = (
        "Use the logosforge MCP server and call logosforge_list_projects exactly once. "
        "Do not use shell commands or files. Reply with exactly PACKAGED_MCP_CODEX_OK "
        "if the tool succeeds with ok=true; otherwise report the failure."
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
                app_pid = descriptor.get("app_pid")
                if not isinstance(app_pid, int) or app_pid <= 0:
                    raise RuntimeError("packaged app published an invalid application process id")
                core_pid = descriptor.get("core_pid")
                if not isinstance(core_pid, int) or core_pid <= 0:
                    raise RuntimeError("packaged app published an invalid core process id")
                with urllib.request.urlopen(
                    f"http://127.0.0.1:{port}/api/health", timeout=3,
                ) as response:
                    health = json.load(response)
                if (
                    health.get("service") != "logosforge-api"
                    or health.get("mode") != "desktop"
                    or health.get("instance_nonce") != descriptor.get("instance_nonce")
                ):
                    raise RuntimeError("packaged app/core identity does not match its MCP descriptor")
                if not installed_mcp_path.is_file():
                    raise RuntimeError(
                        f"packaged app did not install its MCP companion: {installed_mcp_path}"
                    )
                asyncio.run(
                    asyncio.wait_for(
                        _exercise_installed_mcp(installed_mcp_path, [], env), timeout=45,
                    )
                )
                if codex_command:
                    _exercise_codex(
                        codex_command, installed_mcp_path, descriptor_path, work,
                    )
        except (urllib.error.URLError, OSError, RuntimeError):
            if log_path.exists():
                print(log_path.read_text(encoding="utf-8", errors="replace")[-4000:])
            raise
        finally:
            if process is not None:
                _stop_process_tree(process, app_pid, core_pid)
        print("Packaged Pro published a verified descriptor and served an authenticated MCP read.")


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
