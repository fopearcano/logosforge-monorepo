"""Suppression for proactive suggestions: dismiss / snooze / hide-type.

Dismissed ids and hidden types persist in *project settings*
(``logos_suppressed``) so they survive restarts; snoozes are time-boxed. When no
project settings are available the store still works in-memory for the session.
"""

from __future__ import annotations

import time

_SETTINGS_KEY = "logos_suppressed"


class SuppressionStore:
    """Holds dismissed ids, snoozed ids (until ts), and hidden types.

    Backed by project settings via ``db.get_project_settings`` /
    ``save_project_settings`` when available; otherwise session-only.
    """

    def __init__(self, db=None, project_id: int | None = None) -> None:
        self._db = db
        self._project_id = project_id
        self._dismissed: set[str] = set()
        self._snoozed: dict[str, float] = {}
        self._hidden_types: set[str] = set()
        self._load()

    # -- Persistence ---------------------------------------------------------

    def _load(self) -> None:
        data = self._read_settings()
        self._dismissed = set(data.get("dismissed", []))
        self._snoozed = {k: float(v) for k, v in (data.get("snoozed", {}) or {}).items()}
        self._hidden_types = set(data.get("hidden_types", []))

    def _read_settings(self) -> dict:
        if self._db is None or self._project_id is None:
            return {}
        try:
            settings = self._db.get_project_settings(self._project_id)
            raw = settings.get(_SETTINGS_KEY, {})
            return raw if isinstance(raw, dict) else {}
        except Exception:
            return {}

    def _persist(self) -> None:
        if self._db is None or self._project_id is None:
            return
        try:
            settings = self._db.get_project_settings(self._project_id)
            settings[_SETTINGS_KEY] = {
                "dismissed": sorted(self._dismissed),
                "snoozed": {k: v for k, v in self._snoozed.items()},
                "hidden_types": sorted(self._hidden_types),
            }
            self._db.save_project_settings(self._project_id, settings)
        except Exception:
            pass

    # -- Mutators ------------------------------------------------------------

    def dismiss(self, suggestion_id: str) -> None:
        self._dismissed.add(suggestion_id)
        self._persist()

    def snooze(self, suggestion_id: str, *, seconds: float = 86400.0) -> None:
        self._snoozed[suggestion_id] = time.time() + seconds
        self._persist()

    def hide_type(self, suggestion_type: str) -> None:
        self._hidden_types.add(suggestion_type)
        self._persist()

    def reset(self) -> None:
        self._dismissed.clear()
        self._snoozed.clear()
        self._hidden_types.clear()
        self._persist()

    # -- Queries -------------------------------------------------------------

    def is_suppressed(self, suggestion) -> bool:
        if suggestion.type in self._hidden_types:
            return True
        if suggestion.id in self._dismissed:
            return True
        until = self._snoozed.get(suggestion.id, 0.0)
        return until > time.time()

    def hidden_types(self) -> set[str]:
        return set(self._hidden_types)
