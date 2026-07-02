"""New Project dialog — collects title, narrative engine, writing format."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
)

from logosforge.project_compat import (
    ALL_ENGINES,
    ALL_FORMATS,
    ENGINE_LABELS,
    ENGINE_NOVEL,
    FORMAT_LABELS,
    default_format_for_engine,
)


class NewProjectDialog(QDialog):
    """Dialog for creating a new project with engine + format upfront."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._format_manually_changed = False
        self.setWindowTitle("New Project")
        self.setMinimumWidth(420)
        # Window-modal (a sheet on macOS) so creating a project never forces the
        # main window out of fullscreen / onto another Space.
        self.setWindowModality(Qt.WindowModality.WindowModal)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(10)

        header = QLabel("Create a new project")
        header.setStyleSheet("font-size: 14px; font-weight: bold;")
        layout.addWidget(header)

        hint = QLabel(
            "Pick the narrative engine and default writing format for"
            " this project. You can change them later in Project Settings."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #94a3b8; font-size: 11px;")
        layout.addWidget(hint)

        # -- Title -----------------------------------------------------------
        title_row = QHBoxLayout()
        title_row.addWidget(QLabel("Title:"))
        self._title_edit = QLineEdit()
        self._title_edit.setPlaceholderText("Untitled")
        title_row.addWidget(self._title_edit, stretch=1)
        layout.addLayout(title_row)

        # -- Narrative engine ------------------------------------------------
        engine_row = QHBoxLayout()
        engine_row.addWidget(QLabel("Narrative Engine:"))
        self._engine_combo = QComboBox()
        for key in ALL_ENGINES:
            self._engine_combo.addItem(ENGINE_LABELS[key], key)
        idx = self._engine_combo.findData(ENGINE_NOVEL)
        self._engine_combo.setCurrentIndex(max(idx, 0))
        self._engine_combo.currentIndexChanged.connect(self._on_engine_changed)
        engine_row.addWidget(self._engine_combo, stretch=1)
        layout.addLayout(engine_row)

        # -- Default writing format ------------------------------------------
        format_row = QHBoxLayout()
        format_row.addWidget(QLabel("Default Writing Format:"))
        self._format_combo = QComboBox()
        for key in ALL_FORMATS:
            self._format_combo.addItem(FORMAT_LABELS[key], key)
        suggested = default_format_for_engine(ENGINE_NOVEL)
        idx = self._format_combo.findData(suggested)
        self._format_combo.setCurrentIndex(max(idx, 0))
        self._format_combo.currentIndexChanged.connect(self._on_format_user_changed)
        format_row.addWidget(self._format_combo, stretch=1)
        layout.addLayout(format_row)

        # -- Writing Language --------------------------------------------------
        from logosforge import languages as L
        from logosforge.i18n import tr
        lang_row = QHBoxLayout()
        lang_row.addWidget(QLabel(tr("Writing Language:")))
        self._language_combo = QComboBox()
        self._language_combo.setObjectName("newProjectWritingLanguage")
        for code, label in L.selector_choices():
            self._language_combo.addItem(label, code)
        idx = self._language_combo.findData(L.default_writing_language())
        self._language_combo.setCurrentIndex(max(idx, 0))
        lang_row.addWidget(self._language_combo, stretch=1)
        layout.addLayout(lang_row)

        # -- Buttons ---------------------------------------------------------
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_engine_changed(self, _index: int) -> None:
        if self._format_manually_changed:
            return
        engine = self._engine_combo.currentData()
        suggested = default_format_for_engine(engine)
        idx = self._format_combo.findData(suggested)
        if idx >= 0:
            self._format_combo.blockSignals(True)
            self._format_combo.setCurrentIndex(idx)
            self._format_combo.blockSignals(False)

    def _on_format_user_changed(self, _index: int) -> None:
        self._format_manually_changed = True

    def get_title(self) -> str:
        return (self._title_edit.text() or "").strip() or "Untitled"

    def get_engine(self) -> str:
        return self._engine_combo.currentData()

    def get_format(self) -> str:
        return self._format_combo.currentData()

    def get_writing_language(self) -> str:
        return self._language_combo.currentData() or "en"
