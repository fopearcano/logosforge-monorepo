"""Graphic Novel Mode — Phase 5 acceptance suite.

Controlled rewrite: targeted revision request → preview (with a page/panel diff +
validation) → confirmed apply. The AI never overwrites the body; apply requires
confirmation, touches only Scene.content, and preserves Outline / page breakdown /
panel plan / Timeline / PSYKE / Notes. Explicitly no image generation.
"""

from __future__ import annotations

import warnings

import pytest
from PySide6.QtWidgets import QApplication

warnings.filterwarnings("ignore")

from logosforge.db import Database
from logosforge import story_structure as ss
from logosforge import graphic_novel_pipeline as gp
from logosforge import graphic_novel_rewrite as grw


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


def _gn(db, title="GN"):
    return db.create_project(title, narrative_engine="graphic_novel",
                             default_writing_format="graphic_novel").id


_CONTENT = ("PAGE 1\n\n"
            "PANEL 1\nVisual: INT. kitchen. Maria stands by the window.\n"
            "Dialogue: MARIA: Hello.\n\n"
            "PANEL 2\nVisual: John steps into the room.\n"
            "Dialogue: JOHN: Go away.\n")
_GOOD = ("PAGE 1\n\n"
         "PANEL 1\nVisual: INT. kitchen. Maria slams the drawer shut.\n"
         "Dialogue: MARIA: Look at me.\n\n"
         "PANEL 2\nVisual: John freezes in the doorway.\n"
         "Dialogue: JOHN: No.\n")
_PANEL_NEW = "Visual: Maria hurls the glass at the wall.\nSFX: CRASH\n"
_PAGE_NEW = ("PANEL 1\nVisual: Maria turns to leave.\n\n"
             "PANEL 2\nVisual: The door slams behind her.\nSFX: BANG\n")
_TWO_PAGE = ("PAGE 1\n\nPANEL 1\nVisual: Page one establishing shot.\n\n"
             "PAGE 2\n\nPANEL 1\nVisual: Page two quiet moment.\n")


def _scene(db, pid, *, content=_CONTENT, summary="Maria pushes John", title="Confront"):
    return ss.create_scene(db, pid, act="Act I", chapter="Chapter 1",
                           title=title, content=content, summary=summary).id


# ==========================================================================
# 1-7  Rewrite request
# ==========================================================================


def test_request_includes_scene_context():
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid)
    req = grw.build_rewrite_request(db, pid, sid, instruction="make_more_visual")
    assert req.scene_title == "Confront"
    assert "Maria pushes John" in req.outline_summary
    assert req.original_body == _CONTENT
    assert req.writing_mode == "graphic_novel"


def test_request_includes_breakdown_when_available():
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid)
    gp.save_page_breakdown(db, pid, gp.PageBreakdown(scene_id=sid,
                                                     pacing_goal="build tension"))
    req = grw.build_rewrite_request(db, pid, sid)
    assert "build tension" in req.breakdown_text


def test_request_includes_plan_when_available():
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid)
    gp.save_panel_plan(db, pid, gp.PanelPlan(scene_id=sid, pages=[gp.PlannedPage(
        number=1, panels=[gp.PlannedPanel(visual_beat="establishing shot")])]))
    req = grw.build_rewrite_request(db, pid, sid)
    assert "establishing shot" in req.plan_text


def test_request_includes_reflection_report():
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid)
    req = grw.build_rewrite_request(db, pid, sid, instruction="from_reflection")
    assert "Reader Perspective" in req.reflection_text


def test_request_includes_selected_panel():
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid)
    req = grw.build_rewrite_request(db, pid, sid, selected_text=_PANEL_NEW,
                                    target=grw.TARGET_PANEL, target_page=1,
                                    target_panel=1)
    assert req.selected_text == _PANEL_NEW and req.target == grw.TARGET_PANEL
    assert req.target_page == 1 and req.target_panel == 1


