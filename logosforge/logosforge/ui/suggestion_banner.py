"""Inline suggestion banner — a thin horizontal strip above a scene editor.

Presents a single auto-link Suggestion with Accept / Dismiss / Ignore actions.
Never acts on the database itself — it emits signals for the parent view.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QWidget,
)

from logosforge.auto_link import Suggestion


_KIND_ICON = {
    "create": "+",
    "alias": "≈",
    "relation": "↔",
    "memory": "✎",
}


class SuggestionBanner(QWidget):
    """Compact strip that proposes one auto-link action."""

    accepted = Signal(object)   # emits Suggestion
    dismissed = Signal(object)  # emits Suggestion
    ignored = Signal(object)    # emits Suggestion

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("suggestionBanner")
        self._current: Suggestion | None = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 3, 8, 3)
        layout.setSpacing(6)

        self._icon_label = QLabel()
        self._icon_label.setObjectName("suggestionBannerIcon")
        layout.addWidget(self._icon_label)

        self._label = QLabel()
        self._label.setObjectName("suggestionBannerLabel")
        self._label.setWordWrap(False)
        self._label.setTextInteractionFlags(
            Qt.TextInteractionFlag.NoTextInteraction,
        )
        layout.addWidget(self._label, stretch=1)

        self._accept_btn = self._make_btn("Accept")
        self._accept_btn.clicked.connect(self._on_accept)
        layout.addWidget(self._accept_btn)

        self._dismiss_btn = self._make_btn("Dismiss")
        self._dismiss_btn.clicked.connect(self._on_dismiss)
        layout.addWidget(self._dismiss_btn)

        self._ignore_btn = self._make_btn("Ignore")
        self._ignore_btn.setToolTip("Never suggest this again")
        self._ignore_btn.clicked.connect(self._on_ignore)
        layout.addWidget(self._ignore_btn)

        self.hide()

    @staticmethod
    def _make_btn(text: str) -> QPushButton:
        btn = QPushButton(text)
        btn.setFlat(True)
        btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn.setObjectName("suggestionBannerBtn")
        return btn

    # -- Public API -----------------------------------------------------------

    def show_suggestion(self, suggestion: Suggestion) -> None:
        self._current = suggestion
        self._icon_label.setText(_KIND_ICON.get(suggestion.kind, "•"))
        self._label.setText(suggestion.label)
        self.show()

    def clear(self) -> None:
        self._current = None
        self.hide()

    @property
    def current(self) -> Suggestion | None:
        return self._current

    # -- Internal -------------------------------------------------------------

    def _on_accept(self) -> None:
        if self._current is not None:
            self.accepted.emit(self._current)

    def _on_dismiss(self) -> None:
        if self._current is not None:
            self.dismissed.emit(self._current)

    def _on_ignore(self) -> None:
        if self._current is not None:
            self.ignored.emit(self._current)
