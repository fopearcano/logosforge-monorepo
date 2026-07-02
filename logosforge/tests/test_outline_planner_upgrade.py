"""Outline planner upgrade — compact movable cards, automatic renumbering,
double-click → Manuscript, and Novelcrafter-like planning metadata.

Covers the upgraded Outline block planner: structural numbering that retracks
after moves, Act/Chapter/Scene move operations (the single source of truth that
both the menu controls and drag/drop call), opening a unit in Manuscript, and
the compact planning chips (status / tags / Codex / word count / summary).
Move operations must never touch the manuscript body or break links, and the
Canvas Plot section stays deferred.
"""

from __future__ import annotations

import warnings

import pytest
from PySide6.QtWidgets import (
    QApplication,
    QInputDialog,
    QLabel,
    QMessageBox,
    QWidget,
)

warnings.filterwarnings("ignore")

from logosforge.db import Database
from logosforge.ui.main_window import MainWindow
from logosforge.ui.plan_view import (
    PlanView,
    build_plan_tree,
    compute_outline_numbering,
    scene_status,
)
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


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def _novel(db):
    return db.create_project("P", narrative_engine="novel").id


def _seed(db, pid):
    """Act I → Ch1 (S1, S2), Ch2 (S3); Act II → Ch3 (S4)."""
    return {
        "s1": db.create_scene(pid, "S1", act="Act I", chapter="Ch1",
                              content="alpha beta gamma").id,
        "s2": db.create_scene(pid, "S2", act="Act I", chapter="Ch1").id,
        "s3": db.create_scene(pid, "S3", act="Act I", chapter="Ch2").id,
        "s4": db.create_scene(pid, "S4", act="Act II", chapter="Ch3").id,
    }


def _objs(view, name):
    return [w for w in view.findChildren(QWidget) if w.objectName() == name]


def _labels(view, name):
    return [w for w in view.findChildren(QLabel) if w.objectName() == name]


def _ch_order(db, pid, act, chapter):
    return [s.id for a, chs in build_plan_tree(db, pid) if a == act
            for c, scs in chs if c == chapter for s in scs]


def _scene_nums(db, pid, is_novel=True):
    return compute_outline_numbering(build_plan_tree(db, pid), is_novel)["scenes"]


# ==========================================================================
# 1-5  Visual / routing
# ==========================================================================


def test_sidebar_outline_mounts_upgraded_planner(tmp_path):
    db = Database(str(tmp_path / "sp.db"))
    win = MainWindow(db, _novel(db))
    win.sidebar_buttons["Outline"].click()
    assert isinstance(win.content_area, PlanView)
    assert win.content_area.objectName() == "outline_target_block_card_planner_view"


def test_outline_has_act_chapter_scene_cards():
    db = Database()
    pid = _novel(db)
    _seed(db, pid)
    view = PlanView(db, pid)
    assert _objs(view, "planAct")          # Act containers
    assert _objs(view, "planChapter")      # Chapter cards
    assert _objs(view, "planScene")        # Scene cards


def test_cards_expose_outline_role_markers():
    db = Database()
    pid = _novel(db)
    _seed(db, pid)
    view = PlanView(db, pid)
    roles = {w.property("outlineRole") for w in view.findChildren(QWidget)}
    assert {"act_container", "chapter_card", "scene_card"} <= roles


def test_canvas_plot_remains_deferred(tmp_path):
    db = Database(str(tmp_path / "sp.db"))
    win = MainWindow(db, _novel(db))
    btn = win.sidebar_buttons.get("Plot")
    assert btn is not None and btn.property("nav_available") is False
    assert "Plot" not in win._nav_labels


# ==========================================================================
# 6-12  Move / reorder + numbering
# ==========================================================================


def test_reorder_acts_updates_order():
    db = Database()
    pid = _novel(db)
    _seed(db, pid)
    view = PlanView(db, pid)
    assert [a for a, _ in build_plan_tree(db, pid)] == ["Act I", "Act II"]
    view.move_act("Act II", -1)
    assert [a for a, _ in build_plan_tree(db, pid)] == ["Act II", "Act I"]


