"""Search view — global search across project entities with filtering."""

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from logosforge.db import Database

USER_ROLE = Qt.ItemDataRole.UserRole
MAX_PREVIEW = 80
FILTER_ALL = "All"
ENTITY_TYPES = ("Character", "Place", "Note", "Scene")


class SearchView(QWidget):
    def __init__(
        self,
        db: Database,
        project_id: int,
        on_result_selected: Callable[[str, int], None] | None = None,
    ) -> None:
        super().__init__()
        self._db = db
        self._project_id = project_id
        self._on_result_selected = on_result_selected
        self._last_results: list[dict] = []

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Search"))

        # -- Search input row ------------------------------------------------
        search_row = QHBoxLayout()
        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("Search characters, places, notes, scenes...")
        self._search_input.returnPressed.connect(self._on_search)
        search_row.addWidget(self._search_input)

        search_btn = QPushButton("Search")
        search_btn.clicked.connect(self._on_search)
        search_row.addWidget(search_btn)

        layout.addLayout(search_row)

        # -- Entity type checkboxes ------------------------------------------
        type_row = QHBoxLayout()
        type_row.addWidget(QLabel("Show:"))

        self._type_checks: dict[str, QCheckBox] = {}
        for entity_type in ENTITY_TYPES:
            cb = QCheckBox(entity_type + "s")
            cb.setChecked(True)
            cb.stateChanged.connect(self._on_filter_changed)
            type_row.addWidget(cb)
            self._type_checks[entity_type] = cb

        type_row.addStretch()
        layout.addLayout(type_row)

        # -- Scene-specific filters ------------------------------------------
        scene_filter_row = QHBoxLayout()

        scene_filter_row.addWidget(QLabel("Chapter:"))
        self._chapter_filter = QComboBox()
        self._chapter_filter.addItem(FILTER_ALL)
        for ch in self._db.get_scene_chapters(self._project_id):
            self._chapter_filter.addItem(ch)
        self._chapter_filter.currentTextChanged.connect(self._on_filter_changed)
        scene_filter_row.addWidget(self._chapter_filter)

        scene_filter_row.addWidget(QLabel("Plotline:"))
        self._plotline_filter = QComboBox()
        self._plotline_filter.addItem(FILTER_ALL)
        for pl in self._db.get_scene_plotlines(self._project_id):
            self._plotline_filter.addItem(pl)
        self._plotline_filter.currentTextChanged.connect(self._on_filter_changed)
        scene_filter_row.addWidget(self._plotline_filter)

        scene_filter_row.addWidget(QLabel("Tag:"))
        self._tag_filter = QComboBox()
        self._tag_filter.addItem(FILTER_ALL)
        for tag in self._db.get_scene_tags(self._project_id):
            self._tag_filter.addItem(tag)
        self._tag_filter.currentTextChanged.connect(self._on_filter_changed)
        scene_filter_row.addWidget(self._tag_filter)

        scene_filter_row.addStretch()
        layout.addLayout(scene_filter_row)

        # -- Status and results ----------------------------------------------
        self._status_label = QLabel("")
        layout.addWidget(self._status_label)

        self._results_list = QListWidget()
        self._results_list.itemDoubleClicked.connect(self._on_item_double_clicked)
        layout.addWidget(self._results_list)

        self._search_input.setFocus()
        self._sync_scene_filter_state()

    # -- Search --------------------------------------------------------------

    def _on_search(self) -> None:
        query = self._search_input.text().strip()

        if not query:
            self._last_results = []
            self._results_list.clear()
            self._status_label.setText("Enter a search term.")
            return

        self._last_results = self._db.search_project(self._project_id, query)
        self._apply_filters()

    # -- Filters -------------------------------------------------------------

    def _on_filter_changed(self) -> None:
        self._sync_scene_filter_state()
        if self._last_results:
            self._apply_filters()

    def _sync_scene_filter_state(self) -> None:
        scenes_checked = self._type_checks["Scene"].isChecked()
        self._chapter_filter.setEnabled(scenes_checked)
        self._plotline_filter.setEnabled(scenes_checked)
        self._tag_filter.setEnabled(scenes_checked)

    def _apply_filters(self) -> None:
        allowed_types = {t for t, cb in self._type_checks.items() if cb.isChecked()}
        chapter_filter = self._chapter_filter.currentText()
        plotline_filter = self._plotline_filter.currentText()
        tag_filter = self._tag_filter.currentText()

        filtered: list[dict] = []
        for result in self._last_results:
            if result["type"] not in allowed_types:
                continue
            if result["type"] == "Scene":
                if chapter_filter != FILTER_ALL:
                    if result.get("chapter", "") != chapter_filter:
                        continue
                if plotline_filter != FILTER_ALL:
                    if result.get("plotline", "") != plotline_filter:
                        continue
                if tag_filter != FILTER_ALL:
                    scene_tags = [
                        t.strip().lower()
                        for t in result.get("tags", "").split(",")
                        if t.strip()
                    ]
                    if tag_filter.lower() not in scene_tags:
                        continue
            filtered.append(result)

        self._display_results(filtered)

    # -- Display -------------------------------------------------------------

    def _display_results(self, results: list[dict]) -> None:
        self._results_list.clear()
        query = self._search_input.text().strip()

        if not results and not self._last_results:
            self._status_label.setText(f'No results for "{query}".')
            return

        if not results and self._last_results:
            total = len(self._last_results)
            self._status_label.setText(
                f'0 of {total} result(s) shown (all filtered out).'
            )
            return

        total = len(self._last_results)
        shown = len(results)
        if shown == total:
            self._status_label.setText(f'{shown} result(s) for "{query}".')
        else:
            self._status_label.setText(
                f'{shown} of {total} result(s) for "{query}".'
            )

        for result in results:
            label = f"[{result['type']}] {result['label']}"
            preview = result.get("preview", "")
            if preview:
                if len(preview) > MAX_PREVIEW:
                    preview = preview[:MAX_PREVIEW] + "..."
                label += f"  —  {preview}"

            item = QListWidgetItem(label)
            item.setData(USER_ROLE, (result["type"], result["id"]))
            self._results_list.addItem(item)

    # -- Navigation ----------------------------------------------------------

    def _on_item_double_clicked(self, item: QListWidgetItem) -> None:
        if self._on_result_selected is None:
            return
        data = item.data(USER_ROLE)
        if data:
            entity_type, entity_id = data
            self._on_result_selected(entity_type, entity_id)
