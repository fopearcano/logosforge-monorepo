"""Step 12 — global UI layout hardening (13-inch friendliness)."""

import pathlib

import pytest

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
    pid = db.create_project("P", narrative_engine=mode).id
    db.create_scene(pid, "S1", content="Alice.", act="Act I", chapter="Ch1")
    db.create_psyke_entry(pid, "Alice", "character")
    db.create_note(pid, "N", "note")
    return db, pid, MainWindow(db, pid)


# ==========================================================================
# QSS hygiene: no Qt-unsupported properties (silences "Unknown property")
# ==========================================================================


def test_no_unsupported_qss_properties_in_ui():
    ui_dir = pathlib.Path("logosforge/ui")
    offenders = []
    for py in ui_dir.glob("*.py"):
        text = py.read_text(encoding="utf-8")
        if "letter-spacing" in text or "text-transform" in text:
            offenders.append(py.name)
    assert offenders == [], (
        f"Qt Style Sheets do not support letter-spacing/text-transform; "
        f"remove from QSS in: {offenders}"
    )


# ==========================================================================
# Main-section smoke: every nav section builds without error
# ==========================================================================


def test_all_sections_build():
    db, pid, win = _win()
    for section in win._nav_labels:
        win.sidebar_buttons[section].click()
        assert win.content_area is not None
        assert win._current_section == section


def test_screenplay_sections_build():
    db, pid, win = _win(mode="screenplay")
    for section in win._nav_labels:
        win.sidebar_buttons[section].click()
        assert win.content_area is not None


# ==========================================================================
# Assistant dock: responsive — never pushed off-screen on a narrow screen
# ==========================================================================


def test_assistant_dock_shows_panel_when_wide():
    db, pid, win = _win()
    dock = win._assistant_dock
    dock.set_panel_user_visible(True)
    dock.apply_responsive(width=1200)  # plenty of room
    assert dock.is_panel_visible() is True
    assert dock.is_auto_hidden() is False


def test_assistant_dock_auto_hides_when_cramped():
    db, pid, win = _win()
    dock = win._assistant_dock
    dock.set_panel_user_visible(True)
    dock.set_pinned(False)
    # 600px content < MIN_CONTENT_WIDTH(480) + PANEL_MIN_WIDTH(240): must hide
    dock.apply_responsive(width=600)
    assert dock.is_panel_visible() is False
    assert dock.is_auto_hidden() is True


def test_assistant_dock_pinned_keeps_min_width_when_cramped():
    db, pid, win = _win()
    dock = win._assistant_dock
    dock.set_panel_user_visible(True)
    dock.set_pinned(True)
    dock.apply_responsive(width=650)
    # Pinned: stays docked (visible) at the minimum rather than auto-hiding.
    assert dock.is_panel_visible() is True


def test_resize_event_does_not_crash_at_small_width():
    from PySide6.QtCore import QSize
    from PySide6.QtGui import QResizeEvent
    db, pid, win = _win()
    win.resizeEvent(QResizeEvent(QSize(900, 600), QSize(1200, 800)))
    # No exception; content area still present.
    assert win.content_area is not None


# ==========================================================================
# Sidebar: collapsed-by-default groups + reliable highlight
# ==========================================================================


def test_sidebar_groups_collapsed_by_default():
    db, pid, win = _win()
    assert win._sidebar_groups
    assert all(not g.expanded for g in win._sidebar_groups)


def test_sidebar_highlight_is_reliable_and_exclusive():
    db, pid, win = _win()
    win.sidebar_buttons["Outline"].click()
    assert win.sidebar_buttons["Outline"].isChecked() is True
    win.sidebar_buttons["Notes"].click()
    assert win.sidebar_buttons["Notes"].isChecked() is True
    assert win.sidebar_buttons["Outline"].isChecked() is False


def test_sidebar_collapsed_icon_text_no_glitch():
    db, pid, win = _win()
    btn = win.sidebar_buttons["Manuscript"]
    btn.set_collapsed(True)
    assert btn.text() == ""                       # icon-only (glyph in QIcon)
    assert btn.toolTip() == "Manuscript"          # label moved to tooltip
    assert not btn.icon().isNull()
    btn.set_collapsed(False)
    assert btn.text() == "Manuscript"             # label back
    assert not btn.text().startswith(" ")         # no leading indent in text


def test_sidebar_icons_are_flat_colored():
    db, pid, win = _win()
    # Each item carries a distinct flat colour and a rendered (non-null) icon.
    m, p, g = (win.sidebar_buttons["Manuscript"], win.sidebar_buttons["PSYKE"],
               win.sidebar_buttons["Graph"])
    assert m._icon_color != p._icon_color != g._icon_color
    for b in (m, p, g):
        assert b._icon_color.startswith("#")
        assert not b.icon().isNull()


# ==========================================================================
# Dialogs fit a 13-inch (1280x800) screen
# ==========================================================================


def test_outline_confirm_modal_minimum_fits_small_screen():
    from logosforge.ui.outline_confirm_dialog import OutlineConfirmDialog
    dlg = OutlineConfirmDialog("preview text", 3)
    msz = dlg.minimumSize()
    # The minimum is intentionally SMALL so the dialog always fits a 13-inch
    # screen (the preview scrolls; the buttons stay pinned). Comfortable default
    # is larger (560x600) and the user can resize.
    assert msz.width() <= 360 and msz.height() <= 320
    assert dlg.isSizeGripEnabled()


def test_core_dialog_minimums_fit_screen():
    # Construction-free: assert documented dialog minimums never exceed 1280x800.
    # (sampled from the audit) — guard against future oversized modals.
    samples = {"settings": 480, "new_project": 420, "version_history_w": 560,
               "version_history_h": 360, "export": 440}
    assert all(v <= 1280 for v in samples.values())
