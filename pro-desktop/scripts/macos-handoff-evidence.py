#!/usr/bin/env python3
"""Create and verify a bounded, self-describing Pro macOS handoff directory."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
import shutil
import stat
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Mapping, Sequence


SCHEMA = "logosforge-pro-macos-handoff-v1"
PLATFORM = "macos-intel-x64"
MANIFEST_NAME = "macos-handoff.json"
PIP_FREEZE_NAME = "pip-freeze.txt"
BUILD_EVIDENCE_NAME = "SHA256SUMS-and-build.txt"
READ_CHUNK_SIZE = 1024 * 1024
MAX_MANIFEST_BYTES = 1024 * 1024
MAX_EVIDENCE_BYTES = 32 * 1024 * 1024
MAX_DMG_BYTES = 8 * 1024 * 1024 * 1024

REPOSITORY_PATTERN = re.compile(
    r"(?=.{3,200}\Z)[A-Za-z0-9](?:[A-Za-z0-9_.-]{0,98}[A-Za-z0-9_.-])?"
    r"/[A-Za-z0-9](?:[A-Za-z0-9_.-]{0,98}[A-Za-z0-9_.-])?\Z"
)
SHA1_PATTERN = re.compile(r"[0-9a-fA-F]{40}\Z")
SHA256_PATTERN = re.compile(r"[0-9a-fA-F]{64}\Z")
POSITIVE_INTEGER_PATTERN = re.compile(r"[1-9][0-9]{0,30}\Z")
SEMVER_PATTERN = re.compile(
    r"(?:0|[1-9][0-9]*)\."
    r"(?:0|[1-9][0-9]*)\."
    r"(?:0|[1-9][0-9]*)"
    r"(?:-(?:0|[1-9][0-9]*|[0-9A-Za-z-]*[A-Za-z-][0-9A-Za-z-]*)"
    r"(?:\.(?:0|[1-9][0-9]*|[0-9A-Za-z-]*[A-Za-z-][0-9A-Za-z-]*))*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?\Z"
)
WORKFLOW_REF_PATTERN = re.compile(r"[A-Za-z0-9._/@+:-]{1,1024}\Z")
DIRECTORY_COMPONENT_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")


class HandoffError(RuntimeError):
    """Raised when handoff evidence is invalid or cannot be handled safely."""


@dataclass(frozen=True)
class Identity:
    repository: str
    repository_id: str
    tag: str
    source_sha: str
    source_tree_sha256: str
    workflow_ref: str
    workflow_sha: str
    run_id: str
    run_attempt: str
    version: str
    platform: str
    dmg_name: str


@dataclass(frozen=True)
class FileEvidence:
    size: int
    sha256: str

    def as_json(self) -> dict[str, object]:
        return {"sha256": self.sha256, "size": self.size}


def _validate_identity(identity: Identity) -> Identity:
    if REPOSITORY_PATTERN.fullmatch(identity.repository) is None:
        raise HandoffError("repository must be a safe OWNER/REPO name")
    if any(piece in {".", ".."} for piece in identity.repository.split("/")):
        raise HandoffError("repository contains an unsafe path component")
    if POSITIVE_INTEGER_PATTERN.fullmatch(identity.repository_id) is None:
        raise HandoffError("repository ID must be a positive canonical decimal integer")
    if SEMVER_PATTERN.fullmatch(identity.version) is None:
        raise HandoffError("version must be a valid semantic version")
    expected_tag = f"v{identity.version}"
    if identity.tag != expected_tag:
        raise HandoffError(f"tag must exactly match the Pro version: {expected_tag}")
    if SHA1_PATTERN.fullmatch(identity.source_sha) is None:
        raise HandoffError("source SHA must be a complete 40-character hexadecimal commit ID")
    if SHA256_PATTERN.fullmatch(identity.source_tree_sha256) is None:
        raise HandoffError("source tree SHA-256 must contain exactly 64 hexadecimal characters")
    expected_workflow_prefix = (
        f"{identity.repository}/.github/workflows/release-windows.yml@refs/"
    )
    if (
        WORKFLOW_REF_PATTERN.fullmatch(identity.workflow_ref) is None
        or not identity.workflow_ref.startswith(expected_workflow_prefix)
    ):
        raise HandoffError(
            "workflow ref must identify release-windows.yml in the expected repository"
        )
    if SHA1_PATTERN.fullmatch(identity.workflow_sha) is None:
        raise HandoffError("workflow SHA must be a complete 40-character hexadecimal commit ID")
    if POSITIVE_INTEGER_PATTERN.fullmatch(identity.run_id) is None:
        raise HandoffError("run ID must be a positive canonical decimal integer")
    if POSITIVE_INTEGER_PATTERN.fullmatch(identity.run_attempt) is None:
        raise HandoffError("run attempt must be a positive canonical decimal integer")
    if identity.platform != PLATFORM:
        raise HandoffError(f"platform must exactly equal {PLATFORM}")
    expected_dmg_name = f"LogosForge Pro-{identity.version}-x64.dmg"
    if identity.dmg_name != expected_dmg_name:
        raise HandoffError(
            f"DMG name must exactly match the Pro version: {expected_dmg_name}"
        )
    if (
        Path(identity.dmg_name).name != identity.dmg_name
        or identity.dmg_name in {".", ".."}
        or "/" in identity.dmg_name
        or "\\" in identity.dmg_name
        or any(ord(character) < 32 or ord(character) == 127 for character in identity.dmg_name)
        or len(identity.dmg_name.encode("utf-8")) > 255
    ):
        raise HandoffError("DMG name is not a safe filename")
    return Identity(
        repository=identity.repository,
        repository_id=identity.repository_id,
        tag=identity.tag,
        source_sha=identity.source_sha.lower(),
        source_tree_sha256=identity.source_tree_sha256.lower(),
        workflow_ref=identity.workflow_ref,
        workflow_sha=identity.workflow_sha.lower(),
        run_id=identity.run_id,
        run_attempt=identity.run_attempt,
        version=identity.version,
        platform=identity.platform,
        dmg_name=identity.dmg_name,
    )


def _identity_from_args(args: argparse.Namespace) -> Identity:
    return _validate_identity(
        Identity(
            repository=args.repository,
            repository_id=args.repository_id,
            tag=args.tag,
            source_sha=args.source_sha,
            source_tree_sha256=args.source_tree_sha256,
            workflow_ref=args.workflow_ref,
            workflow_sha=args.workflow_sha,
            run_id=args.run_id,
            run_attempt=args.run_attempt,
            version=args.version,
            platform=args.platform,
            dmg_name=args.dmg_name,
        )
    )


def _file_identity(value: os.stat_result) -> tuple[int, int, int, int]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_size,
        value.st_mtime_ns,
    )


def _directory_identity(value: os.stat_result) -> tuple[int, int]:
    return (value.st_dev, value.st_ino)


def _open_read_only_regular(path: Path, maximum_bytes: int, label: str) -> tuple[int, os.stat_result]:
    try:
        path_stat = path.lstat()
    except OSError as exc:
        raise HandoffError(f"cannot safely inspect {label}: {path}") from exc
    if stat.S_ISLNK(path_stat.st_mode) or not stat.S_ISREG(path_stat.st_mode):
        raise HandoffError(f"{label} must be a non-symlink regular file")
    if path_stat.st_size < 1 or path_stat.st_size > maximum_bytes:
        raise HandoffError(f"{label} must be between 1 and {maximum_bytes} bytes")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise HandoffError(f"cannot safely open {label}: {path}") from exc
    try:
        file_stat = os.fstat(descriptor)
        if not stat.S_ISREG(file_stat.st_mode):
            raise HandoffError(f"{label} must be a regular file")
        if _file_identity(path_stat) != _file_identity(file_stat):
            raise HandoffError(f"{label} changed while it was opened")
        if file_stat.st_size < 1 or file_stat.st_size > maximum_bytes:
            raise HandoffError(
                f"{label} must be between 1 and {maximum_bytes} bytes"
            )
        return descriptor, file_stat
    except Exception:
        os.close(descriptor)
        raise


def _write_all(descriptor: int, payload: bytes) -> None:
    offset = 0
    while offset < len(payload):
        written = os.write(descriptor, payload[offset:])
        if written < 1:
            raise HandoffError("an output file stopped accepting data")
        offset += written


def _copy_regular_with_digest(
    source: Path,
    destination: Path,
    maximum_bytes: int,
    label: str,
) -> FileEvidence:
    source_descriptor, before = _open_read_only_regular(source, maximum_bytes, label)
    destination_flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_BINARY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        destination_descriptor = os.open(destination, destination_flags, 0o600)
    except OSError as exc:
        os.close(source_descriptor)
        raise HandoffError(f"cannot create staged {label}: {destination}") from exc

    digest = hashlib.sha256()
    total = 0
    try:
        while True:
            chunk = os.read(source_descriptor, READ_CHUNK_SIZE)
            if not chunk:
                break
            total += len(chunk)
            if total > maximum_bytes:
                raise HandoffError(f"{label} grew beyond its bounded size limit")
            digest.update(chunk)
            _write_all(destination_descriptor, chunk)
        after = os.fstat(source_descriptor)
        if _file_identity(before) != _file_identity(after) or total != before.st_size:
            raise HandoffError(f"{label} changed while it was copied")
        os.fsync(destination_descriptor)
    finally:
        os.close(destination_descriptor)
        os.close(source_descriptor)

    return FileEvidence(size=total, sha256=digest.hexdigest())


def _hash_regular(
    path: Path, maximum_bytes: int, label: str
) -> tuple[FileEvidence, tuple[int, int, int, int]]:
    descriptor, before = _open_read_only_regular(path, maximum_bytes, label)
    digest = hashlib.sha256()
    total = 0
    try:
        while True:
            chunk = os.read(descriptor, READ_CHUNK_SIZE)
            if not chunk:
                break
            total += len(chunk)
            if total > maximum_bytes:
                raise HandoffError(f"{label} grew beyond its bounded size limit")
            digest.update(chunk)
        after = os.fstat(descriptor)
        if _file_identity(before) != _file_identity(after) or total != before.st_size:
            raise HandoffError(f"{label} changed while it was verified")
    finally:
        os.close(descriptor)
    return FileEvidence(size=total, sha256=digest.hexdigest()), _file_identity(after)


def _assert_path_identity(
    path: Path,
    expected: tuple[int, int, int, int],
    label: str,
) -> None:
    try:
        observed = path.lstat()
    except OSError as exc:
        raise HandoffError(f"cannot re-inspect {label}") from exc
    if stat.S_ISLNK(observed.st_mode) or not stat.S_ISREG(observed.st_mode):
        raise HandoffError(f"{label} stopped being a non-symlink regular file")
    if _file_identity(observed) != expected:
        raise HandoffError(f"{label} changed after it was verified")


def _read_bounded_regular(path: Path, maximum_bytes: int, label: str) -> bytes:
    descriptor, before = _open_read_only_regular(path, maximum_bytes, label)
    chunks: list[bytes] = []
    total = 0
    try:
        while True:
            chunk = os.read(descriptor, min(READ_CHUNK_SIZE, maximum_bytes + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > maximum_bytes:
                raise HandoffError(f"{label} exceeds its bounded size limit")
        after = os.fstat(descriptor)
        if _file_identity(before) != _file_identity(after) or total != before.st_size:
            raise HandoffError(f"{label} changed while it was read")
    finally:
        os.close(descriptor)
    return b"".join(chunks)


def _canonical_json(value: Mapping[str, object]) -> bytes:
    return (
        json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
        + "\n"
    ).encode("utf-8")


def _atomic_write_json(directory: Path, value: Mapping[str, object]) -> None:
    payload = _canonical_json(value)
    if len(payload) > MAX_MANIFEST_BYTES:
        raise HandoffError("canonical handoff manifest exceeds its bounded size limit")
    temporary = directory / f".{MANIFEST_NAME}.tmp-{secrets.token_hex(8)}"
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_BINARY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    descriptor = -1
    try:
        descriptor = os.open(temporary, flags, 0o600)
        _write_all(descriptor, payload)
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        os.replace(temporary, directory / MANIFEST_NAME)
    except Exception:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
        raise


def _safe_directory_path(raw_path: Path, *, must_exist: bool) -> Path:
    if any(piece == ".." for piece in raw_path.parts):
        raise HandoffError("staging directory path must not contain parent traversal")
    if raw_path.name in {"", ".", ".."} or DIRECTORY_COMPONENT_PATTERN.fullmatch(raw_path.name) is None:
        raise HandoffError("staging directory must end in one safe path component")
    try:
        parent = raw_path.parent.resolve(strict=True)
    except OSError as exc:
        raise HandoffError("staging directory parent does not exist") from exc
    try:
        parent_stat = parent.stat()
    except OSError as exc:
        raise HandoffError("cannot inspect staging directory parent") from exc
    if not stat.S_ISDIR(parent_stat.st_mode):
        raise HandoffError("staging directory parent is not a directory")
    path = parent / raw_path.name
    exists = os.path.lexists(path)
    if must_exist and not exists:
        raise HandoffError(f"staging directory does not exist: {path}")
    if not must_exist and exists:
        raise HandoffError(f"staging directory already exists: {path}")
    return path


def _validate_exact_directory(directory: Path, expected_names: set[str]) -> None:
    try:
        directory_stat = directory.lstat()
    except OSError as exc:
        raise HandoffError(f"cannot inspect staging directory: {directory}") from exc
    if stat.S_ISLNK(directory_stat.st_mode) or not stat.S_ISDIR(directory_stat.st_mode):
        raise HandoffError("staging directory must be a real directory, not a symlink")
    try:
        entries = list(os.scandir(directory))
    except OSError as exc:
        raise HandoffError("cannot enumerate staging directory") from exc
    names = {entry.name for entry in entries}
    if len(names) != len(entries):
        raise HandoffError("staging directory contains duplicate names")
    missing = sorted(expected_names - names)
    extra = sorted(names - expected_names)
    if missing or extra:
        details: list[str] = []
        if missing:
            details.append("missing=" + ",".join(missing))
        if extra:
            details.append("extra=" + ",".join(extra))
        raise HandoffError("staging directory contents do not match the contract: " + " ".join(details))
    for entry in entries:
        try:
            entry_stat = entry.stat(follow_symlinks=False)
        except OSError as exc:
            raise HandoffError(f"cannot inspect staged file: {entry.name}") from exc
        _validate_staged_file_mode(entry_stat.st_mode, entry.name)
        if entry_stat.st_size < 1:
            raise HandoffError(f"staged file must not be empty: {entry.name}")


def _validate_staged_file_mode(mode: int, name: str) -> None:
    if stat.S_ISLNK(mode) or not stat.S_ISREG(mode):
        raise HandoffError(f"staged file must be a non-symlink regular file: {name}")


def _manifest(identity: Identity, evidence: Mapping[str, FileEvidence]) -> dict[str, object]:
    return {
        "dmg_name": identity.dmg_name,
        "files": {name: item.as_json() for name, item in evidence.items()},
        "platform": identity.platform,
        "repository": identity.repository,
        "repository_id": identity.repository_id,
        "run_attempt": identity.run_attempt,
        "run_id": identity.run_id,
        "schema": SCHEMA,
        "source_sha": identity.source_sha,
        "source_tree_sha256": identity.source_tree_sha256,
        "tag": identity.tag,
        "version": identity.version,
        "workflow_ref": identity.workflow_ref,
        "workflow_sha": identity.workflow_sha,
    }


def _validate_file_record(value: object, name: str) -> FileEvidence:
    if not isinstance(value, dict) or set(value) != {"sha256", "size"}:
        raise HandoffError(f"manifest contains an invalid file record for {name}")
    size = value.get("size")
    digest = value.get("sha256")
    if isinstance(size, bool) or not isinstance(size, int) or size < 1:
        raise HandoffError(f"manifest contains an invalid size for {name}")
    if not isinstance(digest, str) or SHA256_PATTERN.fullmatch(digest) is None or digest != digest.lower():
        raise HandoffError(f"manifest contains an invalid SHA-256 for {name}")
    return FileEvidence(size=size, sha256=digest)


def _parse_manifest(payload: bytes, identity: Identity) -> tuple[dict[str, object], dict[str, FileEvidence]]:
    try:
        decoded = payload.decode("utf-8")
        value = json.loads(decoded)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HandoffError("handoff manifest is not valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise HandoffError("handoff manifest must be a JSON object")
    expected_keys = {
        "dmg_name",
        "files",
        "platform",
        "repository",
        "repository_id",
        "run_attempt",
        "run_id",
        "schema",
        "source_sha",
        "source_tree_sha256",
        "tag",
        "version",
        "workflow_ref",
        "workflow_sha",
    }
    if set(value) != expected_keys:
        raise HandoffError("handoff manifest fields do not match the canonical schema")
    expected_metadata = {
        "dmg_name": identity.dmg_name,
        "platform": identity.platform,
        "repository": identity.repository,
        "repository_id": identity.repository_id,
        "run_attempt": identity.run_attempt,
        "run_id": identity.run_id,
        "schema": SCHEMA,
        "source_sha": identity.source_sha,
        "source_tree_sha256": identity.source_tree_sha256,
        "tag": identity.tag,
        "version": identity.version,
        "workflow_ref": identity.workflow_ref,
        "workflow_sha": identity.workflow_sha,
    }
    for field, expected in expected_metadata.items():
        if value.get(field) != expected:
            raise HandoffError(f"handoff manifest {field} does not match the expected value")
    files = value.get("files")
    expected_file_names = {identity.dmg_name, PIP_FREEZE_NAME, BUILD_EVIDENCE_NAME}
    if not isinstance(files, dict) or set(files) != expected_file_names:
        raise HandoffError("handoff manifest file records do not match the exact staged files")
    records = {name: _validate_file_record(files[name], name) for name in expected_file_names}
    if payload != _canonical_json(value):
        raise HandoffError("handoff manifest is not encoded as canonical JSON")
    return value, records


def create_handoff(
    staging_directory: Path,
    dmg_path: Path,
    pip_freeze_path: Path,
    build_evidence_path: Path,
    identity: Identity,
) -> dict[str, object]:
    identity = _validate_identity(identity)
    if dmg_path.name != identity.dmg_name:
        raise HandoffError("input DMG name does not match the required exact output name")
    if pip_freeze_path.name != PIP_FREEZE_NAME:
        raise HandoffError(f"pip-freeze input must be named {PIP_FREEZE_NAME}")
    if build_evidence_path.name != BUILD_EVIDENCE_NAME:
        raise HandoffError(f"build-evidence input must be named {BUILD_EVIDENCE_NAME}")
    target = _safe_directory_path(staging_directory, must_exist=False)
    try:
        os.mkdir(target, 0o700)
    except OSError as exc:
        raise HandoffError(f"cannot create staging directory: {target}") from exc
    target_identity = _directory_identity(target.lstat())
    completed = False
    try:
        evidence = {
            identity.dmg_name: _copy_regular_with_digest(
                dmg_path, target / identity.dmg_name, MAX_DMG_BYTES, "DMG"
            ),
            PIP_FREEZE_NAME: _copy_regular_with_digest(
                pip_freeze_path,
                target / PIP_FREEZE_NAME,
                MAX_EVIDENCE_BYTES,
                "pip-freeze evidence",
            ),
            BUILD_EVIDENCE_NAME: _copy_regular_with_digest(
                build_evidence_path,
                target / BUILD_EVIDENCE_NAME,
                MAX_EVIDENCE_BYTES,
                "build evidence",
            ),
        }
        manifest = _manifest(identity, evidence)
        _atomic_write_json(target, manifest)
        expected_names = {
            identity.dmg_name,
            MANIFEST_NAME,
            PIP_FREEZE_NAME,
            BUILD_EVIDENCE_NAME,
        }
        _validate_exact_directory(target, expected_names)
        verify_handoff(target, identity)
        completed = True
        return manifest
    finally:
        if not completed and os.path.lexists(target):
            try:
                target_stat = target.lstat()
                if (
                    stat.S_ISDIR(target_stat.st_mode)
                    and _directory_identity(target_stat) == target_identity
                ):
                    shutil.rmtree(target)
            except OSError:
                # Preserve an unexpectedly changed target for diagnosis rather
                # than risking deletion outside the directory created above.
                pass


def verify_handoff(staging_directory: Path, identity: Identity) -> dict[str, object]:
    identity = _validate_identity(identity)
    directory = _safe_directory_path(staging_directory, must_exist=True)
    expected_names = {
        identity.dmg_name,
        MANIFEST_NAME,
        PIP_FREEZE_NAME,
        BUILD_EVIDENCE_NAME,
    }
    _validate_exact_directory(directory, expected_names)
    manifest_payload = _read_bounded_regular(
        directory / MANIFEST_NAME, MAX_MANIFEST_BYTES, "handoff manifest"
    )
    manifest, records = _parse_manifest(manifest_payload, identity)
    limits = {
        identity.dmg_name: MAX_DMG_BYTES,
        PIP_FREEZE_NAME: MAX_EVIDENCE_BYTES,
        BUILD_EVIDENCE_NAME: MAX_EVIDENCE_BYTES,
    }
    verified_identities: dict[str, tuple[int, int, int, int]] = {}
    for name, expected in records.items():
        observed, observed_identity = _hash_regular(
            directory / name, limits[name], f"staged {name}"
        )
        if observed.size != expected.size:
            raise HandoffError(f"staged {name} size does not match the manifest")
        if observed.sha256 != expected.sha256:
            raise HandoffError(f"staged {name} SHA-256 does not match the manifest")
        verified_identities[name] = observed_identity
    for name, observed_identity in verified_identities.items():
        _assert_path_identity(directory / name, observed_identity, f"staged {name}")
    if _read_bounded_regular(
        directory / MANIFEST_NAME, MAX_MANIFEST_BYTES, "handoff manifest"
    ) != manifest_payload:
        raise HandoffError("handoff manifest changed after it was verified")
    _validate_exact_directory(directory, expected_names)
    return manifest


def _expect_rejection(label: str, callback: object) -> None:
    try:
        callback()  # type: ignore[operator]
    except HandoffError:
        return
    raise AssertionError(f"self-test expected rejection: {label}")


def run_self_test() -> None:
    identity = Identity(
        repository="example/logosforge",
        repository_id="123456",
        tag="v1.2.3",
        source_sha="0123456789abcdef0123456789abcdef01234567",
        source_tree_sha256="a" * 64,
        workflow_ref=(
            "example/logosforge/.github/workflows/release-windows.yml@refs/heads/main"
        ),
        workflow_sha="89abcdef0123456789abcdef0123456789abcdef",
        run_id="987654321",
        run_attempt="2",
        version="1.2.3",
        platform=PLATFORM,
        dmg_name="LogosForge Pro-1.2.3-x64.dmg",
    )
    with tempfile.TemporaryDirectory(prefix="logosforge-pro-macos-handoff-") as temp:
        root = Path(temp)
        inputs = root / "inputs"
        inputs.mkdir()
        dmg = inputs / identity.dmg_name
        pip_freeze = inputs / PIP_FREEZE_NAME
        build_evidence = inputs / BUILD_EVIDENCE_NAME
        dmg_bytes = b"fake deterministic disk image\n"
        pip_bytes = b"logosforge==1.2.3\n"
        build_bytes = b"source_sha=0123456789abcdef0123456789abcdef01234567\n"
        dmg.write_bytes(dmg_bytes)
        pip_freeze.write_bytes(pip_bytes)
        build_evidence.write_bytes(build_bytes)
        staging = root / "handoff"

        create_handoff(staging, dmg, pip_freeze, build_evidence, identity)
        verify_handoff(staging, identity)

        (staging / identity.dmg_name).write_bytes(b"fake deterministic disk imagf\n")
        _expect_rejection("tampered DMG", lambda: verify_handoff(staging, identity))
        (staging / identity.dmg_name).write_bytes(dmg_bytes)
        verify_handoff(staging, identity)

        extra = staging / "unexpected.txt"
        extra.write_text("unexpected\n", encoding="utf-8")
        _expect_rejection("extra file", lambda: verify_handoff(staging, identity))
        extra.unlink()

        staged_pip = staging / PIP_FREEZE_NAME
        staged_pip.unlink()
        try:
            os.symlink(pip_freeze, staged_pip)
        except OSError:
            # Some Windows hosts deny symlink creation without Developer Mode.
            # Exercise the same rejection branch directly on those hosts so the
            # self-test remains portable while still covering link detection.
            _expect_rejection(
                "symlink mode",
                lambda: _validate_staged_file_mode(stat.S_IFLNK | 0o777, PIP_FREEZE_NAME),
            )
        else:
            _expect_rejection("symlinked file", lambda: verify_handoff(staging, identity))
            staged_pip.unlink()
        staged_pip.write_bytes(pip_bytes)
        verify_handoff(staging, identity)

        mismatched = Identity(**{**identity.__dict__, "run_attempt": "3"})
        _expect_rejection("metadata mismatch", lambda: verify_handoff(staging, mismatched))


def _add_identity_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--repository", required=True, help="GitHub OWNER/REPO")
    parser.add_argument("--repository-id", required=True, help="immutable GitHub repository ID")
    parser.add_argument("--tag", required=True, help="exact Pro release tag")
    parser.add_argument("--source-sha", required=True, help="full immutable source commit SHA")
    parser.add_argument(
        "--source-tree-sha256", required=True, help="SHA-256 of the immutable source tree listing"
    )
    parser.add_argument("--workflow-ref", required=True, help="GitHub workflow ref")
    parser.add_argument("--workflow-sha", required=True, help="full workflow commit SHA")
    parser.add_argument("--run-id", required=True, help="GitHub Actions run ID")
    parser.add_argument("--run-attempt", required=True, help="GitHub Actions run attempt")
    parser.add_argument("--version", required=True, help="Pro semantic version")
    parser.add_argument("--platform", required=True, help=f"must be {PLATFORM}")
    parser.add_argument("--dmg-name", required=True, help="exact versioned Pro DMG filename")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="exercise valid and rejected handoff cases without network access",
    )
    subparsers = parser.add_subparsers(dest="command")

    create_parser = subparsers.add_parser("create", help="create a new atomic handoff directory")
    create_parser.add_argument("--staging-dir", type=Path, required=True)
    create_parser.add_argument("--dmg", type=Path, required=True)
    create_parser.add_argument("--pip-freeze", type=Path, required=True)
    create_parser.add_argument("--sha256s-and-build", type=Path, required=True)
    _add_identity_arguments(create_parser)

    verify_parser = subparsers.add_parser("verify", help="verify a pulled handoff directory")
    verify_parser.add_argument("--staging-dir", type=Path, required=True)
    _add_identity_arguments(verify_parser)

    args = parser.parse_args(argv)
    if args.self_test:
        if args.command is not None:
            parser.error("--self-test cannot be combined with a command")
    elif args.command is None:
        parser.error("a create or verify command is required")
    return args


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.self_test:
            run_self_test()
            print("Pro macOS handoff evidence self-test passed.")
            return 0

        identity = _identity_from_args(args)
        if args.command == "create":
            manifest = create_handoff(
                args.staging_dir,
                args.dmg,
                args.pip_freeze,
                args.sha256s_and_build,
                identity,
            )
            digest = manifest["files"][identity.dmg_name]["sha256"]  # type: ignore[index]
            print(f"created verified Pro macOS handoff: {args.staging_dir} (sha256:{digest})")
        else:
            manifest = verify_handoff(args.staging_dir, identity)
            digest = manifest["files"][identity.dmg_name]["sha256"]  # type: ignore[index]
            print(f"verified Pro macOS handoff: {args.staging_dir} (sha256:{digest})")
        return 0
    except (HandoffError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
