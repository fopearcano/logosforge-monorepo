"""End-to-end smoke for a packaged LogosForge Whiteboard MCP bridge.

The input is the unpacked application executable on Windows, the AppImage on
Linux, or the DMG on macOS.  The smoke keeps every runtime artifact in an
isolated temporary directory and only terminates processes proven to belong to
the application process tree it launched.
"""

from __future__ import annotations

import argparse
import asyncio
import ctypes
import json
import os
import shutil
import signal
import socket
import stat
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import mcp
from mcp.client.stdio import stdio_client

EXPECTED_SERVER_NAME = "logosforge-whiteboard"
EXPECTED_TOOL_NAMES = frozenset(
    {
        "logosforge_whiteboard_get_capabilities",
        "logosforge_whiteboard_list_documents",
        "logosforge_whiteboard_select_document",
        "logosforge_whiteboard_get_current_document",
        "logosforge_whiteboard_get_document_snapshot",
        "logosforge_whiteboard_get_outline",
        "logosforge_whiteboard_get_comments",
        "logosforge_whiteboard_get_psyke",
        "logosforge_whiteboard_search",
    }
)
DESCRIPTOR_MAX_BYTES = 16 * 1024
HEALTH_MAX_BYTES = 64 * 1024


def _available_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def _structured(result: object) -> dict[str, Any] | None:
    value = getattr(result, "structuredContent", None)
    if value is None:
        value = getattr(result, "structured_content", None)
    return value if isinstance(value, dict) else None


async def _exercise_installed_mcp(command: Path, env: dict[str, str]) -> None:
    params = mcp.StdioServerParameters(
        command=str(command),
        args=[],
        cwd=str(command.parent),
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
        names = {tool.name for tool in listed.tools}
        if len(listed.tools) != len(EXPECTED_TOOL_NAMES) or names != EXPECTED_TOOL_NAMES:
            raise RuntimeError(
                "packaged Whiteboard MCP advertised an unexpected tool registry: "
                f"{sorted(names)!r}"
            )
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
        capabilities_result = (
            capabilities_value.get("result")
            if isinstance(capabilities_value, dict)
            else None
        )
        if (
            capabilities.isError
            or not capabilities_value
            or capabilities_value.get("ok") is not True
            or not isinstance(capabilities_result, dict)
            or capabilities_result.get("server") != EXPECTED_SERVER_NAME
            or capabilities_result.get("read_only") is not True
            or capabilities_result.get("writes_available") is not False
        ):
            raise RuntimeError("packaged Whiteboard MCP capabilities read failed")

        documents = await session.call_tool(
            "logosforge_whiteboard_list_documents", {"offset": 0, "limit": 10}
        )
        documents_value = _structured(documents)
        documents_result = (
            documents_value.get("result")
            if isinstance(documents_value, dict)
            else None
        )
        if (
            documents.isError
            or not documents_value
            or documents_value.get("ok") is not True
            or not isinstance(documents_result, dict)
            or not isinstance(documents_result.get("documents"), list)
        ):
            raise RuntimeError("authenticated Whiteboard document-list read failed")


def _process_is_alive(pid: int | None) -> bool:
    if not pid or pid <= 0:
        return False
    if os.name == "nt":
        from ctypes import wintypes

        query_limited_information = 0x1000
        still_active = 259
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, wintypes.LPDWORD]
        kernel32.GetExitCodeProcess.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel32.OpenProcess(query_limited_information, False, pid)
        if not handle:
            return False
        try:
            exit_code = wintypes.DWORD()
            return bool(kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))) and (
                exit_code.value == still_active
            )
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _windows_parent_map() -> dict[int, int]:
    """Return live process parentage using Toolhelp; called only on Windows."""
    from ctypes import wintypes

    class ProcessEntry32W(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.POINTER(wintypes.ULONG)),
            ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", wintypes.LONG),
            ("dwFlags", wintypes.DWORD),
            ("szExeFile", wintypes.WCHAR * 260),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessEntry32W)]
    kernel32.Process32FirstW.restype = wintypes.BOOL
    kernel32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessEntry32W)]
    kernel32.Process32NextW.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]

    snapshot = kernel32.CreateToolhelp32Snapshot(0x00000002, 0)
    invalid_handle = ctypes.c_void_p(-1).value
    if snapshot == invalid_handle:
        raise OSError(ctypes.get_last_error(), "CreateToolhelp32Snapshot failed")
    parents: dict[int, int] = {}
    try:
        entry = ProcessEntry32W()
        entry.dwSize = ctypes.sizeof(ProcessEntry32W)
        present = kernel32.Process32FirstW(snapshot, ctypes.byref(entry))
        while present:
            parents[int(entry.th32ProcessID)] = int(entry.th32ParentProcessID)
            present = kernel32.Process32NextW(snapshot, ctypes.byref(entry))
    finally:
        kernel32.CloseHandle(snapshot)
    return parents


