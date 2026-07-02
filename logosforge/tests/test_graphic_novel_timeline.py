"""Tests for Slice 7 — Graphic Novel Timeline (reading-flow, page/panel)."""

import pytest

from logosforge.db import Database
from logosforge.graphic_novel_plot import (
    get_gn_panel_markers,
    get_gn_timeline_pages,
)


@pytest.fixture(autouse=True)
def _isolated_settings(monkeypatch, tmp_path):
    import logosforge.settings as settings
    settings._instance = None
    monkeypatch.setattr(settings, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(settings, "SETTINGS_FILE", tmp_path / "settings.json")
    yield
    settings._instance = None


def _gn(db):
    return db.create_project(
        "GN", narrative_engine="graphic_novel",
        default_writing_format="graphic_novel",
    )


def _view(db, project_id):
    from logosforge.ui.timeline_view import TimelineView
    return TimelineView(db, project_id)


def _marker_count(view):
    return sum(
        1 for i in range(view._gn_layout.count())
        if view._gn_layout.itemAt(i).widget()
        and view._gn_layout.itemAt(i).widget().__class__.__name__
        == "_GnTimelineMarker"
    )


def _panel_marker_count(view):
    return sum(
        1 for i in range(view._gn_layout.count())
        if view._gn_layout.itemAt(i).widget()
        and view._gn_layout.itemAt(i).widget().__class__.__name__
        == "_GnPanelMarker"
    )


# =========================================================================
# 1. Pages in reading order (§1, §2)
# =========================================================================

def test_timeline_pages_in_reading_order():
    db = Database()
    p = _gn(db)
    db.create_gn_page(p.id, summary="one")
    db.create_gn_page(p.id, summary="two")
    db.create_gn_page(p.id, summary="three")
    markers = get_gn_timeline_pages(db, p.id)
    assert [m["page_number"] for m in markers] == [1, 2, 3]
    assert [m["summary"] for m in markers] == ["one", "two", "three"]


def test_reading_order_follows_reorder():
    db = Database()
    p = _gn(db)
    a = db.create_gn_page(p.id, summary="alpha")
    b = db.create_gn_page(p.id, summary="beta")
    db.reorder_gn_pages(p.id, [b.id, a.id])
    markers = get_gn_timeline_pages(db, p.id)
    assert [m["summary"] for m in markers] == ["beta", "alpha"]


# =========================================================================
# 2. Page marker fields (§3)
# =========================================================================

def test_page_marker_fields():
    db = Database()
    p = _gn(db)
    i = db.create_gn_issue(p.id, title="Origins")
    page = db.create_gn_page(p.id, issue_id=i.id, summary="A body",
                             density_level="dense", reveal_type="cliffhanger",
                             emotional_beat="dread", splash_page=True)
    db.create_gn_panel(page.id, visual_motifs=["broken halo"],
                       characters_present=["Zampano"])
    db.create_gn_panel(page.id)
    m = get_gn_timeline_pages(db, p.id)[0]
    assert m["issue_title"] == "Origins"
    assert m["density"] == "dense"
    assert m["reveal_marker"] == "cliffhanger"
    assert m["splash_page"] is True
    assert m["panel_count"] == 2
    assert "broken halo" in m["motif_markers"]
    assert "Zampano" in m["characters"]


# =========================================================================
# 3. Panel-level expansion (§4)
# =========================================================================

def test_panel_markers_in_order():
    db = Database()
    p = _gn(db)
    page = db.create_gn_page(p.id)
    db.create_gn_panel(page.id, description="first", shot_type="wide",
                       dialogue_refs=["hi"])
    db.create_gn_panel(page.id, description="second", camera_angle="low_angle")
    markers = get_gn_panel_markers(db, page.id)
    assert [m["panel_number"] for m in markers] == [1, 2]
    assert markers[0]["shot_type"] == "wide"
    assert markers[0]["has_dialogue"] is True
    assert markers[1]["camera_angle"] == "low_angle"
    assert markers[1]["has_dialogue"] is False


def test_view_expands_panels_lazily():
    db = Database()
    p = _gn(db)
    page = db.create_gn_page(p.id)
    db.create_gn_panel(page.id, description="a")
    db.create_gn_panel(page.id, description="b")
    view = _view(db, p.id)
    assert view.is_page_expanded(page.id) is False
    assert _panel_marker_count(view) == 0   # not expanded by default (§12)
    view.toggle_page_expand(page.id)
    assert view.is_page_expanded(page.id) is True
    assert _panel_marker_count(view) == 2
    view.toggle_page_expand(page.id)
    assert _panel_marker_count(view) == 0


# =========================================================================
# 4. Page-turn / reveal pressure (§5)
# =========================================================================

def test_page_turn_marker_when_reveal_set():
    db = Database()
    p = _gn(db)
    db.create_gn_page(p.id, reveal_type="cliffhanger")  # sets up a turn
    db.create_gn_page(p.id)                              # reveal lands here
    markers = get_gn_timeline_pages(db, p.id)
    assert markers[0]["is_page_turn"] is True
    assert markers[0]["reveal_pressure"] is True
    assert markers[1]["is_page_turn"] is False


def test_no_page_turn_without_reveal():
    db = Database()
    p = _gn(db)
    db.create_gn_page(p.id)
    db.create_gn_page(p.id)
    markers = get_gn_timeline_pages(db, p.id)
    assert all(not m["is_page_turn"] for m in markers)


# =========================================================================
# 5. Motif chips (§7)
# =========================================================================

def test_motif_chips_from_panels():
    db = Database()
    p = _gn(db)
    page = db.create_gn_page(p.id)
    db.create_gn_panel(page.id, visual_motifs=["broken halo", "muddy cross"])
    m = get_gn_timeline_pages(db, p.id)[0]
    assert "broken halo" in m["motif_markers"]
    assert "muddy cross" in m["motif_markers"]


# =========================================================================
# 6. View rendering + edit + gating (§9, §11)
# =========================================================================

def test_view_renders_markers_and_hides_table():
    db = Database()
    p = _gn(db)
    db.create_gn_page(p.id)
    db.create_gn_page(p.id)
    view = _view(db, p.id)
    assert view.is_graphic_novel_mode() is True
    assert view._table.isHidden() is True       # scene table hidden for GN
    assert _marker_count(view) == 2


def test_edit_page_from_timeline_persists():
    db = Database()
    p = _gn(db)
    page = db.create_gn_page(p.id, summary="old")
    view = _view(db, p.id)
    view.gn_update_page(page.id, summary="new", density_level="dense",
                        reveal_type="page_turn", splash_page=True)
    pg = db.get_gn_page_by_id(page.id)
    assert pg.summary == "new"
    assert pg.density_level == "dense"
    assert pg.reveal_type == "page_turn"
    assert pg.splash_page is True


def test_edit_emits_data_changed():
    db = Database()
    p = _gn(db)
    page = db.create_gn_page(p.id)
    seen = []
    from logosforge.ui.timeline_view import TimelineView
    view = TimelineView(db, p.id, on_data_changed=lambda: seen.append(1))
    view.gn_update_page(page.id, summary="x")
    assert seen


def test_non_gn_timeline_unaffected():
    db = Database()
    p = db.create_project("Novel")
    db.create_scene(p.id, "Chapter 1", chapter="One", content="x")
    view = _view(db, p.id)
    assert view.is_graphic_novel_mode() is False
    assert view.get_gn_timeline_pages() == []
    assert view._table.isHidden() is False       # scene table still used


# =========================================================================
# 7. Refresh after external change + reload (§10, §13.7, §13.9)
# =========================================================================

def test_timeline_reflects_external_page_change():
    db = Database()
    p = _gn(db)
    page = db.create_gn_page(p.id, summary="old")
    view = _view(db, p.id)
    db.update_gn_page(page.id, summary="changed elsewhere")
    view.refresh()
    assert get_gn_timeline_pages(db, p.id)[0]["summary"] == "changed elsewhere"


def test_reload_preserves_timeline_data(tmp_path):
    path = str(tmp_path / "gn.db")
    db = Database(path)
    p = _gn(db)
    page = db.create_gn_page(p.id, summary="persisted", density_level="dense")
    db.create_gn_panel(page.id, description="panel text")
    pid, page_id = p.id, page.id

    db2 = Database(path)
    markers = get_gn_timeline_pages(db2, pid)
    assert len(markers) == 1
    assert markers[0]["summary"] == "persisted"
    assert markers[0]["density"] == "dense"
    assert markers[0]["panel_count"] == 1
    assert get_gn_panel_markers(db2, page_id)[0]["excerpt"] == "panel text"


# =========================================================================
# 8. Empty project safety
# =========================================================================

def test_empty_gn_timeline_safe():
    db = Database()
    p = _gn(db)
    assert get_gn_timeline_pages(db, p.id) == []
    view = _view(db, p.id)
    assert _marker_count(view) == 0
