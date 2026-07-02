"""Outline ↔ Timeline ↔ Manuscript logical integration around ONE canonical
story structure (logosforge.story_structure).

Verifies: the shared adapter's ordered tree + numbering; Manuscript reads that
order (never Scenes-before-Acts, no fabricated Acts); Outline edits the same
structure; Timeline *links* to it (canonical chip numbers) without duplicating
or reordering it; and everything stays project-isolated.
"""

from __future__ import annotations

import warnings

import pytest
from PySide6.QtWidgets import QApplication, QLabel

warnings.filterwarnings("ignore")

from logosforge.db import Database
from logosforge.story_structure import (
    UNASSIGNED_ACT,
    build_structure_tree,
    compute_structural_numbers,
    get_ordered_structure,
    get_unit_path,
    is_novel_project,
)
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


def _novel(db):
    return db.create_project("P", narrative_engine="novel").id


def _act_headers(view):
    return [w.text() for w in view.findChildren(QLabel)
            if w.objectName() == "writingActHeader"]


# ==========================================================================
# 1-6  Canonical structure adapter
# ==========================================================================


def test_ordered_structure_is_act_chapter_scene():
    db = Database()
    pid = _novel(db)
    db.create_scene(pid, "S1", act="Act I", chapter="Ch1", content="x")
    tree = get_ordered_structure(db, pid)
    assert [a for a, _ in tree] == ["Act I"]
    assert [c for _, chs in tree for c, _ in chs] == ["Ch1"]


def test_orphan_scenes_sort_last_under_unassigned():
    db = Database()
    pid = _novel(db)
    # Orphan created FIRST (lowest sort_order) — must still render last.
    db.create_scene(pid, "Loose", content="body")
    db.create_scene(pid, "Real", act="Act I", chapter="Ch1", content="x")
    acts = [a for a, _ in build_structure_tree(db, pid)]
    assert acts == ["Act I", UNASSIGNED_ACT]          # named first, orphan last


def test_numbering_is_1_1p1_1p1p1():
    db = Database()
    pid = _novel(db)
    sid = db.create_scene(pid, "S1", act="Act I", chapter="Ch1", content="x").id
    nums = compute_structural_numbers(build_structure_tree(db, pid), True)
    assert nums["acts"]["Act I"] == "1"
    assert nums["chapters"][("Act I", "Ch1")] == "1.1"
    assert nums["scenes"][sid] == "1.1.1"


def test_moving_chapter_updates_numbering():
    db = Database()
    pid = _novel(db)
    db.create_scene(pid, "A", act="Act I", chapter="Ch1", content="x")
    db.create_scene(pid, "B", act="Act I", chapter="Ch2", content="y")
    view = PlanView(db, pid)
    nums = compute_structural_numbers(build_structure_tree(db, pid), True)
    assert nums["chapters"][("Act I", "Ch1")] == "1.1"
    view.move_chapter("Act I", "Ch2", -1)             # Ch2 now first
    nums = compute_structural_numbers(build_structure_tree(db, pid), True)
    assert nums["chapters"][("Act I", "Ch2")] == "1.1"
    assert nums["chapters"][("Act I", "Ch1")] == "1.2"


def test_moving_scene_updates_numbering():
    db = Database()
    pid = _novel(db)
    a = db.create_scene(pid, "A", act="Act I", chapter="Ch1", content="x").id
    b = db.create_scene(pid, "B", act="Act I", chapter="Ch1", content="y").id
    view = PlanView(db, pid)
    view.move_scene(a, +1)                              # B before A
    nums = compute_structural_numbers(build_structure_tree(db, pid), True)
    assert nums["scenes"][b] == "1.1.1" and nums["scenes"][a] == "1.1.2"


def test_orphan_scenes_unnumbered():
    db = Database()
    pid = _novel(db)
    o = db.create_scene(pid, "Loose", content="x").id
    nums = compute_structural_numbers(build_structure_tree(db, pid), True)
    assert nums["scenes"][o] == ""                      # safe, never a fake Act


def test_unit_path_is_canonical():
    db = Database()
    pid = _novel(db)
    sid = db.create_scene(pid, "S", act="Act I", chapter="Ch1", content="x").id
    assert get_unit_path(db, pid, sid) == "Act 1 · Chapter 1.1 · Scene 1.1.1"


# ==========================================================================
# 7-12  Manuscript reads the canonical structure
# ==========================================================================


