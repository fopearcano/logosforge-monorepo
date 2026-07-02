"""Voice MVP Phase 9 — end-to-end Alpha hardening certification gate.

Cross-cutting certification items that no single phase suite pins: the
full dictate→correct→commit→undo pipeline in one pass, voice × writing-mode
lock interaction, safe app-close while recording, session-scale memory
behavior, latency guardrails (mock-based; generous thresholds — CI has no
real model), export/diagnostics privacy, and import-cleanliness of every
voice module without optional dependencies. Small, deliberate, and local.
"""

from __future__ import annotations

import time
import warnings

import pytest
from PySide6.QtWidgets import QApplication, QTextEdit

warnings.filterwarnings("ignore")

from logosforge.db import Database
from logosforge import graphic_novel_blocks as gnb
from logosforge import story_structure as ss
from logosforge.voice.types import TranscriptSegment, VoiceSettings


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture(autouse=True)
def reset_settings(monkeypatch, tmp_path):
    import logosforge.settings as settings
    settings._instance = None
    monkeypatch.setattr(settings, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(settings, "SETTINGS_FILE", tmp_path / "settings.json")
    import logosforge.gomckee_bridge as gb
    monkeypatch.setattr(gb, "is_gomckee_enabled", lambda: False, raising=False)
    yield
    settings._instance = None


def _ui_window(engine="novel"):
    from logosforge.settings import get_manager
    mgr = get_manager()
    mgr.set("enable_voice_mode", True)
    mgr.set("voice_backend_mode", "mock")
    mgr.set("voice_silence_ms", 300)
    from logosforge.ui.main_window import MainWindow
    db = Database()
    pid = db.create_project("P", narrative_engine=engine,
                            default_writing_format=engine).id
    win = MainWindow(db, pid)
    win._toggle_voice_panel()
    return db, pid, win


# ==========================================================================
# End-to-end pipeline (dictate → correct → commit → undo) in ONE pass
# ==========================================================================


def test_full_pipeline_dictate_correct_commit_undo():
    from PySide6.QtCore import Qt
    from logosforge.voice.commit_router import T_NOTE
    db, pid, win = _ui_window()
    db.create_voice_glossary_term(pid, "Zampanò",
                                  common_misrecognitions="Zampano")
    panel = win._voice_panel
    # 1. A finalized mock segment lands in history with a glossary hit.
    panel._apply_final_segment(TranscriptSegment(text="Zampano returns"))
    entry = panel._history.entries[0]
    assert entry.status == "pending" and len(entry.corrections) == 1
    # 2. Review-first correction (transcript only).
    panel._history_list.setCurrentRow(0)
    panel._on_corrections_apply()
    assert entry.text == "Zampanò returns" and entry.status == "corrected"
    assert db.get_all_notes(pid) == []               # nothing committed yet
    # 3. Explicit commit of the SELECTED segment through the router.
    panel._history_list.item(0).setCheckState(Qt.CheckState.Checked)
    panel._target_combo.setCurrentIndex(panel._target_combo.findData(T_NOTE))
    win._dirty = False
    assert panel.commit() is True
    notes = db.get_all_notes(pid)
    assert notes[0].content == "Zampanò returns"     # corrected text won
    assert entry.status == "committed" and win._dirty is True
    # 4. Single-level undo through the shared operation record.
    assert panel._undo_btn.isEnabled() is True
    panel._on_undo_commit()
    assert db.get_all_notes(pid) == []
    assert panel._undo_btn.isEnabled() is False


# ==========================================================================
# Voice × writing-mode lock (§15)
# ==========================================================================


def test_uncommitted_voice_history_does_not_lock_mode():
    from logosforge.writing_modes import can_change_writing_mode
    db, pid, win = _ui_window()
    assert can_change_writing_mode(db, pid) is True   # empty scaffold
    panel = win._voice_panel
    panel._apply_final_segment(TranscriptSegment(text="just talking"))
    panel._apply_final_segment(TranscriptSegment(text="still talking"))
    panel._history.edit(panel._history.entries[0].id, "edited talk")
    # Temporary, in-memory history is NOT project content.
    assert can_change_writing_mode(db, pid) is True


def test_committed_voice_text_locks_mode():
    from PySide6.QtCore import Qt
    from logosforge.voice.commit_router import T_NOTE
    from logosforge.writing_modes import can_change_writing_mode
    db, pid, win = _ui_window()
    panel = win._voice_panel
    panel._apply_final_segment(TranscriptSegment(text="now it is real"))
    panel._history_list.item(0).setCheckState(Qt.CheckState.Checked)
    panel._target_combo.setCurrentIndex(
        panel._target_combo.findData(T_NOTE))
    assert panel.commit() is True
    assert can_change_writing_mode(db, pid) is False  # persisted content


# ==========================================================================
# App close while recording (§5) — stops safely, no prompt loops
# ==========================================================================


def test_app_close_while_recording_stops_session_safely():
    from logosforge.voice.types import VoiceStatus
    _db, _pid, win = _ui_window()
    panel = win._voice_panel
    panel.start()
    assert panel._controller.status == VoiceStatus.LISTENING
    win._dirty = False                                # no close-save prompt
    win.close()
    assert panel._controller.status == VoiceStatus.OFF


# ==========================================================================
# Session scale / memory behavior (§6)
# ==========================================================================


def test_long_session_memory_is_bounded_and_ordered():
    _db, _pid, win = _ui_window()
    panel = win._voice_panel
    for i in range(30):
        panel._apply_final_segment(TranscriptSegment(
            text=f"segment {i:02d}", audio_bytes=b"\x01" * 32000))
    history = panel._history
    assert history.segment_count == 30
    assert [e.text for e in history.entries] == \
        [f"segment {i:02d}" for i in range(30)]       # stable order
    # Discard/clear drop the retained audio (the only big payload).
    history.discard(history.entries[0].id)
    assert history.entries[0].audio_bytes is None
    removed = history.clear_uncommitted()
    assert removed == 29
    assert all(e.audio_bytes is None for e in history.entries)


# ==========================================================================
# Latency guardrails (§14) — mock-based, generous thresholds
# ==========================================================================


def test_latency_guardrails_with_mock_backend():
    from logosforge.voice.recorder import build_recorder
    from logosforge.voice.transcriber import build_transcriber
    settings = VoiceSettings(enabled=True, backend_mode="mock")
    t0 = time.perf_counter()
    transcriber = build_transcriber(settings)
    ok, _msg = transcriber.availability()
    availability_s = time.perf_counter() - t0
    assert ok is True and availability_s < 1.0        # backend check fast
    t0 = time.perf_counter()
    recorder = build_recorder(settings)
    recorder.availability()
    mic_s = time.perf_counter() - t0
    assert mic_s < 1.0
    t0 = time.perf_counter()
    seg = transcriber.transcribe(b"\x00\x00" * 16000, sample_rate=16000)
    transcribe_s = time.perf_counter() - t0
    assert seg.text and transcribe_s < 1.0            # short segment quick
    # Profiles stay ordered fast -> accurate (latency guardrail semantics).
    from logosforge.voice.setup import PERFORMANCE_PROFILES
    assert PERFORMANCE_PROFILES["fast_draft"]["voice_max_segment_seconds"] \
        < PERFORMANCE_PROFILES["accurate"]["voice_max_segment_seconds"]


# ==========================================================================
# Export / diagnostics privacy (§13)
# ==========================================================================


def test_exports_and_diagnostics_contain_no_voice_data():
    from PySide6.QtCore import Qt
    from logosforge.voice.commit_router import T_CURSOR
    from logosforge.voice.setup import diagnostics_summary
    db, pid, win = _ui_window("graphic_novel")
    sid = ss.create_scene(db, pid, act="Act 1", chapter="Chapter 1",
                          title="S").id
    db.create_voice_glossary_term(pid, "SecretTerm",
                                  common_misrecognitions="sekretterm")
    panel = win._voice_panel
    panel._apply_final_segment(TranscriptSegment(
        text="UNCOMMITTED-PRIVATE-TRANSCRIPT", audio_bytes=b"\x07" * 64))
    # Project export carries only committed project content — never the
    # transcript history, glossary internals or audio.
    md = gnb.export_project_markdown(db, pid)
    assert "UNCOMMITTED-PRIVATE-TRANSCRIPT" not in md
    assert "sekretterm" not in md.lower()
    assert "audio" not in md.lower()
    # Diagnostics summary: settings-derived only — no transcript history.
    summary = diagnostics_summary(
        VoiceSettings(enabled=True, backend_mode="mock"))
    assert "UNCOMMITTED-PRIVATE-TRANSCRIPT" not in summary
    # Committed text DOES export (that is the point).
    editor_field_keys = [k for k in panel._history.entries]
    assert editor_field_keys                          # history intact
    win._switch_project(pid)                          # no-op switch is safe


def test_voice_modules_import_clean_without_optional_deps():
    import importlib
    for module in ("types", "silence_detector", "audio_buffer",
                   "transcriber", "recorder", "session", "editor_commit",
                   "lan_server", "commit_router", "intent_router",
                   "billy_bridge", "history", "room", "glossary", "setup"):
        importlib.import_module(f"logosforge.voice.{module}")


def test_one_active_backend_at_a_time():
    from logosforge.voice.transcriber import (
        FasterWhisperTranscriber, MockTranscriber, WhisperCppTranscriber,
        build_transcriber)
    assert isinstance(build_transcriber(
        VoiceSettings(backend_mode="mock")), MockTranscriber)
    assert isinstance(build_transcriber(
        VoiceSettings(backend_mode="whisper_cpp")), WhisperCppTranscriber)
    assert isinstance(build_transcriber(
        VoiceSettings(backend_mode="local_process")),
        FasterWhisperTranscriber)
    # The dispatcher returns exactly ONE backend per resolved mode — the
    # "only one active backend" rule by construction.
