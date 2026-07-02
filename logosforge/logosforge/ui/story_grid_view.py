"""Visual Story Grid — 3-column block grid grouped by Acts.

Displays scenes (or chapters in Novel mode) as square-ish movable cards in a
3-column grid, grouped under Act sections.  Supports drag-and-drop reordering
within and between Acts, zoom levels, color coding by plotline/tag/beat, and
Story Flow indicators (tension bars, character dots, scene type badges, pacing
warnings).
"""

from __future__ import annotations

from collections.abc import Callable

import shiboken6 as shiboken
from PySide6.QtCore import QMimeData, QPoint, Qt, QTimer
from PySide6.QtGui import QAction, QDrag, QMouseEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMenu,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from logosforge.db import Database
from logosforge.story_flow import (
    FlowAnalysis,
    SceneTension,
    SceneType,
    analyze_flow,
    scene_type_icon,
    tension_color,
)
from logosforge.ui import theme


_BLOCK_SIZE = 160
_GRID_COLUMNS = 3
_DRAG_THRESHOLD = 10

_COLOR_PALETTE = [
    "#4ade80", "#60a5fa", "#f59e0b", "#a78bfa",
    "#f472b6", "#34d399", "#fb923c", "#38bdf8",
]


# ---------------------------------------------------------------------------
# Scene / Chapter block card
# ---------------------------------------------------------------------------

