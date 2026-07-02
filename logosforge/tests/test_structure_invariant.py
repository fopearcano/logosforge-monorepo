"""Structural invariant — Act → Chapter → Scene enforced everywhere.

Every Scene must have a Chapter; every Chapter an Act. New structure is created
valid (no orphans); legacy orphan data is repaired in place into Recovered Act /
Recovered Chapter (preserving body + links); and no normal UI surface shows
orphan/"Unassigned" structure.
"""

from __future__ import annotations

import warnings

import pytest
from PySide6.QtWidgets import QApplication, QInputDialog, QLabel

warnings.filterwarnings("ignore")

from logosforge.db import Database
from logosforge import story_structure as ss
from logosforge.story_structure import (
    UNASSIGNED_ACT,
    build_structure_tree,
    compute_structural_numbers,
    ensure_valid_structure,
    is_novel_project,
    validate_structure,
)
from logosforge.ui.main_window import MainWindow
from logosforge.ui.plan_view import PlanView
from logosforge.ui.plot_timeline_view import PlotTimelineView
from logosforge.ui.writing_core_view import WritingCoreView, _SceneEditor


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


def _text(monkeypatch, value):
    monkeypatch.setattr(QInputDialog, "getText",
                        staticmethod(lambda *a, **k: (value, True)))


# ==========================================================================
# 1-7  Canonical structure + invariant on creation
# ==========================================================================


def test_new_project_has_no_orphans():
    db = Database()
    pid = _novel(db)
    assert validate_structure(db, pid) == []        # empty project, no orphans
    assert build_structure_tree(db, pid) == []


def test_create_scene_without_chapter_autoparents():
    db = Database()
    pid = _novel(db)
    s = ss.create_scene(db, pid, title="First")      # no parent given
    s = db.get_scene_by_id(s.id)
    assert s.act and s.chapter                        # both filled
    assert validate_structure(db, pid) == []


def test_create_chapter_without_act_autoparents():
    db = Database()
    pid = _novel(db)
    s = ss.create_chapter(db, pid, act="", name="Ch X")
    s = db.get_scene_by_id(s.id)
    assert s.act and s.chapter == "Ch X"
    assert validate_structure(db, pid) == []


def test_create_act_seeds_valid_chain_not_orphan():
    db = Database()
    pid = _novel(db)
    ss.create_act(db, pid, "Act I")
    assert validate_structure(db, pid) == []          # Act → Chapter → Scene
    tree = build_structure_tree(db, pid)
    assert [a for a, _ in tree] == ["Act I"]
    assert [c for _, chs in tree for c, _ in chs] == [ss.DEFAULT_CHAPTER]


def test_ordered_structure_and_numbering():
    db = Database()
    pid = _novel(db)
    sid = ss.create_scene(db, pid, act="Act I", chapter="Ch1", title="S").id
    tree = build_structure_tree(db, pid)
    assert [a for a, _ in tree] == ["Act I"]
    nums = compute_structural_numbers(tree, True)
    assert nums["acts"]["Act I"] == "1"
    assert nums["chapters"][("Act I", "Ch1")] == "1.1"
    assert nums["scenes"][sid] == "1.1.1"


def test_no_duplicate_numbering():
    db = Database()
    pid = _novel(db)
    for i in range(3):
        ss.create_scene(db, pid, act="Act I", chapter="Ch1", title=f"S{i}")
    nums = compute_structural_numbers(build_structure_tree(db, pid), True)["scenes"]
    assert len(set(nums.values())) == len(nums) == 3


# ==========================================================================
# 8-12  Repair of legacy buggy data
# ==========================================================================


def test_orphan_scene_repaired_into_recovered_act_chapter():
    db = Database()
    pid = _novel(db)
    sid = db.create_scene(pid, "Loose", content="x").id   # no act/chapter
    ensure_valid_structure(db, pid)
    s = db.get_scene_by_id(sid)
    assert s.act == ss.RECOVERED_ACT and s.chapter == ss.RECOVERED_CHAPTER


