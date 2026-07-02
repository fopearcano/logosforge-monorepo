"""Canvas Plot — a free, zoomable, pannable visual plotting board.

A calm dark-mode thinking canvas (not a table / not a timeline): blocks placed
anywhere, moved, coloured, connected with lines, and grouped with light visual
frames. Everything is owned per project by dedicated stores (CanvasPlotNode /
CanvasPlotLink / CanvasPlotFrame) — never derived from Timeline or scene order.
The view transform (zoom / centre) is remembered per project.

Built on QGraphicsView / QGraphicsScene / QGraphicsItem.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QLineF, QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QPainter,
    QPainterPath,
    QPainterPathStroker,
    QPen,
)
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGraphicsItem,
    QGraphicsLineItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from logosforge.db import Database
from logosforge.ui import theme
from logosforge.ui.color_labels import COLOR_LABELS, build_color_menu, color_hex

_SCENE_HALF = 6000
_MIN_ZOOM = 0.25
_MAX_ZOOM = 4.0
_DEF_W = 188.0
_DEF_H = 116.0
_FRAME_TITLE_H = 26.0
_SETTINGS_KEY = "canvas_plot_view"
_Z_FRAME = -2.0
_Z_LINK = -1.0


# ===========================================================================
# Block item
# ===========================================================================


class _BlockItem(QGraphicsItem):
    """A movable, selectable card representing one CanvasPlotNode."""

    def __init__(self, node, owner: "CanvasPlotView") -> None:
        super().__init__()
        self._node = node
        self.node_id = node.id
        self._owner = owner
        self._w = float(node.width or _DEF_W)
        self._h = float(node.height or _DEF_H)
        self.setZValue(float(node.sort_order or 0))
        self.setPos(float(node.x), float(node.y))
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        self.setAcceptHoverEvents(True)
        self._press_scene_pos: QPointF | None = None

    def boundingRect(self) -> QRectF:
        return QRectF(0, 0, self._w, self._h)

    def center_scene(self) -> QPointF:
        return self.scenePos() + QPointF(self._w / 2, self._h / 2)

    def paint(self, painter: QPainter, option, widget=None) -> None:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(1, 1, self._w - 2, self._h - 2)
        selected = self.isSelected()
        painter.setBrush(QColor(theme.CARD_BG))
        painter.setPen(QPen(
            QColor(theme.ACCENT if selected else theme.CARD_BORDER),
            2 if selected else 1,
        ))
        painter.drawRoundedRect(rect, 8, 8)

        stripe = color_hex(getattr(self._node, "color_label", ""))
        if stripe:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(stripe))
            painter.drawRoundedRect(QRectF(2, 2, 5, self._h - 4), 3, 3)

        left = 14
        title = (self._node.title or "Untitled").strip() or "Untitled"
        tf = QFont(painter.font()); tf.setPointSize(10); tf.setBold(True)
        painter.setFont(tf)
        painter.setPen(QColor(theme.TEXT_PRIMARY))
        trect = QRectF(left, 8, self._w - left - 8, 18)
        painter.drawText(
            trect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            QFontMetrics(tf).elidedText(title, Qt.TextElideMode.ElideRight,
                                        int(trect.width())),
        )

        body = (self._node.body or "").strip()
        if body:
            bf = QFont(painter.font()); bf.setPointSize(8); bf.setBold(False)
            painter.setFont(bf)
            painter.setPen(QColor(theme.TEXT_SECONDARY))
            brect = QRectF(left, 28, self._w - left - 8, self._h - 28 - 18)
            painter.drawText(
                brect,
                int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
                    | Qt.TextFlag.TextWordWrap),
                body,
            )

        cat = (self._node.group_label or "").strip()
        if cat:
            cf = QFont(painter.font()); cf.setPointSize(8); cf.setBold(False)
            painter.setFont(cf)
            painter.setPen(QColor(theme.TEXT_MUTED))
            crect = QRectF(left, self._h - 18, self._w - left - 8, 14)
            painter.drawText(
                crect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                QFontMetrics(cf).elidedText("# " + cat, Qt.TextElideMode.ElideRight,
                                            int(crect.width())),
            )

    def itemChange(self, change, value):
        if (change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged
                and not self._owner._building):
            self._owner._on_block_moved(self.node_id)
        return super().itemChange(change, value)

    def mousePressEvent(self, event) -> None:
        self._press_scene_pos = self.scenePos()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        super().mouseReleaseEvent(event)
        if self._press_scene_pos is not None and self.scenePos() != self._press_scene_pos:
            self._owner._persist_position(self.node_id, self.x(), self.y())
        self._press_scene_pos = None

    def mouseDoubleClickEvent(self, event) -> None:
        self._owner._edit_block(self.node_id)

    def contextMenuEvent(self, event) -> None:
        self._owner._block_menu(self.node_id, event.screenPos())


# ===========================================================================
# Connection line item
# ===========================================================================


class _LinkItem(QGraphicsLineItem):
    """A connection line between two blocks (rendered behind the cards)."""

    def __init__(self, link, owner: "CanvasPlotView") -> None:
        super().__init__()
        self.link_id = link.id
        self._link = link
        self._owner = owner
        self.setZValue(_Z_LINK)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self._color = QColor(color_hex(link.color_label) or theme.TEXT_MUTED)

    def set_color_key(self, key: str) -> None:
        self._color = QColor(color_hex(key) or theme.TEXT_MUTED)
        self.update()

    def boundingRect(self) -> QRectF:
        return super().boundingRect().adjusted(-12, -18, 12, 18)

    def shape(self) -> QPainterPath:
        path = QPainterPath()
        path.moveTo(self.line().p1())
        path.lineTo(self.line().p2())
        stroker = QPainterPathStroker()
        stroker.setWidth(12)
        return stroker.createStroke(path)

    def paint(self, painter: QPainter, option, widget=None) -> None:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        selected = self.isSelected()
        pen = QPen(QColor(theme.ACCENT) if selected else self._color,
                   3 if selected else 2)
        painter.setPen(pen)
        painter.drawLine(self.line())
        label = (self._link.label or "").strip()
        if label:
            mid = self.line().pointAt(0.5)
            f = QFont(painter.font()); f.setPointSize(8)
            painter.setFont(f)
            painter.setPen(QColor(theme.TEXT_SECONDARY))
            painter.drawText(QPointF(mid.x() + 4, mid.y() - 4), label)

    def contextMenuEvent(self, event) -> None:
        self._owner._link_menu(self.link_id, event.screenPos())


# ===========================================================================
# Frame item (lightweight visual group)
# ===========================================================================


class _FrameItem(QGraphicsRectItem):
    """A titled, coloured, movable frame drawn behind the blocks.

    Only the title strip is interactive (movable / clickable) so the body lets
    mouse events pass through to the canvas for panning and to the blocks above.
    """

    def __init__(self, frame, owner: "CanvasPlotView") -> None:
        super().__init__(0, 0, float(frame.width), float(frame.height))
        self.frame_id = frame.id
        self._frame = frame
        self._owner = owner
        self.setZValue(_Z_FRAME)
        self.setPos(float(frame.x), float(frame.y))
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        self._press_scene_pos: QPointF | None = None

    def shape(self) -> QPainterPath:
        # Interactive region = title strip only (body passes events through).
        path = QPainterPath()
        path.addRect(QRectF(0, 0, self.rect().width(), _FRAME_TITLE_H))
        return path

    def paint(self, painter: QPainter, option, widget=None) -> None:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = self.rect()
        base = color_hex(getattr(self._frame, "color_label", "")) or theme.TEXT_MUTED
        col = QColor(base)
        fill = QColor(col); fill.setAlpha(26)
        border = QColor(col); border.setAlpha(140)
        painter.setBrush(fill)
        painter.setPen(QPen(border, 2 if self.isSelected() else 1))
        painter.drawRoundedRect(rect.adjusted(1, 1, -1, -1), 10, 10)
        # Title strip.
        title = (self._frame.title or "Frame").strip() or "Frame"
        strip = QColor(col); strip.setAlpha(60)
        painter.setBrush(strip); painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(QRectF(1, 1, rect.width() - 2, _FRAME_TITLE_H), 8, 8)
        f = QFont(painter.font()); f.setPointSize(9); f.setBold(True)
        painter.setFont(f)
        painter.setPen(QColor(theme.TEXT_PRIMARY))
        painter.drawText(
            QRectF(10, 1, rect.width() - 16, _FRAME_TITLE_H),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            QFontMetrics(f).elidedText(title, Qt.TextElideMode.ElideRight,
                                       int(rect.width() - 16)),
        )

    def mousePressEvent(self, event) -> None:
        self._press_scene_pos = self.scenePos()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        super().mouseReleaseEvent(event)
        if self._press_scene_pos is not None and self.scenePos() != self._press_scene_pos:
            self._owner._persist_frame_position(self.frame_id, self.x(), self.y())
        self._press_scene_pos = None

    def contextMenuEvent(self, event) -> None:
        self._owner._frame_menu(self.frame_id, event.screenPos())


# ===========================================================================
# Board view (zoom + pan)
# ===========================================================================


class _BoardView(QGraphicsView):
    def __init__(self, scene: QGraphicsScene, owner: "CanvasPlotView") -> None:
        super().__init__(scene)
        self._owner = owner
        self._panning = False
        self._pan_last = None
        self.setRenderHints(
            QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing
            | QPainter.RenderHint.SmoothPixmapTransform
        )
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setBackgroundBrush(QColor(theme.BG_DARK))

    def wheelEvent(self, event) -> None:
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        self._owner._apply_zoom_factor(factor)
        event.accept()

    def mousePressEvent(self, event) -> None:
        if (event.button() == Qt.MouseButton.LeftButton
                and self.itemAt(event.pos()) is None):
            self._panning = True
            self._pan_last = event.pos()
            self.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)
            self.scene().clearSelection()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._panning and self._pan_last is not None:
            delta = event.pos() - self._pan_last
            self._pan_last = event.pos()
            h = self.horizontalScrollBar(); v = self.verticalScrollBar()
            h.setValue(h.value() - delta.x()); v.setValue(v.value() - delta.y())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if self._panning:
            self._panning = False
            self.viewport().setCursor(Qt.CursorShape.ArrowCursor)
            self._owner._save_view_state()
            event.accept()
            return
        super().mouseReleaseEvent(event)


# ===========================================================================
# Dialogs
# ===========================================================================


class _BlockEditDialog(QDialog):
    def __init__(self, node, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Edit block")
        self.setMinimumWidth(360)
        form = QFormLayout(self)
        self._title = QLineEdit(node.title or "")
        form.addRow("Title", self._title)
        self._body = QPlainTextEdit(node.body or "")
        self._body.setMaximumHeight(120)
        form.addRow("Summary", self._body)
        self._category = QLineEdit(node.group_label or "")
        self._category.setPlaceholderText("e.g. theme, subplot, idea…")
        form.addRow("Category", self._category)
        self._color = QComboBox()
        for key, label in COLOR_LABELS.items():
            self._color.addItem(label, key)
        idx = self._color.findData(node.color_label or "")
        if idx >= 0:
            self._color.setCurrentIndex(idx)
        form.addRow("Colour", self._color)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def values(self) -> dict:
        return {
            "title": self._title.text().strip(),
            "body": self._body.toPlainText().strip(),
            "group_label": self._category.text().strip(),
            "color_label": self._color.currentData() or "",
        }


class _FrameEditDialog(QDialog):
    def __init__(self, frame, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Edit frame")
        self.setMinimumWidth(340)
        form = QFormLayout(self)
        self._title = QLineEdit(frame.title or "")
        form.addRow("Title", self._title)
        self._color = QComboBox()
        for key, label in COLOR_LABELS.items():
            self._color.addItem(label, key)
        idx = self._color.findData(frame.color_label or "")
        if idx >= 0:
            self._color.setCurrentIndex(idx)
        form.addRow("Colour", self._color)
        self._w = QLineEdit(str(int(frame.width)))
        form.addRow("Width", self._w)
        self._h = QLineEdit(str(int(frame.height)))
        form.addRow("Height", self._h)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def _num(self, edit, default) -> float:
        try:
            return max(80.0, float(edit.text()))
        except ValueError:
            return default

    def values(self) -> dict:
        return {
            "title": self._title.text().strip(),
            "color_label": self._color.currentData() or "",
            "width": self._num(self._w, 360.0),
            "height": self._num(self._h, 260.0),
        }


# ===========================================================================
# Canvas Plot view
# ===========================================================================


class CanvasPlotView(QWidget):
    """Free zoomable/pannable plotting board with links + frames, per project."""

    def __init__(
        self,
        db: Database,
        project_id: int,
        on_data_changed: Callable[[], None] | None = None,
    ) -> None:
        super().__init__()
        self._db = db
        self._project_id = project_id
        self._on_data_changed = on_data_changed
        self._zoom = 1.0
        self._building = False
        self._items: dict[int, _BlockItem] = {}
        self._link_items: dict[int, _LinkItem] = {}
        self._frame_items: dict[int, _FrameItem] = {}
        self._links: list = []
        self._pending_source: int | None = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(6)
        outer.addLayout(self._build_toolbar())

        self._scene = QGraphicsScene(self)
        self._scene.setSceneRect(-_SCENE_HALF, -_SCENE_HALF,
                                 _SCENE_HALF * 2, _SCENE_HALF * 2)
        self._view = _BoardView(self._scene, self)
        outer.addWidget(self._view, stretch=1)
        self.refresh()

    # -- toolbar (compact dropdown menus) -----------------------------------

    def _menu_button(self, text: str, actions: list) -> QToolButton:
        btn = QToolButton()
        btn.setText(text)
        btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(btn)
        for entry in actions:
            if entry is None:
                menu.addSeparator()
            else:
                label, slot = entry
                menu.addAction(label, slot)
        btn.setMenu(menu)
        btn.setStyleSheet(
            f"QToolButton {{ color: {theme.TEXT_PRIMARY}; background: {theme.BG_PANEL};"
            f" border: 1px solid {theme.BORDER}; border-radius: 4px;"
            f" padding: 3px 8px; }}"
            f"QToolButton::menu-indicator {{ width: 0px; }}"
        )
        return btn

    def _build_toolbar(self) -> QHBoxLayout:
        bar = QHBoxLayout()
        bar.setSpacing(6)
        title = QLabel("Canvas Plot")
        title.setStyleSheet(
            f"color: {theme.TEXT_PRIMARY}; font-size: 14px; font-weight: 700;")
        bar.addWidget(title)

        bar.addWidget(self._menu_button("View ▾", [
            ("Zoom In", lambda: self._apply_zoom_factor(1.15)),
            ("Zoom Out", lambda: self._apply_zoom_factor(1 / 1.15)),
            ("Reset View", self.reset_view),
            ("Fit Content", self.fit_content),
        ]))
        bar.addWidget(self._menu_button("Add ▾", [
            ("New Block", self._new_block),
            ("New Frame / Group", self._new_frame),
        ]))
        bar.addWidget(self._menu_button("Arrange ▾", [
            ("Bring Forward", self._bring_forward),
            ("Send Back", self._send_back),
        ]))
        bar.addWidget(self._menu_button("Connect ▾", [
            ("Create Link from Selected…", self._connect_from_selected),
            ("Cancel Connection", self._cancel_connection),
        ]))

        bar.addStretch()
        self._status = QLabel("")
        self._status.setStyleSheet(f"color: {theme.ACCENT}; font-size: 10px;")
        bar.addWidget(self._status)

        zoom_out = QPushButton("−"); zoom_out.setFixedWidth(28)
        zoom_out.clicked.connect(lambda: self._apply_zoom_factor(1 / 1.15))
        bar.addWidget(zoom_out)
        self._zoom_label = QPushButton("100%"); self._zoom_label.setFixedWidth(56)
        self._zoom_label.setFlat(True)
        self._zoom_label.clicked.connect(self._zoom_to_100)
        self._zoom_label.setStyleSheet(
            f"QPushButton {{ color: {theme.TEXT_SECONDARY}; border: none; }}")
        bar.addWidget(self._zoom_label)
        zoom_in = QPushButton("+"); zoom_in.setFixedWidth(28)
        zoom_in.clicked.connect(lambda: self._apply_zoom_factor(1.15))
        bar.addWidget(zoom_in)
        return bar

    # -- load / rebuild -----------------------------------------------------

    def refresh(self) -> None:
        h = self._view.horizontalScrollBar().value()
        v = self._view.verticalScrollBar().value()
        self._building = True
        self._scene.clear()
        self._items.clear(); self._link_items.clear(); self._frame_items.clear()

        for frame in self._db.get_canvas_plot_frames(self._project_id):
            item = _FrameItem(frame, self)
            self._scene.addItem(item)
            self._frame_items[frame.id] = item

        for node in self._db.get_canvas_plot_nodes(self._project_id):
            item = _BlockItem(node, self)
            self._scene.addItem(item)
            self._items[node.id] = item

        self._links = self._db.get_canvas_plot_links(self._project_id)
        for link in self._links:
            item = _LinkItem(link, self)
            self._scene.addItem(item)
            self._link_items[link.id] = item
        self._rebuild_all_link_geometry()

        self._building = False
        self._restore_view_state()
        self._view.horizontalScrollBar().setValue(h)
        self._view.verticalScrollBar().setValue(v)
        self._update_zoom_label()

    # -- block CRUD ---------------------------------------------------------

    def _next_sort_order(self) -> int:
        nodes = self._db.get_canvas_plot_nodes(self._project_id)
        return max([n.sort_order for n in nodes], default=0) + 1

    def _new_block(self) -> None:
        centre = self._view.mapToScene(self._view.viewport().rect().center())
        n = len(self._items)
        off = (n % 6) * 26
        node = self._db.create_canvas_plot_node(
            self._project_id, title="New block",
            x=centre.x() - _DEF_W / 2 + off, y=centre.y() - _DEF_H / 2 + off,
            width=_DEF_W, height=_DEF_H,
        )
        self.refresh()
        self._select_only(node.id)
        self._touch()

    def _get_node(self, node_id: int):
        return next((n for n in self._db.get_canvas_plot_nodes(self._project_id)
                     if n.id == node_id), None)

    def _edit_block(self, node_id: int) -> None:
        node = self._get_node(node_id)
        if node is None:
            return
        dlg = _BlockEditDialog(node, parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        vals = dlg.values()
        self._db.update_canvas_plot_node(
            node_id, title=vals["title"], body=vals["body"],
            group_label=vals["group_label"], color_label=vals["color_label"])
        self.refresh(); self._select_only(node_id); self._touch()

    def _block_menu(self, node_id: int, global_pos) -> None:
        menu = QMenu(self)
        menu.addAction("Edit…", lambda: self._edit_block(node_id))
        node = self._items.get(node_id)
        cur = node._node.color_label if node else ""
        build_color_menu(menu, cur, lambda key: self._set_block_color(node_id, key))
        menu.addSeparator()
        if self._pending_source is None:
            menu.addAction("Start connection from here",
                           lambda: self._start_connection(node_id))
        elif self._pending_source != node_id:
            link_menu = QMenu("Connect to here", menu)
            build_color_menu(link_menu, "gray",
                             lambda key: self._finish_connection(node_id, key),
                             title="Line colour")
            menu.addMenu(link_menu)
            menu.addAction("Cancel connection", self._cancel_connection)
        menu.addSeparator()
        menu.addAction("Bring Forward", lambda: self._bring_forward(node_id))
        menu.addAction("Send Back", lambda: self._send_back(node_id))
        menu.addSeparator()
        menu.addAction("Delete block…", lambda: self._delete_block(node_id))
        menu.exec(global_pos)

    def _set_block_color(self, node_id: int, key: str) -> None:
        self._db.update_canvas_plot_node(node_id, color_label=key)
        self.refresh(); self._touch()

    def _delete_block(self, node_id: int) -> None:
        answer = QMessageBox.question(
            self, "Delete block",
            "Delete this block and its connections? This cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._db.delete_canvas_plot_node(node_id)
        self.refresh(); self._touch()

    def _persist_position(self, node_id: int, x: float, y: float) -> None:
        self._db.update_canvas_plot_node(node_id, x=float(x), y=float(y))

    def _select_only(self, node_id: int) -> None:
        self._scene.clearSelection()
        item = self._items.get(node_id)
        if item is not None:
            item.setSelected(True)

    def _selected_block_id(self) -> int | None:
        for nid, item in self._items.items():
            if item.isSelected():
                return nid
        return None

    # -- arrange (z-order) --------------------------------------------------

    def _bring_forward(self, node_id: int | None = None) -> None:
        node_id = node_id or self._selected_block_id()
        if node_id is None:
            return
        self._db.update_canvas_plot_node(node_id, sort_order=self._next_sort_order())
        self.refresh(); self._select_only(node_id); self._touch()

    def _send_back(self, node_id: int | None = None) -> None:
        node_id = node_id or self._selected_block_id()
        if node_id is None:
            return
        nodes = self._db.get_canvas_plot_nodes(self._project_id)
        lowest = min([n.sort_order for n in nodes], default=0) - 1
        self._db.update_canvas_plot_node(node_id, sort_order=lowest)
        self.refresh(); self._select_only(node_id); self._touch()

    # -- connections --------------------------------------------------------

    def _connect_from_selected(self) -> None:
        nid = self._selected_block_id()
        if nid is None:
            self._status.setText("Select a block first, then Create Link.")
            return
        self._start_connection(nid)

    def _start_connection(self, node_id: int) -> None:
        self._pending_source = node_id
        node = self._items.get(node_id)
        title = (node._node.title if node else "") or "block"
        self._status.setText(f"Connecting from “{title}” — pick a target block")

    def _finish_connection(self, target_id: int, color_key: str) -> None:
        src = self._pending_source
        self._cancel_connection()
        if src is None:
            return
        self._db.add_canvas_plot_link(
            self._project_id, src, target_id, color_label=color_key or "gray")
        self.refresh(); self._touch()

    def _cancel_connection(self) -> None:
        self._pending_source = None
        self._status.setText("")

    def _link_menu(self, link_id: int, global_pos) -> None:
        menu = QMenu(self)
        link = next((l for l in self._links if l.id == link_id), None)
        cur = link.color_label if link else "gray"
        build_color_menu(menu, cur,
                         lambda key: self._set_link_color(link_id, key),
                         title="Line colour")
        menu.addAction("Edit label…", lambda: self._edit_link_label(link_id))
        menu.addSeparator()
        menu.addAction("Remove link", lambda: self._remove_link(link_id))
        menu.exec(global_pos)

    def _set_link_color(self, link_id: int, key: str) -> None:
        self._db.set_canvas_plot_link_color(link_id, key)
        self.refresh(); self._touch()

    def _edit_link_label(self, link_id: int) -> None:
        link = next((l for l in self._links if l.id == link_id), None)
        text, ok = QInputDialog.getText(
            self, "Link label", "Label:", text=(link.label if link else ""))
        if ok:
            self._db.set_canvas_plot_link_label(link_id, text.strip())
            self.refresh(); self._touch()

    def _remove_link(self, link_id: int) -> None:
        self._db.remove_canvas_plot_link(link_id)
        self.refresh(); self._touch()

    def _on_block_moved(self, node_id: int) -> None:
        for link in self._links:
            if node_id in (link.source_node_id, link.target_node_id):
                self._update_link_geometry(link)

    def _update_link_geometry(self, link) -> None:
        item = self._link_items.get(link.id)
        src = self._items.get(link.source_node_id)
        tgt = self._items.get(link.target_node_id)
        if item is None or src is None or tgt is None:
            return
        a = src.center_scene(); b = tgt.center_scene()
        item.setLine(QLineF(a, b))

    def _rebuild_all_link_geometry(self) -> None:
        for link in self._links:
            self._update_link_geometry(link)

    # -- frames -------------------------------------------------------------

    def _new_frame(self) -> None:
        centre = self._view.mapToScene(self._view.viewport().rect().center())
        n = len(self._frame_items)
        off = (n % 5) * 30
        frame = self._db.create_canvas_plot_frame(
            self._project_id, title="Group",
            x=centre.x() - 180 + off, y=centre.y() - 130 + off,
            width=360, height=260)
        self.refresh(); self._touch()

    def _frame_menu(self, frame_id: int, global_pos) -> None:
        menu = QMenu(self)
        menu.addAction("Edit…", lambda: self._edit_frame(frame_id))
        frame = next((f for f in self._db.get_canvas_plot_frames(self._project_id)
                      if f.id == frame_id), None)
        cur = frame.color_label if frame else ""
        build_color_menu(menu, cur, lambda key: self._set_frame_color(frame_id, key))
        menu.addSeparator()
        menu.addAction("Delete frame…", lambda: self._delete_frame(frame_id))
        menu.exec(global_pos)

    def _edit_frame(self, frame_id: int) -> None:
        frame = next((f for f in self._db.get_canvas_plot_frames(self._project_id)
                      if f.id == frame_id), None)
        if frame is None:
            return
        dlg = _FrameEditDialog(frame, parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        vals = dlg.values()
        self._db.update_canvas_plot_frame(
            frame_id, title=vals["title"], color_label=vals["color_label"],
            width=vals["width"], height=vals["height"])
        self.refresh(); self._touch()

    def _set_frame_color(self, frame_id: int, key: str) -> None:
        self._db.update_canvas_plot_frame(frame_id, color_label=key)
        self.refresh(); self._touch()

    def _delete_frame(self, frame_id: int) -> None:
        answer = QMessageBox.question(
            self, "Delete frame",
            "Delete this frame? The blocks inside are NOT deleted.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._db.delete_canvas_plot_frame(frame_id)
        self.refresh(); self._touch()

    def _persist_frame_position(self, frame_id: int, x: float, y: float) -> None:
        self._db.update_canvas_plot_frame(frame_id, x=float(x), y=float(y))

    # -- notify -------------------------------------------------------------

    def _touch(self) -> None:
        if self._on_data_changed:
            self._on_data_changed()

    # -- zoom / view state --------------------------------------------------

    def _apply_zoom_factor(self, factor: float) -> None:
        new = max(_MIN_ZOOM, min(_MAX_ZOOM, self._zoom * factor))
        actual = new / self._zoom if self._zoom else 1.0
        if abs(actual - 1.0) < 1e-6:
            return
        self._view.scale(actual, actual)
        self._zoom = new
        self._update_zoom_label(); self._save_view_state()

    def _zoom_to_100(self) -> None:
        if self._zoom:
            self._view.scale(1.0 / self._zoom, 1.0 / self._zoom)
        self._zoom = 1.0
        self._update_zoom_label(); self._save_view_state()

    def reset_view(self) -> None:
        self._zoom_to_100()
        if self._items or self._frame_items:
            self._view.centerOn(self._scene.itemsBoundingRect().center())
        else:
            self._view.centerOn(0, 0)
        self._save_view_state()

    def fit_content(self) -> None:
        if not (self._items or self._frame_items):
            self.reset_view(); return
        rect = self._scene.itemsBoundingRect().adjusted(-40, -40, 40, 40)
        self._view.fitInView(rect, Qt.AspectRatioMode.KeepAspectRatio)
        self._zoom = max(_MIN_ZOOM, min(_MAX_ZOOM, self._view.transform().m11()))
        self._update_zoom_label(); self._save_view_state()

    def _update_zoom_label(self) -> None:
        self._zoom_label.setText(f"{int(round(self._zoom * 100))}%")

    def _save_view_state(self) -> None:
        centre = self._view.mapToScene(self._view.viewport().rect().center())
        settings = self._db.get_project_settings(self._project_id)
        settings[_SETTINGS_KEY] = {"zoom": self._zoom, "cx": centre.x(),
                                   "cy": centre.y()}
        self._db.save_project_settings(self._project_id, settings)

    def _restore_view_state(self) -> None:
        state = self._db.get_project_settings(self._project_id).get(_SETTINGS_KEY)
        if not isinstance(state, dict):
            return
        zoom = max(_MIN_ZOOM, min(_MAX_ZOOM, float(state.get("zoom", 1.0) or 1.0)))
        if self._zoom:
            self._view.scale(zoom / self._zoom, zoom / self._zoom)
        self._zoom = zoom
        cx, cy = state.get("cx"), state.get("cy")
        if cx is not None and cy is not None:
            self._view.centerOn(float(cx), float(cy))
