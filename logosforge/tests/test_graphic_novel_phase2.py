"""Graphic Novel Mode — Phase 2 acceptance suite (page/panel planning pipeline).

Outline summary → page breakdown → panel plan → panel-script draft preview →
confirmed apply. The AI never overwrites the body: planning artifacts are stored
separately (project settings), generation only previews, and the draft reaches
Scene.content only through Controlled Apply with explicit confirmation.
"""

from __future__ import annotations

import warnings

import pytest
from PySide6.QtWidgets import QApplication

warnings.filterwarnings("ignore")

from logosforge.db import Database
from logosforge import story_structure as ss
from logosforge import graphic_novel_pipeline as gp
from logosforge import graphic_novel_blocks as gnb


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


def _scene(db, pid, *, summary="Hero confronts villain", content=""):
    return ss.create_scene(db, pid, act="Act I", chapter="Ch1", title="S",
                           summary=summary, content=content).id


_BD_TEXT = ("Target Pages: 3\nPacing Goal: build to reveal\nPage Turns: page 2\n"
            "Emotional Progression: dread to resolve\nVisual Rhythm: wide then tight\n"
            "Continuity Notes: the locket\nPage Summaries:\n- approach\n"
            "- confrontation\n- aftermath")
_PLAN_TEXT = ("PAGE 1\nPANEL 1\nVisual beat: hero lands\nAction: rolls\n"
              "Framing: low\nCaption: Three years.\nDialogue: HERO: It ends.\n"
              "SFX: THUD\nTransition: cut\nPANEL 2\nVisual beat: villain turns\n"
              "PAGE 2\nPANEL 1\nVisual beat: clash")
_DRAFT = ("PAGE 1: Approach\n\nPANEL 1\nVisual: Hero lands on the gravel.\n"
          "Caption: Three years.\nDialogue: HERO: It ends now.\nSFX: THUD\n"
          "Notes: low angle\n\nPANEL 2\nVisual: The villain turns.")


# ==========================================================================
# 1-6  Page breakdown
# ==========================================================================


def test_page_breakdown_prompt_uses_summary():
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid, summary="Hero confronts villain on the rooftop")
    prompt = gp.build_page_breakdown_prompt(db, pid, sid)
    assert "Hero confronts villain on the rooftop" in prompt
    assert "Target Pages:" in prompt and "Graphic Novel" in prompt


def test_page_breakdown_stored_separately_from_body():
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid, content="EXISTING BODY", summary="OUTLINE SUMMARY")
    bd = gp.parse_page_breakdown_response(_BD_TEXT, scene_id=sid)
    gp.save_page_breakdown(db, pid, bd)
    assert gp.get_page_breakdown(db, pid, sid).target_page_count == 3
    after = db.get_scene_by_id(sid)
    assert after.content == "EXISTING BODY" and after.summary == "OUTLINE SUMMARY"


def test_accept_page_breakdown_stores_it():
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid)
    gp.save_page_breakdown(db, pid, gp.parse_page_breakdown_response(_BD_TEXT, sid))
    assert gp.has_page_breakdown(db, pid, sid)
    assert gp.clear_page_breakdown(db, pid, sid) is True
    assert gp.get_page_breakdown(db, pid, sid) is None


def test_discard_page_breakdown_changes_nothing():
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid, content="BODY")
    # Parsing + not saving = discard.
    gp.parse_page_breakdown_response(_BD_TEXT, scene_id=sid)
    assert gp.get_page_breakdown(db, pid, sid) is None
    assert db.get_scene_by_id(sid).content == "BODY"


def test_page_breakdown_project_bound_and_isolated(tmp_path):
    db = Database(str(tmp_path / "gn.db"))
    a = _gn(db, "A")
    sa = _scene(db, a)
    gp.save_page_breakdown(db, a, gp.parse_page_breakdown_response(_BD_TEXT, sa))
    b = _gn(db, "B")
    assert gp.get_page_breakdown(db, b, sa) is None       # no leak across projects


# ==========================================================================
# 7-11  Panel plan
# ==========================================================================


def test_panel_plan_prompt_uses_breakdown():
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid)
    gp.save_page_breakdown(db, pid, gp.parse_page_breakdown_response(_BD_TEXT, sid))
    prompt = gp.build_panel_plan_prompt(db, pid, sid)
    assert "build to reveal" in prompt


