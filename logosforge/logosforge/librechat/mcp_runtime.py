"""Secure discovery of a running packaged LogosForge Pro core.

The Electron shell publishes a small, per-user descriptor only after the core
has answered its nonce-bound health check.  The packaged MCP entrypoint reads
that descriptor so credentials never need to be copied into Codex config or
placed on a command line.
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
MAX_DESCRIPTOR_BYTES = 16 * 1024
MAX_HEALTH_BYTES = 64 * 1024


class RuntimeDescriptorError(RuntimeError):
    """A packaged-runtime descriptor is absent, unsafe, stale, or invalid."""


@dataclass(frozen=True)
class RuntimeDescriptor:
    base_url: str
    auth_token: str = field(repr=False)
    instance_nonce: str
    app_pid: int
    core_pid: int
    created_at: str


def default_runtime_path() -> Path:
    """Match Electron's ``app.getPath('userData')`` for LogosForge Pro."""
    home = Path.home()
    if sys.platform == "win32":
        app_data = Path(os.environ.get("APPDATA", home / "AppData" / "Roaming"))
    elif sys.platform == "darwin":
        app_data = home / "Library" / "Application Support"
    else:
        app_data = Path(os.environ.get("XDG_CONFIG_HOME", home / ".config"))
    return app_data / "LogosForge Pro" / MCP_RUNTIME_FILENAME


