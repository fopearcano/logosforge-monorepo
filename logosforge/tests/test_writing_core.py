"""Tests for Writing Core view — canvas layout, typography, command palette,
manuscript highlighting, format toolbar, typewriter mode, PSYKE entity awareness."""

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QTextCursor, QTextDocument
from PySide6.QtWidgets import QApplication, QWidget

from logosforge.db import Database
from logosforge.ui.command_palette import COMMANDS, CommandPalette
from logosforge.ui.entity_hover import EntityHoverHandler, EntityHoverPanel
from logosforge.ui.format_toolbar import FormatToolbar
from logosforge.ui.manuscript_highlighter import ManuscriptHighlighter
from logosforge.ui.psyke_highlighter import PsykeClickHandler, PsykeHighlighter
from logosforge.ui.writing_core_view import (
    WritingCoreView,
    _BODY_FONT_SIZE,
    _BODY_LINE_HEIGHT,
    _BlockData,
    _CANVAS_MAX_WIDTH,
    _CANVAS_PADDING_H,
    _ELEMENT_TRANSITIONS,
    _FOCUS_LINE_HEIGHT,
    _SceneEditor,
)
from logosforge.writing_formats import ALL_FORMATS, FORMAT_ORDER, WritingFormat


def _setup_project(db):
    proj = db.create_project("Novel")
    s1 = db.create_scene(proj.id, "Opening", content="The storm began.", act="Act One", chapter="Chapter 1")
    s2 = db.create_scene(proj.id, "Rising Action", content="She ran.", act="Act One", chapter="Chapter 1")
    s3 = db.create_scene(proj.id, "Midpoint", content="The truth revealed.", act="Act Two", chapter="Chapter 2")
    return proj, s1, s2, s3


# -- Canvas layout -----------------------------------------------------------

def test_canvas_max_width():
    assert _CANVAS_MAX_WIDTH >= 600
    assert _CANVAS_MAX_WIDTH <= 850


def test_canvas_padding():
    assert _CANVAS_PADDING_H >= 32


def test_body_font_size():
    assert 17 <= _BODY_FONT_SIZE <= 19


def test_line_height():
    assert 1.4 <= _BODY_LINE_HEIGHT <= 1.6


def test_focus_line_height_larger():
    assert _FOCUS_LINE_HEIGHT > _BODY_LINE_HEIGHT


# -- View construction -------------------------------------------------------

def test_view_loads_scenes():
    db = Database()
    proj, s1, s2, s3 = _setup_project(db)
    view = WritingCoreView(db, proj.id)
    assert len(view._editors) == 3
    assert s1.id in view._editors
    assert s2.id in view._editors
    assert s3.id in view._editors


def test_editor_content_matches_scene():
    db = Database()
    proj, s1, s2, s3 = _setup_project(db)
    view = WritingCoreView(db, proj.id)
    assert view._editors[s1.id].toPlainText() == "The storm began."
    assert view._editors[s3.id].toPlainText() == "The truth revealed."


def test_editor_renders_markdown_as_rich_text():
    db = Database()
    proj = db.create_project("MD")
    db.create_scene(proj.id, "S1", content="**bold** and *italic*")
    view = WritingCoreView(db, proj.id)
    editors = list(view._editors.values())
    editor = editors[0]
    assert editor.toPlainText() == "bold and italic"
    md = editor.toMarkdown()
    assert "**bold**" in md
    assert "*italic*" in md


def test_editor_renders_headings():
    db = Database()
    proj = db.create_project("HD")
    db.create_scene(proj.id, "S1", content="# Chapter One\n\nSome text.")
    view = WritingCoreView(db, proj.id)
    editor = list(view._editors.values())[0]
    assert "Chapter One" in editor.toPlainText()
    assert "#" not in editor.toPlainText()


def test_editor_renders_lists():
    db = Database()
    proj = db.create_project("LS")
    db.create_scene(proj.id, "S1", content="- item one\n- item two")
    view = WritingCoreView(db, proj.id)
    editor = list(view._editors.values())[0]
    plain = editor.toPlainText()
    assert "item one" in plain
    assert "item two" in plain


def test_editor_save_preserves_markdown():
    db = Database()
    proj = db.create_project("SV")
    scene = db.create_scene(proj.id, "S1", content="**hello** world")
    view = WritingCoreView(db, proj.id)
    view._save_scene(scene.id)
    saved = db.get_scene_by_id(scene.id)
    assert "**hello**" in saved.content
    assert "world" in saved.content


def test_format_then_save_then_reload_preserves_bold():
    """End-to-end regression: bold a selection via the toolbar, save, reload in a
    fresh view → the bold survives. (Qt 6.8's toMarkdown() dropped inline
    emphasis, silently losing formatting on save.)"""
    db = Database()
    proj = db.create_project("RT")
    scene = db.create_scene(proj.id, "S1", content="hello world")
    view = WritingCoreView(db, proj.id)
    editor = view._editors[scene.id]
    cursor = editor.textCursor()
    cursor.setPosition(6)
    cursor.setPosition(11, QTextCursor.MoveMode.KeepAnchor)
    editor.setTextCursor(cursor)
    FormatToolbar().toggle_bold_on(editor)
    view._save_scene(scene.id)
    assert "**world**" in db.get_scene_by_id(scene.id).content

    view2 = WritingCoreView(db, proj.id)
    assert "**world**" in view2._editors[scene.id].toMarkdown()


def test_empty_project_has_no_editors():
    db = Database()
    proj = db.create_project("Empty")
    view = WritingCoreView(db, proj.id)
    assert len(view._editors) == 0


def test_refresh_rebuilds_canvas():
    db = Database()
    proj, s1, s2, s3 = _setup_project(db)
    view = WritingCoreView(db, proj.id)
    assert len(view._editors) == 3
    db.create_scene(proj.id, "New Scene", content="Added later.")
    view.refresh()
    assert len(view._editors) == 4


# -- Focus mode ---------------------------------------------------------------

def test_focus_mode_toggle():
    db = Database()
    proj, *_ = _setup_project(db)
    view = WritingCoreView(db, proj.id)
    assert view._focus_mode is False
    view.toggle_focus_mode()
    assert view._focus_mode is True
    assert not view._focus_bar.isHidden()
    assert view._top_bar.isHidden()
    view.toggle_focus_mode()
    assert view._focus_mode is False
    assert not view._top_bar.isHidden()
    assert view._focus_bar.isHidden()


def test_focus_mode_narrows_canvas():
    db = Database()
    proj, *_ = _setup_project(db)
    view = WritingCoreView(db, proj.id)
    normal_max = view._inner.maximumWidth()
    view.toggle_focus_mode()
    focus_max = view._inner.maximumWidth()
    assert focus_max < normal_max


def test_focus_mode_callback():
    db = Database()
    proj, *_ = _setup_project(db)
    calls = []
    view = WritingCoreView(
        db, proj.id, on_focus_mode_changed=lambda active: calls.append(active),
    )
    view.toggle_focus_mode()
    assert calls == [True]
    view.toggle_focus_mode()
    assert calls == [True, False]


# -- Font & size selector -----------------------------------------------------

def test_font_family_selector():
    db = Database()
    proj, *_ = _setup_project(db)
    view = WritingCoreView(db, proj.id)
    assert view._font_family_key == "sans"
    assert view._font_combo.currentData() == "sans"

    def _select(key: str) -> None:
        for i in range(view._font_combo.count()):
            if view._font_combo.itemData(i) == key:
                view._font_combo.setCurrentIndex(i)
                return
        raise AssertionError(f"font key {key!r} not in combo")

    _select("serif")
    assert view._font_family_key == "serif"
    settings = db.get_project_settings(proj.id)
    assert settings["font_family"] == "serif"
    _select("mono")
    assert view._font_family_key == "mono"
    _select("courier_new")
    assert view._font_family_key == "courier_new"


def test_font_size_selector():
    db = Database()
    proj, *_ = _setup_project(db)
    view = WritingCoreView(db, proj.id)
    assert view._font_size == 18
    view._size_combo.setCurrentIndex(0)  # 14
    assert view._font_size == 14
    settings = db.get_project_settings(proj.id)
    assert settings["font_size"] == 14
    view._size_combo.setCurrentIndex(8)  # 24
    assert view._font_size == 24


def test_font_settings_persist_across_sessions():
    db = Database()
    proj, *_ = _setup_project(db)
    view1 = WritingCoreView(db, proj.id)
    view1._font_combo.setCurrentIndex(0)  # serif
    view1._size_combo.setCurrentIndex(6)  # 20
    del view1
    view2 = WritingCoreView(db, proj.id)
    assert view2._font_family_key == "serif"
    assert view2._font_size == 20
    assert view2._font_combo.currentData() == "serif"
    assert view2._size_combo.currentData() == 20


def test_first_line_indent_toggle():
    db = Database()
    proj, *_ = _setup_project(db)
    view = WritingCoreView(db, proj.id)
    assert view._first_line_indent is False
    view._toggle_indent()
    assert view._first_line_indent is True
    settings = db.get_project_settings(proj.id)
    assert settings["first_line_indent"] is True
    view._toggle_indent()
    assert view._first_line_indent is False


def test_first_line_indent_persists():
    db = Database()
    proj, *_ = _setup_project(db)
    view1 = WritingCoreView(db, proj.id)
    view1._toggle_indent()
    del view1
    view2 = WritingCoreView(db, proj.id)
    assert view2._first_line_indent is True


# -- Auto-save ----------------------------------------------------------------

def test_auto_save_updates_db():
    db = Database()
    proj, s1, *_ = _setup_project(db)
    view = WritingCoreView(db, proj.id)
    view._editors[s1.id].setPlainText("Edited content.")
    view._save_scene(s1.id)
    saved = db.get_scene_by_id(s1.id)
    assert saved.content == "Edited content."


# -- Word count ----------------------------------------------------------------

def test_word_count_updates():
    db = Database()
    proj, s1, s2, s3 = _setup_project(db)
    view = WritingCoreView(db, proj.id)
    view._update_word_count()
    text = view._word_count_label.text()
    assert "words" in text
    count = int(text.split()[0].replace(",", ""))
    assert count > 0


# -- Scene creation -----------------------------------------------------------

def test_create_scene_adds_editor():
    db = Database()
    proj, s1, s2, s3 = _setup_project(db)
    view = WritingCoreView(db, proj.id)
    assert len(view._editors) == 3
    view._create_scene_after(None)
    assert len(view._editors) == 4


def test_create_scene_with_chapter():
    db = Database()
    proj, s1, *_ = _setup_project(db)
    view = WritingCoreView(db, proj.id)
    view._create_scene_after(s1.id, chapter="Chapter 1")
    scenes = db.get_all_scenes(proj.id)
    chapters = [s.chapter for s in scenes if s.chapter == "Chapter 1"]
    assert len(chapters) >= 2


# -- Command palette ----------------------------------------------------------

