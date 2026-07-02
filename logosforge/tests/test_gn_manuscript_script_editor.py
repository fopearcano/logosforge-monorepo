"""Graphic Novel Manuscript — Superscript-style comics SCRIPT editor.

The GN Manuscript renders the selected scene as a flowing script document:
PAGE headings, then ONE large free-typing script block per panel in which the
writer types labeled sections (Visual / Caption / Dialogue / SFX / Notes —
labels optional, unlabeled text is the Visual, speaker lines stay content).
It is neither an outliner/tree nor a form of small per-field inputs. Blocks
parse back into the canonical five-field model on commit, so the Outline (the
structure manager) mirrors automatically over the same shared
``Scene.content`` body, and line breaks are preserved end-to-end. These tests
cover mount routing, the script shape, the empty-state ladder, block
editing/parsing safety, navigation/deep-links, mirroring, fullscreen safety
and the export guards.
"""

from __future__ import annotations

import warnings

import pytest
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QTreeWidget,
)

warnings.filterwarnings("ignore")

from logosforge.db import Database
from logosforge import graphic_novel_blocks as gnb
from logosforge import graphic_novel_outline as gno
from logosforge import story_structure as ss
from logosforge.ui import safe_dialogs


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


def _scene(db, pid, title="P1"):
    return ss.create_scene(db, pid, act="Act 1", chapter="Chapter 1",
                           title=title).id


def _view(db, pid):
    from logosforge.ui.graphic_novel_manuscript_view import (
        GraphicNovelManuscriptView)
    return GraphicNovelManuscriptView(db, pid, on_data_changed=lambda: None)


def _body(db, sid):
    return gnb.load_scene_script(db, sid)


def _scripted_view(db, *, pages=1, panels=1):
    """A GN project + scene with pages×panels and a view on it."""
    pid = _gn(db)
    sid = _scene(db, pid)
    script = gnb.GraphicNovelScript()
    for p in range(pages):
        page = gnb.add_page(script, title=f"T{p + 1}")
        for _ in range(panels):
            gnb.add_panel(page)
    gnb._renumber(script)
    gnb.save_scene_script(db, sid, script)
    v = _view(db, pid)
    v.select_scene(sid)
    return pid, sid, v


def _sid(view):
    return next(iter(view._scripts), None)


def _block(view, pi=0, ci=0, sid=None):
    sid = sid if sid is not None else _sid(view)
    return view._field_editors[("panel", sid, pi, ci)]


def _commit_block(view, pi, ci, text):
    ed = _block(view, pi, ci)
    ed.setPlainText(text)
    ed.committed.emit()


_FULL_BLOCK = ("Visual:\nA tiny chapel buried under rain.\n"
               "The dog stands at the threshold.\n\n"
               "Caption:\nThe road had forgotten his name.\n\n"
               "Dialogue:\nZAMPANÒ: Woof.\n\n"
               "SFX:\nTHOOM\n\n"
               "Notes:\nKeep this panel wide and quiet.")


# ==========================================================================
# Mount routing
# ==========================================================================


def test_gn_manuscript_mounts_shared_editor():
    from logosforge.ui.main_window import MainWindow
    from logosforge.ui.writing_core_view import WritingCoreView
    from logosforge.ui.graphic_novel_manuscript_view import (
        GraphicNovelManuscriptView)
    db = Database()
    win = MainWindow(db, _gn(db))
    win._show_manuscript()
    # GN uses the SAME shared Manuscript editor as Screenplay; the legacy
    # page/panel renderer is no longer routed.
    assert isinstance(win.content_area, WritingCoreView)
    assert not isinstance(win.content_area, GraphicNovelManuscriptView)


@pytest.mark.parametrize("engine", ["novel", "screenplay", "stage_script",
                                    "series"])
def test_non_gn_modes_keep_writing_core(engine):
    from logosforge.ui.main_window import MainWindow
    from logosforge.ui.writing_core_view import WritingCoreView
    db = Database()
    pid = db.create_project(engine, narrative_engine=engine,
                            default_writing_format=engine).id
    win = MainWindow(db, pid)
    win._show_manuscript()
    assert isinstance(win.content_area, WritingCoreView)


# ==========================================================================
# Script-editor shape — NOT an outliner, NOT a form
# ==========================================================================


