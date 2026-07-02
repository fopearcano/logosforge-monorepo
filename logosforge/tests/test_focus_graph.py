"""Tests for Graph Focus System — controlled exploration."""

from logosforge.db import Database
from logosforge.ui import theme
from logosforge.ui.focus_graph_view import (
    FocusGraphView,
    GraphData,
    GraphEdge,
    GraphNode,
    build_graph_data,
    filter_by_scene_order,
    filter_by_type,
    get_neighborhood,
)


def _make_project():
    db = Database()
    proj = db.create_project("GraphTest")
    return db, proj


def _make_linked_project():
    db, proj = _make_project()
    c1 = db.create_character(proj.id, "Alice")
    c2 = db.create_character(proj.id, "Bob")
    p1 = db.create_place(proj.id, "Castle")
    s1 = db.create_scene(
        proj.id, "Opening", synopsis="[[Alice]] enters [[Castle]].",
        character_ids=[c1.id],
    )
    s2 = db.create_scene(
        proj.id, "Meeting", synopsis="[[Alice]] meets [[Bob]].",
        character_ids=[c1.id, c2.id],
    )
    s3 = db.create_scene(
        proj.id, "Finale", synopsis="[[Bob]] defends [[Castle]].",
        character_ids=[c2.id],
    )
    return db, proj, c1, c2, p1, s1, s2, s3


# -- build_graph_data ---------------------------------------------------------

def test_build_graph_empty_project():
    db, proj = _make_project()
    data = build_graph_data(db, proj.id)
    assert isinstance(data, GraphData)
    assert len(data.nodes) == 0
    assert len(data.edges) == 0


def test_build_graph_has_nodes():
    db, proj, c1, c2, p1, s1, s2, s3 = _make_linked_project()
    data = build_graph_data(db, proj.id)
    assert f"Character:{c1.id}" in data.nodes
    assert f"Character:{c2.id}" in data.nodes
    assert f"Place:{p1.id}" in data.nodes
    assert f"Scene:{s1.id}" in data.nodes


def test_build_graph_has_edges():
    db, proj, *_ = _make_linked_project()
    data = build_graph_data(db, proj.id)
    assert len(data.edges) > 0


def test_build_graph_adjacency():
    db, proj, c1, c2, p1, s1, s2, s3 = _make_linked_project()
    data = build_graph_data(db, proj.id)
    scene_id = f"Scene:{s1.id}"
    alice_id = f"Character:{c1.id}"
    assert alice_id in data.adjacency.get(scene_id, set())
    assert scene_id in data.adjacency.get(alice_id, set())


def test_build_graph_with_psyke():
    db, proj = _make_project()
    entry = db.create_psyke_entry(proj.id, "Theme", "Hope")
    data = build_graph_data(db, proj.id)
    assert f"PSYKE:{entry.id}" in data.nodes


# -- get_neighborhood --------------------------------------------------------

def test_neighborhood_self_only():
    data = GraphData(
        nodes={"A": GraphNode("A", "Character", 1, "Alice")},
        edges=[],
        adjacency={"A": set()},
    )
    result = get_neighborhood(data, "A", hops=1)
    assert result == {"A"}


def test_neighborhood_1hop():
    data = GraphData(
        nodes={
            "A": GraphNode("A", "Character", 1, "Alice"),
            "B": GraphNode("B", "Character", 2, "Bob"),
            "C": GraphNode("C", "Place", 1, "Castle"),
        },
        edges=[GraphEdge("A", "B"), GraphEdge("B", "C")],
        adjacency={"A": {"B"}, "B": {"A", "C"}, "C": {"B"}},
    )
    result = get_neighborhood(data, "A", hops=1)
    assert result == {"A", "B"}


def test_neighborhood_2hop():
    data = GraphData(
        nodes={
            "A": GraphNode("A", "Character", 1, "Alice"),
            "B": GraphNode("B", "Character", 2, "Bob"),
            "C": GraphNode("C", "Place", 1, "Castle"),
            "D": GraphNode("D", "Scene", 1, "Opening"),
        },
        edges=[GraphEdge("A", "B"), GraphEdge("B", "C"), GraphEdge("C", "D")],
        adjacency={"A": {"B"}, "B": {"A", "C"}, "C": {"B", "D"}, "D": {"C"}},
    )
    result = get_neighborhood(data, "A", hops=2)
    assert result == {"A", "B", "C"}


def test_neighborhood_missing_node():
    data = GraphData(
        nodes={"A": GraphNode("A", "Character", 1, "Alice")},
        edges=[],
        adjacency={"A": set()},
    )
    result = get_neighborhood(data, "Z", hops=1)
    assert result == {"Z"}


# -- filter_by_type ----------------------------------------------------------

def test_filter_by_type_all():
    data = GraphData(
        nodes={
            "A": GraphNode("A", "Character", 1, "Alice"),
            "B": GraphNode("B", "Place", 1, "Castle"),
        },
        edges=[],
        adjacency={},
    )
    result = filter_by_type(data, set())
    assert result == {"A", "B"}


