"""PSYKE (story-bible) — wraps the core's project-scoped PSYKE routes.

The Whiteboard frontend is project-agnostic and uses a slightly different DTO,
so this router injects the pinned project id and translates between the core
``PsykeEntryDTO`` (id:int, ``type``, ``details`` dict) and the frontend
``PsykeEntry`` (id:str, ``entry_type``, free-text ``description``). The
frontend's ``description`` is stored in the core entry's ``details["description"]``
so it round-trips without a new core column.
"""
from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass

import httpx
from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.document_lifecycle import locked_document_request, request_document_incarnation
from app.local_state import PsykeRevisionState, psyke_revision_store
from app.resource_revision import (
    IF_MATCH_HEADER,
    MUTATION_ID_HEADER,
    RevisionPrecondition,
    mutation_id_conflict,
    request_mutation_id,
    request_revision_precondition,
    resource_etag,
    revision_conflict,
)

router = APIRouter()

# The element types the Whiteboard offers (mirrors the frontend form).
ALLOWED_TYPES = {"character", "place", "object", "lore", "theme", "other"}
MAX_RELATION_TYPE_CHARACTERS = 1_000
MAX_PROGRESSION_TEXT_CHARACTERS = 250_000


class PsykeElementCreate(BaseModel):
    type: str = "other"
    name: str = Field(min_length=1)
    description: str = ""
    notes: str = ""


class PsykeElementUpdate(BaseModel):
    """Partial update — only the provided fields change."""

    type: str | None = None
    name: str | None = None
    description: str | None = None
    notes: str | None = None


class PsykeRelationCreate(BaseModel):
    """One new relation. Existing unordered pairs are never overwritten."""

    model_config = ConfigDict(extra="forbid")

    source_id: int = Field(gt=0)
    target_id: int = Field(gt=0)
    relation_type: str = ""

    @field_validator("relation_type")
    @classmethod
    def validate_relation_type(cls, value: str) -> str:
        normalized = value.strip()
        if len(normalized) > MAX_RELATION_TYPE_CHARACTERS:
            raise ValueError(
                "relation type exceeds the maximum supported length"
            )
        return normalized


class PsykeProgressionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entry_id: int = Field(gt=0)
    text: str = Field(min_length=1)
    scene_id: int | None = Field(default=None, gt=0)

    @field_validator("text")
    @classmethod
    def validate_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("progression text must not be blank")
        if len(normalized) > MAX_PROGRESSION_TEXT_CHARACTERS:
            raise ValueError(
                "progression text exceeds the maximum supported length"
            )
        return normalized


class PsykeProgressionUpdate(BaseModel):
    """A partial wrapper patch; the core requires a full replacement body."""

    model_config = ConfigDict(extra="forbid")

    text: str | None = None
    scene_id: int | None = Field(default=None, gt=0)

    @field_validator("text")
    @classmethod
    def validate_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("progression text must not be blank")
        if len(normalized) > MAX_PROGRESSION_TEXT_CHARACTERS:
            raise ValueError(
                "progression text exceeds the maximum supported length"
            )
        return normalized


@dataclass(frozen=True)
class PsykeCollectionSnapshot:
    """One wrapper-level view of the complete core-owned PSYKE collection."""

    entries: list[dict]
    relations: list[dict]
    progressions: list[dict]


def _to_frontend(entry: dict) -> dict:
    details = entry.get("details") or {}
    description = details.get("description", "") if isinstance(details, dict) else ""
    return {
        "id": str(entry.get("id", "")),
        "name": entry.get("name", ""),
        "entry_type": entry.get("type", "other"),
        "aliases": entry.get("aliases", []),
        "description": description,
        "notes": entry.get("notes", ""),
        "created_at": None,
        "updated_at": None,
    }


