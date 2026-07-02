"""PSYKE syntax highlighter and Ctrl+Click jump handler for the scene editor."""

from __future__ import annotations

import re

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import (
    QColor,
    QMouseEvent,
    QSyntaxHighlighter,
    QTextCharFormat,
    QTextDocument,
)
from PySide6.QtWidgets import QTextEdit

from logosforge.ui import theme

_TYPE_COLOR_KEYS = {
    "character": "PSYKE_CHARACTER",
    "place": "PSYKE_PLACE",
    "object": "PSYKE_OBJECT",
}


class PsykeHighlighter(QSyntaxHighlighter):
    """Highlights PSYKE entry names with per-type color coding."""

    def __init__(self, document: QTextDocument) -> None:
        super().__init__(document)
        self._pattern: re.Pattern | None = None
        self._term_types: dict[str, str] = {}
        self._formats: dict[str, QTextCharFormat] = {}
        self._default_fmt = QTextCharFormat()
        self._build_formats()

    def _build_formats(self) -> None:
        for entry_type, color_key in _TYPE_COLOR_KEYS.items():
            color = QColor(theme.get(color_key))
            fmt = QTextCharFormat()
            fmt.setUnderlineStyle(QTextCharFormat.UnderlineStyle.SingleUnderline)
            fmt.setUnderlineColor(color)
            fmt.setForeground(color)
            self._formats[entry_type] = fmt

        fallback = QColor(theme.get("ACCENT"))
        self._default_fmt = QTextCharFormat()
        self._default_fmt.setUnderlineStyle(QTextCharFormat.UnderlineStyle.SingleUnderline)
        self._default_fmt.setUnderlineColor(fallback)
        self._default_fmt.setForeground(fallback)

    def refresh_patterns(
        self,
        terms: list[str],
        term_types: dict[str, str] | None = None,
    ) -> None:
        self._build_formats()
        self._term_types = term_types or {}
        if not terms:
            self._pattern = None
            self.rehighlight()
            return
        escaped = sorted((re.escape(t) for t in terms if t.strip()), key=len, reverse=True)
        if not escaped:
            self._pattern = None
            self.rehighlight()
            return
        self._pattern = re.compile(
            r"\b(?:" + "|".join(escaped) + r")\b",
            re.IGNORECASE,
        )
        self.rehighlight()

    def highlightBlock(self, text: str) -> None:
        if self._pattern is None:
            return
        for match in self._pattern.finditer(text):
            term_lower = match.group().lower()
            entry_type = self._term_types.get(term_lower, "")
            fmt = self._formats.get(entry_type, self._default_fmt)
            self.setFormat(match.start(), match.end() - match.start(), fmt)


class PsykeClickHandler(QObject):
    """Event filter: Ctrl+Click on a highlighted PSYKE term jumps to that entry."""

    def __init__(
        self,
        editor: QTextEdit,
        highlighter: PsykeHighlighter,
        on_jump: callable,
    ) -> None:
        super().__init__(editor)
        self._editor = editor
        self._highlighter = highlighter
        self._on_jump = on_jump
        self._term_to_entry_id: dict[str, int] = {}
        editor.viewport().installEventFilter(self)

    def set_term_map(self, term_map: dict[str, int]) -> None:
        self._term_to_entry_id = term_map

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if event.type() != QEvent.Type.MouseButtonRelease:
            return False
        mouse: QMouseEvent = event
        if not (mouse.modifiers() & Qt.KeyboardModifier.ControlModifier):
            return False
        if mouse.button() != Qt.MouseButton.LeftButton:
            return False

        pattern = self._highlighter._pattern
        if pattern is None:
            return False

        cursor = self._editor.cursorForPosition(mouse.pos())
        block = cursor.block()
        col = cursor.positionInBlock()
        text = block.text()

        for match in pattern.finditer(text):
            if match.start() <= col <= match.end():
                matched_text = match.group()
                entry_id = self._term_to_entry_id.get(matched_text.lower())
                if entry_id is not None:
                    self._on_jump(entry_id)
                    return True
        return False
