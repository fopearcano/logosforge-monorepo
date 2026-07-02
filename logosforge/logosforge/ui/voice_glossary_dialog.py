"""Project Voice Glossary manager — safe, parented, modeless dialog.

Lists/edits this project's voice glossary terms (canonical text, spoken
forms, known misrecognitions, category, enabled) and offers the controlled
"Import project terms" action (read-only candidate scan over PSYKE/
characters/Outline titles, created only after the user confirms). Follows
the verified-safe window rules: parented to the main window, modeless, no
extra window flags — never a parentless top-level window.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
)

from logosforge.ui import safe_dialogs
from logosforge.voice import glossary as vg


class VoiceGlossaryDialog(QDialog):
    """Modeless, parented manager for the project's voice glossary."""

    def __init__(self, db, project_id: int, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("voiceGlossaryDialog")
        self.setWindowTitle("Project Voice Glossary (local)")
        self.setModal(False)
        self.setMinimumSize(460, 360)
        self._db = db
        self._project_id = project_id

        layout = QVBoxLayout(self)
        note = QLabel("Local, project-scoped dictation vocabulary — names, "
                      "places, lore terms and known misrecognitions. "
                      "No audio, nothing leaves this device.")
        note.setWordWrap(True)
        note.setStyleSheet("color: #94a3b8; font-size: 11px;")
        layout.addWidget(note)

        self._search = QLineEdit()
        self._search.setObjectName("glossarySearch")
        self._search.setPlaceholderText("Filter terms…")
        self._search.textChanged.connect(self.refresh)
        layout.addWidget(self._search)

        self._list = QListWidget()
        self._list.setObjectName("glossaryList")
        layout.addWidget(self._list, stretch=1)

        form = QHBoxLayout()
        self._canonical = QLineEdit()
        self._canonical.setObjectName("glossaryCanonical")
        self._canonical.setPlaceholderText("Canonical spelling (e.g. Zampanò)")
        form.addWidget(self._canonical, stretch=2)
        self._slips = QLineEdit()
        self._slips.setObjectName("glossarySlips")
        self._slips.setPlaceholderText("Misrecognitions, comma-separated")
        form.addWidget(self._slips, stretch=2)
        self._category = QComboBox()
        self._category.setObjectName("glossaryCategory")
        for category in vg.GLOSSARY_CATEGORIES:
            self._category.addItem(category)
        form.addWidget(self._category)
        layout.addLayout(form)

        buttons = QHBoxLayout()
        for label, slot, name in (
            ("Add", self._on_add, "glossaryAdd"),
            ("Delete", self._on_delete, "glossaryDelete"),
            ("Enable/Disable", self._on_toggle, "glossaryToggle"),
            ("Import project terms…", self._on_import, "glossaryImport"),
        ):
            button = QPushButton(label)
            button.setObjectName(name)
            button.clicked.connect(slot)
            buttons.addWidget(button)
        buttons.addStretch()
        close_btn = QPushButton("Close")
        close_btn.setObjectName("glossaryClose")
        close_btn.clicked.connect(self.hide)
        buttons.addWidget(close_btn)
        layout.addLayout(buttons)

        self.refresh()

    # ------------------------------------------------------------------ data
    def set_project(self, project_id: int) -> None:
        self._project_id = project_id
        self.refresh()

    def _selected_term_id(self) -> int | None:
        item = self._list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def refresh(self) -> None:
        needle = self._search.text().strip().lower()
        self._list.clear()
        for term in self._db.get_voice_glossary_terms(self._project_id):
            slips = ", ".join(vg._forms(term.common_misrecognitions))
            label = f"[{term.category}] {term.canonical_text}"
            if slips:
                label += f"  ←  {slips}"
            if not term.enabled:
                label += "  (disabled)"
            if needle and needle not in label.lower():
                continue
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, term.id)
            item.setToolTip(f"source: {term.source}")
            self._list.addItem(item)

    # --------------------------------------------------------------- actions
    def _on_add(self) -> None:
        ok, reason = vg.validate_glossary_term(self._canonical.text())
        if not ok:
            safe_dialogs.warning(self, "Voice Glossary", reason)
            return
        self._db.create_voice_glossary_term(
            self._project_id, self._canonical.text().strip(),
            common_misrecognitions="\n".join(
                vg._forms(self._slips.text())),
            category=self._category.currentText())
        self._canonical.clear()
        self._slips.clear()
        self.refresh()

    def _on_delete(self) -> None:
        term_id = self._selected_term_id()
        if term_id is None:
            return
        if safe_dialogs.question(self, "Delete term",
                                 "Delete this glossary term?"):
            self._db.delete_voice_glossary_term(term_id)
            self.refresh()

    def _on_toggle(self) -> None:
        term_id = self._selected_term_id()
        if term_id is None:
            return
        term = next((t for t in
                     self._db.get_voice_glossary_terms(self._project_id)
                     if t.id == term_id), None)
        if term is not None:
            self._db.update_voice_glossary_term(term_id,
                                                enabled=not term.enabled)
            self.refresh()

    def _on_import(self) -> None:
        candidates = vg.build_import_candidates(self._db, self._project_id)
        if not candidates:
            safe_dialogs.information(self, "Import project terms",
                                     "No new candidate terms found.")
            return
        preview = ", ".join(c["canonical_text"] for c in candidates[:8])
        if len(candidates) > 8:
            preview += ", …"
        if not safe_dialogs.question(
                self, "Import project terms",
                f"Import {len(candidates)} term(s) from PSYKE/Outline into "
                f"the voice glossary?\n\n{preview}\n\n(PSYKE and the Outline "
                "are not modified.)"):
            return
        created = vg.import_candidates(self._db, self._project_id, candidates)
        safe_dialogs.information(self, "Import project terms",
                                 f"Imported {created} term(s).")
        self.refresh()
