"""Entity hover panel and mouse handler for PSYKE-aware manuscript editing.

Shows a floating info panel when hovering over detected PSYKE entities in the
scene editor: name, type, temporal state at the current scene position, and
a notes excerpt.  Debounced to avoid flicker during normal mouse movement.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QEvent, QObject, QPoint, Qt, QTimer
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from logosforge.ui import theme
from logosforge.ui.psyke_highlighter import PsykeHighlighter


def _ellipsize(text: str, limit: int) -> str:
    text = text or ""
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


class EntityHoverPanel(QWidget):
    """Floating panel that shows PSYKE entity info on hover."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("entityHoverPanel")
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)

        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.setInterval(300)
        self._hide_timer.timeout.connect(self.hide)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(3)

        header = QHBoxLayout()
        header.setSpacing(6)
        self._name_label = QLabel()
        self._name_label.setObjectName("entityHoverName")
        header.addWidget(self._name_label)
        header.addStretch()
        self._type_label = QLabel()
        self._type_label.setObjectName("entityHoverType")
        header.addWidget(self._type_label)
        layout.addLayout(header)

        self._state_label = QLabel()
        self._state_label.setObjectName("entityHoverState")
        self._state_label.setWordWrap(True)
        layout.addWidget(self._state_label)

        self._notes_label = QLabel()
        self._notes_label.setObjectName("entityHoverNotes")
        self._notes_label.setWordWrap(True)
        layout.addWidget(self._notes_label)

        self.setMaximumWidth(320)
        self.hide()

    def show_entity(
        self,
        name: str,
        entry_type: str,
        state_text: str,
        notes: str,
        pos: QPoint,
    ) -> None:
        self._hide_timer.stop()
        self._name_label.setText(name)
        self._type_label.setText(entry_type)

        if state_text:
            self._state_label.setText(_ellipsize(state_text, 150))
            self._state_label.show()
        else:
            self._state_label.hide()

        if notes:
            self._notes_label.setText(_ellipsize(notes, 180))
            self._notes_label.show()
        else:
            self._notes_label.hide()

        self.adjustSize()

        parent = self.parentWidget()
        if parent:
            x = max(4, min(pos.x(), parent.width() - self.width() - 4))
            y = pos.y() + 4
            if y + self.height() > parent.height():
                y = pos.y() - self.height() - 4
            self.move(x, max(0, y))

        self.show()
        self.raise_()

    def schedule_hide(self) -> None:
        self._hide_timer.start()

    def enterEvent(self, event) -> None:  # noqa: N802
        self._hide_timer.stop()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hide_timer.start()
        super().leaveEvent(event)


class EntityHoverHandler(QObject):
    """Event filter that detects PSYKE entity hover and triggers callbacks."""

    def __init__(
        self,
        editor: QTextEdit,
        highlighter: PsykeHighlighter,
        term_map: dict[str, int],
        hover_parent: QWidget,
        on_show: Callable[[int, QTextEdit, QPoint], None],
        on_hide: Callable[[], None],
    ) -> None:
        super().__init__(editor)
        self._editor = editor
        self._highlighter = highlighter
        self._term_map = term_map
        self._hover_parent = hover_parent
        self._on_show = on_show
        self._on_hide = on_hide

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(150)
        self._timer.timeout.connect(self._check)

        self._last_pos: QPoint | None = None
        self._current_entry_id: int | None = None

        editor.viewport().installEventFilter(self)

    def set_term_map(self, term_map: dict[str, int]) -> None:
        self._term_map = term_map

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:  # noqa: N802
        if event.type() == QEvent.Type.MouseMove:
            self._last_pos = event.pos()
            self._timer.start()
        elif event.type() == QEvent.Type.Leave:
            self._timer.stop()
            if self._current_entry_id is not None:
                self._current_entry_id = None
                self._on_hide()
        return False

    def _check(self) -> None:
        if self._last_pos is None:
            return

        pattern = self._highlighter._pattern
        if pattern is None:
            if self._current_entry_id is not None:
                self._current_entry_id = None
                self._on_hide()
            return

        cursor = self._editor.cursorForPosition(self._last_pos)
        block = cursor.block()
        col = cursor.positionInBlock()
        text = block.text()

        for match in pattern.finditer(text):
            if match.start() <= col <= match.end():
                term = match.group().lower()
                entry_id = self._term_map.get(term)
                if entry_id is not None:
                    if entry_id == self._current_entry_id:
                        return
                    self._current_entry_id = entry_id
                    target = QTextCursor(self._editor.document())
                    target.setPosition(block.position() + match.end())
                    rect = self._editor.cursorRect(target)
                    pos = self._editor.mapTo(
                        self._hover_parent, rect.bottomLeft(),
                    )
                    self._on_show(entry_id, self._editor, pos)
                    return

        if self._current_entry_id is not None:
            self._current_entry_id = None
            self._on_hide()
