"""Security and lifecycle tests for the packaged Pro MCP connection handoff."""

from __future__ import annotations

import io
import json
import os
import traceback
from pathlib import Path
from urllib import error as urlerror

import pytest
from logosforge.librechat.mcp_runtime import (
    RuntimeDescriptorError,
    config_from_runtime_descriptor,
    load_runtime_descriptor,
    process_is_alive,
    resolve_runtime_descriptor_path,
    verify_runtime_descriptor,
)


class _Response(io.BytesIO):
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


def _descriptor(*, token: str = "runtime-secret-000000000000000000") -> dict:
    return {
        "schema_version": 1,
        "base_url": "http://127.0.0.1:43117",
        "auth_token": token,
        "instance_nonce": "desktop-instance-one",
        "app_pid": 1001,
        "core_pid": 1002,
        # Deliberately old: liveness and the health nonce, not wall-clock age,
        # define whether a long-running Pro session is still current.
        "created_at": "2000-01-01T00:00:00.000Z",
    }


def _write_descriptor(path: Path, value: dict | str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = value if isinstance(value, str) else json.dumps(value)
    path.write_text(text, encoding="utf-8")
    if os.name != "nt":
        path.chmod(0o600)


def _field(value, name: str):
    if isinstance(value, dict):
        return value[name]
    return getattr(value, name)


def test_runtime_descriptor_path_honors_explicit_environment_override(tmp_path):
    target = tmp_path / "explicit" / "runtime.json"

    resolved = resolve_runtime_descriptor_path(
        environ={"LOGOSFORGE_MCP_CONNECTION_FILE": str(target)},
    )

    assert resolved == target.resolve()


def test_load_runtime_descriptor_accepts_old_but_live_local_session(tmp_path):
    target = tmp_path / "mcp-runtime.json"
    _write_descriptor(target, _descriptor())
    checked: list[int] = []

    descriptor = load_runtime_descriptor(
        target,
        process_alive=lambda pid: checked.append(pid) is None or True,
    )

    assert checked == [1001, 1002]
    assert _field(descriptor, "base_url") == "http://127.0.0.1:43117"
    assert _field(descriptor, "auth_token") == "runtime-secret-000000000000000000"
    assert _field(descriptor, "instance_nonce") == "desktop-instance-one"


@pytest.mark.parametrize("dead_pid", [1001, 1002])
def test_load_runtime_descriptor_rejects_dead_app_or_core_process(tmp_path, dead_pid):
    target = tmp_path / "mcp-runtime.json"
    _write_descriptor(target, _descriptor())

    with pytest.raises(RuntimeDescriptorError, match="not running|stale"):
        load_runtime_descriptor(
            target,
            process_alive=lambda pid: pid != dead_pid,
        )


@pytest.mark.parametrize(
    "mutation",
    [
        lambda value: value.pop("instance_nonce"),
        lambda value: value.__setitem__("schema_version", 2),
        lambda value: value.__setitem__("app_pid", 0),
        lambda value: value.__setitem__("created_at", "2026-09-24T10:00:00"),
        lambda value: value.__setitem__("base_url", "https://example.test"),
        lambda value: value.__setitem__("base_url", "http://user:pw@127.0.0.1:43117"),
    ],
)
def test_load_runtime_descriptor_rejects_malformed_or_unsafe_fields(
    tmp_path, mutation,
):
    target = tmp_path / "mcp-runtime.json"
    value = _descriptor()
    mutation(value)
    _write_descriptor(target, value)

    with pytest.raises(RuntimeDescriptorError):
        load_runtime_descriptor(target, process_alive=lambda _pid: True)


def test_load_runtime_descriptor_rejects_invalid_json_without_leaking_it(tmp_path):
    target = tmp_path / "mcp-runtime.json"
    secret = "malformed-file-secret"
    _write_descriptor(target, f'{{"auth_token":"{secret}",not-json')

    with pytest.raises(RuntimeDescriptorError) as caught:
        load_runtime_descriptor(target, process_alive=lambda _pid: True)

    assert secret not in str(caught.value)


def test_process_liveness_probe_is_non_destructive_for_current_process():
    assert process_is_alive(os.getpid()) is True
    assert process_is_alive(-1) is False


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission bits do not model Windows ACLs")
def test_load_runtime_descriptor_rejects_group_or_world_readable_file(tmp_path):
    target = tmp_path / "mcp-runtime.json"
    _write_descriptor(target, _descriptor())
    target.chmod(0o644)

    with pytest.raises(RuntimeDescriptorError, match="permission|private"):
        load_runtime_descriptor(target, process_alive=lambda _pid: True)


def test_verify_runtime_descriptor_requires_matching_health_nonce_without_auth(tmp_path):
    target = tmp_path / "mcp-runtime.json"
    _write_descriptor(target, _descriptor())
    descriptor = load_runtime_descriptor(target, process_alive=lambda _pid: True)
    captured = {}

    def urlopen(request, timeout=None):
        captured.update(
            url=request.full_url,
            authorization=request.headers.get("Authorization"),
            timeout=timeout,
        )
        return _Response(json.dumps({
            "status": "ok",
            "service": "logosforge-api",
            "mode": "desktop",
            "instance_nonce": "desktop-instance-one",
        }).encode("utf-8"))

    verified = verify_runtime_descriptor(descriptor, urlopen=urlopen)

    assert verified is descriptor
    assert captured["url"] == "http://127.0.0.1:43117/api/health"
    assert captured["authorization"] is None
    assert 0 < captured["timeout"] <= 15


def test_verify_runtime_descriptor_rejects_nonce_mismatch_as_stale(tmp_path):
    target = tmp_path / "mcp-runtime.json"
    _write_descriptor(target, _descriptor())
    descriptor = load_runtime_descriptor(target, process_alive=lambda _pid: True)

    def urlopen(_request, timeout=None):
        del timeout
        return _Response(json.dumps({
            "status": "ok",
            "service": "logosforge-api",
            "mode": "desktop",
            "instance_nonce": "different-session",
        }).encode("utf-8"))

    with pytest.raises(RuntimeDescriptorError, match="nonce|stale"):
        verify_runtime_descriptor(descriptor, urlopen=urlopen)


def test_runtime_network_failure_does_not_leak_auth_token(tmp_path):
    target = tmp_path / "mcp-runtime.json"
    token = "network-error-secret-0000000000000000"
    _write_descriptor(target, _descriptor(token=token))
    descriptor = load_runtime_descriptor(target, process_alive=lambda _pid: True)

    def urlopen(_request, timeout=None):
        del timeout
        raise urlerror.URLError(f"cannot connect with {token}")

    with pytest.raises(RuntimeDescriptorError) as caught:
        verify_runtime_descriptor(descriptor, urlopen=urlopen)

    assert token not in str(caught.value)
    assert token not in "".join(
        traceback.format_exception(
            type(caught.value), caught.value, caught.value.__traceback__,
        )
    )


@pytest.mark.parametrize(
    "override",
    [
        {"LOGOSFORGE_API_URL": "http://localhost:49999/"},
        {"LOGOSFORGE_API_TOKEN": "explicit-secret-000000000000000000"},
    ],
)
def test_descriptor_connection_rejects_api_environment_overrides(tmp_path, override):
    target = tmp_path / "mcp-runtime.json"
    _write_descriptor(target, _descriptor())

    with pytest.raises(RuntimeDescriptorError, match="may not override"):
        config_from_runtime_descriptor(
            target,
            environ={**override, "LOGOSFORGE_MCP_ALLOW_WRITES": "1"},
            process_alive=lambda _pid: True,
        )