def _collection_digest(snapshot: PsykeCollectionSnapshot) -> str:
    """Hash every raw PSYKE surface without depending on response ordering."""
    try:
        canonical: dict[str, list[str]] = {}
        for name in ("entries", "relations", "progressions"):
            rows = getattr(snapshot, name)
            canonical[name] = sorted(
                json.dumps(
                    row,
                    ensure_ascii=False,
                    separators=(",", ":"),
                    sort_keys=True,
                    allow_nan=False,
                )
                for row in rows
            )
        encoded = json.dumps(
            canonical,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError, UnicodeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The core returned invalid PSYKE collection data.",
        ) from exc
    return hashlib.sha256(encoded).hexdigest()


async def _core_collection(core, path: str, label: str) -> list[dict]:
    value = (await core.request("GET", path)).json()
    if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"The core returned an invalid PSYKE {label} collection.",
        )
    return value


async def _collection_snapshot(core, project_id: int) -> PsykeCollectionSnapshot:
    """Read the three core PSYKE collections while the document lock is held."""
    prefix = f"/api/projects/{project_id}/psyke"
    return PsykeCollectionSnapshot(
        # Keep every raw field: aliases/details, endpoint names, scene titles and
        # sort order are all observable state and must therefore affect the ETag.
        entries=await _core_collection(core, f"{prefix}/entries", "entry"),
        relations=await _core_collection(core, f"{prefix}/relations", "relation"),
        progressions=await _core_collection(
            core, f"{prefix}/progressions", "progression"
        ),
    )


def _relation_pair(value: dict) -> tuple[int, int] | None:
    source_id = value.get("source_id")
    target_id = value.get("target_id")
    if (
        not isinstance(source_id, int)
        or isinstance(source_id, bool)
        or source_id < 1
        or not isinstance(target_id, int)
        or isinstance(target_id, bool)
        or target_id < 1
    ):
        return None
    return min(source_id, target_id), max(source_id, target_id)


def _progression_id(value: dict) -> int | None:
    progression_id = value.get("id")
    if (
        not isinstance(progression_id, int)
        or isinstance(progression_id, bool)
        or progression_id < 1
    ):
        return None
    return progression_id


def _committed_relation(
    snapshot: PsykeCollectionSnapshot,
    source_id: int,
    target_id: int,
) -> dict:
    expected = min(source_id, target_id), max(source_id, target_id)
    relation = next(
        (row for row in snapshot.relations if _relation_pair(row) == expected),
        None,
    )
    if relation is None:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The core did not return the committed PSYKE relation.",
        )
    return dict(relation)


def _committed_progression(
    snapshot: PsykeCollectionSnapshot,
    progression_id: int,
) -> dict:
    progression = next(
        (row for row in snapshot.progressions if _progression_id(row) == progression_id),
        None,
    )
    if progression is None:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The core did not return the committed PSYKE progression.",
        )
    return dict(progression)


def _search_entries(entries: list[dict], query: str) -> list[dict]:
    """Match the core search contract against the same snapshot as the ETag."""
    needle = query.strip().lower()
    if not needle:
        return entries
    matches: list[dict] = []
    for entry in entries:
        aliases = entry.get("aliases")
        aliases_csv = ", ".join(
            str(alias) for alias in aliases
        ) if isinstance(aliases, list) else str(aliases or "")
        haystack = " ".join([
            str(entry.get("name") or ""),
            aliases_csv,
            str(entry.get("notes") or ""),
        ]).lower()
        if needle in haystack:
            matches.append(entry)
    return matches


def _conditional_mode(request: Request) -> bool:
    headers = getattr(request, "headers", {})
    return (
        headers.get(IF_MATCH_HEADER) is not None
        or headers.get(IF_MATCH_HEADER.lower()) is not None
        or headers.get(MUTATION_ID_HEADER) is not None
        or headers.get(MUTATION_ID_HEADER.lower()) is not None
    )


