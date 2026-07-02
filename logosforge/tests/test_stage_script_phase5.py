"""Stage Script Mode — Phase 5 acceptance suite.

Controlled rewrite: targeted revision request → preview (with a block diff +
validation) → confirmed apply. The AI never overwrites the body; apply requires
confirmation, touches only Scene.content, and preserves Outline / beat plan /
blocking plan / Timeline / PSYKE / Notes. No image generation.
"""

from __future__ import annotations

import warnings

import pytest
from PySide6.QtWidgets import QApplication

warnings.filterwarnings("ignore")

from logosforge.db import Database
from logosforge import story_structure as ss
from logosforge import stage_script_pipeline as ssp
from logosforge import stage_script_rewrite as srw


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


_CONTENT = ("SCENE: Kitchen\n\n"
            "STAGE: Maria stands by the window.\n\n"
            "CHARACTER: MARIA\nHello there.\n\n"
            "CHARACTER: JOHN\nGo away.")
_GOOD = ("SCENE: Kitchen\n\n"
         "STAGE: Maria slams the drawer shut.\n\n"
         "CHARACTER: MARIA\nLook at me.\n\n"
         "CHARACTER: JOHN\nNo.")
_BLOCK_NEW = "STAGE: Maria hurls the cup at the wall."


def _scene(db, pid, *, content=_CONTENT, summary="Maria pushes John", title="Confront"):
    return ss.create_scene(db, pid, act="Act I", chapter="Chapter 1",
                           title=title, content=content, summary=summary).id


# ==========================================================================
# 1-6  Rewrite request
# ==========================================================================


def test_request_includes_scene_context():
    db = Database()
    pid = _stage(db)
    sid = _scene(db, pid)
    req = srw.build_rewrite_request(db, pid, sid, instruction="make_more_playable")
    assert req.scene_title == "Confront"
    assert "Maria pushes John" in req.outline_summary
    assert req.original_body == _CONTENT and req.writing_mode == "stage_script"


def test_request_includes_beat_plan():
    db = Database()
    pid = _stage(db)
    sid = _scene(db, pid)
    ssp.save_beat_plan(db, pid, ssp.StageBeatPlan(scene_id=sid, objective="get John to talk"))
    req = srw.build_rewrite_request(db, pid, sid)
    assert "get John to talk" in req.beat_plan_text


def test_request_includes_blocking_plan():
    db = Database()
    pid = _stage(db)
    sid = _scene(db, pid)
    ssp.save_blocking_plan(db, pid, ssp.BlockingCuePlan(
        scene_id=sid, staging_area_notes="thrust stage, single chair"))
    req = srw.build_rewrite_request(db, pid, sid)
    assert "thrust stage" in req.blocking_plan_text


def test_request_includes_reflection():
    db = Database()
    pid = _stage(db)
    sid = _scene(db, pid)
    req = srw.build_rewrite_request(db, pid, sid, instruction="from_reflection")
    assert "Audience Perspective" in req.reflection_text


def test_request_includes_selected_block():
    db = Database()
    pid = _stage(db)
    sid = _scene(db, pid)
    req = srw.build_rewrite_request(db, pid, sid, selected_text=_BLOCK_NEW,
                                    target=srw.TARGET_BLOCK, target_block_indices=[1])
    assert req.selected_text == _BLOCK_NEW and req.target == srw.TARGET_BLOCK
    assert req.target_block_indices == [1]


def test_request_excludes_api_keys():
    db = Database()
    from logosforge.settings import get_manager
    get_manager().set("ai_api_key", "SECRET_KEY_SENTINEL")
    pid = _stage(db)
    sid = _scene(db, pid)
    req = srw.build_rewrite_request(db, pid, sid, instruction="from_reflection")
    blob = str(req.to_dict()) + srw.build_rewrite_prompt(req)
    assert "SECRET_KEY_SENTINEL" not in blob
    assert not any("api" in k.lower() or "secret" in k.lower() or k.lower() == "key"
                   for k in req.to_dict())


# ==========================================================================
# 7-12  Output parsing + validation
# ==========================================================================


def test_valid_block_output_parses():
    script = srw.parse_rewrite_output(_GOOD)
    kinds = [b.block_type for b in script.blocks]
    assert "scene_heading" in kinds and "character" in kinds and "dialogue" in kinds


def test_plain_text_output_adapts():
    script = srw.parse_rewrite_output("Maria crosses the room and opens the window.")
    assert script.blocks and script.blocks[0].block_type == "stage_direction"
    assert srw.validate_rewrite_output(
        "Maria crosses the room and opens the window.", target=srw.TARGET_SCENE).is_valid


