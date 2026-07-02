"""Part 3 — Create New project flow is clean (no fullscreen/minimize glitch).

Exactly one project switch, one final navigation target (Dashboard), the
projects list refreshes, and no showNormal/showMinimized side effects occur.
(True fullscreen behavior is macOS-specific and not testable headlessly.)
"""

from __future__ import annotations

import warnings

import pytest
from PySide6.QtWidgets import QApplication

warnings.filterwarnings("ignore")

from logosforge.db import Database
from logosforge.ui.main_window import MainWindow


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    app = QApplication.instance() or QApplication([])
    yield app


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


class _FakeDialog:
    def __init__(self, *a, **k): ...
    def exec(self): return True
    def get_title(self): return "Fresh"
    def get_engine(self): return "novel"
    def get_format(self): return "novel"


def _patch_dialog(monkeypatch):
    import logosforge.ui.new_project_dialog as npd
    monkeypatch.setattr(npd, "NewProjectDialog", _FakeDialog, raising=False)


def test_create_new_one_switch_one_target_no_minimize(monkeypatch):
    db = Database()
    a = db.create_project("A", narrative_engine="novel").id
    win = MainWindow(db, a)
    _patch_dialog(monkeypatch)

    counters = {"switch": 0, "normal": 0, "minimized": 0, "refresh": 0}

    orig_switch = win._switch_project
    monkeypatch.setattr(
        win, "_switch_project",
        lambda nid, *a, **k: (counters.__setitem__("switch", counters["switch"] + 1),
                              orig_switch(nid, *a, **k))[1],
    )
    monkeypatch.setattr(
        win, "showNormal",
        lambda: counters.__setitem__("normal", counters["normal"] + 1),
    )
    monkeypatch.setattr(
        win, "showMinimized",
        lambda: counters.__setitem__("minimized", counters["minimized"] + 1),
    )
    orig_refresh = win._refresh_projects_view
    monkeypatch.setattr(
        win, "_refresh_projects_view",
        lambda *a, **k: (counters.__setitem__("refresh", counters["refresh"] + 1),
                         orig_refresh(*a, **k))[1],
    )

    win._on_new_project()

    assert counters["switch"] == 1            # exactly one project switch
    assert win._current_section == "Dashboard"  # one final navigation target
    assert counters["normal"] == 0            # never showNormal
    assert counters["minimized"] == 0         # never minimize
    assert counters["refresh"] == 1           # projects list refreshed once


def test_create_new_switches_to_fresh_empty_project(monkeypatch):
    db = Database()
    a = db.create_project("A", narrative_engine="novel").id
    db.create_scene(a, "Old", content="old")
    win = MainWindow(db, a)
    _patch_dialog(monkeypatch)
    win._on_new_project()
    new_id = win._project_id
    assert new_id != a
    assert db.get_all_scenes(new_id) == []     # clean new project


# ==========================================================================
# Fullscreen flashing/minimize fix: single lifecycle signal, no window mutation
# ==========================================================================


def test_create_new_emits_single_lifecycle_signal(monkeypatch):
    # The new-project flow must fire exactly ONE lifecycle signal so Dashboard /
    # Character Arc (which listen to both) recompute once, not twice (the flash).
    from logosforge.project_events import get_event_bus
    db = Database()
    a = db.create_project("A", narrative_engine="novel").id
    win = MainWindow(db, a)
    _patch_dialog(monkeypatch)

    counts = {"loaded": 0, "created": 0}
    bus = get_event_bus()
    bus.project_loaded.connect(lambda *_: counts.__setitem__("loaded", counts["loaded"] + 1))
    bus.project_created.connect(lambda *_: counts.__setitem__("created", counts["created"] + 1))

    win._on_new_project()

    assert counts["created"] == 1     # single "brand new" announcement
    assert counts["loaded"] == 0      # switch's project_loaded suppressed


def test_create_new_makes_no_window_state_calls(monkeypatch):
    db = Database()
    a = db.create_project("A", narrative_engine="novel").id
    win = MainWindow(db, a)
    _patch_dialog(monkeypatch)

    calls = {"fullscreen": 0, "normal": 0, "minimized": 0, "setstate": 0}
    monkeypatch.setattr(win, "showFullScreen",
                        lambda: calls.__setitem__("fullscreen", calls["fullscreen"] + 1))
    monkeypatch.setattr(win, "showNormal",
                        lambda: calls.__setitem__("normal", calls["normal"] + 1))
    monkeypatch.setattr(win, "showMinimized",
                        lambda: calls.__setitem__("minimized", calls["minimized"] + 1))
    monkeypatch.setattr(win, "setWindowState",
                        lambda *_a: calls.__setitem__("setstate", calls["setstate"] + 1))

    win._on_new_project()

    # The flow never mutates window state — so it cannot slide Spaces or minimise.
    assert calls == {"fullscreen": 0, "normal": 0, "minimized": 0, "setstate": 0}


def test_create_new_reentrancy_guard_blocks_duplicate(monkeypatch):
    db = Database()
    a = db.create_project("A", narrative_engine="novel").id
    win = MainWindow(db, a)

    opened = {"n": 0}

    class _CountingDialog(_FakeDialog):
        def __init__(self, *a, **k):
            opened["n"] += 1

    import logosforge.ui.new_project_dialog as npd
    monkeypatch.setattr(npd, "NewProjectDialog", _CountingDialog, raising=False)

    # Simulate a creation already in progress → a second invocation is a no-op.
    win._creating_project = True
    win._on_new_project()
    assert opened["n"] == 0            # no second dialog opened

    # Normal invocation opens exactly one dialog.
    win._creating_project = False
    win._on_new_project()
    assert opened["n"] == 1


def test_switch_announce_flag_controls_project_loaded():
    # Regression guard for the canonical switch: announce=True (default) emits
    # project_loaded; announce=False suppresses it.
    from logosforge.project_events import get_event_bus
    db = Database()
    a = db.create_project("A", narrative_engine="novel").id
    b = db.create_project("B", narrative_engine="novel").id
    win = MainWindow(db, a)
    bus = get_event_bus()
    seen = {"n": 0}
    bus.project_loaded.connect(lambda *_: seen.__setitem__("n", seen["n"] + 1))

    win._switch_project(b)                       # default announce=True
    assert seen["n"] == 1
    win._switch_project(a, announce=False)       # suppressed
    assert seen["n"] == 1
