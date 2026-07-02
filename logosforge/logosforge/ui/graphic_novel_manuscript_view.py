"""LEGACY — NOT ROUTED (kept for compatibility only).

Graphic Novel Manuscript now mounts the SHARED editor family (see
main_window routing + docs/PORTING_ARCHITECTURE_ALPHA.md); this module is
no longer reachable from Alpha navigation and must not be ported.

Graphic Novel Manuscript — the full block-based writing editor.

The Graphic Novel writing surface, mounted as the **Manuscript** for Graphic
Novel projects. It uses the SAME UX paradigm as the other modes' Manuscript:
one full-width writing canvas over the whole project, structured as blocks —
not a separate page-management screen, not the old standalone "Comics
Script" single-scene renderer (no scene dropdown, no bespoke chrome):

    ACT 1
    ────────────────────────────────────────────────────────────────────
    SCENE 1 · <editable scene title>                        Pages 1–2

      PAGE 1 · <page title>                       [+ Panel] [Delete Page]
        Panel 1                                            ▲ ▼ Delete
        Visual: …        (one free-typing script block per panel;
        Dialogue: …       labels optional — unlabeled text is the Visual)

      PAGE 2 · …

    SCENE 2 · …
    ACT 2 …

Structure is the canonical **Act → Page → Scene → Panel** model from
:mod:`graphic_novel_structure`: PAGE headings show the act-wide page
numbers; a Scene can span Pages and a Page can hold Panels from several
Scenes (each scene edits its own slice). Chapters stay hidden (compat
labels only). The Manuscript derives from the same shared ``Scene.content``
bodies the Outline manages — it owns no separate Page/Panel storage, so the
two mirror immediately. Panel blocks parse back into the canonical
five-field model on commit (focus-out) via
:func:`graphic_novel_blocks.parse_panel_text`; line breaks are preserved;
numbers stay auto-numbered.

Toolbar: a "Graphic Novel" mode label + live word/character count (the
count follows the project Writing Language — no-word-space scripts show an
approximate character count), matching the shared Manuscript toolbar
vocabulary. Empty-state ladder: no Act → *"Create an Act to begin your
Graphic Novel."* (+ Act); scene without pages → + Add Page; page without
panels → + Panel. Child-widget-only; no top-level window; no image /
prompt / ComfyUI fields.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from logosforge import graphic_novel_blocks as gnb
from logosforge import graphic_novel_structure as gns
from logosforge.ui import safe_dialogs, theme

EMPTY_PROJECT_MESSAGE = "Create an Act to begin your Graphic Novel."

_SCRIPT_PLACEHOLDER = (
    "Visual:\n"
    "What we see in this panel…\n\n"
    "Dialogue:\n"
    "NAME: spoken line\n\n"
    "Labels (Visual / Caption / Dialogue / SFX / Notes) are optional — "
    "unlabeled text is the Visual."
)

_BORDERLESS_TEXT = (
    "QPlainTextEdit { border: none; background: transparent;"
    " font-size: 14px; }")
_BORDERLESS_LINE = (
    "QLineEdit { border: none; background: transparent; }")


class _FocusPlainText(QPlainTextEdit):
    """Multi-line edit that commits (emits) when it loses focus."""

    committed = Signal()

    def __init__(self, *a, **k) -> None:
        super().__init__(*a, **k)
        self.setTabChangesFocus(True)   # Tab walks the script like a document

    def focusOutEvent(self, event) -> None:  # noqa: N802 (Qt signature)
        super().focusOutEvent(event)
        self.committed.emit()


class _AutoGrowScript(_FocusPlainText):
    """A script block that grows with its text (no inner scrollbar), so the
    whole manuscript scrolls as ONE document — editor flow, not form fields."""

    focused = Signal()

    def focusInEvent(self, event) -> None:  # noqa: N802 (Qt signature)
        super().focusInEvent(event)
        self.focused.emit()

    def __init__(self, *, min_height: int = 120, parent=None) -> None:
        super().__init__(parent)
        self._min_height = min_height
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setStyleSheet(_BORDERLESS_TEXT)
        self.textChanged.connect(self._grow)
        self._grow()

    def _grow(self) -> None:
        # Block count gives a layout-independent height (the document's pixel
        # size is unreliable before the first paint in offscreen/headless).
        line_h = self.fontMetrics().lineSpacing()
        px = max(self._min_height,
                 self.document().blockCount() * (line_h + 2) + 24)
        self.setFixedHeight(px)

    def setPlainText(self, text: str) -> None:  # noqa: N802 (Qt signature)
        super().setPlainText(text)
        self._grow()


class GraphicNovelManuscriptView(QWidget):
    """Full-document Graphic Novel editor (Act → Page → Scene → Panel)."""

    def __init__(
        self, db, project_id: int, *,
        on_data_changed: Callable[[], None] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("graphicNovelManuscriptView")
        self._db = db
        self._project_id = project_id
        self._on_data_changed = on_data_changed

        # Per-scene parsed bodies for the rendered document.
        self._scripts: dict[int, gnb.GraphicNovelScript] = {}
        self._placements: dict[int, gns.ScenePlacement] = {}
        # Scene the Outline last navigated to (select_page/select_panel are
        # scoped to it; falls back to the first scene).
        self._active_scene_id: int | None = None
        # Last panel whose script block had focus — (scene_id, page, panel).
        # The Voice Commit Router reads this as "the selected Panel".
        self._last_panel_loc: tuple[int, int, int] | None = None
        # Logical location -> live editor widget (focus restore/navigation).
        # Keys: ("panel", sid, pi, ci) -> panel script block;
        #       ("page", sid, pi, "title"|"summary") -> page header editors;
        #       ("scene", sid) -> the scene header (scroll anchor);
        #       ("scene_title", sid) -> the scene title editor.
        self._field_editors: dict[tuple, QWidget] = {}
        # Fingerprint of the rendered document; refresh() skips the rebuild
        # when nothing changed (keeps focus/cursor alive through the
        # app-wide refresh that follows every save).
        self._rendered_fp: tuple | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 8, 10, 8)
        root.setSpacing(8)

        # -- Shared-manuscript-style toolbar: mode label + word count --
        bar = QHBoxLayout()
        bar.setSpacing(8)
        mode = QLabel("Graphic Novel")
        mode.setObjectName("gnModeLabel")
        mode.setStyleSheet(
            f"color: {theme.TEXT_MUTED}; font-size: 11px; font-weight: bold;"
            f" border: 1px solid {theme.BORDER}; border-radius: 8px;"
            f" padding: 2px 8px;")
        bar.addWidget(mode)
        bar.addStretch()
        self._word_count_label = QLabel("")
        self._word_count_label.setObjectName("gnWordCount")
        self._word_count_label.setStyleSheet(
            f"color: {theme.TEXT_MUTED}; font-size: 11px;")
        bar.addWidget(self._word_count_label)
        root.addLayout(bar)

        # -- The document: one full-width writing canvas --
        self._scroll = QScrollArea()
        self._scroll.setObjectName("gnScriptScroll")
        self._scroll.setWidgetResizable(True)
        self._scroll.setStyleSheet("QScrollArea { border: none; }")
        self._host = QWidget()
        self._host.setObjectName("gnScriptHost")
        self._doc_layout = QVBoxLayout(self._host)
        self._doc_layout.setContentsMargins(24, 10, 24, 10)
        self._doc_layout.setSpacing(8)
        self._scroll.setWidget(self._host)
        root.addWidget(self._scroll, stretch=1)

        self.refresh()

    # ---------------------------------------------------------------- refresh
    def refresh(self) -> None:
        """Re-read the shared bodies; rebuild only if something changed."""
        view = gns.act_view(self._db, self._project_id)
        fp = tuple(
            (act, tuple(
                (p.scene.id, (p.scene.title or ""), p.start_page,
                 gnb.serialize_graphic_novel_script(p.script))
                for p in placements))
            for act, _pages, placements in view)
        if fp == self._rendered_fp:
            return                       # rendered UI already matches the data
        focus_loc = self._focused_location()
        self._scripts = {}
        self._placements = {}
        for _act, _pages, placements in view:
            for p in placements:
                self._scripts[p.scene.id] = p.script
                self._placements[p.scene.id] = p
        if self._active_scene_id not in self._scripts:
            self._active_scene_id = next(iter(self._scripts), None)
        self._rebuild_document(view)
        self._rendered_fp = fp
        self._update_word_count()
        if focus_loc is not None:
            self._restore_focus(focus_loc)

    def _mark_rendered_current(self) -> None:
        """After an in-place commit the visible blocks already show the new
        text — record the new state so the app-wide refresh skips the rebuild
        and the user's focus/cursor survive."""
        view_fp = []
        for act, _pages, placements in gns.act_view(self._db,
                                                    self._project_id):
            view_fp.append((act, tuple(
                (p.scene.id, (p.scene.title or ""), p.start_page,
                 gnb.serialize_graphic_novel_script(
                     self._scripts.get(p.scene.id, p.script)))
                for p in placements)))
        self._rendered_fp = tuple(view_fp)

    def _update_word_count(self) -> None:
        from logosforge import languages as L
        code = L.get_project_writing_language(self._db, self._project_id)
        spaced = L.uses_word_spaces(code)
        total = 0
        for script in self._scripts.values():
            for page in script.pages:
                chunks = [page.title, page.summary]
                for panel in page.panels:
                    chunks += [panel.visual_description, panel.caption,
                               panel.dialogue, panel.sfx, panel.notes]
                for text in chunks:
                    if not (text or "").strip():
                        continue
                    total += (len(text.split()) if spaced
                              else len("".join(text.split())))
        self._word_count_label.setText(
            f"{total:,} words" if spaced else f"≈ {total:,} characters")

    # ------------------------------------------------------ focus preservation
    def _focused_location(self) -> tuple | None:
        w = QApplication.focusWidget()
        if w is None or not self.isAncestorOf(w):
            return None
        loc = getattr(w, "_gn_loc", None)
        if loc is None:
            return None
        if isinstance(w, QPlainTextEdit):
            pos = w.textCursor().position()
        elif isinstance(w, QLineEdit):
            pos = w.cursorPosition()
        else:
            pos = 0
        return (loc, pos)

    def _restore_focus(self, focus_loc: tuple) -> None:
        loc, pos = focus_loc
        editor = self._field_editors.get(loc)
        if editor is None:
            return
        editor.setFocus()
        if isinstance(editor, QPlainTextEdit):
            cur = editor.textCursor()
            cur.setPosition(min(pos, len(editor.toPlainText())))
            editor.setTextCursor(cur)
        elif isinstance(editor, QLineEdit):
            editor.setCursorPosition(min(pos, len(editor.text())))

    # ------------------------------------------------------------- navigation
    def select_scene(self, scene_id: int) -> None:
        """Scroll to a scene's section (Outline deep-link); the scene becomes
        the target for select_page/select_panel."""
        self._active_scene_id = scene_id
        anchor = self._field_editors.get(("scene", scene_id))
        if anchor is not None:
            self._scroll.ensureWidgetVisible(anchor)

    def select_page(self, page_idx: int) -> None:
        """Scroll to / focus a page's title in the active scene."""
        sid = self._active_scene_id
        editor = self._field_editors.get(("page", sid, page_idx, "title"))
        if editor is not None:
            self._scroll.ensureWidgetVisible(editor)
            editor.setFocus()

    def select_panel(self, page_idx: int, panel_idx: int) -> None:
        """Scroll to / focus a panel's script block in the active scene."""
        sid = self._active_scene_id
        editor = self._field_editors.get(("panel", sid, page_idx, panel_idx))
        if editor is not None:
            self._note_panel_focus(sid, page_idx, panel_idx)
            self._scroll.ensureWidgetVisible(editor)
            editor.setFocus()

    def _note_panel_focus(self, sid: int, pi: int, ci: int) -> None:
        self._last_panel_loc = (sid, pi, ci)
        self._active_scene_id = sid

    def current_panel_ref(self) -> tuple[int, int, int] | None:
        """The selected Panel for voice commits: (scene_id, page_idx,
        panel_idx) of the last-focused script block, validated against the
        live script — or ``None`` when nothing valid is selected."""
        if self._last_panel_loc is None:
            return None
        sid, pi, ci = self._last_panel_loc
        script = self._scripts.get(sid)
        if script is None or not (0 <= pi < len(script.pages)):
            return None
        if not (0 <= ci < len(script.pages[pi].panels)):
            return None
        return (sid, pi, ci)

    # ------------------------------------------------------------ document
    def _clear_document(self) -> None:
        self._field_editors = {}
        while self._doc_layout.count():
            it = self._doc_layout.takeAt(0)
            w = it.widget()
            if w is not None:
                w.setParent(None)        # drop from the child tree right away
                w.deleteLater()

    def _muted(self, text: str, *, name: str = "") -> QLabel:
        lbl = QLabel(text)
        if name:
            lbl.setObjectName(name)
        lbl.setStyleSheet("color: palette(mid); font-size: 12px;")
        return lbl

    def _rebuild_document(self, view) -> None:
        self._clear_document()
        if not view or not self._scripts:
            # Empty state A: no Act in the project yet.
            msg = QLabel(EMPTY_PROJECT_MESSAGE)
            msg.setObjectName("gnScriptEmpty")
            self._doc_layout.addWidget(msg)
            btn = QPushButton("+ Act")
            btn.setObjectName("gnScriptCreateAct")
            btn.clicked.connect(self._add_act)
            self._doc_layout.addWidget(btn)
            self._doc_layout.addStretch()
            return

        for act, _pages, placements in view:
            header = QLabel((act or "Act").upper())
            header.setObjectName("gnActHeader")
            header.setStyleSheet(
                f"font-size: 18px; font-weight: bold; letter-spacing: 1px;"
                f" color: {theme.TEXT_PRIMARY}; padding-top: 8px;")
            self._doc_layout.addWidget(header)
            rule = QFrame()
            rule.setFrameShape(QFrame.Shape.HLine)
            rule.setObjectName("gnActRule")
            self._doc_layout.addWidget(rule)
            for index, placement in enumerate(placements, start=1):
                self._doc_layout.addWidget(
                    self._build_scene_section(index, placement))

        tail = QHBoxLayout()
        add_scene = QPushButton("+ Scene")
        add_scene.setObjectName("gnScriptAddScene")
        add_scene.setFlat(True)
        add_scene.clicked.connect(self._add_scene)
        tail.addWidget(add_scene)
        add_act = QPushButton("+ Act")
        add_act.setObjectName("gnScriptAddAct")
        add_act.setFlat(True)
        add_act.clicked.connect(self._add_act)
        tail.addWidget(add_act)
        tail.addStretch()
        holder = QWidget()
        holder.setLayout(tail)
        self._doc_layout.addWidget(holder)
        self._doc_layout.addStretch()

    def _build_scene_section(self, index: int,
                             placement: gns.ScenePlacement) -> QFrame:
        sid = placement.scene.id
        section = QFrame()
        section.setObjectName("gnSceneSection")
        v = QVBoxLayout(section)
        v.setContentsMargins(0, 6, 0, 4)
        v.setSpacing(4)

        head = QHBoxLayout()
        head.setSpacing(8)
        lbl = QLabel(f"SCENE {index}")
        lbl.setObjectName("gnSceneHeader")
        lbl.setStyleSheet("font-weight: bold; color: palette(mid);"
                          " font-size: 13px;")
        head.addWidget(lbl)
        title = QLineEdit(placement.scene.title or "")
        title.setObjectName("gnSceneTitle")
        title.setPlaceholderText("Scene title")
        title.setStyleSheet(_BORDERLESS_LINE + " QLineEdit {"
                            " font-size: 14px; font-weight: bold; }")
        title._gn_loc = ("scene_title", sid)
        title.editingFinished.connect(
            lambda e=title, s=sid: self._commit_scene_title(s, e.text()))
        self._field_editors[("scene_title", sid)] = title
        head.addWidget(title, stretch=1)
        pages_chip = QLabel(gns.scene_page_range_label(placement))
        pages_chip.setObjectName("gnScenePagesChip")
        pages_chip.setStyleSheet("color: palette(mid); font-size: 11px;")
        head.addWidget(pages_chip)
        v.addLayout(head)
        self._field_editors[("scene", sid)] = lbl    # scroll anchor

        script = self._scripts[sid]
        if not script.pages:
            # Empty state B: a scene with no pages yet.
            v.addWidget(self._muted("Start the comics script for this "
                                    "scene.", name="gnScriptEmpty"))
            btn = QPushButton("+ Add Page")
            btn.setObjectName("gnDetailAddPage")
            btn.clicked.connect(lambda _=False, s=sid: self._add_page(s))
            v.addWidget(btn)
            return section

        for pi, page in enumerate(script.pages):
            v.addWidget(self._build_page_block(placement, pi, page))
        more = QPushButton("+ Add Page")
        more.setObjectName("gnScriptAddPageBottom")
        more.setFlat(True)
        more.clicked.connect(lambda _=False, s=sid: self._add_page(s))
        v.addWidget(more)
        return section

    def _build_page_block(self, placement: gns.ScenePlacement, pi: int,
                          page: gnb.Page) -> QFrame:
        sid = placement.scene.id
        box = QFrame()
        box.setObjectName("gnPageBlock")
        v = QVBoxLayout(box)
        v.setContentsMargins(0, 10, 0, 4)
        v.setSpacing(4)

        head = QHBoxLayout()
        head.setSpacing(8)
        # Act-wide page number (the Outline's canonical coordinate).
        lbl = QLabel(f"PAGE {placement.global_page(pi)}")
        lbl.setObjectName("gnPageHeader")
        lbl.setStyleSheet("font-size: 16px; font-weight: bold;")
        head.addWidget(lbl)

        title = QLineEdit(page.title or "")
        title.setObjectName("gnPageTitle")
        title.setPlaceholderText("Page title (optional)")
        title.setStyleSheet(_BORDERLESS_LINE + " QLineEdit { font-size: 13px; }")
        title._gn_loc = ("page", sid, pi, "title")
        title.editingFinished.connect(
            lambda e=title, s=sid, p=pi:
            self._commit_page_field(s, p, "title", e.text()))
        self._field_editors[("page", sid, pi, "title")] = title
        head.addWidget(title, stretch=1)

        add_panel = QPushButton("+ Panel")
        add_panel.setObjectName("gnDetailAddPanel")
        add_panel.setFlat(True)
        add_panel.clicked.connect(
            lambda _=False, s=sid, p=pi: self._add_panel(s, p))
        head.addWidget(add_panel)
        del_page = QPushButton("Delete Page")
        del_page.setObjectName("gnPageDelete")
        del_page.setFlat(True)
        del_page.clicked.connect(
            lambda _=False, s=sid, p=pi: self._delete_page(s, p))
        head.addWidget(del_page)
        v.addLayout(head)

        rule = QFrame()
        rule.setFrameShape(QFrame.Shape.HLine)
        rule.setObjectName("gnPageRule")
        v.addWidget(rule)

        notes = _FocusPlainText()
        notes.setObjectName("gnPageSummary")
        notes.setPlaceholderText("Page notes (optional)")
        notes.setPlainText(page.summary or "")
        notes.setFixedHeight(34)
        notes.setStyleSheet(_BORDERLESS_TEXT + " QPlainTextEdit {"
                            " font-size: 12px; font-style: italic; }")
        notes._gn_loc = ("page", sid, pi, "summary")
        notes.committed.connect(
            lambda e=notes, s=sid, p=pi:
            self._commit_page_field(s, p, "summary", e.toPlainText()))
        self._field_editors[("page", sid, pi, "summary")] = notes
        v.addWidget(notes)

        if not page.panels:
            # Empty state C: a page with no panels yet.
            v.addWidget(self._muted("No panels yet. Add a Panel to write "
                                    "this page.", name="gnPageNoPanels"))
        for ci, panel in enumerate(page.panels):
            v.addWidget(self._build_panel_block(sid, pi, ci, panel))
        return box

    def _build_panel_block(self, sid: int, pi: int, ci: int,
                           panel: gnb.Panel) -> QFrame:
        block = QFrame()
        block.setObjectName("gnPanelCard")
        block.setStyleSheet(
            "QFrame#gnPanelCard { border: none;"
            " border-left: 2px solid palette(midlight); }")
        v = QVBoxLayout(block)
        v.setContentsMargins(12, 2, 0, 6)
        v.setSpacing(2)

        head = QHBoxLayout()
        head.setSpacing(4)
        lbl = QLabel(f"Panel {panel.number}")
        lbl.setObjectName("gnPanelHeader")
        lbl.setStyleSheet("font-weight: bold; color: palette(mid);"
                          " font-size: 12px;")
        head.addWidget(lbl)
        head.addStretch()
        for text, delta, name in (("▲", -1, "gnPanelMoveUp"),
                                  ("▼", +1, "gnPanelMoveDown")):
            b = QPushButton(text)
            b.setObjectName(name)
            b.setFlat(True)
            b.setFixedWidth(26)
            b.clicked.connect(
                lambda _=False, s=sid, p=pi, c=ci, d=delta:
                self._move_panel(s, p, c, d))
            head.addWidget(b)
        delb = QPushButton("Delete")
        delb.setObjectName("gnPanelDelete")
        delb.setFlat(True)
        delb.clicked.connect(
            lambda _=False, s=sid, p=pi, c=ci: self._delete_panel(s, p, c))
        head.addWidget(delb)
        v.addLayout(head)

        ed = _AutoGrowScript(min_height=120)
        ed.setObjectName("gnPanelScript")
        ed.setPlaceholderText(_SCRIPT_PLACEHOLDER)
        ed.setPlainText(gnb.panel_script_text(panel))
        ed.focused.connect(
            lambda s=sid, p=pi, c=ci: self._note_panel_focus(s, p, c))
        ed.committed.connect(
            lambda e=ed, s=sid, p=pi, c=ci:
            self._commit_panel_script(s, p, c, e.toPlainText()))
        ed._gn_loc = ("panel", sid, pi, ci)
        self._field_editors[("panel", sid, pi, ci)] = ed
        v.addWidget(ed)
        return block

    # ------------------------------------------------------------- mutations
    def _save(self, sid: int) -> None:
        script = self._scripts.get(sid)
        if script is None:
            return
        gnb.save_scene_script(self._db, sid, script)
        if self._on_data_changed:
            self._on_data_changed()

    def _commit_panel_script(self, sid, page_idx, panel_idx, text) -> None:
        """Parse one panel's script block back into the five canonical fields."""
        try:
            panel = self._scripts[sid].pages[page_idx].panels[panel_idx]
        except (KeyError, IndexError, TypeError):
            return
        fields = gnb.parse_panel_text(text)
        if all(getattr(panel, key, "") == value
               for key, value in fields.items()):
            return
        for key, value in fields.items():
            setattr(panel, key, value)
        self._mark_rendered_current()    # the block already shows this text
        self._update_word_count()
        self._save(sid)

    def _commit_page_field(self, sid, page_idx, field, value) -> None:
        try:
            page = self._scripts[sid].pages[page_idx]
        except (KeyError, IndexError, TypeError):
            return
        if getattr(page, field, None) == value:
            return
        setattr(page, field, value)
        self._mark_rendered_current()
        self._save(sid)

    def _commit_scene_title(self, sid, title) -> None:
        title = (title or "").strip()
        scene = self._db.get_scene_by_id(sid)
        # Empty titles are refused (never blank a scene by accident).
        if scene is None or not title or (scene.title or "") == title:
            return
        self._db.update_scene_title(sid, title)
        self._mark_rendered_current()
        if self._on_data_changed:
            self._on_data_changed()

    def _add_act(self) -> None:
        from logosforge import story_structure as ss
        scene = ss.create_act(self._db, self._project_id)
        self._active_scene_id = scene.id
        self._rendered_fp = None
        self.refresh()
        if self._on_data_changed:
            self._on_data_changed()

    def _add_scene(self) -> None:
        from logosforge import story_structure as ss
        from logosforge import graphic_novel_structure as g
        acts = [a for a, _s in g.acts_with_scenes(self._db, self._project_id)]
        scene = ss.create_scene(self._db, self._project_id,
                                act=acts[-1] if acts else None,
                                title="Untitled Scene")
        self._active_scene_id = scene.id
        self._rendered_fp = None
        self.refresh()
        if self._on_data_changed:
            self._on_data_changed()

    def _add_page(self, sid: int | None = None) -> None:
        sid = sid if sid is not None else self._active_scene_id
        script = self._scripts.get(sid)
        if script is None:
            return
        gnb.add_page(script, title="")
        self._active_scene_id = sid
        self._save(sid)
        self.refresh()
        self.select_page(len(self._scripts[sid].pages) - 1)

    def _add_panel(self, sid: int | None = None,
                   page_idx: int | None = None) -> None:
        sid = sid if sid is not None else self._active_scene_id
        script = self._scripts.get(sid)
        if script is None:
            return
        if not script.pages:
            gnb.add_page(script, title="")
        if page_idx is None or not (0 <= page_idx < len(script.pages)):
            page_idx = len(script.pages) - 1
        gnb.add_panel(script.pages[page_idx])
        gnb._renumber(script)
        self._active_scene_id = sid
        self._save(sid)
        self.refresh()
        self.select_panel(page_idx, len(script.pages[page_idx].panels) - 1)

    def _move_panel(self, sid: int, page_idx: int, panel_idx: int,
                    delta: int) -> None:
        try:
            page = self._scripts[sid].pages[page_idx]
        except (KeyError, IndexError, TypeError):
            return
        if not (0 <= panel_idx < len(page.panels)):
            return
        gnb.move_panel(page, panel_idx, delta)
        self._save(sid)
        self.refresh()

    def _delete_panel(self, sid: int, page_idx: int, panel_idx: int) -> None:
        if not safe_dialogs.question(self, "Delete Panel",
                                     "Delete this panel?"):
            return
        try:
            gnb.delete_panel(self._scripts[sid].pages[page_idx], panel_idx)
        except (KeyError, IndexError, TypeError):
            return
        self._save(sid)
        self.refresh()

    def _delete_page(self, sid: int, page_idx: int) -> None:
        if not safe_dialogs.question(self, "Delete Page",
                                     "Delete this page and its panels?"):
            return
        try:
            gnb.delete_page(self._scripts[sid], page_idx)
        except (KeyError, IndexError, TypeError):
            return
        self._save(sid)
        self.refresh()
