"""Mode Suggestions View — shows current AI mode and mode-specific suggestions."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from logosforge.adaptive_mode import AIMode, ModeResult
from logosforge.db import Database
from logosforge.mode_suggestions import ModeSuggestion, generate_mode_suggestions


_MODE_COLORS = {
    AIMode.STRUCTURE: "#6366f1",
    AIMode.BALANCE: "#f59e0b",
    AIMode.REFINEMENT: "#4ade80",
}


class _SuggestionRow(QFrame):
    """Single suggestion row with mode-colored dot."""

    def __init__(self, suggestion: ModeSuggestion, color: str, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("modeSuggestionRow")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(8)

        dot = QWidget()
        dot.setFixedSize(6, 6)
        dot.setStyleSheet(
            f"background-color: {color}; border-radius: 3px;"
        )
        layout.addWidget(dot, alignment=Qt.AlignmentFlag.AlignVCenter)

        text = QLabel(suggestion.text)
        text.setObjectName("modeSuggestionText")
        text.setWordWrap(True)
        layout.addWidget(text, stretch=1)


class ModeSuggestionsView(QWidget):
    """Displays current AI mode and mode-appropriate suggestions."""

    def __init__(
        self,
        db: Database,
        project_id: int,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._db = db
        self._project_id = project_id
        self._mode_result: ModeResult | None = None
        self._suggestions: list[ModeSuggestion] = []

        self.setObjectName("modeSuggestionsView")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        title = QLabel("Adapt")
        title.setObjectName("modeSuggestionsTitle")
        layout.addWidget(title)

        intro = QLabel(
            "Logosforge adapts the Assistant's focus to your story's stage — "
            "this is the current AI mode and what it suggests next."
        )
        intro.setObjectName("modeSuggestionsIntro")
        intro.setWordWrap(True)
        intro.setStyleSheet("color: #94a3b8; font-size: 12px;")
        layout.addWidget(intro)

        self._mode_badge = QLabel()
        self._mode_badge.setObjectName("modeBadge")
        layout.addWidget(self._mode_badge)

        self._mode_desc = QLabel()
        self._mode_desc.setObjectName("modeDescription")
        self._mode_desc.setWordWrap(True)
        layout.addWidget(self._mode_desc)

        self._stage_label = QLabel()
        self._stage_label.setObjectName("modeStageLabel")
        layout.addWidget(self._stage_label)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setObjectName("modeSeparator")
        layout.addWidget(sep)

        suggestions_header = QLabel("Suggestions")
        suggestions_header.setObjectName("modeSuggestionsHeader")
        layout.addWidget(suggestions_header)

        self._content = QWidget()
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(0, 0, 0, 0)
        self._content_layout.setSpacing(4)
        layout.addWidget(self._content)
        layout.addStretch()

        self.refresh()

    def refresh(self) -> None:
        self._mode_result, self._suggestions = generate_mode_suggestions(
            self._db, self._project_id
        )
        self._rebuild()

    def _rebuild(self) -> None:
        if self._mode_result is None:
            return

        mode = self._mode_result.mode
        color = _MODE_COLORS.get(mode, "#9ca3af")

        self._mode_badge.setText(self._mode_result.mode_name)
        self._mode_badge.setStyleSheet(
            f"color: {color}; font-size: 18px; font-weight: bold; background: transparent;"
        )
        self._mode_desc.setText(self._mode_result.description)
        self._stage_label.setText(
            f"Stage: {self._mode_result.stage.value} \u2022 "
            f"Health: {self._mode_result.health.value}"
        )

        layout = self._content_layout
        while layout.count():
            child = layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        if not self._suggestions:
            empty = QLabel("No suggestions at this time.")
            empty.setObjectName("modeSuggestionsEmpty")
            layout.addWidget(empty)
            return

        for suggestion in self._suggestions:
            row = _SuggestionRow(suggestion, color)
            layout.addWidget(row)

    def get_mode_result(self) -> ModeResult | None:
        return self._mode_result

    def get_suggestions(self) -> list[ModeSuggestion]:
        return self._suggestions
