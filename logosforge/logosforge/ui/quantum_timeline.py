"""Quantum Timeline Superposition — canon scenes + active branches in parallel."""

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from logosforge.quantum_outliner.scoring import (
    DEFAULT_WEIGHTS,
    FACTOR_LABELS,
    PRESET_NAMES,
    SCORING_PRESETS,
)
from logosforge.quantum_outliner.state import OutlineMode, get_state
from logosforge.ui import theme

if TYPE_CHECKING:
    from logosforge.db import Database


_WEIGHT_DISPLAY: dict[str, str] = {
    "structure_fit": "Structure",
    "psyke_consistency": "PSYKE",
    "tension_gain": "Tension",
    "novelty": "Novelty",
    "goal_alignment": "Goal",
}


class ScoringWeightsPopover(QFrame):
    """Compact popover with preset dropdown and sliders for scoring weights."""

    weights_changed = Signal(dict)
    preset_changed = Signal(str)

    def __init__(
        self,
        weights: dict[str, float],
        preset: str = "Balanced",
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("weightsPopover")
        self.setWindowFlags(Qt.WindowType.Popup)
        self.setFixedWidth(230)

        self._sliders: dict[str, QSlider] = {}
        self._value_labels: dict[str, QLabel] = {}
        self._weights = dict(weights)
        self._applying_preset = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)

        title = QLabel("Scoring Weights")
        title.setObjectName("weightsTitle")
        layout.addWidget(title)

        self._preset_combo = QComboBox()
        self._preset_combo.setObjectName("weightsPresetCombo")
        for name in PRESET_NAMES:
            self._preset_combo.addItem(name)
        self._preset_combo.addItem("Custom")
        idx = PRESET_NAMES.index(preset) if preset in PRESET_NAMES else len(PRESET_NAMES)
        self._preset_combo.setCurrentIndex(idx)
        self._preset_combo.currentIndexChanged.connect(self._on_preset_selected)
        layout.addWidget(self._preset_combo)

        for key in DEFAULT_WEIGHTS:
            row = QHBoxLayout()
            row.setSpacing(6)

            label = QLabel(_WEIGHT_DISPLAY.get(key, key))
            label.setToolTip(FACTOR_LABELS.get(key, key))
            label.setFixedWidth(58)
            row.addWidget(label)

            slider = QSlider(Qt.Orientation.Horizontal)
            slider.setRange(0, 100)
            slider.setValue(int(self._weights.get(key, 0.0) * 100))
            slider.setObjectName(f"weightSlider_{key}")
            self._sliders[key] = slider
            row.addWidget(slider, stretch=1)

            val_lbl = QLabel(f"{self._weights.get(key, 0.0):.0%}")
            val_lbl.setObjectName("weightsValue")
            val_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self._value_labels[key] = val_lbl
            row.addWidget(val_lbl)

            layout.addLayout(row)

            slider.valueChanged.connect(self._on_slider_changed)

        reset_row = QHBoxLayout()
        reset_row.addStretch()
        reset_btn = QPushButton("Reset")
        reset_btn.setObjectName("weightsBtn")
        reset_btn.clicked.connect(self._reset_defaults)
        reset_row.addWidget(reset_btn)
        layout.addLayout(reset_row)

    def _on_preset_selected(self, index: int) -> None:
        name = self._preset_combo.currentText()
        if name == "Custom" or name not in SCORING_PRESETS:
            return
        self._apply_weights(SCORING_PRESETS[name])
        self.preset_changed.emit(name)

    def _apply_weights(self, weights: dict[str, float]) -> None:
        self._applying_preset = True
        for key, slider in self._sliders.items():
            slider.blockSignals(True)
            slider.setValue(int(weights.get(key, 0.0) * 100))
            slider.blockSignals(False)
        self._applying_preset = False
        self._weights = dict(weights)
        for k, lbl in self._value_labels.items():
            lbl.setText(f"{weights[k]:.0%}")
        self.weights_changed.emit(dict(weights))

    def _on_slider_changed(self) -> None:
        if self._applying_preset:
            return

        raw = {k: s.value() for k, s in self._sliders.items()}
        total = sum(raw.values())
        if total == 0:
            normalized = {k: 1.0 / len(raw) for k in raw}
        else:
            normalized = {k: round(v / total, 4) for k, v in raw.items()}

        self._weights = normalized
        for k, lbl in self._value_labels.items():
            lbl.setText(f"{normalized[k]:.0%}")

        self._preset_combo.blockSignals(True)
        self._preset_combo.setCurrentIndex(len(PRESET_NAMES))
        self._preset_combo.blockSignals(False)
        self.preset_changed.emit("Custom")

        self.weights_changed.emit(dict(normalized))

    def _reset_defaults(self) -> None:
        self._preset_combo.blockSignals(True)
        self._preset_combo.setCurrentIndex(0)
        self._preset_combo.blockSignals(False)
        self._apply_weights(DEFAULT_WEIGHTS)
        self.preset_changed.emit("Balanced")

    def get_weights(self) -> dict[str, float]:
        return dict(self._weights)

    def get_preset(self) -> str:
        return self._preset_combo.currentText()


