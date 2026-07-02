"""Screenplay Mode — Phase 5 acceptance suite.

Counterpart / Reflection: a deterministic two-stance (internal character +
external audience) scene reflection that produces feedback and questions — never
a rewrite, never a mutation. Builds on Phase 3 diagnostics + Phase 2 beat plan +
PSYKE; optionally AI-enhanced; optionally savable as a scene-linked Note.
"""

from __future__ import annotations

import warnings

import pytest
from PySide6.QtWidgets import QApplication

warnings.filterwarnings("ignore")

from logosforge.db import Database
from logosforge import story_structure as ss
from logosforge import screenplay_pipeline as spp
from logosforge import screenplay_reflection as sr


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


def _scene(db, pid, content, *, summary="", title="S"):
    return ss.create_scene(db, pid, act="Act I", chapter="Seq 1", title=title,
                           content=content, summary=summary).id


_RICH = (
    "INT. KITCHEN - NIGHT\n\n"
    "Maria stands by the window.\n\n"
    "MARIA\nHello there John.\n\n"
    "JOHN\nGo away."
)


# ==========================================================================
# 1-10  Reflection core + sections + no mutation
# ==========================================================================


def test_report_can_be_generated():
    db = Database()
    pid = _screenplay(db)
    sid = _scene(db, pid, _RICH, summary="Maria confronts John")
    rep = sr.build_scene_reflection(db, pid, sid)
    assert rep.scene_id == sid and rep.snapshot


def test_report_includes_scene_snapshot():
    db = Database()
    pid = _screenplay(db)
    sid = _scene(db, pid, _RICH)
    assert sr.SEC_SNAPSHOT in sr.build_scene_reflection(db, pid, sid).to_text()


def test_report_includes_internal_character_perspective():
    db = Database()
    pid = _screenplay(db)
    sid = _scene(db, pid, _RICH)
    rep = sr.build_scene_reflection(db, pid, sid)
    assert rep.characters
    assert sr.SEC_INTERNAL in rep.to_text()


def test_report_includes_external_audience_perspective():
    db = Database()
    pid = _screenplay(db)
    sid = _scene(db, pid, _RICH, summary="Maria confronts John")
    assert sr.SEC_EXTERNAL in sr.build_scene_reflection(db, pid, sid).to_text()


def test_report_includes_conflict_objective_section():
    db = Database()
    pid = _screenplay(db)
    sid = _scene(db, pid, _RICH)
    assert sr.SEC_CONFLICT in sr.build_scene_reflection(db, pid, sid).to_text()


def test_report_includes_visual_action_notes():
    db = Database()
    pid = _screenplay(db)
    sid = _scene(db, pid, _RICH)
    assert sr.SEC_VISUAL in sr.build_scene_reflection(db, pid, sid).to_text()


def test_report_includes_dialogue_notes():
    db = Database()
    pid = _screenplay(db)
    sid = _scene(db, pid, _RICH)
    assert sr.SEC_DIALOGUE in sr.build_scene_reflection(db, pid, sid).to_text()


def test_report_includes_beat_plan_alignment():
    db = Database()
    pid = _screenplay(db)
    sid = _scene(db, pid, _RICH)
    rep = sr.build_scene_reflection(db, pid, sid)
    assert rep.beat_plan_alignment           # at least the "no beat plan" note
    assert sr.SEC_ALIGN in rep.to_text()


def test_report_includes_revision_questions():
    db = Database()
    pid = _screenplay(db)
    sid = _scene(db, pid, _RICH)
    rep = sr.build_scene_reflection(db, pid, sid)
    assert rep.questions
    assert any("object" in q.lower() or "gesture" in q.lower() for q in rep.questions)


def test_report_does_not_mutate_scene_body():
    db = Database()
    pid = _screenplay(db)
    sid = _scene(db, pid, _RICH, summary="keep")
    before = (db.get_scene_by_id(sid).content, db.get_scene_by_id(sid).summary)
    sr.build_scene_reflection(db, pid, sid)
    after = (db.get_scene_by_id(sid).content, db.get_scene_by_id(sid).summary)
    assert before == after


# ==========================================================================
# 11-14  Internal character perspective
# ==========================================================================


def test_character_blocks_detected():
    db = Database()
    pid = _screenplay(db)
    sid = _scene(db, pid, _RICH)
    names = {c.name for c in sr.build_scene_reflection(db, pid, sid).characters}
    assert names == {"MARIA", "JOHN"}


def test_unlinked_characters_reported():
    db = Database()
    pid = _screenplay(db)
    sid = _scene(db, pid, _RICH)
    rep = sr.build_scene_reflection(db, pid, sid)
    maria = next(c for c in rep.characters if c.name == "MARIA")
    assert maria.linked is False
    assert any("unlinked" in n.lower() for n in maria.notes)


