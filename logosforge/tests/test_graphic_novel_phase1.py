"""Graphic Novel Mode — Phase 1 acceptance suite.

Page/panel script foundation inside the *universal* Manuscript: a deterministic
scene-body adapter (parse/serialize Page/Panel from Scene.content — no schema
change, no separate Manuscript section), script operations, Markdown export,
validation, and minimal Assistant/Logos context. Primary unit = Scene.
Outline summary, PSYKE, Timeline, Novel prose, and Screenplay blocks are
preserved.
"""

from __future__ import annotations

import warnings

import pytest
from PySide6.QtWidgets import QApplication

warnings.filterwarnings("ignore")

from logosforge.db import Database
from logosforge import story_structure as ss
from logosforge import graphic_novel_blocks as gn
from logosforge.writing_modes import current_primary_unit_type


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


def _novel(db):
    return db.create_project("N", narrative_engine="novel").id


_BODY = (
    "PAGE 1: Opening\nSummary: the alley at dawn\n\n"
    "PANEL 1\nVisual: Maria steps over rubble.\nCaption: Three years later.\n"
    "Dialogue: MARIA: Never again.\nSFX: CRUNCH\nNotes: low angle\n\n"
    "PANEL 2\nVisual: A shadow moves."
)


# ==========================================================================
# 1-4  Mode behavior + universal Manuscript reuse
# ==========================================================================


def test_graphic_novel_primary_unit_is_scene():
    db = Database()
    proj = db.get_project_by_id(_gn(db))
    assert current_primary_unit_type(proj) == "scene"


def test_novel_and_screenplay_modes_unchanged():
    db = Database()
    novel = db.get_project_by_id(_novel(db))
    sp = db.get_project_by_id(db.create_project("S", narrative_engine="screenplay").id)
    assert current_primary_unit_type(novel) == "chapter"
    assert current_primary_unit_type(sp) == "scene"


def test_universal_manuscript_reused_no_separate_gn_section(tmp_path):
    # Alpha: the standalone Pages section is disabled (macOS fullscreen bug), so in
    # Graphic Novel mode the single "Manuscript" nav section hosts the embedded
    # comics script editor over the SAME shared Scene.content body. There is still
    # ONE Manuscript nav entry — no separate "Graphic Novel Manuscript" section.
    from logosforge.ui.main_window import MainWindow
    from logosforge.ui.graphic_novel_manuscript_view import (
        GraphicNovelManuscriptView)
    db = Database(str(tmp_path / "gn.db"))
    pid = _gn(db)
    ss.create_scene(db, pid, act="Act I", chapter="Ch1", title="S", content=_BODY)
    win = MainWindow(db, pid)
    win.sidebar_buttons["Manuscript"].click()
    # The single Manuscript section hosts the SHARED editor (the legacy
    # GN-specific renderer is no longer routed).
    from logosforge.ui.writing_core_view import WritingCoreView
    assert isinstance(win.content_area, WritingCoreView)
    assert not isinstance(win.content_area, GraphicNovelManuscriptView)
    assert "Manuscript" in win._nav_labels
    assert not any("graphic" in lbl.lower() and "manuscript" in lbl.lower()
                   for lbl in win._nav_labels)


# ==========================================================================
# 5-17  Data / model: pages, panels, fields, order, move, delete
# ==========================================================================


def test_create_page_and_panel_persist_to_scene_body():
    db = Database()
    pid = _gn(db)
    sid = ss.create_scene(db, pid, act="Act I", chapter="Ch1", title="S",
                          content="").id
    script = gn.GraphicNovelScript()
    page = gn.add_page(script, title="One")
    gn.add_panel(page, visual_description="A door.")
    gn.save_scene_script(db, sid, script)
    reloaded = gn.load_scene_script(db, sid)
    assert len(reloaded.pages) == 1 and len(reloaded.pages[0].panels) == 1
    assert reloaded.pages[0].panels[0].visual_description == "A door."


def test_edit_all_panel_fields():
    script = gn.parse_graphic_novel_text(_BODY)
    p = script.pages[0].panels[0]
    assert p.visual_description == "Maria steps over rubble."
    assert p.caption == "Three years later."
    assert p.dialogue == "MARIA: Never again."
    assert p.sfx == "CRUNCH"
    assert p.notes == "low angle"


def test_page_and_panel_order_persists(tmp_path):
    path = str(tmp_path / "gn.db")
    db = Database(path)
    pid = _gn(db)
    sid = ss.create_scene(db, pid, act="Act I", chapter="Ch1", title="S",
                          content="").id
    script = gn.GraphicNovelScript()
    pg = gn.add_page(script)
    gn.add_panel(pg, visual_description="first")
    gn.add_panel(pg, visual_description="second")
    gn.save_scene_script(db, sid, script)
    out = gn.load_scene_script(Database(path), sid)
    assert [pn.visual_description for pn in out.pages[0].panels] == ["first", "second"]
    assert [pn.number for pn in out.pages[0].panels] == [1, 2]


