"""Routing guard: clicking the sidebar must mount the *new* Manuscript /
Outline / Timeline views in the running app — not old/duplicate views.

These tests exercise the real MainWindow section factory + sidebar wiring (the
gap that let earlier UI work pass unit tests while the running app showed old
views) and assert on the diagnostic objectName markers the new views carry.
"""

from __future__ import annotations

import warnings

import pytest
from PySide6.QtWidgets import QApplication

warnings.filterwarnings("ignore")

from logosforge.db import Database
from logosforge.ui.main_window import MainWindow
from logosforge.ui.plan_view import PlanView
from logosforge.ui.plot_timeline_view import PlotTimelineView
from logosforge.ui.writing_core_view import WritingCoreView


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


def _win(db, engine="novel"):
    pid = db.create_project("P", narrative_engine=engine,
                            default_writing_format=engine).id
    return MainWindow(db, pid), pid


# ==========================================================================
# Section factory map points at the canonical (new) classes
# ==========================================================================


def test_section_factory_maps_to_new_classes():
    db = Database()
    win, _ = _win(db)
    assert win._nav_section_handlers["Manuscript"].__name__ == "_show_manuscript"
    assert win._nav_section_handlers["Outline"].__name__ == "_show_plan"
    assert win._nav_section_handlers["Timeline"].__name__ == "_show_timeline"


# ==========================================================================
# Sidebar click → the new view (verified by class + diagnostic objectName)
# ==========================================================================


def test_click_manuscript_opens_new_selected_unit_view():
    db = Database()
    win, pid = _win(db, "screenplay")
    db.create_scene(pid, "S", act="Act I", chapter="Ch1", content="x")
    win.sidebar_buttons["Manuscript"].click()
    view = win.content_area
    assert isinstance(view, WritingCoreView)
    assert view._structured_list is True                 # simplified mode
    assert view.objectName() == "manuscript_target_writing_page_view"
    assert hasattr(view, "_render_writing_page")           # continuous writing page
    assert not hasattr(view, "_structure_tree")            # no left outliner tree
    assert not hasattr(view, "_scene_number")            # no numbered gutter


def test_click_outline_opens_block_card_planner():
    db = Database()
    win, pid = _win(db)
    db.create_scene(pid, "S", act="Act I", chapter="Ch1", content="x")
    win.sidebar_buttons["Outline"].click()
    view = win.content_area
    assert isinstance(view, PlanView)
    assert view.objectName() == "outline_target_block_card_planner_view"
    assert hasattr(view, "_type_badge")                  # card type badges
    from PySide6.QtWidgets import QLabel
    badges = [w.text() for w in view.findChildren(QLabel)
              if w.objectName() == "planTypeBadge"]
    assert "ACT" in badges and "SCENE" in badges


def test_click_timeline_opens_colored_lane_link_view():
    db = Database()
    win, pid = _win(db)
    db.create_scene(pid, "S", plotline="Main", content="x")
    db.create_timeline_lane(pid, "Main", "green")
    win.sidebar_buttons["Timeline"].click()
    view = win.content_area
    assert isinstance(view, PlotTimelineView)
    assert view.objectName() == "timeline_target_colored_lane_link_view"
    assert hasattr(view, "_lane_bands")                  # coloured lane bands
    assert hasattr(view, "_add_structure_link")          # event→Act/Chapter links
    assert any(chex for _, _, chex in view._lane_bands)  # a lane carries colour


# ==========================================================================
# No old/deprecated view is the default for these sections
# ==========================================================================


def test_no_legacy_views_registered_for_sections():
    # ChapterManuscriptView was deleted; ensure it can't be imported/used.
    import importlib
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("logosforge.ui.chapter_manuscript_view")


def test_outline_view_module_not_default_outline():
    # The legacy OutlineView class is not what the Outline section mounts.
    db = Database()
    win, _ = _win(db)
    win.sidebar_buttons["Outline"].click()
    assert type(win.content_area).__name__ == "PlanView"


# ==========================================================================
# Project switch keeps the new views (no stale/old widget reuse)
# ==========================================================================


# ==========================================================================
# Runtime diagnostics + visible dev markers (runtime proof, not just imports)
# ==========================================================================


def test_runtime_report_points_at_local_view_modules():
    from logosforge.diagnostics import runtime_report
    r = runtime_report()
    assert "writing_core_view" in r["manuscript_view"]
    assert "plan_view" in r["outline_view"]
    assert "plot_timeline_view" in r["timeline_view"]
    assert r["logosforge_pkg"].endswith("logosforge/__init__.py")
    assert r["commit"]                       # some commit string resolved


def test_dev_marker_off_by_default(monkeypatch):
    monkeypatch.delenv("LOGOSFORGE_DEV_MARKERS", raising=False)
    db = Database()
    win, pid = _win(db)
    win.sidebar_buttons["Outline"].click()
    from PySide6.QtWidgets import QLabel
    marks = [w for w in win.content_area.findChildren(QLabel)
             if w.objectName() == "devRuntimeMarker"]
    assert marks == []                       # never in normal UX


def test_dev_marker_visible_when_enabled_via_routing(monkeypatch):
    monkeypatch.setenv("LOGOSFORGE_DEV_MARKERS", "1")
    db = Database()
    a = db.create_project("A", narrative_engine="screenplay",
                          default_writing_format="screenplay").id
    db.create_scene(a, "S", plotline="Main", content="x")
    win = MainWindow(db, a)
    from PySide6.QtWidgets import QLabel
    for section, expect in (
        ("Manuscript", "NEW MANUSCRIPT VIEW"),
        ("Outline", "NEW OUTLINE VIEW"),
        ("Timeline", "NEW TIMELINE VIEW"),
    ):
        win.sidebar_buttons[section].click()
        texts = [w.text() for w in win.content_area.findChildren(QLabel)
                 if w.objectName() == "devRuntimeMarker"]
        assert any(expect in t for t in texts), f"{section}: {texts}"


def test_project_switch_keeps_new_views():
    db = Database()
    a = db.create_project("A", narrative_engine="screenplay",
                          default_writing_format="screenplay").id
    b = db.create_project("B", narrative_engine="novel").id
    win = MainWindow(db, a)
    for section, cls, marker in (
        ("Manuscript", WritingCoreView, "manuscript_target_writing_page_view"),
        ("Outline", PlanView, "outline_target_block_card_planner_view"),
        ("Timeline", PlotTimelineView, "timeline_target_colored_lane_link_view"),
    ):
        win.sidebar_buttons[section].click()
        assert isinstance(win.content_area, cls)
        win._switch_project(b)
        win.sidebar_buttons[section].click()
        assert isinstance(win.content_area, cls)
        assert win.content_area.objectName() == marker
        win._switch_project(a)
