"""Series Mode — Phase 1 acceptance suite.

Series / teleplay block foundation inside the universal Manuscript: a Scene's flat
body is parsed into ordered, typed teleplay blocks (reusing the screenplay engine
+ serial markers) and serialized back (no schema change), with deterministic
validation, Markdown export (Chapter shown as Episode), a 'Series Scene Check'
Logos action, and strict Outline/Manuscript separation. No AI generation, and
explicitly no image generation. Canonical Act -> Chapter -> Scene is preserved.
"""

from __future__ import annotations

import warnings

import pytest
from PySide6.QtWidgets import QApplication

warnings.filterwarnings("ignore")

from logosforge.db import Database
from logosforge import story_structure as ss
from logosforge import series_blocks as srb
from logosforge.writing_modes import (
    get_project_writing_mode_by_id, set_project_writing_mode,
    current_primary_unit_type, NOVEL, SCREENPLAY, GRAPHIC_NOVEL, STAGE_SCRIPT, SERIES,
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


def _series(db, title="SR"):
    return db.create_project(title, narrative_engine="series",
                             default_writing_format="series").id


def _scene(db, pid, content="", *, title="S", summary="s", act="Act I",
           chapter="Chapter 1"):
    return ss.create_scene(db, pid, act=act, chapter=chapter, title=title,
                           content=content, summary=summary).id


_RICH = (
    "INT. APARTMENT - NIGHT\n\n"
    "Maria opens the door slowly.\n\n"
    "MARIA\n(quietly)\nHello there.\n\n"
    "CUT TO:\n\n"
    "COLD OPEN\n\n"
    "ACT BREAK\n\n"
    "TAG"
)


# ==========================================================================
# 1-6  Mode behavior
# ==========================================================================


def test_series_primary_unit_is_scene():
    db = Database()
    pid = _series(db)
    assert get_project_writing_mode_by_id(db, pid) == SERIES
    assert current_primary_unit_type(db.get_project_by_id(pid)) == "scene"


def test_universal_manuscript_reused_no_separate_section():
    from logosforge.ui.writing_core_view import WritingCoreView
    db = Database()
    pid = _series(db)
    _scene(db, pid, "INT. X - DAY\n\nAction.")
    view = WritingCoreView(db, pid, structured_list=True)
    assert isinstance(view, WritingCoreView)
    ed = next(iter(view._editors.values()))
    # Series shows neither screenplay-only, graphic-novel-only, nor stage controls.
    assert ed._screenplay_mode is False and ed._graphic_novel_mode is False


def test_other_modes_preserved():
    from logosforge.logos.controller import LogosController
    db = Database()
    nv = db.create_project("N", narrative_engine="novel").id
    assert current_primary_unit_type(db.get_project_by_id(nv)) == "chapter"
    for engine, prefix in (("screenplay", "sp_"), ("graphic_novel", "gn_"),
                           ("stage_script", "stage_")):
        db.create_project(engine, narrative_engine=engine,
                          default_writing_format=engine)
        names = [a.name for a in LogosController(db).available_actions(
            "Manuscript", writing_mode=engine)]
        assert any(n.startswith(prefix) for n in names)
        assert "series_check" not in names


# ==========================================================================
# 7-11  Structure / labels (canonical Act -> Chapter -> Scene preserved)
# ==========================================================================


def test_canonical_structure_internally():
    db = Database()
    pid = _series(db)
    b = _scene(db, pid, "INT. B - DAY\n\nb.", title="B", act="Act II",
               chapter="Chapter 2")
    a = _scene(db, pid, "INT. A - DAY\n\na.", title="A", act="Act I",
               chapter="Chapter 1")
    db.reorder_scenes(pid, [a, b])
    assert ss.canonical_scene_order(db, pid) == [a, b]   # canonical, not id order


def test_chapter_displayed_as_episode():
    assert srb.episode_label("1") == "Episode 1"
    assert srb.episode_label("Episode 2") == "Episode 2"
    assert srb.episode_label("") == "Episode"


def test_scene_belongs_to_episode_and_no_orphans():
    db = Database()
    pid = _series(db)
    sid = _scene(db, pid, "INT. X - DAY\n\nAction.", act="Act I", chapter="Chapter 1")
    scene = db.get_scene_by_id(sid)
    assert (getattr(scene, "act", "") or "").strip()       # belongs to an Act
    assert (getattr(scene, "chapter", "") or "").strip()   # belongs to a Chapter/Episode
    assert all((getattr(s, "act", "") or "").strip()
               and (getattr(s, "chapter", "") or "").strip()
               for s in db.get_all_scenes(pid))             # no orphans


# ==========================================================================
# 12-24  Data / model
# ==========================================================================


def test_all_required_block_types_parse():
    script = srb.parse_series_text(_RICH)
    types = {b.block_type for b in script.blocks}
    assert {srb.BT_SCENE_HEADING, srb.BT_ACTION, srb.BT_CHARACTER, srb.BT_DIALOGUE,
            srb.BT_PARENTHETICAL, srb.BT_TRANSITION, srb.BT_ACT_BREAK,
            srb.BT_TEASER, srb.BT_TAG} <= types


def test_series_markers_reclassified():
    script = srb.parse_series_text("COLD OPEN\n\nACT BREAK\n\nEND OF ACT ONE\n\nTAG")
    assert [b.block_type for b in script.blocks] == [
        srb.BT_TEASER, srb.BT_ACT_BREAK, srb.BT_ACT_BREAK, srb.BT_TAG]


def test_character_dialogue_parenthetical():
    script = srb.parse_series_text("MARIA\n(quietly)\nHello there.")
    assert [b.block_type for b in script.blocks] == [
        srb.BT_CHARACTER, srb.BT_PARENTHETICAL, srb.BT_DIALOGUE]


def test_plain_text_loads_as_action():
    script = srb.parse_series_text("A bare paragraph of prose with no markers.")
    assert script.blocks and script.blocks[0].block_type == srb.BT_ACTION


def test_block_order_and_type_persist_round_trip():
    script = srb.parse_series_text(_RICH)
    types_before = [b.block_type for b in script.blocks]
    rnd = srb.parse_series_text(srb.serialize_series_script(script))
    assert [b.block_type for b in rnd.blocks] == types_before
    assert all(b.order_index == i for i, b in enumerate(rnd.blocks))


def test_add_move_delete_block():
    script = srb.SeriesScript()
    srb.add_block(script, srb.BT_SCENE_HEADING, "INT. X - DAY")
    srb.add_block(script, srb.BT_ACTION, "Action.")
    srb.add_block(script, srb.BT_TAG, "TAG")
    assert [b.order_index for b in script.blocks] == [0, 1, 2]
    assert srb.move_block(script, 2, -1)
    assert script.blocks[1].block_type == srb.BT_TAG
    assert srb.delete_block(script, 0)
    assert [b.block_type for b in script.blocks] == [srb.BT_TAG, srb.BT_ACTION]
    assert not srb.delete_block(script, 99)


def test_create_shot_block_via_model():
    script = srb.SeriesScript()
    srb.add_block(script, srb.BT_SHOT, "ANGLE ON the window")
    assert script.blocks[0].block_type == srb.BT_SHOT


# ==========================================================================
# 25-28  Outline / Manuscript separation
# ==========================================================================


def test_outline_summary_not_in_body():
    db = Database()
    pid = _series(db)
    sid = _scene(db, pid, "INT. X - DAY\n\nAction.", summary="PLANNING_SUMMARY")
    body = srb.serialize_series_script(srb.load_scene_script(db, sid))
    assert "PLANNING_SUMMARY" not in body
    assert db.get_scene_by_id(sid).summary == "PLANNING_SUMMARY"


def test_saving_body_does_not_overwrite_summary():
    db = Database()
    pid = _series(db)
    sid = _scene(db, pid, "", summary="KEEP")
    script = srb.SeriesScript()
    srb.add_block(script, srb.BT_ACTION, "A new beat.")
    srb.save_scene_script(db, sid, script)
    assert db.get_scene_by_id(sid).summary == "KEEP"
    assert "A new beat" in db.get_scene_by_id(sid).content


def test_timeline_event_does_not_become_a_block():
    db = Database()
    pid = _series(db)
    sid = _scene(db, pid, "INT. X - DAY\n\nAction.")
    before = len(srb.load_scene_script(db, sid).blocks)
    db.add_timeline_event(pid, sid)
    assert len(srb.load_scene_script(db, sid).blocks) == before


def test_validation_does_not_mutate_psyke():
    db = Database()
    pid = _series(db)
    db.create_psyke_entry(pid, "Maria", "character")
    sid = _scene(db, pid, _RICH)
    before = len(db.get_all_psyke_entries(pid))
    srb.validate_series_script(srb.load_scene_script(db, sid))
    srb.export_project_markdown(db, pid)
    assert len(db.get_all_psyke_entries(pid)) == before == 1


# ==========================================================================
# 29-34  Export
# ==========================================================================


def test_export_scene_markdown():
    db = Database()
    pid = _series(db)
    sid = _scene(db, pid, "INT. X - DAY\n\nMaria opens the door.\n\nMARIA\nHi.",
                 chapter="Chapter 3")
    md = srb.export_scene_markdown(db, pid, sid)
    assert "MARIA" in md and "Maria opens the door" in md and "Scene Heading" in md


def test_export_project_canonical_order_and_episode_label():
    db = Database()
    pid = _series(db)
    b = _scene(db, pid, "INT. B - DAY\n\nBeta action.", title="Beta",
               act="Act II", chapter="Chapter 2")
    a = _scene(db, pid, "INT. A - DAY\n\nAlpha action.", title="Alpha",
               act="Act I", chapter="Chapter 1")
    db.reorder_scenes(pid, [a, b])
    md = srb.export_project_markdown(db, pid)
    assert md.index("Alpha action") < md.index("Beta action")   # canonical order
    assert "Episode" in md                                       # Episode label


def test_export_excludes_secrets_and_planning():
    db = Database()
    from logosforge.settings import get_manager
    get_manager().set("ai_api_key", "SECRET_KEY_SENTINEL")
    pid = _series(db)
    sid = _scene(db, pid, "INT. X - DAY\n\nAction.", summary="PLAN_ONLY_SENTINEL")
    db.add_timeline_event(pid, sid)
    md = srb.export_project_markdown(db, pid)
    assert "SECRET_KEY_SENTINEL" not in md
    assert "PLAN_ONLY_SENTINEL" not in md
    assert "Action" in md


# ==========================================================================
# 35-41  Validation
# ==========================================================================


def test_empty_scene_warning():
    rep = srb.validate_series_script(srb.SeriesScript())
    assert rep.is_valid is False and rep.warnings


def test_dialogue_without_character_warning():
    script = srb.SeriesScript()
    srb.add_block(script, srb.BT_SCENE_HEADING, "INT. X - DAY")
    srb.add_block(script, srb.BT_DIALOGUE, "A line with no speaker.")
    rep = srb.validate_series_script(script)
    assert any("no preceding character" in w.lower() for w in rep.warnings)


def test_character_without_dialogue_warning():
    script = srb.SeriesScript()
    srb.add_block(script, srb.BT_SCENE_HEADING, "INT. X - DAY")
    srb.add_block(script, srb.BT_CHARACTER, "MARIA")
    srb.add_block(script, srb.BT_ACTION, "She leaves.")
    rep = srb.validate_series_script(script)
    assert any("no following dialogue" in w.lower() for w in rep.warnings)


def test_missing_scene_heading_warning():
    rep = srb.validate_series_script(
        srb.parse_series_text("Maria opens the door.\n\nMARIA\nHi."))
    assert any("scene heading" in w.lower() for w in rep.warnings)


def test_empty_block_warning():
    script = srb.parse_series_text("INT. X - DAY\n\nAction.")
    srb.add_block(script, srb.BT_ACTION, "")
    rep = srb.validate_series_script(script)
    assert any("empty" in w.lower() for w in rep.warnings)


def test_dialogue_only_run_warning():
    body = "MARIA\n" + "\n".join(f"Line {i}." for i in range(1, 7))
    rep = srb.validate_series_script(srb.parse_series_text(body))
    assert any("row" in w.lower() for w in rep.warnings)


def test_act_break_placement_warning():
    rep = srb.validate_series_script(
        srb.parse_series_text("ACT BREAK\n\nINT. X - DAY\n\nAction."))
    assert any("act break" in w.lower() and "start" in w.lower()
               for w in rep.warnings)


# ==========================================================================
# 42-44  Project isolation
# ==========================================================================


def test_series_blocks_isolated_across_projects(tmp_path):
    db = Database(str(tmp_path / "sr.db"))
    a = _series(db, "A")
    _scene(db, a, "INT. X - DAY\n\nA_SENTINEL action here.")
    b = _series(db, "B")
    assert [s.id for s in db.get_all_scenes(b)] == []
    assert "A_SENTINEL" not in srb.export_project_markdown(db, b)
    assert "A_SENTINEL" in srb.export_project_markdown(db, a)


def test_new_project_starts_clean():
    db = Database()
    a = _series(db, "A")
    _scene(db, a, "INT. X - DAY\n\nAction.")
    c = _series(db, "C")
    assert len(db.get_all_scenes(c)) == 0


# ==========================================================================
# Mode switching + Logos + no image generation
# ==========================================================================


def test_mode_switch_preserves_body():
    db = Database()
    pid = _series(db)
    sid = _scene(db, pid, "INT. X - DAY\n\nMaria opens the door.", summary="keep")
    for mode in (NOVEL, SCREENPLAY, GRAPHIC_NOVEL, STAGE_SCRIPT, SERIES):
        set_project_writing_mode(db, pid, mode)
        assert db.get_scene_by_id(sid).content == "INT. X - DAY\n\nMaria opens the door."
        assert db.get_scene_by_id(sid).summary == "keep"


def test_logos_dropdown_includes_series_check():
    from logosforge.logos.controller import LogosController
    db = Database()
    db.create_project("SR", narrative_engine="series", default_writing_format="series")
    names = [a.name for a in LogosController(db).available_actions(
        "Manuscript", writing_mode="series")]
    assert "series_check" in names
    novel = [a.name for a in LogosController(db).available_actions(
        "Manuscript", writing_mode="novel")]
    assert "series_check" not in novel


def test_series_check_runs_deterministically():
    from logosforge.logos.controller import LogosController
    from logosforge.logos.context import build_logos_context

    def _boom(*a, **k):
        raise AssertionError("deterministic action must not call the LLM")

    db = Database()
    pid = _series(db)
    sid = _scene(db, pid, _RICH)
    ctl = LogosController(db, provider_resolver=_boom, chat_fn=_boom)
    ctx = build_logos_context(db, pid, section_name="Manuscript", current_scene_id=sid)
    res = ctl.run(ctx, "series_check")
    assert res.ok and res.title == "Series Scene Check" and res.proposed_operations == []


def test_assistant_context_identifies_series_scene():
    db = Database()
    pid = _series(db)
    sid = _scene(db, pid, "INT. X - DAY\n\nMARIA\nHi.")
    ctx = srb.series_context(db, pid, sid)
    assert "[Series Script]" in ctx
    nv = db.create_project("N", narrative_engine="novel").id
    nv_s = _scene(db, nv, "prose")
    assert srb.series_context(db, nv, nv_s) == ""


def test_no_image_generation_code_or_actions():
    import os, tokenize
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = os.path.join(here, "logosforge", "series_blocks.py")
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
