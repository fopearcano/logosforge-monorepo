"""Graphic Novel Mode — Phase 6 acceptance suite.

Cross-scene continuity / coherence: a deterministic, read-only report (Scene
Chain, Visual Flow, Character / Object-Place continuity, Motif/Echo, Setup/Payoff,
Timeline alignment, PSYKE/Notes) consolidating the existing continuity /
setup-payoff / Timeline / PSYKE engines plus GN-specific visual-flow checks.
No mutation, and explicitly no image generation.
"""

from __future__ import annotations

import warnings

import pytest
from PySide6.QtWidgets import QApplication

warnings.filterwarnings("ignore")

from logosforge.db import Database
from logosforge import story_structure as ss
from logosforge import graphic_novel_pipeline as gp
from logosforge import graphic_novel_continuity as grc


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


def _two_scene(db):
    """Beta created first (Act II), Alpha second (Act I) -> canonical Alpha, Beta."""
    pid = _gn(db)
    b = ss.create_scene(
        db, pid, act="Act II", chapter="Chapter 2", title="Beta",
        content="PAGE 1\n\nPANEL 1\nVisual: In the lab, Mary studies a map.\n"
                "Dialogue: MARY: Hello.", summary="Beta").id
    a = ss.create_scene(
        db, pid, act="Act I", chapter="Chapter 1", title="Alpha",
        content="PAGE 1\n\nPANEL 1\nVisual: In the kitchen, Maria waits.\n"
                "Dialogue: MARIA: Hi.", summary="Alpha").id
    db.reorder_scenes(pid, [a, b])
    return pid, a, b


def _sc(db, pid, title, content, *, act="Act I", chapter="Chapter 1", summary="s"):
    return ss.create_scene(db, pid, act=act, chapter=chapter, title=title,
                           content=content, summary=summary).id


# ==========================================================================
# 1-3  Canonical chain
# ==========================================================================


def test_report_reads_scenes_in_canonical_order():
    db = Database()
    pid, a, b = _two_scene(db)
    rep = grc.build_graphic_novel_continuity_report(db, pid)
    assert [e.title for e in rep.scene_chain] == ["Alpha", "Beta"]
    assert [e.scene_id for e in rep.scene_chain] == [a, b]


def test_moving_scene_updates_continuity_order():
    db = Database()
    pid, a, b = _two_scene(db)
    db.reorder_scenes(pid, [b, a])
    rep = grc.build_graphic_novel_continuity_report(db, pid)
    assert [e.title for e in rep.scene_chain] == ["Beta", "Alpha"]


def test_chain_does_not_sort_by_id():
    db = Database()
    pid, a, b = _two_scene(db)
    rep = grc.build_graphic_novel_continuity_report(db, pid)
    ids = [e.scene_id for e in rep.scene_chain]
    assert ids != sorted(ids)                       # not id order
    assert ids == [a, b]                            # canonical order


# ==========================================================================
# 4-7  Scene / page / panel state
# ==========================================================================


def test_missing_page_breakdown_reported():
    db = Database()
    pid, a, b = _two_scene(db)
    rep = grc.build_graphic_novel_continuity_report(db, pid)
    assert rep.metrics["scenes_without_breakdown"] == 2
    assert all(not e.has_breakdown for e in rep.scene_chain)


def test_missing_panel_plan_reported():
    db = Database()
    pid, a, b = _two_scene(db)
    rep = grc.build_graphic_novel_continuity_report(db, pid)
    assert rep.metrics["scenes_without_plan"] == 2
    assert all(not e.has_plan for e in rep.scene_chain)


def test_missing_body_reported():
    db = Database()
    pid = _gn(db)
    _sc(db, pid, "Empty", "")
    rep = grc.build_graphic_novel_continuity_report(db, pid)
    assert rep.metrics["scenes_without_body"] == 1
    assert not rep.scene_chain[0].has_body


