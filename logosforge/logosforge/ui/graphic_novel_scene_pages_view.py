"""Graphic Novel Pages/Panels — scene-centric editor over the *shared* body.

The Graphic Novel scene body is a single source of truth: ``Scene.content``,
parsed/serialized by :mod:`logosforge.graphic_novel_blocks` into Pages → Panels
(visual / caption / dialogue / SFX / notes). The Manuscript editor and this Pages
section both read and write **that same body**, so editing in one is reflected in
the other (on refresh / section switch); there is no second store.

This view is a compact, collapsible navigator/editor: a scene list on the left and,
for the selected scene, collapsible Page groups with collapsible Panel cards. Every
edit / add / delete / reorder mutates the in-memory :class:`GraphicNovelScript` and
saves it back to ``Scene.content`` via ``graphic_novel_blocks.save_scene_script``.

No image generation, no ComfyUI, no prompt fields, no visual canvas — this is
writing/script structure only. It never touches Outline summaries, Timeline,
PSYKE, or Notes (only ``Scene.content``).
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from logosforge import graphic_novel_blocks as gnb
from logosforge.ui import safe_dialogs

_ID_ROLE = Qt.ItemDataRole.UserRole
# (field key, label, multiline?)
_PANEL_FIELDS = (
    ("visual_description", "Visual", True),
    ("caption", "Caption", False),
    ("dialogue", "Dialogue", True),
    ("sfx", "SFX", False),
    ("notes", "Notes", True),
)


class _FocusPlainText(QPlainTextEdit):
    """A multi-line edit that commits (emits) when it loses focus."""

    committed = Signal()

    def focusOutEvent(self, event) -> None:  # noqa: N802 (Qt signature)
        super().focusOutEvent(event)
        self.committed.emit()


class _PanelCard(QWidget):
    """A collapsible card for one Panel. Collapsed → a compact summary; expanded →
    the editable text fields. Emits ``field_changed(field, value)`` on commit."""

    field_changed = Signal(str, str)
    delete_requested = Signal()
    move_requested = Signal(int)        # delta: -1 up / +1 down

    def __init__(self, panel: gnb.Panel, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("gnPanelCard")
        self._panel = panel
        self._collapsed = False
        self._editors: dict[str, QWidget] = {}

        outer = QVBoxLayout(self)
        outer.setContentsMargins(6, 4, 6, 4)
        outer.setSpacing(3)

        header = QHBoxLayout()
        self._toggle = QToolButton()
        self._toggle.setObjectName("gnPanelToggle")
        self._toggle.setArrowType(Qt.ArrowType.DownArrow)
        self._toggle.clicked.connect(lambda: self.set_collapsed(not self._collapsed))
        header.addWidget(self._toggle)
        self._summary = QLabel()
        self._summary.setObjectName("gnPanelSummary")
        header.addWidget(self._summary, stretch=1)
        up = QPushButton("↑"); up.setFixedWidth(26)
        up.clicked.connect(lambda: self.move_requested.emit(-1))
        down = QPushButton("↓"); down.setFixedWidth(26)
        down.clicked.connect(lambda: self.move_requested.emit(1))
        delete = QPushButton("✕"); delete.setFixedWidth(26)
        delete.setObjectName("gnPanelDelete")
        delete.clicked.connect(self.delete_requested.emit)
        for b in (up, down, delete):
            header.addWidget(b)
        outer.addLayout(header)

        self._body = QWidget()
        body = QVBoxLayout(self._body)
        body.setContentsMargins(22, 0, 0, 0)
        body.setSpacing(2)
        for key, label, multiline in _PANEL_FIELDS:
            body.addWidget(QLabel(label))
            if multiline:
                ed = _FocusPlainText()
                ed.setPlainText(getattr(panel, key, "") or "")
                ed.setFixedHeight(46)
                ed.committed.connect(
                    lambda k=key, e=ed: self.field_changed.emit(k, e.toPlainText()))
            else:
                ed = QLineEdit(getattr(panel, key, "") or "")
                ed.editingFinished.connect(
                    lambda k=key, e=ed: self.field_changed.emit(k, e.text()))
            ed.setObjectName(f"gnPanelField_{key}")
            self._editors[key] = ed
            body.addWidget(ed)
        outer.addWidget(self._body)
        self._refresh_summary()

    def _refresh_summary(self) -> None:
        vis = (self._panel.visual_description or "").strip().replace("\n", " ")
        snippet = (vis[:48] + "…") if len(vis) > 48 else (vis or "(empty panel)")
        flags = []
        if (self._panel.dialogue or "").strip():
            flags.append("💬")
        if (self._panel.caption or "").strip():
            flags.append("▤")
        if (self._panel.sfx or "").strip():
            flags.append("✺")
        tag = ("  " + " ".join(flags)) if flags else ""
        self._summary.setText(f"Panel {self._panel.number} — {snippet}{tag}")

    def summary_text(self) -> str:
        return self._summary.text()

    def is_collapsed(self) -> bool:
        return self._collapsed

    def set_collapsed(self, collapsed: bool) -> None:
        self._collapsed = collapsed
        self._body.setVisible(not collapsed)
        self._toggle.setArrowType(
            Qt.ArrowType.RightArrow if collapsed else Qt.ArrowType.DownArrow)
        self._refresh_summary()


class GraphicNovelScenePagesView(QWidget):
    """Scene-centric Pages/Panels editor that shares ``Scene.content`` with the
    Manuscript (via :mod:`graphic_novel_blocks`). Read+write, never a second store."""

    def __init__(
        self, db, project_id: int, *, scene_id: int | None = None,
        on_data_changed: Callable[[], None] | None = None,
        on_open_manuscript: Callable[[int], None] | None = None,
        embedded_as_manuscript: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("graphicNovelScenePagesView")
        self._db = db
        self._project_id = project_id
        self._on_data_changed = on_data_changed
        self._on_open_manuscript = on_open_manuscript
        self._embedded_as_manuscript = embedded_as_manuscript
        self._scene_id: int | None = None
        self._script = gnb.GraphicNovelScript()
        self._panel_cards: list[_PanelCard] = []
        self._collapsed_pages: set[int] = set()   # session-only page collapse state

        root = QHBoxLayout(self)
        root.setContentsMargins(10, 8, 10, 8)
        root.setSpacing(10)

        # -- Left: scene list (canonical order) + scene management --
        left = QVBoxLayout()
        left.setSpacing(4)
        left.addWidget(QLabel("Scenes"))
        self._scene_list = QListWidget()
        self._scene_list.setObjectName("gnPagesSceneList")
        self._scene_list.setMaximumWidth(220)
        self._scene_list.currentItemChanged.connect(self._on_scene_selected)
        left.addWidget(self._scene_list, stretch=1)
        # Create a scene without leaving the editor (so a brand-new Graphic Novel
        # project is never stuck on an empty "Begin writing" prose state).
        add_scene_btn = QPushButton("+ Scene")
        add_scene_btn.setObjectName("gnPagesAddScene")
        add_scene_btn.setToolTip("Create a new Graphic Novel scene")
        add_scene_btn.clicked.connect(self._create_scene)
        left.addWidget(add_scene_btn)
        # "Open in Manuscript" is redundant when this view *is* the Manuscript.
        if not embedded_as_manuscript and on_open_manuscript is not None:
            open_btn = QPushButton("Open in Manuscript")
            open_btn.clicked.connect(self._open_in_manuscript)
            left.addWidget(open_btn)
        root.addLayout(left)

        # -- Right: pages/panels for the selected scene --
        right = QVBoxLayout()
        right.setSpacing(6)
        head = QHBoxLayout()
        self._heading = QLabel("Pages & Panels")
        self._heading.setStyleSheet("font-size: 14px; font-weight: bold;")
        head.addWidget(self._heading, stretch=1)
        for label, slot in (("+ Page", self._add_page), ("+ Panel", self._add_panel),
                            ("Refresh", self.refresh)):
            b = QPushButton(label)
            b.setObjectName("gnPages_" + label.strip("+ ").replace(" ", ""))
            b.clicked.connect(slot)
            head.addWidget(b)
        right.addLayout(head)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._pages_host = QWidget()
        self._pages_layout = QVBoxLayout(self._pages_host)
        self._pages_layout.setContentsMargins(0, 0, 0, 0)
        self._pages_layout.setSpacing(8)
        self._scroll.setWidget(self._pages_host)
        right.addWidget(self._scroll, stretch=1)
        root.addLayout(right, stretch=1)

        self._reload_scene_list(preselect=scene_id)

    # -- Scene list ----------------------------------------------------------

    def _gn_scenes(self) -> list:
        from logosforge import story_structure as ss
        try:
            order = ss.canonical_scene_order(self._db, self._project_id)
            by_id = {s.id: s for s in self._db.get_all_scenes(self._project_id)}
            return [by_id[s] for s in order if s in by_id]
        except Exception:
            try:
                return list(self._db.get_all_scenes(self._project_id) or [])
            except Exception:
                return []

    def _reload_scene_list(self, preselect: int | None = None) -> None:
        self._scene_list.blockSignals(True)
        self._scene_list.clear()
        scenes = self._gn_scenes()
        for s in scenes:
            item = QListWidgetItem((getattr(s, "title", "") or "Untitled").strip()
                                   or "Untitled")
            item.setData(_ID_ROLE, s.id)
            self._scene_list.addItem(item)
        self._scene_list.blockSignals(False)
        if not scenes:
            self._scene_id = None
            self._render_empty(
                "Begin building your Graphic Novel scene. Use “+ Scene” on the "
                "left to create your first scene, then add Pages and Panels here.")
            return
        target = preselect if preselect in {s.id for s in scenes} else scenes[0].id
        for i in range(self._scene_list.count()):
            if self._scene_list.item(i).data(_ID_ROLE) == target:
                self._scene_list.setCurrentRow(i)
                break

    def _on_scene_selected(self, cur, _prev) -> None:
        if cur is None:
            return
        self.select_scene(int(cur.data(_ID_ROLE)))

    def select_scene(self, scene_id: int) -> None:
        self._scene_id = scene_id
        self.refresh()

    def _create_scene(self) -> None:
        """Create a Graphic Novel scene in place and select it (so the editor is
        never stuck on an empty no-scene state). Writes only a new Scene; the
        page/panel body is added afterwards via “+ Page” / “+ Panel”."""
        from logosforge import story_structure as ss
        scene = ss.create_scene(self._db, self._project_id,
                                title="Untitled Scene")
        self._reload_scene_list(preselect=scene.id)
        if self._on_data_changed:
            self._on_data_changed()

    # -- Build pages/panels (read from the shared Scene.content body) --------

    def refresh(self) -> None:
        """Reload the selected scene's body from Scene.content and rebuild. This is
        how Manuscript edits become visible here (shared single source)."""
        # Keep the scene list in sync with the project (renames/new scenes).
        if self._scene_list.count() != len(self._gn_scenes()):
            self._reload_scene_list(preselect=self._scene_id)
            return
        if self._scene_id is None:
            self._render_empty("Select a scene.")
            return
        self._script = gnb.load_scene_script(self._db, self._scene_id)
        self._render_pages()

    def _clear_pages(self) -> None:
        self._panel_cards = []
        while self._pages_layout.count():
            item = self._pages_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

    def _render_empty(self, message: str) -> None:
        self._clear_pages()
        lbl = QLabel(message)
        lbl.setObjectName("gnPagesEmpty")
        lbl.setWordWrap(True)
        self._pages_layout.addWidget(lbl)
        self._pages_layout.addStretch()

    def _render_pages(self) -> None:
        self._clear_pages()
        if not self._script.pages:
            self._render_empty("Add a Page to start structuring panels — use "
                               "“+ Page” above. Panels hold Visual / Caption / "
                               "Dialogue / SFX / Notes.")
            return
        for pi, page in enumerate(self._script.pages):
            self._pages_layout.addWidget(self._build_page_widget(pi, page))
        self._pages_layout.addStretch()

    def _build_page_widget(self, page_idx: int, page: gnb.Page) -> QWidget:
        box = QWidget()
        box.setObjectName("gnPageGroup")
        lay = QVBoxLayout(box)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(3)

        header = QHBoxLayout()
        toggle = QToolButton()
        collapsed = page_idx in self._collapsed_pages
        toggle.setArrowType(Qt.ArrowType.RightArrow if collapsed
                            else Qt.ArrowType.DownArrow)
        ptitle = (page.title or "").strip()
        head_lbl = QLabel(f"Page {page.number}" + (f" — {ptitle}" if ptitle else "")
                          + f"   ({len(page.panels)} panel(s))")
        head_lbl.setStyleSheet("font-weight: bold;")
        body = QWidget()
        body.setVisible(not collapsed)

        def _toggle_page() -> None:
            now = page_idx not in self._collapsed_pages
            if now:
                self._collapsed_pages.add(page_idx)
            else:
                self._collapsed_pages.discard(page_idx)
            body.setVisible(not now)
            toggle.setArrowType(Qt.ArrowType.RightArrow if now
                                else Qt.ArrowType.DownArrow)
        toggle.clicked.connect(_toggle_page)
        header.addWidget(toggle)
        header.addWidget(head_lbl, stretch=1)
        del_page = QPushButton("Delete Page")
        del_page.clicked.connect(lambda: self._delete_page(page_idx))
        header.addWidget(del_page)
        lay.addLayout(header)

        bl = QVBoxLayout(body)
        bl.setContentsMargins(8, 0, 0, 0)
        bl.setSpacing(4)
        for ci, panel in enumerate(page.panels):
            card = _PanelCard(panel)
            card.field_changed.connect(
                lambda field, value, p=page_idx, c=ci:
                self._set_panel_field(p, c, field, value))
            card.delete_requested.connect(
                lambda p=page_idx, c=ci: self._delete_panel(p, c))
            card.move_requested.connect(
                lambda delta, p=page_idx, c=ci: self._move_panel(p, c, delta))
            self._panel_cards.append(card)
            bl.addWidget(card)
        lay.addWidget(body)
        return box

    # -- Mutations (write the shared Scene.content body) ---------------------

    def _save(self) -> None:
        if self._scene_id is None:
            return
        gnb.save_scene_script(self._db, self._scene_id, self._script)
        if self._on_data_changed:
            self._on_data_changed()

    def _set_panel_field(self, page_idx: int, panel_idx: int, field: str,
                         value: str) -> None:
        try:
            panel = self._script.pages[page_idx].panels[panel_idx]
        except (IndexError, AttributeError):
            return
        if getattr(panel, field, None) == value:
            return
        setattr(panel, field, value)
        self._save()

    def _add_page(self) -> None:
        if self._scene_id is None:
            return
        gnb.add_page(self._script, title="")
        self._save()
        self._render_pages()

    def _add_panel(self) -> None:
        if self._scene_id is None:
            return
        if not self._script.pages:
            gnb.add_page(self._script, title="")
        gnb.add_panel(self._script.pages[-1])
        gnb._renumber(self._script)
        self._save()
        self._render_pages()

    def _move_panel(self, page_idx: int, panel_idx: int, delta: int) -> None:
        try:
            gnb.move_panel(self._script.pages[page_idx], panel_idx, delta)
        except (IndexError, AttributeError):
            return
        self._save()
        self._render_pages()

    def _delete_panel(self, page_idx: int, panel_idx: int,
                      confirm: bool = True) -> None:
        try:
            page = self._script.pages[page_idx]
        except (IndexError, AttributeError):
            return
        if confirm:
            if not safe_dialogs.question(self, "Delete Panel",
                                         "Delete this panel?"):
                return
        gnb.delete_panel(page, panel_idx)
        self._save()
        self._render_pages()

    def _delete_page(self, page_idx: int, confirm: bool = True) -> None:
        if confirm:
            if not safe_dialogs.question(self, "Delete Page",
                                         "Delete this page and its panels?"):
                return
        gnb.delete_page(self._script, page_idx)
        self._save()
        self._render_pages()

    # -- Navigation ----------------------------------------------------------

    def _open_in_manuscript(self) -> None:
        if self._scene_id is not None and self._on_open_manuscript:
            self._on_open_manuscript(self._scene_id)
