"""Tests for the final Graph UX polish: edge defaults, persistence,
presets, hover tooltips, stable labels, keyboard navigation, smooth view.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (
    QApplication,
    QGraphicsLineItem,
    QGraphicsPathItem,
    QGraphicsSimpleTextItem,
    QGraphicsView,
)

from logosforge.db import Database
from logosforge.ui.focus_graph_view import (
    EDGE_MENTION,
    EDGE_PARTICIPATION,
    EDGE_PSYKE_RELATION,
    MODE_ALL,
    FocusGraphView,
    _ZoomGraphicsView,
)


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture(autouse=True)
def _isolated_settings(monkeypatch, tmp_path):
    """Isolate the settings file per test.

    Graph state and presets are now persisted under per-project keys
    (graph_state:<id> / graph_presets:<id>). In-memory test DBs reuse
    project id 1, so without isolation those keys leak across tests via
    the shared global settings file. A fresh settings file per test
    keeps each case clean.
    """
    import logosforge.settings as settings
    settings._instance = None
    monkeypatch.setattr(settings, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(settings, "SETTINGS_FILE", tmp_path / "settings.json")
    yield
    settings._instance = None


def _project_with_mentions():
    db = Database()
    proj = db.create_project("Polish")
    c1 = db.create_character(proj.id, "Alice")
    c2 = db.create_character(proj.id, "Bob")
    db.create_scene(
        proj.id, "Opening", act="Act I",
        character_ids=[c1.id, c2.id],
        synopsis="[[Bob]] meets [[Alice]] in the dawn.",
    )
    db.create_scene(
        proj.id, "Midpoint", act="Act II",
        character_ids=[c1.id],
        synopsis="[[Alice]] reflects.",
    )
    return db, proj, c1, c2


# -- 1. no spaghetti at startup --------------------------------------------

def test_mention_edges_hidden_by_default():
    db, proj, *_ = _project_with_mentions()
    view = FocusGraphView(db, proj.id)
    assert view._edge_visibility[EDGE_MENTION] is False
    # No QGraphicsLineItem should have edge_type == EDGE_MENTION.
    for item in view._edge_items:
        assert item.data(0) != EDGE_MENTION


def test_mention_toggle_brings_them_back():
    db, proj, *_ = _project_with_mentions()
    view = FocusGraphView(db, proj.id)
    view.set_mode(MODE_ALL)  # default Structure hides character/mention edges
    view._on_mentions_toggled(True)
    mention_items = [
        item for item in view._edge_items
        if item.data(0) == EDGE_MENTION
    ]
    assert len(mention_items) >= 1


def test_structural_edges_still_visible_by_default():
    db, proj, *_ = _project_with_mentions()
    view = FocusGraphView(db, proj.id)
    view.set_mode(MODE_ALL)  # show character participation edges
    # Participation and containment are not noisy — should be visible.
    types_seen = {item.data(0) for item in view._edge_items}
    assert EDGE_PARTICIPATION in types_seen


# -- 2. smooth zoom/pan ----------------------------------------------------

def test_zoom_view_uses_scroll_hand_drag():
    db, proj, *_ = _project_with_mentions()
    view = FocusGraphView(db, proj.id)
    assert view._gview.dragMode() == QGraphicsView.DragMode.ScrollHandDrag


def test_zoom_view_render_hints_include_antialiasing():
    from PySide6.QtGui import QPainter
    db, proj, *_ = _project_with_mentions()
    view = FocusGraphView(db, proj.id)
    hints = view._gview.renderHints()
    assert hints & QPainter.RenderHint.Antialiasing


def test_zoom_view_reset_zoom_returns_to_one():
    db, proj, *_ = _project_with_mentions()
    view = FocusGraphView(db, proj.id)
    view._gview._zoom = 2.0
    view._gview.scale(2.0, 2.0)
    view._gview.reset_zoom()
    assert view._gview.current_zoom() == 1.0


# -- 3. stable labels ------------------------------------------------------

def test_labels_ignore_transformations():
    db, proj, *_ = _project_with_mentions()
    view = FocusGraphView(db, proj.id)
    for label in view._label_items.values():
        flag = label.flags() & label.GraphicsItemFlag.ItemIgnoresTransformations
        assert flag, "labels must ignore view zoom to stay readable"


# -- 4. hover tooltips -----------------------------------------------------

def test_node_items_have_tooltips():
    db, proj, *_ = _project_with_mentions()
    view = FocusGraphView(db, proj.id)
    for node_id, item in view._node_items.items():
        tip = item.toolTip()
        assert tip
        assert "Kind:" in tip
        assert "Neighbours:" in tip


# -- 5. keyboard navigation ------------------------------------------------

def test_arrow_key_cycles_focus():
    db, proj, *_ = _project_with_mentions()
    view = FocusGraphView(db, proj.id)
    if not view._node_items:
        pytest.skip("no visible nodes")
    visible_ids = sorted(view._node_items.keys())
    event_right = QKeyEvent(
        QKeyEvent.Type.KeyPress, Qt.Key.Key_Right, Qt.KeyboardModifier.NoModifier,
    )
    view.keyPressEvent(event_right)
    assert view.get_focus_node() == visible_ids[0]
    view.keyPressEvent(event_right)
    assert view.get_focus_node() != visible_ids[0]


def test_escape_clears_focus():
    db, proj, c1, *_ = _project_with_mentions()
    view = FocusGraphView(db, proj.id)
    view.focus_on(f"Character:{c1.id}")
    event_esc = QKeyEvent(
        QKeyEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier,
    )
    view.keyPressEvent(event_esc)
    assert view.get_focus_node() is None


def test_view_accepts_keyboard_focus():
    db, proj, *_ = _project_with_mentions()
    view = FocusGraphView(db, proj.id)
    assert view.focusPolicy() == Qt.FocusPolicy.StrongFocus


# -- 6. state persistence --------------------------------------------------

def test_capture_state_round_trip():
    db, proj, *_ = _project_with_mentions()
    view = FocusGraphView(db, proj.id)
    from logosforge.ui.focus_graph_view import MODE_THEME
    view.set_mode(MODE_THEME)
    view._on_gravity_toggled(False)
    view._on_flow_toggled(True)

    snap = view._capture_state()
    # New view, then apply snapshot.
    db2, proj2, *_ = _project_with_mentions()
    fresh = FocusGraphView(db2, proj2.id)
    fresh._apply_state(snap)

    assert fresh.get_mode() == MODE_THEME
    assert fresh.is_gravity_enabled() is False
    assert fresh.is_flow_enabled() is True


def test_persist_state_writes_to_settings():
    from logosforge.settings import get_manager
    db, proj, *_ = _project_with_mentions()
    view = FocusGraphView(db, proj.id)
    view._on_gravity_toggled(False)  # triggers _persist_state
    # Graph state is persisted under a per-project key.
    state = get_manager().get(view._graph_state_key())
    assert isinstance(state, dict)
    assert "gravity" in state
    assert state["gravity"] is False


def test_restore_persisted_state_no_op_when_empty():
    """An empty saved state must not corrupt a fresh view."""
    from logosforge.settings import get_manager
    get_manager().set("graph_state", {})
    db, proj, *_ = _project_with_mentions()
    view = FocusGraphView(db, proj.id)
    initial_count = view.get_visible_count()
    view.restore_persisted_state()
    # Visible count should be unchanged (no broken state applied).
    assert view.get_visible_count() == initial_count


# -- 7. saved presets ------------------------------------------------------

def test_save_and_load_preset():
    from logosforge.settings import get_manager
    # Start from clean preset store.
    get_manager().set("graph_presets", {})
    db, proj, *_ = _project_with_mentions()
    view = FocusGraphView(db, proj.id)
    from logosforge.ui.focus_graph_view import MODE_STRUCTURE
    view.set_mode(MODE_STRUCTURE)
    view._on_gravity_toggled(False)
    view.save_preset("My View")
    presets = view.get_saved_presets()
    assert "My View" in presets

    # Reset, then load the preset.
    db2, proj2, *_ = _project_with_mentions()
    fresh = FocusGraphView(db2, proj2.id)
    assert fresh.load_preset("My View") is True
    assert fresh.get_mode() == MODE_STRUCTURE
    assert fresh.is_gravity_enabled() is False

    # Cleanup.
    get_manager().set("graph_presets", {})


def test_load_unknown_preset_returns_false():
    from logosforge.settings import get_manager
    get_manager().set("graph_presets", {})
    db, proj, *_ = _project_with_mentions()
    view = FocusGraphView(db, proj.id)
    assert view.load_preset("ghost") is False


def test_delete_preset_removes_it():
    from logosforge.settings import get_manager
    get_manager().set("graph_presets", {})
    db, proj, *_ = _project_with_mentions()
    view = FocusGraphView(db, proj.id)
    view.save_preset("Temp")
    view.delete_preset("Temp")
    assert "Temp" not in view.get_saved_presets()


def test_save_preset_with_empty_name_is_noop():
    from logosforge.settings import get_manager
    get_manager().set("graph_presets", {})
    db, proj, *_ = _project_with_mentions()
    view = FocusGraphView(db, proj.id)
    view.save_preset("")
    assert view.get_saved_presets() == {}
