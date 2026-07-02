"""Inline AI editing bar — floating widget for selection-based AI actions."""

from collections.abc import Callable

from PySide6.QtCore import QEvent, Qt, QThread, Signal
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from logosforge.assistant import build_messages, chat_completion
from logosforge.context_builder import gather_scene_context
from logosforge.db import Database
from logosforge.providers import ProviderConfig
from logosforge.ui import theme
from logosforge.ui.inline_assistant import SELECTION_ACTIONS, SLASH_COMMANDS
from logosforge.ui.provider_settings import ProviderSettingsWidget

def _bar_style() -> str:
    return (
        f"InlineEditBar {{ background: {theme.BG_PANEL};"
        f" border: 1px solid {theme.BORDER}; border-radius: 6px; }}"
    )


def _suggestion_style() -> str:
    return (
        f"QPlainTextEdit {{ background: {theme.DIFF_PROPOSED_BG};"
        f" color: {theme.DIFF_PROPOSED_TEXT};"
        f" border: 1px solid {theme.DIFF_PROPOSED_BORDER};"
        f" border-radius: 5px; padding: 8px; }}"
    )


class _InlineWorker(QThread):
    completed = Signal(str)
    failed = Signal(str)

    def __init__(self, messages: list[dict], provider: ProviderConfig) -> None:
        super().__init__()
        self._messages = messages
        self._provider = provider

    def run(self) -> None:
        try:
            result, _from_cache = chat_completion(
                self._messages, provider=self._provider,
            )
            self.completed.emit(result)
        except Exception as exc:
            self.failed.emit(str(exc))