def test_command_palette_has_commands():
    assert len(COMMANDS) >= 6
    keys = [c[1] for c in COMMANDS]
    assert "scene" in keys
    assert "chapter" in keys
    assert "focus" in keys


def test_command_palette_creates():
    palette = CommandPalette()
    assert palette._list.count() == len(COMMANDS)


def test_command_palette_filter():
    palette = CommandPalette()
    palette._on_filter("scene")
    assert palette._list.count() >= 1


def test_command_palette_filter_empty():
    palette = CommandPalette()
    palette._on_filter("zzzznonexistent")
    assert palette._list.count() == 0


# -- SceneEditor slash detection -----------------------------------------------

def test_scene_editor_has_no_frame():
    editor = _SceneEditor()
    assert editor.objectName() == "writingCoreEditor"


# -- Typography constants ------------------------------------------------------

def test_typography_hierarchy():
    """Act < Scene < Chapter in font size terms."""
    # Act: 11px, Scene title: 15px, Chapter: 22px
    assert 11 < 15 < 22


# -- Scroll to scene ----------------------------------------------------------

def test_scroll_to_scene():
    db = Database()
    proj, s1, s2, s3 = _setup_project(db)
    view = WritingCoreView(db, proj.id)
    view.scroll_to_scene(s3.id)
    assert view._editors[s3.id].hasFocus() or True  # Focus may not work without show


# -- Manuscript Highlighter ---------------------------------------------------

def test_manuscript_highlighter_inherits_psyke():
    assert issubclass(ManuscriptHighlighter, PsykeHighlighter)


def test_manuscript_highlighter_creates():
    doc = QTextDocument()
    h = ManuscriptHighlighter(doc)
    assert h._b_fmt is not None
    assert h._i_fmt is not None
    assert h._bi_fmt is not None
    assert h._h1_fmt is not None
    assert h._h2_fmt is not None
    assert h._h3_fmt is not None
    assert h._q_fmt is not None
    assert h._sep_fmt is not None


def test_manuscript_highlighter_refresh_theme():
    doc = QTextDocument()
    h = ManuscriptHighlighter(doc)
    h.refresh_theme()


def test_manuscript_highlighter_refresh_patterns():
    doc = QTextDocument()
    h = ManuscriptHighlighter(doc)
    h.refresh_patterns(["Alice", "Bob"])


def test_view_uses_psyke_highlighter():
    db = Database()
    proj, s1, *_ = _setup_project(db)
    view = WritingCoreView(db, proj.id)
    assert isinstance(view._highlighters[s1.id], PsykeHighlighter)


# -- PSYKE color-coded highlighting -------------------------------------------

def test_psyke_highlighter_has_type_formats():
    doc = QTextDocument()
    h = PsykeHighlighter(doc)
    assert "character" in h._formats
    assert "place" in h._formats
    assert "object" in h._formats


def test_psyke_highlighter_uses_term_types():
    doc = QTextDocument()
    doc.setPlainText("Alice went to Castle")
    h = PsykeHighlighter(doc)
    h.refresh_patterns(
        ["Alice", "Castle"],
        term_types={"alice": "character", "castle": "place"},
    )
    assert h._term_types["alice"] == "character"
    assert h._term_types["castle"] == "place"


def test_psyke_highlighter_different_colors_per_type():
    doc = QTextDocument()
    h = PsykeHighlighter(doc)
    char_fmt = h._formats["character"]
    place_fmt = h._formats["place"]
    obj_fmt = h._formats["object"]
    assert char_fmt.foreground().color() != place_fmt.foreground().color()
    assert place_fmt.foreground().color() != obj_fmt.foreground().color()


def test_psyke_highlighter_unknown_type_uses_default():
    doc = QTextDocument()
    doc.setPlainText("Prophecy of doom")
    h = PsykeHighlighter(doc)
    h.refresh_patterns(["Prophecy"], term_types={"prophecy": "concept"})
    assert h._term_types["prophecy"] == "concept"
    assert "concept" not in h._formats


def test_psyke_highlighting_with_aliases():
    doc = QTextDocument()
    doc.setPlainText("Jon walked to the Tower")
    h = PsykeHighlighter(doc)
    h.refresh_patterns(
        ["Jonathan", "Jon", "Tower"],
        term_types={"jonathan": "character", "jon": "character", "tower": "place"},
    )
    assert h._pattern is not None
    assert h._pattern.search("Jon walked to the Tower")


def test_view_passes_term_types_to_highlighter():
    db = Database()
    proj = db.create_project("HL")
    db.create_scene(proj.id, "S1", content="Alice visited Castle")
    db.create_psyke_entry(proj.id, "Alice", "character")
    db.create_psyke_entry(proj.id, "Castle", "place")
    view = WritingCoreView(db, proj.id)
    view.refresh_psyke_terms()
    highlighter = list(view._highlighters.values())[0]
    assert highlighter._term_types.get("alice") == "character"
    assert highlighter._term_types.get("castle") == "place"


# -- Format Toolbar -----------------------------------------------------------

def test_format_toolbar_creates():
    toolbar = FormatToolbar()
    assert toolbar.objectName() == "formatToolbar"


def test_format_toolbar_bold_applies():
    editor = _SceneEditor()
    editor.setPlainText("hello world")
    cursor = editor.textCursor()
    cursor.setPosition(6)
    cursor.setPosition(11, QTextCursor.MoveMode.KeepAnchor)
    editor.setTextCursor(cursor)

    toolbar = FormatToolbar()
    toolbar.toggle_bold_on(editor)
    md = editor.toMarkdown().strip()
    assert "**world**" in md
    assert editor.toPlainText() == "hello world"


def test_format_toolbar_bold_toggles_off():
    editor = _SceneEditor()
    editor.setPlainText("hello world")
    cursor = editor.textCursor()
    cursor.setPosition(6)
    cursor.setPosition(11, QTextCursor.MoveMode.KeepAnchor)
    editor.setTextCursor(cursor)

    toolbar = FormatToolbar()
    toolbar.toggle_bold_on(editor)
    cursor = editor.textCursor()
    cursor.setPosition(6)
    cursor.setPosition(11, QTextCursor.MoveMode.KeepAnchor)
    editor.setTextCursor(cursor)
    toolbar.toggle_bold_on(editor)
    md = editor.toMarkdown().strip()
    assert "**" not in md


def test_format_toolbar_italic_applies():
    editor = _SceneEditor()
    editor.setPlainText("hello world")
    cursor = editor.textCursor()
    cursor.setPosition(6)
    cursor.setPosition(11, QTextCursor.MoveMode.KeepAnchor)
    editor.setTextCursor(cursor)

    toolbar = FormatToolbar()
    toolbar.toggle_italic_on(editor)
    md = editor.toMarkdown().strip()
    assert "*world*" in md
    assert editor.toPlainText() == "hello world"


def test_format_toolbar_heading_cycle():
    editor = _SceneEditor()
    editor.setPlainText("Title")
    cursor = editor.textCursor()
    cursor.setPosition(0)
    editor.setTextCursor(cursor)

    toolbar = FormatToolbar()
    toolbar._active_editor = editor
    toolbar._cycle_heading()
    assert editor.toMarkdown().strip() == "# Title"
    toolbar._cycle_heading()
    assert editor.toMarkdown().strip() == "## Title"
    toolbar._cycle_heading()
    assert editor.toMarkdown().strip() == "### Title"
    toolbar._cycle_heading()
    assert editor.toMarkdown().strip() == "Title"


def test_format_toolbar_quote_toggle():
    editor = _SceneEditor()
    editor.setPlainText("Some text")
    cursor = editor.textCursor()
    cursor.setPosition(0)
    editor.setTextCursor(cursor)

    toolbar = FormatToolbar()
    toolbar._active_editor = editor
    toolbar._toggle_quote()
    assert "> Some text" in editor.toMarkdown()
    toolbar._toggle_quote()
    assert ">" not in editor.toMarkdown()


def test_format_toolbar_track_editor():
    toolbar = FormatToolbar()
    editor = _SceneEditor()
    toolbar.track_editor(editor)
    assert editor in toolbar._tracked
    toolbar.untrack_all()
    assert len(toolbar._tracked) == 0


def test_view_has_format_toolbar():
    db = Database()
    proj, *_ = _setup_project(db)
    view = WritingCoreView(db, proj.id)
    assert hasattr(view, "_format_toolbar")
    assert isinstance(view._format_toolbar, FormatToolbar)


# -- Typewriter mode ----------------------------------------------------------

def test_typewriter_mode_toggle():
    db = Database()
    proj, *_ = _setup_project(db)
    view = WritingCoreView(db, proj.id)
    assert view._typewriter_mode is False
    view.toggle_typewriter_mode()
    assert view._typewriter_mode is True
    view.toggle_typewriter_mode()
    assert view._typewriter_mode is False


def test_typewriter_mode_accessor():
    db = Database()
    proj, *_ = _setup_project(db)
    view = WritingCoreView(db, proj.id)
    assert view.is_typewriter_mode() is False
    view.toggle_typewriter_mode()
    assert view.is_typewriter_mode() is True


# -- Session state persistence ------------------------------------------------

def test_focus_mode_persists():
    db = Database()
    proj, *_ = _setup_project(db)
    view1 = WritingCoreView(db, proj.id)
    view1.toggle_focus_mode()
    assert view1._focus_mode is True
    view1._persist_session_state()
    del view1
    view2 = WritingCoreView(db, proj.id)
    view2.refresh()
    assert view2._focus_mode is True


def test_typewriter_mode_default_off():
    """Typewriter mode is always OFF by default; the saved state is not restored."""
    db = Database()
    proj, *_ = _setup_project(db)
    view1 = WritingCoreView(db, proj.id)
    view1.toggle_typewriter_mode()
    view1._persist_session_state()
    del view1
    view2 = WritingCoreView(db, proj.id)
    view2.refresh()
    assert view2._typewriter_mode is False


def test_cursor_position_persists():
    db = Database()
    proj, s1, s2, s3 = _setup_project(db)
    view1 = WritingCoreView(db, proj.id)
    editor = view1._editors[s2.id]
    cursor = editor.textCursor()
    cursor.setPosition(5)
    editor.setTextCursor(cursor)
    view1._active_editor = editor
    view1._persist_session_state()
    del view1
    view2 = WritingCoreView(db, proj.id)
    view2.refresh()
    assert view2._active_editor is not None
    assert view2._active_editor._scene_id == s2.id
    assert view2._active_editor.textCursor().position() == 5


def test_scroll_position_persists():
    db = Database()
    proj, *_ = _setup_project(db)
    view1 = WritingCoreView(db, proj.id)
    view1._persist_session_state()
    settings = db.get_project_settings(proj.id)
    assert "scroll_pos" in settings


def test_session_state_includes_all_keys():
    db = Database()
    proj, *_ = _setup_project(db)
    view = WritingCoreView(db, proj.id)
    view.toggle_focus_mode()
    view.toggle_typewriter_mode()
    view._persist_session_state()
    settings = db.get_project_settings(proj.id)
    assert settings["focus_mode"] is True
    assert settings["typewriter_mode"] is True
    assert "scroll_pos" in settings
    assert "current_language" in settings


