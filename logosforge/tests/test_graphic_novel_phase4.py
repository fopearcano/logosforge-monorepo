"""Graphic Novel Mode — Phase 4 acceptance suite.

Counterpart / Reflection: a deterministic, multi-perspective (reader / artist /
story / dialogue) scene reflection that produces feedback and revision questions
— never a rewrite, never a mutation, never an image. Builds on Phase 3
diagnostics + Phase 2 breakdown/plan + PSYKE; optionally AI-enhanced; optionally
savable as a scene-linked Note.
"""

from __future__ import annotations

import warnings

import pytest
from PySide6.QtWidgets import QApplication

warnings.filterwarnings("ignore")

from logosforge.db import Database
from logosforge import story_structure as ss
from logosforge import graphic_novel_pipeline as gp
from logosforge import graphic_novel_reflection as gr


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


def _scene(db, pid, content, *, summary="", title="S"):
    return ss.create_scene(db, pid, act="Act I", chapter="Chapter 1", title=title,
                           content=content, summary=summary).id


# A scene with location, conflict, a turn, and named dialogue across two pages.
_RICH = (
    "PAGE 1\n\n"
    "PANEL 1\nVisual: INT. office. Maria stands at the window, tense.\n"
    "Dialogue: MARIA: It ends now.\n\n"
    "PANEL 2\nVisual: John steps back but refuses to leave the room.\n"
    "Dialogue: JOHN: No.\n\n"
    "PAGE 2\n\n"
    "PANEL 1\nVisual: Maria grabs the letter. Suddenly the lights go out.\n"
    "SFX: CLICK\n"
)


# ==========================================================================
# 1-11  Reflection core + sections + no mutation
# ==========================================================================


def test_report_can_be_generated():
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid, _RICH, summary="Maria confronts John")
    rep = gr.build_scene_reflection(db, pid, sid)
    assert rep.scene_id == sid and rep.snapshot


def test_report_includes_scene_snapshot():
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid, _RICH)
    assert gr.SEC_SNAPSHOT in gr.build_scene_reflection(db, pid, sid).to_text()


def test_report_includes_reader_and_artist_perspectives():
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid, _RICH)
    text = gr.build_scene_reflection(db, pid, sid).to_text()
    assert gr.SEC_READER in text and gr.SEC_ARTIST in text


def test_report_includes_page_flow_and_panel_continuity():
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid, _RICH)
    text = gr.build_scene_reflection(db, pid, sid).to_text()
    assert gr.SEC_FLOW in text and gr.SEC_PANEL_CONTINUITY in text


def test_report_includes_visual_and_dialogue_notes():
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid, _RICH)
    text = gr.build_scene_reflection(db, pid, sid).to_text()
    assert gr.SEC_VISUAL in text and gr.SEC_DIALOGUE in text


def test_report_includes_story_function_and_plan_alignment():
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid, _RICH)
    text = gr.build_scene_reflection(db, pid, sid).to_text()
    assert gr.SEC_STORY in text and gr.SEC_ALIGN in text and gr.SEC_PSYKE in text


def test_report_includes_revision_questions():
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid, _RICH)
    rep = gr.build_scene_reflection(db, pid, sid)
    assert rep.questions
    assert gr.SEC_QUESTIONS in rep.to_text()
    assert any("object" in q.lower() or "composition" in q.lower()
               or "gesture" in q.lower() for q in rep.questions)


def test_report_includes_suggested_human_actions_section():
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid, _RICH)
    assert gr.SEC_ACTIONS in gr.build_scene_reflection(db, pid, sid).to_text()


def test_report_does_not_mutate_scene_body():
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid, _RICH, summary="keep")
    before = (db.get_scene_by_id(sid).content, db.get_scene_by_id(sid).summary)
    gr.build_scene_reflection(db, pid, sid)
    after = (db.get_scene_by_id(sid).content, db.get_scene_by_id(sid).summary)
    assert before == after


def test_report_serializes_to_dict():
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid, _RICH)
    import json
    d = gr.build_scene_reflection(db, pid, sid).to_dict()
    assert json.dumps(d) and d["scene_id"] == sid and "metrics" in d


# ==========================================================================
# 12-15  Reader perspective
# ==========================================================================


