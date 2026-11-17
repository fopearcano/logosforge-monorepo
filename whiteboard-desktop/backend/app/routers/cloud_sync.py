"""Internal lossless restore used by Whiteboard Cloud Folder Sync.

This route is intentionally separate from the user-facing import commands.
``.lfbundle`` remains the one-way Whiteboard -> Pro transfer format; cloud sync
uses the same complete project payload only as a validated snapshot and always
restores it copy-on-write under a fresh core/local document identity.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import math
import threading
from decimal import Decimal
from collections import defaultdict
from contextlib import asynccontextmanager
from typing import Any, Literal
from uuid import uuid4

import httpx
from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core_client import core_error_message
from app.document_lifecycle import (
    complete_core_allocation,
    document_identity_publication,
    document_lifecycle_lock,
    locked_document_lifecycle,
    request_document_incarnation,
    require_document_incarnation,
)
from app.local_state import (
    CloudRestorePending,
    CloudRestorePreparedValidators,
    CloudRestoreReceipt,
    Comment,
    DrafterPage,
    LocalStateError,
    WhiteboardBlock,
    WhiteboardCreate,
    WhiteboardDocument,
    cloud_restore_receipt_store,
    comments_store,
    drafter_pages_store,
    outline_items_store,
    whiteboard_store,
)
from app.persistence_order import (
    begin_document_delete,
    cancel_document_delete,
    create_document_incarnation,
    request_delete_order_floors,
)
from app.resource_revision import resource_etag
from app.routers.documents import (
    _cleanup_local_document_state,
    _settle_unpublished_core_project_uninterruptibly,
)
from app.routers.export import (
    BUNDLE_FORMAT,
    BUNDLE_VERSION,
    SOURCE_APP,
    assemble_project_bundle,
)
from app.routers.psyke import _collection_digest, _collection_snapshot

router = APIRouter()
_RESTORE_LOCKS_GUARD = threading.Lock()
_RESTORE_LOCKS: dict[str, tuple[asyncio.Lock, int]] = {}


@asynccontextmanager
async def _serialized_restore(restore_id: str):
    """Serialize identical retry ids without retaining an unbounded lock map."""
    with _RESTORE_LOCKS_GUARD:
        lock, users = _RESTORE_LOCKS.get(restore_id, (asyncio.Lock(), 0))
        _RESTORE_LOCKS[restore_id] = (lock, users + 1)
    acquired = False
    try:
        await lock.acquire()
        acquired = True
        yield
    finally:
        if acquired:
            lock.release()
        with _RESTORE_LOCKS_GUARD:
            current, users = _RESTORE_LOCKS[restore_id]
            if current is lock and users == 1:
                _RESTORE_LOCKS.pop(restore_id, None)
            else:
                _RESTORE_LOCKS[restore_id] = (current, users - 1)


def _positive_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


class _BundleSource(BaseModel):
    app: Literal["logosforge-whiteboard"]


class _BundleManuscript(BaseModel):
    blocks: list[WhiteboardBlock] = Field(default_factory=list)


class _BundleDrafter(BaseModel):
    pages: list[DrafterPage] = Field(default_factory=list)


class _BundlePsykeEntry(BaseModel):
    id: str
    name: str = Field(min_length=1)
    entry_type: str = Field(default="other", min_length=1)
    aliases: list[str] = Field(default_factory=list)
    description: str = ""
    notes: str = ""
    created_at: Any = None
    updated_at: Any = None

    @field_validator("id")
    @classmethod
    def validate_source_id(cls, value: str) -> str:
        try:
            parsed = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "PSYKE entry id must be a positive integer string"
            ) from exc
        if parsed < 1 or str(parsed) != value:
            raise ValueError("PSYKE entry id must be a positive integer string")
        return value


class _BundlePsykeRelation(BaseModel):
    id: str
    source_id: int = Field(gt=0, strict=True)
    target_id: int = Field(gt=0, strict=True)
    source: str = ""
    target: str = ""
    relation_type: str = ""

    @model_validator(mode="after")
    def validate_pair(self) -> _BundlePsykeRelation:
        if self.source_id == self.target_id:
            raise ValueError("PSYKE relations require two distinct entries")
        if self.id != f"{self.source_id}:{self.target_id}":
            raise ValueError("PSYKE relation id does not match its endpoints")
        return self


class _BundleLegacyProgression(BaseModel):
    id: int = Field(gt=0, strict=True)
    entry_id: int = Field(gt=0, strict=True)
    text: str = Field(min_length=1)
    scene_id: int | None = Field(default=None, gt=0, strict=True)
    scene_title: str = ""
    sort_order: int = Field(default=0, ge=0, strict=True)

    @model_validator(mode="after")
    def reject_scene_anchor(self) -> _BundleLegacyProgression:
        # Whiteboard has one block document rather than core scenes. A scene id
        # cannot be remapped losslessly into a fresh Whiteboard project.
        if self.scene_id is not None:
            raise ValueError(
                "Whiteboard cloud snapshots cannot contain scene-anchored PSYKE progressions"
            )
        return self


class _BundlePsyke(BaseModel):
    elements: list[_BundlePsykeEntry] = Field(default_factory=list)
    relations: list[_BundlePsykeRelation] = Field(default_factory=list)
    progressions: list[_BundleLegacyProgression] = Field(default_factory=list)


class _BundleProgressionBeat(BaseModel):
    id: int = Field(gt=0, strict=True)
    track_id: int = Field(gt=0, strict=True)
    text: str = Field(min_length=1, max_length=50_000)
    sort_order: int = Field(ge=0, strict=True)
    anchor_kind: Literal["unanchored", "scene", "document_block"]
    scene_id: int | None = Field(default=None, gt=0, strict=True)
    scene_title: str = ""
    anchor_ref: str | None = None
    anchor_label: str = Field(default="", max_length=500)

    @model_validator(mode="after")
    def validate_anchor(self) -> _BundleProgressionBeat:
        if self.anchor_kind == "scene":
            raise ValueError(
                "Whiteboard cloud snapshots cannot contain scene-anchored progression beats"
            )
        if self.anchor_kind == "unanchored" and (
            self.scene_id is not None
            or self.anchor_ref is not None
            or self.anchor_label
        ):
            raise ValueError("unanchored progression beats cannot contain anchor data")
        if self.anchor_kind == "document_block" and (
            self.scene_id is not None or not (self.anchor_ref or "").strip()
        ):
            raise ValueError(
                "document-block progression beats require an anchor_ref only"
            )
        return self


class _BundleProgressionTrack(BaseModel):
    id: int = Field(gt=0, strict=True)
    kind: Literal["story", "character", "relationship", "theme", "world", "custom"]
    title: str = Field(min_length=1, max_length=500)
    description: str = Field(default="", max_length=10_000)
    color_label: str = Field(default="", max_length=100)
    sort_order: int = Field(ge=0, strict=True)
    legacy_compatibility: bool = False
    primary_psyke_entry_id: int | None = Field(default=None, gt=0, strict=True)
    primary_psyke_entry_name: str = ""
    primary_psyke_entry_type: str = ""
    secondary_psyke_entry_id: int | None = Field(default=None, gt=0, strict=True)
    secondary_psyke_entry_name: str = ""
    secondary_psyke_entry_type: str = ""
    beats: list[_BundleProgressionBeat] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_beats(self) -> _BundleProgressionTrack:
        if any(beat.track_id != self.id for beat in self.beats):
            raise ValueError("progression beat track_id does not match its track")
        if len({beat.id for beat in self.beats}) != len(self.beats):
            raise ValueError("progression beat ids must be unique within a track")
        return self


class _BundleProject(BaseModel):
    id: str
    title: str = Field(min_length=1, max_length=500)
    mode: str
    settings: dict[str, Any] = Field(default_factory=dict)
    manuscript: _BundleManuscript
    outline: list[dict[str, Any]] = Field(default_factory=list)
    comments: list[Comment] = Field(default_factory=list)
    drafter: _BundleDrafter = Field(default_factory=_BundleDrafter)
    psyke: _BundlePsyke = Field(default_factory=_BundlePsyke)
    progression_tracks: list[_BundleProgressionTrack] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_complete_graph(self) -> _BundleProject:
        element_ids = [int(entry.id) for entry in self.psyke.elements]
        if len(element_ids) != len(set(element_ids)):
            raise ValueError("PSYKE entry ids must be unique")
        known = set(element_ids)

        relation_pairs: set[tuple[int, int]] = set()
        for relation in self.psyke.relations:
            if relation.source_id not in known or relation.target_id not in known:
                raise ValueError("PSYKE relation references an unknown entry")
            pair = (
                min(relation.source_id, relation.target_id),
                max(relation.source_id, relation.target_id),
            )
            if pair in relation_pairs:
                raise ValueError("PSYKE relation endpoint pairs must be unique")
            relation_pairs.add(pair)

        progression_ids: set[int] = set()
        for progression in self.psyke.progressions:
            if progression.id in progression_ids:
                raise ValueError("PSYKE progression ids must be unique")
            progression_ids.add(progression.id)
            if progression.entry_id not in known:
                raise ValueError("PSYKE progression references an unknown entry")

        track_ids: set[int] = set()
        beat_ids: set[int] = set()
        for track in self.progression_tracks:
            if track.id in track_ids:
                raise ValueError("progression track ids must be unique")
            track_ids.add(track.id)
            for subject in (
                track.primary_psyke_entry_id,
                track.secondary_psyke_entry_id,
            ):
                if subject is not None and subject not in known:
                    raise ValueError(
                        "progression track references an unknown PSYKE entry"
                    )
            for beat in track.beats:
                if beat.id in beat_ids:
                    raise ValueError("progression beat ids must be globally unique")
                beat_ids.add(beat.id)

        comment_ids = [comment.id for comment in self.comments]
        if len(comment_ids) != len(set(comment_ids)):
            raise ValueError("comment ids must be unique")
        reply_ids = [reply.id for comment in self.comments for reply in comment.replies]
        if len(reply_ids) != len(set(reply_ids)):
            raise ValueError("comment reply ids must be unique")
        return self


class CloudProjectBundle(BaseModel):
    model_config = ConfigDict(extra="ignore")

    format: Literal["logosforge-project-bundle"]
    version: Literal["1.0"]
    exportedAt: str
    source: _BundleSource
    project: _BundleProject

    @model_validator(mode="after")
    def validate_contract_constants(self) -> CloudProjectBundle:
        # Literals make the normal validation error precise; these assertions
        # keep the contract tied to the exporter constants when versions evolve.
        if self.format != BUNDLE_FORMAT or self.version != BUNDLE_VERSION:
            raise ValueError("unsupported Whiteboard project bundle")
        if self.source.app != SOURCE_APP:
            raise ValueError("the snapshot was not produced by Whiteboard")
        return self


class CloudRestoreRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bundle: CloudProjectBundle
    restore_id: str = Field(min_length=1, max_length=512)
    title_suffix: str = Field(default="", max_length=120)

    @field_validator("restore_id")
    @classmethod
    def validate_restore_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized or any(ord(character) < 32 for character in normalized):
            raise ValueError("restore_id must be non-blank printable text")
        return normalized


class CloudRetireRequest(BaseModel):
    """Exact complete-state precondition for retiring a superseded local copy."""

    model_config = ConfigDict(extra="forbid")

    expected_digest: str
    expected_bundle: CloudProjectBundle

    @field_validator("expected_digest")
    @classmethod
    def validate_expected_digest(cls, value: str) -> str:
        if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
            raise ValueError("expected_digest must be a lowercase SHA-256 digest")
        return value


def _canonical_cloud_project(bundle: CloudProjectBundle) -> dict[str, Any]:
    """Remove only device-local allocation metadata from a complete bundle.

    This mirrors the Electron transport's canonical content identity. Core
    integer ids and timestamps change during copy-on-write restore, so they are
    remapped by stable exported order while all story content and references
    remain in the comparison.
    """
    canonical = bundle.model_dump(mode="json")
    canonical.pop("exportedAt", None)
    project = canonical["project"]
    project.pop("id", None)

    psyke = project.get("psyke")
    if not isinstance(psyke, dict):
        return canonical
    elements = psyke.get("elements")
    entry_ids: dict[str, int] = {}
    if isinstance(elements, list):
        for index, entry in enumerate(elements):
            if not isinstance(entry, dict):
                continue
            entry_ids[str(entry.get("id"))] = index + 1
            entry["id"] = str(index + 1)
            entry.pop("created_at", None)
            entry.pop("updated_at", None)

    relations = psyke.get("relations")
    if isinstance(relations, list):
        for relation in relations:
            if not isinstance(relation, dict):
                continue
            source = entry_ids.get(str(relation.get("source_id")))
            target = entry_ids.get(str(relation.get("target_id")))
            if source is not None:
                relation["source_id"] = source
            if target is not None:
                relation["target_id"] = target
            if source is not None and target is not None:
                relation["id"] = f"{source}:{target}"

    legacy_progressions = psyke.get("progressions")
    if isinstance(legacy_progressions, list):
        for index, progression in enumerate(legacy_progressions):
            if not isinstance(progression, dict):
                continue
            progression["id"] = index + 1
            entry_id = entry_ids.get(str(progression.get("entry_id")))
            if entry_id is not None:
                progression["entry_id"] = entry_id

    tracks = project.get("progression_tracks")
    if not isinstance(tracks, list):
        return canonical
    track_ids = {
        str(track.get("id")): index + 1
        for index, track in enumerate(tracks)
        if isinstance(track, dict)
    }
    next_beat_id = 1
    for index, track in enumerate(tracks):
        if not isinstance(track, dict):
            continue
        canonical_track_id = index + 1
        track["id"] = canonical_track_id
        for field in ("primary_psyke_entry_id", "secondary_psyke_entry_id"):
            if track.get(field) is None:
                continue
            entry_id = entry_ids.get(str(track[field]))
            if entry_id is not None:
                track[field] = entry_id
        beats = track.get("beats")
        if not isinstance(beats, list):
            continue
        for beat in beats:
            if not isinstance(beat, dict):
                continue
            beat["id"] = next_beat_id
            next_beat_id += 1
            beat["track_id"] = track_ids.get(
                str(beat.get("track_id")), canonical_track_id
            )
    return canonical


def _javascript_number(value: int | float) -> str:
    """Serialize a parsed JSON number the way ``JSON.stringify`` does."""
    number = float(value)
    if not math.isfinite(number):
        return "null"
    if number == 0:
        return "0"
    absolute = abs(number)
    rendered = repr(number).lower()
    if 1e-6 <= absolute < 1e21:
        plain = format(Decimal(rendered), "f")
        if "." in plain:
            plain = plain.rstrip("0").rstrip(".")
        return plain
    if "e" not in rendered:
        rendered = format(number, ".15e")
    mantissa, exponent = rendered.split("e", 1)
    mantissa = mantissa.rstrip("0").rstrip(".") if "." in mantissa else mantissa
    exponent_value = int(exponent)
    sign = "+" if exponent_value >= 0 else ""
    return f"{mantissa}e{sign}{exponent_value}"


def _stable_javascript_json(value: Any) -> str:
    """Match Electron's recursively key-sorted ``JSON.stringify`` payload."""
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, (int, float)):
        return _javascript_number(value)
    if isinstance(value, str):
        rendered = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        # Well-formed JSON.stringify escapes lone UTF-16 surrogates while
        # preserving ordinary Unicode characters verbatim.
        return "".join(
            f"\\u{ord(character):04x}"
            if 0xD800 <= ord(character) <= 0xDFFF
            else character
            for character in rendered
        )
    if isinstance(value, list):
        return "[" + ",".join(_stable_javascript_json(item) for item in value) + "]"
    if isinstance(value, dict):
        # JavaScript's default Array.sort compares UTF-16 code units.
        keys = sorted(
            value,
            key=lambda item: str(item).encode("utf-16-be", errors="surrogatepass"),
        )
        return "{" + ",".join(
            f"{_stable_javascript_json(str(key))}:{_stable_javascript_json(value[key])}"
            for key in keys
        ) + "}"
    raise TypeError(f"Unsupported cloud bundle value: {type(value).__name__}")


