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

from fastapi import APIRouter, Query, Request

from app.core_client import resolve_pid
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
) -> dict[str, Any]:
    """Assemble the bundle dict from already-fetched pieces. Pure + testable.

    Each subsystem is carried in the SAME shape the app's own GET returns, so the
    bundle is a faithful, lossless snapshot: manuscript blocks (verbatim), the
    opaque outline node list, comments (with their block-index anchors), and the
    PSYKE entries in the frontend shape (``entry_type``/``description``/…).
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
            "manuscript": {"blocks": [b.model_dump(exclude_none=True) for b in wb.blocks]},
            "outline": list(outline_items),
            "comments": [c.model_dump() for c in comments.comments],
            "psyke": {"elements": list(psyke_elements)},
        },
    }


async def _list_psyke(core, pid: int) -> list[dict[str, Any]]:
    """All PSYKE entries for the project, in the frontend shape. Best-effort — a
    project with an empty/unreadable bible exports an empty list rather than
    failing the whole bundle."""
    try:
        entries = (await core.request("GET", f"/api/projects/{pid}/psyke/entries")).json()
    except Exception:
        return []
    return [_to_frontend(e) for e in entries]


@router.get("/api/export/project")
async def export_project(request: Request, doc: int | None = Query(None)) -> dict[str, Any]:
    """Return the complete ``.lfbundle`` for the given document (default doc when
    ``doc`` is omitted). One request = the whole project, one pass."""
    core = request.app.state.core
    pid = await resolve_pid(core, doc)
    wb = whiteboard_store.get(str(pid))
    outline_items = outline_items_store.get(str(pid))
    comments = comments_store.get(str(pid))
    psyke_elements = await _list_psyke(core, pid)
    exported_at = datetime.now(timezone.utc).isoformat()
    return build_project_bundle(pid, wb, outline_items, comments, psyke_elements, exported_at)
