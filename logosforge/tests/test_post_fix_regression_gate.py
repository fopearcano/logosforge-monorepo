"""POST-FIX REGRESSION GATE — Graphic Novel shared body + corrected Series
hierarchy + writing-mode lock + Alpha export-dependency safety.

A focused gate that re-verifies the cross-cutting invariants after the three
Alpha-blocker fixes, alongside the detailed per-area suites
(``test_gn_pages_manuscript_sync`` / ``test_series_hierarchy`` /
``test_writing_mode_lock`` / ``test_series_navigator``). It asserts the audit's
specific concerns: episode-local Acts/Chapters are not confused with
Seasons/Episodes, Navigator scenes open in the Manuscript, moving structure never
loses a body, ComfyUI stays a disabled stub with no image-generation actions,
Canvas Plot stays hidden, and the dependency manifest is correct.
"""

from __future__ import annotations

import os
import warnings

import pytest
from PySide6.QtWidgets import QApplication

warnings.filterwarnings("ignore")

from logosforge.db import Database
from logosforge import series_structure as sst
from logosforge import story_structure as ss
from logosforge import writing_modes as wm

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


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


def _nav(db, pid, **cb):
    from logosforge.ui.series_navigator_view import SeriesNavigatorView
    return SeriesNavigatorView(db, pid, **cb)


def _find_item(view, predicate):
    t = view._tree
    stack = [t.topLevelItem(i) for i in range(t.topLevelItemCount())]
    while stack:
        it = stack.pop()
        if predicate(it):
            return it
        for i in range(it.childCount()):
            stack.append(it.child(i))
    return None


# ==========================================================================
# A. Graphic Novel — shared body has no image-generation data; ComfyUI is a
#    disabled stub (image-PROMPT export is a separate, pre-existing feature).
# ==========================================================================


def test_gn_shared_body_panel_fields_are_script_only():
    from logosforge import graphic_novel_blocks as gnb
    fields = set(vars(gnb.Panel()).keys())
    assert fields == {"number", "visual_description", "caption", "dialogue",
                      "sfx", "notes"}
    for banned in ("image", "prompt", "lora", "checkpoint", "comfyui", "seed",
                   "sampler", "cfg"):
        assert not any(banned in f for f in fields), banned


def test_gn_body_is_single_store_scene_content():
    from logosforge import graphic_novel_blocks as gnb
    db = Database()
    pid = db.create_project("GN", narrative_engine="graphic_novel",
                            default_writing_format="graphic_novel").id
    sid = db.create_scene(pid, title="P").id
    script = gnb.GraphicNovelScript(pages=[gnb.Page(
        number=1, panels=[gnb.Panel(number=1, visual_description="A wide shot")])])
    gnb.save_scene_script(db, sid, script)
    # The write lands in Scene.content (the shared body), not a side table.
    assert "A wide shot" in (db.get_scene_by_id(sid).content or "")


def test_comfyui_connector_is_disabled_stub():
    from logosforge import graphic_novel_ai_export as ax
    assert ax.comfyui_available() is False
    with pytest.raises(NotImplementedError):
        ax.send_to_comfyui(None)


def test_logos_registry_has_no_image_or_comfyui_actions():
    from logosforge.logos import actions as A
    blob = " ".join((a.name + " " + a.label).lower() for a in A.list_actions())
    for banned in ("comfyui", "image gen", "generate image", "image prompt",
                   "img2img", "txt2img", "stable diffusion", "canvas plot"):
        assert banned not in blob, banned


# ==========================================================================
# B. Series — corrected hierarchy: episode-local Acts/Chapters are NOT the
#    same thing as Seasons/Episodes (no shortcut confusion).
# ==========================================================================