def test_panel_plan_parse_and_store_separately():
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid, content="BODY")
    plan = gp.parse_panel_plan_response(_PLAN_TEXT, scene_id=sid)
    assert len(plan.pages) == 2 and len(plan.pages[0].panels) == 2
    assert plan.pages[0].panels[0].visual_beat == "hero lands"
    gp.save_panel_plan(db, pid, plan)
    assert gp.has_panel_plan(db, pid, sid)
    assert db.get_scene_by_id(sid).content == "BODY"      # body untouched


def test_discard_panel_plan_changes_nothing():
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid)
    gp.parse_panel_plan_response(_PLAN_TEXT, scene_id=sid)   # not saved
    assert gp.get_panel_plan(db, pid, sid) is None


def test_panel_plan_project_bound(tmp_path):
    db = Database(str(tmp_path / "gn.db"))
    a = _gn(db, "A")
    sa = _scene(db, a)
    gp.save_panel_plan(db, a, gp.parse_panel_plan_response(_PLAN_TEXT, sa))
    b = _gn(db, "B")
    assert gp.get_panel_plan(db, b, sa) is None


# ==========================================================================
# 12-16  Draft preview
# ==========================================================================


def test_draft_returns_page_panel_structure():
    script = gp.parse_draft_response(_DRAFT)
    assert len(script.pages) == 1 and len(script.pages[0].panels) == 2
    assert script.pages[0].panels[0].visual_description == "Hero lands on the gravel."


def test_draft_preview_does_not_auto_apply():
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid, content="")
    script = gp.parse_draft_response(_DRAFT, scene_id=sid)
    prev = gp.preview_draft_apply(db, pid, sid, script, mode=gp.APPLY_REPLACE)
    assert prev is not None
    assert db.get_scene_by_id(sid).content == ""           # NOT applied


def test_invalid_draft_rejected():
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid, content="")
    empty = gnb.GraphicNovelScript()
    res = gp.apply_draft(db, pid, sid, empty, mode=gp.APPLY_TO_EMPTY, confirmed=True)
    assert res["ok"] is False and "validation" in res
    assert db.get_scene_by_id(sid).content == ""


def test_provider_error_or_empty_does_not_mutate():
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid, content="")
    # Empty generation -> invalid -> blocked, no mutation (models a failed call).
    res = gp.apply_draft(db, pid, sid, gp.parse_draft_response(""),
                         mode=gp.APPLY_REPLACE, confirmed=True)
    assert res["ok"] is False and db.get_scene_by_id(sid).content == ""


def test_markdown_fence_leak_rejected():
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid, content="")
    # Fences inside a panel field (not stripped by parse) -> blocked.
    bad = gnb.parse_graphic_novel_text("PAGE 1\n\nPANEL 1\nVisual: ```fountain")
    res = gp.apply_draft(db, pid, sid, bad, mode=gp.APPLY_TO_EMPTY, confirmed=True)
    assert res["ok"] is False
    # And a clean fenced reply parses fine once fences are stripped.
    clean = gp.parse_draft_response("```\nPAGE 1\n\nPANEL 1\nVisual: ok.\n```")
    assert gp.validate_draft_script(clean).is_valid


# ==========================================================================
# 17-26  Controlled apply
# ==========================================================================


def test_apply_to_empty_writes_pages_panels():
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid, content="")
    res = gp.apply_draft(db, pid, sid, gp.parse_draft_response(_DRAFT),
                         mode=gp.APPLY_TO_EMPTY, confirmed=True)
    assert res["ok"] and "Hero lands on the gravel." in db.get_scene_by_id(sid).content


def test_replace_requires_confirmation():
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid, content="PAGE 1\n\nPANEL 1\nVisual: old.")
    res = gp.apply_draft(db, pid, sid, gp.parse_draft_response(_DRAFT),
                         mode=gp.APPLY_REPLACE, confirmed=False)
    assert res["ok"] is False and "old." in db.get_scene_by_id(sid).content


def test_apply_to_empty_refused_on_nonempty():
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid, content="PAGE 1\n\nPANEL 1\nVisual: keep.")
    res = gp.apply_draft(db, pid, sid, gp.parse_draft_response(_DRAFT),
                         mode=gp.APPLY_TO_EMPTY, confirmed=True)
    assert res["ok"] is False and "keep." in db.get_scene_by_id(sid).content