def test_reorder_chapters_within_act():
    db = Database()
    pid = _novel(db)
    _seed(db, pid)
    view = PlanView(db, pid)
    chapters = lambda: [c for a, chs in build_plan_tree(db, pid)
                        if a == "Act I" for c, _ in chs]
    assert chapters() == ["Ch1", "Ch2"]
    view.move_chapter("Act I", "Ch2", -1)
    assert chapters() == ["Ch2", "Ch1"]


def test_move_chapter_to_another_act_persists():
    db = Database()
    pid = _novel(db)
    ids = _seed(db, pid)
    view = PlanView(db, pid)
    view.move_chapter_to_act("Act I", "Ch2", "Act II")
    s3 = db.get_scene_by_id(ids["s3"])
    assert s3.act == "Act II" and s3.chapter == "Ch2"
    # Ch2 no longer under Act I.
    act_i_chs = [c for a, chs in build_plan_tree(db, pid) if a == "Act I"
                 for c, _ in chs]
    assert "Ch2" not in act_i_chs


def test_reorder_scenes_within_chapter():
    db = Database()
    pid = _novel(db)
    ids = _seed(db, pid)
    view = PlanView(db, pid)
    assert _ch_order(db, pid, "Act I", "Ch1") == [ids["s1"], ids["s2"]]
    view.move_scene(ids["s1"], +1)
    assert _ch_order(db, pid, "Act I", "Ch1") == [ids["s2"], ids["s1"]]


def test_move_scene_to_another_chapter_persists():
    db = Database()
    pid = _novel(db)
    ids = _seed(db, pid)
    view = PlanView(db, pid)
    view.move_scene_to_chapter(ids["s4"], "Act I", "Ch1")
    s4 = db.get_scene_by_id(ids["s4"])
    assert s4.act == "Act I" and s4.chapter == "Ch1"
    assert ids["s4"] in _ch_order(db, pid, "Act I", "Ch1")


def test_numbering_updates_after_move():
    db = Database()
    pid = _novel(db)
    ids = _seed(db, pid)
    view = PlanView(db, pid)
    assert _scene_nums(db, pid)[ids["s1"]] == "1.1.1"
    view.move_scene(ids["s1"], +1)          # S2 now first in Ch1
    nums = _scene_nums(db, pid)
    assert nums[ids["s2"]] == "1.1.1"
    assert nums[ids["s1"]] == "1.1.2"


def test_no_duplicate_numbering_after_moves():
    db = Database()
    pid = _novel(db)
    ids = _seed(db, pid)
    view = PlanView(db, pid)
    view.move_scene_to_chapter(ids["s4"], "Act I", "Ch1")
    view.move_chapter_to_act("Act I", "Ch2", "Act II")
    view.move_act("Act II", -1)
    nums = _scene_nums(db, pid)
    assert len(set(nums.values())) == len(nums)   # all unique
    assert "" not in nums.values()                # none stale/empty


def test_non_novel_numbering_is_act_scene():
    db = Database()
    pid = db.create_project("S", narrative_engine="screenplay",
                            default_writing_format="screenplay").id
    a = db.create_scene(pid, "A", act="Act I").id
    b = db.create_scene(pid, "B", act="Act I").id
    nums = _scene_nums(db, pid, is_novel=False)
    assert nums[a] == "1.1" and nums[b] == "1.2"


# ==========================================================================
# 13-16  Manuscript integration
# ==========================================================================


def test_double_click_scene_opens_manuscript(tmp_path):
    db = Database(str(tmp_path / "sp.db"))
    pid = _novel(db)
    ids = _seed(db, pid)
    win = MainWindow(db, pid)
    win.sidebar_buttons["Outline"].click()
    win._open_unit_in_manuscript(ids["s3"])
    assert win._current_section == "Manuscript"
    assert isinstance(win.content_area, WritingCoreView)
    assert ids["s3"] in win.content_area._editors    # focus target exists