def _canonical_cloud_digest(bundle: CloudProjectBundle) -> str:
    payload = _stable_javascript_json(_canonical_cloud_project(bundle)).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _request_digest(body: CloudRestoreRequest) -> str:
    encoded = json.dumps(
        {
            "bundle": body.bundle.model_dump(mode="json"),
            "title_suffix": body.title_suffix,
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _allocation_marker(restore_id: str, request_digest: str) -> str:
    restore_digest = hashlib.sha256(restore_id.encode("utf-8")).hexdigest()
    return f"logosforge-whiteboard-cloud-restore:{restore_digest}:{request_digest}"


async def _core_json(core, method: str, path: str, **kwargs: Any) -> Any:
    try:
        return (await core.request(method, path, **kwargs)).json()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=core_error_message(
                exc, fallback="Cloud snapshot restore failed in the core"
            ),
        ) from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Cloud snapshot restore failed while communicating with the core.",
        ) from exc


async def _restore_psyke(core, project_id: int, source: _BundleProject) -> str:
    prefix = f"/api/projects/{project_id}"
    id_map: dict[int, int] = {}
    for entry in source.psyke.elements:
        restored = await _core_json(
            core,
            "POST",
            f"{prefix}/psyke/entries",
            json={
                "name": entry.name,
                "type": entry.entry_type,
                "aliases": list(entry.aliases),
                "notes": entry.notes,
                "details": {"description": entry.description},
            },
        )
        new_id = restored.get("id") if isinstance(restored, dict) else None
        if not _positive_int(new_id):
            raise HTTPException(
                status_code=502,
                detail="The core returned an invalid restored PSYKE entry.",
            )
        id_map[int(entry.id)] = new_id

    for relation in source.psyke.relations:
        await _core_json(
            core,
            "POST",
            f"{prefix}/psyke/relations",
            json={
                "source_id": id_map[relation.source_id],
                "target_id": id_map[relation.target_id],
                "relation_type": relation.relation_type,
            },
        )

    # Creating a legacy PSYKE progression also creates its compatibility track.
    # Recreate those tracks in their exported global order, then insert modern
    # tracks at their original dense indices below.
    by_entry: dict[int, list[_BundleLegacyProgression]] = defaultdict(list)
    for progression in source.psyke.progressions:
        by_entry[progression.entry_id].append(progression)
    ordered_entries: list[int] = []
    for track in sorted(
        source.progression_tracks, key=lambda item: (item.sort_order, item.id)
    ):
        if (
            track.legacy_compatibility
            and track.primary_psyke_entry_id is not None
            and track.primary_psyke_entry_id in by_entry
            and track.primary_psyke_entry_id not in ordered_entries
        ):
            ordered_entries.append(track.primary_psyke_entry_id)
    ordered_entries.extend(sorted(set(by_entry) - set(ordered_entries)))
    for source_entry_id in ordered_entries:
        for progression in sorted(
            by_entry[source_entry_id], key=lambda item: (item.sort_order, item.id)
        ):
            await _core_json(
                core,
                "POST",
                f"{prefix}/psyke/progressions",
                json={
                    "entry_id": id_map[source_entry_id],
                    "text": progression.text,
                    "scene_id": None,
                },
            )

    snapshot = await _core_json(core, "GET", f"{prefix}/progressions")
    revision = snapshot.get("revision") if isinstance(snapshot, dict) else None
    if not isinstance(revision, str) or len(revision) != 64:
        raise HTTPException(
            status_code=502,
            detail="The core returned an invalid Progressions revision.",
        )

    for track in sorted(
        source.progression_tracks, key=lambda item: (item.sort_order, item.id)
    ):
        if track.legacy_compatibility:
            continue
        result = await _core_json(
            core,
            "POST",
            f"{prefix}/progressions/commands",
            headers={"Idempotency-Key": f"cloud-restore-{uuid4().hex}"},
            json={
                "kind": "create_track",
                "expected_revision": revision,
                "track_kind": track.kind,
                "title": track.title,
                "description": track.description,
                "color_label": track.color_label,
                "primary_psyke_entry_id": (
                    id_map[track.primary_psyke_entry_id]
                    if track.primary_psyke_entry_id is not None
                    else None
                ),
                "secondary_psyke_entry_id": (
                    id_map[track.secondary_psyke_entry_id]
                    if track.secondary_psyke_entry_id is not None
                    else None
                ),
                "index": track.sort_order,
            },
        )
        if not isinstance(result, dict) or not _positive_int(
            result.get("created_track_id")
        ):
            raise HTTPException(
                status_code=502,
                detail="The core did not confirm the restored Progressions track.",
            )
        new_track_id = result["created_track_id"]
        progressions = result.get("progressions")
        revision = (
            progressions.get("revision") if isinstance(progressions, dict) else None
        )
        if not isinstance(revision, str) or len(revision) != 64:
            raise HTTPException(
                status_code=502,
                detail="The core returned an invalid Progressions revision.",
            )

        for beat in sorted(track.beats, key=lambda item: (item.sort_order, item.id)):
            result = await _core_json(
                core,
                "POST",
                f"{prefix}/progressions/commands",
                headers={"Idempotency-Key": f"cloud-restore-{uuid4().hex}"},
                json={
                    "kind": "create_beat",
                    "expected_revision": revision,
                    "track_id": new_track_id,
                    "text": beat.text,
                    "anchor_kind": beat.anchor_kind,
                    "scene_id": None,
                    "anchor_ref": beat.anchor_ref,
                    "anchor_label": beat.anchor_label,
                    "index": beat.sort_order,
                },
            )
            progressions = (
                result.get("progressions") if isinstance(result, dict) else None
            )
            revision = (
                progressions.get("revision") if isinstance(progressions, dict) else None
            )
            if not _positive_int(
                result.get("created_beat_id") if isinstance(result, dict) else None
            ):
                raise HTTPException(
                    status_code=502,
                    detail="The core did not confirm the restored Progressions beat.",
                )
            if not isinstance(revision, str) or len(revision) != 64:
                raise HTTPException(
                    status_code=502,
                    detail="The core returned an invalid Progressions revision.",
                )
    return revision