def test_request_excludes_api_keys():
    db = Database()
    from logosforge.settings import get_manager
    get_manager().set("ai_api_key", "SECRET_KEY_SENTINEL")
    pid = _gn(db)
    sid = _scene(db, pid)
    req = grw.build_rewrite_request(db, pid, sid, instruction="from_reflection")
    blob = str(req.to_dict()) + grw.build_rewrite_prompt(req)
    assert "SECRET_KEY_SENTINEL" not in blob
    assert not any("api" in k.lower() or "secret" in k.lower() or k.lower() == "key"
                   for k in req.to_dict())


def test_request_excludes_image_settings():
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid)
    req = grw.build_rewrite_request(db, pid, sid)
    blob = (str(req.to_dict()) + grw.build_rewrite_prompt(req)).lower()
    for banned in ("comfyui", "image generation", "lora", "stable diffusion"):
        assert banned not in blob


# ==========================================================================
# 8-13  Output parsing + validation
# ==========================================================================


def test_valid_output_parses():
    script = grw.parse_rewrite_output(_GOOD)
    assert len(script.pages) == 1 and len(script.pages[0].panels) == 2
    assert "slams the drawer" in script.pages[0].panels[0].visual_description


def test_plain_text_output_adapts_or_validates():
    text = "Maria crosses the room and opens the window."
    script = grw.parse_rewrite_output(text)
    assert script.panel_count() >= 1
    assert grw.validate_rewrite_output(text, target=grw.TARGET_SCENE).is_valid


def test_markdown_fences_are_cleaned():
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid)
    fenced = "```\nPAGE 1\n\nPANEL 1\nVisual: A clean panel.\n```"
    assert grw.validate_rewrite_output(fenced, target=grw.TARGET_SCENE).is_valid
    prev = grw.build_rewrite_preview(db, pid, sid, fenced)
    assert "```" not in prev.proposed_text


def test_unknown_field_degrades_safely():
    text = "PAGE 1\n\nPANEL 1\nVisual: x.\nFoobar: y.\n"
    script = grw.parse_rewrite_output(text)
    assert script.panel_count() == 1                     # absorbed, never corrupt
    assert grw.validate_rewrite_output(text, target=grw.TARGET_SCENE).is_valid


def test_system_prompt_leakage_is_rejected():
    v = grw.validate_rewrite_output("As an AI language model, here is the script.",
                                    target=grw.TARGET_SCENE)
    assert not v.is_valid and v.errors


def test_image_generation_leakage_is_rejected():
    text = ("PAGE 1\n\nPANEL 1\nVisual: a hero.\n"
            "Notes: comfyui workflow, stable diffusion prompt, lora: hero.\n")
    v = grw.validate_rewrite_output(text, target=grw.TARGET_SCENE)
    assert not v.is_valid and v.errors


# ==========================================================================
# 14-19  Preview
# ==========================================================================


def test_preview_does_not_mutate_body():
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid)
    grw.build_rewrite_preview(db, pid, sid, _GOOD)
    assert db.get_scene_by_id(sid).content == _CONTENT


def test_preview_shows_original_and_proposed():
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid)
    prev = grw.build_rewrite_preview(db, pid, sid, _GOOD)
    assert prev.original_text == _CONTENT
    assert "slams the drawer" in prev.proposed_text
    assert prev.panel_diff and "panels_changed" in prev.panel_diff


def test_preview_shows_target():
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid)
    prev = grw.build_rewrite_preview(db, pid, sid, _PANEL_NEW,
                                     target=grw.TARGET_PANEL, target_page=1,
                                     target_panel=1)
    assert prev.target == grw.TARGET_PANEL
    assert prev.target_page == 1 and prev.target_panel == 1


def test_preview_surfaces_validation_warnings():
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid)
    prev = grw.build_rewrite_preview(
        db, pid, sid, "PAGE 1\n\nPANEL 1\nDialogue: BOB: hi there friend.\n",
        target=grw.TARGET_SCENE)
    assert prev.can_apply and prev.warnings


