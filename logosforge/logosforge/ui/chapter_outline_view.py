"""Novel Outline — Act → Chapter planning over the Chapter store.

Novel's primary unit is the Chapter, so the Outline section in Novel shows a
two-level Act → Chapter hierarchy and applies AI generation to the Chapter
planning store (title / summary / act) — never to any manuscript body. Non-Novel
modes keep the existing scene-based PlanView (Act → Scene).
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from logosforge.db import Database
from logosforge.ui import theme

_CHAPTER_ID = Qt.ItemDataRole.UserRole


class ChapterOutlineView(QWidget):
    """Act → Chapter outline for Novel mode."""

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
        self._gen_worker = None

        outer = QHBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(12)

        left = QVBoxLayout()
        left.setSpacing(6)
        header = QHBoxLayout()
        title = QLabel("Outline")
        title.setStyleSheet(
            f"color: {theme.TEXT_PRIMARY}; font-size: 14px; font-weight: 700;")
        header.addWidget(title)
        badge = QLabel("Novel · Act → Chapter")
        badge.setStyleSheet(f"color: {theme.TEXT_MUTED}; font-size: 10px;")
        header.addWidget(badge)
        header.addStretch()
        left.addLayout(header)

        self._tree = QTreeWidget()
        self._tree.setHeaderHidden(True)
        self._tree.setMinimumWidth(260)
        self._tree.currentItemChanged.connect(self._on_selected)
        left.addWidget(self._tree, stretch=1)

        btns = QHBoxLayout()
        btns.setSpacing(4)
        gen_btn = QPushButton("✨ Generate Outline")
        gen_btn.setStyleSheet(theme.primary_btn())
        gen_btn.clicked.connect(self._generate)
        btns.addWidget(gen_btn)
        add_act = QPushButton("+ Act")
        add_act.clicked.connect(self._add_act)
        btns.addWidget(add_act)
        add_chap = QPushButton("+ Chapter")
        add_chap.clicked.connect(self._add_chapter)
        btns.addWidget(add_chap)
        left.addLayout(btns)
        self._status = QLabel("")
        self._status.setStyleSheet(f"color: {theme.ACCENT}; font-size: 10px;")
        left.addWidget(self._status)
        outer.addLayout(left, stretch=1)

        # Right edit form.
        right = QVBoxLayout()
        right.setSpacing(6)
        right.addWidget(QLabel("Chapter title"))
        self._title_input = QLineEdit()
        right.addWidget(self._title_input)
        right.addWidget(QLabel("Description / purpose"))
        self._desc_input = QPlainTextEdit()
        right.addWidget(self._desc_input, stretch=1)
        form_btns = QHBoxLayout()
        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self._save)
        form_btns.addWidget(save_btn)
        open_btn = QPushButton("Open in Manuscript")
        open_btn.clicked.connect(self._open)
        form_btns.addWidget(open_btn)
        form_btns.addStretch()
        del_btn = QPushButton("Delete")
        del_btn.clicked.connect(self._delete)
        form_btns.addWidget(del_btn)
        right.addLayout(form_btns)
        outer.addLayout(right, stretch=2)

        self.refresh()

    # -- build --------------------------------------------------------------

    def refresh(self) -> None:
        self._tree.blockSignals(True)
        self._tree.clear()
        act_nodes: dict[str, QTreeWidgetItem] = {}
        for ch in self._db.get_chapters(self._project_id):
            act = (ch.act or "").strip() or "(no act)"
            parent = act_nodes.get(act)
            if parent is None:
                parent = QTreeWidgetItem([f"Act — {act}" if act != "(no act)" else act])
                parent.setFirstColumnSpanned(True)
                self._tree.addTopLevelItem(parent)
                parent.setExpanded(True)
                act_nodes[act] = parent
            label = ch.title or "(untitled chapter)"
            if (ch.summary or "").strip():
                label += f"  —  {ch.summary.strip()[:50]}"
            item = QTreeWidgetItem([label])
            item.setData(0, _CHAPTER_ID, ch.id)
            parent.addChild(item)
        self._tree.blockSignals(False)
        if self._selected_id is not None:
            self._select_id(self._selected_id)
        if self._selected_id is None:
            self._clear_form()

    def _select_id(self, chapter_id: int) -> None:
        it = self._find_item(chapter_id)
        if it is not None:
            self._tree.setCurrentItem(it)
        else:
            self._selected_id = None

    def _find_item(self, chapter_id: int):
        for i in range(self._tree.topLevelItemCount()):
            act = self._tree.topLevelItem(i)
            for j in range(act.childCount()):
                c = act.child(j)
                if c.data(0, _CHAPTER_ID) == chapter_id:
                    return c
        return None

    def _on_selected(self, current, _prev=None) -> None:
        cid = current.data(0, _CHAPTER_ID) if current is not None else None
        if cid is None:
            self._selected_id = None
            self._clear_form()
            return
        ch = self._db.get_chapter_by_id(cid)
        if ch is None:
            self._selected_id = None
            self._clear_form()
            return
        self._selected_id = cid
        self._title_input.setText(ch.title or "")
        self._desc_input.setPlainText(ch.summary or "")

    def _clear_form(self) -> None:
        self._title_input.clear()
        self._desc_input.clear()

    # -- actions ------------------------------------------------------------

    def _add_act(self) -> None:
        name, ok = QInputDialog.getText(self, "Add Act", "Act name:", text="New Act")
        if not ok or not name.strip():
            return
        ch = self._db.create_chapter(self._project_id, title="Chapter 1",
                                     act=name.strip())
        self._selected_id = ch.id
        self.refresh()
        self._notify()

    def _add_chapter(self) -> None:
        act = ""
        cur = self._tree.currentItem()
        if cur is not None:
            top = cur if cur.parent() is None else cur.parent()
            txt = top.text(0)
            act = txt[len("Act — "):] if txt.startswith("Act — ") else ""
        n = self._db.get_chapters(self._project_id)
        ch = self._db.create_chapter(self._project_id,
                                     title=f"Chapter {len(n) + 1}", act=act)
        self._selected_id = ch.id
        self.refresh()
        self._notify()

    def _save(self) -> None:
        if self._selected_id is None:
            return
        self._db.update_chapter(
            self._selected_id,
            title=self._title_input.text().strip(),
            summary=self._desc_input.toPlainText())
        self.refresh()
        self._notify()

    def _delete(self) -> None:
        if self._selected_id is None:
            return
        if QMessageBox.question(
            self, "Delete chapter", "Delete this chapter? This cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return
        self._db.delete_chapter(self._selected_id)
        self._selected_id = None
        self.refresh()
        self._notify()

    def _open(self) -> None:
        if self._selected_id is not None and self._on_open_chapter is not None:
            self._on_open_chapter(self._selected_id)

    # -- AI generation ------------------------------------------------------

    def _generate(self) -> None:
        from logosforge.ui.outline_ai import OutlineGenWorker, build_provider, outline_messages
        from logosforge.outline_actions import build_mode_outline_prompt
        if self._gen_worker is not None:
            return
        provider = build_provider()
        if provider is None:
            QMessageBox.information(
                self, "Generate Outline",
                "No AI provider is configured. Set one in Settings first.")
            return
        prompt = build_mode_outline_prompt("novel")
        self._status.setText("Generating…")
        self._gen_worker = OutlineGenWorker(outline_messages(prompt), provider)
        self._gen_worker.completed.connect(self._on_generated)
        self._gen_worker.failed.connect(self._on_generation_failed)
        self._gen_worker.start()

    def _on_generation_failed(self, error: str) -> None:
        self._gen_worker = None
        self._status.setText("")
        QMessageBox.warning(self, "Generate Outline", f"Generation failed:\n\n{error}")

    def _on_generated(self, text: str) -> None:
        self._gen_worker = None
        self._status.setText("")
        self.apply_generated_outline(text)

    def apply_generated_outline(self, text: str, *, confirm: bool = True) -> list[int]:
        """Parse → repair → validate → apply as Chapters (never manuscript)."""
        from logosforge.outline_actions import (
            apply_outline_as_chapters,
            count_ops,
            format_outline_preview,
            parse_outline_response,
            repair_outline_ops,
            validate_mode_outline,
        )
        ops = parse_outline_response(text or "")
        if not ops:
            QMessageBox.information(
                self, "Generate Outline",
                "The AI response did not contain a usable outline.")
            return []
        ops, warnings = repair_outline_ops(ops)
        ok, errors = validate_mode_outline("novel", ops)
        if not ok:
            QMessageBox.warning(
                self, "Generate Outline",
                "The generated outline can't be applied safely:\n\n• "
                + "\n• ".join(errors))
            return []
        if confirm:
            from logosforge.ui.outline_confirm_dialog import OutlineConfirmDialog
            if not OutlineConfirmDialog.confirm(
                format_outline_preview(ops), count_ops(ops),
                title="Apply generated outline (Chapters)", warnings=warnings,
                parent=self):
                return []
        created = apply_outline_as_chapters(self._db, self._project_id, ops)
        if created:
            self.refresh()
            self._notify()
        return created

    def _notify(self) -> None:
        if self._on_data_changed:
            self._on_data_changed()