def _conditional_preconditions(
    request: Request,
    incarnation: str,
    *,
    conditional: bool,
) -> tuple[RevisionPrecondition | None, str | None]:
    if not conditional:
        return None, None
    precondition = request_revision_precondition(
        request,
        "psyke",
        incarnation,
        required=True,
    )
    mutation_id = request_mutation_id(request, required=True)
    assert precondition is not None and mutation_id is not None
    return precondition, mutation_id


def _mutation_fingerprint(
    operation: str,
    payload: dict,
    expected_revision: str,
    *,
    element_id: int | None = None,
) -> str:
    encoded = json.dumps(
        {
            "operation": operation,
            "element_id": element_id,
            "expected_revision": expected_revision,
            "payload": payload,
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _patch_changes_entry(entry: dict | None, payload: dict) -> bool:
    """Return whether forwarding *payload* can change an existing core row."""
    if entry is None:
        return True  # The core must retain authority for its normal 404 response.
    return any(entry.get(key) != value for key, value in payload.items())


def _conditional_retry(
    state: PsykeRevisionState,
    precondition: RevisionPrecondition,
    mutation_id: str,
    fingerprint: str,
    incarnation: str,
) -> dict | None:
    if not precondition.matches_resource:
        raise revision_conflict(
            "psyke", incarnation, precondition.revision, state.revision
        )
    if state.last_mutation_id and hmac.compare_digest(
        state.last_mutation_id, mutation_id
    ):
        if not hmac.compare_digest(state.last_mutation_fingerprint, fingerprint):
            raise mutation_id_conflict(mutation_id)
        if state.last_mutation_result is None:
            # Invalid/corrupt state is normally rejected by the store parser;
            # retain a fail-closed guard at the route boundary too.
            raise mutation_id_conflict(mutation_id)
        return dict(state.last_mutation_result)
    if not hmac.compare_digest(precondition.revision, state.revision):
        raise revision_conflict(
            "psyke", incarnation, precondition.revision, state.revision
        )
    return None


def _publish_revision(
    response: Response | None,
    incarnation: str,
    revision: str,
) -> None:
    if response is not None:
        response.headers["ETag"] = resource_etag("psyke", incarnation, revision)


@router.get("/api/psyke/search")
async def search(
    request: Request,
    q: str = Query(""),
    doc: int | None = Query(None),
    response: Response = None,
):
    core = request.app.state.core
    async with locked_document_request(request, doc) as locked:
        snapshot = await _collection_snapshot(core, locked.project_id)
        state = psyke_revision_store.observe(
            locked.document_id,
            locked.incarnation,
            _collection_digest(snapshot),
        )
        _publish_revision(response, locked.incarnation, state.revision)
        return {
            "query": q,
            "results": [
                _to_frontend(entry)
                for entry in _search_entries(snapshot.entries, q)
            ],
            "revision": state.revision,
        }


@router.get("/api/psyke/relations")
async def list_relations(
    request: Request,
    doc: int | None = Query(None),
    response: Response = None,
):
    core = request.app.state.core
    async with locked_document_request(request, doc) as locked:
        snapshot = await _collection_snapshot(core, locked.project_id)
        state = psyke_revision_store.observe(
            locked.document_id,
            locked.incarnation,
            _collection_digest(snapshot),
        )
        _publish_revision(response, locked.incarnation, state.revision)
        return {
            "relations": [dict(relation) for relation in snapshot.relations],
            "revision": state.revision,
        }


@router.get("/api/psyke/progressions")
async def list_progressions(
    request: Request,
    doc: int | None = Query(None),
    response: Response = None,
):
    core = request.app.state.core
    async with locked_document_request(request, doc) as locked:
        snapshot = await _collection_snapshot(core, locked.project_id)
        state = psyke_revision_store.observe(
            locked.document_id,
            locked.incarnation,
            _collection_digest(snapshot),
        )
        _publish_revision(response, locked.incarnation, state.revision)
        return {
            "progressions": [
                dict(progression) for progression in snapshot.progressions
            ],
            "revision": state.revision,
        }


@router.post("/api/psyke/elements")
async def create_element(
    request: Request,
    body: PsykeElementCreate,
    doc: int | None = Query(None),
    response: Response = None,
):
    core = request.app.state.core
    conditional = _conditional_mode(request)
    if conditional:
        # Conditional writes always carry all three pieces of identity, even on
        # the legacy default-document URL.
        request_document_incarnation(request, required=True)
    async with locked_document_request(request, doc, mutation=True) as locked:
        payload = {
            "name": body.name,
            "type": body.type if body.type in ALLOWED_TYPES else "other",
            "notes": body.notes,
            "aliases": [],
            "is_global": False,
            "details": {"description": body.description} if body.description else {},
        }
        precondition, mutation_id = _conditional_preconditions(
            request, locked.incarnation, conditional=conditional
        )
        snapshot = await _collection_snapshot(core, locked.project_id)
        state = psyke_revision_store.observe(
            locked.document_id,
            locked.incarnation,
            _collection_digest(snapshot),
        )
        fingerprint = ""
        if precondition is not None and mutation_id is not None:
            fingerprint = _mutation_fingerprint(
                "create", payload, precondition.revision
            )
            replay = _conditional_retry(
                state,
                precondition,
                mutation_id,
                fingerprint,
                locked.incarnation,
            )
            if replay is not None:
                _publish_revision(response, locked.incarnation, state.revision)
                return {"ok": True, "element": replay, "revision": state.revision}
        created = (
            await core.request(
                "POST", f"/api/projects/{locked.project_id}/psyke/entries", json=payload
            )
        ).json()
        element = _to_frontend(created)
        committed_snapshot = await _collection_snapshot(core, locked.project_id)
        committed = psyke_revision_store.commit_mutation(
            locked.document_id,
            locked.incarnation,
            _collection_digest(committed_snapshot),
            mutation_id=mutation_id,
            mutation_fingerprint=fingerprint,
            result=element,
        )
        _publish_revision(response, locked.incarnation, committed.revision)
        return {"ok": True, "element": element, "revision": committed.revision}


@router.patch("/api/psyke/elements/{element_id}")
async def update_element(
    request: Request,
    element_id: int,
    body: PsykeElementUpdate,
    doc: int | None = Query(None),
    response: Response = None,
):
    """Partially update a PSYKE element. Forwards only the provided fields to the
    core's PATCH; the frontend ``description`` maps to the entry's
    ``details['description']``. A missing id (core 404) is translated, not a 500."""
    core = request.app.state.core
    conditional = _conditional_mode(request)
    if conditional:
        request_document_incarnation(request, required=True)
    async with locked_document_request(request, doc, mutation=True) as locked:
        precondition, mutation_id = _conditional_preconditions(
            request, locked.incarnation, conditional=conditional
        )
        snapshot = await _collection_snapshot(core, locked.project_id)
        state = psyke_revision_store.observe(
            locked.document_id,
            locked.incarnation,
            _collection_digest(snapshot),
        )
        current = next(
            (
                entry
                for entry in snapshot.entries
                if str(entry.get("id")) == str(element_id)
            ),
            None,
        )
        payload: dict = {}
        if body.name is not None:
            payload["name"] = body.name
        if body.type is not None:
            payload["type"] = body.type if body.type in ALLOWED_TYPES else "other"
        if body.notes is not None:
            payload["notes"] = body.notes
        if body.description is not None:
            details = (
                dict(current.get("details") or {})
                if isinstance(current, dict) and isinstance(current.get("details"), dict)
                else {}
            )
            if body.description:
                details["description"] = body.description
            else:
                details.pop("description", None)
            payload["details"] = details
        fingerprint = ""
        if precondition is not None and mutation_id is not None:
            fingerprint = _mutation_fingerprint(
                "update",
                payload,
                precondition.revision,
                element_id=element_id,
            )
            replay = _conditional_retry(
                state,
                precondition,
                mutation_id,
                fingerprint,
                locked.incarnation,
            )
            if replay is not None:
                _publish_revision(response, locked.incarnation, state.revision)
                return {"ok": True, "element": replay, "revision": state.revision}
        if not _patch_changes_entry(current, payload):
            # Do not send a semantic no-op to the core.  If the following local
            # receipt write fails, retrying is side-effect free; a content digest
            # alone cannot otherwise distinguish whether a no-op PATCH committed.
            assert current is not None
            element = _to_frontend(current)
            committed = psyke_revision_store.commit_mutation(
                locked.document_id,
                locked.incarnation,
                _collection_digest(snapshot),
                mutation_id=mutation_id,
                mutation_fingerprint=fingerprint,
                result=element,
            )
            _publish_revision(response, locked.incarnation, committed.revision)
            return {"ok": True, "element": element, "revision": committed.revision}
        try:
            updated = (
                await core.request(
                    "PATCH",
                    f"/api/projects/{locked.project_id}/psyke/entries/{element_id}",
                    json=payload,
                )
            ).json()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                raise HTTPException(status_code=404, detail=f"PSYKE element {element_id} not found")
            raise
        element = _to_frontend(updated)
        committed_snapshot = await _collection_snapshot(core, locked.project_id)
        committed = psyke_revision_store.commit_mutation(
            locked.document_id,
            locked.incarnation,
            _collection_digest(committed_snapshot),
            mutation_id=mutation_id,
            mutation_fingerprint=fingerprint,
            result=element,
        )
        _publish_revision(response, locked.incarnation, committed.revision)
        return {"ok": True, "element": element, "revision": committed.revision}


@router.post("/api/psyke/relations")
async def create_relation(
    request: Request,
    body: PsykeRelationCreate,
    doc: int | None = Query(None),
    response: Response = None,
):
    """Create one new unordered pair; relation replacement is intentionally absent."""
    core = request.app.state.core
    request_document_incarnation(request, required=True)
    async with locked_document_request(request, doc, mutation=True) as locked:
        precondition, mutation_id = _conditional_preconditions(
            request, locked.incarnation, conditional=True
        )
        assert precondition is not None and mutation_id is not None
        snapshot = await _collection_snapshot(core, locked.project_id)
        state = psyke_revision_store.observe(
            locked.document_id,
            locked.incarnation,
            _collection_digest(snapshot),
        )
        payload = body.model_dump()
        fingerprint = _mutation_fingerprint(
            "create_relation", payload, precondition.revision
        )
        replay = _conditional_retry(
            state,
            precondition,
            mutation_id,
            fingerprint,
            locked.incarnation,
        )
        if replay is not None:
            _publish_revision(response, locked.incarnation, state.revision)
            return {"ok": True, "relation": replay, "revision": state.revision}

        if body.source_id == body.target_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A PSYKE relation needs two distinct entries.",
            )
        entry_ids = {
            entry.get("id")
            for entry in snapshot.entries
            if isinstance(entry.get("id"), int)
            and not isinstance(entry.get("id"), bool)
        }
        missing_entry = next(
            (
                entry_id
                for entry_id in (body.source_id, body.target_id)
                if entry_id not in entry_ids
            ),
            None,
        )
        if missing_entry is not None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"PSYKE element {missing_entry} not found",
            )
        requested_pair = min(body.source_id, body.target_id), max(
            body.source_id, body.target_id
        )
        if any(
            _relation_pair(relation) == requested_pair
            for relation in snapshot.relations
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "psyke_relation_already_exists",
                    "message": (
                        "These PSYKE entries are already related; relation editing "
                        "is not available through this endpoint."
                    ),
                },
            )

        try:
            created = (
                await core.request(
                    "POST",
                    f"/api/projects/{locked.project_id}/psyke/relations",
                    json=payload,
                )
            ).json()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                raise HTTPException(
                    status_code=404,
                    detail="One or both PSYKE relation entries were not found.",
                ) from exc
            raise
        if (
            not isinstance(created, dict)
            or created.get("source_id") != body.source_id
            or created.get("target_id") != body.target_id
            or created.get("relation_type") != body.relation_type
        ):
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="The core returned an invalid PSYKE relation.",
            )
        committed_snapshot = await _collection_snapshot(core, locked.project_id)
        # The collection uses canonical endpoint orientation, while the create
        # receipt preserves the caller's directional request. Require the pair
        # to exist in the committed snapshot, then retain the exact POST DTO.
        _committed_relation(
            committed_snapshot, body.source_id, body.target_id
        )
        relation = dict(created)
        committed = psyke_revision_store.commit_mutation(
            locked.document_id,
            locked.incarnation,
            _collection_digest(committed_snapshot),
            mutation_id=mutation_id,
            mutation_fingerprint=fingerprint,
            result=relation,
        )
        _publish_revision(response, locked.incarnation, committed.revision)
        return {"ok": True, "relation": relation, "revision": committed.revision}


