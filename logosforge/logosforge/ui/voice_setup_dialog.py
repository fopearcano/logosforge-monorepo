"""Voice Setup — local Whisper configuration & diagnostics (Phase 8).

Parented, modeless, fullscreen-safe dialog (same verified pattern as the
glossary manager): enable Voice Mode, pick ONE local backend
(faster-whisper / whisper.cpp / LAN / mock-test), set model & executable
paths (with Browse), language and performance profile, and run the safe
diagnostics — microphone check, backend check, file-based local test
transcription (result shown here only; never committed, never sent to
Billy/AI, audio never retained) and a copyable secrets-free summary.
Nothing is installed or downloaded; invalid paths produce clear messages,
never crashes.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)

from logosforge.voice import setup as vs
from logosforge.voice.types import VoiceSettings


class VoiceSetupDialog(QDialog):
    """Modeless, parented Voice Setup panel."""

    def __init__(self, *, settings_get=None, settings_set=None,
                 parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("voiceSetupDialog")
        self.setWindowTitle("Voice Setup (local)")
        self.setModal(False)
        self.setMinimumSize(520, 460)
        self._get = settings_get
        self._set = settings_set
        self._last_error = ""

        layout = QVBoxLayout(self)

        # -- A. Voice Mode ----------------------------------------------------
        self._enable = QCheckBox("Enable Voice Mode")
        self._enable.setObjectName("setupEnableVoice")
        self._enable.toggled.connect(self._on_enable_toggled)
        layout.addWidget(self._enable)
        note = QLabel(vs.LOCAL_ONLY_STATEMENT + " Only transcript text may "
                      "be sent to Billy when you explicitly use Billy "
                      "actions.")
        note.setObjectName("setupPrivacyNote")
        note.setWordWrap(True)
        note.setStyleSheet("color: #94a3b8; font-size: 11px;")
        layout.addWidget(note)

        # -- B. Backend ---------------------------------------------------------
        backend_row = QHBoxLayout()
        backend_row.addWidget(QLabel("Backend:"))
        self._backend = QComboBox()
        self._backend.setObjectName("setupBackendCombo")
        for value, label in vs.BACKENDS:
            self._backend.addItem(label, value)
        self._backend.currentIndexChanged.connect(self._on_backend_changed)
        backend_row.addWidget(self._backend, stretch=1)
        self._backend_status = QLabel("")
        self._backend_status.setObjectName("setupBackendStatus")
        backend_row.addWidget(self._backend_status)
        layout.addLayout(backend_row)

        # -- C. Model -----------------------------------------------------------
        model_row = QHBoxLayout()
        model_row.addWidget(QLabel("Model path:"))
        self._model_path = QLineEdit()
        self._model_path.setObjectName("setupModelPath")
        self._model_path.setPlaceholderText(
            "Local Whisper model (directory for faster-whisper, file for "
            "whisper.cpp) — never downloaded automatically")
        self._model_path.editingFinished.connect(
            lambda: self._store("voice_whisper_model_path",
                                self._model_path.text().strip()))
        model_row.addWidget(self._model_path, stretch=1)
        browse_model = QPushButton("Browse…")
        browse_model.setObjectName("setupBrowseModel")
        browse_model.clicked.connect(self._on_browse_model)
        model_row.addWidget(browse_model)
        layout.addLayout(model_row)

        # -- D. whisper.cpp executable -------------------------------------------
        exe_row = QHBoxLayout()
        self._exe_label = QLabel("whisper.cpp executable:")
        exe_row.addWidget(self._exe_label)
        self._exe_path = QLineEdit()
        self._exe_path.setObjectName("setupExecutablePath")
        self._exe_path.setPlaceholderText(
            "Path to the whisper.cpp binary (e.g. ./main) — never installed "
            "automatically")
        self._exe_path.editingFinished.connect(
            lambda: self._store("voice_whisper_executable_path",
                                self._exe_path.text().strip()))
        exe_row.addWidget(self._exe_path, stretch=1)
        browse_exe = QPushButton("Browse…")
        browse_exe.setObjectName("setupBrowseExecutable")
        browse_exe.clicked.connect(self._on_browse_executable)
        exe_row.addWidget(browse_exe)
        self._exe_widgets = (self._exe_label, self._exe_path, browse_exe)
        layout.addLayout(exe_row)

        # -- E/F. Language + performance profile ---------------------------------
        lang_row = QHBoxLayout()
        lang_row.addWidget(QLabel("Language:"))
        self._language = QComboBox()
        self._language.setObjectName("setupLanguage")
        # Transcription language: follow the project's writing language
        # (default), Auto detect, or an explicit code (full Whisper list).
        from logosforge.i18n import tr
        self._language.addItem(tr("Use project language"), "project")
        for value, label in vs.LANGUAGES:           # full Whisper list
            self._language.addItem(
                label if value == "auto" else f"{label} ({value})", value)
        self._language.currentIndexChanged.connect(self._on_language_changed)
        lang_row.addWidget(self._language)
        lang_row.addSpacing(12)
        lang_row.addWidget(QLabel("Performance:"))
        self._profile = QComboBox()
        self._profile.setObjectName("setupProfile")
        for value, data in vs.PERFORMANCE_PROFILES.items():
            self._profile.addItem(data["label"], value)
        self._profile.currentIndexChanged.connect(self._on_profile_changed)
        lang_row.addWidget(self._profile)
        lang_row.addStretch()
        layout.addLayout(lang_row)
        self._profile_note = QLabel("")
        self._profile_note.setObjectName("setupProfileNote")
        self._profile_note.setStyleSheet("color: #94a3b8; font-size: 11px;")
        layout.addWidget(self._profile_note)

        # Custom profile values (visible for "custom" only).
        custom_row = QHBoxLayout()
        self._custom_widgets = []
        for label_text, key, name in (
                ("Silence ms:", "voice_silence_ms", "setupSilenceMs"),
                ("Max segment s:", "voice_max_segment_seconds",
                 "setupMaxSegment"),
                ("Beam size:", "voice_beam_size", "setupBeamSize")):
            lbl = QLabel(label_text)
            edit = QLineEdit()
            edit.setObjectName(name)
            edit.setMaximumWidth(64)
            edit.editingFinished.connect(
                lambda e=edit, k=key: self._store_int(k, e.text()))
            custom_row.addWidget(lbl)
            custom_row.addWidget(edit)
            self._custom_widgets += [lbl, edit]
        custom_row.addStretch()
        layout.addLayout(custom_row)

        # -- G. Diagnostics -------------------------------------------------------
        diag_row = QHBoxLayout()
        for label, slot, name in (
            ("Test microphone", self._on_test_mic, "setupTestMic"),
            ("Test backend", self._on_test_backend, "setupTestBackend"),
            ("Test transcription", self._on_test_transcription,
             "setupTestTranscription"),
            ("Copy diagnostics", self._on_copy_diagnostics,
             "setupCopyDiagnostics"),
        ):
            button = QPushButton(label)
            button.setObjectName(name)
            button.clicked.connect(slot)
            diag_row.addWidget(button)
        diag_row.addStretch()
        layout.addLayout(diag_row)
        self._result = QPlainTextEdit()
        self._result.setObjectName("setupResult")
        self._result.setReadOnly(True)
        self._result.setMaximumHeight(120)
        self._result.setPlaceholderText(
            "Diagnostics results appear here. Test transcripts are shown "
            "here only — never committed, never sent to Billy.")
        layout.addWidget(self._result)

        close_row = QHBoxLayout()
        close_row.addStretch()
        close_btn = QPushButton("Close")
        close_btn.setObjectName("setupClose")
        close_btn.clicked.connect(self.hide)
        close_row.addWidget(close_btn)
        layout.addLayout(close_row)

        self.refresh()

    # ------------------------------------------------------------- settings
    def _getter(self):
        if self._get is not None:
            return self._get
        from logosforge.settings import get_manager
        return get_manager().get

    def _store(self, key: str, value) -> None:
        setter = self._set
        if setter is None:
            from logosforge.settings import get_manager
            setter = get_manager().set
        setter(key, value)
        self._refresh_status()

    def _store_int(self, key: str, raw: str) -> None:
        try:
            self._store(key, int(raw))
        except (TypeError, ValueError):
            pass                          # invalid input: keep previous value

    def _on_enable_toggled(self, on: bool) -> None:
        self._store("enable_voice_mode", bool(on))
        # Enabling Voice Mode while the backend is still "disabled" leaves the
        # combo showing a backend that isn't actually applied — so "Test
        # backend" says "set to Disabled. Pick a backend" even though one
        # appears selected. Apply the shown backend so the displayed choice is
        # the real one (Test backend then gives the actionable model-path hint).
        if on and str(self._getter()("voice_backend_mode") or "disabled") \
                == "disabled":
            shown = self._backend.currentData()
            if shown and shown != "disabled":
                self._store("voice_backend_mode", shown)

    def _on_language_changed(self, _index: int) -> None:
        """Persist the transcription language MODE (+ explicit code)."""
        data = self._language.currentData()
        if data == "project":
            self._store("voice_language_mode", "project")
        elif data == "auto":
            self._store("voice_language_mode", "auto")
        else:
            self._store("voice_language", data)
            self._store("voice_language_mode", "explicit")

    def _settings(self) -> VoiceSettings:
        return VoiceSettings.from_store(self._getter())

    # --------------------------------------------------------------- refresh
    def refresh(self) -> None:
        get = self._getter()
        self._enable.blockSignals(True)
        self._enable.setChecked(bool(get("enable_voice_mode")))
        self._enable.blockSignals(False)
        mode = str(get("voice_backend_mode") or "disabled")
        idx = self._backend.findData(mode)
        self._backend.blockSignals(True)
        self._backend.setCurrentIndex(idx if idx >= 0 else 0)
        self._backend.blockSignals(False)
        self._model_path.setText(str(get("voice_whisper_model_path") or ""))
        self._exe_path.setText(
            str(get("voice_whisper_executable_path") or ""))
        # Transcription language selection = mode + explicit code. "Use
        # project language" (default) follows the project; an invalid saved
        # explicit value repairs to Auto detect exactly as before.
        from logosforge.voice.types import normalize_language
        raw_lang = str(get("voice_language") or "auto")
        normalized = normalize_language(raw_lang)
        if normalized == "auto" and raw_lang not in ("", "auto"):
            self._show_result("Saved language is no longer supported; "
                              "using Auto detect.")
            setter = self._set
            if setter is None:
                from logosforge.settings import get_manager
                setter = get_manager().set
            setter("voice_language", "auto")
            setter("voice_language_mode", "auto")
            lang_idx = self._language.findData("auto")
        else:
            mode = self._settings().resolved_language_mode()
            if mode == "project":
                lang_idx = self._language.findData("project")
            elif mode == "auto":
                lang_idx = self._language.findData("auto")
            else:
                lang_idx = self._language.findData(normalized)
        self._language.blockSignals(True)
        self._language.setCurrentIndex(lang_idx if lang_idx >= 0 else 0)
        self._language.blockSignals(False)
        profile_idx = self._profile.findData(
            str(get("voice_performance_profile") or "balanced"))
        self._profile.blockSignals(True)
        self._profile.setCurrentIndex(profile_idx if profile_idx >= 0 else 1)
        self._profile.blockSignals(False)
        for name, key in (("setupSilenceMs", "voice_silence_ms"),
                          ("setupMaxSegment", "voice_max_segment_seconds"),
                          ("setupBeamSize", "voice_beam_size")):
            edit = self.findChild(QLineEdit, name)
            if edit is not None:
                edit.setText(str(get(key) or 0))
        self._refresh_status()

    def _refresh_status(self) -> None:
        settings = self._settings()
        profile = vs.build_backend_profile(settings)
        self._backend_status.setText(f"[{profile.status}]")
        self._backend_status.setToolTip(profile.message)
        is_wcpp = self._backend.currentData() == "whisper_cpp"
        for widget in self._exe_widgets:
            widget.setVisible(is_wcpp)
        profile_id = self._profile.currentData() or "balanced"
        self._profile_note.setText(
            vs.PERFORMANCE_PROFILES.get(profile_id, {}).get("note", ""))
        for widget in self._custom_widgets:
            widget.setVisible(profile_id == "custom")

    # --------------------------------------------------------------- actions
    def _on_backend_changed(self, _index: int) -> None:
        self._store("voice_backend_mode", self._backend.currentData())

    def _on_profile_changed(self, _index: int) -> None:
        setter = self._set
        if setter is None:
            from logosforge.settings import get_manager
            setter = get_manager().set
        vs.apply_performance_profile(setter,
                                     self._profile.currentData()
                                     or "balanced")
        self.refresh()

    def _on_browse_model(self) -> None:
        if self._backend.currentData() == "whisper_cpp":
            path, _f = QFileDialog.getOpenFileName(
                self, "Whisper model file", "", "Model files (*)")
        else:
            path = QFileDialog.getExistingDirectory(
                self, "Whisper model directory")
        if path:
            self._model_path.setText(path)
            self._store("voice_whisper_model_path", path)

    def _on_browse_executable(self) -> None:
        path, _f = QFileDialog.getOpenFileName(
            self, "whisper.cpp executable", "", "Executables (*)")
        if path:
            self._exe_path.setText(path)
            self._store("voice_whisper_executable_path", path)

    def _show_result(self, text: str) -> None:
        self._result.setPlainText(text)

    def _on_test_mic(self) -> None:
        ok, msg = vs.microphone_diagnostics(self._settings())
        if not ok:
            self._last_error = msg
        self._show_result(("Microphone: OK — " if ok
                           else "Microphone: unavailable — ") + msg)

    def _on_test_backend(self) -> None:
        profile = vs.build_backend_profile(self._settings())
        if not profile.ready:
            self._last_error = profile.message
        text = f"Backend [{profile.status}]: {profile.message}"
        if profile.backend_id == "whisper_cpp" and profile.ready:
            ok, probe = vs.probe_whisper_cpp(profile.executable_path)
            text += f"\nProbe: {probe}"
            if not ok:
                self._last_error = probe
        self._show_result(text)

    def _on_test_transcription(self) -> None:
        settings = self._settings()
        profile = vs.build_backend_profile(settings)
        if not profile.ready:
            self._last_error = profile.message
            self._show_result(profile.message or vs.SETUP_REQUIRED_MESSAGE)
            return
        wav_path = ""
        if profile.backend_id != "mock":
            wav_path, _f = QFileDialog.getOpenFileName(
                self, "Short WAV file for the local test", "",
                "WAV audio (*.wav)")
            if not wav_path:
                self._show_result("Test cancelled — no file selected.")
                return
        ok, text = vs.run_test_transcription(settings, wav_path=wav_path)
        if not ok:
            self._last_error = text
        self._show_result(("Test transcript (shown here only — not "
                           "committed):\n" + text) if ok else text)

    def _on_copy_diagnostics(self) -> None:
        from PySide6.QtWidgets import QApplication
        summary = vs.diagnostics_summary(self._settings(),
                                         last_error=self._last_error)
        QApplication.clipboard().setText(summary)
        self._show_result(summary)
