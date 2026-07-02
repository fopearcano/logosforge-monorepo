"""Voice dictation — local-first panel + floating Voice Dictation window.

:class:`VoicePanel` is the dictation surface (status, backend row, transcript
preview, Start / Stop / Commit / Clear / Hide). It drives
:class:`VoiceSessionController`; transcription runs off the UI thread (on the
recorder's callback thread) and results are marshaled back via Qt signals.

:class:`VoiceDictationWindow` is the panel's host: a **floating, modeless,
resizable** window so the transcript can be reviewed comfortably while
writing. It is always **parented to the main window** (never a parentless
top-level window, no unsafe window flags — the rules that keep it clear of
the old standalone-Pages fullscreen-minimize bug). Showing/hiding it never
touches project state; closing/hiding while recording stops the session
safely and keeps the transcript preview (nothing is silently discarded, and
nothing is ever auto-committed).

Local-first: only the local backends are ever used; audio is processed on
this device (or, in LAN mode, sent only to the configured local-network
Whisper server). Feature-flagged OFF by default; when the backend is not
configured the panel shows a non-blocking setup message and stays inert.
"""

from __future__ import annotations

from collections.abc import Callable

import time

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from logosforge.voice.history import VoiceTranscriptHistory

from logosforge.voice.editor_commit import EditorCommitTarget
from logosforge.voice.types import PRIVACY_NOTE, SETUP_MESSAGE, VoiceStatus

# (value stored in settings, label shown in the selector)
_BACKEND_MODES = (
    ("disabled", "Disabled"),
    ("local_process", "Local PC"),
    ("whisper_cpp", "whisper.cpp"),
    ("lan_server", "Local LAN Server"),
    ("mock", "Mock / Test"),
)

_STATUS_TEXT = {
    VoiceStatus.DISABLED: "Voice: not configured",
    VoiceStatus.OFF: "Voice: off",
    VoiceStatus.LISTENING: "Voice: listening…",
    VoiceStatus.PROCESSING: "Voice: processing…",
    VoiceStatus.TRANSCRIPT_READY: "Voice: transcript ready",
    VoiceStatus.ERROR: "Voice: error",
}


