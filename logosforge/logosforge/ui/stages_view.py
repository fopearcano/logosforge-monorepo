"""STAGES — central panel for narrative versioning + branching."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QTextOption
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QTextEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from logosforge.db import Database
from logosforge.models import STAGE_SCOPE_TYPES, STAGE_STATUSES
from logosforge.stages import (
    SAFETY_STAGE_NAME,
    branch_from,
    capture_scope,
    diff_payloads,
    load_snapshot,
    restore_snapshot,
    save_snapshot,
)
from logosforge.ui import theme

_USER_SCOPES = ("project", "scene", "chapter", "outline", "psyke")
_USER_STATUSES = ("alternate", "canonical", "archived")

# Human-readable scope choices for the New-Stage picker (what each captures).
_SCOPE_LABELS: dict[str, str] = {
    "project": "Project — everything (scenes, outline, story bible)",
    "scene": "Scene — the scene currently open in the editor",
    "chapter": "Chapter — the current chapter's scenes",
    "outline": "Outline — the outline structure",
    "psyke": "Story bible — characters, places, lore, themes…",
}


def _scope_from_label(label: str) -> str:
    for scope, text in _SCOPE_LABELS.items():
        if text == label:
            return scope
    return "project"


class StagesView(QWidget):
    """Central STAGES panel — tree on the left, details + actions on the right."""

    data_changed = Signal()

    def __init__(
        self,
        db: Database,
        project_id: int,
        on_data_changed: Callable[[], None] | None = None,
        get_active_scene_id: Callable[[], int | None] | None = None,
    ) -> None:
        super().__init__()
        self._db = db
        self._project_id = project_id
        self._on_data_changed = on_data_changed
        self._get_active_scene_id = get_active_scene_id or (lambda: None)
        self._selected_stage_id: int | None = None
        self._selected_snapshot_id: int | None = None
        self._pending_restore_snapshot_id: int | None = None
        self._build_ui()
        self._reload_tree()

    # -- UI ------------------------------------------------------------------

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        title = QLabel("Stages")
        title.setStyleSheet(
            f"color: {theme.get('TEXT_PRIMARY')};"
            f" font-size: 22px; font-weight: 600;"
        )
        layout.addWidget(title)

        subtitle = QLabel(
            "Track narrative versions and alternate directions. "
            "Stages are intentional — autosave still protects loss."
        )
        subtitle.setStyleSheet(
            f"color: {theme.get('TEXT_MUTED')}; font-size: 12px;"
        )
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(splitter, 1)

        splitter.addWidget(self._build_left_panel())
        splitter.addWidget(self._build_right_panel())
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([300, 700])

        self._action_bar = self._build_action_bar()
        layout.addWidget(self._action_bar)

        self.setStyleSheet(
            f"QWidget {{ background-color: {theme.get('BG_PANEL')}; }}"
        )

    def _build_left_panel(self) -> QWidget:
        panel = QWidget()
        col = QVBoxLayout(panel)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(6)

        self._tree = QTreeWidget()
        self._tree.setHeaderLabels(["Stage", "Status"])
        self._tree.setObjectName("stagesTree")
        self._tree.setRootIsDecorated(True)
        self._tree.itemSelectionChanged.connect(self._on_tree_selection)
        col.addWidget(self._tree, 1)

        new_stage_btn = QPushButton("+ New Stage")
        new_stage_btn.setStyleSheet(_button_style(primary=False))
        new_stage_btn.clicked.connect(self._on_new_stage)
        col.addWidget(new_stage_btn)

        return panel

    def _build_right_panel(self) -> QWidget:
        panel = QWidget()
        col = QVBoxLayout(panel)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(8)

        self._detail_label = QLabel("Select a stage to see its details.")
        self._detail_label.setStyleSheet(
            f"color: {theme.get('TEXT_PRIMARY')}; font-size: 16px; font-weight: 600;"
        )
        col.addWidget(self._detail_label)

        self._meta_label = QLabel("")
        self._meta_label.setStyleSheet(
            f"color: {theme.get('TEXT_MUTED')}; font-size: 12px;"
        )
        col.addWidget(self._meta_label)

        status_row = QHBoxLayout()
        status_row.setSpacing(6)
        status_label = QLabel("Status:")
        status_label.setStyleSheet(f"color: {theme.get('TEXT_MUTED')};")
        status_row.addWidget(status_label)

        self._status_combo = QComboBox()
        for s in _USER_STATUSES:
            self._status_combo.addItem(s.capitalize(), s)
        self._status_combo.currentIndexChanged.connect(self._on_status_change)
        status_row.addWidget(self._status_combo)
        status_row.addStretch(1)
        col.addLayout(status_row)

        snap_label = QLabel("Snapshots")
        snap_label.setStyleSheet(
            f"color: {theme.get('TEXT_PRIMARY')};"
            f" font-size: 13px; font-weight: 600; margin-top: 8px;"
        )
        col.addWidget(snap_label)

        self._snapshot_list = QListWidget()
        self._snapshot_list.itemSelectionChanged.connect(self._on_snapshot_selection)
        col.addWidget(self._snapshot_list, 1)

        self._diff_view = QTextEdit()
        self._diff_view.setReadOnly(True)
        self._diff_view.setWordWrapMode(QTextOption.WrapMode.NoWrap)
        self._diff_view.setPlaceholderText(
            "Compare current state vs the selected snapshot — click Compare."
        )
        self._diff_view.setStyleSheet(
            f"QTextEdit {{ font-family: monospace; font-size: 12px;"
            f" color: {theme.get('TEXT_PRIMARY')};"
            f" background-color: {theme.get('BG_INPUT')};"
            f" border: 1px solid {theme.get('BORDER')};"
            f" border-radius: 6px; }}"
        )
        self._diff_view.setMinimumHeight(160)
        col.addWidget(self._diff_view, 1)

        self._restore_status = QLabel("")
        self._restore_status.setStyleSheet(
            f"color: {theme.get('TEXT_MUTED')}; font-size: 11px;"
        )
        col.addWidget(self._restore_status)

        return panel

    def _build_action_bar(self) -> QWidget:
        bar = QFrame()
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self._snapshot_btn = QPushButton("Snapshot current")
        self._snapshot_btn.setStyleSheet(_button_style())
        self._snapshot_btn.clicked.connect(self._on_take_snapshot)

        self._compare_btn = QPushButton("Compare")
        self._compare_btn.setStyleSheet(_button_style(primary=False))
        self._compare_btn.clicked.connect(self._on_compare)

        self._branch_btn = QPushButton("Branch from stage")
        self._branch_btn.setStyleSheet(_button_style(primary=False))
        self._branch_btn.clicked.connect(self._on_branch)

        self._restore_btn = QPushButton("Restore snapshot")
        self._restore_btn.setStyleSheet(_button_style(primary=False))
        self._restore_btn.clicked.connect(self._on_restore)

        self._confirm_btn = QPushButton("Confirm restore")
        self._confirm_btn.setStyleSheet(_button_style(danger=True))
        self._confirm_btn.clicked.connect(self._on_confirm_restore)
        self._confirm_btn.hide()

        layout.addWidget(self._snapshot_btn)
        layout.addWidget(self._compare_btn)
        layout.addWidget(self._branch_btn)
        layout.addStretch(1)
        layout.addWidget(self._restore_btn)
        layout.addWidget(self._confirm_btn)
        return bar

    # -- Data loading --------------------------------------------------------

    def refresh(self) -> None:
        self._reload_tree()

    def _reload_tree(self) -> None:
        # Preserve the current selection across a rebuild. A reload is triggered
        # by every data-changed action (snapshot / branch / status, and the
        # app-wide _on_data_changed → refresh), and clearing the tree would
        # otherwise drop the selection — making the next action say "select a
        # stage first" and hiding the snapshot the user just took.
        keep_id = self._selected_stage_id
        self._tree.blockSignals(True)
        self._tree.clear()
        stages = self._db.get_all_stages(self._project_id)
        roots = [s for s in stages if s.parent_stage_id is None]
        node_by_id: dict[int, QTreeWidgetItem] = {}
        for root in roots:
            self._add_tree_item(self._tree.invisibleRootItem(), root, node_by_id)
        for s in stages:
            if s.parent_stage_id and s.parent_stage_id in node_by_id and s.id not in node_by_id:
                parent_node = node_by_id[s.parent_stage_id]
                self._add_tree_item(parent_node, s, node_by_id)
        self._tree.expandAll()
        self._tree.resizeColumnToContents(0)
        self._tree.blockSignals(False)
        if keep_id is not None and keep_id in node_by_id:
            self._select_stage(keep_id)   # restore selection + re-render detail
        elif self._tree.topLevelItemCount() == 0:
            self._selected_stage_id = None
            self._render_detail(None)     # show the empty-state guidance

    def _add_tree_item(
        self,
        parent_item,
        stage,
        node_by_id: dict,
    ) -> QTreeWidgetItem:
        item = QTreeWidgetItem(parent_item, [stage.name, stage.status])
        item.setData(0, Qt.ItemDataRole.UserRole, stage.id)
        if stage.status == "canonical":
            item.setForeground(0, _color(theme.get("ACCENT")))
        elif stage.status == "archived":
            item.setForeground(0, _color(theme.get("TEXT_MUTED")))
        node_by_id[stage.id] = item
        for child in self._db.get_child_stages(stage.id):
            if child.id not in node_by_id:
                self._add_tree_item(item, child, node_by_id)
        return item

    def _on_tree_selection(self) -> None:
        items = self._tree.selectedItems()
        if not items:
            self._selected_stage_id = None
            self._render_detail(None)
            return
        stage_id = items[0].data(0, Qt.ItemDataRole.UserRole)
        self._selected_stage_id = stage_id
        self._pending_restore_snapshot_id = None
        self._confirm_btn.hide()
        self._render_detail(self._db.get_stage(stage_id))

    def _render_detail(self, stage) -> None:
        if stage is None:
            if self._tree.topLevelItemCount() == 0:
                # First-run guidance — distinguish "no stages exist yet" from
                # "stages exist but none selected".
                self._detail_label.setText("No stages yet")
                self._meta_label.setText(
                    "Click '+ New Stage' to capture a version of your project, "
                    "a scene, the outline, or the story bible — then snapshot, "
                    "compare and restore it later."
                )
            else:
                self._detail_label.setText("Select a stage to see its details.")
                self._meta_label.setText("")
            self._snapshot_list.clear()
            self._diff_view.clear()
            return
        self._detail_label.setText(stage.name)
        scope = f"{stage.scope_type}"
        if stage.scope_id is not None:
            scope += f"#{stage.scope_id}"
        meta = f"{scope} · created {stage.created_at:%Y-%m-%d %H:%M}"
        if stage.description:
            meta += f"\n{stage.description}"
        self._meta_label.setText(meta)

        idx = self._status_combo.findData(stage.status)
        if idx < 0:
            idx = self._status_combo.findData("alternate")
        self._status_combo.blockSignals(True)
        self._status_combo.setCurrentIndex(idx)
        self._status_combo.blockSignals(False)

        self._snapshot_list.clear()
        for snap in self._db.get_stage_snapshots(stage.id):
            label = snap.label or f"Snapshot {snap.id}"
            display = f"{label} — {snap.summary} · {snap.created_at:%Y-%m-%d %H:%M}"
            item = QListWidgetItem(display)
            item.setData(Qt.ItemDataRole.UserRole, snap.id)
            self._snapshot_list.addItem(item)

        self._diff_view.clear()
        self._restore_status.setText("")

    def _on_snapshot_selection(self) -> None:
        items = self._snapshot_list.selectedItems()
        if not items:
            self._selected_snapshot_id = None
            return
        self._selected_snapshot_id = items[0].data(Qt.ItemDataRole.UserRole)
        self._pending_restore_snapshot_id = None
        self._confirm_btn.hide()
        self._restore_status.setText("")

    # -- Actions -------------------------------------------------------------

    def _on_new_stage(self) -> None:
        name, ok = QInputDialog.getText(
            self, "New stage", "Name:", QLineEdit.EchoMode.Normal, "",
        )
        if not ok or not name.strip():
            return
        choice, ok2 = QInputDialog.getItem(
            self, "New stage scope", "What should this stage version?",
            [_SCOPE_LABELS[s] for s in _USER_SCOPES], 0, False,
        )
        if not ok2:
            return
        scope_type = _scope_from_label(choice)
        scope_id = None
        if scope_type == "scene":
            scope_id = self._get_active_scene_id()
        parent_id = self._selected_stage_id
        stage = self._db.create_stage(
            self._project_id,
            name.strip(),
            scope_type=scope_type,
            scope_id=scope_id,
            parent_stage_id=parent_id,
            status="alternate",
        )
        self._reload_tree()
        self._select_stage(stage.id)
        if self._on_data_changed is not None:
            self._on_data_changed()

    def _on_take_snapshot(self) -> None:
        stage_id = self._selected_stage_id
        if stage_id is None:
            self._restore_status.setText("Select a stage first.")
            return
        stage = self._db.get_stage(stage_id)
        if stage is None:
            return
        captured = capture_scope(
            self._db, self._project_id, stage.scope_type, stage.scope_id,
        )
        save_snapshot(
            self._db, stage.id, captured,
            # No time prefix: the list row already shows the snapshot's real
            # created-at timestamp, and the previous "Snap {stage.created_at}"
            # gave every snapshot of a stage the same misleading time. Empty
            # label → the list falls back to a distinct "Snapshot {id}".
            reason="Manual snapshot",
        )
        self._render_detail(stage)
        self._restore_status.setText("Snapshot captured.")
        if self._on_data_changed is not None:
            self._on_data_changed()

    def _on_branch(self) -> None:
        if self._selected_stage_id is None:
            self._restore_status.setText("Select a stage to branch from.")
            return
        name, ok = QInputDialog.getText(
            self, "Branch from stage", "New stage name:",
            QLineEdit.EchoMode.Normal, "",
        )
        if not ok or not name.strip():
            return
        reason, ok2 = QInputDialog.getText(
            self, "Branch from stage", "Branch reason (optional):",
            QLineEdit.EchoMode.Normal, "",
        )
        if not ok2:
            reason = ""
        new_stage = branch_from(
            self._db, self._selected_stage_id,
            name=name.strip(),
            branch_reason=reason.strip(),
        )
        if new_stage is None:
            return
        self._reload_tree()
        self._select_stage(new_stage.id)
        if self._on_data_changed is not None:
            self._on_data_changed()

    def _on_compare(self) -> None:
        if self._selected_snapshot_id is None or self._selected_stage_id is None:
            self._restore_status.setText("Select a snapshot to compare.")
            return
        payload = load_snapshot(self._db, self._selected_snapshot_id)
        if payload is None:
            return
        current = capture_scope(
            self._db, self._project_id, payload.scope_type, payload.scope_id,
        )
        diff = diff_payloads(payload, current)
        text = diff.unified or "(no differences)"
        self._diff_view.setPlainText(text)

    def _on_restore(self) -> None:
        if self._selected_snapshot_id is None:
            self._restore_status.setText("Select a snapshot to restore.")
            return
        self._pending_restore_snapshot_id = self._selected_snapshot_id
        self._confirm_btn.show()
        self._restore_status.setText(
            "Click 'Confirm restore' to overwrite current state. "
            "A safety snapshot will be taken automatically."
        )

    def _on_confirm_restore(self) -> None:
        if self._pending_restore_snapshot_id is None:
            self._confirm_btn.hide()
            return
        result = restore_snapshot(
            self._db, self._project_id, self._pending_restore_snapshot_id,
        )
        self._pending_restore_snapshot_id = None
        self._confirm_btn.hide()
        if result["ok"]:
            self._restore_status.setText(
                f"Restored. Safety snapshot saved (id={result['safety_snapshot_id']})."
            )
            if self._on_data_changed is not None:
                self._on_data_changed()
            self._reload_tree()
        else:
            self._restore_status.setText(f"Restore failed: {result['error']}")

    def _on_status_change(self) -> None:
        if self._selected_stage_id is None:
            return
        new_status = self._status_combo.currentData()
        stage = self._db.get_stage(self._selected_stage_id)
        # Count peers that will be auto-demoted (canonical is 1-per-scope) so we
        # can surface that otherwise-silent side effect.
        demoted = self._canonical_peers(stage) if (
            stage is not None and new_status == "canonical"
        ) else 0
        self._db.set_stage_status(self._selected_stage_id, new_status)
        self._reload_tree()
        self._select_stage(self._selected_stage_id)
        if self._on_data_changed is not None:
            self._on_data_changed()
        # Set the message LAST — the reloads above clear the status line.
        if new_status == "canonical" and demoted > 0:
            self._restore_status.setText(
                f"Set as canonical — demoted {demoted} other canonical "
                f"stage{'' if demoted == 1 else 's'} in this scope to alternate."
            )
        elif new_status == "canonical":
            self._restore_status.setText("Set as canonical for this scope.")
        else:
            self._restore_status.setText(f"Status set to {new_status}.")

    def _canonical_peers(self, stage) -> int:
        """How many other canonical stages share this stage's canonical scope
        (project, or a specific scene) and would be demoted to alternate."""
        if stage is None:
            return 0
        others = self._db.get_all_stages(self._project_id)
        if stage.scope_type == "project":
            return sum(
                1 for o in others
                if o.id != stage.id and o.scope_type == "project"
                and o.status == "canonical"
            )
        if stage.scope_type == "scene" and stage.scope_id is not None:
            return sum(
                1 for o in others
                if o.id != stage.id and o.scope_type == "scene"
                and o.scope_id == stage.scope_id and o.status == "canonical"
            )
        return 0

    # -- Helpers -------------------------------------------------------------

    def _select_stage(self, stage_id: int) -> None:
        for i in range(self._tree.topLevelItemCount()):
            item = self._tree.topLevelItem(i)
            if self._select_in_subtree(item, stage_id):
                return

    def _select_in_subtree(self, item: QTreeWidgetItem, stage_id: int) -> bool:
        if item.data(0, Qt.ItemDataRole.UserRole) == stage_id:
            self._tree.setCurrentItem(item)
            return True
        for i in range(item.childCount()):
            if self._select_in_subtree(item.child(i), stage_id):
                return True
        return False


# ---------------------------------------------------------------------------
# Style helpers
# ---------------------------------------------------------------------------


def _button_style(primary: bool = True, danger: bool = False) -> str:
    if danger:
        bg = "#a83232"
        bg_hover = "#c14040"
        fg = "#ffffff"
    elif primary:
        bg = theme.get("ACCENT")
        bg_hover = theme.get("ACCENT_DIM")
        fg = theme.get("ACCENT_TEXT")
    else:
        bg = "transparent"
        bg_hover = theme.get("BG_HOVER")
        fg = theme.get("TEXT_PRIMARY")
    border = "none" if primary or danger else f"1px solid {theme.get('BORDER')}"
    return (
        f"QPushButton {{ background-color: {bg}; color: {fg};"
        f" border: {border}; padding: 6px 14px; border-radius: 6px; }}"
        f"QPushButton:hover {{ background-color: {bg_hover}; }}"
        f"QPushButton:disabled {{ color: {theme.get('TEXT_MUTED')}; }}"
    )


def _color(hex_str: str):
    from PySide6.QtGui import QColor
    return QColor(hex_str)