def test_episode_local_act_is_not_the_season():
    db = Database()
    pid = _series(db)
    season = sst.create_season(db, pid, "Act 1")          # season named like an act
    ep = sst.create_episode(db, season.id, "E1", project_id=pid)
    sst.create_episode_scene(db, pid, ep.id, act="Act 1", chapter="Chapter 1")
    sst.rename_episode_act(db, ep.id, "Act 1", "Prologue")
    # The Season row is independent of the episode-local Act label.
    assert db.get_season_by_id(season.id).title == "Act 1"
    assert sst.build_episode_tree(db, ep.id)[0][0] == "Prologue"


def test_episode_local_chapter_is_not_the_episode():
    db = Database()
    pid = _series(db)
    season = sst.create_season(db, pid, "S1")
    ep = sst.create_episode(db, season.id, "Chapter 1", project_id=pid)  # like a chapter
    sst.create_episode_scene(db, pid, ep.id, act="Act 1", chapter="Chapter 1")
    sst.rename_episode_chapter(db, ep.id, "Act 1", "Chapter 1", "Opening")
    assert db.get_episode_by_id(ep.id).title == "Chapter 1"
    assert sst.build_episode_tree(db, ep.id)[0][1][0][0] == "Opening"


def test_navigator_renders_distinct_five_levels():
    db = Database()
    pid = _series(db)
    season = sst.create_season(db, pid, "Pilot Season")
    ep = sst.create_episode(db, season.id, "Cold Open", project_id=pid)
    sst.create_episode_scene(db, pid, ep.id, act="Act 1", chapter="Chapter 1",
                             title="Alpha")
    sst.create_episode_act(db, pid, ep.id, "Act 2")       # makes structure rich
    view = _nav(db, pid)
    assert _find_item(view, lambda it: "Pilot Season" in it.text(0))      # Season
    assert _find_item(view, lambda it: "Cold Open" in it.text(0))         # Episode
    assert _find_item(view, lambda it: it.text(0) == "Act 1")            # Act
    assert _find_item(view, lambda it: it.text(0) == "Chapter 1")        # Chapter
    assert _find_item(view, lambda it: "Alpha" in it.text(0))            # Scene


def test_navigator_hierarchy_scene_opens_manuscript():
    db = Database()
    pid = _series(db)
    season = sst.create_season(db, pid, "S1")
    ep = sst.create_episode(db, season.id, "E1", project_id=pid)
    sid = sst.create_episode_scene(db, pid, ep.id, title="Opener").id
    opened = []
    view = _nav(db, pid, on_open_manuscript=lambda i: opened.append(i))
    scene_item = _find_item(view, lambda it: "Opener" in it.text(0))
    view._activate(scene_item)
    assert opened == [sid]


def test_scene_series_path_full_hierarchy_when_rich():
    db = Database()
    pid = _series(db)
    season = sst.create_season(db, pid, "Pilot Season")
    ep = sst.create_episode(db, season.id, "Cold Open", project_id=pid)
    sid = sst.create_episode_scene(db, pid, ep.id, act="Act 1",
                                   chapter="Chapter 1", title="Alpha").id
    sst.create_episode_act(db, pid, ep.id, "Act 2")       # structure is now rich
    path = sst.scene_series_path(db, pid, sid)
    assert "Pilot Season" in path and "Cold Open" in path
    assert "Act 1" in path and "Scene" in path


def test_moving_episode_preserves_scene_body():
    db = Database()
    pid = _series(db)
    season = sst.create_season(db, pid, "S1")
    e1 = sst.create_episode(db, season.id, "E1", project_id=pid)
    e2 = sst.create_episode(db, season.id, "E2", project_id=pid)
    sid = sst.create_episode_scene(db, pid, e2.id, title="Keep").id
    db.update_scene_content(sid, "BODY TO KEEP")
    assert sst.move_episode(db, season.id, e2.id, -1) is True
    scene = db.get_scene_by_id(sid)
    assert scene.content == "BODY TO KEEP" and scene.episode_id == e2.id