def test_markdown_fences_are_cleaned():
    db = Database()
    pid = _stage(db)
    sid = _scene(db, pid)
    fenced = "```\nSCENE: X\n\nSTAGE: A clean room.\n```"
    assert srw.validate_rewrite_output(fenced, target=srw.TARGET_SCENE).is_valid
    prev = srw.build_rewrite_preview(db, pid, sid, fenced)
    assert "```" not in prev.proposed_text


def test_unknown_block_degrades_safely():
    text = "STAGE: A room.\n\nWEIRD: an unrecognized label."
    script = srw.parse_rewrite_output(text)
    assert all(b.block_type in __import__("logosforge.stage_script_blocks",
               fromlist=["BLOCK_TYPES"]).BLOCK_TYPES for b in script.blocks)
    assert srw.validate_rewrite_output(text, target=srw.TARGET_SCENE).is_valid


def test_system_prompt_leakage_is_rejected():
    v = srw.validate_rewrite_output("As an AI language model, here is the script.",
                                    target=srw.TARGET_SCENE)
    assert not v.is_valid and v.errors


def test_screenplay_formatting_is_rejected():
    v = srw.validate_rewrite_output("INT. KITCHEN - DAY\n\nMARIA\nHello.",
                                    target=srw.TARGET_SCENE)
    assert not v.is_valid and v.errors


# ==========================================================================
# 13-18  Preview
# ==========================================================================


def test_preview_does_not_mutate_body():
    db = Database()
    pid = _stage(db)
    sid = _scene(db, pid)
    srw.build_rewrite_preview(db, pid, sid, _GOOD)
    assert db.get_scene_by_id(sid).content == _CONTENT


def test_preview_shows_original_and_proposed():
    db = Database()
    pid = _stage(db)
    sid = _scene(db, pid)
    prev = srw.build_rewrite_preview(db, pid, sid, _GOOD)
    assert prev.original_text == _CONTENT and "slams the drawer" in prev.proposed_text
    assert prev.block_diff and "changed" in prev.block_diff


def test_preview_shows_target():
    db = Database()
    pid = _stage(db)
    sid = _scene(db, pid)
    prev = srw.build_rewrite_preview(db, pid, sid, _BLOCK_NEW,
                                     target=srw.TARGET_BLOCK, target_block_indices=[1])
    assert prev.target == srw.TARGET_BLOCK and prev.target_block_indices == [1]


def test_preview_surfaces_validation_warnings():
    db = Database()
    pid = _stage(db)
    sid = _scene(db, pid)
    prev = srw.build_rewrite_preview(
        db, pid, sid, "CHARACTER: MARIA\nHi.\n\nCHARACTER: JOHN\nBye.",
        target=srw.TARGET_SCENE)
    assert prev.can_apply and prev.warnings


def test_cancel_leaves_body_unchanged():
    db = Database()
    pid = _stage(db)
    sid = _scene(db, pid)
    res = srw.apply_rewrite(db, pid, sid, _GOOD, mode=srw.MODE_CANCEL, confirmed=True)
    assert res["ok"] is False and res.get("cancelled")
    assert db.get_scene_by_id(sid).content == _CONTENT


def test_copy_only_leaves_body_unchanged():
    db = Database()
    pid = _stage(db)
    sid = _scene(db, pid)
    res = srw.apply_rewrite(db, pid, sid, _GOOD, mode=srw.MODE_COPY_ONLY, confirmed=True)
    assert res["ok"] and res["mutated"] is False
    assert db.get_scene_by_id(sid).content == _CONTENT


# ==========================================================================
# 19-29  Apply
# ==========================================================================


def test_apply_selected_block_replaces_only_that_block():
    db = Database()
    pid = _stage(db)
    sid = _scene(db, pid)
    res = srw.apply_rewrite(db, pid, sid, _BLOCK_NEW, target=srw.TARGET_BLOCK,
                            target_block_indices=[1], mode=srw.MODE_REPLACE,
                            confirmed=True)
    body = db.get_scene_by_id(sid).content
    assert res["ok"]
    assert "hurls the cup" in body
    assert "Hello there" in body and "Go away" in body         # other blocks kept
    assert "stands by the window" not in body                  # block 1 replaced


def test_full_scene_replace_requires_confirmation():
    db = Database()
    pid = _stage(db)
    sid = _scene(db, pid)
    res = srw.apply_rewrite(db, pid, sid, _GOOD, mode=srw.MODE_REPLACE,
                            confirmed=False)
    assert res["ok"] is False
    assert db.get_scene_by_id(sid).content == _CONTENT


