"""Manuscript in-page summary/navigation rail (no separate Navigator panel).

The extra right-side "Navigator" panel was removed; the existing per-scene
"Add summary…" column is now the compact navigation/summary rail: it shows a
summary preview or placeholder, uses canonical order, and clicking an item jumps
to that scene's editor. It never writes Outline summaries into the body.
"""

from __future__ import annotations

import warnings

import pytest
from PySide6.QtWidgets import QApplication, QLabel, QWidget

warnings.filterwarnings("ignore")

from logosforge.db import Database
from logosforge import story_structure as ss
from logosforge.ui.main_window import MainWindow
from logosforge.ui.writing_core_view import (
    WritingCoreView,
    _SceneEditor,
    _SummaryRailLabel,
)


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


def _novel(db):
    return db.create_project("P", narrative_engine="novel").id


def _manuscript(db, pid):
    return WritingCoreView(db, pid, structured_list=True)


def _rail(view):
    return [w for w in view.findChildren(QLabel)
            if w.objectName() == "writingSceneSummaryMeta"]


def _ctx(view):
    return [w.text() for w in view.findChildren(QLabel)
            if w.objectName() == "writingSceneContext"]


# ==========================================================================
# 1-2  No separate external Navigator panel
# ==========================================================================


def test_no_external_navigator_panel():
    db = Database()
    pid = _novel(db)
    ss.create_scene(db, pid, act="Act I", chapter="Ch1", title="S", content="x")
    view = _manuscript(db, pid)
    assert view._navigator is None
    # No standalone navigator widget / header anywhere in the view.
    objs = {w.objectName() for w in view.findChildren(QWidget)}
    assert "manuscriptNavigator" not in objs
    assert "navigatorTree" not in objs
    assert not [w for w in view.findChildren(QLabel)
                if w.text() == "Navigator"]


def test_manuscript_via_mainwindow_has_no_navigator_panel(tmp_path):
    db = Database(str(tmp_path / "sp.db"))
    pid = _novel(db)
    ss.create_scene(db, pid, act="Act I", chapter="Ch1", title="S", content="x")
    win = MainWindow(db, pid)
    win.sidebar_buttons["Manuscript"].click()
    assert win.content_area._navigator is None
    objs = {w.objectName() for w in win.content_area.findChildren(QWidget)}
    assert "manuscriptNavigator" not in objs


# ==========================================================================
# 3-6  The in-page summary/nav rail
# ==========================================================================


def test_internal_rail_present_with_preview_and_placeholder():
    db = Database()
    pid = _novel(db)
    ss.create_scene(db, pid, act="Act I", chapter="Ch1", title="A",
                    summary="hero wakes", content="x")
    ss.create_scene(db, pid, act="Act I", chapter="Ch1", title="B")  # no summary
    rail = _rail(_manuscript(db, pid))
    texts = [w.text() for w in rail]
    assert "hero wakes" in texts            # preview when summary exists
    assert "Add summary…" in texts          # placeholder otherwise
    assert all(isinstance(w, _SummaryRailLabel) for w in rail)


def test_clicking_rail_item_jumps_to_scene():
    db = Database()
    pid = _novel(db)
    a = ss.create_scene(db, pid, act="Act I", chapter="Ch1", title="A",
                        content="x").id
    b = ss.create_scene(db, pid, act="Act I", chapter="Ch1", title="B",
                        content="y").id
    view = _manuscript(db, pid)
    rail = _rail(view)
    rail[1]._on_click()                      # second scene's rail item
    assert view._selected_scene_id == b


def test_rail_uses_canonical_order_and_numbering():
    db = Database()
    pid = _novel(db)
    ss.create_scene(db, pid, act="Act I", chapter="Ch1", title="A", content="x")
    ss.create_scene(db, pid, act="Act I", chapter="Ch1", title="B", content="y")
    ctx = _ctx(_manuscript(db, pid))
    assert ctx == ["SCENE 1.1.1", "SCENE 1.1.2"]   # canonical order + numbers


# ==========================================================================
# 7-9  Refresh on change / switch; body stays separate
# ==========================================================================


def test_rail_refreshes_after_structure_change():
    db = Database()
    pid = _novel(db)
    ss.create_scene(db, pid, act="Act I", chapter="Ch1", title="A",
                    summary="ALPHA", content="x")
    view = _manuscript(db, pid)
    # The newly added scene's summary appears after refresh. (Counting via
    # findChildren is unreliable headless — deleteLater'd labels linger — so we
    # assert by content + the canonical context order instead.)
    assert "BETA" not in [w.text() for w in _rail(view)]
    ss.create_scene(db, pid, act="Act I", chapter="Ch1", title="B",
                    summary="BETA", content="y")
    view.refresh()
    assert "BETA" in [w.text() for w in _rail(view)]
    assert _ctx(view)[-1] == "SCENE 1.1.2"     # two scenes, canonical order


def test_rail_refreshes_after_project_switch(tmp_path):
    db = Database(str(tmp_path / "sp.db"))
    a = _novel(db)
    ss.create_scene(db, a, act="Act A", chapter="Ch", title="S",
                    summary="A-SUMMARY", content="x")
    b = _novel(db)
    win = MainWindow(db, a)
    win.sidebar_buttons["Manuscript"].click()
    assert any("A-SUMMARY" in w.text() for w in _rail(win.content_area))
    win._switch_project(b)
    win.sidebar_buttons["Manuscript"].click()
    assert not any("A-SUMMARY" in w.text() for w in _rail(win.content_area))


def test_rail_does_not_write_summary_into_body():
    db = Database()
    pid = _novel(db)
    sid = ss.create_scene(db, pid, act="Act I", chapter="Ch1", title="S",
                          summary="PLAN_ONLY", content="REAL_BODY").id
    view = _manuscript(db, pid)
    view._rail = _rail(view)
    bodies = " ".join(e.toPlainText() for e in view.findChildren(_SceneEditor))
    assert "REAL_BODY" in bodies and "PLAN_ONLY" not in bodies
    assert db.get_scene_by_id(sid).content == "REAL_BODY"


# ==========================================================================
# 10  Logos dropdown fix still intact
# ==========================================================================


def test_logos_dropdown_still_readable():
    from PySide6.QtWidgets import QComboBox
    from logosforge.logos.controller import LogosController
    from logosforge.ui.logos.logos_toolbar import LogosToolbar
    db = Database()
    db.create_project("P", narrative_engine="novel")
    tb = LogosToolbar(LogosController(db),
                      lambda: type("C", (), {"writing_mode": "novel"})())
    tb.set_section("Outline")
    assert isinstance(tb._action_combo, QComboBox)
    assert tb._action_combo.itemText(0) == "Choose action…"
    assert tb._apply_btn.text() == "Apply…"
