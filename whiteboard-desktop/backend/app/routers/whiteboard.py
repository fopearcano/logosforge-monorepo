"""Whiteboard document endpoints (GET/POST/PUT /api/whiteboard) — local store.

Desktop-only board state (no core equivalent), served from the per-document
atomic-JSON store. Each call is scoped to a document via the optional ``doc``
query param (the document/core-project id); omitting it targets the default
document (back-compat).
"""
from __future__ import annotations

from fastapi import APIRouter, Query, Request, Response, status

from app.document_lifecycle import locked_document_request
from app.local_state import (
    MutationIdConflict,
    ResourceRevisionConflict,
    WhiteboardCreate,
    WhiteboardDocument,
    WhiteboardUpdate,
    whiteboard_store,
)
from app.persistence_order import accept_persistence_write, request_persistence_order
from app.resource_revision import (
    mutation_id_conflict,
    request_mutation_id,
    request_revision_precondition,
    resource_already_exists,
    resource_etag,
    revision_conflict,
)

router = APIRouter()


@router.get("/api/whiteboard", response_model=WhiteboardDocument)
async def get_whiteboard(
    request: Request,
    response: Response,
    doc: int | None = Query(None),
) -> WhiteboardDocument:
    async with locked_document_request(request, doc) as locked:
        document = whiteboard_store.get(locked.document_id)
        response.headers["ETag"] = resource_etag(
            "whiteboard", locked.incarnation, document.revision
        )
        return document


@router.post(
    "/api/whiteboard", response_model=WhiteboardDocument,
    status_code=status.HTTP_201_CREATED,
)
async def create_whiteboard(
    request: Request,
    response: Response,
    payload: WhiteboardCreate,
    doc: int | None = Query(None),
) -> WhiteboardDocument:
    async with locked_document_request(
        request,
        doc,
        mutation=True,
        create_missing=True,
    ) as locked:
        if whiteboard_store.exists(locked.document_id):
            current = whiteboard_store.get(locked.document_id)
            raise resource_already_exists(
                "whiteboard", locked.incarnation, current.revision
            )
        document = whiteboard_store.create(locked.document_id, payload)
        response.headers["ETag"] = resource_etag(
            "whiteboard", document.incarnation, document.revision
        )
        return document


@router.put("/api/whiteboard", response_model=WhiteboardDocument)
async def update_whiteboard(
    request: Request,
    response: Response,
    payload: WhiteboardUpdate,
    doc: int | None = Query(None),
) -> WhiteboardDocument:
    async with locked_document_request(request, doc, mutation=True) as locked:
        precondition = request_revision_precondition(
            request,
            "whiteboard",
            locked.incarnation,
            required=doc is not None,
        )
        mutation_id = request_mutation_id(request)
        if precondition is not None and not precondition.matches_resource:
            current = whiteboard_store.get(locked.document_id)
            raise revision_conflict(
                "whiteboard",
                locked.incarnation,
                precondition.revision,
                current.revision,
            )
        order = request_persistence_order(request)
        with accept_persistence_write(
            "whiteboard",
            locked.document_id,
            order,
            current_revision=lambda: whiteboard_store.get(locked.document_id).revision,
        ) as accepted:
            if not accepted:
                document = whiteboard_store.get(locked.document_id)
            else:
                try:
                    document = whiteboard_store.update(
                        locked.document_id,
                        payload,
                        expected_revision=(
                            precondition.revision if precondition is not None else None
                        ),
                        mutation_id=mutation_id,
                    )
                except ResourceRevisionConflict as exc:
                    raise revision_conflict(
                        "whiteboard",
                        locked.incarnation,
                        exc.expected_revision,
                        exc.current_revision,
                    ) from exc
                except MutationIdConflict as exc:
                    raise mutation_id_conflict(exc.mutation_id) from exc
                accepted.commit(document.revision)
            response.headers["ETag"] = resource_etag(
                "whiteboard", locked.incarnation, document.revision
            )
            return document