def test_manuscript_repairs_orphans_no_unassigned(tmp_path):
    db = Database(str(tmp_path / "sp.db"))
    pid = _novel(db)
    db.create_scene(pid, "Loose", content="orphan body")   # orphan FIRST
    db.create_scene(pid, "Real", act="Act I", chapter="Ch1", content="x")
    win = MainWindow(db, pid)
    win.sidebar_buttons["Manuscript"].click()
    headers = _act_headers(win.content_area)
    assert headers, "expected Act headers"
    # The invariant is enforced before display: the orphan is recovered into a
    # real Act → Chapter, so there is NO "Unassigned" surface and no floating
    # scene. Every header is a real Act.
    assert not any("UNASSIGNED" in h for h in headers)
    assert any("RECOVERED ACT" in h for h in headers)
    assert any("ACT I" in h for h in headers)
    from logosforge.story_structure import validate_structure
    assert validate_structure(db, pid) == []          # no orphans remain


def test_manuscript_scene_context_uses_canonical_number(tmp_path):
    db = Database(str(tmp_path / "sp.db"))
    pid = _novel(db)
    db.create_scene(pid, "S", act="Act I", chapter="Ch1", content="x")
    win = MainWindow(db, pid)
    win.sidebar_buttons["Manuscript"].click()
    ctx = [w.text() for w in win.content_area.findChildren(QLabel)
           if w.objectName() == "writingSceneContext"]
    assert "SCENE 1.1.1" in ctx


def test_double_click_outline_chapter_opens_manuscript(tmp_path):
    db = Database(str(tmp_path / "sp.db"))
    pid = _novel(db)
    sid = db.create_scene(pid, "S", act="Act I", chapter="Ch1", content="x").id
    win = MainWindow(db, pid)
    win.sidebar_buttons["Outline"].click()
    win.content_area._open_chapter_in_manuscript("Act I", "Ch1")
    assert win._current_section == "Manuscript"
    assert isinstance(win.content_area, WritingCoreView)
    assert sid in win.content_area._editors


def test_double_click_outline_scene_opens_manuscript(tmp_path):
    db = Database(str(tmp_path / "sp.db"))
    pid = _novel(db)
    sid = db.create_scene(pid, "S", act="Act I", chapter="Ch1", content="x").id
    win = MainWindow(db, pid)
    win.sidebar_buttons["Outline"].click()
    win.content_area._open_in_manuscript(sid)
    assert win._current_section == "Manuscript"
    assert isinstance(win.content_area, WritingCoreView)


def test_outline_edit_summary_does_not_touch_body(monkeypatch):
    db = Database()
    pid = _novel(db)
    sid = db.create_scene(pid, "S", act="Act I", chapter="Ch1",
                          content="REAL PROSE").id
    PlanView(db, pid)._save_scene_summary(sid, "planning text")
    s = db.get_scene_by_id(sid)
    assert s.summary == "planning text" and s.content == "REAL PROSE"


def test_outline_move_does_not_overwrite_body():
    db = Database()
    pid = _novel(db)
    a = db.create_scene(pid, "A", act="Act I", chapter="Ch1",
                        content="BODY A").id
    db.create_scene(pid, "B", act="Act II", chapter="Ch2", content="y")
    PlanView(db, pid).move_chapter_to_act("Act I", "Ch1", "Act II")
    assert db.get_scene_by_id(a).content == "BODY A"


# ==========================================================================
# 13-16  Outline edits the canonical structure
# ==========================================================================


def test_outline_cards_show_canonical_numbers():
    db = Database()
    pid = _novel(db)
    db.create_scene(pid, "S", act="Act I", chapter="Ch1", content="x")
    view = PlanView(db, pid)
    nums = [w.text() for w in view.findChildren(QLabel)
            if w.objectName() == "planNumber"]
    assert "1" in nums and "1.1" in nums and "1.1.1" in nums


def test_outline_move_updates_canonical_structure():
    db = Database()
    pid = _novel(db)
    db.create_scene(pid, "A", act="Act I", chapter="Ch1", content="x")
    db.create_scene(pid, "B", act="Act II", chapter="Ch2", content="y")
    PlanView(db, pid).move_act("Act II", -1)
    assert [a for a, _ in get_ordered_structure(db, pid)] == ["Act II", "Act I"]


def test_outline_move_reflected_in_fresh_manuscript(tmp_path):
    db = Database(str(tmp_path / "sp.db"))
    pid = _novel(db)
    db.create_scene(pid, "A", act="Act I", chapter="Ch1", content="x")
    db.create_scene(pid, "B", act="Act II", chapter="Ch2", content="y")
    PlanView(db, pid).move_act("Act II", -1)
    win = MainWindow(db, pid)
    win.sidebar_buttons["Manuscript"].click()
    headers = _act_headers(win.content_area)
    assert headers[0] == "ACT 1 · ACT II"              # canonical order shared


# ==========================================================================
# 17-23  Timeline links (not duplicates) the canonical structure
# ==========================================================================


