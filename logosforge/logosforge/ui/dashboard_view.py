"""Story Dashboard — project overview and entry points to current work."""

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from logosforge import preferences
from logosforge.analytics import compute_scene_stats
from logosforge.db import Database
from logosforge.ui import theme




class DashboardView(QWidget):
    def __init__(
        self,
        db: Database,
        project_id: int,
        on_navigate: Callable[[str, int], None] | None = None,
        on_open_section: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__()
        self._db = db
        self._project_id = project_id
        self._on_navigate = on_navigate
        self._on_open_section = on_open_section

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer.addWidget(scroll)

        self._container = QWidget()
        self._layout = QVBoxLayout(self._container)
        self._layout.setContentsMargins(32, 32, 32, 32)
        self._layout.setSpacing(24)
        self._layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        scroll.setWidget(self._container)

        self._connect_events()
        self._build()

    # -- Event wiring --------------------------------------------------------

    def _connect_events(self) -> None:
        """Recompute whenever the active project changes or its data is
        mutated. Bound-method connections auto-disconnect when this widget
        is destroyed, so persisted/replaced dashboards never leak."""
        from logosforge.project_events import get_event_bus
        bus = get_event_bus()
        # Lifecycle: a different project is now active — re-point + recompute.
        bus.project_loaded.connect(self._on_project_changed)
        bus.project_created.connect(self._on_project_changed)
        # Data mutations within the current project — recompute in place.
        for signal in (
            bus.project_data_changed,
            bus.scene_changed,
            bus.scenes_changed,
            bus.outline_changed,
            bus.psyke_changed,
            bus.psyke_list_changed,
            bus.plot_changed,
            bus.notes_changed,
        ):
            signal.connect(self._on_data_event)

    def _on_project_changed(self, project_id: int) -> None:
        """A new project became active. Drop everything tied to the old
        project, re-point at the new one, and recompute from scratch."""
        self.set_project(project_id)

    def _on_data_event(self, *_args) -> None:
        """Project data changed — recompute for the current project."""
        self.refresh()

    def set_project(self, project_id: int) -> None:
        """Point the dashboard at *project_id*, clearing old state first
        so no metrics from the previous project can survive."""
        self._project_id = project_id
        self.refresh()

    def refresh(self) -> None:
        if not self._is_alive():
            return
        # Clear old dashboard state first — recompute is total, so no
        # metric from a previous project (or a stale data version) remains.
        while self._layout.count():
            item = self._layout.takeAt(0)
            widget = item.widget()
            if widget:
                self._discard_widget(widget)
            else:
                sublayout = item.layout()
                if sublayout is not None:
                    self._drop_layout(sublayout)
        self._build()

    def _is_alive(self) -> bool:
        """Guard against signals arriving after the C++ widget is gone."""
        try:
            self._layout.count()
            return True
        except RuntimeError:
            return False

    @staticmethod
    def _discard_widget(widget) -> None:
        """Detach a widget synchronously, then schedule its deletion.

        deleteLater() alone defers removal to the event loop, so old
        labels would linger in the widget tree (and on screen) between a
        project switch and the next loop tick. Re-parenting to None
        removes them immediately, guaranteeing no stale metrics remain.
        """
        widget.setParent(None)
        widget.deleteLater()

    def _drop_layout(self, layout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget:
                self._discard_widget(widget)
            elif item.layout() is not None:
                self._drop_layout(item.layout())

    # -- Build ---------------------------------------------------------------

    def _build(self) -> None:
        project = self._db.get_project_by_id(self._project_id)
        scenes = self._db.get_all_scenes(self._project_id)

        self._add_header(project)

        if not scenes:
            self._add_empty_state()
            self._layout.addStretch()
            return

        self._add_progress(scenes)
        self._add_current_work(scenes)
        if (
            len(scenes) >= 3
            and not preferences.get_flag("has_seen_timeline_hint")
        ):
            self._add_timeline_hint()
        self._add_quick_actions()
        self._add_stats(scenes)
        self._layout.addStretch()

    def _add_timeline_hint(self) -> None:
        row = QHBoxLayout()
        row.setSpacing(8)
        tip = QLabel("Tip: open the Timeline to see your story arc.")
        tip.setStyleSheet(
            f"color: {theme.TEXT_SECONDARY}; font-size: 12px;"
        )
        row.addWidget(tip)
        link = QPushButton("Open Timeline")
        link.setFlat(True)
        link.setStyleSheet(
            f"QPushButton {{ color: {theme.LINK_COLOR};"
            f" border: none; padding: 0 4px; font-size: 12px; }}"
            f"QPushButton:hover {{ color: {theme.TEXT_PRIMARY}; }}"
        )
        link.clicked.connect(lambda: self._open_section("timeline"))
        row.addWidget(link)
        row.addStretch()
        self._layout.addLayout(row)

    # -- Header --------------------------------------------------------------

    def _add_header(self, project) -> None:
        box = QVBoxLayout()
        box.setSpacing(4)

        title_text = project.title if project else "Untitled Project"
        title = QLabel(title_text)
        title_font = QFont()
        title_font.setBold(True)
        title_font.setPointSize(title_font.pointSize() + 6)
        title.setFont(title_font)
        title.setStyleSheet(f"color: {theme.TEXT_PRIMARY};")
        box.addWidget(title)

        if project and project.updated_at:
            subtitle = QLabel(
                f"Last edited {project.updated_at.strftime('%b %d, %Y')}"
            )
            subtitle.setStyleSheet(
                f"color: {theme.TEXT_SECONDARY}; font-size: 12px;"
            )
            box.addWidget(subtitle)

        # Narrative engine + writing format — read from the centralized
        # accessors so the Dashboard reflects the project's mode (and updates
        # when the active view is rebuilt after a Project Settings change).
        try:
            from logosforge.project_compat import (
                ENGINE_LABELS,
                FORMAT_LABELS,
                get_project_narrative_engine,
                get_project_writing_format,
            )
            engine = ENGINE_LABELS.get(
                get_project_narrative_engine(project), "Novel")
            fmt = FORMAT_LABELS.get(
                get_project_writing_format(project), "Prose")
            self._mode_label = QLabel(f"{engine}  ·  {fmt}")
            self._mode_label.setObjectName("dashboardModeChip")
            self._mode_label.setStyleSheet(
                f"color: {theme.TEXT_SECONDARY}; font-size: 12px;"
            )
            box.addWidget(self._mode_label)

            # Structural vocabulary for the active writing mode (Phase 9) —
            # makes the project's declared medium visibly active on the
            # Dashboard, e.g. "Structure: Acts / Chapters / Scenes".
            from logosforge.writing_modes import (
                get_project_writing_mode,
                structural_vocabulary,
            )
            mode = get_project_writing_mode(project)
            self._structure_label = QLabel(
                f"Structure: {structural_vocabulary(mode)}"
            )
            self._structure_label.setObjectName("dashboardStructureChip")
            self._structure_label.setStyleSheet(
                f"color: {theme.TEXT_SECONDARY}; font-size: 11px;"
            )
            box.addWidget(self._structure_label)
        except Exception:
            pass

        self._layout.addLayout(box)

    # -- Empty state ---------------------------------------------------------

    def _add_empty_state(self) -> None:
        card = self._make_card()
        theme.apply_card_shadow(card)
        inner = QVBoxLayout(card)
        inner.setContentsMargins(24, 24, 24, 24)
        inner.setSpacing(16)

        heading = QLabel("Your story starts here")
        heading_font = QFont()
        heading_font.setBold(True)
        heading_font.setPointSize(heading_font.pointSize() + 2)
        heading.setFont(heading_font)
        inner.addWidget(heading)

        body = QLabel(
            "No scenes yet. Create your first scene to begin outlining and writing."
        )
        body.setWordWrap(True)
        body.setStyleSheet(f"color: {theme.TEXT_SECONDARY};")
        inner.addWidget(body)

        btn = QPushButton("Create Scene")
        btn.setStyleSheet(theme.primary_btn())
        btn.clicked.connect(lambda: self._open_section("scenes"))

        btn_row = QHBoxLayout()
        btn_row.addWidget(btn)
        btn_row.addStretch()
        inner.addLayout(btn_row)

        self._layout.addWidget(card)

    # -- Progress ------------------------------------------------------------

    def _add_progress(self, scenes) -> None:
        chapters = {s.chapter for s in scenes if s.chapter}
        latest = max(scenes, key=lambda s: s.created_at)
        position = next(
            (i for i, s in enumerate(scenes, 1) if s.id == latest.id), 0
        )

        row = QHBoxLayout()
        row.setSpacing(32)
        row.addLayout(self._stat_block("Scenes", str(len(scenes))))
        row.addLayout(self._stat_block("Chapters", str(len(chapters))))
        if position:
            row.addLayout(
                self._stat_block(
                    "Current position", f"#{position} of {len(scenes)}"
                )
            )
        row.addStretch()
        self._layout.addLayout(row)

    def _stat_block(self, label: str, value: str) -> QVBoxLayout:
        box = QVBoxLayout()
        box.setSpacing(1)

        value_label = QLabel(value)
        value_font = QFont()
        value_font.setBold(True)
        value_font.setPointSize(value_font.pointSize() + 4)
        value_label.setFont(value_font)
        value_label.setStyleSheet(f"color: {theme.TEXT_PRIMARY};")

        label_label = QLabel(label)
        label_label.setStyleSheet(
            f"color: {theme.TEXT_SECONDARY}; font-size: 11px;"
        )

        box.addWidget(value_label)
        box.addWidget(label_label)
        return box

    # -- Current work --------------------------------------------------------

    def _add_current_work(self, scenes) -> None:
        latest = max(scenes, key=lambda s: s.created_at)

        card = QFrame()
        card.setObjectName("heroCard")
        card.setStyleSheet(theme.hero_card_style())
        theme.apply_card_shadow(card)
        inner = QVBoxLayout(card)
        inner.setContentsMargins(28, 24, 28, 24)
        inner.setSpacing(12)

        eyebrow = QLabel("Continue writing")
        eyebrow.setStyleSheet(theme.eyebrow())
        inner.addWidget(eyebrow)

        title = QLabel(latest.title or "Untitled scene")
        title_font = QFont()
        title_font.setBold(True)
        title_font.setPointSize(title_font.pointSize() + 4)
        title.setFont(title_font)
        title.setWordWrap(True)
        inner.addWidget(title)

        if latest.chapter:
            meta = QLabel(latest.chapter)
            meta.setStyleSheet(
                f"color: {theme.TEXT_SECONDARY}; font-size: 12px;"
            )
            inner.addWidget(meta)

        btn = QPushButton("Open Scene")
        btn.setStyleSheet(theme.primary_btn())
        btn.clicked.connect(lambda: self._navigate("Scene", latest.id))

        btn_row = QHBoxLayout()
        btn_row.addWidget(btn)
        btn_row.addStretch()
        inner.addLayout(btn_row)

        self._layout.addWidget(card)

    # -- Quick actions -------------------------------------------------------

    def _add_quick_actions(self) -> None:
        header = QLabel("Quick actions")
        header.setStyleSheet(theme.eyebrow())
        self._layout.addWidget(header)

        row = QHBoxLayout()
        row.setSpacing(8)
        for label, target in (
            ("New Scene", "scenes"),
            ("New Character", "characters"),
            ("Open Timeline", "timeline"),
        ):
            btn = QPushButton(label)
            btn.clicked.connect(
                lambda _=False, t=target: self._open_section(t)
            )
            row.addWidget(btn)
        row.addStretch()
        self._layout.addLayout(row)

    # -- Stats ---------------------------------------------------------------

    def _add_stats(self, scenes) -> None:
        header = QLabel("Stats")
        header.setStyleSheet(theme.eyebrow())
        self._layout.addWidget(header)

        total_words = sum(len((s.content or "").split()) for s in scenes)
        texts = [s.content for s in scenes if s.content and s.content.strip()]
        if texts:
            ratios = [compute_scene_stats(t)["dialogue_ratio"] for t in texts]
            dialogue_pct = round(100 * sum(ratios) / len(ratios))
        else:
            dialogue_pct = None

        rows = [
            ("Total words", f"{total_words:,}"),
            ("Scenes", str(len(scenes))),
        ]
        if dialogue_pct is not None:
            rows.append(("Dialogue", f"{dialogue_pct}%"))

        for label, value in rows:
            line = QHBoxLayout()
            line.setSpacing(12)
            lbl = QLabel(label)
            lbl.setStyleSheet(f"color: {theme.TEXT_SECONDARY};")
            lbl.setMinimumWidth(120)
            val = QLabel(value)
            val.setStyleSheet(f"color: {theme.TEXT_PRIMARY};")
            line.addWidget(lbl)
            line.addWidget(val)
            line.addStretch()
            self._layout.addLayout(line)

    # -- Helpers -------------------------------------------------------------

    def _make_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("dashCard")
        card.setStyleSheet(theme.card_style())
        theme.apply_card_shadow(card)
        return card

    def _navigate(self, entity_type: str, entity_id: int) -> None:
        if self._on_navigate:
            self._on_navigate(entity_type, entity_id)

    def _open_section(self, name: str) -> None:
        if self._on_open_section:
            self._on_open_section(name)