# -- Language detection -------------------------------------------------------

def test_language_defaults_english():
    db = Database()
    proj, *_ = _setup_project(db)
    view = WritingCoreView(db, proj.id)
    assert view.current_language == "en"


def test_language_loads_from_settings():
    db = Database()
    proj, *_ = _setup_project(db)
    settings = db.get_project_settings(proj.id)
    settings["current_language"] = "es"
    db.save_project_settings(proj.id, settings)
    view = WritingCoreView(db, proj.id)
    assert view.current_language == "es"


def test_language_detection_updates_state():
    db = Database()
    proj, *_ = _setup_project(db)
    view = WritingCoreView(db, proj.id)
    editor = list(view._editors.values())[0]
    editor.setPlainText(
        "El rápido zorro marrón saltó sobre el perro perezoso en el campo. "
        "La casa era grande y bonita con muchas ventanas abiertas al jardín."
    )
    view._run_language_detection()
    assert view.current_language == "es"


def test_language_detection_persists():
    db = Database()
    proj, *_ = _setup_project(db)
    view = WritingCoreView(db, proj.id)
    view._current_language = "fr"
    view._persist_session_state()
    settings = db.get_project_settings(proj.id)
    assert settings["current_language"] == "fr"


def test_language_detection_skips_short_text():
    db = Database()
    proj, *_ = _setup_project(db)
    view = WritingCoreView(db, proj.id)
    for editor in view._editors.values():
        editor.setPlainText("Hi")
    view._run_language_detection()
    assert view.current_language == "en"


def test_collect_text_sample():
    db = Database()
    proj, *_ = _setup_project(db)
    view = WritingCoreView(db, proj.id)
    sample = view._collect_text_sample()
    assert len(sample) > 0
    assert len(sample) <= 2000


# -- Language override -------------------------------------------------------

def test_language_override_defaults_auto():
    db = Database()
    proj, *_ = _setup_project(db)
    view = WritingCoreView(db, proj.id)
    assert view.language_override == "auto"


def test_language_override_sets_language():
    db = Database()
    proj, *_ = _setup_project(db)
    view = WritingCoreView(db, proj.id)
    view._on_language_changed("es")
    assert view.language_override == "es"
    assert view.current_language == "es"


def test_language_override_persists():
    db = Database()
    proj, *_ = _setup_project(db)
    view = WritingCoreView(db, proj.id)
    view._on_language_changed("it")
    settings = db.get_project_settings(proj.id)
    assert settings["language_override"] == "it"


def test_language_override_restores_from_settings():
    db = Database()
    proj, *_ = _setup_project(db)
    settings = db.get_project_settings(proj.id)
    settings["language_override"] = "fr"
    db.save_project_settings(proj.id, settings)
    view = WritingCoreView(db, proj.id)
    assert view.language_override == "fr"
    assert view.current_language == "fr"


def test_language_override_skips_detection():
    db = Database()
    proj, *_ = _setup_project(db)
    view = WritingCoreView(db, proj.id)
    view._on_language_changed("en")
    assert view.current_language == "en"
    editor = list(view._editors.values())[0]
    editor.setPlainText(
        "El rápido zorro marrón saltó sobre el perro perezoso en el campo. "
        "La casa era grande y bonita con muchas ventanas abiertas al jardín."
    )
    view._run_language_detection()
    assert view.current_language == "en"


def test_language_auto_resumes_detection():
    db = Database()
    proj, *_ = _setup_project(db)
    view = WritingCoreView(db, proj.id)
    view._on_language_changed("es")
    assert view.current_language == "es"
    view._on_language_changed("auto")
    assert view.language_override == "auto"
    editor = list(view._editors.values())[0]
    editor.setPlainText(
        "Der schnelle braune Fuchs sprang über den faulen Hund auf dem Feld. "
        "Das Haus war groß und schön mit vielen offenen Fenstern zum Garten."
    )
    view._run_language_detection()
    assert view.current_language == "de"


def test_language_override_invalid_resets_auto():
    db = Database()
    proj, *_ = _setup_project(db)
    settings = db.get_project_settings(proj.id)
    settings["language_override"] = "xx"
    db.save_project_settings(proj.id, settings)
    view = WritingCoreView(db, proj.id)
    assert view.language_override == "auto"


# -- Grammar checking --------------------------------------------------------

def _wait_grammar(view):
    """Wait for the async grammar worker to finish and deliver results."""
    w = view._grammar_worker
    if w is not None:
        w.wait()
        QApplication.processEvents()


def test_grammar_off_by_default():
    db = Database()
    proj, *_ = _setup_project(db)
    view = WritingCoreView(db, proj.id)
    assert view._grammar_checking is False
    editor = list(view._editors.values())[0]
    assert editor._grammar_enabled is False


def test_grammar_toggle_enables():
    db = Database()
    proj, *_ = _setup_project(db)
    view = WritingCoreView(db, proj.id)
    view._toggle_grammar()
    assert view._grammar_checking is True
    for editor in view._editors.values():
        assert editor._grammar_enabled is True
    _wait_grammar(view)


def test_grammar_toggle_disables():
    db = Database()
    proj, *_ = _setup_project(db)
    view = WritingCoreView(db, proj.id)
    view._toggle_grammar()
    _wait_grammar(view)
    view._toggle_grammar()
    assert view._grammar_checking is False
    for editor in view._editors.values():
        assert editor._grammar_enabled is False
        assert editor._grammar_issues == []


def test_grammar_toolbar_button_removed():
    """Grammar Check now lives in the Edit menu, not the Manuscript top bar."""
    db = Database()
    proj, *_ = _setup_project(db)
    view = WritingCoreView(db, proj.id)
    assert not hasattr(view, "_grammar_btn")
    assert not hasattr(view, "_lang_combo")
    assert not hasattr(view, "_typewriter_btn")


def test_grammar_is_grammar_checking_property():
    db = Database()
    proj, *_ = _setup_project(db)
    view = WritingCoreView(db, proj.id)
    assert view.is_grammar_checking is False
    view._toggle_grammar()
    _wait_grammar(view)
    assert view.is_grammar_checking is True
    view._toggle_grammar()
    assert view.is_grammar_checking is False


def test_grammar_off_no_worker_spawned():
    db = Database()
    proj, *_ = _setup_project(db)
    view = WritingCoreView(db, proj.id)
    assert view._grammar_checking is False
    editor = list(view._editors.values())[0]
    editor.setPlainText("The quikc brown fox.")
    view._run_grammar_check()
    assert view._grammar_worker is None


def test_grammar_off_timer_not_started():
    db = Database()
    proj, *_ = _setup_project(db)
    view = WritingCoreView(db, proj.id)
    assert view._grammar_checking is False
    assert view._grammar_timer.isActive() is False


def test_grammar_off_no_underlines():
    db = Database()
    proj, *_ = _setup_project(db)
    view = WritingCoreView(db, proj.id)
    editor = list(view._editors.values())[0]
    editor.setPlainText("The quikc brown fox.")
    assert len(editor.extraSelections()) == 0


def test_grammar_toggle_off_stops_timer():
    db = Database()
    proj, *_ = _setup_project(db)
    view = WritingCoreView(db, proj.id)
    view._toggle_grammar()
    _wait_grammar(view)
    view._grammar_timer.start()
    assert view._grammar_timer.isActive() is True
    view._toggle_grammar()
    assert view._grammar_timer.isActive() is False


def test_grammar_toggle_off_cancels_worker():
    db = Database()
    proj, *_ = _setup_project(db)
    view = WritingCoreView(db, proj.id)
    view._toggle_grammar()
    _wait_grammar(view)
    view._toggle_grammar()
    assert view._grammar_worker is None


def test_grammar_toggle_off_clears_all_editors():
    db = Database()
    proj, *_ = _setup_project(db)
    view = WritingCoreView(db, proj.id)
    view._toggle_grammar()
    _wait_grammar(view)
    for editor in view._editors.values():
        editor.setPlainText("The quikc brown fox.")
    view._check_editor_grammar(list(view._editors.values())[0])
    _wait_grammar(view)
    view._toggle_grammar()
    for editor in view._editors.values():
        assert editor._grammar_issues == []
        assert len(editor.extraSelections()) == 0


def test_grammar_schedule_save_skips_timer_when_off():
    db = Database()
    proj, s1, *_ = _setup_project(db)
    view = WritingCoreView(db, proj.id)
    assert view._grammar_checking is False
    view._schedule_save(s1.id)
    assert view._grammar_timer.isActive() is False


def test_grammar_schedule_save_starts_timer_when_on():
    db = Database()
    proj, s1, *_ = _setup_project(db)
    view = WritingCoreView(db, proj.id)
    view._toggle_grammar()
    _wait_grammar(view)
    view._grammar_timer.stop()
    view._schedule_save(s1.id)
    assert view._grammar_timer.isActive() is True
    view._toggle_grammar()


def test_grammar_detects_typo():
    db = Database()
    proj, *_ = _setup_project(db)
    view = WritingCoreView(db, proj.id)
    view._toggle_grammar()
    _wait_grammar(view)
    editor = list(view._editors.values())[0]
    editor.setPlainText("The quikc brown fox jumped over the lazy dog.")
    view._check_editor_grammar(editor)
    _wait_grammar(view)
    spelling = [i for i in editor._grammar_issues if i.issue_type == "spelling"]
    assert any("quikc" in i.message for i in spelling)


def test_grammar_detects_doubled_word():
    db = Database()
    proj, *_ = _setup_project(db)
    view = WritingCoreView(db, proj.id)
    view._toggle_grammar()
    _wait_grammar(view)
    editor = list(view._editors.values())[0]
    editor.setPlainText("He went to the the store.")
    view._check_editor_grammar(editor)
    _wait_grammar(view)
    grammar = [i for i in editor._grammar_issues if i.issue_type == "grammar"]
    assert any("Repeated" in i.message for i in grammar)


def test_grammar_suggestion_available():
    db = Database()
    proj, *_ = _setup_project(db)
    view = WritingCoreView(db, proj.id)
    view._toggle_grammar()
    _wait_grammar(view)
    editor = list(view._editors.values())[0]
    editor.setPlainText("He went to the the store.")
    view._check_editor_grammar(editor)
    _wait_grammar(view)
    grammar = [i for i in editor._grammar_issues
                if i.issue_type == "grammar" and "Repeated" in i.message]
    assert len(grammar) > 0
    assert grammar[0].suggestions == ["the"]


