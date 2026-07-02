"""Quantum state persistence — bridge between in-memory state and DB."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from logosforge.quantum_outliner.state import (
    NarrativeState,
    _STATES,
    deserialize_state,
    get_state,
    serialize_state,
)

if TYPE_CHECKING:
    from logosforge.db import Database

logger = logging.getLogger(__name__)


def save_state(db: Database, project_id: int) -> None:
    """Persist current in-memory NarrativeState to DB."""
    state = _STATES.get(project_id)
    if state is None:
        return
    raw = serialize_state(state)
    db.save_quantum_state_json(project_id, raw)


def load_state(db: Database, project_id: int) -> NarrativeState:
    """Load NarrativeState from DB into memory. Returns the state."""
    raw = db.get_quantum_state_json(project_id)
    if raw:
        restored = deserialize_state(raw, project_id)
        if restored is not None:
            _STATES[project_id] = restored
            return restored
    return get_state(project_id)


def export_quantum_state(db: Database, project_id: int) -> dict | None:
    """Return quantum state as a dict for JSON project export."""
    raw = db.get_quantum_state_json(project_id)
    if not raw:
        state = _STATES.get(project_id)
        if state and state.wavefunctions:
            raw = serialize_state(state)
    if not raw:
        return None
    try:
        import json
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None


def import_quantum_state(db: Database, project_id: int, data: dict) -> None:
    """Restore quantum state from JSON project import data."""
    if not isinstance(data, dict):
        return
    import json
    raw = json.dumps(data)
    restored = deserialize_state(raw, project_id)
    if restored is not None:
        _STATES[project_id] = restored
        db.save_quantum_state_json(project_id, raw)
