"""Graphic Novel Mode — Phase 3 acceptance suite.

Deterministic page/panel script intelligence: metrics, panel/visual/dialogue/
caption checks, page flow, dramatic function, plan alignment, PSYKE continuity,
and the "Graphic Novel Check" Logos action. Read-only, report-only — no mutation,
no LLM, and explicitly no image generation / ComfyUI / image prompts.
"""

from __future__ import annotations

import warnings

import pytest
from PySide6.QtWidgets import QApplication

warnings.filterwarnings("ignore")

from logosforge.db import Database
from logosforge import story_structure as ss
from logosforge import graphic_novel_blocks as gnb
from logosforge import graphic_novel_pipeline as gp
from logosforge import graphic_novel_diagnostics as gd


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


def _report(body, **kw):
    return gd.analyze_scene(gnb.parse_graphic_novel_text(body), **kw)


def _ids(report):
    return [i.id for i in report.issues]


# ==========================================================================
# 1-8  Metrics
# ==========================================================================


def test_counts_pages_and_panels():
    body = ("PAGE 1\n\nPANEL 1\nVisual: a.\n\nPANEL 2\nVisual: b.\n\n"
            "PAGE 2\n\nPANEL 1\nVisual: c.")
    rep = _report(body)
    assert rep.total_pages == 2 and rep.total_panels == 3


def test_avg_panels_per_page():
    body = "PAGE 1\n\nPANEL 1\nVisual: a.\n\nPANEL 2\nVisual: b.\n\nPAGE 2\n\nPANEL 1\nVisual: c."
    assert _report(body).avg_panels_per_page == 1.5


def test_counts_panels_without_visual_and_empty():
    # Buckets are mutually exclusive: a fully-empty panel counts as empty only,
    # a content-but-no-visual panel counts as without-visual only.
    body = "PAGE 1\n\nPANEL 1\nVisual: a.\n\nPANEL 2\nCaption: x.\n\nPANEL 3\n"
    rep = _report(body)
    assert rep.panels_without_visual == 1 and rep.empty_panels == 1


def test_counts_dialogue_heavy_and_caption_heavy():
    body = ("PAGE 1\n\nPANEL 1\nVisual: a.\nDialogue: BOB: " + " ".join(["w"] * 40)
            + "\n\nPANEL 2\nVisual: b.\nCaption: " + " ".join(["w"] * 45))
    rep = _report(body)
    assert rep.dialogue_heavy_panels == 1 and rep.caption_heavy_panels == 1


def test_counts_sfx_usage():
    body = "PAGE 1\n\nPANEL 1\nVisual: a.\nSFX: BANG\n\nPANEL 2\nVisual: b.\nSFX: POW"
    assert _report(body).sfx_count == 2


# ==========================================================================
# 9-14  Panel-level checks
# ==========================================================================


def test_warns_panel_without_visual():
    rep = _report("PAGE 1\n\nPANEL 1\nCaption: only a caption.")
    assert any(i.id.startswith("no_visual") for i in rep.issues)


def test_warns_dialogue_too_long():
    body = "PAGE 1\n\nPANEL 1\nVisual: a.\nDialogue: BOB: " + " ".join(["w"] * 40)
    assert any(i.id.startswith("dialogue_heavy") for i in _report(body).issues)


def test_warns_caption_too_long():
    body = "PAGE 1\n\nPANEL 1\nVisual: a.\nCaption: " + " ".join(["w"] * 45)
    assert any(i.id.startswith("caption_heavy") for i in _report(body).issues)


def test_warns_empty_panel():
    body = "PAGE 1\n\nPANEL 1\nVisual: a.\n\nPANEL 2\n"
    assert any(i.id.startswith("empty_panel") for i in _report(body).issues)


def test_warns_notes_present_but_no_visual():
    rep = _report("PAGE 1\n\nPANEL 1\nNotes: low angle, dramatic light.")
    assert any(i.id.startswith("notes_no_visual") for i in rep.issues)


def test_clear_balanced_panel_not_flagged():
    rep = _report("PAGE 1\n\nPANEL 1\nVisual: Maria kicks the door open, gun raised."
                  "\nDialogue: MARIA: Move, but he refuses.")
    assert not any(i.id.startswith(("no_visual", "empty_panel", "dialogue_heavy",
                                    "internal_visual", "vague_visual"))
                   for i in rep.issues)


# ==========================================================================
# 15-19  Page flow
# ==========================================================================


def test_warns_page_with_no_panels():
    rep = _report("PAGE 1: Intro\nSummary: a page with no panels\n\nPAGE 2\n\n"
                  "PANEL 1\nVisual: x.")
    assert any(i.id.startswith("empty_page") for i in rep.issues)


def test_warns_page_with_too_many_panels():
    body = "PAGE 1\n" + "".join(f"\nPANEL {i}\nVisual: beat {i}.\n" for i in range(1, 11))
    assert any(i.id.startswith("page_overloaded") for i in _report(body).issues)


