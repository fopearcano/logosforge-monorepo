"""Bounded, project-scoped Narrative Knowledge Graph reads."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from logosforge.api import schemas, serializers
from logosforge.api.deps import get_db, get_project
from logosforge.api.errors import not_found
from logosforge.db import Database
from logosforge.knowledge_graph.builder import build_knowledge_graph
from logosforge.models.models import Project

router = APIRouter(tags=["knowledge-graph"])


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
):
    """Return a bounded Project Map or a 1-/2-hop node neighborhood.

    The graph is rebuilt deterministically from the resolved project only.  A
    stale or foreign ``focus_key`` is indistinguishable from any unknown key and
    returns 404; no cross-project graph is ever consulted.
    """
    query = schemas.KnowledgeGraphQueryDTO(
        focus_key=focus_key,
        depth=depth,
        limit=limit,
        include_inferred=include_inferred,
    )
    graph = build_knowledge_graph(db, project.id).graph
    internal_focus_key = None
    if query.focus_key is not None:
        internal_focus_key = serializers.resolve_knowledge_graph_focus_key(
            graph, query.focus_key,
        )
        if internal_focus_key is None:
            raise not_found("Knowledge Graph node not found")
    return serializers.knowledge_graph_read_to_dto(
        graph,
        focus_key=internal_focus_key,
        depth=query.depth,
        limit=query.limit,
        include_inferred=query.include_inferred,
    )
