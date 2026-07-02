"""LogosSuggestionBar — a compact, non-intrusive proactive-suggestion strip.

Shows the active proactive suggestions for the current section as small pills.
Clicking a pill opens a compact details popover with the evidence and the
suggested Logos actions (Explain / Suggest Fix / …), plus Ignore and Snooze.

Non-intrusive by contract: no modal popups, never steals focus, hidden when
there are no suggestions. Acting on a suggestion routes back to the host via the
``on_run_action`` callback, which runs the *existing* Logos action through the
normal preview/confirm path — this widget never mutates data.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QWidget,
)

from logosforge.logos.proactive.suggestion import (
    SEVERITY_IMPORTANT,
    SEVERITY_WARNING,
)
from logosforge.ui import theme

_SEVERITY_COLOR = {
    SEVERITY_IMPORTANT: "#e25555",
    SEVERITY_WARNING: "#e0a52e",
}


class LogosSuggestionBar(QWidget):
    """A horizontal strip of dismissible suggestion pills."""

    # (suggestion, action_name) — host runs the existing Logos action.
    run_action = Signal(object, str)
    # (suggestion, kind) where kind in {"dismiss", "snooze", "hide_type"}.
    suppress = Signal(object, str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("logosSuggestionBar")
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)  # never steal focus
        self._suggestions: list = []

        self._row = QHBoxLayout(self)
        self._row.setContentsMargins(8, 2, 8, 2)
        self._row.setSpacing(6)

        self._label = QLabel("Logos")
        self._label.setStyleSheet(
            f"color: {theme.ACCENT}; font-size: 10px; font-weight: bold;"
        )
        self._row.addWidget(self._label)
        self._pills_host = QHBoxLayout()
        self._pills_host.setSpacing(4)
        self._row.addLayout(self._pills_host)
        self._row.addStretch()
        self._pills: list[QPushButton] = []

    # -- Public --------------------------------------------------------------

    def set_suggestions(self, suggestions: list) -> None:
        self._suggestions = list(suggestions)
        self._rebuild()

    def suggestions(self) -> list:
        return list(self._suggestions)

    # -- Build ---------------------------------------------------------------

    def _rebuild(self) -> None:
        for pill in self._pills:
            self._pills_host.removeWidget(pill)
            pill.deleteLater()
        self._pills = []

        count = len(self._suggestions)
        if count == 0:
            self._label.setText("Logos · no suggestions")
            return
        # Stable "Logos · N suggestion(s)" prefix so the count reads at a glance.
        self._label.setText(
            f"Logos · {count} suggestion{'' if count == 1 else 's'}"
        )
        for sug in self._suggestions:
            self._pills_host.addWidget(self._make_pill(sug))

    def _make_pill(self, sug) -> QPushButton:
        color = _SEVERITY_COLOR.get(sug.severity, theme.TEXT_MUTED)
        pct = int(round(sug.confidence * 100))
        pill = QPushButton(f"● {sug.title}  ({pct}%)")
        pill.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        pill.setToolTip(f"{sug.message}\nEvidence: {sug.evidence}")
        pill.setStyleSheet(
            f"QPushButton {{ color: {theme.TEXT_PRIMARY}; border: 1px solid "
            f"{color}; border-radius: 9px; padding: 1px 8px; font-size: 11px; }}"
            f"QPushButton:hover {{ background: {color}22; }}"
        )
        pill.clicked.connect(lambda _=False, s=sug, b=pill: self._open_menu(s, b))
        self._pills.append(pill)
        return pill

    def _open_menu(self, sug, anchor: QWidget) -> None:
        menu = QMenu(anchor)

        header = menu.addAction(sug.title)
        header.setEnabled(False)
        if sug.evidence:
            ev = menu.addAction(f"  ⋯ {sug.evidence[:70]}")
            ev.setEnabled(False)
        menu.addSeparator()

        # Suggested Logos actions (run through the existing preview/confirm).
        from logosforge.logos.actions import get_action
        for action_name in sug.suggested_actions:
            action = get_action(action_name)
            label = action.label if action else action_name
            act = menu.addAction(f"▸ {label}")
            act.triggered.connect(
                lambda _=False, s=sug, n=action_name: self.run_action.emit(s, n)
            )
        menu.addSeparator()

        ignore = menu.addAction("Ignore")
        ignore.triggered.connect(lambda: self.suppress.emit(sug, "dismiss"))
        snooze = menu.addAction("Snooze (1 day)")
        snooze.triggered.connect(lambda: self.suppress.emit(sug, "snooze"))
        hide = menu.addAction(f"Hide all '{sug.type}' suggestions")
        hide.triggered.connect(lambda: self.suppress.emit(sug, "hide_type"))

        menu.exec(anchor.mapToGlobal(anchor.rect().bottomLeft()))