def test_orphan_chapter_repaired_keeps_act():
    db = Database()
    pid = _novel(db)
    sid = db.create_scene(pid, "HalfA", act="Act I", content="x").id  # no chapter
    ensure_valid_structure(db, pid)
    s = db.get_scene_by_id(sid)
    assert s.act == "Act I" and s.chapter == ss.RECOVERED_CHAPTER


def test_repair_preserves_body():
    db = Database()
    pid = _novel(db)
    sid = db.create_scene(pid, "S", content="PRECIOUS PROSE").id
    ensure_valid_structure(db, pid)
    assert db.get_scene_by_id(sid).content == "PRECIOUS PROSE"


def test_repair_preserves_note_links():
    db = Database()
    pid = _novel(db)
    sid = db.create_scene(pid, "S", content="x").id
    note = db.create_note(pid, "N", "body")
    db.link_note_to_scene(note.id, sid)
    ensure_valid_structure(db, pid)
    assert sid in db.get_note_scene_links(note.id)


def test_repair_is_idempotent():
    db = Database()
    pid = _novel(db)
    db.create_scene(pid, "S", content="x")
    assert ensure_valid_structure(db, pid)["repaired"] == 1
    assert ensure_valid_structure(db, pid)["repaired"] == 0


def test_manuscript_render_repairs_and_hides_unassigned(tmp_path):
    db = Database(str(tmp_path / "sp.db"))
    pid = _novel(db)
    db.create_scene(pid, "Loose", content="x")        # orphan
    WritingCoreView(db, pid, structured_list=True)     # render repairs
    assert validate_structure(db, pid) == []
    assert UNASSIGNED_ACT not in [a for a, _ in build_structure_tree(db, pid)]


# ==========================================================================
# 13-19  Manuscript
# ==========================================================================


def test_manuscript_add_scene_under_current_chapter():
    db = Database()
    pid = _novel(db)
    ss.create_scene(db, pid, act="Act I", chapter="Ch1", title="S")
    view = WritingCoreView(db, pid, structured_list=True)
    view._page_new_scene("Act I", "Ch1", None)
    new = [s for s in db.get_all_scenes(pid) if s.title == "Untitled"][-1]
    assert new.act == "Act I" and new.chapter == "Ch1"
    assert validate_structure(db, pid) == []


def test_manuscript_add_chapter_under_current_act():
    db = Database()
    pid = _novel(db)
    ss.create_scene(db, pid, act="Act I", chapter="Ch1", title="S")
    view = WritingCoreView(db, pid, structured_list=True)
    view._page_new_chapter("Act I")
    chapters = {(s.act, s.chapter) for s in db.get_all_scenes(pid)}
    assert ("Act I", "New Chapter") in chapters
    assert validate_structure(db, pid) == []


def test_manuscript_empty_state_add_creates_valid_chain():
    db = Database()
    pid = _novel(db)
    view = WritingCoreView(db, pid, structured_list=True)
    view._create_scene_after(None)                     # the empty-state button
    assert validate_structure(db, pid) == []
    s = db.get_all_scenes(pid)[0]
    assert s.act == ss.DEFAULT_ACT and s.chapter == ss.DEFAULT_CHAPTER


def test_manuscript_body_separate_from_summary(tmp_path):
    db = Database(str(tmp_path / "sp.db"))
    pid = _novel(db)
    db.create_scene(pid, "S", summary="OUTLINE_ONLY", content="REAL PROSE")
    win = MainWindow(db, pid)
    win.sidebar_buttons["Manuscript"].click()
    bodies = " ".join(e.toPlainText()
                      for e in win.content_area.findChildren(_SceneEditor))
    assert "REAL PROSE" in bodies and "OUTLINE_ONLY" not in bodies


# ==========================================================================
# 20-25  Outline writes valid structure
# ==========================================================================


def test_outline_add_act_creates_no_orphan(monkeypatch):
    db = Database()
    pid = _novel(db)
    view = PlanView(db, pid)
    _text(monkeypatch, "Act I")
    view._add_act()
    assert validate_structure(db, pid) == []           # Act seeded with Chapter


