"""Series Mode — Phase 5 acceptance suite.

Controlled Series rewrite: a targeted revision is always requested -> previewed
(with a block diff) -> confirmed -> applied through Controlled Apply. The AI never
overwrites the Manuscript; apply requires confirmation, touches only Scene.content,
and preserves Outline summaries / Season-Arc & Episode plans / Timeline / PSYKE /
Notes. Output stays Series teleplay blocks (no Stage cues, no Graphic Novel panels,
no novel prose). No image generation.
"""

from __future__ import annotations

import warnings

import pytest
from PySide6.QtWidgets import QApplication

warnings.filterwarnings("ignore")

from logosforge.db import Database
from logosforge import story_structure as ss
from logosforge import series_blocks as sbk
from logosforge import series_pipeline as spp
from logosforge import series_rewrite as srw


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
           chapter="Episode 1"):
    return ss.create_scene(db, pid, act=act, chapter=chapter, title=title,
                           content=content, summary=summary).id


_BODY = "INT. X - DAY\n\nOriginal action.\n\nMARIA\nOriginal line."
_NEW = "INT. NEW - NIGHT\n\nMaria slams the door.\n\nMARIA\nIt's over."


# ==========================================================================
# 1-6  Rewrite request
# ==========================================================================


def test_request_includes_scene_context():
    db = Database()
    pid = _series(db)
    sid = _scene(db, pid, content=_BODY, title="The Door", summary="Maria leaves")
    req = srw.build_rewrite_request(db, pid, sid)
    assert req.scene_title == "The Door" and req.original_body == _BODY
    assert req.act == "Act I" and req.episode_label == "Episode 1"


def test_request_includes_season_plan():
    db = Database()
    pid = _series(db)
    sid = _scene(db, pid, content=_BODY)
    spp.save_season_plan(db, pid, spp.SeasonArcPlan(act="Act I", premise="SEASON_X"))
    req = srw.build_rewrite_request(db, pid, sid)
    assert "SEASON_X" in req.season_plan_text


def test_request_includes_episode_plan():
    db = Database()
    pid = _series(db)
    sid = _scene(db, pid, content=_BODY)
    spp.save_episode_plan(db, pid, spp.EpisodeBeatPlan(chapter="Episode 1",
                                                       a_story="EP_X"))
    req = srw.build_rewrite_request(db, pid, sid)
    assert "EP_X" in req.episode_plan_text


def test_request_includes_reflection():
    db = Database()
    pid = _series(db)
    sid = _scene(db, pid, content=_BODY)
    req = srw.build_rewrite_request(db, pid, sid, include_reflection=True)
    assert "Scene Snapshot" in req.reflection_text


def test_request_includes_selected_text():
    db = Database()
    pid = _series(db)
    sid = _scene(db, pid, content=_BODY)
    req = srw.build_rewrite_request(db, pid, sid, selected_text="MARIA\nOriginal line.",
                                    target=srw.TARGET_SELECTION)
    assert req.selected_text == "MARIA\nOriginal line." and req.target == "selection"


def test_request_excludes_api_keys():
    db = Database()
    from logosforge.settings import get_manager
    get_manager().set("ai_api_key", "SECRET_KEY_SENTINEL")
    pid = _series(db)
    sid = _scene(db, pid, content=_BODY)
    req = srw.build_rewrite_request(db, pid, sid)
    blob = str(req.to_dict()) + srw.build_rewrite_prompt(req)
    assert "SECRET_KEY_SENTINEL" not in blob


# ==========================================================================
# 7-12  Output parsing + validation
# ==========================================================================


def test_valid_output_parses():
    script = srw.parse_rewrite_output(_NEW)
    kinds = {b.block_type for b in script.blocks}
    assert {sbk.BT_SCENE_HEADING, sbk.BT_ACTION, sbk.BT_CHARACTER,
            sbk.BT_DIALOGUE} <= kinds


def test_plain_text_adapts_safely():
    script = srw.parse_rewrite_output("Just a plain paragraph of description.")
    assert script.blocks and script.blocks[0].block_type == sbk.BT_ACTION
    assert srw.validate_rewrite_output(
        "Just a plain paragraph.", target=srw.TARGET_SCENE).is_valid