class VoicePanel(QWidget):
    """Embedded local dictation panel (plain-text commit only, Alpha MVP)."""

    # Marshal controller callbacks (possibly off-thread) to the UI thread.
    _status_changed = Signal(str)
    _final_text = Signal(str)
    _final_segment = Signal(object)      # full TranscriptSegment (history)
    _notice = Signal(str)                # plain-language session feedback
    _level = Signal(float)               # live mic input level (int16 RMS)
    # Emitted by the panel's Hide button; the hosting window hides safely.
    hide_requested = Signal()

    def __init__(self, *, settings_get: Callable[[str], object] | None = None,
                 settings_set: Callable[[str, object], None] | None = None,
                 commit_target: EditorCommitTarget | None = None,
                 context_provider: Callable[[], object] | None = None,
                 on_data_changed: Callable[[], None] | None = None,
                 project_language_getter: Callable[[], str] | None = None,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("voicePanel")
        self._settings_get = settings_get
        self._settings_set = settings_set
        # Multi-language coordination: the active project's writing language
        # ("Use project language" mode resolves through this; None → auto).
        self._project_language_getter = project_language_getter
        self._commit = commit_target or EditorCommitTarget()
        # Phase 2: mode-aware commit routing (optional — without a context
        # provider the panel behaves exactly as the cursor-only MVP).
        self._context_provider = context_provider
        self._on_data_changed = on_data_changed
        self._transcript_project_id: int | None = None
        self._had_transcript = False
        self._targets_active = False     # True once the router populated targets
        # Phase 3: local, session-only transcript history (review layer).
        self._history = VoiceTranscriptHistory()
        self._editing_entry_id: str | None = None
        # Phase 6: Dexter's Room shell (internal VoiceRoom* modules) —
        # session state + proposal queue.
        from logosforge.voice.room import (ProposalQueue,
                                             VoiceRoomStateMachine)
        self._room = VoiceRoomStateMachine()
        self._queue = ProposalQueue()
        self._controller = None
        self._status = VoiceStatus.OFF

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(4)

        # Dexter's Room shell header (internal VoiceRoom* modules power
        # the Dexter's Room UI): session state + context summary.
        self._room_label = QLabel("Dexter's Room (Alpha) · idle")
        self._room_label.setObjectName("voiceRoomStatus")
        self._room_label.setStyleSheet("color: #94a3b8; font-size: 11px;")
        layout.addWidget(self._room_label)

        top = QHBoxLayout()
        self._status_label = QLabel(_STATUS_TEXT[VoiceStatus.OFF])
        self._status_label.setObjectName("voiceStatusLabel")
        self._status_label.setStyleSheet("font-weight: bold;")
        top.addWidget(self._status_label, stretch=1)
        # Live microphone input level while recording — answers "is it hearing
        # me?" at a glance (amber when below the speech threshold, green above).
        self._level_meter = QProgressBar()
        self._level_meter.setObjectName("voiceLevelMeter")
        self._level_meter.setRange(0, 100)
        self._level_meter.setTextVisible(False)
        self._level_meter.setFixedSize(120, 10)
        self._level_meter.setToolTip("Microphone input level (while recording)")
        self._level_meter.setVisible(False)
        self._level_quiet = None
        top.addWidget(self._level_meter)
        # Elapsed-time ticker for the (otherwise opaque) transcribing state.
        self._proc_timer = QTimer(self)
        self._proc_timer.setInterval(300)
        self._proc_timer.timeout.connect(self._tick_processing)
        self._proc_start = 0.0
        note = QLabel(PRIVACY_NOTE)
        note.setObjectName("voicePrivacyNote")
        note.setStyleSheet("color: #94a3b8; font-size: 11px;")
        top.addWidget(note)
        layout.addLayout(top)

        # -- Backend selector + contextual config (Local PC model path / LAN URL)
        cfg = QHBoxLayout()
        cfg.addWidget(QLabel("Backend:"))
        self._backend_combo = QComboBox()
        self._backend_combo.setObjectName("voiceBackendCombo")
        for value, label in _BACKEND_MODES:
            self._backend_combo.addItem(label, value)
        self._backend_combo.currentIndexChanged.connect(self._on_backend_changed)
        cfg.addWidget(self._backend_combo)
        self._config_edit = QLineEdit()
        self._config_edit.setObjectName("voiceConfigEdit")
        self._config_edit.editingFinished.connect(self._on_config_edited)
        cfg.addWidget(self._config_edit, stretch=1)
        self._lan_check_btn = QPushButton("Check LAN server")
        self._lan_check_btn.setObjectName("voiceLanCheck")
        self._lan_check_btn.clicked.connect(self._on_check_lan)
        cfg.addWidget(self._lan_check_btn)
        self._setup_btn = QPushButton("Voice Setup…")
        self._setup_btn.setObjectName("voiceSetupOpen")
        self._setup_btn.clicked.connect(self._on_setup_open)
        cfg.addWidget(self._setup_btn)
        layout.addLayout(cfg)
        self._setup_dialog = None
        self._sync_backend_row()

        # -- Commit target row (Phase 2; shown only with a context provider) --
        target_row = QHBoxLayout()
        self._mode_combo = QComboBox()
        self._mode_combo.setObjectName("voiceModeSelect")
        self._mode_combo.addItem("Dictation", "dictation")   # default
        self._mode_combo.addItem("Intent", "intent")
        self._mode_combo.addItem("Ask Billy", "ask_billy")
        self._mode_combo.addItem("Edit with Billy", "edit_billy")
        self._mode_combo.setToolTip(
            "Dictation: the transcript is content. Intent: the transcript "
            "is an instruction — preview first, apply only on confirm.")
        self._mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        target_row.addWidget(self._mode_combo)
        self._target_label = QLabel("Send to:")
        self._target_label.setObjectName("voiceTargetLabel")
        target_row.addWidget(self._target_label)
        self._target_combo = QComboBox()
        self._target_combo.setObjectName("voiceTargetCombo")
        self._target_combo.currentIndexChanged.connect(
            self._on_target_changed)
        target_row.addWidget(self._target_combo, stretch=1)
        self._psyke_type = QComboBox()
        self._psyke_type.setObjectName("voicePsykeType")
        from logosforge.voice.commit_router import PSYKE_ENTRY_TYPES
        for value in PSYKE_ENTRY_TYPES:                  # "other" first/default
            self._psyke_type.addItem(value.capitalize(), value)
        self._psyke_type.setToolTip(
            "PSYKE entry type — chosen by you, never guessed.")
        target_row.addWidget(self._psyke_type)
        self._char_combo = QComboBox()
        self._char_combo.setObjectName("voiceCharacterCombo")
        self._char_combo.setEditable(True)               # manual entry allowed
        self._char_combo.setToolTip(
            "Character cue for the dialogue — chosen by you, never guessed.")
        target_row.addWidget(self._char_combo)
        layout.addLayout(target_row)

        # -- Intent row (Phase 4; visible only in Intent mode) ----------------
        intent_row = QHBoxLayout()
        self._intent_label = QLabel("Intent:")
        self._intent_label.setObjectName("voiceIntentLabel")
        intent_row.addWidget(self._intent_label)
        self._intent_combo = QComboBox()
        self._intent_combo.setObjectName("voiceIntentCombo")
        self._intent_combo.currentIndexChanged.connect(
            self._on_intent_changed)
        intent_row.addWidget(self._intent_combo, stretch=1)
        self._gn_field_combo = QComboBox()
        self._gn_field_combo.setObjectName("voiceGnFieldCombo")
        from logosforge.voice.intent_router import GN_FIELD_CHOICES
        for value, label in GN_FIELD_CHOICES:
            self._gn_field_combo.addItem(label, value)
        intent_row.addWidget(self._gn_field_combo)
        self._intent_preview_btn = QPushButton("Preview")
        self._intent_preview_btn.setObjectName("voiceIntentPreview")
        self._intent_preview_btn.clicked.connect(self._on_intent_preview)
        intent_row.addWidget(self._intent_preview_btn)
        self._intent_apply_btn = QPushButton("Apply")
        self._intent_apply_btn.setObjectName("voiceIntentApply")
        self._intent_apply_btn.clicked.connect(self._on_intent_apply)
        self._intent_apply_btn.setEnabled(False)
        intent_row.addWidget(self._intent_apply_btn)
        self._intent_cancel_btn = QPushButton("Cancel")
        self._intent_cancel_btn.setObjectName("voiceIntentCancel")
        self._intent_cancel_btn.clicked.connect(self._on_intent_cancel)
        intent_row.addWidget(self._intent_cancel_btn)
        layout.addLayout(intent_row)
        self._intent_preview_area = QPlainTextEdit()
        self._intent_preview_area.setObjectName("voiceIntentPreviewArea")
        self._intent_preview_area.setReadOnly(True)
        self._intent_preview_area.setMaximumHeight(110)
        layout.addWidget(self._intent_preview_area)
        self._pending_intent_preview = None

        # -- Billy Voice Bridge (Phase 5) -------------------------------------
        billy_row = QHBoxLayout()
        self._billy_label = QLabel("Billy:")
        self._billy_label.setObjectName("voiceBillyLabel")
        billy_row.addWidget(self._billy_label)
        self._billy_op_combo = QComboBox()
        self._billy_op_combo.setObjectName("voiceBillyOpCombo")
        billy_row.addWidget(self._billy_op_combo, stretch=1)
        self._billy_generate_btn = QPushButton("Generate Proposal")
        self._billy_generate_btn.setObjectName("voiceBillyGenerate")
        self._billy_generate_btn.clicked.connect(self._on_billy_generate)
        billy_row.addWidget(self._billy_generate_btn)
        self._billy_apply_btn = QPushButton("Apply")
        self._billy_apply_btn.setObjectName("voiceBillyApply")
        self._billy_apply_btn.clicked.connect(self._on_billy_apply)
        self._billy_apply_btn.setEnabled(False)
        billy_row.addWidget(self._billy_apply_btn)
        self._billy_cancel_btn = QPushButton("Cancel")
        self._billy_cancel_btn.setObjectName("voiceBillyCancel")
        self._billy_cancel_btn.clicked.connect(self._on_billy_cancel)
        billy_row.addWidget(self._billy_cancel_btn)
        self._billy_copy_btn = QPushButton("Copy")
        self._billy_copy_btn.setObjectName("voiceBillyCopy")
        self._billy_copy_btn.clicked.connect(self._on_billy_copy)
        billy_row.addWidget(self._billy_copy_btn)
        layout.addLayout(billy_row)
        self._billy_preview_area = QPlainTextEdit()
        self._billy_preview_area.setObjectName("voiceBillyPreviewArea")
        self._billy_preview_area.setReadOnly(True)
        self._billy_preview_area.setMaximumHeight(110)
        layout.addWidget(self._billy_preview_area)
        self._pending_billy_proposal = None
        # Proposal queue (session-scoped; preview-first; stale-guarded).
        self._queue_list = QListWidget()
        self._queue_list.setObjectName("voiceProposalQueue")
        self._queue_list.setMaximumHeight(64)
        self._queue_list.setToolTip(
            "This session's proposals — double-click a ready one to make it "
            "the active proposal again. Stale proposals cannot be applied.")
        self._queue_list.itemDoubleClicked.connect(self._on_queue_activate)
        self._queue_list.setVisible(False)
        layout.addWidget(self._queue_list)

        # -- Voice glossary corrections (Phase 7; local, review-first) --------
        corr_row = QHBoxLayout()
        self._glossary_info = QLabel("")
        self._glossary_info.setObjectName("voiceGlossaryInfo")
        self._glossary_info.setStyleSheet("color: #94a3b8; font-size: 11px;")
        corr_row.addWidget(self._glossary_info, stretch=1)
        for label, slot, name in (
            ("Apply corrections", self._on_corrections_apply,
             "voiceGlossaryApply"),
            ("Reject", self._on_corrections_reject, "voiceGlossaryReject"),
            ("Learn correction…", self._on_glossary_learn,
             "voiceGlossaryLearn"),
            ("Glossary…", self._on_glossary_open, "voiceGlossaryOpen"),
        ):
            button = QPushButton(label)
            button.setObjectName(name)
            button.setFlat(True)
            button.clicked.connect(slot)
            corr_row.addWidget(button)
        layout.addLayout(corr_row)
        self._correction_list = QListWidget()
        self._correction_list.setObjectName("voiceCorrectionList")
        self._correction_list.setMaximumHeight(56)
        self._correction_list.setVisible(False)
        layout.addWidget(self._correction_list)
        self._glossary_dialog = None
        self._glossary_widgets = (self._glossary_info, self._correction_list)
        self._billy_widgets = (self._billy_label, self._billy_op_combo,
                               self._billy_generate_btn,
                               self._billy_apply_btn,
                               self._billy_cancel_btn, self._billy_copy_btn,
                               self._billy_preview_area)
        for w in self._billy_widgets:
            w.setVisible(False)          # inert without a context provider
        self._intent_widgets = (self._intent_label, self._intent_combo,
                                self._gn_field_combo,
                                self._intent_preview_btn,
                                self._intent_apply_btn,
                                self._intent_cancel_btn,
                                self._intent_preview_area)
        for w in self._intent_widgets:
            w.setVisible(False)          # Dictation mode is the default

        for w in (self._mode_combo, self._target_label, self._target_combo,
                  self._psyke_type, self._char_combo):
            w.setVisible(False)          # inert without a context provider

        self._preview = QPlainTextEdit()
        self._preview.setObjectName("voiceTranscriptPreview")
        self._preview.setPlaceholderText(
            "Transcript preview — review, then Commit to the editor.")
        self._preview.setMinimumHeight(120)   # readable; grows with the window
        layout.addWidget(self._preview, stretch=1)

        # -- Transcript history (Phase 3): session-only, local review layer --
        self._history_list = QListWidget()
        self._history_list.setObjectName("voiceHistoryList")
        self._history_list.setMaximumHeight(110)
        self._history_list.setToolTip(
            "This session's transcript segments — check segments to commit "
            "them together. History is local and temporary.")
        self._history_list.currentItemChanged.connect(
            lambda *_: self._refresh_corrections_ui())
        layout.addWidget(self._history_list)

        hist_row = QHBoxLayout()
        for label, slot, name in (
            ("Edit", self._on_hist_edit, "voiceHistEdit"),
            ("Apply Edit", self._on_hist_apply_edit, "voiceHistApplyEdit"),
            ("Restore", self._on_hist_restore, "voiceHistRestore"),
            ("Discard", self._on_hist_discard, "voiceHistDiscard"),
            ("Retry", self._on_hist_retry, "voiceHistRetry"),
            ("Merge", self._on_hist_merge, "voiceHistMerge"),
            ("Split at cursor", self._on_hist_split, "voiceHistSplit"),
        ):
            b = QPushButton(label)
            b.setObjectName(name)
            b.setFlat(True)
            b.clicked.connect(slot)
            hist_row.addWidget(b)
        hist_row.addStretch()
        self._undo_btn = QPushButton("Undo last commit")
        self._undo_btn.setObjectName("voiceUndoCommit")
        self._undo_btn.setFlat(True)
        self._undo_btn.clicked.connect(self._on_undo_commit)
        hist_row.addWidget(self._undo_btn)
        self._clear_pending_btn = QPushButton("Clear uncommitted")
        self._clear_pending_btn.setObjectName("voiceHistClearPending")
        self._clear_pending_btn.setFlat(True)
        self._clear_pending_btn.clicked.connect(self._on_clear_uncommitted)
        hist_row.addWidget(self._clear_pending_btn)
        layout.addLayout(hist_row)

        row = QHBoxLayout()
        self._start_btn = QPushButton("Start")
        self._start_btn.setObjectName("voiceStart")
        self._start_btn.clicked.connect(self.start)
        self._stop_btn = QPushButton("Stop")
        self._stop_btn.setObjectName("voiceStop")
        self._stop_btn.clicked.connect(self.stop)
        self._pause_btn = QPushButton("Pause")
        self._pause_btn.setObjectName("voicePause")
        self._pause_btn.setToolTip(
            "Pause listening — the session, transcript history and queue "
            "are kept.")
        self._pause_btn.clicked.connect(self._on_pause)
        self._commit_btn = QPushButton("Commit to editor")
        self._commit_btn.setObjectName("voiceCommit")
        self._commit_btn.clicked.connect(self.commit)
        self._clear_btn = QPushButton("Clear")
        self._clear_btn.setObjectName("voiceClear")
        self._clear_btn.clicked.connect(self.clear_preview)
        self._copy_btn = QPushButton("Copy")
        self._copy_btn.setObjectName("voiceCopy")
        self._copy_btn.clicked.connect(self._copy_transcript)
        self._auto_commit = QCheckBox("Auto-commit after pause")
        self._auto_commit.setObjectName("voiceAutoCommit")
        self._hide_btn = QPushButton("Hide")
        self._hide_btn.setObjectName("voiceHide")
        self._hide_btn.clicked.connect(self.hide_requested.emit)
        for w in (self._start_btn, self._stop_btn, self._pause_btn,
                  self._commit_btn, self._clear_btn, self._copy_btn):
            row.addWidget(w)
        row.addWidget(self._auto_commit)
        row.addStretch()
        row.addWidget(self._hide_btn)
        layout.addLayout(row)

        self._status_changed.connect(self._apply_status_str)
        self._final_text.connect(self._apply_final_text)
        self._final_segment.connect(self._apply_final_segment)
        self._notice.connect(lambda msg: self._status_label.setText(msg))
        self._level.connect(self._apply_level)
        self._preview.textChanged.connect(self._refresh_buttons)

        self.setVisible(False)               # hidden until toggled / enabled
        self._apply_status(VoiceStatus.OFF)

    # -- settings / availability --------------------------------------------
    def _load_settings(self):
        from logosforge.voice.types import VoiceSettings
        get = self._settings_get
        if get is None:
            from logosforge.settings import get_manager
            get = get_manager().get
        settings = VoiceSettings.from_store(get)
        # Fill the project's writing language so "Use project language"
        # resolves; any failure degrades to Auto detect (never crashes).
        if self._project_language_getter is not None:
            try:
                settings.project_language_code = str(
                    self._project_language_getter() or "auto")
            except Exception:
                settings.project_language_code = "auto"
        return settings

    def is_enabled(self) -> bool:
        return bool(self._load_settings().enabled)

    def _store_set(self, key: str, value) -> None:
        setter = self._settings_set
        if setter is None:
            from logosforge.settings import get_manager
            setter = get_manager().set
        setter(key, value)

    # -- backend selector / config row ----------------------------------------
    def _sync_backend_row(self) -> None:
        """Reflect the stored backend mode + contextual config field."""
        settings = self._load_settings()
        mode = (settings.backend_mode or "disabled").strip().lower()
        idx = next((i for i, (v, _l) in enumerate(_BACKEND_MODES) if v == mode), 0)
        self._backend_combo.blockSignals(True)
        self._backend_combo.setCurrentIndex(idx)
        self._backend_combo.blockSignals(False)
        if mode == "lan_server":
            self._config_edit.setVisible(True)
            self._lan_check_btn.setVisible(True)
            self._config_edit.setPlaceholderText(
                "LAN Whisper server URL (private address only, e.g. "
                "http://192.168.1.50:8000)")
            self._config_edit.setText(settings.lan_base_url)
            self._config_edit.setToolTip(
                "LAN mode sends audio only to the configured local network "
                "Whisper server. Do not use public URLs.")
        elif mode == "local_process":
            self._config_edit.setVisible(True)
            self._lan_check_btn.setVisible(False)
            self._config_edit.setPlaceholderText(
                "Local Whisper model path (no automatic downloads)")
            self._config_edit.setText(settings.model_path)
            self._config_edit.setToolTip(
                "Path to a local faster-whisper model directory.")
        elif mode == "whisper_cpp":
            self._config_edit.setVisible(True)
            self._lan_check_btn.setVisible(False)
            self._config_edit.setPlaceholderText(
                "whisper.cpp model file (executable set in Voice Setup)")
            self._config_edit.setText(settings.model_path)
            self._config_edit.setToolTip(
                "Path to a local whisper.cpp model file; the executable "
                "path is configured in Voice Setup.")
        else:
            self._config_edit.setVisible(False)
            self._lan_check_btn.setVisible(False)

    def _on_backend_changed(self, index: int) -> None:
        # Changing the backend mode mid-session must not leave the previous
        # backend recording: stop the active session safely first (finalizes a
        # valid pending segment; transcript stays uncommitted for review).
        if self._controller is not None and self._controller.status in (
                VoiceStatus.LISTENING, VoiceStatus.PROCESSING):
            self.stop()
        value = self._backend_combo.itemData(index) or "disabled"
        self._store_set("voice_backend_mode", value)
        self._sync_backend_row()

    def _on_config_edited(self) -> None:
        mode = self._backend_combo.currentData() or "disabled"
        text = self._config_edit.text().strip()
        if mode == "lan_server":
            self._store_set("voice_lan_base_url", text)
        elif mode in ("local_process", "whisper_cpp"):
            self._store_set("voice_whisper_model_path", text)

    def _on_check_lan(self) -> None:
        from logosforge.voice.lan_server import LanWhisperTranscriber
        settings = self._load_settings()
        ok, msg = LanWhisperTranscriber(settings).health_check()
        self._status_label.setText(msg)

    def _ensure_controller(self) -> tuple[bool, str]:
        settings = self._load_settings()
        if not settings.enabled:
            return (False, "Voice mode is off. Enable it in Settings.")
        from logosforge.voice.recorder import build_recorder
        from logosforge.voice.session import VoiceSessionController
        from logosforge.voice.transcriber import build_transcriber
        recorder = build_recorder(settings)
        transcriber = build_transcriber(settings)
        self._controller = VoiceSessionController(
            settings, recorder, transcriber,
            on_status=lambda s: self._status_changed.emit(s.value),
            on_final_transcript=lambda seg: self._final_segment.emit(seg),
            on_notice=lambda msg: self._notice.emit(msg),
            on_level=lambda rms: self._level.emit(rms))
        return self._controller.availability()

    # -- lifecycle -----------------------------------------------------------
    def toggle_panel(self) -> None:
        """Show/hide the panel widget itself (legacy/widget-level toggle).

        Hiding must always work — even with the feature flag off (the old
        behavior pinned the panel visible in that state, which is exactly the
        "panel never hides again" bug). The flag only controls whether the
        controls are live, never whether the panel can be dismissed.
        """
        if self.isVisible():
            self.setVisible(False)
            return
        self.sync_enabled_state()
        self.setVisible(True)

    def sync_enabled_state(self) -> None:
        """Reflect the feature flag: inert message when off, live when on."""
        if not self.is_enabled():
            self._apply_status(VoiceStatus.DISABLED)
            self._status_label.setText(
                "Voice mode is off — enable it in Settings.")
            self._set_controls_enabled(False)
        else:
            self._sync_backend_row()
            self._set_controls_enabled(True)
            self._refresh_buttons()
            self._apply_setup_gate()
        self._refresh_targets()

    # -- Phase 2: mode-aware commit targets ----------------------------------
    def _build_context(self):
        """The live VoiceCommitContext + the user's explicit selections."""
        if self._context_provider is None:
            return None
        try:
            ctx = self._context_provider()
        except Exception:
            return None
        if ctx is None:
            return None
        ctx.psyke_entry_type = self._psyke_type.currentData() or "other"
        ctx.character_name = self._char_combo.currentText().strip()
        ctx.transcript_project_id = self._transcript_project_id
        ctx.gn_field_choice = (self._gn_field_combo.currentData()
                               or "visual_description")
        return ctx

    def _selected_target_id(self) -> str:
        from logosforge.voice.commit_router import T_CURSOR
        if not self._targets_active or self._target_combo.currentIndex() < 0:
            return T_CURSOR
        return self._target_combo.currentData() or T_CURSOR

    def _refresh_targets(self) -> None:
        """Rebuild the target list from the router (read-only; no mutation)."""
        ctx = self._build_context()
        if ctx is None:
            return                       # cursor-only MVP behavior (row hidden)
        from logosforge.voice.commit_router import (
            get_available_voice_commit_targets)
        targets = get_available_voice_commit_targets(ctx)
        keep = self._target_combo.currentData()
        self._target_combo.blockSignals(True)
        self._target_combo.clear()
        for target in targets:
            self._target_combo.addItem(target.label, target.id)
            i = self._target_combo.count() - 1
            item = self._target_combo.model().item(i)
            if not target.enabled:
                item.setEnabled(False)
                item.setToolTip(target.reason_if_disabled)
                self._target_combo.setItemData(
                    i, target.reason_if_disabled, Qt.ItemDataRole.ToolTipRole)
        idx = self._target_combo.findData(keep)
        self._target_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self._target_combo.blockSignals(False)
        self._targets_active = True
        has_text = bool(self._preview.toPlainText().strip())
        for w in (self._mode_combo, self._target_label, self._target_combo):
            w.setVisible(True)
        self._target_combo.setEnabled(has_text)
        self._sync_target_subcontrols(ctx)
        if self.voice_mode() == "intent":
            self._refresh_intents()
        for w in self._billy_widgets:
            if w is not self._billy_preview_area:
                w.setVisible(True)
        self._queue_list.setVisible(True)
        self._refresh_billy_ops()
        self._update_room_label()

    def _sync_target_subcontrols(self, ctx=None) -> None:
        from logosforge.voice.commit_router import (
            T_PSYKE, T_SP_DIALOGUE, T_STAGE_DIALOGUE)
        tid = self._target_combo.currentData()
        self._psyke_type.setVisible(tid == T_PSYKE)
        wants_char = tid in (T_SP_DIALOGUE, T_STAGE_DIALOGUE)
        self._char_combo.setVisible(wants_char)
        if wants_char and ctx is not None and self._char_combo.count() == 0:
            try:                          # existing characters only; no guessing
                for c in ctx.db.get_all_characters(ctx.project_id):
                    self._char_combo.addItem(c.name)
                self._char_combo.setCurrentText("")
            except Exception:
                pass

    def _on_target_changed(self, _index: int) -> None:
        ctx = self._build_context()
        self._sync_target_subcontrols(ctx)

    def _copy_transcript(self) -> None:
        from PySide6.QtWidgets import QApplication
        QApplication.clipboard().setText(self._preview.toPlainText())
        self._status_label.setText("Voice: transcript copied")

    # -- Phase 3: transcript history -----------------------------------------
    def _apply_final_segment(self, seg) -> None:
        """A finalized segment: record it in the local history, then feed the
        live preview exactly as before."""
        ctx = self._build_context()
        entry = self._history.add_final_segment(
            seg,
            project_id=getattr(ctx, "project_id", 0) if ctx else 0,
            writing_mode=getattr(ctx, "writing_mode", "") if ctx else "")
        self._generate_corrections(entry, ctx)
        self._refresh_history_ui()
        self._apply_final_text(seg.text)

    def _checked_entry_ids(self) -> list[str]:
        ids = []
        for i in range(self._history_list.count()):
            item = self._history_list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                ids.append(item.data(Qt.ItemDataRole.UserRole))
        return ids

    def _current_entry(self):
        item = self._history_list.currentItem()
        if item is None:
            return None
        return self._history.get(item.data(Qt.ItemDataRole.UserRole))

    def _refresh_history_ui(self) -> None:
        keep_current = None
        if self._history_list.currentItem() is not None:
            keep_current = self._history_list.currentItem().data(
                Qt.ItemDataRole.UserRole)
        checked = set(self._checked_entry_ids())
        self._history_list.blockSignals(True)
        self._history_list.clear()
        for entry in self._history.visible_entries():
            label = f"[{entry.status}] {entry.preview()}"
            if entry.committed_target:
                label += f"  → {entry.committed_target}"
            if getattr(entry, "corrections", None):
                label += f"  · {len(entry.corrections)} suggestion(s)"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, entry.id)
            item.setToolTip(entry.text)
            if self._history.committable(entry):
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(
                    Qt.CheckState.Checked if entry.id in checked
                    else Qt.CheckState.Unchecked)
            self._history_list.addItem(item)
            if entry.id == keep_current:
                self._history_list.setCurrentItem(item)
        self._history_list.blockSignals(False)
        # Undo button reflects the live can_undo state (with the reason).
        from logosforge.voice.commit_router import can_undo
        ctx = self._build_context()
        if ctx is None:
            self._undo_btn.setEnabled(False)
            self._undo_btn.setToolTip("Nothing to undo.")
        else:
            ok, reason = can_undo(self._history.last_commit_op, ctx)
            self._undo_btn.setEnabled(ok)
            self._undo_btn.setToolTip("" if ok else reason)

    def _on_hist_edit(self) -> None:
        entry = self._current_entry()
        if entry is None:
            self._status_label.setText("Voice: select a segment first")
            return
        self._editing_entry_id = entry.id
        self._preview.setPlainText(entry.text)
        self._status_label.setText(
            "Voice: editing segment — change the text, then Apply Edit")

    def _on_hist_apply_edit(self) -> None:
        if self._editing_entry_id is None:
            self._status_label.setText("Voice: click Edit on a segment first")
            return
        ok = self._history.edit(self._editing_entry_id,
                                self._preview.toPlainText())
        self._status_label.setText(
            "Voice: segment updated" if ok
            else "Voice: this segment can no longer be edited")
        if ok:
            self._editing_entry_id = None
        self._refresh_history_ui()

    def _on_hist_restore(self) -> None:
        entry = self._current_entry()
        if entry is not None and self._history.restore_original(entry.id):
            self._status_label.setText("Voice: original text restored")
            if self._editing_entry_id == entry.id:
                self._preview.setPlainText(entry.text)
        self._refresh_history_ui()

    def _on_hist_discard(self) -> None:
        ids = self._checked_entry_ids()
        entry = self._current_entry()
        if not ids and entry is not None:
            ids = [entry.id]
        discarded = sum(1 for eid in ids if self._history.discard(eid))
        if discarded:
            self._status_label.setText(f"Voice: {discarded} segment(s) "
                                       "discarded")
        self._refresh_history_ui()

    def _on_hist_retry(self) -> None:
        entry = self._current_entry()
        if entry is None:
            self._status_label.setText("Voice: select a segment first")
            return
        ok, reason = self._history.can_retry(entry)
        if not ok:
            self._status_label.setText(f"Voice: {reason}")
            return
        from logosforge.voice.transcriber import build_transcriber
        transcriber = build_transcriber(self._load_settings())
        ok, msg = self._history.retry_transcription(entry.id, transcriber)
        self._status_label.setText(f"Voice: {msg}")
        if ok and self._editing_entry_id == entry.id:
            self._preview.setPlainText(entry.text)
        self._refresh_history_ui()

    def _on_hist_merge(self) -> None:
        ids = self._checked_entry_ids()
        merged = self._history.merge(ids)
        self._status_label.setText(
            "Voice: segments merged" if merged is not None
            else "Voice: select 2+ adjacent uncommitted segments to merge")
        self._refresh_history_ui()

    def _on_hist_split(self) -> None:
        if self._editing_entry_id is None:
            self._status_label.setText(
                "Voice: click Edit on a segment, place the cursor, then Split")
            return
        # Apply any pending edit first so the split sees the visible text.
        self._history.edit(self._editing_entry_id, self._preview.toPlainText())
        pos = self._preview.textCursor().position()
        result = self._history.split(self._editing_entry_id, pos)
        self._status_label.setText(
            "Voice: segment split" if result is not None
            else "Voice: both halves must be non-empty")
        if result is not None:
            self._editing_entry_id = None
        self._refresh_history_ui()

    def _on_undo_commit(self) -> None:
        ctx = self._build_context()
        if ctx is None:
            self._status_label.setText("Voice: nothing to undo")
            return
        from logosforge.voice.commit_router import undo_commit
        ok, msg = undo_commit(self._history.last_commit_op, ctx)
        self._status_label.setText(f"Voice: {msg}")
        if ok:
            self._history.last_commit_op = None
            if self._on_data_changed is not None:
                self._on_data_changed()
        self._refresh_history_ui()

    def _on_clear_uncommitted(self) -> None:
        removed = self._history.clear_uncommitted()
        self._editing_entry_id = None
        self._status_label.setText(f"Voice: {removed} uncommitted segment(s) "
                                   "cleared")
        self._refresh_history_ui()

    # -- Phase 4: Intent mode -------------------------------------------------
    def voice_mode(self) -> str:
        return self._mode_combo.currentData() or "dictation"

    def _on_mode_changed(self, _index: int) -> None:
        mode = self.voice_mode()
        intent_mode = mode == "intent"
        for w in self._intent_widgets:
            w.setVisible(intent_mode)
        self._intent_preview_area.setVisible(
            intent_mode and self._pending_intent_preview is not None)
        if intent_mode:
            self._refresh_intents()
        # Workflow presets for the Billy modes (explicit, never inferred).
        if mode in ("ask_billy", "edit_billy"):
            from logosforge.voice.billy_bridge import (
                OP_ASK, OP_REWRITE_SELECTION)
            preset = OP_ASK if mode == "ask_billy" else OP_REWRITE_SELECTION
            idx = self._billy_op_combo.findData(preset)
            if idx >= 0:
                self._billy_op_combo.setCurrentIndex(idx)
        self._sync_target_subcontrols(self._build_context())
        self._update_room_label()

    def _refresh_intents(self) -> None:
        ctx = self._build_context()
        if ctx is None:
            return
        from logosforge.voice.intent_router import (
            get_available_voice_intents)
        keep = self._intent_combo.currentData()
        self._intent_combo.blockSignals(True)
        self._intent_combo.clear()
        for intent in get_available_voice_intents(ctx):
            self._intent_combo.addItem(intent.label, intent.id)
            i = self._intent_combo.count() - 1
            item = self._intent_combo.model().item(i)
            if not intent.enabled:
                item.setEnabled(False)
                item.setToolTip(intent.reason_if_disabled)
        idx = self._intent_combo.findData(keep)
        self._intent_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self._intent_combo.blockSignals(False)
        self._on_intent_changed(self._intent_combo.currentIndex())

    def _on_intent_changed(self, _index: int) -> None:
        from logosforge.voice.intent_router import (
            I_GN_PANEL_FIELD, I_INSERT_CLEANED)
        tid = self._intent_combo.currentData()
        self._gn_field_combo.setVisible(
            self.voice_mode() == "intent" and tid == I_GN_PANEL_FIELD)
        # The commit-target combo doubles as the destination for
        # "insert cleaned transcript".
        self._target_combo.setEnabled(
            tid == I_INSERT_CLEANED or self.voice_mode() == "dictation"
            or bool(self._preview.toPlainText().strip()))

    def _intent_source_text(self) -> tuple[str, list[str]]:
        """Checked segments (visible order) → current row → preview text."""
        ids = self._checked_entry_ids()
        if ids:
            return self._history.concat_text(ids), ids
        entry = self._current_entry()
        if entry is not None and self._history.committable(entry):
            return entry.text, [entry.id]
        return self._preview.toPlainText().strip(), []

    def _on_intent_preview(self) -> None:
        ctx = self._build_context()
        if ctx is None:
            return
        from logosforge.voice.intent_router import build_intent_preview
        text, source_ids = self._intent_source_text()
        intent_id = self._intent_combo.currentData()
        preview = build_intent_preview(
            intent_id, text, ctx,
            commit_target_id=self._selected_target_id(),
            source_segment_ids=source_ids)
        self._pending_intent_preview = preview
        self._queue.add_intent(preview)
        self._room_step("choosing_target")
        self._refresh_queue_ui()
        if not preview.can_apply:
            self._intent_preview_area.setVisible(True)
            self._intent_preview_area.setPlainText(preview.reason_if_blocked)
            self._intent_apply_btn.setEnabled(False)
            self._status_label.setText(f"Voice: {preview.reason_if_blocked}")
            return
        parts = [f"Target: {preview.target_summary}",
                 f"Risk: {preview.risk_level}"]
        if preview.created_note_preview:
            parts.append("— NOTE PREVIEW —\n"
                         f"{preview.created_note_preview['title']}\n"
                         f"{preview.created_note_preview['content']}")
        elif preview.created_psyke_entry_preview:
            data = preview.created_psyke_entry_preview
            parts.append("— PSYKE ENTRY PREVIEW —\n"
                         f"[{data['entry_type']}] {data['name']}\n"
                         f"{data['notes']}")
        else:
            if preview.before_text is not None:
                parts.append(f"— BEFORE —\n{preview.before_text}")
            parts.append(f"— AFTER —\n{preview.after_text or ''}")
        self._intent_preview_area.setVisible(True)
        self._intent_preview_area.setPlainText("\n\n".join(parts))
        self._intent_apply_btn.setEnabled(True)
        self._status_label.setText(
            "Voice: preview ready — review, then Apply")

    def _on_intent_apply(self) -> None:
        preview = self._pending_intent_preview
        ctx = self._build_context()
        if preview is None or ctx is None:
            self._status_label.setText("Voice: build a preview first")
            return
        from logosforge.voice.intent_router import (
            I_CLEANUP, apply_intent_preview)
        self._room_to("applying")
        ok, msg, op = apply_intent_preview(preview, ctx)
        self._status_label.setText(f"Voice: {msg}")
        if not ok:
            self._intent_apply_btn.setEnabled(False)
            from logosforge.voice.room import Q_STALE
            self._queue_sync(preview, Q_STALE)
            return
        self._room_to("applied")
        from logosforge.voice.room import Q_APPLIED
        self._queue_sync(preview, Q_APPLIED, op)
        if preview.intent_type == I_CLEANUP:
            # Transcript-only: update the source segments / live preview.
            if preview.source_segment_ids:
                for eid in preview.source_segment_ids:
                    self._history.edit(eid, preview.after_text or "")
            else:
                self._preview.setPlainText(preview.after_text or "")
        else:
            if op is not None:
                self._history.last_commit_op = op
            if preview.source_segment_ids:
                self._history.mark_committed(preview.source_segment_ids,
                                             preview.intent_type,
                                             op.id if op else "")
            if self._on_data_changed is not None:
                self._on_data_changed()   # dirty only after real mutation
        self._pending_intent_preview = None
        self._intent_apply_btn.setEnabled(False)
        self._refresh_history_ui()

    def _on_intent_cancel(self) -> None:
        from logosforge.voice.intent_router import cancel_voice_intent
        if self._pending_intent_preview is not None:
            from logosforge.voice.room import Q_CANCELLED
            self._queue_sync(self._pending_intent_preview, Q_CANCELLED)
        cancel_voice_intent(self._pending_intent_preview)
        self._pending_intent_preview = None
        self._intent_apply_btn.setEnabled(False)
        self._intent_preview_area.clear()
        self._intent_preview_area.setVisible(False)
        self._status_label.setText("Voice: intent preview cancelled")

    # -- Phase 6: Dexter's Room shell (state + queue + summary) ---------------
    def _room_to(self, state: str) -> None:
        self._room.to(state)              # invalid transitions are no-ops
        self._update_room_label()

    def _room_step(self, state: str) -> None:
        """Reach *state*, hopping through ``ready`` when needed (e.g. the
        user works from history without ever starting the microphone)."""
        if not self._room.can(state):
            self._room.to("ready")
        self._room_to(state)

    def _update_room_label(self) -> None:
        from logosforge.voice.room import (build_voice_room_context,
                                             context_summary_line)
        ctx = self._build_context()
        line = f"Dexter's Room (Alpha) · {self._room.state}"
        if ctx is not None:
            room = build_voice_room_context(ctx, self._history, self._queue)
            line += f" · {context_summary_line(room)}"
        self._room_label.setText(line)

    def _refresh_queue_ui(self) -> None:
        self._queue_list.clear()
        for item in self._queue.items:
            row = QListWidgetItem(f"[{item.status}] {item.kind}: {item.label}")
            row.setData(Qt.ItemDataRole.UserRole, item.id)
            if item.reason:
                row.setToolTip(item.reason)
            self._queue_list.addItem(row)
        self._update_room_label()

    def _queue_sync(self, payload, status: str, op=None) -> None:
        for item in self._queue.items:
            if item.payload is payload:
                item.status = status
                if op is not None:
                    item.operation_id = getattr(op, "id", "")
        self._refresh_queue_ui()

    def _on_queue_activate(self, row) -> None:
        from logosforge.voice.room import Q_READY
        item = self._queue.get(row.data(Qt.ItemDataRole.UserRole))
        if item is None or item.status != Q_READY:
            self._status_label.setText(
                "Voice: that proposal can no longer be applied"
                if item is not None else "Voice: proposal not found")
            return
        if item.kind == "billy":
            self._pending_billy_proposal = item.payload
            self._billy_apply_btn.setEnabled(True)
            self._status_label.setText("Voice: Billy proposal re-activated")
        else:
            self._pending_intent_preview = item.payload
            self._intent_apply_btn.setEnabled(True)
            self._status_label.setText("Voice: intent preview re-activated")

    def _on_pause(self) -> None:
        self.stop()                       # safe stop; history/queue kept
        self._room_to("ready")
        self._status_label.setText(
            "Voice: paused — session, history and proposals kept")

    # -- Phase 8: Voice Setup integration --------------------------------------
    def _apply_setup_gate(self) -> None:
        """Start is enabled only when the selected backend is ready; an
        invalid setup shows the Open-Voice-Setup message instead."""
        from logosforge.voice import setup as vsetup
        try:
            profile = vsetup.build_backend_profile(self._load_settings())
        except Exception:
            return
        listening = self._status in (VoiceStatus.LISTENING,
                                     VoiceStatus.PROCESSING)
        self._start_btn.setEnabled(profile.ready and not listening)
        self._start_btn.setToolTip(
            "" if profile.ready else vsetup.SETUP_REQUIRED_MESSAGE)
        if not profile.ready:
            self._status_label.setText(vsetup.SETUP_REQUIRED_MESSAGE)

    def _on_setup_open(self) -> None:
        if self._setup_dialog is None:
            from logosforge.ui.voice_setup_dialog import VoiceSetupDialog
            self._setup_dialog = VoiceSetupDialog(
                settings_get=self._settings_get,
                settings_set=self._settings_set, parent=self.window())
        else:
            self._setup_dialog.refresh()
        self._setup_dialog.show()
        self._setup_dialog.raise_()

    # -- Phase 5: Billy Voice Bridge ------------------------------------------
    def _refresh_billy_ops(self) -> None:
        ctx = self._build_context()
        if ctx is None:
            return
        from logosforge.voice.billy_bridge import (
            get_available_billy_operations)
        keep = self._billy_op_combo.currentData()
        self._billy_op_combo.blockSignals(True)
        self._billy_op_combo.clear()
        for op_id, label, enabled, reason in \
                get_available_billy_operations(ctx):
            self._billy_op_combo.addItem(label, op_id)
            i = self._billy_op_combo.count() - 1
            item = self._billy_op_combo.model().item(i)
            if not enabled:
                item.setEnabled(False)
                item.setToolTip(reason)
        idx = self._billy_op_combo.findData(keep)
        self._billy_op_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self._billy_op_combo.blockSignals(False)
        from logosforge.voice.billy_bridge import BILLY_UNCONFIGURED
        has_billy = getattr(ctx, "ai_complete", None) is not None
        self._billy_generate_btn.setEnabled(has_billy)
        self._billy_generate_btn.setToolTip(
            "" if has_billy else BILLY_UNCONFIGURED)

    def _on_billy_generate(self) -> None:
        ctx = self._build_context()
        if ctx is None:
            return
        from logosforge.voice.billy_bridge import request_billy_proposal
        text, source_ids = self._intent_source_text()
        self._room_step("sending_to_billy")
        proposal = request_billy_proposal(
            self._billy_op_combo.currentData(), text, ctx,
            source_segment_ids=source_ids)
        self._pending_billy_proposal = proposal
        self._queue.add_billy(proposal)
        self._room_to("proposal_ready" if proposal.can_apply
                      else "transcript_ready")
        self._refresh_queue_ui()
        for eid in source_ids:            # history: text-only Billy tracking
            entry = self._history.get(eid)
            if entry is not None:
                entry.sent_to_billy = True
                entry.billy_proposal_id = proposal.id
                entry.billy_state = "proposed"
        if proposal.reason_if_blocked:
            self._billy_preview_area.setVisible(True)
            self._billy_preview_area.setPlainText(proposal.reason_if_blocked)
            self._billy_apply_btn.setEnabled(False)
            self._status_label.setText(
                f"Voice: {proposal.reason_if_blocked}")
            return
        parts = [f"Target: {proposal.target_summary}"]
        if proposal.proposal_type == "chat_only":
            parts.append(f"— BILLY —\n{proposal.response_text}")
        elif proposal.note_preview:
            parts.append("— NOTE PREVIEW —\n"
                         f"{proposal.note_preview['title']}\n"
                         f"{proposal.note_preview['content']}")
        elif proposal.psyke_preview:
            data = proposal.psyke_preview
            parts.append("— PSYKE ENTRY PREVIEW —\n"
                         f"[{data['entry_type']}] {data['name']}\n"
                         f"{data['notes']}")
        else:
            if proposal.before_text is not None:
                parts.append(f"— BEFORE —\n{proposal.before_text}")
            parts.append(f"— AFTER —\n{proposal.after_text or ''}")
        self._billy_preview_area.setVisible(True)
        self._billy_preview_area.setPlainText("\n\n".join(parts))
        self._billy_apply_btn.setEnabled(proposal.can_apply)
        self._status_label.setText(
            "Voice: Billy proposal ready — review, then Apply"
            if proposal.can_apply else "Voice: Billy answered (chat only)")
        self._refresh_history_ui()

    def _on_billy_apply(self) -> None:
        proposal = self._pending_billy_proposal
        ctx = self._build_context()
        if proposal is None or ctx is None:
            self._status_label.setText("Voice: generate a proposal first")
            return
        from logosforge.voice.billy_bridge import apply_billy_voice_proposal
        self._room_to("applying")
        ok, msg, op = apply_billy_voice_proposal(proposal, ctx)
        self._status_label.setText(f"Voice: {msg}")
        if not ok:
            self._billy_apply_btn.setEnabled(False)
            from logosforge.voice.room import Q_STALE
            self._queue_sync(proposal, Q_STALE)
            self._room_to("proposal_ready")
            return
        self._room_to("applied")
        from logosforge.voice.room import Q_APPLIED
        self._queue_sync(proposal, Q_APPLIED, op)
        if op is not None:
            self._history.last_commit_op = op
        for eid in proposal.source_segment_ids:
            entry = self._history.get(eid)
            if entry is not None:
                entry.billy_state = "applied"
        if proposal.source_segment_ids:
            self._history.mark_committed(proposal.source_segment_ids,
                                         proposal.operation,
                                         op.id if op is not None else "")
        if self._on_data_changed is not None:
            self._on_data_changed()       # dirty only after real mutation
        self._pending_billy_proposal = None
        self._billy_apply_btn.setEnabled(False)
        self._refresh_history_ui()

    def _on_billy_cancel(self) -> None:
        from logosforge.voice.billy_bridge import (
            cancel_billy_voice_proposal)
        proposal = self._pending_billy_proposal
        cancel_billy_voice_proposal(proposal)
        if proposal is not None:
            from logosforge.voice.room import Q_CANCELLED
            self._queue_sync(proposal, Q_CANCELLED)
        if proposal is not None:
            for eid in proposal.source_segment_ids:
                entry = self._history.get(eid)
                if entry is not None and entry.billy_state == "proposed":
                    entry.billy_state = "cancelled"
        self._pending_billy_proposal = None
        self._billy_apply_btn.setEnabled(False)
        self._billy_preview_area.clear()
        self._billy_preview_area.setVisible(False)
        self._status_label.setText("Voice: Billy proposal cancelled")
        self._refresh_history_ui()

    def _on_billy_copy(self) -> None:
        from PySide6.QtWidgets import QApplication
        proposal = self._pending_billy_proposal
        text = (proposal.response_text if proposal is not None
                else self._billy_preview_area.toPlainText())
        QApplication.clipboard().setText(text or "")
        self._status_label.setText("Voice: Billy proposal copied")

    # -- Phase 7: project voice glossary corrections --------------------------
    def _glossary_settings(self):
        get = self._settings_get
        if get is None:
            from logosforge.settings import get_manager
            get = get_manager().get
        return {
            "enabled": bool(get("enable_voice_glossary")),
            "punctuation": bool(get("voice_spoken_punctuation")),
            "fuzzy": bool(get("voice_fuzzy_suggestions")),
            "auto_exact": bool(get("voice_auto_apply_exact")),
            "auto_punct": bool(get("voice_auto_apply_punctuation")),
        }

    def _generate_corrections(self, entry, ctx) -> None:
        """Suggestions after transcription (read-only; transcript-level)."""
        if ctx is None:
            return
        cfg = self._glossary_settings()
        if not cfg["enabled"]:
            return
        from logosforge.voice import glossary as vg
        try:
            suggestions = vg.suggest_transcript_corrections(
                ctx.db, ctx.project_id, entry.text,
                spoken_punctuation=cfg["punctuation"], fuzzy=cfg["fuzzy"])
        except Exception:
            return
        # Explicitly-enabled auto-apply classes (Alpha default: OFF).
        auto = [s for s in suggestions
                if (cfg["auto_exact"] and s.source in (
                    "misrecognition", "spoken_form", "canonical_case"))
                or (cfg["auto_punct"] and s.source == "punctuation")]
        if auto:
            new_text = vg.apply_selected_corrections(entry.text, auto)
            self._history.apply_corrections(entry.id, new_text)
            # Auto-apply silently mutates the transcript — tell the user it
            # happened (and that the changes are reviewable in the list).
            self._notice.emit(
                f"Applied {len(auto)} glossary auto-correction(s) — "
                "review them in the segment list.")
            suggestions = vg.suggest_transcript_corrections(
                ctx.db, ctx.project_id, entry.text,
                spoken_punctuation=cfg["punctuation"], fuzzy=cfg["fuzzy"])
        entry.corrections = [s for s in suggestions if not s.applied]

    def _refresh_corrections_ui(self) -> None:
        entry = self._current_entry()
        self._correction_list.clear()
        if entry is None or not entry.corrections:
            self._glossary_info.setText("")
            self._correction_list.setVisible(False)
            return
        count = len(entry.corrections)
        self._glossary_info.setText(
            f"{count} glossary suggestion(s) for the selected segment")
        for suggestion in entry.corrections:
            item = QListWidgetItem(
                f"{suggestion.original_text} → "
                f"{suggestion.replacement_text!r}"
                if suggestion.source == "punctuation" else
                f"{suggestion.original_text} → {suggestion.replacement_text}")
            item.setToolTip(suggestion.reason)
            item.setData(Qt.ItemDataRole.UserRole, suggestion.id)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked)
            self._correction_list.addItem(item)
        self._correction_list.setVisible(True)

    def _on_corrections_apply(self) -> None:
        entry = self._current_entry()
        ctx = self._build_context()
        if entry is None or not entry.corrections:
            self._status_label.setText("Voice: no suggestions for this "
                                       "segment")
            return
        from logosforge.voice import glossary as vg
        if ctx is not None and                 entry.project_id_at_capture != ctx.project_id:
            self._status_label.setText(vg.PROJECT_MISMATCH_CORRECTIONS)
            return
        checked_ids = set()
        for i in range(self._correction_list.count()):
            item = self._correction_list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                checked_ids.add(item.data(Qt.ItemDataRole.UserRole))
        selected = [s for s in entry.corrections if s.id in checked_ids]
        if not selected:
            self._status_label.setText("Voice: no suggestions selected")
            return
        new_text = vg.apply_selected_corrections(entry.text, selected)
        self._history.apply_corrections(entry.id, new_text)
        entry.corrections = [s for s in entry.corrections
                             if s.id not in checked_ids]
        if self._editing_entry_id == entry.id:
            self._preview.setPlainText(entry.text)
        self._status_label.setText(
            f"Voice: {len(selected)} correction(s) applied to the "
            "transcript")
        self._refresh_history_ui()
        self._refresh_corrections_ui()

    def _on_corrections_reject(self) -> None:
        entry = self._current_entry()
        if entry is not None and entry.corrections:
            entry.corrections = []
            self._status_label.setText("Voice: suggestions rejected")
        self._refresh_history_ui()
        self._refresh_corrections_ui()

    def _on_glossary_learn(self) -> None:
        entry = self._current_entry()
        ctx = self._build_context()
        if entry is None or ctx is None:
            self._status_label.setText("Voice: select a segment first")
            return
        from logosforge.voice import glossary as vg
        pairs = vg.diff_correction_pairs(entry.original_text, entry.text)
        if not pairs:
            self._status_label.setText(
                "Voice: edit the segment first — no correction pair found")
            return
        pairs = pairs[:3]
        from logosforge.ui import safe_dialogs
        listing = "\n".join(f"{a} → {b}" for a, b in pairs)
        if not safe_dialogs.question(
                self, "Remember correction",
                "Remember for this project?\n\n" + listing):
            return
        for original, corrected in pairs:
            vg.learn_correction(ctx.db, ctx.project_id, original, corrected)
        self._status_label.setText(
            f"Voice: {len(pairs)} correction(s) learned for this project")

    def _on_glossary_open(self) -> None:
        ctx = self._build_context()
        if ctx is None:
            self._status_label.setText("Voice: glossary needs an open "
                                       "project")
            return
        if self._glossary_dialog is None:
            from logosforge.ui.voice_glossary_dialog import (
                VoiceGlossaryDialog)
            self._glossary_dialog = VoiceGlossaryDialog(
                ctx.db, ctx.project_id, parent=self.window())
        else:
            self._glossary_dialog.set_project(ctx.project_id)
        self._glossary_dialog.show()
        self._glossary_dialog.raise_()

    def note_project_switched(self, new_project_id: int) -> None:
        """Project changed: freeze (don't lose) the visible history — every
        commit re-validates per-entry project ids, so stale segments can
        never land in the new project."""
        self._history.mark_session_stale()
        # Pending intent previews / Billy proposals are project-bound:
        # invalidate them on switch.
        self._pending_intent_preview = None
        self._intent_apply_btn.setEnabled(False)
        self._intent_preview_area.clear()
        self._pending_billy_proposal = None
        self._billy_apply_btn.setEnabled(False)
        self._billy_preview_area.clear()
        # Queue: proposals from the previous project become stale.
        self._queue.on_project_switch(new_project_id)
        self._refresh_queue_ui()
        self._room_to("ready")
        if self._glossary_dialog is not None:
            self._glossary_dialog.set_project(new_project_id)
        self._refresh_corrections_ui()
        if any(e.status in ("pending", "edited")
               for e in self._history.entries):
            self._status_label.setText(
                "Voice: project changed — transcript history is from "
                "another project")
        self._refresh_history_ui()

    def _commit_selected(self, entry_ids: list[str]) -> bool:
        text = self._history.concat_text(entry_ids)
        if not text:
            self._status_label.setText("Voice: selected segments are empty")
            return False
        ctx = self._build_context()
        from logosforge.voice.commit_router import (
            T_CURSOR, commit_transcript_op)
        target_id = self._selected_target_id()
        if ctx is None:
            ok = self._commit.insert_as_plain_text(text)
            if ok:
                self._history.mark_committed(entry_ids, T_CURSOR)
                self._status_label.setText("Voice: committed to editor")
            else:
                self._status_label.setText(
                    "Voice: no active editor — click into the editor, "
                    "then Commit")
            self._refresh_history_ui()
            return ok
        ok_p, msg_p = self._history.check_same_project(entry_ids,
                                                       ctx.project_id)
        if not ok_p:
            self._status_label.setText(msg_p)
            return False
        ok, msg, op = commit_transcript_op(text, target_id, ctx)
        self._status_label.setText(
            msg or ("Voice: transcript committed" if ok
                    else "Voice: commit failed"))
        if ok:
            self._history.last_commit_op = op
            self._history.mark_committed(entry_ids, target_id,
                                         op.id if op is not None else "")
            if self._on_data_changed is not None:
                self._on_data_changed()
        self._refresh_history_ui()
        return ok

    def stop_if_active(self) -> None:
        """Hide/close policy (Alpha): stop a live session safely, keep the
        transcript preview. Never silently discards or auto-commits."""
        if self._controller is not None and self._controller.status in (
                VoiceStatus.LISTENING, VoiceStatus.PROCESSING):
            self.stop()

    def start(self) -> None:
        # Never create an overlapping session: if a controller is already
        # listening, keep it; otherwise stop/cleanup the previous one before
        # building a fresh controller (prevents an orphaned open mic stream).
        if self._controller is not None and self._controller.status in (
                VoiceStatus.LISTENING, VoiceStatus.PROCESSING):
            return
        self.stop_session()
        self._room_to("checking_backend")
        ok, msg = self._ensure_controller()
        if not ok:
            self._room_to("error")
            self._apply_status(VoiceStatus.DISABLED)
            self._status_label.setText(msg or SETUP_MESSAGE)
            return
        self._room_to("ready")
        if self._controller.start_voice_session():
            self._apply_status(VoiceStatus.LISTENING)
            # One active history session at a time (no secrets — model label
            # is just the path tail). Existing entries are kept.
            settings = self._load_settings()
            ctx = self._build_context()
            import os
            self._history.start_session(
                getattr(ctx, "project_id", 0) if ctx else 0,
                backend=settings.backend_mode,
                model_label=os.path.basename(settings.model_path or ""),
                language=settings.language or "")

    def stop(self) -> None:
        if self._controller is not None:
            self._controller.stop_voice_session()
        if hasattr(self, "_room"):
            self._room_to("stopped")
        self._apply_status(VoiceStatus.OFF)

    def stop_session(self) -> None:
        """Safe stop for app close / project switch (no UI assumptions)."""
        try:
            if self._controller is not None:
                self._controller.stop_voice_session()
        except Exception:
            pass

    def commit(self) -> bool:
        # Checked history segments are the explicit selection — they commit
        # together (in visible order) through the router.
        checked = self._checked_entry_ids()
        if checked:
            return self._commit_selected(checked)
        text = self._preview.toPlainText()
        if not text.strip():
            self._status_label.setText("Voice: nothing to commit")
            return False
        ctx = self._build_context()
        if ctx is None:
            # The original MVP path: plain text at the active editor's cursor.
            from logosforge.voice.commit_router import T_CURSOR
            ok = self._commit.insert_as_plain_text(text)
            if ok:
                self._status_label.setText("Voice: committed to editor")
                self._mark_preview_entries_committed(T_CURSOR, "")
            else:
                self._status_label.setText(
                    "Voice: no active editor — click into the editor, "
                    "then Commit")
            return ok
        from logosforge.voice.commit_router import commit_transcript_op
        target_id = self._selected_target_id()
        ok, message, op = commit_transcript_op(text, target_id, ctx)
        self._status_label.setText(
            message or ("Voice: transcript committed"
                        if ok else "Voice: commit failed"))
        if ok:
            self._history.last_commit_op = op
            self._mark_preview_entries_committed(
                target_id, op.id if op is not None else "")
            if self._on_data_changed is not None:
                self._on_data_changed()   # project dirty only AFTER commit
        return ok

    def _mark_preview_entries_committed(self, target_id: str,
                                        op_id: str) -> None:
        """A preview commit consumed the live dictation: mark the segments
        that fed it (all still-committable entries) as committed."""
        ids = [e.id for e in self._history.entries
               if self._history.committable(e)]
        if ids:
            self._history.mark_committed(ids, target_id, op_id)
        self._refresh_history_ui()

    def clear_preview(self) -> None:
        self._preview.clear()
        self._transcript_project_id = None
        self._editing_entry_id = None
        self._refresh_targets()

    # -- slots (UI thread) ---------------------------------------------------
    def _apply_status_str(self, status_value: str) -> None:
        try:
            self._apply_status(VoiceStatus(status_value))
        except ValueError:
            pass

    def _apply_status(self, status: VoiceStatus) -> None:
        self._status = status
        self._status_label.setText(_STATUS_TEXT.get(status, "Voice"))
        # Live level meter shows only while actively capturing.
        listening = status == VoiceStatus.LISTENING
        self._level_meter.setVisible(listening)
        if not listening:
            self._level_meter.setValue(0)
            self._level_quiet = None
        # Show elapsed time while transcribing so PROCESSING isn't a black box.
        if status == VoiceStatus.PROCESSING:
            self._proc_start = time.monotonic()
            self._proc_timer.start()
            self._tick_processing()
        else:
            self._proc_timer.stop()
        # Mirror the controller status into the room state machine.
        room_state = {
            VoiceStatus.LISTENING: "listening",
            VoiceStatus.PROCESSING: "transcribing",
            VoiceStatus.TRANSCRIPT_READY: "transcript_ready",
            VoiceStatus.ERROR: "error",
        }.get(status)
        if room_state is not None and hasattr(self, "_room"):
            self._room_to(room_state)
        self._refresh_buttons()

    def _tick_processing(self) -> None:
        elapsed = time.monotonic() - self._proc_start
        self._status_label.setText(f"Voice: transcribing… {elapsed:.0f}s")

    def _apply_level(self, rms: float) -> None:
        """Render the live mic level (int16 RMS). Speech threshold is 500;
        speech typically runs ~2000-6000, so map ~5000 -> full scale."""
        self._level_meter.setValue(max(0, min(100, int(rms / 50))))
        quiet = rms < 500
        if quiet != self._level_quiet:
            self._level_quiet = quiet
            colour = "#b45309" if quiet else "#16a34a"   # amber too-quiet / green
            self._level_meter.setStyleSheet(
                "QProgressBar{border:1px solid #334155;border-radius:3px;"
                "background:#1e293b;}"
                f"QProgressBar::chunk{{background:{colour};border-radius:2px;}}")

    def _apply_final_text(self, text: str) -> None:
        if not text:
            return
        existing = self._preview.toPlainText()
        if not existing.strip():
            # Capture the project this transcript belongs to: a later project
            # switch blocks the commit (never into the wrong project).
            ctx = None
            if self._context_provider is not None:
                try:
                    ctx = self._context_provider()
                except Exception:
                    ctx = None
            self._transcript_project_id = (
                getattr(ctx, "project_id", None) if ctx is not None else None)
        self._preview.setPlainText((existing + " " + text).strip()
                                   if existing else text)
        if self._auto_commit.isChecked():
            self.commit()

    def _set_controls_enabled(self, enabled: bool) -> None:
        for w in (self._start_btn, self._stop_btn, self._commit_btn,
                  self._clear_btn, self._auto_commit):
            w.setEnabled(enabled)

    def _refresh_buttons(self) -> None:
        listening = self._status in (VoiceStatus.LISTENING,
                                     VoiceStatus.PROCESSING)
        has_text = bool(self._preview.toPlainText().strip())
        self._start_btn.setEnabled(not listening)
        self._stop_btn.setEnabled(listening)
        self._commit_btn.setEnabled(has_text)
        self._clear_btn.setEnabled(bool(self._preview.toPlainText()))
        self._copy_btn.setEnabled(has_text)
        if has_text != self._had_transcript:
            self._had_transcript = has_text
            self._refresh_targets()       # empty <-> ready transition only


