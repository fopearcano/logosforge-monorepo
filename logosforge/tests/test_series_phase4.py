"""Series Mode — Phase 4 acceptance suite.

Counterpart / Reflection for episodic writing: a deterministic, non-mutating
multi-perspective report (Audience / Showrunner / Character Arc / Episode
Structure / Writers-Room) that re-projects the Phase 3 diagnostics + Phase 2 plans
+ PSYKE + Timeline into feedback and revision questions — never a rewrite. Optional
AI seam (explain-only) and opt-in, confirmed save-as-Note. No image generation.
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
from logosforge import series_reflection as sr


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


def _rich(db, title="SR"):
    """A deliberately weak Series scene + an Episode plan that expects markers,
    with no Season plan — exercises every reflection section."""
    pid = _series(db, title)
    sid = _scene(db, pid, content=(
        "INT. ROOM - DAY\n\nMaria waters her plants.\n\n"
        "MARIA\nThe weather is nice today and I water the plants."),
        summary="Maria waters plants", act="Act I", chapter="Episode 1")
    spp.save_episode_plan(db, pid, spp.EpisodeBeatPlan(
        chapter="Episode 1", episode_objective="overthrow the empire",
        a_story="the rebellion army", b_story="the secret romance",
        teaser_or_cold_open="cold open", act_breaks=["end of act one"],
        tag_or_button="the button", climax="the fall"))
    return pid, sid


# ==========================================================================
# 1-12  Reflection core
# ==========================================================================


def test_reflection_generated_for_scene():
    db = Database()
    pid, sid = _rich(db)
    rep = sr.build_scene_reflection(db, pid, sid)
    assert rep.scene_id == sid


def test_episode_reflection_generated():
    db = Database()
    pid, _sid = _rich(db)
    rep = sr.build_episode_reflection(db, pid, "Episode 1")
    assert rep.snapshot and rep.episode_label == "Episode 1"


def test_report_includes_snapshot():
    db = Database()
    pid, sid = _rich(db)
    assert sr.build_scene_reflection(db, pid, sid).snapshot


def test_report_includes_audience():
    db = Database()
    pid, sid = _rich(db)
    assert sr.build_scene_reflection(db, pid, sid).audience


def test_report_includes_showrunner():
    db = Database()
    pid, sid = _rich(db)
    assert sr.build_scene_reflection(db, pid, sid).showrunner


def test_report_includes_character_arc():
    db = Database()
    pid, sid = _rich(db)
    assert sr.build_scene_reflection(db, pid, sid).character_arc


def test_report_includes_episode_structure():
    db = Database()
    pid, sid = _rich(db)
    assert sr.build_scene_reflection(db, pid, sid).episode_structure


def test_report_includes_writers_room():
    db = Database()
    pid, sid = _rich(db)
    assert sr.build_scene_reflection(db, pid, sid).writers_room


def test_report_includes_abc_alignment():
    db = Database()
    pid, sid = _rich(db)
    assert sr.build_scene_reflection(db, pid, sid).abc_alignment


def test_report_includes_season_alignment():
    db = Database()
    pid, sid = _rich(db)
    assert sr.build_scene_reflection(db, pid, sid).season_alignment


def test_report_includes_revision_questions():
    db = Database()
    pid, sid = _rich(db)
    assert sr.build_scene_reflection(db, pid, sid).questions


def test_reflection_does_not_mutate_body():
    db = Database()
    pid, sid = _rich(db)
    before = db.get_scene_by_id(sid).content
    sr.build_scene_reflection(db, pid, sid)
    assert db.get_scene_by_id(sid).content == before


# ==========================================================================
# 13-16  Audience perspective
# ==========================================================================


def test_audience_detects_unclear_hook():
    db = Database()
    pid, sid = _rich(db)
    rep = sr.build_scene_reflection(db, pid, sid)
    assert any("hook" in i.title.lower() or "conflict" in i.title.lower()
               for i in rep.audience)


def test_audience_detects_exposition_heavy():
    db = Database()
    pid = _series(db)
    sid = _scene(db, pid, content=(
        "INT. X - DAY\n\nAction beat here.\n\n"
        "MARIA\nLine one here.\nLine two here.\nLine three here.\nLine four here."))
    rep = sr.build_scene_reflection(db, pid, sid)
    assert any("exposition" in i.title.lower() for i in rep.audience)


def test_audience_detects_weak_ending():
    db = Database()
    pid, sid = _rich(db)
    rep = sr.build_scene_reflection(db, pid, sid)
    assert any("new question" in i.title.lower() or "without" in i.title.lower()
               for i in rep.audience)


def test_audience_reports_takeaway_concern():
    db = Database()
    pid, sid = _rich(db)
    assert sr.build_scene_reflection(db, pid, sid).audience   # non-empty for weak scene


# ==========================================================================
# 17-20  Showrunner perspective
# ==========================================================================


def test_showrunner_detects_unclear_episode_function():
    db = Database()
    pid, sid = _rich(db)
    rep = sr.build_scene_reflection(db, pid, sid)
    assert any("job in the episode" in i.title.lower() for i in rep.showrunner)


def test_showrunner_detects_redundant_scene():
    db = Database()
    pid = _series(db)
    body = "INT. ROOM - DAY\n\nMaria waters the plants in the quiet room."
    _scene(db, pid, content=body, title="A", chapter="Episode 1")
    b = _scene(db, pid, content=body, title="B", chapter="Episode 1")
    rep = sr.build_scene_reflection(db, pid, b)
    assert any("repeat" in i.title.lower() for i in rep.showrunner)


def test_showrunner_detects_weak_abc_alignment():
    db = Database()
    pid, sid = _rich(db)
    rep = sr.build_scene_reflection(db, pid, sid)
    assert rep.abc_alignment   # plan defines A/B/C; scene doesn't echo them


def test_showrunner_detects_season_mismatch():
    db = Database()
    pid, sid = _rich(db)
    spp.save_season_plan(db, pid, spp.SeasonArcPlan(
        act="Act I", arc_question="who poisoned the chancellor"))
    rep = sr.build_scene_reflection(db, pid, sid)
    assert any("arc" in i.title.lower() for i in rep.season_alignment)


# ==========================================================================
# 21-24  Character arc perspective
# ==========================================================================


def test_character_blocks_detected():
    db = Database()
    pid, sid = _rich(db)
    rep = sr.build_scene_reflection(db, pid, sid)
    assert any(c.name == "MARIA" for c in rep.character_arc)


def test_unlinked_characters_reported():
    db = Database()
    pid, sid = _rich(db)            # no PSYKE entries created
    rep = sr.build_scene_reflection(db, pid, sid)
    maria = next(c for c in rep.character_arc if c.name == "MARIA")
    assert maria.linked is False and any("unlinked" in n.lower() for n in maria.notes)


def test_character_objective_unclear_warning():
    db = Database()
    pid, sid = _rich(db)
    rep = sr.build_scene_reflection(db, pid, sid)
    maria = next(c for c in rep.character_arc if c.name == "MARIA")
    assert maria.wants == "unclear"


def test_character_arc_movement_warning():
    db = Database()
    pid, sid = _rich(db)
    rep = sr.build_scene_reflection(db, pid, sid)
    maria = next(c for c in rep.character_arc if c.name == "MARIA")
    assert maria.arc_movement == "unclear"


# ==========================================================================
# 25-28  Episode structure
# ==========================================================================


def test_episode_structure_includes_cold_open():
    db = Database()
    pid, sid = _rich(db)
    rep = sr.build_scene_reflection(db, pid, sid)
    assert any("teaser" in i.title.lower() or "cold open" in i.title.lower()
               for i in rep.episode_structure)


def test_episode_structure_includes_act_break():
    db = Database()
    pid, sid = _rich(db)
    rep = sr.build_scene_reflection(db, pid, sid)
    assert any("act break" in i.title.lower() for i in rep.episode_structure)


def test_episode_structure_includes_tag():
    db = Database()
    pid, sid = _rich(db)
    rep = sr.build_scene_reflection(db, pid, sid)
    assert any("tag" in i.title.lower() for i in rep.episode_structure)


def test_beat_plan_mismatch_included():
    db = Database()
    pid = _series(db)
    # Scene carries an Act Break the Episode plan does not list.
    sid = _scene(db, pid, content="INT. X - DAY\n\nA beat.\n\nACT BREAK",
                 chapter="Episode 1")
    spp.save_episode_plan(db, pid, spp.EpisodeBeatPlan(
        chapter="Episode 1", episode_premise="a premise", climax="x"))
    rep = sr.build_scene_reflection(db, pid, sid)
    assert any("not in the episode plan" in i.title.lower() for i in rep.beat_alignment)


# ==========================================================================
# 29-31  AI fallback
# ==========================================================================


def test_deterministic_report_without_provider():
    db = Database()
    pid, sid = _rich(db)
    rep = sr.build_scene_reflection(db, pid, sid)   # no provider involved
    assert rep.ai_enhanced is False and rep.to_text()


def test_provider_error_does_not_mutate():
    from logosforge.logos.controller import LogosController
    from logosforge.logos.context import build_logos_context

    def _boom(*a, **k):
        raise AssertionError("reflection is deterministic — must not call the LLM")

    db = Database()
    pid, sid = _rich(db)
    before = db.get_scene_by_id(sid).content
    ctl = LogosController(db, provider_resolver=_boom, chat_fn=_boom)
    ctx = build_logos_context(db, pid, section_name="Manuscript", current_scene_id=sid)
    res = ctl.run(ctx, "series_reflection")
    assert res.ok and db.get_scene_by_id(sid).content == before


def test_ai_enhanced_messages_are_structured():
    db = Database()
    pid, sid = _rich(db)
    rep = sr.build_scene_reflection(db, pid, sid)
    msgs = sr.build_reflection_messages(rep, scene_context="[Scene] X")
    assert isinstance(msgs, list) and len(msgs) == 2
    assert msgs[0]["role"] == "system" and msgs[1]["role"] == "user"
    assert "do not" in msgs[1]["content"].lower()   # explain-only, no rewrite


# ==========================================================================
# 32-40  UI / actions
# ==========================================================================


def _series_actions(db, section="Manuscript"):
    from logosforge.logos.controller import LogosController
    return list(LogosController(db).available_actions(section, writing_mode="series"))


def test_logos_dropdown_contains_series_reflection():
    db = Database()
    _series(db)
    assert "series_reflection" in [a.name for a in _series_actions(db)]


def test_logos_dropdown_contains_showrunner_perspective():
    db = Database()
    _series(db)
    assert "series_showrunner_reflection" in [a.name for a in _series_actions(db)]


def test_reflection_actions_are_readable():
    db = Database()
    _series(db)
    refl = {a.name: a for a in _series_actions(db) if a.name in (
        "series_reflection", "series_audience_reflection", "series_showrunner_reflection",
        "series_character_reflection", "series_episode_structure_reflection",
        "series_writers_room")}
    assert len(refl) == 6
    for a in refl.values():
        assert len(a.label) >= 5 and a.description


def test_reflection_runs_without_selection():
    from logosforge.logos.controller import LogosController
    from logosforge.logos.context import build_logos_context
    db = Database()
    pid, sid = _rich(db)
    ctl = LogosController(db)
    ctx = build_logos_context(db, pid, section_name="Manuscript", current_scene_id=sid)
    assert ctx.selected_text == ""
    res = ctl.run(ctx, "series_reflection")
    assert res.ok and res.message


def test_episode_structure_action_runs_from_scene_context():
    from logosforge.logos.controller import LogosController
    from logosforge.logos.context import build_logos_context
    db = Database()
    pid, sid = _rich(db)
    ctl = LogosController(db)
    ctx = build_logos_context(db, pid, section_name="Manuscript", current_scene_id=sid)
    res = ctl.run(ctx, "series_episode_structure_reflection")
    assert res.ok and "Episode Structure" in res.message


def test_reflection_actions_do_not_require_selection():
    db = Database()
    _series(db)
    for a in _series_actions(db):
        if "reflection" in a.name or a.name == "series_writers_room":
            assert a.needs_selection is False


def test_assistant_reflection_action_is_deterministic():
    from logosforge.logos.controller import LogosController
    from logosforge.logos.context import build_logos_context

    def _boom(*a, **k):
        raise AssertionError("must not call the LLM")

    db = Database()
    pid, sid = _rich(db)
    ctl = LogosController(db, provider_resolver=_boom, chat_fn=_boom)
    ctx = build_logos_context(db, pid, section_name="Manuscript", current_scene_id=sid)
    for action in ("series_reflection", "series_audience_reflection",
                   "series_showrunner_reflection", "series_character_reflection",
                   "series_episode_structure_reflection", "series_writers_room"):
        res = ctl.run(ctx, action)
        assert res.ok and res.proposed_operations == [] and res.message


def test_report_appears_in_response_area():
    from logosforge.logos.controller import LogosController
    from logosforge.logos.context import build_logos_context
    db = Database()
    pid, sid = _rich(db)
    ctl = LogosController(db)
    ctx = build_logos_context(db, pid, section_name="Manuscript", current_scene_id=sid)
    res = ctl.run(ctx, "series_reflection")
    assert isinstance(res.message, str) and "Scene Snapshot" in res.message


# ==========================================================================
# 41-43  Optional Notes
# ==========================================================================


def test_save_reflection_requires_confirmation():
    db = Database()
    pid, sid = _rich(db)
    rep = sr.build_scene_reflection(db, pid, sid)
    res = sr.save_reflection_as_note(db, pid, sid, rep, confirmed=False)
    assert res["ok"] is False


def test_saved_note_links_to_scene():
    db = Database()
    pid, sid = _rich(db)
    rep = sr.build_scene_reflection(db, pid, sid)
    res = sr.save_reflection_as_note(db, pid, sid, rep, confirmed=True)
    assert res["ok"] and sid in db.get_note_scene_links(res["note_id"])


def test_cancel_save_does_not_mutate_notes():
    db = Database()
    pid, sid = _rich(db)
    rep = sr.build_scene_reflection(db, pid, sid)
    before = len(db.get_all_notes(pid))
    sr.save_reflection_as_note(db, pid, sid, rep, confirmed=False)
    assert len(db.get_all_notes(pid)) == before


# ==========================================================================
# Regression guards
# ==========================================================================


def test_no_image_generation_in_reflection():
    import os, tokenize
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = os.path.join(here, "logosforge", "series_reflection.py")
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


def test_reflection_actions_absent_from_other_modes():
    from logosforge.logos.controller import LogosController
    db = Database()
    for engine in ("novel", "screenplay", "graphic_novel", "stage_script"):
        db.create_project(engine, narrative_engine=engine,
                          default_writing_format=engine)
        names = [a.name for a in LogosController(db).available_actions(
            "Manuscript", writing_mode=engine)]
        assert not any(n.startswith("series_") for n in names)