def test_manuscript_contains_no_tree_widget():
    db = Database()
    _pid, _sid, v = _scripted_view(db, pages=2, panels=2)
    assert v.findChildren(QTreeWidget) == []


def test_one_script_block_per_panel_not_five_form_fields():
    db = Database()
    _pid, _sid_, v = _scripted_view(db, pages=2, panels=2)
    blocks = [w for w in v._host.findChildren(QPlainTextEdit)
              if w.objectName() == "gnPanelScript"]
    assert len(blocks) == 4                      # ONE block per panel



def test_labeled_sections_render_inside_block_text():
    db = Database()
    _pid, sid, v = _scripted_view(db)
    gno.set_panel_field(db, sid, 0, 0, "visual_description", "A door.")
    gno.set_panel_field(db, sid, 0, 0, "dialogue", "BOB: hi")
    v.refresh()
    text = _block(v).toPlainText()
    assert "Visual:\nA door." in text
    assert "Dialogue:\nBOB: hi" in text


def test_blocks_are_multiline_writing_oriented():
    db = Database()
    _pid, _sid, v = _scripted_view(db)
    ed = _block(v)
    assert isinstance(ed, QPlainTextEdit)        # multiline
    assert ed.tabChangesFocus() is True          # keyboard walks the script
    assert ed.minimumHeight() >= 100             # large writing area
    h0 = ed.height()
    ed.setPlainText("\n".join(f"line {i}" for i in range(30)))
    assert ed.height() > h0                      # grows like a document


def test_page_headers_rendered_in_order():
    db = Database()
    _pid, _sid, v = _scripted_view(db, pages=3)
    heads = [w.text() for w in v._host.findChildren(QLabel)
             if w.objectName() == "gnPageHeader"]
    assert heads == ["PAGE 1", "PAGE 2", "PAGE 3"]


def test_panel_headers_rendered_in_order():
    db = Database()
    _pid, _sid, v = _scripted_view(db, pages=1, panels=3)
    heads = [w.text() for w in v._host.findChildren(QLabel)
             if w.objectName() == "gnPanelHeader"]
    assert heads == ["Panel 1", "Panel 2", "Panel 3"]


def test_scene_context_header_visible():
    db = Database()
    _pid, _sid_, v = _scripted_view(db)
    # Full-document editor: ACT header + SCENE header + act-wide pages chip;
    # chapters are HIDDEN in Graphic Novel mode.
    acts = [w.text() for w in v._host.findChildren(QLabel)
            if w.objectName() == "gnActHeader"]
    assert acts == ["ACT 1"]
    assert [w.text() for w in v._host.findChildren(QLabel)
            if w.objectName() == "gnSceneHeader"] == ["SCENE 1"]
    chips = [w.text() for w in v._host.findChildren(QLabel)
             if w.objectName() == "gnScenePagesChip"]
    assert chips and "Page" in chips[0]
    assert not any("Chapter" in w.text() for w in v._host.findChildren(QLabel))



def test_full_document_editor_no_scene_dropdown():
    db = Database()
    _pid, _sid_, v = _scripted_view(db)
    # The old single-scene "Comics Script" renderer is gone: no scene
    # dropdown, no Comics Script title — one full document that scrolls.
    assert not hasattr(v, "_scene_combo")
    assert not any("Comics Script" in w.text()
                   for w in v.findChildren(QLabel))
    assert v._scroll.widget() is v._host
    from PySide6.QtCore import Qt
    assert (_block(v).verticalScrollBarPolicy()
            == Qt.ScrollBarPolicy.ScrollBarAlwaysOff)



def test_state_a_no_act_offers_create_act():
    db = Database()
    v = _view(db, _gn(db))                       # project without an Act
    msgs = [w.text() for w in v._host.findChildren(QLabel)
            if w.objectName() == "gnScriptEmpty"]
    assert msgs == ["Create an Act to begin your Graphic Novel."]
    btn = v._host.findChild(QPushButton, "gnScriptCreateAct")
    assert btn is not None and btn.text() == "+ Act"


