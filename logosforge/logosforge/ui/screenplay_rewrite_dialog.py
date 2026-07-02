"""Controlled screenplay rewrite — preview / diff / confirmed-apply dialog (Phase 6).

Self-contained and non-mutating: it shows the original vs the proposed revision
(with a block diff + validation), lets the author edit the proposed text, and
returns only the author's chosen apply mode. The caller routes it through
``screenplay_rewrite.apply_rewrite`` (confirmed). The AI never overwrites here.
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

from logosforge import screenplay_rewrite as srw


def _small(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet("font-size: 11px; color: #888;")
    lbl.setWordWrap(True)
    return lbl


class RewritePreviewDialog(QDialog):
    def __init__(self, preview, *, parent=None, title: str = "") -> None:
        super().__init__(parent)
        self._preview = preview
        self._mode: str | None = None
        self._body_is_empty = bool(getattr(preview, "body_is_empty", True))
        self.setWindowTitle("Controlled Rewrite — Review & Apply")
        self.resize(680, 640)
        self.setMinimumSize(460, 400)
        self.setSizeGripEnabled(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)

        heading = QLabel(f"Controlled Rewrite{f' — {title}' if title else ''}")
        heading.setStyleSheet("font-weight: bold;")
        layout.addWidget(heading)

        # Make the rewrite target explicit before the author applies anything.
        _target_label = {
            srw.TARGET_SELECTION: "selected text",
            srw.TARGET_BLOCK: "selected block",
            srw.TARGET_SCENE: "whole scene",
        }.get(getattr(preview, "target", srw.TARGET_SCENE), "whole scene")
        target_row = QLabel(f"Target: {_target_label}")
        target_row.setObjectName("rewriteTarget")
        target_row.setStyleSheet("font-size: 11px; color: #aaa;")
        layout.addWidget(target_row)

        bd = getattr(preview, "block_diff", {}) or {}
        layout.addWidget(_small(
            f"Block changes — changed: {bd.get('changed', 0)} · added: "
            f"{bd.get('added', 0)} · removed: {bd.get('removed', 0)} · unchanged: "
            f"{bd.get('unchanged', 0)}"))

        errors = list(getattr(preview, "errors", []) or [])
        warnings = list(getattr(preview, "warnings", []) or [])
        if errors:
            e = QLabel("Cannot apply — fix these first:\n• " + "\n• ".join(errors))
            e.setObjectName("rewriteErrors")
            e.setWordWrap(True)
            e.setStyleSheet("color: #d66; font-size: 11px;")
            layout.addWidget(e)
        if warnings:
            w = QLabel("Warnings (you can still apply):\n• " + "\n• ".join(warnings))
            w.setObjectName("rewriteWarnings")
            w.setWordWrap(True)
            w.setStyleSheet("color: #c90; font-size: 11px;")
            layout.addWidget(w)

        layout.addWidget(_small("Original (read-only):"))
        self._orig = QPlainTextEdit()
        self._orig.setObjectName("rewriteOriginal")
        self._orig.setReadOnly(True)
        self._orig.setPlainText(getattr(preview, "original_text", "") or "")
        self._orig.setMaximumHeight(160)
        layout.addWidget(self._orig)

        layout.addWidget(_small("Proposed revision (editable):"))
        self._proposed = QPlainTextEdit()
        self._proposed.setObjectName("rewriteProposed")
        self._proposed.setPlainText(getattr(preview, "proposed_text", "") or "")
        layout.addWidget(self._proposed, stretch=1)

        layout.addLayout(self._build_buttons(bool(getattr(preview, "can_apply", True))))

    def _build_buttons(self, can_apply: bool):
        row = QHBoxLayout()
        cancel = QPushButton("Cancel")
        cancel.setObjectName("rewriteCancel")
        cancel.clicked.connect(self.reject)
        row.addWidget(cancel)
        row.addStretch()

        copy = QPushButton("Copy Only")
        copy.setObjectName("rewriteCopyOnly")
        copy.clicked.connect(lambda: self._choose(srw.MODE_COPY_ONLY))
        row.addWidget(copy)

        candidate = QPushButton("Save Candidate")
        candidate.setObjectName("rewriteSaveCandidate")
        candidate.setEnabled(can_apply)
        candidate.clicked.connect(lambda: self._choose(srw.MODE_REVISION_CANDIDATE))
        row.addWidget(candidate)

        self._append_btn = QPushButton("Append as Alternate")
        self._append_btn.setObjectName("rewriteAppend")
        self._append_btn.setEnabled(can_apply)
        self._append_btn.clicked.connect(lambda: self._choose(srw.MODE_APPEND_ALTERNATE))
        row.addWidget(self._append_btn)

        self._replace_btn = QPushButton("Apply Replacement")
        self._replace_btn.setObjectName("rewriteReplace")
        self._replace_btn.setEnabled(can_apply)
        self._replace_btn.setDefault(True)
        self._replace_btn.clicked.connect(self._on_replace)
        row.addWidget(self._replace_btn)
        return row

    def _on_replace(self) -> None:
        if not self._body_is_empty:
            ok = QMessageBox.question(
                self, "Replace scene content?",
                "This replaces the current Manuscript text for this target.\n"
                "A checkpoint is created first. Continue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if ok != QMessageBox.StandardButton.Yes:
                return
        self._choose(srw.MODE_REPLACE)

    def _choose(self, mode: str) -> None:
        self._mode = mode
        self.accept()

    def chosen_mode(self) -> str | None:
        return self._mode

    def proposed_text(self) -> str:
        return self._proposed.toPlainText()

    @staticmethod
    def get_choice(preview, *, parent=None, title: str = "") -> tuple[str, str] | None:
        """Show modally; return ``(mode, edited_text)`` or None if cancelled."""
        dlg = RewritePreviewDialog(preview, parent=parent, title=title)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.chosen_mode():
            return (dlg.chosen_mode(), dlg.proposed_text())
        return None
