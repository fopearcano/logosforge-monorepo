"""Document library — list / create / delete whiteboard documents.

A whiteboard 'document' is one core project (for its ISOLATED PSYKE bible) plus a
local blocks file + outline file keyed by that project id. These routes manage the
SET of documents; the per-document blocks/outline/psyke are served by the scoped
routes via the ``?doc=<id>`` query param.
"""
from __future__ import annotations

import asyncio
import logging

import httpx
from fastapi import APIRouter, HTTPException, Request, Response

from app.document_lifecycle import (
    complete_core_allocation,
    document_identity_publication,
    document_incarnation_matches,
    document_lifecycle_lock,
    locked_document_lifecycle,
    request_document_incarnation,
    validate_delete_incarnation,
)
from app.local_state import (
    LocalStateError,
    WhiteboardCreate,
    comments_store,
    outline_items_store,
    psyke_revision_store,
    whiteboard_store,
)
from app.persistence_order import (
    begin_document_delete,
    cancel_document_delete,
    create_document_incarnation,
    request_delete_order_floors,
)
from app.resource_revision import resource_etag

router = APIRouter()
_LOG = logging.getLogger(__name__)
_pending_local_cleanup: set[str] = set()


def _local_document_ids() -> set[str]:
    return set().union(
        whiteboard_store.list_document_ids(),
        outline_items_store.list_document_ids(),
        comments_store.list_document_ids(),
        psyke_revision_store.list_document_ids(),
    )


def _cleanup_local_document_state(doc_id: str) -> list[str]:
    """Best-effort removal after core has made a delete authoritative.

    Every store is attempted even if an earlier one fails. Failed ids remain
    hidden from the library and are retried by subsequent library reads.
    """
    failed: list[str] = []
    for label, store in (
        ("manuscript", whiteboard_store),
        ("outline", outline_items_store),
        ("comments", comments_store),
        ("PSYKE revision metadata", psyke_revision_store),
    ):
        try:
            store.delete(doc_id)
        except Exception:
            failed.append(label)
            _LOG.exception("Could not clean up %s state for deleted document %s", label, doc_id)
    if failed:
        _pending_local_cleanup.add(doc_id)
    else:
        _pending_local_cleanup.discard(doc_id)
    return failed


async def _settle_unpublished_core_project(core, doc_id: str) -> bool:
    """Remove/quarantine an allocation that never published an incarnation.

    This coroutine is run in its own shielded task by ``create_document`` so a
    cancellation cannot interrupt compensation.  Core deletion makes the id
    authoritatively absent; taking the per-id lock before local cleanup also
    ensures no prior request is still using the stale incarnation.  The backend
    persistence tombstone remains until a future successful creation reopens it.

    Returns ``True`` when the core rollback could not be confirmed.
    """
    rollback_failed = False
    try:
        await core.delete_project(int(doc_id))
    except asyncio.CancelledError:
        rollback_failed = True
        _LOG.error("Core rollback was cancelled for unpublished project %s", doc_id)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code != 404:
            rollback_failed = True
            _LOG.exception("Could not roll back unpublished core project %s", doc_id)
    except Exception:
        rollback_failed = True
        _LOG.exception("Could not roll back unpublished core project %s", doc_id)

    async with document_lifecycle_lock(doc_id):
        _cleanup_local_document_state(doc_id)
        begin_document_delete(doc_id)
    return rollback_failed


async def _settle_unpublished_core_project_uninterruptibly(core, doc_id: str) -> bool:
    """Finish compensation before releasing the identity-publication gate."""
    settlement = asyncio.create_task(_settle_unpublished_core_project(core, doc_id))
    while True:
        try:
            return await asyncio.shield(settlement)
        except asyncio.CancelledError:
            # Preserve cancellation by re-raising the original exception in the
            # caller, but never expose the half-created identity in between.
            if settlement.done():
                return settlement.result()
            continue


@router.get("/api/documents")
async def list_documents(request: Request) -> dict:
    """List every document (summary only — no blocks), most-recently-edited first."""
    # Core projects are authoritative. This both prevents a failed post-delete
    # file cleanup from resurrecting a document after restart and discovers
    # orphaned outline/comment-only state for another cleanup attempt.
    projects = await request.app.state.core.list_projects()
    active_ids = {str(project["id"]) for project in projects}
    retry_ids = _pending_local_cleanup | (_local_document_ids() - active_ids)
    for cleanup_id in sorted(retry_ids):
        async with locked_document_lifecycle(cleanup_id):
            # The first core snapshot can race a just-created reused id. Recheck
            # under the same lock used by create/delete before removing files.
            current = await request.app.state.core.list_projects()
            if cleanup_id not in {str(project["id"]) for project in current}:
                _cleanup_local_document_state(cleanup_id)
    # Incarnation is part of the document wire identity. Migrate only existing
    # Whiteboard manuscripts: core may also contain projects owned by another
    # LogosForge surface, and listing Whiteboard documents must not materialize
    # an "Untitled" local shell for those unrelated projects.
    whiteboard_ids = whiteboard_store.list_document_ids()
    for active_id in sorted(active_ids & whiteboard_ids):
        async with locked_document_lifecycle(active_id):
            current = await request.app.state.core.list_projects()
            if active_id in {str(project["id"]) for project in current}:
                whiteboard_store.ensure_incarnation(active_id)
    visible_ids = (active_ids & whiteboard_ids) - _pending_local_cleanup
    return {
        "documents": [
            summary.model_dump()
            for summary in whiteboard_store.list_summaries(include_ids=visible_ids)
        ]
    }