async def _project_exists(core, project_id: int) -> bool:
    try:
        await core.request("GET", f"/api/projects/{project_id}")
        return True
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == status.HTTP_404_NOT_FOUND:
            return False
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=core_error_message(
                exc, fallback="Cloud restore identity could not be checked"
            ),
        ) from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Cloud restore identity could not be checked.",
        ) from exc


async def _prepared_validators(
    core,
    document_id: str,
) -> CloudRestorePreparedValidators:
    """Read validators for every restored resource except the manuscript."""
    try:
        psyke = await _collection_snapshot(core, int(document_id))
        progression_snapshot = await _core_json(
            core, "GET", f"/api/projects/{document_id}/progressions"
        )
        progression_revision = (
            progression_snapshot.get("revision")
            if isinstance(progression_snapshot, dict)
            else None
        )
        if not isinstance(progression_revision, str) or len(progression_revision) != 64:
            raise HTTPException(
                status_code=502,
                detail="The core returned an invalid Progressions revision.",
            )
        return CloudRestorePreparedValidators(
            outline_revision=outline_items_store.get_document(document_id).revision,
            drafter_revision=drafter_pages_store.get_document(document_id).revision,
            comments_revision=comments_store.get(document_id).revision,
            psyke_digest=_collection_digest(psyke),
            progressions_revision=progression_revision,
        )
    except (HTTPException, LocalStateError):
        raise
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=core_error_message(
                exc, fallback="Cloud restore validators could not be read"
            ),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Cloud restore validators could not be read safely.",
        ) from exc


