"""Graphic Novel — Page Canvas / Preview.

A read-mostly planning surface that renders a single GraphicNovelPage and
its GraphicNovelPanels as boxes laid out on a page rectangle. It is a
preview/planning canvas — NOT an image generator, thumbnail tool, or
drawing surface.

Data source is the same as the page/panel lists and editor: the live
GraphicNovelPage / GraphicNovelPanel rows via the existing db getters.
Layout is derived (splash flag + panel count); no layout schema is added.

Clicking a panel box reports the panel id through the on_panel_selected
callback so the host view can drive selection. Highlight + content are
re-rendered straight from the DB, so there is no independent stale state.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QFont, QFontMetrics, QPen
from PySide6.QtWidgets import (
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsView,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from logosforge.db import Database
from logosforge.ui import theme

# Page surface geometry (scene units ~ a 2:3 page).
_PAGE_W = 340.0
_PAGE_H = 510.0
_MARGIN = 16.0
_GUTTER = 10.0

# Subtle, dark-theme-friendly tones (neutral; selection uses the accent).
_PAGE_FILL = "#1f242c"
_PAGE_BORDER = "#3a4250"
_BOX_FILL = "#262d37"
_BOX_FILL_SEL = "#2f3a4a"
_BOX_BORDER = "#46506180"
_BOX_BORDER_SEL = "#5b9bd5"
_TEXT = "#cbd5e1"
_TEXT_DIM = "#8a93a3"

LAYOUT_SPLASH = "splash"
LAYOUT_AUTO_GRID = "auto_grid"


class _PanelBox(QGraphicsRectItem):
    """A clickable panel rectangle."""

    def __init__(
        self, x: float, y: float, w: float, h: float,
        panel_id: int, on_click: Callable[[int], None] | None,
    ) -> None:
        super().__init__(x, y, w, h)
        self._panel_id = panel_id
        self._on_click = on_click
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, event) -> None:
        if self._on_click and event.button() == Qt.MouseButton.LeftButton:
            self._on_click(self._panel_id)
        super().mousePressEvent(event)


class GraphicNovelPageCanvas(QWidget):
    """Renders the selected page + its panels as a planning surface."""

    def __init__(
        self,
        db: Database,
        on_panel_selected: Callable[[int], None] | None = None,
    ) -> None:
        super().__init__()
        self._db = db
        self._on_panel_selected = on_panel_selected
        self._page_id: int | None = None
        self._selected_panel_id: int | None = None
        self._box_items: dict[int, _PanelBox] = {}
        self._layout_mode: str = LAYOUT_AUTO_GRID

        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(6)

        self._header = QLabel("")
        self._header.setStyleSheet(f"color: {theme.TEXT_MUTED}; font-size: 11px;")
        self._header.setWordWrap(True)
        outer.addWidget(self._header)

        self._scene = QGraphicsScene()
        self._gview = QGraphicsView(self._scene)
        self._gview.setFrameShape(QGraphicsView.Shape.NoFrame)
        from PySide6.QtGui import QPainter
        self._gview.setRenderHints(
            QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing
        )
        self._gview.setStyleSheet("background: transparent;")
        outer.addWidget(self._gview, stretch=1)

        self._render()

    # -- Public API ----------------------------------------------------------

    def set_page(self, page_id: int | None) -> None:
        """Render *page_id* (None clears the canvas)."""
        self._page_id = page_id
        self._render()

    def set_selected_panel(self, panel_id: int | None) -> None:
        """Highlight a panel without changing the page."""
        self._selected_panel_id = panel_id
        self._render()

    def clear(self) -> None:
        self.set_page(None)

    # -- Accessors (used by host + tests) ------------------------------------

    def page_id(self) -> int | None:
        return self._page_id

    def selected_panel_id(self) -> int | None:
        return self._selected_panel_id

    def layout_mode(self) -> str:
        return self._layout_mode

    def panel_box_ids(self) -> list[int]:
        """Panel ids currently drawn, in reading order."""
        return list(self._box_items.keys())

    def panel_box_count(self) -> int:
        return len(self._box_items)

    def header_text(self) -> str:
        return self._header.text()

    # -- Rendering -----------------------------------------------------------

    def _handle_panel_click(self, panel_id: int) -> None:
        self._selected_panel_id = panel_id
        self._render()
        if self._on_panel_selected:
            self._on_panel_selected(panel_id)

    def _render(self) -> None:
        self._scene.clear()
        self._box_items.clear()

        if self._page_id is None:
            self._header.setText("")
            return
        page = self._db.get_gn_page_by_id(self._page_id)
        if page is None:
            self._header.setText("")
            self._page_id = None
            return

        self._header.setText(self._page_header(page))

        # Page surface.
        surface = self._scene.addRect(
            0, 0, _PAGE_W, _PAGE_H,
            QPen(QColor(_PAGE_BORDER), 1.5),
            QBrush(QColor(_PAGE_FILL)),
        )
        surface.setZValue(-1)

        panels = self._db.get_gn_panels_for_page(self._page_id)
        self._layout_mode = (
            LAYOUT_SPLASH if page.splash_page else LAYOUT_AUTO_GRID
        )

        if not panels:
            self._draw_empty_hint()
            self._scene.setSceneRect(0, 0, _PAGE_W, _PAGE_H)
            return

        for rect, panel in self._layout_boxes(panels):
            self._draw_panel(rect, panel)

        self._scene.setSceneRect(0, 0, _PAGE_W, _PAGE_H)

    def _page_header(self, page: Any) -> str:
        bits = [f"Page {page.page_number}"]
        if page.density_level:
            bits.append(page.density_level)
        if page.reveal_type and page.reveal_type != "none":
            bits.append(f"reveal: {page.reveal_type}")
        if page.splash_page:
            bits.append("splash")
        if (page.emotional_beat or "").strip():
            bits.append(f"beat: {page.emotional_beat.strip()}")
        return "   ·   ".join(bits)

    def _layout_boxes(
        self, panels: list,
    ) -> list[tuple[tuple[float, float, float, float], Any]]:
        """Return [(x, y, w, h), panel] derived from splash flag + count."""
        n = len(panels)
        if self._layout_mode == LAYOUT_SPLASH:
            cols, rows = 1, n  # one tall column of large surfaces
        else:
            cols = 1 if n <= 1 else 2 if n <= 4 else 3 if n <= 9 else 4
            rows = max(1, math.ceil(n / cols))

        avail_w = _PAGE_W - 2 * _MARGIN
        avail_h = _PAGE_H - 2 * _MARGIN
        box_w = (avail_w - (cols - 1) * _GUTTER) / cols
        box_h = (avail_h - (rows - 1) * _GUTTER) / max(rows, 1)

        out = []
        for i, panel in enumerate(panels):
            r, c = divmod(i, cols)
            x = _MARGIN + c * (box_w + _GUTTER)
            y = _MARGIN + r * (box_h + _GUTTER)
            out.append(((x, y, box_w, box_h), panel))
        return out

    def _draw_panel(
        self, rect: tuple[float, float, float, float], panel: Any,
    ) -> None:
        x, y, w, h = rect
        selected = panel.id == self._selected_panel_id
        box = _PanelBox(x, y, w, h, panel.id, self._handle_panel_click)
        box.setBrush(QBrush(QColor(_BOX_FILL_SEL if selected else _BOX_FILL)))
        box.setPen(QPen(
            QColor(_BOX_BORDER_SEL if selected else _BOX_BORDER),
            2.0 if selected else 1.0,
        ))
        self._scene.addItem(box)
        self._box_items[panel.id] = box

        pad = 6.0
        inner_w = w - 2 * pad

        # Panel number (top-left).
        self._text(f"P{panel.panel_number}", x + pad, y + pad,
                   color=_TEXT, bold=True, size=9)

        # Shot · camera (top, under number).
        meta = " · ".join(b for b in (panel.shot_type, panel.camera_angle) if b)
        if meta:
            self._text(meta, x + pad, y + pad + 13, color=_TEXT_DIM,
                       size=7, max_w=inner_w)

        # Description excerpt (middle).
        desc = (panel.description or panel.action or "").strip()
        if desc and h > 46:
            self._text(desc, x + pad, y + pad + 26, color=_TEXT,
                       size=7, max_w=inner_w)

        # Bottom-left: transition + reading priority.
        foot = []
        if panel.transition_type:
            foot.append(f"→ {panel.transition_type}")
        if panel.reading_priority:
            foot.append(f"p{panel.reading_priority}")
        if foot:
            self._text(" · ".join(foot), x + pad, y + h - 14,
                       color=_TEXT_DIM, size=7, max_w=inner_w)

        # Bottom-right badges for fields that actually exist on the panel.
        badges = self._badges(panel)
        if badges:
            self._text(badges, x + w - pad - 44, y + h - 14,
                       color=_TEXT_DIM, size=8, bold=True)

    @staticmethod
    def _badges(panel: Any) -> str:
        # Only fields backed by real columns. Caption/SFX badges await the
        # manuscript-binding slice (no panel field for them yet).
        out = []
        if (panel.dialogue_refs or "").strip():
            out.append("D")
        if (panel.characters_present or "").strip():
            out.append("C")
        if (panel.visual_motifs or "").strip():
            out.append("M")
        if (panel.action or "").strip():
            out.append("A")
        return " ".join(out)

    def _draw_empty_hint(self) -> None:
        t = self._scene.addSimpleText("No panels yet")
        t.setBrush(QBrush(QColor(_TEXT_DIM)))
        f = t.font()
        f.setPointSize(9)
        t.setFont(f)
        t.setPos(_PAGE_W / 2 - 40, _PAGE_H / 2 - 8)

    def _text(
        self, text: str, x: float, y: float, *, color: str,
        size: int = 8, bold: bool = False, max_w: float | None = None,
    ) -> None:
        item = QGraphicsSimpleTextItem()
        font = QFont()
        font.setPointSize(size)
        font.setBold(bold)
        item.setFont(font)
        if max_w is not None:
            fm = QFontMetrics(font)
            text = fm.elidedText(text, Qt.TextElideMode.ElideRight, int(max_w))
        item.setText(text)
        item.setBrush(QBrush(QColor(color)))
        item.setPos(x, y)
        self._scene.addItem(item)
