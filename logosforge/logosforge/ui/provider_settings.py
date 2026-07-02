"""Reusable provider settings widget for the writing assistant views."""

import os

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from logosforge.assistant import test_connection
from logosforge.providers import (
    PROVIDER_CAPABILITIES,
    PROVIDER_NAMES,
    ProviderConfig,
    default_config,
    resolve_api_key,
    validate_provider,
)
from logosforge.ui import theme


class _TestWorker(QThread):
    finished = Signal(bool, str)

    def __init__(self, provider: ProviderConfig) -> None:
        super().__init__()
        self._provider = provider

    def run(self) -> None:
        ok, msg = test_connection(self._provider)
        self.finished.emit(ok, msg)


class ProviderSettingsWidget(QWidget):
    # Emitted whenever the user changes any provider setting (provider,
    # model, base URL, API key). Hosts connect this to persist settings
    # immediately rather than waiting for a dialog accept / app close.
    settings_changed = Signal()

    def __init__(self, compact: bool = False) -> None:
        super().__init__()
        self._test_worker: _TestWorker | None = None
        # Per-provider memory of the last-used base URL / model / API key so
        # switching away and back restores that provider's values instead of
        # resetting to defaults. Hosts can seed/read it to persist across runs.
        self._provider_memory: dict[str, dict[str, str]] = {}
        self._current_provider: str | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        if compact:
            self._build_compact(layout)
        else:
            self._build_wide(layout)

        self._on_provider_changed(self._provider_combo.currentText())
        self._wire_change_signals()

    def _build_compact(self, layout: QVBoxLayout) -> None:
        layout.setSpacing(4)

        self._provider_combo = QComboBox()
        for name in PROVIDER_NAMES:
            self._provider_combo.addItem(name)
        self._provider_combo.currentTextChanged.connect(
            self._on_provider_changed
        )
        layout.addWidget(self._provider_combo)

        self._model_combo = QComboBox()
        self._model_combo.setEditable(True)
        self._model_combo.setMaxVisibleItems(15)
        self._tame_model_combo()
        layout.addWidget(self._model_combo)

        self._url_input = QLineEdit()
        self._url_input.setPlaceholderText("Base URL")
        layout.addWidget(self._url_input)

        # NOTE: this label MUST be added to the layout — a parentless QLabel
        # that gets setVisible(True) on a key-requiring provider would render
        # as a stray empty top-level window.
        self._key_label = QLabel("API key")
        self._key_label.setStyleSheet(
            f"color: {theme.TEXT_SECONDARY}; font-size: 11px;"
        )
        self._key_label.setVisible(False)
        layout.addWidget(self._key_label)
        self._key_input = QLineEdit()
        self._key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._key_input.setPlaceholderText("API key")
        layout.addWidget(self._key_input)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(4)
        self._defaults_btn = QPushButton("Defaults")
        self._defaults_btn.clicked.connect(self._load_defaults)
        btn_row.addWidget(self._defaults_btn)
        self._test_btn = QPushButton("Test")
        self._test_btn.clicked.connect(self._on_test)
        btn_row.addWidget(self._test_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        self._status_label = QLabel("")
        self._status_label.setStyleSheet("font-size: 11px;")
        self._status_label.setWordWrap(True)
        layout.addWidget(self._status_label)

    def _build_wide(self, layout: QVBoxLayout) -> None:
        # Row 1: provider + model + defaults
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Provider:"))
        self._provider_combo = QComboBox()
        for name in PROVIDER_NAMES:
            self._provider_combo.addItem(name)
        self._provider_combo.currentTextChanged.connect(
            self._on_provider_changed
        )
        row1.addWidget(self._provider_combo)

        row1.addWidget(QLabel("Model:"))
        self._model_combo = QComboBox()
        self._model_combo.setEditable(True)
        self._model_combo.setMaximumWidth(260)
        self._model_combo.setMaxVisibleItems(15)
        self._tame_model_combo()
        row1.addWidget(self._model_combo)

        self._defaults_btn = QPushButton("Defaults")
        self._defaults_btn.setMaximumWidth(70)
        self._defaults_btn.clicked.connect(self._load_defaults)
        row1.addWidget(self._defaults_btn)
        row1.addStretch()
        layout.addLayout(row1)

        # Row 2: URL + API key + test
        row2 = QHBoxLayout()
        row2.addWidget(QLabel("URL:"))
        self._url_input = QLineEdit()
        self._url_input.setMaximumWidth(300)
        row2.addWidget(self._url_input)

        self._key_label = QLabel("Key:")
        row2.addWidget(self._key_label)
        self._key_input = QLineEdit()
        self._key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._key_input.setMaximumWidth(200)
        self._key_input.setPlaceholderText("not required")
        row2.addWidget(self._key_input)

        self._test_btn = QPushButton("Test")
        self._test_btn.setMaximumWidth(60)
        self._test_btn.clicked.connect(self._on_test)
        row2.addWidget(self._test_btn)

        self._status_label = QLabel("")
        self._status_label.setStyleSheet("font-size: 11px;")
        row2.addWidget(self._status_label)
        row2.addStretch()
        layout.addLayout(row2)

    def _tame_model_combo(self) -> None:
        """Stop the editable model combo from flashing a completer popup.

        The model combo is editable so users can type a custom model
        name. By default an editable QComboBox installs a QCompleter whose
        popup is a top-level window; when we rebuild the item list on a
        provider switch (clear() + addItem() + setCurrentText()), that
        popup briefly renders as a tiny floating window. Removing the
        completer and disabling auto-insert keeps switching glitch-free
        without losing the ability to type a model name.
        """
        self._model_combo.setCompleter(None)
        self._model_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)

    def _wire_change_signals(self) -> None:
        """Emit settings_changed on any user edit so hosts can persist."""
        self._model_combo.currentTextChanged.connect(
            lambda *_: self.settings_changed.emit()
        )
        self._url_input.editingFinished.connect(self.settings_changed.emit)
        self._key_input.editingFinished.connect(self.settings_changed.emit)

    def _capture_current(self, name: str) -> None:
        """Remember the current field values for provider *name*."""
        if not name:
            return
        self._provider_memory[name] = {
            "base_url": self._url_input.text().strip(),
            "model": self._model_combo.currentText().strip(),
            "api_key": self._key_input.text().strip(),
        }

    def _on_provider_changed(self, name: str) -> None:
        caps = PROVIDER_CAPABILITIES.get(name)
        if caps is None:
            return

        # Capture the outgoing provider so a later switch-back restores it.
        if self._current_provider and self._current_provider != name:
            self._capture_current(self._current_provider)
        self._current_provider = name
        remembered = self._provider_memory.get(name) or {}

        self._url_input.setText(remembered.get("base_url") or caps.default_base_url)

        # Rebuild the model list with signals blocked so the editable
        # combo doesn't emit spurious change events (or surface its popup)
        # mid-rebuild. We emit settings_changed once at the end instead.
        self._model_combo.blockSignals(True)
        self._model_combo.clear()
        for m in caps.default_models:
            self._model_combo.addItem(m)
        remembered_model = remembered.get("model") or ""
        if remembered_model:
            self._model_combo.setCurrentText(remembered_model)
        elif caps.default_models:
            self._model_combo.setCurrentText(caps.default_models[0])
        else:
            self._model_combo.setCurrentText("")
        self._model_combo.lineEdit().setPlaceholderText(
            caps.default_models[0] if caps.default_models else "server default"
        )
        self._model_combo.blockSignals(False)

        self._key_label.setVisible(caps.requires_api_key)
        self._key_input.setVisible(caps.requires_api_key)
        if caps.requires_api_key:
            # Restore the remembered key (without re-emitting change events).
            self._key_input.blockSignals(True)
            self._key_input.setText(remembered.get("api_key") or "")
            self._key_input.blockSignals(False)
            env_val = os.environ.get(caps.env_key_name, "") if caps.env_key_name else ""
            if env_val:
                self._key_input.setPlaceholderText(f"from ${caps.env_key_name}")
            else:
                self._key_input.setPlaceholderText("required")
        else:
            self._key_input.clear()
            self._key_input.setPlaceholderText("not required")
        self._status_label.setText("")
        self.settings_changed.emit()

    # -- Per-provider memory (so hosts can persist across restarts) ----------

    def provider_memory(self) -> dict[str, dict[str, str]]:
        """Return per-provider remembered values (current provider captured)."""
        if self._current_provider:
            self._capture_current(self._current_provider)
        return {k: dict(v) for k, v in self._provider_memory.items()}

    def set_provider_memory(self, memory: dict) -> None:
        """Seed per-provider memory (e.g. from saved settings)."""
        if isinstance(memory, dict):
            self._provider_memory = {
                k: dict(v) for k, v in memory.items() if isinstance(v, dict)
            }

    def reload_current_provider(self) -> None:
        """Re-apply the active provider's remembered values to the fields."""
        self._on_provider_changed(self._provider_combo.currentText())

    def _load_defaults(self) -> None:
        name = self._provider_combo.currentText()
        caps = PROVIDER_CAPABILITIES.get(name)
        if caps is None:
            return
        self._url_input.setText(caps.default_base_url)
        if caps.default_models:
            self._model_combo.setCurrentText(caps.default_models[0])
        else:
            self._model_combo.setCurrentText("")
        self._status_label.setText("")
        self.settings_changed.emit()

    def get_provider_config(self) -> ProviderConfig:
        name = self._provider_combo.currentText()
        caps = PROVIDER_CAPABILITIES.get(name)
        extra = dict(caps.extra_headers) if caps else {}
        config = ProviderConfig(
            name=name,
            base_url=self._url_input.text().strip()
            or (caps.default_base_url if caps else ""),
            api_key=self._key_input.text().strip(),
            model=self._model_combo.currentText().strip(),
            extra_headers=extra,
        )
        if not config.api_key:
            config.api_key = resolve_api_key(config)
        return config

    def validate(self) -> str | None:
        return validate_provider(self.get_provider_config())

    def _on_test(self) -> None:
        if self._test_worker is not None:
            return
        error = self.validate()
        if error:
            self._status_label.setStyleSheet(
                f"font-size: 11px; color: {theme.STATUS_ERR};"
            )
            self._status_label.setText(error)
            return

        provider = self.get_provider_config()
        self._status_label.setStyleSheet(
            f"font-size: 11px; color: {theme.TEXT_SECONDARY};"
        )
        self._status_label.setText("Testing...")
        self._test_btn.setEnabled(False)

        self._test_worker = _TestWorker(provider)
        self._test_worker.finished.connect(self._on_test_done)
        self._test_worker.start()

    def _on_test_done(self, ok: bool, msg: str) -> None:
        if ok:
            self._status_label.setStyleSheet(
                f"font-size: 11px; color: {theme.STATUS_OK};"
            )
        else:
            self._status_label.setStyleSheet(
                f"font-size: 11px; color: {theme.STATUS_ERR};"
            )
        self._status_label.setText(msg[:80])
        self._test_btn.setEnabled(True)
        self._test_worker = None
