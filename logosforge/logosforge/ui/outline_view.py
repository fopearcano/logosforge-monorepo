"""Outline view — editable story structure with template presets."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from logosforge.db import Database
from logosforge.outline_templates import get_template, list_templates
from logosforge.ui import theme

_NODE_ID_ROLE = Qt.ItemDataRole.UserRole


class _OutlineGenWorker(QThread):
    """Runs an outline-generation LLM request off the UI thread."""

    completed = Signal(str)
    failed = Signal(str)

    def __init__(self, messages, provider) -> None:
        super().__init__()
        self._messages = messages
        self._provider = provider

    def run(self) -> None:
        try:
            from logosforge.assistant import chat_completion
            text, _from_cache = chat_completion(
                self._messages, provider=self._provider,
            )
            self.completed.emit(text)
        except Exception as e:  # pragma: no cover - network/provider errors
            self.failed.emit(str(e))


class OutlineView(QWidget):
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
        self._current_node_id: int | None = None
        self._suppress = False
        self._gen_worker: _OutlineGenWorker | None = None
        self._pending_scope: str = "full"
        self._pending_parent_id: int | None = None

        from logosforge.project_compat import get_project_narrative_engine
        self._engine = get_project_narrative_engine(
            db.get_project_by_id(project_id)
        )
        from logosforge.outline_actions import (
            _unit_label,
            engine_structural_units,
        )
        self._units = engine_structural_units(self._engine)
        self._unit_label = _unit_label

        self._save_timer = QTimer()
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(300)
        self._save_timer.timeout.connect(self._flush_description)

        self._build_ui()
        self._load_outline()

    # -- Layout ----------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # -- Toolbar -----------------------------------------------------------
        toolbar = QWidget()
        toolbar.setObjectName("outlineToolbar")
        tb = QHBoxLayout(toolbar)
        tb.setContentsMargins(12, 8, 12, 8)
        tb.setSpacing(8)

        tb.addWidget(QLabel("Template:"))
        self._template_combo = QComboBox()
        self._template_combo.addItem("Choose a template…", userData="")
        for key, name, desc in list_templates():
            self._template_combo.addItem(name, userData=key)
            self._template_combo.setItemData(
                self._template_combo.count() - 1, desc, Qt.ItemDataRole.ToolTipRole,
            )
        tb.addWidget(self._template_combo)

        apply_btn = QPushButton("Apply")
        apply_btn.setToolTip("Replace outline with the selected template")
        apply_btn.clicked.connect(self._apply_template)
        tb.addWidget(apply_btn)

        tb.addSpacing(16)

        # -- AI generation -----------------------------------------------------
        self._ai_outline_btn = QPushButton("✨ AI Generate Outline")
        self._ai_outline_btn.setToolTip(
            "Generate a full story outline with AI "
            "(uses the project's narrative engine, selected template, and "
            "PSYKE). You confirm before anything is written."
        )
        self._ai_outline_btn.clicked.connect(lambda: self._ai_generate("full"))
        tb.addWidget(self._ai_outline_btn)

        # Contextual generate — relabels to Act/Chapter/Scene by selection.
        self._ai_node_btn = QPushButton("✨ AI Generate")
        self._ai_node_btn.setToolTip(
            "Generate structure under the selected outline node with AI."
        )
        self._ai_node_btn.clicked.connect(self._ai_generate_node)
        self._ai_node_btn.setEnabled(False)
        tb.addWidget(self._ai_node_btn)

        self._ai_status = QLabel("")
        self._ai_status.setStyleSheet(
            f"color: {theme.TEXT_SECONDARY}; font-style: italic;"
        )
        tb.addWidget(self._ai_status)

        tb.addSpacing(16)

        # Labels adapt to the project's narrative engine (units[0] is the
        # top structural unit: Part / Act / Issue / Season; the deepest is the
        # leaf: Scene / Beat / Panel).
        top_unit = self._unit_label(self._units[0]) if self._units else "Section"
        leaf_unit = self._unit_label(self._units[-1]) if self._units else "Beat"
        add_section_btn = QPushButton(f"+ {top_unit}")
        add_section_btn.setToolTip(f"Add a top-level {top_unit.lower()}")
        add_section_btn.clicked.connect(self._add_section)
        tb.addWidget(add_section_btn)

        add_beat_btn = QPushButton(f"+ {leaf_unit}")
        add_beat_btn.setToolTip(
            f"Add a {leaf_unit.lower()} under the selected node"
        )
        add_beat_btn.clicked.connect(self._add_beat)
        tb.addWidget(add_beat_btn)

        delete_btn = QPushButton("Delete")
        delete_btn.clicked.connect(self._delete_node)
        tb.addWidget(delete_btn)

        tb.addSpacing(8)

        up_btn = QPushButton("▲")
        up_btn.setFixedWidth(28)
        up_btn.setToolTip("Move up")
        up_btn.clicked.connect(self._move_up)
        tb.addWidget(up_btn)

        down_btn = QPushButton("▼")
        down_btn.setFixedWidth(28)
        down_btn.setToolTip("Move down")
        down_btn.clicked.connect(self._move_down)
        tb.addWidget(down_btn)

        tb.addStretch()

        export_btn = QPushButton("Export")
        export_btn.clicked.connect(self._export_outline)
        tb.addWidget(export_btn)

        root.addWidget(toolbar)

        # -- Splitter: tree + editor -------------------------------------------
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left: tree
        self._tree = QTreeWidget()
        self._tree.setHeaderHidden(True)
        self._tree.setIndentation(20)
        self._tree.setMinimumWidth(200)
        self._tree.currentItemChanged.connect(self._on_item_selected)
        self._tree.setStyleSheet(
            f"QTreeWidget {{ border: none; background: {theme.BG_DARK}; }}"
            f"QTreeWidget::item {{ padding: 4px 6px; }}"
            f"QTreeWidget::item:selected {{"
            f"  background: {theme.ACCENT}; color: #ffffff;"
            f"}}"
        )
        splitter.addWidget(self._tree)

        # Right: editor
        editor = QWidget()
        editor.setMinimumWidth(300)
        ed = QVBoxLayout(editor)
        ed.setContentsMargins(16, 16, 16, 16)
        ed.setSpacing(10)

        self._editor_label = QLabel("Select or create a section to begin")
        label_font = QFont()
        label_font.setBold(True)
        self._editor_label.setFont(label_font)
        self._editor_label.setStyleSheet(f"color: {theme.TEXT_SECONDARY};")
        ed.addWidget(self._editor_label)

        title_label = QLabel("Title")
        title_label.setStyleSheet(f"color: {theme.TEXT_SECONDARY}; font-size: 11px;")
        ed.addWidget(title_label)

        self._title_input = QLineEdit()
        self._title_input.setPlaceholderText("Beat title")
        self._title_input.textChanged.connect(self._on_title_changed)
        ed.addWidget(self._title_input)

        desc_label = QLabel("Description")
        desc_label.setStyleSheet(f"color: {theme.TEXT_SECONDARY}; font-size: 11px;")
        ed.addWidget(desc_label)

        self._desc_input = QPlainTextEdit()
        self._desc_input.setPlaceholderText(
            "Write your outline notes, scene ideas, or structure plan…"
        )
        self._desc_input.textChanged.connect(self._on_desc_changed)
        self._desc_input.setStyleSheet(
            f"QPlainTextEdit {{"
            f"  background-color: {theme.BG_PANEL};"
            f"  color: {theme.TEXT_PRIMARY};"
            f"  border: 1px solid {theme.BORDER};"
            f"  border-radius: 4px; padding: 8px;"
            f"}}"
        )
        ed.addWidget(self._desc_input, stretch=1)

        splitter.addWidget(editor)
        splitter.setSizes([280, 520])
        root.addWidget(splitter, stretch=1)

        self._set_editor_enabled(False)

    # -- Tree operations -------------------------------------------------------

    def refresh(self) -> None:
        self._load_outline()

    def _load_outline(self) -> None:
        self._tree.clear()
        nodes = self._db.get_outline_nodes(self._project_id)

        children_map: dict[int | None, list] = {}
        for node in nodes:
            children_map.setdefault(node.parent_id, []).append(node)

        self._populate_tree(None, children_map, None)
        self._tree.expandAll()

        if self._tree.topLevelItemCount() == 0:
            self._current_node_id = None
            self._set_editor_enabled(False)

    def _populate_tree(
        self,
        parent_id: int | None,
        children_map: dict[int | None, list],
        parent_item: QTreeWidgetItem | None,
    ) -> None:
        children = children_map.get(parent_id, [])
        children.sort(key=lambda n: (n.sort_order, n.id))

        for node in children:
            item = QTreeWidgetItem()
            item.setText(0, node.title)
            item.setData(0, _NODE_ID_ROLE, node.id)

            if parent_id is None:
                font = item.font(0)
                font.setBold(True)
                item.setFont(0, font)

            if parent_item is None:
                self._tree.addTopLevelItem(item)
            else:
                parent_item.addChild(item)

            self._populate_tree(node.id, children_map, item)

    def _find_tree_item(self, node_id: int) -> QTreeWidgetItem | None:
        def _search(parent_item: QTreeWidgetItem | None) -> QTreeWidgetItem | None:
            count = (
                parent_item.childCount()
                if parent_item
                else self._tree.topLevelItemCount()
            )
            for i in range(count):
                child = (
                    parent_item.child(i)
                    if parent_item
                    else self._tree.topLevelItem(i)
                )
                if child.data(0, _NODE_ID_ROLE) == node_id:
                    return child
                found = _search(child)
                if found:
                    return found
            return None

        return _search(None)

    def _select_node(self, node_id: int) -> None:
        item = self._find_tree_item(node_id)
        if item:
            self._tree.setCurrentItem(item)

    # -- Editor ----------------------------------------------------------------

    def _set_editor_enabled(self, enabled: bool) -> None:
        self._title_input.setEnabled(enabled)
        self._desc_input.setEnabled(enabled)
        if not enabled:
            self._suppress = True
            self._title_input.clear()
            self._desc_input.clear()
            self._editor_label.setText("Select or create a section to begin")
            self._suppress = False

    def _on_item_selected(
        self, current: QTreeWidgetItem | None, _prev: QTreeWidgetItem | None,
    ) -> None:
        if current is None:
            self._current_node_id = None
            self._set_editor_enabled(False)
            self._update_ai_node_button(None)
            return

        node_id = current.data(0, _NODE_ID_ROLE)
        self._current_node_id = node_id
        node = self._db.get_outline_node_by_id(node_id)
        if node is None:
            self._set_editor_enabled(False)
            self._update_ai_node_button(None)
            return

        self._suppress = True
        self._set_editor_enabled(True)
        self._title_input.setText(node.title)
        self._desc_input.setPlainText(node.description)
        self._editor_label.setText(self._unit_for_depth(self._node_depth(current)))
        self._suppress = False
        self._update_ai_node_button(current)

    def _node_depth(self, item: QTreeWidgetItem) -> int:
        depth = 0
        p = item.parent()
        while p is not None:
            depth += 1
            p = p.parent()
        return depth

    def _unit_for_depth(self, depth: int) -> str:
        """The engine's structural-unit label for a tree depth."""
        if not self._units:
            return "Section" if depth == 0 else "Beat"
        idx = min(depth, len(self._units) - 1)
        return self._unit_label(self._units[idx])

    def _update_ai_node_button(self, item: QTreeWidgetItem | None) -> None:
        """Relabel the contextual AI button to match the selection's level."""
        if not hasattr(self, "_ai_node_btn"):
            return
        if item is None:
            self._ai_node_btn.setEnabled(False)
            self._ai_node_btn.setText("✨ AI Generate")
            return
        depth = self._node_depth(item)
        unit = self._unit_for_depth(depth)
        self._ai_node_btn.setText(f"✨ AI Generate {unit}")
        self._ai_node_btn.setToolTip(
            f"Generate {unit.lower()}-level structure under the selected node."
        )
        self._ai_node_btn.setEnabled(True)

    def _on_title_changed(self, text: str) -> None:
        if self._suppress or self._current_node_id is None:
            return
        self._db.update_outline_node(self._current_node_id, title=text)
        current = self._tree.currentItem()
        if current:
            current.setText(0, text)
        self._notify()

    def _on_desc_changed(self) -> None:
        if self._suppress or self._current_node_id is None:
            return
        self._save_timer.start()

    def _flush_description(self) -> None:
        if self._current_node_id is None:
            return
        self._db.update_outline_node(
            self._current_node_id,
            description=self._desc_input.toPlainText(),
        )
        self._notify()

    # -- Add / delete ----------------------------------------------------------

    def _add_section(self) -> None:
        siblings = self._db.get_outline_children(self._project_id, None)
        node = self._db.create_outline_node(
            self._project_id, "New Section",
            parent_id=None, sort_order=len(siblings),
        )
        self._load_outline()
        self._select_node(node.id)
        self._title_input.selectAll()
        self._title_input.setFocus()
        self._notify()

    def _add_beat(self) -> None:
        current = self._tree.currentItem()
        if current is None:
            self._add_section()
            return

        section_item = current
        while section_item.parent() is not None:
            section_item = section_item.parent()
        parent_id = section_item.data(0, _NODE_ID_ROLE)

        siblings = self._db.get_outline_children(self._project_id, parent_id)
        node = self._db.create_outline_node(
            self._project_id, "New Beat",
            parent_id=parent_id, sort_order=len(siblings),
        )
        self._load_outline()
        self._select_node(node.id)
        self._title_input.selectAll()
        self._title_input.setFocus()
        self._notify()

    def _delete_node(self) -> None:
        current = self._tree.currentItem()
        if current is None:
            return
        node_id = current.data(0, _NODE_ID_ROLE)
        has_children = current.childCount() > 0
        msg = (
            "Delete this section and all its beats?"
            if has_children
            else "Delete this item?"
        )
        answer = QMessageBox.question(
            self, "Delete", msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        self._db.delete_outline_node(node_id)
        self._current_node_id = None
        self._load_outline()
        self._set_editor_enabled(False)
        self._notify()

    # -- Reorder ---------------------------------------------------------------

    def _move_up(self) -> None:
        self._swap_sibling(-1)

    def _move_down(self) -> None:
        self._swap_sibling(1)

    def _swap_sibling(self, direction: int) -> None:
        current = self._tree.currentItem()
        if current is None:
            return
        node_id = current.data(0, _NODE_ID_ROLE)
        node = self._db.get_outline_node_by_id(node_id)
        if node is None:
            return

        siblings = self._db.get_outline_children(self._project_id, node.parent_id)
        siblings.sort(key=lambda n: (n.sort_order, n.id))
        idx = next((i for i, n in enumerate(siblings) if n.id == node_id), -1)
        target = idx + direction
        if idx < 0 or target < 0 or target >= len(siblings):
            return

        other = siblings[target]
        self._db.update_outline_node(node_id, sort_order=other.sort_order)
        self._db.update_outline_node(other.id, sort_order=node.sort_order)
        if node.sort_order == other.sort_order:
            self._db.update_outline_node(node_id, sort_order=target)
            self._db.update_outline_node(other.id, sort_order=idx)
        self._load_outline()
        self._select_node(node_id)
        self._notify()

    # -- Templates -------------------------------------------------------------

    def _apply_template(self) -> None:
        key = self._template_combo.currentData()
        if not key:
            return
        template = get_template(key)
        if not template:
            return

        existing = self._db.get_outline_nodes(self._project_id)
        if existing:
            answer = QMessageBox.question(
                self,
                "Apply Template",
                f"Apply “{template.name}” template?\n\n"
                "This will replace the current outline structure.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return

        self._db.delete_all_outline_nodes(self._project_id)

        def create_beats(beats, parent_id: int | None) -> None:
            for i, beat in enumerate(beats):
                node = self._db.create_outline_node(
                    self._project_id, beat.title, beat.description,
                    parent_id=parent_id, sort_order=i,
                )
                if beat.children:
                    create_beats(beat.children, node.id)

        create_beats(template.beats, None)

        self._load_outline()
        self._template_combo.setCurrentIndex(0)
        self._notify()

    # -- Export ----------------------------------------------------------------

    def _export_outline(self) -> None:
        nodes = self._db.get_outline_nodes(self._project_id)
        if not nodes:
            QMessageBox.information(self, "Export", "No outline to export.")
            return

        path, selected = QFileDialog.getSaveFileName(
            self, "Export Outline", "",
            "Markdown (*.md);;Text (*.txt)",
        )
        if not path:
            return

        is_md = "Markdown" in selected or path.endswith(".md")
        if not path.endswith((".md", ".txt")):
            path += ".md" if is_md else ".txt"

        children_map: dict[int | None, list] = {}
        for node in nodes:
            children_map.setdefault(node.parent_id, []).append(node)

        project = self._db.get_project_by_id(self._project_id)
        title = project.title if project else "Untitled"

        lines: list[str] = []
        if is_md:
            lines.append(f"# {title} — Story Outline")
        else:
            header = f"{title} — Story Outline"
            lines.append(header)
            lines.append("=" * len(header))
        lines.append("")

        def write_nodes(parent_id: int | None, depth: int) -> None:
            children = children_map.get(parent_id, [])
            children.sort(key=lambda n: (n.sort_order, n.id))
            for node in children:
                if is_md:
                    prefix = "#" * (depth + 2)
                    lines.append(f"{prefix} {node.title}")
                else:
                    indent = "  " * depth
                    lines.append(f"{indent}{node.title}")
                if node.description:
                    lines.append("")
                    if is_md:
                        lines.append(node.description)
                    else:
                        pad = "  " * (depth + 1)
                        for line in node.description.split("\n"):
                            lines.append(f"{pad}{line}")
                lines.append("")
                write_nodes(node.id, depth + 1)

        write_nodes(None, 0)

        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        QMessageBox.information(self, "Export", f"Outline exported to {path}")

    # -- Helpers ---------------------------------------------------------------

    # -- AI generation ---------------------------------------------------------

    def _build_provider(self):
        # Thin delegate to the single shared provider builder (Phase 8B).
        from logosforge.providers import build_active_provider
        return build_active_provider(require_configured=True)

    def build_generation_prompt(self, scope: str, parent_id: int | None) -> str:
        """Compose the outline-generation prompt (engine + template + PSYKE)."""
        from logosforge.outline_actions import build_outline_generation_prompt
        # Selected template, if any.
        template_name, beats = "", []
        key = self._template_combo.currentData() if hasattr(self, "_template_combo") else ""
        tmpl = get_template(key) if key else None
        if tmpl is not None:
            template_name = tmpl.name
            beats = [b.title for b in tmpl.beats]
        # PSYKE context.
        try:
            from logosforge.context_builder import gather_psyke_context
            psyke = gather_psyke_context(self._db, self._project_id)
        except Exception:
            psyke = ""
        target_title = ""
        if parent_id is not None:
            node = self._db.get_outline_node_by_id(parent_id)
            target_title = node.title if node else ""
        return build_outline_generation_prompt(
            scope, engine=self._engine, template_name=template_name,
            template_beats=beats, psyke_context=psyke,
            target_title=target_title,
        )

    def _ai_generate_node(self) -> None:
        current = self._tree.currentItem()
        if current is None:
            return
        depth = self._node_depth(current)
        scope = "act" if depth == 0 else "chapter" if depth == 1 else "scene"
        self._ai_generate(scope, parent_id=current.data(0, _NODE_ID_ROLE))

    def _ai_generate(self, scope: str = "full", parent_id: int | None = None) -> bool:
        """Kick off an AI outline generation for *scope*. Returns False if busy
        or no provider is configured."""
        if self._gen_worker is not None:
            return False
        provider = self._build_provider()
        if provider is None:
            QMessageBox.information(
                self, "AI Generate Outline",
                "No AI provider is configured. Set one in Settings first.",
            )
            return False
        self._pending_scope = scope
        self._pending_parent_id = parent_id
        prompt = self.build_generation_prompt(scope, parent_id)
        messages = [
            {"role": "system",
             "content": "You are a story-structure assistant. Produce a "
                        "clean, structured outline only — no prose."},
            {"role": "user", "content": prompt},
        ]
        self._set_ai_busy(True)
        self._gen_worker = _OutlineGenWorker(messages, provider)
        self._gen_worker.completed.connect(self._on_generation_done)
        self._gen_worker.failed.connect(self._on_generation_failed)
        self._gen_worker.start()
        return True

    def _set_ai_busy(self, busy: bool) -> None:
        self._ai_status.setText("Generating…" if busy else "")
        if hasattr(self, "_ai_outline_btn"):
            self._ai_outline_btn.setEnabled(not busy)
            self._ai_node_btn.setEnabled(not busy and self._current_node_id is not None)

    def _on_generation_failed(self, error: str) -> None:
        self._gen_worker = None
        self._set_ai_busy(False)
        QMessageBox.warning(self, "AI Generate Outline",
                            f"Generation failed:\n\n{error}")

    def _on_generation_done(self, text: str) -> None:
        self._gen_worker = None
        self._set_ai_busy(False)
        self.apply_generated_outline(text, self._pending_scope,
                                     self._pending_parent_id)

    def apply_generated_outline(
        self, text: str, scope: str = "full", parent_id: int | None = None,
        *, confirm: bool = True,
    ) -> list[int]:
        """Parse generated outline text, confirm, then apply additively.

        For full-outline scope the nodes are added at the top level; for
        act/chapter/scene scope they are nested under *parent_id*.
        """
        from logosforge.outline_actions import (
            apply_outline_ops,
            count_ops,
            format_outline_preview,
            parse_outline_response,
            repair_outline_ops,
            validate_outline_ops,
        )
        ops = parse_outline_response(text or "")
        if not ops:
            QMessageBox.information(
                self, "AI Generate Outline",
                "The AI response did not contain a usable outline structure.",
            )
            return []
        # Fill empty descriptions / trim prose, then reject unusable output so
        # we never create empty placeholder nodes or apply prose as structure.
        ops, gen_warnings = repair_outline_ops(ops)
        ok, errors = validate_outline_ops(ops)
        if not ok:
            QMessageBox.warning(
                self, "AI Generate Outline",
                "The generated outline can't be applied safely:\n\n• "
                + "\n• ".join(errors),
            )
            return []
        if confirm:
            preview = format_outline_preview(ops)
            warn_txt = ("\n\n⚠ " + "\n⚠ ".join(gen_warnings)) if gen_warnings else ""
            answer = QMessageBox.question(
                self, "Apply generated outline",
                f"Add {count_ops(ops)} outline node(s)?\n\n"
                "Existing nodes are kept; the new structure is appended."
                + warn_txt + "\n\n" + preview,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return []
        created = apply_outline_ops(self._db, self._project_id, ops, parent_id)
        if created:
            self._load_outline()
            from logosforge.project_events import get_event_bus
            bus = get_event_bus()
            bus.outline_changed.emit()
            bus.project_data_changed.emit()
            self._notify()
        return created

    def _notify(self) -> None:
        if self._on_data_changed:
            self._on_data_changed()