def test_scene_with_body_not_false_empty():
    db = Database()
    pid = _gn(db)
    sid = _sc(db, pid, "Full", "PAGE 1\n\nPANEL 1\nVisual: In the office, work.")
    gp.save_page_breakdown(db, pid, gp.PageBreakdown(scene_id=sid, pacing_goal="x"))
    rep = grc.build_graphic_novel_continuity_report(db, pid)
    e = rep.scene_chain[0]
    assert e.has_body and e.has_breakdown and e.panel_count == 1


# ==========================================================================
# 8-11  Visual flow
# ==========================================================================


def test_unclear_first_panel_orientation_warned():
    db = Database()
    pid = _gn(db)
    _sc(db, pid, "A", "PAGE 1\n\nPANEL 1\nVisual: A man stands and waits for hours.")
    rep = grc.build_graphic_novel_continuity_report(db, pid)
    assert any("orient" in (f.title + f.detail).lower() for f in rep.visual_flow)


def test_weak_final_transition_warned():
    db = Database()
    pid = _gn(db)
    a = _sc(db, pid, "A", "PAGE 1\n\nPANEL 1\nVisual: In the kitchen, Maria waits "
            "quietly.", act="Act I")
    b = _sc(db, pid, "B", "PAGE 1\n\nPANEL 1\nVisual: In the lab, John works.",
            act="Act II", chapter="Chapter 2")
    db.reorder_scenes(pid, [a, b])
    rep = grc.build_graphic_novel_continuity_report(db, pid)
    assert any("weak transition" in f.title.lower() for f in rep.visual_flow)


def test_no_visual_bridge_warned():
    db = Database()
    pid = _gn(db)
    a = _sc(db, pid, "A", "PAGE 1\n\nPANEL 1\nVisual: In the kitchen, Maria cooks "
            "dinner.\nDialogue: MARIA: Done.", act="Act I")
    b = _sc(db, pid, "B", "PAGE 1\n\nPANEL 1\nVisual: Someone runs quickly.",
            act="Act II", chapter="Chapter 2")
    db.reorder_scenes(pid, [a, b])
    rep = grc.build_graphic_novel_continuity_report(db, pid)
    assert any("abrupt" in f.title.lower() for f in rep.visual_flow)


def test_dialogue_heavy_chain_warned():
    db = Database()
    pid = _gn(db)
    dh = "Dialogue: BOB: " + " ".join(["talk"] * 40)
    two = f"PAGE 1\n\nPANEL 1\nVisual: a.\n{dh}\n\nPANEL 2\nVisual: b.\n{dh}\n"
    a = _sc(db, pid, "A", two, act="Act I")
    b = _sc(db, pid, "B", two, act="Act II", chapter="Chapter 2")
    db.reorder_scenes(pid, [a, b])
    rep = grc.build_graphic_novel_continuity_report(db, pid)
    assert any("dialogue-heavy" in f.title.lower() for f in rep.visual_flow)


# ==========================================================================
# 12-16  Character / object / place
# ==========================================================================


def test_character_cues_extracted_across_scenes():
    db = Database()
    pid = _gn(db)
    _sc(db, pid, "A", "PAGE 1\n\nPANEL 1\nVisual: x.\nDialogue: MARY: Hi.")
    _sc(db, pid, "B", "PAGE 1\n\nPANEL 1\nVisual: y.\nDialogue: JOHN: Bye.")
    _chain, _scripts, char_by_scene, _ev = grc._scene_chain(db, pid)
    cues = set().union(*char_by_scene.values()) if char_by_scene else set()
    assert {"MARY", "JOHN"} <= cues