def test_markdown_fences_are_cleaned():
    v = srw.validate_rewrite_output("```\nINT. X - DAY\n\nAction.\n```",
                                    target=srw.TARGET_SCENE)
    assert v.is_valid and any("fence" in w.lower() for w in v.warnings)
    assert "```" not in sbk.serialize_series_script(
        srw.parse_rewrite_output("```\nINT. X - DAY\n\nAction.\n```"))


def test_unknown_gn_structure_is_rejected():
    v = srw.validate_rewrite_output("PAGE 1\n\nPANEL 1\nMaria stands in the doorway.",
                                    target=srw.TARGET_SCENE)
    assert v.is_valid is False


def test_system_prompt_leakage_is_rejected():
    v = srw.validate_rewrite_output(
        "As an AI language model, here is the scene you requested.",
        target=srw.TARGET_SCENE)
    assert v.is_valid is False


def test_stage_formatting_is_rejected():
    v = srw.validate_rewrite_output("STAGE: A bare room.\n\nMARIA\nHi.",
                                    target=srw.TARGET_SCENE)
    assert v.is_valid is False


# ==========================================================================
# 13-18  Preview
# ==========================================================================


def test_preview_does_not_mutate_body():
    db = Database()
    pid = _series(db)
    sid = _scene(db, pid, content=_BODY)
    srw.build_rewrite_preview(db, pid, sid, _NEW, target=srw.TARGET_SCENE)
    assert db.get_scene_by_id(sid).content == _BODY


def test_preview_shows_original_and_proposed():
    db = Database()
    pid = _series(db)
    sid = _scene(db, pid, content=_BODY)
    prev = srw.build_rewrite_preview(db, pid, sid, _NEW, target=srw.TARGET_SCENE)
    assert "Original action" in prev.original_text and "slams the door" in prev.proposed_text
    assert prev.block_diff and prev.changed_blocks >= 1


def test_preview_shows_target_description():
    db = Database()
    pid = _series(db)
    sid = _scene(db, pid, content=_BODY)
    prev = srw.build_rewrite_preview(db, pid, sid, _NEW, target=srw.TARGET_SCENE)
    assert prev.target_description == "Whole Series scene"
    prev_b = srw.build_rewrite_preview(db, pid, sid, "New action.",
                                       target=srw.TARGET_BLOCK, target_block_indices=[1])
    assert "block" in prev_b.target_description.lower()


def test_preview_shows_validation_warnings():
    db = Database()
    pid = _series(db)
    sid = _scene(db, pid, content=_BODY)
    prev = srw.build_rewrite_preview(db, pid, sid, "MARIA\nHi there.",
                                     target=srw.TARGET_SCENE)
    assert any("scene heading" in w.lower() for w in prev.warnings)


def test_cancel_leaves_body_unchanged():
    db = Database()
    pid = _series(db)
    sid = _scene(db, pid, content=_BODY)
    res = srw.apply_rewrite(db, pid, sid, _NEW, target=srw.TARGET_SCENE,
                            mode=srw.MODE_CANCEL, confirmed=True)
    assert res.get("cancelled") and db.get_scene_by_id(sid).content == _BODY


def test_copy_only_leaves_body_unchanged():
    db = Database()
    pid = _series(db)
    sid = _scene(db, pid, content=_BODY)
    res = srw.apply_rewrite(db, pid, sid, _NEW, target=srw.TARGET_SCENE,
                            mode=srw.MODE_COPY_ONLY, confirmed=True)
    assert res["ok"] and res.get("mutated") is False
    assert db.get_scene_by_id(sid).content == _BODY


# ==========================================================================
# 19-29  Controlled apply
# ==========================================================================


def test_block_replacement_mutates_only_target():
    db = Database()
    pid = _series(db)
    sid = _scene(db, pid, content=_BODY)   # [heading, action, character, dialogue]
    res = srw.apply_rewrite(db, pid, sid, "Maria hesitates at the threshold.",
                            target=srw.TARGET_BLOCK, target_block_indices=[1],
                            confirmed=True)
    assert res["ok"]
    body = db.get_scene_by_id(sid).content
    assert "hesitates at the threshold" in body            # block replaced
    assert "Original action" not in body                    # old block gone
    assert "INT. X - DAY" in body and "Original line" in body  # others preserved


