"""Step 6 — refresh propagation: data changes appear without a section switch."""

import pytest

from logosforge.db import Database
from logosforge.ui.main_window import MainWindow


@pytest.fixture(autouse=True)
def reset_settings(monkeypatch, tmp_path):
    import logosforge.settings as settings
    settings._instance = None
    monkeypatch.setattr(settings, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(settings, "SETTINGS_FILE", tmp_path / "settings.json")
    import logosforge.gomckee_bridge as gb
    monkeypatch.setattr(gb, "is_gomckee_enabled", lambda: False, raising=False)
    yield
    settings._instance = None


def _win():
    db = Database()
    pid = db.create_project("P", narrative_engine="novel").id
    db.create_scene(pid, "S1", content="Alice.", act="Act I", chapter="Ch1")
    return db, pid, MainWindow(db, pid)


# ==========================================================================
# Previously-stale views now expose refresh() and get refreshed on data change
# ==========================================================================


@pytest.mark.parametrize("section", ["Projects", "Acts", "Beats", "Tags"])
def test_section_view_refreshes_on_data_change(section):
    db, pid, win = _win()
    win.sidebar_buttons[section].click()
    view = win.content_area
    assert hasattr(view, "refresh")
    calls = []
    view.refresh = lambda *a, **k: calls.append(1)  # spy
    win._on_data_changed()
    assert calls, f"{section} view was not refreshed on data change"


def test_core_section_views_refresh_on_data_change():
    db, pid, win = _win()
    for section in ("Outline", "Scenes", "Manuscript", "Plot", "Timeline",
                    "PSYKE", "Notes", "Graph", "Dashboard"):
        win.sidebar_buttons[section].click()
        view = win.content_area
        assert hasattr(view, "refresh"), f"{section} has no refresh()"
        calls = []
        view.refresh = lambda *a, **k: calls.append(1)
        win._on_data_changed()
        assert calls, f"{section} not refreshed"


# ==========================================================================
# Outline Apply persists data and notifies the UI
# ==========================================================================


def test_outline_apply_persists_scenes():
    from logosforge.outline_actions import OutlineOp, apply_outline_as_scenes
    db, pid, win = _win()
    before = len(db.get_all_scenes(pid))
    ops = [OutlineOp(title="New Act", kind="act", children=[
        OutlineOp(title="New Scene", kind="scene", description="a beat")])]
    created = apply_outline_as_scenes(db, pid, ops)
    assert created
    assert len(db.get_all_scenes(pid)) == before + len(created)


def test_assistant_apply_outline_notifies_and_persists():
    db, pid, win = _win()
    from logosforge.outline_actions import OutlineOp
    panel = win._assistant_panel
    spy = []
    panel._on_data_changed = lambda: spy.append(1)
    before = len(db.get_all_scenes(pid))
    created = panel.apply_outline_ops([OutlineOp(title="Sc", kind="scene")])
    assert created
    assert len(db.get_all_scenes(pid)) == before + len(created)
    assert spy, "apply_outline_ops did not notify on_data_changed"


# ==========================================================================
# Logos mutation path notifies
# ==========================================================================


def test_logos_apply_refreshes_active_view(monkeypatch):
    db, pid, win = _win()
    win.sidebar_buttons["Scenes"].click()
    refreshed = []
    win.content_area.refresh = lambda *a, **k: refreshed.append(1)

    # Mock the confirm dialog + the actual write so no UI dialog / LLM runs.
    from logosforge.ui.logos.logos_apply_preview import LogosApplyPreview
    from logosforge.logos import operations as logos_ops
    monkeypatch.setattr(LogosApplyPreview, "get_operation",
                        staticmethod(lambda *a, **k: {"target": "scene"}))
    monkeypatch.setattr(logos_ops, "apply_logos_operation",
                        lambda *a, **k: {"ok": True, "events": ["scenes_changed"],
                                         "scene_id": None})
    win._logos_request_apply(result=object(), context=object())
    assert refreshed, "Logos apply did not refresh the active view"


# ==========================================================================
# PSYKE / Notes edits propagate
# ==========================================================================


def test_psyke_view_refreshes_after_entry_added():
    db, pid, win = _win()
    win.sidebar_buttons["PSYKE"].click()
    view = win.content_area
    calls = []
    view.refresh = lambda *a, **k: calls.append(1)
    db.create_psyke_entry(pid, "Bob", "character")
    win._on_data_changed()
    assert calls


def test_notes_view_refreshes_on_data_change():
    db, pid, win = _win()
    win.sidebar_buttons["Notes"].click()
    view = win.content_area
    calls = []
    view.refresh = lambda *a, **k: calls.append(1)
    win._on_data_changed()
    assert calls


# ==========================================================================
# No recursive loops on project_data_changed
# ==========================================================================


def test_project_data_changed_does_not_recurse():
    from logosforge.project_events import get_event_bus
    db, pid, win = _win()
    win.sidebar_buttons["Dashboard"].click()
    bus = get_event_bus()
    count = []
    bus.project_data_changed.connect(lambda: count.append(1))
    # A single emit must trigger exactly one fan-out (active-view refresh must
    # not re-emit project_data_changed and cause a cascade).
    bus.project_data_changed.emit()
    from PySide6.QtWidgets import QApplication
    QApplication.instance().processEvents()
    assert len(count) == 1


def test_on_data_changed_runs_once_per_emit():
    from logosforge.project_events import get_event_bus
    db, pid, win = _win()
    calls = []
    orig = win._on_data_changed

    def counting():
        calls.append(1)
        orig()

    # Reconnect the bus to our counting wrapper.
    bus = get_event_bus()
    bus.project_data_changed.connect(counting)
    bus.project_data_changed.emit()
    from PySide6.QtWidgets import QApplication
    QApplication.instance().processEvents()
    # Exactly one wrapper invocation; the refresh inside must not re-fire it.
    assert len(calls) == 1
