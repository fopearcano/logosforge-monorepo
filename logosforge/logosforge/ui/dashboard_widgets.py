"""Custom-painted dashboard panels for the Narrative Dashboard.

Four lightweight QWidget subclasses that render charts using QPainter:
  - TensionCurvePanel      — polyline with filled area
  - CharacterPresencePanel — horizontal strip timeline
  - StructurePanel         — segmented horizontal bar
  - ThemeContinuityPanel   — horizontal strip timeline for themes

Each panel is self-contained: hand it the data, it draws.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
)
from PySide6.QtWidgets import QToolTip, QWidget

from logosforge.narrative_dashboard import (
    CharacterPresence,
    StructureDistribution,
    TensionCurve,
    ThemePresence,
)
from logosforge.ui import theme

_MARGIN_L = 40
_MARGIN_R = 16
_MARGIN_T = 24
_MARGIN_B = 32
_MIN_PANEL_H = 180

_PRESENCE_ROW_H = 22
_PRESENCE_DOT_R = 5
_PRESENCE_LABEL_W = 100


def _accent() -> QColor:
    return QColor(theme.get("ACCENT"))


def _accent_dim() -> QColor:
    return QColor(theme.get("ACCENT_DIM"))


def _muted() -> QColor:
    return QColor(theme.get("TEXT_MUTED"))


def _secondary() -> QColor:
    return QColor(theme.get("TEXT_SECONDARY"))


def _primary() -> QColor:
    return QColor(theme.get("TEXT_PRIMARY"))


def _border() -> QColor:
    return QColor(theme.get("BORDER"))


def _panel_bg() -> QColor:
    return QColor(theme.get("BG_PANEL"))


def _status_err() -> QColor:
    return QColor(theme.get("STATUS_ERR"))


_SOFT_PALETTE = [
    "#4ade80", "#60a5fa", "#f472b6", "#facc15",
    "#a78bfa", "#fb923c", "#2dd4bf", "#e879f9",
]


# ===========================================================================
# Tension Curve
# ===========================================================================

class TensionCurvePanel(QWidget):
    """Polyline tension chart with filled area gradient."""

    scene_clicked = Signal(int)  # scene_id
    scene_hovered = Signal(int, str)  # scene_id, tooltip text

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._data: TensionCurve | None = None
        self._point_rects: list[tuple[QRectF, int, str]] = []
        self.setMinimumHeight(_MIN_PANEL_H)
        self.setMouseTracking(True)

    def set_data(self, data: TensionCurve) -> None:
        self._data = data
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        if not self._data or not self._data.points:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        chart_w = w - _MARGIN_L - _MARGIN_R
        chart_h = h - _MARGIN_T - _MARGIN_B

        if chart_w < 10 or chart_h < 10:
            painter.end()
            return

        points = self._data.points
        n = len(points)
        max_score = max((p.score for p in points), default=100) or 100

        # Axes
        pen = QPen(_border(), 1)
        painter.setPen(pen)
        painter.drawLine(
            int(_MARGIN_L), int(_MARGIN_T),
            int(_MARGIN_L), int(h - _MARGIN_B),
        )
        painter.drawLine(
            int(_MARGIN_L), int(h - _MARGIN_B),
            int(w - _MARGIN_R), int(h - _MARGIN_B),
        )

        # Y-axis labels
        font = QFont()
        font.setPixelSize(9)
        painter.setFont(font)
        painter.setPen(_muted())
        for frac in (0, 0.25, 0.5, 0.75, 1.0):
            y = _MARGIN_T + chart_h * (1 - frac)
            val = int(max_score * frac)
            painter.drawText(
                QRectF(0, y - 6, _MARGIN_L - 6, 12),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                str(val),
            )
            if frac > 0 and frac < 1.0:
                painter.setPen(QPen(_border(), 1, Qt.PenStyle.DotLine))
                painter.drawLine(
                    int(_MARGIN_L + 1), int(y),
                    int(w - _MARGIN_R), int(y),
                )
                painter.setPen(_muted())

        # Compute pixel positions
        step = chart_w / max(n - 1, 1) if n > 1 else chart_w
        coords: list[QPointF] = []
        self._point_rects.clear()
        for i, p in enumerate(points):
            x = _MARGIN_L + i * step
            y = _MARGIN_T + chart_h * (1 - p.score / max_score)
            coords.append(QPointF(x, y))
            rect = QRectF(x - 5, y - 5, 10, 10)
            tip = (
                f"{p.scene_title}\n"
                f"Tension: {p.score}\n"
                f"Characters: {p.char_count}  "
                f"Keywords: {p.keyword_hits}\n"
                f"Relations: {p.relation_pairs}  "
                f"Progressions: {p.progression_count}"
            )
            self._point_rects.append((rect, p.scene_id, tip))

        # Filled area
        if len(coords) >= 2:
            path = QPainterPath()
            path.moveTo(QPointF(coords[0].x(), h - _MARGIN_B))
            for pt in coords:
                path.lineTo(pt)
            path.lineTo(QPointF(coords[-1].x(), h - _MARGIN_B))
            path.closeSubpath()

            grad = QLinearGradient(0, _MARGIN_T, 0, h - _MARGIN_B)
            accent = _accent()
            fill_top = QColor(accent)
            fill_top.setAlpha(50)
            fill_bot = QColor(accent)
            fill_bot.setAlpha(5)
            grad.setColorAt(0, fill_top)
            grad.setColorAt(1, fill_bot)
            painter.setBrush(grad)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawPath(path)

        # Line
        painter.setPen(QPen(_accent(), 2))
        for i in range(len(coords) - 1):
            painter.drawLine(coords[i], coords[i + 1])

        # Dots
        painter.setBrush(_accent())
        painter.setPen(Qt.PenStyle.NoPen)
        for pt in coords:
            painter.drawEllipse(pt, 3, 3)

        # X-axis labels
        painter.setPen(_muted())
        painter.setFont(font)
        for i, p in enumerate(points):
            x = _MARGIN_L + i * step
            label = str(i + 1)
            painter.drawText(
                QRectF(x - 15, h - _MARGIN_B + 4, 30, 14),
                Qt.AlignmentFlag.AlignCenter,
                label,
            )

        painter.end()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        for rect, sid, _ in self._point_rects:
            if rect.contains(event.position()):
                self.scene_clicked.emit(sid)
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        for rect, sid, tip in self._point_rects:
            if rect.contains(event.position()):
                QToolTip.showText(event.globalPosition().toPoint(), tip, self)
                self.scene_hovered.emit(sid, tip)
                return
        QToolTip.hideText()
        super().mouseMoveEvent(event)


# ===========================================================================
# Character Presence
# ===========================================================================

class CharacterPresencePanel(QWidget):
    """Horizontal strip timeline of character presence across scenes."""

    scene_clicked = Signal(int)
    visibility_toggled = Signal(int, bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._data: list[CharacterPresence] = []
        self._visible_ids: set[int] = set()
        self._dot_rects: list[tuple[QRectF, int, str]] = []
        self.setMouseTracking(True)

    def set_data(self, data: list[CharacterPresence]) -> None:
        self._data = data
        self._visible_ids = {d.entry_id for d in data}
        self.setMinimumHeight(
            max(_MIN_PANEL_H, _MARGIN_T + len(data) * _PRESENCE_ROW_H + _MARGIN_B),
        )
        self.update()

    def toggle_character(self, entry_id: int) -> None:
        if entry_id in self._visible_ids:
            self._visible_ids.discard(entry_id)
        else:
            self._visible_ids.add(entry_id)
        self.visibility_toggled.emit(
            entry_id, entry_id in self._visible_ids,
        )
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        if not self._data:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        chart_x = _PRESENCE_LABEL_W + 8
        chart_w = w - chart_x - _MARGIN_R

        total = self._data[0].total_scenes if self._data else 0
        if chart_w < 10 or total == 0:
            painter.end()
            return

        font = QFont()
        font.setPixelSize(10)
        painter.setFont(font)

        self._dot_rects.clear()

        step = chart_w / max(total, 1)
        for row, cp in enumerate(self._data):
            y = _MARGIN_T + row * _PRESENCE_ROW_H + _PRESENCE_ROW_H // 2
            visible = cp.entry_id in self._visible_ids
            color_idx = row % len(_SOFT_PALETTE)
            color = QColor(_SOFT_PALETTE[color_idx])

            label_color = _primary() if visible else _muted()
            painter.setPen(label_color)
            painter.drawText(
                QRectF(4, y - 8, _PRESENCE_LABEL_W, 16),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                cp.name[:14],
            )

            if not visible:
                painter.setPen(QPen(_border(), 1, Qt.PenStyle.DotLine))
                painter.drawLine(
                    int(chart_x), int(y),
                    int(chart_x + chart_w), int(y),
                )
                continue

            # Track line
            painter.setPen(QPen(_border(), 1))
            painter.drawLine(
                int(chart_x), int(y),
                int(chart_x + chart_w), int(y),
            )

            # Presence dots
            painter.setBrush(color)
            painter.setPen(Qt.PenStyle.NoPen)
            for order in cp.present_scenes:
                cx = chart_x + order * step + step / 2
                painter.drawEllipse(QPointF(cx, y), _PRESENCE_DOT_R, _PRESENCE_DOT_R)
                rect = QRectF(cx - 5, y - 5, 10, 10)
                flags_str = ", ".join(cp.flags) if cp.flags else ""
                tip = f"{cp.name} — Scene {order + 1}"
                if flags_str:
                    tip += f"\n{flags_str}"
                self._dot_rects.append((rect, cp.present_scenes[0], tip))

            # Flags indicator
            if cp.flags:
                painter.setPen(_status_err())
                flag_font = QFont()
                flag_font.setPixelSize(8)
                painter.setFont(flag_font)
                painter.drawText(
                    QRectF(chart_x + chart_w + 2, y - 6, 80, 12),
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                    cp.flags[0][:15],
                )
                painter.setFont(font)

        painter.end()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        # Check if click is on a name label → toggle visibility
        for row, cp in enumerate(self._data):
            y = _MARGIN_T + row * _PRESENCE_ROW_H + _PRESENCE_ROW_H // 2
            label_rect = QRectF(4, y - 8, _PRESENCE_LABEL_W, 16)
            if label_rect.contains(event.position()):
                self.toggle_character(cp.entry_id)
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        for rect, _, tip in self._dot_rects:
            if rect.contains(event.position()):
                QToolTip.showText(event.globalPosition().toPoint(), tip, self)
                return
        QToolTip.hideText()
        super().mouseMoveEvent(event)


# ===========================================================================
# Structure Distribution
# ===========================================================================

class StructurePanel(QWidget):
    """Segmented horizontal bar for act/structure distribution."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._data: StructureDistribution | None = None
        self._seg_rects: list[tuple[QRectF, str]] = []
        self.setMinimumHeight(100)
        self.setMouseTracking(True)

    def set_data(self, data: StructureDistribution) -> None:
        self._data = data
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        if not self._data or not self._data.segments:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        bar_h = 28
        bar_y = h // 2 - bar_h // 2
        bar_x = _MARGIN_L
        bar_w = w - _MARGIN_L - _MARGIN_R

        if bar_w < 20:
            painter.end()
            return

        total = self._data.total_words or 1
        self._seg_rects.clear()
        x = bar_x

        font = QFont()
        font.setPixelSize(10)
        painter.setFont(font)

        for i, seg in enumerate(self._data.segments):
            frac = seg.word_count / total if total > 0 else 1 / len(self._data.segments)
            seg_w = max(2, int(bar_w * frac))

            color = QColor(_SOFT_PALETTE[i % len(_SOFT_PALETTE)])
            color.setAlpha(160)
            painter.setBrush(color)
            painter.setPen(QPen(_panel_bg(), 1))
            rect = QRectF(x, bar_y, seg_w, bar_h)
            painter.drawRoundedRect(rect, 4, 4)

            tip = (
                f"{seg.label}\n"
                f"{seg.scene_count} scenes, {seg.word_count:,} words"
            )
            self._seg_rects.append((rect, tip))

            painter.setPen(_primary())
            text_rect = QRectF(x, bar_y, seg_w, bar_h)
            if seg_w > 40:
                painter.drawText(
                    text_rect, Qt.AlignmentFlag.AlignCenter,
                    seg.label[:20],
                )
            x += seg_w

        # Flags below bar
        if self._data.flags:
            painter.setPen(_status_err())
            flag_font = QFont()
            flag_font.setPixelSize(9)
            painter.setFont(flag_font)
            for j, flag in enumerate(self._data.flags[:3]):
                painter.drawText(
                    QRectF(bar_x, bar_y + bar_h + 6 + j * 14, bar_w, 14),
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                    flag,
                )

        painter.end()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        for rect, tip in self._seg_rects:
            if rect.contains(event.position()):
                QToolTip.showText(event.globalPosition().toPoint(), tip, self)
                return
        QToolTip.hideText()
        super().mouseMoveEvent(event)


