"""Tests for sidebar group collapsed-default and active highlight."""

import json

import pytest

from logosforge.db import Database
from logosforge.ui.main_window import MainWindow, _SidebarGroupHeader


def _setup():
    db = Database()
    proj = db.create_project("Test")
    return db, proj


@pytest.fixture(autouse=True)
def reset_settings(monkeypatch, tmp_path):
    """Use an isolated settings file so tests don't pollute user state."""
    import logosforge.settings as settings
    settings._instance = None
    monkeypatch.setattr(settings, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(settings, "SETTINGS_FILE", tmp_path / "settings.json")
    yield
    settings._instance = None


# ==========================================================================
# 1. Groups collapsed by default
# ==========================================================================

def test_groups_collapsed_on_first_startup():
    db, proj = _setup()
    win = MainWindow(db, proj.id)
    assert len(win._sidebar_groups) > 0
    for group in win._sidebar_groups:
        assert group.expanded is False, (
            f"Group '{group.label}' should be collapsed by default"
        )


def test_group_children_hidden_when_collapsed():
    db, proj = _setup()
    win = MainWindow(db, proj.id)
    win.show()
    for group in win._sidebar_groups:
        for child in group._children:
            assert child.isVisible() is False, (
                f"Child of collapsed group '{group.label}' should be hidden"
            )


# ==========================================================================
# 2. Manual expand/collapse
# ==========================================================================

def test_clicking_group_expands_it():
    db, proj = _setup()
    win = MainWindow(db, proj.id)
    win.show()
    group = win._sidebar_groups[0]
    assert group.expanded is False
    group._toggle()
    assert group.expanded is True
    for child in group._children:
        # Children marked unavailable for the current writing mode (e.g. the
        # Graphic-Novel-only Pages item in a novel project) stay hidden even
        # when the group is expanded.
        available = child.property("nav_available") is not False
        assert child.isVisible() is available


def test_clicking_expanded_group_collapses_it():
    db, proj = _setup()
    win = MainWindow(db, proj.id)
    win.show()
    group = win._sidebar_groups[0]
    group._toggle()
    assert group.expanded is True
    group._toggle()
    assert group.expanded is False


# ==========================================================================
# 3. Groups always start collapsed when the app opens
# ==========================================================================

def test_groups_always_collapse_on_reopen():
    """A group expanded in one session must open collapsed next time — groups
    are always hidden at the beginning when the app opens."""
    db, proj = _setup()
    win = MainWindow(db, proj.id)
    target = win._sidebar_groups[0]
    label = target.label
    target._toggle()
    assert target.expanded is True   # expanded in this session

    win2 = MainWindow(db, proj.id)
    matching = [g for g in win2._sidebar_groups if g.label == label]
    assert len(matching) == 1
    assert matching[0].expanded is False  # collapsed again on reopen


def test_collapsed_state_persists():
    db, proj = _setup()
    win = MainWindow(db, proj.id)
    target = win._sidebar_groups[0]
    label = target.label
    target._toggle()
    target._toggle()
    assert target.expanded is False

    win2 = MainWindow(db, proj.id)
    matching = [g for g in win2._sidebar_groups if g.label == label]
    assert matching[0].expanded is False


# ==========================================================================
# 4. Active section highlight
# ==========================================================================

def test_set_active_section_highlights_one_button():
    db, proj = _setup()
    win = MainWindow(db, proj.id)
    win._set_active_section("Dashboard")
    checked = [
        l for l in win._nav_labels
        if win.sidebar_buttons[l].isChecked()
    ]
    assert checked == ["Dashboard"]


def test_active_section_switches_correctly():
    db, proj = _setup()
    win = MainWindow(db, proj.id)
    win._set_active_section("Dashboard")
    win._set_active_section("Notes")
    checked = [
        l for l in win._nav_labels
        if win.sidebar_buttons[l].isChecked()
    ]
    assert checked == ["Notes"]


def test_active_section_in_collapsed_group_expands_it():
    db, proj = _setup()
    win = MainWindow(db, proj.id)
    plan = next(g for g in win._sidebar_groups if g.label == "Plan")
    assert plan.expanded is False
    win._set_active_section("Outline")
    assert plan.expanded is True
    assert win.sidebar_buttons["Outline"].isChecked() is True


def test_active_section_repeatedly_switching():
    db, proj = _setup()
    win = MainWindow(db, proj.id)
    sequence = ["Dashboard", "Notes", "Manuscript", "Tags", "PSYKE"]
    for name in sequence:
        win._set_active_section(name)
        checked = [
            l for l in win._nav_labels
            if win.sidebar_buttons[l].isChecked()
        ]
        assert checked == [name], (
            f"After activating {name}, expected only {name} checked, got {checked}"
        )


# ==========================================================================
# 5. Collapsing a group with active item keeps internal state
# ==========================================================================

def test_collapsing_group_with_active_item_preserves_check():
    db, proj = _setup()
    win = MainWindow(db, proj.id)
    win._set_active_section("Outline")
    assert win.sidebar_buttons["Outline"].isChecked() is True

    plan = next(g for g in win._sidebar_groups if g.label == "Plan")
    plan._toggle()
    assert plan.expanded is False
    assert win.sidebar_buttons["Outline"].isChecked() is True
    assert win._current_section == "Outline"


# ==========================================================================
# 6. Hover/active visual distinction
# ==========================================================================

def test_checked_button_has_no_inline_stylesheet():
    db, proj = _setup()
    win = MainWindow(db, proj.id)
    win._set_active_section("Dashboard")
    btn = win.sidebar_buttons["Dashboard"]
    assert btn.styleSheet() == "", (
        "Checked button must rely on Qt :checked rule, not inline style"
    )


def test_uncheck_clears_inline_style():
    db, proj = _setup()
    win = MainWindow(db, proj.id)
    win._set_active_section("Dashboard")
    btn = win.sidebar_buttons["Dashboard"]
    btn.setStyleSheet("background: red;")
    win._set_active_section("Notes")
    assert btn.styleSheet() == ""


# ==========================================================================
# 7. Group state survives sidebar collapse
# ==========================================================================

def test_sidebar_collapse_then_expand_preserves_group_state():
    db, proj = _setup()
    win = MainWindow(db, proj.id)
    plan = next(g for g in win._sidebar_groups if g.label == "Plan")
    plan._toggle()
    assert plan.expanded is True

    for g in win._sidebar_groups:
        g.set_sidebar_collapsed(True)
    for g in win._sidebar_groups:
        g.set_sidebar_collapsed(False)
    assert plan.expanded is True


# ==========================================================================
# 8. Settings file content
# ==========================================================================

def test_persistence_writes_to_settings_file(tmp_path):
    import logosforge.settings as settings
    db, proj = _setup()
    win = MainWindow(db, proj.id)
    plan = next(g for g in win._sidebar_groups if g.label == "Plan")
    plan._toggle()
    saved = json.loads(settings.SETTINGS_FILE.read_text())
    assert saved["sidebar_groups_expanded"]["Plan"] is True
