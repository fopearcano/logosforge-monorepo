"""Series Mode — Phase 6 acceptance suite.

Cross-episode continuity / coherence: a deterministic, read-only report that reads
the canonical Season -> Episode -> Scene chain and consolidates season/arc
coherence, the episode chain, A/B/C story tracking, character arcs, setup/payoff,
episode structure, Timeline alignment, and PSYKE/Notes. No mutation, no auto-apply,
no LLM required, no image generation.
"""

from __future__ import annotations

import warnings

import pytest
from PySide6.QtWidgets import QApplication

warnings.filterwarnings("ignore")

from logosforge.db import Database
from logosforge import story_structure as ss
from logosforge import series_pipeline as spp
from logosforge import series_continuity as sc


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


def _report(db, pid):
    return sc.build_series_continuity_report(db, pid)


def _findings(report):
    return report.all_findings()


# ==========================================================================
# 1-4  Canonical chain
# ==========================================================================


def test_chain_reads_episodes_in_canonical_order():
    db = Database()
    pid = _series(db)
    a = _scene(db, pid, content="INT. A - DAY\n\na.", title="A", chapter="Episode 1")
    b = _scene(db, pid, content="INT. B - DAY\n\nb.", title="B", chapter="Episode 2")
    db.reorder_scenes(pid, [a, b])
    rep = _report(db, pid)
    assert [e.chapter for e in rep.episode_chain] == ["Episode 1", "Episode 2"]


def test_moving_episode_updates_order():
    db = Database()
    pid = _series(db)
    a = _scene(db, pid, content="INT. A - DAY\n\na.", title="A", chapter="Episode 1")
    b = _scene(db, pid, content="INT. B - DAY\n\nb.", title="B", chapter="Episode 2")
    db.reorder_scenes(pid, [b, a])      # Episode 2 first
    rep = _report(db, pid)
    assert [e.chapter for e in rep.episode_chain] == ["Episode 2", "Episode 1"]


def test_moving_scene_updates_order():
    db = Database()
    pid = _series(db)
    # Two episodes, created out of order; canonical order follows sort_order.
    b = _scene(db, pid, content="INT. B - DAY\n\nb.", title="B", chapter="Episode 2")
    a = _scene(db, pid, content="INT. A - DAY\n\na.", title="A", chapter="Episode 1")
    db.reorder_scenes(pid, [a, b])
    rep = _report(db, pid)
    assert [e.chapter for e in rep.episode_chain] == ["Episode 1", "Episode 2"]


def test_chain_not_sorted_by_id():
    db = Database()
    pid = _series(db)
    b = _scene(db, pid, content="INT. B - DAY\n\nb.", title="B", chapter="Episode 2")
    a = _scene(db, pid, content="INT. A - DAY\n\na.", title="A", chapter="Episode 1")
    db.reorder_scenes(pid, [a, b])
    rep = _report(db, pid)
    # Episode 1 (higher scene id) comes first because canonical order != id order.
    assert rep.episode_chain[0].chapter == "Episode 1" and a > b


# ==========================================================================
# 5-9  Episode / scene state
# ==========================================================================


def test_missing_season_plan_reported():
    db = Database()
    pid = _series(db)
    _scene(db, pid, content="INT. X - DAY\n\nx.")
    rep = _report(db, pid)
    assert any("season / arc plan" in f.title.lower() for f in rep.season_overview)


def test_missing_episode_plan_reported():
    db = Database()
    pid = _series(db)
    _scene(db, pid, content="INT. X - DAY\n\nx.", chapter="Episode 1")
    rep = _report(db, pid)
    assert any("beat plan" in f.title.lower() for f in rep.episode_structure)


def test_missing_series_body_reported():
    db = Database()
    pid = _series(db)
    _scene(db, pid, content="", chapter="Episode 1")   # scene exists, no body
    rep = _report(db, pid)
    assert any("body" in f.title.lower() for f in rep.episode_structure)


def test_empty_episode_reported():
    db = Database()
    pid = _series(db)
    _scene(db, pid, content="", chapter="Episode 1")
    rep = _report(db, pid)
    assert rep.metrics["episodes_without_body"] >= 1


