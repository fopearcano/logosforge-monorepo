"""Project-level event bus — one place every write announces itself.

Qt's signal/slot system but project-scoped: any module that mutates
project data should emit through `get_event_bus()` so the host (today
MainWindow) can refresh the active view without each write path
needing to know about the UI.

Signals are intentionally narrow — `project_data_changed` is the
catch-all that triggers a full refresh; the typed signals
(`scene_changed`, `psyke_changed`, etc.) exist for future targeted
refresh, but the host is free to ignore them and just listen on
`project_data_changed`.

The bus is a process-global singleton; tests can call
`get_event_bus().disconnect_all_listeners()` to reset between runs.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal


class ProjectEventBus(QObject):
    """Central pubsub for project-data mutations."""

    # Lifecycle — the active project changed. Carries the new project_id
    # so views can re-point and recompute against the right project.
    project_loaded = Signal(int)           # project_id (load / switch / restore)
    project_created = Signal(int)          # project_id (brand-new project)

    # Catch-all — any write fires this. Hosts that want a single
    # subscription should connect here.
    project_data_changed = Signal()

    # Typed signals — fired in addition to project_data_changed for
    # listeners that want to skip work when an unrelated entity changed.
    scene_changed = Signal(int)            # scene_id
    scenes_changed = Signal()              # scene list (added / deleted)
    outline_changed = Signal()
    psyke_changed = Signal(int)            # entry_id
    psyke_list_changed = Signal()
    notes_changed = Signal()
    plot_changed = Signal()
    assistant_action_completed = Signal(str)  # action name


_INSTANCE: ProjectEventBus | None = None


def get_event_bus() -> ProjectEventBus:
    """Return the process-global event bus, creating it on first use."""
    global _INSTANCE
    if _INSTANCE is None:
        _INSTANCE = ProjectEventBus()
    return _INSTANCE


# -- Convenience emitters ----------------------------------------------------
# Centralizing the "which signals does each action raise?" decision here so
# every write site doesn't have to spell it out.

_WRITE_ACTION_SIGNALS: dict[str, tuple[str, ...]] = {
    "create_scene": ("scenes_changed",),
    "update_scene_title": ("scenes_changed",),
    "update_scene_content": ("scenes_changed",),
    "create_psyke_entry": ("psyke_list_changed",),
    "update_psyke_entry": ("psyke_list_changed",),
    "create_note": ("notes_changed",),
    "update_note": ("notes_changed",),
    "create_plotline": ("plot_changed",),
    "update_outline": ("outline_changed",),
}


def emit_action_completed(action_name: str) -> None:
    """Emit the appropriate signals for a successful write action."""
    bus = get_event_bus()
    for signal_name in _WRITE_ACTION_SIGNALS.get(action_name, ()):
        signal = getattr(bus, signal_name, None)
        if signal is not None:
            signal.emit()
    bus.assistant_action_completed.emit(action_name)
    bus.project_data_changed.emit()


def emit_scene_changed(scene_id: int) -> None:
    bus = get_event_bus()
    bus.scene_changed.emit(scene_id)
    bus.project_data_changed.emit()


def emit_psyke_changed(entry_id: int) -> None:
    bus = get_event_bus()
    bus.psyke_changed.emit(entry_id)
    bus.project_data_changed.emit()


def emit_project_data_changed() -> None:
    get_event_bus().project_data_changed.emit()


def emit_project_loaded(project_id: int) -> None:
    """Announce that *project_id* is now the active project."""
    get_event_bus().project_loaded.emit(project_id)


def emit_project_created(project_id: int) -> None:
    """Announce a brand-new project (also fires project_loaded)."""
    bus = get_event_bus()
    bus.project_created.emit(project_id)
    bus.project_loaded.emit(project_id)


# -- Conceptual → real event mapping (documentation + compatibility) ---------
#
# Earlier specs referred to granular signals (manuscript_changed,
# timeline_changed, graph_changed, strategy_changed, health_report_changed,
# assistant_settings_changed) that this codebase does NOT define. The real model
# is intentionally coarser: most writes raise ``project_data_changed`` (the
# catch-all) plus a specific signal where one exists (scene_changed / scenes_
# changed / outline_changed / psyke_changed / psyke_list_changed / notes_changed
# / plot_changed). Strategy/Health are derived state, not events — they recompute
# from project_data_changed.
#
# This map documents the equivalence and lets callers raise a conceptual event
# without inventing fake signals. (Timeline/Plot/Graph are scene-derived, so a
# scene/data change already refreshes them.)
CONCEPTUAL_EVENT_MAP: dict[str, tuple[str, ...]] = {
    "manuscript_changed": ("scene_changed", "project_data_changed"),
    "timeline_changed": ("project_data_changed",),
    "graph_changed": ("project_data_changed",),
    "strategy_changed": ("project_data_changed",),
    "health_report_changed": ("project_data_changed",),
    "assistant_settings_changed": ("project_data_changed",),
}


def emit_conceptual(event_name: str, scene_id: int | None = None) -> None:
    """Emit the real signal(s) a conceptual event maps to.

    Unknown names fall back to ``project_data_changed`` so a caller can use a
    descriptive name without the bus needing a dedicated signal.
    """
    bus = get_event_bus()
    real = CONCEPTUAL_EVENT_MAP.get(event_name, ("project_data_changed",))
    for sig_name in real:
        sig = getattr(bus, sig_name, None)
        if sig is None:
            continue
        try:
            if sig_name == "scene_changed" and scene_id is not None:
                sig.emit(scene_id)
            else:
                sig.emit()
        except TypeError:
            pass
