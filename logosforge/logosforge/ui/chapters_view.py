"""Chapters section — the primary writing unit for Novel mode.

A compact, mode-specific manager over the additive ``Chapter`` store (Novel
only). Scenes remain the primary unit for all other modes and are never touched
here. List / create / edit (title, summary, body) / reorder / delete-with-
confirm. Project-scoped; rebuilt fresh on project switch so no stale selection
or data leaks.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from logosforge.db import Database
from logosforge.ui import theme


class ChaptersView(QWidget):
    """List + edit chapters (Novel primary unit)."""

    def __init__(
        self,
        db: Database,
        project_id: int,
        on_data_changed: Callable[[], None] | None = None,
        on_open_chapter: Callable[[int], None] | None = None,
    ) -> None:
        super().__init__()
        self._db = db
        self._project_id = project_id
        self._on_data_changed = on_data_changed
        self._on_open_chapter = on_open_chapter
        self._selected_id: int | None = None

        outer = QHBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(12)

        # -- Left: chapter list + list controls ----------------------------
        left = QVBoxLayout()
        left.setSpacing(6)
        heading = QLabel("Chapters")
        heading.setStyleSheet(
            f"color: {theme.TEXT_PRIMARY}; font-size: 14px; font-weight: 700;")
        left.addWidget(heading)

        self._list = QListWidget()
        self._list.setMinimumWidth(220)
        self._list.currentItemChanged.connect(self._on_selected)
        left.addWidget(self._list, stretch=1)

        row = QHBoxLayout()
        row.setSpacing(4)
        new_btn = QPushButton("New Chapter")
        new_btn.setStyleSheet(theme.primary_btn())
        new_btn.clicked.connect(self._new_chapter)
        row.addWidget(new_btn)
        self._up_btn = QPushButton("↑")
        self._up_btn.setFixedWidth(30)
        self._up_btn.clicked.connect(lambda: self._move(-1))
        row.addWidget(self._up_btn)
        self._down_btn = QPushButton("↓")
        self._down_btn.setFixedWidth(30)
        self._down_btn.clicked.connect(lambda: self._move(1))
        row.addWidget(self._down_btn)
        left.addLayout(row)
        outer.addLayout(left, stretch=1)

        # -- Right: edit form ----------------------------------------------
        right = QVBoxLayout()
        right.setSpacing(6)
        right.addWidget(QLabel("Title"))
        self._title_input = QLineEdit()
        self._title_input.setPlaceholderText("e.g. Chapter 1 — The Arrival")
        right.addWidget(self._title_input)
        right.addWidget(QLabel("Summary / description"))
        self._summary_input = QPlainTextEdit()
        self._summary_input.setMaximumHeight(90)
        right.addWidget(self._summary_input)
        right.addWidget(QLabel("Chapter text"))
        self._body_input = QPlainTextEdit()
        right.addWidget(self._body_input, stretch=1)

        btns = QHBoxLayout()
        btns.setSpacing(4)
        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self._save)
        btns.addWidget(save_btn)
        self._open_btn = QPushButton("Open in Manuscript")
        self._open_btn.clicked.connect(self._open_in_manuscript)
        btns.addWidget(self._open_btn)
        btns.addStretch()
        self._delete_btn = QPushButton("Delete")
        self._delete_btn.clicked.connect(self._delete)
        btns.addWidget(self._delete_btn)
        right.addLayout(btns)
        outer.addLayout(right, stretch=2)

        self.refresh()

    # -- data -----------------------------------------------------------------

    def refresh(self) -> None:
        self._list.blockSignals(True)
        self._list.clear()
        for ch in self._db.get_chapters(self._project_id):
            item = QListWidgetItem(ch.title or "(untitled chapter)")
            item.setData(0x0100, ch.id)        # Qt.UserRole
            self._list.addItem(item)
        self._list.blockSignals(False)
        # Keep a valid selection (or clear the form if nothing/removed).
        if self._selected_id is not None:
            self._select_id(self._selected_id)
        if self._selected_id is None:
            self._clear_form()

    def _select_id(self, chapter_id: int) -> None:
        for i in range(self._list.count()):
            if self._list.item(i).data(0x0100) == chapter_id:
                self._list.setCurrentRow(i)
                return
        self._selected_id = None

    def _on_selected(self, current: QListWidgetItem | None) -> None:
        if current is None:
            self._selected_id = None
            self._clear_form()
            return
        cid = current.data(0x0100)
        ch = self._db.get_chapter_by_id(cid)
        if ch is None:
            self._selected_id = None
            self._clear_form()
            return
        self._selected_id = cid
        self._title_input.setText(ch.title or "")
        self._summary_input.setPlainText(ch.summary or "")
        self._body_input.setPlainText(ch.content or "")

    def _clear_form(self) -> None:
        self._title_input.clear()
        self._summary_input.clear()
        self._body_input.clear()

    # -- actions --------------------------------------------------------------

    def _new_chapter(self) -> None:
        n = self._db.get_chapters(self._project_id)
        ch = self._db.create_chapter(
            self._project_id, title=f"Chapter {len(n) + 1}")
        self._selected_id = ch.id
        self.refresh()
        self._notify()

    def _save(self) -> None:
        if self._selected_id is None:
            # No selection → create from the form contents.
            ch = self._db.create_chapter(
                self._project_id,
                title=self._title_input.text().strip() or "Untitled chapter",
                summary=self._summary_input.toPlainText(),
                content=self._body_input.toPlainText(),
            )
            self._selected_id = ch.id
        else:
            self._db.update_chapter(
                self._selected_id,
                title=self._title_input.text().strip(),
                summary=self._summary_input.toPlainText(),
                content=self._body_input.toPlainText(),
            )
        self.refresh()
        self._notify()

    def _move(self, delta: int) -> None:
        if self._selected_id is None:
            return
        chapters = self._db.get_chapters(self._project_id)
        idx = next((i for i, c in enumerate(chapters)
                    if c.id == self._selected_id), None)
        if idx is None:
            return
        self._db.reorder_chapter(self._selected_id, idx + delta)
        self.refresh()
        self._notify()

    def _delete(self) -> None:
        if self._selected_id is None:
            return
        ch = self._db.get_chapter_by_id(self._selected_id)
        name = (ch.title if ch else "this chapter") or "this chapter"
        answer = QMessageBox.question(
            self, "Delete chapter",
            f"Delete “{name}”? This cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._db.delete_chapter(self._selected_id)
        self._selected_id = None
        self.refresh()
        self._notify()

    def _open_in_manuscript(self) -> None:
        if self._selected_id is not None and self._on_open_chapter is not None:
            self._on_open_chapter(self._selected_id)

    def _notify(self) -> None:
        if self._on_data_changed:
            self._on_data_changed()
