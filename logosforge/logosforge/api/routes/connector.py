"""Connector endpoints — list available actions and execute them safely."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from logosforge.api import schemas
from logosforge.api.actions import run_action
from logosforge.api.deps import get_broker, get_db, get_project
from logosforge.api.events import ApiEventBroker
from logosforge.db import Database

router = APIRouter(tags=["connector"])


@router.get(
    "/projects/{project_id}/connector/actions",
    response_model=list[schemas.ConnectorActionDTO],
)
def list_actions(project=Depends(get_project)):
    import logosforge.connector_actions  # noqa: F401  (populate registry)
    from logosforge.connector_registry import describe_all_actions

    out = []
    for action in describe_all_actions():
        params = [
            schemas.ConnectorActionParamDTO(
                name=p.get("name", ""),
                param_type=p.get("type", p.get("param_type", "str")),
                required=p.get("required", True),
                default=p.get("default"),
            )
            for p in action.get("params", [])
        ]
        out.append(
            schemas.ConnectorActionDTO(
                name=action.get("name", ""),
                description=action.get("description", ""),
                category=action.get("category", ""),
                params=params,
            )
        )
    return out


@router.post(
    "/projects/{project_id}/connector/execute",
    response_model=schemas.ConnectorResultDTO,
)
def execute(
    body: schemas.ConnectorExecuteDTO,
    project=Depends(get_project),
    db: Database = Depends(get_db),
    broker: ApiEventBroker = Depends(get_broker),
):
    result = run_action(db, project.id, body.action, body.args)
    if result.get("ok") and _action_category(body.action) == "write":
        broker.publish("project_data_changed", project_id=project.id)
    return schemas.ConnectorResultDTO(
        ok=bool(result.get("ok")),
        action=result.get("action", body.action),
        result=result.get("result"),
        error=result.get("error", ""),
    )


def _action_category(action: str) -> str:
    import logosforge.connector_actions  # noqa: F401
    from logosforge.connector_registry import get_action

    defn = get_action(action)
    return getattr(defn, "category", "") if defn else ""
