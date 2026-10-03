"""Plot endpoints.

Plot is scene-derived: a "plot block" is the set of scenes sharing a plotline,
exactly as the desktop Multi-Plot view presents them.  There is no separate
plot table, so block ids are plotline names.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from logosforge.api import schemas, serializers
from logosforge.api.deps import get_broker, get_db, get_project
from logosforge.api.errors import not_found
from logosforge.api.events import ApiEventBroker
from logosforge.db import Database

router = APIRouter(tags=["plot"])


@router.get(
    "/projects/{project_id}/plot",
    response_model=list[schemas.PlotBlockDTO],
)
def get_plot(project=Depends(get_project), db: Database = Depends(get_db)):
    return serializers.plot_blocks(db, project.id)


@router.patch(
    "/projects/{project_id}/plot/blocks/{block_id}",
    response_model=schemas.PlotBlockDTO,
)
def update_plot_block(
    block_id: str,
    body: schemas.PlotBlockUpdateDTO,
    project=Depends(get_project),
    db: Database = Depends(get_db),
    broker: ApiEventBroker = Depends(get_broker),
):
    result = db.update_plot_block(
        project.id,
        block_id,
        plotline=body.plotline,
        color_label=body.color_label,
    )
    if result is None:
        raise not_found(f"Plot block '{block_id}' not found")

    for scene_id in result.changed_scene_ids:
        broker.publish(
            "scene_changed", project_id=project.id, scene_id=scene_id,
        )
    broker.publish("plot_changed", project_id=project.id)
    if result.timeline_changed:
        broker.publish("timeline_changed", project_id=project.id)

    blocks = serializers.plot_blocks(db, project.id)
    for block in blocks:
        if block.id == result.new_name:
            return block
    # If the block became empty after a rename collision, return a stub.
    return schemas.PlotBlockDTO(
        id=result.new_name, plotline=result.new_name, scenes=[],
    )
