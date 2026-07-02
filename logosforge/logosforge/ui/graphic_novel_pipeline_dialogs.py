"""Confirm-before-apply dialogs for the Graphic Novel planning pipeline (Phase 2).

Three small, self-contained dialogs — they never mutate anything. They show a
generated artifact, let the author edit it, and return the author's *choice*:

* :class:`PageBreakdownPreviewDialog` / :class:`PanelPlanPreviewDialog` — review a
  generated plan; Save / Cancel. Returns the edited text, or ``None`` on cancel.
  (Saving the plan is the caller's job; plans are never the Manuscript body.)
* :class:`PanelDraftPreviewDialog` — review a generated page/panel draft + its
  deterministic validation, then pick how to apply it: Apply to empty (only when
  the body is empty), Append, Replace (with an extra confirm), or Cancel.
  Returns ``(apply_mode, edited_text)`` or ``None`` — the AI never auto-applies.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)

from logosforge import graphic_novel_pipeline as gp


def _small(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet("font-size: 11px; color: #888;")
    lbl.setWordWrap(True)
    return lbl


class _PlanPreviewDialog(QDialog):
    """Shared editable plan preview (Save / Cancel)."""

    def __init__(self, plan_text: str, *, parent=None, window_title: str,
                 heading: str, blurb: str, save_label: str,
                 edit_object: str) -> None:
        super().__init__(parent)
        self._result_text: str | None = None
        self.setWindowTitle(window_title)
        self.resize(560, 520)
        self.setMinimumSize(380, 320)
        self.setSizeGripEnabled(True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)
        h = QLabel(heading)
        h.setStyleSheet("font-weight: bold;")
        layout.addWidget(h)
        layout.addWidget(_small(blurb))
        self._edit = QPlainTextEdit()
        self._edit.setObjectName(edit_object)
        self._edit.setPlainText(plan_text or "")
        layout.addWidget(self._edit, stretch=1)
        row = QHBoxLayout()
        row.addStretch()
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        row.addWidget(cancel)
        save = QPushButton(save_label)
        save.setDefault(True)
        save.clicked.connect(self._on_save)
        row.addWidget(save)
        layout.addLayout(row)

    def _on_save(self) -> None:
        if not self._edit.toPlainText().strip():
            QMessageBox.information(self, "Nothing to save", "The plan is empty.")
            return
        self._result_text = self._edit.toPlainText()
        self.accept()

    def result_text(self) -> str | None:
        return self._result_text


class PageBreakdownPreviewDialog(_PlanPreviewDialog):
    def __init__(self, plan_text: str, *, parent=None, title: str = "") -> None:
        super().__init__(
            plan_text, parent=parent,
            window_title="Page Breakdown — Review & Save",
            heading=f"Page Breakdown{f' — {title}' if title else ''}",
            blurb="The scene's page-level plan — separate from the Manuscript body "
                  "and the Outline summary. Edit freely, then Save.",
            save_label="Save Breakdown", edit_object="gnBreakdownPreviewEdit")

    @staticmethod
    def get_text(plan_text: str, *, parent=None, title: str = "") -> str | None:
        dlg = PageBreakdownPreviewDialog(plan_text, parent=parent, title=title)
        return dlg.result_text() if dlg.exec() == QDialog.DialogCode.Accepted else None


class PanelPlanPreviewDialog(_PlanPreviewDialog):
    def __init__(self, plan_text: str, *, parent=None, title: str = "") -> None:
        super().__init__(
            plan_text, parent=parent,
            window_title="Panel Plan — Review & Save",
            heading=f"Panel Plan{f' — {title}' if title else ''}",
            blurb="The scene's panel plan (visual beats per page) — separate from "
                  "the Manuscript body. Edit freely, then Save.",
            save_label="Save Panel Plan", edit_object="gnPlanPreviewEdit")

    @staticmethod
    def get_text(plan_text: str, *, parent=None, title: str = "") -> str | None:
        dlg = PanelPlanPreviewDialog(plan_text, parent=parent, title=title)
        return dlg.result_text() if dlg.exec() == QDialog.DialogCode.Accepted else None


class PanelDraftPreviewDialog(QDialog):
    def __init__(self, draft_text: str, validation, *, body_is_empty: bool,
                 parent=None, title: str = "") -> None:
        super().__init__(parent)
        self._mode: str | None = None
        self._body_is_empty = bool(body_is_empty)
        self.setWindowTitle("Draft Panels — Review & Apply")
        self.resize(640, 600)
        self.setMinimumSize(420, 360)
        self.setSizeGripEnabled(True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)
        head = QLabel(f"Panel Draft{f' — {title}' if title else ''}")
        head.setStyleSheet("font-weight: bold;")
        layout.addWidget(head)

        errors = list(getattr(validation, "errors", []) or [])
        warnings = list(getattr(validation, "warnings", []) or [])
        is_valid = bool(getattr(validation, "is_valid", True))
        if errors:
            e = QLabel("Cannot apply — fix these first:\n• " + "\n• ".join(errors))
            e.setObjectName("gnDraftErrors")
            e.setWordWrap(True)
            e.setStyleSheet("color: #d66; font-size: 11px;")
            layout.addWidget(e)
        if warnings:
            w = QLabel("Warnings (you can still apply):\n• " + "\n• ".join(warnings))
            w.setObjectName("gnDraftWarnings")
            w.setWordWrap(True)
            w.setStyleSheet("color: #c90; font-size: 11px;")
            layout.addWidget(w)

        layout.addWidget(_small(
            "Generated page/panel script (editable). This only touches the "
            "Manuscript body if you choose Apply / Append / Replace."))
        self._edit = QPlainTextEdit()
        self._edit.setObjectName("gnDraftPreviewEdit")
        self._edit.setPlainText(draft_text or "")
        layout.addWidget(self._edit, stretch=1)
        layout.addLayout(self._buttons(is_valid))

    def _buttons(self, is_valid: bool):
        row = QHBoxLayout()
        cancel = QPushButton("Cancel")
        cancel.setObjectName("gnDraftCancel")
        cancel.clicked.connect(self.reject)
        row.addWidget(cancel)
        row.addStretch()
        self._apply_empty_btn = QPushButton("Apply to empty scene")
        self._apply_empty_btn.setObjectName("gnDraftApplyEmpty")
        self._apply_empty_btn.setEnabled(is_valid and self._body_is_empty)
        self._apply_empty_btn.clicked.connect(lambda: self._choose(gp.APPLY_TO_EMPTY))
        row.addWidget(self._apply_empty_btn)
        self._append_btn = QPushButton("Append as new pages")
        self._append_btn.setObjectName("gnDraftAppend")
        self._append_btn.setEnabled(is_valid)
        self._append_btn.clicked.connect(lambda: self._choose(gp.APPLY_APPEND))
        row.addWidget(self._append_btn)
        self._replace_btn = QPushButton("Replace…")
        self._replace_btn.setObjectName("gnDraftReplace")
        self._replace_btn.setEnabled(is_valid)
        self._replace_btn.setDefault(True)
        self._replace_btn.clicked.connect(self._on_replace)
        row.addWidget(self._replace_btn)
        return row

    def _on_replace(self) -> None:
        if not self._body_is_empty:
            ok = QMessageBox.question(
                self, "Replace page/panel body?",
                "This replaces the existing page/panel script for this scene.\n"
                "A checkpoint is created first. Continue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No)
            if ok != QMessageBox.StandardButton.Yes:
                return
        self._choose(gp.APPLY_REPLACE)

    def _choose(self, mode: str) -> None:
        self._mode = mode
        self.accept()

    def chosen_mode(self) -> str | None:
        return self._mode

    def draft_text(self) -> str:
        return self._edit.toPlainText()

    @staticmethod
    def get_choice(draft_text: str, validation, *, body_is_empty: bool,
                   parent=None, title: str = "") -> tuple[str, str] | None:
        dlg = PanelDraftPreviewDialog(draft_text, validation,
                                      body_is_empty=body_is_empty, parent=parent,
                                      title=title)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.chosen_mode():
            return (dlg.chosen_mode(), dlg.draft_text())
        return None
