"""Manual story-outliner endpoints (GET/PUT /api/outline/items) — local store.

The node shape is owned by the frontend (stored opaquely). Scoped per document
via the optional ``doc`` query param (omitting it targets the default document).
"""
from __future__ import annotations

from fastapi import APIRouter, Query, Request, Response

from app.document_lifecycle import locked_document_request
from app.local_state import (
    MutationIdConflict,
    OutlineItemsDocument,
    ResourceRevisionConflict,
    outline_items_store,
)
from app.persistence_order import accept_persistence_write, request_persistence_order
from app.resource_revision import (
    mutation_id_conflict,
    request_mutation_id,
    request_revision_precondition,
    resource_etag,
    revision_conflict,
)

router = APIRouter()


@router.get("/api/outline/items", response_model=OutlineItemsDocument)
async def get_outline_items(
    request: Request,
    response: Response,
    doc: int | None = Query(None),
) -> OutlineItemsDocument:
    async with locked_document_request(request, doc) as locked:
        outline = outline_items_store.get_document(locked.document_id)
        response.headers["ETag"] = resource_etag(
            "outline", locked.incarnation, outline.revision
        )
        return outline


@router.put("/api/outline/items", response_model=OutlineItemsDocument)
async def put_outline_items(
    request: Request,
    response: Response,
    payload: OutlineItemsDocument,
    doc: int | None = Query(None),
) -> OutlineItemsDocument:
    async with locked_document_request(request, doc, mutation=True) as locked:
        precondition = request_revision_precondition(
            request,
            "outline",
            locked.incarnation,
            required=doc is not None,
        )
        mutation_id = request_mutation_id(request)
        if precondition is not None and not precondition.matches_resource:
            current = outline_items_store.get_document(locked.document_id)
            raise revision_conflict(
                "outline",
                locked.incarnation,
                precondition.revision,
                current.revision,
            )
        order = request_persistence_order(request)
        with accept_persistence_write(
            "outline",
            locked.document_id,
            order,
            current_revision=lambda: outline_items_store.get_document(
                locked.document_id
            ).revision,
        ) as accepted:
            if not accepted:
                outline = outline_items_store.get_document(locked.document_id)
            else:
                try:
                    outline = outline_items_store.replace_document(
                        locked.document_id,
                        payload.items,
                        expected_revision=(
                            precondition.revision if precondition is not None else None
                        ),
                        mutation_id=mutation_id,
                    )
                except ResourceRevisionConflict as exc:
                    raise revision_conflict(
                        "outline",
                        locked.incarnation,
                        exc.expected_revision,
                        exc.current_revision,
                    ) from exc
                except MutationIdConflict as exc:
                    raise mutation_id_conflict(exc.mutation_id) from exc
                accepted.commit(outline.revision)
            response.headers["ETag"] = resource_etag(
                "outline", locked.incarnation, outline.revision
            )
            return outline