def test_state_a_create_act_advances_to_add_page():
    db = Database()
    pid = _gn(db)
    v = _view(db, pid)
    v._host.findChild(QPushButton, "gnScriptCreateAct").click()
    assert ss.list_acts(db, pid) == ["Act 1"]    # Act 1 + its first scene
    assert len(ss.list_scenes(db, pid)) == 1
    assert v._host.findChild(QPushButton, "gnDetailAddPage") is not None


def test_state_b_shows_scene_path_and_start_message():
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid, "Cold Open")
    v = _view(db, pid)
    titles = [w.text() for w in v._host.findChildren(QLineEdit)
              if w.objectName() == "gnSceneTitle"]
    assert titles == ["Cold Open"]                   # scene shown in document
    msgs = [w.text() for w in v._host.findChildren(QLabel)
            if w.objectName() == "gnScriptEmpty"]
    assert msgs == ["Start the comics script for this scene."]
    assert v._host.findChild(QPushButton, "gnDetailAddPage") is not None



def test_state_c_page_without_panels_offers_add_panel():
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid)
    v = _view(db, pid)
    v.select_scene(sid)
    v._add_page()
    heads = [w.text() for w in v._host.findChildren(QLabel)
             if w.objectName() == "gnPageHeader"]
    assert heads == ["PAGE 1"]                       # the PAGE block shows
    assert any(w.objectName() == "gnPageNoPanels"
               for w in v._host.findChildren(QLabel))
    assert v._host.findChild(QPushButton, "gnDetailAddPanel") is not None


def test_state_d_panels_render_script_blocks():
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid)
    v = _view(db, pid)
    v.select_scene(sid)
    v._add_page(sid)
    v._add_panel(sid)
    assert not any(w.objectName() == "gnPageNoPanels"
                   for w in v._host.findChildren(QLabel))
    assert ("panel", sid, 0, 0) in v._field_editors



def test_full_block_commit_fills_all_five_fields():
    db = Database()
    _pid, sid, v = _scripted_view(db)
    _commit_block(v, 0, 0, _FULL_BLOCK)
    p = _body(db, sid).pages[0].panels[0]
    assert p.visual_description == ("A tiny chapel buried under rain.\n"
                                    "The dog stands at the threshold.")
    assert p.caption == "The road had forgotten his name."
    assert p.dialogue == "ZAMPANÒ: Woof."         # speaker line stays content
    assert p.sfx == "THOOM"
    assert p.notes == "Keep this panel wide and quiet."


def test_line_breaks_preserved_across_save_reload():
    db = Database()
    _pid, sid, v = _scripted_view(db)
    _commit_block(v, 0, 0, "Visual:\nline one\nline two\nline three")
    reloaded = gnb.load_scene_script(db, sid)    # fresh parse of Scene.content
    assert reloaded.pages[0].panels[0].visual_description == \
        "line one\nline two\nline three"


def test_unlabeled_text_goes_to_visual_nothing_lost():
    db = Database()
    _pid, sid, v = _scripted_view(db)
    _commit_block(v, 0, 0, "Just prose with no labels.\nSecond line.")
    p = _body(db, sid).pages[0].panels[0]
    assert p.visual_description == "Just prose with no labels.\nSecond line."


def test_recommit_same_text_does_not_duplicate_panels():
    db = Database()
    _pid, sid, v = _scripted_view(db, pages=1, panels=2)
    _commit_block(v, 0, 0, _FULL_BLOCK)
    before = db.get_scene_by_id(sid).content
    _commit_block(v, 0, 0, _FULL_BLOCK)          # identical re-commit
    body = _body(db, sid)
    assert body.panel_count() == 2               # no duplication
    assert db.get_scene_by_id(sid).content == before


def test_structural_markers_inside_block_stay_plain_text():
    # Typing "PAGE 2" / "PANEL 9" inside a panel block must NOT change the
    # scene structure — blocks edit content, the Outline manages structure.
    db = Database()
    _pid, sid, v = _scripted_view(db, pages=1, panels=1)
    _commit_block(v, 0, 0, "Visual:\nPAGE 2\nPANEL 9\nstill the same panel")
    body = _body(db, sid)                            # fresh parse of the body
    assert len(body.pages) == 1                      # structure unchanged
    assert body.panel_count() == 1
    visual = body.pages[0].panels[0].visual_description
    # Content preserved (marker-looking lines folded, never dropped).
    assert "PAGE 2" in visual and "PANEL 9" in visual
    assert "still the same panel" in visual