def _is_descendant(pid: int, ancestor: int, parents: dict[int, int]) -> bool:
    current = pid
    seen: set[int] = set()
    while current > 0 and current not in seen:
        if current == ancestor:
            return True
        seen.add(current)
        current = parents.get(current, 0)
    return False


def _validate_owned_pids(
    process: subprocess.Popen[bytes], app_pid: int, backend_pid: int
) -> set[int]:
    candidates = {app_pid, backend_pid}
    if os.getpid() in candidates:
        raise RuntimeError("packaged app descriptor points at the smoke-test process")
    if any(not _process_is_alive(pid) for pid in candidates):
        raise RuntimeError("packaged app descriptor contains a process that is not alive")
    if os.name == "nt":
        parents = _windows_parent_map()
        if any(not _is_descendant(pid, process.pid, parents) for pid in candidates):
            raise RuntimeError("packaged app descriptor contains a process outside its owned tree")
    else:
        try:
            if any(os.getpgid(pid) != process.pid for pid in candidates):
                raise RuntimeError(
                    "packaged app descriptor contains a process outside its owned group"
                )
        except ProcessLookupError as exc:
            raise RuntimeError("a packaged app process exited during validation") from exc
    return candidates


def _stop_owned_process_tree(
    process: subprocess.Popen[bytes], owned_pids: set[int]
) -> None:
    if os.name == "nt":
        if process.poll() is None:
            subprocess.run(
                ["taskkill.exe", "/PID", str(process.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        # A wrapper may have exited before cleanup. These PIDs were accepted
        # only after proving they descended from our launch root.
        for pid in owned_pids:
            if _process_is_alive(pid):
                subprocess.run(
                    ["taskkill.exe", "/PID", str(pid), "/T", "/F"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                )
        return

    # start_new_session=True makes the launch PID the process-group id. This
    # covers AppImage/xvfb wrappers, Electron helpers, and the backend child.
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass

    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        try:
            os.killpg(process.pid, 0)
        except ProcessLookupError:
            break
        time.sleep(0.1)
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        # The group has been signalled already; use the Popen handle only for
        # the launch process, never a PID learned from untrusted state.
        process.kill()
        process.wait(timeout=5)


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        info = path.lstat()
        if (
            not stat.S_ISREG(info.st_mode)
            or stat.S_ISLNK(info.st_mode)
            or info.st_size <= 0
            or info.st_size > DESCRIPTOR_MAX_BYTES
        ):
            return None
        if os.name != "nt" and info.st_mode & 0o077:
            return None
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else None
    except (FileNotFoundError, OSError, UnicodeError, json.JSONDecodeError):
        return None


def _wait_for_descriptor(
    path: Path, process: subprocess.Popen[bytes], timeout: int
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        candidate = _read_json(path)
        if candidate is not None and candidate.get("schema_version") == 1:
            return candidate
        if process.poll() is not None:
            break
        time.sleep(0.5)
    raise RuntimeError(
        f"packaged app did not publish its MCP descriptor (exit={process.poll()})"
    )


def _validate_descriptor(
    descriptor: dict[str, Any], expected_port: int
) -> tuple[str, str, int, int]:
    if type(descriptor.get("schema_version")) is not int or descriptor["schema_version"] != 1:
        raise RuntimeError("packaged app published an unsupported MCP descriptor schema")
    base_url = descriptor.get("base_url")
    if not isinstance(base_url, str) or not base_url:
        raise RuntimeError("packaged app published an invalid backend URL")
    parsed = urllib.parse.urlparse(base_url)
    try:
        port = parsed.port
    except ValueError as exc:
        raise RuntimeError("packaged app published an invalid backend port") from exc
    if (
        parsed.scheme != "http"
        or (parsed.hostname or "").lower() not in {"127.0.0.1", "localhost", "::1"}
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
        or port != expected_port
    ):
        raise RuntimeError("packaged app MCP descriptor is not the expected loopback endpoint")

    auth_token = descriptor.get("auth_token")
    nonce = descriptor.get("instance_nonce")
    if (
        not isinstance(auth_token, str)
        or auth_token != auth_token.strip()
        or len(auth_token) < 32
    ):
        raise RuntimeError("packaged app published an invalid MCP bearer token")
    if not isinstance(nonce, str) or nonce != nonce.strip() or len(nonce) < 16:
        raise RuntimeError("packaged app published an invalid backend nonce")
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

    return base_url.rstrip("/"), nonce, required_pid("app_pid"), required_pid("backend_pid")


def _fetch_health(base_url: str) -> dict[str, Any]:
    request = urllib.request.Request(
        f"{base_url}/health",
        headers={"Accept": "application/json", "User-Agent": "Whiteboard-Packaged-MCP-Smoke"},
    )
    with urllib.request.urlopen(request, timeout=3) as response:
        raw = response.read(HEALTH_MAX_BYTES + 1)
    if len(raw) > HEALTH_MAX_BYTES:
        raise RuntimeError("packaged Whiteboard backend returned oversized health data")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("packaged Whiteboard backend returned invalid health data") from exc
    if not isinstance(value, dict):
        raise RuntimeError("packaged Whiteboard backend health response is not an object")
    return value


def _exercise_codex(
    codex_command: str,
    mcp_command: Path,
    descriptor_path: Path,
    work: Path,
) -> None:
    output_path = work / "codex-result.txt"
    prompt = (
        "Use the MCP server named logosforge-whiteboard. Call "
        "logosforge_whiteboard_get_capabilities once and "
        "logosforge_whiteboard_list_documents once. Do not use shell commands or files. "
        "Reply with exactly PACKAGED_WHITEBOARD_MCP_CODEX_OK only if both tools succeed "
        "with ok=true and the capabilities report read_only=true; otherwise report the failure."
    )
    command = [
        codex_command,
        "exec",
        "--ignore-user-config",
        "--ephemeral",
        "--skip-git-repo-check",
        "--sandbox",
        "read-only",
        "--output-last-message",
        str(output_path),
        "-c",
        f"mcp_servers.{EXPECTED_SERVER_NAME}.command={json.dumps(str(mcp_command))}",
        "-c",
        f"mcp_servers.{EXPECTED_SERVER_NAME}.args=[]",
        "-c",
        f"mcp_servers.{EXPECTED_SERVER_NAME}.required=true",
        "-c",
        (
            f"mcp_servers.{EXPECTED_SERVER_NAME}.env."
            "LOGOSFORGE_WHITEBOARD_MCP_CONNECTION_FILE="
            f"{json.dumps(str(descriptor_path))}"
        ),
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
    final = (
        output_path.read_text(encoding="utf-8", errors="replace")
        if output_path.exists()
        else ""
    )
    if result.returncode != 0 or final.strip() != "PACKAGED_WHITEBOARD_MCP_CODEX_OK":
        raise RuntimeError(
            "Local Codex did not validate the packaged Whiteboard MCP companion.\n"
            + result.stdout[-4000:]
            + "\nFinal response: "
            + final[-1000:]
        )
    print("Local Codex completed read-only reads through logosforge-whiteboard.")


def _launch_command(app: Path, user_data_dir: Path, env: dict[str, str]) -> list[str]:
    command = [str(app), "--disable-gpu", f"--user-data-dir={user_data_dir}"]
    if sys.platform.startswith("linux"):
        if not os.access(app, os.X_OK):
            raise RuntimeError(f"AppImage is not executable: {app}")
        getuid = getattr(os, "getuid", None)
        if getuid is not None and getuid() == 0:
            command.append("--no-sandbox")
        if not env.get("DISPLAY"):
            xvfb_run = shutil.which("xvfb-run")
            if not xvfb_run:
                raise RuntimeError(
                    "Linux packaged smoke requires DISPLAY or xvfb-run for Electron."
                )
            command = [xvfb_run, "-a", "--server-args=-screen 0 1280x1024x24", *command]
    return command


def _smoke_app(app: Path, timeout: int, codex_command: str | None = None) -> None:
    app = app.resolve()
    if not app.is_file():
        raise RuntimeError(f"packaged application is missing: {app}")
    with tempfile.TemporaryDirectory(
        prefix="logosforge-whiteboard-packaged-mcp-",
        ignore_cleanup_errors=True,
    ) as temp:
        work = Path(temp).resolve()
        descriptor_path = (work / "mcp-runtime-v1.json").resolve()
        installed_mcp_path = (
            work
            / (
                "logosforge-whiteboard-mcp.exe"
                if os.name == "nt"
                else "logosforge-whiteboard-mcp"
            )
        ).resolve()
        port = _available_port()
        env = os.environ.copy()
        env.update(
            {
                "HOME": str(work),
                "USERPROFILE": str(work),
                "APPDATA": str(work / "appdata"),
                "LOCALAPPDATA": str(work / "local-appdata"),
                "XDG_CONFIG_HOME": str(work / "config"),
                "LOGOSFORGE_DATA_DIR": str(work / "data"),
                "LOGOSFORGE_DB_PATH": str(work / "whiteboard.db"),
                "LOGOSFORGE_PORT": str(port),
                "LOGOSFORGE_WHITEBOARD_MCP_CONNECTION_FILE": str(descriptor_path),
                "LOGOSFORGE_WHITEBOARD_MCP_LAUNCHER_PATH": str(installed_mcp_path),
                "APPIMAGE_EXTRACT_AND_RUN": "1",
                "ELECTRON_ENABLE_LOGGING": "1",
            }
        )
        log_path = work / "app.log"
        command = _launch_command(app, work / "electron-user-data", env)
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
        process: subprocess.Popen[bytes] | None = None
        owned_pids: set[int] = set()
        try:
            with log_path.open("wb") as log:
                process = subprocess.Popen(
                    command,
                    cwd=app.parent,
                    env=env,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    creationflags=creationflags,
                    start_new_session=os.name != "nt",
                )
                descriptor = _wait_for_descriptor(descriptor_path, process, timeout)
                base_url, nonce, app_pid, backend_pid = _validate_descriptor(
                    descriptor, port
                )
                owned_pids = _validate_owned_pids(process, app_pid, backend_pid)

                health = _fetch_health(base_url)
                if (
                    health.get("status") != "ok"
                    or health.get("service") != "logosforge-whiteboard-backend"
                    or health.get("instance_nonce") != nonce
                ):
                    raise RuntimeError(
                        "packaged Whiteboard backend identity does not match its MCP descriptor"
                    )

                try:
                    installed_info = installed_mcp_path.lstat()
                except OSError as exc:
                    raise RuntimeError(
                        f"packaged app did not install its MCP companion: {installed_mcp_path}"
                    ) from exc
                if (
                    not stat.S_ISREG(installed_info.st_mode)
                    or stat.S_ISLNK(installed_info.st_mode)
                    or installed_info.st_size <= 0
                    or (os.name != "nt" and not os.access(installed_mcp_path, os.X_OK))
                ):
                    raise RuntimeError("packaged app installed an invalid MCP companion")

                asyncio.run(
                    asyncio.wait_for(
                        _exercise_installed_mcp(installed_mcp_path, env), timeout=45
                    )
                )
                if codex_command:
                    _exercise_codex(
                        codex_command, installed_mcp_path, descriptor_path, work
                    )
        except Exception:
            if log_path.exists():
                print(log_path.read_text(encoding="utf-8", errors="replace")[-4000:])
            raise
        finally:
            if process is not None:
                _stop_owned_process_tree(process, owned_pids)
        print(
            "Packaged Whiteboard published a verified descriptor and served "
            "authenticated read-only MCP reads."
        )


def smoke(package: Path, timeout: int, codex_command: str | None = None) -> None:
    package = package.resolve()
    if not package.is_file():
        raise RuntimeError(f"packaged application is missing: {package}")
    if timeout <= 0:
        raise RuntimeError("timeout must be greater than zero")

    if sys.platform == "darwin":
        if package.suffix.lower() != ".dmg":
            raise RuntimeError("macOS packaged smoke expects a Whiteboard DMG.")
        with tempfile.TemporaryDirectory(prefix="logosforge-whiteboard-mcp-dmg-") as mount:
            mount_path = Path(mount).resolve()
            subprocess.run(
                [
                    "hdiutil",
                    "attach",
                    str(package),
                    "-nobrowse",
                    "-readonly",
                    "-mountpoint",
                    str(mount_path),
                ],
                check=True,
                stdout=subprocess.DEVNULL,
            )
            try:
                app = (
                    mount_path
                    / "LogosForge Whiteboard.app"
                    / "Contents"
                    / "MacOS"
                    / "LogosForge Whiteboard"
                )
                _smoke_app(app, timeout, codex_command)
            finally:
                subprocess.run(
                    ["hdiutil", "detach", str(mount_path), "-force"],
                    check=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
        return

    if package.suffix.lower() == ".dmg":
        raise RuntimeError("A DMG runtime smoke requires macOS.")
    if os.name == "nt" and package.suffix.lower() != ".exe":
        raise RuntimeError("Windows packaged smoke expects an unpacked .exe application.")
    if sys.platform.startswith("linux") and not package.name.lower().endswith(".appimage"):
        raise RuntimeError("Linux packaged smoke expects a Whiteboard AppImage.")
    _smoke_app(package, timeout, codex_command)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Launch a packaged Whiteboard application and validate its installed, "
            "read-only MCP companion end to end."
        )
    )
    parser.add_argument(
        "package",
        type=Path,
        help="Windows unpacked app executable, Linux AppImage, or macOS DMG",
    )
    parser.add_argument("--timeout", type=int, default=90)
    parser.add_argument(
        "--codex-command",
        help="optional local Codex executable for an additional MCP read validation",
    )
    args = parser.parse_args()
    smoke(args.package, args.timeout, args.codex_command)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
