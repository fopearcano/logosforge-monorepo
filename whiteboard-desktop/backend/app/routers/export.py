"""Project bundle export — GET /api/export/project?doc=<id>.

Assembles ONE self-contained ``.lfbundle`` JSON for a single document/project:
manuscript blocks + Drafter scratch pages + the manual outline + comments + the
PSYKE story bible. This is the Whiteboard side of the Whiteboard -> Pro
migration (and doubles as a portable single-project backup/transfer format).

Read-only: it never mutates any store, and it only READS the core API (PSYKE),
so it respects the core's ownership rules — no core change is required.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Query, Request, status

from app.core_client import core_error_message
from app.document_lifecycle import locked_document_request
from app.local_state import (
    CommentsDocument,
    DrafterPage,
    WhiteboardDocument,
    comments_store,
    drafter_pages_store,
    outline_items_store,
    whiteboard_store,
)
from app.routers.psyke import _to_frontend

router = APIRouter()

BUNDLE_FORMAT = "logosforge-project-bundle"
BUNDLE_VERSION = "1.0"
SOURCE_APP = "logosforge-whiteboard"


def build_project_bundle(
    pid: int | str,
    wb: WhiteboardDocument,
    outline_items: list[dict[str, Any]],
    comments: CommentsDocument,
    psyke_elements: list[dict[str, Any]],
    exported_at: str,
    *,
    psyke_relations: list[dict[str, Any]] | None = None,
    psyke_progressions: list[dict[str, Any]] | None = None,
    progression_tracks: list[dict[str, Any]] | None = None,
    drafter_pages: list[DrafterPage] | None = None,
) -> dict[str, Any]:
    """Assemble the bundle dict from already-fetched pieces. Pure + testable.

    Each subsystem is carried in the SAME shape the app's own GET returns, so the
    bundle is a faithful, lossless snapshot: manuscript blocks (verbatim),
    Drafter pages, the opaque outline node list, comments (with their block-index
    anchors), and the PSYKE entries in the frontend shape
    (``entry_type``/``description``/…),
    plus the core's canonical relation and progression DTOs.  The latter are
    additive fields in bundle version 1.0, whose readers are required to be
    forward-compatible with additional PSYKE sections.
    """
    return {
        "format": BUNDLE_FORMAT,
        "version": BUNDLE_VERSION,
        "exportedAt": exported_at,
        "source": {"app": SOURCE_APP},
        "project": {
            "id": str(pid),
            "title": wb.title,
            "mode": wb.mode,
            "settings": dict(wb.settings),
            "manuscript": {"blocks": [b.model_dump(exclude_none=True) for b in wb.blocks]},
            "outline": list(outline_items),
            "comments": [c.model_dump() for c in comments.comments],
            "drafter": {
                "pages": [page.model_dump() for page in (drafter_pages or [])],
            },
            "psyke": {
                "elements": list(psyke_elements),
                "relations": list(psyke_relations or []),
                "progressions": list(psyke_progressions or []),
            },
            # Additive v1.0 section: legacy readers ignore unknown project keys;
            # Pro readers can remap source PSYKE ids and retain document anchors.
            "progression_tracks": list(progression_tracks or []),
        },
    }


async def _read_psyke_collection(
    core,
    pid: int,
    resource: str,
    label: str,
) -> list[dict[str, Any]]:
    """Read one complete core-owned PSYKE collection or abort the export."""
    try:
        value = (
            await core.request(
                "GET", f"/api/projects/{pid}/psyke/{resource}"
            )
        ).json()
    except httpx.HTTPStatusError as exc:
        detail = core_error_message(exc, fallback=f"{label} could not be read")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Project bundle export aborted: {detail}",
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Project bundle export aborted because {label} could not be read.",
        ) from exc
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Project bundle export aborted: the {label} response was invalid.",
        )
    return value


async def _list_psyke(core, pid: int) -> list[dict[str, Any]]:
    """Return every PSYKE entry or abort the supposedly complete export.

    An empty list is a valid bible; a transport, project, or payload error is not.
    Silently translating those errors to ``[]`` would create a bundle that looks
    complete while omitting story data — especially dangerous when used as backup.
    """
    entries = await _read_psyke_collection(core, pid, "entries", "PSYKE")
    try:
        return [_to_frontend(e) for e in entries]
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Project bundle export aborted: a PSYKE entry was invalid.",
        ) from exc


def _positive_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _nonnegative_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


async def _list_psyke_relations(core, pid: int) -> list[dict[str, Any]]:
    """Return canonical relation DTOs without silently dropping bad rows."""
    rows = await _read_psyke_collection(
        core, pid, "relations", "PSYKE relations"
    )
    relations: list[dict[str, Any]] = []
    for row in rows:
        relation_id = row.get("id")
        source_id = row.get("source_id")
        target_id = row.get("target_id")
        source = row.get("source")
        target = row.get("target")
        relation_type = row.get("relation_type")
        if (
            not isinstance(relation_id, str)
            or not _positive_int(source_id)
            or not _positive_int(target_id)
            or source_id == target_id
            or relation_id != f"{source_id}:{target_id}"
            or not isinstance(source, str)
            or not isinstance(target, str)
            or not isinstance(relation_type, str)
        ):
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=(
                    "Project bundle export aborted: the PSYKE relations "
                    "response was invalid."
                ),
            )
        relations.append({
            "id": relation_id,
            "source_id": source_id,
            "target_id": target_id,
            "source": source,
            "target": target,
            "relation_type": relation_type,
        })
    return sorted(
        relations,
        key=lambda item: (
            item["source_id"],
            item["target_id"],
            item["relation_type"],
            item["id"],
        ),
    )


async def _list_psyke_progressions(core, pid: int) -> list[dict[str, Any]]:
    """Return canonical progression DTOs without silently dropping bad rows."""
    rows = await _read_psyke_collection(
        core, pid, "progressions", "PSYKE progressions"
    )
    progressions: list[dict[str, Any]] = []
    for row in rows:
        progression_id = row.get("id")
        entry_id = row.get("entry_id")
        text = row.get("text")
        scene_id = row.get("scene_id")
        scene_title = row.get("scene_title")
        sort_order = row.get("sort_order")
        if (
            not _positive_int(progression_id)
            or not _positive_int(entry_id)
            or not isinstance(text, str)
            or (scene_id is not None and not _positive_int(scene_id))
            or not isinstance(scene_title, str)
            or not isinstance(sort_order, int)
            or isinstance(sort_order, bool)
            or sort_order < 0
        ):
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=(
                    "Project bundle export aborted: the PSYKE progressions "
                    "response was invalid."
                ),
            )
        progressions.append({
            "id": progression_id,
            "entry_id": entry_id,
            "text": text,
            "scene_id": scene_id,
            "scene_title": scene_title,
            "sort_order": sort_order,
        })
    return sorted(
        progressions,
        key=lambda item: (item["entry_id"], item["sort_order"], item["id"]),
    )


async def _list_progression_tracks(core, pid: int) -> list[dict[str, Any]]:
    """Read and strip the canonical Progressions snapshot for portable export."""
    try:
        snapshot = (
            await core.request("GET", f"/api/projects/{pid}/progressions")
        ).json()
    except httpx.HTTPStatusError as exc:
        detail = core_error_message(exc, fallback="Progressions could not be read")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Project bundle export aborted: {detail}",
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Project bundle export aborted because Progressions could not be read.",
        ) from exc

    if (
        not isinstance(snapshot, dict)
        or snapshot.get("project_id") != pid
        or not isinstance(snapshot.get("revision"), str)
        or len(snapshot["revision"]) != 64
        or any(char not in "0123456789abcdef" for char in snapshot["revision"])
        or not isinstance(snapshot.get("tracks"), list)
        or not isinstance(snapshot.get("summary"), dict)
    ):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Project bundle export aborted: the Progressions response was invalid.",
        )

    allowed_kinds = {"story", "character", "relationship", "theme", "world", "custom"}
    allowed_anchors = {"unanchored", "scene", "document_block"}
    result: list[dict[str, Any]] = []
    track_ids: set[int] = set()
    beat_ids: set[int] = set()
    for track in snapshot["tracks"]:
        if not isinstance(track, dict):
            raise HTTPException(status_code=502, detail="Project bundle export aborted: the Progressions response was invalid.")
        track_id = track.get("id")
        primary_id = track.get("primary_psyke_entry_id")
        secondary_id = track.get("secondary_psyke_entry_id")
        if (
            not _positive_int(track_id)
            or track_id in track_ids
            or track.get("project_id") != pid
            or track.get("kind") not in allowed_kinds
            or not isinstance(track.get("title"), str)
            or not track["title"].strip()
            or not isinstance(track.get("description"), str)
            or not isinstance(track.get("color_label"), str)
            or not _nonnegative_int(track.get("sort_order"))
            or not isinstance(track.get("legacy_compatibility"), bool)
            or (primary_id is not None and not _positive_int(primary_id))
            or (secondary_id is not None and not _positive_int(secondary_id))
            or not isinstance(track.get("primary_psyke_entry_name"), str)
            or not isinstance(track.get("primary_psyke_entry_type"), str)
            or not isinstance(track.get("secondary_psyke_entry_name"), str)
            or not isinstance(track.get("secondary_psyke_entry_type"), str)
            or not isinstance(track.get("beats"), list)
        ):
            raise HTTPException(status_code=502, detail="Project bundle export aborted: the Progressions response was invalid.")
        track_ids.add(track_id)
        beats: list[dict[str, Any]] = []
        for beat in track["beats"]:
            if not isinstance(beat, dict):
                raise HTTPException(status_code=502, detail="Project bundle export aborted: the Progressions response was invalid.")
            beat_id = beat.get("id")
            anchor_kind = beat.get("anchor_kind")
            scene_id = beat.get("scene_id")
            anchor_ref = beat.get("anchor_ref")
            if (
                not _positive_int(beat_id)
                or beat_id in beat_ids
                or beat.get("track_id") != track_id
                or not isinstance(beat.get("text"), str)
                or not _nonnegative_int(beat.get("sort_order"))
                or anchor_kind not in allowed_anchors
                or (scene_id is not None and not _positive_int(scene_id))
                or not isinstance(beat.get("scene_title"), str)
                or (anchor_ref is not None and not isinstance(anchor_ref, str))
                or not isinstance(beat.get("anchor_label"), str)
                or (anchor_kind == "document_block" and (scene_id is not None or not isinstance(anchor_ref, str) or not anchor_ref.strip()))
                or (anchor_kind == "scene" and not _positive_int(scene_id))
                or (anchor_kind == "unanchored" and (scene_id is not None or anchor_ref is not None))
            ):
                raise HTTPException(status_code=502, detail="Project bundle export aborted: the Progressions response was invalid.")
            beat_ids.add(beat_id)
            beats.append({
                "id": beat_id,
                "track_id": track_id,
                "text": beat["text"],
                "sort_order": beat["sort_order"],
                "anchor_kind": anchor_kind,
                "scene_id": scene_id,
                "scene_title": beat["scene_title"],
                "anchor_ref": anchor_ref,
                "anchor_label": beat["anchor_label"],
            })
        beats.sort(key=lambda beat: (beat["sort_order"], beat["id"]))
        result.append({
            "id": track_id,
            "kind": track["kind"],
            "title": track["title"],
            "description": track["description"],
            "color_label": track["color_label"],
            "sort_order": track["sort_order"],
            "legacy_compatibility": track["legacy_compatibility"],
            "primary_psyke_entry_id": primary_id,
            "primary_psyke_entry_name": track["primary_psyke_entry_name"],
            "primary_psyke_entry_type": track["primary_psyke_entry_type"],
            "secondary_psyke_entry_id": secondary_id,
            "secondary_psyke_entry_name": track["secondary_psyke_entry_name"],
            "secondary_psyke_entry_type": track["secondary_psyke_entry_type"],
            "beats": beats,
        })
    return sorted(result, key=lambda track: (track["sort_order"], track["id"]))


@router.get("/api/export/project")
async def export_project(request: Request, doc: int | None = Query(None)) -> dict[str, Any]:
    """Return the complete ``.lfbundle`` for the given document (default doc when
    ``doc`` is omitted). One request = the whole project, one pass."""
    core = request.app.state.core
    # Keep the numeric id and its incarnation stable across every subsystem read;
    # DELETE/reuse and all mutations share this same lifecycle lock.
    async with locked_document_request(request, doc) as locked:
        wb = whiteboard_store.get(locked.document_id)
        outline_items = outline_items_store.get(locked.document_id)
        comments = comments_store.get(locked.document_id)
        drafter_pages = drafter_pages_store.get_document(locked.document_id).pages
        psyke_elements = await _list_psyke(core, locked.project_id)
        psyke_relations = await _list_psyke_relations(core, locked.project_id)
        psyke_progressions = await _list_psyke_progressions(
            core, locked.project_id
        )
        progression_tracks = await _list_progression_tracks(core, locked.project_id)
        exported_at = datetime.now(timezone.utc).isoformat()
        return build_project_bundle(
            locked.project_id,
            wb,
            outline_items,
            comments,
            psyke_elements,
            exported_at,
            psyke_relations=psyke_relations,
            psyke_progressions=psyke_progressions,
            progression_tracks=progression_tracks,
            drafter_pages=drafter_pages,
        )