def test_full_scene_replace_requires_confirmation():
    db = Database()
    pid = _series(db)
    sid = _scene(db, pid, content=_BODY)
    res = srw.apply_rewrite(db, pid, sid, _NEW, target=srw.TARGET_SCENE,
                            confirmed=False)
    assert res["ok"] is False and db.get_scene_by_id(sid).content == _BODY


def test_append_as_alternate_preserves_original():
    db = Database()
    pid = _series(db)
    sid = _scene(db, pid, content=_BODY)
    res = srw.apply_rewrite(db, pid, sid, _NEW, target=srw.TARGET_SCENE,
                            mode=srw.MODE_APPEND_ALTERNATE, confirmed=True)
    assert res["ok"]
    body = db.get_scene_by_id(sid).content
    assert "Original action" in body and "slams the door" in body


def test_apply_marks_dirty_and_refreshes():
    db = Database()
    pid = _series(db)
    sid = _scene(db, pid, content=_BODY)
    from logosforge.project_events import get_event_bus
    fired = []
    get_event_bus().project_data_changed.connect(lambda *a: fired.append(1))
    srw.apply_rewrite(db, pid, sid, _NEW, target=srw.TARGET_SCENE, confirmed=True)
    assert fired


def test_apply_preserves_outline_summary():
    db = Database()
    pid = _series(db)
    sid = _scene(db, pid, content=_BODY, summary="SUMMARY_KEPT")
    srw.apply_rewrite(db, pid, sid, _NEW, target=srw.TARGET_SCENE, confirmed=True)
    assert db.get_scene_by_id(sid).summary == "SUMMARY_KEPT"


def test_apply_preserves_plans_timeline_psyke_notes():
    db = Database()
    pid = _series(db)
    sid = _scene(db, pid, content=_BODY, act="Act I", chapter="Episode 1")
    spp.save_season_plan(db, pid, spp.SeasonArcPlan(act="Act I", premise="KEEP_S"))
    spp.save_episode_plan(db, pid, spp.EpisodeBeatPlan(chapter="Episode 1",
                                                       a_story="KEEP_E"))
    db.add_timeline_event(pid, sid)
    db.create_psyke_entry(pid, "Maria", "character")
    db.create_note(pid, "n", "b")
    tl = db.get_timeline_event_ids(pid)
    psyke = len(db.get_all_psyke_entries(pid))
    notes = len(db.get_all_notes(pid))
    srw.apply_rewrite(db, pid, sid, _NEW, target=srw.TARGET_SCENE, confirmed=True)
    assert spp.get_season_plan(db, pid, "Act I").premise == "KEEP_S"
    assert spp.get_episode_plan(db, pid, "Episode 1").a_story == "KEEP_E"
    assert db.get_timeline_event_ids(pid) == tl
    assert len(db.get_all_psyke_entries(pid)) == psyke
    assert len(db.get_all_notes(pid)) == notes


def test_revision_candidate_does_not_mutate_body():
    db = Database()
    pid = _series(db)
    sid = _scene(db, pid, content=_BODY)
    res = srw.apply_rewrite(db, pid, sid, _NEW, target=srw.TARGET_SCENE,
                            mode=srw.MODE_REVISION_CANDIDATE, confirmed=True,
                            label="alt 1")
    assert res["ok"] and res.get("mutated") is False
    assert db.get_scene_by_id(sid).content == _BODY
    assert sid in db.get_note_scene_links(res["note_id"])


# ==========================================================================
# 30-34  Logos
# ==========================================================================


def _series_actions(db):
    from logosforge.logos.controller import LogosController
    return list(LogosController(db).available_actions("Manuscript",
                                                      writing_mode="series"))


def test_logos_includes_rewrite_actions():
    db = Database()
    _series(db)
    names = {a.name for a in _series_actions(db)}
    assert {"series_rewrite_scene", "series_rewrite_block", "series_tighten_dialogue",
            "series_rewrite_from_reflection"} <= names


def test_rewrite_block_requires_selection():
    db = Database()
    _series(db)
    block = next(a for a in _series_actions(db) if a.name == "series_rewrite_block")
    assert block.needs_selection is True
    scene = next(a for a in _series_actions(db) if a.name == "series_rewrite_scene")
    assert scene.needs_selection is False


