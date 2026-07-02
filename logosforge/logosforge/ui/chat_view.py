"""Project Chat — central panel for long-form, project-aware conversation.

Reuses the existing chat_completion infrastructure, PSYKE context
gatherers, and Connector action system. Messages persist per project
in the ChatMessage table; older messages are folded into a rolling
summary so prompts stay bounded.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from html import escape

from PySide6.QtCore import QByteArray, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QColor, QKeyEvent, QTextDocument, QTextOption
from PySide6.QtWidgets import (
    QColorDialog,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from logosforge.assistant import chat_completion, chat_completion_stream
from logosforge.chat_context import build_chat_context, context_summary
from logosforge.chat_memory import (
    ActionProposal,
    build_memory_frame,
    build_system_prompt,
    heuristic_summary,
    needs_summary_update,
    parse_action_proposals,
    visible_reply_text,
)
from logosforge.connector_executor import execute_action
from logosforge.connector_registry import get_action
from logosforge.db import Database
from logosforge.models.models import CHAT_PERSONALITIES
from logosforge.providers import ProviderConfig
from logosforge.ui import theme

_BODY_RE = re.compile(r"<body[^>]*>(.*)</body>", re.DOTALL)


def render_markdown_html(text: str) -> str:
    """Convert assistant Markdown to QLabel-friendly rich text.

    Uses Qt's native Markdown parser, then keeps only the inner ``<body>`` markup
    so the document-level font-size/family don't override the bubble's themed
    font. ``toHtml`` embeds no colors, so the QLabel stylesheet's text color
    still applies. Falls back to escaped plain text on any error.
    """
    text = text or ""
    try:
        doc = QTextDocument()
        doc.setMarkdown(text)
        html = doc.toHtml()
        match = _BODY_RE.search(html)
        return (match.group(1).strip() if match else html) or escape(text)
    except Exception:
        return escape(text).replace("\n", "<br>")


_PERSONALITY_LABELS: dict[str, str] = {
    "default": "Default",
    "mentor": "Mentor",
    "skeptic": "Skeptic",
    "editor": "Editor",
    "brutal": "Brutally honest",
    "whimsical": "Whimsical",
    "minimalist": "Minimalist",
    "philosopher": "Philosopher",
}


# ---------------------------------------------------------------------------
# Worker
# ---------------------------------------------------------------------------

class _ChatWorker(QThread):
    completed = Signal(str, bool)
    failed = Signal(str)
    chunk = Signal(str)

    def __init__(
        self, messages: list[dict], provider: ProviderConfig,
    ) -> None:
        super().__init__()
        self._messages = messages
        self._provider = provider

    def run(self) -> None:
        try:
            try:
                result, from_cache = chat_completion_stream(
                    self._messages, provider=self._provider,
                    on_chunk=self.chunk.emit,
                )
            except Exception:
                # Streaming unsupported or interrupted mid-flight — fall back to
                # the normal (retrying) completion so the reply still arrives.
                result, from_cache = chat_completion(
                    self._messages, provider=self._provider, use_cache=False,
                )
            self.completed.emit(result, from_cache)
        except Exception as e:
            self.failed.emit(str(e))


# ---------------------------------------------------------------------------
# Composer (input box that auto-sends on Enter)
# ---------------------------------------------------------------------------

_COMPOSER_PLACEHOLDER = "Message your project — Enter to send, Shift+Enter for newline"
_COMPOSER_BUSY_PLACEHOLDER = "Assistant is responding…"


class _Composer(QTextEdit):
    submitted = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("chatComposer")
        self.setPlaceholderText(_COMPOSER_PLACEHOLDER)
        self.setAcceptRichText(False)
        self.setWordWrapMode(QTextOption.WrapMode.WordWrap)
        self.setFixedHeight(96)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                super().keyPressEvent(event)
                return
            if self.isReadOnly():
                # Busy waiting on a reply — swallow Enter instead of queueing.
                return
            text = self.toPlainText().strip()
            if text:
                self.submitted.emit(text)
                self.clear()
            return
        super().keyPressEvent(event)


# ---------------------------------------------------------------------------
# Action card (Apply / Discard for a proposed write action)
# ---------------------------------------------------------------------------

class _ActionCard(QFrame):
    apply_requested = Signal(object)  # ActionProposal
    discarded = Signal(object)

    def __init__(
        self, proposal: ActionProposal, parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._proposal = proposal
        self.setObjectName("chatActionCard")
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setStyleSheet(
            f"#chatActionCard {{"
            f"  background-color: {theme.get('BG_INPUT')};"
            f"  border: 1px solid {theme.get('BORDER')};"
            f"  border-radius: 8px;"
            f"  padding: 10px;"
            f"}}"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)

        header = QLabel(f"Proposed action: {proposal.label}")
        header.setStyleSheet(
            f"color: {theme.get('TEXT_PRIMARY')}; font-weight: 600;"
        )
        layout.addWidget(header)

        action_def = get_action(proposal.action)
        category = action_def.category if action_def else "?"
        meta = QLabel(f"{proposal.action} ({category})")
        meta.setStyleSheet(f"color: {theme.get('TEXT_MUTED')}; font-size: 11px;")
        layout.addWidget(meta)

        if proposal.args:
            preview = QLabel(self._format_args(proposal.args))
            preview.setWordWrap(True)
            preview.setStyleSheet(
                f"color: {theme.get('TEXT_SECONDARY')}; font-size: 12px;"
                f" background: transparent;"
            )
            layout.addWidget(preview)

        button_row = QHBoxLayout()
        button_row.setContentsMargins(0, 4, 0, 0)
        button_row.setSpacing(8)

        apply_btn = QPushButton("Apply")
        apply_btn.setStyleSheet(
            f"QPushButton {{"
            f"  background-color: {theme.get('ACCENT')};"
            f"  color: {theme.get('ACCENT_TEXT')};"
            f"  border: none; padding: 6px 14px; border-radius: 6px;"
            f"}}"
            f"QPushButton:hover {{ background-color: {theme.get('ACCENT_DIM')}; }}"
        )
        apply_btn.clicked.connect(lambda: self.apply_requested.emit(self._proposal))

        discard_btn = QPushButton("Discard")
        discard_btn.setStyleSheet(
            f"QPushButton {{"
            f"  background-color: transparent;"
            f"  color: {theme.get('TEXT_MUTED')};"
            f"  border: 1px solid {theme.get('BORDER')};"
            f"  padding: 6px 14px; border-radius: 6px;"
            f"}}"
            f"QPushButton:hover {{ color: {theme.get('TEXT_PRIMARY')}; }}"
        )
        discard_btn.clicked.connect(lambda: self.discarded.emit(self._proposal))

        button_row.addWidget(apply_btn)
        button_row.addWidget(discard_btn)
        button_row.addStretch(1)
        layout.addLayout(button_row)

        self._apply_btn = apply_btn
        self._discard_btn = discard_btn
        self._status_label: QLabel | None = None

    def _format_args(self, args: dict) -> str:
        try:
            return json.dumps(args, indent=2, ensure_ascii=False)
        except (TypeError, ValueError):
            return str(args)

    def mark_executed(self, message: str) -> None:
        self._apply_btn.setEnabled(False)
        self._discard_btn.setEnabled(False)
        if self._status_label is None:
            self._status_label = QLabel(message)
            self._status_label.setStyleSheet(
                f"color: {theme.get('ACCENT')}; font-size: 11px;"
            )
            self.layout().addWidget(self._status_label)
        else:
            self._status_label.setText(message)


# ---------------------------------------------------------------------------
# Message bubble
# ---------------------------------------------------------------------------

class _MessageBubble(QFrame):
    def __init__(
        self, role: str, content: str, text_color: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("chatBubble")
        self._role = role
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        role_label_text = {
            "user": "You",
            "assistant": "Assistant",
            "system": "System",
        }.get(role, role.capitalize())
        role_label = QLabel(role_label_text)
        role_label.setStyleSheet(
            f"color: {theme.get('TEXT_MUTED')};"
            f" font-size: 11px;"
        )
        layout.addWidget(role_label)

        body = QLabel()
        body.setWordWrap(True)
        body.setStyleSheet(
            f"color: {text_color or theme.get('TEXT_PRIMARY')};"
            f" font-size: 14px; line-height: 1.45;"
        )
        if role == "assistant":
            # Render the model's Markdown (bold, lists, code, tables…) so the
            # reply reads naturally instead of showing raw markup.
            body.setTextFormat(Qt.TextFormat.RichText)
            body.setText(render_markdown_html(content))
            body.setOpenExternalLinks(True)
            body.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse
                | Qt.TextInteractionFlag.LinksAccessibleByMouse
            )
        else:
            # User/system text stays literal — never interpret it as markup.
            body.setTextFormat(Qt.TextFormat.PlainText)
            body.setText(content)
            body.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse
            )
        self._body = body
        layout.addWidget(body)

    def set_text_color(self, color: str) -> None:
        self._body.setStyleSheet(
            f"color: {color}; font-size: 14px; line-height: 1.45;"
        )


# ---------------------------------------------------------------------------
# Chat view
# ---------------------------------------------------------------------------

class ChatView(QWidget):
    """Central project chat panel.

    Can be detached into a hideable, always-on-top floating window (the
    MainWindow reparents it). Supports a window-opacity control and
    user-chosen text/background colors, persisted per project.
    """

    data_changed = Signal()

    def __init__(
        self,
        db: Database,
        project_id: int,
        on_data_changed: Callable[[], None] | None = None,
        get_active_scene_id: Callable[[], int | None] | None = None,
    ) -> None:
        super().__init__()
        self._db = db
        self._project_id = project_id
        self._on_data_changed = on_data_changed
        self._get_active_scene_id = get_active_scene_id or (lambda: None)
        self._worker: _ChatWorker | None = None
        self._action_cards: list[_ActionCard] = []
        self._typing_label: QLabel | None = None
        self._typing_timer: QTimer | None = None
        self._typing_cycle = 0
        self._stream_label: QLabel | None = None
        self._stream_text = ""
        self._awaiting_reply = False

        settings = self._db.get_project_settings(project_id)
        personality = settings.get("chat_personality", "default")
        if personality not in CHAT_PERSONALITIES:
            personality = "default"
        self._personality = personality

        # Floating-window + appearance state (opacity/colors persist per project).
        self._floating = False
        self._float_geometry: QByteArray | None = None
        self._opacity = self._clamp_opacity(settings.get("chat_opacity", 100))
        self._text_color = settings.get("chat_text_color", "") or ""
        self._bg_color = settings.get("chat_bg_color", "") or ""

        self._build_ui()
        self._reload_history()
        self._apply_appearance()

    @staticmethod
    def _clamp_opacity(value) -> int:
        try:
            return max(20, min(100, int(value)))
        except (TypeError, ValueError):
            return 100

    # -- UI ------------------------------------------------------------------

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 16, 24, 16)
        layout.setSpacing(12)

        layout.addLayout(self._build_header())
        layout.addLayout(self._build_appearance_row())

        self._messages_scroll = QScrollArea()
        self._messages_scroll.setWidgetResizable(True)
        self._messages_scroll.setFrameShape(QFrame.Shape.NoFrame)

        self._messages_host = QWidget()
        self._messages_layout = QVBoxLayout(self._messages_host)
        self._messages_layout.setContentsMargins(0, 0, 0, 0)
        self._messages_layout.setSpacing(14)
        self._messages_layout.addStretch(1)
        self._messages_scroll.setWidget(self._messages_host)
        layout.addWidget(self._messages_scroll, 1)

        self._composer = _Composer()
        self._composer.submitted.connect(self._on_user_submit)
        layout.addWidget(self._composer)

        self._status_label = QLabel(self._build_status_text())
        self._status_label.setStyleSheet(
            f"color: {theme.get('TEXT_MUTED')}; font-size: 11px;"
        )
        layout.addWidget(self._status_label)

        self.setStyleSheet(
            f"QWidget {{ background-color: {theme.get('BG_PANEL')}; }}"
        )

    def _build_header(self) -> QHBoxLayout:
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 4)
        header.setSpacing(12)

        title = QLabel("Chat")
        title.setStyleSheet(
            f"color: {theme.get('TEXT_PRIMARY')};"
            f" font-size: 22px; font-weight: 600;"
        )
        header.addWidget(title)

        header.addStretch(1)

        personality_label = QLabel("Personality:")
        personality_label.setStyleSheet(f"color: {theme.get('TEXT_MUTED')};")
        header.addWidget(personality_label)

        self._personality_combo = QComboBox()
        for key in CHAT_PERSONALITIES:
            self._personality_combo.addItem(_PERSONALITY_LABELS.get(key, key), key)
        idx = self._personality_combo.findData(self._personality)
        if idx >= 0:
            self._personality_combo.setCurrentIndex(idx)
        self._personality_combo.currentIndexChanged.connect(
            self._on_personality_changed
        )
        header.addWidget(self._personality_combo)

        clear_btn = QPushButton("Clear")
        clear_btn.setStyleSheet(self._chip_button_style())
        clear_btn.clicked.connect(self._on_clear_clicked)
        header.addWidget(clear_btn)

        return header

    @staticmethod
    def _chip_button_style() -> str:
        return (
            f"QPushButton {{ color: {theme.get('TEXT_MUTED')};"
            f" background: transparent; border: 1px solid {theme.get('BORDER')};"
            f" padding: 4px 10px; border-radius: 4px; }}"
            f"QPushButton:hover {{ color: {theme.get('TEXT_PRIMARY')}; }}"
        )

    def _build_appearance_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)

        opacity_label = QLabel("Opacity")
        opacity_label.setStyleSheet(f"color: {theme.get('TEXT_MUTED')}; font-size: 11px;")
        row.addWidget(opacity_label)

        self._opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self._opacity_slider.setRange(20, 100)
        self._opacity_slider.setValue(self._opacity)
        self._opacity_slider.setFixedWidth(120)
        self._opacity_slider.setEnabled(False)  # only meaningful while floating
        self._opacity_slider.setToolTip("Window opacity (applies to the floating window)")
        self._opacity_slider.valueChanged.connect(self._on_opacity_changed)
        row.addWidget(self._opacity_slider)

        self._opacity_value = QLabel(f"{self._opacity}%")
        self._opacity_value.setStyleSheet(f"color: {theme.get('TEXT_MUTED')}; font-size: 11px;")
        self._opacity_value.setFixedWidth(34)
        row.addWidget(self._opacity_value)

        row.addStretch(1)

        self._text_color_btn = QPushButton("Text colour")
        self._text_color_btn.setStyleSheet(self._chip_button_style())
        self._text_color_btn.clicked.connect(self._pick_text_color)
        row.addWidget(self._text_color_btn)

        self._bg_color_btn = QPushButton("Background")
        self._bg_color_btn.setStyleSheet(self._chip_button_style())
        self._bg_color_btn.clicked.connect(self._pick_bg_color)
        row.addWidget(self._bg_color_btn)

        reset_btn = QPushButton("Reset")
        reset_btn.setStyleSheet(self._chip_button_style())
        reset_btn.setToolTip("Reset colours and opacity to the theme defaults")
        reset_btn.clicked.connect(self._reset_appearance)
        row.addWidget(reset_btn)

        return row

    def _build_status_text(self) -> str:
        ctx = context_summary(
            self._db, self._project_id,
            active_scene_id=self._get_active_scene_id(),
        )
        return f"Project memory active · PSYKE context active · Actions require confirmation · {ctx}"

    # -- History rendering ---------------------------------------------------

    def _reload_history(self) -> None:
        # Drop any in-flight stream preview first so its pointer can't dangle
        # after the widgets below are torn down.
        self._clear_stream_label()
        for i in reversed(range(self._messages_layout.count() - 1)):
            item = self._messages_layout.itemAt(i)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        self._action_cards = []
        for msg in self._db.get_chat_messages(self._project_id):
            self._render_stored_message(msg)
        self._scroll_to_bottom()

    def _render_stored_message(self, msg) -> None:
        bubble = _MessageBubble(msg.role, msg.content, text_color=self._text_color or None)
        self._messages_layout.insertWidget(
            self._messages_layout.count() - 1, bubble,
        )
        if msg.role != "assistant" or not msg.metadata_json:
            return
        try:
            metadata = json.loads(msg.metadata_json)
        except (json.JSONDecodeError, TypeError):
            return
        proposals_data = metadata.get("proposals", [])
        executed = metadata.get("executed", {})
        for entry in proposals_data:
            proposal = ActionProposal(
                action=entry.get("action", ""),
                args=entry.get("args", {}),
                label=entry.get("label", entry.get("action", "")),
                raw=entry.get("raw", ""),
            )
            card = self._add_action_card(proposal)
            status = executed.get(proposal.action)
            if status:
                card.mark_executed(status)

    def _add_message_bubble(self, role: str, content: str) -> None:
        bubble = _MessageBubble(role, content, text_color=self._text_color or None)
        self._messages_layout.insertWidget(
            self._messages_layout.count() - 1, bubble,
        )
        self._scroll_to_bottom()

    def _add_action_card(self, proposal: ActionProposal) -> _ActionCard:
        card = _ActionCard(proposal)
        card.apply_requested.connect(self._on_apply_action)
        card.discarded.connect(self._on_discard_action)
        self._messages_layout.insertWidget(
            self._messages_layout.count() - 1, card,
        )
        self._action_cards.append(card)
        self._scroll_to_bottom()
        return card

    def _scroll_to_bottom(self) -> None:
        QTimer.singleShot(0, lambda: self._messages_scroll.verticalScrollBar().setValue(
            self._messages_scroll.verticalScrollBar().maximum(),
        ))

    # -- Settings ------------------------------------------------------------

    def _on_personality_changed(self) -> None:
        self._personality = self._personality_combo.currentData()
        settings = self._db.get_project_settings(self._project_id)
        settings["chat_personality"] = self._personality
        self._db.save_project_settings(self._project_id, settings)
        # Transient inline confirmation (not persisted) so the change is visible.
        label = _PERSONALITY_LABELS.get(self._personality, self._personality)
        self._add_message_bubble(
            "system", f"Personality set to {label} — applies to new messages."
        )

    # -- Float + appearance --------------------------------------------------

    def set_floating(self, floating: bool) -> None:
        """Activate floating mode: enable the opacity control and apply the
        saved window opacity. The MainWindow owns the windowing itself."""
        self._floating = floating
        self._opacity_slider.setEnabled(floating)
        self.setWindowOpacity(self._opacity / 100 if floating else 1.0)

    def is_floating(self) -> bool:
        return self._floating

    def save_float_geometry(self) -> None:
        self._float_geometry = self.saveGeometry()

    def apply_float_geometry(self) -> None:
        if self._float_geometry is not None and self.restoreGeometry(
            self._float_geometry
        ):
            return
        self.resize(460, 620)

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt override)
        # While floating, the window is hideable — closing tucks it away (re-open
        # via the Chat nav item) rather than destroying the conversation widget.
        if self._floating:
            self.save_float_geometry()
            event.ignore()
            self.hide()
            return
        super().closeEvent(event)

    def _on_opacity_changed(self, value: int) -> None:
        self._opacity = self._clamp_opacity(value)
        self._opacity_value.setText(f"{self._opacity}%")
        if self._floating:
            self.setWindowOpacity(self._opacity / 100)
        self._save_setting("chat_opacity", self._opacity)

    def _pick_text_color(self) -> None:
        start = QColor(self._text_color) if self._text_color else QColor(
            theme.get("TEXT_PRIMARY")
        )
        color = QColorDialog.getColor(start, self, "Chat text colour")
        if color.isValid():
            self._text_color = color.name()
            self._save_setting("chat_text_color", self._text_color)
            self._apply_appearance()

    def _pick_bg_color(self) -> None:
        start = QColor(self._bg_color) if self._bg_color else QColor(
            theme.get("BG_PANEL")
        )
        color = QColorDialog.getColor(start, self, "Chat background colour")
        if color.isValid():
            self._bg_color = color.name()
            self._save_setting("chat_bg_color", self._bg_color)
            self._apply_appearance()

    def _reset_appearance(self) -> None:
        self._text_color = ""
        self._bg_color = ""
        self._opacity = 100
        self._opacity_slider.setValue(100)
        self._opacity_value.setText("100%")
        self._save_setting("chat_text_color", "")
        self._save_setting("chat_bg_color", "")
        self._save_setting("chat_opacity", 100)
        if self._floating:
            self.setWindowOpacity(1.0)
        self._apply_appearance()

    def _apply_appearance(self) -> None:
        """Apply the chosen background (the view) + text colour (existing bubbles),
        in place — no widget churn, so it is safe to call while floating."""
        bg = self._bg_color or theme.get("BG_PANEL")
        self.setStyleSheet(f"QWidget {{ background-color: {bg}; }}")
        color = self._text_color or theme.get("TEXT_PRIMARY")
        for i in range(self._messages_layout.count()):
            widget = self._messages_layout.itemAt(i).widget()
            if isinstance(widget, _MessageBubble):
                widget.set_text_color(color)

    def _save_setting(self, key: str, value) -> None:
        settings = self._db.get_project_settings(self._project_id)
        settings[key] = value
        self._db.save_project_settings(self._project_id, settings)

    # -- Submit flow ---------------------------------------------------------

    def _on_user_submit(self, text: str) -> None:
        if text.startswith("/"):
            handled = self._handle_slash_command(text)
            if handled:
                return
        if self._worker is not None and self._worker.isRunning():
            return  # a reply is still streaming back — ignore the submission
        self._db.add_chat_message(self._project_id, "user", text)
        self._add_message_bubble("user", text)
        self._send_to_assistant()

    def _set_busy(self, busy: bool) -> None:
        """Reflect request state in the composer so the user knows to wait."""
        self._composer.setReadOnly(busy)
        self._composer.setPlaceholderText(
            _COMPOSER_BUSY_PLACEHOLDER if busy else _COMPOSER_PLACEHOLDER
        )

    def _send_to_assistant(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            return
        provider = self._build_provider()
        if provider is None:
            self._add_message_bubble(
                "system",
                "No AI provider configured. Open Settings → AI to set one up.",
            )
            return
        scene_id = self._get_active_scene_id()
        context = build_chat_context(
            self._db, self._project_id, active_scene_id=scene_id,
        )
        system_prompt = build_system_prompt(self._personality, context)

        all_messages = self._db.get_chat_messages(self._project_id)
        summary_record = self._db.get_chat_summary(self._project_id)
        summary_text = summary_record.summary if summary_record else ""
        last_summarized_id = summary_record.last_summarized_message_id if summary_record else 0

        frame = build_memory_frame(
            all_messages, summary_text, last_summarized_id,
        )

        messages: list[dict] = [{"role": "system", "content": system_prompt}]
        if frame.summary:
            messages.append({
                "role": "system",
                "content": f"Earlier conversation summary:\n{frame.summary}",
            })
        messages.extend(frame.recent)

        self._show_typing_indicator()
        self._set_busy(True)
        self._awaiting_reply = True
        self._worker = _ChatWorker(messages, provider)
        self._worker.chunk.connect(self._on_chunk)
        self._worker.completed.connect(self._on_completion)
        self._worker.failed.connect(self._on_failure)
        self._worker.finished.connect(self._worker.deleteLater)  # no leaked threads
        self._worker.start()

    def _on_chunk(self, token: str) -> None:
        """Append a streamed token to a live plain-text preview. The preview is
        replaced by the final Markdown-rendered bubble in _on_completion."""
        if not self._awaiting_reply:
            # A chunk queued before completion but delivered after it — ignore,
            # so we never resurrect the preview once the final bubble is shown.
            return
        if self._stream_label is None:
            self._hide_typing_indicator()
            self._stream_text = ""
            label = QLabel()
            label.setWordWrap(True)
            label.setTextFormat(Qt.TextFormat.PlainText)
            label.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse
            )
            label.setStyleSheet(
                f"color: {self._text_color or theme.get('TEXT_PRIMARY')};"
                f" font-size: 14px;"
            )
            self._messages_layout.insertWidget(
                self._messages_layout.count() - 1, label,
            )
            self._stream_label = label
        self._stream_text += token
        self._stream_label.setText(self._stream_text)
        self._scroll_to_bottom()

    def _clear_stream_label(self) -> None:
        if self._stream_label is not None:
            self._stream_label.setParent(None)
            self._stream_label.deleteLater()
            self._stream_label = None
        self._stream_text = ""

    def _build_provider(self) -> ProviderConfig | None:
        # Thin delegate to the single shared provider builder (Phase 8B).
        from logosforge.providers import build_active_provider
        return build_active_provider(require_configured=True)

    def _show_typing_indicator(self) -> None:
        if self._typing_label is not None:
            return
        label = QLabel("Assistant is thinking")
        label.setStyleSheet(
            f"color: {theme.get('TEXT_MUTED')}; font-style: italic;"
        )
        self._messages_layout.insertWidget(
            self._messages_layout.count() - 1, label,
        )
        self._typing_label = label
        self._typing_cycle = 0
        timer = QTimer(self)
        timer.setInterval(450)
        timer.timeout.connect(self._tick_typing)
        timer.start()
        self._typing_timer = timer
        self._scroll_to_bottom()

    def _tick_typing(self) -> None:
        if self._typing_label is None:
            return
        self._typing_cycle = (self._typing_cycle + 1) % 4
        self._typing_label.setText("Assistant is thinking" + "." * self._typing_cycle)

    def _hide_typing_indicator(self) -> None:
        if self._typing_timer is not None:
            self._typing_timer.stop()
            self._typing_timer.deleteLater()
            self._typing_timer = None
        if self._typing_label is not None:
            self._typing_label.setParent(None)
            self._typing_label.deleteLater()
            self._typing_label = None

    def _on_completion(self, raw_text: str, _from_cache: bool) -> None:
        self._awaiting_reply = False
        self._hide_typing_indicator()
        self._clear_stream_label()  # drop the live preview; show the final bubble
        self._set_busy(False)
        proposals = parse_action_proposals(raw_text)
        visible = visible_reply_text(raw_text, proposals)

        metadata: dict = {}
        if proposals:
            metadata["proposals"] = [
                {
                    "action": p.action,
                    "args": p.args,
                    "label": p.label,
                    "raw": p.raw,
                }
                for p in proposals
            ]

        self._db.add_chat_message(
            self._project_id, "assistant", visible,
            metadata=metadata or None,
        )
        self._add_message_bubble("assistant", visible)
        for proposal in proposals:
            self._add_action_card(proposal)

        self._maybe_update_summary()
        self._refresh_status()

    def _on_failure(self, error: str) -> None:
        self._awaiting_reply = False
        self._hide_typing_indicator()
        self._clear_stream_label()
        self._set_busy(False)
        msg = f"Assistant call failed: {error}"
        self._db.add_chat_message(self._project_id, "system", msg)
        self._add_message_bubble("system", msg)

    # -- Action confirmation -------------------------------------------------

    def _on_apply_action(self, proposal: ActionProposal) -> None:
        result = execute_action(
            self._db, self._project_id,
            {"action": proposal.action, "args": proposal.args},
            enforce_settings=False,
        )
        for card in self._action_cards:
            if card._proposal is proposal:
                if result.get("ok"):
                    card.mark_executed("Applied")
                else:
                    card.mark_executed(
                        f"Failed: {result.get('error', 'unknown error')}"
                    )
                self._persist_action_status(
                    proposal,
                    "Applied" if result.get("ok") else f"Failed: {result.get('error', '')}",
                )
                break
        if result.get("ok") and self._on_data_changed is not None:
            self._on_data_changed()

    def _on_discard_action(self, proposal: ActionProposal) -> None:
        for card in self._action_cards:
            if card._proposal is proposal:
                card.mark_executed("Discarded")
                self._persist_action_status(proposal, "Discarded")
                break

    def _persist_action_status(
        self, proposal: ActionProposal, status: str,
    ) -> None:
        messages = self._db.get_chat_messages(self._project_id)
        for msg in reversed(messages):
            if msg.role != "assistant":
                continue
            try:
                metadata = json.loads(msg.metadata_json) if msg.metadata_json else {}
            except (json.JSONDecodeError, TypeError):
                metadata = {}
            proposals = metadata.get("proposals") or []
            if any(p.get("action") == proposal.action for p in proposals):
                executed = metadata.get("executed") or {}
                executed[proposal.action] = status
                metadata["executed"] = executed
                self._db.update_chat_message_metadata(msg.id, metadata)
                return

    # -- Slash commands ------------------------------------------------------

    def _handle_slash_command(self, text: str) -> bool:
        cmd = text.strip().lower()
        if cmd == "/series" or cmd.startswith("/series "):
            self._handle_series_command(text)
            return True
        if cmd == "/gn" or cmd.startswith("/gn "):
            self._handle_gn_command(text)
            return True
        if cmd == "/context":
            ctx = build_chat_context(
                self._db, self._project_id,
                active_scene_id=self._get_active_scene_id(),
            )
            self._db.add_chat_message(self._project_id, "system", "/context")
            self._add_message_bubble("user", text)
            preview = ctx if ctx.strip() else "(no project context yet)"
            self._db.add_chat_message(self._project_id, "system", preview)
            self._add_message_bubble("system", preview)
            return True
        if cmd == "/memory":
            summary = self._db.get_chat_summary(self._project_id)
            text_out = summary.summary if summary else "(no summary yet)"
            self._add_message_bubble("user", text)
            self._add_message_bubble("system", text_out)
            self._db.add_chat_message(self._project_id, "system", text_out)
            return True
        if cmd in ("/clear chat", "/clear"):
            self._add_message_bubble("user", text)
            self._add_message_bubble(
                "system",
                "Type '/clear chat confirm' to actually clear all messages.",
            )
            return True
        if cmd == "/clear chat confirm":
            self._db.clear_chat_messages(self._project_id)
            self._reload_history()
            self._add_message_bubble("system", "Chat cleared.")
            return True
        if cmd == "/summarize chat":
            self._add_message_bubble("user", text)
            self._maybe_update_summary(force=True)
            summary = self._db.get_chat_summary(self._project_id)
            out = summary.summary if summary else "(nothing to summarize)"
            self._add_message_bubble("system", out)
            return True
        return False

    def _handle_series_command(self, text: str) -> None:
        """Render a /series … response (only meaningful for Series projects)."""
        sub = text.strip()[len("/series"):].strip()
        self._add_message_bubble("user", text)
        try:
            from logosforge.narrative_engines import engine_for_project
            project = self._db.get_project_by_id(self._project_id)
            is_series = engine_for_project(project).name == "series"
        except Exception:
            is_series = False
        if not is_series:
            out = "/series commands are only available for Series-engine projects."
        else:
            from logosforge.series_review import format_series_command
            out = format_series_command(self._db, self._project_id, sub)
        self._db.add_chat_message(self._project_id, "system", out)
        self._add_message_bubble("system", out)

    def _handle_gn_command(self, text: str) -> None:
        """Render a /gn … response (only meaningful for Graphic Novel projects)."""
        sub = text.strip()[len("/gn"):].strip()
        self._add_message_bubble("user", text)
        try:
            from logosforge.narrative_engines import engine_for_project
            project = self._db.get_project_by_id(self._project_id)
            is_gn = engine_for_project(project).name == "graphic_novel"
        except Exception:
            is_gn = False
        if not is_gn:
            out = "/gn commands are only available for Graphic Novel projects."
        else:
            from logosforge.graphic_novel_review import format_gn_command
            out = format_gn_command(self._db, self._project_id, sub)
        self._db.add_chat_message(self._project_id, "system", out)
        self._add_message_bubble("system", out)

    # -- Memory --------------------------------------------------------------

    def _maybe_update_summary(self, force: bool = False) -> None:
        all_messages = self._db.get_chat_messages(self._project_id)
        summary_record = self._db.get_chat_summary(self._project_id)
        last_id = summary_record.last_summarized_message_id if summary_record else 0
        previous = summary_record.summary if summary_record else ""
        if not force and not needs_summary_update(all_messages, last_id):
            return
        from logosforge.chat_memory import RECENT_WINDOW
        if force:
            new_messages = [m for m in all_messages if (m.id or 0) > last_id]
        else:
            older = all_messages[:-RECENT_WINDOW] if len(all_messages) > RECENT_WINDOW else []
            new_messages = [m for m in older if (m.id or 0) > last_id]
        if not new_messages:
            return
        new_summary, new_last_id = heuristic_summary(previous, new_messages)
        self._db.update_chat_summary(self._project_id, new_summary, new_last_id)

    # -- Misc ----------------------------------------------------------------

    def _on_clear_clicked(self) -> None:
        self._handle_slash_command("/clear chat")

    def _refresh_status(self) -> None:
        self._status_label.setText(self._build_status_text())