def _manuscript_matches(
    document: WhiteboardDocument,
    source: _BundleProject,
    title: str,
) -> bool:
    return (
        document.title == title
        and document.mode == source.mode
        and document.blocks == source.manuscript.blocks
        and document.settings == source.settings
    )


def _stale_retry_error(
    message: str,
    preserved_document: WhiteboardDocument | None = None,
) -> HTTPException:
    detail: dict[str, Any] = {
        "code": "cloud_restore_retry_stale",
        "message": message,
    }
    if preserved_document is not None:
        # Only return the opaque identity needed to finish renderer/main binding
        # reconciliation. Never include manuscript or provider payload data.
        detail["document_id"] = preserved_document.id
        detail["incarnation"] = preserved_document.incarnation
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=detail,
    )


def _restore_id_conflict() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "code": "cloud_restore_id_conflict",
            "message": "This restore_id was already used for a different cloud snapshot.",
        },
    )


def _idempotent_result(
    response: Response,
    document: WhiteboardDocument,
    source_project_id: str,
) -> dict[str, Any]:
    response.status_code = status.HTTP_200_OK
    response.headers["ETag"] = resource_etag(
        "whiteboard", document.incarnation, document.revision
    )
    return {
        "ok": True,
        "idempotent": True,
        "document": document.model_dump(),
        "source_project_id": source_project_id,
    }