def test_warns_all_dialogue_page():
    body = ("PAGE 1\n\nPANEL 1\nVisual: a.\nDialogue: A: " + " ".join(["w"] * 40)
            + "\n\nPANEL 2\nVisual: b.\nDialogue: B: " + " ".join(["w"] * 40))
    assert any(i.id.startswith("page_all_talk") for i in _report(body).issues)


def test_warns_missing_page_turn_when_multipage():
    db = Database()
    pid = _gn(db)
    sid = ss.create_scene(db, pid, act="Act I", chapter="Ch1", title="S",
                          content="PAGE 1\n\nPANEL 1\nVisual: a.\n\nPAGE 2\n\n"
                                  "PANEL 1\nVisual: b.").id
    gp.save_page_breakdown(db, pid, gp.parse_page_breakdown_response(
        "Target Pages: 2\nPacing Goal: fast", sid))   # no Page Turns
    rep = gd.analyze_scene_by_id(db, pid, sid)
    assert any(i.id == "no_page_turn" for i in rep.issues)


# ==========================================================================
# 20-22  Plan alignment (read-only)
# ==========================================================================


def test_warns_breakdown_exists_but_no_pages():
    db = Database()
    pid = _gn(db)
    sid = ss.create_scene(db, pid, act="Act I", chapter="Ch1", title="S",
                          content="", summary="intent").id
    gp.save_page_breakdown(db, pid, gp.parse_page_breakdown_response(
        "Target Pages: 3\nPacing Goal: fast", sid))
    rep = gd.analyze_scene_by_id(db, pid, sid)
    assert any(i.id == "no_pages" for i in rep.issues)


def test_warns_plan_beat_missing_from_body():
    plan = gp.parse_panel_plan_response(
        "PAGE 1\nPANEL 1\nVisual beat: dragon erupts from the volcano", scene_id=1)
    rep = _report("PAGE 1\n\nPANEL 1\nVisual: a quiet kitchen.", plan=plan)
    assert any(i.id.startswith("plan_beat_missing") for i in rep.issues)


def test_alignment_does_not_mutate_plan_or_breakdown():
    db = Database()
    pid = _gn(db)
    sid = ss.create_scene(db, pid, act="Act I", chapter="Ch1", title="S",
                          content="PAGE 1\n\nPANEL 1\nVisual: x.", summary="s").id
    gp.save_page_breakdown(db, pid, gp.parse_page_breakdown_response(
        "Target Pages: 2", sid))
    gp.save_panel_plan(db, pid, gp.parse_panel_plan_response(
        "PAGE 1\nPANEL 1\nVisual beat: x", sid))
    bd_before = gp.get_page_breakdown(db, pid, sid).to_dict()
    plan_before = gp.get_panel_plan(db, pid, sid).to_dict()
    gd.analyze_scene_by_id(db, pid, sid)
    assert gp.get_page_breakdown(db, pid, sid).to_dict() == bd_before
    assert gp.get_panel_plan(db, pid, sid).to_dict() == plan_before


# ==========================================================================
# 23-25  Continuity / PSYKE
# ==========================================================================


def test_character_mention_warning_when_psyke_missing():
    rep = _report("PAGE 1\n\nPANEL 1\nVisual: x.\nDialogue: BOB: hi.",
                  psyke_characters={"ALICE": True})
    assert any(i.id == "character_not_in_psyke_BOB" for i in rep.issues)
    assert not any(i.id == "character_not_in_psyke_ALICE" for i in rep.issues)


def test_no_psyke_warning_without_story_bible():
    rep = _report("PAGE 1\n\nPANEL 1\nVisual: x.\nDialogue: BOB: hi.")
    assert not any(i.id.startswith("character_not_in_psyke") for i in rep.issues)


def test_continuity_isolated_and_no_psyke_mutation(tmp_path):
    db = Database(str(tmp_path / "gn.db"))
    a = _gn(db, "A")
    db.create_psyke_entry(a, "Alice", "character")
    b = _gn(db, "B")
    sid_b = ss.create_scene(db, b, act="Act I", chapter="Ch1", title="S",
                            content="PAGE 1\n\nPANEL 1\nVisual: x.\nDialogue: BOB: hi.").id
    before = len(db.get_all_psyke_entries(b))
    rep_b = gd.analyze_scene_by_id(db, b, sid_b)
    # B has no PSYKE -> no continuity warnings (A's Alice never leaks).
    assert not any(i.id.startswith("character_not_in_psyke") for i in rep_b.issues)
    assert len(db.get_all_psyke_entries(b)) == before


# ==========================================================================
# 26-31  Logos / Assistant
# ==========================================================================


def test_logos_dropdown_includes_graphic_novel_check():
    from logosforge.logos.controller import LogosController
    db = Database()
    db.create_project("GN", narrative_engine="graphic_novel",
                      default_writing_format="graphic_novel")
    names = [a.name for a in LogosController(db).available_actions(
        "Manuscript", writing_mode="graphic_novel")]
    assert "gn_scene_health" in names
    assert "gn_scene_health" not in [a.name for a in LogosController(db).available_actions(
        "Manuscript", writing_mode="novel")]