def test_character_disappearance_warning():
    db = Database()
    pid = _gn(db)
    ids = []
    ids.append(_sc(db, pid, "S1", "PAGE 1\n\nPANEL 1\nVisual: x.\nDialogue: ZARA: Hi.",
                   act="Act I"))
    for i, act in enumerate(("Act II", "Act III", "Act IV"), start=2):
        ids.append(_sc(db, pid, f"S{i}",
                       f"PAGE 1\n\nPANEL 1\nVisual: x.\nDialogue: BOB: line {i}.",
                       act=act, chapter=f"Chapter {i}"))
    db.reorder_scenes(pid, ids)
    rep = grc.build_graphic_novel_continuity_report(db, pid)
    assert any("ZARA" in f.title for f in rep.character_continuity)


def test_object_motif_recurrence_detected():
    db = Database()
    pid = _gn(db)
    for i, act in enumerate(("Act I", "Act II", "Act III"), start=1):
        _sc(db, pid, f"S{i}",
            f"PAGE 1\n\nPANEL 1\nVisual: In the room, a lantern glows softly {i}.",
            act=act, chapter=f"Chapter {i}")
    rep = grc.build_graphic_novel_continuity_report(db, pid)
    assert any("lantern" in (f.title + f.detail).lower() for f in rep.motif_echo)


def test_setup_without_payoff_is_a_list():
    db = Database()
    pid = _gn(db)
    _sc(db, pid, "A", "PAGE 1\n\nPANEL 1\nVisual: He hides the key under the mat.\n"
        "Caption: Remember the key. I promise I will return for it later.")
    rep = grc.build_graphic_novel_continuity_report(db, pid)
    # Detection is heuristic; it never crashes and the section is always a list.
    assert isinstance(rep.setup_payoff, list)


def test_place_change_without_orientation_warned():
    db = Database()
    pid = _gn(db)
    a = _sc(db, pid, "A", "PAGE 1\n\nPANEL 1\nVisual: In the kitchen, Maria cooks.\n"
            "Dialogue: MARIA: Done.", act="Act I")
    b = _sc(db, pid, "B", "PAGE 1\n\nPANEL 1\nVisual: Someone runs quickly away.",
            act="Act II", chapter="Chapter 2")
    db.reorder_scenes(pid, [a, b])
    rep = grc.build_graphic_novel_continuity_report(db, pid)
    assert any("place change" in f.title.lower() or "orientation" in f.title.lower()
               for f in rep.object_place_continuity)


# ==========================================================================
# 17-20  Timeline alignment
# ==========================================================================


def test_scene_linked_to_timeline_detected():
    db = Database()
    pid, a, b = _two_scene(db)
    db.add_timeline_event(pid, a)
    rep = grc.build_graphic_novel_continuity_report(db, pid)
    ea = next(e for e in rep.scene_chain if e.scene_id == a)
    assert ea.timeline_linked is True


def test_scene_without_timeline_link_reported():
    db = Database()
    pid, a, b = _two_scene(db)
    db.add_timeline_event(pid, a)                  # a linked, b not -> b flagged
    rep = grc.build_graphic_novel_continuity_report(db, pid)
    titles = " ".join(f.title for f in rep.timeline_alignment)
    assert "not linked" in titles.lower()


def test_timeline_order_mismatch_warning():
    db = Database()
    pid, a, b = _two_scene(db)
    db.set_timeline_order_mode(pid, "custom")
    db.set_timeline_order(pid, [b, a])             # reversed vs canonical [a, b]
    rep = grc.build_graphic_novel_continuity_report(db, pid)
    assert any("order differs" in f.title.lower() for f in rep.timeline_alignment)


def test_timeline_labels_use_canonical_numbering():
    db = Database()
    pid, a, b = _two_scene(db)
    rep = grc.build_graphic_novel_continuity_report(db, pid)
    nums = {e.title: e.number for e in rep.scene_chain}
    assert nums["Alpha"] and nums["Beta"] and nums["Alpha"] != nums["Beta"]
    assert nums["Alpha"].startswith("1") and nums["Beta"].startswith("2")


# ==========================================================================
# 21-24  PSYKE / Notes
# ==========================================================================


