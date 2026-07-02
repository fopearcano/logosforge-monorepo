"""Tests for Stage Script Plot and Timeline behavior (theatre-aware)."""

import pytest

from logosforge.db import Database
from logosforge.stage_script_plot import (
    get_act_progression,
    get_cue_markers,
    get_entrance_exit_markers,
    get_stage_plot_acts,
    get_stage_plot_blocks,
    get_stage_timeline,
)


@pytest.fixture(autouse=True)
def _isolated_settings(monkeypatch, tmp_path):
    import logosforge.settings as settings
    settings._instance = None
    monkeypatch.setattr(settings, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(settings, "SETTINGS_FILE", tmp_path / "settings.json")
    yield
    settings._instance = None


def _play(db):
    return db.create_project(
        "Play", narrative_engine="stage_script",
        default_writing_format="stage_script",
    )


def _build(db, project_id):
    h = db.create_character(project_id, "Hamlet")
    c = db.create_character(project_id, "Claudius")
    skull = db.create_psyke_entry(project_id, "Skull", entry_type="object")
    s1 = db.create_scene(
        project_id, "The Ghost", act="Act 1",
        scene_objective="learn the truth", dramatic_turn="vow revenge",
        performance_duration_minutes=10, character_ids=[h.id],
        offstage_events="the king sleeps",
    )
    s2 = db.create_scene(
        project_id, "The Play", act="Act 2",
        scene_objective="trap the king", character_ids=[h.id, c.id],
    )
    db.create_stage_entrance_exit(s1.id, character_id=h.id, type="entrance")
    db.create_stage_entrance_exit(s1.id, character_id=h.id, type="exit")
    db.create_stage_cue(s1.id, cue_type="light", cue_text="moonlight")
    db.create_stage_cue(s1.id, cue_type="sound", cue_text="owl")
    db.create_stage_business(
        s2.id, prop_psyke_entry_id=skull.id, character_id=h.id,
        stage_action="holds skull",
    )
    return h, c, skull, s1, s2


# =========================================================================
# 1. Plot grid — scenes grouped by acts (§1)
# =========================================================================

def test_plot_blocks_have_theatre_metadata():
    db = Database()
    p = _play(db)
    _build(db, p.id)
    blocks = get_stage_plot_blocks(db, p.id)
    b1 = blocks[0]
    assert b1["title"] == "The Ghost"
    assert b1["act"] == "Act 1"
    assert b1["scene_objective"] == "learn the truth"
    assert b1["dramatic_turn"] == "vow revenge"
    assert b1["characters_on_stage"] == ["Hamlet"]
    assert b1["entrance_exit_count"] == 2
    assert b1["estimated_duration"] == 10


def test_plot_block_important_props():
    db = Database()
    p = _play(db)
    _build(db, p.id)
    blocks = get_stage_plot_blocks(db, p.id)
    assert "Skull" in blocks[1]["important_props"]


def test_plot_grouped_by_acts():
    db = Database()
    p = _play(db)
    _build(db, p.id)
    acts = get_stage_plot_acts(db, p.id)
    assert [g["act"] for g in acts] == ["Act 1", "Act 2"]
    assert [s["title"] for s in acts[0]["scenes"]] == ["The Ghost"]
    assert [s["title"] for s in acts[1]["scenes"]] == ["The Play"]


# =========================================================================
# 2. Plot view integration (§1, §5)
# =========================================================================

def test_grid_view_stage_mode():
    from logosforge.ui.story_grid_view import StoryGridView
    db = Database()
    p = _play(db)
    view = StoryGridView(db, p.id)
    assert view.is_stage_script_mode() is True
    assert view._block_unit == "scene"
    assert view._block_number_label(1) == "Scene 1"


def test_grid_view_shows_scenes_grouped_by_acts():
    from logosforge.ui.story_grid_view import StoryGridView
    db = Database()
    p = _play(db)
    _build(db, p.id)
    view = StoryGridView(db, p.id)
    acts = view.get_stage_plot_acts()
    assert [g["act"] for g in acts] == ["Act 1", "Act 2"]
    assert len(view.get_stage_plot_blocks()) == 2


def test_grid_view_novel_no_stage_blocks():
    from logosforge.ui.story_grid_view import StoryGridView
    db = Database()
    p = db.create_project("Novel")
    view = StoryGridView(db, p.id)
    assert view.is_stage_script_mode() is False
    assert view.get_stage_plot_blocks() == []


# =========================================================================
# 3. Timeline (§2, §3, §4)
# =========================================================================

def test_timeline_rows():
    db = Database()
    p = _play(db)
    _build(db, p.id)
    rows = get_stage_timeline(db, p.id)
    assert [r["order"] for r in rows] == [1, 2]
    assert rows[0]["act"] == "Act 1"
    assert rows[0]["emotional_pressure"] == "turn"   # has dramatic_turn
    assert rows[1]["emotional_pressure"] == "pursuit"  # has objective only


def test_timeline_shows_entrances_exits():
    db = Database()
    p = _play(db)
    _build(db, p.id)
    row = get_stage_timeline(db, p.id)[0]
    assert row["entrance_exit_count"] == 2
    types = [e["type"] for e in row["entrances_exits"]]
    assert types == ["entrance", "exit"]
    assert all(e["character"] == "Hamlet" for e in row["entrances_exits"])


def test_timeline_cue_markers():
    db = Database()
    p = _play(db)
    _build(db, p.id)
    row = get_stage_timeline(db, p.id)[0]
    assert row["cue_count"] == 2
    assert {c["type"] for c in row["cues"]} == {"light", "sound"}


def test_timeline_offstage_events():
    db = Database()
    p = _play(db)
    _build(db, p.id)
    assert get_stage_timeline(db, p.id)[0]["offstage_events"] == "the king sleeps"


def test_act_progression():
    db = Database()
    p = _play(db)
    _build(db, p.id)
    assert get_act_progression(db, p.id) == ["Act 1", "Act 2"]


def test_timeline_view_integration():
    from logosforge.ui.timeline_view import TimelineView
    db = Database()
    p = _play(db)
    _build(db, p.id)
    view = TimelineView(db, p.id)
    assert view.is_stage_script_mode() is True
    rows = view.get_stage_timeline_rows()
    assert len(rows) == 2
    assert view.get_stage_act_progression() == ["Act 1", "Act 2"]


def test_timeline_view_novel_empty():
    from logosforge.ui.timeline_view import TimelineView
    db = Database()
    p = db.create_project("Novel")
    view = TimelineView(db, p.id)
    assert view.is_stage_script_mode() is False
    assert view.get_stage_timeline_rows() == []


# =========================================================================
# 4. Entrance/Exit + Cue markers (§3, §4)
# =========================================================================

def test_entrance_exit_markers_include_offstage():
    db = Database()
    p = _play(db)
    _h, _c, _s, s1, _s2 = _build(db, p.id)
    markers = get_entrance_exit_markers(db, p.id, s1.id)
    types = [m["type"] for m in markers]
    assert "entrance" in types and "exit" in types
    assert "offstage" in types  # offstage_events surfaced as a marker


def test_cue_markers_compact():
    db = Database()
    p = _play(db)
    _h, _c, _s, s1, _s2 = _build(db, p.id)
    markers = get_cue_markers(db, s1.id)
    assert [m["cue_type"] for m in markers] == ["light", "sound"]
    assert markers[0]["text"] == "moonlight"


def test_view_markers_accessors():
    from logosforge.ui.timeline_view import TimelineView
    db = Database()
    p = _play(db)
    _h, _c, _s, s1, _s2 = _build(db, p.id)
    view = TimelineView(db, p.id)
    assert len(view.get_stage_entrance_exit_markers(s1.id)) >= 2
    assert len(view.get_stage_cue_markers(s1.id)) == 2


# =========================================================================
# 5. Data updates when scene metadata changes (§5)
# =========================================================================

def test_data_updates_on_metadata_change():
    db = Database()
    p = _play(db)
    s = db.create_scene(p.id, "Scene", act="Act 1")
    blocks = get_stage_plot_blocks(db, p.id)
    assert blocks[0]["scene_objective"] == ""
    db.update_scene(s.id, "Scene", act="Act 1", scene_objective="win",
                    performance_duration_minutes=5)
    blocks = get_stage_plot_blocks(db, p.id)
    assert blocks[0]["scene_objective"] == "win"
    assert blocks[0]["estimated_duration"] == 5


def test_new_cue_appears_in_timeline():
    db = Database()
    p = _play(db)
    s = db.create_scene(p.id, "Scene", act="Act 1")
    assert get_stage_timeline(db, p.id)[0]["cue_count"] == 0
    db.create_stage_cue(s.id, cue_type="music", cue_text="fanfare")
    assert get_stage_timeline(db, p.id)[0]["cue_count"] == 1


def test_empty_project_safe():
    db = Database()
    p = _play(db)
    assert get_stage_plot_blocks(db, p.id) == []
    assert get_stage_timeline(db, p.id) == []
    assert get_act_progression(db, p.id) == []
