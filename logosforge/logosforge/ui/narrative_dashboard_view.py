"""Narrative Dashboard view — visual story intelligence at a glance.

Assembles the four dashboard panels (tension curve, character presence,
act distribution, theme continuity) into a scrollable layout with section
headers, flag summaries, and click-to-navigate-to-scene support.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from logosforge.db import Database
from logosforge.narrative_dashboard import (
    NarrativeDashboardData,
    compute_dashboard,
)
from logosforge.ui import theme
from logosforge.ui.dashboard_widgets import (
    CharacterPresencePanel,
    StructurePanel,
    TensionCurvePanel,
    ThemeContinuityPanel,
)


class NarrativeDashboardView(QWidget):
    """Top-level view that hosts all four narrative panels."""

    def __init__(
        self,
        db: Database,
        project_id: int,
        on_scene_selected: Callable[[int], None] | None = None,
    ) -> None:
        super().__init__()
        self._db = db
        self._project_id = project_id
        self._on_scene_selected = on_scene_selected
        self._data: NarrativeDashboardData | None = None

        self._build_ui()
        self._compute_and_populate()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff,
        )
        outer.addWidget(scroll)

        canvas = QWidget()
        canvas.setObjectName("narrativeDashboard")
        layout = QVBoxLayout(canvas)
        layout.setContentsMargins(24, 24, 24, 32)
        layout.setSpacing(8)

        title = QLabel("Narrative Dashboard")
        title.setObjectName("narrativeDashboardTitle")
        layout.addWidget(title)

        subtitle = QLabel("Story structure, tension, character presence, and themes.")
        subtitle.setObjectName("narrativeDashboardSubtitle")
        layout.addWidget(subtitle)
        layout.addSpacing(12)

        # -- Flags summary
        self._flags_container = QWidget()
        self._flags_container.setObjectName("narrativeFlags")
        self._flags_layout = QVBoxLayout(self._flags_container)
        self._flags_layout.setContentsMargins(12, 8, 12, 8)
        self._flags_layout.setSpacing(2)
        self._flags_container.hide()
        layout.addWidget(self._flags_container)
        layout.addSpacing(8)

        # -- Tension curve
        layout.addWidget(self._section_header("Tension Curve"))
        tension_help = QLabel(
            "Tension (0–100) ≈ character presence + relationships + "
            "dramatic keywords + character progressions "
            "(each contributes up to 25 points)."
        )
        tension_help.setObjectName("narrativeDashboardSubtitle")
        tension_help.setWordWrap(True)
        layout.addWidget(tension_help)
        self._tension_panel = TensionCurvePanel()
        self._tension_panel.scene_clicked.connect(self._on_scene_click)
        layout.addWidget(self._tension_panel)
        layout.addSpacing(16)

        # -- Character presence
        layout.addWidget(self._section_header("Character Presence"))
        self._char_label = QLabel("Click a name to toggle visibility.")
        self._char_label.setObjectName("narrativeDashboardHint")
        layout.addWidget(self._char_label)
        self._char_panel = CharacterPresencePanel()
        self._char_panel.scene_clicked.connect(self._on_scene_click)
        layout.addWidget(self._char_panel)
        layout.addSpacing(16)

        # -- Act structure
        layout.addWidget(self._section_header("Act / Structure Distribution"))
        self._structure_caveat = QLabel("")
        self._structure_caveat.setObjectName("narrativeDashboardHint")
        self._structure_caveat.setWordWrap(True)
        self._structure_caveat.hide()
        layout.addWidget(self._structure_caveat)
        self._structure_panel = StructurePanel()
        layout.addWidget(self._structure_panel)
        layout.addSpacing(16)

        # -- Theme continuity
        layout.addWidget(self._section_header("Theme Continuity"))
        self._theme_label = QLabel("Click a name to toggle visibility.")
        self._theme_label.setObjectName("narrativeDashboardHint")
        layout.addWidget(self._theme_label)
        self._theme_panel = ThemeContinuityPanel()
        self._theme_panel.scene_clicked.connect(self._on_scene_click)
        layout.addWidget(self._theme_panel)

        layout.addStretch()
        scroll.setWidget(canvas)

        self._apply_style()

    @staticmethod
    def _section_header(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("narrativeSectionHeader")
        return label

    def _apply_style(self) -> None:
        style = (
            f"#narrativeDashboard {{"
            f"  background-color: {theme.BG_DARK};"
            f"}}"
            f"#narrativeDashboardTitle {{"
            f"  color: {theme.TEXT_PRIMARY};"
            f"  font-size: 20px;"
            f"  font-weight: bold;"
            f"  background: transparent;"
            f"}}"
            f"#narrativeDashboardSubtitle {{"
            f"  color: {theme.TEXT_MUTED};"
            f"  font-size: 12px;"
            f"  background: transparent;"
            f"}}"
            f"#narrativeSectionHeader {{"
            f"  color: {theme.TEXT_SECONDARY};"
            f"  font-size: 13px;"
            f"  font-weight: bold;"
            f"  background: transparent;"
            f"  padding: 6px 0 2px 0;"
            f"}}"
            f"#narrativeDashboardHint {{"
            f"  color: {theme.TEXT_MUTED};"
            f"  font-size: 10px;"
            f"  background: transparent;"
            f"  font-style: italic;"
            f"}}"
            f"#narrativeFlags {{"
            f"  background: {theme.BG_PANEL};"
            f"  border: 1px solid {theme.BORDER};"
            f"  border-radius: 6px;"
            f"}}"
        )
        self.setStyleSheet(style)

    def _compute_and_populate(self) -> None:
        self._data = compute_dashboard(self._db, self._project_id)

        self._tension_panel.set_data(self._data.tension)
        self._char_panel.set_data(self._data.characters)
        self._structure_panel.set_data(self._data.structure)
        if self._data.structure.inferred and self._data.structure.segments:
            self._structure_caveat.setText(
                "Acts inferred by word count — no explicit Act labels in this "
                "project. Assign Acts to scenes for an accurate breakdown."
            )
            self._structure_caveat.show()
        else:
            self._structure_caveat.hide()
        self._theme_panel.set_data(self._data.themes)

        if not self._data.characters:
            self._char_label.setText(
                "No characters found. Add character entries in PSYKE.",
            )
        if not self._data.themes:
            self._theme_label.setText(
                "No themes found. Add theme entries in PSYKE.",
            )

        self._populate_flags()

    def _populate_flags(self) -> None:
        while self._flags_layout.count():
            item = self._flags_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        all_flags: list[str] = []
        if self._data:
            all_flags.extend(self._data.tension.flags)
            for cp in self._data.characters:
                for f in cp.flags:
                    all_flags.append(f"{cp.name}: {f}")
            all_flags.extend(self._data.structure.flags)
            for tp in self._data.themes:
                for f in tp.flags:
                    all_flags.append(f"Theme «{tp.name}»: {f}")

        if all_flags:
            header = QLabel("Flags")
            header.setStyleSheet(
                f"color: {theme.STATUS_ERR}; font-size: 11px;"
                " font-weight: bold; background: transparent;"
            )
            self._flags_layout.addWidget(header)
            for flag_text in all_flags[:10]:
                lbl = QLabel(f"  {flag_text}")
                lbl.setStyleSheet(
                    f"color: {theme.TEXT_SECONDARY}; font-size: 11px;"
                    " background: transparent;"
                )
                lbl.setWordWrap(True)
                self._flags_layout.addWidget(lbl)
            self._flags_container.show()
        else:
            self._flags_container.hide()

    def _on_scene_click(self, scene_id: int) -> None:
        if self._on_scene_selected:
            self._on_scene_selected(scene_id)

    # -- Public API -----------------------------------------------------------

    def refresh(self) -> None:
        self._compute_and_populate()

    @property
    def data(self) -> NarrativeDashboardData | None:
        return self._data
