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
    # Governance gate (the same flags the Qt Preferences expose) — enforced here
    # so the settings are REAL controls, not decoration: the connector must be
    # enabled, write actions require allow-writes, and disabled actions are blocked.
    from logosforge.settings import get_manager

    s = get_manager()
    category = _action_category(body.action)
    if not s.get("connector_enabled"):
        return schemas.ConnectorResultDTO(
            ok=False, action=body.action, result=None,
            error="Connector is disabled. Enable it in AI Behaviour settings to let the AI run actions.",
        )
    disabled = s.get("connector_disabled_actions")
    if isinstance(disabled, list) and body.action in disabled:
        return schemas.ConnectorResultDTO(
            ok=False, action=body.action, result=None,
            error=f"Action '{body.action}' is disabled in AI Behaviour settings.",
        )
    if category == "write" and not s.get("connector_allow_writes"):
        return schemas.ConnectorResultDTO(
            ok=False, action=body.action, result=None,
            error="Write actions are turned off. Enable 'Allow write actions' in AI Behaviour settings.",
        )

    result = run_action(db, project.id, body.action, body.args)
    if result.get("ok") and category == "write":
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