def test_append_alternate_does_not_overwrite_original():
    db = Database()
    pid = _stage(db)
    sid = _scene(db, pid)
    res = srw.apply_rewrite(db, pid, sid, _GOOD, mode=srw.MODE_APPEND_ALTERNATE,
                            confirmed=True)
    body = db.get_scene_by_id(sid).content
    assert res["ok"]
    assert "stands by the window" in body and "slams the drawer" in body


def test_apply_marks_project_dirty():
    db = Database()
    pid = _stage(db)
    sid = _scene(db, pid)
    from logosforge.project_events import get_event_bus
    fired = []
    get_event_bus().project_data_changed.connect(lambda *a: fired.append(1))
    srw.apply_rewrite(db, pid, sid, _GOOD, mode=srw.MODE_REPLACE, confirmed=True)
    assert fired


def test_apply_updates_body():
    db = Database()
    pid = _stage(db)
    sid = _scene(db, pid)
    res = srw.apply_rewrite(db, pid, sid, _GOOD, mode=srw.MODE_REPLACE, confirmed=True)
    assert res["ok"] and "slams the drawer" in db.get_scene_by_id(sid).content


def test_apply_preserves_outline_summary():
    db = Database()
    pid = _stage(db)
    sid = _scene(db, pid, summary="SUMMARY_KEPT")
    srw.apply_rewrite(db, pid, sid, _GOOD, mode=srw.MODE_REPLACE, confirmed=True)
    assert db.get_scene_by_id(sid).summary == "SUMMARY_KEPT"


def test_apply_preserves_beat_plan():
    db = Database()
    pid = _stage(db)
    sid = _scene(db, pid)
    ssp.save_beat_plan(db, pid, ssp.StageBeatPlan(scene_id=sid, objective="KEEP_OBJ"))
    srw.apply_rewrite(db, pid, sid, _GOOD, mode=srw.MODE_REPLACE, confirmed=True)
    assert ssp.get_beat_plan(db, pid, sid).objective == "KEEP_OBJ"


def test_apply_preserves_blocking_plan():
    db = Database()
    pid = _stage(db)
    sid = _scene(db, pid)
    ssp.save_blocking_plan(db, pid, ssp.BlockingCuePlan(scene_id=sid,
                                                        lighting_cues=["KEEP_L"]))
    srw.apply_rewrite(db, pid, sid, _GOOD, mode=srw.MODE_REPLACE, confirmed=True)
    assert ssp.get_blocking_plan(db, pid, sid).lighting_cues == ["KEEP_L"]


def test_apply_preserves_timeline_events():
    db = Database()
    pid = _stage(db)
    sid = _scene(db, pid)
    db.add_timeline_event(pid, sid)
    before = db.get_timeline_event_ids(pid)
    srw.apply_rewrite(db, pid, sid, _GOOD, mode=srw.MODE_REPLACE, confirmed=True)
    assert db.get_timeline_event_ids(pid) == before


def test_apply_preserves_psyke_data():
    db = Database()
    pid = _stage(db)
    sid = _scene(db, pid)
    db.create_psyke_entry(pid, "Maria", "character")
    before = len(db.get_all_psyke_entries(pid))
    srw.apply_rewrite(db, pid, sid, _GOOD, mode=srw.MODE_REPLACE, confirmed=True)
    assert len(db.get_all_psyke_entries(pid)) == before == 1


def test_apply_preserves_notes():
    db = Database()
    pid = _stage(db)
    sid = _scene(db, pid)
    db.create_note(pid, "Keep me", "note body")
    before = len(db.get_all_notes(pid))
    srw.apply_rewrite(db, pid, sid, _GOOD, mode=srw.MODE_REPLACE, confirmed=True)
    assert len(db.get_all_notes(pid)) == before


# ==========================================================================
# 30-33  Logos
# ==========================================================================


def test_logos_dropdown_includes_rewrite_actions():
    from logosforge.logos.controller import LogosController
    db = Database()
    db.create_project("ST", narrative_engine="stage_script",
                      default_writing_format="stage_script")
    names = [a.name for a in LogosController(db).available_actions(
        "Manuscript", writing_mode="stage_script")]
    assert "stage_rewrite_from_reflection" in names
    assert "stage_rewrite_block" in names and "stage_make_playable" in names


def test_rewrite_block_requires_selected_text():
    from logosforge.logos.controller import LogosController
    from logosforge.logos.context import build_logos_context
    db = Database()
    pid = _stage(db)
    sid = _scene(db, pid)
    ctl = LogosController(db, provider_resolver=lambda: object(),
                          chat_fn=lambda m, p: "x")
    ctx = build_logos_context(db, pid, section_name="Manuscript", current_scene_id=sid)
    res = ctl.run(ctx, "stage_rewrite_block")            # needs_selection
    assert not res.ok and "Select" in (res.error or "")


