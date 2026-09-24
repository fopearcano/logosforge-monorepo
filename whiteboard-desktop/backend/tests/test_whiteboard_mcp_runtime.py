"""Security and lifecycle tests for the Whiteboard MCP connection handoff."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.whiteboard_mcp.runtime import (
    CONNECTION_FILE_ENV,
    MCP_RUNTIME_FILENAME,
    RuntimeDescriptorError,
    load_runtime_descriptor,
    resolve_runtime_descriptor_path,
    verify_runtime_descriptor,
)


def _descriptor(**updates) -> dict:
    value = {
        "schema_version": 1,
        "base_url": "http://127.0.0.1:43117",
        "auth_token": "runtime-secret-000000000000000000",
        "instance_nonce": "whiteboard-instance-one",
        "app_pid": 1234,
        "backend_pid": 5678,
        "created_at": "2026-09-24T10:00:00.000Z",
    }
    value.update(updates)
    return value


def _write(path: Path, value: object) -> None:
    path.write_text(
        value if isinstance(value, str) else json.dumps(value),
        encoding="utf-8",
    )
    if os.name != "nt":
        path.chmod(0o600)


def test_runtime_path_uses_product_user_data_and_whiteboard_override(tmp_path: Path) -> None:
    assert resolve_runtime_descriptor_path(tmp_path) == tmp_path.resolve() / MCP_RUNTIME_FILENAME
    explicit = tmp_path / "private" / MCP_RUNTIME_FILENAME
    assert resolve_runtime_descriptor_path(
        environ={CONNECTION_FILE_ENV: str(explicit)}
    ) == explicit

    with pytest.raises(RuntimeDescriptorError, match="absolute"):
        resolve_runtime_descriptor_path(
            environ={CONNECTION_FILE_ENV: MCP_RUNTIME_FILENAME}
        )
    with pytest.raises(RuntimeDescriptorError, match=MCP_RUNTIME_FILENAME):
        resolve_runtime_descriptor_path(
            environ={CONNECTION_FILE_ENV: str(tmp_path / "important.json")}
        )


@pytest.mark.skipif(os.name == "nt", reason="symlink creation is not portable on Windows")
def test_runtime_override_preserves_the_logical_final_path(tmp_path: Path) -> None:
    target = tmp_path / "target.json"
    target.write_text("{}", encoding="utf-8")
    logical = tmp_path / MCP_RUNTIME_FILENAME
    logical.symlink_to(target)
    assert resolve_runtime_descriptor_path(
        environ={CONNECTION_FILE_ENV: str(logical)}
    ) == logical


def test_load_runtime_descriptor_accepts_live_loopback_session(tmp_path: Path) -> None:
    path = tmp_path / MCP_RUNTIME_FILENAME
    _write(path, _descriptor())
    value = load_runtime_descriptor(path, process_alive=lambda _pid: True)
    assert value.base_url == "http://127.0.0.1:43117"
    assert value.auth_token == "runtime-secret-000000000000000000"
    assert value.backend_pid == 5678


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("schema_version", 2),
        ("base_url", "https://127.0.0.1:43117"),
        ("base_url", "http://example.test:43117"),
        ("base_url", "http://127.0.0.1:43117/api"),
        ("base_url", "http://name:secret@127.0.0.1:43117"),
        ("auth_token", "short"),
        ("instance_nonce", "short"),
        ("app_pid", True),
        ("backend_pid", 0),
        ("created_at", "2026-09-24T10:00:00"),
    ],
)
def test_load_runtime_descriptor_rejects_unsafe_fields(
    tmp_path: Path, field: str, value: object,
) -> None:
    path = tmp_path / MCP_RUNTIME_FILENAME
    _write(path, _descriptor(**{field: value}))
    with pytest.raises(RuntimeDescriptorError):
        load_runtime_descriptor(path, process_alive=lambda _pid: True)


@pytest.mark.parametrize("dead_pid", [1234, 5678])
def test_load_runtime_descriptor_rejects_dead_owner_process(
    tmp_path: Path, dead_pid: int,
) -> None:
    path = tmp_path / MCP_RUNTIME_FILENAME
    _write(path, _descriptor())
    with pytest.raises(RuntimeDescriptorError, match="stale"):
        load_runtime_descriptor(path, process_alive=lambda pid: pid != dead_pid)


def test_invalid_descriptor_diagnostics_never_echo_token(tmp_path: Path) -> None:
    secret = "must-never-appear-in-diagnostics"
    path = tmp_path / MCP_RUNTIME_FILENAME
    _write(path, f'{{"auth_token":"{secret}",not-json')
    with pytest.raises(RuntimeDescriptorError) as caught:
        load_runtime_descriptor(path, process_alive=lambda _pid: True)
    assert secret not in str(caught.value)


@pytest.mark.skipif(os.name == "nt", reason="POSIX file-mode check")
def test_descriptor_must_be_private_on_posix(tmp_path: Path) -> None:
    path = tmp_path / MCP_RUNTIME_FILENAME
    _write(path, _descriptor())
    path.chmod(0o644)
    with pytest.raises(RuntimeDescriptorError, match="not private"):
        load_runtime_descriptor(path, process_alive=lambda _pid: True)


class _Response:
    def __init__(self, value: object) -> None:
        self.raw = json.dumps(value).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, size: int = -1) -> bytes:
        return self.raw[:size]


def test_health_verification_requires_service_and_matching_nonce(tmp_path: Path) -> None:
    path = tmp_path / MCP_RUNTIME_FILENAME
    _write(path, _descriptor())
    descriptor = load_runtime_descriptor(path, process_alive=lambda _pid: True)
    seen = {}

    def urlopen(request, timeout):
        seen["url"] = request.full_url
        seen["authorization"] = request.get_header("Authorization")
        seen["timeout"] = timeout
        return _Response(
            {
                "status": "ok",
                "service": "logosforge-whiteboard-backend",
                "instance_nonce": "whiteboard-instance-one",
            }
        )

    assert verify_runtime_descriptor(descriptor, urlopen=urlopen) is descriptor
    assert seen == {
        "url": "http://127.0.0.1:43117/health",
        "authorization": None,
        "timeout": 3.0,
    }

    def wrong_nonce(_request, timeout):
        del timeout
        return _Response(
            {
                "status": "ok",
                "service": "logosforge-whiteboard-backend",
                "instance_nonce": "another-whiteboard-instance",
            }
        )

    with pytest.raises(RuntimeDescriptorError, match="identity or nonce"):
        verify_runtime_descriptor(descriptor, urlopen=wrong_nonce)


def test_descriptor_repr_hides_bearer_token(tmp_path: Path) -> None:
    path = tmp_path / MCP_RUNTIME_FILENAME
    _write(path, _descriptor())
    descriptor = load_runtime_descriptor(path, process_alive=lambda _pid: True)
    assert descriptor.auth_token not in repr(descriptor)