def test_move_panel_within_page():
    script = gn.GraphicNovelScript()
    pg = gn.add_page(script)
    gn.add_panel(pg, visual_description="a")
    gn.add_panel(pg, visual_description="b")
    gn.move_panel(pg, 0, 1)
    assert [p.visual_description for p in pg.panels] == ["b", "a"]
    assert [p.number for p in pg.panels] == [1, 2]


def test_move_panel_to_another_page():
    script = gn.GraphicNovelScript()
    pg1 = gn.add_page(script)
    gn.add_panel(pg1, visual_description="x")
    pg2 = gn.add_page(script)
    assert gn.move_panel_to_page(script, 0, 0, 1) is True
    assert len(script.pages[0].panels) == 0 and len(script.pages[1].panels) == 1


def test_delete_panel_and_page():
    script = gn.parse_graphic_novel_text(_BODY)
    gn.delete_panel(script.pages[0], 0)
    assert len(script.pages[0].panels) == 1
    gn.delete_page(script, 0)
    assert script.pages == []


# ==========================================================================
# 18-21  Outline / Manuscript / PSYKE / Timeline separation
# ==========================================================================


def test_saving_script_does_not_touch_outline_summary():
    db = Database()
    pid = _gn(db)
    sid = ss.create_scene(db, pid, act="Act I", chapter="Ch1", title="S",
                          content="", summary="OUTLINE_SUMMARY").id
    script = gn.GraphicNovelScript()
    gn.add_panel(gn.add_page(script), visual_description="A panel.")
    gn.save_scene_script(db, sid, script)
    assert db.get_scene_by_id(sid).summary == "OUTLINE_SUMMARY"   # untouched
    assert "A panel." in db.get_scene_by_id(sid).content          # body holds script


def test_outline_summary_is_not_parsed_as_panel_body():
    db = Database()
    pid = _gn(db)
    sid = ss.create_scene(db, pid, act="Act I", chapter="Ch1", title="S",
                          content=_BODY, summary="SUMMARY_NOT_A_PANEL").id
    script = gn.load_scene_script(db, sid)
    blob = " ".join(p.visual_description + p.caption + p.dialogue
                    for pg in script.pages for p in pg.panels)
    assert "SUMMARY_NOT_A_PANEL" not in blob


def test_script_save_does_not_mutate_psyke_or_timeline():
    db = Database()
    pid = _gn(db)
    db.create_psyke_entry(pid, "Maria", "character")
    sid = ss.create_scene(db, pid, act="Act I", chapter="Ch1", title="S",
                          content="").id
    db.add_timeline_event(pid, sid)
    before_psyke = len(db.get_all_psyke_entries(pid))
    before_tl = db.get_timeline_event_ids(pid)
    script = gn.GraphicNovelScript()
    gn.add_panel(gn.add_page(script), visual_description="x")
    gn.save_scene_script(db, sid, script)
    assert len(db.get_all_psyke_entries(pid)) == before_psyke
    assert db.get_timeline_event_ids(pid) == before_tl


# ==========================================================================
# 22-26  Export
# ==========================================================================


def test_export_scene_markdown_structure():
    db = Database()
    pid = _gn(db)
    sid = ss.create_scene(db, pid, act="Act I", chapter="Ch1", title="Alley",
                          content=_BODY).id
    md = gn.export_scene_markdown(db, pid, sid)
    assert md.startswith("# Alley")
    assert "## Page 1" in md and "### Panel 1" in md
    assert "Visual: Maria steps over rubble." in md and "SFX: CRUNCH" in md


def test_export_project_markdown_canonical_order():
    db = Database()
    pid = _gn(db)
    b = ss.create_scene(db, pid, act="Act II", chapter="Ch2", title="Beta",
                        content="PAGE 1\n\nPANEL 1\nVisual: beta panel.").id
    a = ss.create_scene(db, pid, act="Act I", chapter="Ch1", title="Alpha",
                        content="PAGE 1\n\nPANEL 1\nVisual: alpha panel.").id
    db.reorder_scenes(pid, [a, b])
    md = gn.export_project_markdown(db, pid)
    assert md.index("alpha panel.") < md.index("beta panel.")
    assert "### Panel 1" in md


def test_export_excludes_secrets_and_outline_summary():
    db = Database()
    from logosforge.settings import get_manager
    get_manager().set("ai_api_key", "SECRET_KEY_SENTINEL")
    pid = _gn(db)
    ss.create_scene(db, pid, act="Act I", chapter="Ch1", title="S",
                    content=_BODY, summary="OUTLINE_ONLY_SENTINEL")
    md = gn.export_project_markdown(db, pid)
    assert "SECRET_KEY_SENTINEL" not in md
    assert "OUTLINE_ONLY_SENTINEL" not in md      # summary never exported as body


