"""Command palette — lightweight "/" triggered popup for writing actions."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from logosforge.ui import theme

COMMANDS = [
    ("New Scene", "scene", "Create a new scene after this one"),
    ("New Chapter", "chapter", "Start a new chapter"),
    ("Insert PSYKE Entry", "psyke", "Reference a story bible entry"),
    ("Rewrite", "ai_rewrite", "AI: rewrite selected text"),
    ("Expand", "ai_expand", "AI: expand selected text"),
    ("Dialogue", "ai_dialogue", "AI: improve dialogue"),
    ("Suggest Beats", "ai_suggest", "AI: suggest narrative directions"),
    ("Style Improve", "style_improve", "Analyze selection and suggest improvements"),
    ("Voice Rewrite", "voice_rewrite", "Rewrite selection in character voice"),
    ("Focus Mode", "focus", "Toggle distraction-free writing"),
]


class CommandPalette(QFrame):
    """Floating command palette activated by typing '/' in the editor."""

    command_selected = Signal(str)
    dismissed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint
        )
        self.setObjectName("commandPalette")
        self.setFixedWidth(320)
        self.setMaximumHeight(340)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)

        self._filter = QLineEdit()
        self._filter.setPlaceholderText("Type a command...")
        self._filter.setObjectName("commandPaletteFilter")
        self._filter.textChanged.connect(self._on_filter)
        self._filter.installEventFilter(self)
        layout.addWidget(self._filter)

        self._list = QListWidget()
        self._list.setObjectName("commandPaletteList")
        self._list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._list.itemClicked.connect(self._on_item_clicked)
        layout.addWidget(self._list)

        self._all_commands = list(COMMANDS)
        self._populate(self._all_commands)

    def _populate(self, commands: list[tuple[str, str, str]]) -> None:
        self._list.clear()
        for label, key, desc in commands:
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, key)
            widget = QWidget()
            row = QVBoxLayout(widget)
            row.setContentsMargins(8, 4, 8, 4)
            row.setSpacing(1)
            name_label = QLabel(label)
            name_label.setStyleSheet(
                f"color: {theme.TEXT_PRIMARY}; font-size: 13px;"
                f" font-weight: bold; background: transparent;"
            )
            desc_label = QLabel(desc)
            desc_label.setStyleSheet(
                f"color: {theme.TEXT_MUTED}; font-size: 11px;"
                f" background: transparent;"
            )
            row.addWidget(name_label)
            row.addWidget(desc_label)
            item.setSizeHint(widget.sizeHint())
            self._list.addItem(item)
            self._list.setItemWidget(item, widget)
        if self._list.count() > 0:
            self._list.setCurrentRow(0)

    def _on_filter(self, text: str) -> None:
        filtered = [
            c for c in self._all_commands
            if text.lower() in c[0].lower() or text.lower() in c[2].lower()
        ]
        self._populate(filtered)

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        key = item.data(Qt.ItemDataRole.UserRole)
        if key:
            self.command_selected.emit(key)
            self.close()

    def _select_current(self) -> None:
        item = self._list.currentItem()
        if item:
            key = item.data(Qt.ItemDataRole.UserRole)
            if key:
                self.command_selected.emit(key)
                self.close()

    def eventFilter(self, obj, event):
        if obj is self._filter and isinstance(event, QKeyEvent):
            if event.key() == Qt.Key.Key_Escape:
                self.dismissed.emit()
                self.close()
                return True
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self._select_current()
                return True
            if event.key() == Qt.Key.Key_Down:
                row = self._list.currentRow()
                if row < self._list.count() - 1:
                    self._list.setCurrentRow(row + 1)
                return True
            if event.key() == Qt.Key.Key_Up:
                row = self._list.currentRow()
                if row > 0:
                    self._list.setCurrentRow(row - 1)
                return True
        return super().eventFilter(obj, event)

    def open_at(self, global_pos) -> None:
        self._filter.clear()
        self._populate(self._all_commands)
        self.move(global_pos)
        self.show()
        self._filter.setFocus()

    def showEvent(self, event):
        self.setStyleSheet(
            f"#commandPalette {{"
            f"  background-color: {theme.BG_PANEL};"
            f"  border: 1px solid {theme.BORDER};"
            f"  border-radius: 10px;"
            f"}}"
            f"#commandPaletteFilter {{"
            f"  background-color: {theme.BG_INPUT};"
            f"  color: {theme.TEXT_PRIMARY};"
            f"  border: 1px solid {theme.BORDER};"
            f"  border-radius: 6px;"
            f"  padding: 6px 10px;"
            f"  font-size: 14px;"
            f"}}"
            f"#commandPaletteFilter:focus {{"
            f"  border-color: {theme.ACCENT};"
            f"}}"
            f"#commandPaletteList {{"
            f"  background-color: transparent;"
            f"  border: none;"
            f"  outline: none;"
            f"}}"
            f"#commandPaletteList::item {{"
            f"  border-radius: 6px;"
            f"  margin: 1px 0;"
            f"}}"
            f"#commandPaletteList::item:selected {{"
            f"  background-color: {theme.SELECTION_BG};"
            f"}}"
            f"#commandPaletteList::item:hover {{"
            f"  background-color: {theme.BG_HOVER};"
            f"}}"
        )
        super().showEvent(event)