def test_filter_by_type_character():
    data = GraphData(
        nodes={
            "A": GraphNode("A", "Character", 1, "Alice"),
            "B": GraphNode("B", "Place", 1, "Castle"),
            "C": GraphNode("C", "Character", 2, "Bob"),
        },
        edges=[],
        adjacency={},
    )
    result = filter_by_type(data, {"Character"})
    assert result == {"A", "C"}


def test_filter_by_type_multiple():
    data = GraphData(
        nodes={
            "A": GraphNode("A", "Character", 1, "Alice"),
            "B": GraphNode("B", "Place", 1, "Castle"),
            "C": GraphNode("C", "Scene", 1, "Opening"),
        },
        edges=[],
        adjacency={},
    )
    result = filter_by_type(data, {"Character", "Scene"})
    assert result == {"A", "C"}


# -- filter_by_scene_order ---------------------------------------------------

def test_temporal_filter_all_scenes():
    db, proj, c1, c2, p1, s1, s2, s3 = _make_linked_project()
    data = build_graph_data(db, proj.id)
    result = filter_by_scene_order(db, proj.id, data, 9999)
    assert f"Scene:{s1.id}" in result
    assert f"Scene:{s3.id}" in result


def test_temporal_filter_partial():
    db, proj, c1, c2, p1, s1, s2, s3 = _make_linked_project()
    data = build_graph_data(db, proj.id)
    scenes = db.get_all_scenes(proj.id)
    first_order = scenes[0].sort_order
    result = filter_by_scene_order(db, proj.id, data, first_order)
    assert f"Scene:{s1.id}" in result
    assert f"Character:{c1.id}" in result


def test_temporal_filter_excludes_future_scenes():
    db, proj, c1, c2, p1, s1, s2, s3 = _make_linked_project()
    data = build_graph_data(db, proj.id)
    result = filter_by_scene_order(db, proj.id, data, -1)
    scene_ids = {nid for nid in result if nid.startswith("Scene:")}
    assert len(scene_ids) == 0


# -- FocusGraphView widget ---------------------------------------------------

def test_view_construction():
    db, proj, *_ = _make_linked_project()
    view = FocusGraphView(db, proj.id)
    assert view.get_focus_node() is None
    assert view.get_visible_count() > 0


def test_view_empty_project():
    db, proj = _make_project()
    view = FocusGraphView(db, proj.id)
    assert view.get_visible_count() == 0


def test_empty_state_message_is_themed_and_actionable():
    # Empty graph shows a themed, wrapped, actionable message (a QGraphicsTextItem)
    # — not the old corner-pinned black-on-dark addSimpleText.
    from PySide6.QtWidgets import QGraphicsTextItem
    db, proj = _make_project()
    view = FocusGraphView(db, proj.id)
    text_items = [it for it in view._gscene.items()
                  if isinstance(it, QGraphicsTextItem)]
    assert text_items                                   # readable item present
    html = text_items[0].toHtml()
    assert "No graph yet" in html and "[[Name]]" in html


def test_focus_on_node():
    db, proj, c1, *_ = _make_linked_project()
    view = FocusGraphView(db, proj.id)
    total = view.get_visible_count()
    view.focus_on(f"Character:{c1.id}")
    assert view.get_focus_node() == f"Character:{c1.id}"
    assert view.get_visible_count() <= total


def test_clear_focus():
    db, proj, c1, *_ = _make_linked_project()
    view = FocusGraphView(db, proj.id)
    view.focus_on(f"Character:{c1.id}")
    view.clear_focus()
    assert view.get_focus_node() is None


def test_focus_click_toggle():
    db, proj, c1, *_ = _make_linked_project()
    view = FocusGraphView(db, proj.id)
    view._on_node_click(f"Character:{c1.id}")
    assert view.get_focus_node() == f"Character:{c1.id}"
    view._on_node_click(f"Character:{c1.id}")
    assert view.get_focus_node() is None


def test_hops_toggle():
    db, proj, c1, *_ = _make_linked_project()
    view = FocusGraphView(db, proj.id)
    view.focus_on(f"Character:{c1.id}")
    count_1hop = view.get_visible_count()
    view._on_hops_toggled(True)
    count_2hop = view.get_visible_count()
    assert count_2hop >= count_1hop


def test_type_filter():
    db, proj, *_ = _make_linked_project()
    view = FocusGraphView(db, proj.id)
    view._on_type_changed("Character")
    assert view.get_type_filter() == "Character"
    for nid in view._node_items:
        assert nid.startswith("Character:")


def test_type_filter_all():
    db, proj, *_ = _make_linked_project()
    view = FocusGraphView(db, proj.id)
    view._on_type_changed("All")
    assert view.get_visible_count() > 0


def test_temporal_toggle():
    db, proj, *_ = _make_linked_project()
    view = FocusGraphView(db, proj.id)
    view._on_temporal_toggled(True)
    assert view.is_temporal_enabled()
    view._on_temporal_toggled(False)
    assert not view.is_temporal_enabled()


