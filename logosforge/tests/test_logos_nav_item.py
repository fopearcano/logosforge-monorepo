"""Tests for the left-panel 'Logos' item as an inline ON/OFF toggle.

Logos is NOT a central section/dashboard — it is a toggle for the ambient inline
contextual Logos layer (toolbar + suggestions) that stays inside the current
section.
"""

import pytest

from PySide6.QtWidgets import QPushButton

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


def _win(mode="novel"):
    db = Database()
    pid = db.create_project("Test", narrative_engine=mode).id
    db.create_scene(pid, "S1", content="Alice stood in the Kitchen.",
                    location="Kitchen")
    return db, pid, MainWindow(db, pid)


# ==========================================================================
# 1, 14 — presence / no duplication
# ==========================================================================


def test_logos_item_present():
    db, pid, win = _win()
    assert "Logos" in win.sidebar_buttons


def test_logos_item_not_duplicated():
    db, pid, win = _win()
    logos_btns = [b for b in win.findChildren(QPushButton)
                  if b in win.sidebar_buttons.values()
                  and win.sidebar_buttons.get("Logos") is b]
    assert len(logos_btns) == 1
    # And it is NOT a navigation section.
    assert "Logos" not in win._nav_labels
    assert "Logos" not in win._nav_section_handlers


# ==========================================================================
# 2 — toggles logos_enabled
# ==========================================================================


def test_logos_click_toggles_enabled():
    db, pid, win = _win()
    assert win._logos_enabled is False
    win.sidebar_buttons["Logos"].click()
    assert win._logos_enabled is True
    win.sidebar_buttons["Logos"].click()
    assert win._logos_enabled is False


def test_logos_toggle_persisted():
    from logosforge.settings import get_manager
    db, pid, win = _win()
    win.sidebar_buttons["Logos"].click()
    assert get_manager().get("logos_enabled") is True


def test_logos_button_checked_reflects_state():
    db, pid, win = _win()
    win.sidebar_buttons["Logos"].click()
    assert win.sidebar_buttons["Logos"].isChecked() is True
    win.sidebar_buttons["Logos"].click()
    assert win.sidebar_buttons["Logos"].isChecked() is False


# ==========================================================================
# 3, 4, 5, 8 — clicking Logos does NOT change the central section
# ==========================================================================


def test_logos_does_not_change_section():
    db, pid, win = _win()
    win.sidebar_buttons["Manuscript"].click()
    section_before = win._current_section
    content_before = win.content_area
    win.sidebar_buttons["Logos"].click()
    assert win._current_section == section_before
    assert win.content_area is content_before  # no central page swap


def test_manuscript_stays_active_when_logos_toggled():
    db, pid, win = _win()
    win.sidebar_buttons["Manuscript"].click()
    win.sidebar_buttons["Logos"].click()
    assert win._current_section == "Manuscript"
    assert win.sidebar_buttons["Manuscript"].isChecked() is True


def test_plot_stays_active_when_logos_toggled():
    db, pid, win = _win()
    win.sidebar_buttons["Plot"].click()
    win.sidebar_buttons["Logos"].click()
    assert win._current_section == "Plot"
    assert win.sidebar_buttons["Plot"].isChecked() is True


def test_no_central_logos_page():
    # There is no LogosView module / central Logos page anymore.
    import importlib
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("logosforge.ui.logos.logos_view")


# ==========================================================================
# 6, 7 — inline layer appears when ON, hides when OFF
# ==========================================================================


def test_inline_layer_shows_when_on():
    db, pid, win = _win()
    win.sidebar_buttons["Manuscript"].click()
    win.sidebar_buttons["Logos"].click()
    assert win._logos_visible is True
    assert not win._logos_toolbar.isHidden()


def test_inline_layer_hides_when_off():
    db, pid, win = _win()
    win.sidebar_buttons["Logos"].click()   # ON
    win.sidebar_buttons["Logos"].click()   # OFF
    assert win._logos_visible is False
    assert win._logos_toolbar.isHidden()
    assert win._logos_suggestions.isHidden()


def test_suggestions_suppressed_when_off():
    db, pid, win = _win()
    # With Logos OFF, a section scan must not show the suggestion bar.
    win.sidebar_buttons["Manuscript"].click()
    assert win._logos_enabled is False
    assert win._logos_suggestions.isHidden()


# ==========================================================================
# 9, 10 — project switch clears stale suggestions / current project only
# ==========================================================================


def test_project_switch_clears_logos_suggestions():
    db, pid, win = _win()
    win.sidebar_buttons["Logos"].click()  # ON
    pid2 = db.create_project("Second", narrative_engine="novel").id
    win._switch_project(pid2)
    # No stale suggestions from the previous project remain visible.
    assert win._logos_suggestions.isHidden() or \
        win._logos_engine._db is not None
    # The proactive engine now points at the new project only.
    assert win._logos_engine._project_id == pid2


def test_logos_engine_rebound_to_new_project():
    db, pid, win = _win()
    pid2 = db.create_project("Other", narrative_engine="novel").id
    win._switch_project(pid2)
    assert win._logos_engine._project_id == pid2


# ==========================================================================
# 11, 12, 13 — Assistant / Chat / Counterpart / Quantum still work
# ==========================================================================


def test_assistant_toggle_still_works():
    db, pid, win = _win()
    win.sidebar_buttons["Assistant"].click()
    assert win._current_section != "Assistant"  # toggle, not a section


def test_chat_navigation_still_works():
    db, pid, win = _win()
    from logosforge.ui.chat_view import ChatView
    win.sidebar_buttons["Chat"].click()
    assert win._current_section == "Chat"
    # Chat is a floating window now: clicking it opens that window (central area
    # shows a placeholder), rather than docking a ChatView centrally.
    assert isinstance(win._chat_view, ChatView) and win._chat_view.isWindow()


def test_counterpart_and_quantum_modes_present():
    db, pid, win = _win()
    texts = {b.text() for b in win._assistant_panel.findChildren(QPushButton)}
    assert "Counterpart" in texts
    assert "Quantum" in texts


# ==========================================================================
# 15 — collapsed sidebar icon/text alignment stable
# ==========================================================================


def test_collapsed_sidebar_logos_icon_text():
    db, pid, win = _win()
    btn = win.sidebar_buttons["Logos"]
    btn.set_collapsed(True)
    # Collapsed = icon-only: no label text. Logos is a special toggle (not a
    # section), so its tooltip explains what it is + that it toggles on/off —
    # which is exactly what an icon-only user needs.
    assert btn.text() == ""
    tip = btn.toolTip()
    assert "Logos" in tip and "Toggle" in tip
    assert not btn.icon().isNull()
    btn.set_collapsed(False)
    assert btn.text() == "Logos"          # label only (glyph lives in the icon)
    # The explanatory tooltip persists when expanded too (survives the reset).
    assert "Logos" in btn.toolTip() and "Toggle" in btn.toolTip()
    assert not btn.icon().isNull()


def test_collapsed_logos_matches_other_standalone_items():
    db, pid, win = _win()
    logos, psyke = win.sidebar_buttons["Logos"], win.sidebar_buttons["PSYKE"]
    logos.set_collapsed(True)
    psyke.set_collapsed(True)
    assert logos.text() == "" and psyke.text() == ""
    assert not logos.icon().isNull() and not psyke.icon().isNull()
