"""Multi-View Plotting — dynamic story perspectives.

Container widget that offers four view modes (Grid, Timeline, Arc, Character)
over the same story data, with unified filtering by character/tag/plotline.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from logosforge.db import Database
from logosforge.ui import theme
from logosforge.ui.color_labels import build_color_menu, color_hex
from logosforge.ui.story_grid_view import StoryGridView


@dataclass
class PlotFilters:
    """Active filter state for all plot views."""

    character_id: int | None = None
    tag: str = ""
    plotline: str = ""


# =============================================================================
# Shared context-menu behaviour for scene cards
# =============================================================================

class _SceneCardContextMixin:
    """Mixin providing context-menu actions for scene cards.

    Requires the host class to have ``_db``, ``_on_data_changed``, and
    ``_on_open_scene`` attributes.
    """

    def _setup_card_context(self, card: QFrame, scene_id: int) -> None:
        card.setProperty("scene_id", scene_id)
        card.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        card.customContextMenuRequested.connect(
            lambda pos, c=card: self._on_card_context(c, pos),
        )
        card.setCursor(Qt.CursorShape.PointingHandCursor)

    def _apply_card_color(self, card: QFrame, color_label: str | None) -> None:
        """Apply a subtle left-border strip + dot to indicate the scene color."""
        hex_color = color_hex(color_label)
        if hex_color:
            card.setStyleSheet(
                f"QFrame {{ border-left: 4px solid {hex_color}; }}"
            )
        else:
            card.setStyleSheet("")
        card.setProperty("color_label", color_label or "")

    def _on_card_context(self, card: QFrame, pos) -> None:
        scene_id = card.property("scene_id")
        scene = self._db.get_scene_by_id(scene_id)
        if scene is None:
            return
        menu = QMenu(card)

        if self._on_open_scene is not None:
            open_act = QAction("Open in Manuscript", menu)
            open_act.triggered.connect(lambda: self._on_open_scene(scene_id))
            menu.addAction(open_act)

        edit_title = QAction("Edit Title", menu)
        edit_title.triggered.connect(lambda: self._edit_title(scene_id))
        menu.addAction(edit_title)

        edit_summary = QAction("Edit Summary", menu)
        edit_summary.triggered.connect(lambda: self._edit_summary(scene_id))
        menu.addAction(edit_summary)

        all_scenes = self._db.get_all_scenes(self._project_id)
        acts = sorted({(s.act or "").strip() for s in all_scenes} - {""})
        if acts:
            move_menu = QMenu("Move to Act", menu)
            for act in acts:
                if act != (scene.act or "").strip():
                    act_action = QAction(act, move_menu)
                    act_action.triggered.connect(
                        lambda _, a=act, sid=scene_id: self._move_to_act(sid, a),
                    )
                    move_menu.addAction(act_action)
            if move_menu.actions():
                menu.addMenu(move_menu)

        build_color_menu(
            menu, scene.color_label,
            lambda key, sid=scene_id: self._set_color(sid, key),
        )

        delete_act = QAction("Delete", menu)
        delete_act.triggered.connect(lambda: self._delete_scene(scene_id))
        menu.addAction(delete_act)

        menu.exec(card.mapToGlobal(pos))

    def _set_color(self, scene_id: int, color_label: str) -> None:
        self._db.update_scene_color(scene_id, color_label)
        if self._on_data_changed:
            self._on_data_changed()

    def _edit_title(self, scene_id: int) -> None:
        scene = self._db.get_scene_by_id(scene_id)
        if scene is None:
            return
        new_title, ok = QInputDialog.getText(self, "Edit Title", "Title:", text=scene.title)
        if not ok or not new_title.strip():
            return
        self._db.update_scene(
            scene_id=scene.id, title=new_title.strip(),
            summary=scene.summary, synopsis=scene.synopsis,
            goal=scene.goal, conflict=scene.conflict, outcome=scene.outcome,
            beat=scene.beat, tags=scene.tags, act=scene.act,
            content=scene.content, chapter=scene.chapter, plotline=scene.plotline,
        )
        if self._on_data_changed:
            self._on_data_changed()

    def _edit_summary(self, scene_id: int) -> None:
        scene = self._db.get_scene_by_id(scene_id)
        if scene is None:
            return
        new_summary, ok = QInputDialog.getMultiLineText(
            self, "Edit Summary", "Summary:", scene.summary or "",
        )
        if not ok:
            return
        self._db.update_scene_summary(scene_id, new_summary.strip())
        if self._on_data_changed:
            self._on_data_changed()

    def _move_to_act(self, scene_id: int, target_act: str) -> None:
        scene = self._db.get_scene_by_id(scene_id)
        if scene is None:
            return
        self._db.update_scene(
            scene_id=scene.id, title=scene.title,
            summary=scene.summary, synopsis=scene.synopsis,
            goal=scene.goal, conflict=scene.conflict, outcome=scene.outcome,
            beat=scene.beat, tags=scene.tags, act=target_act,
            content=scene.content, chapter=scene.chapter, plotline=scene.plotline,
        )
        if self._on_data_changed:
            self._on_data_changed()

    def _delete_scene(self, scene_id: int) -> None:
        scene = self._db.get_scene_by_id(scene_id)
        if scene is None:
            return
        confirm = QMessageBox.question(
            self, "Delete Scene",
            f"Delete scene '{scene.title}'?\nThis cannot be undone.",
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        self._db.delete_scene(scene_id)
        if self._on_data_changed:
            self._on_data_changed()


# =============================================================================
# Timeline Strip — horizontal left-to-right scene flow
# =============================================================================

class _TimelineStrip(_SceneCardContextMixin, QWidget):
    """Horizontal timeline: scenes as cards flowing left to right."""

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
        self._filters: PlotFilters | None = None

        project = self._db.get_project_by_id(self._project_id)
        from logosforge.project_compat import is_screenplay_project
        self._screenplay_mode = is_screenplay_project(project)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Phase 9B — surface the active project writing mode + structural
        # vocabulary (read fresh at construction; the view is rebuilt on
        # project switch, so no stale mode). Read-only reflection of
        # Project.narrative_engine — never a second source of truth.
        try:
            from logosforge.writing_modes import (
                get_project_writing_mode,
                mode_label,
                structural_vocabulary,
            )
            _mode = get_project_writing_mode(project)
            self._mode_label = QLabel(
                f"Mode: {mode_label(_mode)}  ·  {structural_vocabulary(_mode)}"
            )
            self._mode_label.setObjectName("plotModeChip")
            self._mode_label.setContentsMargins(16, 8, 16, 0)
            outer.addWidget(self._mode_label)
        except Exception:
            pass

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setObjectName("timelineScroll")
        outer.addWidget(self._scroll)

        self._container = QWidget()
        self._container.setObjectName("timelineContainer")
        self._layout = QHBoxLayout(self._container)
        self._layout.setContentsMargins(16, 16, 16, 16)
        self._layout.setSpacing(0)
        self._layout.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self._scroll.setWidget(self._container)

        self._cards: list[QFrame] = []

    def refresh(self, filters: PlotFilters | None = None) -> None:
        self._filters = filters
        self._clear()
        scenes = self._filtered_scenes(filters)

        current_group = None
        for scene in scenes:
            group = (scene.act or scene.chapter or "").strip()
            if group and group != current_group:
                current_group = group
                self._add_group_header(group)

            self._add_scene_card(scene)

        if not scenes:
            self._add_empty()

        self._layout.addStretch()

    def _filtered_scenes(self, filters: PlotFilters | None):
        scenes = self._db.get_all_scenes(self._project_id)
        if not filters:
            return scenes
        return _apply_filters(self._db, scenes, filters)

    def _clear(self) -> None:
        self._cards.clear()
        while self._layout.count():
            item = self._layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

    def _add_group_header(self, text: str) -> None:
        header = QLabel(text)
        header.setObjectName("timelineGroupHeader")
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._layout.addWidget(header)
        self._layout.addSpacing(8)

    def _add_scene_card(self, scene) -> None:
        card = QFrame()
        card.setObjectName("timelineCard")
        card.setFixedWidth(160)
        card.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Minimum)
        self._setup_card_context(card, scene.id)
        self._apply_card_color(card, scene.color_label)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(2)

        title = QLabel(scene.title or "Untitled")
        title.setObjectName("timelineCardTitle")
        title.setWordWrap(True)
        layout.addWidget(title)

        summary = scene.summary or scene.synopsis or ""
        if summary:
            if len(summary) > 60:
                summary = summary[:57] + "..."
            lbl = QLabel(summary)
            lbl.setObjectName("timelineCardSummary")
            lbl.setWordWrap(True)
            layout.addWidget(lbl)

        if self._screenplay_mode:
            sp_parts: list[str] = []
            duration = getattr(scene, "estimated_duration_minutes", 0) or 0
            if duration:
                sp_parts.append(f"{duration}m")
            location = getattr(scene, "location", "") or ""
            if location:
                sp_parts.append(location[:15])
            ie = getattr(scene, "interior_exterior", "") or ""
            tod = getattr(scene, "time_of_day", "") or ""
            if ie or tod:
                sp_parts.append(f"{ie}/{tod}" if ie and tod else (ie or tod))
            if sp_parts:
                sp_lbl = QLabel(" · ".join(sp_parts))
                sp_lbl.setObjectName("timelineCardMeta")
                sp_lbl.setStyleSheet(
                    f"color: {theme.TEXT_MUTED}; font-size: 10px;"
                )
                layout.addWidget(sp_lbl)

            emotional_turn = getattr(scene, "emotional_turn", "") or ""
            if emotional_turn:
                et_short = emotional_turn[:25] + "..." if len(emotional_turn) > 25 else emotional_turn
                et_lbl = QLabel(f"↻ {et_short}")
                et_lbl.setObjectName("timelineCardTurn")
                et_lbl.setStyleSheet(
                    f"color: {theme.ACCENT_DIM}; font-size: 10px; font-style: italic;"
                )
                layout.addWidget(et_lbl)

            montage = getattr(scene, "montage_group", "") or ""
            if montage:
                mg_lbl = QLabel(f"▸ {montage}")
                mg_lbl.setObjectName("timelineCardMontage")
                mg_lbl.setStyleSheet(
                    f"color: {theme.TEXT_SECONDARY}; font-size: 10px;"
                )
                layout.addWidget(mg_lbl)

        self._layout.addWidget(card)
        self._layout.addSpacing(4)
        self._cards.append(card)

    def _add_empty(self) -> None:
        lbl = QLabel("No scenes match the current filters.")
        lbl.setObjectName("timelineEmpty")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._layout.addWidget(lbl)

    def card_count(self) -> int:
        return len(self._cards)


# =============================================================================
# Arc Lanes — one row per plotline
# =============================================================================

class _ArcLanes(_SceneCardContextMixin, QWidget):
    """Arc view: one horizontal lane per plotline."""

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
        self._filters: PlotFilters | None = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setObjectName("arcScroll")
        outer.addWidget(self._scroll)

        self._container = QWidget()
        self._container.setObjectName("arcContainer")
        self._lanes_layout = QVBoxLayout(self._container)
        self._lanes_layout.setContentsMargins(16, 16, 16, 16)
        self._lanes_layout.setSpacing(12)
        self._scroll.setWidget(self._container)

        self._lane_count = 0

    def refresh(self, filters: PlotFilters | None = None) -> None:
        self._filters = filters
        self._clear()
        scenes = self._filtered_scenes(filters)

        arcs: dict[str, list] = {}
        for scene in scenes:
            plotline = (scene.plotline or "").strip()
            if not plotline:
                plotline = "Unassigned"
            arcs.setdefault(plotline, []).append(scene)

        if not arcs:
            self._add_empty()
            return

        for arc_name in sorted(arcs.keys(), key=lambda k: (k == "Unassigned", k)):
            self._add_lane(arc_name, arcs[arc_name])

    def _filtered_scenes(self, filters: PlotFilters | None):
        scenes = self._db.get_all_scenes(self._project_id)
        if not filters:
            return scenes
        return _apply_filters(self._db, scenes, filters)

    def _clear(self) -> None:
        self._lane_count = 0
        while self._lanes_layout.count():
            item = self._lanes_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

    def _add_lane(self, arc_name: str, scenes: list) -> None:
        lane = QFrame()
        lane.setObjectName("arcLane")
        lane_layout = QVBoxLayout(lane)
        lane_layout.setContentsMargins(8, 6, 8, 6)
        lane_layout.setSpacing(4)

        header = QLabel(arc_name)
        header.setObjectName("arcLaneHeader")
        lane_layout.addWidget(header)

        cards_row = QHBoxLayout()
        cards_row.setSpacing(6)
        for scene in scenes:
            card = self._make_card(scene)
            cards_row.addWidget(card)
        cards_row.addStretch()
        lane_layout.addLayout(cards_row)

        self._lanes_layout.addWidget(lane)
        self._lane_count += 1

    def _make_card(self, scene) -> QFrame:
        card = QFrame()
        card.setObjectName("arcCard")
        card.setFixedWidth(140)
        self._setup_card_context(card, scene.id)
        self._apply_card_color(card, scene.color_label)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(2)

        title = QLabel(scene.title or "Untitled")
        title.setObjectName("arcCardTitle")
        title.setWordWrap(True)
        layout.addWidget(title)

        if scene.beat:
            beat = QLabel(scene.beat)
            beat.setObjectName("arcCardBeat")
            layout.addWidget(beat)

        return card

    def _add_empty(self) -> None:
        lbl = QLabel("No arcs found. Assign plotlines to scenes.")
        lbl.setObjectName("arcEmpty")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lanes_layout.addWidget(lbl)

    def lane_count(self) -> int:
        return self._lane_count


# =============================================================================
# Character Lanes — one row per character
# =============================================================================

class _CharLanes(_SceneCardContextMixin, QWidget):
    """Character view: one horizontal lane per character."""

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
        self._filters: PlotFilters | None = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setObjectName("charScroll")
        outer.addWidget(self._scroll)

        self._container = QWidget()
        self._container.setObjectName("charContainer")
        self._lanes_layout = QVBoxLayout(self._container)
        self._lanes_layout.setContentsMargins(16, 16, 16, 16)
        self._lanes_layout.setSpacing(12)
        self._scroll.setWidget(self._container)

        self._lane_count = 0

    def refresh(self, filters: PlotFilters | None = None) -> None:
        self._filters = filters
        self._clear()
        scenes = self._filtered_scenes(filters)
        characters = self._db.get_all_characters(self._project_id)

        char_scenes: dict[int, list] = {c.id: [] for c in characters}
        for scene in scenes:
            char_ids = self._db.get_scene_character_ids(scene.id)
            for cid in char_ids:
                if cid in char_scenes:
                    char_scenes[cid].append(scene)

        if not any(char_scenes.values()):
            self._add_empty()
            return

        for char in characters:
            if char_scenes[char.id]:
                self._add_lane(char, char_scenes[char.id])

    def _filtered_scenes(self, filters: PlotFilters | None):
        scenes = self._db.get_all_scenes(self._project_id)
        if not filters:
            return scenes
        return _apply_filters(self._db, scenes, filters)

    def _clear(self) -> None:
        self._lane_count = 0
        while self._lanes_layout.count():
            item = self._lanes_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

    def _add_lane(self, character, scenes: list) -> None:
        lane = QFrame()
        lane.setObjectName("charLane")
        lane_layout = QVBoxLayout(lane)
        lane_layout.setContentsMargins(8, 6, 8, 6)
        lane_layout.setSpacing(4)

        header_row = QHBoxLayout()
        header_row.setSpacing(6)

        dot = QLabel()
        dot.setFixedSize(10, 10)
        dot.setStyleSheet(
            f"background-color: {character.color}; border-radius: 5px;"
        )
        header_row.addWidget(dot)

        name = QLabel(character.name)
        name.setObjectName("charLaneHeader")
        header_row.addWidget(name)
        header_row.addStretch()

        count = QLabel(f"{len(scenes)} scenes")
        count.setObjectName("charLaneCount")
        header_row.addWidget(count)
        lane_layout.addLayout(header_row)

        cards_row = QHBoxLayout()
        cards_row.setSpacing(6)
        for scene in scenes:
            card = self._make_card(scene)
            cards_row.addWidget(card)
        cards_row.addStretch()
        lane_layout.addLayout(cards_row)

        self._lanes_layout.addWidget(lane)
        self._lane_count += 1

    def _make_card(self, scene) -> QFrame:
        card = QFrame()
        card.setObjectName("charCard")
        card.setFixedWidth(130)
        self._setup_card_context(card, scene.id)
        self._apply_card_color(card, scene.color_label)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(1)

        title = QLabel(scene.title or "Untitled")
        title.setObjectName("charCardTitle")
        title.setWordWrap(True)
        layout.addWidget(title)

        chapter = (scene.chapter or scene.act or "").strip()
        if chapter:
            ch_lbl = QLabel(chapter)
            ch_lbl.setObjectName("charCardChapter")
            layout.addWidget(ch_lbl)

        return card

    def _add_empty(self) -> None:
        lbl = QLabel("No characters linked to scenes.\nLink characters in the Scenes view.")
        lbl.setObjectName("charEmpty")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setWordWrap(True)
        self._lanes_layout.addWidget(lbl)

    def lane_count(self) -> int:
        return self._lane_count


# =============================================================================
# Shared filter logic
# =============================================================================

def _apply_filters(db: Database, scenes: list, filters: PlotFilters) -> list:
    result = scenes

    if filters.character_id:
        char_scene_ids: set[int] = set()
        for s in scenes:
            if filters.character_id in db.get_scene_character_ids(s.id):
                char_scene_ids.add(s.id)
        result = [s for s in result if s.id in char_scene_ids]

    if filters.tag:
        tag_lower = filters.tag.lower()
        result = [
            s for s in result
            if tag_lower in (s.tags or "").lower()
        ]

    if filters.plotline:
        result = [
            s for s in result
            if (s.plotline or "").strip().lower() == filters.plotline.lower()
        ]

    return result


# =============================================================================
# Main container
# =============================================================================

_VIEW_MODES = ["Grid", "Timeline", "Arc", "Character"]


class MultiPlotView(QWidget):
    """Multi-view plotting — switch between Grid, Timeline, Arc, Character."""

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

        self._active_mode = "Grid"
        self._filters = PlotFilters()

        self._build_ui()
        self._activate_view("Grid")

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # -- Toolbar ---------------------------------------------------------
        toolbar = QWidget()
        toolbar.setObjectName("multiPlotToolbar")
        tb_layout = QHBoxLayout(toolbar)
        tb_layout.setContentsMargins(12, 6, 12, 6)
        tb_layout.setSpacing(6)

        self._mode_buttons: dict[str, QPushButton] = {}
        for mode in _VIEW_MODES:
            btn = QPushButton(mode)
            btn.setCheckable(True)
            btn.setChecked(mode == "Grid")
            btn.clicked.connect(lambda _, m=mode: self._switch_mode(m))
            btn.setObjectName("multiPlotModeBtn")
            tb_layout.addWidget(btn)
            self._mode_buttons[mode] = btn

        tb_layout.addSpacing(16)

        tb_layout.addWidget(QLabel("Filter:"))

        self._char_filter = QComboBox()
        self._char_filter.setMinimumWidth(100)
        self._char_filter.addItem("All Characters", userData=None)
        for char in self._db.get_all_characters(self._project_id):
            self._char_filter.addItem(char.name, userData=char.id)
        self._char_filter.currentIndexChanged.connect(self._on_filter_changed)
        tb_layout.addWidget(self._char_filter)

        self._tag_filter = QComboBox()
        self._tag_filter.setMinimumWidth(80)
        self._tag_filter.addItem("All Tags")
        for tag in self._db.get_scene_tags(self._project_id):
            self._tag_filter.addItem(tag)
        self._tag_filter.currentIndexChanged.connect(self._on_filter_changed)
        tb_layout.addWidget(self._tag_filter)

        self._arc_filter = QComboBox()
        self._arc_filter.setMinimumWidth(80)
        self._arc_filter.addItem("All Arcs")
        for pl in self._db.get_scene_plotlines(self._project_id):
            self._arc_filter.addItem(pl)
        self._arc_filter.currentIndexChanged.connect(self._on_filter_changed)
        tb_layout.addWidget(self._arc_filter)

        tb_layout.addStretch()
        outer.addWidget(toolbar)

        # -- Content area ----------------------------------------------------
        self._content = QVBoxLayout()
        self._content.setContentsMargins(0, 0, 0, 0)
        self._content.setSpacing(0)
        outer.addLayout(self._content, stretch=1)

        # -- Create sub-views ------------------------------------------------
        self._grid_view = StoryGridView(
            self._db, self._project_id,
            on_data_changed=self._on_data_changed,
            on_open_scene=self._on_open_scene,
        )
        self._timeline_view = _TimelineStrip(
            self._db, self._project_id,
            on_data_changed=self._on_data_changed,
            on_open_scene=self._on_open_scene,
        )
        self._arc_view = _ArcLanes(
            self._db, self._project_id,
            on_data_changed=self._on_data_changed,
            on_open_scene=self._on_open_scene,
        )
        self._char_view = _CharLanes(
            self._db, self._project_id,
            on_data_changed=self._on_data_changed,
            on_open_scene=self._on_open_scene,
        )

        self._views: dict[str, QWidget] = {
            "Grid": self._grid_view,
            "Timeline": self._timeline_view,
            "Arc": self._arc_view,
            "Character": self._char_view,
        }

        for view in self._views.values():
            view.setVisible(False)
            self._content.addWidget(view)

    # -- Mode switching -------------------------------------------------------

    def _switch_mode(self, mode: str) -> None:
        if mode == self._active_mode:
            return
        self._activate_view(mode)

    def _activate_view(self, mode: str) -> None:
        self._active_mode = mode
        for name, btn in self._mode_buttons.items():
            btn.setChecked(name == mode)
        for name, view in self._views.items():
            view.setVisible(name == mode)
        self._refresh_active()

    def _refresh_active(self) -> None:
        view = self._views[self._active_mode]
        if self._active_mode == "Grid":
            self._grid_view.refresh()
        elif self._active_mode == "Timeline":
            self._timeline_view.refresh(self._filters)
        elif self._active_mode == "Arc":
            self._arc_view.refresh(self._filters)
        elif self._active_mode == "Character":
            self._char_view.refresh(self._filters)

    # -- Filters --------------------------------------------------------------

    def _on_filter_changed(self) -> None:
        char_data = self._char_filter.currentData()
        self._filters.character_id = char_data if char_data else None

        tag_text = self._tag_filter.currentText()
        self._filters.tag = "" if tag_text == "All Tags" else tag_text

        arc_text = self._arc_filter.currentText()
        self._filters.plotline = "" if arc_text == "All Arcs" else arc_text

        self._refresh_active()

    def get_filters(self) -> PlotFilters:
        return self._filters

    # -- Public API -----------------------------------------------------------

    def get_active_mode(self) -> str:
        return self._active_mode

    def refresh(self) -> None:
        """Refresh the currently active view and filter combos."""
        self._refresh_filters()
        self._refresh_active()

    def _refresh_filters(self) -> None:
        for combo, loader, default in (
            (self._char_filter, lambda: [
                (c.name, c.id) for c in self._db.get_all_characters(self._project_id)
            ], "All Characters"),
            (self._tag_filter, lambda: [
                (t, None) for t in self._db.get_scene_tags(self._project_id)
            ], "All Tags"),
            (self._arc_filter, lambda: [
                (p, None) for p in self._db.get_scene_plotlines(self._project_id)
            ], "All Arcs"),
        ):
            current = combo.currentText()
            combo.blockSignals(True)
            combo.clear()
            combo.addItem(default, userData=None)
            for label, uid in loader():
                combo.addItem(label, userData=uid)
            idx = combo.findText(current)
            combo.setCurrentIndex(idx if idx >= 0 else 0)
            combo.blockSignals(False)

    def get_view(self, mode: str) -> QWidget | None:
        return self._views.get(mode)