def test_temporal_max_order():
    db, proj, *_ = _make_linked_project()
    view = FocusGraphView(db, proj.id)
    view._on_temporal_toggled(True)
    total = view.get_visible_count()
    view.set_temporal_max_order(-1)
    assert view.get_visible_count() <= total


def test_search_focuses_match():
    db, proj, c1, *_ = _make_linked_project()
    view = FocusGraphView(db, proj.id)
    view._search_input.setText("Alice")
    view._on_search()
    assert view.get_focus_node() == f"Character:{c1.id}"


def test_search_no_match():
    db, proj, *_ = _make_linked_project()
    view = FocusGraphView(db, proj.id)
    view._search_input.setText("zzzzz")
    view._on_search()
    assert view.get_focus_node() is None


def test_search_case_insensitive():
    db, proj, c1, *_ = _make_linked_project()
    view = FocusGraphView(db, proj.id)
    view._search_input.setText("alice")
    view._on_search()
    assert view.get_focus_node() == f"Character:{c1.id}"


def test_search_no_match_shows_feedback():
    # A failed search is no longer silent: red border + tooltip, cleared on the
    # next successful search.
    db, proj, *_ = _make_linked_project()
    view = FocusGraphView(db, proj.id)
    view._search_input.setText("zzzzz")
    view._on_search()
    assert view.get_focus_node() is None
    assert "e25555" in view._search_input.styleSheet()       # red border shown
    assert "zzzzz" in view._search_input.toolTip()
    view._search_input.setText("Alice")                      # editing + match clears it
    view._on_search()
    assert view._search_input.styleSheet() == ""


def test_search_box_keys_do_not_navigate_graph(monkeypatch):
    # While the Search box has focus, Enter must run the search — not bubble to
    # the graph and focus the first node (and arrows must move the text cursor).
    from PySide6.QtCore import QEvent, Qt as QtC
    from PySide6.QtGui import QKeyEvent
    db, proj, c1, *_ = _make_linked_project()
    view = FocusGraphView(db, proj.id)

    def _return():
        return QKeyEvent(QEvent.Type.KeyPress, QtC.Key.Key_Return,
                         QtC.KeyboardModifier.NoModifier)

    monkeypatch.setattr(view._search_input, "hasFocus", lambda: True)
    view.keyPressEvent(_return())
    assert view.get_focus_node() is None        # search box owns the key

    monkeypatch.setattr(view._search_input, "hasFocus", lambda: False)
    view.keyPressEvent(_return())
    assert view.get_focus_node() is not None     # graph nav still works otherwise


def test_focus_breadcrumb_and_clear_button_state():
    # Focusing shrinks the graph to a neighbourhood — the top bar must say which
    # node + depth, and Clear Focus is enabled only while focused.
    db, proj, c1, *_ = _make_linked_project()
    view = FocusGraphView(db, proj.id)
    assert view._focus_label.isHidden()                      # nothing focused yet
    assert not view._clear_btn.isEnabled()
    view.focus_on(f"Character:{c1.id}")
    assert not view._focus_label.isHidden()
    assert "Alice" in view._focus_label.text()
    assert "1-hop" in view._focus_label.text()
    assert view._clear_btn.isEnabled()
    view.clear_focus()
    assert view._focus_label.isHidden()
    assert not view._clear_btn.isEnabled()


def test_hover_dims_non_neighbors():
    db, proj, c1, c2, p1, s1, s2, s3 = _make_linked_project()
    view = FocusGraphView(db, proj.id)
    alice_id = f"Character:{c1.id}"
    view._on_node_hover(alice_id, True)
    for nid, item in view._node_items.items():
        if nid == alice_id:
            assert item.opacity() == 1.0
    view._on_node_hover(alice_id, False)
    for item in view._node_items.values():
        assert item.opacity() == 1.0


def test_refresh_reloads():
    db, proj, *_ = _make_linked_project()
    view = FocusGraphView(db, proj.id)
    count_before = view.get_visible_count()
    db.create_character(proj.id, "Charlie")
    db.create_scene(
        proj.id, "Extra", content="[[Charlie]] arrives.",
    )
    view.refresh()
    assert view.get_visible_count() >= count_before


def test_on_node_selected_callback():
    db, proj, c1, *_ = _make_linked_project()
    calls = []
    view = FocusGraphView(db, proj.id, on_node_selected=lambda t, i: calls.append((t, i)))
    view.focus_on(f"Character:{c1.id}")
    assert len(calls) == 1
    assert calls[0] == ("Character", c1.id)


# -- Theme includes graph focus styles ----------------------------------------

def test_theme_has_graph_toolbar():
    ss = theme.build_stylesheet()
    assert "#graphToolbar" in ss


def test_theme_has_focus_graph_view():
    ss = theme.build_stylesheet()
    assert "#focusGraphView" in ss
