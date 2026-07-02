"""Shared link preview widget — renders [[Entity Name]] as clickable links."""

import re
from collections.abc import Callable
from urllib.parse import quote, unquote

from PySide6.QtCore import Qt, QUrl
from PySide6.QtWidgets import QLabel, QListWidget, QListWidgetItem, QTextBrowser, QVBoxLayout, QWidget

from logosforge.db import Database
from logosforge.ui import theme

LINK_PATTERN = re.compile(r"\[\[(.+?)\]\]")
LINK_SCHEME = "storylink"


def render_linked_text(plain_text: str) -> str:
    if not plain_text:
        return ""

    def _replace(match: re.Match) -> str:
        name = match.group(1)
        encoded = quote(name, safe="")
        escaped = _esc(name)
        return (
            f'<a href="{LINK_SCHEME}://{encoded}"'
            f' style="color: {theme.LINK_COLOR};">{escaped}</a>'
        )

    escaped_text = _esc_except_links(plain_text)
    return escaped_text.replace("\n", "<br>")


def _esc(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _esc_except_links(text: str) -> str:
    parts: list[str] = []
    last_end = 0
    for match in LINK_PATTERN.finditer(text):
        parts.append(_esc(text[last_end:match.start()]))
        name = match.group(1)
        encoded = quote(name, safe="")
        escaped = _esc(name)
        parts.append(
            f'<a href="{LINK_SCHEME}://{encoded}"'
            f' style="color: {theme.LINK_COLOR};">{escaped}</a>'
        )
        last_end = match.end()
    parts.append(_esc(text[last_end:]))
    return "".join(parts)


def create_link_browser(
    on_link_clicked: Callable[[str], None],
    max_height: int = 80,
) -> QTextBrowser:
    browser = QTextBrowser()
    browser.setMaximumHeight(max_height)
    browser.setOpenLinks(False)
    browser.setStyleSheet(
        f"QTextBrowser {{ background: {theme.BG_PANEL};"
        f" border: 1px solid {theme.BORDER}; }}"
    )

    def _handle_click(url: QUrl) -> None:
        if url.scheme() == LINK_SCHEME:
            name = unquote(url.host())
            on_link_clicked(name)

    browser.anchorClicked.connect(_handle_click)
    return browser


USER_ROLE = Qt.ItemDataRole.UserRole


class BacklinksWidget(QWidget):
    def __init__(
        self,
        db: Database,
        project_id: int,
        on_backlink_clicked: Callable[[str, int], None] | None = None,
    ) -> None:
        super().__init__()
        self._db = db
        self._project_id = project_id
        self._on_backlink_clicked = on_backlink_clicked

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._label = QLabel("Referenced by")
        layout.addWidget(self._label)

        self._list = QListWidget()
        self._list.setMaximumHeight(80)
        self._list.itemClicked.connect(self._on_item_clicked)
        layout.addWidget(self._list)

    def load(self, entity_name: str) -> None:
        self._list.clear()
        backlinks = self._db.find_backlinks(self._project_id, entity_name)
        if not backlinks:
            self._label.setText("Referenced by (none)")
            return
        self._label.setText(f"Referenced by ({len(backlinks)})")
        for entity_type, entity_id, label in backlinks:
            item = QListWidgetItem(f"[{entity_type}] {label}")
            item.setData(USER_ROLE, (entity_type, entity_id))
            self._list.addItem(item)

    def clear_backlinks(self) -> None:
        self._list.clear()
        self._label.setText("Referenced by")

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        if self._on_backlink_clicked is None:
            return
        data = item.data(USER_ROLE)
        if data:
            entity_type, entity_id = data
            self._on_backlink_clicked(entity_type, entity_id)