def test_timeline_links_to_act_chapter_scene():
    db = Database()
    pid = _novel(db)
    s = db.create_scene(pid, "S", act="Act I", chapter="Ch1", content="x").id
    other = db.create_scene(pid, "O", content="y").id
    view = PlotTimelineView(db, pid)
    view._add_structure_link(s, "act", "Act I")
    view._add_structure_link(s, "chapter", "Ch1")
    view._link_to_scene_direct(s, other)
    assert {(l.target_type, l.target_ref)
            for l in db.get_timeline_structure_links(s)} == {
                ("act", "Act I"), ("chapter", "Ch1")}
    assert len(db.get_timeline_links(pid)) == 1


def test_timeline_chip_shows_canonical_number_and_updates_on_move():
    db = Database()
    pid = _novel(db)
    s = db.create_scene(pid, "S", act="Act I", chapter="Ch1", content="x").id
    db.create_scene(pid, "S2", act="Act II", content="y")
    view = PlotTimelineView(db, pid)
    view._add_structure_link(s, "act", "Act I")
    sl = db.get_timeline_structure_links(s)[0]
    assert view._struct_ref_label(sl) == "Act 1"
    # Reorder Acts in the Outline → the Timeline chip's canonical number follows.
    PlanView(db, pid).move_act("Act II", -1)
    view.refresh()
    sl = db.get_timeline_structure_links(s)[0]
    assert view._struct_ref_label(sl) == "Act 2"


def test_timeline_move_does_not_reorder_outline():
    db = Database()
    pid = _novel(db)
    # Events must be on a lane to be reorderable on the Timeline.
    a = db.create_scene(pid, "A", act="Act I", chapter="Ch1", content="x",
                        plotline="Main").id
    b = db.create_scene(pid, "B", act="Act I", chapter="Ch1", content="y",
                        plotline="Main").id
    before = [s.id for s in db.get_all_scenes(pid)]
    view = PlotTimelineView(db, pid)
    view._move_event(b, -1)                            # timeline-only reorder
    assert [s.id for s in db.get_all_scenes(pid)] == before     # Outline intact
    assert db.get_timeline_order(pid) == [b, a]                 # timeline order


def test_unassigned_scene_does_not_create_lane_without_real_lanes():
    # An Outline scene (no plotline) is NOT a Timeline event, so it never shows
    # as a lane/Unassigned — even after a real lane is created. The Timeline is
    # user-controlled: only assigned/linked scenes become events.
    db = Database()
    pid = _novel(db)
    db.create_scene(pid, "Floating", content="x")      # Outline scene, no lane
    view = PlotTimelineView(db, pid)
    assert view._rows == []                             # nothing shown
    db.create_timeline_lane(pid, "Main", "green")       # user opts into Timeline
    view.refresh()
    names = [name for _, name, _ in view._rows]
    assert names == ["Main"]                            # still no Unassigned row


def test_timeline_chip_safe_when_target_renamed():
    db = Database()
    pid = _novel(db)
    s = db.create_scene(pid, "S", act="Act I", content="x").id
    db.add_timeline_structure_link(pid, s, "act", "Ghost")   # no such act
    view = PlotTimelineView(db, pid)
    sl = db.get_timeline_structure_links(s)[0]
    assert view._struct_ref_label(sl) == "Ghost"        # falls back, no crash


# ==========================================================================
# 24-26 / 30  Project isolation + Canvas Plot deferral
# ==========================================================================


def test_structure_isolated_across_projects(tmp_path):
    db = Database(str(tmp_path / "sp.db"))
    a = _novel(db)
    db.create_scene(a, "A", act="Act A", chapter="Ch", content="x")
    db.add_timeline_structure_link(a, db.get_all_scenes(a)[0].id, "act", "Act A")
    b = _novel(db)
    assert get_ordered_structure(db, b) == []
    assert db.get_all_timeline_structure_links(b) == []


def test_switch_clears_selection_and_structure(tmp_path):
    db = Database(str(tmp_path / "sp.db"))
    a = _novel(db)
    sa = db.create_scene(a, "A", act="Act A", chapter="Ch", content="x").id
    b = _novel(db)
    win = MainWindow(db, a)
    win.sidebar_buttons["Timeline"].click()
    win.content_area._start_link(sa)
    win._switch_project(b)
    win.sidebar_buttons["Timeline"].click()
    assert win.content_area._pending_link_source is None
    assert get_ordered_structure(db, b) == []


def test_canvas_plot_still_deferred(tmp_path):
    db = Database(str(tmp_path / "sp.db"))
    win = MainWindow(db, _novel(db))
    assert "Plot" not in win._nav_labels