# ==========================================================================
# 27-30  Validation
# ==========================================================================


def test_validation_empty_page_and_panel():
    # A real (titled) page that has no panels yet -> "no panels" warning.
    script = gn.parse_graphic_novel_text(
        "PAGE 1: Intro\nSummary: a page with no panels yet")
    rep = gn.validate_graphic_novel_script(script)
    assert any("no panels" in w for w in rep.warnings)


def test_validation_panel_without_visual_and_empty():
    script = gn.parse_graphic_novel_text("PAGE 1\n\nPANEL 1\nCaption: just words.")
    rep = gn.validate_graphic_novel_script(script)
    assert any("no visual" in w for w in rep.warnings)


def test_validation_dialogue_heavy():
    body = "PAGE 1\n\nPANEL 1\nVisual: a.\nDialogue: NAME: " + " ".join(["word"] * 40)
    rep = gn.validate_graphic_novel_script(gn.parse_graphic_novel_text(body))
    assert any("dialogue-heavy" in w for w in rep.warnings)


def test_validation_empty_script_not_valid():
    rep = gn.validate_graphic_novel_script(gn.GraphicNovelScript())
    assert not rep.is_valid


# ==========================================================================
# Round-trip + legacy safety
# ==========================================================================


def test_parse_serialize_round_trip():
    script = gn.parse_graphic_novel_text(_BODY)
    assert gn.parse_graphic_novel_text(
        gn.serialize_graphic_novel_script(script)).to_dict() == script.to_dict()


def test_legacy_plain_text_is_preserved():
    legacy = "An old prose body with no page or panel markers."
    script = gn.parse_graphic_novel_text(legacy)
    assert script.pages and script.pages[0].panels
    assert "old prose body" in script.pages[0].panels[0].visual_description


# ==========================================================================
# 31-33  Project isolation
# ==========================================================================


def test_pages_isolated_across_projects(tmp_path):
    db = Database(str(tmp_path / "gn.db"))
    a = _gn(db, "A")
    sa = ss.create_scene(db, a, act="Act I", chapter="Ch1", title="SA",
                         content="PAGE 1\n\nPANEL 1\nVisual: A_ONLY_PANEL.").id
    b = _gn(db, "B")
    md_b = gn.export_project_markdown(db, b)
    assert "A_ONLY_PANEL" not in md_b
    assert gn.load_scene_script(db, sa).panel_count() == 1   # A intact


def test_new_project_has_empty_script():
    db = Database()
    pid = _gn(db)
    sid = ss.create_scene(db, pid, act="Act I", chapter="Ch1", title="S",
                          content="").id
    assert gn.load_scene_script(db, sid).is_empty()


# ==========================================================================
# Assistant / Logos context
# ==========================================================================


def test_assistant_context_includes_graphic_novel_script():
    from logosforge import context_builder as cb
    db = Database()
    pid = _gn(db)
    sid = ss.create_scene(db, pid, act="Act I", chapter="Ch1", title="S",
                          content=_BODY).id
    assert "[Graphic Novel Script]" in cb.gather_scene_context(db, pid, sid)


def test_assistant_context_absent_for_novel():
    from logosforge import context_builder as cb
    db = Database()
    pid = _novel(db)
    sid = ss.create_scene(db, pid, act="A", chapter="C", title="S", content="prose").id
    assert "[Graphic Novel Script]" not in cb.gather_scene_context(db, pid, sid)


def test_panel_check_logos_action_mode_gated_and_deterministic():
    from logosforge.logos import actions as A, deterministic as det
    from logosforge.logos.controller import LogosController
    from logosforge.logos.context import build_logos_context
    db = Database()
    pid = _gn(db)
    sid = ss.create_scene(db, pid, act="Act I", chapter="Ch1", title="S",
                          content="PAGE 1\n\nPANEL 1\nCaption: x.").id
    act = A.get_action("gn_panel_check")
    assert act and act.deterministic and act.modes == ("graphic_novel",)
    names = [a.name for a in
             LogosController(db).available_actions("Manuscript", writing_mode="graphic_novel")]
    assert "gn_panel_check" in names
    assert "gn_panel_check" not in [
        a.name for a in LogosController(db).available_actions("Manuscript", writing_mode="novel")]

    def _boom(*a, **k):
        raise AssertionError("deterministic action must not call the LLM")

    ctl = LogosController(db, provider_resolver=_boom, chat_fn=_boom)
    ctx = build_logos_context(db, pid, section_name="Manuscript", current_scene_id=sid)
    res = ctl.run(ctx, "gn_panel_check")
    assert res.ok and res.title == "Panel Check" and res.proposed_operations == []
    assert db.get_scene_by_id(sid).content == "PAGE 1\n\nPANEL 1\nCaption: x."  # no mutation