async def _replay_receipt(
    core,
    receipt: CloudRestoreReceipt,
    request_digest: str,
    response: Response,
) -> dict[str, Any] | None:
    """Return a safe exact retry, ``None`` only when its identity was deleted."""
    if receipt.request_digest != request_digest:
        raise _restore_id_conflict()
    async with document_lifecycle_lock(receipt.document_id):
        if not whiteboard_store.exists(receipt.document_id):
            return None
        document = whiteboard_store.get(receipt.document_id)
        if document.incarnation != receipt.incarnation:
            return None
        if not await _project_exists(core, int(receipt.document_id)):
            return None
        current = await _prepared_validators(core, receipt.document_id)
        expected = receipt.validators
        if (
            document.revision != expected.whiteboard_revision
            or current.outline_revision != expected.outline_revision
            or current.drafter_revision != expected.drafter_revision
            or current.comments_revision != expected.comments_revision
            or current.psyke_digest != expected.psyke_digest
            or current.progressions_revision != expected.progressions_revision
        ):
            raise _stale_retry_error(
                "The project restored by this request has since been edited. "
                "Whiteboard will not replay the older cloud snapshot over it.",
                document,
            )
        return _idempotent_result(response, document, receipt.source_project_id)


async def _replay_prepared_pending(
    core,
    pending: CloudRestorePending,
    source: _BundleProject,
    title: str,
    request_digest: str,
    response: Response,
) -> dict[str, Any] | None:
    """Recover a crash after manuscript publication but before receipt commit."""
    if pending.request_digest != request_digest:
        raise _restore_id_conflict()
    async with document_lifecycle_lock(pending.document_id):
        if not whiteboard_store.exists(pending.document_id):
            return None
        document = whiteboard_store.get(pending.document_id)
        if not await _project_exists(core, int(pending.document_id)):
            raise _stale_retry_error(
                "An interrupted restore left a local document without its core project.",
                document,
            )
        if pending.prepared is None:
            raise _stale_retry_error(
                "An interrupted restore published a document before its complete state "
                "could be verified. It was preserved for manual review.",
                document,
            )
        current = await _prepared_validators(core, pending.document_id)
        if current != pending.prepared or not _manuscript_matches(
            document, source, title
        ):
            raise _stale_retry_error(
                "The interrupted restore was edited before retry recovery. "
                "It was preserved and the older snapshot was not replayed.",
                document,
            )
        committed = cloud_restore_receipt_store.commit(
            pending, document.incarnation, document.revision
        )
        return _idempotent_result(response, document, committed.source_project_id)


