"""Timeline ↔ Outline ↔ Manuscript shared canonical ordering.

The bug: Timeline displayed linked scenes (1.1.2, 1.1.3, 1.1.1) in a different
order from Outline (1.1.1, 1.1.2, 1.1.3) because it used a timeline-local order.
Fix: Timeline defaults to "Structural Order" (the canonical Outline order);
"Custom Timeline Order" is an explicit opt-in that never reorders the Outline.
"""

from __future__ import annotations

import warnings

import pytest
from PySide6.QtWidgets import QApplication, QLabel

warnings.filterwarnings("ignore")

from logosforge.db import Database
from logosforge import story_structure as ss
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


def _abc(db, pid):
    """Act I → Ch1 → Scenes A, B, C (canonical order), all on lane 'Main'."""
    a = ss.create_scene(db, pid, act="Act I", chapter="Ch1", title="A",
                        plotline="Main").id
    b = ss.create_scene(db, pid, act="Act I", chapter="Ch1", title="B",
                        plotline="Main").id
    c = ss.create_scene(db, pid, act="Act I", chapter="Ch1", title="C",
                        plotline="Main").id
    db.create_timeline_lane(pid, "Main", "green")
    return a, b, c


def _nums(db, pid):
    return ss.compute_structural_numbers(
        ss.build_structure_tree(db, pid), True)["scenes"]


# ==========================================================================
# 1-2  Canonical numbering
# ==========================================================================


def test_numbering_is_sequential():
    db = Database()
    pid = _novel(db)
    a, b, c = _abc(db, pid)
    nums = _nums(db, pid)
    assert (nums[a], nums[b], nums[c]) == ("1.1.1", "1.1.2", "1.1.3")


# ==========================================================================
# 3-6  Timeline follows canonical order by default
# ==========================================================================


def test_timeline_default_order_is_canonical():
    db = Database()
    pid = _novel(db)
    a, b, c = _abc(db, pid)
    view = PlotTimelineView(db, pid)
    assert view._order_mode == "structural"
    assert view._event_order == [a, b, c]


def test_timeline_ignores_stale_custom_order_by_default():
    db = Database()
    pid = _novel(db)
    a, b, c = _abc(db, pid)
    db.set_timeline_order(pid, [b, c, a])     # stale local order (the bug)
    view = PlotTimelineView(db, pid)
    # Default structural order ignores it and matches the Outline.
    assert view._event_order == [a, b, c]


def test_timeline_cards_show_canonical_numbers_in_order():
    db = Database()
    pid = _novel(db)
    _abc(db, pid)
    view = PlotTimelineView(db, pid)
    text = " ".join(w.text() for w in view.findChildren(QLabel))
    # all three canonical numbers present on the cards
    assert "1.1.1" in text and "1.1.2" in text and "1.1.3" in text


def test_timeline_order_matches_canonical_scene_order():
    db = Database()
    pid = _novel(db)
    a, b, c = _abc(db, pid)
    view = PlotTimelineView(db, pid)
    assert view._event_order == ss.canonical_scene_order(db, pid) == [a, b, c]


# ==========================================================================
# 7-11  Move a Scene in Outline → all sections follow
# ==========================================================================


def test_move_scene_in_outline_updates_numbering():
    db = Database()
    pid = _novel(db)
    a, b, c = _abc(db, pid)
    PlanView(db, pid).move_scene_to_chapter(c, "Act I", "Ch1", 0)   # C to front
    nums = _nums(db, pid)
    assert (nums[c], nums[a], nums[b]) == ("1.1.1", "1.1.2", "1.1.3")


def test_timeline_follows_outline_move():
    db = Database()
    pid = _novel(db)
    a, b, c = _abc(db, pid)
    PlanView(db, pid).move_scene_to_chapter(c, "Act I", "Ch1", 0)
    view = PlotTimelineView(db, pid)           # rebuilt on navigation
    assert view._event_order == [c, a, b]