def test_episode_with_body_not_falsely_empty():
    db = Database()
    pid = _series(db)
    _scene(db, pid, content="INT. X - DAY\n\nReal action.", chapter="Episode 1")
    rep = _report(db, pid)
    e = next(x for x in rep.episode_chain if x.chapter == "Episode 1")
    assert e.body_scene_count == 1


# ==========================================================================
# 10-15  A/B/C story tracking
# ==========================================================================


def test_a_story_support_detected():
    db = Database()
    pid = _series(db)
    _scene(db, pid, content="INT. BANK - DAY\n\nThey plan the heist carefully.",
           chapter="Episode 1")
    spp.save_episode_plan(db, pid, spp.EpisodeBeatPlan(
        chapter="Episode 1", a_story="the bank heist"))
    rep = _report(db, pid)
    e = next(x for x in rep.episode_chain if x.chapter == "Episode 1")
    assert e.abc_support.get("A", 0) >= 1


def test_b_story_support_detected():
    db = Database()
    pid = _series(db)
    _scene(db, pid, content="INT. CAFE - DAY\n\nThe romance blossoms over coffee.",
           chapter="Episode 1")
    spp.save_episode_plan(db, pid, spp.EpisodeBeatPlan(
        chapter="Episode 1", a_story="anything", b_story="the romance subplot"))
    rep = _report(db, pid)
    e = next(x for x in rep.episode_chain if x.chapter == "Episode 1")
    assert e.abc_support.get("B", 0) >= 1


def test_missing_a_story_support_reported():
    db = Database()
    pid = _series(db)
    _scene(db, pid, content="INT. X - DAY\n\nMaria waters plants.", chapter="Episode 1")
    spp.save_episode_plan(db, pid, spp.EpisodeBeatPlan(
        chapter="Episode 1", a_story="the bank heist downtown"))
    rep = _report(db, pid)
    assert any("a-story has no scene support" in f.title.lower()
               for f in rep.abc_tracking)


def test_missing_b_story_support_reported():
    db = Database()
    pid = _series(db)
    _scene(db, pid, content="INT. X - DAY\n\nThe heist begins.", chapter="Episode 1")
    spp.save_episode_plan(db, pid, spp.EpisodeBeatPlan(
        chapter="Episode 1", a_story="the heist", b_story="the secret romance"))
    rep = _report(db, pid)
    assert any("b-story has no scene support" in f.title.lower()
               for f in rep.abc_tracking)


def test_thread_introduced_then_abandoned_reported():
    db = Database()
    pid = _series(db)
    _scene(db, pid, content="INT. BANK - DAY\n\nThe heist crew assembles.",
           title="A", chapter="Episode 1")
    _scene(db, pid, content="INT. PARK - DAY\n\nBirds sing softly.",
           title="B", chapter="Episode 2")
    spp.save_episode_plan(db, pid, spp.EpisodeBeatPlan(chapter="Episode 1",
                                                       a_story="the heist crew"))
    spp.save_episode_plan(db, pid, spp.EpisodeBeatPlan(chapter="Episode 2",
                                                       a_story="the heist crew"))
    rep = _report(db, pid)
    assert any("abandoned" in f.title.lower() for f in rep.abc_tracking)


def test_abc_unavailable_when_no_threads():
    db = Database()
    pid = _series(db)
    _scene(db, pid, content="INT. X - DAY\n\nx.", chapter="Episode 1")
    spp.save_episode_plan(db, pid, spp.EpisodeBeatPlan(
        chapter="Episode 1", episode_premise="a premise", climax="c"))   # no A/B/C
    rep = _report(db, pid)
    assert any("unavailable" in f.title.lower() for f in rep.abc_tracking)


# ==========================================================================
# 16-20  Season / Arc alignment
# ==========================================================================