async def _reconcile_unrecorded_marker(
    core,
    restore_id: str,
    request_digest: str,
) -> None:
    """Resolve a crash after atomic core allocation but before intent storage."""
    restore_digest = hashlib.sha256(restore_id.encode("utf-8")).hexdigest()
    marker_prefix = f"logosforge-whiteboard-cloud-restore:{restore_digest}:"
    projects = await _core_json(core, "GET", "/api/projects")
    if not isinstance(projects, list):
        raise HTTPException(
            status_code=502, detail="The core returned an invalid project list."
        )
    for project in projects:
        if not isinstance(project, dict):
            raise HTTPException(
                status_code=502, detail="The core returned an invalid project list."
            )
        description = project.get("description")
        if not isinstance(description, str) or not description.startswith(
            marker_prefix
        ):
            continue
        if description != _allocation_marker(restore_id, request_digest):
            raise _restore_id_conflict()
        project_id = project.get("id")
        if not _positive_int(project_id):
            raise HTTPException(
                status_code=502, detail="The core returned an invalid project identity."
            )
        document_id = str(project_id)
        if whiteboard_store.exists(document_id):
            preserved = whiteboard_store.get(document_id)
            raise _stale_retry_error(
                "A prior restore with this id exists but its retry receipt is unavailable. "
                "The document was preserved for manual review.",
                preserved,
            )
        # The marker proves this otherwise-unpublished allocation belongs to
        # this exact request, so it is safe to finish its interrupted rollback.
        await _settle_unpublished_core_project_uninterruptibly(core, document_id)


