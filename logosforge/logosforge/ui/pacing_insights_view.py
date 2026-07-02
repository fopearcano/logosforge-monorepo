"""Pacing & Insight View — non-intrusive insight panel."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from logosforge.db import Database
from logosforge.pacing_insights import (
    MIN_SCENES,
    Insight,
    generate_insights,
    insight_color,
)


class _InsightRow(QFrame):
    """Single insight row: color dot + text."""

    def __init__(self, insight: Insight, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("insightRow")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(8)

        dot = QWidget()
        dot.setObjectName("insightDot")
        dot.setFixedSize(6, 6)
        dot.setStyleSheet(
            f"background-color: {insight_color(insight.category)}; border-radius: 3px;"
        )
        layout.addWidget(dot, alignment=Qt.AlignmentFlag.AlignVCenter)

        text = QLabel(insight.text)
        text.setObjectName("insightText")
        text.setWordWrap(True)
        layout.addWidget(text, stretch=1)


class PacingInsightsView(QWidget):
    """Pacing insights panel — max 5 short, dismissible insights."""

    def __init__(
        self,
        db: Database,
        project_id: int,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._db = db
        self._project_id = project_id
        self._insights: list[Insight] = []

        self.setObjectName("pacingInsightsView")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        title = QLabel("Pacing Insights")
        title.setObjectName("insightsTitle")
        layout.addWidget(title)

        self._content = QWidget()
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(0, 0, 0, 0)
        self._content_layout.setSpacing(6)
        layout.addWidget(self._content)
        layout.addStretch()

        self.refresh()

    def refresh(self) -> None:
        self._insights = generate_insights(self._db, self._project_id)
        self._rebuild()

    def _rebuild(self) -> None:
        layout = self._content_layout
        while layout.count():
            child = layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        if not self._insights:
            # Distinguish "not enough story yet to analyze" from "analyzed,
            # nothing wrong" — otherwise a 2-scene draft looks falsely healthy.
            scene_count = len(self._db.get_all_scenes(self._project_id))
            if scene_count < MIN_SCENES:
                msg = (f"Pacing analysis activates at {MIN_SCENES}+ scenes "
                       f"(you have {scene_count}).")
            else:
                msg = "No pacing issues detected — pacing looks even."
            empty = QLabel(msg)
            empty.setObjectName("insightsEmpty")
            empty.setWordWrap(True)
            layout.addWidget(empty)
            return

        for insight in self._insights:
            row = _InsightRow(insight)
            layout.addWidget(row)

    def get_insights(self) -> list[Insight]:
        return self._insights
