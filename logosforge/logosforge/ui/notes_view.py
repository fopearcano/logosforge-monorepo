"""Notes management view — a simple note list + editor with a compact
"Linked to" section that links each note to Outline structure (Act / Chapter /
Scene) and, optionally, PSYKE entries.

Acts/Chapters are string labels (NoteStructureLink, keyed by name); Scenes use
NoteSceneLink; PSYKE uses NotePsykeLink. All are shown together as removable
chips. Everything is project-bound and reloads on project switch.
"""

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from logosforge.db import Database
from logosforge.ui import theme

USER_ROLE = Qt.ItemDataRole.UserRole


class NotesView(QWidget):
    def __init__(
        self,
        db: Database,
        project_id: int,
        on_data_changed: Callable[[], None] | None = None,
        on_link_clicked: Callable[[str, int], None] | None = None,
    ) -> None:
        super().__init__()
        self._db = db
        self._project_id = project_id
        self._on_data_changed = on_data_changed
        self._on_link_clicked = on_link_clicked
        self._selected_id: int | None = None
        # Unsaved-edits guard: any field change marks the form dirty so we can
        # auto-save before the user switches note / starts a new one / navigates
        # away — previously those silently discarded in-progress edits.
        self._dirty = False
        # Snapshot of the last deleted note (fields + links) for one-step undo.
        self._last_deleted: dict | None = None

        root = QHBoxLayout(self)

        # -- Left: search + compact note list --------------------------------
        left = QVBoxLayout()
        left.addWidget(QLabel("Notes"))
        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("Search notes…")
        self._search_input.setClearButtonEnabled(True)
        self._search_input.setMaximumWidth(240)
        self._search_input.textChanged.connect(lambda *_: self._refresh_list())
        left.addWidget(self._search_input)
        self._list = QListWidget()
        self._list.setMaximumWidth(240)
        self._list.currentItemChanged.connect(self._on_selected)
        left.addWidget(self._list)
        new_btn = QPushButton("+ New Note")
        new_btn.clicked.connect(self._clear_form)
        left.addWidget(new_btn)
        root.addLayout(left)

        # -- Right: editor + compact link area -------------------------------
        right = QVBoxLayout()

        self._form_label = QLabel("New Note")
        self._form_label.setStyleSheet("font-weight: bold;")
        right.addWidget(self._form_label)

        right.addWidget(QLabel("Title"))
        self._title_input = QLineEdit()
        right.addWidget(self._title_input)

        content_header = QHBoxLayout()
        content_header.addWidget(QLabel("Content"))
        content_header.addStretch()
        self._preview_btn = QPushButton("Preview")
        self._preview_btn.setCheckable(True)
        self._preview_btn.setFlat(True)
        self._preview_btn.setToolTip("Render the note as Markdown (read-only)")
        self._preview_btn.toggled.connect(self._on_preview_toggled)
        content_header.addWidget(self._preview_btn)
        right.addLayout(content_header)

        self._content_input = QPlainTextEdit()
        right.addWidget(self._content_input, stretch=1)
        self._content_preview = QTextBrowser()
        self._content_preview.setOpenExternalLinks(True)
        self._content_preview.setVisible(False)
        right.addWidget(self._content_preview, stretch=1)

        right.addWidget(QLabel("Tags (comma-separated)"))
        self._tags_input = QLineEdit()
        self._tags_input.setPlaceholderText("e.g. worldbuilding, magic, backstory")
        right.addWidget(self._tags_input)

        self._pinned_check = QCheckBox(
            "Pinned (always include in Assistant context)"
        )
        right.addWidget(self._pinned_check)

        # -- "Linked to" — compact, removable chips --------------------------
        link_header = QHBoxLayout()
        lk = QLabel("Linked to")
        lk.setStyleSheet(f"color: {theme.TEXT_MUTED}; font-weight: bold;")
        link_header.addWidget(lk)
        link_header.addStretch()
        self._link_btn = QPushButton("Link to…")
        self._link_btn.clicked.connect(self._on_link_to)
        link_header.addWidget(self._link_btn)
        right.addLayout(link_header)

        self._links_list = QListWidget()
        self._links_list.setObjectName("noteLinksList")
        self._links_list.setFlow(QListWidget.Flow.LeftToRight)
        self._links_list.setWrapping(True)
        self._links_list.setResizeMode(QListWidget.ResizeMode.Adjust)
        self._links_list.setSpacing(4)
        self._links_list.setMaximumHeight(96)
        self._links_list.setSelectionMode(
            QListWidget.SelectionMode.NoSelection,
        )
        self._links_list.setStyleSheet(
            "QListWidget#noteLinksList { background: transparent; border: none; }"
        )
        self._empty_links = QLabel("No links yet — use “Link to…”.")
        self._empty_links.setStyleSheet(
            f"color: {theme.TEXT_MUTED}; font-style: italic; font-size: 11px;"
        )
        right.addWidget(self._empty_links)
        right.addWidget(self._links_list)

        # -- Controls --------------------------------------------------------
        controls = QHBoxLayout()
        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self._on_save)
        controls.addWidget(save_btn)
        self._delete_btn = QPushButton("Delete")
        self._delete_btn.setEnabled(False)
        self._delete_btn.clicked.connect(self._on_delete)
        controls.addWidget(self._delete_btn)
        self._undo_btn = QPushButton("↶ Undo delete")
        self._undo_btn.setToolTip(
            "Restore the note you just deleted (only while this view is open)")
        self._undo_btn.setVisible(False)
        self._undo_btn.clicked.connect(self._on_undo_delete)
        controls.addWidget(self._undo_btn)
        controls.addStretch()
        right.addLayout(controls)

        root.addLayout(right, stretch=1)

        self._refresh_list()
        self._refresh_links()

        # Track edits (connected last so initial setup doesn't mark dirty).
        self._title_input.textChanged.connect(self._mark_dirty)
        self._content_input.textChanged.connect(self._mark_dirty)
        self._tags_input.textChanged.connect(self._mark_dirty)
        self._pinned_check.toggled.connect(self._mark_dirty)

    # -- Dirty state / autosave ---------------------------------------------

    def _form_base_label(self) -> str:
        return "Edit Note" if self._selected_id is not None else "New Note"

    def _update_form_label(self) -> None:
        base = self._form_base_label()
        self._form_label.setText(f"{base}   •  unsaved" if self._dirty else base)

    def _mark_dirty(self, *_) -> None:
        if not self._dirty:
            self._dirty = True
            self._update_form_label()

    def _set_clean(self) -> None:
        self._dirty = False
        self._update_form_label()

    def _load_into_form(self, note) -> None:
        """Populate the editor from a note without tripping the dirty flag."""
        widgets = (self._title_input, self._content_input,
                   self._tags_input, self._pinned_check)
        for w in widgets:
            w.blockSignals(True)
        self._title_input.setText(note.title)
        self._content_input.setPlainText(note.content)
        self._tags_input.setText(note.tags)
        self._pinned_check.setChecked(note.pinned)
        for w in widgets:
            w.blockSignals(False)
        self._exit_preview()                 # always land in edit mode
        self._set_clean()

    def _flush_pending(self) -> None:
        """Persist in-progress edits before switching away. DB-only (no list
        refresh / data-changed signal) so it's safe to call mid-selection."""
        if not self._dirty:
            return
        title = self._title_input.text().strip()
        content = self._content_input.toPlainText().strip()
        tags = self._tags_input.text().strip()
        pinned = self._pinned_check.isChecked()
        if self._selected_id is not None:
            # Existing note — always persist; keep a title if it was cleared so
            # the body is never dropped.
            self._db.update_note(self._selected_id, title or "Untitled",
                                 content, tags=tags, pinned=pinned)
        elif title or content:
            # New note with something in it — auto-create rather than lose it.
            note = self._db.create_note(self._project_id, title or "Untitled",
                                        content, tags=tags, pinned=pinned)
            self._selected_id = note.id
        self._dirty = False

    def hideEvent(self, event) -> None:
        # Best-effort save when the section is navigated away from / closed.
        try:
            self._flush_pending()
        except Exception:
            pass
        super().hideEvent(event)

    # -- Markdown preview ----------------------------------------------------

    def _on_preview_toggled(self, checked: bool) -> None:
        """Toggle between the plain-text editor and a read-only Markdown render
        of the current content (content stays plain text — preview only)."""
        if checked:
            try:
                from logosforge.ui.chat_view import render_markdown_html
                self._content_preview.setHtml(
                    render_markdown_html(self._content_input.toPlainText()))
                self._content_input.setVisible(False)
                self._content_preview.setVisible(True)
            except Exception:
                # Never get stuck half-rendered — fall back to the editor.
                self._content_preview.setVisible(False)
                self._content_input.setVisible(True)
                self._preview_btn.blockSignals(True)
                self._preview_btn.setChecked(False)
                self._preview_btn.blockSignals(False)
        else:
            self._content_preview.setVisible(False)
            self._content_input.setVisible(True)

    def _exit_preview(self) -> None:
        """Force back to edit mode (used when (re)loading a note)."""
        if self._preview_btn.isChecked():
            self._preview_btn.setChecked(False)   # toggled → shows the editor

    # -- List ----------------------------------------------------------------

    def _refresh_list(self) -> None:
        self._list.blockSignals(True)
        self._list.clear()
        query = (self._search_input.text().strip().lower()
                 if hasattr(self, "_search_input") else "")
        notes = self._db.get_all_notes(self._project_id)
        # Pinned notes float to the top, then alphabetical by title.
        notes.sort(key=lambda n: (not n.pinned, (n.title or "untitled").lower()))
        for note in notes:
            if query:
                hay = f"{note.title}\n{note.content}\n{note.tags}".lower()
                if query not in hay:
                    continue
            label = note.title or "Untitled"
            if note.pinned:
                label = f"📌 {label}"
            item = QListWidgetItem(label)
            item.setData(USER_ROLE, note.id)
            self._list.addItem(item)
        self._list.blockSignals(False)

    def refresh(self) -> None:
        self._refresh_list()
        self._refresh_links()

    # -- Selection -----------------------------------------------------------

    def _on_selected(self, current: QListWidgetItem | None) -> None:
        if current is None:
            return
        self._flush_pending()   # save edits to the PREVIOUS note before loading
        self._undo_btn.setVisible(False)   # moving on — undo no longer applies
        note = self._db.get_note_by_id(current.data(USER_ROLE))
        if note is None:
            return
        self._selected_id = note.id
        self._delete_btn.setEnabled(True)
        self._load_into_form(note)
        self._refresh_links()

    # -- Save / Delete -------------------------------------------------------

    def _on_save(self) -> None:
        title = self._title_input.text().strip()
        if not title:
            # Was a silent no-op; now say why nothing happened.
            self._form_label.setText(
                f"{self._form_base_label()}   —  add a title to save")
            return
        content = self._content_input.toPlainText().strip()
        tags = self._tags_input.text().strip()
        pinned = self._pinned_check.isChecked()

        if self._selected_id is not None:
            self._db.update_note(
                self._selected_id, title, content, tags=tags, pinned=pinned,
            )
        else:
            note = self._db.create_note(
                self._project_id, title, content, tags=tags, pinned=pinned,
            )
            self._selected_id = note.id

        # Keep the saved note selected so it can be linked immediately.
        self._delete_btn.setEnabled(True)
        self._set_clean()
        self._refresh_list()
        # If an active search filter hides the just-saved note, clear it so the
        # user can actually see/select what they saved (else the form shows a
        # note that's invisible in the list).
        if not self._list_contains(self._selected_id):
            self._search_input.blockSignals(True)
            self._search_input.clear()
            self._search_input.blockSignals(False)
            self._refresh_list()
        self.select_note(self._selected_id)
        if self._on_data_changed:
            self._on_data_changed()

    def _list_contains(self, note_id) -> bool:
        return any(self._list.item(i).data(USER_ROLE) == note_id
                   for i in range(self._list.count()))

    def _on_delete(self) -> None:
        if self._selected_id is None:
            return
        note = self._db.get_note_by_id(self._selected_id)
        name = note.title if note else "this note"
        if QMessageBox.question(
            self, "Delete Note",
            f"Delete “{name}”? You can undo while this view stays open.",
        ) != QMessageBox.StandardButton.Yes:
            return
        # Snapshot the note + its links so the delete can be undone.
        self._last_deleted = {
            "title": note.title, "content": note.content,
            "tags": note.tags, "pinned": note.pinned,
            "links": self._collect_links(),
        } if note else None
        self._db.delete_note(self._selected_id)
        self._dirty = False          # discard the deleted note's edits
        self._reset_form()
        self._refresh_list()
        self._undo_btn.setVisible(self._last_deleted is not None)
        if self._on_data_changed:
            self._on_data_changed()

    def _on_undo_delete(self) -> None:
        data = self._last_deleted
        if not data:
            return
        note = self._db.create_note(
            self._project_id, data["title"] or "Untitled", data["content"],
            tags=data["tags"], pinned=data["pinned"],
        )
        for ln in data["links"]:
            kind, ref = ln["kind"], ln["ref"]
            if kind in ("act", "chapter"):
                self._db.add_note_structure_link(
                    note.id, self._project_id, kind, ref)
            elif kind == "scene":
                # Skip if the scene was deleted between delete and undo.
                if self._db.get_scene_by_id(ref) is not None:
                    self._db.link_note_to_scene(note.id, ref)
            elif kind == "psyke":
                if self._db.get_psyke_entry_by_id(ref) is not None:
                    self._db.link_note_to_psyke(note.id, ref)
        self._last_deleted = None
        self._undo_btn.setVisible(False)
        self._refresh_list()
        self.select_note(note.id)
        if self._on_data_changed:
            self._on_data_changed()

    def select_note(self, note_id: int) -> None:
        for i in range(self._list.count()):
            if self._list.item(i).data(USER_ROLE) == note_id:
                self._list.setCurrentRow(i)
                return

    def _clear_form(self) -> None:
        # "+ New Note": save the current note's edits before starting fresh.
        self._flush_pending()
        self._undo_btn.setVisible(False)
        self._reset_form()

    def _reset_form(self) -> None:
        self._selected_id = None
        self._delete_btn.setEnabled(False)
        widgets = (self._title_input, self._content_input,
                   self._tags_input, self._pinned_check)
        for w in widgets:
            w.blockSignals(True)
        self._title_input.clear()
        self._content_input.clear()
        self._tags_input.clear()
        self._pinned_check.setChecked(False)
        for w in widgets:
            w.blockSignals(False)
        self._exit_preview()                 # a fresh form is always editable
        self._list.clearSelection()
        self._set_clean()
        self._refresh_links()

    # -- Linked-to chips -----------------------------------------------------

    def _collect_links(self) -> list[dict]:
        """Aggregate a note's links (act/chapter/scene/psyke) into uniform chip
        descriptors; targets that no longer exist are flagged ``missing``."""
        if self._selected_id is None:
            return []
        from logosforge.story_structure import note_link_label
        out: list[dict] = []
        for ttype, ref in self._db.get_note_structure_links(self._selected_id):
            label, missing = note_link_label(
                self._db, self._project_id, ttype, ref)
            out.append({"kind": ttype, "ref": ref,
                        "label": label, "missing": missing})
        for sid in self._db.get_note_scene_links(self._selected_id):
            label, missing = note_link_label(
                self._db, self._project_id, "scene", sid)
            out.append({"kind": "scene", "ref": sid,
                        "label": label, "missing": missing})
        for eid in self._db.get_note_psyke_links(self._selected_id):
            entry = self._db.get_psyke_entry_by_id(eid)
            out.append({
                "kind": "psyke", "ref": eid,
                "label": f"PSYKE: {entry.name}" if entry else "PSYKE: (missing)",
                "missing": entry is None,
            })
        return out

    def _refresh_links(self) -> None:
        self._links_list.clear()
        links = self._collect_links()
        has = bool(links)
        self._empty_links.setVisible(not has and self._selected_id is not None)
        self._link_btn.setEnabled(self._selected_id is not None)
        for link in links:
            chip = self._make_chip(link)
            item = QListWidgetItem()
            item.setSizeHint(chip.sizeHint())
            self._links_list.addItem(item)
            self._links_list.setItemWidget(item, chip)

    def _make_chip(self, link: dict) -> QWidget:
        """A pill with a label (click → open the linked item, when navigable)
        and a separate ✕ (click → remove the link)."""
        navigable = (link["kind"] in ("scene", "psyke") and not link["missing"]
                     and self._on_link_clicked is not None)
        text = link["label"] + ("  (missing)" if link["missing"] else "")
        chip = QWidget()
        row = QHBoxLayout(chip)
        row.setContentsMargins(8, 1, 4, 1)
        row.setSpacing(2)

        lbl = QPushButton(text)
        lbl.setFlat(True)
        lbl.setStyleSheet(
            f"QPushButton {{ color: {theme.TEXT_PRIMARY}; font-size: 11px;"
            f" border: none; background: transparent; padding: 0; text-align: left; }}"
            + (f"QPushButton:hover {{ color: {theme.ACCENT};"
               f" text-decoration: underline; }}" if navigable else "")
        )
        if navigable:
            lbl.setCursor(Qt.CursorShape.PointingHandCursor)
            lbl.setToolTip("Open the linked item")
            lbl.clicked.connect(lambda _=False, ln=link: self._navigate_link(ln))
        else:
            lbl.setToolTip(link["label"])
        row.addWidget(lbl)

        x = QPushButton("✕")
        x.setFlat(True)
        x.setCursor(Qt.CursorShape.PointingHandCursor)
        x.setToolTip("Remove link")
        x.setStyleSheet(
            f"QPushButton {{ color: {theme.TEXT_MUTED}; font-size: 11px;"
            f" border: none; background: transparent; padding: 0 2px; }}"
            f"QPushButton:hover {{ color: {theme.ACCENT}; }}"
        )
        x.clicked.connect(lambda _=False, ln=link: self._remove_link(ln))
        row.addWidget(x)

        border = theme.TEXT_MUTED if link["missing"] else theme.BORDER
        chip.setStyleSheet(
            f"QWidget {{ border: 1px solid {border}; border-radius: 10px;"
            f" background: {theme.BG_PANEL}; }}"
        )
        return chip

    def _navigate_link(self, link: dict) -> None:
        if self._on_link_clicked is None:
            return
        kind, ref = link["kind"], link["ref"]
        if kind == "scene":
            self._on_link_clicked("Scene", ref)
        elif kind == "psyke":
            self._on_link_clicked("PsykeEntry", ref)

    def _remove_link(self, link: dict) -> None:
        if self._selected_id is None:
            return
        kind, ref = link["kind"], link["ref"]
        if kind in ("act", "chapter"):
            self._db.remove_note_structure_link(self._selected_id, kind, ref)
        elif kind == "scene":
            self._db.unlink_note_from_scene(self._selected_id, ref)
        elif kind == "psyke":
            self._db.unlink_note_from_psyke(self._selected_id, ref)
        self._refresh_links()
        if self._on_data_changed:
            self._on_data_changed()

    # -- "Link to…" menu -----------------------------------------------------

    # Above this many items a flat submenu becomes unwieldy → searchable picker.
    _LINK_MENU_INLINE_MAX = 15

    def _on_link_to(self) -> None:
        if self._selected_id is None:
            QMessageBox.information(
                self, "Link to…", "Save the note first, then add links.",
            )
            return
        menu = QMenu(self)

        acts = self._db.get_scene_acts(self._project_id)
        self._link_category(
            menu, "Act", [(a, a) for a in acts],
            lambda v: self._add_structure("act", v))

        chapters = self._db.get_scene_chapters(self._project_id)
        self._link_category(
            menu, "Chapter", [(c, c) for c in chapters],
            lambda v: self._add_structure("chapter", v))

        scenes = self._db.get_all_scenes(self._project_id)
        self._link_category(
            menu, "Scene",
            [(s.title or "Untitled", s.id) for s in scenes], self._add_scene)

        entries = self._db.get_all_psyke_entries(self._project_id)
        self._link_category(
            menu, "PSYKE",
            [(f"{e.name} ({e.entry_type})", e.id) for e in entries],
            self._add_psyke)

        menu.exec(self._link_btn.mapToGlobal(
            self._link_btn.rect().bottomLeft(),
        ))

    def _link_category(self, menu, label, items, on_pick) -> None:
        """Add a 'Link to…' category. Few items → inline submenu; many → a single
        action that opens a searchable picker (avoids an unbounded mega-menu)."""
        if not items:
            sub = menu.addMenu(label)
            sub.setEnabled(False)
            return
        if len(items) > self._LINK_MENU_INLINE_MAX:
            menu.addAction(
                f"{label}…  ({len(items)})",
                lambda: self._pick_and_link(label, items, on_pick))
        else:
            sub = menu.addMenu(label)
            for disp, val in items:
                sub.addAction(disp, lambda v=val: on_pick(v))

    def _pick_and_link(self, title, items, on_pick) -> None:
        val = self._pick_one(f"Link to {title}", items)
        if val is not None:
            on_pick(val)

    def _pick_one(self, title, items):
        """Filterable picker dialog over (display, value) items. Returns the
        chosen value, or None if cancelled."""
        dlg = QDialog(self)
        dlg.setWindowTitle(title)
        lay = QVBoxLayout(dlg)
        search = QLineEdit()
        search.setPlaceholderText("Type to filter…")
        lay.addWidget(search)
        listw = QListWidget()
        lay.addWidget(listw)

        def _populate(query=""):
            listw.clear()
            q = query.strip().lower()
            for disp, val in items:
                if q and q not in disp.lower():
                    continue
                it = QListWidgetItem(disp)
                it.setData(USER_ROLE, val)
                listw.addItem(it)
            if listw.count():
                listw.setCurrentRow(0)

        _populate()
        search.textChanged.connect(_populate)
        listw.itemDoubleClicked.connect(lambda *_: dlg.accept())
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        lay.addWidget(buttons)
        dlg.resize(320, 360)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return None
        cur = listw.currentItem()
        return cur.data(USER_ROLE) if cur is not None else None

    def _add_structure(self, ttype: str, ref: str) -> None:
        if self._selected_id is None:
            return
        self._db.add_note_structure_link(
            self._selected_id, self._project_id, ttype, ref,
        )
        self._after_link()

    def _add_scene(self, scene_id: int) -> None:
        if self._selected_id is None:
            return
        self._db.link_note_to_scene(self._selected_id, scene_id)
        self._after_link()

    def _add_psyke(self, entry_id: int) -> None:
        if self._selected_id is None:
            return
        self._db.link_note_to_psyke(self._selected_id, entry_id)
        self._after_link()

    def _after_link(self) -> None:
        self._refresh_links()
        if self._on_data_changed:
            self._on_data_changed()