class InlineEditBar(QWidget):
    """Floating action bar + inline suggestion for AI editing."""

    ai_action_completed = Signal()

    def __init__(
        self,
        editor: QPlainTextEdit,
        db: Database,
        project_id: int,
        get_scene_id: Callable[[], int | None],
        provider_widget: ProviderSettingsWidget,
        on_data_changed: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(editor.viewport())
        self.setObjectName("InlineEditBar")
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setStyleSheet(_bar_style())
        self.setMaximumWidth(400)

        self._editor = editor
        self._db = db
        self._project_id = project_id
        self._get_scene_id = get_scene_id
        self._provider_widget = provider_widget
        self._on_data_changed = on_data_changed
        self._worker: _InlineWorker | None = None

        self._sel_start: int | None = None
        self._sel_end: int | None = None
        self._sel_text: str | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(4)

        # -- Action buttons --------------------------------------------------
        self._action_row = QWidget()
        self._action_row.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        ar = QHBoxLayout(self._action_row)
        ar.setContentsMargins(0, 0, 0, 0)
        ar.setSpacing(4)
        for label in ("Rewrite", "Expand", "Dialogue"):
            btn = QPushButton(label)
            btn.setStyleSheet(theme.small_btn())
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            btn.clicked.connect(lambda _, k=label: self._run_action(k))
            ar.addWidget(btn)
        layout.addWidget(self._action_row)

        # -- Loading indicator ------------------------------------------------
        self._loading_label = QLabel("Thinking\u2026")
        self._loading_label.setStyleSheet(
            f"color: {theme.TEXT_MUTED}; font-size: 11px; padding: 2px;"
        )
        self._loading_label.hide()
        layout.addWidget(self._loading_label)

        # -- Result area ------------------------------------------------------
        self._result_area = QWidget()
        self._result_area.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        ra = QVBoxLayout(self._result_area)
        ra.setContentsMargins(0, 0, 0, 0)
        ra.setSpacing(4)

        self._suggestion = QPlainTextEdit()
        self._suggestion.setReadOnly(True)
        self._suggestion.setMaximumHeight(120)
        self._suggestion.setStyleSheet(_suggestion_style())
        self._suggestion.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        ra.addWidget(self._suggestion)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(4)
        for label, slot in (
            ("Replace", self._on_replace),
            ("Insert below", self._on_insert_below),
            ("Cancel", self._dismiss),
        ):
            btn = QPushButton(label)
            btn.setStyleSheet(theme.small_btn())
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            btn.clicked.connect(slot)
            btn_row.addWidget(btn)
        btn_row.addStretch()
        ra.addLayout(btn_row)

        self._result_area.hide()
        layout.addWidget(self._result_area)

        self.hide()

        self._editor.selectionChanged.connect(self._on_selection_changed)
        self._editor.verticalScrollBar().valueChanged.connect(self._reposition)

    # -- Public API ----------------------------------------------------------

    def activate(self) -> None:
        cursor = self._editor.textCursor()
        text = cursor.selectedText().replace("\u2029", "\n").strip()
        if not text:
            return
        self._sel_start = cursor.selectionStart()
        self._sel_end = cursor.selectionEnd()
        self._sel_text = text
        self._show_actions()

    def show_inline_result(self, text: str) -> None:
        cursor = self._editor.textCursor()
        pos = cursor.position()
        self._sel_end = pos
        self.show()
        self._show_result(text)

    # -- Selection tracking --------------------------------------------------

    def _on_selection_changed(self) -> None:
        if self._result_area.isVisible() or self._loading_label.isVisible():
            return
        cursor = self._editor.textCursor()
        text = cursor.selectedText().replace("\u2029", "\n").strip()
        if text:
            self._sel_start = cursor.selectionStart()
            self._sel_end = cursor.selectionEnd()
            self._sel_text = text
            self._show_actions()
        elif self._action_row.isVisible():
            self.hide()

    # -- State transitions ---------------------------------------------------

    def _show_actions(self) -> None:
        self._action_row.show()
        self._loading_label.hide()
        self._result_area.hide()
        self.adjustSize()
        self.show()
        self._reposition()

    def _show_loading(self) -> None:
        self._action_row.hide()
        self._loading_label.show()
        self._result_area.hide()
        self.adjustSize()
        self._reposition()

    def _show_result(self, text: str) -> None:
        self._suggestion.setPlainText(text)
        self._action_row.hide()
        self._loading_label.hide()
        self._result_area.show()
        self.adjustSize()
        self._reposition()

    def _dismiss(self) -> None:
        self.hide()
        self._action_row.hide()
        self._loading_label.hide()
        self._result_area.hide()
        self._sel_start = None
        self._sel_end = None
        self._sel_text = None
        self._worker = None

    # -- Positioning ---------------------------------------------------------

    def _reposition(self) -> None:
        if not self.isVisible() or self._sel_end is None:
            return
        doc = self._editor.document()
        pos = min(self._sel_end, doc.characterCount() - 1)
        cursor = QTextCursor(doc)
        cursor.setPosition(max(pos, 0))
        rect = self._editor.cursorRect(cursor)

        vp = self._editor.viewport()
        x = max(rect.x(), 8)
        y = rect.y() + rect.height() + 4
        if x + self.width() > vp.width():
            x = max(vp.width() - self.width() - 8, 8)
        if y + self.height() > vp.height():
            y = rect.y() - self.height() - 4
        self.move(max(x, 0), max(y, 0))

    # -- AI actions ----------------------------------------------------------

    def _run_action(self, key: str) -> None:
        if self._worker is not None or not self._sel_text:
            return

        instruction = SELECTION_ACTIONS.get(key, "")
        if not instruction:
            return

        error = self._provider_widget.validate()
        if error:
            self._show_result(f"Provider error: {error}")
            return

        scene_id = self._get_scene_id()
        if scene_id is None:
            self._show_result("No scene selected.")
            return

        scene_ctx = gather_scene_context(self._db, self._project_id, scene_id)
        prompt = f"{instruction}\n\nText:\n{self._sel_text}"
        messages = build_messages(prompt, scene_ctx)

        self._show_loading()

        provider = self._provider_widget.get_provider_config()
        self._worker = _InlineWorker(messages, provider)
        self._worker.completed.connect(self._on_completed)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def _on_completed(self, text: str) -> None:
        self._show_result(text)
        self._worker = None
        self.ai_action_completed.emit()

    def _on_failed(self, error: str) -> None:
        self._show_result(f"Error: {error}")
        self._worker = None

    # -- Apply actions -------------------------------------------------------

    def _on_replace(self) -> None:
        text = self._suggestion.toPlainText().strip()
        if not text or self._sel_start is None or self._sel_text is None:
            return

        doc = self._editor.toPlainText()
        current = doc[self._sel_start : self._sel_end]
        if current != self._sel_text:
            self._suggestion.setPlainText(
                "Selection changed since action was run.\n"
                "Use 'Insert below' instead."
            )
            return

        cursor = self._editor.textCursor()
        cursor.setPosition(self._sel_start)
        cursor.setPosition(self._sel_end, cursor.MoveMode.KeepAnchor)
        cursor.insertText(text)
        self._editor.setTextCursor(cursor)
        self._save_content()
        self._dismiss()

    def _on_insert_below(self) -> None:
        text = self._suggestion.toPlainText().strip()
        if not text:
            return

        cursor = self._editor.textCursor()
        if self._sel_end is not None:
            cursor.setPosition(self._sel_end)

        doc = self._editor.toPlainText()
        pos = cursor.position()
        insert = text
        if pos > 0 and not doc[pos - 1 : pos].isspace():
            insert = "\n\n" + insert
        if pos < len(doc) and not doc[pos : pos + 1].isspace():
            insert = insert + "\n\n"

        cursor.insertText(insert)
        self._editor.setTextCursor(cursor)
        self._save_content()
        self._dismiss()

    def _save_content(self) -> None:
        scene_id = self._get_scene_id()
        if scene_id is not None:
            self._db.update_scene_content(
                scene_id, self._editor.toPlainText()
            )
            if self._on_data_changed:
                self._on_data_changed()