def test_full_scene_rewrite_action_runs_without_selection():
    from logosforge.logos.controller import LogosController
    from logosforge.logos.context import build_logos_context
    calls = []
    db = Database()
    pid = _stage(db)
    sid = _scene(db, pid)
    ctl = LogosController(
        db, provider_resolver=lambda: object(),
        chat_fn=lambda m, p: calls.append(1) or "SCENE: X\n\nSTAGE: New.")
    ctx = build_logos_context(db, pid, section_name="Manuscript", current_scene_id=sid)
    res = ctl.run(ctx, "stage_rewrite_from_reflection")  # no selection
    assert res.ok and calls == [1]
    assert db.get_scene_by_id(sid).content == _CONTENT   # not auto-applied


def test_logos_rewrite_does_not_auto_apply():
    from logosforge.logos.controller import LogosController
    from logosforge.logos.context import build_logos_context
    db = Database()
    pid = _stage(db)
    sid = _scene(db, pid)
    ctl = LogosController(db, provider_resolver=lambda: object(),
                          chat_fn=lambda m, p: "STAGE: Rewritten.")
    ctx = build_logos_context(db, pid, section_name="Manuscript",
                              current_scene_id=sid,
                              selected_text="STAGE: Maria stands by the window.")
    res = ctl.run(ctx, "stage_make_playable")
    assert res.ok
    assert db.get_scene_by_id(sid).content == _CONTENT


# ==========================================================================
# 34-36  Assistant / provider-error safety
# ==========================================================================


def test_assistant_rewrite_produces_preview_without_mutation():
    db = Database()
    pid = _stage(db)
    sid = _scene(db, pid)
    srw.build_rewrite_request(db, pid, sid, instruction="make_more_playable")
    prev = srw.build_rewrite_preview(db, pid, sid, _GOOD)
    assert prev.proposed_text and db.get_scene_by_id(sid).content == _CONTENT


def test_assistant_does_not_mutate_before_confirmation():
    db = Database()
    pid = _stage(db)
    sid = _scene(db, pid)
    res = srw.apply_rewrite(db, pid, sid, _GOOD, mode=srw.MODE_REPLACE,
                            confirmed=False)
    assert res["ok"] is False and db.get_scene_by_id(sid).content == _CONTENT


def test_provider_error_does_not_mutate():
    db = Database()
    pid = _stage(db)
    sid = _scene(db, pid)
    res = srw.apply_rewrite(db, pid, sid, "", mode=srw.MODE_REPLACE, confirmed=True)
    assert res["ok"] is False
    assert db.get_scene_by_id(sid).content == _CONTENT


# ==========================================================================
# Revision candidate + isolation + mode gating + no image gen
# ==========================================================================


def test_revision_candidate_requires_confirmation():
    db = Database()
    pid = _stage(db)
    sid = _scene(db, pid)
    res = srw.apply_rewrite(db, pid, sid, _GOOD, mode=srw.MODE_REVISION_CANDIDATE,
                            confirmed=False)
    assert res["ok"] is False and len(db.get_all_notes(pid)) == 0
    assert db.get_scene_by_id(sid).content == _CONTENT


def test_revision_candidate_saves_scene_linked_note():
    db = Database()
    pid = _stage(db)
    sid = _scene(db, pid)
    res = srw.apply_rewrite(db, pid, sid, _GOOD, mode=srw.MODE_REVISION_CANDIDATE,
                            confirmed=True, label="alt")
    assert res["ok"] and res["mutated"] is False
    assert res["note_id"] in db.get_scene_note_links(sid)
    assert db.get_scene_by_id(sid).content == _CONTENT


def test_rewrite_actions_gated_to_stage_script():
    from logosforge.logos.controller import LogosController
    db = Database()
    db.create_project("N", narrative_engine="novel")
    novel = [a.name for a in LogosController(db).available_actions(
        "Manuscript", writing_mode="novel")]
    assert "stage_rewrite_block" not in novel
    assert "stage_rewrite_from_reflection" not in novel


def test_rewrite_isolated_across_projects(tmp_path):
    db = Database(str(tmp_path / "st.db"))
    a = _stage(db, "A")
    sid_a = _scene(db, a)
    b = _stage(db, "B")
    sid_b = _scene(db, b, content="SCENE: B\n\nSTAGE: Project B scene.")
    srw.apply_rewrite(db, b, sid_b, "SCENE: B\n\nSTAGE: Project B rewritten.",
                      mode=srw.MODE_REPLACE, confirmed=True)
    assert db.get_scene_by_id(sid_a).content == _CONTENT


def test_no_image_generation_code():
    import os, tokenize
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = os.path.join(here, "logosforge", "stage_script_rewrite.py")
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
