"""Mode-aware Outline + Manuscript: Novel = Act→Chapter (chapters write body),
non-Novel = Act→Scene. Generation never writes manuscript body."""

from __future__ import annotations

import json
import warnings

import pytest
from PySide6.QtWidgets import QApplication

warnings.filterwarnings("ignore")

from logosforge.db import Database
from logosforge.export import export_json
from logosforge.import_data import import_json
from logosforge.outline_actions import (
    apply_outline_as_chapters,
    apply_outline_as_scenes,
    build_mode_outline_prompt,
    outline_unit_labels,
    parse_outline_response,
    repair_outline_ops,
    validate_mode_outline,
)
from logosforge.ui.chapter_outline_view import ChapterOutlineView
from logosforge.ui.main_window import MainWindow
from logosforge.ui.plan_view import PlanView
from logosforge.ui.writing_core_view import WritingCoreView
from logosforge.writing_modes import primary_unit_label


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


def _project(db, engine, fmt=""):
    return db.create_project("P", narrative_engine=engine,
                             default_writing_format=fmt or engine).id


_NOVEL_RESP = """# Act 1: Beginning
- Chapter: Dawn — the hero wakes to a strange light
- Chapter: The Call — a summons arrives at the door
# Act 2: Rising
- Chapter: Threshold — leaving the old life behind
"""
_SCREEN_RESP = """# Act 1
- Scene: INT. KITCHEN — the argument boils over
- Scene: EXT. STREET — the chase begins
"""


# ==========================================================================
# Outline generation — mode-aware structure + descriptions + no manuscript write
# ==========================================================================


def test_unit_labels():
    assert outline_unit_labels("novel") == ("Act", "Chapter")
    assert outline_unit_labels("screenplay") == ("Act", "Scene")
    assert primary_unit_label("novel") == "Chapter"
    assert primary_unit_label("screenplay") == "Scene"


def test_novel_prompt_is_act_chapter():
    p = build_mode_outline_prompt("novel")
    assert "Act → Chapter" in p
    s = build_mode_outline_prompt("screenplay")
    assert "Act → Scene" in s


def test_novel_outline_creates_act_chapter_with_descriptions():
    db = Database()
    pid = _project(db, "novel")
    ops, _ = repair_outline_ops(parse_outline_response(_NOVEL_RESP))
    ok, errors = validate_mode_outline("novel", ops)
    assert ok, errors
    created = apply_outline_as_chapters(db, pid, ops)
    chapters = db.get_chapters(pid)
    assert len(chapters) == len(created) == 3
    assert {c.act for c in chapters} == {"Act 1", "Act 2"}
    assert all(c.summary.strip() for c in chapters)     # descriptions present
    # No scene layer required / created; manuscript body untouched.
    assert db.get_all_scenes(pid) == []
    assert all((c.content or "") == "" for c in chapters)


def test_non_novel_outline_creates_act_scene_with_descriptions():
    db = Database()
    pid = _project(db, "screenplay", "screenplay")
    ops, _ = repair_outline_ops(parse_outline_response(_SCREEN_RESP))
    ok, errors = validate_mode_outline("screenplay", ops)
    assert ok, errors
    created = apply_outline_as_scenes(db, pid, ops)
    scenes = db.get_all_scenes(pid)
    assert len(scenes) == len(created) == 2
    assert all(s.summary.strip() for s in scenes)       # descriptions present
    assert db.get_chapters(pid) == []                   # no chapters in screenplay


def test_screenplay_outline_does_not_create_chapters():
    db = Database()
    pid = _project(db, "screenplay", "screenplay")
    ops, _ = repair_outline_ops(parse_outline_response(_SCREEN_RESP))
    apply_outline_as_scenes(db, pid, ops)
    assert db.get_chapters(pid) == []


def test_invalid_generated_outline_rejected():
    ops = parse_outline_response("")
    ok, errors = validate_mode_outline("novel", ops)
    assert ok is False and errors
    prose = parse_outline_response("It was a dark and stormy night, " * 20)
    ok2, errors2 = validate_mode_outline("novel", prose)
    assert ok2 is False


