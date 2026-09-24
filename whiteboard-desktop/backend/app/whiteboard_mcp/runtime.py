"""Secure discovery of a running LogosForge Whiteboard backend.

The Electron application publishes a private, per-user descriptor only after
its nonce-bound backend health check succeeds.  The MCP process reads that
descriptor so the backend bearer token never appears in Codex configuration or
on a process command line.
"""

from __future__ import annotations

import ctypes
import json
import os
import stat
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

MCP_RUNTIME_FILENAME = "mcp-runtime-v1.json"
MCP_RUNTIME_SCHEMA_VERSION = 1
CONNECTION_FILE_ENV = "LOGOSFORGE_WHITEBOARD_MCP_CONNECTION_FILE"
MAX_DESCRIPTOR_BYTES = 16 * 1024
MAX_HEALTH_BYTES = 64 * 1024


class RuntimeDescriptorError(RuntimeError):
    """The Whiteboard runtime descriptor is absent, unsafe, stale, or invalid."""


@dataclass(frozen=True)
class RuntimeDescriptor:
    base_url: str
    auth_token: str = field(repr=False)
    instance_nonce: str
    app_pid: int
    backend_pid: int
    created_at: str


def default_runtime_path() -> Path:
    """Match Electron's default ``app.getPath('userData')`` for Whiteboard."""
    home = Path.home()
    if sys.platform == "win32":
        config_root = Path(os.environ.get("APPDATA", home / "AppData" / "Roaming"))
    elif sys.platform == "darwin":
        config_root = home / "Library" / "Application Support"
    else:
        config_root = Path(os.environ.get("XDG_CONFIG_HOME", home / ".config"))
    return config_root / "LogosForge Whiteboard" / MCP_RUNTIME_FILENAME


def resolve_runtime_descriptor_path(
    user_data_dir: str | os.PathLike[str] | None = None,
    *,
    environ: Mapping[str, str] | None = None,
) -> Path:
    """Resolve the explicit Whiteboard descriptor override or product default."""
    env = os.environ if environ is None else environ
    explicit = env.get(CONNECTION_FILE_ENV, "").strip()
    if explicit:
        override = Path(explicit)
        if not override.is_absolute() or override.name != MCP_RUNTIME_FILENAME:
            raise RuntimeDescriptorError(
                "The Whiteboard MCP connection-file override must be an absolute "
                f"{MCP_RUNTIME_FILENAME} path."
            )
        # Keep the logical path intact. Electron uses the same absolute string
        # and atomically replaces the final path rather than following a final
        # symlink, so resolving it here would make the two processes disagree.
        return override
    if user_data_dir is not None:
        return Path(user_data_dir).expanduser().resolve() / MCP_RUNTIME_FILENAME
    return default_runtime_path().resolve()


def _windows_process_is_alive(pid: int) -> bool:
    """Query process state without signalling the process on Windows."""
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
        exit_code = ctypes.c_ulong()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
            return False
        return exit_code.value == still_active
    finally:
        kernel32.CloseHandle(handle)


def process_is_alive(pid: int) -> bool:
    if pid <= 0 or pid > 0xFFFFFFFF:
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


def _read_private_json(path: Path) -> dict:
    if not path.is_absolute():
        raise RuntimeDescriptorError("The Whiteboard MCP descriptor path must be absolute.")
    try:
        before = path.lstat()
    except FileNotFoundError as exc:
        raise RuntimeDescriptorError(
            "LogosForge Whiteboard is not running or has not finished starting."
        ) from exc
    except OSError as exc:
        raise RuntimeDescriptorError("The Whiteboard MCP descriptor cannot be inspected.") from exc
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
        raise RuntimeDescriptorError("The Whiteboard MCP descriptor must be a regular file.")
    if before.st_size <= 0 or before.st_size > MAX_DESCRIPTOR_BYTES:
        raise RuntimeDescriptorError("The Whiteboard MCP descriptor has an invalid size.")
    if os.name != "nt":
        if before.st_mode & 0o077:
            raise RuntimeDescriptorError(
                "The Whiteboard MCP descriptor is not private (expected mode 0600)."
            )
        getuid = getattr(os, "getuid", None)
        if getuid is not None and before.st_uid != getuid():
            raise RuntimeDescriptorError("The Whiteboard MCP descriptor belongs to another user.")

    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise RuntimeDescriptorError(
            "The Whiteboard MCP descriptor cannot be opened safely."
        ) from exc
    try:
        opened = os.fstat(fd)
        if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
            raise RuntimeDescriptorError("The Whiteboard MCP descriptor changed while opening it.")
        chunks: list[bytes] = []
        remaining = MAX_DESCRIPTOR_BYTES + 1
        while remaining > 0:
            chunk = os.read(fd, remaining)
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
    finally:
        os.close(fd)
    if len(raw) > MAX_DESCRIPTOR_BYTES:
        raise RuntimeDescriptorError("The Whiteboard MCP descriptor is too large.")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise RuntimeDescriptorError("The Whiteboard MCP descriptor is not valid JSON.") from exc
    if not isinstance(payload, dict):
        raise RuntimeDescriptorError("The Whiteboard MCP descriptor must contain a JSON object.")
    return payload