def test_cancel_leaves_body_unchanged():
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid)
    res = grw.apply_rewrite(db, pid, sid, _GOOD, mode=grw.MODE_CANCEL, confirmed=True)
    assert res["ok"] is False and res.get("cancelled")
    assert db.get_scene_by_id(sid).content == _CONTENT


def test_copy_only_leaves_body_unchanged():
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid)
    res = grw.apply_rewrite(db, pid, sid, _GOOD, mode=grw.MODE_COPY_ONLY,
                            confirmed=True)
    assert res["ok"] and res["mutated"] is False
    assert db.get_scene_by_id(sid).content == _CONTENT


# ==========================================================================
# 20-31  Apply
# ==========================================================================


def test_apply_selected_panel_replaces_only_that_panel():
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid)
    res = grw.apply_rewrite(db, pid, sid, _PANEL_NEW, target=grw.TARGET_PANEL,
                            target_page=1, target_panel=1, mode=grw.MODE_REPLACE,
                            confirmed=True)
    body = db.get_scene_by_id(sid).content
    assert res["ok"]
    assert "hurls the glass" in body
    assert "John steps into the room" in body            # panel 2 preserved
    assert "Maria stands by the window" not in body       # panel 1 replaced


def test_apply_selected_page_replaces_only_that_page():
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid, content=_TWO_PAGE)
    res = grw.apply_rewrite(db, pid, sid, _PAGE_NEW, target=grw.TARGET_PAGE,
                            target_page=2, mode=grw.MODE_REPLACE, confirmed=True)
    body = db.get_scene_by_id(sid).content
    assert res["ok"]
    assert "The door slams behind her" in body            # page 2 replaced
    assert "Page one establishing shot" in body           # page 1 preserved
    assert "Page two quiet moment" not in body            # page 2 old content gone


def test_full_scene_replace_requires_confirmation():
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid)
    res = grw.apply_rewrite(db, pid, sid, _GOOD, mode=grw.MODE_REPLACE,
                            confirmed=False)
    assert res["ok"] is False
    assert db.get_scene_by_id(sid).content == _CONTENT


def test_append_alternate_does_not_overwrite_original():
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid)
    res = grw.apply_rewrite(db, pid, sid, _GOOD, mode=grw.MODE_APPEND_ALTERNATE,
                            confirmed=True)
    body = db.get_scene_by_id(sid).content
    assert res["ok"]
    assert "Maria stands by the window" in body           # original preserved
    assert "slams the drawer" in body                     # alternate appended


def test_apply_marks_project_dirty():
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid)
    from logosforge.project_events import get_event_bus
    fired = []
    get_event_bus().project_data_changed.connect(lambda *a: fired.append(1))
    grw.apply_rewrite(db, pid, sid, _GOOD, mode=grw.MODE_REPLACE, confirmed=True)
    assert fired                                          # marks dirty / refresh


def test_apply_updates_body_for_manuscript_refresh():
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid)
    res = grw.apply_rewrite(db, pid, sid, _GOOD, mode=grw.MODE_REPLACE,
                            confirmed=True)
    assert res["ok"] and "slams the drawer" in db.get_scene_by_id(sid).content


def test_apply_preserves_outline_summary():
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid, summary="SUMMARY_KEPT")
    grw.apply_rewrite(db, pid, sid, _GOOD, mode=grw.MODE_REPLACE, confirmed=True)
    assert db.get_scene_by_id(sid).summary == "SUMMARY_KEPT"


def test_apply_preserves_page_breakdown():
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid)
    gp.save_page_breakdown(db, pid, gp.PageBreakdown(scene_id=sid,
                                                     pacing_goal="KEEP_PACING"))
    grw.apply_rewrite(db, pid, sid, _GOOD, mode=grw.MODE_REPLACE, confirmed=True)
    assert gp.get_page_breakdown(db, pid, sid).pacing_goal == "KEEP_PACING"