# ===========================================================================
# Theme Continuity
# ===========================================================================

class ThemeContinuityPanel(QWidget):
    """Horizontal strip timeline for theme presence across scenes."""

    scene_clicked = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._data: list[ThemePresence] = []
        self._visible_ids: set[int] = set()
        self.setMouseTracking(True)

    def set_data(self, data: list[ThemePresence]) -> None:
        self._data = data
        self._visible_ids = {d.entry_id for d in data}
        self.setMinimumHeight(
            max(80, _MARGIN_T + len(data) * _PRESENCE_ROW_H + _MARGIN_B),
        )
        self.update()

    def toggle_theme(self, entry_id: int) -> None:
        if entry_id in self._visible_ids:
            self._visible_ids.discard(entry_id)
        else:
            self._visible_ids.add(entry_id)
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        if not self._data:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        chart_x = _PRESENCE_LABEL_W + 8
        chart_w = w - chart_x - _MARGIN_R

        total = self._data[0].total_scenes if self._data else 0
        if chart_w < 10 or total == 0:
            painter.end()
            return

        font = QFont()
        font.setPixelSize(10)
        painter.setFont(font)

        step = chart_w / max(total, 1)
        for row, tp in enumerate(self._data):
            y = _MARGIN_T + row * _PRESENCE_ROW_H + _PRESENCE_ROW_H // 2
            visible = tp.entry_id in self._visible_ids
            color_idx = (row + 4) % len(_SOFT_PALETTE)
            color = QColor(_SOFT_PALETTE[color_idx])

            label_color = _primary() if visible else _muted()
            painter.setPen(label_color)
            painter.drawText(
                QRectF(4, y - 8, _PRESENCE_LABEL_W, 16),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                tp.name[:14],
            )

            if not visible:
                painter.setPen(QPen(_border(), 1, Qt.PenStyle.DotLine))
                painter.drawLine(
                    int(chart_x), int(y),
                    int(chart_x + chart_w), int(y),
                )
                continue

            painter.setPen(QPen(_border(), 1))
            painter.drawLine(
                int(chart_x), int(y),
                int(chart_x + chart_w), int(y),
            )

            # Presence bars
            bar_h = _PRESENCE_ROW_H - 8
            painter.setBrush(color)
            painter.setPen(Qt.PenStyle.NoPen)
            for order in tp.present_scenes:
                cx = chart_x + order * step
                bar_w = max(step - 2, 4)
                painter.drawRoundedRect(
                    QRectF(cx + 1, y - bar_h // 2, bar_w, bar_h),
                    2, 2,
                )

            if tp.flags:
                painter.setPen(_status_err())
                flag_font = QFont()
                flag_font.setPixelSize(8)
                painter.setFont(flag_font)
                painter.drawText(
                    QRectF(chart_x + chart_w + 2, y - 6, 80, 12),
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                    tp.flags[0][:15],
                )
                painter.setFont(font)

        painter.end()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        for row, tp in enumerate(self._data):
            y = _MARGIN_T + row * _PRESENCE_ROW_H + _PRESENCE_ROW_H // 2
            label_rect = QRectF(4, y - 8, _PRESENCE_LABEL_W, 16)
            if label_rect.contains(event.position()):
                self.toggle_theme(tp.entry_id)
                return
        super().mousePressEvent(event)
