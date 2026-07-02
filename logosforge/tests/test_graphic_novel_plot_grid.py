"""Tests for Slice 6 — Graphic Novel Plot grid (page-aware planning)."""

import pytest

from logosforge.db import Database
from logosforge.graphic_novel_plot import (
    GN_PLOT_FILTERS,
    filter_gn_plot_pages,
    get_gn_plot_pages_grouped,
    page_rhythm_indicators,
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
    from logosforge.ui.story_grid_view import StoryGridView
    return StoryGridView(db, project_id)


# =========================================================================
# 1. Page blocks + fields (§2, §3)
# =========================================================================

def test_page_block_has_all_fields():
    db = Database()
    p = _gn(db)
    page = db.create_gn_page(p.id, summary="A body turns up",
                             density_level="dense", reveal_type="cliffhanger",
                             emotional_beat="dread", splash_page=True)
    db.create_gn_panel(page.id, action="runs", characters_present=["Zampano"],
                       visual_motifs=["broken halo"])
    db.create_gn_panel(page.id)
    block = get_gn_plot_pages_grouped(db, p.id)[0]["pages"][0]
    assert block["page_number"] == 1
    assert block["summary"] == "A body turns up"
    assert block["density"] == "dense"
    assert block["reveal_marker"] == "cliffhanger"
    assert block["splash_page"] is True
    assert block["panel_count"] == 2
    assert block["emotional_beat"] == "dread"
    assert "broken halo" in block["motif_markers"]
    assert "Zampano" in block["characters"]


def test_page_rhythm_indicators():
    db = Database()
    p = _gn(db)
    page = db.create_gn_page(p.id, density_level="dense",
                             reveal_type="page_turn", splash_page=True)
    db.create_gn_panel(page.id, action="leaps",
                       dialogue_refs=["a", "b", "c", "d"])
    tags = page_rhythm_indicators(db, db.get_gn_page_by_id(page.id))
    assert "dense" in tags
    assert "action" in tags
    assert "reveal" in tags
    assert "splash" in tags
    assert "dialogue-heavy" in tags


def test_quiet_page_rhythm():
    db = Database()
    p = _gn(db)
    page = db.create_gn_page(p.id, density_level="silent")
    db.create_gn_panel(page.id, description="still water")
    tags = page_rhythm_indicators(db, db.get_gn_page_by_id(page.id))
    assert tags == ["quiet"]


# =========================================================================
# 2. Grouping by Issue / Sequence / flat (§1, §2)
# =========================================================================

def test_pages_grouped_by_issue():
    db = Database()
    p = _gn(db)
    a = db.create_gn_issue(p.id, title="Origins")
    b = db.create_gn_issue(p.id, title="Fallout")
    db.create_gn_page(p.id, issue_id=a.id)
    db.create_gn_page(p.id, issue_id=a.id)
    db.create_gn_page(p.id, issue_id=b.id)
    groups = get_gn_plot_pages_grouped(db, p.id)
    assert [g["group_title"] for g in groups] == ["Origins", "Fallout"]
    assert [g["group_kind"] for g in groups] == ["issue", "issue"]
    assert [len(g["pages"]) for g in groups] == [2, 1]


def test_unassigned_pages_grouped_separately():
    db = Database()
    p = _gn(db)
    a = db.create_gn_issue(p.id, title="Origins")
    db.create_gn_page(p.id, issue_id=a.id)
    db.create_gn_page(p.id)  # unassigned
    groups = get_gn_plot_pages_grouped(db, p.id)
    assert groups[-1]["group_title"] == "(unassigned)"
    assert len(groups[-1]["pages"]) == 1


def test_fallback_to_sequence_grouping():
    db = Database()
    p = _gn(db)
    seq = db.create_gn_sequence(p.id, title="Opening")
    db.create_gn_page(p.id, sequence_id=seq.id)
    groups = get_gn_plot_pages_grouped(db, p.id)
    assert groups[0]["group_kind"] == "sequence"
    assert groups[0]["group_title"] == "Opening"


def test_flat_grouping_without_issues_or_sequences():
    db = Database()
    p = _gn(db)
    db.create_gn_page(p.id)
    db.create_gn_page(p.id)
    groups = get_gn_plot_pages_grouped(db, p.id)
    assert len(groups) == 1
    assert groups[0]["group_kind"] == "none"
    assert len(groups[0]["pages"]) == 2


# =========================================================================
# 3. Filters (§8)
# =========================================================================

def test_filter_constants():
    for f in ("all", "splash", "reveal", "dense", "motifs", "missing_summary"):
        assert f in GN_PLOT_FILTERS


def test_filter_splash_and_missing_summary():
    db = Database()
    p = _gn(db)
    db.create_gn_page(p.id, summary="has summary", splash_page=True)
    db.create_gn_page(p.id, summary="")  # missing summary, not splash
    blocks = get_gn_plot_pages_grouped(db, p.id)[0]["pages"]
    assert [b["page_number"] for b in filter_gn_plot_pages(blocks, "splash")] == [1]
    assert [b["page_number"] for b in
            filter_gn_plot_pages(blocks, "missing_summary")] == [2]


def test_grouped_filter_drops_empty_groups():
    db = Database()
    p = _gn(db)
    a = db.create_gn_issue(p.id, title="A")
    b = db.create_gn_issue(p.id, title="B")
    db.create_gn_page(p.id, issue_id=a.id, splash_page=True)
    db.create_gn_page(p.id, issue_id=b.id)  # not splash
    groups = get_gn_plot_pages_grouped(db, p.id, "splash")
    assert [g["group_title"] for g in groups] == ["A"]


# =========================================================================
# 4. StoryGridView rendering + accessors (§2, §9)
# =========================================================================

def test_view_renders_page_cards_grouped():
    db = Database()
    p = _gn(db)
    a = db.create_gn_issue(p.id, title="Origins")
    db.create_gn_page(p.id, issue_id=a.id)
    db.create_gn_page(p.id, issue_id=a.id)
    view = _view(db, p.id)
    assert view.is_graphic_novel_mode() is True
    assert len(view._columns) == 1
    assert view._columns[0].card_count() == 2


def test_view_grouped_accessor():
    db = Database()
    p = _gn(db)
    db.create_gn_page(p.id)
    view = _view(db, p.id)
    groups = view.get_gn_plot_pages_grouped()
    assert len(groups) == 1
    assert len(groups[0]["pages"]) == 1


def test_non_gn_view_unaffected():
    db = Database()
    p = db.create_project("Novel")
    db.create_scene(p.id, "Chapter 1", act="Act 1", content="x")
    view = _view(db, p.id)
    assert view.is_graphic_novel_mode() is False
    assert view.get_gn_plot_pages_grouped() == []
    # Scene grid still renders (existing behavior).
    assert len(view._columns) >= 1


# =========================================================================
# 5. Edit page from Plot persists (§4, §10)
# =========================================================================

def test_edit_summary_from_plot_persists():
    db = Database()
    p = _gn(db)
    page = db.create_gn_page(p.id, summary="old")
    view = _view(db, p.id)
    view.gn_update_page(page.id, summary="new summary")
    assert db.get_gn_page_by_id(page.id).summary == "new summary"


def test_edit_density_reveal_splash_persists():
    db = Database()
    p = _gn(db)
    page = db.create_gn_page(p.id)
    view = _view(db, p.id)
    view.gn_update_page(page.id, density_level="dense",
                        reveal_type="cliffhanger", splash_page=True)
    pg = db.get_gn_page_by_id(page.id)
    assert pg.density_level == "dense"
    assert pg.reveal_type == "cliffhanger"
    assert pg.splash_page is True


def test_edit_emits_data_changed():
    db = Database()
    p = _gn(db)
    page = db.create_gn_page(p.id)
    seen = []
    from logosforge.ui.story_grid_view import StoryGridView
    view = StoryGridView(db, p.id, on_data_changed=lambda: seen.append(1))
    view.gn_update_page(page.id, summary="x")
    assert seen


# =========================================================================
# 6. Reorder pages from Plot (§5)
# =========================================================================

def test_reorder_pages_from_plot():
    db = Database()
    p = _gn(db)
    p1 = db.create_gn_page(p.id)
    p2 = db.create_gn_page(p.id)
    p3 = db.create_gn_page(p.id)
    view = _view(db, p.id)
    view.gn_move_page(p3.id, -1)
    assert [pg.id for pg in db.get_gn_pages(p.id)] == [p1.id, p3.id, p2.id]
    assert [pg.page_number for pg in db.get_gn_pages(p.id)] == [1, 2, 3]


def test_reorder_at_edge_is_noop():
    db = Database()
    p = _gn(db)
    p1 = db.create_gn_page(p.id)
    p2 = db.create_gn_page(p.id)
    view = _view(db, p.id)
    view.gn_move_page(p1.id, -1)  # already first
    assert [pg.id for pg in db.get_gn_pages(p.id)] == [p1.id, p2.id]


# =========================================================================
# 7. Data consistency — Plot reflects Pages-view changes (§10)
# =========================================================================

def test_plot_reflects_pages_view_change():
    db = Database()
    p = _gn(db)
    page = db.create_gn_page(p.id, summary="old")
    view = _view(db, p.id)
    # Simulate an edit made elsewhere (Pages view / canvas use the same db).
    db.update_gn_page(page.id, summary="changed elsewhere")
    view.refresh()
    block = view.get_gn_plot_pages_grouped()[0]["pages"][0]
    assert block["summary"] == "changed elsewhere"


# =========================================================================
# 8. Old sequence-block accessor still works (§11.9)
# =========================================================================

def test_legacy_sequence_blocks_still_work():
    db = Database()
    p = _gn(db)
    seq = db.create_gn_sequence(p.id, title="Opening")
    db.create_gn_page(p.id, sequence_id=seq.id)
    view = _view(db, p.id)
    blocks = view.get_gn_plot_blocks()  # default sequence unit
    assert any(b["title"] == "Opening" for b in blocks)
    page_blocks = view.get_gn_plot_blocks(unit="page")
    assert page_blocks and page_blocks[0]["type"] == "page"
