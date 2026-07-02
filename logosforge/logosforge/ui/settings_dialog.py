"""Global settings dialog — appearance and AI provider configuration.

Layout contract (small-screen safe): all settings content lives inside a
vertical ``QScrollArea`` and the Close button row is **sticky outside** the
scroll area, so the bottom controls stay reachable no matter how tall the
content grows. The dialog clamps its height to the available screen geometry
(~85%), so it works on small laptops, at high UI scale and in fullscreen.
"""

from __future__ import annotations

from collections.abc import Callable

from pathlib import Path

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtCore import QUrl

import logosforge.connector_actions  # noqa: F401 — registers actions
from logosforge.cloud_storage import detect_cloud_folders
from logosforge.connector_registry import list_actions
from logosforge.settings import get_manager as get_settings
from logosforge.ui import theme
from logosforge.ui.provider_settings import ProviderSettingsWidget


class SettingsDialog(QDialog):
    def __init__(
        self,
        on_theme_changed: Callable[[str], None],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._on_theme_changed = on_theme_changed

        self.setWindowTitle("Preferences")
        self.setMinimumWidth(480)
        self.setMaximumWidth(600)
        self.setMinimumHeight(320)
        # Never grow past the available screen height — on small screens the
        # content scrolls instead, and the bottom buttons stay reachable.
        avail_h = self._available_screen_height()
        if avail_h:
            self.setMaximumHeight(self._max_dialog_height(avail_h))
            self.resize(560, min(640, self.maximumHeight()))

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # -- Scrollable settings content --------------------------------------
        content = QWidget()
        content.setObjectName("prefsContent")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(10)

        # -- Appearance ---------------------------------------------------------
        layout.addWidget(self._section_label("Appearance"))

        theme_row = QHBoxLayout()
        theme_row.setSpacing(6)
        self._theme_btns: dict[str, QPushButton] = {}
        for name, label in (
            ("Dark", "Dark"),
            ("Light (Green)", "Light (Green)"),
            ("Light (Warm)", "Light (Warm)"),
        ):
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setChecked(name == theme.current_palette())
            btn.clicked.connect(lambda _, n=name: self._select_theme(n))
            theme_row.addWidget(btn)
            self._theme_btns[name] = btn
        theme_row.addStretch()
        layout.addLayout(theme_row)

        layout.addWidget(self._separator())

        # -- Language -----------------------------------------------------------
        # Alpha scope: the UI is ENGLISH-ONLY (no UI-language selector;
        # localization is deferred — logosforge.i18n stays dormant). The
        # default WRITING language for new projects is a separate,
        # fully-multilingual concept and remains configurable.
        from logosforge import languages as L
        layout.addWidget(self._section_label("Language"))

        wl_row = QHBoxLayout()
        wl_row.addWidget(QLabel(
            "Default writing language (new projects):"))
        self._default_writing_combo = QComboBox()
        self._default_writing_combo.setObjectName("prefsDefaultWritingLanguage")
        for code, label in L.selector_choices():
            self._default_writing_combo.addItem(label, code)
        idx = self._default_writing_combo.findData(L.default_writing_language())
        self._default_writing_combo.setCurrentIndex(max(idx, 0))
        self._default_writing_combo.currentIndexChanged.connect(
            lambda _i: get_settings().set(
                "default_writing_language",
                self._default_writing_combo.currentData()))
        wl_row.addWidget(self._default_writing_combo, stretch=1)
        layout.addLayout(wl_row)

        ui_lang_note = QLabel(
            "The app interface is English-only in Alpha (interface "
            "localization is deferred). Writing language and Dexter "
            "transcription language are separate and fully multilingual.")
        ui_lang_note.setObjectName("prefsUiLanguageNote")
        ui_lang_note.setWordWrap(True)
        ui_lang_note.setStyleSheet("color: #94a3b8; font-size: 11px;")
        layout.addWidget(ui_lang_note)

        layout.addWidget(self._separator())

        # -- AI Provider --------------------------------------------------------
        layout.addWidget(self._section_label("AI Provider"))

        self._provider_widget = ProviderSettingsWidget(compact=True)
        self._restore_ai_settings()
        layout.addWidget(self._provider_widget)

        layout.addWidget(self._separator())

        # -- Connector ----------------------------------------------------------
        layout.addWidget(self._section_label("Connector"))
        desc = QLabel(
            "Allow the AI to invoke safe actions on this project "
            "(listing scenes, creating notes, etc.)."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color: {theme.TEXT_MUTED}; font-size: 11px;")
        layout.addWidget(desc)

        mgr = get_settings()
        self._conn_enabled = QCheckBox("Enable Connector")
        self._conn_enabled.setChecked(bool(mgr.get("connector_enabled")))
        layout.addWidget(self._conn_enabled)

        self._conn_writes = QCheckBox("Allow write actions (create / update)")
        self._conn_writes.setChecked(bool(mgr.get("connector_allow_writes")))
        layout.addWidget(self._conn_writes)

        self._conn_confirm = QCheckBox("Confirm before running write actions")
        self._conn_confirm.setChecked(bool(mgr.get("connector_confirm_writes")))
        layout.addWidget(self._conn_confirm)

        self._conn_enabled.toggled.connect(self._update_connector_enabled)
        self._update_connector_enabled(self._conn_enabled.isChecked())

        actions_label = QLabel("Available actions (uncheck to disable):")
        actions_label.setStyleSheet(
            f"color: {theme.TEXT_SECONDARY}; font-size: 11px; margin-top: 4px;"
        )
        layout.addWidget(actions_label)

        disabled = set(mgr.get("connector_disabled_actions") or [])
        self._conn_actions_list = QListWidget()
        self._conn_actions_list.setMaximumHeight(140)
        for action in sorted(list_actions(), key=lambda a: (a.category, a.name)):
            item = QListWidgetItem(f"[{action.category}] {action.name} — {action.description}")
            item.setData(Qt.ItemDataRole.UserRole, action.name)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(
                Qt.CheckState.Unchecked if action.name in disabled else Qt.CheckState.Checked
            )
            self._conn_actions_list.addItem(item)
        layout.addWidget(self._conn_actions_list)

        layout.addWidget(self._separator())

        # -- LibreChat ----------------------------------------------------------
        layout.addWidget(self._section_label("LibreChat"))
        lc_desc = QLabel(
            "Optional advanced chat workspace (a separate LibreChat instance). "
            "LibreChat manages its own AI providers — LogosForge only connects to "
            "it. Localhost by default; LogosForge stays fully usable without it."
        )
        lc_desc.setWordWrap(True)
        lc_desc.setStyleSheet(f"color: {theme.TEXT_MUTED}; font-size: 11px;")
        layout.addWidget(lc_desc)

        from logosforge.librechat.config import LibreChatConfig
        lc = LibreChatConfig.load()

        self._lc_enabled = QCheckBox("Enable LibreChat integration")
        self._lc_enabled.setChecked(lc.enabled)
        layout.addWidget(self._lc_enabled)

        lc_url_row = QHBoxLayout()
        lc_url_row.setSpacing(6)
        lc_url_row.addWidget(QLabel("Base URL:"))
        self._lc_url = QLineEdit(lc.base_url)
        self._lc_url.setPlaceholderText("http://localhost:3080")
        lc_url_row.addWidget(self._lc_url, stretch=1)
        layout.addLayout(lc_url_row)

        lc_mode_row = QHBoxLayout()
        lc_mode_row.setSpacing(6)
        lc_mode_row.addWidget(QLabel("Instance:"))
        self._lc_mode = QComboBox()
        self._lc_mode.addItem("Local", "local")
        self._lc_mode.addItem("Remote", "remote")
        mode_idx = self._lc_mode.findData(lc.mode)
        if mode_idx >= 0:
            self._lc_mode.setCurrentIndex(mode_idx)
        lc_mode_row.addWidget(self._lc_mode)
        lc_mode_row.addStretch(1)
        layout.addLayout(lc_mode_row)

        self._lc_auto = QCheckBox("Automatically connect on launch")
        self._lc_auto.setChecked(lc.auto_connect)
        layout.addWidget(self._lc_auto)
        self._lc_embed = QCheckBox("Prefer embedded workspace (in-app webview)")
        self._lc_embed.setChecked(lc.prefer_embedded)
        layout.addWidget(self._lc_embed)
        self._lc_browser = QCheckBox("Open in external browser if embedding is unavailable")
        self._lc_browser.setChecked(lc.browser_fallback)
        layout.addWidget(self._lc_browser)
        self._lc_visible = QCheckBox("Show LibreChat button in the sidebar")
        self._lc_visible.setChecked(lc.button_visible)
        layout.addWidget(self._lc_visible)

        lc_cmd_row = QHBoxLayout()
        lc_cmd_row.setSpacing(6)
        lc_cmd_row.addWidget(QLabel("Startup command:"))
        self._lc_cmd = QLineEdit(lc.startup_command)
        self._lc_cmd.setPlaceholderText(
            "Optional local command to start LibreChat (advanced)"
        )
        lc_cmd_row.addWidget(self._lc_cmd, stretch=1)
        layout.addLayout(lc_cmd_row)

        lc_test_row = QHBoxLayout()
        lc_test_row.addStretch()
        lc_test_btn = QPushButton("Test connection")
        lc_test_btn.clicked.connect(self._on_test_librechat)
        lc_test_row.addWidget(lc_test_btn)
        layout.addLayout(lc_test_row)
        self._lc_test_label = QLabel("")
        self._lc_test_label.setWordWrap(True)
        self._lc_test_label.setStyleSheet(f"color: {theme.TEXT_MUTED}; font-size: 11px;")
        layout.addWidget(self._lc_test_label)

        layout.addWidget(self._separator())

        # -- Project Storage ----------------------------------------------------
        layout.addWidget(self._section_label("Project Storage"))
        storage_desc = QLabel(
            "Pick a default folder for new projects.  Choosing a cloud-synced "
            "folder (Dropbox, Google Drive, iCloud Drive, OneDrive, NAS) lets "
            "you open the project from any device once the file sync completes."
        )
        storage_desc.setWordWrap(True)
        storage_desc.setStyleSheet(f"color: {theme.TEXT_MUTED}; font-size: 11px;")
        layout.addWidget(storage_desc)

        folder_row = QHBoxLayout()
        folder_row.setSpacing(6)
        self._default_folder_input = QLineEdit()
        self._default_folder_input.setText(
            str(mgr.get("default_projects_folder") or "")
        )
        self._default_folder_input.setPlaceholderText(
            "Default projects folder (optional)"
        )
        folder_row.addWidget(self._default_folder_input, stretch=1)

        choose_btn = QPushButton("Choose…")
        choose_btn.clicked.connect(self._on_choose_default_folder)
        folder_row.addWidget(choose_btn)

        open_btn = QPushButton("Open")
        open_btn.clicked.connect(self._on_open_default_folder)
        folder_row.addWidget(open_btn)

        layout.addLayout(folder_row)

        detected = detect_cloud_folders()
        if detected:
            detected_label = QLabel("Detected cloud folders on this machine:")
            detected_label.setStyleSheet(
                f"color: {theme.TEXT_SECONDARY}; font-size: 11px; margin-top: 4px;"
            )
            layout.addWidget(detected_label)
            self._cloud_combo = QComboBox()
            self._cloud_combo.addItem("(pick a detected folder)", "")
            for folder in detected:
                self._cloud_combo.addItem(
                    f"{folder.provider} — {folder.path}", str(folder.path)
                )
            self._cloud_combo.currentIndexChanged.connect(
                self._on_cloud_combo_changed
            )
            layout.addWidget(self._cloud_combo)
        else:
            self._cloud_combo = None  # type: ignore[assignment]

        layout.addStretch()

        scroll = QScrollArea()
        scroll.setObjectName("prefsScrollArea")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(content)
        outer.addWidget(scroll, stretch=1)

        # -- Sticky bottom button row (outside the scroll area) ---------------
        outer.addWidget(self._separator())
        close_row = QHBoxLayout()
        close_row.setContentsMargins(16, 8, 16, 10)
        close_row.addStretch()
        close_btn = QPushButton("Close")
        close_btn.setObjectName("prefsCloseButton")
        close_btn.setDefault(True)
        close_btn.clicked.connect(self.accept)
        close_row.addWidget(close_btn)
        outer.addLayout(close_row)

    # -- screen-aware sizing ---------------------------------------------------
    @staticmethod
    def _max_dialog_height(available_height: int) -> int:
        """Clamp to ~85% of the available screen height (never below the
        dialog's minimum, so tiny/odd geometries still get a usable window)."""
        return max(320, int(available_height * 0.85))

    def _available_screen_height(self) -> int:
        screen = self.screen() or QGuiApplication.primaryScreen()
        if screen is None:
            return 0
        return screen.availableGeometry().height()

    def _restore_ai_settings(self) -> None:
        mgr = get_settings()
        pw = self._provider_widget
        saved_provider = str(mgr.get("ai_provider") or "")

        raw_memory = mgr.get("ai_provider_memory")
        memory = dict(raw_memory) if isinstance(raw_memory, dict) else {}
        if saved_provider:
            entry = dict(memory.get(saved_provider) or {})
            entry.setdefault("model", str(mgr.get("ai_model") or ""))
            entry.setdefault("base_url", str(mgr.get("ai_base_url") or ""))
            entry.setdefault("api_key", str(mgr.get("ai_api_key") or ""))
            memory[saved_provider] = entry
        pw.set_provider_memory(memory)

        idx = pw._provider_combo.findText(saved_provider)
        if idx >= 0:
            pw._provider_combo.setCurrentIndex(idx)
        pw.reload_current_provider()

    def accept(self) -> None:
        config = self._provider_widget.get_provider_config()
        mgr = get_settings()
        mgr.set("ai_provider", config.name)
        mgr.set("ai_model", config.model)
        mgr.set("ai_api_key", self._provider_widget._key_input.text().strip())
        mgr.set("ai_base_url", config.base_url)
        mgr.set("ai_provider_memory", self._provider_widget.provider_memory())

        mgr.set("connector_enabled", self._conn_enabled.isChecked())
        mgr.set("connector_allow_writes", self._conn_writes.isChecked())
        mgr.set("connector_confirm_writes", self._conn_confirm.isChecked())
        disabled: list[str] = []
        for i in range(self._conn_actions_list.count()):
            item = self._conn_actions_list.item(i)
            if item.checkState() != Qt.CheckState.Checked:
                disabled.append(str(item.data(Qt.ItemDataRole.UserRole)))
        mgr.set("connector_disabled_actions", disabled)

        mgr.set(
            "default_projects_folder",
            self._default_folder_input.text().strip(),
        )

        from logosforge.librechat.config import LibreChatConfig
        LibreChatConfig(
            enabled=self._lc_enabled.isChecked(),
            base_url=self._lc_url.text(),
            mode=str(self._lc_mode.currentData() or "local"),
            auto_connect=self._lc_auto.isChecked(),
            prefer_embedded=self._lc_embed.isChecked(),
            browser_fallback=self._lc_browser.isChecked(),
            startup_command=self._lc_cmd.text(),
            button_visible=self._lc_visible.isChecked(),
        ).save()
        super().accept()

    def _on_test_librechat(self) -> None:
        from logosforge.librechat.config import LibreChatConfig
        from logosforge.librechat.service import (
            ConnectionState,
            LibreChatService,
        )

        cfg = LibreChatConfig(
            enabled=True,  # force a probe regardless of the saved enabled flag
            base_url=self._lc_url.text(),
            mode=str(self._lc_mode.currentData() or "local"),
        )
        if not cfg.is_valid_url():
            self._lc_test_label.setText("✗ Invalid base URL.")
            return
        self._lc_test_label.setText("Testing…")
        status = LibreChatService(cfg).check_connection(timeout=2.0)
        ok = status.state is ConnectionState.CONNECTED
        self._lc_test_label.setText(
            ("✓ " if ok else "✗ ") + (status.detail or status.state.value)
        )

    def _on_choose_default_folder(self) -> None:
        start = self._default_folder_input.text().strip() or str(Path.home())
        chosen = QFileDialog.getExistingDirectory(
            self, "Default Projects Folder", start,
        )
        if chosen:
            self._default_folder_input.setText(chosen)

    def _on_open_default_folder(self) -> None:
        path = self._default_folder_input.text().strip()
        if not path:
            return
        if not Path(path).is_dir():
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def _on_cloud_combo_changed(self, index: int) -> None:
        if self._cloud_combo is None:
            return
        data = self._cloud_combo.itemData(index)
        if data:
            self._default_folder_input.setText(str(data))

    def _update_connector_enabled(self, enabled: bool) -> None:
        self._conn_writes.setEnabled(enabled)
        self._conn_confirm.setEnabled(enabled)

    def _select_theme(self, name: str) -> None:
        for key, btn in self._theme_btns.items():
            btn.setChecked(key == name)
        self._on_theme_changed(name)

    @staticmethod
    def _section_label(text: str) -> QLabel:
        label = QLabel(text)
        label.setStyleSheet(
            f"color: {theme.TEXT_PRIMARY}; font-weight: bold; font-size: 13px;"
            f" padding: 0; margin: 0;"
        )
        return label

    @staticmethod
    def _separator() -> QFrame:
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {theme.BORDER};")
        return sep
