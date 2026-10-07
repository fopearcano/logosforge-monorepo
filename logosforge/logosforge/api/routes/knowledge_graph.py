"""Bounded, project-scoped Narrative Knowledge Graph reads."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Response
from fastapi.responses import JSONResponse

from logosforge.api import schemas, serializers
from logosforge.api.deps import get_broker, get_db, get_project
from logosforge.api.errors import ApiError, bad_request, conflict, not_found
from logosforge.api.events import ApiEventBroker
from logosforge.db import (
    Database,
    KnowledgeGraphCommandError,
    KnowledgeGraphEdgeNotFound,
    KnowledgeGraphIdempotencyKeyConflict,
    KnowledgeGraphProjectNotFound,
    KnowledgeGraphReviewStateCorrupt,
    KnowledgeGraphRevisionConflict,
)
from logosforge.graph_gravity import compute_canonical_gravity_totals
from logosforge.knowledge_graph.builder import build_knowledge_graph
from logosforge.models.models import Project

router = APIRouter(tags=["knowledge-graph"])

_RECEIPT_RESPONSE_HEADERS = {
    "Cache-Control": "no-store",
    "Vary": "Authorization, Idempotency-Key",
}

_CORRUPT_REVIEW_STATE_MESSAGE = (
    "Knowledge Graph review state is inconsistent. "
    "Repair it before continuing edge review."
)


def _review_state_corrupt_error() -> ApiError:
    """Return the stable, non-disclosing envelope for persisted corruption."""
    return ApiError(
        500,
        _CORRUPT_REVIEW_STATE_MESSAGE,
        code="knowledge_graph_review_state_corrupt",
    )


def _build_graph_or_500(db: Database, project_id: int):
    """Build a graph while keeping persisted row details out of HTTP errors."""
    try:
        return build_knowledge_graph(db, project_id).graph
    except KnowledgeGraphProjectNotFound as exc:
        # The dependency resolved the project earlier, but deletion may win the
        # race before the builder opens its persisted-review snapshot.
        raise not_found(f"Project {project_id} not found") from exc
    except KnowledgeGraphReviewStateCorrupt as exc:
        raise _review_state_corrupt_error() from exc


def _receipt_error(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message}},
        headers=_RECEIPT_RESPONSE_HEADERS,
    )


def _find_edge(graph, source: str, target: str, edge_type: str):
    """Resolve one public directional identity inside this project graph."""
    for edge in graph.edges:
        if (
            serializers.knowledge_graph_wire_key(edge.source) == source
            and serializers.knowledge_graph_wire_key(edge.target) == target
            and edge.edge_type == edge_type
        ):
            return edge
    return None


@router.get(
    "/projects/{project_id}/knowledge-graph",
    response_model=schemas.KnowledgeGraphReadDTO,
)
def get_knowledge_graph(
    project: Annotated[Project, Depends(get_project)],
    db: Annotated[Database, Depends(get_db)],
    focus_key: Annotated[
        str | None,
        Query(min_length=1, max_length=512),
    ] = None,
    depth: Annotated[int, Query(ge=1, le=2)] = 1,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    include_inferred: bool = True,
    view_mode: Annotated[
        schemas.KnowledgeGraphViewMode,
        Query(),
    ] = "project_map",
):
    """Return a bounded canonical view or a 1-/2-hop node neighborhood.

    The graph is rebuilt deterministically from the resolved project only.  A
    stale or foreign ``focus_key`` is indistinguishable from any unknown key and
    returns 404; no cross-project graph is ever consulted.
    """
    query = schemas.KnowledgeGraphQueryDTO(
        focus_key=focus_key,
        depth=depth,
        limit=limit,
        include_inferred=include_inferred,
        view_mode=view_mode,
    )
    graph = _build_graph_or_500(db, project.id)
    gravity_available, gravity_totals = compute_canonical_gravity_totals(
        db, project.id, graph,
    )
    internal_focus_key = None
    if query.focus_key is not None:
        internal_focus_key = serializers.resolve_knowledge_graph_focus_key(
            graph, query.focus_key,
        )
        visible_keys = serializers.knowledge_graph_view_node_keys(
            graph,
            view_mode=query.view_mode,
            include_inferred=query.include_inferred,
        )
        if internal_focus_key is None or internal_focus_key not in visible_keys:
            raise not_found("Knowledge Graph node not found")
    return serializers.knowledge_graph_read_to_dto(
        graph,
        focus_key=internal_focus_key,
        depth=query.depth,
        limit=query.limit,
        include_inferred=query.include_inferred,
        view_mode=query.view_mode,
        story_gravity_available=gravity_available,
        story_gravity_totals=gravity_totals,
    )


@router.get(
    "/projects/{project_id}/knowledge-graph/hidden-edges",
    response_model=schemas.KnowledgeGraphHiddenEdgePageDTO,
)
def get_hidden_knowledge_graph_edges(
    project: Annotated[Project, Depends(get_project)],
    db: Annotated[Database, Depends(get_db)],
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
):
    """Page through every durable hidden edge decision without stranding it."""
    graph = _build_graph_or_500(db, project.id)
    return serializers.knowledge_graph_hidden_edges_to_dto(
        graph,
        offset=offset,
        limit=limit,
    )


@router.post(
    "/projects/{project_id}/knowledge-graph/commands",
    response_model=schemas.KnowledgeGraphCommandResultDTO,
)
def execute_knowledge_graph_command(
    body: schemas.KnowledgeGraphCommandDTO,
    project: Annotated[Project, Depends(get_project)],
    db: Annotated[Database, Depends(get_db)],
    broker: Annotated[ApiEventBroker, Depends(get_broker)],
    idempotency_key: Annotated[
        str | None,
        Header(alias="Idempotency-Key"),
    ] = None,
):
    """Atomically confirm, hide, or restore one reviewed directional edge."""
    if idempotency_key is None:
        raise bad_request("Idempotency-Key is required")
    command = body.root
    payload = command.model_dump()
    kind = payload.pop("kind")

    try:
        # A durable exact retry is resolved before live-graph construction, so
        # recovery does not depend on the inferred basis still existing.
        result = db.replay_knowledge_graph_command(
            project.id,
            kind=kind,
            idempotency_key=idempotency_key,
            **payload,
        )
        if result is None:
            graph = _build_graph_or_500(db, project.id)
            edge = _find_edge(
                graph,
                payload["source"],
                payload["target"],
                payload["edge_type"],
            )
            source_node = None if edge is None else graph.get_node(edge.source)
            target_node = None if edge is None else graph.get_node(edge.target)
            result = db.execute_knowledge_graph_command(
                project.id,
                kind=kind,
                idempotency_key=idempotency_key,
                edge=edge,
                source_node=source_node,
                target_node=target_node,
                **payload,
            )
    except KnowledgeGraphIdempotencyKeyConflict as exc:
        raise conflict(
            "This Idempotency-Key was already used for a different Knowledge Graph command.",
            code="idempotency_key_conflict",
        ) from exc
    except KnowledgeGraphRevisionConflict as exc:
        raise conflict(
            "Knowledge Graph review state changed after it was loaded. Reload and retry.",
            code="knowledge_graph_conflict",
        ) from exc
    except KnowledgeGraphProjectNotFound as exc:
        raise not_found(f"Project {project.id} not found") from exc
    except KnowledgeGraphEdgeNotFound as exc:
        # A stale and a foreign edge are deliberately indistinguishable.
        raise not_found("Knowledge Graph edge not found") from exc
    except KnowledgeGraphCommandError as exc:
        raise bad_request(str(exc)) from exc
    except KnowledgeGraphReviewStateCorrupt as exc:
        raise _review_state_corrupt_error() from exc

    broker.reconcile()
    # Rebuild after every successful command.  In particular, an exact replay
    # may discover a receipt after another writer advanced review state, so its
    # preflight graph is not safe to return.  ``applied_revision`` intentionally
    # remains the original command revision even if this current map is newer.
    graph = _build_graph_or_500(db, project.id)
    gravity_available, gravity_totals = compute_canonical_gravity_totals(
        db, project.id, graph,
    )

    affected = schemas.KnowledgeGraphEdgeIdentityDTO(
        source=result.affected_edge.source,
        target=result.affected_edge.target,
        edge_type=result.affected_edge.edge_type,
    )
    return schemas.KnowledgeGraphCommandResultDTO(
        knowledge_graph=serializers.knowledge_graph_read_to_dto(
            graph,
            story_gravity_available=gravity_available,
            story_gravity_totals=gravity_totals,
        ),
        changed=result.changed,
        affected_edge=affected,
        replayed=result.replayed,
        applied_revision=result.applied_revision,
    )


@router.get(
    "/projects/{project_id}/knowledge-graph/command-receipt",
    response_model=schemas.KnowledgeGraphCommandReceiptDTO,
)
def get_knowledge_graph_command_receipt(
    response: Response,
    project: Annotated[Project, Depends(get_project)],
    db: Annotated[Database, Depends(get_db)],
    idempotency_key: Annotated[
        str | None,
        Header(alias="Idempotency-Key"),
    ] = None,
):
    """Resolve one committed graph edge-review command by capability."""
    if idempotency_key is None:
        return _receipt_error(400, "bad_request", "Idempotency-Key is required")
    try:
        receipt = db.get_knowledge_graph_command_receipt(
            project.id,
            idempotency_key,
        )
    except KnowledgeGraphCommandError as exc:
        return _receipt_error(400, "bad_request", str(exc))
    if receipt is None:
        return _receipt_error(
            404,
            "knowledge_graph_receipt_not_found",
            "No committed Knowledge Graph command exists for this Idempotency-Key.",
        )
    response.headers.update(_RECEIPT_RESPONSE_HEADERS)
    edge = receipt.original_affected_edge
    return schemas.KnowledgeGraphCommandReceiptDTO(
        project_id=receipt.project_id,
        request_digest=receipt.request_digest,
        command_kind=receipt.kind,
        expected_revision=receipt.expected_revision,
        applied_revision=receipt.applied_revision,
        original_changed=receipt.original_changed,
        original_affected_edge=schemas.KnowledgeGraphEdgeIdentityDTO(
            source=edge.source,
            target=edge.target,
            edge_type=edge.edge_type,
        ),
        committed_at=receipt.created_at,
    )
