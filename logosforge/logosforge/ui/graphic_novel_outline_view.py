"""LEGACY — NOT ROUTED (kept for compatibility only).

Graphic Novel Outline now mounts the SHARED editor family (see
main_window routing + docs/PORTING_ARCHITECTURE_ALPHA.md); this module is
no longer reachable from Alpha navigation and must not be ported.

Graphic Novel Outline — block/card planner (Act → Page → Scene → Panel).

Mounted as the **Outline** for Graphic Novel projects. Uses the same
block-card UX paradigm as the shared Outline planner (full-width dark
card canvas + header action bar — not the old thin tree with an empty
detail pane), with the Graphic Novel hierarchy substituted:

    Outline                      [+ Act] [+ Page] [+ Scene] [+ Panel] …
    ┌─ ACT 1 ────────────────────────────────────────────────────────┐
    │  ┌─ PAGE 1 · <title> ─────────────────────────────────────────┐│
    │  │  SCENE — A                       (rename · starts-on-page) ││
    │  │    [ PANEL 1 — snippet ]  [ PANEL 2 — snippet ]            ││
    │  └────────────────────────────────────────────────────────────┘│
    │  ┌─ PAGE 2 ───────────────────────────────────────────────────┐│
    │  │  SCENE — A (continued)                                     ││
    │  │  SCENE — B                                                 ││
    │  └────────────────────────────────────────────────────────────┘│
    │  SCENE — D (no pages yet)                                      │
    └─────────────────────────────────────────────────────────────────┘

An Act owns its act-wide Pages and its Scenes; a Panel belongs to one Scene
and sits on one Page; a Scene can span Pages (``(continued)`` groups) and
one Page can hold Panels from several Scenes. **Chapters are hidden**
(compat storage labels only). Coordinates come from
:mod:`graphic_novel_structure`; all edits go through the shared body
(:mod:`graphic_novel_outline`), so the Manuscript mirrors immediately.

Click selects (highlighted card); double-click opens the block in the
Manuscript (Panels deep-link to their script block). Panel text is written
in the Manuscript — cards show snippets, page title/notes and scene
rename/start-page stay inline here. Selection never mutates; deletes
confirm; child-widget-only (no separate route, no top-level window).
No image / prompt / ComfyUI fields.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from logosforge import graphic_novel_outline as gno
from logosforge import graphic_novel_structure as gns
from logosforge import story_structure as ss
from logosforge.ui import safe_dialogs, theme

EMPTY_PROJECT_MESSAGE = "Create an Act to begin your Graphic Novel."

_CARD_BASE = (
    "QFrame#gnPanelCard {{ background: {bg}; border: 1px solid {border};"
    " border-radius: 6px; }}"
    "QFrame#gnPanelCard[selected=\"true\"] {{ border: 1px solid {accent}; }}"
    "QFrame#gnSceneGroup {{ border: none; border-left: 2px solid {border};"
    " border-radius: 0px; }}"
    "QFrame#gnSceneGroup[selected=\"true\"] {{ border-left: 2px solid"
    " {accent}; }}"
    "QFrame#gnPageCard {{ background: {bg}; border: 1px solid {border};"
    " border-radius: 8px; }}"
    "QFrame#gnPageCard[selected=\"true\"] {{ border: 1px solid {accent}; }}"
    "QFrame#gnActCard {{ background: {panel}; border: 1px solid {border};"
    " border-radius: 10px; }}"
    "QFrame#gnActCard[selected=\"true\"] {{ border: 1px solid {accent}; }}"
)


class _FocusPlainText(QPlainTextEdit):
    committed = Signal()

    def focusOutEvent(self, event) -> None:  # noqa: N802 (Qt signature)
        super().focusOutEvent(event)
        self.committed.emit()


class _Card(QFrame):
    """A selectable block card: click selects, double-click opens it in the
    Manuscript. Carries its structural descriptor in ``gn_data``."""

    def __init__(self, view: "GraphicNovelOutlineView", data: dict,
                 object_name: str) -> None:
        super().__init__()
        self._view = view
        self.gn_data = data
        self.setObjectName(object_name)
        self.setProperty("selected", "false")

    def mousePressEvent(self, event) -> None:  # noqa: N802 (Qt signature)
        if event.button() == Qt.MouseButton.LeftButton:
            self._view._select(self.gn_data)
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        self._view._activate(self.gn_data)
        super().mouseDoubleClickEvent(event)


class GraphicNovelOutlineView(QWidget):
    """Block/card Outline over the canonical Act → Page → Scene → Panel."""

    def __init__(
        self, db, project_id: int, *,
        on_data_changed: Callable[[], None] | None = None,
        on_open_manuscript: Callable[[int], None] | None = None,
        on_open_panel: Callable[[int, int, int], None] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("graphicNovelOutlineView")
        self._db = db
        self._project_id = project_id
        self._on_data_changed = on_data_changed
        self._on_open_manuscript = on_open_manuscript
        # Deep-link: opening a Panel focuses its script block in the
        # Manuscript (scene_id, local_page_idx, panel_idx).
        self._on_open_panel = on_open_panel
        self._sel: dict = {}
        self._cards: list[_Card] = []

        self.setStyleSheet(_CARD_BASE.format(
            bg="rgba(255,255,255,0.03)", border=theme.BORDER,
            accent=theme.ACCENT, panel=theme.BG_PANEL))

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 12)
        root.setSpacing(8)

        # -- Header: title + mode chip + action bar (shared Outline style) --
        head = QHBoxLayout()
        head.setSpacing(6)
        title = QLabel("Outline")
        title.setObjectName("gnOutlineHeading")
        title.setStyleSheet(
            f"font-size: 18px; font-weight: bold;"
            f" color: {theme.TEXT_PRIMARY};")
        head.addWidget(title)
        chip = QLabel("Graphic Novel · Act → Page → Scene → Panel")
        chip.setObjectName("gnOutlineModeChip")
        chip.setStyleSheet(f"color: {theme.TEXT_MUTED}; font-size: 11px;")
        head.addWidget(chip)
        head.addStretch()
        for label, slot, name in (
            ("+ Act", self._add_act, "gnOutlineAddAct"),
            ("+ Scene", self._add_scene, "gnOutlineAddScene"),
            ("+ Page", self._add_page, "gnOutlineAddPage"),
            ("+ Panel", self._add_panel, "gnOutlineAddPanel"),
            ("▲", self._move_up, "gnOutlineMoveUp"),
            ("▼", self._move_down, "gnOutlineMoveDown"),
            ("Delete", self._delete_selected, "gnOutlineDelete"),
        ):
            b = QPushButton(label)
            b.setObjectName(name)
            b.clicked.connect(slot)
            head.addWidget(b)
        root.addLayout(head)

        # -- Full-width card canvas --
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setStyleSheet("QScrollArea { border: none; }")
        self._host = QWidget()
        self._host.setObjectName("gnOutlineCanvas")
        self._canvas = QVBoxLayout(self._host)
        self._canvas.setContentsMargins(4, 4, 4, 4)
        self._canvas.setSpacing(10)
        self._scroll.setWidget(self._host)
        root.addWidget(self._scroll, stretch=1)

        self.refresh()

    # -------------------------------------------------------------- rebuild
    def refresh(self) -> None:
        self._cards = []
        while self._canvas.count():
            it = self._canvas.takeAt(0)
            w = it.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        view = gns.act_view(self._db, self._project_id)
        if not view:
            # Empty state A: no Act yet.
            msg = QLabel(EMPTY_PROJECT_MESSAGE)
            msg.setObjectName("gnOutlineEmpty")
            self._canvas.addWidget(msg)
            btn = QPushButton("+ Act")
            btn.setObjectName("gnOutlineDetailAddAct")
            btn.clicked.connect(self._add_act)
            self._canvas.addWidget(btn)
            self._canvas.addStretch()
            self._sel = {}
            return
        for act, pages, placements in view:
            self._canvas.addWidget(self._build_act_card(act, pages,
                                                        placements))
        self._canvas.addStretch()
        self._apply_selection_styles()

    @staticmethod
    def _scene_title(scene) -> str:
        return (getattr(scene, "title", "") or "Untitled").strip() or "Untitled"

    def _register(self, card: _Card) -> _Card:
        self._cards.append(card)
        return card

    def _build_act_card(self, act, pages, placements) -> QFrame:
        card = self._register(_Card(self, {"kind": "act", "act": act},
                                    "gnActCard"))
        v = QVBoxLayout(card)
        v.setContentsMargins(12, 10, 12, 10)
        v.setSpacing(8)
        head = QLabel((act or "Act").upper())
        head.setObjectName("gnActCardTitle")
        head.setStyleSheet(
            f"font-size: 15px; font-weight: bold; letter-spacing: 1px;"
            f" color: {theme.TEXT_PRIMARY};")
        v.addWidget(head)
        for page_no, slices in pages:
            v.addWidget(self._build_page_card(act, page_no, slices))
        # Scenes without pages stay visible inside their Act.
        for placement in placements:
            if placement.page_count == 0:
                v.addWidget(self._build_scene_group(
                    act, placement, local_idx=None, page_no=None,
                    continued=False))
        return card

    def _build_page_card(self, act, page_no, slices) -> QFrame:
        card = self._register(_Card(
            self, {"kind": "act_page", "act": act, "page_no": page_no},
            "gnPageCard"))
        v = QVBoxLayout(card)
        v.setContentsMargins(10, 8, 10, 8)
        v.setSpacing(6)

        head = QHBoxLayout()
        head.setSpacing(8)
        lbl = QLabel(f"PAGE {page_no}")
        lbl.setObjectName("gnOutlinePageHeader")
        lbl.setStyleSheet("font-size: 13px; font-weight: bold;")
        head.addWidget(lbl)
        # Page title/notes live on the scene-local page object: editable on
        # the page's FIRST slice (one page object per scene slice).
        first = slices[0]
        title = QLineEdit(first.page.title or "")
        title.setObjectName("gnOutlinePageTitle")
        title.setPlaceholderText("Page title (optional)")
        title.editingFinished.connect(
            lambda e=title, s=first: self._commit_page(
                s.placement.scene.id, s.local_idx, "title", e.text()))
        head.addWidget(title, stretch=1)
        v.addLayout(head)

        notes = _FocusPlainText()
        notes.setObjectName("gnOutlinePageSummary")
        notes.setPlaceholderText("Page notes (optional)")
        notes.setPlainText(first.page.summary or "")
        notes.setFixedHeight(40)
        notes.committed.connect(
            lambda e=notes, s=first: self._commit_page(
                s.placement.scene.id, s.local_idx, "summary",
                e.toPlainText()))
        v.addWidget(notes)

        for sl in slices:
            v.addWidget(self._build_scene_group(
                act, sl.placement, local_idx=sl.local_idx, page_no=page_no,
                continued=sl.continued, page=sl.page))
        return card

    def _build_scene_group(self, act, placement, *, local_idx, page_no,
                           continued, page=None) -> QFrame:
        sid = placement.scene.id
        if local_idx is None:
            data = {"kind": "scene", "act": act, "scene_id": sid}
        else:
            data = {"kind": "scene_page", "act": act, "scene_id": sid,
                    "page": local_idx, "page_no": page_no,
                    "continued": continued}
        group = self._register(_Card(self, data, "gnSceneGroup"))
        v = QVBoxLayout(group)
        v.setContentsMargins(10, 4, 4, 4)
        v.setSpacing(4)

        head = QHBoxLayout()
        head.setSpacing(8)
        marker = " (continued)" if continued else ""
        suffix = " (no pages yet)" if local_idx is None else ""
        lbl = QLabel(f"SCENE — {self._scene_title(placement.scene)}"
                     f"{marker}{suffix}")
        lbl.setObjectName("gnOutlineSceneLabel")
        lbl.setStyleSheet("font-weight: bold; font-size: 12px;")
        head.addWidget(lbl)
        head.addStretch()
        if not continued:
            rename = QLineEdit(placement.scene.title or "")
            rename.setObjectName("gnOutlineSceneTitle")
            rename.setPlaceholderText("Scene title")
            rename.setMaximumWidth(180)
            rename.editingFinished.connect(
                lambda e=rename, s=sid: self._commit_scene_title(s, e.text()))
            head.addWidget(rename)
            head.addWidget(self._start_page_controls(sid, placement))
        v.addLayout(head)

        if local_idx is None:
            btn = QPushButton("+ Add Page")
            btn.setObjectName("gnOutlineDetailAddPage")
            btn.setFlat(True)
            btn.clicked.connect(
                lambda _=False, s=sid: self._add_page_for(s))
            v.addWidget(btn)
            return group

        for ci, panel in enumerate(page.panels):
            v.addWidget(self._build_panel_card(act, sid, local_idx, ci,
                                               page_no, panel))
        return group

    def _build_panel_card(self, act, sid, local_idx, ci, page_no,
                          panel) -> QFrame:
        card = self._register(_Card(
            self, {"kind": "panel", "act": act, "scene_id": sid,
                   "page": local_idx, "panel": ci, "page_no": page_no},
            "gnPanelCard"))
        row = QHBoxLayout(card)
        row.setContentsMargins(8, 4, 8, 4)
        row.setSpacing(8)
        lbl = QLabel(f"PANEL {panel.number}")
        lbl.setObjectName("gnOutlinePanelHeader")
        lbl.setStyleSheet("font-weight: bold; color: palette(mid);"
                          " font-size: 11px;")
        row.addWidget(lbl)
        snippet = QLabel(gno.panel_snippet(panel))
        snippet.setObjectName("gnOutlinePanelSnippet")
        snippet.setStyleSheet("font-size: 11px;")
        row.addWidget(snippet, stretch=1)
        move = QToolButton()
        move.setObjectName("gnOutlinePanelMove")
        move.setText("⇢")
        move.setToolTip("Move panel to another page of this scene")
        move.clicked.connect(
            lambda _=False, s=sid, p=local_idx, c=ci:
            self._show_move_menu(move, s, p, c))
        row.addWidget(move)
        return card

    def _show_move_menu(self, button, sid, from_idx, ci) -> None:
        script = gno.gnb.load_scene_script(self._db, sid)
        if len(script.pages) < 2:
            return
        _act, placement = gns.find_placement(self._db, self._project_id, sid)
        menu = QMenu(button)
        for to_idx in range(len(script.pages)):
            if to_idx == from_idx:
                continue
            no = placement.global_page(to_idx) if placement else to_idx + 1
            menu.addAction(
                f"Move to Page {no}",
                lambda s=sid, f=from_idx, c=ci, t=to_idx:
                self._assign_panel_to_page(s, f, c, t))
        menu.exec(button.mapToGlobal(button.rect().bottomLeft()))

    def _start_page_controls(self, scene_id: int, placement) -> QWidget:
        """Pin / auto-chain a scene's act-wide start page (how a scene is
        placed onto a shared page)."""
        holder = QWidget()
        row = QHBoxLayout(holder)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(4)
        lbl = QLabel("starts on page")
        lbl.setStyleSheet("color: palette(mid); font-size: 10px;")
        row.addWidget(lbl)
        spin = QSpinBox()
        spin.setObjectName("gnOutlineStartPage")
        spin.setRange(1, 9999)
        spin.setValue(placement.start_page if placement else 1)
        auto = QCheckBox("Auto")
        auto.setObjectName("gnOutlineStartAuto")
        auto.setToolTip("Auto (after previous scene)")
        auto.setChecked(not (placement and placement.explicit))
        spin.setEnabled(not auto.isChecked())

        def commit_spin() -> None:
            if auto.isChecked():
                return
            if gns.set_scene_start_page(self._db, scene_id, spin.value()):
                self._select_scene_node(scene_id)
                self._notify()

        def toggled(checked: bool) -> None:
            spin.setEnabled(not checked)
            value = None if checked else spin.value()
            if gns.set_scene_start_page(self._db, scene_id, value):
                self._select_scene_node(scene_id)
                self._notify()

        spin.editingFinished.connect(commit_spin)
        auto.toggled.connect(toggled)
        row.addWidget(spin)
        row.addWidget(auto)
        return holder

    # -------------------------------------------------------------- selection
    def _apply_selection_styles(self) -> None:
        for card in self._cards:
            selected = "true" if card.gn_data == self._sel else "false"
            if card.property("selected") != selected:
                card.setProperty("selected", selected)
                card.style().unpolish(card)
                card.style().polish(card)

    def _select(self, data: dict) -> None:
        self._sel = dict(data)
        self._apply_selection_styles()

    def _activate(self, data: dict) -> None:
        if not isinstance(data, dict):
            return
        if data.get("kind") == "panel" and self._on_open_panel is not None:
            self._on_open_panel(int(data["scene_id"]),
                                int(data["page"]), int(data["panel"]))
            return
        if data.get("kind") in ("scene", "scene_page", "panel") \
                and self._on_open_manuscript:
            self._on_open_manuscript(int(data["scene_id"]))
        elif data.get("kind") == "act_page" and self._on_open_manuscript:
            # Open the page's first scene in the Manuscript.
            slices = self._act_page_slices(data.get("act"),
                                           data.get("page_no"))
            if slices:
                self._on_open_manuscript(slices[0].placement.scene.id)

    def select_scene(self, scene_id: int) -> None:
        self._select_scene_node(scene_id)
        self._apply_selection_styles()

    def _select_scene_node(self, scene_id: int) -> None:
        """Point _sel at a scene's first card after a structural change."""
        act, placement = gns.find_placement(self._db, self._project_id,
                                            scene_id)
        if placement is None:
            self._sel = {}
        elif placement.page_count:
            self._sel = {"kind": "scene_page", "act": act,
                         "scene_id": scene_id, "page": 0,
                         "page_no": placement.start_page, "continued": False}
        else:
            self._sel = {"kind": "scene", "act": act, "scene_id": scene_id}

    def _act_page_slices(self, act, page_no):
        for a, pages, _placements in gns.act_view(self._db, self._project_id):
            if a != act:
                continue
            for no, slices in pages:
                if no == page_no:
                    return slices
        return []

    # -------------------------------------------------------------- mutations
    def _notify(self) -> None:
        self.refresh()
        if self._on_data_changed:
            self._on_data_changed()

    def _commit_panel(self, sid, pi, ci, field, value) -> None:
        if gno.set_panel_field(self._db, sid, pi, ci, field, value):
            self._notify()

    def _commit_page(self, sid, pi, field, value) -> None:
        if gno.set_page_field(self._db, sid, pi, field, value):
            self._notify()

    def _commit_scene_title(self, sid: int, title: str) -> None:
        title = (title or "").strip()
        scene = self._db.get_scene_by_id(sid)
        # Empty titles are refused (never blank a scene by accident).
        if scene is None or not title or (scene.title or "") == title:
            return
        self._db.update_scene_title(sid, title)
        self._notify()

    def _selected_act(self) -> str | None:
        act = self._sel.get("act")
        if act:
            return act
        acts = [a for a, _s in gns.acts_with_scenes(self._db,
                                                    self._project_id)]
        return acts[-1] if acts else None

    def _add_act(self) -> None:
        scene = ss.create_act(self._db, self._project_id)
        self._select_scene_node(scene.id)
        self._notify()

    def _add_scene(self) -> None:
        act = self._selected_act()
        scene = ss.create_scene(self._db, self._project_id, act=act,
                                title="Untitled Scene")
        self._select_scene_node(scene.id)
        self._notify()

    def _scene_for_structure_ops(self) -> int | None:
        """The scene a '+ Page' acts on: the selected scene, else the
        selected Act's last scene (created if the Act is empty)."""
        sid = self._sel.get("scene_id")
        if sid is not None:
            return sid
        act = self._sel.get("act")
        if not act:
            acts = gns.acts_with_scenes(self._db, self._project_id)
            if not acts:
                return None
            act = acts[-1][0]
        for a, scenes in gns.acts_with_scenes(self._db, self._project_id):
            if a == act:
                if scenes:
                    return scenes[-1].id
                return ss.create_scene(self._db, self._project_id, act=act,
                                       title="Untitled Scene").id
        return None

    def _add_page(self) -> None:
        sid = self._scene_for_structure_ops()
        if sid is None:
            return
        self._add_page_for(sid)

    def _add_page_for(self, sid: int) -> None:
        idx = gno.add_page(self._db, sid)
        act, placement = gns.find_placement(self._db, self._project_id, sid)
        if placement is not None:
            self._sel = {"kind": "scene_page", "act": act, "scene_id": sid,
                         "page": idx, "page_no": placement.global_page(idx),
                         "continued": idx > 0}
        self._notify()

    def _add_panel(self) -> None:
        sid = self._sel.get("scene_id")
        if sid is None:
            return
        page_idx = self._sel.get("page")
        gno.add_panel(self._db, sid, page_idx)
        self._notify()

    def _assign_panel_to_page(self, sid, from_idx, panel_idx, to_idx) -> None:
        if gno.move_panel_to_page(self._db, sid, from_idx, panel_idx, to_idx):
            self._select_scene_node(sid)
            self._notify()

    def _move_up(self) -> None:
        self._move(-1)

    def _move_down(self) -> None:
        self._move(+1)

    def _move(self, delta: int) -> None:
        if self._sel.get("kind") != "panel":
            return
        sid, pi, ci = (self._sel.get("scene_id"), self._sel.get("page"),
                       self._sel.get("panel"))
        if gno.move_panel(self._db, sid, pi, ci, delta):
            self._sel = {**self._sel, "panel": ci + delta}
            self._notify()

    def _delete_selected(self) -> None:
        kind = self._sel.get("kind")
        sid = self._sel.get("scene_id")
        if kind == "panel":
            if not safe_dialogs.question(self, "Delete Panel",
                                         "Delete this panel?"):
                return
            gno.delete_panel(self._db, sid, self._sel.get("page"),
                             self._sel.get("panel"))
            self._select_scene_node(sid)
            self._notify()
        elif kind == "scene_page":
            if not safe_dialogs.question(self, "Delete Page",
                                         "Delete this page and its panels?"):
                return
            gno.delete_page(self._db, sid, self._sel.get("page"))
            self._select_scene_node(sid)
            self._notify()
        elif kind == "scene":
            if not safe_dialogs.question(
                    self, "Delete Scene",
                    "Delete this scene and its pages/panels? "
                    "This removes its body."):
                return
            self._db.delete_scene(sid)
            self._sel = {}
            self._notify()