def test_episode_not_connected_to_arc_warned():
    db = Database()
    pid = _series(db)
    _scene(db, pid, content="INT. X - DAY\n\nMaria waters plants.", act="Act I",
           chapter="Episode 1", summary="watering")
    spp.save_season_plan(db, pid, spp.SeasonArcPlan(
        act="Act I", arc_question="who murdered the senator"))
    rep = _report(db, pid)
    assert any("arc" in f.title.lower() for f in rep.season_overview)


def test_setup_payoff_without_support_reported():
    db = Database()
    pid = _series(db)
    _scene(db, pid, content="INT. X - DAY\n\nMaria waters plants.", act="Act I",
           chapter="Episode 1")
    spp.save_season_plan(db, pid, spp.SeasonArcPlan(
        act="Act I", setup_payoff_notes="the hidden treasure vault"))
    rep = _report(db, pid)
    assert any("setup" in f.title.lower() for f in rep.setup_payoff)


def test_cliffhanger_without_followthrough_reported():
    db = Database()
    pid = _series(db)
    _scene(db, pid, content="INT. X - DAY\n\nMaria waters plants.", act="Act I",
           chapter="Episode 1")
    spp.save_season_plan(db, pid, spp.SeasonArcPlan(
        act="Act I", cliffhanger_reveal_notes="the long-lost twin returns"))
    rep = _report(db, pid)
    assert any("cliffhanger" in f.title.lower() for f in rep.setup_payoff)


def test_recurring_motif_support_detected():
    db = Database()
    pid = _series(db)
    _scene(db, pid, content="INT. HALL - DAY\n\nShe opens the red door slowly.",
           act="Act I", chapter="Episode 1")
    spp.save_season_plan(db, pid, spp.SeasonArcPlan(
        act="Act I", recurring_motifs=["the red door"]))
    rep = _report(db, pid)
    assert not any("motif" in f.title.lower() for f in rep.setup_payoff)   # supported


def test_season_plan_not_mutated():
    db = Database()
    pid = _series(db)
    _scene(db, pid, content="INT. X - DAY\n\nx.", act="Act I", chapter="Episode 1")
    spp.save_season_plan(db, pid, spp.SeasonArcPlan(act="Act I", premise="KEEP"))
    _report(db, pid)
    assert spp.get_season_plan(db, pid, "Act I").premise == "KEEP"


# ==========================================================================
# 21-24  Episode structure
# ==========================================================================


def test_cold_open_without_followup_warned():
    db = Database()
    pid = _series(db)
    # Single scene that is the cold open — nothing follows it.
    _scene(db, pid, content="COLD OPEN\n\nINT. X - NIGHT\n\nA shocking image.",
           chapter="Episode 1")
    rep = _report(db, pid)
    assert any("cold open" in f.title.lower() for f in rep.progression)


def test_tag_not_connected_to_turn_warned():
    db = Database()
    pid = _series(db)
    _scene(db, pid, content="INT. X - DAY\n\nA calm beat.\n\nTAG", chapter="Episode 1")
    rep = _report(db, pid)
    assert any("tag" in f.title.lower() for f in rep.progression)


def test_act_break_expected_but_missing_warned():
    db = Database()
    pid = _series(db)
    _scene(db, pid, content="INT. X - DAY\n\nA beat.", chapter="Episode 1")
    spp.save_episode_plan(db, pid, spp.EpisodeBeatPlan(
        chapter="Episode 1", act_breaks=["end of act one"], climax="c"))
    rep = _report(db, pid)
    assert any("act break" in f.title.lower() for f in rep.episode_structure)


def test_episode_progression_mismatch_reported():
    db = Database()
    pid = _series(db)
    _scene(db, pid, content="INT. X - DAY\n\nx.", act="Act I", chapter="Episode 1")
    spp.save_season_plan(db, pid, spp.SeasonArcPlan(
        act="Act I", episode_progression=["beat a", "beat b", "beat c"]))
    rep = _report(db, pid)
    assert any("progression mismatch" in f.title.lower() for f in rep.season_overview)


# ==========================================================================
# 25-28  Timeline alignment
# ==========================================================================


