"""Series Mode — Phase 8 full integration integrity audit.

End-to-end smoke + cross-mode regression + scope/privacy/isolation guards for the
universal-Manuscript Series writing system (Phases 1-7). This suite is
audit/stabilization: it asserts the phases work *together* and that Series did not
break Novel / Screenplay / Graphic Novel / Stage Script, leak across projects,
introduce a Season/Episode storage hierarchy, or add any image-generation /
production-automation surface. No new features.
"""

from __future__ import annotations

import os
import tokenize
import warnings

import pytest
from PySide6.QtWidgets import QApplication

warnings.filterwarnings("ignore")

from logosforge.db import Database
from logosforge import story_structure as ss
from logosforge import series_blocks as sbk
from logosforge import series_pipeline as spp
from logosforge import series_diagnostics as sd
from logosforge import series_reflection as sr
from logosforge import series_rewrite as srw
from logosforge import series_continuity as scont
from logosforge import series_dashboard as sdash
from logosforge.writing_modes import (
    get_project_writing_mode_by_id, current_primary_unit_type,
    NOVEL, SCREENPLAY, GRAPHIC_NOVEL, STAGE_SCRIPT, SERIES,
)

_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SERIES_MODULES = (
    "logosforge/series_blocks.py", "logosforge/series_pipeline.py",
    "logosforge/series_diagnostics.py", "logosforge/series_reflection.py",
    "logosforge/series_rewrite.py", "logosforge/series_continuity.py",
    "logosforge/series_dashboard.py", "logosforge/ui/series_review_view.py",
)


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


def _code_skeleton(rel_path: str) -> str:
    """Tokenized source with comments + string literals removed (honest disclaimer
    docstrings don't count as scope creep)."""
    toks = []
    with open(os.path.join(_HERE, rel_path), "rb") as fh:
        for tok in tokenize.tokenize(fh.readline):
            name = tokenize.tok_name[tok.type]
            if tok.type == tokenize.COMMENT or name.endswith("STRING"):
                continue
            toks.append(tok.string.lower())
    return " ".join(toks)


# ==========================================================================
# 1  Full Series smoke flow (all phases together)
# ==========================================================================


def test_full_series_smoke_flow():
    db = Database()
    pid = _series(db)
    assert get_project_writing_mode_by_id(db, pid) == SERIES
    assert current_primary_unit_type(db.get_project_by_id(pid)) == "scene"
    sid = _scene(db, pid, content="", title="Pilot", summary="Maria escapes")

    # Phase 1 — Series blocks via the scene body.
    script = sbk.SeriesScript()
    sbk.add_block(script, sbk.BT_SCENE_HEADING, "INT. CELL - NIGHT")
    sbk.add_block(script, sbk.BT_ACTION, "Maria tests the bars.")
    sbk.save_scene_script(db, sid, script)
    assert "INT. CELL" in db.get_scene_by_id(sid).content

    # Phase 2 — Season/Arc plan -> Episode beat plan (accept).
    spp.save_season_plan(db, pid, spp.parse_season_plan_response(
        "Premise: a kingdom falls\nArc Question: who rules", act="Act I"))
    spp.save_episode_plan(db, pid, spp.parse_episode_plan_response(
        "Premise: the pilot\nA Story: the escape", chapter="Episode 1"))
    assert spp.get_season_plan(db, pid, "Act I").premise == "a kingdom falls"
    assert spp.get_episode_plan(db, pid, "Episode 1").a_story == "the escape"

    # Phase 2 — draft preview (no mutation) then confirmed apply.
    draft = spp.parse_draft_response(
        "INT. CELL - NIGHT\n\nMaria escapes the cell.\n\nMARIA\nLet us go.")
    before = db.get_scene_by_id(sid).content
    assert spp.preview_draft_apply(db, pid, sid, draft, mode=spp.APPLY_REPLACE) is not None
    assert db.get_scene_by_id(sid).content == before
    assert spp.apply_draft(db, pid, sid, draft, mode=spp.APPLY_REPLACE,
                           confirmed=True)["ok"]
    assert "Maria escapes the cell" in db.get_scene_by_id(sid).content

    # Phase 3 — health, Phase 4 — reflection, Phase 5 — rewrite preview + cancel.
    assert sd.analyze_scene_by_id(db, pid, sid).metrics.total_blocks >= 1
    refl = sr.build_scene_reflection(db, pid, sid)
    assert "Scene Snapshot" in refl.to_text()
    body = db.get_scene_by_id(sid).content
    srw.build_rewrite_preview(db, pid, sid, "INT. NEW - DAY\n\nx.",
                              target=srw.TARGET_SCENE)
    assert db.get_scene_by_id(sid).content == body
    assert srw.apply_rewrite(db, pid, sid, "x", target=srw.TARGET_SCENE,
                             mode=srw.MODE_CANCEL, confirmed=True).get("cancelled")
    assert db.get_scene_by_id(sid).content == body

    # Phase 6 — continuity, Phase 7 — dashboard, export.
    assert scont.build_series_continuity_report(db, pid).episode_chain
    review = sdash.build_series_review(db, pid)
    assert review.total_episodes == 1 and review.written_scenes == 1
    assert "Maria escapes the cell" in sbk.export_project_markdown(db, pid)


