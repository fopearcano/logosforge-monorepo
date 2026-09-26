"""HTTP validators for conditional Whiteboard resource persistence."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from fastapi import HTTPException, Request, status


ResourceKind = Literal["whiteboard", "outline", "psyke", "comments"]
IF_MATCH_HEADER = "If-Match"
MUTATION_ID_HEADER = "X-LogosForge-Mutation-Id"

_TAG_RE = re.compile(
    r'^"lfwb:(whiteboard|outline|psyke|comments):([0-9a-f]{32}):([0-9a-f]{32})"$'
)
_MUTATION_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


@dataclass(frozen=True)
class RevisionPrecondition:
    raw_etag: str
    revision: str
    matches_resource: bool


class ResourceProtocolError(HTTPException):
    """HTTP error rendered through the wrapper's structured ``error`` envelope."""


def resource_etag(kind: ResourceKind, incarnation: str, revision: str) -> str:
    """Build the one canonical strong ETag accepted by this API."""
    return f'"lfwb:{kind}:{incarnation}:{revision}"'


def request_revision_precondition(
    request: Request,
    kind: ResourceKind,
    incarnation: str,
    *,
    required: bool,
) -> RevisionPrecondition | None:
    """Parse one exact strong If-Match tag; lists, wildcards and weak tags fail."""
    raw = getattr(request, "headers", {}).get("if-match")
    if raw is None:
        if required:
            raise ResourceProtocolError(
                status_code=status.HTTP_428_PRECONDITION_REQUIRED,
                detail={
                    "code": "revision_precondition_required",
                    "message": "Reload this resource and retry with its current ETag.",
                },
            )
        return None
    value = raw.strip()
    match = _TAG_RE.fullmatch(value)
    if match is None:
        raise ResourceProtocolError(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "invalid_if_match",
                "message": "If-Match must contain one exact strong LogosForge resource ETag.",
            },
        )
    supplied_kind, supplied_incarnation, revision = match.groups()
    return RevisionPrecondition(
        raw_etag=value,
        revision=revision,
        matches_resource=(supplied_kind == kind and supplied_incarnation == incarnation),
    )


def request_mutation_id(request: Request, *, required: bool = False) -> str | None:
    raw = getattr(request, "headers", {}).get("x-logosforge-mutation-id")
    if raw is None:
        if required:
            raise ResourceProtocolError(
                status_code=status.HTTP_428_PRECONDITION_REQUIRED,
                detail={
                    "code": "mutation_id_required",
                    "message": (
                        "A mutation id is required for this conditional write."
                    ),
                },
            )
        return None
    value = raw.strip()
    if _MUTATION_ID_RE.fullmatch(value) is None:
        raise ResourceProtocolError(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "invalid_mutation_id",
                "message": "The mutation id must be 1-128 safe ASCII characters.",
            },
        )
    return value


def revision_conflict(
    kind: ResourceKind,
    incarnation: str,
    expected_revision: str,
    current_revision: str,
) -> ResourceProtocolError:
    current_etag = resource_etag(kind, incarnation, current_revision)
    return ResourceProtocolError(
        status_code=status.HTTP_409_CONFLICT,
        headers={"ETag": current_etag},
        detail={
            "code": "revision_conflict",
            "message": "The resource changed after it was loaded. Reload before saving again.",
            "expected_revision": expected_revision,
            "current_revision": current_revision,
            "current_etag": current_etag,
        },
    )


def mutation_id_conflict(mutation_id: str) -> ResourceProtocolError:
    return ResourceProtocolError(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "code": "mutation_id_conflict",
            "message": "This mutation id was already used for a different request.",
            "mutation_id": mutation_id,
        },
    )


def resource_already_exists(
    kind: ResourceKind,
    incarnation: str,
    current_revision: str,
) -> ResourceProtocolError:
    current_etag = resource_etag(kind, incarnation, current_revision)
    return ResourceProtocolError(
        status_code=status.HTTP_409_CONFLICT,
        headers={"ETag": current_etag},
        detail={
            "code": "resource_already_exists",
            "message": "This resource already exists; use a conditional PUT to update it.",
            "current_revision": current_revision,
            "current_etag": current_etag,
        },
    )
