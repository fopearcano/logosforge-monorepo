"""Screenplay Review Dashboard view (Phase 8).

A compact, read-only project overview: summary cards, a per-scene status table,
filters, and row actions (open in Manuscript/Outline/Timeline, copy report, save
as note). It never mutates story data — navigation and report-copy only; the only
write is the explicit, confirmed "Save as Note".

Built from :func:`logosforge.screenplay_review.build_screenplay_review`.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from logosforge import screenplay_review as srv

_COLUMNS = ["#", "Scene", "Plan", "Body", "Health", "Continuity", "Timeline",
            "PSYKE", "Export", "Next Action"]


class _Card(QWidget):
    def __init__(self, title: str) -> None:
        super().__init__()
        self.setObjectName("screenplayReviewCard")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(2)
        self._value = QLabel("0")
        self._value.setObjectName("screenplayReviewCardValue")
        self._value.setStyleSheet("font-size: 18px; font-weight: bold;")
        self._caption = QLabel(title)
        self._caption.setObjectName("screenplayReviewCardCaption")
        self._caption.setStyleSheet("font-size: 10px; color: #888;")
        lay.addWidget(self._value)
        lay.addWidget(self._caption)

    def set_value(self, value) -> None:
        self._value.setText(str(value))


class ScreenplayReviewView(QWidget):
    def __init__(
        self, db, project_id: int, *,
        on_open_manuscript: Callable[[int], None] | None = None,
        on_open_outline: Callable[[int], None] | None = None,
        on_open_timeline: Callable[[int], None] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("screenplayReviewView")
        self._db = db
        self._project_id = project_id
        self._on_open_manuscript = on_open_manuscript
        self._on_open_outline = on_open_outline
        self._on_open_timeline = on_open_timeline
        self._report: srv.ScreenplayReviewReport | None = None
        self._rows_in_view: list[srv.SceneReviewRow] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)

        heading = QLabel("Screenplay Review")
        heading.setObjectName("screenplayReviewHeading")
        heading.setStyleSheet("font-size: 15px; font-weight: bold;")
        layout.addWidget(heading)

        # Summary cards.
        cards_row = QHBoxLayout()
        cards_row.setSpacing(8)
        self._cards: dict[str, _Card] = {}
        for key in ("Total Scenes", "Written", "Planned", "Needs Work",
                    "Export Warnings", "Continuity Risks"):
            card = _Card(key)
            self._cards[key] = card
            cards_row.addWidget(card)
        cards_row.addStretch()
        layout.addLayout(cards_row)

        # Controls row: filter + refresh + copy + (export readiness).
        controls = QHBoxLayout()
        controls.addWidget(QLabel("Filter:"))
        self._filter_combo = QComboBox()
        self._filter_combo.setObjectName("screenplayReviewFilter")
        for f in srv.FILTERS:
            self._filter_combo.addItem(f)
        self._filter_combo.currentIndexChanged.connect(self._apply_filter)
        controls.addWidget(self._filter_combo)
        controls.addStretch()
        self._export_label = QLabel("")
        self._export_label.setObjectName("screenplayReviewExportReady")
        controls.addWidget(self._export_label)
        refresh_btn = QPushButton("Refresh")
        refresh_btn.setObjectName("screenplayReviewRefresh")
        refresh_btn.clicked.connect(self.refresh)
        controls.addWidget(refresh_btn)
        copy_btn = QPushButton("Copy Report")
        copy_btn.setObjectName("screenplayReviewCopy")
        copy_btn.clicked.connect(self.copy_report)
        controls.addWidget(copy_btn)
        note_btn = QPushButton("Save as Note")
        note_btn.setObjectName("screenplayReviewSaveNote")
        note_btn.clicked.connect(self._save_as_note)
        controls.addWidget(note_btn)
        layout.addLayout(controls)

        # Scene table.
        self._table = QTableWidget(0, len(_COLUMNS))
        self._table.setObjectName("screenplayReviewTable")
        self._table.setHorizontalHeaderLabels(_COLUMNS)
        self._table.verticalHeader().setVisible(False)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        try:
            self._table.horizontalHeader().setSectionResizeMode(
                1, QHeaderView.ResizeMode.Stretch)
        except Exception:
            pass
        layout.addWidget(self._table, stretch=1)

        # Row actions.
        actions = QHBoxLayout()
        for label, slot in (("Open in Manuscript", self._open_manuscript),
                            ("Open in Outline", self._open_outline),
                            ("Open in Timeline", self._open_timeline)):
            btn = QPushButton(label)
            btn.clicked.connect(slot)
            actions.addWidget(btn)
        actions.addStretch()
        layout.addLayout(actions)

        self.refresh()

    # -- Data ----------------------------------------------------------------

    def refresh(self) -> None:
        self._report = srv.build_screenplay_review(self._db, self._project_id)
        r = self._report
        self._cards["Total Scenes"].set_value(r.total_scenes)
        self._cards["Written"].set_value(r.written)
        self._cards["Planned"].set_value(r.planned)
        self._cards["Needs Work"].set_value(r.needs_work)
        self._cards["Export Warnings"].set_value(r.with_export_warnings)
        self._cards["Continuity Risks"].set_value(r.with_continuity_warnings)
        self._export_label.setText(
            "Export ready ✓" if r.export_ready else "Not export-ready")
        self._apply_filter()

    def _apply_filter(self) -> None:
        if self._report is None:
            return
        rows = self._report.filtered_rows(self._filter_combo.currentText())
        self._rows_in_view = rows
        self._table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            cells = [row.number or "-", row.title or "Untitled",
                     row.beat_plan_status, row.body_status, row.health_status,
                     row.continuity_status, row.timeline_status, row.psyke_status,
                     row.export_status, row.next_action]
            for c, text in enumerate(cells):
                item = QTableWidgetItem(str(text))
                if c == 0:
                    item.setData(0x0100, row.scene_id)  # Qt.UserRole on the # cell
                self._table.setItem(i, c, item)

    # -- Selection / navigation (read-only) ----------------------------------

    def _selected_scene_id(self) -> int | None:
        rows = self._table.selectionModel().selectedRows() if \
            self._table.selectionModel() else []
        idx = rows[0].row() if rows else self._table.currentRow()
        if idx is None or idx < 0 or idx >= len(self._rows_in_view):
            return None
        return self._rows_in_view[idx].scene_id

    def _open_manuscript(self) -> None:
        sid = self._selected_scene_id()
        if sid is not None and self._on_open_manuscript:
            self._on_open_manuscript(sid)

    def _open_outline(self) -> None:
        sid = self._selected_scene_id()
        if sid is not None and self._on_open_outline:
            self._on_open_outline(sid)

    def _open_timeline(self) -> None:
        sid = self._selected_scene_id()
        if sid is not None and self._on_open_timeline:
            self._on_open_timeline(sid)

    # -- Report copy / save (no story mutation) ------------------------------

    def report_markdown(self) -> str:
        if self._report is None:
            self.refresh()
        return self._report.to_markdown() if self._report else ""

    def copy_report(self) -> None:
        text = self.report_markdown()
        if text:
            QApplication.clipboard().setText(text)

    def _save_as_note(self) -> None:
        if self._report is None:
            return
        ok = QMessageBox.question(
            self, "Save Review as Note",
            "Save this screenplay review as a project Note?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if ok != QMessageBox.StandardButton.Yes:
            return
        try:
            self._db.create_note(self._project_id, "Screenplay Review",
                                 self._report.to_markdown(), tags="review")
            QMessageBox.information(self, "Save as Note", "Saved.")
        except Exception as exc:
            QMessageBox.warning(self, "Save as Note", f"Could not save:\n{exc}")
