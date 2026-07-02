"""Graphic Novel — Page & Panel management.

The structured editing surface for Graphic Novel projects: a page list on
the left (add / reorder / delete + a page form), and, for the selected
page, a panel list with a panel editor on the right. It is the creation UI
for the GraphicNovelPage / GraphicNovelPanel data that the GN plot,
timeline, graph and assistant features already consume.

Engine-gated: for non-Graphic-Novel projects the view shows an inert
placeholder and all mutating methods are no-ops.

This slice is deliberately structural — no page canvas / thumbnail
rendering yet (that is a later slice).
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from logosforge.db import Database
from logosforge.models import GN_DENSITY_LEVELS, GN_TRANSITION_TYPES
from logosforge.ui import theme
from logosforge.ui.graphic_novel_page_canvas import GraphicNovelPageCanvas

# Shot / camera vocabularies kept local — they are presentation choices, not
# persisted enums (the columns are free-text on the model).
_SHOT_TYPES = (
    "", "establishing", "wide", "full", "medium", "close_up",
    "extreme_close_up", "insert", "splash",
)
_CAMERA_ANGLES = (
    "", "eye_level", "high_angle", "low_angle", "birds_eye",
    "worms_eye", "dutch_tilt", "over_shoulder", "pov",
)
_REVEAL_TYPES = ("", "none", "page_turn", "cliffhanger", "splash_reveal")

_ID_ROLE = Qt.ItemDataRole.UserRole


class GraphicNovelPagesView(QWidget):
    """Page list + panel list/editor for Graphic Novel projects."""

    data_changed = Signal()

    def __init__(
        self,
        db: Database,
        project_id: int,
        on_data_changed: Callable[[], None] | None = None,
    ) -> None:
        super().__init__()
        self._db = db
        self._project_id = project_id
        self._on_data_changed = on_data_changed

        project = db.get_project_by_id(project_id)
        from logosforge.project_compat import get_project_narrative_engine
        self._graphic_novel_mode = (
            get_project_narrative_engine(project) == "graphic_novel"
        )

        self._current_page_id: int | None = None
        self._current_panel_id: int | None = None
        # Guards so programmatic list updates don't re-trigger selection logic.
        self._loading = False
        self._canvas: GraphicNovelPageCanvas | None = None

        if self._graphic_novel_mode:
            self._build_ui()
            self.refresh()
        else:
            self._build_placeholder()

    # -- Build ---------------------------------------------------------------

    def _build_placeholder(self) -> None:
        layout = QVBoxLayout(self)
        msg = QLabel(
            "Pages are only available for Graphic Novel projects.\n"
            "Switch the project's narrative engine to Graphic Novel to plan "
            "pages and panels."
        )
        msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        msg.setStyleSheet(f"color: {theme.TEXT_MUTED};")
        layout.addWidget(msg)

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        self._canvas = GraphicNovelPageCanvas(
            self._db, on_panel_selected=self._on_canvas_panel_clicked,
        )

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._build_page_pane())
        splitter.addWidget(self._build_panel_pane())
        splitter.addWidget(self._canvas)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)
        splitter.setStretchFactor(2, 3)
        outer.addWidget(splitter)

    def _on_canvas_panel_clicked(self, panel_id: int) -> None:
        """Canvas box clicked → drive the shared selection."""
        self.select_panel(panel_id)

    # -- AI prompt export (one-way: structure + PSYKE -> prompt packet) ------

    def build_panel_prompt_package(self):
        """Prompt package for the selected panel (None if none / non-GN)."""
        if not self._graphic_novel_mode or self._current_panel_id is None:
            return None
        from logosforge.graphic_novel_ai_export import (
            build_gn_panel_prompt_package,
        )
        return build_gn_panel_prompt_package(
            self._db, self._project_id, self._current_panel_id,
        )

    def build_page_prompt_packages(self):
        if not self._graphic_novel_mode or self._current_page_id is None:
            return []
        from logosforge.graphic_novel_ai_export import (
            build_gn_page_prompt_packages,
        )
        return build_gn_page_prompt_packages(
            self._db, self._project_id, self._current_page_id,
        )

    def _copy(self, text: str) -> None:
        from PySide6.QtWidgets import QApplication
        QApplication.clipboard().setText(text or "")

    def copy_panel_prompt(self) -> None:
        pkg = self.build_panel_prompt_package()
        if pkg is not None:
            self._copy(pkg.prompt)

    def copy_panel_negative_prompt(self) -> None:
        pkg = self.build_panel_prompt_package()
        if pkg is not None:
            self._copy(pkg.negative_prompt)

    def copy_page_prompts(self) -> None:
        from logosforge.graphic_novel_ai_export import package_to_markdown
        pkgs = self.build_page_prompt_packages()
        if pkgs:
            self._copy(package_to_markdown(pkgs))

    def export_panel_prompt(self, fmt: str = "json") -> str | None:
        pkg = self.build_panel_prompt_package()
        if pkg is None:
            return None
        return self._save_export(pkg, fmt, f"panel_{self._current_panel_id}")

    def export_page_prompts(self, fmt: str = "json") -> str | None:
        pkgs = self.build_page_prompt_packages()
        if not pkgs:
            return None
        return self._save_export(pkgs, fmt, f"page_{self._current_page_id}")

    def _save_export(self, package, fmt: str, stem: str) -> str | None:
        from logosforge.graphic_novel_ai_export import (
            package_to_json,
            package_to_markdown,
        )
        if fmt == "markdown":
            content, ext, filt = (
                package_to_markdown(package), "md", "Markdown (*.md)",
            )
        else:
            content, ext, filt = (
                package_to_json(package), "json", "JSON (*.json)",
            )
        from PySide6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Prompt", f"{stem}_prompt.{ext}", filt,
        )
        if not path:
            return None
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(content)
        return path

    # -- Manuscript draft generation (one-way: structure -> prose) -----------

    def generate_manuscript_draft(
        self, scope: str = "all", *, confirm: bool = True,
    ) -> str | None:
        """Generate a manuscript scaffold from GN structure and append it to
        the manuscript as ordinary editable text.

        One-way and additive: reads pages/panels, writes Scene.content only.
        Never parses prose back, never mutates pages/panels, never overwrites
        existing scene text (it appends). Returns the generated text, or None
        if nothing was generated / the user declined.
        """
        if not self._graphic_novel_mode:
            return None
        text = self._build_draft_text(scope)
        if not text or not text.strip():
            return None

        target = self._draft_target_scene()
        if target is None:
            # No manuscript scene exists — create one only with confirmation
            # (silent scene creation is avoided).
            if confirm and not self._confirm(
                "No manuscript scene exists. Create one for the Graphic "
                "Novel draft?"
            ):
                return None
            scene = self._db.create_scene(
                self._project_id, title="Graphic Novel Draft", content=text,
            )
            self._notify_scene_list_changed(scene.id)
            return text

        existing = (target.content or "")
        if existing.strip() and confirm and not self._confirm(
            "Append generated Graphic Novel draft to current manuscript scene?"
        ):
            return None

        # Single, additive update — never overwrites existing prose.
        new_content = (existing.rstrip() + "\n\n" + text) if existing.strip() else text
        self._db.update_scene_content(target.id, new_content)
        self._notify_scene_changed(target.id)
        return text

    def _build_draft_text(self, scope: str) -> str:
        from logosforge.graphic_novel_manuscript import generate_draft
        issue_id = None
        if scope == "issue":
            page = (
                self._db.get_gn_page_by_id(self._current_page_id)
                if self._current_page_id else None
            )
            issue_id = page.issue_id if page else None
            if issue_id is None:
                return ""
        return generate_draft(
            self._db, self._project_id, scope=scope,
            page_id=self._current_page_id, issue_id=issue_id,
        )

    def _draft_target_scene(self):
        """Append target = the last manuscript scene (end of the script)."""
        scenes = self._db.get_all_scenes(self._project_id)
        return scenes[-1] if scenes else None

    def _confirm(self, message: str) -> bool:
        ans = QMessageBox.question(
            self, "Generate Manuscript Draft", message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        return ans == QMessageBox.StandardButton.Yes

    def _notify_scene_changed(self, scene_id: int) -> None:
        """Manuscript prose changed — refresh project, NOT GN page/panel."""
        try:
            from logosforge.project_events import emit_scene_changed
            emit_scene_changed(scene_id)
        except Exception:
            pass
        if self._on_data_changed:
            self._on_data_changed()

    def _notify_scene_list_changed(self, scene_id: int) -> None:
        try:
            from logosforge.project_events import get_event_bus
            bus = get_event_bus()
            bus.scenes_changed.emit()
            bus.project_data_changed.emit()
        except Exception:
            pass
        if self._on_data_changed:
            self._on_data_changed()

    @staticmethod
    def insert_text_as_single_undo(editor, text: str) -> None:
        """Insert *text* at the editor's cursor as ONE undoable operation.

        Helper for the live-editor insertion path (begin/end edit block).
        The Pages-view action uses the Scene.content path above; this exists
        so insertion into a live QTextEdit/QPlainTextEdit is a single undo
        step where an editor is available.
        """
        cursor = editor.textCursor()
        cursor.beginEditBlock()
        try:
            cursor.insertText(text)
        finally:
            cursor.endEditBlock()

    def _build_page_pane(self) -> QWidget:
        pane = QWidget()
        col = QVBoxLayout(pane)
        col.addWidget(QLabel("Pages"))

        bar = QHBoxLayout()
        self._add_page_btn = QPushButton("+ Page")
        self._add_page_btn.clicked.connect(self.add_page)
        self._page_up_btn = QPushButton("↑")
        self._page_up_btn.setToolTip("Move page earlier")
        self._page_up_btn.clicked.connect(lambda: self.move_page(-1))
        self._page_down_btn = QPushButton("↓")
        self._page_down_btn.setToolTip("Move page later")
        self._page_down_btn.clicked.connect(lambda: self.move_page(1))
        self._del_page_btn = QPushButton("Delete")
        self._del_page_btn.clicked.connect(self.delete_selected_page)
        for w in (self._add_page_btn, self._page_up_btn,
                  self._page_down_btn, self._del_page_btn):
            bar.addWidget(w)
        bar.addStretch()

        # Generate Manuscript Draft — one-way projection: GN structure ->
        # editable manuscript text. Does not alter pages/panels.
        self._gen_draft_btn = QPushButton("Generate Draft")
        self._gen_draft_btn.setToolTip(
            "Insert an editable manuscript scaffold built from the page/panel "
            "structure. Pages and panels are not modified."
        )
        gen_menu = QMenu(self._gen_draft_btn)
        gen_menu.addAction(
            "Selected Page", lambda: self.generate_manuscript_draft("page"),
        )
        gen_menu.addAction(
            "All Pages", lambda: self.generate_manuscript_draft("all"),
        )
        gen_menu.addAction(
            "Current Issue", lambda: self.generate_manuscript_draft("issue"),
        )
        self._gen_draft_btn.setMenu(gen_menu)
        bar.addWidget(self._gen_draft_btn)
        col.addLayout(bar)

        self._page_list = QListWidget()
        self._page_list.currentItemChanged.connect(self._on_page_selected)
        col.addWidget(self._page_list, stretch=1)

        # Page form.
        form = QFormLayout()
        self._page_density = QComboBox()
        self._page_density.addItems(("",) + GN_DENSITY_LEVELS)
        self._page_reveal = QComboBox()
        self._page_reveal.addItems(_REVEAL_TYPES)
        self._page_splash = QCheckBox("Splash page")
        self._page_beat = QLineEdit()
        self._page_summary = QPlainTextEdit()
        self._page_summary.setFixedHeight(56)
        form.addRow("Density", self._page_density)
        form.addRow("Reveal", self._page_reveal)
        form.addRow("", self._page_splash)
        form.addRow("Beat", self._page_beat)
        form.addRow("Summary", self._page_summary)
        col.addLayout(form)

        self._save_page_btn = QPushButton("Save Page")
        self._save_page_btn.clicked.connect(self.save_page_edits)
        col.addWidget(self._save_page_btn)
        return pane

    def _build_panel_pane(self) -> QWidget:
        pane = QWidget()
        col = QVBoxLayout(pane)
        col.addWidget(QLabel("Panels"))

        bar = QHBoxLayout()
        self._add_panel_btn = QPushButton("+ Panel")
        self._add_panel_btn.clicked.connect(self.add_panel)
        self._panel_up_btn = QPushButton("↑")
        self._panel_up_btn.clicked.connect(lambda: self.move_panel(-1))
        self._panel_down_btn = QPushButton("↓")
        self._panel_down_btn.clicked.connect(lambda: self.move_panel(1))
        self._del_panel_btn = QPushButton("Delete")
        self._del_panel_btn.clicked.connect(self.delete_selected_panel)
        for w in (self._add_panel_btn, self._panel_up_btn,
                  self._panel_down_btn, self._del_panel_btn):
            bar.addWidget(w)
        bar.addStretch()

        # AI prompt export (one-way: structured panel/page -> prompt packet).
        self._prompt_btn = QPushButton("Prompt")
        self._prompt_btn.setToolTip(
            "Build an image-generation prompt package from this panel/page "
            "and PSYKE visual memory."
        )
        pmenu = QMenu(self._prompt_btn)
        pmenu.addAction("Copy Panel Prompt", self.copy_panel_prompt)
        pmenu.addAction("Copy Negative Prompt", self.copy_panel_negative_prompt)
        pmenu.addAction("Export Panel Prompt (JSON)",
                        lambda: self.export_panel_prompt("json"))
        pmenu.addAction("Export Panel Prompt (Markdown)",
                        lambda: self.export_panel_prompt("markdown"))
        pmenu.addSeparator()
        pmenu.addAction("Copy All Panel Prompts", self.copy_page_prompts)
        pmenu.addAction("Export Page Prompt Pack (JSON)",
                        lambda: self.export_page_prompts("json"))
        pmenu.addAction("Export Page Prompt Pack (Markdown)",
                        lambda: self.export_page_prompts("markdown"))
        self._prompt_btn.setMenu(pmenu)
        bar.addWidget(self._prompt_btn)
        col.addLayout(bar)

        self._panel_list = QListWidget()
        self._panel_list.currentItemChanged.connect(self._on_panel_selected)
        col.addWidget(self._panel_list, stretch=1)

        form = QFormLayout()
        self._panel_desc = QPlainTextEdit()
        self._panel_desc.setFixedHeight(56)
        self._panel_shot = QComboBox()
        self._panel_shot.addItems(_SHOT_TYPES)
        self._panel_camera = QComboBox()
        self._panel_camera.addItems(_CAMERA_ANGLES)
        self._panel_tone = QLineEdit()
        self._panel_action = QLineEdit()
        self._panel_chars = QLineEdit()
        self._panel_chars.setPlaceholderText("comma,separated")
        self._panel_dialogue = QLineEdit()
        self._panel_dialogue.setPlaceholderText("comma,separated")
        self._panel_motifs = QLineEdit()
        self._panel_motifs.setPlaceholderText("comma,separated")
        self._panel_transition = QComboBox()
        self._panel_transition.addItems(("",) + GN_TRANSITION_TYPES)
        self._panel_priority = QSpinBox()
        self._panel_priority.setRange(0, 99)
        form.addRow("Description", self._panel_desc)
        form.addRow("Shot", self._panel_shot)
        form.addRow("Camera", self._panel_camera)
        form.addRow("Tone", self._panel_tone)
        form.addRow("Action", self._panel_action)
        form.addRow("Characters", self._panel_chars)
        form.addRow("Dialogue", self._panel_dialogue)
        form.addRow("Motifs", self._panel_motifs)
        form.addRow("Transition", self._panel_transition)
        form.addRow("Reading priority", self._panel_priority)
        col.addLayout(form)

        self._save_panel_btn = QPushButton("Save Panel")
        self._save_panel_btn.clicked.connect(self.save_panel_edits)
        col.addWidget(self._save_panel_btn)
        return pane

    # -- Data refresh --------------------------------------------------------

    def refresh(self) -> None:
        if not self._graphic_novel_mode:
            return
        self._reload_pages(select_id=self._current_page_id)

    def _reload_pages(self, select_id: int | None = None) -> None:
        self._loading = True
        self._page_list.clear()
        pages = self._db.get_gn_pages(self._project_id)
        for page in pages:
            label = f"Page {page.page_number}"
            extras = []
            if page.density_level:
                extras.append(page.density_level)
            if page.reveal_type and page.reveal_type != "none":
                extras.append(page.reveal_type)
            if page.splash_page:
                extras.append("splash")
            if extras:
                label += "  ·  " + " · ".join(extras)
            item = QListWidgetItem(label)
            item.setData(_ID_ROLE, page.id)
            self._page_list.addItem(item)
        self._loading = False

        ids = [p.id for p in pages]
        target = select_id if select_id in ids else (ids[0] if ids else None)
        if target is not None:
            self.select_page(target)
        else:
            self._current_page_id = None
            self._clear_page_form()
            self._reload_panels(None)

    def _reload_panels(self, page_id: int | None, select_id: int | None = None) -> None:
        # Canvas mirrors the current page from the same source of truth.
        if self._canvas is not None:
            self._canvas.set_page(page_id)
        self._loading = True
        self._panel_list.clear()
        panels = self._db.get_gn_panels_for_page(page_id) if page_id else []
        for panel in panels:
            preview = (panel.description or panel.action or "").strip()
            if len(preview) > 40:
                preview = preview[:37] + "…"
            label = f"Panel {panel.panel_number}"
            if panel.shot_type:
                label += f"  ·  {panel.shot_type}"
            if preview:
                label += f"  —  {preview}"
            item = QListWidgetItem(label)
            item.setData(_ID_ROLE, panel.id)
            self._panel_list.addItem(item)
        self._loading = False

        ids = [p.id for p in panels]
        target = select_id if select_id in ids else (ids[0] if ids else None)
        if target is not None:
            self.select_panel(target)
        else:
            self._current_panel_id = None
            self._clear_panel_form()
            if self._canvas is not None:
                self._canvas.set_selected_panel(None)

    # -- Selection -----------------------------------------------------------

    def _on_page_selected(self, current, _previous) -> None:
        if self._loading or current is None:
            return
        self.select_page(current.data(_ID_ROLE))

    def select_page(self, page_id: int | None) -> None:
        if not self._graphic_novel_mode or page_id is None:
            return
        self._current_page_id = page_id
        self._sync_list_selection(self._page_list, page_id)
        page = self._db.get_gn_page_by_id(page_id)
        if page is not None:
            self._load_page_form(page)
        self._reload_panels(page_id)

    def _on_panel_selected(self, current, _previous) -> None:
        if self._loading or current is None:
            return
        self.select_panel(current.data(_ID_ROLE))

    def select_panel(self, panel_id: int | None) -> None:
        if not self._graphic_novel_mode or panel_id is None:
            return
        self._current_panel_id = panel_id
        self._sync_list_selection(self._panel_list, panel_id)
        if self._canvas is not None:
            self._canvas.set_selected_panel(panel_id)
        panel = self._db.get_gn_panel_by_id(panel_id)
        if panel is not None:
            self._load_panel_form(panel)

    def _sync_list_selection(self, widget: QListWidget, entity_id: int) -> None:
        self._loading = True
        for i in range(widget.count()):
            if widget.item(i).data(_ID_ROLE) == entity_id:
                widget.setCurrentRow(i)
                break
        self._loading = False

    # -- Page mutations ------------------------------------------------------

    def add_page(self):
        if not self._graphic_novel_mode:
            return None
        page = self._db.create_gn_page(self._project_id)
        self._reload_pages(select_id=page.id)
        self._emit_changed()
        return page.id

    def delete_selected_page(self) -> None:
        if not self._graphic_novel_mode or self._current_page_id is None:
            return
        self._db.delete_gn_page(self._current_page_id)
        self._current_page_id = None
        self._reload_pages()
        self._emit_changed()

    def move_page(self, delta: int) -> None:
        if not self._graphic_novel_mode or self._current_page_id is None:
            return
        ids = [p.id for p in self._db.get_gn_pages(self._project_id)]
        if self._current_page_id not in ids:
            return
        idx = ids.index(self._current_page_id)
        new_idx = idx + delta
        if new_idx < 0 or new_idx >= len(ids):
            return
        ids[idx], ids[new_idx] = ids[new_idx], ids[idx]
        self._db.reorder_gn_pages(self._project_id, ids)
        self._reload_pages(select_id=self._current_page_id)
        self._emit_changed()

    def save_page_edits(self) -> None:
        if not self._graphic_novel_mode or self._current_page_id is None:
            return
        self._db.update_gn_page(
            self._current_page_id,
            density_level=self._page_density.currentText(),
            reveal_type=self._page_reveal.currentText(),
            splash_page=self._page_splash.isChecked(),
            emotional_beat=self._page_beat.text().strip(),
            summary=self._page_summary.toPlainText().strip(),
        )
        self._reload_pages(select_id=self._current_page_id)
        self._emit_changed()

    def _load_page_form(self, page) -> None:
        self._page_density.setCurrentText(page.density_level or "")
        self._page_reveal.setCurrentText(page.reveal_type or "")
        self._page_splash.setChecked(bool(page.splash_page))
        self._page_beat.setText(page.emotional_beat or "")
        self._page_summary.setPlainText(page.summary or "")

    def _clear_page_form(self) -> None:
        self._page_density.setCurrentText("")
        self._page_reveal.setCurrentText("")
        self._page_splash.setChecked(False)
        self._page_beat.clear()
        self._page_summary.clear()

    # -- Panel mutations -----------------------------------------------------

    def add_panel(self):
        if not self._graphic_novel_mode or self._current_page_id is None:
            return None
        panel = self._db.create_gn_panel(self._current_page_id)
        self._reload_panels(self._current_page_id, select_id=panel.id)
        self._emit_changed()
        return panel.id

    def delete_selected_panel(self) -> None:
        if not self._graphic_novel_mode or self._current_panel_id is None:
            return
        self._db.delete_gn_panel(self._current_panel_id)
        self._current_panel_id = None
        self._reload_panels(self._current_page_id)
        self._emit_changed()

    def move_panel(self, delta: int) -> None:
        if (not self._graphic_novel_mode or self._current_page_id is None
                or self._current_panel_id is None):
            return
        ids = [p.id for p in self._db.get_gn_panels_for_page(self._current_page_id)]
        if self._current_panel_id not in ids:
            return
        idx = ids.index(self._current_panel_id)
        new_idx = idx + delta
        if new_idx < 0 or new_idx >= len(ids):
            return
        ids[idx], ids[new_idx] = ids[new_idx], ids[idx]
        self._db.reorder_gn_panels(self._current_page_id, ids)
        self._reload_panels(self._current_page_id, select_id=self._current_panel_id)
        self._emit_changed()

    def save_panel_edits(self) -> None:
        if not self._graphic_novel_mode or self._current_panel_id is None:
            return
        self._db.update_gn_panel(
            self._current_panel_id,
            description=self._panel_desc.toPlainText().strip(),
            shot_type=self._panel_shot.currentText(),
            camera_angle=self._panel_camera.currentText(),
            emotional_tone=self._panel_tone.text().strip(),
            action=self._panel_action.text().strip(),
            characters_present=self._split(self._panel_chars.text()),
            dialogue_refs=self._split(self._panel_dialogue.text()),
            visual_motifs=self._split(self._panel_motifs.text()),
            transition_type=self._panel_transition.currentText(),
            reading_priority=self._panel_priority.value(),
        )
        self._reload_panels(self._current_page_id, select_id=self._current_panel_id)
        self._emit_changed()

    def _load_panel_form(self, panel) -> None:
        self._panel_desc.setPlainText(panel.description or "")
        self._panel_shot.setCurrentText(panel.shot_type or "")
        self._panel_camera.setCurrentText(panel.camera_angle or "")
        self._panel_tone.setText(panel.emotional_tone or "")
        self._panel_action.setText(panel.action or "")
        self._panel_chars.setText(panel.characters_present or "")
        self._panel_dialogue.setText(panel.dialogue_refs or "")
        self._panel_motifs.setText(panel.visual_motifs or "")
        self._panel_transition.setCurrentText(panel.transition_type or "")
        self._panel_priority.setValue(panel.reading_priority or 0)

    def _clear_panel_form(self) -> None:
        self._panel_desc.clear()
        self._panel_shot.setCurrentText("")
        self._panel_camera.setCurrentText("")
        self._panel_tone.clear()
        self._panel_action.clear()
        self._panel_chars.clear()
        self._panel_dialogue.clear()
        self._panel_motifs.clear()
        self._panel_transition.setCurrentText("")
        self._panel_priority.setValue(0)

    # -- Helpers / accessors -------------------------------------------------

    @staticmethod
    def _split(text: str) -> list[str]:
        return [p.strip() for p in (text or "").split(",") if p.strip()]

    def _emit_changed(self) -> None:
        self.data_changed.emit()
        if self._on_data_changed:
            self._on_data_changed()

    def is_graphic_novel_mode(self) -> bool:
        return self._graphic_novel_mode

    def page_ids(self) -> list[int]:
        """Page ids in display (reading) order. [] for non-GN projects."""
        if not self._graphic_novel_mode:
            return []
        return [
            self._page_list.item(i).data(_ID_ROLE)
            for i in range(self._page_list.count())
        ]

    def panel_ids(self) -> list[int]:
        """Panel ids for the selected page, in order. [] for non-GN."""
        if not self._graphic_novel_mode:
            return []
        return [
            self._panel_list.item(i).data(_ID_ROLE)
            for i in range(self._panel_list.count())
        ]

    def current_page_id(self) -> int | None:
        return self._current_page_id

    def current_panel_id(self) -> int | None:
        return self._current_panel_id
