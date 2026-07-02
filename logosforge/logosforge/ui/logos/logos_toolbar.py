"""LogosToolbar — a compact, non-intrusive inline Logos entry point.

A slim bar that sits below the section content. It shows the Logos actions
available for the current section and renders the structured
:class:`LogosResult` in a small read-only area. It is hidden by default, never
pops up on its own, and never steals focus.

Phase 1: actions call the real (shared) Assistant backend off the UI thread so
the bar shows a visible loading state and stays responsive; the result can be
copied or dismissed; errors render in-place.

It is deliberately separate from AssistantPanel/AssistantDock: it does not touch
them, owns no provider settings, and only calls the shared LogosController.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from logosforge.logos.controller import LogosController
from logosforge.logos.result import LogosResult
from logosforge.ui import theme


class _LogosWorker(QThread):
    """Runs a Logos action off the UI thread so the bar never freezes."""

    done = Signal(object)  # LogosResult

    def __init__(self, controller: LogosController, context, action_name: str) -> None:
        super().__init__()
        self._controller = controller
        self._context = context
        self._action_name = action_name

    def run(self) -> None:
        try:
            result = self._controller.run(self._context, self._action_name)
        except Exception as exc:  # pragma: no cover - defensive
            result = LogosResult.failure(self._action_name, f"Logos error: {exc}")
        self.done.emit(result)


class LogosToolbar(QWidget):
    """Inline Logos action bar + result preview for one section at a time."""

    action_completed = Signal(str, bool)  # (action_name, ok)

    def __init__(
        self,
        controller: LogosController,
        context_provider: Callable[[], object],
        parent: QWidget | None = None,
        on_request_apply: Callable[[object, object], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self._controller = controller
        # Pulls a fresh LogosContext on demand (so selection/section are live).
        self._context_provider = context_provider
        # Called when the user clicks "Apply…": (result, context) -> None.
        self._on_request_apply = on_request_apply
        self._section = ""
        self._worker: _LogosWorker | None = None
        self._last_result: LogosResult | None = None
        self._last_context: object | None = None

        self.setObjectName("logosToolbar")
        # Don't grab focus when shown — Logos must never steal the caret.
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 4, 8, 6)
        outer.setSpacing(4)

        self._row = QHBoxLayout()
        self._row.setSpacing(6)
        self._title = QLabel("Logos")
        self._title.setStyleSheet(
            f"color: {theme.ACCENT}; font-weight: bold; font-size: 11px;"
        )
        self._row.addWidget(self._title)
        # Readable dropdown of actions instead of a row of tiny, clipping
        # buttons. Selecting an item runs that action; the global stylesheet
        # themes the combo (Dark / Green / Warm).
        self._action_combo = QComboBox()
        self._action_combo.setObjectName("logosActionCombo")
        self._action_combo.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._action_combo.setMinimumWidth(160)
        self._action_combo.setToolTip("Choose a Logos action to run")
        self._action_combo.activated.connect(self._on_action_selected)
        self._row.addWidget(self._action_combo)
        self._row.addStretch()
        self._status = QLabel("")
        self._status.setStyleSheet(f"color: {theme.TEXT_MUTED}; font-size: 10px;")
        self._row.addWidget(self._status)

        self._copy_btn = self._tool_button("Copy", self._copy_result)
        self._dismiss_btn = self._tool_button("Dismiss", self.clear_result)
        self._apply_btn = self._tool_button("Apply…", self._request_apply)
        self._apply_btn.setEnabled(False)
        self._copy_btn.setEnabled(False)
        self._dismiss_btn.setEnabled(False)
        self._row.addWidget(self._apply_btn)
        self._row.addWidget(self._copy_btn)
        self._row.addWidget(self._dismiss_btn)
        outer.addLayout(self._row)

        self._result = QPlainTextEdit()
        self._result.setReadOnly(True)
        self._result.setMaximumHeight(120)
        self._result.setPlaceholderText(
            "Select text (Manuscript) or open an outline node, then run a Logos "
            "action.",
        )
        self._result.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        outer.addWidget(self._result)

    # -- Small helpers -------------------------------------------------------

    def _tool_button(self, label: str, slot: Callable[[], None]) -> QPushButton:
        btn = QPushButton(label)
        btn.setFlat(True)
        btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn.setStyleSheet(
            f"QPushButton {{ color: {theme.TEXT_MUTED}; border: none; "
            f"font-size: 10px; padding: 1px 6px; }}"
            f"QPushButton:hover:enabled {{ color: {theme.TEXT_PRIMARY}; }}"
        )
        btn.clicked.connect(slot)
        return btn

    # -- Section wiring ------------------------------------------------------

    def set_section(self, section_name: str) -> None:
        if section_name == self._section:
            return
        self._section = section_name
        self.refresh_actions()

    def refresh_actions(self) -> None:
        # Mode-aware: pull the live LogosContext so screenplay-only actions
        # show (and order first) in screenplay projects, and stay hidden in
        # Novel. Falls back to unfiltered if the mode can't be resolved.
        writing_mode = ""
        try:
            ctx = self._context_provider()
            writing_mode = getattr(ctx, "writing_mode", "") or ""
        except Exception:
            writing_mode = ""
        actions = self._controller.available_actions(
            self._section, writing_mode=writing_mode,
        )
        # Group actions by readable UX category (Planning / Checks / Reflection /
        # Rewrite / Export). Separators only appear *between* groups, so index 1
        # remains a real action and the dropdown stays readable at small widths.
        from logosforge.logos.actions import group_actions
        grouped = group_actions(actions)
        self._action_combo.blockSignals(True)
        self._action_combo.clear()
        self._action_combo.addItem("Choose action…", userData="")
        for gi, (group_label, group_actions_) in enumerate(grouped):
            if gi > 0:
                self._action_combo.insertSeparator(self._action_combo.count())
            for action in group_actions_:
                self._action_combo.addItem(action.label, userData=action.name)
                idx = self._action_combo.count() - 1
                tip = action.description or ""
                if action.needs_selection:
                    tip = (tip + " " if tip else "") + "(needs selected text)"
                self._action_combo.setItemData(
                    idx, f"{group_label}: {action.label}", Qt.ItemDataRole.AccessibleTextRole)
                if tip:
                    self._action_combo.setItemData(
                        idx, tip, Qt.ItemDataRole.ToolTipRole)
        self._action_combo.setCurrentIndex(0)
        self._action_combo.blockSignals(False)
        self._action_combo.setEnabled(bool(actions))

        if not actions:
            # Section-scoped, not a loading state — most Logos actions are
            # deterministic (no AI needed), so "no actions here" is definitive.
            self._status.setText("No Logos actions for this section.")
        else:
            self._status.setText("")

    def _on_action_selected(self, index: int) -> None:
        """Run the action chosen from the dropdown (index 0 is the placeholder)."""
        if index <= 0:
            return
        name = self._action_combo.itemData(index)
        if name:
            self.run_action(name)

    def available_action_names(self) -> list[str]:
        """Action names currently offered in the dropdown (excludes placeholder
        and group separators)."""
        return [d for i in range(1, self._action_combo.count())
                if (d := self._action_combo.itemData(i))]

    # -- Run -----------------------------------------------------------------

    def run_action(self, action_name: str) -> None:
        """Pull a fresh context from the host, then run the action."""
        try:
            context = self._context_provider()
        except Exception as exc:  # never crash the host on context capture
            self._render(LogosResult.failure(action_name, f"Could not read context: {exc}"))
            self.action_completed.emit(action_name, False)
            return
        self.run_action_with_context(context, action_name)

    def run_action_with_context(self, context, action_name: str) -> None:
        """Run an action against an explicit context (e.g. an outline node)."""
        if self._worker is not None:
            return  # one at a time
        self._last_context = context
        self._set_busy(True)
        worker = _LogosWorker(self._controller, context, action_name)
        worker.done.connect(lambda res, n=action_name: self._on_done(n, res))
        self._worker = worker
        worker.start()

    def _on_done(self, action_name: str, result: LogosResult) -> None:
        self._worker = None
        self._set_busy(False)
        self._render(result)
        self.action_completed.emit(action_name, bool(result.ok))

    def _set_busy(self, busy: bool) -> None:
        self._status.setText("Logos thinking…" if busy else "")
        self._action_combo.setEnabled(not busy)

    # -- Result display ------------------------------------------------------

    def _render(self, result: LogosResult) -> None:
        self._last_result = result
        lines: list[str] = []
        if result.title:
            lines.append(f"▸ {result.title}")
        if not result.ok and result.error:
            lines.append(f"⚠ {result.error}")
        if result.message:
            lines.append(result.message)
        if result.suggestions:
            lines.append("")
            lines.extend(f"• {s}" for s in result.suggestions)
        text = "\n".join(lines).strip()
        self._result.setPlainText(text)
        has_text = bool(text)
        self._copy_btn.setEnabled(has_text)
        self._dismiss_btn.setEnabled(has_text)
        # "Apply…" only when the result carries confirmable operations and a
        # handler is wired.
        can_apply = bool(
            result.ok and result.proposed_operations and self._on_request_apply
        )
        self._apply_btn.setEnabled(can_apply)

    def _request_apply(self) -> None:
        if (
            self._on_request_apply is None
            or self._last_result is None
            or not self._last_result.proposed_operations
        ):
            return
        self._on_request_apply(self._last_result, self._last_context)

    def set_status(self, text: str) -> None:
        self._status.setText(text)

    def result_text(self) -> str:
        return self._result.toPlainText()

    def clear_result(self) -> None:
        self._result.clear()
        self._last_result = None
        self._copy_btn.setEnabled(False)
        self._dismiss_btn.setEnabled(False)
        self._apply_btn.setEnabled(False)

    def _copy_result(self) -> None:
        text = self._result.toPlainText()
        if text:
            QApplication.clipboard().setText(text)
            self._status.setText("Copied")