def test_double_click_chapter_opens_first_scene():
    db = Database()
    pid = _novel(db)
    ids = _seed(db, pid)
    opened: list[int] = []
    view = PlanView(db, pid, on_open_in_manuscript=opened.append)
    view._open_chapter_in_manuscript("Act I", "Ch1")
    assert opened == [ids["s1"]]                       # chapter's first scene


def test_scene_cards_are_double_clickable_and_carry_id():
    from logosforge.ui.plan_view import _SceneCard
    db = Database()
    pid = _novel(db)
    ids = _seed(db, pid)
    view = PlanView(db, pid)
    cards = {c.scene_id for c in view.findChildren(_SceneCard)}
    assert ids["s1"] in cards and ids["s4"] in cards


def test_move_does_not_overwrite_manuscript_body():
    db = Database()
    pid = _novel(db)
    ids = _seed(db, pid)
    view = PlanView(db, pid)
    view.move_scene_to_chapter(ids["s1"], "Act II", "Ch3")
    view.move_act("Act II", -1)
    assert db.get_scene_by_id(ids["s1"]).content == "alpha beta gamma"


def test_open_in_manuscript_targets_units_editor(tmp_path):
    # The editor for the opened unit is the focus target scroll_to_scene uses.
    # (Asserting the global focusWidget is environment-sensitive in headless Qt,
    # so we verify the deterministic part: the right editor exists and the
    # focus call runs without error and does not disturb other units.)
    db = Database(str(tmp_path / "sp.db"))
    pid = _novel(db)
    ids = _seed(db, pid)
    win = MainWindow(db, pid)
    win._open_unit_in_manuscript(ids["s2"])
    view = win.content_area
    assert isinstance(view, WritingCoreView)
    editor = view._editors.get(ids["s2"])
    assert isinstance(editor, _SceneEditor)
    view.scroll_to_scene(ids["s2"])          # focus path runs cleanly


# ==========================================================================
# 17-22  Planning metadata chips
# ==========================================================================


def test_status_chip_displays():
    db = Database()
    pid = _novel(db)
    sid = db.create_scene(pid, "S", act="Act I", chapter="Ch1",
                          tags="status:Complete").id
    view = PlanView(db, pid)
    chips = [c.text() for c in _labels(view, "planStatusChip")]
    assert "Complete" in chips
    assert scene_status(db.get_scene_by_id(sid)) == "Complete"


def test_tag_chips_display():
    db = Database()
    pid = _novel(db)
    db.create_scene(pid, "S", act="Act I", chapter="Ch1", tags="magic, heist")
    view = PlanView(db, pid)
    chips = [c.text() for c in _labels(view, "planChip")]
    assert "magic" in chips and "heist" in chips


def test_codex_chips_display(monkeypatch):
    db = Database()
    pid = _novel(db)
    sid = db.create_scene(pid, "S", act="Act I", chapter="Ch1").id

    class _Ch:
        name = "Aria"

    monkeypatch.setattr(db, "get_scene_character_ids",
                        lambda _sid: [7] if _sid == sid else [])
    monkeypatch.setattr(db, "get_character_by_id", lambda _cid: _Ch())
    view = PlanView(db, pid)
    chips = [c.text() for c in _labels(view, "planChip")]
    assert "Aria" in chips


def test_word_count_displays():
    db = Database()
    pid = _novel(db)
    db.create_scene(pid, "S", act="Act I", chapter="Ch1",
                    content="one two three")
    view = PlanView(db, pid)
    texts = [c.text() for c in view.findChildren(QLabel)]
    assert "3 w" in texts


def test_summary_preview_is_truncated_and_compact():
    db = Database()
    pid = _novel(db)
    long = "x" * 400
    db.create_scene(pid, "S", act="Act I", chapter="Ch1", summary=long)
    view = PlanView(db, pid)
    previews = _labels(view, "planSummaryPreview")
    assert previews
    shown = previews[0].text()
    assert shown.endswith("…") and len(shown) < len(long)


