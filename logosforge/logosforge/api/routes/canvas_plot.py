"""Revisioned, project-owned Canvas Plot endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from logosforge.api import schemas, serializers
from logosforge.api.deps import get_broker, get_db, get_project
from logosforge.api.errors import bad_request, conflict, not_found
from logosforge.api.events import ApiEventBroker
from logosforge.db import (
    CanvasPlotCommandError,
    CanvasPlotFrameNotFound,
    CanvasPlotLinkNotFound,
    CanvasPlotNodeNotFound,
    CanvasPlotProjectNotFound,
    CanvasPlotRevisionConflict,
    CanvasPlotSceneNotFound,
    Database,
)

router = APIRouter(tags=["canvas-plot"])


@router.get(
    "/projects/{project_id}/canvas-plot",
    response_model=schemas.CanvasPlotSnapshotDTO,
)
def get_canvas_plot(project=Depends(get_project), db: Database = Depends(get_db)):
    snapshot = db.read_canvas_plot_snapshot(project.id)
    if snapshot is None:
        raise not_found(f"Project {project.id} not found")
    return serializers.canvas_plot_snapshot_to_dto(snapshot)


@router.post(
    "/projects/{project_id}/canvas-plot/commands",
    response_model=schemas.CanvasPlotCommandResultDTO,
)
def execute_canvas_plot_command(
    body: schemas.CanvasPlotCommandDTO,
    project=Depends(get_project),
    db: Database = Depends(get_db),
    broker: ApiEventBroker = Depends(get_broker),
):
    """Run one optimistic-concurrency guarded board command atomically."""
    command = body.root
    payload = command.model_dump(exclude_unset=True)
    kind = payload.pop("kind")
    try:
        result = db.execute_canvas_plot_command(
            project.id,
            kind=kind,
            **payload,
        )
    except CanvasPlotRevisionConflict as exc:
        raise conflict(
            "The Canvas Plot changed after it was loaded. Reload it and retry the command.",
            code="canvas_plot_conflict",
        ) from exc
    except CanvasPlotProjectNotFound as exc:
        raise not_found(f"Project {project.id} not found") from exc
    except CanvasPlotNodeNotFound as exc:
        missing = exc.args[0] if exc.args else payload.get("node_id")
        raise not_found(f"Canvas Plot node {missing} not found") from exc
    except CanvasPlotLinkNotFound as exc:
        missing = exc.args[0] if exc.args else payload.get("link_id")
        raise not_found(f"Canvas Plot link {missing} not found") from exc
    except CanvasPlotFrameNotFound as exc:
        missing = exc.args[0] if exc.args else payload.get("frame_id")
        raise not_found(f"Canvas Plot frame {missing} not found") from exc
    except CanvasPlotSceneNotFound as exc:
        missing = exc.args[0] if exc.args else payload.get("scene_id")
        raise not_found(f"Scene {missing} not found") from exc
    except CanvasPlotCommandError as exc:
        raise bad_request(str(exc)) from exc

    if result.changed:
        broker.publish(
            "canvas_plot_changed",
            project_id=project.id,
            affected_node_ids=list(result.affected_node_ids),
            affected_link_ids=list(result.affected_link_ids),
            affected_frame_ids=list(result.affected_frame_ids),
        )

    return schemas.CanvasPlotCommandResultDTO(
        canvas_plot=serializers.canvas_plot_snapshot_to_dto(result.snapshot),
        changed=result.changed,
        affected_node_ids=list(result.affected_node_ids),
        affected_link_ids=list(result.affected_link_ids),
        affected_frame_ids=list(result.affected_frame_ids),
        created_node_id=result.created_node_id,
        created_link_id=result.created_link_id,
        created_frame_id=result.created_frame_id,
    )