def test_full_scene_rewrite_runs_without_selection_no_auto_apply():
    from logosforge.logos.controller import LogosController
    from logosforge.logos.context import build_logos_context
    db = Database()
    pid = _series(db)
    sid = _scene(db, pid, content=_BODY)
    ctl = LogosController(db, provider_resolver=lambda: object(),
                         chat_fn=lambda m, p: _NEW)
    ctx = build_logos_context(db, pid, section_name="Manuscript", current_scene_id=sid)
    res = ctl.run(ctx, "series_rewrite_scene")
    assert res.ok
    assert db.get_scene_by_id(sid).content == _BODY   # generative preview, no auto-apply


def test_reflection_rewrite_runs_from_scene_context():
    from logosforge.logos.controller import LogosController
    from logosforge.logos.context import build_logos_context
    db = Database()
    pid = _series(db)
    sid = _scene(db, pid, content=_BODY)
    ctl = LogosController(db, provider_resolver=lambda: object(),
                         chat_fn=lambda m, p: _NEW)
    ctx = build_logos_context(db, pid, section_name="Manuscript", current_scene_id=sid)
    res = ctl.run(ctx, "series_rewrite_from_reflection")
    assert res.ok and db.get_scene_by_id(sid).content == _BODY


def test_block_rewrite_without_selection_does_not_mutate():
    from logosforge.logos.controller import LogosController
    from logosforge.logos.context import build_logos_context
    db = Database()
    pid = _series(db)
    sid = _scene(db, pid, content=_BODY)
    ctl = LogosController(db, provider_resolver=lambda: object(),
                         chat_fn=lambda m, p: _NEW)
    ctx = build_logos_context(db, pid, section_name="Manuscript", current_scene_id=sid)
    ctl.run(ctx, "series_rewrite_block")   # no selection -> central guard
    assert db.get_scene_by_id(sid).content == _BODY


# ==========================================================================
# 35-37  Assistant safety
# ==========================================================================


def test_assistant_rewrite_produces_preview_without_mutation():
    db = Database()
    pid = _series(db)
    sid = _scene(db, pid, content=_BODY)
    prev = srw.build_rewrite_preview(db, pid, sid, _NEW, target=srw.TARGET_SCENE)
    assert prev.proposed_text and db.get_scene_by_id(sid).content == _BODY


def test_no_mutation_before_confirmation():
    db = Database()
    pid = _series(db)
    sid = _scene(db, pid, content=_BODY)
    res = srw.apply_rewrite(db, pid, sid, _NEW, target=srw.TARGET_SCENE,
                            confirmed=False)
    assert res["ok"] is False and db.get_scene_by_id(sid).content == _BODY


def test_provider_error_does_not_mutate():
    db = Database()
    pid = _series(db)
    sid = _scene(db, pid, content=_BODY)
    # An empty generation (failed provider) is invalid -> apply is blocked.
    res = srw.apply_rewrite(db, pid, sid, "", target=srw.TARGET_SCENE, confirmed=True)
    assert res["ok"] is False and db.get_scene_by_id(sid).content == _BODY


# ==========================================================================
# Regression guards
# ==========================================================================


def test_no_image_generation_in_rewrite():
    import os, tokenize
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = os.path.join(here, "logosforge", "series_rewrite.py")
    toks = []
    with open(src, "rb") as fh:
        for tok in tokenize.tokenize(fh.readline):
            name = tokenize.tok_name[tok.type]
            if tok.type == tokenize.COMMENT or name.endswith("STRING"):
                continue
            toks.append(tok.string.lower())
    skeleton = " ".join(toks)
    for banned in ("comfyui", "image generation", "image prompt", "lora",
                   "stable diffusion", "img2img", "txt2img"):
        assert banned not in skeleton, banned


def test_rewrite_actions_absent_from_other_modes():
    from logosforge.logos.controller import LogosController
    db = Database()
    for engine in ("novel", "screenplay", "graphic_novel", "stage_script"):
        db.create_project(engine, narrative_engine=engine,
                          default_writing_format=engine)
        names = [a.name for a in LogosController(db).available_actions(
            "Manuscript", writing_mode=engine)]
        assert not any(n.startswith("series_") for n in names)
