"""Tests for Stage Script-aware Assistant: review checks + context."""

import pytest

from logosforge.db import Database
from logosforge.narrative_engines import STAGE_SCRIPT_ENGINE
from logosforge.psyke_theatre import set_theatre_memory
from logosforge.stage_script_plot import build_stage_script_context
from logosforge.stage_script_review import (
    StageScriptCheck,
    review_stage_script,
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


def _types(checks):
    return {c.check_type for c in checks}


# =========================================================================
# 1. Engine priorities + review checks reach the Assistant (§1)
# =========================================================================

def test_engine_priorities_theatrical():
    for pr in ("playable conflict", "actor motivation", "spoken pressure",
               "subtext", "stage blocking", "prop continuity",
               "audience visibility", "scene objective"):
        assert pr in STAGE_SCRIPT_ENGINE.assistant_priorities


def test_engine_context_block_reaches_format():
    block = STAGE_SCRIPT_ENGINE.format_context_block()
    assert "[Narrative Engine: Stage Script]" in block
    assert "playable conflict" in block


# =========================================================================
# 2. Review checks (§2, §4)
# =========================================================================

def test_playable_objective_check():
    db = Database()
    p = _play(db)
    db.create_scene(p.id, "Talk", act="Act 1", content="They chat.")
    checks = review_stage_script(db, p.id)
    assert "playable_objective" in _types(checks)


def test_objective_present_passes():
    db = Database()
    p = _play(db)
    db.create_scene(p.id, "Talk", act="Act 1", content="x",
                    scene_objective="win the argument", dramatic_turn="loses")
    assert "playable_objective" not in _types(review_stage_script(db, p.id))


def test_stageable_conflict_check():
    db = Database()
    p = _play(db)
    db.create_scene(p.id, "Argue", act="Act 1", content="x",
                    conflict="power struggle", scene_objective="dominate")
    # conflict but no blocking/physical/entrances → not playable
    assert "stageable_conflict" in _types(review_stage_script(db, p.id))


def test_stageable_conflict_passes_with_blocking():
    db = Database()
    p = _play(db)
    db.create_scene(p.id, "Argue", act="Act 1", content="x",
                    conflict="power struggle", scene_objective="dominate",
                    blocking_notes="circles the table")
    assert "stageable_conflict" not in _types(review_stage_script(db, p.id))


def test_unmotivated_exit_check():
    db = Database()
    p = _play(db)
    c = db.create_character(p.id, "Hamlet")
    s = db.create_scene(p.id, "Scene", act="Act 1", content="x",
                        scene_objective="o", dramatic_turn="t")
    db.create_stage_entrance_exit(s.id, character_id=c.id, type="exit")
    assert "motivated_exit" in _types(review_stage_script(db, p.id))


def test_motivated_exit_passes():
    db = Database()
    p = _play(db)
    c = db.create_character(p.id, "Hamlet")
    s = db.create_scene(p.id, "Scene", act="Act 1", content="x",
                        scene_objective="o", dramatic_turn="t")
    db.create_stage_entrance_exit(s.id, character_id=c.id, type="exit",
                                  cue_text="hears the bell")
    assert "motivated_exit" not in _types(review_stage_script(db, p.id))


def test_prop_continuity_check():
    db = Database()
    p = _play(db)
    skull = db.create_psyke_entry(p.id, "Skull", entry_type="object")
    s = db.create_scene(p.id, "Scene", act="Act 1", content="x",
                        scene_objective="o", dramatic_turn="t")
    db.create_stage_business(s.id, prop_psyke_entry_id=skull.id,
                             stage_action="lifts")  # no continuity note
    assert "prop_continuity" in _types(review_stage_script(db, p.id))


def test_audience_visibility_check():
    db = Database()
    p = _play(db)
    db.create_scene(p.id, "Murder", act="Act 1", content="x",
                    scene_objective="kill", dramatic_turn="the deed",
                    audience_visibility_notes="the killing is hidden behind a screen")
    assert "audience_visibility" in _types(review_stage_script(db, p.id))


def test_scene_turn_check():
    db = Database()
    p = _play(db)
    db.create_scene(p.id, "Flat", act="Act 1", content="x",
                    scene_objective="o")  # no dramatic_turn
    assert "scene_turn" in _types(review_stage_script(db, p.id))


def test_act_break_pressure_check():
    db = Database()
    p = _play(db)
    # Act 1 ends on a scene with no turn → weak act break.
    db.create_scene(p.id, "A1S1", act="Act 1", content="x",
                    scene_objective="o", dramatic_turn="t")
    db.create_scene(p.id, "A1S2", act="Act 1", content="x",
                    scene_objective="o")  # last of Act 1, no turn
    db.create_scene(p.id, "A2S1", act="Act 2", content="x",
                    scene_objective="o", dramatic_turn="t")
    checks = review_stage_script(db, p.id)
    assert "act_break_pressure" in _types(checks)


def test_checks_typed_and_empty_safe():
    db = Database()
    p = _play(db)
    assert review_stage_script(db, p.id) == []
    db.create_scene(p.id, "Flat", act="Act 1", content="x")
    assert all(isinstance(c, StageScriptCheck) for c in review_stage_script(db, p.id))


# =========================================================================
# 3. Context builder (§3)
# =========================================================================

def test_context_includes_stage_facets():
    db = Database()
    p = _play(db)
    c = db.create_character(p.id, "Hamlet")
    hp = db.create_psyke_entry(p.id, "Hamlet", entry_type="character")
    set_theatre_memory(db, hp.id, offstage_knowledge="the king is guilty")
    skull = db.create_psyke_entry(p.id, "Skull", entry_type="object")
    s = db.create_scene(
        p.id, "The Closet", act="Act 3", scene_objective="confront mother",
        blocking_notes="behind the arras", subtext_notes="grief as rage",
        offstage_events="Polonius listens", character_ids=[c.id],
    )
    db.create_stage_entrance_exit(s.id, character_id=c.id, type="entrance")
    db.create_stage_business(s.id, prop_psyke_entry_id=skull.id, character_id=c.id,
                             stage_action="draws")
    ctx = build_stage_script_context(db, p.id, s.id)
    assert "[Stage Script Context]" in ctx
    assert "Objective: confront mother" in ctx
    assert "Blocking: behind the arras" in ctx
    assert "Entrances/Exits" in ctx and "Hamlet entrance" in ctx
    assert "Props: Skull" in ctx
    assert "Subtext: grief as rage" in ctx
    assert "Offstage: Polonius listens" in ctx
    assert "Offstage knowledge" in ctx and "the king is guilty" in ctx


def test_context_with_stage_layout():
    db = Database()
    p = _play(db)
    place = db.create_place(p.id, "Throne Room")
    pp = db.create_psyke_entry(p.id, "Throne Room", entry_type="place")
    set_theatre_memory(db, pp.id, stage_layout="raised dais, two doors")
    s = db.create_scene(p.id, "Court", act="Act 1", scene_objective="petition",
                        place_ids=[place.id])
    ctx = build_stage_script_context(db, p.id, s.id)
    assert "Stage layout" in ctx and "raised dais" in ctx


def test_context_empty_project():
    db = Database()
    p = _play(db)
    assert build_stage_script_context(db, p.id) == ""


# =========================================================================
# 4. Assistant integration (§6)
# =========================================================================

def test_assistant_context_for_stage_project():
    from logosforge.ui.assistant_view import AssistantPanel
    db = Database()
    p = _play(db)
    db.create_scene(p.id, "Scene", content="x", scene_objective="win",
                    blocking_notes="paces")
    panel = AssistantPanel(db, p.id)
    structural = panel._build_context()[8]
    assert "[Stage Script Context]" in structural
    assert "playable conflict" in structural  # engine priority in format block


def test_assistant_context_not_stage_for_novel():
    from logosforge.ui.assistant_view import AssistantPanel
    db = Database()
    p = db.create_project("Novel")
    db.create_scene(p.id, "Chapter 1", content="x")
    panel = AssistantPanel(db, p.id)
    assert "[Stage Script Context]" not in panel._build_context()[8]
