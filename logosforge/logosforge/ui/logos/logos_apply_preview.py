"""LogosApplyPreview — confirm-before-apply dialog for Logos Phase 2.

Shows the proposed change and returns a *finalized* structured operation only
when the user confirms. It never mutates anything itself; the caller applies the
returned operation through ``logosforge.logos.operations``.

* Manuscript: a read-only "Before" (current selection) and an editable
  "Generated" box; buttons Apply Replace / Insert After / Copy / Cancel.
* Outline: editable Title + Summary fields; buttons Create Node / Update Summary
  / Update Title / Copy / Cancel (update buttons appear only for a real node).

Resizable, scrollable, with the action buttons pinned at the bottom.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from logosforge.logos import operations as ops


class LogosApplyPreview(QDialog):
    def __init__(self, result, context, parent=None) -> None:
        super().__init__(parent)
        self._result = result
        self._context = context
        self._operation: dict | None = None  # finalized op, set on confirm

        self._target = (
            result.proposed_operations[0]["target"]
            if result.proposed_operations else ""
        )

        self.setWindowTitle("Logos — Review & Apply")
        self.resize(560, 560)
        self.setMinimumSize(380, 340)
        self.setSizeGripEnabled(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)

        heading = QLabel(result.title or "Logos result")
        heading.setStyleSheet("font-weight: bold;")
        layout.addWidget(heading)

        if self._target == ops.TARGET_MANUSCRIPT:
            self._build_manuscript(layout)
        elif self._target == ops.TARGET_OUTLINE:
            self._build_outline(layout)
        elif self._target == ops.TARGET_PSYKE:
            self._build_psyke(layout)
        else:
            layout.addWidget(QLabel("Nothing to apply."))

        layout.addLayout(self._build_buttons())

    # -- Manuscript ----------------------------------------------------------

    def _build_manuscript(self, layout: QVBoxLayout) -> None:
        before = (getattr(self._context, "selected_text", "") or "").strip()
        layout.addWidget(self._small_label("Before (current selection):"))
        before_box = QPlainTextEdit()
        before_box.setReadOnly(True)
        before_box.setPlainText(before)
        before_box.setMaximumHeight(120)
        layout.addWidget(before_box)

        layout.addWidget(self._small_label("Generated (editable):"))
        self._generated = QPlainTextEdit()
        self._generated.setPlainText(self._result.message or "")
        layout.addWidget(self._generated, stretch=1)

    # -- Outline -------------------------------------------------------------

    def _build_outline(self, layout: QVBoxLayout) -> None:
        create_op = self._find_op(ops.OP_CREATE_OUTLINE_NODE)
        update_op = self._find_op(ops.OP_UPDATE_OUTLINE_SUMMARY)
        self._scene_id = (update_op or {}).get("payload", {}).get("scene_id")
        self._act = (create_op or {}).get("payload", {}).get("act", "")
        self._chapter = (create_op or {}).get("payload", {}).get("chapter", "")

        node_label = getattr(self._context, "outline_node_label", "")
        if node_label:
            layout.addWidget(self._small_label(f"Outline node: {node_label}"))

        layout.addWidget(self._small_label("Title:"))
        self._title_field = QLineEdit()
        self._title_field.setText(
            (create_op or {}).get("payload", {}).get("title", "") or node_label
        )
        layout.addWidget(self._title_field)

        layout.addWidget(self._small_label("Summary / body (editable):"))
        self._summary_field = QPlainTextEdit()
        self._summary_field.setPlainText(self._result.message or "")
        layout.addWidget(self._summary_field, stretch=1)

    # -- PSYKE ---------------------------------------------------------------

    def _build_psyke(self, layout: QVBoxLayout) -> None:
        prog_op = self._find_op(ops.OP_CREATE_PSYKE_PROGRESSION)
        notes_op = self._find_op(ops.OP_APPEND_PSYKE_NOTES)
        self._psyke_op = prog_op or notes_op
        payload = (self._psyke_op or {}).get("payload", {})
        self._psyke_entry_id = payload.get("entry_id")
        self._psyke_scene_id = payload.get("scene_id")

        kind = "progression" if prog_op else "note"
        layout.addWidget(self._small_label(
            f"This will be added as a PSYKE {kind} (editable):"
        ))
        self._psyke_text = QPlainTextEdit()
        self._psyke_text.setPlainText(self._result.message or "")
        layout.addWidget(self._psyke_text, stretch=1)

    # -- Buttons -------------------------------------------------------------

    def _build_buttons(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.addStretch()

        copy_btn = QPushButton("Copy")
        copy_btn.clicked.connect(self._copy)
        row.addWidget(copy_btn)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        row.addWidget(cancel_btn)

        if self._target == ops.TARGET_MANUSCRIPT:
            insert_btn = QPushButton("Insert After")
            insert_btn.clicked.connect(self._confirm_insert)
            row.addWidget(insert_btn)
            replace_btn = QPushButton("Apply Replace")
            replace_btn.setDefault(True)
            replace_btn.clicked.connect(self._confirm_replace)
            row.addWidget(replace_btn)
        elif self._target == ops.TARGET_OUTLINE:
            if self._scene_id is not None:
                upd_title = QPushButton("Update Title")
                upd_title.clicked.connect(self._confirm_update_title)
                row.addWidget(upd_title)
                upd_sum = QPushButton("Update Summary")
                upd_sum.clicked.connect(self._confirm_update_summary)
                row.addWidget(upd_sum)
            create_btn = QPushButton("Create Node")
            create_btn.setDefault(True)
            create_btn.clicked.connect(self._confirm_create)
            row.addWidget(create_btn)
        elif self._target == ops.TARGET_PSYKE:
            op_name = (self._psyke_op or {}).get("operation")
            if op_name == ops.OP_CREATE_PSYKE_PROGRESSION:
                btn = QPushButton("Add Progression")
                btn.clicked.connect(self._confirm_psyke_progression)
            else:
                btn = QPushButton("Append to Notes")
                btn.clicked.connect(self._confirm_psyke_notes)
            btn.setDefault(True)
            row.addWidget(btn)
        return row

    # -- Confirm handlers (build finalized op, validate, accept) -------------

    def _confirm_replace(self) -> None:
        self._finish({
            "operation": ops.OP_REPLACE_SELECTION, "target": ops.TARGET_MANUSCRIPT,
            "payload": {"replacement_text": self._generated.toPlainText()},
        })

    def _confirm_insert(self) -> None:
        self._finish({
            "operation": ops.OP_INSERT_AFTER, "target": ops.TARGET_MANUSCRIPT,
            "payload": {"text": self._generated.toPlainText()},
        })

    def _confirm_create(self) -> None:
        self._finish({
            "operation": ops.OP_CREATE_OUTLINE_NODE, "target": ops.TARGET_OUTLINE,
            "payload": {
                "act": self._act, "chapter": self._chapter,
                "title": self._title_field.text(),
                "summary": self._summary_field.toPlainText(), "beat": "",
            },
        })

    def _confirm_update_summary(self) -> None:
        self._finish({
            "operation": ops.OP_UPDATE_OUTLINE_SUMMARY, "target": ops.TARGET_OUTLINE,
            "payload": {"scene_id": self._scene_id,
                        "summary": self._summary_field.toPlainText()},
        })

    def _confirm_update_title(self) -> None:
        self._finish({
            "operation": ops.OP_UPDATE_OUTLINE_TITLE, "target": ops.TARGET_OUTLINE,
            "payload": {"scene_id": self._scene_id, "title": self._title_field.text()},
        })

    def _confirm_psyke_notes(self) -> None:
        self._finish({
            "operation": ops.OP_APPEND_PSYKE_NOTES, "target": ops.TARGET_PSYKE,
            "payload": {"entry_id": self._psyke_entry_id,
                        "note": self._psyke_text.toPlainText()},
        })

    def _confirm_psyke_progression(self) -> None:
        self._finish({
            "operation": ops.OP_CREATE_PSYKE_PROGRESSION, "target": ops.TARGET_PSYKE,
            "payload": {"entry_id": self._psyke_entry_id,
                        "text": self._psyke_text.toPlainText(),
                        "scene_id": self._psyke_scene_id},
        })

    def _finish(self, op: dict) -> None:
        err = ops.validate_operation(op)
        if err:
            self._heading_error(err)
            return
        self._operation = op
        self.accept()

    # -- Misc ----------------------------------------------------------------

    def _copy(self) -> None:
        text = self._result.message or ""
        if text:
            QApplication.clipboard().setText(text)

    def _heading_error(self, msg: str) -> None:
        # Show validation problems inline rather than silently doing nothing.
        self.setWindowTitle(f"Logos — {msg}")

    @staticmethod
    def _small_label(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet("font-size: 11px; color: #888;")
        return lbl

    def _find_op(self, name: str) -> dict | None:
        for op in self._result.proposed_operations:
            if op.get("operation") == name:
                return op
        return None

    # -- Public --------------------------------------------------------------

    def operation(self) -> dict | None:
        return self._operation

    @staticmethod
    def get_operation(result, context, parent=None) -> dict | None:
        """Show modally; return the finalized op, or None if cancelled."""
        dlg = LogosApplyPreview(result, context, parent)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            return dlg.operation()
        return None
