"""Shared color label palette for visual organization across views.

Provides a small consistent palette of muted colors usable as scene/element
labels in Plot, Timeline, and other views. Colors are dark-theme friendly:
muted, readable, and not visually noisy.

Use ``COLOR_LABELS`` for the canonical key→display name mapping.
Use ``color_hex(key)`` to get the display color for a stored label key.
Use ``build_color_menu(parent, current, on_select)`` to add a "Color"
submenu to any context menu.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtGui import QAction, QColor, QPixmap, QIcon
from PySide6.QtWidgets import QMenu


COLOR_LABELS: dict[str, str] = {
    "": "None / Default",
    "red": "Red",
    "orange": "Orange",
    "amber": "Amber",
    "yellow": "Yellow",
    "green": "Green",
    "teal": "Teal",
    "blue": "Blue",
    "purple": "Purple",
    "gray": "Gray",
}


_PALETTE_HEX: dict[str, str] = {
    "red": "#c75450",
    "orange": "#d18250",
    "amber": "#cba23a",
    "yellow": "#c8b03a",
    "green": "#6ba35a",
    "teal": "#4ea29a",
    "blue": "#5a8fcc",
    "purple": "#9070b8",
    "gray": "#8a8a8a",
}


def color_hex(key: str | None) -> str | None:
    """Return the hex color for a label key, or None if no color."""
    if not key:
        return None
    return _PALETTE_HEX.get(key)


def is_valid_label(key: str | None) -> bool:
    """True if *key* is a known label (empty string is valid → 'none')."""
    if not key:
        return True
    return key in _PALETTE_HEX


def _swatch_icon(hex_color: str | None, size: int = 12) -> QIcon:
    pix = QPixmap(size, size)
    pix.fill(QColor(0, 0, 0, 0))
    if hex_color:
        from PySide6.QtGui import QPainter
        painter = QPainter(pix)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setBrush(QColor(hex_color))
        painter.setPen(QColor(hex_color))
        painter.drawEllipse(0, 0, size - 1, size - 1)
        painter.end()
    return QIcon(pix)


def build_color_menu(
    parent: QMenu,
    current: str | None,
    on_select: Callable[[str], None],
    title: str = "Color",
) -> QMenu:
    """Append a 'Color' submenu to *parent* with palette choices.

    *current* is the currently-stored label key (or '' / None for default).
    *on_select* is invoked with the new label key when the user picks one.
    Returns the submenu for further customization.
    """
    submenu = QMenu(title, parent)
    cur = current or ""
    for key, label in COLOR_LABELS.items():
        action = QAction(label, submenu)
        action.setIcon(_swatch_icon(_PALETTE_HEX.get(key)))
        action.setCheckable(True)
        action.setChecked(key == cur)
        action.triggered.connect(lambda _=False, k=key: on_select(k))
        submenu.addAction(action)
    parent.addMenu(submenu)
    return submenu
