"""Timeline view — plotline-column or chapter-column overview with minimal editing."""

from collections.abc import Callable

from PySide6.QtCore import QEvent, QPoint, Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from PySide6.QtWidgets import QInputDialog, QMenu

from logosforge.db import Database
from logosforge.ui import theme
from logosforge.ui.color_labels import build_color_menu, color_hex

FILTER_ALL = "All"
UNASSIGNED = "Unassigned"

MODE_BY_PLOTLINE = "By Plotline"
MODE_BY_CHAPTER = "By Chapter"

def _card_style() -> str:
    return (
        f"QFrame {{ background: {theme.CARD_BG}; border: 1px solid {theme.CARD_BORDER};"
        f" border-radius: 8px; }}"
        f"QFrame:hover {{ background: {theme.BG_HOVER}; }}"
    )


def _card_beat_style() -> str:
    return (
        f"QFrame {{ background: {theme.CARD_BEAT_BG}; border: 1px solid {theme.CARD_BORDER};"
        f" border-left: 3px solid {theme.CARD_BEAT_BORDER}; border-radius: 8px; }}"
        f"QFrame:hover {{ background: {theme.BG_HOVER}; }}"
    )


def _card_key_beat_style() -> str:
    return (
        f"QFrame {{ background: {theme.CARD_KEY_BEAT_BG}; border: 1px solid {theme.CARD_BORDER};"
        f" border-left: 3px solid {theme.CARD_KEY_BEAT_BORDER}; border-radius: 8px; }}"
        f"QFrame:hover {{ background: {theme.BG_HOVER}; }}"
    )


def _card_selected_style() -> str:
    return (
        f"QFrame {{ background: {theme.SELECTION_BG}; border: 1px solid {theme.ACCENT};"
        f" border-radius: 8px; }}"
    )

KEY_BEATS = {"Midpoint", "All Is Lost", "Finale", "Climax", "Break into Three"}

DRAG_THRESHOLD = 10

TITLE_MAX_CHARS = 60
SUMMARY_MAX_CHARS = 120
TAGS_MAX_CHARS = 50
CARD_MIN_HEIGHT = 88


def _truncate(text: str, limit: int) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "\u2026"


_GN_DENSITY_OPTS = ("silent", "light", "medium", "dense", "explosive")
_GN_REVEAL_OPTS = ("none", "page_turn", "cliffhanger", "splash_reveal")


class _GnTimelineMarker(QFrame):
    """A compact page marker in the GN reading-flow strip (\u00a73, \u00a75, \u00a76)."""

    def __init__(
        self, marker: dict, *, expanded: bool,
        on_toggle: Callable[[int], None],
        on_edit: Callable[[int, str], None],
    ) -> None:
        super().__init__()
        self._marker = marker
        self._page_id = marker["id"]
        self._on_toggle = on_toggle
        self._on_edit = on_edit
        self.setObjectName("gnTimelineMarker")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self._build(expanded)

    def _build(self, expanded: bool) -> None:
        m = self._marker
        col = QVBoxLayout(self)
        col.setContentsMargins(8, 5, 8, 5)
        col.setSpacing(2)

        top = QHBoxLayout()
        self._expand_btn = QPushButton("\u25be" if expanded else "\u25b8")
        self._expand_btn.setFixedWidth(22)
        self._expand_btn.clicked.connect(lambda: self._on_toggle(self._page_id))
        top.addWidget(self._expand_btn)

        num = QLabel(f"Page {m['page_number']}")
        num.setStyleSheet("font-weight: bold;")
        top.addWidget(num)

        for tag in (m.get("rhythm") or [])[:5]:
            chip = QLabel(tag)
            chip.setStyleSheet(
                "background: rgba(255,255,255,0.08); border-radius: 6px;"
                " padding: 0 5px; font-size: 9px;"
            )
            top.addWidget(chip)
        if m.get("is_page_turn"):
            pt = QLabel("\u27f3 page turn")
            pt.setStyleSheet("color: #eab308; font-size: 9px;")
            top.addWidget(pt)
        top.addStretch()

        menu_btn = QPushButton("\u22ef")
        menu_btn.setFixedWidth(22)
        menu_btn.clicked.connect(lambda: self._open_menu(menu_btn))
        top.addWidget(menu_btn)
        col.addLayout(top)

        meta_bits = [f"{m['panel_count']} panels"]
        if m["density"]:
            meta_bits.append(m["density"])
        if m["reveal_marker"]:
            meta_bits.append(f"reveal: {m['reveal_marker']}")
        meta = QLabel("  \u00b7  ".join(meta_bits))
        meta.setStyleSheet("color: #8a93a3; font-size: 10px;")
        col.addWidget(meta)

        summary = (m.get("summary") or "").strip()
        if summary:
            s = QLabel(_truncate(summary, 80))
            s.setStyleSheet("font-size: 11px;")
            s.setWordWrap(True)
            col.addWidget(s)

        chips = list(m.get("motif_markers") or []) + [
            f"@{c}" for c in (m.get("characters") or [])
        ]
        if chips:
            chip_lbl = QLabel(" ".join(f"\u00b7{c}" for c in chips[:8]))
            chip_lbl.setStyleSheet("color: #06b6d4; font-size: 9px;")
            chip_lbl.setWordWrap(True)
            col.addWidget(chip_lbl)

    def _open_menu(self, anchor) -> None:
        menu = QMenu(self)
        menu.addAction("Edit summary", lambda: self._on_edit(self._page_id, "summary"))
        menu.addAction("Edit emotional beat",
                       lambda: self._on_edit(self._page_id, "emotional_beat"))
        dens = menu.addMenu("Density")
        for opt in _GN_DENSITY_OPTS:
            dens.addAction(opt, lambda o=opt: self._on_edit(self._page_id, f"density:{o}"))
        rev = menu.addMenu("Reveal")
        for opt in _GN_REVEAL_OPTS:
            rev.addAction(opt, lambda o=opt: self._on_edit(self._page_id, f"reveal:{o}"))
        menu.addAction("Toggle splash page",
                       lambda: self._on_edit(self._page_id, "splash_page"))
        menu.exec(anchor.mapToGlobal(anchor.rect().bottomLeft()))


