"""Step 13 — Manuscript writing experience stabilization.

Locks the core writing-experience guarantees: the editor opens, typing persists
without losing focus or read-only-locking, font/size/grammar/element controls
work without rebuilding (and thus without stealing focus), the top bar behaves,
and Manuscript reflects the current writing mode.
"""

import pytest
from PySide6.QtWidgets import QApplication, QPushButton

from logosforge.db import Database
from logosforge.ui.writing_core_view import WritingCoreView


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture(autouse=True)
def _isolated(monkeypatch, tmp_path):
    import logosforge.settings as settings
    settings._instance = None
    monkeypatch.setattr(settings, "CONFIG_DIR", tmp_path, raising=False)
    monkeypatch.setattr(settings, "SETTINGS_FILE", tmp_path / "settings.json",
                        raising=False)
    yield
    settings._instance = None


def _view(mode="novel"):
    db = Database()
    pid = db.create_project("P", narrative_engine=mode).id
    s1 = db.create_scene(pid, "Opening", content="The storm began.",
                         act="Act I", chapter="Ch1")
    return db, pid, s1, WritingCoreView(db, pid, on_content_saved=lambda: None)


# ==========================================================================
# Opens + typing
# ==========================================================================


def test_editor_opens_with_scene_editors():
    db, pid, s1, view = _view()
    assert s1.id in view._editors
    assert view._editors[s1.id].isEnabled() is True
    assert view._editors[s1.id].isReadOnly() is False


def test_typing_persists_to_db():
    db, pid, s1, view = _view()
    view._editors[s1.id].setPlainText("A freshly typed line.")
    view._save_scene(s1.id)
    assert "A freshly typed line" in (db.get_scene_by_id(s1.id).content or "")


def test_save_does_not_recreate_editor_or_lock_it():
    db, pid, s1, view = _view()
    before = view._editors[s1.id]
    view._editors[s1.id].setPlainText("more text")
    view._save_scene(s1.id)
    after = view._editors[s1.id]
    assert after is before                  # not rebuilt -> focus preserved
    assert after.isReadOnly() is False       # never locked read-only
    assert after.isEnabled() is True         # never greyed out


# ==========================================================================
# Font + size controls (work without rebuilding the canvas)
# ==========================================================================


def test_font_family_change_applies_and_persists():
    db, pid, s1, view = _view()
    editor_before = view._editors[s1.id]
    # Pick a different font preset via the real combo signal path.
    idx = (view._font_combo.currentIndex() + 1) % view._font_combo.count()
    view._font_combo.setCurrentIndex(idx)
    assert view._font_family_key == view._font_combo.itemData(idx)
    assert db.get_project_settings(pid).get("font_family") == view._font_family_key
    # Typography re-applied as a stylesheet — editor NOT recreated.
    assert view._editors[s1.id] is editor_before


def test_font_size_change_applies_and_persists():
    db, pid, s1, view = _view()
    editor_before = view._editors[s1.id]
    idx = (view._size_combo.currentIndex() + 1) % view._size_combo.count()
    view._size_combo.setCurrentIndex(idx)
    assert view._font_size == view._size_combo.itemData(idx)
    assert db.get_project_settings(pid).get("font_size") == view._font_size
    assert view._editors[s1.id] is editor_before


# ==========================================================================
# Grammar / focus / review controls do not crash
# ==========================================================================


def test_grammar_toggle_works():
    db, pid, s1, view = _view()
    before = view._grammar_checking
    view._toggle_grammar()
    assert view._grammar_checking is (not before)
    assert db.get_project_settings(pid).get("grammar_checking") == view._grammar_checking


def test_focus_mode_toggle_hides_and_restores_top_bar():
    db, pid, s1, view = _view()
    assert view._top_bar.isVisibleTo(view) or not view._focus_mode
    view.toggle_focus_mode()
    assert view._focus_mode is True
    assert view._top_bar.isHidden() is True          # hidden in focus mode
    view.toggle_focus_mode()
    assert view._focus_mode is False
    assert view._top_bar.isHidden() is False          # restored, not stuck
    assert view._topbar_opacity.opacity() == 1.0      # opacity not stuck faded


# ==========================================================================
# Menu builders exist (compact toolbar: font/color/bg under one button)
# ==========================================================================


def test_compact_toolbar_menu_builders_present():
    db, pid, s1, view = _view()
    for name in ("_show_text_bg_menu", "_show_review_menu", "_show_ap_menu"):
        assert callable(getattr(view, name))
    # font/size combos are consolidated (hidden) under the Text/Bg button.
    assert view._font_combo.isVisible() is False
    assert view._size_combo.isVisible() is False


def test_typewriter_is_not_a_visible_toolbar_button():
    db, pid, s1, view = _view()
    texts = {b.text() for b in view._top_bar.findChildren(QPushButton)}
    assert "Typewriter" not in texts  # shortcut-only, no toolbar clutter


# ==========================================================================
# Reflects current writing mode
# ==========================================================================


def test_element_combo_reflects_novel_mode():
    db, pid, s1, view = _view(mode="novel")
    items = [view._element_combo.itemData(i)
             for i in range(view._element_combo.count())]
    assert "body" in items
    assert "scene_heading" not in items  # screenplay-only element absent


def test_element_combo_reflects_screenplay_mode():
    db, pid, s1, view = _view(mode="screenplay")
    items = [view._element_combo.itemData(i)
             for i in range(view._element_combo.count())]
    assert "scene_heading" in items
    assert "dialogue" in items


def test_format_badge_shows_mode():
    db, pid, s1, view = _view(mode="screenplay")
    assert view._format_badge.text()  # non-empty engine/format label
