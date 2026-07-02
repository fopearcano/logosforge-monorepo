"""Scenes management view — list, create, edit, with chapter/plotline grouping."""

from collections.abc import Callable

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QKeySequence, QShortcut, QTextBlockFormat, QTextCursor
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from logosforge import preferences
from logosforge.analytics import compute_scene_stats
from logosforge.ui import theme

from logosforge.db import Database
from logosforge.ui.inline_assistant import InlineAssistantPanel
from logosforge.ui.inline_edit_bar import InlineEditBar
from logosforge.ui.link_preview import BacklinksWidget, create_link_browser, render_linked_text
from logosforge.ui.psyke_highlighter import PsykeClickHandler, PsykeHighlighter
from logosforge.ui.psyke_quick_create import PsykeQuickCreateDialog

USER_ROLE = Qt.ItemDataRole.UserRole
FILTER_ALL = "All"
BEAT_OPTIONS = [
    "",
    "Opening Image",
    "Setup",
    "Catalyst",
    "Debate",
    "Break into Two",
    "Midpoint",
    "Bad Guys Close In",
    "All Is Lost",
    "Break into Three",
    "Finale",
    "Final Image",
]


class ScenesView(QWidget):
    def __init__(
        self,
        db: Database,
        project_id: int,
        on_data_changed: Callable[[], None] | None = None,
        on_link_clicked: Callable[[str, int], None] | None = None,
        on_focus_mode_changed: Callable[[bool], None] | None = None,
        on_open_psyke_entry: Callable[[int], None] | None = None,
    ) -> None:
        super().__init__()
        self._db = db
        self._project_id = project_id
        self._on_data_changed = on_data_changed
        self._on_link_clicked = on_link_clicked
        self._on_focus_mode_changed = on_focus_mode_changed
        self._on_open_psyke_entry = on_open_psyke_entry
        self._selected_scene_id: int | None = None
        self._focus_mode = False
        self._refreshing = False
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(50)
        self._refresh_timer.timeout.connect(self._do_refresh)

        root = QHBoxLayout(self)

        # -- Left: scene list (wrapped for focus toggle) ---------------------
        self._left_panel = QWidget()
        self._left_panel.setFixedWidth(220)
        left = QVBoxLayout(self._left_panel)
        left.setContentsMargins(0, 0, 0, 0)
        left.addWidget(QLabel("Scenes"))

        left.addWidget(QLabel("Chapter filter"))
        self._chapter_filter = QComboBox()
        self._chapter_filter.currentTextChanged.connect(self._on_filter_changed)
        left.addWidget(self._chapter_filter)

        left.addWidget(QLabel("Plotline filter"))
        self._plotline_filter = QComboBox()
        self._plotline_filter.currentTextChanged.connect(self._on_filter_changed)
        left.addWidget(self._plotline_filter)

        left.addWidget(QLabel("Tag filter"))
        self._tag_filter = QComboBox()
        self._tag_filter.currentTextChanged.connect(self._on_filter_changed)
        left.addWidget(self._tag_filter)

        self._list = QListWidget()
        self._list.currentItemChanged.connect(self._on_scene_selected)
        left.addWidget(self._list)

        self._move_up_btn = QPushButton("Move Up")
        self._move_up_btn.setEnabled(False)
        self._move_up_btn.clicked.connect(self._on_move_up)
        left.addWidget(self._move_up_btn)

        self._move_down_btn = QPushButton("Move Down")
        self._move_down_btn.setEnabled(False)
        self._move_down_btn.clicked.connect(self._on_move_down)
        left.addWidget(self._move_down_btn)

        root.addWidget(self._left_panel)

        # -- Right: form -----------------------------------------------------
        right = QVBoxLayout()

        # -- Focus-mode top bar (hidden by default) --------------------------
        self._focus_top_bar = QWidget()
        ftb = QHBoxLayout(self._focus_top_bar)
        ftb.setContentsMargins(0, 0, 0, 10)
        self._focus_title_label = QLabel("")
        focus_title_font = QFont()
        focus_title_font.setBold(True)
        focus_title_font.setPointSize(focus_title_font.pointSize() + 1)
        self._focus_title_label.setFont(focus_title_font)
        self._focus_title_label.setStyleSheet(f"color: {theme.TEXT_SECONDARY};")
        ftb.addWidget(self._focus_title_label)
        ftb.addStretch()
        self._focus_word_label = QLabel("")
        self._focus_word_label.setStyleSheet(
            f"color: {theme.TEXT_MUTED}; font-size: 11px; padding-right: 12px;"
        )
        ftb.addWidget(self._focus_word_label)
        self._focus_exit_btn = QPushButton("Exit Focus")
        self._focus_exit_btn.clicked.connect(self._exit_focus_mode)
        ftb.addWidget(self._focus_exit_btn)
        self._focus_top_bar.setVisible(False)
        right.addWidget(self._focus_top_bar)

        self._form_label = QLabel("New Scene")
        right.addWidget(self._form_label)

        right.addWidget(QLabel("Title"))
        self._title_input = QLineEdit()
        right.addWidget(self._title_input)

        # -- Planning fields (hidden in focus mode) --------------------------
        self._planning_fields = QWidget()
        pf = QVBoxLayout(self._planning_fields)
        pf.setContentsMargins(0, 0, 0, 0)

        pf.addWidget(QLabel("Chapter"))
        self._chapter_input = QLineEdit()
        self._chapter_input.setPlaceholderText("e.g. Chapter 1")
        pf.addWidget(self._chapter_input)

        pf.addWidget(QLabel("Plotline"))
        self._plotline_input = QLineEdit()
        self._plotline_input.setPlaceholderText("e.g. Main Plot")
        pf.addWidget(self._plotline_input)

        pf.addWidget(QLabel("Act"))
        self._act_input = QComboBox()
        self._act_input.setEditable(True)
        self._act_input.lineEdit().setPlaceholderText("e.g. Act I")
        pf.addWidget(self._act_input)

        pf.addWidget(QLabel("Beat"))
        self._beat_input = QComboBox()
        self._beat_input.setEditable(True)
        self._beat_input.addItems(BEAT_OPTIONS)
        self._beat_input.lineEdit().setPlaceholderText("e.g. Catalyst")
        pf.addWidget(self._beat_input)

        pf.addWidget(QLabel("Tags"))
        self._tags_input = QLineEdit()
        self._tags_input.setPlaceholderText("e.g. love, betrayal, redemption")
        pf.addWidget(self._tags_input)

        pf.addWidget(QLabel("Summary"))
        self._summary_input = QPlainTextEdit()
        self._summary_input.setMaximumHeight(60)
        pf.addWidget(self._summary_input)

        pf.addWidget(QLabel("Synopsis"))
        self._synopsis_input = QPlainTextEdit()
        self._synopsis_input.setMaximumHeight(60)
        pf.addWidget(self._synopsis_input)

        pf.addWidget(QLabel("Goal"))
        self._goal_input = QPlainTextEdit()
        self._goal_input.setMaximumHeight(40)
        pf.addWidget(self._goal_input)

        pf.addWidget(QLabel("Conflict"))
        self._conflict_input = QPlainTextEdit()
        self._conflict_input.setMaximumHeight(40)
        pf.addWidget(self._conflict_input)

        pf.addWidget(QLabel("Outcome"))
        self._outcome_input = QPlainTextEdit()
        self._outcome_input.setMaximumHeight(40)
        pf.addWidget(self._outcome_input)

        right.addWidget(self._planning_fields)

        # -- Content (writing area) ------------------------------------------
        self._content_label = QLabel("Content")
        self._content_label.setStyleSheet(
            f"font-weight: bold; font-size: 15px; margin-top: 12px;"
            f" color: {theme.TEXT_SECONDARY};"
        )
        right.addWidget(self._content_label)

        self._ai_hint_bar = self._build_ai_hint_bar()
        self._ai_hint_bar.setVisible(False)
        right.addWidget(self._ai_hint_bar)

        writing_col = QHBoxLayout()
        writing_col.addStretch()
        self._content_input = QPlainTextEdit()
        self._content_input.setObjectName("contentEditor")
        self._content_input.setMinimumHeight(200)
        self._content_input.setMaximumWidth(800)
        self._content_input.setPlaceholderText("Write the full scene content here...")
        writing_font = QFont()
        writing_font.setPointSize(14)
        self._content_input.setFont(writing_font)
        self._content_input.setTabStopDistance(40.0)
        self._apply_line_spacing(self._content_input)
        writing_col.addWidget(self._content_input)
        writing_col.addStretch()
        right.addLayout(writing_col)

        # -- Scene stats (auto-updating) ------------------------------------
        self._stats_label = QLabel("")
        self._stats_label.setStyleSheet(
            f"color: {theme.TEXT_MUTED}; font-size: 11px; padding: 2px 4px;"
        )
        right.addWidget(self._stats_label)

        self._stats_timer = QTimer(self)
        self._stats_timer.setSingleShot(True)
        self._stats_timer.setInterval(300)
        self._stats_timer.timeout.connect(self._update_scene_stats)
        self._content_input.textChanged.connect(self._stats_timer.start)

        # -- Inline AI assist (togglable) ------------------------------------
        self._assist_toggle = QPushButton("AI Assist")
        self._assist_toggle.clicked.connect(self._toggle_assist_panel)
        right.addWidget(self._assist_toggle)

        self._assist_panel = InlineAssistantPanel(
            content_editor=self._content_input,
            db=db,
            project_id=project_id,
            get_scene_id=lambda: self._selected_scene_id,
            on_data_changed=on_data_changed,
        )
        self._assist_panel.setVisible(False)
        right.addWidget(self._assist_panel)

        # -- Inline edit bar (floats over editor viewport) -------------------
        self._inline_edit = InlineEditBar(
            editor=self._content_input,
            db=db,
            project_id=project_id,
            get_scene_id=lambda: self._selected_scene_id,
            provider_widget=self._assist_panel._provider_widget,
            on_data_changed=on_data_changed,
        )
        self._assist_panel.slash_completed.connect(
            self._inline_edit.show_inline_result,
        )
        self._inline_edit.ai_action_completed.connect(self._dismiss_ai_hint)
        self._assist_panel.slash_completed.connect(
            lambda _: self._dismiss_ai_hint(),
        )

        # -- PSYKE highlighter + click-to-jump --------------------------------
        self._psyke_highlighter = PsykeHighlighter(self._content_input.document())
        self._psyke_click_handler = PsykeClickHandler(
            self._content_input,
            self._psyke_highlighter,
            on_jump=self._on_psyke_jump,
        )
        self._content_input.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu
        )
        self._content_input.customContextMenuRequested.connect(
            self._show_editor_context_menu
        )
        QTimer.singleShot(0, self._refresh_psyke_terms)

        # -- Detail fields (hidden in focus mode) ----------------------------
        self._detail_fields = QWidget()
        df = QVBoxLayout(self._detail_fields)
        df.setContentsMargins(0, 0, 0, 0)

        df.addWidget(QLabel("Link Preview"))
        self._link_preview = create_link_browser(self._on_link_name_clicked)
        df.addWidget(self._link_preview)

        df.addWidget(QLabel("Characters"))
        self._char_list = QListWidget()
        self._char_list.setMaximumHeight(100)
        df.addWidget(self._char_list)

        df.addWidget(QLabel("Places"))
        self._place_list = QListWidget()
        self._place_list.setMaximumHeight(100)
        df.addWidget(self._place_list)

        df.addWidget(QLabel("Character States"))
        state_row = QHBoxLayout()
        self._state_char_combo = QComboBox()
        state_row.addWidget(self._state_char_combo)
        self._state_text_input = QLineEdit()
        self._state_text_input.setPlaceholderText("e.g. conflicted, hopeful")
        state_row.addWidget(self._state_text_input)
        self._add_state_btn = QPushButton("Add")
        self._add_state_btn.clicked.connect(self._on_add_state)
        state_row.addWidget(self._add_state_btn)
        df.addLayout(state_row)

        self._state_list = QListWidget()
        self._state_list.setMaximumHeight(80)
        df.addWidget(self._state_list)

        self._remove_state_btn = QPushButton("Remove State")
        self._remove_state_btn.clicked.connect(self._on_remove_state)
        df.addWidget(self._remove_state_btn)

        self._save_btn = QPushButton("Save")
        self._save_btn.clicked.connect(self._on_save)
        df.addWidget(self._save_btn)

        self._delete_btn = QPushButton("Delete")
        self._delete_btn.setEnabled(False)
        self._delete_btn.clicked.connect(self._on_delete)
        df.addWidget(self._delete_btn)

        self._new_btn = QPushButton("New Scene")
        self._new_btn.clicked.connect(self._clear_form)
        df.addWidget(self._new_btn)

        self._backlinks = BacklinksWidget(
            db, project_id, on_backlink_clicked=on_link_clicked,
        )
        df.addWidget(self._backlinks)

        right.addWidget(self._detail_fields)

        # -- Focus mode toggle -----------------------------------------------
        self._focus_btn = QPushButton("Focus Mode")
        self._focus_btn.clicked.connect(self.toggle_focus_mode)
        right.addWidget(self._focus_btn)

        right.addStretch()

        right_widget = QWidget()
        right_widget.setLayout(right)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(right_widget)
        root.addWidget(scroll, stretch=1)

        # Escape exits focus mode
        esc = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        esc.activated.connect(self._exit_focus_mode)

        # Ctrl/Cmd+Shift+F toggles focus mode (widget-local to avoid
        # conflict with the global menu-bar shortcut)
        focus_shortcut = QShortcut(QKeySequence("Ctrl+Shift+F"), self)
        focus_shortcut.setContext(
            Qt.ShortcutContext.WidgetWithChildrenShortcut
        )
        focus_shortcut.activated.connect(self.toggle_focus_mode)

        # Ctrl/Cmd+K triggers inline edit bar
        inline_shortcut = QShortcut(QKeySequence("Ctrl+K"), self)
        inline_shortcut.setContext(
            Qt.ShortcutContext.WidgetWithChildrenShortcut
        )
        inline_shortcut.activated.connect(self._inline_edit.activate)

        psyke_create_shortcut = QShortcut(QKeySequence("Ctrl+Shift+K"), self)
        psyke_create_shortcut.setContext(
            Qt.ShortcutContext.WidgetWithChildrenShortcut
        )
        psyke_create_shortcut.activated.connect(self._quick_create_psyke)

        self._refresh_filters()
        self._refresh_act_options()
        self._refresh_list()
        QTimer.singleShot(0, self._load_characters_and_states)
        QTimer.singleShot(0, self._load_places)

    # -- Populate checkable lists --------------------------------------------

    def refresh(self) -> None:
        """Schedule a debounced data refresh."""
        self._refresh_timer.start()

    def _do_refresh(self) -> None:
        if self._refreshing:
            return
        self._refreshing = True
        try:
            self._load_characters_and_states()
            self._load_places()
            self._refresh_filters()
            self._refresh_act_options()
            self._refresh_list()
            self._refresh_psyke_terms()
        finally:
            self._refreshing = False

    def _refresh_act_options(self) -> None:
        current = self._act_input.currentText()
        self._act_input.blockSignals(True)
        self._act_input.clear()
        self._act_input.addItem("")
        acts = sorted({
            (s.act or "").strip()
            for s in self._db.get_all_scenes(self._project_id)
        } - {""})
        if not acts:
            acts = ["Act I", "Act II", "Act III"]
        for act in acts:
            self._act_input.addItem(act)
        self._act_input.setCurrentText(current)
        self._act_input.blockSignals(False)

    def _load_characters_and_states(self) -> None:
        chars = self._db.get_all_characters(self._project_id)

        self._char_list.clear()
        self._state_char_combo.clear()
        self._char_id_by_name: dict[str, int] = {}
        self._char_name_by_id: dict[int, str] = {}

        for char in chars:
            item = QListWidgetItem(char.name)
            item.setData(USER_ROLE, char.id)
            item.setCheckState(Qt.CheckState.Unchecked)
            self._char_list.addItem(item)

            self._state_char_combo.addItem(char.name)
            self._char_id_by_name[char.name] = char.id
            self._char_name_by_id[char.id] = char.name

    def _load_places(self) -> None:
        self._place_list.clear()
        for place in self._db.get_all_places(self._project_id):
            item = QListWidgetItem(place.name)
            item.setData(USER_ROLE, place.id)
            item.setCheckState(Qt.CheckState.Unchecked)
            self._place_list.addItem(item)

    def _on_add_state(self) -> None:
        name = self._state_char_combo.currentText()
        state = self._state_text_input.text().strip()
        if not name or not state:
            return
        char_id = self._char_id_by_name.get(name)
        if char_id is None:
            return
        item = QListWidgetItem(f"{name}: {state}")
        item.setData(USER_ROLE, (char_id, state))
        self._state_list.addItem(item)
        self._state_text_input.clear()

    def _on_remove_state(self) -> None:
        row = self._state_list.currentRow()
        if row >= 0:
            self._state_list.takeItem(row)

    def _get_character_states(self) -> list[tuple[int, str]]:
        states = []
        for i in range(self._state_list.count()):
            data = self._state_list.item(i).data(USER_ROLE)
            if data:
                states.append(data)
        return states

    def _load_character_states(self, scene_id: int) -> None:
        self._state_list.clear()
        for char_id, state in self._db.get_scene_character_states(scene_id):
            name = self._char_name_by_id.get(char_id, f"Character {char_id}")
            item = QListWidgetItem(f"{name}: {state}")
            item.setData(USER_ROLE, (char_id, state))
            self._state_list.addItem(item)

    # -- Filters -------------------------------------------------------------

    def _refresh_filters(self) -> None:
        self._refresh_combo(
            self._chapter_filter,
            self._db.get_scene_chapters(self._project_id),
        )
        self._refresh_combo(
            self._plotline_filter,
            self._db.get_scene_plotlines(self._project_id),
        )
        self._refresh_combo(
            self._tag_filter,
            self._db.get_scene_tags(self._project_id),
        )

    def _refresh_combo(self, combo: QComboBox, values: list[str]) -> None:
        combo.blockSignals(True)
        current = combo.currentText()
        combo.clear()
        combo.addItem(FILTER_ALL)
        for val in values:
            combo.addItem(val)
        idx = combo.findText(current)
        combo.setCurrentIndex(idx if idx >= 0 else 0)
        combo.blockSignals(False)

    def _get_filter_value(self, combo: QComboBox) -> str | None:
        text = combo.currentText()
        return None if text == FILTER_ALL else text

    def _on_filter_changed(self) -> None:
        self._clear_form()
        self._refresh_list()

    # -- Scene list ----------------------------------------------------------

    def _refresh_list(self) -> None:
        self._list.blockSignals(True)
        self._list.clear()
        scenes = self._db.get_all_scenes(
            self._project_id,
            chapter=self._get_filter_value(self._chapter_filter),
            plotline=self._get_filter_value(self._plotline_filter),
            tag=self._get_filter_value(self._tag_filter),
        )
        for scene in scenes:
            label = self._format_scene_label(scene)
            item = QListWidgetItem(label)
            item.setData(USER_ROLE, scene.id)
            self._list.addItem(item)
        self._list.blockSignals(False)

    def _format_scene_label(self, scene) -> str:
        tags = []
        if scene.chapter:
            tags.append(scene.chapter)
        if scene.plotline:
            tags.append(scene.plotline)
        if scene.beat:
            tags.append(scene.beat)
        if tags:
            return f"[{' | '.join(tags)}] {scene.title}"
        return scene.title

    # -- Selection -----------------------------------------------------------

    def _on_scene_selected(self, current: QListWidgetItem | None) -> None:
        if current is None:
            return

        scene_id = current.data(USER_ROLE)
        scene = self._db.get_scene_by_id(scene_id)
        if scene is None:
            return

        self._selected_scene_id = scene.id
        self._form_label.setText("Edit Scene")
        self._delete_btn.setEnabled(True)
        self._move_up_btn.setEnabled(True)
        self._move_down_btn.setEnabled(True)
        self._title_input.setText(scene.title)
        self._chapter_input.setText(scene.chapter)
        self._plotline_input.setText(scene.plotline)
        self._act_input.setCurrentText(scene.act or "")
        self._beat_input.setCurrentText(scene.beat)
        self._tags_input.setText(scene.tags)
        self._summary_input.setPlainText(scene.summary)
        self._synopsis_input.setPlainText(scene.synopsis)
        self._goal_input.setPlainText(scene.goal)
        self._conflict_input.setPlainText(scene.conflict)
        self._outcome_input.setPlainText(scene.outcome)
        self._content_input.blockSignals(True)
        self._content_input.setPlainText(scene.content)
        if scene.content:
            self._apply_line_spacing(self._content_input)
        self._content_input.blockSignals(False)
        self._update_scene_stats()
        self._update_link_preview(scene.summary, scene.synopsis)
        self._backlinks.load(scene.title)
        self._load_character_states(scene_id)

        # Check linked characters
        linked_char_ids = set(self._db.get_scene_character_ids(scene_id))
        for i in range(self._char_list.count()):
            item = self._char_list.item(i)
            checked = item.data(USER_ROLE) in linked_char_ids
            item.setCheckState(
                Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
            )

        # Check linked places
        linked_place_ids = set(self._db.get_scene_place_ids(scene_id))
        for i in range(self._place_list.count()):
            item = self._place_list.item(i)
            checked = item.data(USER_ROLE) in linked_place_ids
            item.setCheckState(
                Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
            )

    # -- Save (create or update) ---------------------------------------------

    def _on_save(self) -> None:
        title = self._title_input.text().strip()
        if not title:
            return

        summary = self._summary_input.toPlainText().strip()
        synopsis = self._synopsis_input.toPlainText().strip()
        goal = self._goal_input.toPlainText().strip()
        conflict = self._conflict_input.toPlainText().strip()
        outcome = self._outcome_input.toPlainText().strip()
        content = self._content_input.toPlainText()
        beat = self._beat_input.currentText().strip()
        tags = ", ".join(
            t for t in (t.strip() for t in self._tags_input.text().split(",")) if t
        )
        act = self._act_input.currentText()
        chapter = self._chapter_input.text().strip()
        plotline = self._plotline_input.text().strip()
        char_ids = self._get_checked_ids(self._char_list)
        place_ids = self._get_checked_ids(self._place_list)
        char_states = self._get_character_states()

        if self._selected_scene_id is not None:
            self._db.update_scene(
                scene_id=self._selected_scene_id,
                title=title,
                summary=summary,
                synopsis=synopsis,
                goal=goal,
                conflict=conflict,
                outcome=outcome,
                beat=beat,
                tags=tags,
                act=act,
                content=content,
                chapter=chapter,
                plotline=plotline,
                character_ids=char_ids,
                place_ids=place_ids,
                character_states=char_states,
            )
        else:
            self._db.create_scene(
                project_id=self._project_id,
                title=title,
                summary=summary,
                synopsis=synopsis,
                goal=goal,
                conflict=conflict,
                outcome=outcome,
                beat=beat,
                tags=tags,
                act=act,
                content=content,
                chapter=chapter,
                plotline=plotline,
                character_ids=char_ids,
                place_ids=place_ids,
                character_states=char_states,
            )

        self._clear_form()
        self._refresh_filters()
        self._refresh_list()
        if self._on_data_changed:
            self._on_data_changed()

    # -- Delete --------------------------------------------------------------

    def _on_delete(self) -> None:
        if self._selected_scene_id is None:
            return
        self._db.delete_scene(self._selected_scene_id)
        self._clear_form()
        self._refresh_filters()
        self._refresh_list()
        if self._on_data_changed:
            self._on_data_changed()

    # -- Reorder -------------------------------------------------------------

    def _on_move_up(self) -> None:
        if self._selected_scene_id is None:
            return
        self._db.move_scene_up(self._selected_scene_id)
        self._refresh_list()
        self._reselect(self._selected_scene_id)
        if self._on_data_changed:
            self._on_data_changed()

    def _on_move_down(self) -> None:
        if self._selected_scene_id is None:
            return
        self._db.move_scene_down(self._selected_scene_id)
        self._refresh_list()
        self._reselect(self._selected_scene_id)
        if self._on_data_changed:
            self._on_data_changed()

    def select_scene(self, scene_id: int) -> None:
        """Programmatically select a scene by ID (used by Timeline navigation)."""
        self._reselect(scene_id)

    def _reselect(self, scene_id: int) -> None:
        for i in range(self._list.count()):
            if self._list.item(i).data(USER_ROLE) == scene_id:
                self._list.setCurrentRow(i)
                return

    # -- Helpers -------------------------------------------------------------

    def _build_ai_hint_bar(self) -> QWidget:
        bar = QWidget()
        bar.setStyleSheet(
            f"background: {theme.BG_PANEL};"
            f" border: 1px solid {theme.BORDER}; border-radius: 6px;"
        )
        row = QHBoxLayout(bar)
        row.setContentsMargins(12, 8, 8, 8)
        row.setSpacing(8)
        hint = QLabel("Select text and press Ctrl+K to edit with AI.")
        hint.setStyleSheet(
            f"color: {theme.TEXT_SECONDARY}; font-size: 11px;"
        )
        row.addWidget(hint)
        row.addStretch()
        close = QPushButton("\u2715")
        close.setFixedWidth(22)
        close.setFlat(True)
        close.setStyleSheet(
            f"QPushButton {{ color: {theme.TEXT_MUTED}; border: none; }}"
            f"QPushButton:hover {{ color: {theme.TEXT_PRIMARY}; }}"
        )
        close.clicked.connect(self._dismiss_ai_hint)
        row.addWidget(close)
        return bar

    def _dismiss_ai_hint(self) -> None:
        if self._ai_hint_bar.isVisible():
            self._ai_hint_bar.setVisible(False)
            preferences.set_flag("has_seen_ai_hint", True)

    @staticmethod
    def _apply_line_spacing(editor: QPlainTextEdit, percent: int = 165) -> None:
        fmt = QTextBlockFormat()
        fmt.setLineHeight(percent, 1)  # 1 = ProportionalHeight
        fmt.setBottomMargin(8 if percent >= 200 else 4)
        cursor = editor.textCursor()
        cursor.select(QTextCursor.SelectionType.Document)
        cursor.mergeBlockFormat(fmt)
        cursor.clearSelection()
        editor.setTextCursor(cursor)

    def _clear_form(self) -> None:
        self._selected_scene_id = None
        self._form_label.setText("New Scene")
        self._delete_btn.setEnabled(False)
        self._move_up_btn.setEnabled(False)
        self._move_down_btn.setEnabled(False)
        self._title_input.clear()
        self._chapter_input.clear()
        self._plotline_input.clear()
        self._act_input.setCurrentIndex(0)
        self._beat_input.setCurrentIndex(0)
        self._tags_input.clear()
        self._summary_input.clear()
        self._synopsis_input.clear()
        self._goal_input.clear()
        self._conflict_input.clear()
        self._outcome_input.clear()
        self._content_input.blockSignals(True)
        self._content_input.clear()
        self._content_input.blockSignals(False)
        self._stats_label.setText("")
        self._focus_word_label.setText("")
        self._link_preview.clear()
        self._backlinks.clear_backlinks()
        self._state_list.clear()
        self._state_text_input.clear()
        self._uncheck_all(self._char_list)
        self._uncheck_all(self._place_list)
        self._list.clearSelection()

    def _get_checked_ids(self, list_widget: QListWidget) -> list[int]:
        ids = []
        for i in range(list_widget.count()):
            item = list_widget.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                ids.append(item.data(USER_ROLE))
        return ids

    def _uncheck_all(self, list_widget: QListWidget) -> None:
        for i in range(list_widget.count()):
            list_widget.item(i).setCheckState(Qt.CheckState.Unchecked)

    def _update_link_preview(self, summary: str, synopsis: str) -> None:
        parts: list[str] = []
        if summary:
            parts.append(render_linked_text(summary))
        if synopsis:
            if parts:
                parts.append("<hr>")
            parts.append(render_linked_text(synopsis))
        self._link_preview.setHtml("".join(parts) if parts else "")

    def _on_link_name_clicked(self, name: str) -> None:
        result = self._db.resolve_link(self._project_id, name)
        if result is None:
            return
        entity_type, entity_id = result
        if self._on_link_clicked:
            self._on_link_clicked(entity_type, entity_id)

    # -- Scene stats -------------------------------------------------------------

    def _update_scene_stats(self) -> None:
        text = self._content_input.toPlainText()
        stats = compute_scene_stats(text)
        if stats["words"] == 0:
            self._stats_label.setText("")
            self._focus_word_label.setText("")
            return
        pct = round(stats["dialogue_ratio"] * 100)
        parts = [
            f"Words: {stats['words']}",
            f"Paragraphs: {stats['paragraphs']}",
            f"Sentences: ~{stats['sentences']}",
            f"Dialogue: {pct}%",
        ]
        if stats["hint"]:
            parts.append(stats["hint"])
        self._stats_label.setText("  \u00b7  ".join(parts))
        self._focus_word_label.setText(f"{stats['words']} words")

    # -- PSYKE highlighting and quick create ------------------------------------

    def _refresh_psyke_terms(self) -> None:
        entries = self._db.get_all_psyke_entries(self._project_id)
        terms: list[str] = []
        term_map: dict[str, int] = {}
        for e in entries:
            if e.name.strip():
                terms.append(e.name)
                term_map[e.name.lower()] = e.id
            if e.aliases:
                for alias in e.aliases.split(","):
                    alias = alias.strip()
                    if alias:
                        terms.append(alias)
                        term_map[alias.lower()] = e.id
        self._psyke_highlighter.refresh_patterns(terms)
        self._psyke_click_handler.set_term_map(term_map)

    def _on_psyke_jump(self, entry_id: int) -> None:
        if self._on_open_psyke_entry:
            self._on_open_psyke_entry(entry_id)

    def _show_editor_context_menu(self, pos) -> None:
        menu = self._content_input.createStandardContextMenu()
        selection = self._content_input.textCursor().selectedText().strip()
        menu.addSeparator()
        action = menu.addAction("Create PSYKE entry from selection")
        action.setEnabled(bool(selection))
        action.triggered.connect(self._quick_create_psyke)
        menu.exec(self._content_input.mapToGlobal(pos))

    def _quick_create_psyke(self) -> None:
        selection = self._content_input.textCursor().selectedText().strip()
        dlg = PsykeQuickCreateDialog(self, initial_name=selection)
        if dlg.exec() != PsykeQuickCreateDialog.DialogCode.Accepted:
            return
        vals = dlg.get_values()
        if not vals["name"]:
            return
        self._db.create_psyke_entry(
            self._project_id,
            name=vals["name"],
            entry_type=vals["entry_type"],
            aliases=vals["aliases"],
            notes=vals["notes"],
            is_global=vals["is_global"],
        )
        self._refresh_psyke_terms()
        if self._on_data_changed:
            self._on_data_changed()

    # -- Inline assistant --------------------------------------------------------

    def _toggle_assist_panel(self) -> None:
        visible = not self._assist_panel.isVisible()
        self._assist_panel.setVisible(visible)
        self._assist_toggle.setText("Hide AI Assist" if visible else "AI Assist")

    # -- Focus mode --------------------------------------------------------------

    def toggle_focus_mode(self) -> None:
        self._focus_mode = not self._focus_mode
        show = not self._focus_mode

        self.setUpdatesEnabled(False)
        self._left_panel.setVisible(show)
        self._planning_fields.setVisible(show)
        self._detail_fields.setVisible(show)
        self._form_label.setVisible(show)
        self._content_label.setVisible(show)
        self._assist_toggle.setVisible(show)
        self._title_input.setVisible(show)
        self._stats_label.setVisible(show)
        self._focus_btn.setVisible(show)
        self._focus_top_bar.setVisible(self._focus_mode)
        if self._focus_mode:
            self._assist_panel.setVisible(False)
            self._focus_title_label.setText(
                self._title_input.text().strip() or "Untitled scene"
            )
        self.setUpdatesEnabled(True)

        if self._content_input.toPlainText():
            self._apply_line_spacing(
                self._content_input, 200 if self._focus_mode else 165
            )
        self._update_scene_stats()

        self.layout().invalidate()
        self.update()

        if self._on_focus_mode_changed:
            self._on_focus_mode_changed(self._focus_mode)

    def _exit_focus_mode(self) -> None:
        if self._focus_mode:
            self.toggle_focus_mode()
