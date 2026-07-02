"""PSYKE (story-bible) — wraps the core's project-scoped PSYKE routes.

The Whiteboard frontend is project-agnostic and uses a slightly different DTO,
so this router injects the pinned project id and translates between the core
``PsykeEntryDTO`` (id:int, ``type``, ``details`` dict) and the frontend
``PsykeEntry`` (id:str, ``entry_type``, free-text ``description``). The
frontend's ``description`` is stored in the core entry's ``details["description"]``
so it round-trips without a new core column.
"""
from __future__ import annotations

import httpx
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.core_client import resolve_pid

router = APIRouter()

# The element types the Whiteboard offers (mirrors the frontend form).
ALLOWED_TYPES = {"character", "place", "object", "lore", "theme", "other"}


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


@router.get("/api/psyke/search")
async def search(request: Request, q: str = Query(""), doc: int | None = Query(None)):
    core = request.app.state.core
    pid = await resolve_pid(core, doc)
    entries = (
        await core.request(
            "GET", f"/api/projects/{pid}/psyke/search", params={"q": q}
        )
    ).json()
    return {"query": q, "results": [_to_frontend(e) for e in entries]}


@router.post("/api/psyke/elements")
async def create_element(request: Request, body: PsykeElementCreate, doc: int | None = Query(None)):
    core = request.app.state.core
    pid = await resolve_pid(core, doc)
    payload = {
        "name": body.name,
        "type": body.type if body.type in ALLOWED_TYPES else "other",
        "notes": body.notes,
        "aliases": [],
        "is_global": False,
        "details": {"description": body.description} if body.description else {},
    }
    created = (
        await core.request(
            "POST", f"/api/projects/{pid}/psyke/entries", json=payload
        )
    ).json()
    return {"ok": True, "element": _to_frontend(created)}


@router.patch("/api/psyke/elements/{element_id}")
async def update_element(
    request: Request, element_id: int, body: PsykeElementUpdate, doc: int | None = Query(None)
):
    """Partially update a PSYKE element. Forwards only the provided fields to the
    core's PATCH; the frontend ``description`` maps to the entry's
    ``details['description']``. A missing id (core 404) is translated, not a 500."""
    core = request.app.state.core
    pid = await resolve_pid(core, doc)
    payload: dict = {}
    if body.name is not None:
        payload["name"] = body.name
    if body.type is not None:
        payload["type"] = body.type if body.type in ALLOWED_TYPES else "other"
    if body.notes is not None:
        payload["notes"] = body.notes
    if body.description is not None:
        payload["details"] = {"description": body.description} if body.description else {}
    try:
        updated = (
            await core.request(
                "PATCH", f"/api/projects/{pid}/psyke/entries/{element_id}", json=payload
            )
        ).json()
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            raise HTTPException(status_code=404, detail=f"PSYKE element {element_id} not found")
        raise
    return {"ok": True, "element": _to_frontend(updated)}


@router.delete("/api/psyke/elements/{element_id}")
async def delete_element(request: Request, element_id: int, doc: int | None = Query(None)):
    """Delete a PSYKE element by id. Forwards to the core's existing project-scoped
    delete route (which also unlinks any bound manuscript Character). The id is typed
    int (the create response stringifies it, but it round-trips), so a non-numeric id
    is a clean 422 here; a missing id (core 404) is translated rather than surfacing
    as an opaque 500 from the in-process transport's raise_for_status."""
    core = request.app.state.core
    pid = await resolve_pid(core, doc)
    try:
        await core.request(
            "DELETE", f"/api/projects/{pid}/psyke/entries/{element_id}"
        )
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            raise HTTPException(status_code=404, detail=f"PSYKE element {element_id} not found")
        raise
    return {"ok": True, "deleted": element_id}
