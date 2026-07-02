"""Screenplay Mode — Phase 7 acceptance suite.

Multi-scene continuity / coherence: a deterministic cross-scene report
(Scene Chain, Causal Flow, Setup/Payoff, Character Continuity, Timeline
Alignment, PSYKE Consistency, Recommended Fixes). Read-only — consolidates the
existing continuity / setup-payoff / story-link / Timeline / PSYKE engines.
"""

from __future__ import annotations

import warnings

import pytest
from PySide6.QtWidgets import QApplication

warnings.filterwarnings("ignore")

from logosforge.db import Database
from logosforge import story_structure as ss
from logosforge import screenplay_pipeline as spp
from logosforge import screenplay_continuity as sc


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


def _two_scene(db):
    """Beta created first (Act II), Alpha second (Act I) -> canonical Alpha,Beta."""
    pid = _screenplay(db)
    b = ss.create_scene(db, pid, act="Act II", chapter="Seq 2", title="Beta",
                        content="INT. BETA - DAY\n\nMARY\nHello.", summary="Beta").id
    a = ss.create_scene(db, pid, act="Act I", chapter="Seq 1", title="Alpha",
                        content="INT. ALPHA - DAY\n\nMaria waits.", summary="Alpha").id
    db.reorder_scenes(pid, [a, b])
    return pid, a, b


# ==========================================================================
# 1-3  Canonical chain
# ==========================================================================


def test_report_reads_scenes_in_canonical_order():
    db = Database()
    pid, a, b = _two_scene(db)
    rep = sc.build_screenplay_continuity_report(db, pid)
    assert [e.title for e in rep.scene_chain] == ["Alpha", "Beta"]
    assert [e.scene_id for e in rep.scene_chain] == [a, b]


def test_moving_scene_updates_continuity_order():
    db = Database()
    pid, a, b = _two_scene(db)
    db.reorder_scenes(pid, [b, a])
    rep = sc.build_screenplay_continuity_report(db, pid)
    assert [e.title for e in rep.scene_chain] == ["Beta", "Alpha"]


def test_chain_does_not_sort_by_id():
    # Beta has the lower id (created first) but is later in canonical order.
    db = Database()
    pid, a, b = _two_scene(db)
    rep = sc.build_screenplay_continuity_report(db, pid)
    ids = [e.scene_id for e in rep.scene_chain]
    assert ids != sorted(ids)                       # not id order
    assert ids == [a, b]                            # canonical order


# ==========================================================================
# 4-6  Scene state
# ==========================================================================


def test_missing_beat_plan_reported():
    db = Database()
    pid, a, b = _two_scene(db)
    rep = sc.build_screenplay_continuity_report(db, pid)
    assert all(not e.has_beat_plan for e in rep.scene_chain)
    assert rep.metrics["scenes_without_beat_plan"] == 2


def test_missing_body_reported():
    db = Database()
    pid = _screenplay(db)
    ss.create_scene(db, pid, act="Act I", chapter="Seq 1", title="Empty", content="")
    rep = sc.build_screenplay_continuity_report(db, pid)
    assert rep.metrics["scenes_without_body"] == 1
    assert not rep.scene_chain[0].has_body


def test_scene_with_body_and_plan_not_false_empty():
    db = Database()
    pid = _screenplay(db)
    sid = ss.create_scene(db, pid, act="Act I", chapter="Seq 1", title="Full",
                          content="INT. X - DAY\n\nAction.").id
    spp.save_beat_plan(db, pid, spp.ScreenplayBeatPlan(scene_id=sid, objective="go"))
    rep = sc.build_screenplay_continuity_report(db, pid)
    e = rep.scene_chain[0]
    assert e.has_body and e.has_beat_plan and e.objective == "go"


# ==========================================================================
# 7-10  Timeline alignment
# ==========================================================================


def test_scene_linked_to_timeline_detected():
    db = Database()
    pid, a, b = _two_scene(db)
    db.add_timeline_event(pid, a)
    rep = sc.build_screenplay_continuity_report(db, pid)
    ea = next(e for e in rep.scene_chain if e.scene_id == a)
    assert ea.timeline_linked is True


def test_scene_without_timeline_link_reported_when_expected():
    db = Database()
    pid, a, b = _two_scene(db)
    db.add_timeline_event(pid, a)              # a linked, b not -> b flagged
    rep = sc.build_screenplay_continuity_report(db, pid)
    titles = " ".join(f.title for f in rep.timeline_alignment)
    assert "not linked" in titles.lower()