def test_timeline_linked_scene_detected():
    db = Database()
    pid = _series(db)
    a = _scene(db, pid, content="INT. A - DAY\n\na.", chapter="Episode 1")
    db.add_timeline_event(pid, a)
    rep = _report(db, pid)
    assert rep.metrics["timeline_linked_episodes"] >= 1
    e = next(x for x in rep.episode_chain if x.chapter == "Episode 1")
    assert e.timeline_linked_count >= 1


def test_unlinked_episode_reported_when_expected():
    db = Database()
    pid = _series(db)
    a = _scene(db, pid, content="INT. A - DAY\n\na.", chapter="Episode 1")
    _scene(db, pid, content="INT. B - DAY\n\nb.", chapter="Episode 2")
    db.add_timeline_event(pid, a)   # Episode 1 linked, Episode 2 not
    rep = _report(db, pid)
    assert any("not linked to the timeline" in f.title.lower()
               for f in rep.timeline_alignment)


def test_timeline_order_mismatch_warning():
    db = Database()
    pid = _series(db)
    a = _scene(db, pid, content="INT. A - DAY\n\na.", title="A", chapter="Episode 1")
    b = _scene(db, pid, content="INT. B - DAY\n\nb.", title="B", chapter="Episode 2")
    db.reorder_scenes(pid, [a, b])
    db.add_timeline_event(pid, a)
    db.add_timeline_event(pid, b)
    db.set_timeline_order_mode(pid, "custom")
    db.set_timeline_order(pid, [b, a])
    rep = _report(db, pid)
    assert any("order differs" in f.title.lower() for f in rep.timeline_alignment)


def test_timeline_labels_use_canonical_numbering():
    db = Database()
    pid = _series(db)
    a = _scene(db, pid, content="INT. A - DAY\n\na.", chapter="Episode 1")
    db.add_timeline_event(pid, a)
    tree = ss.build_structure_tree(db, pid)
    nums = ss.compute_structural_numbers(tree, ss.is_novel_project(db, pid))
    expected = nums["scenes"].get(a)
    rep = _report(db, pid)
    canonical = next((f for f in rep.timeline_alignment
                      if "canonical" in f.title.lower()), None)
    assert canonical is not None and expected and expected in canonical.detail


# ==========================================================================
# 29-32  PSYKE / Notes
# ==========================================================================


def test_missing_psyke_link_warned():
    db = Database()
    pid = _series(db)
    db.create_psyke_entry(pid, "Maria", "character")
    _scene(db, pid, content="INT. X - DAY\n\nJOHN\nHello.", chapter="Episode 1")
    rep = _report(db, pid)
    assert any("john" in f.title.lower() and "story bible" in f.title.lower()
               for f in rep.psyke_notes)


def test_linked_notes_included():
    db = Database()
    pid = _series(db)
    sid = _scene(db, pid, content="INT. X - DAY\n\nx.", chapter="Episode 1")
    note = db.create_note(pid, "n", "b")
    db.link_note_to_scene(getattr(note, "id", note), sid)
    rep = _report(db, pid)
    assert any("note" in f.title.lower() for f in rep.psyke_notes)


def test_report_does_not_mutate_psyke():
    db = Database()
    pid = _series(db)
    db.create_psyke_entry(pid, "Maria", "character")
    _scene(db, pid, content="INT. X - DAY\n\nMARIA\nHi.", chapter="Episode 1")
    before = len(db.get_all_psyke_entries(pid))
    _report(db, pid)
    assert len(db.get_all_psyke_entries(pid)) == before == 1


def test_report_does_not_mutate_notes():
    db = Database()
    pid = _series(db)
    sid = _scene(db, pid, content="INT. X - DAY\n\nx.", chapter="Episode 1")
    note = db.create_note(pid, "n", "b")
    db.link_note_to_scene(getattr(note, "id", note), sid)
    before = len(db.get_all_notes(pid))
    _report(db, pid)
    assert len(db.get_all_notes(pid)) == before


# ==========================================================================
# 33-36  UI / actions
# ==========================================================================