def test_series_export_no_duplicate_scene_and_no_secrets():
    db = Database()
    pid = _series(db)
    season = sst.create_season(db, pid, "S1")
    ep = sst.create_episode(db, season.id, "E1", project_id=pid)
    sst.create_episode_scene(db, pid, ep.id, title="UNIQUE_SCENE")
    settings = db.get_project_settings(pid) or {}
    settings["api_key"] = "sk-SECRET"
    db.save_project_settings(pid, settings)
    md = sst.export_series_markdown(db, pid)
    assert md.count("UNIQUE_SCENE") == 1            # traversed once, not duplicated
    assert "SECRET" not in md and "sk-" not in md


def test_legacy_shortcut_series_loads_and_is_convertible():
    db = Database()
    pid = _series(db)
    ss.create_scene(db, pid, act="Act I", chapter="Episode 1", title="Legacy",
                    content="OLD BODY")
    assert sst.is_legacy_series(db, pid) is True
    view = _nav(db, pid)
    # Legacy projects render (read-only) without data loss and offer Convert.
    assert _find_item(view, lambda it: "Season / Arc" in it.text(0))
    assert view._convert_btn.isHidden() is False
    res = view.convert_legacy(confirmed=True)
    assert res["ok"] is True
    assert db.get_scene_by_id(  # body survived the migration
        [s.id for s in db.get_all_scenes(pid)][0]).content == "OLD BODY"


# ==========================================================================
# C. Writing-mode lock — locks after meaningful content; blocked change is inert.
# ==========================================================================


def test_empty_series_can_change_mode_but_locks_after_season():
    db = Database()
    pid = _series(db)
    assert wm.can_change_writing_mode(db, pid) is True
    sst.create_season(db, pid, "S1")
    assert wm.can_change_writing_mode(db, pid) is False


def test_blocked_mode_change_does_not_mutate():
    db = Database()
    pid = _series(db)
    season = sst.create_season(db, pid, "S1")
    ep = sst.create_episode(db, season.id, "E1", project_id=pid)
    sst.create_episode_scene(db, pid, ep.id, title="S")
    before = wm.get_project_writing_mode_by_id(db, pid)
    changed, mode = wm.change_writing_mode(db, pid, "novel")
    assert changed is False
    assert wm.get_project_writing_mode_by_id(db, pid) == before   # no mutation
    assert sst.has_series_hierarchy(db, pid) is True              # structure intact


@pytest.mark.parametrize("engine,scene_kw", [
    ("novel", {"content": "Prose body."}),
    ("screenplay", {"content": "INT. ROOM - DAY\n\nAction."}),
    ("stage_script", {"content": "A stage direction."}),
])
def test_other_modes_lock_after_body(engine, scene_kw):
    db = Database()
    pid = db.create_project(engine, narrative_engine=engine,
                            default_writing_format=engine).id
    assert wm.can_change_writing_mode(db, pid) is True
    ss.create_scene(db, pid, act="Act 1", chapter="Chapter 1", title="S",
                    **scene_kw)
    assert wm.can_change_writing_mode(db, pid) is False


# ==========================================================================
# D. Dependency manifest + Canvas Plot deferral + Series-only Navigator.
# ==========================================================================


def test_requirements_lists_reportlab_and_python_docx():
    req = open(os.path.join(_ROOT, "requirements.txt")).read()
    assert "reportlab" in req and "python-docx" in req


def test_canvas_plot_hidden_in_series_mode():
    from logosforge.ui.main_window import MainWindow
    db = Database()
    pid = _series(db)
    win = MainWindow(db, pid)
    assert "Plot" not in win._nav_labels
    btn = win.sidebar_buttons.get("Plot")
    assert btn is not None and btn.property("nav_available") is False


def test_series_navigator_is_series_only():
    from logosforge.ui.main_window import MainWindow
    db = Database()
    series_pid = _series(db)
    novel = db.create_project("N", narrative_engine="novel").id
    win = MainWindow(db, series_pid)
    assert "Series Navigator" in win._nav_labels
    win._switch_project(novel)
    assert "Series Navigator" not in win._nav_labels