# ==========================================================================
# 2  No auto-mutation across reporting / preview phases
# ==========================================================================


def test_reports_and_previews_never_mutate():
    db = Database()
    pid = _series(db)
    sid = _scene(db, pid, content="INT. X - DAY\n\nMaria waits.\n\nMARIA\nNow.",
                 summary="KEEP_SUMMARY")
    spp.save_season_plan(db, pid, spp.SeasonArcPlan(act="Act I", premise="KEEP_S"))
    spp.save_episode_plan(db, pid, spp.EpisodeBeatPlan(chapter="Episode 1",
                                                       a_story="KEEP_E"))
    body = db.get_scene_by_id(sid).content
    # Every read-only surface.
    sd.analyze_scene_by_id(db, pid, sid)
    sd.analyze_episode(db, pid, "Episode 1")
    sr.build_scene_reflection(db, pid, sid)
    sr.build_episode_reflection(db, pid, "Episode 1")
    scont.build_series_continuity_report(db, pid)
    sdash.build_series_review(db, pid)
    srw.build_rewrite_preview(db, pid, sid, "INT. Z - DAY\n\nz.", target=srw.TARGET_SCENE)
    assert db.get_scene_by_id(sid).content == body
    assert db.get_scene_by_id(sid).summary == "KEEP_SUMMARY"
    assert spp.get_season_plan(db, pid, "Act I").premise == "KEEP_S"
    assert spp.get_episode_plan(db, pid, "Episode 1").a_story == "KEEP_E"


# ==========================================================================
# 3  Canonical order shared by every surface
# ==========================================================================


def test_canonical_order_shared_across_surfaces():
    db = Database()
    pid = _series(db)
    a = _scene(db, pid, content="INT. A - DAY\n\nAlpha beat.", title="Alpha",
               chapter="Episode 1")
    b = _scene(db, pid, content="INT. B - DAY\n\nBeta beat.", title="Beta",
               act="Act I", chapter="Episode 2")
    db.reorder_scenes(pid, [b, a])   # Beta/Episode 2 first
    canonical = ss.canonical_scene_order(db, pid)
    assert canonical == [b, a]
    # Continuity chain, dashboard, and export all follow canonical order.
    chain = [e.chapter for e in scont.build_series_continuity_report(db, pid).episode_chain]
    assert chain == ["Episode 2", "Episode 1"]
    dash = [r.title for r in sdash.build_series_review(db, pid).scenes]
    assert dash == ["Beta", "Alpha"]
    md = sbk.export_project_markdown(db, pid)
    assert md.index("Beta beat") < md.index("Alpha beat")


# ==========================================================================
# 4-7  Other-mode regression (mode recognition + gating preserved)
# ==========================================================================


def test_novel_mode_preserved():
    db = Database()
    nid = db.create_project("N", narrative_engine="novel").id
    assert get_project_writing_mode_by_id(db, nid) == NOVEL
    assert current_primary_unit_type(db.get_project_by_id(nid)) == "chapter"
    from logosforge.ui.writing_core_view import WritingCoreView
    ss.create_scene(db, nid, act="Act 1", chapter="Chapter 1", title="C", content="Prose.")
    view = WritingCoreView(db, nid, structured_list=True)
    ed = next(iter(view._editors.values()))
    assert ed._screenplay_mode is False and ed._graphic_novel_mode is False


