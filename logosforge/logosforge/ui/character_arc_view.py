"""Character Arc view — ordered list of a character's states across scenes.

Characters come from PSYKE entries of type "character" (the project's
source of truth), so every story-bible character is selectable. Arc data
is resolved by name against recorded scene character-states.
"""

from collections.abc import Callable
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from logosforge.db import Database

USER_ROLE = Qt.ItemDataRole.UserRole


class CharacterArcView(QWidget):
    def __init__(
        self,
        db: Database,
        project_id: int,
        on_scene_selected: Optional[Callable[[int], None]] = None,
    ) -> None:
        super().__init__()
        self._db = db
        self._project_id = project_id
        self._on_scene_selected = on_scene_selected

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Character Arc"))
        help_label = QLabel(
            "Each row is a scene where this character has a recorded state — "
            "their emotional/mental condition there (set in the Scenes editor). "
            "Double-click a row to open that scene."
        )
        help_label.setWordWrap(True)
        help_label.setStyleSheet("color: #94a3b8; font-size: 12px;")
        layout.addWidget(help_label)

        self._char_combo = QComboBox()
        self._char_combo.currentIndexChanged.connect(self._on_character_changed)
        layout.addWidget(self._char_combo)

        self._arc_list = QListWidget()
        self._arc_list.itemDoubleClicked.connect(self._on_item_double_clicked)
        layout.addWidget(self._arc_list)

        self._empty_label = QLabel("Select a character to view their arc.")
        self._empty_label.setWordWrap(True)
        layout.addWidget(self._empty_label)

        self._connect_events()
        self._load_characters()

    # -- Event wiring --------------------------------------------------------

    def _connect_events(self) -> None:
        """Rebuild the selector when the project or PSYKE entries change.

        Bound-method connections auto-disconnect when this widget is
        destroyed, so replaced views never leak."""
        try:
            from logosforge.project_events import get_event_bus
            bus = get_event_bus()
            bus.project_loaded.connect(self._on_project_changed)
            bus.project_created.connect(self._on_project_changed)
            for signal in (
                bus.psyke_changed,
                bus.psyke_list_changed,
                bus.project_data_changed,
            ):
                signal.connect(self._on_data_event)
        except Exception:
            pass

    def _on_project_changed(self, project_id: int) -> None:
        self.set_project(project_id)

    def _on_data_event(self, *_args) -> None:
        self.refresh()

    def set_project(self, project_id: int) -> None:
        """Point at a new project and reload its PSYKE characters, dropping
        any characters from the previous project."""
        self._project_id = project_id
        self.refresh()

    def _is_alive(self) -> bool:
        try:
            self._char_combo.count()
            return True
        except RuntimeError:
            return False

    def refresh(self) -> None:
        """Rebuild the character selector from current PSYKE characters,
        preserving the current selection by name when still present."""
        if not self._is_alive():
            return
        previous = self._char_combo.currentData()
        self._load_characters(preserve=previous)

    # -- Data ----------------------------------------------------------------

    def _psyke_characters(self):
        entries = self._db.get_all_psyke_entries(self._project_id)
        chars = [
            e for e in entries
            if (getattr(e, "entry_type", "") or "").lower() == "character"
        ]
        chars.sort(key=lambda e: (e.name or "").lower())
        return chars

    def _load_characters(self, preserve: str | None = None) -> None:
        self._char_combo.blockSignals(True)
        self._char_combo.clear()
        self._char_combo.addItem("-- Select Character --", None)
        # Source of truth: PSYKE character entries for THIS project. The
        # item data is the character name, used to resolve arc states.
        restore_index = 0
        for entry in self._psyke_characters():
            self._char_combo.addItem(entry.name, entry.name)
            if preserve is not None and entry.name == preserve:
                restore_index = self._char_combo.count() - 1
        self._char_combo.blockSignals(False)

        if restore_index > 0:
            self._char_combo.setCurrentIndex(restore_index)
            self._on_character_changed(restore_index)
        else:
            self._char_combo.setCurrentIndex(0)
            self._arc_list.clear()
            if self._char_combo.count() <= 1:
                self._empty_label.setText(
                    "No characters yet. Create a character entry in PSYKE."
                )
            else:
                self._empty_label.setText("Select a character to view their arc.")
            self._empty_label.setVisible(True)

    def _on_character_changed(self, index: int) -> None:
        name = self._char_combo.currentData()
        if not name:
            self._arc_list.clear()
            self._empty_label.setText("Select a character to view their arc.")
            self._empty_label.setVisible(True)
            return

        arc = self._db.get_character_arc_by_name(self._project_id, name)
        self._arc_list.clear()

        if not arc:
            # Keep the "No scene states" lead-in, but tailor the next step to
            # whether the project has any scenes at all.
            if len(self._db.get_all_scenes(self._project_id)) == 0:
                guidance = ("Create scenes and give this character a state in "
                            "each to chart their arc.")
            else:
                guidance = ("Add a character state in the Scenes editor for "
                            "the scenes they appear in.")
            self._empty_label.setText(
                "No scene states found for this character.\n" + guidance
            )
            self._empty_label.setVisible(True)
            return

        self._empty_label.setVisible(False)
        for scene_id, title, order_index, state in arc:
            text = f"[{order_index}] {title}  →  \"{state}\""
            item = QListWidgetItem(text)
            item.setData(USER_ROLE, scene_id)
            self._arc_list.addItem(item)

    def _on_item_double_clicked(self, item: QListWidgetItem) -> None:
        scene_id = item.data(USER_ROLE)
        if scene_id is not None and self._on_scene_selected:
            self._on_scene_selected(scene_id)