def test_action_is_readable():
    from logosforge.logos import actions as A
    act = A.get_action("gn_scene_health")
    assert act.label == "Graphic Novel Check"
    assert act.deterministic and not act.needs_selection
    assert act.modes == ("graphic_novel",)


def test_check_runs_without_selection_and_no_llm():
    from logosforge.logos.controller import LogosController
    from logosforge.logos.context import build_logos_context

    def _boom(*a, **k):
        raise AssertionError("deterministic action must not call the LLM")

    db = Database()
    pid = _gn(db)
    sid = ss.create_scene(db, pid, act="Act I", chapter="Ch1", title="S",
                          content="PAGE 1\n\nPANEL 1\nVisual: Maria feels sad.").id
    ctl = LogosController(db, provider_resolver=_boom, chat_fn=_boom)
    ctx = build_logos_context(db, pid, section_name="Manuscript", current_scene_id=sid)
    res = ctl.run(ctx, "gn_scene_health")
    assert res.ok and res.title == "Graphic Novel Check"
    assert "Metrics" in res.message and res.proposed_operations == []


def test_panel_check_still_works():
    from logosforge.logos.controller import LogosController
    from logosforge.logos.context import build_logos_context
    db = Database()
    pid = _gn(db)
    sid = ss.create_scene(db, pid, act="Act I", chapter="Ch1", title="S",
                          content="PAGE 1\n\nPANEL 1\nCaption: x.").id
    ctl = LogosController(db)
    ctx = build_logos_context(db, pid, section_name="Manuscript", current_scene_id=sid)
    res = ctl.run(ctx, "gn_panel_check")          # Phase 1 action unaffected
    assert res.ok and res.title == "Panel Check"


def test_output_is_copyable_text_with_suggestions():
    from logosforge.logos.deterministic import get_handler
    from logosforge.logos.context import build_logos_context
    db = Database()
    pid = _gn(db)
    sid = ss.create_scene(db, pid, act="Act I", chapter="Ch1", title="S",
                          content="PAGE 1\n\nPANEL 1\nCaption: only caption.").id
    ctx = build_logos_context(db, pid, section_name="Manuscript", current_scene_id=sid)
    res = get_handler("gn_scene_health")(db, ctx)
    assert isinstance(res.message, str) and res.message
    assert isinstance(res.suggestions, list)


def test_report_does_not_mutate_scene():
    db = Database()
    pid = _gn(db)
    body = "PAGE 1\n\nPANEL 1\nVisual: x."
    sid = ss.create_scene(db, pid, act="Act I", chapter="Ch1", title="S",
                          content=body, summary="keep").id
    gd.analyze_scene_by_id(db, pid, sid)
    after = db.get_scene_by_id(sid)
    assert after.content == body and after.summary == "keep"


# ==========================================================================
# 32-34  No image generation
# ==========================================================================


def test_no_image_generation_modules_or_actions():
    # No ComfyUI / image-gen code introduced by this phase. We scan the CODE
    # skeleton (identifiers/imports), not docstrings/comments, so the module's
    # honest "does NOT do image generation" disclaimer is allowed while any real
    # use (an import, a call, a field) would still be caught.
    import io, os, tokenize
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = os.path.join(here, "logosforge", "graphic_novel_diagnostics.py")
    code_tokens = []
    with open(src, "rb") as fh:
        for tok in tokenize.tokenize(fh.readline):
            name = tokenize.tok_name[tok.type]
            if tok.type == tokenize.COMMENT or name.endswith("STRING"):
                continue  # drop comments and (f-)string literals -> prose only
            code_tokens.append(tok.string.lower())
    skeleton = " ".join(code_tokens)
    for banned in ("comfyui", "image generation", "image prompt", "lora",
                   "render", "stable diffusion", "img2img", "txt2img"):
        assert banned not in skeleton, banned
    # No image-gen Logos actions registered.
    from logosforge.logos import actions as A
    names = " ".join(a.name + " " + a.label for a in A.list_actions()).lower()
    for banned in ("comfyui", "image gen", "generate image", "image prompt"):
        assert banned not in names


# ==========================================================================
# Mode safety
# ==========================================================================


def test_metrics_and_serialization():
    rep = _report("PAGE 1\n\nPANEL 1\nVisual: x.\nDialogue: BOB: hi.")
    import json
    d = rep.to_dict()
    assert json.dumps(d) and "total_panels" in d and "issues" in d


def test_empty_scene_handled():
    rep = _report("")
    assert rep.total_pages == 0 and "Empty scene" in rep.summary


def test_novel_and_screenplay_unaffected_by_gn_action():
    from logosforge.logos.controller import LogosController
    db = Database()
    db.create_project("N", narrative_engine="novel")
    assert "gn_scene_health" not in [a.name for a in LogosController(db).available_actions(
        "Manuscript", writing_mode="novel")]
    assert "gn_scene_health" not in [a.name for a in LogosController(db).available_actions(
        "Manuscript", writing_mode="screenplay")]
