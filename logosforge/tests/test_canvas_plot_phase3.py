"""Phase 3: Canvas Plot connections, colours, frames, arrange — persistence."""

from __future__ import annotations

import warnings

import pytest
from PySide6.QtWidgets import QApplication

warnings.filterwarnings("ignore")

from logosforge.db import Database
from logosforge.ui.canvas_plot_view import CanvasPlotView, _LinkItem, _FrameItem


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    app = QApplication.instance() or QApplication([])
    yield app


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


def _board_with_blocks(n=3):
    db = Database()
    pid = db.create_project("P").id
    view = CanvasPlotView(db, pid)
    for _ in range(n):
        view._new_block()
    return db, pid, view, list(view._items.keys())


# ==========================================================================
# DB layer
# ==========================================================================


def test_link_dedup_reverse_and_self_reject():
    db = Database()
    pid = db.create_project("P").id
    a = db.create_canvas_plot_node(pid, title="A").id
    b = db.create_canvas_plot_node(pid, title="B").id
    l1 = db.add_canvas_plot_link(pid, a, b)
    assert db.add_canvas_plot_link(pid, b, a).id == l1.id   # reverse dup
    assert db.add_canvas_plot_link(pid, a, a) is None        # self


def test_delete_block_cascades_links_only():
    db = Database()
    pid = db.create_project("P").id
    a = db.create_canvas_plot_node(pid, title="A").id
    b = db.create_canvas_plot_node(pid, title="B").id
    db.add_canvas_plot_link(pid, a, b)
    db.delete_canvas_plot_node(a)
    assert db.get_canvas_plot_links(pid) == []          # link gone
    assert len(db.get_canvas_plot_nodes(pid)) == 1      # B kept


def test_remove_link_keeps_blocks():
    db = Database()
    pid = db.create_project("P").id
    a = db.create_canvas_plot_node(pid, title="A").id
    b = db.create_canvas_plot_node(pid, title="B").id
    link = db.add_canvas_plot_link(pid, a, b)
    db.remove_canvas_plot_link(link.id)
    assert db.get_canvas_plot_links(pid) == []
    assert len(db.get_canvas_plot_nodes(pid)) == 2


# ==========================================================================
# Colours
# ==========================================================================


def test_block_color_persists():
    db, pid, view, ids = _board_with_blocks(1)
    view._set_block_color(ids[0], "violet")
    assert db.get_canvas_plot_nodes(pid)[0].color_label == "violet"


def test_link_color_and_label_persist():
    db, pid, view, ids = _board_with_blocks(2)
    view._start_connection(ids[0])
    view._finish_connection(ids[1], "blue")
    link = db.get_canvas_plot_links(pid)[0]
    assert link.color_label == "blue"
    view._set_link_color(link.id, "red")
    db.set_canvas_plot_link_label(link.id, "causes")
    view.refresh()
    link = db.get_canvas_plot_links(pid)[0]
    assert link.color_label == "red" and link.label == "causes"


# ==========================================================================
# Connections + live geometry
# ==========================================================================


def test_connect_flow_creates_link_and_item():
    db, pid, view, ids = _board_with_blocks(2)
    view._start_connection(ids[0])
    assert view._pending_source == ids[0]
    view._finish_connection(ids[1], "green")
    assert view._pending_source is None
    assert len(db.get_canvas_plot_links(pid)) == 1
    assert len(view._link_items) == 1
    assert all(isinstance(i, _LinkItem) for i in view._link_items.values())


def test_line_follows_block_when_moved():
    db, pid, view, ids = _board_with_blocks(2)
    view._start_connection(ids[0])
    view._finish_connection(ids[1], "green")
    link_id = db.get_canvas_plot_links(pid)[0].id
    before = view._link_items[link_id].line()
    # Move the target block; itemChange must update the line geometry live.
    view._items[ids[1]].setPos(900, 700)
    after = view._link_items[link_id].line()
    assert (before.p2().x(), before.p2().y()) != (after.p2().x(), after.p2().y())


def test_links_render_behind_blocks():
    db, pid, view, ids = _board_with_blocks(2)
    view._start_connection(ids[0]); view._finish_connection(ids[1], "green")
    link_item = next(iter(view._link_items.values()))
    block_item = view._items[ids[0]]
    assert link_item.zValue() < block_item.zValue()


