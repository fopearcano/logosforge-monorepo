"""Quick-create PSYKE entry dialog — launched from scene editor context menu."""

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)

ENTRY_TYPES = ["character", "place", "object", "lore", "theme", "other"]


class PsykeQuickCreateDialog(QDialog):
    def __init__(
        self,
        parent=None,
        initial_name: str = "",
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Create PSYKE Entry")
        self.setMinimumWidth(380)

        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("Name"))
        self._name_input = QLineEdit()
        self._name_input.setText(initial_name)
        layout.addWidget(self._name_input)

        layout.addWidget(QLabel("Type"))
        self._type_combo = QComboBox()
        for t in ENTRY_TYPES:
            self._type_combo.addItem(t.capitalize(), t)
        layout.addWidget(self._type_combo)

        layout.addWidget(QLabel("Aliases (comma-separated)"))
        self._aliases_input = QLineEdit()
        layout.addWidget(self._aliases_input)

        layout.addWidget(QLabel("Notes"))
        self._notes_input = QPlainTextEdit()
        self._notes_input.setMaximumHeight(100)
        layout.addWidget(self._notes_input)

        self._global_check = QCheckBox("Global (visible across projects)")
        layout.addWidget(self._global_check)

        btn_row = QHBoxLayout()
        create_btn = QPushButton("Create")
        create_btn.clicked.connect(self.accept)
        btn_row.addWidget(create_btn)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

    def get_values(self) -> dict:
        return {
            "name": self._name_input.text().strip(),
            "entry_type": self._type_combo.currentData() or "other",
            "aliases": self._aliases_input.text().strip(),
            "notes": self._notes_input.toPlainText().strip(),
            "is_global": self._global_check.isChecked(),
        }
