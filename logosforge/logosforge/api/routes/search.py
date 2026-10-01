"""Typed, project-scoped search."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from logosforge.api import schemas
from logosforge.api.deps import get_db, get_project
from logosforge.api.errors import bad_request
from logosforge.db import Database
from logosforge.models.models import Project
from logosforge.project_search import search_project as run_project_search

router = APIRouter(tags=["search"])


@router.get(
    "/projects/{project_id}/search",
    response_model=schemas.ProjectSearchResponseDTO,
    response_model_exclude_none=True,
)
def search_project(
    q: Annotated[str, Query(min_length=1, max_length=500)],
    project: Annotated[Project, Depends(get_project)],
    db: Annotated[Database, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
    kinds: Annotated[
        list[schemas.ProjectSearchKind] | None,
        Query(),
    ] = None,
):
    query = q.strip()
    if not query:
        raise bad_request("Search query must not be empty")
    matches = run_project_search(
        db,
        project.id,
        query,
        kinds=set(kinds) if kinds is not None else None,
        limit=limit,
    )
    return schemas.ProjectSearchResponseDTO(
        query=query,
        matches=[schemas.ProjectSearchMatchDTO(**match.__dict__) for match in matches],
        limit=limit,
    )
