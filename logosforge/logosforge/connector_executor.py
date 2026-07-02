"""CONNECTOR Executor — validates and executes action requests.

Receives structured action dicts from local AI, validates inputs,
dispatches to registered handlers, and returns structured results.
Never crashes — always returns a response dict.
"""

from __future__ import annotations

from typing import Any

from logosforge.db import Database

import logosforge.connector_actions  # noqa: F401 — registers actions
from logosforge.connector_registry import get_action, ActionParam


def execute_action(
    db: Database,
    project_id: int,
    request: dict[str, Any],
    *,
    enforce_settings: bool = True,
) -> dict[str, Any]:
    """Execute a CONNECTOR action request.

    Args:
        db: Database instance
        project_id: Active project id
        request: Dict with "action" key and optional "args" dict
        enforce_settings: When True (default), honor user settings for
            enabled state, write-access, and disabled-actions. Tests
            can pass False to exercise handlers directly.

    Returns:
        {"ok": True, "result": ...} on success
        {"ok": False, "error": "..."} on failure
    """
    action_name = request.get("action")
    if not action_name or not isinstance(action_name, str):
        return _error("Missing or invalid 'action' field.")

    action_def = get_action(action_name)
    if action_def is None:
        return _error(f"Unknown action: '{action_name}'.")

    if action_def.handler is None:
        return _error(f"Action '{action_name}' has no handler.")

    if enforce_settings:
        from logosforge.settings import get_manager as get_settings
        mgr = get_settings()
        if not mgr.get("connector_enabled"):
            return _error("Connector is disabled in settings.")
        disabled = mgr.get("connector_disabled_actions") or []
        if action_name in disabled:
            return _error(f"Action '{action_name}' is disabled in settings.")
        if action_def.category == "write" and not mgr.get("connector_allow_writes"):
            return _error(
                f"Action '{action_name}' is a write action; "
                "enable 'Allow write actions' in Connector settings."
            )

    raw_args = request.get("args", {})
    if not isinstance(raw_args, dict):
        return _error("'args' must be a dict.")

    validated, err = _validate_args(action_def.params, raw_args)
    if err:
        return _error(err)

    try:
        result = action_def.handler(db, project_id, **validated)
    except Exception as e:
        return _error(f"Execution failed: {e}")

    if isinstance(result, dict) and "error" in result:
        return _error(result["error"])

    # Announce the write through the central event bus so the active
    # UI can refresh without each caller having to wire its own
    # callback. Read actions stay silent.
    if action_def.category == "write":
        from logosforge.project_events import emit_action_completed
        emit_action_completed(action_name)

    return {"ok": True, "action": action_name, "result": result}


def _validate_args(
    params: list[ActionParam], raw: dict[str, Any],
) -> tuple[dict[str, Any], str | None]:
    """Validate and coerce args against param schema."""
    validated: dict[str, Any] = {}

    for param in params:
        if param.name in raw:
            value = raw[param.name]
            coerced, err = _coerce(param.name, value, param.param_type)
            if err:
                return {}, err
            validated[param.name] = coerced
        elif param.required:
            return {}, f"Missing required parameter: '{param.name}'."
        else:
            validated[param.name] = param.default

    return validated, None


def _coerce(name: str, value: Any, expected_type: str) -> tuple[Any, str | None]:
    """Coerce a value to the expected type."""
    if expected_type == "int":
        if isinstance(value, int):
            return value, None
        if isinstance(value, str) and value.isdigit():
            return int(value), None
        return None, f"Parameter '{name}' must be an integer."
    elif expected_type == "str":
        if isinstance(value, str):
            return value, None
        return str(value), None
    elif expected_type == "bool":
        if isinstance(value, bool):
            return value, None
        if isinstance(value, str):
            return value.lower() in ("true", "1", "yes"), None
        return bool(value), None
    return value, None


def _error(message: str) -> dict[str, Any]:
    return {"ok": False, "error": message}