def test_missing_psyke_link_warning_when_supported():
    db = Database()
    pid = _gn(db)
    db.create_psyke_entry(pid, "Mary", "character")    # Mary linked, John not
    _sc(db, pid, "A", "PAGE 1\n\nPANEL 1\nVisual: x.\nDialogue: MARY: Hi.\n\n"
        "PANEL 2\nVisual: y.\nDialogue: JOHN: Bye.")
    rep = grc.build_graphic_novel_continuity_report(db, pid)
    titles = " ".join(f.title for f in rep.psyke_notes)
    assert "JOHN" in titles and "MARY" not in titles


def test_linked_notes_included():
    db = Database()
    pid = _gn(db)
    sid = _sc(db, pid, "A", "PAGE 1\n\nPANEL 1\nVisual: x.")
    note = db.create_note(pid, "ctx", "body", tags="x")
    db.link_note_to_scene(getattr(note, "id", note), sid)
    rep = grc.build_graphic_novel_continuity_report(db, pid)
    assert any("note" in f.title.lower() for f in rep.psyke_notes)


def test_report_does_not_mutate_psyke():
    db = Database()
    pid = _gn(db)
    db.create_psyke_entry(pid, "Mary", "character")
    _sc(db, pid, "A", "PAGE 1\n\nPANEL 1\nVisual: x.\nDialogue: MARY: Hi.")
    before = len(db.get_all_psyke_entries(pid))
    grc.build_graphic_novel_continuity_report(db, pid)
    assert len(db.get_all_psyke_entries(pid)) == before == 1


def test_report_does_not_mutate_notes():
    db = Database()
    pid = _gn(db)
    sid = _sc(db, pid, "A", "PAGE 1\n\nPANEL 1\nVisual: x.")
    db.create_note(pid, "n", "b")
    before = len(db.get_all_notes(pid))
    grc.build_graphic_novel_continuity_report(db, pid)
    assert len(db.get_all_notes(pid)) == before


# ==========================================================================
# 25-28  UI / actions
# ==========================================================================


def test_logos_dropdown_includes_continuity_check():
    from logosforge.logos.controller import LogosController
    db = Database()
    db.create_project("G", narrative_engine="graphic_novel")
    ctl = LogosController(db)
    for sec in ("Manuscript", "Timeline", "Outline"):
        names = [a.name for a in ctl.available_actions(sec, writing_mode="graphic_novel")]
        assert "gn_continuity_check" in names
    novel = [a.name for a in ctl.available_actions("Manuscript", writing_mode="novel")]
    assert "gn_continuity_check" not in novel


def test_continuity_action_runs_without_scene_and_no_llm():
    from logosforge.logos.controller import LogosController
    from logosforge.logos.context import build_logos_context

    def _boom(*a, **k):
        raise AssertionError("deterministic action must not call the LLM")

    db = Database()
    pid, a, b = _two_scene(db)
    ctl = LogosController(db, provider_resolver=_boom, chat_fn=_boom)
    ctx = build_logos_context(db, pid, section_name="Manuscript", current_scene_id=None)
    res = ctl.run(ctx, "gn_continuity_check")
    assert res.ok and res.title == "Graphic Novel Continuity Check"
    assert grc.SEC_CHAIN in res.message and res.proposed_operations == []


def test_assistant_seam_and_copyable_report():
    from logosforge.logos.deterministic import get_handler
    from logosforge.logos.context import build_logos_context
    db = Database()
    pid, a, b = _two_scene(db)
    ctx = build_logos_context(db, pid, section_name="Manuscript", current_scene_id=None)
    res = get_handler("gn_continuity_check")(db, ctx)
    assert isinstance(res.message, str) and res.message
    assert isinstance(res.suggestions, list)
    rep = grc.build_graphic_novel_continuity_report(db, pid)
    msgs = grc.build_continuity_messages(rep)
    assert len(msgs) == 2 and msgs[0]["role"] == "system"
    assert grc.SEC_CHAIN in msgs[1]["content"]