class _GnPanelMarker(QFrame):
    """A panel row shown under an expanded page marker (\u00a74)."""

    def __init__(self, panel: dict) -> None:
        super().__init__()
        self.setObjectName("gnPanelMarker")
        row = QHBoxLayout(self)
        row.setContentsMargins(34, 2, 8, 2)
        row.setSpacing(6)
        num = QLabel(f"P{panel['panel_number']}")
        num.setStyleSheet("color: #94a3b8; font-size: 10px;")
        row.addWidget(num)
        meta = " \u00b7 ".join(
            x for x in (panel.get("shot_type"), panel.get("camera_angle"),
                        panel.get("transition_type")) if x
        )
        if meta:
            lbl = QLabel(meta)
            lbl.setStyleSheet("color: #8a93a3; font-size: 9px;")
            row.addWidget(lbl)
        if panel.get("excerpt"):
            ex = QLabel(panel["excerpt"])
            ex.setStyleSheet("font-size: 10px;")
            row.addWidget(ex)
        badges = []
        if panel.get("has_dialogue"):
            badges.append("D")
        if panel.get("has_motifs"):
            badges.append("M")
        if panel.get("reading_priority"):
            badges.append(f"p{panel['reading_priority']}")
        if badges:
            b = QLabel(" ".join(badges))
            b.setStyleSheet("color: #8a93a3; font-size: 9px;")
            row.addWidget(b)
        row.addStretch()


