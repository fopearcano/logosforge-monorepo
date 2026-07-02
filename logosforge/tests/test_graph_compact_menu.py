"""Tests for the compact Graph top menu and structural-visualisation defaults.

Covers the "Improve Graph section" work: the overloaded toolbar collapsed into
``[Mode ▼] [Filters ▼] [Layout ▼] [Labels ▼] [Actions ▼]`` dropdowns, the
Structure-first default experience, label-density modes, layout overrides,
hide-isolated filtering and click-to-focus neighbourhood reveal.
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication, QPushButton

from logosforge.db import Database
from logosforge.ui.focus_graph_view import (
    FocusGraphView,
    MODE_ALL,
    MODE_STRUCTURE,
    NODE_KIND_CHARACTER,
    node_kind,
)


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture(autouse=True)
def _isolated_settings(monkeypatch, tmp_path):
    import logosforge.settings as settings
    settings._instance = None
    monkeypatch.setattr(settings, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(settings, "SETTINGS_FILE", tmp_path / "settings.json")
    yield
    settings._instance = None


def _make_project():
    db = Database()
    proj = db.create_project("Compact")
    alice = db.create_character(proj.id, "Alice")
    bob = db.create_character(proj.id, "Bob")
    db.create_place(proj.id, "Castle")
    db.create_scene(
        proj.id, "Opening", act="Act I",
        character_ids=[alice.id, bob.id],
        synopsis="[[Alice]] meets [[Bob]].",
    )
    db.create_scene(
        proj.id, "Midpoint", act="Act II",
        character_ids=[alice.id],
        synopsis="[[Alice]] alone.",
    )
    theme = db.create_psyke_entry(proj.id, "Trust", "theme")
    lore = db.create_psyke_entry(proj.id, "Old Pact", "lore")
    db.add_psyke_relation(theme.id, lore.id)
    return db, proj, alice, bob


# -- Compact top menu --------------------------------------------------------

def test_top_menu_has_five_dropdowns():
    db, proj, *_ = _make_project()
    view = FocusGraphView(db, proj.id)
    for attr in (
        "_mode_menu_btn", "_filters_menu_btn", "_layout_menu_btn",
        "_labels_menu_btn", "_actions_menu_btn",
    ):
        btn = getattr(view, attr, None)
        assert isinstance(btn, QPushButton), f"missing dropdown: {attr}"
        assert btn.menu() is not None, f"{attr} has no menu"


def test_search_input_is_directly_visible():
    db, proj, *_ = _make_project()
    view = FocusGraphView(db, proj.id)
    assert hasattr(view, "_search_input")


def test_legacy_widget_attrs_survive_rehousing():
    """Widgets re-housed into dropdown menus keep their attributes so the
    rest of the codebase / tests can still reach them."""
    db, proj, *_ = _make_project()
    view = FocusGraphView(db, proj.id)
    for attr in (
        "_mode_buttons", "_layer_checks", "_hops_check", "_skeleton_btn",
        "_mention_check", "_gravity_check", "_meaning_check", "_type_combo",
        "_flow_check", "_flow_combo", "_preset_combo",
    ):
        assert hasattr(view, attr), f"lost widget attr: {attr}"


# -- Structure-first default experience --------------------------------------

def test_default_mode_is_structure():
    db, proj, *_ = _make_project()
    view = FocusGraphView(db, proj.id)
    assert view.get_mode() == MODE_STRUCTURE


def test_default_label_mode_is_important():
    db, proj, *_ = _make_project()
    view = FocusGraphView(db, proj.id)
    assert view._label_mode == "important"


def test_structure_default_hides_character_hairball():
    """Opening straight into Structure should not show every character node."""
    db, proj, *_ = _make_project()
    view = FocusGraphView(db, proj.id)
    char_nodes = [
        nid for nid in view._node_items
        if node_kind(view._graph_data.nodes[nid]) == NODE_KIND_CHARACTER
    ]
    assert char_nodes == []


# -- Label density -----------------------------------------------------------

def test_label_mode_none_hides_all_labels():
    db, proj, *_ = _make_project()
    view = FocusGraphView(db, proj.id)
    view.set_mode(MODE_ALL)
    view._on_zoom(1.0)
    view._set_label_mode("none")
    assert all(not lbl.isVisible() for lbl in view._label_items.values())


def test_label_mode_all_shows_every_label():
    db, proj, *_ = _make_project()
    view = FocusGraphView(db, proj.id)
    view.set_mode(MODE_ALL)
    view._on_zoom(1.0)
    view._set_label_mode("all")
    assert view._label_items
    assert all(lbl.isVisible() for lbl in view._label_items.values())


def test_label_mode_important_is_subset_of_all():
    db, proj, *_ = _make_project()
    view = FocusGraphView(db, proj.id)
    view.set_mode(MODE_ALL)
    view._on_zoom(1.0)
    view._set_label_mode("all")
    n_all = sum(lbl.isVisible() for lbl in view._label_items.values())
    view._set_label_mode("important")
    n_important = sum(lbl.isVisible() for lbl in view._label_items.values())
    assert n_important <= n_all


# -- Layout override ---------------------------------------------------------

def test_layout_override_changes_effective_layout():
    db, proj, *_ = _make_project()
    view = FocusGraphView(db, proj.id)
    view._set_layout_override("radial")
    assert view._effective_layout() == "radial"
    view._set_layout_override("force")
    assert view._effective_layout() == "circular"
    view._set_layout_override("")  # Auto follows the mode profile
    assert view._effective_layout() == "linear_timeline"  # structure default


def test_radial_layout_produces_positions():
    db, proj, *_ = _make_project()
    view = FocusGraphView(db, proj.id)
    view.set_mode(MODE_ALL)
    view._set_layout_override("radial")
    visible = view._compute_visible_nodes()
    positions = view._layout_nodes(visible)
    assert set(positions) == visible
    assert positions  # non-empty


# -- Hide isolated -----------------------------------------------------------

def test_hide_isolated_drops_unconnected_nodes():
    db = Database()
    proj = db.create_project("Lonely")
    a = db.create_character(proj.id, "Alice")
    b = db.create_character(proj.id, "Bob")
    db.create_scene(
        proj.id, "Together", act="Act I", character_ids=[a.id, b.id],
    )
    # A lone character with no scene/relation links.
    db.create_character(proj.id, "Hermit")
    view = FocusGraphView(db, proj.id)
    view.set_mode(MODE_ALL)
    before = view.get_visible_count()
    view._on_hide_isolated_toggled(True)
    after = view.get_visible_count()
    assert after <= before


# -- Click to focus reveals neighbourhood ------------------------------------

def test_click_focus_reveals_neighbourhood_across_modes():
    """Focusing a character from Structure mode reveals it even though the
    mode normally hides characters."""
    db, proj, alice, _bob = _make_project()
    view = FocusGraphView(db, proj.id)
    assert view.get_mode() == MODE_STRUCTURE
    view._on_node_click(f"Character:{alice.id}")
    assert view.get_focus_node() == f"Character:{alice.id}"
    assert f"Character:{alice.id}" in view._node_items