def test_chapter_outline_view_generation_does_not_touch_manuscript():
    db = Database()
    pid = _project(db, "novel")
    view = ChapterOutlineView(db, pid)
    created = view.apply_generated_outline(_NOVEL_RESP, confirm=False)
    assert created
    assert db.get_all_scenes(pid) == []                 # nothing written to scenes
    assert all((c.content or "") == "" for c in db.get_chapters(pid))


# ==========================================================================
# Manuscript — scene-based (rolled back); only the add-button LABEL is mode-aware
# ==========================================================================


def test_novel_manuscript_add_button_is_chapter():
    db = Database()
    pid = _project(db, "novel")
    view = WritingCoreView(db, pid)
    assert view.add_button_text() == "+ Chapter"


def test_non_novel_manuscript_add_button_is_scene():
    db = Database()
    pid = _project(db, "screenplay", "screenplay")
    view = WritingCoreView(db, pid)
    assert view.add_button_text() == "+ Scene"


# ==========================================================================
# Section wiring per mode (via MainWindow): Manuscript is always WritingCoreView;
# Outline remains mode-aware (Novel ChapterOutlineView / others PlanView).
# ==========================================================================


def test_novel_uses_scene_manuscript_and_unified_outline(tmp_path):
    db = Database(str(tmp_path / "sp.db"))
    pid = _project(db, "novel")
    win = MainWindow(db, pid)
    win.sidebar_buttons["Manuscript"].click()
    assert isinstance(win.content_area, WritingCoreView)
    assert win.content_area.add_button_text() == "+ Chapter"
    # Outline is the single structural section (PlanView) for all modes.
    win.sidebar_buttons["Outline"].click()
    assert isinstance(win.content_area, PlanView)


def test_screenplay_uses_scene_views(tmp_path):
    db = Database(str(tmp_path / "sp.db"))
    pid = _project(db, "screenplay", "screenplay")
    win = MainWindow(db, pid)
    win.sidebar_buttons["Manuscript"].click()
    assert isinstance(win.content_area, WritingCoreView)
    assert win.content_area.add_button_text() == "+ Scene"
    win.sidebar_buttons["Outline"].click()
    assert isinstance(win.content_area, PlanView)


def test_switch_updates_manuscript_label_and_outline_view(tmp_path):
    db = Database(str(tmp_path / "sp.db"))
    nov = _project(db, "novel")
    scr = _project(db, "screenplay", "screenplay")
    win = MainWindow(db, nov)
    win.sidebar_buttons["Manuscript"].click()
    assert win.content_area.add_button_text() == "+ Chapter"
    win._switch_project(scr)
    win.sidebar_buttons["Manuscript"].click()
    assert isinstance(win.content_area, WritingCoreView)
    assert win.content_area.add_button_text() == "+ Scene"
    win.sidebar_buttons["Outline"].click()
    assert isinstance(win.content_area, PlanView)
    win._switch_project(nov)
    win.sidebar_buttons["Outline"].click()
    assert isinstance(win.content_area, PlanView)


def test_outline_rebuilds_fresh_on_switch(tmp_path):
    db = Database(str(tmp_path / "sp.db"))
    a = _project(db, "novel")
    db.create_scene(a, "A-scene", act="Act I", chapter="Ch1")
    b = _project(db, "novel")
    win = MainWindow(db, a)
    win.sidebar_buttons["Outline"].click()
    view_a = win.content_area
    win._switch_project(b)
    win.sidebar_buttons["Outline"].click()
    # Rebuilt fresh for the new (empty) project — no stale acts/chapters/scenes.
    assert win.content_area is not view_a
    from logosforge.ui.plan_view import build_plan_tree
    assert build_plan_tree(db, b) == []


# ==========================================================================
# Export round-trip of chapters
# ==========================================================================


def test_export_import_chapters_roundtrip(tmp_path):
    db = Database(str(tmp_path / "sp.db"))
    pid = _project(db, "novel")
    db.create_chapter(pid, title="Alpha", summary="s", content="body A", act="Act 1")
    data = json.loads(export_json(db, pid))
    assert [c["title"] for c in data["chapters"]] == ["Alpha"]
    new_pid = import_json(db, data)
    new = db.get_chapters(new_pid)
    assert len(new) == 1 and new[0].content == "body A" and new[0].act == "Act 1"
