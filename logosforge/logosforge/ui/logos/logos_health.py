"""LogosHealthDrawer — a compact, non-intrusive Narrative Health surface.

Shows the project's overall health status, a grid of category cards (clear
status labels, no fake percentages), top risks, strengths, and prioritized
recommendations. Each recommendation can launch the existing Logos action it
maps to or open its target. Includes Refresh and Export buttons.

Non-modal, never steals focus, hidden by default. This widget never mutates
project data — actions route to the host via signals (preview/confirm path).
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from logosforge.logos.health.metric import (
    STATUS_CRITICAL,
    STATUS_STABLE,
    STATUS_UNKNOWN,
    STATUS_WATCH,
    STATUS_WEAK,
)
from logosforge.ui import theme

_STATUS_COLOR = {
    STATUS_CRITICAL: "#e25555",
    STATUS_WEAK: "#e0772e",
    STATUS_WATCH: "#e0a52e",
    STATUS_STABLE: "#3fae6a",
    STATUS_UNKNOWN: theme.TEXT_MUTED,
}


class LogosHealthDrawer(QWidget):
    """Project-level narrative health panel."""

    # (recommendation, action_name)
    run_action = Signal(object, str)
    open_target = Signal(object)          # recommendation (or metric)
    refresh_requested = Signal()
    export_requested = Signal(str)        # "json" | "markdown"

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("logosHealthDrawer")
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._report = None
        self._show_unknown = True

        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 6, 8, 8)
        outer.setSpacing(6)

        header = QHBoxLayout()
        self._title = QLabel("Narrative Health")
        self._title.setStyleSheet(
            f"color: {theme.ACCENT}; font-weight: bold; font-size: 12px;"
        )
        header.addWidget(self._title)
        self._overall = QLabel("Not Enough Data")
        self._overall.setStyleSheet(f"color: {theme.TEXT_MUTED}; font-size: 11px;")
        header.addWidget(self._overall)
        self._strategy = QLabel("")
        self._strategy.setStyleSheet(f"color: {theme.ACCENT}; font-size: 10px;")
        header.addWidget(self._strategy)
        header.addStretch()
        for label, slot in (
            ("Refresh", self.refresh_requested.emit),
            ("Export JSON", lambda: self.export_requested.emit("json")),
            ("Export MD", lambda: self.export_requested.emit("markdown")),
        ):
            btn = QPushButton(label)
            btn.setFlat(True)
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            btn.clicked.connect(slot)
            header.addWidget(btn)
        outer.addLayout(header)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setMaximumHeight(280)
        self._body = QWidget()
        self._body_layout = QVBoxLayout(self._body)
        self._body_layout.setContentsMargins(0, 0, 0, 0)
        self._body_layout.setSpacing(8)
        self._scroll.setWidget(self._body)
        outer.addWidget(self._scroll)

    # -- Public --------------------------------------------------------------

    def set_show_unknown(self, show: bool) -> None:
        self._show_unknown = show

    def set_report(self, report) -> None:
        self._report = report
        self._rebuild()

    def set_strategy_label(self, text: str) -> None:
        """Show the active dominant strategy (small, non-intrusive indicator)."""
        self._strategy.setText(text)
        self._strategy.setVisible(bool(text))

    def report(self):
        return self._report

    # -- Build ---------------------------------------------------------------

    def _rebuild(self) -> None:
        while self._body_layout.count():
            item = self._body_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        if self._report is None:
            return

        self._overall.setText(f"Overall: {self._report.overall_label}")

        # Category cards grid.
        grid_host = QWidget()
        grid = QGridLayout(grid_host)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(4)
        col = 0
        row = 0
        for m in self._report.metrics:
            if m.status == STATUS_UNKNOWN and not self._show_unknown:
                continue
            grid.addWidget(self._card(m), row, col)
            col += 1
            if col >= 3:
                col = 0
                row += 1
        self._body_layout.addWidget(grid_host)

        self._add_list("Top Risks", self._report.top_risks)
        self._add_list("Strengths", self._report.strengths)
        self._add_recommendations()

    def _card(self, metric) -> QWidget:
        color = _STATUS_COLOR.get(metric.status, theme.TEXT_MUTED)
        card = QFrame()
        card.setStyleSheet(
            f"QFrame {{ border: 1px solid {color}; border-radius: 5px; }}"
        )
        lay = QVBoxLayout(card)
        lay.setContentsMargins(6, 4, 6, 4)
        lay.setSpacing(1)
        name = QLabel(metric.name)
        name.setStyleSheet(f"color: {theme.TEXT_PRIMARY}; font-size: 11px; font-weight: bold;")
        lay.addWidget(name)
        status = QLabel(metric.status_label)
        status.setStyleSheet(f"color: {color}; font-size: 10px;")
        lay.addWidget(status)
        if metric.evidence:
            card.setToolTip(metric.evidence)
        return card

    def _add_list(self, title: str, items: list) -> None:
        if not items:
            return
        head = QLabel(title)
        head.setStyleSheet(
            f"color: {theme.TEXT_SECONDARY}; font-size: 11px; font-weight: bold;"
        )
        self._body_layout.addWidget(head)
        for it in items:
            lbl = QLabel(f"• {it}")
            lbl.setWordWrap(True)
            lbl.setStyleSheet(f"color: {theme.TEXT_MUTED}; font-size: 10px;")
            self._body_layout.addWidget(lbl)

    def _add_recommendations(self) -> None:
        recs = self._report.recommendations
        if not recs:
            return
        head = QLabel("Recommendations")
        head.setStyleSheet(
            f"color: {theme.TEXT_SECONDARY}; font-size: 11px; font-weight: bold;"
        )
        self._body_layout.addWidget(head)
        from logosforge.logos.actions import get_action
        for rec in recs:
            row = QFrame()
            row.setStyleSheet(
                f"QFrame {{ border: 1px solid {theme.BORDER}; border-radius: 4px; }}"
            )
            lay = QVBoxLayout(row)
            lay.setContentsMargins(6, 3, 6, 3)
            lay.setSpacing(1)
            prob = QLabel(f"<b>{rec.problem}</b> — {rec.why}")
            prob.setWordWrap(True)
            prob.setStyleSheet(f"color: {theme.TEXT_PRIMARY}; font-size: 11px;")
            lay.addWidget(prob)
            if rec.evidence:
                ev = QLabel(rec.evidence)
                ev.setWordWrap(True)
                ev.setStyleSheet(f"color: {theme.TEXT_MUTED}; font-size: 10px;")
                lay.addWidget(ev)
            btn_row = QHBoxLayout()
            btn_row.setSpacing(4)
            if rec.suggested_action:
                action = get_action(rec.suggested_action)
                ask = QPushButton(f"Ask Logos: {action.label if action else rec.suggested_action}")
                ask.setFlat(True)
                ask.setFocusPolicy(Qt.FocusPolicy.NoFocus)
                ask.setStyleSheet(
                    f"QPushButton {{ color: {theme.TEXT_SECONDARY}; border: 1px solid "
                    f"{theme.BORDER}; border-radius: 4px; padding: 1px 6px; font-size: 10px; }}"
                    f"QPushButton:hover {{ color: {theme.TEXT_PRIMARY}; }}"
                )
                ask.clicked.connect(
                    lambda _=False, r=rec, n=rec.suggested_action: self.run_action.emit(r, n)
                )
                btn_row.addWidget(ask)
            if rec.target_id and rec.target_type:
                opent = QPushButton("Open Target")
                opent.setFlat(True)
                opent.setFocusPolicy(Qt.FocusPolicy.NoFocus)
                opent.clicked.connect(lambda _=False, r=rec: self.open_target.emit(r))
                btn_row.addWidget(opent)
            btn_row.addStretch()
            lay.addLayout(btn_row)
            self._body_layout.addWidget(row)
