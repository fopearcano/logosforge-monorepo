"""Outline (hierarchical) endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from logosforge.api import schemas, serializers
from logosforge.api.deps import get_broker, get_db, get_project
from logosforge.api.errors import not_found
from logosforge.api.events import ApiEventBroker
from logosforge.db import Database

router = APIRouter(tags=["outline"])


@router.get(
    "/projects/{project_id}/outline",
    response_model=list[schemas.OutlineNodeDTO],
)
def get_outline(project=Depends(get_project), db: Database = Depends(get_db)):
    return serializers.outline_tree(db, project.id)


@router.post(
    "/projects/{project_id}/outline/nodes",
    response_model=schemas.OutlineNodeDTO, status_code=201,
)
def create_outline_node(
    body: schemas.OutlineNodeCreateDTO,
    project=Depends(get_project),
    db: Database = Depends(get_db),
    broker: ApiEventBroker = Depends(get_broker),
):
    node = db.create_outline_node(
        project.id,
        title=body.title,
        description=body.description,
        parent_id=body.parent_id,
        sort_order=body.sort_order,
    )
    broker.publish("outline_changed", project_id=project.id)
    return serializers.outline_node_to_dto(node)


@router.patch(
    "/projects/{project_id}/outline/nodes/{node_id}",
    response_model=schemas.OutlineNodeDTO,
)
def update_outline_node(
    node_id: int,
    body: schemas.OutlineNodeUpdateDTO,
    project=Depends(get_project),
    db: Database = Depends(get_db),
    broker: ApiEventBroker = Depends(get_broker),
):
    node = db.get_outline_node_by_id(node_id)
    if node is None or node.project_id != project.id:
        raise not_found(f"Outline node {node_id} not found")
    db.update_outline_node(
        node_id,
        title=body.title,
        description=body.description,
        sort_order=body.sort_order,
    )
    broker.publish("outline_changed", project_id=project.id)
    return serializers.outline_node_to_dto(db.get_outline_node_by_id(node_id))


@router.delete("/projects/{project_id}/outline/nodes/{node_id}")
def delete_outline_node(
    node_id: int,
    project=Depends(get_project),
    db: Database = Depends(get_db),
    broker: ApiEventBroker = Depends(get_broker),
):
    node = db.get_outline_node_by_id(node_id)
    if node is None or node.project_id != project.id:
        raise not_found(f"Outline node {node_id} not found")
    db.delete_outline_node(node_id)
    broker.publish("outline_changed", project_id=project.id)
    return {"ok": True, "deleted": node_id}
