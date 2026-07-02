"""Confirm-before-apply dialogs for the screenplay planning pipeline (Phase 2).

Two small, self-contained dialogs — they never mutate anything. They show a
generated artifact, let the author edit it, and return the author's *choice*:

* :class:`BeatPlanPreviewDialog` — review a generated beat plan; Save / Cancel.
  Returns the edited plan text, or ``None`` on cancel. (Saving the plan is the
  caller's job; the beat plan is never the Manuscript body.)
* :class:`DraftPreviewDialog` — review a generated screenplay draft + its
  deterministic validation, then pick how to apply it: Apply to empty (only when
  the body is empty), Replace (with an extra confirm), Append, or Cancel.
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

from logosforge import screenplay_pipeline as spp


def _small_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet("font-size: 11px; color: #888;")
    lbl.setWordWrap(True)
    return lbl


class BeatPlanPreviewDialog(QDialog):
    """Review + edit a generated beat plan before saving it.

    The beat plan is a separate artifact from the Manuscript body, so "Save" here
    only persists the plan (via the caller) — it never writes scene content.
    """

    def __init__(self, plan_text: str, parent=None, *, title: str = "") -> None:
        super().__init__(parent)
        self._result_text: str | None = None
        self.setWindowTitle("Beat Plan — Review & Save")
        self.resize(560, 520)
        self.setMinimumSize(380, 320)
        self.setSizeGripEnabled(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)

        heading = QLabel(f"Beat Plan{f' — {title}' if title else ''}")
        heading.setStyleSheet("font-weight: bold;")
        layout.addWidget(heading)
        layout.addWidget(_small_label(
            "This is the scene's dramatic plan — separate from the Manuscript "
            "body and the Outline summary. Edit freely, then Save."))

        self._edit = QPlainTextEdit()
        self._edit.setObjectName("beatPlanPreviewEdit")
        self._edit.setPlainText(plan_text or "")
        layout.addWidget(self._edit, stretch=1)

        row = QHBoxLayout()
        row.addStretch()
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        row.addWidget(cancel)
        save = QPushButton("Save Beat Plan")
        save.setObjectName("beatPlanSaveBtn")
        save.setDefault(True)
        save.clicked.connect(self._on_save)
        row.addWidget(save)
        layout.addLayout(row)

    def _on_save(self) -> None:
        text = self._edit.toPlainText().strip()
        if not text:
            QMessageBox.information(self, "Beat Plan",
                                    "The beat plan is empty — nothing to save.")
            return
        self._result_text = self._edit.toPlainText()
        self.accept()

    def result_text(self) -> str | None:
        return self._result_text

    @staticmethod
    def get_text(plan_text: str, parent=None, *, title: str = "") -> str | None:
        dlg = BeatPlanPreviewDialog(plan_text, parent, title=title)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            return dlg.result_text()
        return None


class DraftPreviewDialog(QDialog):
    """Review a generated screenplay draft and choose how to apply it.

    Nothing is mutated here — the dialog returns the chosen apply mode and the
    (possibly edited) draft text; the caller routes it through Controlled Apply
    with explicit confirmation.
    """

    def __init__(
        self, draft_text: str, validation, *, body_is_empty: bool, parent=None,
        title: str = "",
    ) -> None:
        super().__init__(parent)
        self._mode: str | None = None
        self._body_is_empty = bool(body_is_empty)
        self.setWindowTitle("Draft from Beat Plan — Review & Apply")
        self.resize(620, 600)
        self.setMinimumSize(420, 360)
        self.setSizeGripEnabled(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)

        heading = QLabel(f"Screenplay Draft{f' — {title}' if title else ''}")
        heading.setStyleSheet("font-weight: bold;")
        layout.addWidget(heading)

        # Validation summary (errors block; warnings are advisory).
        errors = list(getattr(validation, "errors", []) or [])
        warnings = list(getattr(validation, "warnings", []) or [])
        is_valid = bool(getattr(validation, "is_valid", True))
        if errors:
            err_lbl = QLabel("Cannot apply — fix these first:\n• " + "\n• ".join(errors))
            err_lbl.setObjectName("draftPreviewErrors")
            err_lbl.setWordWrap(True)
            err_lbl.setStyleSheet("color: #d66; font-size: 11px;")
            layout.addWidget(err_lbl)
        if warnings:
            warn_lbl = QLabel("Warnings (you can still apply):\n• " + "\n• ".join(warnings))
            warn_lbl.setObjectName("draftPreviewWarnings")
            warn_lbl.setWordWrap(True)
            warn_lbl.setStyleSheet("color: #c90; font-size: 11px;")
            layout.addWidget(warn_lbl)

        layout.addWidget(_small_label(
            "Generated screenplay draft (editable). This will only touch the "
            "Manuscript body if you choose Apply / Replace / Append."))
        self._edit = QPlainTextEdit()
        self._edit.setObjectName("draftPreviewEdit")
        self._edit.setPlainText(draft_text or "")
        layout.addWidget(self._edit, stretch=1)

        layout.addLayout(self._build_buttons(is_valid))

    def _build_buttons(self, is_valid: bool):
        row = QHBoxLayout()
        cancel = QPushButton("Cancel")
        cancel.setObjectName("draftCancelBtn")
        cancel.clicked.connect(self.reject)
        row.addWidget(cancel)
        row.addStretch()

        # Apply to empty — only meaningful (and only enabled) for an empty body.
        self._apply_empty_btn = QPushButton("Apply to empty scene")
        self._apply_empty_btn.setObjectName("draftApplyEmptyBtn")
        self._apply_empty_btn.setEnabled(is_valid and self._body_is_empty)
        self._apply_empty_btn.setToolTip(
            "Enabled only when the scene body is empty (never overwrites text)."
            if not self._body_is_empty else "")
        self._apply_empty_btn.clicked.connect(
            lambda: self._choose(spp.APPLY_TO_EMPTY))
        row.addWidget(self._apply_empty_btn)

        self._append_btn = QPushButton("Append")
        self._append_btn.setObjectName("draftAppendBtn")
        self._append_btn.setEnabled(is_valid)
        self._append_btn.clicked.connect(lambda: self._choose(spp.APPLY_APPEND))
        row.addWidget(self._append_btn)

        self._replace_btn = QPushButton("Replace…")
        self._replace_btn.setObjectName("draftReplaceBtn")
        self._replace_btn.setEnabled(is_valid)
        self._replace_btn.setDefault(True)
        self._replace_btn.clicked.connect(self._on_replace)
        row.addWidget(self._replace_btn)
        return row

    def _on_replace(self) -> None:
        # Replacing existing body is the one destructive choice — double-confirm.
        if not self._body_is_empty:
            ok = QMessageBox.question(
                self, "Replace scene body?",
                "This will replace the existing Manuscript text for this scene.\n"
                "A checkpoint is created first. Continue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if ok != QMessageBox.StandardButton.Yes:
                return
        self._choose(spp.APPLY_REPLACE)

    def _choose(self, mode: str) -> None:
        self._mode = mode
        self.accept()

    def chosen_mode(self) -> str | None:
        return self._mode

    def draft_text(self) -> str:
        return self._edit.toPlainText()

    @staticmethod
    def get_choice(
        draft_text: str, validation, *, body_is_empty: bool, parent=None,
        title: str = "",
    ) -> tuple[str, str] | None:
        """Show modally; return ``(apply_mode, edited_text)`` or ``None``."""
        dlg = DraftPreviewDialog(
            draft_text, validation, body_is_empty=body_is_empty, parent=parent,
            title=title)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.chosen_mode():
            return (dlg.chosen_mode(), dlg.draft_text())
        return None
