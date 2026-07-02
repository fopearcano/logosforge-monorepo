"""Smart Assistant dock — Phase 1 foundation.

A single, reusable container that hosts a section's content view and the shared
Assistant panel side by side, and owns *all* of the panel's layout behaviour so
every section behaves identically:

* responsive sizing (panel width adapts to available width),
* minimum content-width protection (the working area is never squeezed below a
  usable width — the panel auto-hides instead),
* collapse / expand (to a thin strip that keeps the panel reachable),
* pin / unpin (pinned keeps the panel docked even when space is tight; unpinned
  lets it get out of the way),
* internal scrolling (the panel itself owns a QScrollArea).

The dock is deliberately section-independent: the content widget is swapped in
via :meth:`set_content`, so Manuscript / Outline / Plot / Timeline / Graph all
get the exact same panel behaviour from one implementation.

Floating windows are intentionally out of scope for Phase 1.  The dock supports
a :meth:`set_floating` passthrough so an external overlay can borrow the panel,
but it does not create top-level windows itself.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class AssistantDock(QWidget):
    """Hosts ``[ content | collapse-strip | assistant panel ]``."""

    # Layout constants (px). The working area is never allowed below
    # MIN_CONTENT_WIDTH while the panel is shown — the panel auto-hides
    # (when unpinned) or shrinks to PANEL_MIN_WIDTH (when pinned) first.
    MIN_CONTENT_WIDTH = 480
    PANEL_MIN_WIDTH = 240
    PANEL_MAX_WIDTH = 360
    STRIP_WIDTH = 26

    # Emitted when the panel's *effective* visibility changes (shown/hidden),
    # whether by the user or by auto-hide.
    panel_visibility_changed = Signal(bool)
    collapsed_changed = Signal(bool)
    pinned_changed = Signal(bool)

    def __init__(self, panel: QWidget, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._panel = panel
        self._content: QWidget | None = None
        self._user_visible = False   # does the user want the panel shown?
        self._collapsed = False      # explicit user collapse
        self._pinned = False         # keep docked even when cramped
        self._floating = False       # panel borrowed by an external overlay
        self._auto_hidden = False    # hidden purely to protect content width
        self._last_panel_visible = False
        # Last known real width (from resizeEvent / explicit calls). Used when
        # state changes happen before the dock has been laid out, so a small
        # default widget width never spuriously auto-hides the panel.
        self._last_width = self.MIN_CONTENT_WIDTH + self.PANEL_MAX_WIDTH

        self._row = QHBoxLayout(self)
        self._row.setContentsMargins(0, 0, 0, 0)
        self._row.setSpacing(0)

        # Content host — the section view lives here and always stretches.
        self._content_host = QWidget()
        self._content_layout = QVBoxLayout(self._content_host)
        self._content_layout.setContentsMargins(0, 0, 0, 0)
        self._content_layout.setSpacing(0)
        self._row.addWidget(self._content_host, stretch=1)

        # Thin expand strip shown only while collapsed.
        self._strip = self._build_strip()
        self._row.addWidget(self._strip, stretch=0)
        self._strip.setVisible(False)

        # The shared assistant panel.
        self._panel.setMinimumWidth(self.PANEL_MIN_WIDTH)
        self._panel.setMaximumWidth(self.PANEL_MAX_WIDTH)
        self._row.addWidget(self._panel, stretch=0)
        self._panel.setVisible(False)

        # Wire optional panel controls (collapse / pin) if the panel exposes
        # them — keeps the dock decoupled from the concrete panel class.
        if hasattr(self._panel, "collapse_requested"):
            self._panel.collapse_requested.connect(lambda: self.set_collapsed(True))
        if hasattr(self._panel, "pin_toggled"):
            self._panel.pin_toggled.connect(self.set_pinned)

    def apply_theme(self) -> None:
        """Propagate an Appearance change to the embedded Assistant panel
        (whether docked or floating — held by reference) and repolish the dock
        chrome (the collapse strip) so the whole dock updates live."""
        if hasattr(self._panel, "apply_theme"):
            try:
                self._panel.apply_theme()
            except Exception:
                pass
        for w in self.findChildren(QWidget):
            w.style().unpolish(w)
            w.style().polish(w)
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

    # -- Strip ---------------------------------------------------------------

    def _build_strip(self) -> QWidget:
        strip = QWidget()
        strip.setObjectName("assistantStrip")
        strip.setFixedWidth(self.STRIP_WIDTH)
        lay = QVBoxLayout(strip)
        lay.setContentsMargins(2, 4, 2, 4)
        lay.setSpacing(2)
        self._expand_btn = QPushButton("‹")  # ‹
        self._expand_btn.setToolTip("Expand the assistant panel")
        self._expand_btn.setFixedWidth(self.STRIP_WIDTH - 4)
        self._expand_btn.setFlat(True)
        self._expand_btn.clicked.connect(lambda: self.set_collapsed(False))
        lay.addWidget(self._expand_btn)
        lay.addStretch()
        return strip

    # -- Content -------------------------------------------------------------

    def set_content(self, widget: QWidget) -> QWidget | None:
        """Swap the section content view. Returns the previous content."""
        old = self._content
        if old is not None:
            self._content_layout.removeWidget(old)
            old.setParent(None)
        self._content = widget
        if widget is not None:
            self._content_layout.addWidget(widget)
            widget.show()
        return old

    def content(self) -> QWidget | None:
        return self._content

    @property
    def panel(self) -> QWidget:
        return self._panel

    # -- State ---------------------------------------------------------------

    def set_panel_user_visible(self, visible: bool) -> None:
        self._user_visible = visible
        if visible:
            self._collapsed = False
        self.apply_responsive()

    def is_panel_user_visible(self) -> bool:
        return self._user_visible

    def is_panel_visible(self) -> bool:
        # isHidden() reflects the explicit setVisible() state regardless of
        # whether an ancestor is currently shown (so it is reliable in tests
        # and before the window is mapped).
        return not self._panel.isHidden()

    def is_auto_hidden(self) -> bool:
        return self._auto_hidden

    def set_collapsed(self, collapsed: bool) -> None:
        if self._collapsed == collapsed:
            return
        self._collapsed = collapsed
        self.collapsed_changed.emit(collapsed)
        self.apply_responsive()

    def toggle_collapsed(self) -> None:
        self.set_collapsed(not self._collapsed)

    def is_collapsed(self) -> bool:
        return self._collapsed

    def set_pinned(self, pinned: bool) -> None:
        if self._pinned == pinned:
            return
        self._pinned = pinned
        if hasattr(self._panel, "set_pinned_state"):
            self._panel.set_pinned_state(pinned)
        self.pinned_changed.emit(pinned)
        self.apply_responsive()

    def is_pinned(self) -> bool:
        return self._pinned

    def set_floating(self, floating: bool) -> None:
        """Release/retake the panel for an external overlay host.

        While floating, the dock removes the panel from its row so the content
        takes the full width; the overlay host owns parenting/placement.
        """
        if self._floating == floating:
            return
        self._floating = floating
        if floating:
            self._row.removeWidget(self._panel)
        else:
            # Re-add after the strip so the order stays content|strip|panel.
            self._row.addWidget(self._panel, stretch=0)
        self.apply_responsive()

    def is_floating(self) -> bool:
        return self._floating

    # -- Responsive layout ---------------------------------------------------

    def apply_responsive(self, width: int | None = None) -> None:
        """Recompute panel visibility/width and the strip, protecting content."""
        if width is not None and width > 0:
            self._last_width = width
        elif width is None and self.isVisible() and self.width() > 0:
            self._last_width = self.width()
        width = self._last_width

        want_panel = self._user_visible and not self._floating and not self._collapsed
        show_strip = (
            self._user_visible and not self._floating and self._collapsed
        )
        self._strip.setVisible(show_strip)

        if self._floating:
            # Panel is owned by the overlay host; nothing to size here.
            self._auto_hidden = False
            self._emit_visibility()
            return

        if not want_panel:
            self._panel.setVisible(False)
            self._auto_hidden = False
            self._emit_visibility()
            return

        space = width - self.MIN_CONTENT_WIDTH
        if width <= 0 or space >= self.PANEL_MIN_WIDTH:
            # Enough room (or not laid out yet): show at the responsive width.
            target = self.PANEL_MAX_WIDTH
            if width > 0:
                target = max(self.PANEL_MIN_WIDTH, min(self.PANEL_MAX_WIDTH, space))
            self._panel.setMinimumWidth(self.PANEL_MIN_WIDTH)
            self._panel.setMaximumWidth(target)
            self._panel.setVisible(True)
            self._auto_hidden = False
        elif self._pinned:
            # Pinned: keep it docked at the minimum; content scrolls.
            self._panel.setMinimumWidth(self.PANEL_MIN_WIDTH)
            self._panel.setMaximumWidth(self.PANEL_MIN_WIDTH)
            self._panel.setVisible(True)
            self._auto_hidden = False
        else:
            # Unpinned and cramped: auto-hide to protect the working area.
            self._panel.setVisible(False)
            self._auto_hidden = True

        self._emit_visibility()

    def _emit_visibility(self) -> None:
        visible = not self._panel.isHidden()
        if visible != self._last_panel_visible:
            self._last_panel_visible = visible
            self.panel_visibility_changed.emit(visible)

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt signature)
        super().resizeEvent(event)
        self.apply_responsive(event.size().width())
