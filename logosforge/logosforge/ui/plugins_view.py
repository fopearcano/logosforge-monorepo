"""Plugins view — list discovered plugins with details and enable/disable."""

import os
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from logosforge.paths import get_docs_path
from logosforge.plugin_manager import PluginManager, get_plugin_manager

USER_ROLE = Qt.ItemDataRole.UserRole

DOCS_PATH = get_docs_path() / "plugins.md"


class PluginsView(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self._pm: PluginManager = get_plugin_manager()

        root = QHBoxLayout(self)

        # -- Left panel: plugin list -----------------------------------------
        left = QVBoxLayout()
        left.addWidget(QLabel("Plugins"))

        self._list = QListWidget()
        self._list.currentItemChanged.connect(self._on_selected)
        left.addWidget(self._list)

        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self._refresh)
        left.addWidget(refresh_btn)

        docs_btn = QPushButton("Plugin Docs")
        docs_btn.clicked.connect(self._open_docs)
        left.addWidget(docs_btn)

        root.addLayout(left)

        # -- Right panel: details (scrollable) -------------------------------
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)

        detail_widget = QWidget()
        right = QVBoxLayout(detail_widget)

        self._name_label = QLabel("Select a plugin")
        self._name_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        right.addWidget(self._name_label)

        self._version_label = QLabel("")
        right.addWidget(self._version_label)

        self._author_label = QLabel("")
        right.addWidget(self._author_label)

        self._desc_label = QLabel("")
        self._desc_label.setWordWrap(True)
        right.addWidget(self._desc_label)

        self._path_label = QLabel("")
        self._path_label.setWordWrap(True)
        self._path_label.setStyleSheet("font-size: 11px; color: #888;")
        right.addWidget(self._path_label)

        self._status_label = QLabel("")
        right.addWidget(self._status_label)

        self._enabled_check = QCheckBox("Enabled")
        self._enabled_check.toggled.connect(self._on_toggle_enabled)
        right.addWidget(self._enabled_check)

        self._restart_hint = QLabel("Changes take effect on next launch.")
        self._restart_hint.setStyleSheet("font-size: 11px; color: #888; font-style: italic;")
        self._restart_hint.setVisible(False)
        right.addWidget(self._restart_hint)

        right.addWidget(QLabel("Logs"))
        self._log_viewer = QPlainTextEdit()
        self._log_viewer.setReadOnly(True)
        self._log_viewer.setMaximumHeight(120)
        self._log_viewer.setPlaceholderText("No log output.")
        right.addWidget(self._log_viewer)

        self._error_label = QLabel("")
        self._error_label.setWordWrap(True)
        self._error_label.setStyleSheet("color: #e74c3c;")
        right.addWidget(self._error_label)

        right.addStretch()
        scroll.setWidget(detail_widget)
        root.addWidget(scroll)

        self._selected_id: str | None = None
        self._refresh_list()

    def _refresh(self) -> None:
        self._pm.discover()
        self._refresh_list()

    def _refresh_list(self) -> None:
        self._list.blockSignals(True)
        self._list.clear()
        for plugin in self._pm.plugins:
            status = ""
            if plugin.error:
                status = " [error]"
            elif plugin.loaded:
                status = " [loaded]"
            elif not plugin.enabled:
                status = " [disabled]"
            item = QListWidgetItem(f"{plugin.name}{status}")
            item.setData(USER_ROLE, plugin.id)
            self._list.addItem(item)
        self._list.blockSignals(False)

        if not self._pm.plugins:
            self._name_label.setText("No plugins found")
            self._clear_details()

    def _on_selected(self, current: QListWidgetItem | None) -> None:
        if current is None:
            return
        plugin_id = current.data(USER_ROLE)
        self._selected_id = plugin_id
        plugin = next((p for p in self._pm.plugins if p.id == plugin_id), None)
        if plugin is None:
            return

        self._name_label.setText(plugin.name)
        self._version_label.setText(f"Version: {plugin.version}")
        self._author_label.setText(f"Author: {plugin.author}")
        self._desc_label.setText(plugin.description)
        self._path_label.setText(f"Path: {plugin.path}")

        if plugin.error:
            self._status_label.setText("Status: Error")
            self._status_label.setStyleSheet("color: #e74c3c;")
            self._error_label.setText(plugin.error)
        elif plugin.loaded:
            self._status_label.setText("Status: Loaded")
            self._status_label.setStyleSheet("color: #2ecc71;")
            self._error_label.setText("")
        elif not plugin.enabled:
            self._status_label.setText("Status: Disabled")
            self._status_label.setStyleSheet("color: #888;")
            self._error_label.setText("")
        else:
            self._status_label.setText("Status: Not loaded")
            self._status_label.setStyleSheet("color: #f39c12;")
            self._error_label.setText("")

        self._enabled_check.blockSignals(True)
        self._enabled_check.setChecked(plugin.enabled)
        self._enabled_check.blockSignals(False)

        self._log_viewer.setPlainText("\n".join(plugin.logs) if plugin.logs else "")

    def _on_toggle_enabled(self, checked: bool) -> None:
        if self._selected_id is None:
            return
        self._pm.set_enabled(self._selected_id, checked)
        self._restart_hint.setVisible(True)
        self._refresh_list()
        if self._selected_id:
            for i in range(self._list.count()):
                if self._list.item(i).data(USER_ROLE) == self._selected_id:
                    self._list.setCurrentRow(i)
                    break

    def _open_docs(self) -> None:
        if DOCS_PATH.is_file():
            content = DOCS_PATH.read_text(encoding="utf-8")
            self._name_label.setText("Plugin Documentation")
            self._version_label.setText("")
            self._author_label.setText("")
            self._desc_label.setText("")
            self._path_label.setText(str(DOCS_PATH))
            self._status_label.setText("")
            self._error_label.setText("")
            self._log_viewer.setPlainText(content)
            self._enabled_check.setVisible(False)
            self._restart_hint.setVisible(False)
        else:
            self._name_label.setText("Documentation not found")
            self._log_viewer.setPlainText(f"Expected at: {DOCS_PATH}")

    def _clear_details(self) -> None:
        self._version_label.setText("")
        self._author_label.setText("")
        self._desc_label.setText("")
        self._path_label.setText("")
        self._status_label.setText("")
        self._error_label.setText("")
        self._log_viewer.clear()
        self._enabled_check.setVisible(True)
        self._restart_hint.setVisible(False)