def test_numbers_stay_canonical_across_edits():
    db = Database()
    _pid, sid, v = _scripted_view(db, pages=2, panels=2)
    _commit_block(v, 0, 0, "Visual: edited")
    body = _body(db, sid)
    assert [p.number for p in body.pages] == [1, 2]
    # Panels auto-number 1..n within their page (the canonical scheme).
    assert [pl.number for pg in body.pages for pl in pg.panels] == [1, 2, 1, 2]


def test_programmatic_field_commit_updates_block_text():
    db = Database()
    _pid, sid, v = _scripted_view(db)
    # Programmatic path: write the field through the shared body and let
    # refresh re-render the block (the Outline/voice routes work this way).
    gno.set_panel_field(db, sid, 0, 0, "sfx", "KRAKOOM")
    v.refresh()
    assert "SFX:\nKRAKOOM" in _block(v).toPlainText()
    assert _body(db, sid).pages[0].panels[0].sfx == "KRAKOOM"


def test_page_title_and_notes_edit_persist():
    db = Database()
    _pid, sid, v = _scripted_view(db)
    title = v._field_editors[("page", sid, 0, "title")]
    title.setText("Rooftops")
    title.editingFinished.emit()
    notes = v._field_editors[("page", sid, 0, "summary")]
    notes.setPlainText("Splash page")
    notes.committed.emit()
    body = _body(db, sid)
    assert body.pages[0].title == "Rooftops"
    assert body.pages[0].summary == "Splash page"


def test_add_page_and_per_page_add_panel():
    db = Database()
    _pid, sid, v = _scripted_view(db, pages=2, panels=1)
    v._add_page()
    assert [p.number for p in _body(db, sid).pages] == [1, 2, 3]
    btn = [w for w in v._host.findChildren(QPushButton)
           if w.objectName() == "gnDetailAddPanel"][0]   # first page's button
    btn.click()
    body = _body(db, sid)
    assert len(body.pages[0].panels) == 2
    assert len(body.pages[1].panels) == 1


def test_delete_panel_confirm_and_cancel(monkeypatch):
    db = Database()
    _pid, sid, v = _scripted_view(db, pages=1, panels=3)
    monkeypatch.setattr(safe_dialogs, "question", lambda *a, **k: False)
    v._delete_panel(sid, 0, 0)
    assert len(_body(db, sid).pages[0].panels) == 3      # cancel keeps
    monkeypatch.setattr(safe_dialogs, "question", lambda *a, **k: True)
    v._delete_panel(sid, 0, 0)
    assert [p.number for p in _body(db, sid).pages[0].panels] == [1, 2]


def test_delete_page_confirm_and_cancel(monkeypatch):
    db = Database()
    _pid, sid, v = _scripted_view(db, pages=2, panels=1)
    monkeypatch.setattr(safe_dialogs, "question", lambda *a, **k: False)
    v._delete_page(sid, 0)
    assert len(_body(db, sid).pages) == 2
    monkeypatch.setattr(safe_dialogs, "question", lambda *a, **k: True)
    v._delete_page(sid, 0)
    body = _body(db, sid)
    assert len(body.pages) == 1 and body.pages[0].number == 1


def test_move_panel_reorders_within_page():
    db = Database()
    _pid, sid, v = _scripted_view(db, pages=1, panels=2)
    _commit_block(v, 0, 0, "Visual: first")
    _commit_block(v, 0, 1, "Visual: second")
    v._move_panel(sid, 0, 1, -1)
    panels = _body(db, sid).pages[0].panels
    assert panels[0].visual_description == "second"
    assert [p.number for p in panels] == [1, 2]


# ==========================================================================
# Navigation / deep-links
# ==========================================================================


def test_select_scene_targets_that_scenes_script():
    db = Database()
    pid = _gn(db)
    s1 = _scene(db, pid, "One")
    s2 = _scene(db, pid, "Two")
    gno.add_page(db, s2); gno.add_panel(db, s2, 0)
    gno.set_panel_field(db, s2, 0, 0, "visual_description", "SECOND-SCENE")
    v = _view(db, pid)
    v.select_scene(s2)
    assert "SECOND-SCENE" in _block(v, sid=s2).toPlainText()
    v.select_scene(s1)
    assert v._host.findChild(QPushButton, "gnDetailAddPage") is not None



