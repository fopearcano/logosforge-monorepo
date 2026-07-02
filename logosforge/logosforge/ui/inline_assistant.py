"""Inline AI assistant panel embedded in the scene editor."""

from collections.abc import Callable

from PySide6.QtCore import QEvent, QThread, Signal
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from logosforge.adaptive_mode import compute_mode, mode_context_block
from logosforge.assistant import (
    PRESET_ACTIONS,
    build_messages,
    chat_completion,
)
from logosforge.context_builder import (
    gather_graph_context,
    gather_outline_context,
    gather_psyke_context,
    gather_scene_context,
    gather_story_memory,
)
from logosforge.db import Database
from logosforge.memory_context import gather_memory_context
from logosforge.narrative_suggestions import (
    build_suggestion_messages,
    format_suggestion_debug,
)
from logosforge.orchestration import (
    format_orchestration_debug,
    orchestrate_psyke_context,
    resolve_mode,
)
from logosforge.prompt_router import route_prompt
from logosforge.providers import ProviderConfig
from logosforge.ui import theme
from logosforge.ui.provider_settings import ProviderSettingsWidget

SELECTION_ACTIONS = {
    "Rewrite": (
        "Rewrite the following text, improving clarity, flow, and "
        "prose quality while preserving the original meaning."
    ),
    "Expand": (
        "Expand the following text with more detail, sensory "
        "description, and emotional depth."
    ),
    "Tighten": (
        "Tighten the following text. Remove unnecessary words, "
        "cut filler, and make every sentence count. Preserve meaning."
    ),
    "Dialogue": (
        "Improve the dialogue in the following text. Make it more "
        "natural, concise, and character-appropriate. Sharpen subtext."
    ),
    "Tension": (
        "Rewrite the following text to increase tension. Heighten "
        "conflict, add urgency, and raise emotional pressure."
    ),
}

SLASH_COMMANDS: dict[str, tuple[str, str]] = {
    "/rewrite": ("selection", "Rewrite"),
    "/expand": ("selection", "Expand"),
    "/tighten": ("selection", "Tighten"),
    "/dialogue": ("selection", "Dialogue"),
    "/tension": ("selection", "Tension"),
    "/summarize": ("scene", "Summarize"),
}


def _original_style() -> str:
    return (
        f"QPlainTextEdit {{"
        f"  background-color: {theme.DIFF_ORIGINAL_BG};"
        f"  color: {theme.DIFF_ORIGINAL_TEXT};"
        f"  border: 1px solid {theme.DIFF_ORIGINAL_BORDER};"
        f"  border-radius: 6px; padding: 8px;"
        f"}}"
    )


def _proposed_style() -> str:
    return (
        f"QPlainTextEdit {{"
        f"  background-color: {theme.DIFF_PROPOSED_BG};"
        f"  color: {theme.DIFF_PROPOSED_TEXT};"
        f"  border: 1px solid {theme.DIFF_PROPOSED_BORDER};"
        f"  border-radius: 6px; padding: 8px;"
        f"}}"
    )


def _response_style() -> str:
    return (
        f"QPlainTextEdit {{"
        f"  background-color: {theme.BG_PANEL};"
        f"  color: {theme.TEXT_PRIMARY};"
        f"  border: 1px solid {theme.BORDER};"
        f"  border-radius: 6px; padding: 12px;"
        f"}}"
    )

SESSION_MEMORY_LIMIT = 3
SESSION_OUTPUT_PREVIEW_MAX = 100


class _Worker(QThread):
    completed = Signal(str)
    failed = Signal(str)

    def __init__(
        self, messages: list[dict], provider: ProviderConfig,
    ) -> None:
        super().__init__()
        self._messages = messages
        self._provider = provider

    def run(self) -> None:
        try:
            result, _from_cache = chat_completion(
                self._messages, provider=self._provider,
            )
            self.completed.emit(result)
        except Exception as e:
            self.failed.emit(str(e))


