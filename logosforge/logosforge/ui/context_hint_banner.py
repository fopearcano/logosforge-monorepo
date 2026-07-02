"""Context hint banner — a thin strip below the scene editor.

Presents a single ContextHint with Dismiss / Ignore actions and an optional
Accept button for actionable hints.  Never modifies the database — emits
signals for the parent view.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QWidget,
)

from logosforge.context_assistant import ContextHint


_PRIORITY_ICON = {
    1: "!",
    2: "~",
    3: "·",
}


class ContextHintBanner(QWidget):
    """Compact strip that shows one context-aware writing hint."""

    accepted = Signal(object)   # emits ContextHint (for actionable hints)
    dismissed = Signal(object)  # emits ContextHint
    ignored = Signal(object)    # emits ContextHint (never show again)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("contextHintBanner")
        self._current: ContextHint | None = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 3, 8, 3)
        layout.setSpacing(6)

        self._icon_label = QLabel()
        self._icon_label.setObjectName("contextHintBannerIcon")
        layout.addWidget(self._icon_label)

        self._label = QLabel()
        self._label.setObjectName("contextHintBannerLabel")
        self._label.setWordWrap(False)
        self._label.setTextInteractionFlags(
            Qt.TextInteractionFlag.NoTextInteraction,
        )
        layout.addWidget(self._label, stretch=1)

        self._accept_btn = self._make_btn("Apply")
        self._accept_btn.clicked.connect(self._on_accept)
        layout.addWidget(self._accept_btn)

        self._dismiss_btn = self._make_btn("Dismiss")
        self._dismiss_btn.clicked.connect(self._on_dismiss)
        layout.addWidget(self._dismiss_btn)

        self._ignore_btn = self._make_btn("Ignore")
        self._ignore_btn.setToolTip("Never show this hint again for this scene")
        self._ignore_btn.clicked.connect(self._on_ignore)
        layout.addWidget(self._ignore_btn)

        self.hide()

    @staticmethod
    def _make_btn(text: str) -> QPushButton:
        btn = QPushButton(text)
        btn.setFlat(True)
        btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn.setObjectName("contextHintBannerBtn")
        return btn

    # -- Public API -----------------------------------------------------------

    def show_hint(self, hint: ContextHint) -> None:
        self._current = hint
        self._icon_label.setText(_PRIORITY_ICON.get(hint.priority, "·"))
        self._label.setText(hint.message)
        self._accept_btn.setVisible(hint.action is not None)
        self.show()

    def clear(self) -> None:
        self._current = None
        self.hide()

    @property
    def current(self) -> ContextHint | None:
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