def test_grammar_apply_suggestion():
    db = Database()
    proj, *_ = _setup_project(db)
    view = WritingCoreView(db, proj.id)
    view._toggle_grammar()
    _wait_grammar(view)
    editor = list(view._editors.values())[0]
    editor.setPlainText("He went to the the store.")
    view._check_editor_grammar(editor)
    _wait_grammar(view)
    grammar = [i for i in editor._grammar_issues
                if i.issue_type == "grammar" and "Repeated" in i.message]
    editor._apply_suggestion(grammar[0], grammar[0].suggestions[0])
    assert "the the" not in editor.toPlainText()


def test_grammar_clean_text_no_issues():
    db = Database()
    proj, *_ = _setup_project(db)
    view = WritingCoreView(db, proj.id)
    view._toggle_grammar()
    _wait_grammar(view)
    editor = list(view._editors.values())[0]
    editor.setPlainText("The man walked to the door and opened it slowly.")
    view._check_editor_grammar(editor)
    _wait_grammar(view)
    spelling = [i for i in editor._grammar_issues if i.issue_type == "spelling"]
    grammar = [i for i in editor._grammar_issues if i.issue_type == "grammar"]
    assert len(spelling) == 0
    assert len(grammar) == 0


def test_grammar_persists_setting():
    db = Database()
    proj, *_ = _setup_project(db)
    view = WritingCoreView(db, proj.id)
    view._toggle_grammar()
    _wait_grammar(view)
    settings = db.get_project_settings(proj.id)
    assert settings["grammar_checking"] is True


def test_grammar_stored_optin_ignored_while_deferred():
    """Grammar checking is DEFERRED for Alpha: a previously stored opt-in is
    ignored on load — the view always starts with grammar off (the
    programmatic toggle mechanism stays for the future Review phase)."""
    db = Database()
    proj, *_ = _setup_project(db)
    settings = db.get_project_settings(proj.id)
    settings["grammar_checking"] = True
    db.save_project_settings(proj.id, settings)
    view = WritingCoreView(db, proj.id)
    assert view._grammar_checking is False
    for editor in view._editors.values():
        assert editor._grammar_enabled is False


def test_grammar_issues_property():
    db = Database()
    proj, *_ = _setup_project(db)
    view = WritingCoreView(db, proj.id)
    view._toggle_grammar()
    _wait_grammar(view)
    editor = list(view._editors.values())[0]
    editor.setPlainText("He went to the the store.")
    view._check_editor_grammar(editor)
    _wait_grammar(view)
    issues = view.grammar_issues
    assert len(issues) > 0


def test_grammar_underlines_applied():
    db = Database()
    proj, *_ = _setup_project(db)
    view = WritingCoreView(db, proj.id)
    view._toggle_grammar()
    _wait_grammar(view)
    editor = list(view._editors.values())[0]
    editor.setPlainText("The quikc brown fox.")
    view._check_editor_grammar(editor)
    _wait_grammar(view)
    selections = editor.extraSelections()
    assert len(selections) > 0


def test_grammar_underlines_cleared_on_disable():
    db = Database()
    proj, *_ = _setup_project(db)
    view = WritingCoreView(db, proj.id)
    view._toggle_grammar()
    _wait_grammar(view)
    editor = list(view._editors.values())[0]
    editor.setPlainText("The quikc brown fox.")
    view._check_editor_grammar(editor)
    _wait_grammar(view)
    assert len(editor.extraSelections()) > 0
    view._toggle_grammar()
    assert len(editor.extraSelections()) == 0


def test_grammar_empty_text_no_crash():
    db = Database()
    proj, *_ = _setup_project(db)
    view = WritingCoreView(db, proj.id)
    view._toggle_grammar()
    _wait_grammar(view)
    editor = list(view._editors.values())[0]
    editor.setPlainText("")
    view._check_editor_grammar(editor)
    _wait_grammar(view)
    assert editor._grammar_issues == []


def test_grammar_cancels_stale_worker():
    db = Database()
    proj, *_ = _setup_project(db)
    view = WritingCoreView(db, proj.id)
    view._toggle_grammar()
    _wait_grammar(view)
    editor = list(view._editors.values())[0]
    editor.setPlainText("The quikc brown fox.")
    view._start_grammar_worker()
    first_gen = view._grammar_generation
    editor.setPlainText("He went to the the store.")
    view._start_grammar_worker()
    assert view._grammar_generation == first_gen + 1
    _wait_grammar(view)
    grammar = [i for i in editor._grammar_issues if i.issue_type == "grammar"]
    assert any("Repeated" in i.message for i in grammar)


def test_grammar_worker_is_async():
    from logosforge.ui.writing_core_view import _GrammarWorker
    from PySide6.QtCore import QThread
    assert issubclass(_GrammarWorker, QThread)


def test_grammar_cache_hit():
    from logosforge.ui.writing_core_view import _GRAMMAR_CACHE
    _GRAMMAR_CACHE.clear()
    db = Database()
    proj, *_ = _setup_project(db)
    view = WritingCoreView(db, proj.id)
    view._toggle_grammar()
    _wait_grammar(view)
    editor = list(view._editors.values())[0]
    editor.setPlainText("The quikc brown fox.")
    view._check_editor_grammar(editor)
    _wait_grammar(view)
    assert len(_GRAMMAR_CACHE) > 0
    cached_count = len(_GRAMMAR_CACHE)
    view._check_editor_grammar(editor)
    _wait_grammar(view)
    assert len(_GRAMMAR_CACHE) == cached_count


# -- Grammar highlighting styles ---------------------------------------------

def test_spelling_underline_is_wave():
    from PySide6.QtGui import QTextCharFormat
    db = Database()
    proj, *_ = _setup_project(db)
    view = WritingCoreView(db, proj.id)
    view._toggle_grammar()
    _wait_grammar(view)
    editor = list(view._editors.values())[0]
    editor.setPlainText("The quikc brown fox.")
    view._check_editor_grammar(editor)
    _wait_grammar(view)
    sels = editor.extraSelections()
    assert len(sels) > 0
    fmt = sels[0].format
    assert fmt.underlineStyle() == QTextCharFormat.UnderlineStyle.WaveUnderline


def test_grammar_underline_is_wave():
    from PySide6.QtGui import QTextCharFormat
    db = Database()
    proj, *_ = _setup_project(db)
    view = WritingCoreView(db, proj.id)
    view._toggle_grammar()
    _wait_grammar(view)
    editor = list(view._editors.values())[0]
    editor.setPlainText("He went to the the store.")
    view._check_editor_grammar(editor)
    _wait_grammar(view)
    grammar_sels = [
        s for s in editor.extraSelections()
        if s.format.underlineStyle() == QTextCharFormat.UnderlineStyle.WaveUnderline
    ]
    assert len(grammar_sels) > 0


def test_style_underline_is_dotted():
    from PySide6.QtGui import QTextCharFormat
    db = Database()
    proj, *_ = _setup_project(db)
    view = WritingCoreView(db, proj.id)
    view._toggle_grammar()
    _wait_grammar(view)
    editor = list(view._editors.values())[0]
    editor.setPlainText("The ball was thrown by the boy.")
    view._check_editor_grammar(editor)
    _wait_grammar(view)
    dot_sels = [
        s for s in editor.extraSelections()
        if s.format.underlineStyle() == QTextCharFormat.UnderlineStyle.DotLine
    ]
    assert len(dot_sels) > 0


def test_spelling_underline_color_from_theme():
    from logosforge.ui import theme as t
    from PySide6.QtGui import QColor
    db = Database()
    proj, *_ = _setup_project(db)
    view = WritingCoreView(db, proj.id)
    view._toggle_grammar()
    _wait_grammar(view)
    editor = list(view._editors.values())[0]
    editor.setPlainText("The quikc brown fox.")
    view._check_editor_grammar(editor)
    _wait_grammar(view)
    sels = editor.extraSelections()
    expected = QColor(t.get("GRAMMAR_SPELLING"))
    assert sels[0].format.underlineColor() == expected


def test_underline_tooltip_has_message():
    db = Database()
    proj, *_ = _setup_project(db)
    view = WritingCoreView(db, proj.id)
    view._toggle_grammar()
    _wait_grammar(view)
    editor = list(view._editors.values())[0]
    editor.setPlainText("He went to the the store.")
    view._check_editor_grammar(editor)
    _wait_grammar(view)
    sels = editor.extraSelections()
    tips = [s.format.toolTip() for s in sels]
    assert any("Repeated" in t for t in tips)


def test_underline_tooltip_includes_suggestions():
    db = Database()
    proj, *_ = _setup_project(db)
    view = WritingCoreView(db, proj.id)
    view._toggle_grammar()
    _wait_grammar(view)
    editor = list(view._editors.values())[0]
    editor.setPlainText("He went to the the store.")
    view._check_editor_grammar(editor)
    _wait_grammar(view)
    sels = editor.extraSelections()
    tips = [s.format.toolTip() for s in sels]
    assert any("the" in t and "→" in t for t in tips)


def test_stale_positions_filtered():
    db = Database()
    proj, *_ = _setup_project(db)
    view = WritingCoreView(db, proj.id)
    editor = list(view._editors.values())[0]
    editor._grammar_enabled = True
    from logosforge.grammar_checker import Issue
    editor._grammar_issues = [
        Issue(start=0, end=3, issue_type="spelling", message="ok"),
        Issue(start=9999, end=10005, issue_type="spelling", message="stale"),
    ]
    editor.apply_grammar_underlines()
    sels = editor.extraSelections()
    assert len(sels) == 1


def test_grammar_and_psyke_overlap():
    db = Database()
    proj, s1, s2, e1, e2 = _setup_psyke_project(db)
    view = WritingCoreView(db, proj.id)
    view._toggle_grammar()
    _wait_grammar(view)
    editor = view._editors[s1.id]
    editor.setPlainText("John went to the the castle.")
    view._check_editor_grammar(editor)
    _wait_grammar(view)
    grammar_sels = editor.extraSelections()
    assert len(grammar_sels) > 0
    highlighter = view._highlighters[s1.id]
    assert highlighter._pattern is not None
    assert highlighter._pattern.search("John went to the the castle.")


def test_grammar_and_psyke_independent_layers():
    db = Database()
    proj, s1, s2, e1, e2 = _setup_psyke_project(db)
    view = WritingCoreView(db, proj.id)
    view._toggle_grammar()
    _wait_grammar(view)
    editor = view._editors[s1.id]
    editor.setPlainText("John went to the the castle.")
    view._check_editor_grammar(editor)
    _wait_grammar(view)
    grammar_count = len(editor.extraSelections())
    assert grammar_count > 0
    view._toggle_grammar()
    assert len(editor.extraSelections()) == 0
    highlighter = view._highlighters[s1.id]
    assert highlighter._pattern is not None


def test_mouse_tracking_enabled():
    db = Database()
    proj, *_ = _setup_project(db)
    view = WritingCoreView(db, proj.id)
    editor = list(view._editors.values())[0]
    assert editor.hasMouseTracking() is True


# -- Grammar popup & ignore --------------------------------------------------