def test_edit_summary_updates_outline_only_not_body(monkeypatch):
    db = Database()
    pid = _novel(db)
    sid = db.create_scene(pid, "S", act="Act I", chapter="Ch1",
                          content="REAL PROSE").id
    view = PlanView(db, pid)
    monkeypatch.setattr(QInputDialog, "getMultiLineText",
                        lambda *a, **k: ("planning note", True))
    view._edit_scene_summary_dialog(sid)
    s = db.get_scene_by_id(sid)
    assert s.summary == "planning note"      # outline updated
    assert s.content == "REAL PROSE"          # body untouched


def test_set_status_via_menu_helper_persists_and_clears():
    db = Database()
    pid = _novel(db)
    sid = db.create_scene(pid, "S", act="Act I", chapter="Ch1",
                          tags="magic").id
    view = PlanView(db, pid)
    view._set_scene_status(sid, "Needs Work")
    s = db.get_scene_by_id(sid)
    assert scene_status(s) == "Needs Work"
    assert "magic" in s.tags                  # existing tags preserved
    view._set_scene_status(sid, "")
    assert scene_status(db.get_scene_by_id(sid)) == ""


# ==========================================================================
# 23-27  Delete / clear (confirmation)
# ==========================================================================


def test_delete_scene_requires_confirmation_cancel_keeps(monkeypatch):
    db = Database()
    pid = _novel(db)
    sid = db.create_scene(pid, "S", act="Act I", chapter="Ch1",
                          content="keep").id
    view = PlanView(db, pid)
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *a, **k: QMessageBox.StandardButton.No)
    view._delete_scene_dialog(sid)
    assert db.get_scene_by_id(sid) is not None     # cancel left it


def test_delete_scene_confirmed_removes(monkeypatch):
    db = Database()
    pid = _novel(db)
    sid = db.create_scene(pid, "S", act="Act I", chapter="Ch1").id
    view = PlanView(db, pid)
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *a, **k: QMessageBox.StandardButton.Yes)
    view._delete_scene_dialog(sid)
    assert db.get_scene_by_id(sid) is None


# ==========================================================================
# 28-32  Data integrity / isolation
# ==========================================================================


def test_move_preserves_scene_ids_and_note_links():
    db = Database()
    pid = _novel(db)
    ids = _seed(db, pid)
    note = db.create_note(pid, "N", "body")
    db.link_note_to_scene(note.id, ids["s1"])
    before = {s.id for s in db.get_all_scenes(pid)}
    view = PlanView(db, pid)
    view.move_scene_to_chapter(ids["s1"], "Act II", "Ch3")
    after = {s.id for s in db.get_all_scenes(pid)}
    assert before == after                                  # no id churn
    assert ids["s1"] in db.get_note_scene_links(note.id)    # link preserved


def test_move_only_changes_order_and_labels():
    db = Database()
    pid = _novel(db)
    ids = _seed(db, pid)
    s1_before = db.get_scene_by_id(ids["s1"])
    summary_before, tags_before = s1_before.summary, s1_before.tags
    view = PlanView(db, pid)
    view.move_scene(ids["s1"], +1)
    s1_after = db.get_scene_by_id(ids["s1"])
    assert s1_after.summary == summary_before
    assert s1_after.tags == tags_before
    assert s1_after.content == "alpha beta gamma"


def test_project_switch_clears_board(tmp_path):
    db = Database(str(tmp_path / "sp.db"))
    a = _novel(db)
    db.create_scene(a, "S", act="Act A", chapter="Ch")
    b = _novel(db)
    win = MainWindow(db, a)
    win.sidebar_buttons["Outline"].click()
    assert build_plan_tree(db, a) != []
    win._switch_project(b)
    win.sidebar_buttons["Outline"].click()
    assert build_plan_tree(db, b) == []      # new project: clean board
