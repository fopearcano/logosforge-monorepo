"""Resizable confirmation dialog for applying a generated outline.

Replaces the old ``QMessageBox.question`` (which crammed the whole preview into
the message text and pushed the buttons off-screen for long outlines).  The
preview scrolls inside a resizable window; Apply/Cancel stay pinned at the
bottom and remain reachable even at the minimum size.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QPlainTextEdit,
    QVBoxLayout,
)


class OutlineConfirmDialog(QDialog):
    """Preview + confirm dialog for an outline that will be applied."""

    def __init__(
        self,
        preview: str,
        node_count: int,
        *,
        title: str = "Apply to Outline",
        warnings: list[str] | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        # A comfortable default (the user can resize); the minimum stays SMALL
        # on purpose so the dialog always fits a 13-inch / 800px screen — the
        # preview area scrolls, and the confirm/cancel buttons stay pinned
        # outside it.
        self.resize(560, 600)
        self.setMinimumSize(360, 320)
        self.setSizeGripEnabled(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        heading = QLabel(
            f"Add {node_count} item(s) to the Outline?\n"
            "Existing structure is kept — the new items are appended."
        )
        heading.setWordWrap(True)
        heading.setStyleSheet("font-weight: bold;")
        layout.addWidget(heading)

        # Quality warnings (missing descriptions repaired, prose trimmed, …) —
        # shown above the preview so the user sees them before applying.
        if warnings:
            warn = QLabel("⚠ " + "\n⚠ ".join(warnings))
            warn.setWordWrap(True)
            warn.setStyleSheet("color: #c79a3e;")  # amber
            self._warnings_label = warn
            layout.addWidget(warn)

        # Scrolling preview — read-only; only this area grows/scrolls.
        self._preview = QPlainTextEdit()
        self._preview.setReadOnly(True)
        self._preview.setPlainText(preview)
        self._preview.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        layout.addWidget(self._preview, stretch=1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Apply")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        # Pinned at the bottom, outside the stretch — always visible.
        layout.addWidget(buttons, alignment=Qt.AlignmentFlag.AlignRight)

    @staticmethod
    def confirm(
        preview: str, node_count: int, *,
        title: str = "Apply to Outline",
        warnings: list[str] | None = None, parent=None,
    ) -> bool:
        """Show the dialog modally; return True if the user clicked Apply."""
        dlg = OutlineConfirmDialog(
            preview, node_count, title=title, warnings=warnings, parent=parent,
        )
        return dlg.exec() == QDialog.DialogCode.Accepted
