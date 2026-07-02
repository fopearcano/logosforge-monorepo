"""PSYKE must be strictly project-bound: create / open / switch / back must
never leak entries, relations, progressions, details, selection, console
results, scene-editor highlight terms, or Assistant PSYKE context across
projects.
"""

from __future__ import annotations

import warnings

import pytest
from PySide6.QtWidgets import QApplication, QListWidget

warnings.filterwarnings("ignore")

from logosforge.db import Database
from logosforge.context_builder import gather_psyke_context
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


def _list_names(view):
    names = []
    for lw in view.findChildren(QListWidget):
        for i in range(lw.count()):
            names.append(lw.item(i).text())
    return names


# ==========================================================================
# DB layer: every PSYKE read is project-bound (incl. is_global rows)
# ==========================================================================


def test_get_all_psyke_entries_is_strictly_project_scoped():
    db = Database()
    a = db.create_project("A").id
    b = db.create_project("B").id
    db.create_psyke_entry(a, "A-char", "character")
    # A global entry in A must NOT leak into B (project-scoped global).
    db.create_psyke_entry(a, "A-global", "character", is_global=True)
    db.create_psyke_entry(b, "B-char", "character")
    assert {e.name for e in db.get_all_psyke_entries(a)} == {"A-char", "A-global"}
    assert {e.name for e in db.get_all_psyke_entries(b)} == {"B-char"}


def test_relations_and_progressions_do_not_cross_projects():
    db = Database()
    a = db.create_project("A").id
    b = db.create_project("B").id
    a1 = db.create_psyke_entry(a, "A-hero", "character").id
    a2 = db.create_psyke_entry(a, "A-foe", "character").id
    db.add_psyke_relation(a1, a2, "rival")
    db.create_psyke_progression(a1, "A-arc: the hero grows")
    b1 = db.create_psyke_entry(b, "B-hero", "character").id
    # B's entry has no relations/progressions from A.
    assert db.get_related_psyke_entries(b1) == []
    assert db.get_psyke_progressions(b1) == []
    # A's relations/progressions are intact and A-scoped.
    assert {e.name for e in db.get_related_psyke_entries(a1)} == {"A-foe"}
    assert [p.text for p in db.get_psyke_progressions(a1)] == ["A-arc: the hero grows"]


# ==========================================================================
# PsykeView: rebuilt clean for the active project on switch (no manual nav)
# ==========================================================================


def test_psyke_view_shows_only_active_project_across_switch():
    db = Database()
    a = db.create_project("A").id
    db.create_psyke_entry(a, "CHARACTER_A_UNIQUE", "character")
    db.create_psyke_entry(a, "PLACE_A_UNIQUE", "location")
    b = db.create_project("B").id
    win = MainWindow(db, a)
    win.sidebar_buttons["PSYKE"].click()
    assert any("CHARACTER_A_UNIQUE" in n for n in _list_names(win.content_area))

    # Switch to B while PSYKE is the active section — view rebuilds empty,
    # with no manual section switch.
    win._switch_project(b)
    from logosforge.ui.psyke_view import PsykeView
    assert isinstance(win.content_area, PsykeView)
    assert win.content_area._project_id == b
    assert win.content_area._selected_id is None
    assert _list_names(win.content_area) == []

    # Add B entry, then round-trip A -> B and confirm strict isolation.
    db.create_psyke_entry(b, "CHARACTER_B_UNIQUE", "character")
    win._switch_project(a)
    win.sidebar_buttons["PSYKE"].click()
    a_names = " ".join(_list_names(win.content_area))
    assert "CHARACTER_A_UNIQUE" in a_names and "CHARACTER_B_UNIQUE" not in a_names

    win._switch_project(b)
    win.sidebar_buttons["PSYKE"].click()
    b_names = " ".join(_list_names(win.content_area))
    assert "CHARACTER_B_UNIQUE" in b_names and "CHARACTER_A_UNIQUE" not in b_names


def test_psyke_selection_cleared_on_switch():
    db = Database()
    a = db.create_project("A").id
    eid = db.create_psyke_entry(a, "A-char", "character").id
    b = db.create_project("B").id
    win = MainWindow(db, a)
    win.sidebar_buttons["PSYKE"].click()
    win.content_area.select_entry(eid)
    assert win.content_area._selected_id == eid
    win._switch_project(b)
    # Freshly rebuilt PSYKE view has no carried-over selection.
    assert win.content_area._selected_id is None