def test_detects_unclear_page_flow():
    db = Database()
    pid = _gn(db)
    panels = "".join(f"PANEL {i}\nVisual: In the room, beat {i} happens.\n\n"
                     for i in range(1, 12))           # 11 panels on one page
    sid = _scene(db, pid, "PAGE 1\n\n" + panels)
    rep = gr.build_scene_reflection(db, pid, sid)
    assert any("overload" in i.title.lower() for i in rep.page_flow)


def test_detects_weak_page_turn():
    db = Database()
    pid = _gn(db)
    body = ("PAGE 1\n\nPANEL 1\nVisual: A quiet empty room in the house.\n\n"
            "PAGE 2\n\nPANEL 1\nVisual: Morning light fills the house.\n")
    rep = gr.build_scene_reflection(db, pid, _scene(db, pid, body))
    assert any("ends without" in i.title.lower() or "turn" in i.title.lower()
               for i in rep.reader)


def test_detects_caption_over_explanation():
    db = Database()
    pid = _gn(db)
    body = ("PAGE 1\n\nPANEL 1\nVisual: INT office.\n"
            "Caption: Maria had waited her whole life for this single moment.\n")
    rep = gr.build_scene_reflection(db, pid, _scene(db, pid, body))
    assert any("caption" in i.title.lower() for i in rep.reader)


def test_detects_unclear_setting():
    db = Database()
    pid = _gn(db)
    body = "PAGE 1\n\nPANEL 1\nVisual: A man stands and waits for someone.\n"
    rep = gr.build_scene_reflection(db, pid, _scene(db, pid, body))
    assert any("establish" in i.title.lower() or "setting" in i.title.lower()
               for i in rep.reader)


# ==========================================================================
# 16-19  Artist perspective
# ==========================================================================


def test_detects_no_drawable_subject():
    db = Database()
    pid = _gn(db)
    body = "PAGE 1\n\nPANEL 1\nDialogue: BOB: Hello there friend.\n"
    rep = gr.build_scene_reflection(db, pid, _scene(db, pid, body))
    assert any("no visual" in i.title.lower() or "drawable" in i.title.lower()
               for i in rep.artist)


def test_detects_missing_location():
    db = Database()
    pid = _gn(db)
    body = ("PAGE 1\n\nPANEL 1\nVisual: INT. office. Maria reads.\n\n"
            "PAGE 2\n\nPANEL 1\nVisual: She turns and gasps loudly.\n")
    rep = gr.build_scene_reflection(db, pid, _scene(db, pid, body))
    assert any("setting" in i.title.lower() or "location" in i.title.lower()
               for i in rep.artist)


def test_detects_internal_emotion_no_behavior():
    db = Database()
    pid = _gn(db)
    body = ("PAGE 1\n\nPANEL 1\nVisual: In the office she feels abandoned and "
            "thinks about the past.\n")
    rep = gr.build_scene_reflection(db, pid, _scene(db, pid, body))
    assert any("emotion" in i.title.lower() or "shown" in i.title.lower()
               for i in rep.artist)


def test_detects_overloaded_panel():
    db = Database()
    pid = _gn(db)
    body = ("PAGE 1\n\nPANEL 1\nVisual: In the office he opens the door. "
            "He walks across the room. He sits down at the desk.\n")
    rep = gr.build_scene_reflection(db, pid, _scene(db, pid, body))
    assert any("action" in i.title.lower() or "packs" in i.title.lower()
               for i in rep.artist)


# ==========================================================================
# 20-23  Story / dramatic perspective + plan alignment
# ==========================================================================


def test_missing_conflict_warning():
    db = Database()
    pid = _gn(db)
    body = ("PAGE 1\n\nPANEL 1\nVisual: In the room she sits and smiles.\n\n"
            "PANEL 2\nVisual: In the room she waits and rests.\n")
    rep = gr.build_scene_reflection(db, pid, _scene(db, pid, body))
    assert any("conflict" in i.title.lower() for i in rep.story_function)


def test_missing_turn_warning():
    db = Database()
    pid = _gn(db)
    body = ("PAGE 1\n\nPANEL 1\nVisual: In the room he sits.\n\n"
            "PANEL 2\nVisual: In the room he sits again.\n")
    rep = gr.build_scene_reflection(db, pid, _scene(db, pid, body))
    assert any("turn" in i.title.lower() for i in rep.story_function)


