"""Stage Script Mode — Phase 1 acceptance suite.

Stage-play block foundation inside the universal Manuscript: a Scene's flat body
is parsed into ordered, typed stage blocks and serialized back (no schema change),
with deterministic validation, Markdown export, a 'Stage Script Check' Logos
action, and strict Outline/Manuscript separation. No AI generation, and
explicitly no image generation.
"""

from __future__ import annotations

import warnings

import pytest
from PySide6.QtWidgets import QApplication

warnings.filterwarnings("ignore")

from logosforge.db import Database
from logosforge import story_structure as ss
from logosforge import stage_script_blocks as ssb
from logosforge.writing_modes import (
    get_project_writing_mode_by_id, set_project_writing_mode,
    NOVEL, SCREENPLAY, GRAPHIC_NOVEL, STAGE_SCRIPT,
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


def _stage(db, title="ST"):
    return db.create_project(title, narrative_engine="stage_script",
                             default_writing_format="stage_script").id


def _scene(db, pid, content="", *, title="S", summary="s", act="Act I",
           chapter="Chapter 1"):
    return ss.create_scene(db, pid, act=act, chapter=chapter, title=title,
                           content=content, summary=summary).id


_RICH = (
    "SCENE: The Throne Room\n\n"
    "ACT: Act One\n\n"
    "STAGE: A bare room. Evening.\n\n"
    "CHARACTER: MARIA\n(softly)\nIt ends now.\n\n"
    "ENTER: John enters from stage left.\n\n"
    "EXIT: John exits right.\n\n"
    "LIGHT: Lights dim to blue.\n\n"
    "SOUND: Distant thunder.\n\n"
    "SET: A single chair, centre stage.\n\n"
    "TRANSITION: Blackout.\n\n"
    "NOTE: beat to land before the reveal."
)


# ==========================================================================
# 1-5  Mode behavior
# ==========================================================================


def test_stage_primary_unit_is_scene():
    from logosforge.writing_modes import current_primary_unit_type
    db = Database()
    pid = _stage(db)
    assert get_project_writing_mode_by_id(db, pid) == STAGE_SCRIPT
    assert current_primary_unit_type(db.get_project_by_id(pid)) == "scene"


def test_universal_manuscript_reused_no_separate_section():
    from logosforge.ui.writing_core_view import WritingCoreView
    db = Database()
    pid = _stage(db)
    _scene(db, pid, "STAGE: A room.")
    view = WritingCoreView(db, pid, structured_list=True)
    assert isinstance(view, WritingCoreView)            # the one universal section
    ed = next(iter(view._editors.values()))
    # Stage Script shows neither screenplay-only nor graphic-novel-only controls.
    assert ed._screenplay_mode is False and ed._graphic_novel_mode is False


def test_novel_screenplay_graphic_novel_modes_preserved():
    from logosforge.logos.controller import LogosController
    from logosforge.writing_modes import current_primary_unit_type
    db = Database()
    nv = db.create_project("N", narrative_engine="novel").id
    sp = db.create_project("S", narrative_engine="screenplay",
                           default_writing_format="screenplay").id
    gn = db.create_project("G", narrative_engine="graphic_novel",
                           default_writing_format="graphic_novel").id
    assert current_primary_unit_type(db.get_project_by_id(nv)) == "chapter"
    ctl = LogosController(db)
    assert any(a.name.startswith("sp_") for a in
               ctl.available_actions("Manuscript", writing_mode="screenplay"))
    assert any(a.name.startswith("gn_") for a in
               ctl.available_actions("Manuscript", writing_mode="graphic_novel"))


# ==========================================================================
# 6-18  Data / model
# ==========================================================================


def test_all_required_block_types_parse():
    script = ssb.parse_stage_script_text(_RICH)
    types = {b.block_type for b in script.blocks}
    assert {ssb.BT_SCENE_HEADING, ssb.BT_STAGE_DIRECTION, ssb.BT_CHARACTER,
            ssb.BT_DIALOGUE, ssb.BT_PARENTHETICAL, ssb.BT_ENTRANCE, ssb.BT_EXIT,
            ssb.BT_LIGHTING_CUE, ssb.BT_SOUND_CUE, ssb.BT_SET_PROPS,
            ssb.BT_TRANSITION, ssb.BT_NOTE} <= types


def test_character_and_dialogue_blocks():
    script = ssb.parse_stage_script_text("CHARACTER: MARIA\nIt ends now.")
    assert script.blocks[0].block_type == ssb.BT_CHARACTER
    assert script.blocks[0].character == "MARIA"
    assert script.blocks[1].block_type == ssb.BT_DIALOGUE
    assert script.blocks[1].character == "MARIA"


def test_parenthetical_and_cues():
    script = ssb.parse_stage_script_text(
        "CHARACTER: BOB\n(angry)\nNo.\n\nLIGHT: Spotlight up.\n\nSOUND: A bell.")
    kinds = [b.block_type for b in script.blocks]
    assert ssb.BT_PARENTHETICAL in kinds and ssb.BT_LIGHTING_CUE in kinds
    assert ssb.BT_SOUND_CUE in kinds


def test_entrance_exit_blocks():
    script = ssb.parse_stage_script_text(
        "ENTER: Maria enters.\n\nEXIT: Bob exits.")
    assert [b.block_type for b in script.blocks] == [ssb.BT_ENTRANCE, ssb.BT_EXIT]


def test_set_props_and_transition_and_note():
    script = ssb.parse_stage_script_text(
        "SET: A chair.\n\nTRANSITION: Blackout.\n\nNOTE: hold the beat.")
    assert [b.block_type for b in script.blocks] == [
        ssb.BT_SET_PROPS, ssb.BT_TRANSITION, ssb.BT_NOTE]


def test_block_order_and_type_persist_round_trip():
    script = ssb.parse_stage_script_text(_RICH)
    types_before = [b.block_type for b in script.blocks]
    round = ssb.parse_stage_script_text(ssb.serialize_stage_script(script))
    assert [b.block_type for b in round.blocks] == types_before
    assert all(b.order_index == i for i, b in enumerate(round.blocks))


def test_plain_text_loads_as_stage_direction():
    script = ssb.parse_stage_script_text("A bare room. Evening light fades.")
    assert len(script.blocks) == 1
    assert script.blocks[0].block_type == ssb.BT_STAGE_DIRECTION
    assert "bare room" in script.blocks[0].text


def test_add_move_delete_block():
    script = ssb.StageScript()
    ssb.add_block(script, ssb.BT_STAGE_DIRECTION, "First.")
    ssb.add_block(script, ssb.BT_SOUND_CUE, "A bell.")
    ssb.add_block(script, ssb.BT_NOTE, "note")
    assert [b.order_index for b in script.blocks] == [0, 1, 2]
    assert ssb.move_block(script, 2, -1)               # move note up
    assert script.blocks[1].block_type == ssb.BT_NOTE
    assert ssb.delete_block(script, 0)                 # delete the stage direction
    assert [b.block_type for b in script.blocks] == [ssb.BT_NOTE, ssb.BT_SOUND_CUE]
    assert not ssb.delete_block(script, 99)            # out-of-range is safe


# ==========================================================================
# 19-22  Outline / Manuscript separation
# ==========================================================================


def test_outline_summary_not_in_body():
    db = Database()
    pid = _stage(db)
    sid = _scene(db, pid, content="STAGE: A room.", summary="PLANNING_SUMMARY")
    script = ssb.load_scene_script(db, sid)
    assert "PLANNING_SUMMARY" not in ssb.serialize_stage_script(script)
    assert db.get_scene_by_id(sid).summary == "PLANNING_SUMMARY"


def test_saving_body_does_not_overwrite_summary():
    db = Database()
    pid = _stage(db)
    sid = _scene(db, pid, content="", summary="KEEP")
    script = ssb.StageScript()
    ssb.add_block(script, ssb.BT_STAGE_DIRECTION, "A new room.")
    ssb.save_scene_script(db, sid, script)
    assert db.get_scene_by_id(sid).summary == "KEEP"
    assert "A new room" in db.get_scene_by_id(sid).content


def test_timeline_event_does_not_become_a_block():
    db = Database()
    pid = _stage(db)
    sid = _scene(db, pid, content="STAGE: A room.")
    db.add_timeline_event(pid, sid)
    script = ssb.load_scene_script(db, sid)
    assert len(script.blocks) == 1 and script.blocks[0].block_type == ssb.BT_STAGE_DIRECTION


def test_report_does_not_mutate_psyke():
    db = Database()
    pid = _stage(db)
    db.create_psyke_entry(pid, "Maria", "character")
    sid = _scene(db, pid, content=_RICH)
    before = len(db.get_all_psyke_entries(pid))
    ssb.validate_stage_script(ssb.load_scene_script(db, sid))
    ssb.export_project_markdown(db, pid)
    assert len(db.get_all_psyke_entries(pid)) == before == 1


# ==========================================================================
# 23-27  Export
# ==========================================================================


def test_export_scene_markdown():
    db = Database()
    pid = _stage(db)
    sid = _scene(db, pid, content="SCENE: Room\n\nCHARACTER: MARIA\nHello.\n\n"
                 "STAGE: She waits.")
    md = ssb.export_scene_markdown(db, pid, sid)
    assert "MARIA" in md and "Hello" in md and "Stage Direction" in md


def test_export_project_canonical_order():
    db = Database()
    pid = _stage(db)
    b = _scene(db, pid, content="STAGE: Beta room.", title="Beta",
               act="Act II", chapter="Chapter 2")
    a = _scene(db, pid, content="STAGE: Alpha room.", title="Alpha",
               act="Act I", chapter="Chapter 1")
    db.reorder_scenes(pid, [a, b])
    md = ssb.export_project_markdown(db, pid)
    assert md.index("Alpha room") < md.index("Beta room")


def test_export_excludes_secrets_and_planning():
    db = Database()
    from logosforge.settings import get_manager
    get_manager().set("ai_api_key", "SECRET_KEY_SENTINEL")
    pid = _stage(db)
    sid = _scene(db, pid, content="STAGE: A room.", summary="PLAN_ONLY_SENTINEL")
    db.add_timeline_event(pid, sid)
    md = ssb.export_project_markdown(db, pid)
    assert "SECRET_KEY_SENTINEL" not in md          # no API keys
    assert "PLAN_ONLY_SENTINEL" not in md           # no Outline summary as body
    assert "A room" in md                           # the stage body is included


# ==========================================================================
# 28-33  Validation
# ==========================================================================


def test_empty_scene_warning():
    rep = ssb.validate_stage_script(ssb.StageScript())
    assert rep.is_valid is False and rep.warnings


def test_dialogue_without_character_warning():
    rep = ssb.validate_stage_script(
        ssb.parse_stage_script_text("DIALOGUE: A line with no speaker."))
    assert any("no preceding character" in w.lower() for w in rep.warnings)


def test_character_without_dialogue_warning():
    rep = ssb.validate_stage_script(
        ssb.parse_stage_script_text("CHARACTER: MARIA\n\nSTAGE: She leaves."))
    assert any("no following dialogue" in w.lower() for w in rep.warnings)


def test_empty_cue_warning():
    # A non-empty scene that contains an empty cue (an all-empty scene would
    # short-circuit to the "no stage script" warning instead).
    rep = ssb.validate_stage_script(
        ssb.parse_stage_script_text("STAGE: A room.\n\nLIGHT:"))
    assert any("cue text" in w.lower() for w in rep.warnings)


def test_entrance_without_character_warning():
    rep = ssb.validate_stage_script(
        ssb.parse_stage_script_text("STAGE: A room.\n\nENTER:"))
    assert any("movement" in w.lower() or "character" in w.lower()
               for w in rep.warnings)


def test_too_many_dialogue_blocks_warning():
    body = "CHARACTER: MARIA\n" + "\n".join(f"Line {i}." for i in range(1, 7))
    rep = ssb.validate_stage_script(ssb.parse_stage_script_text(body))
    assert any("row" in w.lower() for w in rep.warnings)


# ==========================================================================
# 34-36  Project isolation
# ==========================================================================


def test_stage_blocks_isolated_across_projects(tmp_path):
    db = Database(str(tmp_path / "stage.db"))
    a = _stage(db, "A")
    sid_a = _scene(db, a, content="STAGE: A_SENTINEL room.")
    b = _stage(db, "B")
    assert [s.id for s in db.get_all_scenes(b)] == []
    assert "A_SENTINEL" not in ssb.export_project_markdown(db, b)
    assert "A_SENTINEL" in ssb.export_project_markdown(db, a)


def test_new_project_starts_clean():
    db = Database()
    a = _stage(db, "A")
    _scene(db, a, content="STAGE: room.")
    c = _stage(db, "C")
    assert ssb.export_project_markdown(db, c).strip().splitlines()[0].startswith("#")
    assert len(db.get_all_scenes(c)) == 0


# ==========================================================================
# Mode switching preserves bodies
# ==========================================================================


def test_mode_switch_preserves_body():
    db = Database()
    pid = _stage(db)
    sid = _scene(db, pid, content="STAGE: A bare room.", summary="keep")
    for mode in (NOVEL, SCREENPLAY, GRAPHIC_NOVEL, STAGE_SCRIPT):
        set_project_writing_mode(db, pid, mode)
        assert db.get_scene_by_id(sid).content == "STAGE: A bare room."
        assert db.get_scene_by_id(sid).summary == "keep"


# ==========================================================================
# Logos / Assistant + no image generation
# ==========================================================================


def test_logos_dropdown_includes_stage_check():
    from logosforge.logos.controller import LogosController
    db = Database()
    db.create_project("ST", narrative_engine="stage_script",
                      default_writing_format="stage_script")
    names = [a.name for a in LogosController(db).available_actions(
        "Manuscript", writing_mode="stage_script")]
    assert "stage_check" in names
    for other in ("novel", "screenplay", "graphic_novel"):
        other_names = [a.name for a in LogosController(db).available_actions(
            "Manuscript", writing_mode=other)]
        assert "stage_check" not in other_names


def test_stage_check_runs_deterministically():
    from logosforge.logos.controller import LogosController
    from logosforge.logos.context import build_logos_context

    def _boom(*a, **k):
        raise AssertionError("deterministic action must not call the LLM")

    db = Database()
    pid = _stage(db)
    sid = _scene(db, pid, content="CHARACTER: MARIA\nHello there friend.")
    ctl = LogosController(db, provider_resolver=_boom, chat_fn=_boom)
    ctx = build_logos_context(db, pid, section_name="Manuscript", current_scene_id=sid)
    res = ctl.run(ctx, "stage_check")
    assert res.ok and res.title == "Stage Script Check"
    assert res.proposed_operations == []


def test_assistant_context_identifies_stage_scene():
    db = Database()
    pid = _stage(db)
    sid = _scene(db, pid, content="CHARACTER: MARIA\nHello.\n\nSTAGE: She waits.")
    ctx = ssb.stage_script_context(db, pid, sid)
    assert "[Stage Script]" in ctx
    # A non-stage project gets no stage context block.
    nv = db.create_project("N", narrative_engine="novel").id
    nv_s = _scene(db, nv, content="prose")
    assert ssb.stage_script_context(db, nv, nv_s) == ""


def test_no_image_generation_code_or_actions():
    import os, tokenize
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = os.path.join(here, "logosforge", "stage_script_blocks.py")
    toks = []
    with open(src, "rb") as fh:
        for tok in tokenize.tokenize(fh.readline):
            name = tokenize.tok_name[tok.type]
            if tok.type == tokenize.COMMENT or name.endswith("STRING"):
                continue
            toks.append(tok.string.lower())
    skeleton = " ".join(toks)
    for banned in ("comfyui", "image generation", "image prompt", "lora",
                   "render", "stable diffusion", "img2img", "txt2img"):
        assert banned not in skeleton, banned
    from logosforge.logos import actions as A
    names = " ".join(a.name + " " + a.label for a in A.list_actions()).lower()
    for banned in ("comfyui", "image gen", "generate image", "image prompt"):
        assert banned not in names