@router.post("/api/psyke/progressions")
async def create_progression(
    request: Request,
    body: PsykeProgressionCreate,
    doc: int | None = Query(None),
    response: Response = None,
):
    core = request.app.state.core
    request_document_incarnation(request, required=True)
    async with locked_document_request(request, doc, mutation=True) as locked:
        precondition, mutation_id = _conditional_preconditions(
            request, locked.incarnation, conditional=True
        )
        assert precondition is not None and mutation_id is not None
        snapshot = await _collection_snapshot(core, locked.project_id)
        state = psyke_revision_store.observe(
            locked.document_id,
            locked.incarnation,
            _collection_digest(snapshot),
        )
        payload = body.model_dump()
        fingerprint = _mutation_fingerprint(
            "create_progression", payload, precondition.revision
        )
        replay = _conditional_retry(
            state,
            precondition,
            mutation_id,
            fingerprint,
            locked.incarnation,
        )
        if replay is not None:
            _publish_revision(response, locked.incarnation, state.revision)
            return {"ok": True, "progression": replay, "revision": state.revision}

        if not any(entry.get("id") == body.entry_id for entry in snapshot.entries):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"PSYKE element {body.entry_id} not found",
            )
        try:
            created = (
                await core.request(
                    "POST",
                    f"/api/projects/{locked.project_id}/psyke/progressions",
                    json=payload,
                )
            ).json()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                raise HTTPException(
                    status_code=404,
                    detail="The PSYKE entry or scene was not found.",
                ) from exc
            raise
        if not isinstance(created, dict) or _progression_id(created) is None:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="The core returned an invalid PSYKE progression.",
            )
        progression_id = _progression_id(created)
        assert progression_id is not None
        committed_snapshot = await _collection_snapshot(core, locked.project_id)
        progression = _committed_progression(committed_snapshot, progression_id)
        committed = psyke_revision_store.commit_mutation(
            locked.document_id,
            locked.incarnation,
            _collection_digest(committed_snapshot),
            mutation_id=mutation_id,
            mutation_fingerprint=fingerprint,
            result=progression,
        )
        _publish_revision(response, locked.incarnation, committed.revision)
        return {
            "ok": True,
            "progression": progression,
            "revision": committed.revision,
        }