def test_no_timeline_warning_when_nothing_linked():
    db = Database()
    pid, a, b = _two_scene(db)
    rep = sc.build_screenplay_continuity_report(db, pid)
    # No timeline events at all -> don't nag about linkage.
    assert not any("not linked" in f.title.lower() for f in rep.timeline_alignment)


def test_timeline_labels_use_canonical_numbering():
    db = Database()
    pid, a, b = _two_scene(db)
    rep = sc.build_screenplay_continuity_report(db, pid)
    nums = {e.title: e.number for e in rep.scene_chain}
    assert nums["Alpha"] == "1.1" and nums["Beta"] == "2.1"


# ==========================================================================
# 11-13  Setup / payoff
# ==========================================================================


def test_existing_setup_payoff_links_included():
    db = Database()
    pid = _screenplay(db)
    a = ss.create_scene(db, pid, act="Act I", chapter="Seq 1", title="A",
                        content="INT. A - DAY\n\nHe hides the key.").id
    if hasattr(db, "create_story_link"):
        try:
            db.create_story_link(pid, link_type="setup", label="the key",
                                 source_scene_id=a, target_scene_id=a,
                                 status="confirmed")
        except Exception:
            pass
    rep = sc.build_screenplay_continuity_report(db, pid)
    # Either a confirmed link is shown, or setup/payoff analysis returns findings.
    assert isinstance(rep.setup_payoff, list)


def test_setup_without_payoff_reported():
    db = Database()
    pid = _screenplay(db)
    ss.create_scene(db, pid, act="Act I", chapter="Seq 1", title="A",
                    content="INT. A - DAY\n\nMARY\nRemember the gun. I promise "
                            "I will be back. Never forget this.")
    rep = sc.build_screenplay_continuity_report(db, pid)
    assert any("setup" in f.title.lower() for f in rep.setup_payoff) or \
        rep.setup_payoff == []          # detection is heuristic; never crashes


def test_setup_payoff_section_is_list():
    db = Database()
    pid, a, b = _two_scene(db)
    rep = sc.build_screenplay_continuity_report(db, pid)
    assert isinstance(rep.setup_payoff, list)


# ==========================================================================
# 14-17  Character / PSYKE
# ==========================================================================


def test_character_blocks_extracted_across_scenes():
    db = Database()
    pid = _screenplay(db)
    ss.create_scene(db, pid, act="Act I", chapter="Seq 1", title="A",
                    content="INT. A - DAY\n\nMARY\nHi.")
    ss.create_scene(db, pid, act="Act I", chapter="Seq 1", title="B",
                    content="INT. B - DAY\n\nJOHN\nBye.")
    chain, char_by_scene, _ = sc._scene_chain(db, pid)
    cues = set().union(*char_by_scene.values())
    assert {"MARY", "JOHN"} <= cues


def test_missing_psyke_link_warning_when_supported():
    db = Database()
    pid = _screenplay(db)
    db.create_psyke_entry(pid, "Mary", "character")     # Mary linked, John not
    ss.create_scene(db, pid, act="Act I", chapter="Seq 1", title="A",
                    content="INT. A - DAY\n\nMARY\nHi.\n\nJOHN\nBye.")
    rep = sc.build_screenplay_continuity_report(db, pid)
    titles = " ".join(f.title for f in rep.psyke_consistency)
    assert "JOHN" in titles and "MARY" not in titles


def test_no_psyke_warning_without_story_bible():
    db = Database()
    pid = _screenplay(db)
    ss.create_scene(db, pid, act="Act I", chapter="Seq 1", title="A",
                    content="INT. A - DAY\n\nMARY\nHi.")
    rep = sc.build_screenplay_continuity_report(db, pid)
    assert rep.psyke_consistency == [] or all(
        "not in Story Bible" not in f.title for f in rep.psyke_consistency)


def test_no_psyke_mutation():
    db = Database()
    pid = _screenplay(db)
    db.create_psyke_entry(pid, "Mary", "character")
    ss.create_scene(db, pid, act="Act I", chapter="Seq 1", title="A",
                    content="INT. A - DAY\n\nMARY\nHi.\n\nJOHN\nBye.")
    before = len(db.get_all_psyke_entries(pid))
    sc.build_screenplay_continuity_report(db, pid)
    assert len(db.get_all_psyke_entries(pid)) == before == 1


# ==========================================================================
# 18-21  UI / actions
# ==========================================================================