def test_psyke_details_json_does_not_leak():
    db = Database()
    a = db.create_project("A").id
    db.create_psyke_entry(a, "A-char", "character",
                          details={"backstory": "A_SECRET_DETAIL"})
    b = db.create_project("B").id
    db.create_psyke_entry(b, "B-char", "character")
    # B's entries carry none of A's details.
    for e in db.get_all_psyke_entries(b):
        d = db.get_psyke_entry_details(e.id)
        assert "A_SECRET_DETAIL" not in str(d)


# ==========================================================================
# Always-on PSYKE console: cleared + eagerly rebuilt on switch
# ==========================================================================


def test_psyke_console_resets_on_switch():
    db = Database()
    a = db.create_project("A").id
    db.create_psyke_entry(a, "CHARACTER_A_UNIQUE", "character")
    b = db.create_project("B").id
    win = MainWindow(db, a)
    c = win._psyke_console
    c.rebuild_index()
    c._input.setText("CHAR")
    assert {e.name for e in c._psyke_entries_cache} == {"CHARACTER_A_UNIQUE"}

    win._switch_project(b)
    assert c._project_id == b
    assert c._input.text() == ""               # in-progress query dropped
    assert c._psyke_entries_cache == []         # eagerly rebuilt for B (empty)
    assert c._search_index._project_id == b


# ==========================================================================
# Assistant PSYKE context follows the active project
# ==========================================================================


def test_assistant_psyke_context_follows_active_project():
    db = Database()
    a = db.create_project("A").id
    db.create_psyke_entry(a, "CHARACTER_A_UNIQUE", "character",
                          notes="the weary hero")
    b = db.create_project("B").id
    win = MainWindow(db, a)
    assert "CHARACTER_A_UNIQUE" in gather_psyke_context(db, a)
    win._switch_project(b)
    ctx_b = gather_psyke_context(db, win._project_id)
    assert "CHARACTER_A_UNIQUE" not in ctx_b


# ==========================================================================
# Scene-editor PSYKE highlighter rebuilds its term map per project
# ==========================================================================


def test_manuscript_psyke_highlighter_term_map_is_project_bound():
    # Scene-editor highlighter lives in the scene-based manuscript (non-Novel).
    db = Database()
    a = db.create_project("A", narrative_engine="screenplay",
                          default_writing_format="screenplay").id
    db.create_scene(a, "A-scene", content="text")
    db.create_psyke_entry(a, "Aragorn", "character")
    b = db.create_project("B", narrative_engine="screenplay",
                          default_writing_format="screenplay").id
    db.create_scene(b, "B-scene", content="text")
    win = MainWindow(db, a)
    win.sidebar_buttons["Manuscript"].click()
    terms_a = dict(win.content_area._psyke_term_map)
    assert any("aragorn" in t.lower() for t in terms_a)
    # Switch to B (no PSYKE) — active editor rebuilds with an empty term map.
    win._switch_project(b)
    from logosforge.ui.writing_core_view import WritingCoreView
    assert isinstance(win.content_area, WritingCoreView)
    assert not any("aragorn" in t.lower() for t in win.content_area._psyke_term_map)


# ==========================================================================
# New project is clean; switch announces once; no duplicate subscriptions
# ==========================================================================


def test_new_project_psyke_is_empty():
    db = Database()
    a = db.create_project("A").id
    db.create_psyke_entry(a, "OldChar", "character")
    win = MainWindow(db, a)
    import logosforge.ui.new_project_dialog as npd

    class _FakeDialog:
        def __init__(self, *a, **k): ...
        def exec(self): return True
        def get_title(self): return "Fresh"
        def get_engine(self): return "novel"
        def get_format(self): return "novel"

    mp = pytest.MonkeyPatch()
    mp.setattr(npd, "NewProjectDialog", _FakeDialog, raising=False)
    win._on_new_project()
    mp.undo()
    new_id = win._project_id
    assert db.get_all_psyke_entries(new_id) == []
    # Console rebound + empty for the new project.
    assert win._psyke_console._project_id == new_id
    assert win._psyke_console._psyke_entries_cache == []


def test_switch_does_not_duplicate_psyke_console_subscriptions():
    # _on_data_changed marks the console index dirty exactly once per emit even
    # after repeated switches (no piled-up duplicate subscriptions).
    from logosforge.project_events import get_event_bus
    db = Database()
    a = db.create_project("A").id
    b = db.create_project("B").id
    win = MainWindow(db, a)
    win._switch_project(b)
    win._switch_project(a)
    calls = []
    orig = win._psyke_console.mark_index_dirty
    win._psyke_console.mark_index_dirty = lambda: (calls.append(1), orig())[1]
    get_event_bus().project_data_changed.emit()
    QApplication.instance().processEvents()
    assert len(calls) == 1