def test_psyke_linked_characters_included():
    db = Database()
    pid = _screenplay(db)
    db.create_psyke_entry(pid, "Maria", "character")
    sid = _scene(db, pid, _RICH)
    rep = sr.build_scene_reflection(db, pid, sid)
    maria = next(c for c in rep.characters if c.name == "MARIA")
    assert maria.linked is True and maria.psyke_entry_id is not None


def test_no_psyke_entries_created_automatically():
    db = Database()
    pid = _screenplay(db)
    sid = _scene(db, pid, _RICH)
    before = len(db.get_all_psyke_entries(pid))
    sr.build_scene_reflection(db, pid, sid)
    assert len(db.get_all_psyke_entries(pid)) == before == 0


# ==========================================================================
# 15-18  External / craft perspective
# ==========================================================================


def test_missing_conflict_warning_when_appropriate():
    db = Database()
    pid = _screenplay(db)
    # No opposition/struggle language at all.
    sid = _scene(db, pid, "INT. ROOM - DAY\n\nMaria sits. She waits. She smiles.")
    rep = sr.build_scene_reflection(db, pid, sid)
    assert any("conflict" in i.title.lower() for i in rep.conflict_objective)


def test_missing_turning_point_warning_when_appropriate():
    db = Database()
    pid = _screenplay(db)
    sid = _scene(db, pid, "INT. ROOM - DAY\n\nHe sits. He waits. He stays.")
    rep = sr.build_scene_reflection(db, pid, sid)
    assert any("story state" in i.title.lower() or "change" in i.title.lower()
               for i in rep.external)


def test_exposition_heavy_can_be_flagged():
    db = Database()
    pid = _screenplay(db)
    monologue = " ".join(["word"] * 60)
    sid = _scene(db, pid, f"INT. ROOM - DAY\n\nMARIA\n{monologue}")
    rep = sr.build_scene_reflection(db, pid, sid)
    maria = next(c for c in rep.characters if c.name == "MARIA")
    # Either the character reads exposition-heavy or a dialogue note is present.
    assert "exposition" in maria.dialogue_function.lower() or rep.dialogue_notes


def test_visual_action_weakness_can_be_flagged():
    db = Database()
    pid = _screenplay(db)
    sid = _scene(db, pid,
                 "INT. ROOM - DAY\n\nJohn thinks and remembers and feels and realizes.")
    rep = sr.build_scene_reflection(db, pid, sid)
    assert rep.visual_notes        # internal-state action surfaces a visual note


# ==========================================================================
# 19-21  AI fallback / hybrid
# ==========================================================================


def test_deterministic_report_works_without_provider():
    # build_scene_reflection never touches a provider — works offline.
    db = Database()
    pid = _screenplay(db)
    sid = _scene(db, pid, _RICH)
    rep = sr.build_scene_reflection(db, pid, sid)
    assert rep.to_text() and not rep.ai_enhanced


def test_reflection_and_messages_do_not_mutate():
    db = Database()
    pid = _screenplay(db)
    db.create_psyke_entry(pid, "Maria", "character")
    sid = _scene(db, pid, _RICH, summary="keep")
    body_before = db.get_scene_by_id(sid).content
    psyke_before = len(db.get_all_psyke_entries(pid))
    notes_before = len(db.get_all_notes(pid))
    rep = sr.build_scene_reflection(db, pid, sid)
    sr.build_reflection_messages(rep, scene_context="[Scene]")
    assert db.get_scene_by_id(sid).content == body_before
    assert len(db.get_all_psyke_entries(pid)) == psyke_before
    assert len(db.get_all_notes(pid)) == notes_before


def test_ai_messages_are_structured_and_grounded():
    db = Database()
    pid = _screenplay(db)
    sid = _scene(db, pid, _RICH)
    rep = sr.build_scene_reflection(db, pid, sid)
    msgs = sr.build_reflection_messages(rep, scene_context="[Scene Context]")
    assert len(msgs) == 2
    assert msgs[0]["role"] == "system" and "COUNTERPART" in msgs[0]["content"]
    assert msgs[1]["role"] == "user"
    assert sr.SEC_SNAPSHOT in msgs[1]["content"]      # grounded in the report
    assert "do not produce replacement prose" in msgs[1]["content"].lower() \
        or "do not rewrite" in msgs[1]["content"].lower()


# ==========================================================================
# 22-28  Logos / UI actions
# ==========================================================================


def test_logos_dropdown_contains_counterpart_reflection():
    from logosforge.logos.controller import LogosController
    db = Database()
    db.create_project("S", narrative_engine="screenplay")
    names = [a.name for a in
             LogosController(db).available_actions("Manuscript", writing_mode="screenplay")]
    assert "sp_counterpart_reflection" in names
    novel = [a.name for a in
             LogosController(db).available_actions("Manuscript", writing_mode="novel")]
    assert "sp_counterpart_reflection" not in novel