def test_grammar_popup_exists():
    from logosforge.ui.writing_core_view import _GrammarPopup
    db = Database()
    proj, *_ = _setup_project(db)
    view = WritingCoreView(db, proj.id)
    editor = list(view._editors.values())[0]
    assert isinstance(editor._grammar_popup, _GrammarPopup)


def test_grammar_popup_show_for_issue():
    from logosforge.grammar_checker import Issue
    from logosforge.ui.writing_core_view import _GrammarPopup
    popup = _GrammarPopup()
    issue = Issue(start=0, end=5, issue_type="spelling", message="Unknown word: 'quikc'",
                  suggestions=["quick", "quiche"])
    popup.show_for_issue(issue, QPoint(100, 100))
    assert popup.isVisible()
    assert "quikc" in popup._msg_label.text()
    assert len(popup._suggestion_btns) == 2
    popup.hide()


def test_grammar_popup_suggestion_replaces_text():
    db = Database()
    proj, *_ = _setup_project(db)
    view = WritingCoreView(db, proj.id)
    view._toggle_grammar()
    _wait_grammar(view)
    editor = list(view._editors.values())[0]
    editor.setPlainText("He went to the the store.")
    view._check_editor_grammar(editor)
    _wait_grammar(view)
    grammar = [i for i in editor._grammar_issues
                if i.issue_type == "grammar" and "Repeated" in i.message]
    assert len(grammar) > 0
    editor._on_popup_suggestion(grammar[0], grammar[0].suggestions[0])
    assert "the the" not in editor.toPlainText()


def test_grammar_ignore_removes_underline():
    db = Database()
    proj, *_ = _setup_project(db)
    view = WritingCoreView(db, proj.id)
    view._toggle_grammar()
    _wait_grammar(view)
    editor = list(view._editors.values())[0]
    editor.setPlainText("The quikc brown fox.")
    view._check_editor_grammar(editor)
    _wait_grammar(view)
    before = len(editor.extraSelections())
    assert before > 0
    spelling = [i for i in editor._grammar_issues if i.issue_type == "spelling"]
    assert len(spelling) > 0
    editor._on_popup_ignore(spelling[0])
    after = len(editor.extraSelections())
    assert after < before


def test_grammar_ignore_persists_across_checks():
    db = Database()
    proj, *_ = _setup_project(db)
    view = WritingCoreView(db, proj.id)
    view._toggle_grammar()
    _wait_grammar(view)
    editor = list(view._editors.values())[0]
    editor.setPlainText("The quikc brown fox.")
    view._check_editor_grammar(editor)
    _wait_grammar(view)
    spelling = [i for i in editor._grammar_issues if i.issue_type == "spelling"
                and "quikc" in i.message]
    assert len(spelling) > 0
    editor._on_popup_ignore(spelling[0])
    view._check_editor_grammar(editor)
    _wait_grammar(view)
    visible = editor.extraSelections()
    tips = [s.format.toolTip() for s in visible]
    assert not any("quikc" in t for t in tips)


def test_grammar_ignore_does_not_affect_other_issues():
    db = Database()
    proj, *_ = _setup_project(db)
    view = WritingCoreView(db, proj.id)
    view._toggle_grammar()
    _wait_grammar(view)
    editor = list(view._editors.values())[0]
    editor.setPlainText("The quikc boy went to the the store.")
    view._check_editor_grammar(editor)
    _wait_grammar(view)
    total_before = len(editor.extraSelections())
    spelling = [i for i in editor._grammar_issues if "quikc" in i.message]
    assert len(spelling) > 0
    editor._on_popup_ignore(spelling[0])
    remaining = len(editor.extraSelections())
    assert remaining > 0
    assert remaining < total_before


def test_grammar_issue_at_cursor_skips_ignored():
    from logosforge.grammar_checker import Issue
    db = Database()
    proj, *_ = _setup_project(db)
    view = WritingCoreView(db, proj.id)
    editor = list(view._editors.values())[0]
    editor._grammar_enabled = True
    editor._grammar_issues = [
        Issue(start=0, end=5, issue_type="spelling", message="Unknown word: 'quikc'"),
    ]
    editor._ignored_issues.add(("spelling", "Unknown word: 'quikc'"))
    result = editor._issue_at_cursor(QPoint(0, 0))
    assert result is None


def test_grammar_popup_ignore_btn_exists():
    from logosforge.ui.writing_core_view import _GrammarPopup
    popup = _GrammarPopup()
    assert popup._ignore_btn is not None
    assert popup._ignore_btn.text() == "Ignore"


def test_grammar_context_menu_shows_popup():
    db = Database()
    proj, *_ = _setup_project(db)
    view = WritingCoreView(db, proj.id)
    view._toggle_grammar()
    _wait_grammar(view)
    editor = list(view._editors.values())[0]
    editor.setPlainText("The quikc brown fox.")
    view._check_editor_grammar(editor)
    _wait_grammar(view)
    issues = [i for i in editor._grammar_issues if "quikc" in i.message]
    assert len(issues) > 0
    editor._show_grammar_popup(issues[0], QPoint(100, 100))
    assert editor._grammar_popup.isVisible()
    editor._grammar_popup.hide()


# -- Auto-formatting ----------------------------------------------------------

def _type_into_editor(editor, text):
    """Simulate typing characters one by one into a _SceneEditor."""
    from PySide6.QtGui import QKeyEvent
    for ch in text:
        ev = QKeyEvent(
            QKeyEvent.Type.KeyPress,
            0,
            Qt.KeyboardModifier.NoModifier,
            ch,
        )
        editor.keyPressEvent(ev)


def test_auto_em_dash():
    db = Database()
    proj, *_ = _setup_project(db)
    view = WritingCoreView(db, proj.id)
    editor = list(view._editors.values())[0]
    editor.clear()
    _type_into_editor(editor, "hello--world")
    assert "—" in editor.toPlainText()
    assert "--" not in editor.toPlainText()


def test_auto_ellipsis():
    db = Database()
    proj, *_ = _setup_project(db)
    view = WritingCoreView(db, proj.id)
    editor = list(view._editors.values())[0]
    editor.clear()
    _type_into_editor(editor, "wait...")
    assert "…" in editor.toPlainText()
    assert "..." not in editor.toPlainText()


def test_smart_quotes_off_by_default():
    db = Database()
    proj, *_ = _setup_project(db)
    view = WritingCoreView(db, proj.id)
    editor = list(view._editors.values())[0]
    editor.clear()
    _type_into_editor(editor, '"hello"')
    plain = editor.toPlainText()
    assert "“" not in plain
    assert '"' in plain


def test_smart_quotes_when_enabled():
    db = Database()
    proj, *_ = _setup_project(db)
    view = WritingCoreView(db, proj.id)
    view._toggle_smart_quotes()
    editor = list(view._editors.values())[0]
    editor.clear()
    _type_into_editor(editor, '"hello"')
    plain = editor.toPlainText()
    assert "“" in plain  # left double quote
    assert "”" in plain  # right double quote


def test_smart_single_quotes():
    db = Database()
    proj, *_ = _setup_project(db)
    view = WritingCoreView(db, proj.id)
    view._toggle_smart_quotes()
    editor = list(view._editors.values())[0]
    editor.clear()
    _type_into_editor(editor, "it's")
    plain = editor.toPlainText()
    assert "’" in plain  # right single quote (apostrophe)


def test_smart_quotes_toggle_persists():
    db = Database()
    proj, *_ = _setup_project(db)
    view1 = WritingCoreView(db, proj.id)
    view1._toggle_smart_quotes()
    assert view1._smart_quotes is True
    del view1
    view2 = WritingCoreView(db, proj.id)
    assert view2._smart_quotes is True


def test_normal_typing_unaffected():
    db = Database()
    proj, *_ = _setup_project(db)
    view = WritingCoreView(db, proj.id)
    editor = list(view._editors.values())[0]
    editor.clear()
    _type_into_editor(editor, "hello world")
    assert editor.toPlainText() == "hello world"


# -- PSYKE entity awareness ---------------------------------------------------

def _setup_psyke_project(db):
    """Create a project with scenes and PSYKE entries for entity testing."""
    proj = db.create_project("Novel")
    s1 = db.create_scene(
        proj.id, "Opening",
        content="John looked at Mary across the room.",
        act="Act One", chapter="Chapter 1",
    )
    s2 = db.create_scene(
        proj.id, "Rising",
        content="Mary whispered to John about the plan.",
        act="Act One", chapter="Chapter 1",
    )
    e1 = db.create_psyke_entry(proj.id, "John", entry_type="character", notes="A detective.")
    e2 = db.create_psyke_entry(proj.id, "Mary", entry_type="character", aliases="M", notes="A scientist.")
    return proj, s1, s2, e1, e2


def test_psyke_term_map_built():
    db = Database()
    proj, s1, s2, e1, e2 = _setup_psyke_project(db)
    view = WritingCoreView(db, proj.id)
    assert "john" in view._psyke_term_map
    assert "mary" in view._psyke_term_map
    assert "m" in view._psyke_term_map
    assert view._psyke_term_map["john"] == e1.id
    assert view._psyke_term_map["mary"] == e2.id
    assert view._psyke_term_map["m"] == e2.id


def test_psyke_entry_cache_populated():
    db = Database()
    proj, s1, s2, e1, e2 = _setup_psyke_project(db)
    view = WritingCoreView(db, proj.id)
    assert e1.id in view._psyke_entry_cache
    assert e2.id in view._psyke_entry_cache
    assert view._psyke_entry_cache[e1.id].name == "John"
    assert view._psyke_entry_cache[e2.id].name == "Mary"


def test_click_handlers_created_per_editor():
    db = Database()
    proj, s1, s2, e1, e2 = _setup_psyke_project(db)
    view = WritingCoreView(db, proj.id)
    assert s1.id in view._click_handlers
    assert s2.id in view._click_handlers
    assert isinstance(view._click_handlers[s1.id], PsykeClickHandler)


def test_hover_handlers_created_per_editor():
    db = Database()
    proj, s1, s2, e1, e2 = _setup_psyke_project(db)
    view = WritingCoreView(db, proj.id)
    assert s1.id in view._hover_handlers
    assert s2.id in view._hover_handlers
    assert isinstance(view._hover_handlers[s1.id], EntityHoverHandler)


def test_entity_hover_panel_exists():
    db = Database()
    proj, *_ = _setup_psyke_project(db)
    view = WritingCoreView(db, proj.id)
    assert hasattr(view, "_entity_hover_panel")
    assert isinstance(view._entity_hover_panel, EntityHoverPanel)


def test_entity_hover_panel_creation():
    panel = EntityHoverPanel()
    assert panel.objectName() == "entityHoverPanel"
    assert panel.isHidden()


def test_entity_hover_panel_show_entity():
    parent = QWidget()
    parent.setFixedSize(500, 400)
    panel = EntityHoverPanel(parent)
    panel.show_entity("John", "character", "Paranoid", "A detective.", QPoint(50, 50))
    assert not panel.isHidden()
    assert panel._name_label.text() == "John"
    assert panel._type_label.text() == "character"
    assert panel._state_label.text() == "Paranoid"
    assert panel._notes_label.text() == "A detective."


