"""Narrative dashboard route — derived, read-only analytics for a project.

Exposes the existing ``narrative_dashboard.compute_dashboard`` engine (tension
curve, character/theme presence, structure distribution) over the API. Pure
read: nothing is written to the database.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from logosforge import narrative_dashboard
from logosforge.api import schemas, serializers
from logosforge.api.deps import get_db, get_project
from logosforge.db import Database

router = APIRouter(tags=["dashboard"])


@router.get(
    "/projects/{project_id}/dashboard",
    response_model=schemas.NarrativeDashboardDTO,
)
def get_dashboard(project=Depends(get_project), db: Database = Depends(get_db)):
    """Tension curve, character/theme presence, and structure distribution."""
    data = narrative_dashboard.compute_dashboard(db, project.id)
    return serializers.dashboard_to_dto(data)
