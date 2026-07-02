"""Screenplay Mode — Phase 1 acceptance suite.

A consolidated, cross-cutting check that the Phase 1 foundation holds end to end:
screenplay primary unit = Scene, the block taxonomy + plain-text compatibility
adapter, Fountain serialization (per element + full project in canonical scene
order, body-only — never Outline summaries or Timeline data), Outline/Manuscript
separation, Assistant/Logos screenplay context, and deterministic validation.

Builds on the existing Phase 10A/10B/10G implementation — this file asserts the
Phase 1 *requirements* against those public APIs (no new production code).
"""

from __future__ import annotations

import warnings

import pytest
from PySide6.QtWidgets import QApplication

warnings.filterwarnings("ignore")

from logosforge.db import Database
from logosforge import story_structure as ss
from logosforge import screenplay as sp
from logosforge.screenplay_blocks import (
    ScreenplayBlock,
    parse_screenplay_text,
    serialize_blocks,
)
from logosforge.screenplay_fountain import (
    FountainExportOptions,
    serialize_screenplay_to_fountain,
    validate_fountain_export,
)
from logosforge.export import export_screenplay_fountain
from logosforge.writing_modes import (
    current_primary_unit_type,
    get_project_writing_mode_by_id,
    mode_context_block,
)


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


def _screenplay(db):
    return db.create_project("S", narrative_engine="screenplay",
                             default_writing_format="screenplay").id


def _novel(db):
    return db.create_project("N", narrative_engine="novel").id


# ==========================================================================
# 1-2  Mode + primary unit
# ==========================================================================


def test_screenplay_primary_unit_is_scene():
    db = Database()
    sid_proj = db.get_project_by_id(_screenplay(db))
    assert current_primary_unit_type(sid_proj) == "scene"


def test_novel_primary_unit_unchanged():
    db = Database()
    n = db.get_project_by_id(_novel(db))
    assert current_primary_unit_type(n) == "chapter"


# ==========================================================================
# 3-4  Block taxonomy + plain-text compatibility adapter
# ==========================================================================


def test_block_taxonomy_has_required_types():
    for key in ("scene_heading", "action", "character", "dialogue",
                "parenthetical", "transition", "shot", "note"):
        assert sp.is_valid_element(key)


def test_plain_text_body_adapts_without_loss():
    body = "John walks in.\n\nHe sits down quietly."
    blocks = parse_screenplay_text(body)
    assert blocks and all(b.element_type == "action" for b in blocks)
    # Round-trips with no text loss.
    out = serialize_blocks(blocks)
    assert "John walks in." in out and "He sits down quietly." in out


def test_block_type_and_order_persist():
    blocks = [
        ScreenplayBlock("scene_heading", "INT. HOUSE - DAY", order_index=0),
        ScreenplayBlock("action", "John enters.", order_index=1),
        ScreenplayBlock("character", "JOHN", order_index=2),
        ScreenplayBlock("dialogue", "Hello.", order_index=3),
    ]
    round = [ScreenplayBlock.from_dict(b.to_dict()) for b in blocks]
    assert [b.element_type for b in round] == [
        "scene_heading", "action", "character", "dialogue"]
    assert [b.order_index for b in round] == [0, 1, 2, 3]


def test_invalid_block_type_degrades_to_action():
    assert ScreenplayBlock("nonsense", "x").element_type == "action"


def test_parser_classifies_core_elements():
    body = ("INT. HOUSE - NIGHT\n\nJohn waits.\n\n"
            "JOHN\n(quietly)\nAre you there?\n\nCUT TO:")
    kinds = [b.element_type for b in parse_screenplay_text(body)]
    assert kinds == ["scene_heading", "action", "character",
                     "parenthetical", "dialogue", "transition"]


# ==========================================================================
# 5  Per-element Fountain serialization
# ==========================================================================


def _fountain(blocks):
    return serialize_screenplay_to_fountain(
        blocks, options=FountainExportOptions(include_title_page=False)).text


def test_fountain_scene_heading_and_action():
    out = _fountain([
        ScreenplayBlock("scene_heading", "INT. HOUSE - DAY"),
        ScreenplayBlock("action", "John enters the room."),
    ])
    assert "INT. HOUSE - DAY" in out and "John enters the room." in out


def test_fountain_character_dialogue_parenthetical():
    out = _fountain([
        ScreenplayBlock("character", "john"),
        ScreenplayBlock("parenthetical", "quietly"),
        ScreenplayBlock("dialogue", "Hello there."),
    ])
    assert "JOHN" in out                      # cue uppercased
    assert "(quietly)" in out                 # parenthetical wrapped
    assert "Hello there." in out


def test_fountain_transition():
    out = _fountain([ScreenplayBlock("transition", "cut to:")])
    assert "CUT TO:" in out