def test_apply_preserves_panel_plan():
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid)
    gp.save_panel_plan(db, pid, gp.PanelPlan(scene_id=sid, pages=[gp.PlannedPage(
        number=1, panels=[gp.PlannedPanel(visual_beat="KEEP_BEAT")])]))
    grw.apply_rewrite(db, pid, sid, _GOOD, mode=grw.MODE_REPLACE, confirmed=True)
    plan = gp.get_panel_plan(db, pid, sid)
    assert plan.pages[0].panels[0].visual_beat == "KEEP_BEAT"


def test_apply_preserves_timeline_events():
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid)
    db.add_timeline_event(pid, sid)
    before = db.get_timeline_event_ids(pid)
    grw.apply_rewrite(db, pid, sid, _GOOD, mode=grw.MODE_REPLACE, confirmed=True)
    assert db.get_timeline_event_ids(pid) == before


def test_apply_preserves_psyke_data():
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid)
    db.create_psyke_entry(pid, "Maria", "character")
    before = len(db.get_all_psyke_entries(pid))
    grw.apply_rewrite(db, pid, sid, _GOOD, mode=grw.MODE_REPLACE, confirmed=True)
    assert len(db.get_all_psyke_entries(pid)) == before == 1


def test_apply_preserves_notes():
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid)
    db.create_note(pid, "Keep me", "note body")
    before = len(db.get_all_notes(pid))
    grw.apply_rewrite(db, pid, sid, _GOOD, mode=grw.MODE_REPLACE, confirmed=True)
    assert len(db.get_all_notes(pid)) == before


# ==========================================================================
# 32-35  Logos
# ==========================================================================


def test_logos_dropdown_includes_gn_rewrite_actions():
    from logosforge.logos.controller import LogosController
    db = Database()
    db.create_project("G", narrative_engine="graphic_novel")
    names = [a.name for a in LogosController(db).available_actions(
        "Manuscript", writing_mode="graphic_novel")]
    assert "gn_rewrite_from_reflection" in names
    assert "gn_rewrite_panel" in names
    assert "gn_make_more_visual" in names


def test_rewrite_panel_requires_selected_text():
    from logosforge.logos.controller import LogosController
    from logosforge.logos.context import build_logos_context
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid)
    ctl = LogosController(db, provider_resolver=lambda: object(),
                          chat_fn=lambda m, p: "x")
    ctx = build_logos_context(db, pid, section_name="Manuscript",
                              current_scene_id=sid)
    res = ctl.run(ctx, "gn_rewrite_panel")               # needs_selection
    assert not res.ok and "Select some text" in (res.error or "")


def test_full_scene_rewrite_action_runs_without_selection():
    from logosforge.logos.controller import LogosController
    from logosforge.logos.context import build_logos_context
    calls = []
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid)
    ctl = LogosController(
        db, provider_resolver=lambda: object(),
        chat_fn=lambda m, p: calls.append(1) or "PAGE 1\n\nPANEL 1\nVisual: New.")
    ctx = build_logos_context(db, pid, section_name="Manuscript",
                              current_scene_id=sid)
    res = ctl.run(ctx, "gn_rewrite_from_reflection")     # no selection
    assert res.ok and calls == [1]
    assert db.get_scene_by_id(sid).content == _CONTENT   # not auto-applied


def test_logos_rewrite_does_not_auto_apply():
    from logosforge.logos.controller import LogosController
    from logosforge.logos.context import build_logos_context
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid)
    ctl = LogosController(
        db, provider_resolver=lambda: object(),
        chat_fn=lambda m, p: "PANEL 1\nVisual: Rewritten panel.")
    ctx = build_logos_context(db, pid, section_name="Manuscript",
                              current_scene_id=sid,
                              selected_text="Visual: INT. kitchen. Maria stands by the window.")
    res = ctl.run(ctx, "gn_make_more_visual")
    assert res.ok
    assert db.get_scene_by_id(sid).content == _CONTENT


# ==========================================================================
# 36-38  Assistant / provider-error safety
# ==========================================================================