class TimelineView(QWidget):
    def __init__(
        self,
        db: Database,
        project_id: int,
        on_scene_selected: Callable[[int], None] | None = None,
        on_data_changed: Callable[[], None] | None = None,
    ) -> None:
        super().__init__()
        self._db = db
        self._project_id = project_id
        self._on_scene_selected = on_scene_selected
        self._on_data_changed = on_data_changed

        project = self._db.get_project_by_id(self._project_id)
        from logosforge.project_compat import (
            get_project_narrative_engine,
            is_screenplay_project,
        )
        self._screenplay_mode = is_screenplay_project(project)
        _engine = get_project_narrative_engine(project)
        self._graphic_novel_mode = _engine == "graphic_novel"
        self._stage_script_mode = _engine == "stage_script"
        self._series_mode = _engine == "series"
        self._gn_expanded: set[int] = set()   # page ids expanded to panels

        # Scene data: (row, col) → (scene_id, title, plotline)
        self._cell_data: dict[tuple[int, int], tuple[int, str, str]] = {}
        self._selected_scene_id: int | None = None
        self._selected_card: QWidget | None = None

        # Cached plotline list (refreshed on each table load)
        self._plotline_values: list[str] = []

        # Drag state
        self._reset_drag_state()

        # Column-to-plotline mapping (rebuilt on each load)
        self._col_to_plotline: dict[int, str] = {}

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Timeline"))

        # -- Mode + filter row -----------------------------------------------
        controls_row = QHBoxLayout()

        controls_row.addWidget(QLabel("View"))
        self._mode_combo = QComboBox()
        self._mode_combo.addItem(MODE_BY_PLOTLINE)
        self._mode_combo.addItem(MODE_BY_CHAPTER)
        self._mode_combo.currentTextChanged.connect(self._on_mode_changed)
        controls_row.addWidget(self._mode_combo)

        self._filter_label = QLabel("Filter by Chapter")
        controls_row.addWidget(self._filter_label)
        self._filter_combo = QComboBox()
        self._filter_combo.currentTextChanged.connect(self._on_filter_changed)
        controls_row.addWidget(self._filter_combo)

        controls_row.addWidget(QLabel("Focus Character"))
        self._char_combo = QComboBox()
        self._char_combo.currentIndexChanged.connect(self._on_focus_char_changed)
        controls_row.addWidget(self._char_combo)

        controls_row.addStretch()
        layout.addLayout(controls_row)

        # -- Table -----------------------------------------------------------
        self._table = QTableWidget()
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self._table.verticalHeader().setVisible(False)
        self._table.setShowGrid(False)
        self._table.cellClicked.connect(self._on_cell_clicked)
        self._table.cellDoubleClicked.connect(self._on_double_click)
        self._table.viewport().installEventFilter(self)
        self._table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._on_cell_context_menu)
        layout.addWidget(self._table)

        # -- Status line -----------------------------------------------------
        self._status_label = QLabel("")
        layout.addWidget(self._status_label)

        # -- Actions ---------------------------------------------------------
        actions_row = QHBoxLayout()

        self._move_up_btn = QPushButton("Move Up")
        self._move_up_btn.setEnabled(False)
        self._move_up_btn.clicked.connect(self._on_move_up)
        actions_row.addWidget(self._move_up_btn)

        self._move_down_btn = QPushButton("Move Down")
        self._move_down_btn.setEnabled(False)
        self._move_down_btn.clicked.connect(self._on_move_down)
        actions_row.addWidget(self._move_down_btn)

        actions_row.addWidget(QLabel("Plotline:"))
        self._plotline_combo = QComboBox()
        self._plotline_combo.setEditable(True)
        self._plotline_combo.setEnabled(False)
        actions_row.addWidget(self._plotline_combo)

        self._set_plotline_btn = QPushButton("Set Plotline")
        self._set_plotline_btn.setEnabled(False)
        self._set_plotline_btn.clicked.connect(self._on_set_plotline)
        actions_row.addWidget(self._set_plotline_btn)

        actions_row.addStretch()
        layout.addLayout(actions_row)

        # Graphic Novel projects get a page/panel reading-flow strip instead
        # of the scene table.
        if self._graphic_novel_mode:
            self._build_gn_ui(layout)

        self._focus_char_id: int | None = None
        self._refresh_focus_characters()
        self._refresh_filter()
        self._reload()

    def _build_gn_ui(self, layout) -> None:
        from PySide6.QtWidgets import QScrollArea
        # Hide the scene-table affordances for GN projects.
        self._table.setVisible(False)
        self._status_label.setVisible(False)
        self._gn_scroll = QScrollArea()
        self._gn_scroll.setWidgetResizable(True)
        self._gn_scroll.setFrameShape(self._gn_scroll.Shape.NoFrame)
        self._gn_inner = QWidget()
        self._gn_layout = QVBoxLayout(self._gn_inner)
        self._gn_layout.setContentsMargins(8, 8, 8, 8)
        self._gn_layout.setSpacing(6)
        self._gn_scroll.setWidget(self._gn_inner)
        layout.addWidget(self._gn_scroll, stretch=1)

    # -- Graphic Novel timeline (page/panel-aware) --------------------------

    def is_graphic_novel_mode(self) -> bool:
        return self._graphic_novel_mode

    def get_gn_timeline_rows(self) -> list[dict]:
        """Reading-flow rows (rhythm / reveal timing / action density /
        pacing) for graphic-novel projects; [] otherwise."""
        if not self._graphic_novel_mode:
            return []
        from logosforge.graphic_novel_plot import get_gn_timeline
        return get_gn_timeline(self._db, self._project_id)

    def get_gn_silence_action_pattern(self) -> list[str]:
        if not self._graphic_novel_mode:
            return []
        from logosforge.graphic_novel_plot import get_silence_action_pattern
        return get_silence_action_pattern(self._db, self._project_id)

    def get_gn_page_turn_map(self) -> list[dict]:
        if not self._graphic_novel_mode:
            return []
        from logosforge.graphic_novel_plot import get_page_turn_map
        return get_page_turn_map(self._db, self._project_id)

    def get_gn_timeline_pages(self) -> list[dict]:
        """Rich page markers (reading order) for the GN timeline; [] otherwise."""
        if not self._graphic_novel_mode:
            return []
        from logosforge.graphic_novel_plot import get_gn_timeline_pages
        return get_gn_timeline_pages(self._db, self._project_id)

    def get_gn_panel_markers(self, page_id: int) -> list[dict]:
        """Panel markers for one page (lazy expansion); [] otherwise."""
        if not self._graphic_novel_mode:
            return []
        from logosforge.graphic_novel_plot import get_gn_panel_markers
        return get_gn_panel_markers(self._db, page_id)

    def is_page_expanded(self, page_id: int) -> bool:
        return page_id in self._gn_expanded

    def toggle_page_expand(self, page_id: int) -> None:
        if page_id in self._gn_expanded:
            self._gn_expanded.discard(page_id)
        else:
            self._gn_expanded.add(page_id)
        if self._graphic_novel_mode:
            self._refresh_gn()

    def gn_update_page(self, page_id: int, **fields) -> None:
        """Persist a page edit from the Timeline via the shared GN service
        (§9, §10). Same data source as Pages View / Canvas / Plot."""
        if not self._graphic_novel_mode:
            return
        self._db.update_gn_page(page_id, **fields)
        self._refresh_gn()
        self._emit_gn_changed()

    def _emit_gn_changed(self) -> None:
        try:
            from logosforge.project_events import get_event_bus
            bus = get_event_bus()
            bus.plot_changed.emit()
            bus.project_data_changed.emit()
        except Exception:
            pass
        if self._on_data_changed:
            self._on_data_changed()

    # -- Stage Script timeline (theatre-aware) ------------------------------

    def is_stage_script_mode(self) -> bool:
        return self._stage_script_mode

    def get_stage_timeline_rows(self) -> list[dict]:
        """Performance-order rows (entrances/exits, cues, offstage events,
        prop continuity, emotional pressure). [] for non-stage projects."""
        if not self._stage_script_mode:
            return []
        from logosforge.stage_script_plot import get_stage_timeline
        return get_stage_timeline(self._db, self._project_id)

    def get_stage_act_progression(self) -> list[str]:
        if not self._stage_script_mode:
            return []
        from logosforge.stage_script_plot import get_act_progression
        return get_act_progression(self._db, self._project_id)

    def get_stage_entrance_exit_markers(self, scene_id: int) -> list[dict]:
        if not self._stage_script_mode:
            return []
        from logosforge.stage_script_plot import get_entrance_exit_markers
        return get_entrance_exit_markers(self._db, self._project_id, scene_id)

    def get_stage_cue_markers(self, scene_id: int) -> list[dict]:
        if not self._stage_script_mode:
            return []
        from logosforge.stage_script_plot import get_cue_markers
        return get_cue_markers(self._db, scene_id)

    # -- Series timeline (season/episode-aware) -----------------------------

    def is_series_mode(self) -> bool:
        return self._series_mode

    def get_series_timeline_rows(self) -> list[dict]:
        """Episode-order rows (season, active arcs, setup/payoff,
        cliffhanger). [] for non-series projects."""
        if not self._series_mode:
            return []
        from logosforge.series_plot import get_series_timeline
        return get_series_timeline(self._db, self._project_id)

    def get_series_season_progression(self) -> list[str]:
        if not self._series_mode:
            return []
        from logosforge.series_plot import get_season_progression
        return get_season_progression(self._db, self._project_id)

    def get_series_setup_payoff_chains(self) -> list[dict]:
        if not self._series_mode:
            return []
        from logosforge.series_plot import get_setup_payoff_chains
        return get_setup_payoff_chains(self._db, self._project_id)

    # -- Focus character -----------------------------------------------------

    def _refresh_focus_characters(self) -> None:
        self._char_combo.blockSignals(True)
        self._char_combo.clear()
        self._char_combo.addItem("None", None)
        for char in self._db.get_all_characters(self._project_id):
            self._char_combo.addItem(char.name, char.id)
        self._char_combo.blockSignals(False)

    def _on_focus_char_changed(self, index: int) -> None:
        self._focus_char_id = self._char_combo.currentData()
        self._reload()

    # -- Mode ----------------------------------------------------------------

    def _get_mode(self) -> str:
        return self._mode_combo.currentText()

    def _on_mode_changed(self) -> None:
        self._refresh_filter()
        self._reload()

    # -- Filter --------------------------------------------------------------

    def _is_filtered(self) -> bool:
        return self._filter_combo.currentText() != FILTER_ALL

    def _refresh_filter(self) -> None:
        if self._get_mode() == MODE_BY_PLOTLINE:
            self._filter_label.setText("Filter by Chapter")
            values = self._db.get_scene_chapters(self._project_id)
        else:
            self._filter_label.setText("Filter by Plotline")
            values = self._db.get_scene_plotlines(self._project_id)

        combo = self._filter_combo
        combo.blockSignals(True)
        current = combo.currentText()
        combo.clear()
        combo.addItem(FILTER_ALL)
        for val in values:
            combo.addItem(val)
        idx = combo.findText(current)
        combo.setCurrentIndex(idx if idx >= 0 else 0)
        combo.blockSignals(False)

    def _get_filter_kwargs(self) -> dict[str, str | None]:
        text = self._filter_combo.currentText()
        value = None if text == FILTER_ALL else text
        if self._get_mode() == MODE_BY_PLOTLINE:
            return {"chapter": value}
        else:
            return {"plotline": value}

    def _on_filter_changed(self) -> None:
        self._reload()

    # -- Reload (single entry point) -----------------------------------------

    def refresh(self) -> None:
        self._reload()

    def _reload(self) -> None:
        if self._graphic_novel_mode:
            self._refresh_gn()
            return
        self._selected_card = None
        self._load_table()
        self._reselect()

    # -- Graphic Novel reading-flow strip -----------------------------------

    def _refresh_gn(self) -> None:
        while self._gn_layout.count():
            item = self._gn_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        markers = self.get_gn_timeline_pages()
        if not markers:
            empty = QLabel(
                "No graphic-novel pages yet.\n"
                "Add pages in the Pages view to see the reading flow here."
            )
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._gn_layout.addWidget(empty)
            return

        last_issue = object()
        for marker in markers:
            issue = marker.get("issue_title") or ""
            if issue != last_issue:
                last_issue = issue
                if issue:
                    hdr = QLabel(issue)
                    hdr.setStyleSheet("font-weight: bold; margin-top: 4px;")
                    self._gn_layout.addWidget(hdr)
            card = _GnTimelineMarker(
                marker,
                expanded=marker["id"] in self._gn_expanded,
                on_toggle=self.toggle_page_expand,
                on_edit=self._gn_edit_page,
            )
            self._gn_layout.addWidget(card)
            if marker["id"] in self._gn_expanded:
                for pm in self.get_gn_panel_markers(marker["id"]):
                    self._gn_layout.addWidget(_GnPanelMarker(pm))
        self._gn_layout.addStretch()

    def _gn_edit_page(self, page_id: int, field: str) -> None:
        page = self._db.get_gn_page_by_id(page_id)
        if page is None:
            return
        if field in ("summary", "emotional_beat"):
            current = getattr(page, field, "") or ""
            text, ok = QInputDialog.getMultiLineText(
                self, "Edit Page", field.replace("_", " ").title(), current,
            )
            if ok:
                self.gn_update_page(page_id, **{field: text.strip()})
        elif field == "splash_page":
            self.gn_update_page(page_id, splash_page=not page.splash_page)
        elif field.startswith("density:"):
            self.gn_update_page(page_id, density_level=field.split(":", 1)[1])
        elif field.startswith("reveal:"):
            self.gn_update_page(page_id, reveal_type=field.split(":", 1)[1])

    def _load_table(self) -> None:
        scenes = self._db.get_all_scenes(
            self._project_id,
            **self._get_filter_kwargs(),
        )

        # Cache plotline values once per table load
        self._plotline_values = self._db.get_scene_plotlines(self._project_id)

        mode = self._get_mode()
        if mode == MODE_BY_PLOTLINE:
            columns = self._build_columns(scenes, key=lambda s: s.plotline)
            prefix = "Plotline"
        else:
            columns = self._build_columns(scenes, key=lambda s: s.chapter)
            prefix = "Chapter"

        col_to_idx = {name: i for i, name in enumerate(columns)}

        self._col_to_plotline.clear()
        if mode == MODE_BY_PLOTLINE:
            for name, idx in col_to_idx.items():
                self._col_to_plotline[idx] = "" if name == UNASSIGNED else name

        self._table.blockSignals(True)
        self._table.setRowCount(0)
        self._table.setColumnCount(max(len(columns), 1))

        if columns:
            headers = [f"{prefix}: {c}" for c in columns]
        else:
            headers = [f"{prefix}: {UNASSIGNED}"]
        self._table.setHorizontalHeaderLabels(headers)
        self._table.setRowCount(len(scenes))
        self._cell_data.clear()

        # Pre-fetch character states for focus character
        scene_state: dict[int, str] = {}
        if self._focus_char_id is not None:
            for scene in scenes:
                for cid, state in self._db.get_scene_character_states(scene.id):
                    if cid == self._focus_char_id:
                        scene_state[scene.id] = state
                        break

        for row, scene in enumerate(scenes):
            if mode == MODE_BY_PLOTLINE:
                col_name = scene.plotline if scene.plotline else UNASSIGNED
            else:
                col_name = scene.chapter if scene.chapter else UNASSIGNED
            col = col_to_idx[col_name]

            char_state = scene_state.get(scene.id, "")
            card = self._create_card(row + 1, scene, mode, char_state)
            self._table.setCellWidget(row, col, card)
            self._table.setRowHeight(row, max(card.sizeHint().height(), CARD_MIN_HEIGHT))
            self._cell_data[(row, col)] = (scene.id, scene.title, scene.plotline)

        header = self._table.horizontalHeader()
        for i in range(self._table.columnCount()):
            header.setSectionResizeMode(i, QHeaderView.ResizeMode.Stretch)

        self._table.blockSignals(False)
        self._update_status_count()

    def _update_status_count(self) -> None:
        count = len(self._cell_data)
        filter_text = self._filter_combo.currentText()
        is_filtered = filter_text != FILTER_ALL

        if count == 0 and is_filtered:
            self._status_label.setText(
                f'No scenes match filter "{filter_text}".'
            )
        elif count == 0:
            self._status_label.setText("No scenes to display.")
        elif is_filtered:
            self._status_label.setText(
                f"{count} scene(s) shown (filtered by {filter_text})."
            )
        else:
            self._status_label.setText(f"{count} scene(s).")

    def _build_columns(self, scenes: list, key: Callable) -> list[str]:
        columns: list[str] = []
        seen: set[str] = set()
        has_unassigned = False
        for scene in scenes:
            value = key(scene)
            if not value:
                has_unassigned = True
            elif value not in seen:
                seen.add(value)
                columns.append(value)
        if has_unassigned:
            columns.append(UNASSIGNED)
        return columns

    def _create_card(self, index: int, scene, mode: str, char_state: str = "") -> QFrame:
        card = QFrame()
        card.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        if scene.beat and scene.beat in KEY_BEATS:
            base_style = _card_key_beat_style()
        elif scene.beat:
            base_style = _card_beat_style()
        else:
            base_style = _card_style()
        color = color_hex(getattr(scene, "color_label", "") or "")
        if color:
            base_style += (
                f"\nQFrame {{ border-left: 4px solid {color}; }}"
            )
        card.setStyleSheet(base_style)
        card.setProperty("base_style", base_style)

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 12, 16, 12)
        card_layout.setSpacing(6)

        title_label = QLabel(_truncate(scene.title, TITLE_MAX_CHARS))
        title_font = QFont()
        title_font.setBold(True)
        title_font.setPointSize(title_font.pointSize() + 1)
        title_label.setFont(title_font)
        title_label.setWordWrap(True)
        title_label.setStyleSheet(f"color: {theme.TEXT_PRIMARY};")
        card_layout.addWidget(title_label)

        summary_text = scene.summary or scene.synopsis or ""
        if summary_text:
            summary_label = QLabel(_truncate(summary_text, SUMMARY_MAX_CHARS))
            summary_label.setWordWrap(True)
            summary_label.setStyleSheet(
                f"color: {theme.TEXT_PRIMARY}; font-size: 12px;"
            )
            card_layout.addWidget(summary_label)

        meta_parts = [f"#{index}"]
        if scene.act:
            meta_parts.append(scene.act)
        if mode == MODE_BY_PLOTLINE and scene.chapter:
            meta_parts.append(scene.chapter)
        elif mode == MODE_BY_CHAPTER and scene.plotline:
            meta_parts.append(scene.plotline)
        if scene.beat:
            meta_parts.append(scene.beat)
        if scene.tags:
            meta_parts.append(_truncate(scene.tags, TAGS_MAX_CHARS))

        meta_label = QLabel(" \u00b7 ".join(meta_parts))
        meta_label.setStyleSheet(
            f"color: {theme.TEXT_SECONDARY}; font-size: 11px;"
        )
        meta_label.setWordWrap(True)
        card_layout.addWidget(meta_label)

        if char_state:
            state_label = QLabel(f"\u2192 {char_state}")
            state_label.setStyleSheet(
                f"color: {theme.LINK_COLOR}; font-size: 11px; font-style: italic;"
            )
            state_label.setWordWrap(True)
            card_layout.addWidget(state_label)

        if self._screenplay_mode:
            sp_parts: list[str] = []
            duration = getattr(scene, "estimated_duration_minutes", 0) or 0
            if duration:
                sp_parts.append(f"{duration}m")
            location = getattr(scene, "location", "") or ""
            if location:
                sp_parts.append(_truncate(location, 20))
            ie = getattr(scene, "interior_exterior", "") or ""
            tod = getattr(scene, "time_of_day", "") or ""
            if ie or tod:
                sp_parts.append(f"{ie}/{tod}" if ie and tod else (ie or tod))
            if sp_parts:
                sp_label = QLabel(" \u00b7 ".join(sp_parts))
                sp_label.setStyleSheet(
                    f"color: {theme.TEXT_MUTED}; font-size: 10px;"
                )
                card_layout.addWidget(sp_label)

            dramatic_turn = getattr(scene, "dramatic_turn", "") or ""
            if dramatic_turn:
                dt_label = QLabel(f"\u21bb {_truncate(dramatic_turn, 40)}")
                dt_label.setStyleSheet(
                    f"color: {theme.TEXT_SECONDARY}; font-size: 10px; font-style: italic;"
                )
                dt_label.setWordWrap(True)
                card_layout.addWidget(dt_label)

            setup_payoff = getattr(scene, "setup_payoff_links", "") or ""
            if setup_payoff:
                sp_link_label = QLabel(f"\u2693 {_truncate(setup_payoff, 40)}")
                sp_link_label.setStyleSheet(
                    f"color: {theme.ACCENT_DIM}; font-size: 10px;"
                )
                sp_link_label.setWordWrap(True)
                card_layout.addWidget(sp_link_label)

        return card

    # -- Drag-and-drop reordering --------------------------------------------

    def _reset_drag_state(self) -> None:
        self._drag_start_row: int | None = None
        self._drag_start_col: int | None = None
        self._drag_start_pos: QPoint | None = None
        self._drag_scene_id: int | None = None
        self._dragging = False

    def eventFilter(self, obj: object, event: QEvent) -> bool:
        if obj is not self._table.viewport():
            return super().eventFilter(obj, event)

        if event.type() == QEvent.Type.MouseButtonPress:
            return self._on_drag_press(event)

        if event.type() == QEvent.Type.MouseMove:
            return self._on_drag_move(event)

        if event.type() == QEvent.Type.MouseButtonRelease:
            return self._on_drag_release(event)

        return super().eventFilter(obj, event)

    def _on_drag_press(self, event) -> bool:
        if event.button() != Qt.MouseButton.LeftButton:
            return False

        self._reset_drag_state()

        if self._is_filtered():
            return False

        pos = event.position().toPoint()
        row = self._table.rowAt(pos.y())
        col = self._table.columnAt(pos.x())
        cell_data = self._cell_data.get((row, col))

        if cell_data is not None:
            self._drag_start_row = row
            self._drag_start_col = col
            self._drag_start_pos = pos
            self._drag_scene_id = cell_data[0]

        return False

    def _on_drag_move(self, event) -> bool:
        if self._drag_start_pos is None:
            return False

        if not self._dragging:
            distance = (
                event.position().toPoint() - self._drag_start_pos
            ).manhattanLength()
            if distance > DRAG_THRESHOLD:
                self._dragging = True
                self._table.setCursor(Qt.CursorShape.ClosedHandCursor)

        return False

    def _on_drag_release(self, event) -> bool:
        was_dragging = self._dragging
        drag_scene = self._drag_scene_id
        start_row = self._drag_start_row
        start_col = self._drag_start_col

        self._reset_drag_state()

        if not was_dragging or drag_scene is None:
            return False
        if start_row is None or start_col is None:
            return False

        self._table.unsetCursor()

        pos = event.position().toPoint()
        target_row = self._table.rowAt(pos.y())
        target_col = self._table.columnAt(pos.x())

        if target_row < 0 or target_col < 0:
            return True

        row_changed = target_row != start_row
        col_changed = target_col != start_col

        if not row_changed and not col_changed:
            return True

        self._selected_scene_id = drag_scene

        if col_changed and target_col in self._col_to_plotline:
            new_plotline = self._col_to_plotline[target_col]
            self._db.update_scene_plotline(drag_scene, new_plotline)

        if row_changed:
            self._db.reorder_scene(drag_scene, target_row)

        self._reload()
        if self._on_data_changed:
            self._on_data_changed()
        return True

    # -- Selection -----------------------------------------------------------

    def _on_cell_clicked(self, row: int, col: int) -> None:
        cell_data = self._cell_data.get((row, col))
        scene_id = cell_data[0] if cell_data else None
        self._apply_selection(scene_id)

    def _on_cell_context_menu(self, pos: QPoint) -> None:
        index = self._table.indexAt(pos)
        if not index.isValid():
            return
        row, col = index.row(), index.column()
        cell_data = self._cell_data.get((row, col))
        if not cell_data:
            return
        scene_id = cell_data[0]
        scene = self._db.get_scene_by_id(scene_id)
        if scene is None:
            return
        self._apply_selection(scene_id)

        menu = QMenu(self._table)
        build_color_menu(
            menu, getattr(scene, "color_label", "") or "",
            lambda key, sid=scene_id: self._set_scene_color(sid, key),
        )
        menu.exec(self._table.viewport().mapToGlobal(pos))

    def _set_scene_color(self, scene_id: int, color_label: str) -> None:
        self._db.update_scene_color(scene_id, color_label)
        if self._on_data_changed:
            self._on_data_changed()
        else:
            self._reload()

    def _apply_selection(self, scene_id: int | None) -> None:
        self._selected_scene_id = scene_id
        has_scene = scene_id is not None
        self._set_actions_enabled(has_scene)

        if self._selected_card is not None:
            restore = self._selected_card.property("base_style") or _card_style()
            self._selected_card.setStyleSheet(restore)
            self._selected_card = None

        if has_scene:
            cell = self._find_scene_cell(scene_id)
            if cell is not None:
                _, title, plotline = self._cell_data[cell]
                self._sync_plotline_combo(plotline)
                self._status_label.setText(f"Selected: {title}")
                card = self._table.cellWidget(cell[0], cell[1])
                if card:
                    card.setStyleSheet(_card_selected_style())
                    self._selected_card = card
            else:
                self._selected_scene_id = None
                self._set_actions_enabled(False)
                self._clear_plotline_combo()
                self._update_status_count()
        else:
            self._clear_plotline_combo()
            self._table.setCurrentCell(-1, -1)
            self._update_status_count()

    def _find_scene_cell(self, scene_id: int) -> tuple[int, int] | None:
        for cell, data in self._cell_data.items():
            if data[0] == scene_id:
                return cell
        return None

    def _reselect(self) -> None:
        if self._selected_scene_id is None:
            self._apply_selection(None)
            return

        cell = self._find_scene_cell(self._selected_scene_id)
        if cell is not None:
            self._table.setCurrentCell(cell[0], cell[1])
            self._apply_selection(self._selected_scene_id)
        else:
            self._apply_selection(None)

    def _set_actions_enabled(self, enabled: bool) -> None:
        self._move_up_btn.setEnabled(enabled)
        self._move_down_btn.setEnabled(enabled)
        self._plotline_combo.setEnabled(enabled)
        self._set_plotline_btn.setEnabled(enabled)

    def _sync_plotline_combo(self, current_plotline: str) -> None:
        combo = self._plotline_combo
        combo.blockSignals(True)
        combo.clear()
        combo.addItem("")
        for pl in self._plotline_values:
            combo.addItem(pl)
        idx = combo.findText(current_plotline)
        if idx >= 0:
            combo.setCurrentIndex(idx)
        else:
            combo.setCurrentText(current_plotline)
        combo.blockSignals(False)

    def _clear_plotline_combo(self) -> None:
        combo = self._plotline_combo
        combo.blockSignals(True)
        combo.clear()
        combo.blockSignals(False)

    # -- Actions -------------------------------------------------------------

    def _on_move_up(self) -> None:
        if self._selected_scene_id is None:
            return
        self._db.move_scene_up(self._selected_scene_id)
        self._reload()
        if self._on_data_changed:
            self._on_data_changed()

    def _on_move_down(self) -> None:
        if self._selected_scene_id is None:
            return
        self._db.move_scene_down(self._selected_scene_id)
        self._reload()
        if self._on_data_changed:
            self._on_data_changed()

    def _on_set_plotline(self) -> None:
        if self._selected_scene_id is None:
            return
        plotline = self._plotline_combo.currentText().strip()
        self._db.update_scene_plotline(self._selected_scene_id, plotline)
        self._reload()
        if self._on_data_changed:
            self._on_data_changed()

    # -- Navigation ----------------------------------------------------------

    def _on_double_click(self, row: int, column: int) -> None:
        if self._on_scene_selected is None:
            return
        cell_data = self._cell_data.get((row, column))
        if cell_data is not None:
            self._on_scene_selected(cell_data[0])