# ==========================================================================
# Frames
# ==========================================================================


def test_frame_create_edit_color_persist():
    db = Database()
    pid = db.create_project("P").id
    view = CanvasPlotView(db, pid)
    view._new_frame()
    fid = next(iter(view._frame_items))
    db.update_canvas_plot_frame(fid, title="Act I", color_label="teal",
                                width=420, height=300)
    view.refresh()
    frame = db.get_canvas_plot_frames(pid)[0]
    assert frame.title == "Act I" and frame.color_label == "teal"
    assert frame.width == 420 and frame.height == 300
    assert isinstance(view._frame_items[frame.id], _FrameItem)


def test_delete_frame_keeps_blocks():
    db, pid, view, ids = _board_with_blocks(2)
    view._new_frame()
    fid = next(iter(view._frame_items))
    db.delete_canvas_plot_frame(fid)
    view.refresh()
    assert db.get_canvas_plot_frames(pid) == []
    assert len(db.get_canvas_plot_nodes(pid)) == 2     # blocks untouched


def test_frame_render_behind_links_and_blocks():
    db, pid, view, ids = _board_with_blocks(2)
    view._new_frame()
    view._start_connection(ids[0]); view._finish_connection(ids[1], "green")
    frame_item = next(iter(view._frame_items.values()))
    link_item = next(iter(view._link_items.values()))
    assert frame_item.zValue() < link_item.zValue()


# ==========================================================================
# Arrange (z-order)
# ==========================================================================


def test_bring_forward_and_send_back():
    db, pid, view, ids = _board_with_blocks(3)
    view._send_back(ids[2])
    orders = {n.id: n.sort_order for n in db.get_canvas_plot_nodes(pid)}
    assert orders[ids[2]] == min(orders.values())
    view._bring_forward(ids[2])
    orders = {n.id: n.sort_order for n in db.get_canvas_plot_nodes(pid)}
    assert orders[ids[2]] == max(orders.values())


# ==========================================================================
# Independence from Timeline
# ==========================================================================


def test_canvas_plot_independent_of_timeline():
    db = Database()
    pid = db.create_project("P").id
    # Timeline data (scenes + lanes + timeline links).
    s1 = db.create_scene(pid, "S1", plotline="Main").id
    s2 = db.create_scene(pid, "S2", plotline="Main").id
    db.create_timeline_lane(pid, "Main")
    db.add_timeline_link(pid, s1, s2)
    # A fresh Canvas Plot is empty — Timeline events do NOT appear here.
    view = CanvasPlotView(db, pid)
    assert view._items == {}
    assert db.get_canvas_plot_nodes(pid) == []
    # Adding a Canvas block does not create scenes or timeline links.
    view._new_block()
    assert len(db.get_all_scenes(pid)) == 2            # unchanged
    assert len(db.get_timeline_links(pid)) == 1        # unchanged


# ==========================================================================
# Persistence: reload + project isolation
# ==========================================================================


def test_links_and_frames_reload(tmp_path):
    path = str(tmp_path / "c.db")
    db = Database(path)
    pid = db.create_project("P").id
    a = db.create_canvas_plot_node(pid, title="A").id
    b = db.create_canvas_plot_node(pid, title="B").id
    db.add_canvas_plot_link(pid, a, b, color_label="amber", label="echo")
    db.create_canvas_plot_frame(pid, title="Group", color_label="blue")
    db2 = Database(path)
    view = CanvasPlotView(db2, pid)
    assert len(view._link_items) == 1
    assert len(view._frame_items) == 1
    assert db2.get_canvas_plot_links(pid)[0].label == "echo"


def test_links_frames_project_scoped():
    db = Database()
    a = db.create_project("A").id
    b = db.create_project("B").id
    n1 = db.create_canvas_plot_node(a, title="A1").id
    n2 = db.create_canvas_plot_node(a, title="A2").id
    db.add_canvas_plot_link(a, n1, n2)
    db.create_canvas_plot_frame(a, title="A-frame")
    assert db.get_canvas_plot_links(b) == []
    assert db.get_canvas_plot_frames(b) == []
    view_b = CanvasPlotView(db, b)
    assert view_b._link_items == {} and view_b._frame_items == {}