def test_document_shows_all_scenes_without_switching():
    db = Database()
    pid = _gn(db)
    _s1 = _scene(db, pid, "One")
    s2 = _scene(db, pid, "Two")
    gno.add_page(db, s2)
    v = _view(db, pid)                            # whole project, one document
    titles = [w.text() for w in v._host.findChildren(QLineEdit)
              if w.objectName() == "gnSceneTitle"]
    assert titles == ["One", "Two"]
    heads = [w.text() for w in v._host.findChildren(QLabel)
             if w.objectName() == "gnPageHeader"]
    assert heads == ["PAGE 1"]                    # Two's page, no switching



def test_select_panel_focuses_script_block(monkeypatch):
    db = Database()
    _pid, _sid, v = _scripted_view(db, pages=2, panels=2)
    target = _block(v, 1, 1)
    seen = {"focus": 0, "visible": None}
    monkeypatch.setattr(target, "setFocus",
                        lambda *a: seen.__setitem__("focus", seen["focus"] + 1))
    monkeypatch.setattr(v._scroll, "ensureWidgetVisible",
                        lambda w, *a: seen.__setitem__("visible", w))
    v.select_panel(1, 1)
    assert seen["focus"] == 1 and seen["visible"] is target


def test_outline_panel_double_click_deep_links_to_block():
    from logosforge.ui.graphic_novel_outline_view import GraphicNovelOutlineView
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid)
    gno.add_page(db, sid); gno.add_panel(db, sid, 0); gno.add_panel(db, sid, 0)
    hits = []
    o = GraphicNovelOutlineView(
        db, pid, on_data_changed=lambda: None,
        on_open_manuscript=lambda s: hits.append(("scene", s)),
        on_open_panel=lambda s, p, c: hits.append(("panel", s, p, c)))
    card = next(c for c in o._cards
                if c.gn_data.get("kind") == "panel"
                and c.gn_data.get("panel") == 1)
    o._activate(card.gn_data)
    assert hits == [("panel", sid, 0, 1)]         # deep-link, not scene-only



def test_main_window_panel_deep_link_focuses_block():
    from logosforge.ui.main_window import MainWindow
    from logosforge.ui.writing_core_view import WritingCoreView
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid)
    gno.add_page(db, sid); gno.add_panel(db, sid, 0); gno.add_panel(db, sid, 0)
    win = MainWindow(db, pid)
    win._open_gn_panel_in_manuscript(sid, 0, 1)
    view = win.content_area
    assert isinstance(view, WritingCoreView)
    editor = view._editors[sid]
    # The shared editor's cursor lands inside PANEL 2 (cursor->panel map).
    assert gnb.panel_at_offset(editor.toPlainText(),
                               editor.textCursor().position()) == (0, 1)


def test_outline_view_still_mounts_for_plan_section():
    from logosforge.ui.main_window import MainWindow
    from logosforge.ui.plan_view import PlanView
    db = Database()
    win = MainWindow(db, _gn(db))
    win._show_plan()
    assert isinstance(win.content_area, PlanView)   # shared planner, GN schema



# ==========================================================================
# Outline ⇄ Manuscript mirroring over ONE shared body
# ==========================================================================


def test_outline_add_page_and_panel_appear_in_manuscript():
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid)
    v = _view(db, pid)
    v.select_scene(sid)
    gno.add_page(db, sid)
    gno.add_panel(db, sid, 0)
    gno.set_panel_field(db, sid, 0, 0, "dialogue", "FROM_OUTLINE")
    v.refresh()
    heads = [w.text() for w in v._host.findChildren(QLabel)
             if w.objectName() == "gnPageHeader"]
    assert heads == ["PAGE 1"]
    assert "Dialogue:\nFROM_OUTLINE" in _block(v).toPlainText()