def test_plan_body_mismatch_included():
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid, "PAGE 1\n\nPANEL 1\nVisual: In the room she reads a book.\n")
    plan = gp.PanelPlan(scene_id=sid, pages=[gp.PlannedPage(
        number=1, panels=[gp.PlannedPanel(
            visual_beat="a dragon breathes fire over the castle")])])
    gp.save_panel_plan(db, pid, plan)
    rep = gr.build_scene_reflection(db, pid, sid)
    assert any("beat" in i.title.lower() or "plan" in i.title.lower()
               for i in rep.plan_alignment)


def test_outline_summary_unchanged():
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid, _RICH, summary="original purpose")
    before = db.get_scene_by_id(sid).summary
    gr.build_scene_reflection(db, pid, sid)
    assert db.get_scene_by_id(sid).summary == "original purpose" == before


# ==========================================================================
# 24-26  Deterministic vs AI-enhanced
# ==========================================================================


def test_deterministic_report_works_without_provider():
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid, _RICH)
    rep = gr.build_scene_reflection(db, pid, sid)
    assert rep.to_text() and not rep.ai_enhanced


def test_reflection_and_messages_do_not_mutate():
    db = Database()
    pid = _gn(db)
    db.create_psyke_entry(pid, "Maria", "character")
    sid = _scene(db, pid, _RICH, summary="keep")
    body_before = db.get_scene_by_id(sid).content
    psyke_before = len(db.get_all_psyke_entries(pid))
    notes_before = len(db.get_all_notes(pid))
    rep = gr.build_scene_reflection(db, pid, sid)
    gr.build_reflection_messages(rep, scene_context="[Scene]")
    assert db.get_scene_by_id(sid).content == body_before
    assert len(db.get_all_psyke_entries(pid)) == psyke_before
    assert len(db.get_all_notes(pid)) == notes_before


def test_ai_messages_are_structured_and_grounded():
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid, _RICH)
    rep = gr.build_scene_reflection(db, pid, sid)
    msgs = gr.build_reflection_messages(rep, scene_context="[Scene Context]")
    assert len(msgs) == 2
    assert msgs[0]["role"] == "system" and "COUNTERPART" in msgs[0]["content"]
    assert msgs[1]["role"] == "user"
    assert gr.SEC_SNAPSHOT in msgs[1]["content"]               # grounded in report
    assert "do not rewrite" in msgs[1]["content"].lower()


# ==========================================================================
# 27-33  Logos / UI actions
# ==========================================================================


def test_logos_dropdown_contains_gn_reflection():
    from logosforge.logos.controller import LogosController
    db = Database()
    db.create_project("G", narrative_engine="graphic_novel")
    names = [a.name for a in LogosController(db).available_actions(
        "Manuscript", writing_mode="graphic_novel")]
    assert "gn_reflection" in names
    novel = [a.name for a in LogosController(db).available_actions(
        "Manuscript", writing_mode="novel")]
    assert "gn_reflection" not in novel


def test_action_is_readable():
    from logosforge.logos import actions as A
    act = A.get_action("gn_reflection")
    assert act and act.label == "Graphic Novel Reflection"
    assert act.deterministic and not act.needs_selection
    assert act.modes == ("graphic_novel",)


def test_action_runs_without_selection_and_no_llm():
    from logosforge.logos.controller import LogosController
    from logosforge.logos.context import build_logos_context

    def _boom(*a, **k):
        raise AssertionError("deterministic reflection must not call the LLM")

    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid, _RICH)
    ctl = LogosController(db, provider_resolver=_boom, chat_fn=_boom)
    ctx = build_logos_context(db, pid, section_name="Manuscript",
                              current_scene_id=sid)
    res = ctl.run(ctx, "gn_reflection")                         # no selection
    assert res.ok and res.title == "Graphic Novel Reflection"
    assert gr.SEC_READER in res.message and gr.SEC_ARTIST in res.message
    assert res.proposed_operations == []


def test_selected_text_actions_still_require_selection():
    from logosforge.logos.controller import LogosController
    from logosforge.logos.context import build_logos_context
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid, _RICH)
    ctl = LogosController(db, provider_resolver=lambda: object(),
                          chat_fn=lambda m, p: "x")
    ctx = build_logos_context(db, pid, section_name="Manuscript",
                              current_scene_id=sid)
    res = ctl.run(ctx, "explain_selection")          # needs_selection=True
    assert not res.ok and "Select" in (res.error or "")


def test_assistant_reflection_seam_works():
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid, _RICH)
    rep = gr.build_scene_reflection(db, pid, sid)
    msgs = gr.build_reflection_messages(rep)
    assert isinstance(msgs, list) and msgs and msgs[0]["role"] == "system"