class VoiceDictationWindow(QDialog):
    """Floating, modeless, resizable host for the Voice Dictation panel.

    Window-safety rules (the ones that keep this clear of the old
    standalone-Pages fullscreen-minimize bug):

    * always **parented to the main window** — never a parentless top-level
      window, no extra window flags, no ``Qt.Tool``;
    * **modeless** (shown with ``show()``, never ``exec()``) — writing in the
      main editor continues while it is open;
    * one instance, toggled show/hide; the title-bar close button, the
      panel's **Hide** button and **Esc** all *hide* it (state preserved —
      reopening shows the same transcript preview);
    * hiding while recording stops the session safely first and keeps the
      preview (never silently discards, never auto-commits);
    * never calls ``showMinimized``/``hide``/``close`` on the main window and
      never auto-shows at launch or auto-starts recording.
    """

    def __init__(self, panel: VoicePanel, parent: QWidget | None = None
                 ) -> None:
        super().__init__(parent)
        self.setObjectName("voiceDictationWindow")
        self.setWindowTitle("Dexter's Room — local voice (Alpha)")
        self.setModal(False)
        self.setSizeGripEnabled(True)        # resizable, with a visible grip
        # Open wide enough that the dense control rows (history actions,
        # transcript controls) are fully readable without a manual resize.
        self.setMinimumSize(620, 420)
        self.resize(820, 620)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        self._panel = panel
        panel.setParent(self)
        panel.setVisible(True)               # visibility is window-level now
        layout.addWidget(panel)
        panel.hide_requested.connect(self.hide_safely)

    @property
    def panel(self) -> VoicePanel:
        return self._panel

    def toggle(self) -> None:
        """Single shared toggle for every entry point (menu / shortcut)."""
        if self.isVisible():
            self.hide_safely()
        else:
            self._panel.sync_enabled_state()
            self.show()
            self.raise_()

    def hide_safely(self) -> None:
        """Hide, stopping a live session first; transcript preview is kept."""
        self._panel.stop_if_active()
        self.hide()

    def reject(self) -> None:                # Esc while the window is focused
        self._panel.stop_if_active()
        super().reject()                     # modeless reject == hide

    def closeEvent(self, event) -> None:     # noqa: N802 (Qt signature)
        # Title-bar close hides (instance + transcript preserved, session
        # stopped safely) — it never destroys state or touches the parent.
        self._panel.stop_if_active()
        event.accept()