def test_append_adds_pages_without_overwriting():
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid, content="PAGE 1\n\nPANEL 1\nVisual: keep this.")
    res = gp.apply_draft(db, pid, sid, gp.parse_draft_response(_DRAFT),
                         mode=gp.APPLY_APPEND, confirmed=True)
    body = db.get_scene_by_id(sid).content
    assert res["ok"] and "keep this." in body and "Hero lands on the gravel." in body
    assert "PAGE 2" in body                                # appended as new page


def test_apply_marks_project_dirty():
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid, content="")
    from logosforge.project_events import get_event_bus
    fired = []
    get_event_bus().project_data_changed.connect(lambda *a: fired.append(1))
    gp.apply_draft(db, pid, sid, gp.parse_draft_response(_DRAFT),
                   mode=gp.APPLY_TO_EMPTY, confirmed=True)
    assert fired


def test_apply_preserves_outline_summary_and_planning():
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid, content="", summary="SUMMARY_KEPT")
    gp.save_page_breakdown(db, pid, gp.parse_page_breakdown_response(_BD_TEXT, sid))
    gp.save_panel_plan(db, pid, gp.parse_panel_plan_response(_PLAN_TEXT, sid))
    gp.apply_draft(db, pid, sid, gp.parse_draft_response(_DRAFT),
                   mode=gp.APPLY_TO_EMPTY, confirmed=True)
    assert db.get_scene_by_id(sid).summary == "SUMMARY_KEPT"
    assert gp.get_page_breakdown(db, pid, sid).target_page_count == 3
    assert gp.has_panel_plan(db, pid, sid)


def test_apply_preserves_timeline_psyke_notes():
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid, content="")
    db.add_timeline_event(pid, sid)
    db.create_psyke_entry(pid, "Hero", "character")
    db.create_note(pid, "keep", "note")
    before = (db.get_timeline_event_ids(pid), len(db.get_all_psyke_entries(pid)),
              len(db.get_all_notes(pid)))
    gp.apply_draft(db, pid, sid, gp.parse_draft_response(_DRAFT),
                   mode=gp.APPLY_TO_EMPTY, confirmed=True)
    after = (db.get_timeline_event_ids(pid), len(db.get_all_psyke_entries(pid)),
             len(db.get_all_notes(pid)))
    assert before == after


def test_cancel_leaves_body_unchanged():
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid, content="BODY")
    res = gp.apply_draft(db, pid, sid, gp.parse_draft_response(_DRAFT),
                         mode=gp.APPLY_CANCEL, confirmed=True)
    assert res["ok"] is False and res.get("cancelled")
    assert db.get_scene_by_id(sid).content == "BODY"


# ==========================================================================
# 27-30  Validation
# ==========================================================================


def test_validation_empty_page_warning():
    script = gnb.parse_graphic_novel_text(
        "PAGE 1: Intro\nSummary: a page with no panels\n\nPAGE 2\n\nPANEL 1\nVisual: x.")
    rep = gp.validate_draft_script(script)
    assert rep.is_valid and any("no panels" in w for w in rep.warnings)


def test_validation_panel_without_visual_warning():
    script = gnb.parse_graphic_novel_text("PAGE 1\n\nPANEL 1\nCaption: words only.")
    rep = gp.validate_draft_script(script)
    assert rep.is_valid and any("no visual" in w for w in rep.warnings)


def test_validation_dialogue_heavy_warning():
    body = "PAGE 1\n\nPANEL 1\nVisual: a.\nDialogue: NAME: " + " ".join(["word"] * 40)
    rep = gp.validate_draft_script(gnb.parse_graphic_novel_text(body))
    assert any("dialogue-heavy" in w for w in rep.warnings)


def test_corrupt_or_empty_blocks_apply():
    rep = gp.validate_draft_script(gnb.GraphicNovelScript())
    assert not rep.is_valid and rep.errors


# ==========================================================================
# 31-34  Export
# ==========================================================================


def test_applied_pages_export_as_markdown():
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid, content="")
    gp.apply_draft(db, pid, sid, gp.parse_draft_response(_DRAFT),
                   mode=gp.APPLY_TO_EMPTY, confirmed=True)
    md = gnb.export_scene_markdown(db, pid, sid)
    assert "## Page 1" in md and "### Panel 1" in md
    assert "Visual: Hero lands on the gravel." in md


