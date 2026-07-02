"""Tests for the Arcs (CharacterArcView) PSYKE-sourced character selector."""

import pytest

from logosforge.db import Database
from logosforge.project_events import emit_project_loaded, get_event_bus
from logosforge.ui.character_arc_view import CharacterArcView


@pytest.fixture(autouse=True)
def _isolated_settings(monkeypatch, tmp_path):
    import logosforge.settings as settings
    settings._instance = None
    monkeypatch.setattr(settings, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(settings, "SETTINGS_FILE", tmp_path / "settings.json")
    yield
    settings._instance = None


def _combo_names(view):
    """Selectable character names (excluding the placeholder)."""
    return [
        view._char_combo.itemData(i)
        for i in range(view._char_combo.count())
        if view._char_combo.itemData(i) is not None
    ]


# =========================================================================
# 1. Source = PSYKE character entries
# =========================================================================

def test_psyke_character_appears_in_selector():
    db = Database()
    proj = db.create_project("P")
    db.create_psyke_entry(proj.id, "Alice", entry_type="character")
    view = CharacterArcView(db, proj.id)
    assert "Alice" in _combo_names(view)


def test_non_character_psyke_entries_excluded():
    db = Database()
    proj = db.create_project("P")
    db.create_psyke_entry(proj.id, "Alice", entry_type="character")
    db.create_psyke_entry(proj.id, "Justice", entry_type="theme")
    db.create_psyke_entry(proj.id, "Castle", entry_type="place")
    view = CharacterArcView(db, proj.id)
    names = _combo_names(view)
    assert "Alice" in names
    assert "Justice" not in names
    assert "Castle" not in names


def test_character_table_rows_not_required():
    """A character defined only in PSYKE (no Character row) still appears."""
    db = Database()
    proj = db.create_project("P")
    db.create_psyke_entry(proj.id, "GhostChar", entry_type="character")
    view = CharacterArcView(db, proj.id)
    assert "GhostChar" in _combo_names(view)


def test_empty_project_has_only_placeholder():
    db = Database()
    proj = db.create_project("P")
    view = CharacterArcView(db, proj.id)
    assert _combo_names(view) == []
    assert view._char_combo.count() == 1  # just the placeholder


def test_characters_sorted_by_name():
    db = Database()
    proj = db.create_project("P")
    for n in ("Zara", "Alice", "Mona"):
        db.create_psyke_entry(proj.id, n, entry_type="character")
    view = CharacterArcView(db, proj.id)
    assert _combo_names(view) == ["Alice", "Mona", "Zara"]


# =========================================================================
# 2. Arc resolution by name
# =========================================================================

def test_arc_resolves_by_name():
    db = Database()
    proj = db.create_project("P")
    char = db.create_character(proj.id, "Alice")
    db.create_psyke_entry(proj.id, "Alice", entry_type="character")
    db.create_scene(
        proj.id, "Opening",
        character_ids=[char.id],
        character_states=[(char.id, "hopeful")],
    )
    view = CharacterArcView(db, proj.id)
    idx = view._char_combo.findData("Alice")
    view._char_combo.setCurrentIndex(idx)
    assert view._arc_list.count() == 1
    assert "hopeful" in view._arc_list.item(0).text()


def test_psyke_character_without_states_shows_message():
    db = Database()
    proj = db.create_project("P")
    db.create_psyke_entry(proj.id, "Loner", entry_type="character")
    view = CharacterArcView(db, proj.id)
    idx = view._char_combo.findData("Loner")
    view._char_combo.setCurrentIndex(idx)
    assert view._arc_list.count() == 0
    assert "No scene states" in view._empty_label.text()


def test_get_character_arc_by_name_db():
    db = Database()
    proj = db.create_project("P")
    char = db.create_character(proj.id, "Bob")
    db.create_scene(
        proj.id, "S1",
        character_ids=[char.id],
        character_states=[(char.id, "angry")],
    )
    arc = db.get_character_arc_by_name(proj.id, "Bob")
    assert len(arc) == 1
    assert arc[0][3] == "angry"
    # Unknown / case
    assert db.get_character_arc_by_name(proj.id, "bob")  # case-insensitive
    assert db.get_character_arc_by_name(proj.id, "Nobody") == []


# =========================================================================
# 3. Refresh on PSYKE changes
# =========================================================================

def test_refresh_picks_up_new_psyke_character():
    db = Database()
    proj = db.create_project("P")
    view = CharacterArcView(db, proj.id)
    assert "NewHero" not in _combo_names(view)
    db.create_psyke_entry(proj.id, "NewHero", entry_type="character")
    view.refresh()
    assert "NewHero" in _combo_names(view)


def test_psyke_list_changed_event_refreshes():
    db = Database()
    proj = db.create_project("P")
    view = CharacterArcView(db, proj.id)
    db.create_psyke_entry(proj.id, "Sudden", entry_type="character")
    get_event_bus().psyke_list_changed.emit()
    assert "Sudden" in _combo_names(view)


def test_refresh_preserves_selection_by_name():
    db = Database()
    proj = db.create_project("P")
    db.create_psyke_entry(proj.id, "Alice", entry_type="character")
    view = CharacterArcView(db, proj.id)
    idx = view._char_combo.findData("Alice")
    view._char_combo.setCurrentIndex(idx)
    # Add another character and refresh — Alice stays selected.
    db.create_psyke_entry(proj.id, "Zoe", entry_type="character")
    view.refresh()
    assert view._char_combo.currentData() == "Alice"


def test_deleted_character_disappears_after_refresh():
    db = Database()
    proj = db.create_project("P")
    e = db.create_psyke_entry(proj.id, "Temp", entry_type="character")
    view = CharacterArcView(db, proj.id)
    assert "Temp" in _combo_names(view)
    db.delete_psyke_entry(e.id)
    view.refresh()
    assert "Temp" not in _combo_names(view)


# =========================================================================
# 4. Project switching — no stale characters
# =========================================================================

def test_set_project_swaps_characters():
    db = Database()
    a = db.create_project("A")
    b = db.create_project("B")
    db.create_psyke_entry(a.id, "Alpha", entry_type="character")
    db.create_psyke_entry(b.id, "Beta", entry_type="character")
    view = CharacterArcView(db, a.id)
    assert _combo_names(view) == ["Alpha"]
    view.set_project(b.id)
    names = _combo_names(view)
    assert "Beta" in names
    assert "Alpha" not in names  # no old project characters


def test_project_loaded_event_swaps_characters():
    db = Database()
    a = db.create_project("A")
    b = db.create_project("B")
    db.create_psyke_entry(a.id, "Alpha", entry_type="character")
    db.create_psyke_entry(b.id, "Beta", entry_type="character")
    view = CharacterArcView(db, a.id)
    emit_project_loaded(b.id)
    names = _combo_names(view)
    assert "Beta" in names
    assert "Alpha" not in names