@router.patch("/api/psyke/progressions/{progression_id}")
async def update_progression(
    request: Request,
    progression_id: int,
    body: PsykeProgressionUpdate,
    doc: int | None = Query(None),
    response: Response = None,
):
    core = request.app.state.core
    request_document_incarnation(request, required=True)
    if progression_id < 1:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="PSYKE progression id must be positive.",
        )
    fields = set(body.model_fields_set)
    if not fields:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A PSYKE progression patch must change at least one field.",
        )
    if "text" in fields and body.text is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="PSYKE progression text cannot be null.",
        )

    async with locked_document_request(request, doc, mutation=True) as locked:
        precondition, mutation_id = _conditional_preconditions(
            request, locked.incarnation, conditional=True
        )
        assert precondition is not None and mutation_id is not None
        snapshot = await _collection_snapshot(core, locked.project_id)
        state = psyke_revision_store.observe(
            locked.document_id,
            locked.incarnation,
            _collection_digest(snapshot),
        )
        supplied_patch = body.model_dump(exclude_unset=True)
        fingerprint = _mutation_fingerprint(
            "update_progression",
            supplied_patch,
            precondition.revision,
            element_id=progression_id,
        )
        replay = _conditional_retry(
            state,
            precondition,
            mutation_id,
            fingerprint,
            locked.incarnation,
        )
        if replay is not None:
            _publish_revision(response, locked.incarnation, state.revision)
            return {"ok": True, "progression": replay, "revision": state.revision}

        current = next(
            (
                progression
                for progression in snapshot.progressions
                if _progression_id(progression) == progression_id
            ),
            None,
        )
        if current is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"PSYKE progression {progression_id} not found",
            )
        current_text = current.get("text")
        current_scene_id = current.get("scene_id")
        if not isinstance(current_text, str) or (
            current_scene_id is not None
            and (
                not isinstance(current_scene_id, int)
                or isinstance(current_scene_id, bool)
                or current_scene_id < 1
            )
        ):
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="The core returned an invalid PSYKE progression.",
            )
        payload = {
            "text": body.text if "text" in fields else current_text,
            "scene_id": body.scene_id if "scene_id" in fields else current_scene_id,
        }
        if payload == {"text": current_text, "scene_id": current_scene_id}:
            progression = dict(current)
            committed = psyke_revision_store.commit_mutation(
                locked.document_id,
                locked.incarnation,
                _collection_digest(snapshot),
                mutation_id=mutation_id,
                mutation_fingerprint=fingerprint,
                result=progression,
            )
            _publish_revision(response, locked.incarnation, committed.revision)
            return {
                "ok": True,
                "progression": progression,
                "revision": committed.revision,
            }
        try:
            await core.request(
                "PATCH",
                (
                    f"/api/projects/{locked.project_id}/psyke/progressions/"
                    f"{progression_id}"
                ),
                json=payload,
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                raise HTTPException(
                    status_code=404,
                    detail=(
                        f"PSYKE progression {progression_id} or its scene was not found"
                    ),
                ) from exc
            raise
        committed_snapshot = await _collection_snapshot(core, locked.project_id)
        progression = _committed_progression(committed_snapshot, progression_id)
        committed = psyke_revision_store.commit_mutation(
            locked.document_id,
            locked.incarnation,
            _collection_digest(committed_snapshot),
            mutation_id=mutation_id,
            mutation_fingerprint=fingerprint,
            result=progression,
        )
        _publish_revision(response, locked.incarnation, committed.revision)
        return {
            "ok": True,
            "progression": progression,
            "revision": committed.revision,
        }


@router.delete("/api/psyke/elements/{element_id}")
async def delete_element(request: Request, element_id: int, doc: int | None = Query(None)):
    """Delete a PSYKE element by id. Forwards to the core's existing project-scoped
    delete route (which also unlinks any bound manuscript Character). The id is typed
    int (the create response stringifies it, but it round-trips), so a non-numeric id
    is a clean 422 here; a missing id (core 404) is translated rather than surfacing
    as an opaque 500 from the in-process transport's raise_for_status."""
    core = request.app.state.core
    async with locked_document_request(request, doc, mutation=True) as locked:
        try:
            await core.request(
                "DELETE", f"/api/projects/{locked.project_id}/psyke/entries/{element_id}"
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                raise HTTPException(status_code=404, detail=f"PSYKE element {element_id} not found")
            raise
        return {"ok": True, "deleted": element_id}