@router.get("/api/documents/{doc_id}/exists")
async def document_exists(request: Request, doc_id: int) -> dict:
    """Authoritative, incarnation-aware reconciliation for an uncertain DELETE."""
    async with locked_document_lifecycle(str(doc_id)):
        expected = request_document_incarnation(request)
        projects = await request.app.state.core.list_projects()
        if not any(int(project["id"]) == doc_id for project in projects):
            return {"exists": False}
        if expected is None:
            return {"exists": True}
        # An expected token names a Whiteboard incarnation, not merely a core
        # numeric id. A core-only project may reuse that id; report the old
        # incarnation absent without creating an unrelated local manuscript.
        if not whiteboard_store.exists(str(doc_id)):
            return {"exists": False}
        actual = whiteboard_store.ensure_incarnation(str(doc_id))
        return {"exists": document_incarnation_matches(expected, actual)}


@router.post("/api/documents", status_code=201)
async def create_document(
    request: Request,
    body: WhiteboardCreate,
    response: Response = None,
) -> dict:
    """Create a new document: a fresh core project (its own PSYKE bible) + an empty
    local blocks file keyed by that project id. Returns the new document."""
    core = request.app.state.core
    title = (body.title or "Untitled").strip() or "Untitled"
    # The core chooses the numeric id, so creation cannot take its per-id lock in
    # advance.  Keep allocation and incarnation publication behind the global
    # gate used by every explicit lifecycle request, always acquiring global
    # before per-id to avoid lock-order cycles.
    async with document_identity_publication():
        doc_id: str | None = None
        published = False
        try:
            allocation, cancelled = await complete_core_allocation(core.create_project(title))
            proj = allocation
            doc_id = str(proj["id"])
            if cancelled:
                raise asyncio.CancelledError
            async with document_lifecycle_lock(doc_id):
                # SQLite may reuse a deleted integer id. Clear any orphaned files before
                # attaching local state to the new project so old outline/comments cannot
                # leak into the new document.
                stale_cleanup_failures = _cleanup_local_document_state(doc_id)
                if stale_cleanup_failures:
                    raise HTTPException(
                        status_code=500,
                        detail=(
                            "Document creation was cancelled because stale local data for the reused "
                            "project id could not be cleared."
                        ),
                    )
                try:
                    with create_document_incarnation(doc_id):
                        doc = whiteboard_store.create(
                            doc_id, WhiteboardCreate(title=title, mode=body.mode, blocks=body.blocks)
                        )
                except LocalStateError as exc:
                    raise HTTPException(
                        status_code=500,
                        detail=f"Document creation was cancelled because local storage failed. {exc}",
                    ) from exc
                published = True
                if response is not None:
                    response.headers["ETag"] = resource_etag(
                        "whiteboard", doc.incarnation, doc.revision
                    )
                return {"ok": True, "document": doc.model_dump()}
        except BaseException as exc:
            if doc_id is not None and not published:
                rollback_failed = await _settle_unpublished_core_project_uninterruptibly(core, doc_id)
                if rollback_failed and isinstance(exc, HTTPException):
                    exc.detail = f"{exc.detail} The empty core project could not be rolled back."
            raise


@router.delete("/api/documents/{doc_id}")
async def delete_document(request: Request, doc_id: int) -> dict:
    """Delete a document: its core project (cascades the PSYKE bible) + its local
    blocks and outline files. Tolerant of an already-deleted core project."""
    core = request.app.state.core
    document_id = str(doc_id)
    async with locked_document_lifecycle(document_id):
        target_exists = await validate_delete_incarnation(request, document_id)
        begin_document_delete(document_id, request_delete_order_floors(request))
        try:
            if target_exists:
                await core.delete_project(doc_id)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                pass
            else:
                cancel_document_delete(document_id)
                raise HTTPException(status_code=502, detail="core project delete failed")
        except Exception:
            cancel_document_delete(document_id)
            raise
        cleanup_failures = _cleanup_local_document_state(document_id)
        return {
            "ok": True,
            "deleted": document_id,
            "cleanup_pending": bool(cleanup_failures),
        }
