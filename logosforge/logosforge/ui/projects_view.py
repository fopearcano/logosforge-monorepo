"""Projects view — browse, open, and create project files."""

import os
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from logosforge import recent_projects
from logosforge.ui import theme

USER_ROLE = Qt.ItemDataRole.UserRole


class ProjectsView(QWidget):
    """Browse recent and local project files."""

    def __init__(
        self,
        on_open_file: Callable[[str], None],
        on_save_as: Callable[[], None],
        on_new_project: Callable[[], None] | None = None,
    ) -> None:
        super().__init__()
        self._on_open_file = on_open_file
        self._on_save_as = on_save_as
        self._on_new_project = on_new_project

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer.addWidget(scroll)

        self._container = QWidget()
        self._layout = QVBoxLayout(self._container)
        self._layout.setContentsMargins(32, 32, 32, 32)
        self._layout.setSpacing(16)
        self._layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        scroll.setWidget(self._container)

        self._build()

    def refresh(self) -> None:
        """Re-read the project list (so create/rename/remove appear without a
        manual section switch). Rebuild reads recent/known projects fresh."""
        self._build()

    def _build(self) -> None:
        self._clear_layout()

        heading = QLabel("Projects")
        heading_font = QFont()
        heading_font.setBold(True)
        heading_font.setPointSize(heading_font.pointSize() + 4)
        heading.setFont(heading_font)
        heading.setStyleSheet(f"color: {theme.TEXT_PRIMARY};")
        self._layout.addWidget(heading)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        new_btn = QPushButton("Create New Project")
        new_btn.setStyleSheet(theme.primary_btn())
        # Create a clean, empty project. (Previously this was wired to
        # Save-As/Export, so it never created a project \u2014 the active project
        # stayed, and "opening" the exported copy duplicated the old data.)
        new_btn.clicked.connect(self._create_new_project)
        btn_row.addWidget(new_btn)

        open_btn = QPushButton("Open Project\u2026")
        open_btn.clicked.connect(self._on_browse)
        btn_row.addWidget(open_btn)

        save_as_btn = QPushButton("Save As")
        save_as_btn.setToolTip("Save the current project to a file")
        save_as_btn.clicked.connect(self._on_save_as)
        btn_row.addWidget(save_as_btn)

        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self._build)
        btn_row.addWidget(refresh_btn)

        btn_row.addStretch()
        self._layout.addLayout(btn_row)

        recent_paths = recent_projects.clean()

        if not recent_paths:
            self._add_empty_state()
            self._layout.addStretch()
            return

        self._add_section("Recent projects", recent_paths)
        self._layout.addStretch()

    def _add_section(self, title: str, paths: list[str]) -> None:
        label = QLabel(title)
        label.setStyleSheet(theme.eyebrow())
        self._layout.addWidget(label)

        for path in paths:
            card = self._make_project_card(path)
            self._layout.addWidget(card)

    def _make_project_card(self, path: str) -> QFrame:
        card = QFrame()
        card.setObjectName("projCard")
        card.setStyleSheet(theme.card_style("projCard"))
        theme.apply_card_shadow(card)

        row = QHBoxLayout(card)
        row.setContentsMargins(16, 16, 16, 16)
        row.setSpacing(16)

        info = QVBoxLayout()
        info.setSpacing(4)

        name = QLabel(Path(path).name)
        name_font = QFont()
        name_font.setBold(True)
        name.setFont(name_font)
        name.setStyleSheet(f"color: {theme.TEXT_PRIMARY};")
        info.addWidget(name)

        short = self._shorten_path(path)
        loc = QLabel(short)
        loc.setStyleSheet(
            f"color: {theme.TEXT_MUTED}; font-size: 11px;"
        )
        loc.setWordWrap(True)
        info.addWidget(loc)

        mtime = self._get_mtime(path)
        if mtime:
            time_label = QLabel(mtime)
            time_label.setStyleSheet(
                f"color: {theme.TEXT_MUTED}; font-size: 11px;"
            )
            info.addWidget(time_label)

        row.addLayout(info, stretch=1)

        open_btn = QPushButton("Open")
        open_btn.setStyleSheet(theme.primary_btn())
        open_btn.clicked.connect(lambda _, p=path: self._on_open_file(p))
        row.addWidget(open_btn)

        remove_btn = QPushButton("Remove")
        remove_btn.setStyleSheet(
            f"color: {theme.TEXT_MUTED}; font-size: 11px;"
            " background: transparent; border: none; padding: 4px 8px;"
        )
        remove_btn.setToolTip("Remove from recent list")
        remove_btn.clicked.connect(lambda _, p=path: self._remove_entry(p))
        row.addWidget(remove_btn)

        return card

    def _remove_entry(self, path: str) -> None:
        recent_projects.remove(path)
        self._build()

    def _add_empty_state(self) -> None:
        card = QFrame()
        card.setObjectName("projCard")
        card.setStyleSheet(theme.card_style("projCard"))
        theme.apply_card_shadow(card)

        inner = QVBoxLayout(card)
        inner.setContentsMargins(24, 24, 24, 24)
        inner.setSpacing(16)

        msg = QLabel("No projects found.")
        msg_font = QFont()
        msg_font.setBold(True)
        msg.setFont(msg_font)
        inner.addWidget(msg)

        body = QLabel(
            "Open an existing project file or create a new one to get started."
        )
        body.setWordWrap(True)
        body.setStyleSheet(f"color: {theme.TEXT_SECONDARY};")
        inner.addWidget(body)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        new_btn = QPushButton("Create New Project")
        new_btn.setStyleSheet(theme.primary_btn())
        new_btn.clicked.connect(self._create_new_project)
        btn_row.addWidget(new_btn)

        open_btn = QPushButton("Open Project\u2026")
        open_btn.clicked.connect(self._on_browse)
        btn_row.addWidget(open_btn)

        btn_row.addStretch()
        inner.addLayout(btn_row)

        self._layout.addWidget(card)

    def _create_new_project(self) -> None:
        # Prefer the real "new blank project" callback; fall back to Save-As
        # only if a host didn't provide one (keeps older callers working).
        if self._on_new_project is not None:
            self._on_new_project()
        else:
            self._on_save_as()

    def _on_browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Project", "", "JSON (*.json)",
        )
        if path:
            self._on_open_file(path)

    @staticmethod
    def _shorten_path(path: str) -> str:
        home = str(Path.home())
        if path.startswith(home):
            return "~" + path[len(home):]
        return path

    @staticmethod
    def _get_mtime(path: str) -> str | None:
        try:
            stat = os.stat(path)
            from datetime import datetime, timezone
            dt = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
            return f"Modified {dt.strftime('%b %d, %Y %H:%M')}"
        except OSError:
            return None

    def _clear_layout(self) -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
            else:
                sub = item.layout()
                if sub is not None:
                    self._drop_layout(sub)

    def _drop_layout(self, layout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
            elif item.layout() is not None:
                self._drop_layout(item.layout())