# ==========================================================================
# 6  Full-project Fountain: canonical order, body only
# ==========================================================================


def test_full_project_fountain_canonical_order():
    db = Database()
    pid = _screenplay(db)
    ss.create_scene(db, pid, act="Act I", chapter="Seq 1", title="A",
                    content="INT. ALPHA - DAY\n\nAlpha action.")
    ss.create_scene(db, pid, act="Act II", chapter="Seq 2", title="B",
                    content="INT. BETA - DAY\n\nBeta action.")
    out = export_screenplay_fountain(db, pid)
    assert out.index("ALPHA") < out.index("BETA")     # canonical scene order


def test_fountain_excludes_outline_summary_and_timeline():
    db = Database()
    pid = _screenplay(db)
    ss.create_scene(db, pid, act="Act I", chapter="Seq 1", title="A",
                    content="INT. HOUSE - DAY\n\nReal action.",
                    summary="OUTLINE_SUMMARY_SENTINEL")
    db.create_timeline_lane(pid, "TIMELINE_LANE_SENTINEL", "green")
    out = export_screenplay_fountain(db, pid)
    assert "Real action." in out                       # body present
    assert "OUTLINE_SUMMARY_SENTINEL" not in out        # not the summary
    assert "TIMELINE_LANE_SENTINEL" not in out          # not Timeline data


# ==========================================================================
# 7  Outline ↔ Manuscript separation
# ==========================================================================


def test_summary_edit_does_not_change_body():
    db = Database()
    pid = _screenplay(db)
    sid = ss.create_scene(db, pid, act="Act I", chapter="Seq 1", title="S",
                          content="REAL BODY", summary="SUM ONE").id
    db.update_scene_summary(sid, "SUM TWO")
    assert db.get_scene_by_id(sid).content == "REAL BODY"


def test_body_edit_does_not_change_summary():
    db = Database()
    pid = _screenplay(db)
    s = ss.create_scene(db, pid, act="Act I", chapter="Seq 1", title="S",
                        content="OLD BODY", summary="KEEP SUMMARY")
    db.update_scene(
        scene_id=s.id, title=s.title, summary=s.summary, synopsis=s.synopsis,
        goal=s.goal, conflict=s.conflict, outcome=s.outcome, beat=s.beat,
        tags=s.tags, act=s.act, content="NEW BODY", chapter=s.chapter,
        plotline=s.plotline)
    after = db.get_scene_by_id(s.id)
    assert after.content == "NEW BODY" and after.summary == "KEEP SUMMARY"


# ==========================================================================
# 8-9  Assistant + Logos screenplay context
# ==========================================================================


def test_assistant_context_identifies_screenplay():
    db = Database()
    pid = _screenplay(db)
    block = mode_context_block(get_project_writing_mode_by_id(db, pid))
    assert "Screenplay" in block
    assert "action" in block.lower()           # cinematic guidance present


def test_logos_context_has_screenplay_mode_and_block_type(tmp_path):
    from logosforge.ui.main_window import MainWindow
    from logosforge.ui.writing_core_view import WritingCoreView
    db = Database(str(tmp_path / "sp.db"))
    pid = _screenplay(db)
    ss.create_scene(db, pid, act="Act I", chapter="Seq 1", title="S",
                    content="INT. HOUSE - DAY\n\nAction.")
    win = MainWindow(db, pid)
    win.sidebar_buttons["Manuscript"].click()
    assert isinstance(win.content_area, WritingCoreView)
    # Headless has no focus events; mark the scene editor active so the current
    # screenplay element is available (the host carries it into LogosContext).
    view = win.content_area
    if view._editors:
        view._active_editor = next(iter(view._editors.values()))
    ctx = win._build_logos_context()
    assert getattr(ctx, "writing_mode", "") == "screenplay"
    assert sp.is_valid_element(getattr(ctx, "active_block_type", ""))


# ==========================================================================
# 10  Deterministic validation
# ==========================================================================


def test_validation_flags_empty_and_orphan_dialogue():
    empty = validate_fountain_export("")
    assert not empty.is_valid                  # empty output is invalid
    # Orphan dialogue (no character cue) → warning, not a hard block.
    orphan = validate_fountain_export("INT. HOUSE - DAY\n\nHello there.\n")
    assert orphan.is_valid                      # warnings don't block
    assert orphan.warnings


# ==========================================================================
# 11  Project isolation
# ==========================================================================


def test_screenplay_body_does_not_leak_across_projects(tmp_path):
    db = Database(str(tmp_path / "sp.db"))
    a = _screenplay(db)
    ss.create_scene(db, a, act="Act I", chapter="Seq 1", title="A",
                    content="INT. A-ONLY - DAY\n\nProject A body.")
    b = _screenplay(db)
    out_b = export_screenplay_fountain(db, b)
    assert "A-ONLY" not in out_b and "Project A body" not in out_b