def _validated_loopback_url(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise RuntimeDescriptorError("The Whiteboard MCP descriptor has no API URL.")
    parsed = urllib.parse.urlparse(value)
    if (
        parsed.scheme != "http"
        or (parsed.hostname or "").lower() not in {"127.0.0.1", "localhost", "::1"}
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        raise RuntimeDescriptorError("The Whiteboard API URL must be plain HTTP on loopback.")
    try:
        port = parsed.port
    except ValueError as exc:
        raise RuntimeDescriptorError("The Whiteboard API URL has an invalid port.") from exc
    if port is None or not 1 <= port <= 65535:
        raise RuntimeDescriptorError("The Whiteboard API URL must include a valid port.")
    return value.rstrip("/")


def load_runtime_descriptor(
    path: str | os.PathLike[str],
    *,
    process_alive: Callable[[int], bool] = process_is_alive,
) -> RuntimeDescriptor:
    payload = _read_private_json(Path(path).expanduser())
    if payload.get("schema_version") != MCP_RUNTIME_SCHEMA_VERSION:
        raise RuntimeDescriptorError("The Whiteboard MCP descriptor version is unsupported.")

    def required_text(name: str, minimum: int) -> str:
        value = payload.get(name)
        if not isinstance(value, str) or value != value.strip() or len(value) < minimum:
            raise RuntimeDescriptorError(
                f"The Whiteboard MCP descriptor has an invalid {name}."
            )
        return value

    def required_pid(name: str) -> int:
        value = payload.get(name)
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise RuntimeDescriptorError(
                f"The Whiteboard MCP descriptor has an invalid {name}."
            )
        return value

    descriptor = RuntimeDescriptor(
        base_url=_validated_loopback_url(payload.get("base_url")),
        auth_token=required_text("auth_token", 32),
        instance_nonce=required_text("instance_nonce", 16),
        app_pid=required_pid("app_pid"),
        backend_pid=required_pid("backend_pid"),
        created_at=required_text("created_at", 10),
    )
    try:
        created_at = datetime.fromisoformat(descriptor.created_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise RuntimeDescriptorError(
            "The Whiteboard MCP descriptor has an invalid created_at."
        ) from exc
    if created_at.tzinfo is None or created_at.utcoffset() != timedelta(0):
        raise RuntimeDescriptorError("The Whiteboard MCP descriptor created_at must be UTC.")
    if not process_alive(descriptor.app_pid):
        raise RuntimeDescriptorError(
            "The runtime descriptor is stale: LogosForge Whiteboard is not running."
        )
    if not process_alive(descriptor.backend_pid):
        raise RuntimeDescriptorError(
            "The runtime descriptor is stale: the Whiteboard backend is not running."
        )
    return descriptor


def verify_runtime_descriptor(
    descriptor: RuntimeDescriptor,
    *,
    timeout: float = 3.0,
    urlopen: Callable = urllib.request.urlopen,
) -> RuntimeDescriptor:
    request = urllib.request.Request(
        f"{descriptor.base_url}/health",
        headers={"Accept": "application/json", "User-Agent": "LogosForge-Whiteboard-MCP"},
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read(MAX_HEALTH_BYTES + 1)
    except (urllib.error.URLError, OSError):
        raise RuntimeDescriptorError("The packaged Whiteboard backend is unreachable.") from None
    if len(raw) > MAX_HEALTH_BYTES:
        raise RuntimeDescriptorError("The Whiteboard backend returned an oversized health response.")
    try:
        health = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise RuntimeDescriptorError("The Whiteboard backend returned invalid health data.") from exc
    if not isinstance(health, dict) or any(
        (
            health.get("status") != "ok",
            health.get("service") != "logosforge-whiteboard-backend",
            health.get("instance_nonce") != descriptor.instance_nonce,
        )
    ):
        raise RuntimeDescriptorError(
            "The Whiteboard backend identity or nonce is stale and does not match the application."
        )
    return descriptor


def load_runtime_connection(
    path: str | os.PathLike[str],
    *,
    timeout: float = 3.0,
    is_process_alive: Callable[[int], bool] = process_is_alive,
) -> RuntimeDescriptor:
    descriptor = load_runtime_descriptor(path, process_alive=is_process_alive)
    return verify_runtime_descriptor(descriptor, timeout=timeout)
