"""Tests for Graphic Novel manuscript draft generation (Slice 3).

One-way, additive projection: GN Page/Panel structure -> manuscript text.
"""

import pytest

from logosforge.db import Database
from logosforge.graphic_novel_manuscript import (
    generate_draft,
    generate_page_draft,
)
from logosforge.ui.graphic_novel_pages_view import GraphicNovelPagesView


@pytest.fixture(autouse=True)
def _isolated_settings(monkeypatch, tmp_path):
    import logosforge.settings as settings
    settings._instance = None
    monkeypatch.setattr(settings, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(settings, "SETTINGS_FILE", tmp_path / "settings.json")
    yield
    settings._instance = None


def _gn(db):
    return db.create_project(
        "GN", narrative_engine="graphic_novel",
        default_writing_format="graphic_novel",
    )


def _page_with_panel(db, project_id, **panel_kw):
    page = db.create_gn_page(project_id, density_level="medium",
                             reveal_type="page_turn",
                             emotional_beat="A battlefield.")
    db.create_gn_panel(page.id, **panel_kw)
    return page


# =========================================================================
# 1. Generate selected-page draft — content, omitted fields, order
# =========================================================================

def test_generate_page_draft_content():
    db = Database()
    p = _gn(db)
    page = db.create_gn_page(p.id, density_level="medium",
                             reveal_type="page_turn",
                             emotional_beat="The alley is a battlefield.")
    db.create_gn_panel(
        page.id, shot_type="wide", camera_angle="low_angle",
        transition_type="moment_to_moment", reading_priority=1,
        description="Zampano at the gate.", action="He sniffs.",
        characters_present=["Zampano"], dialogue_refs=["ZAMPANO: ..."],
        visual_motifs=["broken halo", "muddy cross"],
    )
    text = generate_draft(db, p.id, scope="page", page_id=page.id)
    assert "PAGE 1" in text
    assert "Density: medium" in text
    assert "Reveal: page_turn" in text
    assert "Emotional beat: The alley is a battlefield." in text
    assert "PANEL 1" in text
    assert "Shot: wide" in text
    assert "Camera: low_angle" in text
    assert "Transition: moment_to_moment" in text
    assert "Priority: 1" in text
    assert "Description: Zampano at the gate." in text
    assert "Action: He sniffs." in text
    assert "Characters: Zampano" in text
    assert "Dialogue:" in text and "ZAMPANO: ..." in text
    assert "Motifs: broken halo, muddy cross" in text


def test_empty_fields_omitted():
    db = Database()
    p = _gn(db)
    page = db.create_gn_page(p.id)            # no density/reveal/beat
    db.create_gn_panel(page.id, description="Just a description.")
    text = generate_draft(db, p.id, scope="page", page_id=page.id)
    assert "Density:" not in text
    assert "Reveal:" not in text
    assert "Emotional beat:" not in text
    assert "Shot:" not in text
    assert "Camera:" not in text
    assert "Dialogue:" not in text
    assert "Motifs:" not in text
    assert "Description: Just a description." in text
    # No JSON / internal ids leaked.
    assert "{" not in text and "}" not in text
    assert f"id={page.id}" not in text


def test_no_caption_or_sfx_sections():
    """Captions/SFX have no backing panel field — they are not emitted."""
    db = Database()
    p = _gn(db)
    page = db.create_gn_page(p.id)
    db.create_gn_panel(page.id, description="x")
    text = generate_draft(db, p.id, scope="page", page_id=page.id)
    assert "Captions:" not in text
    assert "SFX:" not in text


def test_panels_in_order_within_page():
    db = Database()
    p = _gn(db)
    page = db.create_gn_page(p.id)
    db.create_gn_panel(page.id, description="first")
    db.create_gn_panel(page.id, description="second")
    db.create_gn_panel(page.id, description="third")
    text = generate_page_draft(db, db.get_gn_page_by_id(page.id))
    assert text.index("PANEL 1") < text.index("PANEL 2") < text.index("PANEL 3")
    assert text.index("first") < text.index("second") < text.index("third")


# =========================================================================
# 2. Generate all-pages draft — page + panel order
# =========================================================================

def test_generate_all_pages_in_order():
    db = Database()
    p = _gn(db)
    db.create_gn_page(p.id, summary="page one")
    db.create_gn_page(p.id, summary="page two")
    db.create_gn_page(p.id, summary="page three")
    text = generate_draft(db, p.id, scope="all")
    assert text.index("PAGE 1") < text.index("PAGE 2") < text.index("PAGE 3")
    assert text.index("page one") < text.index("page two") < text.index("page three")


def test_all_pages_respects_reorder():
    db = Database()
    p = _gn(db)
    a = db.create_gn_page(p.id, summary="alpha")
    b = db.create_gn_page(p.id, summary="beta")
    db.reorder_gn_pages(p.id, [b.id, a.id])
    text = generate_draft(db, p.id, scope="all")
    assert text.index("beta") < text.index("alpha")


def test_empty_project_generates_nothing():
    db = Database()
    p = _gn(db)
    assert generate_draft(db, p.id, scope="all") == ""


# =========================================================================
# 3. Generate by issue
# =========================================================================

def test_generate_issue_scope():
    db = Database()
    p = _gn(db)
    issue = db.create_gn_issue(p.id, title="One")
    db.create_gn_page(p.id, issue_id=issue.id, summary="in issue")
    db.create_gn_page(p.id, summary="loose")  # unassigned
    text = generate_draft(db, p.id, scope="issue", issue_id=issue.id)
    assert "in issue" in text
    assert "loose" not in text


# =========================================================================
# 4. Additive insertion through the view
# =========================================================================

def test_additive_append_keeps_existing_prose():
    db = Database()
    p = _gn(db)
    _page_with_panel(db, p.id, description="hero enters")
    scene = db.create_scene(p.id, "Script", content="Existing prose.")
    view = GraphicNovelPagesView(db, p.id)
    out = view.generate_manuscript_draft("all", confirm=False)
    assert out is not None
    updated = db.get_scene_by_id(scene.id)
    assert updated.content.startswith("Existing prose.")
    assert "PAGE 1" in updated.content
    assert "hero enters" in updated.content


def test_append_to_empty_scene_no_confirm_needed():
    db = Database()
    p = _gn(db)
    _page_with_panel(db, p.id, description="x")
    scene = db.create_scene(p.id, "Empty", content="")
    view = GraphicNovelPagesView(db, p.id)
    out = view.generate_manuscript_draft("all")  # default confirm; empty -> no prompt
    assert out is not None
    assert "PAGE 1" in db.get_scene_by_id(scene.id).content


def test_nonempty_scene_decline_leaves_content(monkeypatch):
    # conftest patches QMessageBox.question -> No, so the default confirm
    # path declines and must NOT modify the scene.
    db = Database()
    p = _gn(db)
    _page_with_panel(db, p.id, description="x")
    scene = db.create_scene(p.id, "Script", content="Keep me.")
    view = GraphicNovelPagesView(db, p.id)
    out = view.generate_manuscript_draft("all")  # confirm=True -> declined
    assert out is None
    assert db.get_scene_by_id(scene.id).content == "Keep me."


def test_creates_scene_when_none_exists():
    db = Database()
    p = _gn(db)
    _page_with_panel(db, p.id, description="x")
    assert db.get_all_scenes(p.id) == []
    view = GraphicNovelPagesView(db, p.id)
    out = view.generate_manuscript_draft("all", confirm=False)
    assert out is not None
    scenes = db.get_all_scenes(p.id)
    assert len(scenes) == 1
    assert "PAGE 1" in scenes[0].content


def test_selected_page_scope_uses_current_page():
    db = Database()
    p = _gn(db)
    pg1 = db.create_gn_page(p.id, summary="first page").id
    db.create_gn_page(p.id, summary="second page")
    db.create_scene(p.id, "S", content="")
    view = GraphicNovelPagesView(db, p.id)
    view.select_page(pg1)
    out = view.generate_manuscript_draft("page", confirm=False)
    assert "first page" in out
    assert "second page" not in out


# =========================================================================
# 5. One-operation (single-undo) insertion helper
# =========================================================================

def test_insert_text_single_undo():
    from PySide6.QtWidgets import QPlainTextEdit
    editor = QPlainTextEdit()
    editor.setPlainText("ORIGINAL")
    GraphicNovelPagesView.insert_text_as_single_undo(editor, "\nINSERTED")
    assert "INSERTED" in editor.toPlainText()
    # A single undo removes the whole insertion in one step.
    editor.undo()
    assert editor.toPlainText() == "ORIGINAL"


# =========================================================================
# 6. No reverse mutation — manuscript edits never touch GN rows
# =========================================================================

def test_editing_manuscript_does_not_mutate_panels():
    db = Database()
    p = _gn(db)
    page = _page_with_panel(db, p.id, description="canonical desc")
    panel = db.get_gn_panels_for_page(page.id)[0]
    scene = db.create_scene(p.id, "S", content="")
    view = GraphicNovelPagesView(db, p.id)
    view.generate_manuscript_draft("all", confirm=False)
    # Simulate the user / Assistant editing the manuscript afterwards.
    db.update_scene_content(scene.id, "Totally rewritten script.")
    # GN panel row is unchanged.
    assert db.get_gn_panel_by_id(panel.id).description == "canonical desc"
    assert len(db.get_gn_panels_for_page(page.id)) == 1


def test_assistant_style_update_does_not_change_gn():
    db = Database()
    p = _gn(db)
    page = _page_with_panel(db, p.id, description="keep")
    scene = db.create_scene(p.id, "S", content="x")
    panels_before = [(pn.id, pn.description)
                     for pn in db.get_gn_panels_for_page(page.id)]
    # The Assistant edits Scene.content directly (its only write path).
    db.update_scene_content(scene.id, "Assistant rewrite.")
    panels_after = [(pn.id, pn.description)
                    for pn in db.get_gn_panels_for_page(page.id)]
    assert panels_before == panels_after


# =========================================================================
# 7. Reload safety — both stores persist independently
# =========================================================================

def test_reload_keeps_both_stores(tmp_path):
    path = str(tmp_path / "gn.db")
    db = Database(path)
    p = _gn(db)
    page = _page_with_panel(db, p.id, description="panel text")
    scene = db.create_scene(p.id, "S", content="")
    view = GraphicNovelPagesView(db, p.id)
    view.generate_manuscript_draft("all", confirm=False)
    scene_id, page_id, pid = scene.id, page.id, p.id

    db2 = Database(path)
    # Manuscript prose persisted.
    assert "PAGE 1" in db2.get_scene_by_id(scene_id).content
    # GN structure persisted, unchanged.
    assert len(db2.get_gn_pages(pid)) == 1
    panels = db2.get_gn_panels_for_page(page_id)
    assert len(panels) == 1
    assert panels[0].description == "panel text"


# =========================================================================
# 8. Engine gating
# =========================================================================

def test_action_button_present_for_gn():
    db = Database()
    p = _gn(db)
    view = GraphicNovelPagesView(db, p.id)
    assert hasattr(view, "_gen_draft_btn")


def test_non_gn_project_inert():
    db = Database()
    p = db.create_project("Novel")
    view = GraphicNovelPagesView(db, p.id)
    assert view.generate_manuscript_draft("all", confirm=False) is None
    # No draft button on the placeholder view.
    assert not hasattr(view, "_gen_draft_btn")
    # No scenes were created.
    assert db.get_all_scenes(p.id) == []
