"""Logos quick actions are a readable dropdown, not a row of tiny buttons.

The bottom Logos toolbar exposes its actions through a QComboBox ("Choose
action…") that runs the selected action; Apply / Copy / Dismiss stay readable;
it works across themes and at small widths and preserves the action behavior.
"""

from __future__ import annotations

import warnings

import pytest
from PySide6.QtWidgets import QApplication, QComboBox, QPushButton

warnings.filterwarnings("ignore")

from logosforge.db import Database
from logosforge.logos.controller import LogosController
from logosforge.ui import theme
from logosforge.ui.logos.logos_toolbar import LogosToolbar

DARK, WARM, GREEN = "Dark", "Light (Warm)", "Light (Green)"


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture(autouse=True)
def _theme_dark():
    theme.set_palette(DARK)
    yield
    theme.set_palette(DARK)


def _toolbar(section="Outline", mode="novel"):
    db = Database()
    db.create_project("P", narrative_engine=mode)
    ctx = type("C", (), {"writing_mode": mode})()
    tb = LogosToolbar(LogosController(db), lambda: ctx)
    tb.set_section(section)
    return tb


# ==========================================================================
# Dropdown replaces the tiny button row
# ==========================================================================


def test_actions_are_a_dropdown_not_buttons():
    tb = _toolbar()
    assert isinstance(tb._action_combo, QComboBox)
    # No per-action buttons — only the 3 readable tool buttons remain.
    btns = [b.text() for b in tb.findChildren(QPushButton)]
    assert sorted(btns) == sorted(["Apply…", "Copy", "Dismiss"])


def test_dropdown_lists_actions_with_placeholder():
    tb = _toolbar()
    combo = tb._action_combo
    assert combo.itemText(0) == "Choose action…"          # readable placeholder
    assert combo.count() > 1                                # plus real actions
    names = tb.available_action_names()
    assert names and all(n for n in names)                  # each has a name


def test_selecting_action_runs_it():
    tb = _toolbar()
    ran: list[str] = []
    tb.run_action = lambda name: ran.append(name)           # capture behavior
    tb._on_action_selected(1)                               # pick first real action
    assert ran == [tb._action_combo.itemData(1)]


def test_placeholder_selection_does_nothing():
    tb = _toolbar()
    ran: list[str] = []
    tb.run_action = lambda name: ran.append(name)
    tb._on_action_selected(0)                               # the placeholder
    assert ran == []


def test_apply_copy_dismiss_present_and_readable():
    tb = _toolbar()
    assert tb._apply_btn.text() == "Apply…"
    assert tb._copy_btn.text() == "Copy"
    assert tb._dismiss_btn.text() == "Dismiss"


# ==========================================================================
# Themes + small widths
# ==========================================================================


@pytest.mark.parametrize("palette", [DARK, WARM, GREEN])
def test_dropdown_works_across_themes(palette):
    theme.set_palette(palette)
    tb = _toolbar()
    tb.refresh_actions()
    assert tb._action_combo.count() > 1
    # No stale inline style — the combo follows the global themed stylesheet.
    assert tb._action_combo.styleSheet() == ""


def test_dropdown_usable_at_small_width():
    tb = _toolbar()
    tb.setFixedWidth(180)
    tb.refresh_actions()
    # A dropdown never clips its labels — all actions remain reachable.
    assert tb._action_combo.isEnabled()
    assert tb._action_combo.count() > 1


def test_busy_disables_dropdown_not_missing_buttons():
    tb = _toolbar()
    tb._set_busy(True)
    assert tb._action_combo.isEnabled() is False
    tb._set_busy(False)
    assert tb._action_combo.isEnabled() is True


def test_no_actions_section_shows_message():
    tb = _toolbar(section="NoSuchSection")
    assert tb._action_combo.count() == 1                    # placeholder only
    assert "No Logos actions" in tb._status.text()