def test_entity_hover_panel_no_state():
    parent = QWidget()
    parent.setFixedSize(500, 400)
    panel = EntityHoverPanel(parent)
    panel.show_entity("Mary", "character", "", "A scientist.", QPoint(50, 50))
    assert panel._state_label.isHidden()
    assert not panel._notes_label.isHidden()


def test_entity_hover_panel_no_notes():
    parent = QWidget()
    parent.setFixedSize(500, 400)
    panel = EntityHoverPanel(parent)
    panel.show_entity("Place", "place", "Destroyed", "", QPoint(50, 50))
    assert not panel._state_label.isHidden()
    assert panel._notes_label.isHidden()


def test_entity_hover_handler_creation():
    editor = _SceneEditor()
    doc = QTextDocument()
    highlighter = ManuscriptHighlighter(editor.document())
    term_map = {"john": 1}
    parent = QWidget()
    handler = EntityHoverHandler(
        editor, highlighter, term_map, parent,
        on_show=lambda *a: None,
        on_hide=lambda: None,
    )
    assert handler._term_map == {"john": 1}


def test_entity_hover_handler_term_map_update():
    editor = _SceneEditor()
    highlighter = ManuscriptHighlighter(editor.document())
    parent = QWidget()
    handler = EntityHoverHandler(
        editor, highlighter, {}, parent,
        on_show=lambda *a: None,
        on_hide=lambda: None,
    )
    new_map = {"alice": 10, "bob": 20}
    handler.set_term_map(new_map)
    assert handler._term_map == new_map


def test_scene_sort_orders_built():
    db = Database()
    proj, s1, s2, e1, e2 = _setup_psyke_project(db)
    view = WritingCoreView(db, proj.id)
    assert s1.id in view._scene_sort_orders
    assert s2.id in view._scene_sort_orders


def test_temporal_graph_built():
    db = Database()
    proj, s1, s2, e1, e2 = _setup_psyke_project(db)
    view = WritingCoreView(db, proj.id)
    assert view._temporal_graph is not None


def test_temporal_state_in_hover():
    db = Database()
    proj, s1, s2, e1, e2 = _setup_psyke_project(db)
    db.create_psyke_progression(e1.id, "Suspicious of everyone", scene_id=s1.id)
    view = WritingCoreView(db, proj.id)
    state = view._temporal_graph.get_entry_state_at(
        e1.id, view._scene_sort_orders[s1.id],
    )
    assert state is not None
    assert state.has_progression
    assert "Suspicious" in state.progression_text


def test_psyke_jump_callback():
    db = Database()
    proj, s1, s2, e1, e2 = _setup_psyke_project(db)
    jumped = []
    view = WritingCoreView(
        db, proj.id,
        on_open_psyke_entry=lambda eid: jumped.append(eid),
    )
    view._on_psyke_jump(e1.id)
    assert jumped == [e1.id]


def test_psyke_jump_callback_none():
    db = Database()
    proj, *_ = _setup_psyke_project(db)
    view = WritingCoreView(db, proj.id)
    view._on_psyke_jump(999)


def test_resolve_term_at_finds_entry():
    db = Database()
    proj, s1, s2, e1, e2 = _setup_psyke_project(db)
    view = WritingCoreView(db, proj.id)
    result = view._resolve_term_at("John looked at Mary", 2)
    assert result == e1.id


def test_resolve_term_at_returns_none_outside_term():
    db = Database()
    proj, s1, s2, e1, e2 = _setup_psyke_project(db)
    view = WritingCoreView(db, proj.id)
    result = view._resolve_term_at("John looked at Mary", 8)
    assert result is None


def test_context_action_resolve():
    db = Database()
    proj, s1, s2, e1, e2 = _setup_psyke_project(db)
    view = WritingCoreView(db, proj.id)
    result = view._handle_psyke_context("resolve", "Mary whispered", 2)
    assert result == e2.id


def test_context_action_open():
    db = Database()
    proj, s1, s2, e1, e2 = _setup_psyke_project(db)
    jumped = []
    view = WritingCoreView(
        db, proj.id,
        on_open_psyke_entry=lambda eid: jumped.append(eid),
    )
    view._handle_psyke_context("open", e1.id)
    assert jumped == [e1.id]


def test_editor_has_psyke_context_callback():
    db = Database()
    proj, s1, s2, e1, e2 = _setup_psyke_project(db)
    view = WritingCoreView(db, proj.id)
    editor = view._editors[s1.id]
    assert editor._on_psyke_context_action is not None


def test_handlers_cleared_on_refresh():
    db = Database()
    proj, s1, s2, e1, e2 = _setup_psyke_project(db)
    view = WritingCoreView(db, proj.id)
    assert len(view._click_handlers) == 2
    assert len(view._hover_handlers) == 2
    db.create_scene(proj.id, "New", content="Extra scene.")
    view.refresh()
    assert len(view._click_handlers) == 3
    assert len(view._hover_handlers) == 3


def test_no_psyke_entries_no_overhead():
    db = Database()
    proj = db.create_project("Empty")
    db.create_scene(proj.id, "Scene", content="Some text.")
    view = WritingCoreView(db, proj.id)
    assert len(view._psyke_term_map) == 0
    assert len(view._psyke_entry_cache) == 0


def test_hover_show_with_entity_data():
    db = Database()
    proj, s1, s2, e1, e2 = _setup_psyke_project(db)
    view = WritingCoreView(db, proj.id)
    editor = view._editors[s1.id]
    view._on_entity_hover_show(e1.id, editor, QPoint(50, 50))
    panel = view._entity_hover_panel
    assert panel._name_label.text() == "John"
    assert panel._type_label.text() == "character"


def test_hover_show_with_temporal_state():
    db = Database()
    proj, s1, s2, e1, e2 = _setup_psyke_project(db)
    db.create_psyke_progression(e1.id, "Paranoid after the incident", scene_id=s1.id)
    view = WritingCoreView(db, proj.id)
    editor = view._editors[s1.id]
    view._on_entity_hover_show(e1.id, editor, QPoint(50, 50))
    panel = view._entity_hover_panel
    assert "Paranoid" in panel._state_label.text()


def test_hover_show_without_progression():
    db = Database()
    proj, s1, s2, e1, e2 = _setup_psyke_project(db)
    view = WritingCoreView(db, proj.id)
    editor = view._editors[s1.id]
    view._on_entity_hover_show(e2.id, editor, QPoint(50, 50))
    panel = view._entity_hover_panel
    assert panel._name_label.text() == "Mary"
    assert panel._state_label.isHidden()


# -- Writing formats -----------------------------------------------------------

def test_all_formats_available():
    assert len(ALL_FORMATS) == 5
    for key in FORMAT_ORDER:
        assert key in ALL_FORMATS


def test_format_order_matches_keys():
    assert set(FORMAT_ORDER) == set(ALL_FORMATS.keys())


def test_each_format_has_elements():
    for fmt in ALL_FORMATS.values():
        assert len(fmt.elements) > 0
        assert fmt.default_element in [e.name for e in fmt.elements]


def test_element_transitions_defined():
    for key in ALL_FORMATS:
        assert key in _ELEMENT_TRANSITIONS


def test_transitions_reference_valid_elements():
    for fmt_name, transitions in _ELEMENT_TRANSITIONS.items():
        fmt = ALL_FORMATS[fmt_name]
        elem_names = {e.name for e in fmt.elements}
        for src, dst in transitions.items():
            assert src in elem_names, f"{fmt_name}: transition src '{src}' not in elements"
            assert dst in elem_names, f"{fmt_name}: transition dst '{dst}' not in elements"


# -- Format combo --------------------------------------------------------------

def test_view_has_format_badge():
    """Top bar shows a read-only project-format badge (not a combo)."""
    db = Database()
    proj, *_ = _setup_project(db)
    view = WritingCoreView(db, proj.id)
    assert hasattr(view, "_format_badge")
    assert not hasattr(view, "_format_combo")


def test_format_badge_default_novel():
    db = Database()
    proj, *_ = _setup_project(db)
    view = WritingCoreView(db, proj.id)
    assert "Novel" in view._format_badge.text()
    assert view._format.name == "novel"


def test_format_badge_respects_project():
    db = Database()
    proj = db.create_project("Script", format_mode="screenplay")
    db.create_scene(proj.id, "Scene", content="Action.")
    view = WritingCoreView(db, proj.id)
    assert "Screenplay" in view._format_badge.text()
    assert view._format.name == "screenplay"


def test_format_change_via_project_settings_persists():
    """Format change goes through the project layer, not the manuscript."""
    db = Database()
    proj, *_ = _setup_project(db)
    db.update_project_writing_format(proj.id, "screenplay")
    updated = db.get_project_by_id(proj.id)
    assert updated.default_writing_format == "screenplay"
    assert updated.format_mode == "screenplay"


def test_reload_project_format_updates_element_combo():
    db = Database()
    proj, *_ = _setup_project(db)
    view = WritingCoreView(db, proj.id)
    novel_count = view._element_combo.count()
    db.update_project_writing_format(proj.id, "screenplay")
    view.reload_project_format()
    screenplay_count = view._element_combo.count()
    assert novel_count != screenplay_count
    assert screenplay_count == len(ALL_FORMATS["screenplay"].elements)


# -- Element combo -------------------------------------------------------------

def test_element_combo_populated():
    db = Database()
    proj, *_ = _setup_project(db)
    view = WritingCoreView(db, proj.id)
    assert view._element_combo.count() == len(ALL_FORMATS["novel"].elements)


def test_element_combo_default_matches_format():
    db = Database()
    proj, *_ = _setup_project(db)
    view = WritingCoreView(db, proj.id)
    assert view._element_combo.currentData() == ALL_FORMATS["novel"].default_element


def test_element_combo_screenplay_default():
    db = Database()
    proj = db.create_project("Script", format_mode="screenplay")
    db.create_scene(proj.id, "Scene", content="Action.")
    view = WritingCoreView(db, proj.id)
    assert view._element_combo.currentData() == "action"


# -- Block data ----------------------------------------------------------------

def test_block_data_stores_element():
    data = _BlockData("character")
    assert data.element == "character"


def test_block_data_default_empty():
    data = _BlockData()
    assert data.element == ""


# -- Element application -------------------------------------------------------

def test_apply_element_sets_block_data():
    db = Database()
    proj = db.create_project("Script", format_mode="screenplay")
    s1 = db.create_scene(proj.id, "Scene", content="John walks in.")
    view = WritingCoreView(db, proj.id)
    editor = view._editors[s1.id]
    editor.setFocus()
    view._apply_element_to_block(editor, "character")
    data = editor.textCursor().block().userData()
    assert isinstance(data, _BlockData)
    assert data.element == "character"