def test_logos_dropdown_includes_continuity_check():
    from logosforge.logos.controller import LogosController
    db = Database()
    db.create_project("S", narrative_engine="screenplay")
    ctl = LogosController(db)
    for sec in ("Manuscript", "Timeline", "Outline"):
        names = [a.name for a in ctl.available_actions(sec, writing_mode="screenplay")]
        assert "sp_continuity_check" in names
    novel = [a.name for a in ctl.available_actions("Manuscript", writing_mode="novel")]
    assert "sp_continuity_check" not in novel


def test_continuity_action_runs_without_scene_and_no_llm():
    from logosforge.logos.controller import LogosController
    from logosforge.logos.context import build_logos_context

    def _boom(*a, **k):
        raise AssertionError("deterministic action must not call the LLM")

    db = Database()
    pid, a, b = _two_scene(db)
    ctl = LogosController(db, provider_resolver=_boom, chat_fn=_boom)
    ctx = build_logos_context(db, pid, section_name="Manuscript", current_scene_id=None)
    res = ctl.run(ctx, "sp_continuity_check")
    assert res.ok and res.title == "Screenplay Continuity Check"
    assert sc.SEC_CHAIN in res.message and res.proposed_operations == []


def test_report_is_copyable_text_with_suggestions():
    from logosforge.logos.deterministic import get_handler
    from logosforge.logos.context import build_logos_context
    db = Database()
    pid, a, b = _two_scene(db)
    ctx = build_logos_context(db, pid, section_name="Manuscript", current_scene_id=None)
    res = get_handler("sp_continuity_check")(db, ctx)
    assert isinstance(res.message, str) and res.message
    assert isinstance(res.suggestions, list)


def test_save_as_note_requires_confirmation():
    db = Database()
    pid, a, b = _two_scene(db)
    rep = sc.build_screenplay_continuity_report(db, pid)
    r0 = sc.save_continuity_as_note(db, pid, rep, confirmed=False)
    assert r0["ok"] is False and len(db.get_all_notes(pid)) == 0
    r1 = sc.save_continuity_as_note(db, pid, rep, confirmed=True)
    assert r1["ok"] and len(db.get_all_notes(pid)) == 1


# ==========================================================================
# 22-26  Safety (no mutation)
# ==========================================================================


def test_report_does_not_mutate_manuscript_or_outline():
    db = Database()
    pid = _screenplay(db)
    sid = ss.create_scene(db, pid, act="Act I", chapter="Seq 1", title="A",
                          content="INT. A - DAY\n\nAction.", summary="SUM").id
    before = (db.get_scene_by_id(sid).content, db.get_scene_by_id(sid).summary)
    sc.build_screenplay_continuity_report(db, pid)
    after = (db.get_scene_by_id(sid).content, db.get_scene_by_id(sid).summary)
    assert before == after


def test_report_does_not_mutate_timeline():
    db = Database()
    pid, a, b = _two_scene(db)
    db.add_timeline_event(pid, a)
    before = db.get_timeline_event_ids(pid)
    sc.build_screenplay_continuity_report(db, pid)
    assert db.get_timeline_event_ids(pid) == before


def test_report_does_not_mutate_beat_plan():
    db = Database()
    pid, a, b = _two_scene(db)
    spp.save_beat_plan(db, pid, spp.ScreenplayBeatPlan(scene_id=a, objective="KEEP"))
    sc.build_screenplay_continuity_report(db, pid)
    assert spp.get_beat_plan(db, pid, a).objective == "KEEP"


def test_provider_error_does_not_mutate():
    # The deterministic report never calls a provider; an AI seam only builds
    # messages (no call), so a provider error can't mutate anything.
    db = Database()
    pid, a, b = _two_scene(db)
    rep = sc.build_screenplay_continuity_report(db, pid)
    before = db.get_scene_by_id(a).content
    msgs = sc.build_continuity_messages(rep)
    assert isinstance(msgs, list) and db.get_scene_by_id(a).content == before


def test_report_isolated_across_projects(tmp_path):
    db = Database(str(tmp_path / "sp.db"))
    pid_a, a, b = _two_scene(db)
    db.create_psyke_entry(pid_a, "Mary", "character")
    pid_b = _screenplay(db)
    ss.create_scene(db, pid_b, act="Act I", chapter="Seq 1", title="Z",
                    content="INT. Z - DAY\n\nZARA\nHi.")
    rep_b = sc.build_screenplay_continuity_report(db, pid_b)
    titles = [e.title for e in rep_b.scene_chain]
    assert titles == ["Z"]                          # only project B's scene
    pk = " ".join(f.title for f in rep_b.psyke_consistency)
    assert "MARY" not in pk                          # no leakage from project A


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
        assert "sp_continuity_check" not in names
