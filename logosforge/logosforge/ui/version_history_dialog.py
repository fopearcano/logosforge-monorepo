"""Version History dialog — browse, restore, and delete project snapshots."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from logosforge.ui import theme
from logosforge.version_manager import VersionManager


class VersionHistoryDialog(QDialog):
    """Lists project snapshots and allows restore or delete."""

    def __init__(
        self,
        version_manager: VersionManager,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._vm = version_manager
        self.restored_project_id: int | None = None

        self.setWindowTitle("Version History")
        self.setMinimumSize(560, 360)

        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        header = QLabel("Project Snapshots")
        header.setStyleSheet(
            f"font-size: 14px; font-weight: bold; color: {theme.TEXT_PRIMARY};"
        )
        layout.addWidget(header)

        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(
            ["Timestamp", "Reason", "Label", "Size (KB)"]
        )
        self._table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self._table.setSelectionMode(
            QTableWidget.SelectionMode.SingleSelection
        )
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        h = self._table.horizontalHeader()
        h.setStretchLastSection(True)
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self._table, stretch=1)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        btn_row.addStretch()

        self._restore_btn = QPushButton("Restore Selected")
        self._restore_btn.clicked.connect(self._on_restore)
        btn_row.addWidget(self._restore_btn)

        self._delete_btn = QPushButton("Delete Selected")
        self._delete_btn.clicked.connect(self._on_delete)
        btn_row.addWidget(self._delete_btn)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.reject)
        btn_row.addWidget(close_btn)

        layout.addLayout(btn_row)

        self._refresh()

    def _refresh(self) -> None:
        self._versions = self._vm.list_versions()
        self._table.setRowCount(len(self._versions))
        for row, v in enumerate(self._versions):
            self._table.setItem(row, 0, QTableWidgetItem(v.display_time))
            self._table.setItem(row, 1, QTableWidgetItem(v.reason))
            self._table.setItem(row, 2, QTableWidgetItem(v.label))
            self._table.setItem(
                row, 3, QTableWidgetItem(f"{v.file_size_kb:.1f}")
            )

    def _selected_index(self) -> int | None:
        rows = self._table.selectionModel().selectedRows()
        if not rows:
            return None
        return rows[0].row()

    def _on_restore(self) -> None:
        idx = self._selected_index()
        if idx is None:
            return
        v = self._versions[idx]
        confirm = QMessageBox.question(
            self,
            "Restore Version",
            f"Restore snapshot from {v.display_time}?\n\n"
            "A safety snapshot will be created first.\n"
            "The restored data will be loaded as a new project.",
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        new_id = self._vm.restore_version(v.path)
        if new_id is None:
            QMessageBox.warning(
                self, "Restore Failed",
                "Could not restore the selected version.",
            )
            return
        self.restored_project_id = new_id
        self.accept()

    def _on_delete(self) -> None:
        idx = self._selected_index()
        if idx is None:
            return
        v = self._versions[idx]
        confirm = QMessageBox.question(
            self,
            "Delete Version",
            f"Delete snapshot from {v.display_time}?\n"
            "This cannot be undone.",
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        self._vm.delete_version(v.path)
        self._refresh()
