"""Relationship graph view — visual overview of [[link]] connections."""

import math
from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QFont, QPen
from PySide6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsLineItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsView,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from logosforge.db import Database
from logosforge.ui import theme

TYPE_COLORS = {
    "Character": QColor("#42a5f5"),
    "Place": QColor("#66bb6a"),
    "Scene": QColor("#ffa726"),
    "Note": QColor("#ab47bc"),
}
NODE_RADIUS = 24
GRAPH_RADIUS = 220
EDGE_COLOR = QColor("#4a5568")


class GraphView(QWidget):
    def __init__(
        self,
        db: Database,
        project_id: int,
        on_node_clicked: Callable[[str, int], None] | None = None,
    ) -> None:
        super().__init__()
        self._db = db
        self._project_id = project_id
        self._on_node_clicked = on_node_clicked

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Relationship Graph"))

        # Phase 9B — surface the active project writing mode (read fresh at
        # construction; the view is rebuilt on project switch, so no stale
        # mode). Read-only reflection of Project.narrative_engine — never a
        # second source of truth.
        try:
            from logosforge.writing_modes import (
                get_project_writing_mode,
                mode_label,
            )
            _mode = get_project_writing_mode(db.get_project_by_id(project_id))
            self._mode_label = QLabel(f"Mode: {mode_label(_mode)}")
            self._mode_label.setObjectName("graphModeChip")
            layout.addWidget(self._mode_label)
        except Exception:
            pass

        self._legend = QLabel(self._build_legend())
        layout.addWidget(self._legend)

        self._scene = QGraphicsScene()
        self._view = QGraphicsView(self._scene)
        self._view.setRenderHints(
            self._view.renderHints()
        )
        layout.addWidget(self._view)

        self._node_items: dict[str, tuple[str, int, float, float]] = {}
        self._build_graph()

    def _build_legend(self) -> str:
        parts = []
        for etype, color in TYPE_COLORS.items():
            parts.append(
                f'<span style="color: {color.name()};">●</span> {etype}'
            )
        return "  ".join(parts)

    def refresh(self) -> None:
        self._scene.clear()
        self._node_items.clear()
        self._build_graph()

    def _build_graph(self) -> None:
        nodes, edges = self._db.build_link_graph(self._project_id)

        if not nodes:
            text = self._scene.addSimpleText("No [[links]] found between entities.")
            text.setPos(0, 0)
            return

        positions = self._compute_positions(len(nodes))

        name_to_pos: dict[str, tuple[float, float]] = {}
        for i, (etype, eid, name) in enumerate(nodes):
            x, y = positions[i]
            name_to_pos[name.lower()] = (x, y)
            self._add_node(x, y, name, etype, eid)

        edge_pen = QPen(EDGE_COLOR, 1.5)
        for source_name, target_name in edges:
            src = name_to_pos.get(source_name.lower())
            tgt = name_to_pos.get(target_name.lower())
            if src and tgt:
                line = QGraphicsLineItem(src[0], src[1], tgt[0], tgt[1])
                line.setPen(edge_pen)
                line.setZValue(-1)
                self._scene.addItem(line)

    def _compute_positions(self, count: int) -> list[tuple[float, float]]:
        if count == 1:
            return [(0.0, 0.0)]
        radius = max(GRAPH_RADIUS, count * 20)
        positions = []
        for i in range(count):
            angle = 2 * math.pi * i / count - math.pi / 2
            x = radius * math.cos(angle)
            y = radius * math.sin(angle)
            positions.append((x, y))
        return positions

    def _add_node(
        self, x: float, y: float, name: str, etype: str, eid: int
    ) -> None:
        color = TYPE_COLORS.get(etype, QColor("#9e9e9e"))

        circle = _ClickableEllipse(
            x - NODE_RADIUS, y - NODE_RADIUS,
            NODE_RADIUS * 2, NODE_RADIUS * 2,
            on_click=lambda: self._on_click(etype, eid),
        )
        circle.setBrush(QBrush(color))
        circle.setPen(QPen(color.darker(120), 2))
        circle.setZValue(1)
        circle.setCursor(Qt.CursorShape.PointingHandCursor)
        self._scene.addItem(circle)

        label = QGraphicsSimpleTextItem(name)
        font = QFont()
        font.setPointSize(9)
        label.setFont(font)
        label.setBrush(QBrush(QColor(theme.TEXT_PRIMARY)))
        label_rect = label.boundingRect()
        label.setPos(x - label_rect.width() / 2, y + NODE_RADIUS + 4)
        label.setZValue(2)
        self._scene.addItem(label)

        type_label = QGraphicsSimpleTextItem(etype[0])
        type_font = QFont()
        type_font.setPointSize(10)
        type_font.setBold(True)
        type_label.setFont(type_font)
        type_label.setBrush(QBrush(QColor("#ffffff")))
        tr = type_label.boundingRect()
        type_label.setPos(x - tr.width() / 2, y - tr.height() / 2)
        type_label.setZValue(2)
        self._scene.addItem(type_label)

    def _on_click(self, etype: str, eid: int) -> None:
        if self._on_node_clicked:
            self._on_node_clicked(etype, eid)


class _ClickableEllipse(QGraphicsEllipseItem):
    def __init__(
        self, x: float, y: float, w: float, h: float,
        on_click: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(x, y, w, h)
        self._on_click = on_click

    def mousePressEvent(self, event) -> None:
        if self._on_click and event.button() == Qt.MouseButton.LeftButton:
            self._on_click()
        super().mousePressEvent(event)