class QuantumTimelineWidget(QWidget):
    """Canon timeline with quantum branch lanes beneath linked scenes."""

    branch_selected = Signal(str, str)
    collapse_requested = Signal(str, str)
    archive_requested = Signal(str)

    def __init__(self, db: "Database", project_id: int) -> None:
        super().__init__()
        self._db = db
        self._project_id = project_id
        self._selected_wf: str | None = None
        self._selected_branch: str | None = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        strip_row = QHBoxLayout()
        strip_row.setContentsMargins(0, 0, 0, 0)
        strip_row.setSpacing(0)

        self._mode_strip = QLabel()
        self._mode_strip.setObjectName("qtlModeStrip")
        self._mode_strip.setFixedHeight(16)
        self._mode_strip.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self._mode_strip.setVisible(False)
        strip_row.addWidget(self._mode_strip, stretch=1)

        self._weights_btn = QPushButton("Weights")
        self._weights_btn.setObjectName("weightsBtn")
        self._weights_btn.setFixedHeight(16)
        self._weights_btn.setVisible(False)
        self._weights_btn.clicked.connect(self._show_weights_popover)
        strip_row.addWidget(self._weights_btn)

        outer.addLayout(strip_row)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setObjectName("qtlScroll")
        self._scroll.setFixedHeight(0)
        outer.addWidget(self._scroll)

        self._container = QWidget()
        self._container.setObjectName("qtlContainer")
        self._h_layout = QHBoxLayout(self._container)
        self._h_layout.setContentsMargins(4, 4, 4, 4)
        self._h_layout.setSpacing(0)
        self._h_layout.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self._scroll.setWidget(self._container)

        self._empty_label = QLabel(
            "Generate possibilities to view timeline superposition."
        )
        self._empty_label.setObjectName("qtlEmpty")
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.addWidget(self._empty_label)

    def refresh(self) -> None:
        self._clear()
        scenes = self._db.get_all_scenes(self._project_id)
        state = get_state(self._project_id)
        is_lambda = state.outline_mode is OutlineMode.LAMBDA

        self._update_mode_strip(state)

        wf_by_scene: dict[int | None, list] = defaultdict(list)
        for wf in state.wavefunctions.values():
            wf_by_scene[wf.source_scene_id].append(wf)

        has_wavefunctions = bool(state.wavefunctions)

        if not has_wavefunctions:
            self._empty_label.setVisible(True)
            self._scroll.setFixedHeight(0)
            return

        self._empty_label.setVisible(False)

        max_branch_rows = 0
        for scene in scenes:
            wfs = wf_by_scene.get(scene.id, [])
            if is_lambda:
                col = self._build_scene_column(scene, wfs)
            else:
                col = self._build_classical_column(scene, wfs)
            self._h_layout.addWidget(col)
            self._h_layout.addSpacing(2)
            if is_lambda:
                for wf in wfs:
                    branch_count = len(wf.branches)
                    if branch_count > max_branch_rows:
                        max_branch_rows = branch_count

        unlinked = wf_by_scene.get(None, [])
        if unlinked and is_lambda:
            col = self._build_unlinked_column(unlinked)
            self._h_layout.addWidget(col)
            for wf in unlinked:
                branch_count = len(wf.branches)
                if branch_count > max_branch_rows:
                    max_branch_rows = branch_count

        self._h_layout.addStretch()

        if is_lambda:
            height = 28 + max(max_branch_rows, 1) * 52 + 8
        else:
            height = 54
        self._scroll.setFixedHeight(min(height, 260))

    def _update_mode_strip(self, state) -> None:
        is_lambda = state.outline_mode is OutlineMode.LAMBDA
        if is_lambda:
            self._mode_strip.setText("  Lambda · branching timeline")
            self._mode_strip.setStyleSheet(
                f"color: {theme.ACCENT_DIM}; font-size: 9px; font-weight: bold;"
                f" background: {theme.BG_DARK}; padding-left: 6px;"
            )
        else:
            self._mode_strip.setText("  Classical · linear timeline")
            self._mode_strip.setStyleSheet(
                f"color: {theme.TEXT_MUTED}; font-size: 9px;"
                f" background: {theme.BG_DARK}; padding-left: 6px;"
            )
        has_wfs = bool(state.wavefunctions)
        self._mode_strip.setVisible(has_wfs)
        self._weights_btn.setVisible(has_wfs and is_lambda)

    def _clear(self) -> None:
        while self._h_layout.count():
            item = self._h_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

    # --- Classical columns (single row, beat markers only) ---

    def _build_classical_column(self, scene, wavefunctions: list) -> QFrame:
        col = QFrame()
        col.setObjectName("qtlColumn")
        col.setFixedWidth(140)
        col.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Minimum)

        layout = QVBoxLayout(col)
        layout.setContentsMargins(4, 3, 4, 3)
        layout.setSpacing(2)

        title_text = scene.title or "Untitled"
        if len(title_text) > 20:
            title_text = title_text[:18] + "…"
        title = QLabel(title_text)
        title.setObjectName("qtlSceneTitle")
        title.setToolTip(scene.title or "")
        layout.addWidget(title)

        beat_marker = self._extract_beat_marker(wavefunctions)
        if beat_marker:
            marker_lbl = QLabel(beat_marker)
            marker_lbl.setObjectName("qtlBeatMarker")
            marker_lbl.setToolTip(beat_marker)
            layout.addWidget(marker_lbl)

        layout.addStretch()
        return col

    # --- Lambda columns (full branch fans + uncertainty) ---

    def _build_scene_column(self, scene, wavefunctions: list) -> QFrame:
        col = QFrame()
        col.setObjectName("qtlColumn")
        col.setFixedWidth(140)
        col.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Minimum)

        layout = QVBoxLayout(col)
        layout.setContentsMargins(4, 3, 4, 3)
        layout.setSpacing(2)

        title_text = scene.title or "Untitled"
        if len(title_text) > 20:
            title_text = title_text[:18] + "…"
        title = QLabel(title_text)
        title.setObjectName("qtlSceneTitle")
        title.setToolTip(scene.title or "")
        layout.addWidget(title)

        beat_marker = self._extract_beat_marker(wavefunctions)
        if beat_marker:
            marker_lbl = QLabel(beat_marker)
            marker_lbl.setObjectName("qtlBeatMarker")
            marker_lbl.setToolTip(beat_marker)
            layout.addWidget(marker_lbl)

        if wavefunctions:
            for wf in wavefunctions:
                active_count = len(wf.branches)
                if active_count >= 2 and not wf.is_collapsed():
                    uz = QLabel(f"⟨ψ⟩ {active_count} paths")
                    uz.setObjectName("qtlUncertainty")
                    uz.setToolTip(
                        f"Uncertainty zone: {active_count} branches in superposition"
                    )
                    layout.addWidget(uz)
                lane = self._build_branch_lane(wf)
                layout.addWidget(lane)
        else:
            spacer = QLabel("")
            spacer.setFixedHeight(4)
            layout.addWidget(spacer)

        layout.addStretch()
        return col

    def _build_unlinked_column(self, wavefunctions: list) -> QFrame:
        col = QFrame()
        col.setObjectName("qtlColumn")
        col.setFixedWidth(140)
        col.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Minimum)

        layout = QVBoxLayout(col)
        layout.setContentsMargins(4, 3, 4, 3)
        layout.setSpacing(2)

        title = QLabel("(unlinked)")
        title.setObjectName("qtlSceneTitle")
        title.setStyleSheet(f"color: {theme.TEXT_MUTED}; font-style: italic;")
        layout.addWidget(title)

        for wf in wavefunctions:
            active_count = len(wf.branches)
            if active_count >= 2 and not wf.is_collapsed():
                uz = QLabel(f"⟨ψ⟩ {active_count} paths")
                uz.setObjectName("qtlUncertainty")
                layout.addWidget(uz)
            lane = self._build_branch_lane(wf)
            layout.addWidget(lane)

        layout.addStretch()
        return col

    def _build_branch_lane(self, wf) -> QWidget:
        lane = QWidget()
        lane_layout = QVBoxLayout(lane)
        lane_layout.setContentsMargins(0, 1, 0, 1)
        lane_layout.setSpacing(1)

        for branch in wf.branches:
            node = self._build_branch_node(wf, branch)
            lane_layout.addWidget(node)

        return lane

    def _build_branch_node(self, wf, branch) -> QFrame:
        is_collapsed = wf.collapsed_branch_id == branch.id
        is_archived = wf.is_collapsed() and not is_collapsed
        is_selected = (
            self._selected_wf == wf.id and self._selected_branch == branch.id
        )

        node = QFrame()
        node.setObjectName("qtlBranch")
        node.setCursor(Qt.CursorShape.PointingHandCursor)
        node.setFixedWidth(130)
        node.setProperty("wf_id", wf.id)
        node.setProperty("branch_id", branch.id)

        prob = branch.probability
        show_prob = prob > 0 and not is_collapsed and not is_archived

        if is_collapsed:
            status = "collapsed"
            border_color = theme.ACCENT
            bg = theme.get("SELECTION_BG")
        elif is_archived:
            status = "archived"
            border_color = theme.TEXT_MUTED
            bg = theme.BG_DARK
        elif is_selected:
            status = "selected"
            border_color = theme.ACCENT_DIM
            bg = theme.BG_HOVER
        else:
            status = "active"
            border_color = self._prob_border_color(prob) if show_prob else theme.BORDER
            bg = theme.BG_INPUT

        node.setStyleSheet(
            f"QFrame#qtlBranch {{"
            f"  background: {bg};"
            f"  border: 1px solid {border_color};"
            f"  border-radius: 4px;"
            f"}}"
        )

        layout = QVBoxLayout(node)
        layout.setContentsMargins(4, 3, 4, 3)
        layout.setSpacing(1)

        top_row = QHBoxLayout()
        top_row.setSpacing(3)

        title_text = branch.title or "Branch"
        if len(title_text) > 16:
            title_text = title_text[:14] + "…"
        title_lbl = QLabel(title_text)
        title_lbl.setObjectName("qtlBranchTitle")
        title_lbl.setToolTip(branch.title)
        top_row.addWidget(title_lbl, stretch=1)

        if show_prob:
            prob_lbl = QLabel(f"{prob:.0%}")
            prob_lbl.setObjectName("qtlProbLabel")
            prob_lbl.setToolTip(
                f"Probability: {prob:.1%}"
                + (f"\nScore: {branch.score:.2f}" if branch.score else "")
            )
            top_row.addWidget(prob_lbl)

        badge = QLabel(self._status_badge(status))
        badge.setObjectName("qtlBadge")
        badge.setStyleSheet(self._badge_style(status))
        top_row.addWidget(badge)

        layout.addLayout(top_row)

        meta_row = QHBoxLayout()
        meta_row.setSpacing(3)
        meta_row.setContentsMargins(0, 0, 0, 0)

        if branch.structure_beat:
            beat_text = branch.structure_beat
            if len(beat_text) > 14:
                beat_text = beat_text[:12] + "…"
            beat_lbl = QLabel(beat_text)
            beat_lbl.setObjectName("qtlBranchBeat")
            beat_lbl.setToolTip(f"Beat: {branch.structure_beat}")
            meta_row.addWidget(beat_lbl)

        if branch.branch_type:
            type_lbl = QLabel(self._branch_type_short(branch.branch_type))
            type_lbl.setObjectName("qtlBranchType")
            type_lbl.setStyleSheet(self._branch_type_style(branch.branch_type))
            type_lbl.setToolTip(branch.branch_type)
            meta_row.addWidget(type_lbl)

        meta_row.addStretch()
        if meta_row.count() > 1:
            layout.addLayout(meta_row)

        if branch.stakes:
            stakes_text = branch.stakes
            if len(stakes_text) > 30:
                stakes_text = stakes_text[:28] + "…"
            stakes_lbl = QLabel(stakes_text)
            stakes_lbl.setObjectName("qtlBranchMeta")
            stakes_lbl.setToolTip(branch.stakes)
            layout.addWidget(stakes_lbl)

        if branch.consequence:
            cons_text = branch.consequence
            if len(cons_text) > 30:
                cons_text = cons_text[:28] + "…"
            cons_lbl = QLabel(cons_text)
            cons_lbl.setObjectName("qtlBranchMeta")
            cons_lbl.setToolTip(branch.consequence)
            layout.addWidget(cons_lbl)

        if show_prob:
            bar = QFrame()
            bar.setObjectName("qtlProbBar")
            bar_width = max(int(prob * 122), 2)
            bar.setFixedSize(bar_width, 2)
            bar_color = self._prob_bar_color(prob)
            bar.setStyleSheet(
                f"QFrame#qtlProbBar {{"
                f"  background: {bar_color};"
                f"  border: none; border-radius: 1px;"
                f"}}"
            )
            layout.addWidget(bar)

        node.mousePressEvent = lambda ev, w=wf.id, b=branch.id: self._on_branch_click(ev, w, b)

        return node

    @staticmethod
    def _prob_bar_color(prob: float) -> str:
        if prob >= 0.4:
            return theme.ACCENT
        if prob >= 0.2:
            return theme.ACCENT_DIM
        return theme.TEXT_MUTED

    @staticmethod
    def _prob_border_color(prob: float) -> str:
        if prob >= 0.4:
            return theme.ACCENT_DIM
        if prob >= 0.2:
            return theme.BORDER_FOCUS if hasattr(theme, "BORDER_FOCUS") else theme.ACCENT_DIM
        return theme.BORDER

    def _on_branch_click(self, event, wf_id: str, branch_id: str) -> None:
        if event.button() == Qt.MouseButton.RightButton:
            self._show_branch_menu(event, wf_id, branch_id)
            return
        self._selected_wf = wf_id
        self._selected_branch = branch_id
        self.branch_selected.emit(wf_id, branch_id)
        self.refresh()

    def _show_branch_menu(self, event, wf_id: str, branch_id: str) -> None:
        state = get_state(self._project_id)
        wf = state.get(wf_id)
        if wf is None:
            return

        menu = QMenu(self)

        if not wf.is_collapsed():
            menu.addAction(
                "Collapse this branch",
                lambda: self._confirm_collapse(wf_id, branch_id),
            )

        menu.addAction(
            "Archive wavefunction",
            lambda: self.archive_requested.emit(wf_id),
        )

        menu.exec(event.globalPosition().toPoint())

    def _confirm_collapse(self, wf_id: str, branch_id: str) -> None:
        state = get_state(self._project_id)
        wf = state.get(wf_id)
        if wf is None:
            return
        branch = wf.get_branch(branch_id)
        title = branch.title if branch else branch_id

        reply = QMessageBox.question(
            self,
            "Collapse Branch",
            f"Collapse wavefunction to \"{title}\"?\n\n"
            "This commits this branch as canonical and archives the rest.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.collapse_requested.emit(wf_id, branch_id)

    def _show_weights_popover(self) -> None:
        weights = self._db.get_scoring_weights(self._project_id)
        preset = self._db.get_scoring_preset(self._project_id)
        popover = ScoringWeightsPopover(weights, preset=preset, parent=self)
        popover.weights_changed.connect(self._on_weights_changed)
        popover.preset_changed.connect(self._on_preset_changed)
        btn_pos = self._weights_btn.mapToGlobal(
            self._weights_btn.rect().bottomRight()
        )
        popover.move(btn_pos.x() - popover.width(), btn_pos.y() + 2)
        popover.show()

    def _on_weights_changed(self, weights: dict) -> None:
        self._db.set_scoring_weights(self._project_id, weights)

    def _on_preset_changed(self, preset: str) -> None:
        self._db.set_scoring_preset(self._project_id, preset)

    @staticmethod
    def _status_badge(status: str) -> str:
        return {
            "active": "○",
            "selected": "◉",
            "collapsed": "●",
            "archived": "◌",
        }.get(status, "")

    @staticmethod
    def _badge_style(status: str) -> str:
        color = {
            "active": theme.TEXT_MUTED,
            "selected": theme.ACCENT_DIM,
            "collapsed": theme.ACCENT,
            "archived": theme.TEXT_MUTED,
        }.get(status, theme.TEXT_MUTED)
        return (
            f"QLabel {{ color: {color}; font-size: 10px;"
            f" background: transparent; padding: 0; }}"
        )

    @staticmethod
    def _extract_beat_marker(wavefunctions: list) -> str:
        """Build a compact beat marker from wavefunctions linked to a scene."""
        parts: list[str] = []
        seen: set[str] = set()
        for wf in wavefunctions:
            if wf.structure_method and wf.structure_method not in seen:
                seen.add(wf.structure_method)
                method_short = wf.structure_method
                if len(method_short) > 16:
                    method_short = method_short[:14] + "…"
                if wf.structure_beat:
                    parts.append(f"{method_short} → {wf.structure_beat}")
                else:
                    parts.append(method_short)
        return " | ".join(parts)

    @staticmethod
    def _branch_type_short(branch_type: str) -> str:
        return {
            "deviation": "dev",
            "alternative": "alt",
            "intensification": "int",
            "resolution": "res",
        }.get(branch_type, branch_type[:3])

    @staticmethod
    def _branch_type_style(branch_type: str) -> str:
        color = {
            "deviation": "#e06c75",
            "alternative": "#61afef",
            "intensification": "#e5c07b",
            "resolution": "#98c379",
        }.get(branch_type, theme.TEXT_MUTED)
        return (
            f"QLabel {{ color: {color}; font-size: 8px; font-weight: bold;"
            f" background: transparent; padding: 0 2px; }}"
        )