def test_export_uses_panel_body_not_breakdown_and_no_secrets():
    db = Database()
    from logosforge.settings import get_manager
    get_manager().set("ai_api_key", "SECRET_KEY_SENTINEL")
    pid = _gn(db)
    sid = _scene(db, pid, content="", summary="OUTLINE_SUMMARY_SENTINEL")
    gp.save_page_breakdown(db, pid, gp.parse_page_breakdown_response(
        "Target Pages: 3\nPacing Goal: BREAKDOWN_ONLY_SENTINEL", sid))
    gp.apply_draft(db, pid, sid, gp.parse_draft_response(_DRAFT),
                   mode=gp.APPLY_TO_EMPTY, confirmed=True)
    md = gnb.export_project_markdown(db, pid)
    assert "Hero lands on the gravel." in md               # panel body present
    assert "BREAKDOWN_ONLY_SENTINEL" not in md             # breakdown not exported
    assert "OUTLINE_SUMMARY_SENTINEL" not in md            # summary not exported
    assert "SECRET_KEY_SENTINEL" not in md                 # no provider secrets


def test_project_export_canonical_order():
    db = Database()
    pid = _gn(db)
    b = ss.create_scene(db, pid, act="Act II", chapter="Ch2", title="Beta",
                        content="PAGE 1\n\nPANEL 1\nVisual: beta.").id
    a = ss.create_scene(db, pid, act="Act I", chapter="Ch1", title="Alpha",
                        content="PAGE 1\n\nPANEL 1\nVisual: alpha.").id
    db.reorder_scenes(pid, [a, b])
    md = gnb.export_project_markdown(db, pid)
    assert md.index("alpha.") < md.index("beta.")


# ==========================================================================
# 35-38  Context
# ==========================================================================


def test_assistant_context_identifies_gn_mode_and_scene():
    from logosforge.assistant_context_policy import gather_injected_context
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid, content="PAGE 1\n\nPANEL 1\nVisual: x.")
    ctx = gather_injected_context(db, pid, section_name="Manuscript", scene_id=sid)
    assert "Graphic Novel" in ctx            # mode identified
    assert "scene" in ctx.lower()            # current scene included
    # The GN script/plan blocks flow through the Logos/chat scene-context path:
    from logosforge import context_builder as cb
    assert "[Graphic Novel Script]" in cb.gather_scene_context(db, pid, sid)


def test_planning_context_includes_breakdown_and_plan():
    from logosforge import context_builder as cb
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid, content="")
    gp.save_page_breakdown(db, pid, gp.parse_page_breakdown_response(_BD_TEXT, sid))
    ctx = cb.gather_scene_context(db, pid, sid)
    assert "[Graphic Novel Plan]" in ctx and "build to reveal" in ctx


def test_planning_context_empty_for_novel():
    db = Database()
    pid = db.create_project("N", narrative_engine="novel").id
    sid = ss.create_scene(db, pid, act="A", chapter="C", title="n", content="x").id
    assert gp.gn_planning_context(db, pid, sid) == ""


def test_logos_does_not_break_on_gn_scene():
    from logosforge.logos.controller import LogosController
    from logosforge.logos.context import build_logos_context
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid, content="PAGE 1\n\nPANEL 1\nCaption: x.")
    ctl = LogosController(db, provider_resolver=lambda: (_ for _ in ()).throw(
        AssertionError("no LLM")), chat_fn=None)
    ctx = build_logos_context(db, pid, section_name="Manuscript", current_scene_id=sid)
    res = ctl.run(ctx, "gn_panel_check")            # Phase 1 deterministic action
    assert res.ok and res.title == "Panel Check"


# ==========================================================================
# UI hooks (mode-gated)
# ==========================================================================


def test_plan_view_gn_page_breakdown_hook(tmp_path):
    from logosforge.ui.plan_view import PlanView
    db = Database(str(tmp_path / "gn.db"))
    pid = _gn(db)
    _scene(db, pid)
    assert PlanView(db, pid)._is_graphic_novel_mode() is True
    nid = db.create_project("N", narrative_engine="novel").id
    assert PlanView(db, nid)._is_graphic_novel_mode() is False


def test_manuscript_gn_hooks(tmp_path):
    from logosforge.ui.writing_core_view import WritingCoreView
    db = Database(str(tmp_path / "gn.db"))
    pid = _gn(db)
    _scene(db, pid, content="PAGE 1\n\nPANEL 1\nVisual: x.")
    view = WritingCoreView(db, pid, structured_list=True)
    ed = next(iter(view._editors.values()))
    assert ed._graphic_novel_mode is True
    assert ed._on_gn_panel_plan is not None and ed._on_gn_draft_panels is not None
