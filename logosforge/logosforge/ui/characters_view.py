"""Characters management view — list, create, edit, delete."""

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from logosforge.db import Database
from logosforge.ui.link_preview import BacklinksWidget

USER_ROLE = Qt.ItemDataRole.UserRole


class CharactersView(QWidget):
    def __init__(
        self,
        db: Database,
        project_id: int,
        on_data_changed: Callable[[], None] | None = None,
        on_link_clicked: Callable[[str, int], None] | None = None,
    ) -> None:
        super().__init__()
        self._db = db
        self._project_id = project_id
        self._on_data_changed = on_data_changed
        self._on_link_clicked = on_link_clicked
        self._selected_id: int | None = None

        root = QHBoxLayout(self)

        # -- Left: character list --------------------------------------------
        left = QVBoxLayout()
        left.addWidget(QLabel("Characters"))
        self._list = QListWidget()
        self._list.currentItemChanged.connect(self._on_selected)
        left.addWidget(self._list)
        root.addLayout(left)

        # -- Right: form -----------------------------------------------------
        right = QVBoxLayout()

        self._form_label = QLabel("New Character")
        right.addWidget(self._form_label)

        right.addWidget(QLabel("Name"))
        self._name_input = QLineEdit()
        right.addWidget(self._name_input)

        right.addWidget(QLabel("Description"))
        self._desc_input = QPlainTextEdit()
        right.addWidget(self._desc_input)

        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self._on_save)
        right.addWidget(save_btn)

        self._delete_btn = QPushButton("Delete")
        self._delete_btn.setEnabled(False)
        self._delete_btn.clicked.connect(self._on_delete)
        right.addWidget(self._delete_btn)

        new_btn = QPushButton("New Character")
        new_btn.clicked.connect(self._clear_form)
        right.addWidget(new_btn)

        self._backlinks = BacklinksWidget(
            db, project_id, on_backlink_clicked=on_link_clicked,
        )
        right.addWidget(self._backlinks)

        right.addStretch()
        root.addLayout(right)

        self._refresh_list()

    def refresh(self) -> None:
        self._refresh_list()

    def _refresh_list(self) -> None:
        self._list.blockSignals(True)
        self._list.clear()
        for char in self._db.get_all_characters(self._project_id):
            item = QListWidgetItem(char.name)
            item.setData(USER_ROLE, char.id)
            self._list.addItem(item)
        self._list.blockSignals(False)

    def _on_selected(self, current: QListWidgetItem | None) -> None:
        if current is None:
            return
        char = self._db.get_character_by_id(current.data(USER_ROLE))
        if char is None:
            return
        self._selected_id = char.id
        self._form_label.setText("Edit Character")
        self._delete_btn.setEnabled(True)
        self._name_input.setText(char.name)
        self._desc_input.setPlainText(char.description)
        self._backlinks.load(char.name)

    def _on_save(self) -> None:
        name = self._name_input.text().strip()
        if not name:
            return
        desc = self._desc_input.toPlainText().strip()

        if self._selected_id is not None:
            self._db.update_character(self._selected_id, name, desc)
        else:
            self._db.create_character(self._project_id, name, desc)

        self._clear_form()
        self._refresh_list()
        if self._on_data_changed:
            self._on_data_changed()

    def _on_delete(self) -> None:
        if self._selected_id is None:
            return
        self._db.delete_character(self._selected_id)
        self._clear_form()
        self._refresh_list()
        if self._on_data_changed:
            self._on_data_changed()

    def select_character(self, character_id: int) -> None:
        for i in range(self._list.count()):
            if self._list.item(i).data(USER_ROLE) == character_id:
                self._list.setCurrentRow(i)
                return

    def _clear_form(self) -> None:
        self._selected_id = None
        self._form_label.setText("New Character")
        self._delete_btn.setEnabled(False)
        self._name_input.clear()
        self._desc_input.clear()
        self._backlinks.clear_backlinks()
        self._list.clearSelection()