def test_outline_panel_page_assignment_appears_in_manuscript():
    db = Database()
    pid = _gn(db)
    sid = _scene(db, pid)
    gno.add_page(db, sid); gno.add_page(db, sid)
    gno.add_panel(db, sid, 0)
    gno.set_panel_field(db, sid, 0, 0, "visual_description", "MOVER")
    assert gno.move_panel_to_page(db, sid, 0, 0, 1) is True
    v = _view(db, pid)
    v.select_scene(sid)
    assert ("panel", sid, 0, 0) not in v._field_editors  # left page 1
    assert "MOVER" in _block(v, 1, 0).toPlainText()    # shown under PAGE 2


def test_manuscript_edits_appear_in_outline_data():
    db = Database()
    _pid, sid, v = _scripted_view(db)
    v._add_page(sid)                                   # Manuscript adds page 2
    v._add_panel(sid, 1)                               # … and a panel on it
    _commit_block(v, 1, 0, "Visual:\nFROM_MANUSCRIPT")
    script = gnb.load_scene_script(db, sid)            # what the Outline reads
    assert len(script.pages) == 2
    assert gno.panel_snippet(script.pages[1].panels[0]).startswith(
        "FROM_MANUSCRIPT"[:10])
    assert "FROM_MANUSCRIPT" in (db.get_scene_by_id(sid).content or "")


def test_refresh_skips_rebuild_when_data_unchanged():
    db = Database()
    _pid, _sid, v = _scripted_view(db)
    ed_before = _block(v)
    v.refresh()                                   # nothing changed
    assert _block(v) is ed_before


def test_focus_location_captured_and_restored(monkeypatch):
    db = Database()
    _pid, sid, v = _scripted_view(db)
    ed = _block(v)
    monkeypatch.setattr(QApplication, "focusWidget",
                        staticmethod(lambda: ed))
    restored = {}
    monkeypatch.setattr(v, "_restore_focus",
                        lambda loc: restored.setdefault("loc", loc))
    gno.set_panel_field(db, sid, 0, 0, "caption", "X")   # external change
    v.refresh()
    assert restored["loc"][0] == ("panel", sid, 0, 0)



def test_project_switch_isolation(tmp_path):
    db = Database(str(tmp_path / "iso.db"))
    a = _gn(db, "A")
    sa = _scene(db, a, "A-scene")
    va = _view(db, a)
    va.select_scene(sa)
    va._add_page(sa)
    b = _gn(db, "B")                              # empty project
    vb = _view(db, b)
    assert vb._scripts == {}
    assert vb._host.findChild(QPushButton, "gnScriptCreateAct") is not None



def test_save_reload_round_trip():
    db = Database()
    _pid, sid, v = _scripted_view(db)
    _commit_block(v, 0, 0, _FULL_BLOCK)
    v2 = _view(db, _pid)                          # fresh view, fresh parse
    v2.select_scene(sid)
    assert "ZAMPANÒ: Woof." in _block(v2).toPlainText()


# ==========================================================================
# Parser helpers (panel_script_text / parse_panel_text)
# ==========================================================================


def test_panel_text_round_trip():
    panel = gnb.Panel(number=1, visual_description="a\nb", caption="c",
                      dialogue="NAME: d", sfx="BOOM", notes="n")
    fields = gnb.parse_panel_text(gnb.panel_script_text(panel))
    assert fields == {"visual_description": "a\nb", "caption": "c",
                      "dialogue": "NAME: d", "sfx": "BOOM", "notes": "n"}


def test_parse_panel_text_aliases_and_repeats():
    fields = gnb.parse_panel_text(
        "Art:\nthumbnail note\n\nVisual: one\nVisual: two")
    assert fields["notes"] == "thumbnail note"     # Art -> notes alias
    assert fields["visual_description"] == "one\ntwo"  # repeats append


def test_parse_panel_text_empty_and_unknown_labels():
    assert gnb.parse_panel_text("") == {
        "visual_description": "", "caption": "", "dialogue": "",
        "sfx": "", "notes": ""}
    fields = gnb.parse_panel_text("Dialogue:\nBOB: hi\nMood: tense")
    assert fields["dialogue"] == "BOB: hi\nMood: tense"  # unknown label kept


# ==========================================================================
# Structural fullscreen safety + standalone Pages stays disabled
# ==========================================================================