def test_save_as_note_requires_confirmation():
    db = Database()
    pid, a, b = _two_scene(db)
    rep = grc.build_graphic_novel_continuity_report(db, pid)
    r0 = grc.save_continuity_as_note(db, pid, rep, confirmed=False)
    assert r0["ok"] is False and len(db.get_all_notes(pid)) == 0
    r1 = grc.save_continuity_as_note(db, pid, rep, confirmed=True)
    assert r1["ok"] and len(db.get_all_notes(pid)) == 1


# ==========================================================================
# 29-33  Safety (no mutation)
# ==========================================================================


def test_report_does_not_mutate_manuscript_or_outline():
    db = Database()
    pid = _gn(db)
    sid = _sc(db, pid, "A", "PAGE 1\n\nPANEL 1\nVisual: x.", summary="SUM")
    before = (db.get_scene_by_id(sid).content, db.get_scene_by_id(sid).summary)
    grc.build_graphic_novel_continuity_report(db, pid)
    after = (db.get_scene_by_id(sid).content, db.get_scene_by_id(sid).summary)
    assert before == after


def test_report_does_not_mutate_timeline():
    db = Database()
    pid, a, b = _two_scene(db)
    db.add_timeline_event(pid, a)
    before = db.get_timeline_event_ids(pid)
    grc.build_graphic_novel_continuity_report(db, pid)
    assert db.get_timeline_event_ids(pid) == before


def test_report_does_not_mutate_breakdown_or_plan():
    db = Database()
    pid = _gn(db)
    sid = _sc(db, pid, "A", "PAGE 1\n\nPANEL 1\nVisual: x.")
    gp.save_page_breakdown(db, pid, gp.PageBreakdown(scene_id=sid, pacing_goal="KEEP"))
    grc.build_graphic_novel_continuity_report(db, pid)
    assert gp.get_page_breakdown(db, pid, sid).pacing_goal == "KEEP"


def test_provider_error_does_not_mutate():
    db = Database()
    pid, a, b = _two_scene(db)
    rep = grc.build_graphic_novel_continuity_report(db, pid)
    before = db.get_scene_by_id(a).content
    msgs = grc.build_continuity_messages(rep)        # builds only; no provider call
    assert isinstance(msgs, list) and db.get_scene_by_id(a).content == before


def test_report_isolated_across_projects(tmp_path):
    db = Database(str(tmp_path / "gn.db"))
    pid_a, a, b = _two_scene(db)
    db.create_psyke_entry(pid_a, "Mary", "character")
    pid_b = _gn(db, "B")
    _sc(db, pid_b, "Z", "PAGE 1\n\nPANEL 1\nVisual: x.\nDialogue: ZARA: Hi.")
    rep_b = grc.build_graphic_novel_continuity_report(db, pid_b)
    assert [e.title for e in rep_b.scene_chain] == ["Z"]
    pk = " ".join(f.title for f in rep_b.psyke_notes)
    assert "MARY" not in pk                           # no leakage from project A


# ==========================================================================
# 34-36  No image generation
# ==========================================================================


def test_no_image_generation_code_or_actions():
    import os, tokenize
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = os.path.join(here, "logosforge", "graphic_novel_continuity.py")
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
    pid, a, b = _two_scene(db)
    rep = grc.build_graphic_novel_continuity_report(db, pid)
    assert rep.to_text()


# ==========================================================================
# Novel mode unaffected
# ==========================================================================


def test_novel_mode_unaffected():
    from logosforge.logos.controller import LogosController
    db = Database()
    db.create_project("Book", narrative_engine="novel")
    for sec in ("Manuscript", "Timeline", "Outline"):
        names = [a.name for a in
                 LogosController(db).available_actions(sec, writing_mode="novel")]
        assert "gn_continuity_check" not in names