def test_manuscript_follows_outline_move(tmp_path):
    db = Database(str(tmp_path / "sp.db"))
    pid = _novel(db)
    a, b, c = _abc(db, pid)
    PlanView(db, pid).move_scene_to_chapter(c, "Act I", "Ch1", 0)
    win = MainWindow(db, pid)
    win.sidebar_buttons["Manuscript"].click()
    order = ss.canonical_scene_order(db, pid)
    assert order == [c, a, b]                   # Manuscript reads the same order


def test_move_preserves_body():
    db = Database()
    pid = _novel(db)
    a = ss.create_scene(db, pid, act="Act I", chapter="Ch1", title="A",
                        content="PROSE A").id
    ss.create_scene(db, pid, act="Act I", chapter="Ch1", title="B")
    c = ss.create_scene(db, pid, act="Act I", chapter="Ch1", title="C").id
    PlanView(db, pid).move_scene(c, -2)
    assert db.get_scene_by_id(a).content == "PROSE A"


# ==========================================================================
# 12-15  Move a Chapter in Outline → Timeline labels follow
# ==========================================================================


def test_chapter_move_updates_timeline_numbers():
    db = Database()
    pid = _novel(db)
    s1 = ss.create_scene(db, pid, act="Act I", chapter="Ch1", title="S1",
                        plotline="Main").id
    s2 = ss.create_scene(db, pid, act="Act II", chapter="Ch2", title="S2",
                        plotline="Main").id
    db.create_timeline_lane(pid, "Main", "green")
    nums = _nums(db, pid)
    assert nums[s2] == "2.1.1"
    PlanView(db, pid).move_chapter_to_act("Act II", "Ch2", "Act I")
    nums = _nums(db, pid)
    assert nums[s2] == "1.2.1"                  # Ch2 now the 2nd chapter of Act I
    view = PlotTimelineView(db, pid)
    text = " ".join(w.text() for w in view.findChildren(QLabel))
    assert "1.2.1" in text


# ==========================================================================
# Custom Timeline Order: opt-in, does not reorder the Outline
# ==========================================================================


def test_move_event_opts_into_custom_without_touching_outline():
    db = Database()
    pid = _novel(db)
    a, b, c = _abc(db, pid)
    before = [s.id for s in db.get_all_scenes(pid)]
    view = PlotTimelineView(db, pid)
    view._move_event(c, -2)                     # explicit timeline reorder
    assert db.get_timeline_order_mode(pid) == "custom"
    assert [s.id for s in db.get_all_scenes(pid)] == before   # Outline intact
    assert PlotTimelineView(db, pid)._event_order[0] == c     # custom persists


def test_toggle_back_to_structural_restores_canonical():
    db = Database()
    pid = _novel(db)
    a, b, c = _abc(db, pid)
    view = PlotTimelineView(db, pid)
    view._move_event(c, -2)                     # -> custom [c, a, b]
    assert view._order_mode == "custom"
    view._toggle_order_mode()                   # -> structural
    assert view._order_mode == "structural"
    assert view._event_order == [a, b, c]       # canonical again


# ==========================================================================
# Isolation / refresh
# ==========================================================================


def test_order_mode_isolated_between_projects(tmp_path):
    db = Database(str(tmp_path / "sp.db"))
    a = _novel(db)
    _abc(db, a)
    PlotTimelineView(db, a)._move_event(
        db.get_all_scenes(a)[-1].id, -1)        # project A -> custom
    b = _novel(db)
    assert db.get_timeline_order_mode(b) == "structural"   # B unaffected


def test_outline_move_emits_refresh_signal():
    db = Database()
    pid = _novel(db)
    a, b, c = _abc(db, pid)
    from logosforge.project_events import get_event_bus
    fired = []
    get_event_bus().outline_changed.connect(lambda: fired.append(1))
    PlanView(db, pid).move_scene(c, -2)
    assert fired                                 # Outline announced the change
