"""Floating format toolbar — appears on text selection in the manuscript editor.

Provides quick-access formatting (bold, italic, heading, blockquote) and
emits signals for AI assistant actions (rewrite, expand, dialogue).
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QTextBlockFormat, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (
    QHBoxLayout,
    QTextEdit,
    QPushButton,
    QWidget,
)

from logosforge.ui import theme


class FormatToolbar(QWidget):
    """Compact floating toolbar for text formatting and AI action hooks."""

    ai_action = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("formatToolbar")
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)

        self._active_editor: QTextEdit | None = None
        self._tracked: list[QTextEdit] = []

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(2)

        bold_btn = self._make_btn("B", weight=QFont.Weight.Bold)
        bold_btn.setToolTip("Bold  (Ctrl+B)")
        bold_btn.clicked.connect(self._toggle_bold)
        layout.addWidget(bold_btn)

        italic_btn = self._make_btn("I", italic=True)
        italic_btn.setToolTip("Italic  (Ctrl+I)")
        italic_btn.clicked.connect(self._toggle_italic)
        layout.addWidget(italic_btn)

        heading_btn = self._make_btn("H")
        heading_btn.setToolTip("Cycle heading level")
        heading_btn.clicked.connect(self._cycle_heading)
        layout.addWidget(heading_btn)

        quote_btn = self._make_btn("❝")
        quote_btn.setToolTip("Toggle blockquote")
        quote_btn.clicked.connect(self._toggle_quote)
        layout.addWidget(quote_btn)

        sep = QWidget()
        sep.setFixedWidth(1)
        sep.setFixedHeight(16)
        sep.setObjectName("formatToolbarSep")
        layout.addWidget(sep)

        for label, key in (
            ("Rewrite", "rewrite"),
            ("Expand", "expand"),
            ("Dialogue", "dialogue"),
        ):
            btn = self._make_btn(label)
            btn.clicked.connect(lambda _, k=key: self.ai_action.emit(k))
            layout.addWidget(btn)

        self.hide()

    @staticmethod
    def _make_btn(
        text: str,
        weight: QFont.Weight = QFont.Weight.Normal,
        italic: bool = False,
    ) -> QPushButton:
        btn = QPushButton(text)
        btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        font = btn.font()
        font.setWeight(weight)
        font.setItalic(italic)
        btn.setFont(font)
        return btn

    # -- Editor tracking ------------------------------------------------------

    def track_editor(self, editor: QTextEdit) -> None:
        if editor in self._tracked:
            return
        self._tracked.append(editor)
        editor.selectionChanged.connect(
            lambda e=editor: self._on_selection_changed(e),
        )

    def untrack_all(self) -> None:
        self._tracked.clear()
        self._active_editor = None
        self.hide()

    @property
    def active_editor(self) -> QTextEdit | None:
        return self._active_editor

    @property
    def selected_text(self) -> str:
        if not self._active_editor:
            return ""
        return (
            self._active_editor.textCursor()
            .selectedText()
            .replace(" ", "\n")
        )

    # -- Selection handling ---------------------------------------------------

    def _on_selection_changed(self, editor: QTextEdit) -> None:
        cursor = editor.textCursor()
        if cursor.hasSelection():
            self._active_editor = editor
            self._reposition(editor)
            self.show()
            self.raise_()
        elif editor is self._active_editor:
            self.hide()
            self._active_editor = None

    def _reposition(self, editor: QTextEdit) -> None:
        parent = self.parentWidget()
        if parent is None:
            return
        cursor = editor.textCursor()
        rect = editor.cursorRect(cursor)
        pos = editor.mapTo(parent, rect.topLeft())
        w = self.sizeHint().width()
        h = self.sizeHint().height()
        x = max(4, min(pos.x() - w // 2, parent.width() - w - 4))
        y = pos.y() - h - 6
        if y < 4:
            y = pos.y() + rect.height() + 6
        self.move(x, y)
        self.adjustSize()

    # -- Public format helpers (for keyboard shortcuts) -----------------------

    def toggle_bold_on(self, editor: QTextEdit | None = None) -> None:
        if editor is not None:
            self._active_editor = editor
        self._toggle_bold()

    def toggle_italic_on(self, editor: QTextEdit | None = None) -> None:
        if editor is not None:
            self._active_editor = editor
        self._toggle_italic()

    # -- Formatting actions ---------------------------------------------------

    def _toggle_bold(self) -> None:
        editor = self._active_editor
        if not editor:
            return
        cursor = editor.textCursor()
        fmt = cursor.charFormat()
        weight = QFont.Weight.Normal if fmt.fontWeight() >= QFont.Weight.Bold else QFont.Weight.Bold
        new_fmt = QTextCharFormat()
        new_fmt.setFontWeight(weight)
        cursor.mergeCharFormat(new_fmt)
        editor.setTextCursor(cursor)

    def _toggle_italic(self) -> None:
        editor = self._active_editor
        if not editor:
            return
        cursor = editor.textCursor()
        fmt = cursor.charFormat()
        new_fmt = QTextCharFormat()
        new_fmt.setFontItalic(not fmt.fontItalic())
        cursor.mergeCharFormat(new_fmt)
        editor.setTextCursor(cursor)

    def _cycle_heading(self) -> None:
        editor = self._active_editor
        if not editor:
            return
        cursor = editor.textCursor()
        block_fmt = cursor.blockFormat()
        level = block_fmt.headingLevel()
        new_level = (level % 3) + 1 if level < 3 else 0
        new_fmt = QTextBlockFormat()
        new_fmt.setHeadingLevel(new_level)
        cursor.mergeBlockFormat(new_fmt)
        editor.setTextCursor(cursor)

    def _toggle_quote(self) -> None:
        editor = self._active_editor
        if not editor:
            return
        cursor = editor.textCursor()
        block_fmt = cursor.blockFormat()
        level = block_fmt.property(QTextBlockFormat.Property.BlockQuoteLevel) or 0
        new_fmt = QTextBlockFormat()
        new_fmt.setProperty(QTextBlockFormat.Property.BlockQuoteLevel, 0 if level else 1)
        cursor.mergeBlockFormat(new_fmt)
        editor.setTextCursor(cursor)