def test_action_is_readable():
    from logosforge.logos import actions as A
    act = A.get_action("sp_counterpart_reflection")
    assert act and act.label == "Counterpart Reflection"
    assert act.deterministic and not act.needs_selection and act.modes == ("screenplay",)


def test_action_runs_without_selected_text_and_no_llm():
    from logosforge.logos.controller import LogosController
    from logosforge.logos.context import build_logos_context

    def _boom(*a, **k):
        raise AssertionError("deterministic reflection must not call the LLM")

    db = Database()
    pid = _screenplay(db)
    sid = _scene(db, pid, _RICH)
    ctl = LogosController(db, provider_resolver=_boom, chat_fn=_boom)
    ctx = build_logos_context(db, pid, section_name="Manuscript", current_scene_id=sid)
    res = ctl.run(ctx, "sp_counterpart_reflection")            # no selection
    assert res.ok and res.title == "Counterpart Reflection"
    assert sr.SEC_INTERNAL in res.message and sr.SEC_EXTERNAL in res.message
    assert res.proposed_operations == []


def test_selected_text_actions_still_require_selection():
    from logosforge.logos.controller import LogosController
    from logosforge.logos.context import build_logos_context
    db = Database()
    pid = _screenplay(db)
    sid = _scene(db, pid, _RICH)
    ctl = LogosController(db, provider_resolver=lambda: object(),
                          chat_fn=lambda m, p: "x")
    ctx = build_logos_context(db, pid, section_name="Manuscript", current_scene_id=sid)
    res = ctl.run(ctx, "sp_visual_action")          # needs_selection=True
    assert not res.ok and "Select some text" in (res.error or "")


def test_assistant_reflection_seam_works():
    # The AI "Reflect on Scene" surface is build_reflection_messages over the
    # deterministic report (the existing Counterpart panel runs the chat call).
    db = Database()
    pid = _screenplay(db)
    sid = _scene(db, pid, _RICH)
    rep = sr.build_scene_reflection(db, pid, sid)
    msgs = sr.build_reflection_messages(rep)
    assert isinstance(msgs, list) and msgs and msgs[0]["role"] == "system"


def test_report_message_is_copyable_text():
    from logosforge.logos.deterministic import get_handler
    from logosforge.logos.context import build_logos_context
    db = Database()
    pid = _screenplay(db)
    sid = _scene(db, pid, _RICH)
    ctx = build_logos_context(db, pid, section_name="Manuscript", current_scene_id=sid)
    res = get_handler("sp_counterpart_reflection")(db, ctx)
    # A plain string message + list suggestions -> the Logos result area renders
    # and can copy/dismiss it.
    assert isinstance(res.message, str) and res.message
    assert isinstance(res.suggestions, list)


def test_novel_mode_unaffected():
    from logosforge.logos.controller import LogosController
    db = Database()
    db.create_project("Book", narrative_engine="novel")
    names = [a.name for a in
             LogosController(db).available_actions("Manuscript", writing_mode="novel")]
    assert "sp_counterpart_reflection" not in names


# ==========================================================================
# 29-31  Optional Notes integration
# ==========================================================================


def test_save_reflection_as_note_requires_confirmation():
    db = Database()
    pid = _screenplay(db)
    sid = _scene(db, pid, _RICH)
    rep = sr.build_scene_reflection(db, pid, sid)
    res = sr.save_reflection_as_note(db, pid, sid, rep, confirmed=False)
    assert res["ok"] is False
    assert len(db.get_all_notes(pid)) == 0           # nothing saved


def test_saved_note_links_to_scene():
    db = Database()
    pid = _screenplay(db)
    sid = _scene(db, pid, _RICH)
    rep = sr.build_scene_reflection(db, pid, sid)
    res = sr.save_reflection_as_note(db, pid, sid, rep, confirmed=True)
    assert res["ok"] and res["note_id"]
    assert res["note_id"] in db.get_scene_note_links(sid)
    note_ids = [n.id for n in db.get_all_notes(pid)]
    assert res["note_id"] in note_ids


def test_cancel_save_note_does_not_mutate_notes():
    db = Database()
    pid = _screenplay(db)
    sid = _scene(db, pid, _RICH)
    rep = sr.build_scene_reflection(db, pid, sid)
    before = len(db.get_all_notes(pid))
    sr.save_reflection_as_note(db, pid, sid, rep, confirmed=False)
    assert len(db.get_all_notes(pid)) == before


def test_reflection_isolated_across_projects(tmp_path):
    db = Database(str(tmp_path / "sp.db"))
    a = _screenplay(db)
    db.create_psyke_entry(a, "Alice", "character")
    b = _screenplay(db)
    sid_b = _scene(db, b, "INT. X - DAY\n\nBOB\nHi.")
    rep_b = sr.build_scene_reflection(db, b, sid_b)
    # Project B's reflection must not see project A's Alice.
    names = {c.name for c in rep_b.characters}
    assert names == {"BOB"}
    assert all(not c.linked for c in rep_b.characters)   # no PSYKE in B