@router.post("/api/cloud-sync/retire/{doc_id}")
async def retire_cloud_replaced_document(
    request: Request,
    doc_id: int,
    body: CloudRetireRequest,
) -> dict[str, Any]:
    """Delete a superseded copy only while it is still byte-for-byte expected.

    The complete project comparison and deletion share the same lifecycle lock
    used by every Whiteboard subsystem mutation. A save, MCP command, or other
    backend write that lands before this transaction therefore changes the
    comparison and receives preservation rather than deletion; none can land
    between the successful comparison and the delete.
    """
    core = request.app.state.core
    document_id = str(doc_id)
    expected_incarnation = request_document_incarnation(request, required=True)
    async with locked_document_lifecycle(document_id):
        if not await _project_exists(core, doc_id):
            # The exact incarnation is already absent. Finish any interrupted
            # local cleanup without touching a replacement core identity.
            begin_document_delete(
                document_id, request_delete_order_floors(request)
            )
            cleanup_failures = _cleanup_local_document_state(document_id)
            return {
                "ok": True,
                "deleted": document_id,
                "already_absent": True,
                "cleanup_pending": bool(cleanup_failures),
            }

        if not whiteboard_store.exists(document_id):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "cloud_retire_identity_changed",
                    "message": (
                        "The core project exists without the expected Whiteboard "
                        "document. It was preserved for review."
                    ),
                },
            )
        actual_incarnation = whiteboard_store.ensure_incarnation(document_id)
        require_document_incarnation(expected_incarnation, actual_incarnation)

        expected_digest = _canonical_cloud_digest(body.expected_bundle)
        if not hmac.compare_digest(expected_digest, body.expected_digest):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "cloud_retire_precondition_invalid",
                    "message": (
                        "The retirement snapshot no longer matches its canonical "
                        "digest. The local project was preserved."
                    ),
                },
            )
        current_raw = await assemble_project_bundle(core, doc_id, document_id)
        current = CloudProjectBundle.model_validate(current_raw)
        current_digest = _canonical_cloud_digest(current)
        if (
            not hmac.compare_digest(current_digest, body.expected_digest)
            or _canonical_cloud_project(current)
            != _canonical_cloud_project(body.expected_bundle)
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "cloud_retire_content_changed",
                    "message": (
                        "This local project changed after cloud replacement began. "
                        "Whiteboard preserved it as a separate copy."
                    ),
                },
            )

        begin_document_delete(document_id, request_delete_order_floors(request))
        try:
            await core.delete_project(doc_id)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != status.HTTP_404_NOT_FOUND:
                cancel_document_delete(document_id)
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="core project delete failed",
                ) from exc
        except Exception:
            cancel_document_delete(document_id)
            raise
        cleanup_failures = _cleanup_local_document_state(document_id)
        return {
            "ok": True,
            "deleted": document_id,
            "already_absent": False,
            "cleanup_pending": bool(cleanup_failures),
        }