def test_report_message_is_copyable_text():
    from logosforge.logos.deterministic import get_handler
    from logosforge.logos.context import build_logos_context
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid, _RICH)
    ctx = build_logos_context(db, pid, section_name="Manuscript",
                              current_scene_id=sid)
    res = get_handler("gn_reflection")(db, ctx)
    assert isinstance(res.message, str) and res.message
    assert isinstance(res.suggestions, list)


def test_no_scene_open_is_graceful():
    from logosforge.logos.deterministic import get_handler
    from logosforge.logos.context import build_logos_context
    db = Database()
    pid = _gn(db)
    ctx = build_logos_context(db, pid, section_name="Manuscript")
    res = get_handler("gn_reflection")(db, ctx)
    assert res.ok and "Open a Graphic Novel scene" in res.message
    assert res.proposed_operations == []


# ==========================================================================
# 34-36  Optional Notes integration (confirmed only)
# ==========================================================================


def test_save_reflection_as_note_requires_confirmation():
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid, _RICH)
    rep = gr.build_scene_reflection(db, pid, sid)
    res = gr.save_reflection_as_note(db, pid, sid, rep, confirmed=False)
    assert res["ok"] is False
    assert len(db.get_all_notes(pid)) == 0


def test_saved_note_links_to_scene():
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid, _RICH)
    rep = gr.build_scene_reflection(db, pid, sid)
    res = gr.save_reflection_as_note(db, pid, sid, rep, confirmed=True)
    assert res["ok"] and res["note_id"]
    assert res["note_id"] in db.get_scene_note_links(sid)
    assert res["note_id"] in [n.id for n in db.get_all_notes(pid)]


def test_cancel_save_note_does_not_mutate_notes():
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid, _RICH)
    rep = gr.build_scene_reflection(db, pid, sid)
    before = len(db.get_all_notes(pid))
    gr.save_reflection_as_note(db, pid, sid, rep, confirmed=False)
    assert len(db.get_all_notes(pid)) == before


# ==========================================================================
# 37-39  No image generation
# ==========================================================================


def test_no_image_generation_code_or_actions():
    # Scan the module's CODE skeleton (identifiers/imports), not docstrings or
    # string literals, so the honest "does NOT generate images" disclaimer is
    # allowed while any real use (an import, a call, a field) is still caught.
    import os, tokenize
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = os.path.join(here, "logosforge", "graphic_novel_reflection.py")
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
    # No image-gen Logos actions registered anywhere.
    from logosforge.logos import actions as A
    names = " ".join(a.name + " " + a.label for a in A.list_actions()).lower()
    for banned in ("comfyui", "image gen", "generate image", "image prompt"):
        assert banned not in names


def test_no_image_provider_setting_required():
    # The reflection runs to completion with default settings; it never reads or
    # requires any image-provider configuration.
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid, _RICH)
    rep = gr.build_scene_reflection(db, pid, sid)
    assert rep.to_text()


# ==========================================================================
# Mode safety + isolation
# ==========================================================================


def test_novel_and_screenplay_unaffected():
    from logosforge.logos.controller import LogosController
    db = Database()
    db.create_project("N", narrative_engine="novel")
    novel = [a.name for a in LogosController(db).available_actions(
        "Manuscript", writing_mode="novel")]
    screen = [a.name for a in LogosController(db).available_actions(
        "Manuscript", writing_mode="screenplay")]
    assert "gn_reflection" not in novel and "gn_reflection" not in screen


def test_reflection_isolated_across_projects(tmp_path):
    db = Database(str(tmp_path / "gn.db"))
    a = _gn(db, "A")
    db.create_psyke_entry(a, "Alice", "character")
    b = _gn(db, "B")
    sid_b = _scene(db, b, "PAGE 1\n\nPANEL 1\nVisual: x.\nDialogue: BOB: Hi there.\n")
    rep_b = gr.build_scene_reflection(db, b, sid_b)
    # Project B's continuity risks must not see project A's Alice.
    risk_text = " ".join(i.title + " " + i.detail for i in rep_b.continuity_risks)
    assert "ALICE" not in risk_text.upper()


def test_scene_not_found_is_graceful():
    db = Database()
    pid = _gn(db)
    rep = gr.build_scene_reflection(db, pid, 999999)
    assert rep.snapshot == "Scene not found."
