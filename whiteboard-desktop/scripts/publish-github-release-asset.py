#!/usr/bin/env python3
"""Create or resolve a GitHub prerelease and publish one verified asset."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Protocol


API_VERSION = "2022-11-28"
MAX_JSON_BYTES = 8 * 1024 * 1024
MAX_NOTES_BYTES = 1024 * 1024
MAX_ASSET_BYTES = 2 * 1024 * 1024 * 1024
ASSET_PAGE_SIZE = 100
MAX_ASSET_PAGES = 100
READ_CHUNK_SIZE = 1024 * 1024

REPOSITORY_PATTERN = re.compile(
    r"(?=.{3,200}\Z)[A-Za-z0-9](?:[A-Za-z0-9_.-]{0,98}[A-Za-z0-9_.-])?"
    r"/[A-Za-z0-9](?:[A-Za-z0-9_.-]{0,98}[A-Za-z0-9_.-])?\Z"
)
TAG_PATTERN = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9._/+-]{0,126}[A-Za-z0-9._+-])?\Z")
SHA_PATTERN = re.compile(r"[0-9a-fA-F]{40}\Z")
SEMVER_PATTERN = re.compile(
    r"(?:0|[1-9][0-9]*)\."
    r"(?:0|[1-9][0-9]*)\."
    r"(?:0|[1-9][0-9]*)"
    r"(?:-(?:0|[1-9][0-9]*|[0-9A-Za-z-]*[A-Za-z-][0-9A-Za-z-]*)"
    r"(?:\.(?:0|[1-9][0-9]*|[0-9A-Za-z-]*[A-Za-z-][0-9A-Za-z-]*))*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?\Z"
)
DIGEST_PATTERN = re.compile(r"sha256:([0-9a-fA-F]{64})\Z")


class ValidationError(ValueError):
    """Raised when local input is unsafe or malformed."""


class PublishError(RuntimeError):
    """Raised when GitHub cannot safely complete the requested operation."""


@dataclass(frozen=True)
class HttpResponse:
    status: int
    body: bytes = b""


class Transport(Protocol):
    def request(
        self,
        method: str,
        url: str,
        headers: Mapping[str, str],
        body: bytes | BinaryIO | None = None,
    ) -> HttpResponse:
        """Perform one HTTPS request without following redirects."""


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(  # type: ignore[override]
        self,
        req: urllib.request.Request,
        fp: BinaryIO,
        code: int,
        msg: str,
        headers: Mapping[str, str],
        newurl: str,
    ) -> None:
        return None


class UrllibTransport:
    """Small standard-library HTTPS transport with bounded response reads."""

    def __init__(self, *, timeout_seconds: float = 900.0) -> None:
        self._timeout_seconds = timeout_seconds
        self._opener = urllib.request.build_opener(_NoRedirectHandler())

    @staticmethod
    def _read_response(response: BinaryIO) -> bytes:
        payload = response.read(MAX_JSON_BYTES + 1)
        if len(payload) > MAX_JSON_BYTES:
            raise PublishError("GitHub returned an unexpectedly large response")
        return payload

    def request(
        self,
        method: str,
        url: str,
        headers: Mapping[str, str],
        body: bytes | BinaryIO | None = None,
    ) -> HttpResponse:
        _validate_https_url(url, "request URL", allow_query=True)
        request = urllib.request.Request(
            url=url,
            data=body,  # urllib/http.client streams file objects in fixed-size blocks.
            headers=dict(headers),
            method=method,
        )
        try:
            with self._opener.open(request, timeout=self._timeout_seconds) as response:
                return HttpResponse(
                    status=int(response.status),
                    body=self._read_response(response),
                )
        except urllib.error.HTTPError as exc:
            try:
                payload = self._read_response(exc)
            finally:
                exc.close()
            return HttpResponse(status=int(exc.code), body=payload)
        except (OSError, urllib.error.URLError) as exc:
            raise PublishError("GitHub request failed because of a network or TLS error") from exc


@dataclass(frozen=True)
class PublishConfig:
    repository: str
    tag: str
    source_sha: str
    version: str
    notes_path: Path
    asset_path: Path
    upload_name: str
    api_url: str


@dataclass(frozen=True)
class PublishResult:
    release_id: int
    asset_name: str
    size: int
    digest: str
    action: str


@dataclass(frozen=True)
class _OpenAsset:
    stream: BinaryIO
    size: int
    identity: tuple[int, int, int, int]
    digest: str


def _expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _positive_integer(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise PublishError(f"GitHub returned an invalid {field}")
    return value


def _nonnegative_integer(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise PublishError(f"GitHub returned an invalid {field}")
    return value


def _validate_https_url(
    value: str,
    field: str,
    *,
    allow_query: bool = False,
) -> urllib.parse.SplitResult:
    try:
        parsed = urllib.parse.urlsplit(value)
        port = parsed.port
    except ValueError as exc:
        raise ValidationError(f"{field} is not a valid URL") from exc
    if parsed.scheme.lower() != "https":
        raise ValidationError(f"{field} must use HTTPS")
    if not parsed.hostname or parsed.username is not None or parsed.password is not None:
        raise ValidationError(f"{field} must have a host and no user information")
    if (parsed.query and not allow_query) or parsed.fragment:
        suffix = "fragment" if allow_query else "query or fragment"
        raise ValidationError(f"{field} must not contain a {suffix}")
    if port is not None and not 1 <= port <= 65535:
        raise ValidationError(f"{field} contains an invalid port")
    return parsed


def _normalize_api_url(value: str) -> str:
    if not isinstance(value, str) or value != value.strip() or not value:
        raise ValidationError("API URL is required and cannot contain outer whitespace")
    parsed = _validate_https_url(value, "API URL")
    if parsed.path and not parsed.path.startswith("/"):
        raise ValidationError("API URL path is invalid")
    return value.rstrip("/")


def _validate_config(config: PublishConfig) -> PublishConfig:
    repository = config.repository
    if not isinstance(repository, str) or REPOSITORY_PATTERN.fullmatch(repository) is None:
        raise ValidationError("repository must be an OWNER/REPO name using safe ASCII characters")
    if any(piece in {".", ".."} for piece in repository.split("/")):
        raise ValidationError("repository contains an unsafe path component")

    tag = config.tag
    if not isinstance(tag, str) or TAG_PATTERN.fullmatch(tag) is None:
        raise ValidationError("tag contains unsupported characters or has an invalid length")
    if "//" in tag or any(piece in {".", ".."} for piece in tag.split("/")):
        raise ValidationError("tag contains an unsafe path component")

    if not isinstance(config.source_sha, str) or SHA_PATTERN.fullmatch(config.source_sha) is None:
        raise ValidationError("source SHA must be a complete 40-character hexadecimal commit ID")
    if not isinstance(config.version, str) or len(config.version) > 128:
        raise ValidationError("version is invalid")
    if SEMVER_PATTERN.fullmatch(config.version) is None:
        raise ValidationError("version must be a valid semantic version")
    expected_tag = f"whiteboard-v{config.version}"
    if tag != expected_tag:
        raise ValidationError(f"tag must exactly match the product version: {expected_tag}")

    name = config.upload_name
    if (
        not isinstance(name, str)
        or not name
        or name != name.strip()
        or name in {".", ".."}
        or "/" in name
        or "\\" in name
        or any(ord(character) < 32 or ord(character) == 127 for character in name)
        or len(name.encode("utf-8")) > 255
    ):
        raise ValidationError("upload name must be a safe filename of at most 255 UTF-8 bytes")
    expected_name = f"LogosForge.Whiteboard-{config.version}-x64.dmg"
    if name != expected_name:
        raise ValidationError(f"upload name must exactly match the product version: {expected_name}")

    api_url = _normalize_api_url(config.api_url)
    return PublishConfig(
        repository=repository,
        tag=tag,
        source_sha=config.source_sha.lower(),
        version=config.version,
        notes_path=Path(config.notes_path),
        asset_path=Path(config.asset_path),
        upload_name=name,
        api_url=api_url,
    )


def _open_read_only(path: Path) -> int:
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        return os.open(path, flags)
    except OSError as exc:
        raise ValidationError(f"cannot safely open input file: {path}") from exc


def _file_identity(file_stat: os.stat_result) -> tuple[int, int, int, int]:
    return (
        file_stat.st_dev,
        file_stat.st_ino,
        file_stat.st_size,
        file_stat.st_mtime_ns,
    )


def _read_notes(path: Path) -> str:
    descriptor = _open_read_only(path)
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise ValidationError("release notes must be a regular file")
        if before.st_size < 1 or before.st_size > MAX_NOTES_BYTES:
            raise ValidationError("release notes must be between 1 byte and 1 MiB")
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(descriptor, min(READ_CHUNK_SIZE, MAX_NOTES_BYTES + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > MAX_NOTES_BYTES:
                raise ValidationError("release notes exceed the 1 MiB limit")
        after = os.fstat(descriptor)
        if _file_identity(before) != _file_identity(after):
            raise ValidationError("release notes changed while they were being read")
    finally:
        os.close(descriptor)

    try:
        notes = b"".join(chunks).decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValidationError("release notes must be valid UTF-8") from exc
    if not notes.strip() or "\x00" in notes:
        raise ValidationError("release notes must contain non-NUL text")
    return notes


def _open_asset(path: Path) -> _OpenAsset:
    descriptor = _open_read_only(path)
    stream: BinaryIO | None = None
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise ValidationError("release asset must be a regular file")
        if before.st_size < 1 or before.st_size > MAX_ASSET_BYTES:
            raise ValidationError("release asset must be between 1 byte and 2 GiB")

        stream = os.fdopen(descriptor, "rb", buffering=READ_CHUNK_SIZE)
        descriptor = -1
        digest = hashlib.sha256()
        while chunk := stream.read(READ_CHUNK_SIZE):
            digest.update(chunk)
        after = os.fstat(stream.fileno())
        identity = _file_identity(before)
        if identity != _file_identity(after):
            raise ValidationError("release asset changed while it was being hashed")
        stream.seek(0)
        return _OpenAsset(
            stream=stream,
            size=before.st_size,
            identity=identity,
            digest=f"sha256:{digest.hexdigest()}",
        )
    except Exception:
        if stream is not None:
            stream.close()
        elif descriptor >= 0:
            os.close(descriptor)
        raise


def _json_payload(response: HttpResponse, operation: str) -> object:
    if len(response.body) > MAX_JSON_BYTES:
        raise PublishError(f"{operation} returned an unexpectedly large response")
    try:
        return json.loads(response.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PublishError(f"{operation} returned malformed JSON") from exc


def _headers(token: str) -> dict[str, str]:
    return {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "User-Agent": "LogosForge-release-asset-publisher/1",
        "X-GitHub-Api-Version": API_VERSION,
    }


def _request(
    transport: Transport,
    method: str,
    url: str,
    headers: Mapping[str, str],
    body: bytes | BinaryIO | None = None,
) -> HttpResponse:
    try:
        response = transport.request(method, url, headers, body)
    except (ValidationError, PublishError):
        raise
    except Exception as exc:
        raise PublishError("GitHub request failed unexpectedly") from exc
    if isinstance(response.status, bool) or not isinstance(response.status, int):
        raise PublishError("GitHub transport returned an invalid HTTP status")
    return response


def _release_endpoint(config: PublishConfig) -> str:
    return f"{config.api_url}/repos/{config.repository}/releases"


def _resolve_release(
    config: PublishConfig,
    notes: str,
    transport: Transport,
    headers: Mapping[str, str],
) -> dict[str, object]:
    endpoint = _release_endpoint(config)
    encoded_tag = urllib.parse.quote(config.tag, safe="")
    lookup_url = f"{endpoint}/tags/{encoded_tag}"
    response = _request(transport, "GET", lookup_url, headers)

    if response.status == 404:
        payload = json.dumps(
            {
                "tag_name": config.tag,
                "target_commitish": config.source_sha,
                "name": f"LogosForge Whiteboard {config.version} (Alpha)",
                "body": notes,
                "draft": False,
                "prerelease": True,
                "make_latest": "false",
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        create_headers = dict(headers)
        create_headers["Content-Type"] = "application/json; charset=utf-8"
        create_headers["Content-Length"] = str(len(payload))
        response = _request(transport, "POST", endpoint, create_headers, payload)
        if response.status == 422:
            response = _request(transport, "GET", lookup_url, headers)
            if response.status != 200:
                raise PublishError(
                    "release creation raced with another publisher, but the release could not be refetched"
                )
        elif response.status != 201:
            raise PublishError(f"release creation returned HTTP {response.status}")
    elif response.status != 200:
        raise PublishError(f"release lookup returned HTTP {response.status}")

    parsed = _json_payload(response, "release lookup or creation")
    if not isinstance(parsed, dict):
        raise PublishError("GitHub returned a non-object release")
    if parsed.get("tag_name") != config.tag:
        raise PublishError("resolved release tag does not match the requested tag")
    if parsed.get("prerelease") is not True or parsed.get("draft") is not False:
        raise PublishError("resolved release is not a published prerelease")
    _positive_integer(parsed.get("id"), "release ID")
    return parsed


def _validated_upload_url(
    raw_value: object,
    config: PublishConfig,
    release_id: int,
) -> str:
    if not isinstance(raw_value, str) or not raw_value:
        raise PublishError("resolved release has no upload URL")
    if "{" in raw_value:
        base, template = raw_value.split("{", 1)
        if "{" + template != "{?name,label}":
            raise PublishError("resolved release has an unsupported upload URL template")
    else:
        base = raw_value
    try:
        upload_parts = _validate_https_url(base, "release upload URL")
    except ValidationError as exc:
        raise PublishError(str(exc)) from exc
    api_parts = _validate_https_url(config.api_url, "API URL")

    upload_authority = (upload_parts.hostname.lower(), upload_parts.port)
    api_authority = (api_parts.hostname.lower(), api_parts.port)
    public_pair = (
        api_parts.hostname.lower() == "api.github.com"
        and api_parts.port is None
        and upload_parts.hostname.lower() == "uploads.github.com"
        and upload_parts.port is None
    )
    if upload_authority != api_authority and not public_pair:
        raise PublishError("release upload URL points to an unexpected host")

    expected_suffix = f"/repos/{config.repository}/releases/{release_id}/assets"
    if not upload_parts.path.endswith(expected_suffix):
        raise PublishError("release upload URL does not match the requested repository and release")
    return base


def _list_exact_asset(
    config: PublishConfig,
    release_id: int,
    transport: Transport,
    headers: Mapping[str, str],
) -> dict[str, object] | None:
    matches: list[dict[str, object]] = []
    endpoint = f"{_release_endpoint(config)}/{release_id}/assets"
    for page in range(1, MAX_ASSET_PAGES + 1):
        response = _request(
            transport,
            "GET",
            f"{endpoint}?per_page={ASSET_PAGE_SIZE}&page={page}",
            headers,
        )
        if response.status != 200:
            raise PublishError(f"release asset listing returned HTTP {response.status}")
        parsed = _json_payload(response, "release asset listing")
        if not isinstance(parsed, list):
            raise PublishError("GitHub returned a non-list release asset listing")
        for item in parsed:
            if not isinstance(item, dict):
                raise PublishError("GitHub returned an invalid release asset entry")
            if item.get("name") == config.upload_name:
                matches.append(item)
        if len(parsed) < ASSET_PAGE_SIZE:
            break
    else:
        raise PublishError("release has too many assets to inspect safely")

    if len(matches) > 1:
        raise PublishError("release contains multiple assets with the requested exact name")
    return matches[0] if matches else None


def _normalized_digest(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise PublishError(f"GitHub returned a missing or invalid {field}")
    match = DIGEST_PATTERN.fullmatch(value)
    if match is None:
        raise PublishError(f"GitHub returned a missing or invalid {field}")
    return f"sha256:{match.group(1).lower()}"


def _existing_asset_matches(asset: dict[str, object], opened: _OpenAsset) -> bool:
    if asset.get("state") != "uploaded":
        return False
    size = asset.get("size")
    if isinstance(size, bool) or not isinstance(size, int) or size != opened.size:
        return False
    digest = asset.get("digest")
    if not isinstance(digest, str) or DIGEST_PATTERN.fullmatch(digest) is None:
        return False
    return _normalized_digest(digest, "asset digest") == opened.digest


def _verify_unchanged(opened: _OpenAsset) -> None:
    try:
        current = os.fstat(opened.stream.fileno())
    except OSError as exc:
        raise ValidationError("release asset became unavailable during publishing") from exc
    if _file_identity(current) != opened.identity:
        raise ValidationError("release asset changed during publishing")


def publish_release_asset(
    config: PublishConfig,
    token: str,
    *,
    transport: Transport | None = None,
) -> PublishResult:
    """Publish one asset, replacing only an exact-name nonmatching asset."""

    config = _validate_config(config)
    if (
        not isinstance(token, str)
        or not token
        or token != token.strip()
        or any(ord(character) < 33 or ord(character) == 127 for character in token)
    ):
        raise ValidationError("GITHUB_TOKEN is missing or malformed")

    notes = _read_notes(config.notes_path)
    opened = _open_asset(config.asset_path)
    request_transport = transport if transport is not None else UrllibTransport()
    request_headers = _headers(token)
    try:
        release = _resolve_release(config, notes, request_transport, request_headers)
        release_id = _positive_integer(release.get("id"), "release ID")
        upload_url = _validated_upload_url(release.get("upload_url"), config, release_id)
        existing = _list_exact_asset(
            config,
            release_id,
            request_transport,
            request_headers,
        )

        if existing is not None and _existing_asset_matches(existing, opened):
            _verify_unchanged(opened)
            return PublishResult(
                release_id=release_id,
                asset_name=config.upload_name,
                size=opened.size,
                digest=opened.digest,
                action="unchanged",
            )

        if existing is not None:
            asset_id = _positive_integer(existing.get("id"), "existing asset ID")
            delete_url = f"{config.api_url}/repos/{config.repository}/releases/assets/{asset_id}"
            response = _request(
                request_transport,
                "DELETE",
                delete_url,
                request_headers,
            )
            if response.status != 204:
                raise PublishError(f"existing release asset deletion returned HTTP {response.status}")

        opened.stream.seek(0)
        upload_headers = dict(request_headers)
        upload_headers["Content-Type"] = "application/octet-stream"
        upload_headers["Content-Length"] = str(opened.size)
        encoded_name = urllib.parse.quote(config.upload_name, safe="")
        response = _request(
            request_transport,
            "POST",
            f"{upload_url}?name={encoded_name}",
            upload_headers,
            opened.stream,
        )
        _verify_unchanged(opened)
        if response.status != 201:
            raise PublishError(f"release asset upload returned HTTP {response.status}")
        uploaded = _json_payload(response, "release asset upload")
        if not isinstance(uploaded, dict):
            raise PublishError("GitHub returned a non-object uploaded asset")
        if uploaded.get("name") != config.upload_name:
            raise PublishError("uploaded asset name does not match the requested name")
        if uploaded.get("state") != "uploaded":
            raise PublishError("uploaded asset is not in the uploaded state")
        if _nonnegative_integer(uploaded.get("size"), "uploaded asset size") != opened.size:
            raise PublishError("uploaded asset size does not match the local file")
        if _normalized_digest(uploaded.get("digest"), "uploaded asset digest") != opened.digest:
            raise PublishError("uploaded asset digest does not match the local file")

        return PublishResult(
            release_id=release_id,
            asset_name=config.upload_name,
            size=opened.size,
            digest=opened.digest,
            action="uploaded",
        )
    finally:
        opened.stream.close()


class _FakeTransport:
    def __init__(self, handler: object) -> None:
        self.handler = handler
        self.calls: list[tuple[str, str]] = []

    def request(
        self,
        method: str,
        url: str,
        headers: Mapping[str, str],
        body: bytes | BinaryIO | None = None,
    ) -> HttpResponse:
        self.calls.append((method, url))
        return self.handler(method, url, headers, body)  # type: ignore[operator]


def _json_response(status: int, value: object) -> HttpResponse:
    return HttpResponse(status, json.dumps(value, separators=(",", ":")).encode("utf-8"))


def _self_test_release(config: PublishConfig, release_id: int = 73) -> dict[str, object]:
    return {
        "id": release_id,
        "tag_name": config.tag,
        "draft": False,
        "prerelease": True,
        "upload_url": (
            f"{config.api_url}/repos/{config.repository}/releases/{release_id}/assets"
            "{?name,label}"
        ),
    }


def _read_fake_upload(body: bytes | BinaryIO | None) -> bytes:
    _expect(body is not None and not isinstance(body, bytes), "asset was buffered instead of streamed")
    chunks: list[bytes] = []
    while True:
        chunk = body.read(2)  # type: ignore[union-attr]
        if not chunk:
            break
        chunks.append(chunk)
    return b"".join(chunks)


def run_self_test() -> None:
    token = "self-test-secret-token"
    asset_bytes = b"a streamed fake disk image\n"
    asset_digest = f"sha256:{hashlib.sha256(asset_bytes).hexdigest()}"

    with tempfile.TemporaryDirectory(prefix="logosforge-release-publisher-") as temp:
        root = Path(temp)
        notes_path = root / "notes.md"
        asset_path = root / "candidate.dmg"
        notes_path.write_text("Self-test release notes.\n", encoding="utf-8")
        asset_path.write_bytes(asset_bytes)
        config = PublishConfig(
            repository="example/logosforge",
            tag="whiteboard-v1.2.3",
            source_sha="0123456789abcdef0123456789abcdef01234567",
            version="1.2.3",
            notes_path=notes_path,
            asset_path=asset_path,
            upload_name="LogosForge.Whiteboard-1.2.3-x64.dmg",
            api_url="https://api.example.test",
        )
        metadata_config = PublishConfig(
            **{
                **config.__dict__,
                "tag": "whiteboard-v1.2.3+mac12",
                "version": "1.2.3+mac12",
                "upload_name": "LogosForge.Whiteboard-1.2.3+mac12-x64.dmg",
            }
        )
        _expect(
            _validate_config(metadata_config).tag == metadata_config.tag,
            "matching SemVer build metadata was rejected",
        )
        release = _self_test_release(config)
        releases_url = f"{config.api_url}/repos/{config.repository}/releases"
        lookup_url = f"{releases_url}/tags/{config.tag}"
        assets_url = f"{releases_url}/73/assets?per_page=100&page=1"
        upload_url = (
            f"{config.api_url}/repos/{config.repository}/releases/73/assets"
            f"?name={urllib.parse.quote(config.upload_name, safe='')}"
        )

        # A concurrent creator wins between the initial 404 and this POST's 422.
        create_steps = iter(["lookup-404", "create-422", "refetch", "list", "upload"])

        def create_race_handler(
            method: str,
            url: str,
            headers: Mapping[str, str],
            body: bytes | BinaryIO | None,
        ) -> HttpResponse:
            step = next(create_steps)
            _expect(headers.get("Authorization") == f"Bearer {token}", "authorization missing")
            if step == "lookup-404":
                _expect((method, url) == ("GET", lookup_url), "unexpected initial lookup")
                return HttpResponse(404)
            if step == "create-422":
                _expect((method, url) == ("POST", releases_url), "unexpected create request")
                _expect(isinstance(body, bytes), "release payload was not buffered JSON")
                payload = json.loads(body.decode("utf-8"))
                _expect(payload["target_commitish"] == config.source_sha, "source SHA omitted")
                _expect(payload["prerelease"] is True, "release was not created as a prerelease")
                return _json_response(422, {"message": "already_exists"})
            if step == "refetch":
                _expect((method, url) == ("GET", lookup_url), "create race was not refetched")
                return _json_response(200, release)
            if step == "list":
                _expect((method, url) == ("GET", assets_url), "assets were not listed")
                return _json_response(200, [])
            _expect((method, url) == ("POST", upload_url), "unexpected upload request")
            uploaded = _read_fake_upload(body)
            _expect(uploaded == asset_bytes, "streamed upload content changed")
            return _json_response(
                201,
                {
                    "id": 91,
                    "name": config.upload_name,
                    "state": "uploaded",
                    "size": len(uploaded),
                    "digest": asset_digest,
                },
            )

        race_transport = _FakeTransport(create_race_handler)
        result = publish_release_asset(config, token, transport=race_transport)
        _expect(result.action == "uploaded", "create-race upload did not complete")
        try:
            next(create_steps)
        except StopIteration:
            pass
        else:
            raise AssertionError("create-race scenario omitted expected calls")

        # Matching size plus SHA-256 is a no-op.
        matching_asset = {
            "id": 91,
            "name": config.upload_name,
            "state": "uploaded",
            "size": len(asset_bytes),
            "digest": asset_digest.upper().replace("SHA256", "sha256"),
        }

        def idempotent_handler(
            method: str,
            url: str,
            headers: Mapping[str, str],
            body: bytes | BinaryIO | None,
        ) -> HttpResponse:
            del headers, body
            if (method, url) == ("GET", lookup_url):
                return _json_response(200, release)
            if (method, url) == ("GET", assets_url):
                return _json_response(200, [matching_asset])
            raise AssertionError("idempotent publish performed a mutation")

        idempotent_transport = _FakeTransport(idempotent_handler)
        result = publish_release_asset(config, token, transport=idempotent_transport)
        _expect(result.action == "unchanged", "matching asset was not idempotent")
        _expect(len(idempotent_transport.calls) == 2, "matching asset made extra requests")

        # A mismatching exact-name asset is deleted, then the source is streamed.
        replacement_steps = iter(["lookup", "list", "delete", "upload"])

        def replacement_handler(
            method: str,
            url: str,
            headers: Mapping[str, str],
            body: bytes | BinaryIO | None,
        ) -> HttpResponse:
            del headers
            step = next(replacement_steps)
            if step == "lookup":
                _expect((method, url) == ("GET", lookup_url), "unexpected replacement lookup")
                return _json_response(200, release)
            if step == "list":
                _expect((method, url) == ("GET", assets_url), "unexpected replacement listing")
                return _json_response(
                    200,
                    [
                        {
                            **matching_asset,
                            "digest": "sha256:" + "0" * 64,
                        }
                    ],
                )
            if step == "delete":
                expected = f"{config.api_url}/repos/{config.repository}/releases/assets/91"
                _expect((method, url) == ("DELETE", expected), "wrong asset was deleted")
                return HttpResponse(204)
            _expect((method, url) == ("POST", upload_url), "replacement was not uploaded")
            uploaded = _read_fake_upload(body)
            return _json_response(
                201,
                {
                    "id": 92,
                    "name": config.upload_name,
                    "state": "uploaded",
                    "size": len(uploaded),
                    "digest": f"sha256:{hashlib.sha256(uploaded).hexdigest()}",
                },
            )

        replacement_transport = _FakeTransport(replacement_handler)
        result = publish_release_asset(config, token, transport=replacement_transport)
        _expect(result.action == "uploaded", "mismatching asset was not replaced")

        # Error paths reject unsafe URLs, bad release metadata, duplicates, and
        # an upload whose server-computed digest does not match the source.
        insecure = PublishConfig(**{**config.__dict__, "api_url": "http://api.example.test"})
        try:
            publish_release_asset(insecure, token, transport=idempotent_transport)
        except ValidationError as exc:
            _expect("HTTPS" in str(exc), "unsafe URL error was not specific")
        else:
            raise AssertionError("an HTTP API URL was accepted")

        mismatched_tag = PublishConfig(
            **{**config.__dict__, "tag": "whiteboard-v1.2.4"}
        )
        try:
            publish_release_asset(mismatched_tag, token, transport=idempotent_transport)
        except ValidationError as exc:
            _expect("product version" in str(exc), "tag/version mismatch was not specific")
        else:
            raise AssertionError("a tag/version mismatch was accepted")

        mismatched_name = PublishConfig(
            **{
                **config.__dict__,
                "upload_name": "LogosForge.Whiteboard-1.2.4-x64.dmg",
            }
        )
        try:
            publish_release_asset(mismatched_name, token, transport=idempotent_transport)
        except ValidationError as exc:
            _expect("product version" in str(exc), "name/version mismatch was not specific")
        else:
            raise AssertionError("an upload-name/version mismatch was accepted")

        wrong_release = {**release, "prerelease": False}

        def wrong_release_handler(
            method: str,
            url: str,
            headers: Mapping[str, str],
            body: bytes | BinaryIO | None,
        ) -> HttpResponse:
            del method, url, headers, body
            return _json_response(200, wrong_release)

        try:
            publish_release_asset(config, token, transport=_FakeTransport(wrong_release_handler))
        except PublishError as exc:
            _expect("prerelease" in str(exc), "wrong release kind was not diagnosed")
        else:
            raise AssertionError("a non-prerelease was accepted")

        def duplicate_handler(
            method: str,
            url: str,
            headers: Mapping[str, str],
            body: bytes | BinaryIO | None,
        ) -> HttpResponse:
            del headers, body
            if (method, url) == ("GET", lookup_url):
                return _json_response(200, release)
            if (method, url) == ("GET", assets_url):
                return _json_response(200, [matching_asset, {**matching_asset, "id": 92}])
            raise AssertionError("duplicate test made an unexpected request")

        try:
            publish_release_asset(config, token, transport=_FakeTransport(duplicate_handler))
        except PublishError as exc:
            _expect("multiple assets" in str(exc), "duplicate exact names were not diagnosed")
        else:
            raise AssertionError("duplicate exact-name assets were accepted")

        def bad_digest_handler(
            method: str,
            url: str,
            headers: Mapping[str, str],
            body: bytes | BinaryIO | None,
        ) -> HttpResponse:
            del headers
            if (method, url) == ("GET", lookup_url):
                return _json_response(200, release)
            if (method, url) == ("GET", assets_url):
                return _json_response(200, [])
            if (method, url) == ("POST", upload_url):
                uploaded = _read_fake_upload(body)
                return _json_response(
                    201,
                    {
                        "id": 93,
                        "name": config.upload_name,
                        "state": "uploaded",
                        "size": len(uploaded),
                        "digest": "sha256:" + "f" * 64,
                    },
                )
            raise AssertionError("bad-digest test made an unexpected request")

        try:
            publish_release_asset(config, token, transport=_FakeTransport(bad_digest_handler))
        except PublishError as exc:
            _expect("digest" in str(exc), "bad uploaded digest was not diagnosed")
            _expect(token not in str(exc), "an error exposed the token")
        else:
            raise AssertionError("a mismatching uploaded digest was accepted")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", help="GitHub repository as OWNER/REPO")
    parser.add_argument("--tag", help="exact release tag")
    parser.add_argument("--source-sha", help="full source commit SHA")
    parser.add_argument("--version", help="semantic product version")
    parser.add_argument("--notes", type=Path, help="UTF-8 release-notes file")
    parser.add_argument("--asset", type=Path, help="local release asset")
    parser.add_argument("--upload-name", help="exact GitHub asset filename")
    parser.add_argument("--api-url", help="GitHub HTTPS API base URL")
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="exercise all publishing branches with a fake transport and no network",
    )
    args = parser.parse_args(argv)
    supplied = {
        name: getattr(args, name)
        for name in (
            "repo",
            "tag",
            "source_sha",
            "version",
            "notes",
            "asset",
            "upload_name",
            "api_url",
        )
        if getattr(args, name) is not None
    }
    if args.self_test:
        if supplied:
            parser.error("publishing arguments cannot be combined with --self-test")
    elif len(supplied) != 8:
        missing = sorted(
            name.replace("_", "-")
            for name in (
                "repo",
                "tag",
                "source_sha",
                "version",
                "notes",
                "asset",
                "upload_name",
                "api_url",
            )
            if getattr(args, name) is None
        )
        parser.error("the following arguments are required: " + ", ".join(f"--{x}" for x in missing))
    return args


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.self_test:
        run_self_test()
        print("GitHub release-asset publisher self-test passed.")
        return 0

    token = os.environ.get("GITHUB_TOKEN", "")
    config = PublishConfig(
        repository=args.repo,
        tag=args.tag,
        source_sha=args.source_sha,
        version=args.version,
        notes_path=args.notes,
        asset_path=args.asset,
        upload_name=args.upload_name,
        api_url=args.api_url,
    )
    try:
        result = publish_release_asset(config, token)
    except (ValidationError, PublishError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(
        f"release asset {result.action}: {result.asset_name} "
        f"({result.size} bytes, {result.digest}) on release {result.release_id}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
