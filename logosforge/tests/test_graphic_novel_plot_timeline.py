"""Tests for Graphic Novel Plot and Timeline behavior (page/panel-aware)."""

import pytest

from logosforge.db import Database
from logosforge.graphic_novel_plot import (
    PACING_INDICATORS,
    classify_page_pacing,
    get_gn_plot_blocks,
    get_gn_timeline,
    get_page_turn_map,
    get_silence_action_pattern,
    page_rhythm,
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


def _build_story(db, project_id):
    seq = db.create_gn_sequence(
        project_id, title="Chase", issue="Issue 1", emotional_beat="dread",
    )
    pg1 = db.create_gn_page(project_id, sequence_id=seq.id, density_level="silent")
    pg2 = db.create_gn_page(
        project_id, sequence_id=seq.id, density_level="dense",
        reveal_type="cliffhanger",
    )
    pg3 = db.create_gn_page(
        project_id, sequence_id=seq.id, density_level="explosive",
        splash_page=True,
    )
    db.create_gn_panel(pg2.id, action="runs", visual_motifs=["rain"])
    db.create_gn_panel(pg2.id, action="leaps", visual_motifs=["rain"])
    return seq, pg1, pg2, pg3


# =========================================================================
# 1. Plot grid (§1)
# =========================================================================

def test_plot_blocks_by_sequence():
    db = Database()
    p = _gn(db)
    _build_story(db, p.id)
    blocks = get_gn_plot_blocks(db, p.id, unit="sequence")
    assert len(blocks) == 1
    b = blocks[0]
    assert b["type"] == "sequence"
    assert b["title"] == "Chase"
    assert b["group"] == "Issue 1"        # Act/Issue level
    assert b["page_count"] == 3
    assert b["density"] == "explosive"     # strongest across pages
    assert b["reveal_markers"] == 1
    assert b["emotional_beat"] == "dread"
    assert "rain" in b["motif_markers"]


def test_plot_blocks_by_page():
    db = Database()
    p = _gn(db)
    _build_story(db, p.id)
    blocks = get_gn_plot_blocks(db, p.id, unit="page")
    assert [b["type"] for b in blocks] == ["page", "page", "page"]
    assert blocks[0]["density"] == "silent"
    assert blocks[1]["reveal_marker"] == "cliffhanger"
    assert blocks[2]["splash_page"] is True
    assert "rain" in blocks[1]["motif_markers"]


def test_unassigned_pages_grouped():
    db = Database()
    p = _gn(db)
    db.create_gn_page(p.id)  # no sequence
    blocks = get_gn_plot_blocks(db, p.id, unit="sequence")
    assert any(b["id"] is None and b["page_count"] == 1 for b in blocks)


# =========================================================================
# 2. Plot grid view integration (§1, §5)
# =========================================================================

def test_grid_view_graphic_novel_mode():
    from logosforge.ui.story_grid_view import StoryGridView
    db = Database()
    p = _gn(db)
    view = StoryGridView(db, p.id)
    assert view.is_graphic_novel_mode() is True
    assert view._block_unit == "sequence"
    assert view._block_number_label(1) == "Seq 1"


def test_grid_view_shows_pages_sequences():
    from logosforge.ui.story_grid_view import StoryGridView
    db = Database()
    p = _gn(db)
    _build_story(db, p.id)
    view = StoryGridView(db, p.id)
    seq_blocks = view.get_gn_plot_blocks()
    assert seq_blocks and seq_blocks[0]["title"] == "Chase"
    page_blocks = view.get_gn_plot_blocks(unit="page")
    assert len(page_blocks) == 3


def test_grid_view_novel_no_gn_blocks():
    from logosforge.ui.story_grid_view import StoryGridView
    db = Database()
    p = db.create_project("Novel")
    view = StoryGridView(db, p.id)
    assert view.is_graphic_novel_mode() is False
    assert view.get_gn_plot_blocks() == []


# =========================================================================
# 3. Timeline (§2)
# =========================================================================

def test_timeline_rows_reading_flow():
    db = Database()
    p = _gn(db)
    _build_story(db, p.id)
    rows = get_gn_timeline(db, p.id)
    assert [r["page_number"] for r in rows] == [1, 2, 3]
    assert rows[0]["rhythm"] == "held"      # silent
    assert rows[1]["rhythm"] == "fast"      # dense
    assert rows[2]["rhythm"] == "chaotic"   # explosive
    assert rows[1]["reveal_timing"] == "cliffhanger"
    assert rows[1]["action_density"] == 1.0  # both panels have action


def test_silence_action_alternation():
    db = Database()
    p = _gn(db)
    _build_story(db, p.id)
    pattern = get_silence_action_pattern(db, p.id)
    assert pattern == ["silence", "action", "action"]


def test_timeline_view_integration():
    from logosforge.ui.timeline_view import TimelineView
    db = Database()
    p = _gn(db)
    _build_story(db, p.id)
    view = TimelineView(db, p.id)
    assert view.is_graphic_novel_mode() is True
    rows = view.get_gn_timeline_rows()
    assert len(rows) == 3
    assert view.get_gn_silence_action_pattern() == ["silence", "action", "action"]


def test_timeline_view_novel_empty():
    from logosforge.ui.timeline_view import TimelineView
    db = Database()
    p = db.create_project("Novel")
    view = TimelineView(db, p.id)
    assert view.is_graphic_novel_mode() is False
    assert view.get_gn_timeline_rows() == []


# =========================================================================
# 4. Pacing logic (§4)
# =========================================================================

def test_pacing_indicators():
    db = Database()
    p = _gn(db)
    quiet = db.create_gn_page(p.id, density_level="silent")
    dense = db.create_gn_page(p.id, density_level="dense")
    explosive = db.create_gn_page(p.id, density_level="explosive")
    reveal = db.create_gn_page(p.id, density_level="medium", reveal_type="turn")
    expo = db.create_gn_page(p.id, density_level="medium")
    db.create_gn_panel(expo.id, dialogue_refs=["a", "b"])  # heavy text, 1 panel

    assert classify_page_pacing(db, db.get_gn_page_by_id(quiet.id)) == "quiet"
    assert classify_page_pacing(db, db.get_gn_page_by_id(dense.id)) == "dense"
    assert classify_page_pacing(db, db.get_gn_page_by_id(explosive.id)) == "explosive"
    assert classify_page_pacing(db, db.get_gn_page_by_id(reveal.id)) == "cinematic"
    assert classify_page_pacing(db, db.get_gn_page_by_id(expo.id)) == "exposition-heavy"


def test_all_pacing_values_valid():
    db = Database()
    p = _gn(db)
    _build_story(db, p.id)
    for row in get_gn_timeline(db, p.id):
        assert row["pacing"] in PACING_INDICATORS


def test_page_rhythm_mapping():
    assert page_rhythm("silent") == "held"
    assert page_rhythm("explosive") == "chaotic"
    assert page_rhythm("medium") == "steady"


# =========================================================================
# 5. Page-turn logic (§3) + persistence (§5)
# =========================================================================

def test_page_turn_pairs():
    db = Database()
    p = _gn(db)
    _build_story(db, p.id)
    turns = get_page_turn_map(db, p.id)
    assert len(turns) == 1
    t = turns[0]
    assert t["setup_page_number"] == 2
    assert t["reveal_page_number"] == 3
    assert t["reveal_type"] == "cliffhanger"


def test_page_turn_markers_persist(tmp_path):
    path = str(tmp_path / "gn.db")
    db = Database(path)
    p = _gn(db)
    seq = db.create_gn_sequence(p.id, title="S")
    db.create_gn_page(p.id, sequence_id=seq.id, reveal_type="cliffhanger")
    db.create_gn_page(p.id, sequence_id=seq.id)
    pid = p.id

    # Reload from disk — markers survive.
    db2 = Database(path)
    turns = get_page_turn_map(db2, pid)
    assert len(turns) == 1
    assert turns[0]["reveal_type"] == "cliffhanger"


def test_timeline_view_page_turn_map():
    from logosforge.ui.timeline_view import TimelineView
    db = Database()
    p = _gn(db)
    _build_story(db, p.id)
    view = TimelineView(db, p.id)
    turns = view.get_gn_page_turn_map()
    assert len(turns) == 1
    assert turns[0]["reveal_type"] == "cliffhanger"


def test_empty_project_safe():
    db = Database()
    p = _gn(db)
    assert get_gn_plot_blocks(db, p.id) == []
    assert get_gn_timeline(db, p.id) == []
    assert get_page_turn_map(db, p.id) == []
    assert get_silence_action_pattern(db, p.id) == []
