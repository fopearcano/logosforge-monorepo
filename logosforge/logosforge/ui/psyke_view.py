"""PSYKE Story Bible view — list with search/filter, entry editor, relations, progressions, and scene references."""

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from logosforge.context_builder import find_psyke_scene_references
from logosforge.db import Database
from logosforge.models.psyke_details import (
    FieldSpec,
    get_detail_schema,
    get_visual_schema,
)

USER_ROLE = Qt.ItemDataRole.UserRole

ENTRY_TYPES = ["character", "place", "object", "lore", "theme", "other"]

# Optional typed relations (the empty type = a generic association). These match
# the inverse-mapping in the DB so the reverse edge stays semantically correct.
_RELATION_TYPE_CHOICES = [
    ("Associated", ""),
    ("Sets up →", "supports_setup"),
    ("Pays off →", "payoff"),
    ("Thematic echo", "thematic_echo"),
    ("Visual motif", "visual_motif"),
    ("Subtext opposition", "subtext_opposition"),
    ("Dominates", "dominates"),
    ("Submits to", "submits"),
]
_RELATION_TYPE_LABELS = {t: lbl for lbl, t in _RELATION_TYPE_CHOICES if t}


class PsykeView(QWidget):
    def __init__(
        self,
        db: Database,
        project_id: int,
        on_data_changed: Callable[[], None] | None = None,
        on_open_scene: Callable[[int], None] | None = None,
    ) -> None:
        super().__init__()
        self._db = db
        self._project_id = project_id
        self._on_data_changed = on_data_changed
        self._on_open_scene = on_open_scene
        self._selected_id: int | None = None

        # Graphic Novel projects also edit PSYKE visual memory (a "Visual
        # Memory" group stored under details_json["visual"]).
        try:
            from logosforge.project_compat import get_project_narrative_engine
            project = db.get_project_by_id(project_id)
            self._gn_mode = get_project_narrative_engine(project) == "graphic_novel"
        except Exception:
            self._gn_mode = False
        self._visual_widgets: dict[str, object] = {}

        root = QHBoxLayout(self)

        # -- Left panel: search + filter + list ------------------------------
        left = QVBoxLayout()
        left.addWidget(QLabel("PSYKE"))

        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("Search entries...")
        self._search_input.textChanged.connect(self._apply_filter)
        left.addWidget(self._search_input)

        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("Type:"))
        self._type_filter = QComboBox()
        self._type_filter.addItem("All", "")
        for t in ENTRY_TYPES:
            self._type_filter.addItem(t.capitalize(), t)
        self._type_filter.currentIndexChanged.connect(self._apply_filter)
        filter_row.addWidget(self._type_filter)
        left.addLayout(filter_row)

        self._list = QListWidget()
        self._list.currentItemChanged.connect(self._on_selected)
        left.addWidget(self._list)

        root.addLayout(left)

        # -- Right panel: editor (scrollable) --------------------------------
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)

        right_widget = QWidget()
        right = QVBoxLayout(right_widget)

        self._form_label = QLabel("New Entry")
        right.addWidget(self._form_label)

        right.addWidget(QLabel("Name"))
        self._name_input = QLineEdit()
        right.addWidget(self._name_input)

        right.addWidget(QLabel("Type"))
        self._type_combo = QComboBox()
        for t in ENTRY_TYPES:
            self._type_combo.addItem(t.capitalize(), t)
        right.addWidget(self._type_combo)

        right.addWidget(QLabel("Aliases (comma-separated)"))
        self._aliases_input = QLineEdit()
        right.addWidget(self._aliases_input)

        right.addWidget(QLabel("Notes"))
        self._notes_input = QPlainTextEdit()
        self._notes_input.setMaximumHeight(120)
        right.addWidget(self._notes_input)

        self._global_check = QCheckBox("Global (visible across projects)")
        right.addWidget(self._global_check)

        btn_row = QHBoxLayout()
        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self._on_save)
        btn_row.addWidget(save_btn)

        self._delete_btn = QPushButton("Delete")
        self._delete_btn.setEnabled(False)
        self._delete_btn.clicked.connect(self._on_delete)
        btn_row.addWidget(self._delete_btn)

        new_btn = QPushButton("New Entry")
        new_btn.clicked.connect(self._clear_form)
        btn_row.addWidget(new_btn)
        right.addLayout(btn_row)

        # -- Details section (dynamic per entry type) -----------------------
        self._details_section = QWidget()
        self._details_layout = QVBoxLayout(self._details_section)
        self._details_layout.setContentsMargins(0, 8, 0, 0)
        self._details_label = QLabel("Details")
        self._details_layout.addWidget(self._details_label)
        self._detail_widgets: dict[str, QLineEdit | QPlainTextEdit | QComboBox] = {}
        self._details_section.setVisible(False)
        right.addWidget(self._details_section)

        self._type_combo.currentIndexChanged.connect(self._on_type_changed)

        # -- Related Entries section -----------------------------------------
        self._related_section = QWidget()
        rel_layout = QVBoxLayout(self._related_section)
        rel_layout.setContentsMargins(0, 8, 0, 0)
        rel_layout.addWidget(QLabel("Related Entries"))

        add_rel_row = QHBoxLayout()
        self._related_combo = QComboBox()
        add_rel_row.addWidget(self._related_combo, stretch=1)
        self._relation_type_combo = QComboBox()
        for _lbl, _rtype in _RELATION_TYPE_CHOICES:
            self._relation_type_combo.addItem(_lbl, _rtype)
        self._relation_type_combo.setToolTip(
            "Optional relation kind (used by the Assistant and craft tools)."
        )
        add_rel_row.addWidget(self._relation_type_combo)
        add_rel_btn = QPushButton("Add")
        add_rel_btn.clicked.connect(self._on_add_relation)
        add_rel_row.addWidget(add_rel_btn)
        rel_layout.addLayout(add_rel_row)

        self._related_list = QListWidget()
        self._related_list.setMaximumHeight(100)
        self._related_list.itemDoubleClicked.connect(self._on_related_clicked)
        rel_layout.addWidget(self._related_list)

        remove_rel_btn = QPushButton("Remove Selected")
        remove_rel_btn.clicked.connect(self._on_remove_relation)
        rel_layout.addWidget(remove_rel_btn)

        self._related_section.setVisible(False)
        right.addWidget(self._related_section)

        # -- Progressions section --------------------------------------------
        self._prog_section = QWidget()
        prog_layout = QVBoxLayout(self._prog_section)
        prog_layout.setContentsMargins(0, 8, 0, 0)
        prog_layout.addWidget(QLabel("Progressions"))

        add_prog_row = QHBoxLayout()
        self._prog_text_input = QLineEdit()
        self._prog_text_input.setPlaceholderText("Progression note...")
        add_prog_row.addWidget(self._prog_text_input, stretch=1)
        prog_layout.addLayout(add_prog_row)

        scene_row = QHBoxLayout()
        scene_row.addWidget(QLabel("Scene:"))
        self._prog_scene_combo = QComboBox()
        scene_row.addWidget(self._prog_scene_combo, stretch=1)
        add_prog_btn = QPushButton("Add")
        add_prog_btn.clicked.connect(self._on_add_progression)
        scene_row.addWidget(add_prog_btn)
        prog_layout.addLayout(scene_row)

        self._prog_list = QListWidget()
        self._prog_list.setMaximumHeight(140)
        self._prog_list.currentItemChanged.connect(self._on_prog_selected)
        prog_layout.addWidget(self._prog_list)

        prog_btn_row = QHBoxLayout()
        self._prog_update_btn = QPushButton("Update")
        self._prog_update_btn.setEnabled(False)
        self._prog_update_btn.clicked.connect(self._on_update_progression)
        prog_btn_row.addWidget(self._prog_update_btn)
        self._prog_delete_btn = QPushButton("Delete")
        self._prog_delete_btn.setEnabled(False)
        self._prog_delete_btn.clicked.connect(self._on_delete_progression)
        prog_btn_row.addWidget(self._prog_delete_btn)
        prog_layout.addLayout(prog_btn_row)

        self._prog_section.setVisible(False)
        right.addWidget(self._prog_section)

        # -- Scene References section ----------------------------------------
        self._refs_section = QWidget()
        refs_layout = QVBoxLayout(self._refs_section)
        refs_layout.setContentsMargins(0, 8, 0, 0)
        refs_layout.addWidget(QLabel("Scene References"))

        self._refs_list = QListWidget()
        self._refs_list.setMaximumHeight(100)
        self._refs_list.itemDoubleClicked.connect(self._on_ref_clicked)
        refs_layout.addWidget(self._refs_list)

        self._refs_section.setVisible(False)
        right.addWidget(self._refs_section)

        right.addStretch()
        scroll.setWidget(right_widget)
        root.addWidget(scroll)

        self._refresh_list()

    # -- List management -----------------------------------------------------

    def refresh(self) -> None:
        self._refresh_list()

    def _refresh_list(self) -> None:
        self._all_entries = self._db.get_all_psyke_entries(self._project_id)
        self._apply_filter()

    def _apply_filter(self) -> None:
        query = self._search_input.text().strip().lower()
        type_filter = self._type_filter.currentData()

        self._list.blockSignals(True)
        self._list.clear()
        for entry in self._all_entries:
            if type_filter and entry.entry_type != type_filter:
                continue
            if query:
                searchable = f"{entry.name} {entry.aliases} {entry.notes}".lower()
                if query not in searchable:
                    continue
            label = f"[{entry.entry_type[0].upper()}] {entry.name}"
            item = QListWidgetItem(label)
            item.setData(USER_ROLE, entry.id)
            self._list.addItem(item)
        self._list.blockSignals(False)

    # -- Entry selection / form ----------------------------------------------

    def _on_selected(self, current: QListWidgetItem | None) -> None:
        if current is None:
            return
        entry = self._db.get_psyke_entry_by_id(current.data(USER_ROLE))
        if entry is None:
            return
        self._selected_id = entry.id
        self._form_label.setText("Edit Entry")
        self._delete_btn.setEnabled(True)
        self._name_input.setText(entry.name)
        self._type_combo.blockSignals(True)
        idx = self._type_combo.findData(entry.entry_type)
        if idx >= 0:
            self._type_combo.setCurrentIndex(idx)
        self._type_combo.blockSignals(False)
        self._aliases_input.setText(entry.aliases)
        self._notes_input.setPlainText(entry.notes)
        self._global_check.setChecked(entry.is_global)

        self._rebuild_detail_fields(entry.entry_type)
        details = self._db.get_psyke_entry_details(entry.id)
        self._load_details(details)
        if self._gn_mode:
            self._load_visual(self._db.get_psyke_visual_memory(entry.id))

        self._related_section.setVisible(True)
        self._prog_section.setVisible(True)
        self._refs_section.setVisible(True)
        self._refresh_related()
        self._refresh_progressions()
        self._refresh_references()

    def _on_save(self) -> None:
        name = self._name_input.text().strip()
        if not name:
            QMessageBox.warning(
                self, "Name required",
                "Enter a name before saving this Story Bible entry.",
            )
            self._name_input.setFocus()
            return
        # Warn (don't block) on a duplicate name so the bible stays unambiguous.
        dupe = any(
            e.name.strip().lower() == name.lower() and e.id != self._selected_id
            for e in self._all_entries
        )
        if dupe and QMessageBox.question(
            self, "Duplicate name",
            f"Another entry is already named “{name}”. Create it anyway?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return
        entry_type = self._type_combo.currentData() or "other"
        aliases = self._aliases_input.text().strip()
        notes = self._notes_input.toPlainText().strip()
        is_global = self._global_check.isChecked()

        details = self._collect_details()

        if self._selected_id is not None:
            self._db.update_psyke_entry(
                self._selected_id, name, entry_type, aliases, notes, is_global,
                details=details,
            )
        else:
            entry = self._db.create_psyke_entry(
                self._project_id, name, entry_type, aliases, notes, is_global,
                details=details,
            )
            self._selected_id = entry.id
            self._form_label.setText("Edit Entry")
            self._delete_btn.setEnabled(True)
            self._related_section.setVisible(True)
            self._prog_section.setVisible(True)
            self._refresh_related()
            self._refresh_progressions()

        # Visual memory persists nested under details_json["visual"].
        if self._gn_mode and self._selected_id is not None:
            self._db.set_psyke_visual_memory(
                self._selected_id, self._collect_visual(),
            )

        self._refresh_list()
        self._reselect_current()
        if self._on_data_changed:
            self._on_data_changed()

    def _on_delete(self) -> None:
        if self._selected_id is None:
            return
        name = self._name_input.text().strip() or "this entry"
        if QMessageBox.question(
            self, "Delete entry",
            f"Delete “{name}”? Its relations and progressions are removed too. "
            "This can't be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return
        self._db.delete_psyke_entry(self._selected_id)
        self._clear_form()
        self._refresh_list()
        if self._on_data_changed:
            self._on_data_changed()

    def select_entry(self, entry_id: int) -> None:
        for i in range(self._list.count()):
            if self._list.item(i).data(USER_ROLE) == entry_id:
                self._list.setCurrentRow(i)
                return

    def _reselect_current(self) -> None:
        if self._selected_id is not None:
            self.select_entry(self._selected_id)

    def _clear_form(self) -> None:
        self._selected_id = None
        self._form_label.setText("New Entry")
        self._delete_btn.setEnabled(False)
        self._name_input.clear()
        self._type_combo.setCurrentIndex(0)
        self._aliases_input.clear()
        self._notes_input.clear()
        self._global_check.setChecked(False)
        self._list.clearSelection()
        self._details_section.setVisible(False)
        self._related_section.setVisible(False)
        self._prog_section.setVisible(False)
        self._refs_section.setVisible(False)

    # -- Related Entries -----------------------------------------------------

    def _refresh_related(self) -> None:
        if self._selected_id is None:
            return

        self._related_combo.clear()
        self._related_combo.addItem("Select entry...", None)
        related_ids = {
            e.id for e in self._db.get_related_psyke_entries(self._selected_id)
        }
        for entry in self._all_entries:
            if entry.id == self._selected_id or entry.id in related_ids:
                continue
            self._related_combo.addItem(
                f"[{entry.entry_type[0].upper()}] {entry.name}", entry.id
            )

        self._related_list.clear()
        for entry, rtype in self._db.get_typed_related_psyke_entries(
            self._selected_id
        ):
            label = f"[{entry.entry_type[0].upper()}] {entry.name}"
            if rtype:
                label += f"  · {_RELATION_TYPE_LABELS.get(rtype, rtype)}"
            item = QListWidgetItem(label)
            item.setData(USER_ROLE, entry.id)
            self._related_list.addItem(item)

    def _on_add_relation(self) -> None:
        if self._selected_id is None:
            return
        related_id = self._related_combo.currentData()
        if related_id is None:
            return
        rtype = self._relation_type_combo.currentData() or ""
        self._db.add_psyke_relation(self._selected_id, related_id, rtype)
        self._relation_type_combo.setCurrentIndex(0)
        self._refresh_related()
        if self._on_data_changed:
            self._on_data_changed()

    def _on_remove_relation(self) -> None:
        if self._selected_id is None:
            return
        current = self._related_list.currentItem()
        if current is None:
            return
        related_id = current.data(USER_ROLE)
        self._db.remove_psyke_relation(self._selected_id, related_id)
        self._refresh_related()
        if self._on_data_changed:
            self._on_data_changed()

    def _on_related_clicked(self, item: QListWidgetItem) -> None:
        entry_id = item.data(USER_ROLE)
        self.select_entry(entry_id)

    # -- Progressions --------------------------------------------------------

    def _refresh_progressions(self) -> None:
        if self._selected_id is None:
            return

        self._prog_scene_combo.clear()
        self._prog_scene_combo.addItem("None", None)
        for scene in self._db.get_all_scenes(self._project_id):
            self._prog_scene_combo.addItem(scene.title, scene.id)

        self._prog_list.clear()
        for prog in self._db.get_psyke_progressions(self._selected_id):
            label = prog.text
            if prog.scene_id:
                scene = self._db.get_scene_by_id(prog.scene_id)
                if scene:
                    label += f"  [{scene.title}]"
            item = QListWidgetItem(label)
            item.setData(USER_ROLE, prog.id)
            self._prog_list.addItem(item)

        self._prog_text_input.clear()
        self._prog_scene_combo.setCurrentIndex(0)
        self._prog_update_btn.setEnabled(False)
        self._prog_delete_btn.setEnabled(False)

    def _on_prog_selected(self, current: QListWidgetItem | None) -> None:
        if current is None:
            self._prog_update_btn.setEnabled(False)
            self._prog_delete_btn.setEnabled(False)
            return
        prog_id = current.data(USER_ROLE)
        prog = self._db.get_psyke_progression_by_id(prog_id)
        if prog is None:
            return
        self._prog_text_input.setText(prog.text)
        if prog.scene_id:
            idx = self._prog_scene_combo.findData(prog.scene_id)
            if idx >= 0:
                self._prog_scene_combo.setCurrentIndex(idx)
        else:
            self._prog_scene_combo.setCurrentIndex(0)
        self._prog_update_btn.setEnabled(True)
        self._prog_delete_btn.setEnabled(True)

    def _on_add_progression(self) -> None:
        if self._selected_id is None:
            return
        text = self._prog_text_input.text().strip()
        if not text:
            return
        scene_id = self._prog_scene_combo.currentData()
        self._db.create_psyke_progression(self._selected_id, text, scene_id=scene_id)
        self._refresh_progressions()
        if self._on_data_changed:
            self._on_data_changed()

    def _on_update_progression(self) -> None:
        current = self._prog_list.currentItem()
        if current is None:
            return
        prog_id = current.data(USER_ROLE)
        text = self._prog_text_input.text().strip()
        if not text:
            return
        scene_id = self._prog_scene_combo.currentData()
        self._db.update_psyke_progression(prog_id, text, scene_id=scene_id)
        self._refresh_progressions()
        if self._on_data_changed:
            self._on_data_changed()

    def _on_delete_progression(self) -> None:
        current = self._prog_list.currentItem()
        if current is None:
            return
        prog_id = current.data(USER_ROLE)
        self._db.delete_psyke_progression(prog_id)
        self._refresh_progressions()
        if self._on_data_changed:
            self._on_data_changed()

    # -- Scene References ----------------------------------------------------

    def _refresh_references(self) -> None:
        if self._selected_id is None:
            return
        self._refs_list.clear()
        refs = find_psyke_scene_references(
            self._db, self._project_id, self._selected_id,
        )
        for scene_id, scene_title in refs:
            item = QListWidgetItem(scene_title)
            item.setData(USER_ROLE, scene_id)
            self._refs_list.addItem(item)

    def _on_ref_clicked(self, item: QListWidgetItem) -> None:
        scene_id = item.data(USER_ROLE)
        if self._on_open_scene:
            self._on_open_scene(scene_id)

    # -- Detail fields -------------------------------------------------------

    def _on_type_changed(self) -> None:
        entry_type = self._type_combo.currentData() or "other"
        self._rebuild_detail_fields(entry_type)

    def _rebuild_detail_fields(self, entry_type: str) -> None:
        self._detail_widgets.clear()
        self._visual_widgets.clear()

        layout = self._details_layout
        while layout.count() > 1:
            item = layout.takeAt(1)
            w = item.widget()
            if w:
                w.hide()
                w.deleteLater()

        schema = get_detail_schema(entry_type)
        visual_schema = get_visual_schema(entry_type) if self._gn_mode else []
        if not schema and not visual_schema:
            self._details_section.setVisible(False)
            return
        # The full field list = flat detail fields, then the Visual Memory
        # group (rendered into a separate widget dict so it persists nested).
        schema = list(schema) + list(visual_schema)
        visual_keys = {s.key for s in visual_schema}

        current_section = None
        for spec in schema:
            if spec.section and spec.section != current_section:
                current_section = spec.section
                sep = QFrame()
                sep.setFrameShape(QFrame.Shape.HLine)
                sep.setFrameShadow(QFrame.Shadow.Sunken)
                layout.addWidget(sep)
                section_label = QLabel(f"<b>{current_section}</b>")
                section_label.setStyleSheet("margin-top: 4px; margin-bottom: 2px;")
                layout.addWidget(section_label)

            label = QLabel(spec.label)
            layout.addWidget(label)

            if spec.widget == "combo":
                widget = QComboBox()
                for opt in spec.options:
                    widget.addItem(opt or "(none)", opt)
                layout.addWidget(widget)
            elif spec.widget == "line":
                widget = QLineEdit()
                widget.setMaxLength(spec.max_chars)
                widget.setToolTip(f"Max {spec.max_chars} characters")
                layout.addWidget(widget)
            else:
                widget = QPlainTextEdit()
                widget.setMaximumHeight(80)
                widget.setToolTip(f"Max {spec.max_chars} characters")
                widget.textChanged.connect(
                    lambda w=widget, m=spec.max_chars: self._enforce_max(w, m)
                )
                layout.addWidget(widget)
            if spec.key in visual_keys:
                self._visual_widgets[spec.key] = widget
            else:
                self._detail_widgets[spec.key] = widget

        self._details_section.setVisible(True)

    def _enforce_max(self, widget: QPlainTextEdit, max_chars: int) -> None:
        text = widget.toPlainText()
        if len(text) > max_chars:
            widget.blockSignals(True)
            widget.setPlainText(text[:max_chars])
            cursor = widget.textCursor()
            cursor.movePosition(cursor.MoveOperation.End)
            widget.setTextCursor(cursor)
            widget.blockSignals(False)

    def _collect_details(self) -> dict:
        result: dict[str, str] = {}
        for key, widget in self._detail_widgets.items():
            if isinstance(widget, QComboBox):
                val = widget.currentData() or ""
            elif isinstance(widget, QLineEdit):
                val = widget.text().strip()
            else:
                val = widget.toPlainText().strip()
            if val:
                result[key] = val
        return result

    def _load_details(self, details: dict) -> None:
        for key, widget in self._detail_widgets.items():
            val = details.get(key, "")
            if isinstance(widget, QComboBox):
                idx = widget.findData(val)
                widget.setCurrentIndex(max(0, idx))
            elif isinstance(widget, QLineEdit):
                widget.setText(val)
            else:
                widget.setPlainText(val)

    def _collect_visual(self) -> dict:
        """Visual Memory field values (stored nested under ['visual'])."""
        result: dict[str, str] = {}
        for key, widget in self._visual_widgets.items():
            if isinstance(widget, QComboBox):
                val = widget.currentData() or ""
            elif isinstance(widget, QLineEdit):
                val = widget.text().strip()
            else:
                val = widget.toPlainText().strip()
            # Always include keys so cleared fields clear nested values.
            result[key] = val
        return result

    def _load_visual(self, visual: dict) -> None:
        if not isinstance(visual, dict):
            visual = {}
        for key, widget in self._visual_widgets.items():
            val = visual.get(key, "")
            if isinstance(widget, QComboBox):
                idx = widget.findData(val)
                widget.setCurrentIndex(max(0, idx))
            elif isinstance(widget, QLineEdit):
                widget.setText(val)
            else:
                widget.setPlainText(val)
