"""Fountain import preview + confirm dialog (Phase 4).

Self-contained and non-mutating: it shows the parsed import (scene count, scene
titles, title page, warnings), lets the author pick an import mode, and returns
the chosen mode only on confirm. The caller performs the actual, confirmed
``apply_fountain_import`` — this dialog never touches the database.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)

from logosforge import screenplay_interchange as si

# (mode, label, needs a selected target scene)
_MODE_CHOICES: tuple[tuple[str, str, bool], ...] = (
    (si.IMPORT_INTO_PROJECT, "Add to this project (new Act/Chapter of scenes)", False),
    (si.IMPORT_NEW_PROJECT, "Import as a new project", False),
    (si.IMPORT_INTO_SCENE, "Append to the selected scene", True),
    (si.IMPORT_REPLACE_SCENE, "Replace the selected scene's body", True),
)


class FountainImportDialog(QDialog):
    def __init__(self, preview, *, has_target_scene: bool = False, parent=None) -> None:
        super().__init__(parent)
        self._preview = preview
        self._mode: str | None = None
        self.setWindowTitle("Import Fountain — Preview")
        self.resize(560, 560)
        self.setMinimumSize(420, 380)
        self.setSizeGripEnabled(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)

        heading = QLabel("Import Fountain")
        heading.setStyleSheet("font-weight: bold;")
        layout.addWidget(heading)

        title = (preview.title_page or {}).get("title", "")
        summary = (f"{preview.scene_count} scene(s), {preview.block_count} block(s)"
                   + (f" · Title: {title}" if title else ""))
        layout.addWidget(QLabel(summary))

        scenes = QListWidget()
        scenes.setObjectName("fountainImportSceneList")
        for i, scene in enumerate(preview.scenes, start=1):
            scenes.addItem(f"{i}. {scene.title}  ·  {len(scene.blocks)} blocks")
        layout.addWidget(scenes, stretch=1)

        if preview.warnings:
            warn = QPlainTextEdit()
            warn.setObjectName("fountainImportWarnings")
            warn.setReadOnly(True)
            warn.setMaximumHeight(110)
            warn.setPlainText("Warnings:\n• " + "\n• ".join(preview.warnings))
            layout.addWidget(warn)

        layout.addWidget(self._small("Import mode:"))
        self._mode_combo = QComboBox()
        self._mode_combo.setObjectName("fountainImportMode")
        for mode, label, needs_scene in _MODE_CHOICES:
            if needs_scene and not has_target_scene:
                continue
            self._mode_combo.addItem(label, mode)
        layout.addWidget(self._mode_combo)

        row = QHBoxLayout()
        row.addStretch()
        cancel = QPushButton("Cancel")
        cancel.setObjectName("fountainImportCancel")
        cancel.clicked.connect(self.reject)
        row.addWidget(cancel)
        do_import = QPushButton("Import")
        do_import.setObjectName("fountainImportConfirm")
        do_import.setDefault(True)
        do_import.setEnabled(preview.scene_count > 0)
        do_import.clicked.connect(self._on_import)
        row.addWidget(do_import)
        layout.addLayout(row)

    def _on_import(self) -> None:
        self._mode = self._mode_combo.currentData()
        self.accept()

    def chosen_mode(self) -> str | None:
        return self._mode

    @staticmethod
    def _small(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet("font-size: 11px; color: #888;")
        return lbl

    @staticmethod
    def get_mode(preview, *, has_target_scene: bool = False, parent=None) -> str | None:
        """Show modally; return the chosen import mode, or None if cancelled."""
        dlg = FountainImportDialog(preview, has_target_scene=has_target_scene,
                                   parent=parent)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            return dlg.chosen_mode()
        return None