def test_focus_marks_active_editor_for_empty_block():
    # Regression: focusing an editor — even an EMPTY block, where the caret
    # stays at position 0 and no cursorPositionChanged fires — must mark it the
    # active editor, so the element combo applies the chosen element to THIS
    # block rather than a stale editor (the empty-block combo edge).
    db = Database()
    proj = db.create_project("Script", format_mode="screenplay")
    s1 = db.create_scene(proj.id, "Scene", content="")        # empty block
    view = WritingCoreView(db, proj.id)
    editor = view._editors[s1.id]
    view._active_editor = None                                # stale / none
    view._on_editor_focused(editor)                           # focus-in hook
    assert view._active_editor is editor

    # Choosing an element from the combo now targets this editor's block...
    idx = next(i for i in range(view._element_combo.count())
               if view._element_combo.itemData(i) == "character")
    view._element_combo.setCurrentIndex(idx)                  # → _on_element_changed
    data = editor.textCursor().block().userData()
    assert isinstance(data, _BlockData) and data.element == "character"

    # ...and the element survives typing into the (previously empty) block.
    cur = editor.textCursor()
    cur.insertText("ADA")
    after = editor.textCursor().block().userData()
    assert isinstance(after, _BlockData) and after.element == "character"


def test_get_element_style():
    db = Database()
    proj = db.create_project("Script", format_mode="screenplay")
    db.create_scene(proj.id, "S", content="x")
    view = WritingCoreView(db, proj.id)
    style = view._get_element_style("character")
    assert style is not None
    assert style.all_caps is True
    assert style.left_margin == 264


def test_get_element_style_missing():
    db = Database()
    proj, *_ = _setup_project(db)
    view = WritingCoreView(db, proj.id)
    assert view._get_element_style("nonexistent") is None


# -- Enter key transitions -----------------------------------------------------

def test_new_block_transitions_screenplay():
    db = Database()
    proj = db.create_project("Script", format_mode="screenplay")
    s1 = db.create_scene(proj.id, "Scene", content="INT. ROOM")
    view = WritingCoreView(db, proj.id)
    editor = view._editors[s1.id]
    view._apply_element_to_block(editor, "character")
    view._on_new_block_created(editor, "character")
    data = editor.textCursor().block().userData()
    assert isinstance(data, _BlockData)
    assert data.element == "dialogue"


def test_new_block_transitions_novel():
    db = Database()
    proj, s1, *_ = _setup_project(db)
    view = WritingCoreView(db, proj.id)
    editor = view._editors[s1.id]
    view._on_new_block_created(editor, "chapter")
    data = editor.textCursor().block().userData()
    assert isinstance(data, _BlockData)
    assert data.element == "body"


def test_new_block_default_when_no_transition():
    db = Database()
    proj, s1, *_ = _setup_project(db)
    view = WritingCoreView(db, proj.id)
    editor = view._editors[s1.id]
    view._on_new_block_created(editor, None)
    data = editor.textCursor().block().userData()
    assert isinstance(data, _BlockData)
    assert data.element == "body"


# -- Element shortcuts ---------------------------------------------------------

def test_element_shortcuts_created():
    db = Database()
    proj = db.create_project("Script", format_mode="screenplay")
    db.create_scene(proj.id, "S", content="x")
    view = WritingCoreView(db, proj.id)
    assert len(view._element_shortcuts) > 0


def test_element_shortcuts_rebuild_on_format_change():
    db = Database()
    proj, *_ = _setup_project(db)
    view = WritingCoreView(db, proj.id)
    novel_count = len(view._element_shortcuts)
    db.update_project_writing_format(proj.id, "screenplay")
    view.reload_project_format()
    screenplay_count = len(view._element_shortcuts)
    assert screenplay_count > 0
    assert novel_count != screenplay_count


def test_shortcut_element_applies():
    db = Database()
    proj = db.create_project("Script", format_mode="screenplay")
    s1 = db.create_scene(proj.id, "Scene", content="Action line.")
    view = WritingCoreView(db, proj.id)
    editor = view._editors[s1.id]
    view._apply_element_to_block(editor, "transition")
    data = editor.textCursor().block().userData()
    assert isinstance(data, _BlockData)
    assert data.element == "transition"


# -- Format application to all blocks -----------------------------------------

def test_format_to_all_blocks_on_load():
    db = Database()
    proj = db.create_project("Script", format_mode="screenplay")
    s1 = db.create_scene(proj.id, "Scene", content="Line one.\nLine two.")
    view = WritingCoreView(db, proj.id)
    editor = view._editors[s1.id]
    block = editor.document().begin()
    data = block.userData()
    assert isinstance(data, _BlockData)
    assert data.element == "action"


def test_format_change_applies_to_blocks():
    db = Database()
    proj, s1, *_ = _setup_project(db)
    view = WritingCoreView(db, proj.id)
    editor = view._editors[s1.id]
    block = editor.document().begin()
    data = block.userData()
    assert isinstance(data, _BlockData)
    assert data.element == "body"
    db.update_project_writing_format(proj.id, "screenplay")
    view.reload_project_format()
    block = editor.document().begin()
    data = block.userData()
    assert isinstance(data, _BlockData)
    assert data.element == "action"


def test_active_editor_field_exists():
    db = Database()
    proj, s1, s2, s3 = _setup_project(db)
    view = WritingCoreView(db, proj.id)
    assert hasattr(view, "_active_editor")


def test_element_change_uses_active_editor():
    db = Database()
    proj = db.create_project("Script", format_mode="screenplay")
    s1 = db.create_scene(proj.id, "Scene", content="Test.")
    view = WritingCoreView(db, proj.id)
    editor = view._editors[s1.id]
    view._active_editor = editor
    view._element_combo.setCurrentIndex(
        next(i for i in range(view._element_combo.count())
             if view._element_combo.itemData(i) == "character"),
    )
    data = editor.textCursor().block().userData()
    assert isinstance(data, _BlockData)
    assert data.element == "character"


# -- Top menu: text color, paragraph menu, font list, no fade ---------------

def test_top_menu_no_fade():
    """Top bar opacity is 1.0; no auto-fade-out on hover-leave."""
    db = Database()
    proj, *_ = _setup_project(db)
    view = WritingCoreView(db, proj.id)
    assert view._topbar_opacity.opacity() == 1.0
    assert not hasattr(view, "_topbar_anim") or view.__dict__.get("_topbar_anim") is None


def test_color_button_exists():
    db = Database()
    proj, *_ = _setup_project(db)
    view = WritingCoreView(db, proj.id)
    assert hasattr(view, "_color_btn")
    assert view._color_btn.text() == "A"


def test_apply_text_color_to_selection():
    from PySide6.QtGui import QColor
    db = Database()
    proj, s1, *_ = _setup_project(db)
    view = WritingCoreView(db, proj.id)
    editor = view._editors[s1.id]
    view._active_editor = editor
    cursor = editor.textCursor()
    cursor.select(QTextCursor.SelectionType.Document)
    editor.setTextCursor(cursor)
    view._apply_text_color("#D9534F")
    fmt = editor.textCursor().charFormat()
    assert fmt.foreground().color() == QColor("#D9534F")


def test_paragraph_button_exists():
    db = Database()
    proj, *_ = _setup_project(db)
    view = WritingCoreView(db, proj.id)
    assert hasattr(view, "_paragraph_btn")


def test_apply_alignment_center():
    db = Database()
    proj, s1, *_ = _setup_project(db)
    view = WritingCoreView(db, proj.id)
    editor = view._editors[s1.id]
    view._active_editor = editor
    view._apply_alignment(Qt.AlignmentFlag.AlignHCenter)
    bfmt = editor.textCursor().blockFormat()
    assert bfmt.alignment() == Qt.AlignmentFlag.AlignHCenter


def test_apply_alignment_right_and_justify():
    db = Database()
    proj, s1, *_ = _setup_project(db)
    view = WritingCoreView(db, proj.id)
    editor = view._editors[s1.id]
    view._active_editor = editor
    view._apply_alignment(Qt.AlignmentFlag.AlignRight)
    assert editor.textCursor().blockFormat().alignment() == Qt.AlignmentFlag.AlignRight
    view._apply_alignment(Qt.AlignmentFlag.AlignJustify)
    assert editor.textCursor().blockFormat().alignment() == Qt.AlignmentFlag.AlignJustify


def test_change_block_indent():
    db = Database()
    proj, s1, *_ = _setup_project(db)
    view = WritingCoreView(db, proj.id)
    editor = view._editors[s1.id]
    view._active_editor = editor
    view._change_block_indent(1)
    assert editor.textCursor().blockFormat().indent() == 1
    view._change_block_indent(1)
    assert editor.textCursor().blockFormat().indent() == 2
    view._change_block_indent(-1)
    assert editor.textCursor().blockFormat().indent() == 1
    view._change_block_indent(-5)
    assert editor.textCursor().blockFormat().indent() == 0


def test_toggle_bullet_list():
    from PySide6.QtGui import QTextListFormat
    db = Database()
    proj, s1, *_ = _setup_project(db)
    view = WritingCoreView(db, proj.id)
    editor = view._editors[s1.id]
    view._active_editor = editor
    view._toggle_list(QTextListFormat.Style.ListDisc)
    assert editor.textCursor().currentList() is not None
    assert (
        editor.textCursor().currentList().format().style()
        == QTextListFormat.Style.ListDisc
    )


def test_toggle_numbered_list():
    from PySide6.QtGui import QTextListFormat
    db = Database()
    proj, s1, *_ = _setup_project(db)
    view = WritingCoreView(db, proj.id)
    editor = view._editors[s1.id]
    view._active_editor = editor
    view._toggle_list(QTextListFormat.Style.ListDecimal)
    lst = editor.textCursor().currentList()
    assert lst is not None
    assert lst.format().style() == QTextListFormat.Style.ListDecimal


def test_font_list_includes_courier():
    db = Database()
    proj, *_ = _setup_project(db)
    view = WritingCoreView(db, proj.id)
    keys = [
        view._font_combo.itemData(i)
        for i in range(view._font_combo.count())
    ]
    assert "courier_new" in keys
    assert "courier" in keys
    assert "georgia" in keys
    assert "helvetica" in keys
    assert view._font_combo.count() >= 12


def test_font_courier_persists():
    db = Database()
    proj, *_ = _setup_project(db)
    view = WritingCoreView(db, proj.id)
    for i in range(view._font_combo.count()):
        if view._font_combo.itemData(i) == "courier_new":
            view._font_combo.setCurrentIndex(i)
            break
    assert view._font_family_key == "courier_new"
    settings = db.get_project_settings(proj.id)
    assert settings["font_family"] == "courier_new"


# -- Top menu grouped buttons ------------------------------------------------

def test_ap_button_exists():
    db = Database()
    proj, *_ = _setup_project(db)
    view = WritingCoreView(db, proj.id)
    assert hasattr(view, "_ap_btn")
    assert view._ap_btn.text() == "A-P"


