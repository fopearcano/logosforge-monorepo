"""Project lifecycle hooks — clear all project-scoped state on switch.

Any module that holds project-scoped caches registers a clear callback
via `register_project_clear_hook(fn)`. When the user opens or creates a
project, `MainWindow._switch_project()` calls `clear_project_caches(old_id)`
which fans the callbacks out.

This keeps `_switch_project()` from importing a growing list of internal
caches, and lets future caches opt in by registering at import time.
"""

from __future__ import annotations

from collections.abc import Callable


# Registered hooks. Each hook receives the project_id being LEFT.
_CLEAR_HOOKS: list[Callable[[int | None], None]] = []


def register_project_clear_hook(fn: Callable[[int | None], None]) -> None:
    """Register *fn* to be called when the active project changes.

    The hook receives the project_id being left (may be None on first
    load). Hooks must be idempotent and tolerant of None.
    """
    if fn not in _CLEAR_HOOKS:
        _CLEAR_HOOKS.append(fn)


def clear_project_caches(old_project_id: int | None) -> None:
    """Run every registered clear hook. Failures are swallowed per-hook so
    one broken module can't strand the switch."""
    for hook in list(_CLEAR_HOOKS):
        try:
            hook(old_project_id)
        except Exception:
            pass


def _clear_quantum_state(old_id: int | None) -> None:
    if old_id is None:
        return
    from logosforge.quantum_outliner.state import reset_state
    reset_state(old_id)


def _clear_paragraph_energy(_old_id: int | None) -> None:
    from logosforge.paragraph_energy import clear_cache
    clear_cache()


def _clear_lookahead(_old_id: int | None) -> None:
    from logosforge.quantum_outliner.lookahead_cache import invalidate_lookahead
    invalidate_lookahead("project_switch")


# Register the built-in hooks at import time.
register_project_clear_hook(_clear_quantum_state)
register_project_clear_hook(_clear_paragraph_energy)
register_project_clear_hook(_clear_lookahead)
