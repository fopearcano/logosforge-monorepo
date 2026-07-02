"""Bridge to the safe connector action layer.

All API-driven actions go through :func:`logosforge.connector_executor.execute_action`
so input validation and the registered-action allow-list always apply — the API
never mutates the DB directly.

Read actions are always permitted (they only read).  Write actions respect the
desktop connector settings (``connector_enabled`` / ``connector_allow_writes``)
so enabling remote writes stays an explicit, user-controlled decision.
"""

from __future__ import annotations

from typing import Any

from logosforge.db import Database


def run_action(db: Database, project_id: int, action: str, args: dict[str, Any]) -> dict:
    # Ensure the action registry is populated.
    import logosforge.connector_actions  # noqa: F401
    from logosforge.connector_executor import execute_action
    from logosforge.connector_registry import get_action

    defn = get_action(action)
    is_read = defn is not None and getattr(defn, "category", "") == "read"
    return execute_action(
        db, project_id, {"action": action, "args": args or {}},
        enforce_settings=not is_read,
    )
