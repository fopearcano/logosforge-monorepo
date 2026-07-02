"""Mode Strip Widget — compact AI mode indicator with override control."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from logosforge.adaptive_mode import AIMode, ModeResult, compute_mode
from logosforge.db import Database
from logosforge.ui import theme


_MODE_COLORS = {
    AIMode.STRUCTURE: "#6366f1",
    AIMode.BALANCE: "#f59e0b",
    AIMode.REFINEMENT: "#4ade80",
}

_MODE_HINTS = {
    AIMode.STRUCTURE: "Story structure is forming — suggestions focus on building foundation.",
    AIMode.BALANCE: "Structure growing — suggestions focus on evening out distribution.",
    AIMode.REFINEMENT: "Story is mature — suggestions focus on polish and depth.",
}


class ModeStrip(QFrame):
    """Compact mode indicator with dropdown override."""

    def __init__(
        self,
        db: Database,
        project_id: int,
        on_mode_changed: Callable[[AIMode | None], None] | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._db = db
        self._project_id = project_id
        self._on_mode_changed = on_mode_changed
        self._override: AIMode | None = None
        self._mode_result: ModeResult | None = None

        self.setObjectName("modeStrip")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(2)

        top_row = QHBoxLayout()
        top_row.setSpacing(6)

        self._dot = QWidget()
        self._dot.setFixedSize(6, 6)
        self._dot.setObjectName("modeStripDot")
        top_row.addWidget(self._dot, alignment=Qt.AlignmentFlag.AlignVCenter)

        self._mode_label = QPushButton()
        self._mode_label.setObjectName("modeStripLabel")
        self._mode_label.setFlat(True)
        self._mode_label.setCursor(Qt.CursorShape.PointingHandCursor)

        menu = QMenu(self)
        menu.addAction("Auto", self._set_auto)
        menu.addSeparator()
        menu.addAction("Structure", lambda: self._set_override(AIMode.STRUCTURE))
        menu.addAction("Balance", lambda: self._set_override(AIMode.BALANCE))
        menu.addAction("Refinement", lambda: self._set_override(AIMode.REFINEMENT))
        self._mode_label.setMenu(menu)
        top_row.addWidget(self._mode_label)

        top_row.addStretch()

        self._reset_btn = QPushButton("Reset")
        self._reset_btn.setObjectName("modeStripReset")
        self._reset_btn.setFlat(True)
        self._reset_btn.clicked.connect(self._set_auto)
        self._reset_btn.setVisible(False)
        top_row.addWidget(self._reset_btn)

        layout.addLayout(top_row)

        self._hint_label = QLabel()
        self._hint_label.setObjectName("modeStripHint")
        self._hint_label.setWordWrap(True)
        layout.addWidget(self._hint_label)

        self.refresh()

    def set_project(self, project_id: int) -> None:
        """Re-point at a new project: clear any manual override (it must not
        carry across projects) and recompute from the new project's state."""
        self._project_id = project_id
        self._override = None
        self.refresh()

    def refresh(self) -> None:
        """Recompute mode from project state."""
        self._mode_result = compute_mode(self._db, self._project_id)
        self._update_display()

    def get_effective_mode(self) -> AIMode:
        """Return the active mode (override or auto-detected)."""
        if self._override is not None:
            return self._override
        if self._mode_result is not None:
            return self._mode_result.mode
        return AIMode.STRUCTURE

    def get_mode_result(self) -> ModeResult | None:
        return self._mode_result

    def is_overridden(self) -> bool:
        return self._override is not None

    def _set_override(self, mode: AIMode) -> None:
        self._override = mode
        self._update_display()
        if self._on_mode_changed:
            self._on_mode_changed(mode)

    def _set_auto(self) -> None:
        self._override = None
        self._update_display()
        if self._on_mode_changed:
            self._on_mode_changed(None)

    def _update_display(self) -> None:
        mode = self.get_effective_mode()
        color = _MODE_COLORS.get(mode, "#9ca3af")

        self._dot.setStyleSheet(
            f"background-color: {color}; border-radius: 3px;"
        )

        suffix = " (manual)" if self._override else " ▾"
        self._mode_label.setText(f"{mode.value}{suffix}")
        self._mode_label.setStyleSheet(
            f"QPushButton {{ color: {color}; font-size: 11px; font-weight: bold;"
            f" border: none; padding: 0; text-align: left; }}"
            f"QPushButton:hover {{ color: {theme.TEXT_PRIMARY}; }}"
            f"QPushButton::menu-indicator {{ width: 0; height: 0; }}"
        )

        self._hint_label.setText(_MODE_HINTS.get(mode, ""))
        self._reset_btn.setVisible(self._override is not None)