@router.post("/api/cloud-sync/restore", status_code=status.HTTP_201_CREATED)
async def restore_cloud_snapshot(
    request: Request,
    body: CloudRestoreRequest,
    response: Response,
) -> dict[str, Any]:
    """Create and publish a fresh document from one complete cloud snapshot.

    No existing document is modified. The renderer may switch its cloud binding
    only after this call succeeds, which makes a failed/cancelled pull harmless.
    """
    core = request.app.state.core
    source = body.bundle.project
    title = f"{source.title}{body.title_suffix}".strip() or "Untitled"
    if len(title) > 500:
        raise HTTPException(
            status_code=422, detail="Restored document title is too long."
        )
    request_digest = _request_digest(body)
    marker = _allocation_marker(body.restore_id, request_digest)

    # The global allocation/publication gate also makes receipt inspection,
    # stale-id reconciliation, and any numeric-id reuse one atomic identity
    # decision with respect to ordinary document creation/deletion.
    async with (
        _serialized_restore(body.restore_id),
        document_identity_publication(),
    ):
        receipt = cloud_restore_receipt_store.get_receipt(body.restore_id)
        if receipt is not None:
            replay = await _replay_receipt(core, receipt, request_digest, response)
            if replay is not None:
                return replay
            cloud_restore_receipt_store.discard_receipt(body.restore_id)

        pending = cloud_restore_receipt_store.get_pending(body.restore_id)
        if pending is not None:
            replay = await _replay_prepared_pending(
                core, pending, source, title, request_digest, response
            )
            if replay is not None:
                return replay
            # No manuscript was published. Delete only when the core's
            # durable marker proves the numeric id still names our restore.
            project = (
                await _core_json(core, "GET", f"/api/projects/{pending.document_id}")
                if await _project_exists(core, int(pending.document_id))
                else None
            )
            if project is not None and (
                not isinstance(project, dict) or project.get("description") != marker
            ):
                raise _stale_retry_error(
                    "The interrupted restore's numeric project id was reused. "
                    "Whiteboard preserved the replacement project."
                )
            await _settle_unpublished_core_project_uninterruptibly(
                core, pending.document_id
            )
            cloud_restore_receipt_store.discard_pending(body.restore_id)

        await _reconcile_unrecorded_marker(core, body.restore_id, request_digest)

        doc_id: str | None = None
        committed = False
        try:
            allocation, cancelled = await complete_core_allocation(
                _core_json(
                    core,
                    "POST",
                    "/api/projects",
                    json={"title": title, "description": marker},
                )
            )
            if not isinstance(allocation, dict) or not _positive_int(
                allocation.get("id")
            ):
                raise HTTPException(
                    status_code=502,
                    detail="The core returned an invalid allocated project identity.",
                )
            doc_id = str(allocation["id"])
            if cancelled:
                raise asyncio.CancelledError
            pending = cloud_restore_receipt_store.begin(
                body.restore_id,
                request_digest,
                doc_id,
                source.id,
            )
            async with document_lifecycle_lock(doc_id):
                cleanup_failures = _cleanup_local_document_state(doc_id)
                if cleanup_failures:
                    raise HTTPException(
                        status_code=500,
                        detail=(
                            "Cloud restore could not clear stale local data for a reused "
                            "project identity."
                        ),
                    )
                try:
                    with create_document_incarnation(doc_id):
                        # Core and auxiliary local stores remain invisible to
                        # the library until the manuscript is written last.
                        await _restore_psyke(core, int(doc_id), source)
                        outline_items_store.replace_document(doc_id, source.outline)
                        drafter_pages_store.replace_document(
                            doc_id, source.drafter.pages
                        )
                        comments_store.replace_document(doc_id, source.comments)
                        prepared = await _prepared_validators(core, doc_id)
                        pending = cloud_restore_receipt_store.mark_prepared(
                            body.restore_id, request_digest, prepared
                        )
                        document = whiteboard_store.create(
                            doc_id,
                            WhiteboardCreate(
                                title=title,
                                mode=source.mode,
                                blocks=source.manuscript.blocks,
                                settings=source.settings,
                            ),
                        )
                        cloud_restore_receipt_store.commit(
                            pending, document.incarnation, document.revision
                        )
                except (LocalStateError, ValueError) as exc:
                    raise HTTPException(
                        status_code=500,
                        detail=(
                            "Cloud restore could not write the local project snapshot. "
                            f"{exc}"
                        ),
                    ) from exc
                committed = True
                response.headers["ETag"] = resource_etag(
                    "whiteboard", document.incarnation, document.revision
                )
                return {
                    "ok": True,
                    "idempotent": False,
                    "document": document.model_dump(),
                    "source_project_id": source.id,
                }
        except BaseException as exc:
            if doc_id is not None and not committed:
                rollback_failed = (
                    await _settle_unpublished_core_project_uninterruptibly(core, doc_id)
                )
                try:
                    cloud_restore_receipt_store.discard_pending(body.restore_id)
                except LocalStateError:
                    # A durable pending intent safely forces reconciliation
                    # on retry; never mask the original restore failure.
                    pass
                if rollback_failed and isinstance(exc, HTTPException):
                    exc.detail = f"{exc.detail} The unpublished core project could not be rolled back."
            raise
