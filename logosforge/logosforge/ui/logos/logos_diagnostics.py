"""LogosDiagnosticsDrawer — a compact, non-intrusive diagnostics panel.

Lists the current narrative diagnostics grouped by severity. Each row shows the
category, severity, confidence, evidence, and the suggested Logos actions; the
user can run an action (routed to the existing Logos controller via the host),
dismiss, copy, or open the target. Non-modal, never steals focus, hidden when
empty. This widget never mutates data.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from logosforge.logos.diagnostics.diagnostic import (
    SEVERITY_CRITICAL,
    SEVERITY_IMPORTANT,
    SEVERITY_WARNING,
)
from logosforge.ui import theme

_SEVERITY_COLOR = {
    SEVERITY_CRITICAL: "#e25555",
    SEVERITY_IMPORTANT: "#e25555",
    SEVERITY_WARNING: "#e0a52e",
}


class LogosDiagnosticsDrawer(QWidget):
    """A collapsible drawer listing narrative diagnostics."""

    # (diagnostic, action_name)
    run_action = Signal(object, str)
    # (diagnostic, kind) — kind in {"dismiss"}
    suppress = Signal(object, str)
    # (diagnostic) — host opens the target entity
    open_target = Signal(object)
    rescan_requested = Signal()
    project_scan_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("logosDiagnosticsDrawer")
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._diagnostics: list = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 6, 8, 8)
        outer.setSpacing(6)

        header = QHBoxLayout()
        self._title = QLabel("Logos Diagnostics")
        self._title.setStyleSheet(
            f"color: {theme.ACCENT}; font-weight: bold; font-size: 12px;"
        )
        header.addWidget(self._title)
        self._badge = QLabel("0")
        self._badge.setStyleSheet(
            f"color: {theme.TEXT_MUTED}; font-size: 11px; "
            f"border: 1px solid {theme.BORDER}; border-radius: 8px; padding: 0 6px;"
        )
        header.addWidget(self._badge)
        header.addStretch()

        rescan = QPushButton("Rescan")
        rescan.setFlat(True)
        rescan.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        rescan.clicked.connect(self.rescan_requested.emit)
        header.addWidget(rescan)
        proj = QPushButton("Scan Project")
        proj.setFlat(True)
        proj.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        proj.clicked.connect(self.project_scan_requested.emit)
        header.addWidget(proj)
        outer.addLayout(header)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setMaximumHeight(220)
        self._list_host = QWidget()
        self._list_layout = QVBoxLayout(self._list_host)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(4)
        self._scroll.setWidget(self._list_host)
        outer.addWidget(self._scroll)

    # -- Public --------------------------------------------------------------

    def set_diagnostics(self, diagnostics: list) -> None:
        self._diagnostics = list(diagnostics)
        self._badge.setText(str(len(self._diagnostics)))
        self._rebuild()

    def diagnostics(self) -> list:
        return list(self._diagnostics)

    # -- Build ---------------------------------------------------------------

    def _rebuild(self) -> None:
        while self._list_layout.count():
            item = self._list_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        if not self._diagnostics:
            empty = QLabel("No diagnostics — the story looks consistent here.")
            empty.setStyleSheet(f"color: {theme.TEXT_MUTED}; font-size: 11px;")
            self._list_layout.addWidget(empty)
            return
        for diag in self._diagnostics:
            self._list_layout.addWidget(self._make_row(diag))
        self._list_layout.addStretch()

    def _make_row(self, diag) -> QWidget:
        row = QFrame()
        row.setStyleSheet(
            f"QFrame {{ border: 1px solid {theme.BORDER}; border-radius: 5px; }}"
        )
        lay = QVBoxLayout(row)
        lay.setContentsMargins(8, 4, 8, 4)
        lay.setSpacing(2)

        color = _SEVERITY_COLOR.get(diag.severity, theme.TEXT_MUTED)
        pct = int(round(diag.confidence * 100))
        head = QLabel(
            f"<b>{diag.title}</b>"
            f"<span style='color:{color}'>  · {diag.severity} · {pct}%</span>"
        )
        head.setStyleSheet(f"color: {theme.TEXT_PRIMARY}; font-size: 11px;")
        head.setWordWrap(True)
        lay.addWidget(head)

        meta = QLabel(f"{diag.category} — {diag.evidence}")
        meta.setStyleSheet(f"color: {theme.TEXT_MUTED}; font-size: 10px;")
        meta.setWordWrap(True)
        lay.addWidget(meta)

        actions_row = QHBoxLayout()
        actions_row.setSpacing(4)
        from logosforge.logos.actions import get_action
        for action_name in diag.suggested_actions[:2]:
            action = get_action(action_name)
            btn = QPushButton(action.label if action else action_name)
            btn.setFlat(True)
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            btn.setStyleSheet(
                f"QPushButton {{ color: {theme.TEXT_SECONDARY}; border: 1px solid "
                f"{theme.BORDER}; border-radius: 4px; padding: 1px 6px; "
                f"font-size: 10px; }}"
                f"QPushButton:hover {{ color: {theme.TEXT_PRIMARY}; }}"
            )
            btn.clicked.connect(
                lambda _=False, d=diag, n=action_name: self.run_action.emit(d, n)
            )
            actions_row.addWidget(btn)
        actions_row.addStretch()

        more = QPushButton("⋯")
        more.setFlat(True)
        more.setFixedWidth(22)
        more.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        more.clicked.connect(lambda _=False, d=diag, b=more: self._row_menu(d, b))
        actions_row.addWidget(more)
        lay.addLayout(actions_row)
        return row

    def _row_menu(self, diag, anchor: QWidget) -> None:
        menu = QMenu(anchor)
        if diag.target_id and diag.target_type:
            open_act = menu.addAction("Open Target")
            open_act.triggered.connect(lambda: self.open_target.emit(diag))
        copy = menu.addAction("Copy")
        copy.triggered.connect(lambda: self._copy(diag))
        menu.addSeparator()
        dismiss = menu.addAction("Dismiss")
        dismiss.triggered.connect(lambda: self.suppress.emit(diag, "dismiss"))
        menu.exec(anchor.mapToGlobal(anchor.rect().bottomLeft()))

    def _copy(self, diag) -> None:
        text = f"{diag.title}\n{diag.message}\nEvidence: {diag.evidence}"
        QApplication.clipboard().setText(text)