def test_outline_add_scene_at_act_level_gets_chapter(monkeypatch):
    db = Database()
    pid = db.create_project("S", narrative_engine="screenplay",
                            default_writing_format="screenplay").id
    ss.create_act(db, pid, "Act I")
    view = PlanView(db, pid)
    _text(monkeypatch, "Scene X")
    view._add_scene("Act I", UNASSIGNED_ACT)           # act-level (no chapter)
    assert validate_structure(db, pid) == []           # chapter auto-filled


def test_outline_top_level_is_acts_only_when_valid():
    db = Database()
    pid = _novel(db)
    ss.create_scene(db, pid, act="Act I", chapter="Ch1", title="S")
    tree = build_structure_tree(db, pid)
    assert all(a != UNASSIGNED_ACT for a, _ in tree)    # no Unassigned bucket
    assert [a for a, _ in tree] == ["Act I"]


def test_move_scene_preserves_valid_chapter_parent():
    db = Database()
    pid = _novel(db)
    a = ss.create_scene(db, pid, act="Act I", chapter="Ch1", title="A").id
    ss.create_scene(db, pid, act="Act II", chapter="Ch2", title="B")
    PlanView(db, pid).move_scene_to_chapter(a, "Act II", "Ch2")
    s = db.get_scene_by_id(a)
    assert s.act == "Act II" and s.chapter == "Ch2"
    assert validate_structure(db, pid) == []


def test_move_chapter_preserves_valid_act_parent():
    db = Database()
    pid = _novel(db)
    ss.create_scene(db, pid, act="Act I", chapter="Ch1", title="A")
    ss.create_scene(db, pid, act="Act II", chapter="Ch2", title="B")
    PlanView(db, pid).move_chapter_to_act("Act I", "Ch1", "Act II")
    assert validate_structure(db, pid) == []
    assert db.get_scene_by_id(
        [s.id for s in db.get_all_scenes(pid) if s.chapter == "Ch1"][0]
    ).act == "Act II"


# ==========================================================================
# 28-33  Timeline links + isolation
# ==========================================================================


def test_timeline_create_linked_scene_is_not_orphan():
    db = Database()
    pid = _novel(db)
    db.create_timeline_lane(pid, "Main", "green")
    view = PlotTimelineView(db, pid)
    import logosforge.ui.plot_timeline_view as m
    m.QInputDialog.getText = staticmethod(lambda *a, **k: ("Event", True))
    view._add_event_to_lane("Main")
    assert validate_structure(db, pid) == []           # valid Act/Chapter parent
    ev = [s for s in db.get_all_scenes(pid) if s.title == "Event"][0]
    assert ev.plotline == "Main" and ev.act and ev.chapter


def test_timeline_event_card_shows_canonical_number():
    db = Database()
    pid = _novel(db)
    ss.create_scene(db, pid, act="Act I", chapter="Ch1", title="Opening",
                    plotline="Main")
    db.create_timeline_lane(pid, "Main", "green")
    view = PlotTimelineView(db, pid)
    titles = " ".join(w.text() for w in view.findChildren(QLabel))
    assert "1.1.1" in titles                            # canonical path on card


def test_timeline_move_does_not_change_outline_structure():
    db = Database()
    pid = _novel(db)
    a = ss.create_scene(db, pid, act="Act I", chapter="Ch1", title="A").id
    b = ss.create_scene(db, pid, act="Act I", chapter="Ch1", title="B").id
    before = [(s.id, s.act, s.chapter, s.sort_order)
              for s in db.get_all_scenes(pid)]
    PlotTimelineView(db, pid)._move_event(b, -1)
    after = [(s.id, s.act, s.chapter, s.sort_order)
             for s in db.get_all_scenes(pid)]
    assert before == after                              # Outline untouched


def test_structure_isolated_between_projects(tmp_path):
    db = Database(str(tmp_path / "sp.db"))
    a = _novel(db)
    ss.create_scene(db, a, act="Act A", chapter="Ch", title="S")
    b = _novel(db)
    assert build_structure_tree(db, b) == []
    assert validate_structure(db, b) == []


def test_canvas_plot_still_hidden(tmp_path):
    db = Database(str(tmp_path / "sp.db"))
    win = MainWindow(db, _novel(db))
    assert "Plot" not in win._nav_labels
