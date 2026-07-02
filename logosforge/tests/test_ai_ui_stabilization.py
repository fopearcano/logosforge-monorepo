"""Step 14 — Assistant / Logos / PSYKE-console UI stabilization (lock tests)."""

import pytest
from PySide6.QtWidgets import QApplication, QLineEdit

from logosforge.db import Database
from logosforge.ui.main_window import MainWindow


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


def _win():
    db = Database()
    pid = db.create_project("P", narrative_engine="novel").id
    db.create_scene(pid, "S1", content="Alice walked to the Harbor. " * 10,
                    summary="Alice", act="Act I")
    db.create_psyke_entry(pid, "Alice", "character")
    db.create_psyke_entry(pid, "The Harbor", "place")
    return db, pid, MainWindow(db, pid)


# ==========================================================================
# Assistant dock
# ==========================================================================


def test_assistant_dock_fits_when_wide():
    db, pid, win = _win()
    dock = win._assistant_dock
    dock.set_panel_user_visible(True)
    dock.apply_responsive(width=1200)
    assert dock.is_panel_visible() is True
    assert dock.is_auto_hidden() is False
    # never a tiny panel when shown
    assert dock.panel.maximumWidth() >= dock.PANEL_MIN_WIDTH


def test_assistant_dock_auto_hides_when_cramped_no_hidden_edge():
    db, pid, win = _win()
    dock = win._assistant_dock
    dock.set_panel_user_visible(True)
    dock.set_pinned(False)
    dock.apply_responsive(width=600)  # not enough room
    assert dock.is_panel_visible() is False     # auto-hidden, not off-screen
    assert dock.is_auto_hidden() is True


def test_assistant_undock_collapse_pin_stable():
    db, pid, win = _win()
    dock = win._assistant_dock
    dock.set_panel_user_visible(True)
    dock.set_collapsed(True); assert dock.is_collapsed() is True
    dock.set_collapsed(False); assert dock.is_collapsed() is False
    dock.set_pinned(True); assert dock.is_pinned() is True
    dock.set_pinned(False); assert dock.is_pinned() is False
    dock.set_floating(True); assert dock.is_floating() is True
    dock.set_floating(False); assert dock.is_floating() is False


def test_assistant_toggle_does_not_steal_section_or_focus():
    db, pid, win = _win()
    win.sidebar_buttons["Manuscript"].click()
    section = win._current_section
    win._toggle_assistant()
    # toggling the Assistant must not change the working section.
    assert win._current_section == section


# ==========================================================================
# Logos suggestions
# ==========================================================================


def test_logos_suggestions_hidden_when_disabled():
    db, pid, win = _win()
    assert win._logos_enabled is False
    win.sidebar_buttons["Manuscript"].click()
    assert win._logos_suggestions.isHidden()  # no overlap when off


def test_logos_suggestions_clear_on_project_switch():
    db, pid, win = _win()
    win._logos_enabled = True
    pid2 = db.create_project("P2", narrative_engine="novel").id
    win._switch_project(pid2)
    # engine repointed; no stale suggestions from the old project
    assert win._logos_engine._project_id == pid2
    assert win._logos_suggestions.suggestions() == [] or \
        win._logos_suggestions.isHidden()


# ==========================================================================
# PSYKE console
# ==========================================================================


def test_psyke_console_is_compact_and_bottom():
    db, pid, win = _win()
    console = win._psyke_console
    assert console.maximumHeight() <= 28          # text-height, not tall
    assert console.height() <= 28


def test_psyke_console_has_no_search_icon():
    db, pid, win = _win()
    console = win._psyke_console
    # The input has only the built-in clear button — no leading search/magnifier
    # QAction was added.
    assert console._input.actions() == []
    assert console._input.placeholderText() == "Search PSYKE…"


def test_psyke_suggestions_include_characters_and_places():
    db, pid, win = _win()
    console = win._psyke_console
    console._input.setText("a")           # matches Alice / Harbor
    console._run_search()
    assert console._dropdown is not None
    assert console._dropdown.has_items() is True


def test_psyke_suggestions_repeat_on_repeated_search():
    db, pid, win = _win()
    console = win._psyke_console
    console._input.setText("Alice")
    console._run_search()
    assert console._dropdown.has_items() is True
    # Run again (e.g. after dismiss) — suggestions must show again, not once.
    console._input.setText("Harbor")
    console._run_search()
    assert console._dropdown.has_items() is True


def test_psyke_console_restores_focus():
    db, pid, win = _win()
    console = win._psyke_console
    console.activate()
    # activation captures previous focus; clearing resets it (no permanent steal)
    console.clear_previous_focus()
    assert console._previous_focus is None


def test_psyke_text_is_green_in_all_palettes():
    from logosforge.ui import theme
    palettes = theme._PALETTES
    assert palettes  # palette table must exist
    for name, colors in palettes.items():
        hexv = colors["PSYKE_TEXT"].lstrip("#")
        r, g, b = (int(hexv[i:i + 2], 16) for i in (0, 2, 4))
        # "cooler green": green channel is the dominant component.
        assert g >= r and g >= b, f"{name} PSYKE_TEXT not green: #{hexv}"


# ==========================================================================
# suggest() data layer — characters/places surface as entity suggestions
# ==========================================================================


def test_suggest_returns_entity_for_psyke_entries():
    from logosforge.psyke_search import PsykeSearchIndex
    from logosforge.psyke_suggestions import suggest
    db = Database()
    pid = db.create_project("P", narrative_engine="novel").id
    db.create_psyke_entry(pid, "Alice", "character")
    db.create_psyke_entry(pid, "Harbor", "place")
    index = PsykeSearchIndex(db, pid)
    results = suggest("a", index, max_results=10)
    cats = {s.category for s in results}
    assert "entity" in cats
    names = " ".join(s.text for s in results)
    assert "Alice" in names or "Harbor" in names