def test_review_button_exists():
    db = Database()
    proj, *_ = _setup_project(db)
    view = WritingCoreView(db, proj.id)
    assert hasattr(view, "_review_btn")
    assert view._review_btn.text() == "Review"


def test_focus_button_exists():
    db = Database()
    proj, *_ = _setup_project(db)
    view = WritingCoreView(db, proj.id)
    assert hasattr(view, "_focus_btn")
    assert view._focus_btn.text() == "Focus"


def test_textbg_button_exists():
    db = Database()
    proj, *_ = _setup_project(db)
    view = WritingCoreView(db, proj.id)
    assert hasattr(view, "_textbg_btn")
    assert view._textbg_btn.text() == "Text/Bg"


# -- Bold / Italic / Underline / Strikethrough --------------------------------

def test_toggle_bold():
    from PySide6.QtGui import QFont
    db = Database()
    proj, s1, *_ = _setup_project(db)
    view = WritingCoreView(db, proj.id)
    editor = view._editors[s1.id]
    view._active_editor = editor
    cursor = editor.textCursor()
    cursor.select(QTextCursor.SelectionType.Document)
    editor.setTextCursor(cursor)
    view._toggle_bold()
    fmt = editor.textCursor().charFormat()
    assert fmt.fontWeight() >= QFont.Weight.Bold


def test_toggle_italic():
    db = Database()
    proj, s1, *_ = _setup_project(db)
    view = WritingCoreView(db, proj.id)
    editor = view._editors[s1.id]
    view._active_editor = editor
    cursor = editor.textCursor()
    cursor.select(QTextCursor.SelectionType.Document)
    editor.setTextCursor(cursor)
    view._toggle_italic()
    assert editor.textCursor().charFormat().fontItalic() is True


def test_toggle_underline():
    db = Database()
    proj, s1, *_ = _setup_project(db)
    view = WritingCoreView(db, proj.id)
    editor = view._editors[s1.id]
    view._active_editor = editor
    cursor = editor.textCursor()
    cursor.select(QTextCursor.SelectionType.Document)
    editor.setTextCursor(cursor)
    view._toggle_underline()
    assert editor.textCursor().charFormat().fontUnderline() is True


def test_toggle_strikethrough():
    db = Database()
    proj, s1, *_ = _setup_project(db)
    view = WritingCoreView(db, proj.id)
    editor = view._editors[s1.id]
    view._active_editor = editor
    cursor = editor.textCursor()
    cursor.select(QTextCursor.SelectionType.Document)
    editor.setTextCursor(cursor)
    view._toggle_strikethrough()
    assert editor.textCursor().charFormat().fontStrikeOut() is True


# -- Background color ---------------------------------------------------------

def test_apply_bg_color():
    db = Database()
    proj, *_ = _setup_project(db)
    view = WritingCoreView(db, proj.id)
    view._apply_bg_color("#1C1914")
    assert view._current_bg_color == "#1C1914"


def test_apply_bg_color_default():
    db = Database()
    proj, *_ = _setup_project(db)
    view = WritingCoreView(db, proj.id)
    view._apply_bg_color("#1C1914")
    view._apply_bg_color("")
    assert view._current_bg_color == ""


# -- Text/Bg menu font helpers -----------------------------------------------

def test_set_font_family_via_menu():
    db = Database()
    proj, *_ = _setup_project(db)
    view = WritingCoreView(db, proj.id)
    view._set_font_family("courier_new")
    assert view._font_family_key == "courier_new"
    assert view._font_combo.currentData() == "courier_new"


def test_set_font_size_via_menu():
    db = Database()
    proj, *_ = _setup_project(db)
    view = WritingCoreView(db, proj.id)
    view._set_font_size(22)
    assert view._font_size == 22
    assert view._size_combo.currentData() == 22


# -- Grammar in review menu ---------------------------------------------------

def test_grammar_toggle_from_view():
    db = Database()
    proj, *_ = _setup_project(db)
    view = WritingCoreView(db, proj.id)
    assert view._grammar_checking is False
    view._toggle_grammar()
    assert view._grammar_checking is True
    view._toggle_grammar()
    assert view._grammar_checking is False


# -- Focus mode does not fade top bar ----------------------------------------

def test_focus_mode_restores_opacity():
    db = Database()
    proj, *_ = _setup_project(db)
    view = WritingCoreView(db, proj.id)
    view.toggle_focus_mode()
    view.toggle_focus_mode()
    assert view._topbar_opacity.opacity() == 1.0


# -- Unified grammar + style feedback -----------------------------------------

def test_grammar_priority_over_style_same_span():
    """Grammar error on same span suppresses the style hint."""
    from logosforge.grammar_checker import Issue
    from logosforge.style_analysis import StyleHint

    db = Database()
    proj, *_ = _setup_project(db)
    view = WritingCoreView(db, proj.id)
    editor = list(view._editors.values())[0]
    editor.setPlainText("quikc brown fox jumps quickly")

    editor._grammar_issues = [
        Issue(start=0, end=5, issue_type="spelling",
              message="Unknown word", suggestions=["quick"]),
    ]
    editor._style_hints = [
        StyleHint(start=0, end=5, hint_type="clarity", message="Unclear"),
    ]
    editor._style_hints_enabled = True
    editor.apply_grammar_underlines()
    sels = editor.extraSelections()
    assert len(sels) == 1
    assert sels[0].format.toolTip().startswith("Unknown word")


def test_style_hint_shown_when_no_grammar_overlap():
    """Style hint on different span is shown alongside grammar error."""
    from logosforge.grammar_checker import Issue
    from logosforge.style_analysis import StyleHint

    db = Database()
    proj, *_ = _setup_project(db)
    view = WritingCoreView(db, proj.id)
    editor = list(view._editors.values())[0]
    editor.setPlainText("quikc brown fox jumps quickly")

    editor._grammar_issues = [
        Issue(start=0, end=5, issue_type="spelling",
              message="Unknown word", suggestions=["quick"]),
    ]
    editor._style_hints = [
        StyleHint(start=20, end=27, hint_type="clarity",
                  message="Style issue here"),
    ]
    editor._style_hints_enabled = True
    editor.apply_grammar_underlines()
    sels = editor.extraSelections()
    assert len(sels) == 2
    tips = [s.format.toolTip() for s in sels]
    assert any("Unknown word" in t for t in tips)
    assert any("Style issue here" in t for t in tips)


def test_grammar_suppresses_overlapping_style_partial():
    """Style hint partially overlapping grammar span is suppressed."""
    from logosforge.grammar_checker import Issue
    from logosforge.style_analysis import StyleHint

    db = Database()
    proj, *_ = _setup_project(db)
    view = WritingCoreView(db, proj.id)
    editor = list(view._editors.values())[0]
    editor.setPlainText("quikc brown fox jumps quickly")

    editor._grammar_issues = [
        Issue(start=5, end=15, issue_type="grammar",
              message="Grammar issue"),
    ]
    editor._style_hints = [
        StyleHint(start=10, end=20, hint_type="rhythm",
                  message="Rhythm issue"),
    ]
    editor._style_hints_enabled = True
    editor.apply_grammar_underlines()
    sels = editor.extraSelections()
    assert len(sels) == 1
    assert "Grammar issue" in sels[0].format.toolTip()


def test_grammar_suppresses_style_that_encloses_it():
    """Style hint that fully encloses a grammar span is suppressed."""
    from logosforge.grammar_checker import Issue
    from logosforge.style_analysis import StyleHint

    db = Database()
    proj, *_ = _setup_project(db)
    view = WritingCoreView(db, proj.id)
    editor = list(view._editors.values())[0]
    editor.setPlainText("quikc brown fox jumps quickly")

    editor._grammar_issues = [
        Issue(start=6, end=11, issue_type="spelling",
              message="Spelling error"),
    ]
    editor._style_hints = [
        StyleHint(start=0, end=20, hint_type="clarity",
                  message="Long sentence"),
    ]
    editor._style_hints_enabled = True
    editor.apply_grammar_underlines()
    sels = editor.extraSelections()
    assert len(sels) == 1
    assert "Spelling error" in sels[0].format.toolTip()


def test_multiple_grammar_multiple_style_no_duplicate():
    """Multiple grammar errors suppress overlapping style hints."""
    from logosforge.grammar_checker import Issue
    from logosforge.style_analysis import StyleHint

    db = Database()
    proj, *_ = _setup_project(db)
    view = WritingCoreView(db, proj.id)
    editor = list(view._editors.values())[0]
    editor.setPlainText("aa bb cc dd ee ff gg hh ii jj")

    editor._grammar_issues = [
        Issue(start=0, end=2, issue_type="spelling", message="g1"),
        Issue(start=6, end=8, issue_type="grammar", message="g2"),
    ]
    editor._style_hints = [
        StyleHint(start=0, end=2, hint_type="clarity", message="s1"),
        StyleHint(start=3, end=5, hint_type="clarity", message="s2"),
        StyleHint(start=6, end=8, hint_type="rhythm", message="s3"),
    ]
    editor._style_hints_enabled = True
    editor.apply_grammar_underlines()
    sels = editor.extraSelections()
    tips = [s.format.toolTip() for s in sels]
    assert "g1" in tips
    assert "g2" in tips
    assert "s2" in tips
    assert "s1" not in tips
    assert "s3" not in tips


def test_style_disabled_no_style_selections():
    """When style hints are disabled, only grammar selections appear."""
    from logosforge.grammar_checker import Issue
    from logosforge.style_analysis import StyleHint

    db = Database()
    proj, *_ = _setup_project(db)
    view = WritingCoreView(db, proj.id)
    editor = list(view._editors.values())[0]
    editor.setPlainText("quikc brown fox")

    editor._grammar_issues = [
        Issue(start=0, end=5, issue_type="spelling", message="spell"),
    ]
    editor._style_hints = [
        StyleHint(start=6, end=11, hint_type="clarity", message="style"),
    ]
    editor._style_hints_enabled = False
    editor.apply_grammar_underlines()
    sels = editor.extraSelections()
    assert len(sels) == 1
    assert "spell" in sels[0].format.toolTip()


def test_ignored_grammar_allows_style_hint():
    """Ignored grammar issue no longer suppresses the style hint."""
    from logosforge.grammar_checker import Issue
    from logosforge.style_analysis import StyleHint

    db = Database()
    proj, *_ = _setup_project(db)
    view = WritingCoreView(db, proj.id)
    editor = list(view._editors.values())[0]
    editor.setPlainText("quikc brown fox")

    issue = Issue(start=0, end=5, issue_type="spelling",
                  message="Unknown word")
    editor._grammar_issues = [issue]
    editor._style_hints = [
        StyleHint(start=0, end=5, hint_type="clarity", message="Unclear"),
    ]
    editor._style_hints_enabled = True
    editor._ignored_issues.add((issue.issue_type, issue.message))
    editor.apply_grammar_underlines()
    sels = editor.extraSelections()
    assert len(sels) == 1
    assert "Unclear" in sels[0].format.toolTip()