class InlineAssistantPanel(QWidget):
    slash_completed = Signal(str)

    def __init__(
        self,
        content_editor: QPlainTextEdit,
        db: Database,
        project_id: int,
        get_scene_id: Callable[[], int | None],
        on_data_changed: Callable[[], None] | None = None,
    ) -> None:
        super().__init__()
        self._editor = content_editor
        self._editor.installEventFilter(self)
        self._db = db
        self._project_id = project_id
        self._get_scene_id = get_scene_id
        self._on_data_changed = on_data_changed
        self._worker: _Worker | None = None

        self._session_memory: list[dict] = []
        self._pending_action: str = ""
        self._slash_triggered: bool = False

        self._sel_start: int | None = None
        self._sel_end: int | None = None
        self._sel_text: str | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 0)

        header = QLabel("AI Assist")
        header.setStyleSheet(f"font-weight: bold; color: {theme.TEXT_SECONDARY};")
        layout.addWidget(header)

        # -- Scene template selector -----------------------------------------
        tpl_row = QHBoxLayout()
        tpl_row.addWidget(QLabel("Scene:"))
        self._template_combo = QComboBox()
        for label in PRESET_ACTIONS:
            self._template_combo.addItem(label)
        tpl_row.addWidget(self._template_combo, stretch=1)
        self._run_template_btn = QPushButton("Run")
        self._run_template_btn.clicked.connect(self._on_run_template)
        tpl_row.addWidget(self._run_template_btn)
        layout.addLayout(tpl_row)

        layout.addSpacing(8)

        # -- Selection quick actions -----------------------------------------
        sel_label = QLabel("Selection")
        sel_label.setStyleSheet(f"color: {theme.TEXT_MUTED}; font-size: 11px;")
        layout.addWidget(sel_label)

        sel_row = QHBoxLayout()
        self._rewrite_btn = QPushButton("Rewrite")
        self._rewrite_btn.clicked.connect(
            lambda: self._run_quick_action("Rewrite"),
        )
        sel_row.addWidget(self._rewrite_btn)

        self._expand_btn = QPushButton("Expand")
        self._expand_btn.clicked.connect(
            lambda: self._run_quick_action("Expand"),
        )
        sel_row.addWidget(self._expand_btn)

        self._dialogue_btn = QPushButton("Dialogue")
        self._dialogue_btn.clicked.connect(
            lambda: self._run_quick_action("Dialogue"),
        )
        sel_row.addWidget(self._dialogue_btn)

        self._sel_more_btn = QPushButton("More")
        sel_more_menu = QMenu(self)
        sel_more_menu.addAction(
            "Tighten", lambda: self._run_quick_action("Tighten"),
        )
        sel_more_menu.addAction(
            "Tension", lambda: self._run_quick_action("Tension"),
        )
        self._sel_more_btn.setMenu(sel_more_menu)
        sel_row.addWidget(self._sel_more_btn)
        sel_row.addStretch()
        layout.addLayout(sel_row)

        layout.addSpacing(8)

        # -- Suggest Beats button --------------------------------------------
        suggest_row = QHBoxLayout()
        self._suggest_beats_btn = QPushButton("Suggest Beats")
        self._suggest_beats_btn.setToolTip(
            "Generate structured narrative direction suggestions"
        )
        self._suggest_beats_btn.clicked.connect(self._on_suggest_beats)
        suggest_row.addWidget(self._suggest_beats_btn)
        suggest_row.addStretch()
        layout.addLayout(suggest_row)

        layout.addSpacing(8)

        # -- Context section (collapsible, default collapsed) ----------------
        self._ctx_header_btn = QPushButton("\u25b6 Context")
        self._ctx_header_btn.setFlat(True)
        self._ctx_header_btn.setStyleSheet(
            f"text-align: left; color: {theme.TEXT_MUTED};"
            f" font-size: 11px; padding: 2px 0;"
        )
        self._ctx_header_btn.clicked.connect(self._toggle_context_section)
        layout.addWidget(self._ctx_header_btn)

        self._ctx_section = QWidget()
        ctx_layout = QVBoxLayout(self._ctx_section)
        ctx_layout.setContentsMargins(16, 4, 0, 0)

        self._include_outline = QCheckBox("Include outline")
        ctx_layout.addWidget(self._include_outline)

        self._include_story_memory = QCheckBox("Include story memory")
        ctx_layout.addWidget(self._include_story_memory)

        self._include_psyke = QCheckBox("Include Story Bible")
        ctx_layout.addWidget(self._include_psyke)

        self._ctx_toggle = QCheckBox("Show context sent to model")
        self._ctx_toggle.toggled.connect(self._on_ctx_toggle)
        ctx_layout.addWidget(self._ctx_toggle)

        self._ctx_viewer = QPlainTextEdit()
        self._ctx_viewer.setReadOnly(True)
        self._ctx_viewer.setMaximumHeight(180)
        self._ctx_viewer.setStyleSheet(_response_style())
        self._ctx_viewer.setPlaceholderText(
            "Context will appear here after a request..."
        )
        self._ctx_viewer.hide()
        ctx_layout.addWidget(self._ctx_viewer)

        layout.addWidget(self._ctx_section)
        self._ctx_section.hide()

        layout.addSpacing(8)

        # -- Instructions input ----------------------------------------------
        self._prompt = QPlainTextEdit()
        self._prompt.setMaximumHeight(60)
        self._prompt.setPlaceholderText("Ask about this scene...")
        layout.addWidget(self._prompt)

        # -- Generate button (primary action) --------------------------------
        gen_row = QHBoxLayout()
        gen_row.addStretch()
        self._generate_btn = QPushButton("Generate")
        self._generate_btn.setStyleSheet(theme.primary_btn())
        self._generate_btn.clicked.connect(self._on_send)
        gen_row.addWidget(self._generate_btn)
        layout.addLayout(gen_row)

        layout.addSpacing(8)

        # -- Response area ---------------------------------------------------
        self._response_container = QWidget()
        rc_layout = QVBoxLayout(self._response_container)
        rc_layout.setContentsMargins(0, 0, 0, 0)

        resp_header = QHBoxLayout()
        resp_label = QLabel("Response")
        resp_label.setStyleSheet(
            f"color: {theme.TEXT_MUTED}; font-size: 11px;"
        )
        resp_header.addWidget(resp_label)
        resp_header.addStretch()
        self._copy_btn = QPushButton("Copy")
        self._copy_btn.setFlat(True)
        self._copy_btn.setStyleSheet(
            f"color: {theme.TEXT_SECONDARY}; font-size: 11px;"
        )
        self._copy_btn.clicked.connect(self._copy_response)
        resp_header.addWidget(self._copy_btn)
        rc_layout.addLayout(resp_header)

        self._response = QPlainTextEdit()
        self._response.setReadOnly(True)
        self._response.setMaximumHeight(200)
        self._response.setPlaceholderText("Response...")
        self._response.setStyleSheet(_response_style())
        rc_layout.addWidget(self._response)

        # -- Apply actions ---------------------------------------------------
        action_row = QHBoxLayout()
        self._replace_btn = QPushButton("Replace")
        self._replace_btn.clicked.connect(self._replace_selection)
        action_row.addWidget(self._replace_btn)

        self._insert_btn = QPushButton("Insert at Cursor")
        self._insert_btn.clicked.connect(self._insert_at_cursor)
        action_row.addWidget(self._insert_btn)

        self._apply_more_btn = QPushButton("More")
        apply_more_menu = QMenu(self)
        apply_more_menu.addAction("Compare", self._show_diff)
        self._apply_more_btn.setMenu(apply_more_menu)
        action_row.addWidget(self._apply_more_btn)
        action_row.addStretch()
        rc_layout.addLayout(action_row)

        layout.addWidget(self._response_container)

        # -- Diff container (hidden by default) ------------------------------
        self._diff_container = QWidget()
        dc_layout = QVBoxLayout(self._diff_container)
        dc_layout.setContentsMargins(0, 0, 0, 0)

        orig_label = QLabel("Original")
        orig_label.setStyleSheet(
            f"font-weight: bold; color: {theme.DIFF_ORIGINAL_TEXT};"
        )
        dc_layout.addWidget(orig_label)

        self._diff_original = QPlainTextEdit()
        self._diff_original.setReadOnly(True)
        self._diff_original.setMaximumHeight(140)
        self._diff_original.setStyleSheet(_original_style())
        dc_layout.addWidget(self._diff_original)

        prop_label = QLabel("Proposed")
        prop_label.setStyleSheet(
            f"font-weight: bold; color: {theme.DIFF_PROPOSED_TEXT};"
        )
        dc_layout.addWidget(prop_label)

        self._diff_proposed = QPlainTextEdit()
        self._diff_proposed.setReadOnly(True)
        self._diff_proposed.setMaximumHeight(140)
        self._diff_proposed.setStyleSheet(_proposed_style())
        dc_layout.addWidget(self._diff_proposed)

        diff_action_row = QHBoxLayout()
        diff_replace_btn = QPushButton("Replace Selection")
        diff_replace_btn.clicked.connect(self._replace_selection)
        diff_action_row.addWidget(diff_replace_btn)

        diff_insert_btn = QPushButton("Insert at Cursor")
        diff_insert_btn.clicked.connect(self._insert_at_cursor)
        diff_action_row.addWidget(diff_insert_btn)

        diff_close_btn = QPushButton("Close")
        diff_close_btn.clicked.connect(self._close_diff)
        diff_action_row.addWidget(diff_close_btn)
        diff_action_row.addStretch()
        dc_layout.addLayout(diff_action_row)

        layout.addWidget(self._diff_container)
        self._diff_container.hide()

        # -- Provider settings -----------------------------------------------
        self._provider_widget = ProviderSettingsWidget(compact=True)
        layout.addWidget(self._provider_widget)

        mem_row = QHBoxLayout()
        self._clear_memory_btn = QPushButton("Clear Memory")
        self._clear_memory_btn.clicked.connect(self._clear_session_memory)
        mem_row.addWidget(self._clear_memory_btn)
        mem_row.addStretch()
        layout.addLayout(mem_row)

        self._interactive_buttons = [
            self._rewrite_btn, self._expand_btn, self._dialogue_btn,
            self._sel_more_btn, self._run_template_btn,
            self._suggest_beats_btn, self._generate_btn,
            self._replace_btn, self._insert_btn, self._apply_more_btn,
        ]

    # -- Scene context -------------------------------------------------------

    def _get_scene_context(self) -> str:
        scene_id = self._get_scene_id()
        if scene_id is None:
            return ""
        return gather_scene_context(self._db, self._project_id, scene_id)

    # -- Session memory -------------------------------------------------------

    def _record_session_entry(self, action: str, output: str) -> None:
        preview = output[:SESSION_OUTPUT_PREVIEW_MAX]
        if len(output) > SESSION_OUTPUT_PREVIEW_MAX:
            preview += "..."
        self._session_memory.append({"action": action, "output": preview})
        if len(self._session_memory) > SESSION_MEMORY_LIMIT:
            self._session_memory = self._session_memory[-SESSION_MEMORY_LIMIT:]

    def _build_session_memory_context(self) -> str:
        if not self._session_memory:
            return ""
        lines = ["[Session Memory]"]
        for i, entry in enumerate(self._session_memory, 1):
            lines.append(f"{i}. Action: {entry['action']}")
            lines.append(f"   Output: {entry['output']}")
        return "\n".join(lines)

    def _clear_session_memory(self) -> None:
        self._session_memory.clear()
        self._response.setPlainText("Session memory cleared.")

    # -- Context section ------------------------------------------------------

    def _toggle_context_section(self) -> None:
        visible = not self._ctx_section.isVisible()
        self._ctx_section.setVisible(visible)
        self._ctx_header_btn.setText(
            "\u25bc Context" if visible else "\u25b6 Context"
        )

    def _on_ctx_toggle(self, checked: bool) -> None:
        self._ctx_viewer.setVisible(checked)

    # -- Slash commands -------------------------------------------------------

    def eventFilter(self, obj, event):  # noqa: N802
        if obj is not self._editor:
            return super().eventFilter(obj, event)
        if event.type() != QEvent.Type.KeyPress:
            return super().eventFilter(obj, event)

        from PySide6.QtCore import Qt
        if event.key() not in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            return super().eventFilter(obj, event)

        cursor = self._editor.textCursor()
        cursor.select(cursor.SelectionType.LineUnderCursor)
        line = cursor.selectedText().strip().lower()

        if line not in SLASH_COMMANDS:
            return super().eventFilter(obj, event)

        cursor.removeSelectedText()
        doc = self._editor.toPlainText()
        new_cursor = self._editor.textCursor()
        pos = new_cursor.position()
        if pos > 0 and pos <= len(doc) and doc[pos - 1:pos] == "\n":
            new_cursor.deletePreviousChar()

        self._handle_slash_command(line)
        return True

    def _handle_slash_command(self, command: str) -> None:
        self._slash_triggered = True
        mode, key = SLASH_COMMANDS[command]

        if mode == "scene":
            prompt = PRESET_ACTIONS.get(key, "")
            if prompt:
                self._send_request(prompt, action_key=key)
            return

        instruction = SELECTION_ACTIONS.get(key, "")
        if not instruction:
            return

        cursor = self._editor.textCursor()
        selected = cursor.selectedText().replace("\u2029", "\n").strip()
        if selected:
            self._sel_start = cursor.selectionStart()
            self._sel_end = cursor.selectionEnd()
            self._sel_text = selected
            target_text = selected
        else:
            target_text = self._extract_preceding_paragraph()
            if not target_text:
                self._response.setPlainText(
                    "No text selected and no paragraph found above."
                )
                return
            self._sel_text = target_text
            self._sel_start = None
            self._sel_end = None

        prompt = f"{instruction}\n\nText:\n{target_text}"
        self._send_request(prompt, action_key=key)

    def _extract_preceding_paragraph(self) -> str:
        doc = self._editor.toPlainText()
        cursor = self._editor.textCursor()
        pos = cursor.position()
        text_before = doc[:pos].rstrip()
        if not text_before:
            return ""
        paragraphs = text_before.split("\n\n")
        last = paragraphs[-1].strip()
        return last

    # -- Selection snapshot ---------------------------------------------------

    def _snapshot_selection(self) -> str | None:
        cursor = self._editor.textCursor()
        text = cursor.selectedText().replace("\u2029", "\n")
        if not text.strip():
            self._response.setPlainText("Select text in the editor first.")
            self._sel_start = None
            self._sel_end = None
            self._sel_text = None
            return None
        self._sel_start = cursor.selectionStart()
        self._sel_end = cursor.selectionEnd()
        self._sel_text = text
        return text

    def _verify_selection(self) -> bool:
        if self._sel_start is None or self._sel_text is None:
            self._response.setPlainText(
                "No original selection recorded. "
                "Run a selection action first."
            )
            return False
        doc = self._editor.toPlainText()
        current = doc[self._sel_start:self._sel_end]
        if current != self._sel_text:
            self._response.setPlainText(
                "The original selection has changed or moved.\n"
                "Cannot replace safely.\n\n"
                "Use 'Insert at Cursor' or 'Copy' instead."
            )
            return False
        return True

    # -- Diff view -----------------------------------------------------------

    def _show_diff(self) -> None:
        proposed = self._get_response_text()
        if proposed is None:
            return
        if self._sel_text is None:
            self._response.setPlainText(
                "No original selection recorded. "
                "Run a selection action first to compare."
            )
            return

        self._diff_original.setPlainText(self._sel_text)
        self._diff_proposed.setPlainText(proposed)
        self._response_container.hide()
        self._diff_container.show()

    def _close_diff(self) -> None:
        self._diff_container.hide()
        self._response_container.show()

    # -- Quick actions (selection) -------------------------------------------

    def _run_quick_action(self, key: str) -> None:
        selected = self._snapshot_selection()
        if selected is None:
            return
        instruction = SELECTION_ACTIONS.get(key, "")
        if not instruction:
            return
        prompt = f"{instruction}\n\nText:\n{selected}"
        self._send_request(prompt, action_key=key)

    # -- Template actions (whole scene) --------------------------------------

    def _on_run_template(self) -> None:
        key = self._template_combo.currentText()
        prompt = PRESET_ACTIONS.get(key, "")
        if not prompt:
            return
        self._send_request(prompt, action_key=key)

    def _on_suggest_beats(self) -> None:
        if self._worker is not None:
            return
        scene_id = self._get_scene_id()
        if scene_id is None:
            self._response.setPlainText("No scene selected.")
            return

        error = self._provider_widget.validate()
        if error:
            self._response.setPlainText(error)
            return

        messages, ctx = build_suggestion_messages(
            self._db, self._project_id, scene_id,
        )
        if not messages:
            self._response.setPlainText("Could not build suggestion context.")
            return

        ctx_parts = []
        if ctx and ctx.psyke_context:
            ctx_parts.append(f"--- Story Bible ---\n{ctx.psyke_context}")
        if ctx:
            ctx_parts.append(format_suggestion_debug(ctx))
        self._ctx_viewer.setPlainText("\n\n".join(ctx_parts))

        self._close_diff()
        self._pending_action = "Suggest Beats"
        self._set_busy(True)
        self._response.setPlainText("Generating narrative suggestions...")

        provider = self._provider_widget.get_provider_config()
        self._worker = _Worker(messages, provider)
        self._worker.completed.connect(self._on_completed)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def _on_send(self) -> None:
        prompt = self._prompt.toPlainText().strip()
        if not prompt:
            self._response.setPlainText("Enter a prompt first.")
            return
        template_name, action_prompt = route_prompt(prompt)
        self._send_request(action_prompt, routed_to=template_name)

    # -- Provider communication ------------------------------------------------

    def _send_request(
        self, action_prompt: str, routed_to: str = "",
        action_key: str = "",
    ) -> None:
        if self._worker is not None:
            return
        scene_ctx = self._get_scene_context()
        if not scene_ctx:
            self._response.setPlainText("No scene selected.")
            return

        self._close_diff()
        self._pending_action = action_prompt.split("\n")[0][:80]

        error = self._provider_widget.validate()
        if error:
            self._response.setPlainText(error)
            return

        session_ctx = self._build_session_memory_context()

        outline_ctx = ""
        if self._include_outline.isChecked():
            outline_ctx = gather_outline_context(self._db, self._project_id)

        story_mem = ""
        if self._include_story_memory.isChecked():
            global_mem = gather_story_memory(self._db, self._project_id)
            scene_mem = gather_memory_context(
                self._db, self._project_id, scene_id=scene_id,
            )
            story_mem = "\n\n".join(
                part for part in [global_mem, scene_mem] if part
            )

        psyke_ctx = ""
        orchestration_debug = ""
        scene_id = self._get_scene_id()
        if self._include_psyke.isChecked() and scene_id is not None:
            if action_key:
                mode = resolve_mode(action_key)
                result = orchestrate_psyke_context(
                    self._db, self._project_id, scene_id, mode,
                    selected_text=self._sel_text or "",
                )
                psyke_ctx = result.psyke_context
                orchestration_debug = format_orchestration_debug(result)
            else:
                psyke_ctx = gather_psyke_context(
                    self._db, self._project_id, scene_id,
                )

        graph_ctx = ""
        if scene_id is not None:
            graph_ctx = gather_graph_context(self._db, self._project_id, scene_id)

        mode_result = compute_mode(self._db, self._project_id)
        mode_ctx = mode_context_block(mode_result)

        combined_memory = "\n\n".join(
            part for part in [story_mem, session_ctx] if part
        )
        messages = build_messages(
            action_prompt, scene_ctx,
            outline_context=outline_ctx,
            story_memory_context=combined_memory,
            psyke_context=psyke_ctx,
            graph_context=graph_ctx,
            mode_context=mode_ctx,
        )

        ctx_parts = [f"--- AI Mode ---\n{mode_ctx}"]
        ctx_parts.append(f"--- Scene Context ---\n{scene_ctx}")
        if outline_ctx:
            ctx_parts.append(f"--- Outline ---\n{outline_ctx}")
        if story_mem:
            ctx_parts.append(f"--- Story Memory ---\n{story_mem}")
        if psyke_ctx:
            ctx_parts.append(f"--- Story Bible ---\n{psyke_ctx}")
        if graph_ctx:
            ctx_parts.append(f"--- Graph Context ---\n{graph_ctx}")
        if orchestration_debug:
            ctx_parts.append(orchestration_debug)
        if session_ctx:
            ctx_parts.append(f"--- Session Memory ---\n{session_ctx}")
        ctx_parts.append(f"--- Action ---\n{action_prompt}")
        self._ctx_viewer.setPlainText("\n\n".join(ctx_parts))

        self._set_busy(True)
        if routed_to:
            self._response.setPlainText(
                f"Routed \u2192 {routed_to} | Thinking..."
            )
        else:
            self._response.setPlainText("Thinking...")

        provider = self._provider_widget.get_provider_config()
        self._worker = _Worker(messages, provider)
        self._worker.completed.connect(self._on_completed)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def _on_completed(self, text: str) -> None:
        self._response.setPlainText(text)
        if self._pending_action:
            self._record_session_entry(self._pending_action, text)
            self._pending_action = ""
        if self._slash_triggered:
            self.slash_completed.emit(text)
            self._slash_triggered = False
        self._set_busy(False)
        self._worker = None

    def _on_failed(self, error: str) -> None:
        self._response.setPlainText(f"Error:\n\n{error}")
        self._set_busy(False)
        self._worker = None

    def _set_busy(self, busy: bool) -> None:
        for btn in self._interactive_buttons:
            btn.setEnabled(not busy)

    # -- Apply actions -------------------------------------------------------

    def _get_response_text(self) -> str | None:
        text = self._response.toPlainText().strip()
        if not text or text == "Thinking..." or text.startswith("Error:"):
            return None
        if text.startswith("Routed \u2192"):
            return None
        if text.startswith("=== Context sent to the model ==="):
            return None
        if text.startswith("The original selection has changed"):
            return None
        if text.startswith("No original selection recorded"):
            return None
        if text.startswith("Select text in the editor first"):
            return None
        if text == "Session memory cleared.":
            return None
        return text

    def _replace_selection(self) -> None:
        text = self._get_response_text()
        if text is None:
            return
        if not self._verify_selection():
            self._close_diff()
            return

        answer = QMessageBox.question(
            self,
            "Replace Selection",
            "Replace the selected text with the assistant's output?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        cursor = self._editor.textCursor()
        cursor.setPosition(self._sel_start)
        cursor.setPosition(self._sel_end, cursor.MoveMode.KeepAnchor)
        cursor.insertText(text)
        self._editor.setTextCursor(cursor)
        self._editor.setFocus()

        self._sel_start = None
        self._sel_end = None
        self._sel_text = None

        self._close_diff()
        self._save_content()

    def _insert_at_cursor(self) -> None:
        text = self._get_response_text()
        if text is None:
            return

        cursor = self._editor.textCursor()
        pos = cursor.position()
        doc = self._editor.toPlainText()

        insert = text
        if pos > 0 and not doc[pos - 1].isspace():
            insert = "\n\n" + insert
        if pos < len(doc) and not doc[pos].isspace():
            insert = insert + "\n\n"

        cursor.insertText(insert)
        self._editor.setTextCursor(cursor)
        self._editor.setFocus()

        self._close_diff()
        self._save_content()

    def _copy_response(self) -> None:
        text = self._get_response_text()
        if text:
            QApplication.clipboard().setText(text)

    def _save_content(self) -> None:
        scene_id = self._get_scene_id()
        if scene_id is not None:
            self._db.update_scene_content(scene_id, self._editor.toPlainText())
            if self._on_data_changed:
                self._on_data_changed()