def test_logos_includes_continuity_check():
    from logosforge.logos.controller import LogosController
    db = Database()
    _series(db)
    for section in ("Manuscript", "Timeline", "Outline"):
        names = [a.name for a in LogosController(db).available_actions(
            section, writing_mode="series")]
        assert "series_continuity_check" in names


def test_assistant_continuity_action_is_deterministic():
    from logosforge.logos.controller import LogosController
    from logosforge.logos.context import build_logos_context

    def _boom(*a, **k):
        raise AssertionError("continuity check must not call the LLM")

    db = Database()
    pid = _series(db)
    _scene(db, pid, content="INT. X - DAY\n\nx.", chapter="Episode 1")
    ctl = LogosController(db, provider_resolver=_boom, chat_fn=_boom)
    ctx = build_logos_context(db, pid, section_name="Timeline")
    res = ctl.run(ctx, "series_continuity_check")
    assert res.ok and res.proposed_operations == [] and res.message


def test_report_is_copyable_text():
    db = Database()
    pid = _series(db)
    _scene(db, pid, content="INT. X - DAY\n\nx.", chapter="Episode 1")
    text = _report(db, pid).to_text()
    assert isinstance(text, str) and "Series Continuity" in text


def test_save_as_note_requires_confirmation():
    db = Database()
    pid = _series(db)
    _scene(db, pid, content="INT. X - DAY\n\nx.", chapter="Episode 1")
    rep = _report(db, pid)
    assert sc.save_continuity_as_note(db, pid, rep, confirmed=False)["ok"] is False
    res = sc.save_continuity_as_note(db, pid, rep, confirmed=True)
    assert res["ok"] and res["note_id"]


# ==========================================================================
# 37-41  Safety
# ==========================================================================


def test_report_does_not_mutate_manuscript():
    db = Database()
    pid = _series(db)
    sid = _scene(db, pid, content="INT. X - DAY\n\nKEEP body.", chapter="Episode 1")
    _report(db, pid)
    assert db.get_scene_by_id(sid).content == "INT. X - DAY\n\nKEEP body."


def test_report_does_not_mutate_outline():
    db = Database()
    pid = _series(db)
    sid = _scene(db, pid, content="INT. X - DAY\n\nx.", summary="KEEP_SUMMARY",
                 chapter="Episode 1")
    _report(db, pid)
    assert db.get_scene_by_id(sid).summary == "KEEP_SUMMARY"


def test_report_does_not_mutate_timeline():
    db = Database()
    pid = _series(db)
    a = _scene(db, pid, content="INT. A - DAY\n\na.", chapter="Episode 1")
    db.add_timeline_event(pid, a)
    before = db.get_timeline_event_ids(pid)
    _report(db, pid)
    assert db.get_timeline_event_ids(pid) == before


def test_provider_error_does_not_mutate():
    from logosforge.logos.controller import LogosController
    from logosforge.logos.context import build_logos_context

    def _boom(*a, **k):
        raise AssertionError("must not call the LLM")

    db = Database()
    pid = _series(db)
    sid = _scene(db, pid, content="INT. X - DAY\n\nKEEP.", chapter="Episode 1")
    ctl = LogosController(db, provider_resolver=_boom, chat_fn=_boom)
    ctx = build_logos_context(db, pid, section_name="Manuscript", current_scene_id=sid)
    res = ctl.run(ctx, "series_continuity_check")
    assert res.ok and db.get_scene_by_id(sid).content == "INT. X - DAY\n\nKEEP."


# ==========================================================================
# Regression guards
# ==========================================================================


def test_no_image_generation_in_continuity():
    import os, tokenize
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = os.path.join(here, "logosforge", "series_continuity.py")
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


def test_continuity_action_absent_from_other_modes():
    from logosforge.logos.controller import LogosController
    db = Database()
    for engine in ("novel", "screenplay", "graphic_novel", "stage_script"):
        db.create_project(engine, narrative_engine=engine,
                          default_writing_format=engine)
        names = [a.name for a in LogosController(db).available_actions(
            "Manuscript", writing_mode=engine)]
        assert not any(n.startswith("series_") for n in names)