def test_assistant_rewrite_produces_preview_without_mutation():
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid)
    grw.build_rewrite_request(db, pid, sid, instruction="make_more_visual")
    prev = grw.build_rewrite_preview(db, pid, sid, _GOOD)
    assert prev.proposed_text and db.get_scene_by_id(sid).content == _CONTENT


def test_assistant_does_not_mutate_before_confirmation():
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid)
    res = grw.apply_rewrite(db, pid, sid, _GOOD, mode=grw.MODE_REPLACE,
                            confirmed=False)
    assert res["ok"] is False and db.get_scene_by_id(sid).content == _CONTENT


def test_provider_error_does_not_mutate():
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid)
    res = grw.apply_rewrite(db, pid, sid, "", mode=grw.MODE_REPLACE, confirmed=True)
    assert res["ok"] is False
    assert db.get_scene_by_id(sid).content == _CONTENT


# ==========================================================================
# 39-41  No image generation
# ==========================================================================


def test_no_image_generation_code_or_actions():
    import os, tokenize
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = os.path.join(here, "logosforge", "graphic_novel_rewrite.py")
    code_tokens = []
    with open(src, "rb") as fh:
        for tok in tokenize.tokenize(fh.readline):
            name = tokenize.tok_name[tok.type]
            if tok.type == tokenize.COMMENT or name.endswith("STRING"):
                continue
            code_tokens.append(tok.string.lower())
    skeleton = " ".join(code_tokens)
    for banned in ("comfyui", "image generation", "image prompt", "lora",
                   "render", "stable diffusion", "img2img", "txt2img"):
        assert banned not in skeleton, banned
    from logosforge.logos import actions as A
    names = " ".join(a.name + " " + a.label for a in A.list_actions()).lower()
    for banned in ("comfyui", "image gen", "generate image", "image prompt"):
        assert banned not in names


def test_no_image_provider_setting_required():
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid)
    prev = grw.build_rewrite_preview(db, pid, sid, _GOOD)
    assert prev.proposed_text


# ==========================================================================
# Revision candidate + isolation + mode gating
# ==========================================================================


def test_revision_candidate_requires_confirmation():
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid)
    res = grw.apply_rewrite(db, pid, sid, _GOOD, mode=grw.MODE_REVISION_CANDIDATE,
                            confirmed=False)
    assert res["ok"] is False
    assert len(db.get_all_notes(pid)) == 0
    assert db.get_scene_by_id(sid).content == _CONTENT


def test_revision_candidate_saves_scene_linked_note():
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid)
    res = grw.apply_rewrite(db, pid, sid, _GOOD, mode=grw.MODE_REVISION_CANDIDATE,
                            confirmed=True, label="alt")
    assert res["ok"] and res["mutated"] is False
    assert res["note_id"] in db.get_scene_note_links(sid)
    assert db.get_scene_by_id(sid).content == _CONTENT    # body untouched


def test_gn_rewrite_actions_gated_to_graphic_novel():
    from logosforge.logos.controller import LogosController
    db = Database()
    db.create_project("N", narrative_engine="novel")
    novel = [a.name for a in LogosController(db).available_actions(
        "Manuscript", writing_mode="novel")]
    assert "gn_rewrite_panel" not in novel
    assert "gn_rewrite_from_reflection" not in novel


def test_rewrite_isolated_across_projects(tmp_path):
    db = Database(str(tmp_path / "gn.db"))
    a = _gn(db, "A")
    sid_a = _scene(db, a)
    b = _gn(db, "B")
    sid_b = _scene(db, b, content="PAGE 1\n\nPANEL 1\nVisual: Project B scene.\n")
    grw.apply_rewrite(db, b, sid_b, "PAGE 1\n\nPANEL 1\nVisual: Project B rewritten.\n",
                      mode=grw.MODE_REPLACE, confirmed=True)
    assert db.get_scene_by_id(sid_a).content == _CONTENT  # project A untouched