def test_screenplay_mode_preserved():
    db = Database()
    pid = db.create_project("SP", narrative_engine="screenplay",
                            default_writing_format="screenplay").id
    assert get_project_writing_mode_by_id(db, pid) == SCREENPLAY
    from logosforge.logos.controller import LogosController
    names = [a.name for a in LogosController(db).available_actions(
        "Manuscript", writing_mode="screenplay")]
    assert any(n.startswith("sp_") for n in names)
    assert not any(n.startswith("series_") for n in names)


def test_graphic_novel_mode_preserved():
    db = Database()
    pid = db.create_project("GN", narrative_engine="graphic_novel",
                            default_writing_format="graphic_novel").id
    assert get_project_writing_mode_by_id(db, pid) == GRAPHIC_NOVEL
    from logosforge.logos.controller import LogosController
    names = [a.name for a in LogosController(db).available_actions(
        "Manuscript", writing_mode="graphic_novel")]
    assert any(n.startswith("gn_") for n in names)
    assert not any(n.startswith("series_") for n in names)


def test_stage_script_mode_preserved():
    db = Database()
    pid = db.create_project("ST", narrative_engine="stage_script",
                            default_writing_format="stage_script").id
    assert get_project_writing_mode_by_id(db, pid) == STAGE_SCRIPT
    from logosforge.logos.controller import LogosController
    names = [a.name for a in LogosController(db).available_actions(
        "Manuscript", writing_mode="stage_script")]
    assert any(n.startswith("stage_") for n in names)
    assert not any(n.startswith("series_") for n in names)


def test_series_actions_only_in_series_mode():
    from logosforge.logos.controller import LogosController
    db = Database()
    for engine in ("novel", "screenplay", "graphic_novel", "stage_script"):
        db.create_project(engine, narrative_engine=engine,
                          default_writing_format=engine)
        for section in ("Manuscript", "Outline", "Timeline"):
            names = [a.name for a in LogosController(db).available_actions(
                section, writing_mode=engine)]
            assert not any(n.startswith("series_") for n in names)
    db.create_project("SR", narrative_engine="series", default_writing_format="series")
    series_names = [a.name for a in LogosController(db).available_actions(
        "Manuscript", writing_mode="series")]
    assert any(n.startswith("series_") for n in series_names)


# ==========================================================================
# 8  Project isolation across every Series surface
# ==========================================================================


def test_series_data_isolated_across_projects(tmp_path):
    db = Database(str(tmp_path / "sr.db"))
    a = _series(db, "A")
    sa = _scene(db, a, content="INT. A - DAY\n\nA_SENTINEL action.", chapter="Episode 1")
    spp.save_season_plan(db, a, spp.SeasonArcPlan(act="Act I", premise="A_SEASON"))
    spp.save_episode_plan(db, a, spp.EpisodeBeatPlan(chapter="Episode 1", a_story="A_EP"))
    db.create_psyke_entry(a, "Maria", "character")
    b = _series(db, "B")
    # Project B sees none of A's data.
    assert db.get_all_scenes(b) == []
    assert spp.get_season_plan(db, b, "Act I") is None
    assert spp.get_episode_plan(db, b, "Episode 1") is None
    assert sdash.build_series_review(db, b).total_scenes == 0
    assert "A_SENTINEL" not in scont.build_series_continuity_report(db, b).to_text()
    assert "A_SENTINEL" not in sbk.export_project_markdown(db, b)
    assert len(db.get_all_psyke_entries(b)) == 0
    # A still intact.
    assert "A_SENTINEL" in sbk.export_project_markdown(db, a)
    assert spp.get_season_plan(db, a, "Act I").premise == "A_SEASON"


# ==========================================================================
# 9  Privacy — exports / reports never include secrets
# ==========================================================================


def test_exports_and_reports_exclude_secrets():
    db = Database()
    from logosforge.settings import get_manager
    get_manager().set("ai_api_key", "SECRET_KEY_SENTINEL")
    pid = _series(db)
    _scene(db, pid, content="INT. X - DAY\n\nA beat.", summary="PLAN_ONLY_SENTINEL")
    for text in (sbk.export_project_markdown(db, pid),
                 scont.build_series_continuity_report(db, pid).to_text(),
                 sdash.build_series_review(db, pid).to_markdown()):
        assert "SECRET_KEY_SENTINEL" not in text
    # Export is body-only — Outline summaries are not leaked into the script.
    assert "PLAN_ONLY_SENTINEL" not in sbk.export_project_markdown(db, pid)


