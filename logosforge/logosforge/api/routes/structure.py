"""Canonical, scene-derived story-structure endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from logosforge.api import schemas, serializers
from logosforge.api.deps import get_db, get_project
from logosforge.db import Database

router = APIRouter(tags=["structure"])


@router.get(
    "/projects/{project_id}/story-structure",
    response_model=schemas.StoryStructureDTO,
)
def get_story_structure(
    project=Depends(get_project),
    db: Database = Depends(get_db),
):
    """Return the core-owned Act -> Chapter -> Scene manuscript hierarchy."""
    return serializers.story_structure_to_dto(db, project.id)