class _SceneCard(QFrame):
    """Compact square-ish block card displayed in the grid."""

    def __init__(
        self,
        scene,
        zoom: int,
        block_label: str = "",
        color_accent: str = "",
        flow_visible: bool = False,
        tension: SceneTension | None = None,
        scene_type: SceneType | None = None,
        char_colors: list[str] | None = None,
        pacing_warning: bool = False,
        screenplay_mode: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.scene_id = scene.id
        self._scene = scene
        self.setObjectName("gridSceneCard")
        self.setFixedSize(_BLOCK_SIZE, _BLOCK_SIZE)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(3)

        # -- Number / type row ---------------------------------------------------
        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(4)

        self._number_label = QLabel(block_label)
        self._number_label.setObjectName("gridCardMeta")
        top_row.addWidget(self._number_label)
        top_row.addStretch()

        self._type_label = QLabel()
        self._type_label.setObjectName("gridCardType")
        if scene_type and flow_visible:
            icon = scene_type_icon(scene_type.primary)
            self._type_label.setText(icon)
            self._type_label.setToolTip(scene_type.primary.capitalize())
        top_row.addWidget(self._type_label)
        layout.addLayout(top_row)

        # -- Title ---------------------------------------------------------------
        self._title_label = QLabel(scene.title or "Untitled")
        self._title_label.setObjectName("gridCardTitle")
        self._title_label.setWordWrap(True)
        layout.addWidget(self._title_label)

        # -- Summary -------------------------------------------------------------
        self._summary_label = QLabel()
        self._summary_label.setObjectName("gridCardSummary")
        self._summary_label.setWordWrap(True)
        summary_text = scene.summary or scene.synopsis or ""
        if len(summary_text) > 80:
            summary_text = summary_text[:77] + "..."
        self._summary_label.setText(summary_text)
        layout.addWidget(self._summary_label)

        # -- Screenplay metadata line -------------------------------------------
        self._screenplay_label = QLabel()
        self._screenplay_label.setObjectName("gridCardMeta")
        if screenplay_mode:
            sp_parts: list[str] = []
            duration = getattr(scene, "estimated_duration_minutes", 0) or 0
            if duration:
                sp_parts.append(f"{duration}m")
            location = getattr(scene, "location", "") or ""
            if location:
                loc_short = location[:20] + "..." if len(location) > 20 else location
                sp_parts.append(loc_short)
            ie = getattr(scene, "interior_exterior", "") or ""
            tod = getattr(scene, "time_of_day", "") or ""
            if ie or tod:
                sp_parts.append(f"{ie}/{tod}" if ie and tod else (ie or tod))
            self._screenplay_label.setText(" · ".join(sp_parts) if sp_parts else "")
        layout.addWidget(self._screenplay_label)

        # -- Dramatic turn / setup-payoff markers --------------------------------
        self._turn_label = QLabel()
        self._turn_label.setObjectName("gridCardMeta")
        if screenplay_mode:
            turn_parts: list[str] = []
            dramatic_turn = getattr(scene, "dramatic_turn", "") or ""
            if dramatic_turn:
                dt_short = dramatic_turn[:30] + "..." if len(dramatic_turn) > 30 else dramatic_turn
                turn_parts.append(f"↻ {dt_short}")
            setup_payoff = getattr(scene, "setup_payoff_links", "") or ""
            if setup_payoff:
                turn_parts.append("⚓")  # anchor = setup/payoff marker
            self._turn_label.setText("  ".join(turn_parts))
            self._turn_label.setToolTip(
                f"Setup/payoff: {setup_payoff}" if setup_payoff else ""
            )
        layout.addWidget(self._turn_label)

        # -- Meta line -----------------------------------------------------------
        self._meta_label = QLabel()
        self._meta_label.setObjectName("gridCardMeta")
        meta_parts: list[str] = []
        if scene.beat:
            meta_parts.append(scene.beat)
        if scene.tags:
            tags_clean = [
                t.strip() for t in scene.tags.split(",")
                if not t.strip().lower().startswith("tension:")
            ]
            if tags_clean:
                meta_parts.append(tags_clean[0])
        if scene.plotline:
            meta_parts.append(scene.plotline)
        self._meta_label.setText(" · ".join(meta_parts) if meta_parts else "")
        layout.addWidget(self._meta_label)

        # -- Character dots ------------------------------------------------------
        self._char_row = QWidget()
        self._char_row.setObjectName("gridCharRow")
        char_layout = QHBoxLayout(self._char_row)
        char_layout.setContentsMargins(0, 2, 0, 0)
        char_layout.setSpacing(3)
        if char_colors and flow_visible:
            for color in char_colors[:6]:
                dot = QLabel()
                dot.setFixedSize(6, 6)
                dot.setObjectName("gridCharDot")
                dot.setStyleSheet(
                    f"background-color: {color}; border-radius: 3px;"
                )
                char_layout.addWidget(dot)
        char_layout.addStretch()
        layout.addWidget(self._char_row)

        # -- Tension bar ---------------------------------------------------------
        self._tension_bar = QWidget()
        self._tension_bar.setObjectName("gridTensionBar")
        self._tension_bar.setFixedHeight(3)
        if tension and tension.value > 0 and flow_visible:
            bar_color = tension_color(tension.value)
            width_pct = tension.value * 10
            self._tension_bar.setStyleSheet(
                f"background-color: {bar_color}; border-radius: 1px;"
                f" max-width: {width_pct}%;"
            )
            self._tension_bar.setToolTip(f"Tension: {tension.value}/10 ({tension.source})")
        else:
            self._tension_bar.hide()
        layout.addWidget(self._tension_bar)

        layout.addStretch()

        self._apply_zoom(zoom, flow_visible, screenplay_mode)
        self._apply_accent(color_accent)
        self._apply_pacing_warning(pacing_warning, flow_visible)

        self._drag_start: QPoint | None = None

    def _apply_zoom(self, zoom: int, flow_visible: bool = False, screenplay_mode: bool = False) -> None:
        if zoom == 0:
            self._summary_label.hide()
            self._meta_label.hide()
            self._char_row.hide()
            self._type_label.hide()
            self._screenplay_label.hide()
            self._turn_label.hide()
        elif zoom == 1:
            self._summary_label.setVisible(bool(self._summary_label.text()))
            self._meta_label.hide()
            self._char_row.setVisible(flow_visible)
            self._type_label.setVisible(flow_visible)
            self._screenplay_label.setVisible(screenplay_mode and bool(self._screenplay_label.text()))
            self._turn_label.hide()
        else:
            self._summary_label.setVisible(bool(self._summary_label.text()))
            self._meta_label.setVisible(bool(self._meta_label.text()))
            self._char_row.setVisible(flow_visible)
            self._type_label.setVisible(flow_visible)
            self._screenplay_label.setVisible(screenplay_mode and bool(self._screenplay_label.text()))
            self._turn_label.setVisible(screenplay_mode and bool(self._turn_label.text()))

    def _apply_accent(self, color: str) -> None:
        if color:
            self.setStyleSheet(
                self.styleSheet()
                + f"\n#gridSceneCard {{ border-left: 4px solid {color}; }}"
            )

    def _apply_pacing_warning(self, warning: bool, flow_visible: bool) -> None:
        if warning and flow_visible:
            self.setObjectName("gridSceneCardWarning")

    # -- Drag support -----------------------------------------------------------

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start = event.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag_start is None:
            return
        if (event.pos() - self._drag_start).manhattanLength() < _DRAG_THRESHOLD:
            return
        drag = QDrag(self)
        mime = QMimeData()
        mime.setText(str(self.scene_id))
        drag.setMimeData(mime)
        drag.setPixmap(self.grab())
        drag.setHotSpot(event.pos())
        drag.exec(Qt.DropAction.MoveAction)
        if not shiboken.isValid(self):
            return
        self._drag_start = None

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._drag_start = None
        super().mouseReleaseEvent(event)

    def enterEvent(self, event) -> None:
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self.unsetCursor()
        super().leaveEvent(event)


# ---------------------------------------------------------------------------
# Act section — groups blocks in a 3-column grid
# ---------------------------------------------------------------------------

class _ActSection(QFrame):
    """A single Act section containing scene blocks in a 3-column grid."""

    scene_dropped = None

    def __init__(
        self,
        act_name: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.act_name = act_name
        self.group_name = act_name
        self.setObjectName("gridActSection")
        self.setAcceptDrops(True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 8)
        outer.setSpacing(4)

        self._header = QLabel(act_name or "Unassigned")
        self._header.setObjectName("gridColumnHeader")
        outer.addWidget(self._header)

        self._grid = QGridLayout()
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setSpacing(8)
        outer.addLayout(self._grid)

        self._cards: list[_SceneCard] = []
        self._drop_indicator: QWidget | None = None

    def add_card(self, card: _SceneCard) -> None:
        idx = len(self._cards)
        row, col = divmod(idx, _GRID_COLUMNS)
        self._cards.append(card)
        self._grid.addWidget(card, row, col)

    def card_count(self) -> int:
        return len(self._cards)

    def set_empty_state(self, text: str) -> None:
        lbl = QLabel(text)
        lbl.setObjectName("gridEmptyColumn")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setWordWrap(True)
        self._grid.addWidget(lbl, 0, 0, 1, _GRID_COLUMNS)

    # -- Drop target ------------------------------------------------------------

    def _drop_index(self, pos: QPoint) -> int:
        for i, card in enumerate(self._cards):
            card_rect = card.geometry()
            if pos.y() < card_rect.center().y():
                return i
            if pos.y() < card_rect.bottom() and pos.x() < card_rect.center().x():
                return i
        return len(self._cards)

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasText():
            event.acceptProposedAction()
            self._show_drop_indicator()

    def dragMoveEvent(self, event) -> None:
        if event.mimeData().hasText():
            event.acceptProposedAction()

    def dragLeaveEvent(self, event) -> None:
        self._hide_drop_indicator()

    def dropEvent(self, event) -> None:
        self._hide_drop_indicator()
        if not event.mimeData().hasText():
            return
        scene_id = int(event.mimeData().text())
        drop_idx = self._drop_index(event.position().toPoint())
        event.acceptProposedAction()
        if self.scene_dropped:
            self.scene_dropped(scene_id, self.act_name, drop_idx)

    def _show_drop_indicator(self) -> None:
        if self._drop_indicator is None:
            self._drop_indicator = QWidget(self)
            self._drop_indicator.setFixedHeight(3)
            self._drop_indicator.setObjectName("gridDropIndicator")
            self._drop_indicator.setStyleSheet(
                f"background-color: {theme.ACCENT}; border-radius: 1px;"
            )
        self._drop_indicator.setFixedWidth(self.width() - 16)
        self._drop_indicator.move(8, self.height() - 10)
        self._drop_indicator.show()

    def _hide_drop_indicator(self) -> None:
        if self._drop_indicator:
            self._drop_indicator.hide()


# ---------------------------------------------------------------------------
# Backwards-compatible alias (tests import this name)
# ---------------------------------------------------------------------------
_GridColumn = _ActSection


# ---------------------------------------------------------------------------
# Graphic Novel page planning cards
# ---------------------------------------------------------------------------

_GN_DENSITY_OPTS = ("", "silent", "light", "medium", "dense", "explosive")
_GN_REVEAL_OPTS = ("", "none", "page_turn", "cliffhanger", "splash_reveal")


class _GnIssueSection(QFrame):
    """A titled column holding a run of page cards (grouped by Issue)."""

    def __init__(self, title: str) -> None:
        super().__init__()
        self.setObjectName("gnIssueSection")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(6)
        header = QLabel(title)
        header.setObjectName("gnIssueHeader")
        header.setStyleSheet("font-weight: bold;")
        outer.addWidget(header)
        self._body = QVBoxLayout()
        self._body.setSpacing(6)
        outer.addLayout(self._body)
        self._cards: list[QWidget] = []

    def add_card(self, card: QWidget) -> None:
        self._cards.append(card)
        self._body.addWidget(card)

    def card_count(self) -> int:
        return len(self._cards)


class _GnPageCard(QFrame):
    """Compact page planning card — page number, badges, summary, chips (§3)."""

    def __init__(
        self, block: dict,
        on_move: Callable[[int, int], None] | None = None,
        on_edit: Callable[[int, str], None] | None = None,
        on_open_pages: Callable[[int], None] | None = None,
    ) -> None:
        super().__init__()
        self._block = block
        self._page_id = block["id"]
        self._on_move = on_move
        self._on_edit = on_edit
        self._on_open_pages = on_open_pages
        self.setObjectName("gnPageCard")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self._build()

    def _build(self) -> None:
        b = self._block
        col = QVBoxLayout(self)
        col.setContentsMargins(8, 6, 8, 6)
        col.setSpacing(3)

        # Top row: page number (prominent) + badges + menu.
        top = QHBoxLayout()
        num = QLabel(f"Page {b['page_number']}")
        num.setObjectName("gnPageNumber")
        num.setStyleSheet("font-weight: bold; font-size: 13px;")
        top.addWidget(num)
        for tag in self._badges():
            chip = QLabel(tag)
            chip.setObjectName("gnBadge")
            chip.setStyleSheet(
                "background: rgba(255,255,255,0.08); border-radius: 6px;"
                " padding: 0 5px; font-size: 9px;"
            )
            top.addWidget(chip)
        top.addStretch()

        self._up_btn = QPushButton("↑")
        self._up_btn.setFixedWidth(22)
        self._up_btn.clicked.connect(lambda: self._move(-1))
        self._down_btn = QPushButton("↓")
        self._down_btn.setFixedWidth(22)
        self._down_btn.clicked.connect(lambda: self._move(1))
        self._menu_btn = QPushButton("⋯")
        self._menu_btn.setFixedWidth(22)
        self._menu_btn.clicked.connect(self._open_menu)
        top.addWidget(self._up_btn)
        top.addWidget(self._down_btn)
        top.addWidget(self._menu_btn)
        col.addLayout(top)

        # Meta line: panels + density/reveal.
        meta_bits = [f"{b['panel_count']} panels"]
        if b["density"]:
            meta_bits.append(b["density"])
        if b["reveal_marker"]:
            meta_bits.append(f"reveal: {b['reveal_marker']}")
        meta = QLabel("  ·  ".join(meta_bits))
        meta.setObjectName("gnPageMeta")
        meta.setStyleSheet("color: #8a93a3; font-size: 10px;")
        col.addWidget(meta)

        if (b.get("emotional_beat") or "").strip():
            beat = QLabel("beat: " + b["emotional_beat"])
            beat.setStyleSheet("color: #a0aec0; font-size: 10px;")
            beat.setWordWrap(True)
            col.addWidget(beat)

        summary = (b.get("summary") or "").strip() or "(no summary)"
        s = QLabel(summary)
        s.setWordWrap(True)
        s.setStyleSheet("font-size: 11px;")
        col.addWidget(s)

        chips = list(b.get("motif_markers") or []) + [
            f"@{c}" for c in (b.get("characters") or [])
        ]
        if chips:
            chip_lbl = QLabel(" ".join(f"·{c}" for c in chips[:8]))
            chip_lbl.setObjectName("gnChips")
            chip_lbl.setStyleSheet("color: #06b6d4; font-size: 9px;")
            chip_lbl.setWordWrap(True)
            col.addWidget(chip_lbl)

        if b.get("text_heavy"):
            warn = QLabel("⚠ text-heavy")
            warn.setObjectName("gnTextHeavy")
            warn.setStyleSheet("color: #eab308; font-size: 9px;")
            col.addWidget(warn)

    def _badges(self) -> list[str]:
        out = list(self._block.get("rhythm") or [])
        return out[:5]

    def _move(self, delta: int) -> None:
        if self._on_move:
            self._on_move(self._page_id, delta)

    def _open_menu(self) -> None:
        menu = QMenu(self)
        menu.addAction("Edit summary",
                       lambda: self._edit("summary"))
        menu.addAction("Edit emotional beat",
                       lambda: self._edit("emotional_beat"))
        dens = menu.addMenu("Density")
        for opt in _GN_DENSITY_OPTS[1:]:
            dens.addAction(opt, lambda o=opt: self._edit(f"density:{o}"))
        rev = menu.addMenu("Reveal")
        for opt in _GN_REVEAL_OPTS[1:]:
            rev.addAction(opt, lambda o=opt: self._edit(f"reveal:{o}"))
        menu.addAction("Toggle splash page",
                       lambda: self._edit("splash_page"))
        if self._on_open_pages is not None:
            menu.addSeparator()
            menu.addAction("Open in Pages view",
                           lambda: self._on_open_pages(self._page_id))
        menu.exec(self._menu_btn.mapToGlobal(self._menu_btn.rect().bottomLeft()))

    def _edit(self, field: str) -> None:
        if self._on_edit:
            self._on_edit(self._page_id, field)


# ---------------------------------------------------------------------------
# Main grid view
# ---------------------------------------------------------------------------

_COLUMN_MIN_WIDTH = 200
_COLUMN_MAX_WIDTH = 280


class StoryGridView(QWidget):
    """Visual Story Grid — 3-column block grid grouped by Acts."""

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

        self._group_by = "act"
        self._zoom = 1
        self._color_mode = "none"
        self._flow_visible = False
        self._flow_analysis: FlowAnalysis | None = None
        self._columns: list[_ActSection] = []

        project = self._db.get_project_by_id(self._project_id)
        from logosforge.project_compat import (
            get_project_narrative_engine,
            get_project_writing_format,
        )
        engine = get_project_narrative_engine(project)
        self._graphic_novel_mode = engine == "graphic_novel"
        self._stage_script_mode = engine == "stage_script"
        self._series_mode = engine == "series"
        self._gn_filter = "all"   # Plot page filter (§8)
        # Story grid still keys most branches off the writing format, but
        # falls back to "screenplay" when the engine is screenplay so the
        # scene-grid affordances appear even if the format was overridden.
        self._format_mode = (
            "screenplay"
            if engine == "screenplay"
            else get_project_writing_format(project) or "novel"
        )

        self._build_ui()
        self.refresh()

    @property
    def _block_unit(self) -> str:
        if self._graphic_novel_mode:
            return "sequence"
        if self._series_mode:
            return "episode"
        if self._format_mode == "screenplay" or self._stage_script_mode:
            return "scene"
        return "chapter"

    # -- Series plot (episodes grouped by seasons) --------------------------

    def is_series_mode(self) -> bool:
        return self._series_mode

    def get_series_plot_blocks(self) -> list[dict]:
        """Episode plot blocks (logline, A/B/C indicators, active arcs,
        cliffhanger, setup/payoff markers, runtime). [] for non-series."""
        if not self._series_mode:
            return []
        from logosforge.series_plot import get_series_plot_blocks
        return get_series_plot_blocks(self._db, self._project_id)

    def get_series_plot_seasons(self) -> list[dict]:
        """Episodes grouped by season. [] for non-series projects."""
        if not self._series_mode:
            return []
        from logosforge.series_plot import get_series_plot_seasons
        return get_series_plot_seasons(self._db, self._project_id)

    def get_series_episode_detail(self, episode_id: int) -> dict:
        if not self._series_mode:
            return {}
        from logosforge.series_plot import get_episode_detail
        return get_episode_detail(self._db, self._project_id, episode_id)

    # -- Stage Script plot (scenes grouped by acts) -------------------------

    def is_stage_script_mode(self) -> bool:
        return self._stage_script_mode

    def get_stage_plot_blocks(self) -> list[dict]:
        """Theatre scene blocks (objective, turn, characters on stage,
        entrance/exit count, props, duration). [] for non-stage projects."""
        if not self._stage_script_mode:
            return []
        from logosforge.stage_script_plot import get_stage_plot_blocks
        return get_stage_plot_blocks(self._db, self._project_id)

    def get_stage_plot_acts(self) -> list[dict]:
        """Scenes grouped by act. [] for non-stage projects."""
        if not self._stage_script_mode:
            return []
        from logosforge.stage_script_plot import get_stage_plot_acts
        return get_stage_plot_acts(self._db, self._project_id)

    # -- Graphic Novel plot (page/panel-aware) ------------------------------

    def is_graphic_novel_mode(self) -> bool:
        return self._graphic_novel_mode

    def get_gn_plot_blocks(self, unit: str | None = None) -> list[dict]:
        """Page/sequence plot blocks for graphic-novel projects.

        Returns [] for non-graphic-novel projects. unit defaults to the
        engine's plot block unit ("sequence"); pass "page" for page blocks.
        """
        if not self._graphic_novel_mode:
            return []
        from logosforge.graphic_novel_plot import get_gn_plot_blocks
        return get_gn_plot_blocks(
            self._db, self._project_id, unit=unit or "sequence",
        )

    def get_gn_plot_pages_grouped(self, filter_name: str | None = None) -> list[dict]:
        """Page blocks grouped by Issue/Sequence for the Plot grid (§1, §2).

        [] for non-graphic-novel projects."""
        if not self._graphic_novel_mode:
            return []
        from logosforge.graphic_novel_plot import get_gn_plot_pages_grouped
        return get_gn_plot_pages_grouped(
            self._db, self._project_id, filter_name or self._gn_filter,
        )

    def set_gn_plot_filter(self, filter_name: str) -> None:
        """Set the active page filter (§8) and re-render."""
        self._gn_filter = filter_name or "all"
        if self._graphic_novel_mode:
            self.refresh()

    def gn_update_page(self, page_id: int, **fields) -> None:
        """Persist a page edit from Plot via the shared GN service (§4, §10).

        Same data source as Pages View / Canvas / Timeline — no duplicate
        data. Refreshes and announces a plot/project change."""
        if not self._graphic_novel_mode:
            return
        self._db.update_gn_page(page_id, **fields)
        self.refresh()
        self._emit_gn_changed()

    def gn_move_page(self, page_id: int, delta: int) -> None:
        """Reorder a page from Plot (↑/↓) via reorder_gn_pages (§5)."""
        if not self._graphic_novel_mode:
            return
        ids = [p.id for p in self._db.get_gn_pages(self._project_id)]
        if page_id not in ids:
            return
        idx = ids.index(page_id)
        new_idx = idx + delta
        if new_idx < 0 or new_idx >= len(ids):
            return
        ids[idx], ids[new_idx] = ids[new_idx], ids[idx]
        self._db.reorder_gn_pages(self._project_id, ids)
        self.refresh()
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

    def _block_number_label(self, index: int) -> str:
        if self._block_unit == "sequence":
            return f"Seq {index}"
        if self._block_unit == "episode":
            return f"Ep {index}"
        if self._block_unit == "scene":
            return f"Scene {index}"
        return f"Ch {index}"

    # NOTE: stage_script and screenplay both use the "scene" block unit.

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # -- Toolbar ---------------------------------------------------------
        toolbar = QWidget()
        toolbar.setObjectName("gridToolbar")
        tb_layout = QHBoxLayout(toolbar)
        tb_layout.setContentsMargins(12, 6, 12, 6)
        tb_layout.setSpacing(8)

        tb_layout.addWidget(QLabel("Group:"))
        self._group_combo = QComboBox()
        group_items = ["By Act", "By Chapter"]
        if self._format_mode == "screenplay":
            group_items.append("By Location")
        self._group_combo.addItems(group_items)
        self._group_combo.currentIndexChanged.connect(self._on_group_changed)
        tb_layout.addWidget(self._group_combo)

        tb_layout.addWidget(QLabel("Color:"))
        self._color_combo = QComboBox()
        color_items = ["None", "Plotline", "Tag", "Beat"]
        if self._format_mode == "screenplay":
            color_items.extend(["Pacing", "Continuity"])
        self._color_combo.addItems(color_items)
        self._color_combo.currentIndexChanged.connect(self._on_color_changed)
        tb_layout.addWidget(self._color_combo)

        self._flow_check = QCheckBox("Flow")
        self._flow_check.setToolTip("Show tension, pacing, and character indicators")
        self._flow_check.toggled.connect(self._on_flow_toggled)
        tb_layout.addWidget(self._flow_check)

        tb_layout.addStretch()

        self._zoom_out_btn = QPushButton("−")
        self._zoom_out_btn.setFixedWidth(28)
        self._zoom_out_btn.setToolTip("Zoom out")
        self._zoom_out_btn.clicked.connect(self._zoom_out)
        tb_layout.addWidget(self._zoom_out_btn)

        self._zoom_label = QLabel("Zoom: 2")
        self._zoom_label.setObjectName("gridZoomLabel")
        tb_layout.addWidget(self._zoom_label)

        self._zoom_in_btn = QPushButton("+")
        self._zoom_in_btn.setFixedWidth(28)
        self._zoom_in_btn.setToolTip("Zoom in")
        self._zoom_in_btn.clicked.connect(self._zoom_in)
        tb_layout.addWidget(self._zoom_in_btn)

        outer.addWidget(toolbar)

        # -- Grid scroll area ------------------------------------------------
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setObjectName("gridScrollArea")
        self._scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff,
        )
        outer.addWidget(self._scroll)

        self._grid_container = QWidget()
        self._grid_container.setObjectName("gridContainer")
        self._grid_layout = QVBoxLayout(self._grid_container)
        self._grid_layout.setContentsMargins(12, 12, 12, 12)
        self._grid_layout.setSpacing(16)
        self._grid_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._scroll.setWidget(self._grid_container)

        self._update_zoom_label()

    # -- Data loading --------------------------------------------------------

    def refresh(self) -> None:
        if self._graphic_novel_mode:
            self._refresh_gn()
            return
        self._clear_grid()
        scenes = self._db.get_all_scenes(self._project_id)

        groups: dict[str, list] = {}
        for scene in scenes:
            if self._group_by == "act":
                key = (scene.act or "").strip()
            elif self._group_by == "location":
                key = (getattr(scene, "location", "") or "").strip()
            else:
                key = (scene.chapter or "").strip()
            if not key:
                key = ""
            groups.setdefault(key, []).append(scene)

        color_map = self._build_color_map(scenes)

        if self._flow_visible:
            self._flow_analysis = analyze_flow(self._db, self._project_id)
            char_color_map = self._build_char_color_map(scenes)
            warned_ids = set()
            if self._flow_analysis:
                for w in self._flow_analysis.pacing_warnings:
                    warned_ids.update(w.scene_ids)
        else:
            self._flow_analysis = None
            char_color_map = {}
            warned_ids = set()

        if not groups:
            self._add_empty_grid_state()
            return

        sorted_keys = sorted(groups.keys(), key=lambda k: (k == "", k))
        global_idx = 1

        for key in sorted_keys:
            section = _ActSection(key if key else "Unassigned")
            section.scene_dropped = self._on_scene_dropped
            section.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            section.customContextMenuRequested.connect(
                lambda pos, s=section: self._on_section_context(s, pos)
            )

            for scene in groups[key]:
                from logosforge.ui.color_labels import color_hex
                user_color = color_hex(scene.color_label)
                accent = user_color or color_map.get(scene.id, "")
                tension = (
                    self._flow_analysis.tensions.get(scene.id)
                    if self._flow_analysis else None
                )
                scene_type = (
                    self._flow_analysis.scene_types.get(scene.id)
                    if self._flow_analysis else None
                )
                char_colors = char_color_map.get(scene.id, [])
                card = _SceneCard(
                    scene,
                    self._zoom,
                    block_label=self._block_number_label(global_idx),
                    color_accent=accent,
                    flow_visible=self._flow_visible,
                    tension=tension,
                    scene_type=scene_type,
                    char_colors=char_colors,
                    pacing_warning=scene.id in warned_ids,
                    screenplay_mode=self._format_mode == "screenplay",
                )
                card.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
                card.customContextMenuRequested.connect(
                    lambda pos, c=card: self._on_card_context(c, pos)
                )
                section.add_card(card)
                global_idx += 1

            self._columns.append(section)
            self._grid_layout.addWidget(section)

        self._grid_layout.addStretch()

    def _clear_grid(self) -> None:
        self._columns.clear()
        while self._grid_layout.count():
            item = self._grid_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

    # -- Graphic Novel page grid (§2, §3) -----------------------------------

    def _refresh_gn(self) -> None:
        """Render pages as compact planning cards, grouped by Issue/Sequence."""
        self._clear_grid()
        groups = self.get_gn_plot_pages_grouped()
        if not groups or not any(g["pages"] for g in groups):
            empty = QLabel(
                "No graphic-novel pages yet.\n"
                "Add pages in the Pages view to plan them here."
            )
            empty.setObjectName("gridEmptyLabel")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._grid_layout.addWidget(empty)
            return

        for group in groups:
            if not group["pages"]:
                continue
            section = _GnIssueSection(group["group_title"] or "Pages")
            for block in group["pages"]:
                card = _GnPageCard(
                    block,
                    on_move=self.gn_move_page,
                    on_edit=self._gn_edit_page,
                    on_open_pages=self._on_open_gn_page,
                )
                section.add_card(card)
            self._columns.append(section)
            self._grid_layout.addWidget(section)
        self._grid_layout.addStretch()

    def _gn_edit_page(self, page_id: int, field: str) -> None:
        """Edit-menu handler from a page card (§4). Persists via gn_update_page."""
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

    def _on_open_gn_page(self, page_id: int) -> None:
        """Open a page in the Pages view (deferred — needs host wiring)."""
        cb = getattr(self, "_on_open_gn_page_cb", None)
        if cb is not None:
            cb(page_id)

    def _add_empty_grid_state(self) -> None:
        empty = QWidget()
        empty.setObjectName("gridEmptyState")
        layout = QVBoxLayout(empty)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(12)

        msg = QLabel("Your story grid is empty.\nCreate scenes to see them here.")
        msg.setObjectName("gridEmptyLabel")
        msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(msg)

        add_btn = QPushButton("+ Add Scene")
        add_btn.setObjectName("gridAddSceneBtn")
        add_btn.clicked.connect(self._create_first_scene)
        layout.addWidget(add_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        self._grid_layout.addWidget(empty)

    # -- Color coding --------------------------------------------------------

    def _build_color_map(self, scenes) -> dict[int, str]:
        if self._color_mode == "none":
            return {}

        if self._color_mode == "pacing":
            return self._build_pacing_color_map(scenes)
        if self._color_mode == "continuity":
            return self._build_continuity_color_map(scenes)

        assignments: dict[str, str] = {}
        result: dict[int, str] = {}
        idx = 0

        for scene in scenes:
            if self._color_mode == "plotline":
                key = (scene.plotline or "").strip()
            elif self._color_mode == "tag":
                tags = (scene.tags or "").split(",")
                key = tags[0].strip() if tags else ""
            elif self._color_mode == "beat":
                key = (scene.beat or "").strip()
            else:
                key = ""

            if not key:
                continue

            if key not in assignments:
                assignments[key] = _COLOR_PALETTE[idx % len(_COLOR_PALETTE)]
                idx += 1
            result[scene.id] = assignments[key]

        return result

    def _build_pacing_color_map(self, scenes) -> dict[int, str]:
        """Color scenes by cinematic pacing: fast/medium/slow."""
        _PACING_COLORS = {
            "fast": "#f87171",    # red — high energy
            "medium": "#facc15",  # amber — moderate
            "slow": "#60a5fa",    # blue — deliberate
        }
        result: dict[int, str] = {}
        for scene in scenes:
            pacing = (getattr(scene, "cinematic_pacing", "") or "").strip().lower()
            if pacing in _PACING_COLORS:
                result[scene.id] = _PACING_COLORS[pacing]
        return result

    def _build_continuity_color_map(self, scenes) -> dict[int, str]:
        """Color scenes that have continuity items tracked vs not."""
        result: dict[int, str] = {}
        for scene in scenes:
            items = self._db.get_continuity_for_scene(scene.id)
            if items:
                result[scene.id] = "#4ade80"  # green — tracked
            else:
                char_ids = self._db.get_scene_character_ids(scene.id)
                if char_ids:
                    result[scene.id] = "#f87171"  # red — characters but no continuity
        return result

    # -- Drag and drop -------------------------------------------------------

    def _on_scene_dropped(
        self, scene_id: int, target_group: str, drop_index: int,
    ) -> None:
        scene = self._db.get_scene_by_id(scene_id)
        if scene is None:
            return

        if target_group == "Unassigned":
            target_group = ""

        if self._group_by == "act":
            if scene.act != target_group:
                self._db.update_scene(
                    scene_id=scene.id, title=scene.title,
                    summary=scene.summary, synopsis=scene.synopsis,
                    goal=scene.goal, conflict=scene.conflict, outcome=scene.outcome,
                    beat=scene.beat, tags=scene.tags, act=target_group,
                    content=scene.content, chapter=scene.chapter, plotline=scene.plotline,
                )
        else:
            if scene.chapter != target_group:
                self._db.update_scene(
                    scene_id=scene.id, title=scene.title,
                    summary=scene.summary, synopsis=scene.synopsis,
                    goal=scene.goal, conflict=scene.conflict, outcome=scene.outcome,
                    beat=scene.beat, tags=scene.tags, act=scene.act,
                    content=scene.content, chapter=target_group, plotline=scene.plotline,
                )

        self._db.reorder_scene(scene_id, drop_index)

        if self._on_data_changed:
            self._on_data_changed()
        self.refresh()

    # -- Context menus -------------------------------------------------------

    def _on_card_context(self, card: _SceneCard, pos: QPoint) -> None:
        scene = self._db.get_scene_by_id(card.scene_id)
        if scene is None:
            return
        menu = QMenu(card)

        if self._on_open_scene is not None:
            open_act = QAction("Open in Manuscript", menu)
            open_act.triggered.connect(lambda: self._on_open_scene(card.scene_id))
            menu.addAction(open_act)

        edit_title = QAction("Edit Title", menu)
        edit_title.triggered.connect(lambda: self._edit_title(card.scene_id))
        menu.addAction(edit_title)

        edit_summary = QAction("Edit Summary", menu)
        edit_summary.triggered.connect(lambda: self._edit_summary(card.scene_id))
        menu.addAction(edit_summary)

        # "Move to Act" submenu
        all_scenes = self._db.get_all_scenes(self._project_id)
        acts = sorted({(s.act or "").strip() for s in all_scenes} - {""})
        if acts:
            move_menu = QMenu("Move to Act", menu)
            for act in acts:
                if act != (scene.act or "").strip():
                    act_action = QAction(act, move_menu)
                    act_action.triggered.connect(
                        lambda _, a=act, sid=card.scene_id: self._move_to_act(sid, a)
                    )
                    move_menu.addAction(act_action)
            if move_menu.actions():
                menu.addMenu(move_menu)

        from logosforge.ui.color_labels import build_color_menu
        build_color_menu(
            menu, scene.color_label,
            lambda key, sid=card.scene_id: self._set_color(sid, key),
        )

        delete_act = QAction("Delete", menu)
        delete_act.triggered.connect(lambda: self._delete_scene(card.scene_id))
        menu.addAction(delete_act)

        menu.exec(card.mapToGlobal(pos))

    def _set_color(self, scene_id: int, color_label: str) -> None:
        self._db.update_scene_color(scene_id, color_label)
        if self._on_data_changed:
            self._on_data_changed()

    def _on_section_context(self, section: _ActSection, pos: QPoint) -> None:
        menu = QMenu(section)
        add_act = QAction("Add Scene to this Act", menu)
        add_act.triggered.connect(
            lambda: self._add_scene_to_act(section.act_name)
        )
        menu.addAction(add_act)
        menu.exec(section.mapToGlobal(pos))

    # -- Edit operations -----------------------------------------------------

    def _edit_title(self, scene_id: int) -> None:
        scene = self._db.get_scene_by_id(scene_id)
        if scene is None:
            return
        new_title, ok = QInputDialog.getText(
            self, "Edit Title", "Title:", text=scene.title,
        )
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
        self.refresh()

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
        self.refresh()

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
        self.refresh()

    def _delete_scene(self, scene_id: int) -> None:
        scene = self._db.get_scene_by_id(scene_id)
        if scene is None:
            return
        from PySide6.QtWidgets import QMessageBox
        confirm = QMessageBox.question(
            self, "Delete Scene",
            f"Delete scene '{scene.title}'?\nThis cannot be undone.",
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        self._db.delete_scene(scene_id)
        if self._on_data_changed:
            self._on_data_changed()
        self.refresh()

    def _add_scene_to_act(self, act_name: str) -> None:
        title, ok = QInputDialog.getText(
            self, "Add Scene", "Scene title:", text="Untitled Scene",
        )
        if not ok:
            return
        actual_act = "" if act_name == "Unassigned" else act_name
        self._db.create_scene(
            self._project_id, title.strip() or "Untitled Scene",
            act=actual_act,
        )
        if self._on_data_changed:
            self._on_data_changed()
        self.refresh()

    # -- Zoom ----------------------------------------------------------------

    def _zoom_in(self) -> None:
        if self._zoom < 2:
            self._zoom += 1
            self._update_zoom_label()
            self.refresh()

    def _zoom_out(self) -> None:
        if self._zoom > 0:
            self._zoom -= 1
            self._update_zoom_label()
            self.refresh()

    def _update_zoom_label(self) -> None:
        names = ["Titles", "Summary", "Detail"]
        self._zoom_label.setText(f"Zoom: {names[self._zoom]}")

    def get_zoom(self) -> int:
        return self._zoom

    # -- Flow indicators -------------------------------------------------------

    def _on_flow_toggled(self, checked: bool) -> None:
        self._flow_visible = checked
        self.refresh()

    def is_flow_visible(self) -> bool:
        return self._flow_visible

    def _build_char_color_map(self, scenes) -> dict[int, list[str]]:
        characters = self._db.get_all_characters(self._project_id)
        char_colors: dict[int, str] = {c.id: c.color for c in characters}
        result: dict[int, list[str]] = {}
        for scene in scenes:
            char_ids = self._db.get_scene_character_ids(scene.id)
            colors = [char_colors[cid] for cid in char_ids if cid in char_colors]
            if colors:
                result[scene.id] = colors
        return result

    # -- Group / color switching ---------------------------------------------

    def _on_group_changed(self, index: int) -> None:
        group_modes = ["act", "chapter"]
        if self._format_mode == "screenplay":
            group_modes.append("location")
        self._group_by = group_modes[index] if index < len(group_modes) else "act"
        self.refresh()

    def _on_color_changed(self, index: int) -> None:
        modes = ["none", "plotline", "tag", "beat"]
        if self._format_mode == "screenplay":
            modes.extend(["pacing", "continuity"])
        self._color_mode = modes[index] if index < len(modes) else "none"
        self.refresh()

    def get_color_mode(self) -> str:
        return self._color_mode

    def get_group_by(self) -> str:
        return self._group_by

    # -- Scene creation ------------------------------------------------------

    def _create_first_scene(self) -> None:
        group = "Act I" if self._group_by == "act" else "Chapter 1"
        self._db.create_scene(
            self._project_id, "New Scene",
            act=group if self._group_by == "act" else "",
            chapter=group if self._group_by == "chapter" else "",
        )
        if self._on_data_changed:
            self._on_data_changed()
        self.refresh()

    # -- Public API ----------------------------------------------------------

    def column_count(self) -> int:
        return len(self._columns)

    def total_cards(self) -> int:
        return sum(c.card_count() for c in self._columns)

    def get_format_mode(self) -> str:
        return self._format_mode