def resolve_runtime_descriptor_path(
    user_data_dir: str | os.PathLike[str] | None = None,
    *,
    environ: Mapping[str, str] | None = None,
) -> Path:
    """Resolve an explicit descriptor path or the packaged-app default."""
    env = os.environ if environ is None else environ
    explicit = env.get("LOGOSFORGE_MCP_CONNECTION_FILE", "").strip()
    if explicit:
        return Path(explicit).expanduser().resolve()
    if user_data_dir is not None:
        return Path(user_data_dir).expanduser().resolve() / MCP_RUNTIME_FILENAME
    return default_runtime_path().resolve()


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
        raise RuntimeDescriptorError("The MCP runtime descriptor path must be absolute.")
    try:
        before = path.lstat()
    except FileNotFoundError as exc:
        raise RuntimeDescriptorError(
            "LogosForge Pro is not running or has not finished starting."
        ) from exc
    except OSError as exc:
        raise RuntimeDescriptorError("The MCP runtime descriptor cannot be inspected.") from exc
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
        raise RuntimeDescriptorError("The MCP runtime descriptor must be a regular file.")
    if before.st_size <= 0 or before.st_size > MAX_DESCRIPTOR_BYTES:
        raise RuntimeDescriptorError("The MCP runtime descriptor has an invalid size.")
    if os.name != "nt":
        if before.st_mode & 0o077:
            raise RuntimeDescriptorError(
                "The MCP runtime descriptor is not private (expected mode 0600)."
            )
        getuid = getattr(os, "getuid", None)
        if getuid is not None and before.st_uid != getuid():
            raise RuntimeDescriptorError("The MCP runtime descriptor belongs to another user.")

    flags = os.O_RDONLY
    flags |= getattr(os, "O_BINARY", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise RuntimeDescriptorError("The MCP runtime descriptor cannot be opened safely.") from exc
    try:
        opened = os.fstat(fd)
        if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
            raise RuntimeDescriptorError("The MCP runtime descriptor changed while opening it.")
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
        raise RuntimeDescriptorError("The MCP runtime descriptor is too large.")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise RuntimeDescriptorError("The MCP runtime descriptor is not valid JSON.") from exc
    if not isinstance(payload, dict):
        raise RuntimeDescriptorError("The MCP runtime descriptor must contain a JSON object.")
    return payload


def _validated_loopback_url(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise RuntimeDescriptorError("The MCP runtime descriptor has no API URL.")
    parsed = urllib.parse.urlparse(value)
    if (
        parsed.scheme != "http"
        or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        raise RuntimeDescriptorError("The packaged Pro API URL must be plain HTTP on loopback.")
    try:
        port = parsed.port
    except ValueError as exc:
        raise RuntimeDescriptorError("The packaged Pro API URL has an invalid port.") from exc
    if port is None or not 1 <= port <= 65535:
        raise RuntimeDescriptorError("The packaged Pro API URL must include a valid port.")
    return value.rstrip("/")


def load_runtime_descriptor(
    path: str | os.PathLike[str],
    *,
    process_alive: Callable[[int], bool] = process_is_alive,
) -> RuntimeDescriptor:
    payload = _read_private_json(Path(path).expanduser())
    if payload.get("schema_version") != MCP_RUNTIME_SCHEMA_VERSION:
        raise RuntimeDescriptorError("The MCP runtime descriptor version is unsupported.")

    def required_text(name: str, minimum: int) -> str:
        value = payload.get(name)
        if (
            not isinstance(value, str)
            or value != value.strip()
            or len(value) < minimum
        ):
            raise RuntimeDescriptorError(f"The MCP runtime descriptor has an invalid {name}.")
        return value

    def required_pid(name: str) -> int:
        value = payload.get(name)
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise RuntimeDescriptorError(f"The MCP runtime descriptor has an invalid {name}.")
        return value

    connection = RuntimeDescriptor(
        base_url=_validated_loopback_url(payload.get("base_url")),
        auth_token=required_text("auth_token", 32),
        instance_nonce=required_text("instance_nonce", 16),
        app_pid=required_pid("app_pid"),
        core_pid=required_pid("core_pid"),
        created_at=required_text("created_at", 10),
    )
    try:
        created_at = datetime.fromisoformat(connection.created_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise RuntimeDescriptorError("The MCP runtime descriptor has an invalid created_at.") from exc
    if created_at.tzinfo is None or created_at.utcoffset() != timedelta(0):
        raise RuntimeDescriptorError("The MCP runtime descriptor created_at must be UTC.")
    if not process_alive(connection.app_pid):
        raise RuntimeDescriptorError("The runtime descriptor is stale: LogosForge Pro is not running.")
    if not process_alive(connection.core_pid):
        raise RuntimeDescriptorError("The runtime descriptor is stale: the Pro core is not running.")
    return connection


def verify_runtime_descriptor(
    connection: RuntimeDescriptor,
    *,
    timeout: float = 3.0,
    urlopen: Callable = urllib.request.urlopen,
) -> RuntimeDescriptor:
    request = urllib.request.Request(
        f"{connection.base_url}/api/health",
        headers={"Accept": "application/json", "User-Agent": "LogosForge-MCP"},
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read(MAX_HEALTH_BYTES + 1)
    except (urllib.error.URLError, OSError):
        # Network exceptions may include request details supplied by lower
        # layers. Suppress the cause so credentials can never reach diagnostics.
        raise RuntimeDescriptorError(
            "The packaged LogosForge Pro core is unreachable."
        ) from None
    if len(raw) > MAX_HEALTH_BYTES:
        raise RuntimeDescriptorError("The packaged core returned an oversized health response.")
    try:
        health = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise RuntimeDescriptorError("The packaged core returned invalid health data.") from exc
    if not isinstance(health, dict) or any(
        (
            health.get("status") != "ok",
            health.get("service") != "logosforge-api",
            health.get("mode") != "desktop",
            health.get("instance_nonce") != connection.instance_nonce,
        )
    ):
        raise RuntimeDescriptorError(
            "The packaged core identity or nonce is stale and does not match the application."
        )
    return connection


def load_runtime_connection(
    path: str | os.PathLike[str],
    *,
    timeout: float = 3.0,
    is_process_alive: Callable[[int], bool] = process_is_alive,
) -> RuntimeDescriptor:
    connection = load_runtime_descriptor(path, process_alive=is_process_alive)
    verify_runtime_descriptor(connection, timeout=timeout)
    return connection


def config_from_runtime_descriptor(
    path: str | os.PathLike[str],
    *,
    environ: Mapping[str, str] | None = None,
    process_alive: Callable[[int], bool] = process_is_alive,
    urlopen: Callable = urllib.request.urlopen,
):
    """Build an ``McpConfig`` from a verified descriptor plus safe controls."""
    env = os.environ if environ is None else environ
    if any(
        env.get(name, "").strip()
        for name in ("LOGOSFORGE_API_URL", "LOGOSFORGE_API_TOKEN")
    ):
        raise RuntimeDescriptorError(
            "Packaged MCP connections may not override the descriptor API URL or token."
        )
    descriptor = load_runtime_descriptor(path, process_alive=process_alive)
    verify_runtime_descriptor(descriptor, urlopen=urlopen)

    # Local import avoids a module cycle: mcp_server imports this module to
    # resolve packaged configuration, while this helper returns its public DTO.
    from logosforge.librechat.mcp_server import McpConfig, McpToolError, _env_bool

    project_raw = env.get("LOGOSFORGE_PROJECT_ID", "").strip()
    try:
        project_id = int(project_raw) if project_raw else None
        timeout = float(env.get("LOGOSFORGE_API_TIMEOUT", "15"))
        ttl = int(env.get("LOGOSFORGE_MCP_PROPOSAL_TTL_SECONDS", "900"))
    except ValueError as exc:
        raise McpToolError(f"Invalid numeric MCP environment setting: {exc}") from exc
    config = McpConfig(
        base_url=descriptor.base_url,
        project_id=project_id,
        auth_token=descriptor.auth_token,
        timeout=timeout,
        allow_writes=_env_bool("LOGOSFORGE_MCP_ALLOW_WRITES", environ=env),
        require_auth_for_writes=_env_bool(
            "LOGOSFORGE_MCP_REQUIRE_AUTH_FOR_WRITES", True, environ=env,
        ),
        proposal_ttl_seconds=ttl,
        allow_remote=_env_bool("LOGOSFORGE_MCP_ALLOW_REMOTE", environ=env),
    )
    config.validate()
    return config


# Descriptive aliases retained for callers that prefer connection terminology.
McpRuntimeError = RuntimeDescriptorError
McpRuntimeConnection = RuntimeDescriptor
read_runtime_connection = load_runtime_descriptor
verify_runtime_connection = verify_runtime_descriptor