# ==========================================================================
# 10  Scope — no Season/Episode storage creep, no image-gen / production
# ==========================================================================


def test_series_modules_never_use_season_episode_tables():
    for rel in _SERIES_MODULES:
        skeleton = _code_skeleton(rel)
        # The universal-Manuscript Series system is settings-backed; it must not
        # reference the legacy Season/Episode SQLModel tables.
        assert "season(" not in skeleton, rel
        assert "episode(" not in skeleton, rel
        assert "models.season" not in skeleton and "models.episode" not in skeleton, rel


def test_no_image_generation_or_production_actions():
    from logosforge.logos import actions as A
    names = " ".join(a.name + " " + a.label for a in A.list_actions()).lower()
    # Image-generation / production-automation specific (NOT the bare word "render",
    # which legitimately appears in the screenplay "preview render" = formatted-script
    # preview, a creative-writing feature unrelated to image generation).
    for banned in ("comfyui", "image gen", "generate image", "image prompt",
                   "production schedule", "writers room", "showrunner automation",
                   "stable diffusion", "img2img", "txt2img"):
        assert banned not in names, banned
    for rel in _SERIES_MODULES:
        skeleton = _code_skeleton(rel)
        for banned in ("comfyui", "image generation", "image prompt", "img2img",
                       "txt2img", "stable diffusion", "lora", "production schedul",
                       "rehearsal"):
            assert banned not in skeleton, f"{banned} in {rel}"


def test_series_plans_are_settings_backed():
    db = Database()
    pid = _series(db)
    _scene(db, pid, content="INT. X - DAY\n\nx.", act="Act I", chapter="Episode 1")
    spp.save_season_plan(db, pid, spp.SeasonArcPlan(act="Act I", premise="p"))
    spp.save_episode_plan(db, pid, spp.EpisodeBeatPlan(chapter="Episode 1", a_story="a"))
    settings = db.get_project_settings(pid)
    assert "series_season_plans" in settings and "series_episode_plans" in settings


# ==========================================================================
# 11  UI routing — correct views mount; Series review hook is mode-aware
# ==========================================================================


def test_manuscript_review_hook_is_series_in_series_mode():
    from logosforge.ui.main_window import MainWindow
    from logosforge.ui.writing_core_view import WritingCoreView
    from logosforge.ui.series_review_view import SeriesReviewView
    db = Database()
    pid = _series(db)
    _scene(db, pid, content="INT. X - DAY\n\nx.")
    win = MainWindow(db, pid)
    win._show_manuscript()
    assert isinstance(win.content_area, WritingCoreView)
    assert win.content_area.on_open_review == win._show_series_review
    win._show_series_review()
    assert isinstance(win.content_area, SeriesReviewView)


def test_manuscript_review_hook_not_series_in_novel_mode():
    from logosforge.ui.main_window import MainWindow
    from logosforge.ui.writing_core_view import WritingCoreView
    db = Database()
    nid = db.create_project("N", narrative_engine="novel").id
    ss.create_scene(db, nid, act="Act 1", chapter="Chapter 1", title="C", content="Prose.")
    win = MainWindow(db, nid)
    win._show_manuscript()
    assert isinstance(win.content_area, WritingCoreView)
    assert win.content_area.on_open_review != win._show_series_review


def test_review_dashboard_navigation_callbacks():
    from logosforge.ui.series_review_view import SeriesReviewView
    db = Database()
    pid = _series(db)
    a = _scene(db, pid, content="INT. A - DAY\n\na.", title="Alpha")
    opened = {"m": [], "o": [], "t": []}
    view = SeriesReviewView(
        db, pid, on_open_manuscript=lambda s: opened["m"].append(s),
        on_open_outline=lambda s: opened["o"].append(s),
        on_open_timeline=lambda s: opened["t"].append(s))
    view._table.selectRow(0)
    view._open_manuscript()
    view._open_outline()
    view._open_timeline()
    assert opened["m"] == [a] and opened["o"] == [a] and opened["t"] == [a]
    # Navigation is read-only — the body is untouched.
    assert db.get_scene_by_id(a).content == "INT. A - DAY\n\na."
