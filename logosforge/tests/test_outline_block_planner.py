"""Outline = block/card based planner (Project → Act → Chapter → Scene optional).

Acts/Chapters/Scenes are editable blocks with type badges; chapters may exist
without scenes; structural changes flow through to the Manuscript structure list;
outline generation writes only to Outline data (never the manuscript body).
"""

from __future__ import annotations

import warnings

import pytest
from PySide6.QtWidgets import QApplication, QInputDialog, QLabel

warnings.filterwarnings("ignore")

from logosforge.db import Database
from logosforge.ui.plan_view import PlanView, build_plan_tree
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


def _proj(db):
    return db.create_project("P", narrative_engine="novel").id


def _badges(view):
    return [w.text() for w in view.findChildren(QLabel)
            if w.objectName() == "planTypeBadge"]


# ==========================================================================
# Block/card planner with type badges
# ==========================================================================


def test_outline_renders_block_cards_with_type_badges():
    db = Database()
    pid = _proj(db)
    db.create_scene(pid, "Opening", act="Act I", chapter="Chapter One",
                    content="x")
    view = PlanView(db, pid)
    # Act/Chapter cards exist as distinct styled blocks.
    objs = {w.objectName() for w in view.findChildren(__import__(
        "PySide6.QtWidgets", fromlist=["QWidget"]).QWidget)}
    assert "planAct" in objs and "planChapter" in objs
    badges = _badges(view)
    assert "ACT" in badges and "CHAPTER" in badges and "SCENE" in badges


# ==========================================================================
# Add Act / Chapter / Scene hierarchy
# ==========================================================================


def test_add_act(monkeypatch):
    db = Database()
    pid = _proj(db)
    view = PlanView(db, pid)
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("Act I", True))
    view._add_act()
    assert "Act I" in [a for a, _ in build_plan_tree(db, pid)]


def test_add_chapter_inside_act(monkeypatch):
    db = Database()
    pid = _proj(db)
    db.create_scene(pid, "Untitled Scene", act="Act I")
    view = PlanView(db, pid)
    monkeypatch.setattr(QInputDialog, "getText",
                        lambda *a, **k: ("Chapter One", True))
    view._add_chapter("Act I")
    chapters = [ch for _, chs in build_plan_tree(db, pid) for ch, _ in chs]
    assert "Chapter One" in chapters


def test_add_scene_inside_chapter(monkeypatch):
    db = Database()
    pid = _proj(db)
    db.create_scene(pid, "Untitled Scene", act="Act I", chapter="Ch1")
    view = PlanView(db, pid)
    monkeypatch.setattr(QInputDialog, "getText",
                        lambda *a, **k: ("Opening", True))
    view._add_scene("Act I", "Ch1")
    titles = [s.title for s in db.get_all_scenes(pid)]
    assert "Opening" in titles


def test_chapter_can_exist_without_scene():
    # A chapter placeholder (no real scenes) is still a valid outline node.
    db = Database()
    pid = _proj(db)
    db.create_scene(pid, "Untitled Scene", act="Act I", chapter="Ch1")
    tree = build_plan_tree(db, pid)
    chapters = [ch for _, chs in tree for ch, _ in chs]
    assert "Ch1" in chapters


# ==========================================================================
# Generation writes only to Outline; structural changes reach Manuscript
# ==========================================================================


def test_outline_generation_writes_only_to_outline_not_manuscript():
    from logosforge.outline_actions import (
        apply_outline_as_scenes,
        parse_outline_response,
        repair_outline_ops,
    )
    db = Database()
    pid = _proj(db)
    ops, _ = repair_outline_ops(parse_outline_response(
        "# Act 1\n## Chapter 1\n- Scene: Opening — the hero wakes"))
    created = apply_outline_as_scenes(db, pid, ops)
    assert created
    for sid in created:
        s = db.get_scene_by_id(sid)
        assert (s.content or "") == ""        # never written to manuscript body
        assert (s.summary or "").strip() or s.title


# ==========================================================================
# Mode-aware hierarchy: Novel = Act→Chapter→Scene; others = Act→Scene
# ==========================================================================


def _block_objs(view):
    from PySide6.QtWidgets import QWidget
    return [w.objectName() for w in view.findChildren(QWidget)
            if w.objectName() in ("planAct", "planChapter", "planScene")]


def test_novel_outline_is_act_chapter_scene():
    db = Database()
    pid = db.create_project("N", narrative_engine="novel").id
    db.create_scene(pid, "S1", act="Act I", chapter="Chapter One", content="x")
    objs = _block_objs(PlanView(db, pid))
    assert "planAct" in objs and "planChapter" in objs and "planScene" in objs


def test_non_novel_outline_is_act_scene_flattened():
    # Screenplay scenes with no chapter render directly under the Act — the
    # empty Chapter layer is flattened away (Act → Scene).
    db = Database()
    pid = db.create_project("S", narrative_engine="screenplay",
                            default_writing_format="screenplay").id
    db.create_scene(pid, "S1", act="Act I", content="x")   # no chapter
    objs = _block_objs(PlanView(db, pid))
    assert "planAct" in objs and "planScene" in objs
    assert "planChapter" not in objs                       # flattened


def test_non_novel_named_chapter_still_shown():
    # If a non-Novel project DOES use a named chapter, it is preserved.
    db = Database()
    pid = db.create_project("S", narrative_engine="screenplay",
                            default_writing_format="screenplay").id
    db.create_scene(pid, "S1", act="Act I", chapter="Sequence A", content="x")
    objs = _block_objs(PlanView(db, pid))
    assert "planChapter" in objs


def test_non_novel_act_has_add_scene_button():
    db = Database()
    pid = db.create_project("S", narrative_engine="screenplay",
                            default_writing_format="screenplay").id
    db.create_scene(pid, "S1", act="Act I", content="x")
    from PySide6.QtWidgets import QPushButton
    texts = " ".join(b.text() for b in PlanView(db, pid).findChildren(QPushButton))
    assert "New Scene" in texts


def test_outline_changes_refresh_manuscript_structure_list():
    db = Database()
    pid = db.create_project("S", narrative_engine="screenplay",
                            default_writing_format="screenplay").id
    db.create_scene(pid, "S1", act="Act I", chapter="Ch1", content="a")
    view = WritingCoreView(db, pid, structured_list=True)
    assert len(view._editors) == 1
    # Add a scene via the outline data, then refresh the manuscript page.
    db.create_scene(pid, "S2", act="Act II", chapter="Ch2", content="b")
    view.refresh()
    assert len(view._editors) == 2