def test_pages_sidebar_hidden_and_route_inert():
    from logosforge.ui.main_window import MainWindow
    from logosforge.ui.graphic_novel_scene_pages_view import (
        GraphicNovelScenePagesView)
    from logosforge.ui.graphic_novel_manuscript_view import (
        GraphicNovelManuscriptView)
    db = Database()
    win = MainWindow(db, _gn(db))
    assert "Pages" not in win._nav_labels
    assert "Pages" not in win.sidebar_buttons
    win._show_gn_pages()
    assert not isinstance(win.content_area, GraphicNovelScenePagesView)
    from logosforge.ui.writing_core_view import WritingCoreView
    assert isinstance(win.content_area, WritingCoreView)   # shared editor


def test_mount_creates_no_new_top_level_window():
    from logosforge.ui.main_window import MainWindow
    db = Database()
    win = MainWindow(db, _gn(db))
    before = set(QApplication.topLevelWidgets())
    win._show_manuscript()
    new_visible = [w for w in (set(QApplication.topLevelWidgets()) - before)
                   if w.isVisible()]
    assert new_visible == []
    assert win.content_area.window() is win


def test_manuscript_and_outline_activation_do_not_minimize():
    from logosforge.ui.main_window import MainWindow
    db = Database()
    win = MainWindow(db, _gn(db))
    calls = {"min": 0, "hide": 0}
    win.showMinimized = lambda: calls.__setitem__("min", calls["min"] + 1)  # type: ignore
    win.hide = lambda: calls.__setitem__("hide", calls["hide"] + 1)         # type: ignore
    win._show_manuscript()
    win._show_plan()
    assert calls == {"min": 0, "hide": 0}


def test_no_dialog_children_on_mount():
    db = Database()
    _pid, _sid, v = _scripted_view(db, pages=2, panels=2)
    assert v.findChildren(QDialog) == []


# ==========================================================================
# Export — canonical model, no duplicates, no image generation
# ==========================================================================


def test_export_includes_structure_fields_and_assignment():
    db = Database()
    pid, sid, v = _scripted_view(db, pages=2, panels=1)
    _commit_block(v, 1, 0, _FULL_BLOCK)
    md = gnb.export_project_markdown(db, pid)
    scene = db.get_scene_by_id(sid)
    assert scene.title in md                       # Scene ownership
    assert "Page 1" in md and "Page 2" in md       # Page assignment headers
    for needle in ("Visual:", "Caption:", "Dialogue:", "SFX:", "Notes:"):
        assert needle in md
    assert md.count("ZAMPANÒ: Woof.") == 1         # no duplicate panel text


def test_export_preserves_line_breaks_in_fields():
    db = Database()
    pid, _sid, v = _scripted_view(db)
    _commit_block(v, 0, 0, "Visual:\nfirst line\nsecond line")
    md = gnb.export_project_markdown(db, pid)
    assert "first line" in md and "second line" in md


def test_export_has_no_image_generation_terms():
    db = Database()
    pid, _sid, v = _scripted_view(db)
    _commit_block(v, 0, 0, "Visual:\nA quiet street")
    low = gnb.export_project_markdown(db, pid).lower()
    for banned in ("comfyui", "image prompt", "lora", "img2img", "txt2img"):
        assert banned not in low


def test_panel_model_has_no_image_generation_fields():
    fields = set(vars(gnb.Panel()).keys())
    for banned in ("image", "prompt", "comfyui", "lora", "seed", "sampler"):
        assert not any(banned in f for f in fields), banned


def test_view_module_has_no_image_generation_refs():
    # Scan the CODE only (docstrings state the "no image generation" rule and
    # would trip a raw text scan).
    import ast
    import inspect
    from logosforge.ui import graphic_novel_manuscript_view as mod
    tree = ast.parse(inspect.getsource(mod))
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if (isinstance(body, list) and body and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)):
            body[0].value.value = ""
    code = ast.unparse(tree).lower()
    for banned in ("comfyui", "img2img", "txt2img", "image prompt",
                   "image_generation"):
        assert banned not in code, banned


def test_view_never_imports_standalone_pages_widget():
    import inspect
    from logosforge.ui import graphic_novel_manuscript_view as mod
    src = inspect.getsource(mod)
    assert "graphic_novel_scene_pages_view" not in src
    assert "GraphicNovelScenePagesView" not in src
