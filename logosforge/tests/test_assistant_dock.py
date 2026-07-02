"""Tests for the Phase 1 Smart Assistant Panel foundation (AssistantDock).

Covers the single reusable dock that owns the assistant panel's sizing,
collapse/expand, pin/unpin, minimum content-width protection and
section-independent behaviour across Manuscript / Outline / Plot / Timeline /
Graph.
"""

from __future__ import annotations

import warnings

import pytest
from PySide6.QtWidgets import QApplication, QWidget

warnings.filterwarnings("ignore")

from logosforge.db import Database
from logosforge.ui.assistant_dock import AssistantDock
from logosforge.ui.assistant_view import AssistantPanel


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture(autouse=True)
def _isolated_settings(monkeypatch, tmp_path):
    import logosforge.settings as settings
    settings._instance = None
    monkeypatch.setattr(settings, "CONFIG_DIR", tmp_path, raising=False)
    monkeypatch.setattr(settings, "SETTINGS_FILE", tmp_path / "settings.json", raising=False)
    yield
    settings._instance = None


def _dock():
    panel = QWidget()
    dock = AssistantDock(panel)
    dock.set_content(QWidget())
    return dock, panel


# -- Content hosting ---------------------------------------------------------


def test_set_content_swaps_and_returns_previous():
    dock, _ = _dock()
    first = dock.content()
    new = QWidget()
    old = dock.set_content(new)
    assert old is first
    assert dock.content() is new


# -- Default state -----------------------------------------------------------


def test_panel_hidden_until_user_visible():
    dock, _ = _dock()
    dock.apply_responsive(1200)
    assert not dock.is_panel_visible()


# -- Responsive sizing -------------------------------------------------------


def test_wide_window_caps_panel_width():
    dock, panel = _dock()
    dock.set_panel_user_visible(True)
    dock.apply_responsive(1400)
    assert dock.is_panel_visible()
    assert panel.maximumWidth() == AssistantDock.PANEL_MAX_WIDTH


def test_medium_window_uses_remaining_width():
    dock, panel = _dock()
    dock.set_panel_user_visible(True)
    dock.apply_responsive(760)  # 760 - 480 = 280
    assert dock.is_panel_visible()
    assert panel.maximumWidth() == 280


# -- Minimum content-width protection ---------------------------------------


def test_unpinned_panel_auto_hides_to_protect_content():
    dock, _ = _dock()
    dock.set_panel_user_visible(True)
    dock.apply_responsive(620)  # space 140 < PANEL_MIN -> protect content
    assert not dock.is_panel_visible()
    assert dock.is_auto_hidden()


def test_auto_hidden_panel_returns_when_widened():
    dock, _ = _dock()
    dock.set_panel_user_visible(True)
    dock.apply_responsive(620)
    assert not dock.is_panel_visible()
    dock.apply_responsive(1200)
    assert dock.is_panel_visible()
    assert not dock.is_auto_hidden()


# -- Pin / unpin -------------------------------------------------------------


def test_pinned_panel_stays_docked_when_cramped():
    dock, panel = _dock()
    dock.set_panel_user_visible(True)
    dock.set_pinned(True)
    dock.apply_responsive(620)
    assert dock.is_panel_visible()
    assert panel.maximumWidth() == AssistantDock.PANEL_MIN_WIDTH


def test_pinned_changed_signal_emitted():
    dock, _ = _dock()
    seen = []
    dock.pinned_changed.connect(seen.append)
    dock.set_pinned(True)
    dock.set_pinned(True)  # no-op, no duplicate
    assert seen == [True]


# -- Collapse / expand -------------------------------------------------------


def test_collapse_hides_panel_shows_strip():
    dock, _ = _dock()
    dock.set_panel_user_visible(True)
    dock.apply_responsive(1200)
    dock.set_collapsed(True)
    assert not dock.is_panel_visible()
    assert not dock._strip.isHidden()  # expand strip is shown


def test_expand_restores_panel():
    dock, _ = _dock()
    dock.set_panel_user_visible(True)
    dock.apply_responsive(1200)
    dock.set_collapsed(True)
    dock.set_collapsed(False)
    assert dock.is_panel_visible()
    assert dock._strip.isHidden()


def test_collapsed_changed_signal():
    dock, _ = _dock()
    seen = []
    dock.collapsed_changed.connect(seen.append)
    dock.toggle_collapsed()
    dock.toggle_collapsed()
    assert seen == [True, False]


# -- Floating passthrough (no top-level window in Phase 1) -------------------


def test_floating_releases_panel_and_redocks():
    dock, _ = _dock()
    dock.set_panel_user_visible(True)
    dock.set_floating(True)
    assert dock.is_floating()
    dock.set_floating(False)
    assert not dock.is_floating()


# -- Panel control wiring ----------------------------------------------------


def test_panel_collapse_and_pin_signals_drive_dock():
    db = Database()
    pid = db.create_project("P").id
    panel = AssistantPanel(db, pid)
    dock = AssistantDock(panel)
    dock.set_content(QWidget())
    dock.set_panel_user_visible(True)
    dock.apply_responsive(1200)

    panel.collapse_requested.emit()
    assert dock.is_collapsed()
    dock.set_collapsed(False)

    panel.pin_toggled.emit(True)
    assert dock.is_pinned()
    # Pin state reflected on the header button.
    assert panel._pin_btn.isChecked()


def test_assistant_panel_has_collapse_and_pin_controls():
    db = Database()
    pid = db.create_project("P").id
    panel = AssistantPanel(db, pid)
    assert hasattr(panel, "_collapse_btn")
    assert hasattr(panel, "_pin_btn")
    assert panel._pin_btn.isCheckable()
