"""Project bundle export — GET /api/export/project?doc=<id>.

Assembles ONE self-contained ``.lfbundle`` JSON for a single document/project:
manuscript blocks + the manual outline + comments + the PSYKE story bible. This
is the Whiteboard side of the Whiteboard -> Pro migration (and doubles as a
portable single-project backup/transfer format).

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
    WhiteboardDocument,
    comments_store,
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
) -> dict[str, Any]:
    """Assemble the bundle dict from already-fetched pieces. Pure + testable.

    Each subsystem is carried in the SAME shape the app's own GET returns, so the
    bundle is a faithful, lossless snapshot: manuscript blocks (verbatim), the
    opaque outline node list, comments (with their block-index anchors), and the
    PSYKE entries in the frontend shape (``entry_type``/``description``/…),
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
            "psyke": {
                "elements": list(psyke_elements),
                "relations": list(psyke_relations or []),
                "progressions": list(psyke_progressions or []),
            },
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
        psyke_elements = await _list_psyke(core, locked.project_id)
        psyke_relations = await _list_psyke_relations(core, locked.project_id)
        psyke_progressions = await _list_psyke_progressions(
            core, locked.project_id
        )
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
        )
