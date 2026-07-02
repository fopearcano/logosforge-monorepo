"""Voice MVP Phase 3 — transcript history, correction, undo, retry, segments.

The local, session-only review layer: finalized segments land in a history
the user can edit (original kept), select, merge, split, retry (local
transcriber on in-memory audio only), discard, clear and commit through the
existing Voice Commit Router — plus a safe single-level "Undo last voice
commit" per target kind (cursor/document-revision guard, GN field previous
value, created Note/PSYKE deletion). Project safety is per-entry: segments
captured in another project can never commit into this one. Everything is
local; audio bytes live in memory only and are dropped on discard/clear.
"""

from __future__ import annotations

import warnings

import pytest
from PySide6.QtWidgets import QApplication, QTextEdit

warnings.filterwarnings("ignore")

from logosforge.db import Database
from logosforge import graphic_novel_blocks as gnb
from logosforge import graphic_novel_outline as gno
from logosforge import story_structure as ss
from logosforge.voice import history as vh
from logosforge.voice.commit_router import (
    T_CURSOR,
    T_GN_DIALOGUE,
    T_NOTE,
    T_PSYKE,
    VoiceCommitContext,
    can_undo,
    commit_transcript_op,
    undo_commit,
)
from logosforge.voice.editor_commit import EditorCommitTarget
from logosforge.voice.history import VoiceTranscriptHistory
from logosforge.voice.types import TranscriptSegment


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


def _seg(text, *, audio=None):
    return TranscriptSegment(text=text, audio_bytes=audio)


def _hist(*texts, project_id=1, audio=None):
    h = VoiceTranscriptHistory()
    h.start_session(project_id, backend="mock")
    entries = [h.add_final_segment(_seg(t, audio=audio),
                                   project_id=project_id,
                                   writing_mode="novel") for t in texts]
    return h, entries


def _editor_ctx(db, pid, mode="novel"):
    editor = QTextEdit()
    tgt = EditorCommitTarget()
    tgt.note_focus(editor)
    ctx = VoiceCommitContext(
        db=db, project_id=pid, writing_mode=mode, has_active_editor=True,
        insert_at_cursor=tgt.insert_as_plain_text,
        active_editor_getter=tgt.active_editor)
    return ctx, editor


# ==========================================================================
# 1-9  History model basics
# ==========================================================================


def test_new_session_creates_empty_history():
    h = VoiceTranscriptHistory()
    session = h.start_session(7, backend="mock", model_label="small")
    assert h.entries == []
    assert session.status == "active" and session.project_id == 7
    assert h.segment_count == 0 and h.committed_count == 0


def test_final_transcript_creates_pending_segment_with_capture_info():
    h, (entry,) = _hist("hello there", project_id=42)
    assert entry.status == vh.S_PENDING
    assert entry.project_id_at_capture == 42
    assert entry.writing_mode_at_capture == "novel"
    assert entry.session_id == h.session.id
    assert entry.original_text == "hello there"
    assert entry.source == "local_whisper"


def test_one_active_session_at_a_time():
    h = VoiceTranscriptHistory()
    first = h.start_session(1)
    second = h.start_session(1)
    assert first.status == "stopped" and first.stopped_at is not None
    assert second.status == "active"
    assert h.session is second


def test_edit_updates_text_status_and_keeps_original():
    h, (entry,) = _hist("orignal txt")
    assert h.edit(entry.id, "original text") is True
    assert entry.text == "original text"
    assert entry.original_text == "orignal txt"
    assert entry.status == vh.S_EDITED
    h.restore_original(entry.id)
    assert entry.text == "orignal txt" and entry.status == vh.S_PENDING


def test_empty_edited_segment_cannot_be_committed():
    h, (entry,) = _hist("words")
    h.edit(entry.id, "   ")
    assert h.committable(entry) is False
    assert h.concat_text([entry.id]) == ""


def test_discard_prevents_commit_and_drops_audio():
    h, (entry,) = _hist("bye", audio=b"\x00\x01")
    assert entry.audio_bytes is not None
    assert h.discard(entry.id) is True
    assert entry.status == vh.S_DISCARDED
    assert entry.audio_bytes is None
    assert h.committable(entry) is False
    assert h.concat_text([entry.id]) == ""


def test_clear_uncommitted_and_clear_finished():
    h, (a, b, c) = _hist("one", "two", "three")
    h.mark_committed([a.id], T_NOTE)
    h.discard(b.id)
    assert h.clear_uncommitted() == 1               # removes only "three"
    assert {e.id for e in h.entries} == {a.id, b.id}
    assert h.clear_finished() == 2                  # committed + discarded
    assert h.entries == []


def test_committed_segment_cannot_be_edited_or_discarded():
    h, (entry,) = _hist("done deal")
    h.mark_committed([entry.id], T_NOTE)
    assert h.edit(entry.id, "rewrite") is False
    assert h.discard(entry.id) is False
    assert entry.text == "done deal"


def test_clear_all_ends_session_and_drops_audio():
    h, (entry,) = _hist("x", audio=b"\xff")
    h.clear_all()
    assert h.entries == [] and h.session is None
    assert entry.audio_bytes is None


# ==========================================================================
# 10-15  Commit selected (through the router)
# ==========================================================================


def test_selected_segments_commit_in_visible_order_with_edited_text():
    db = Database()
    pid = db.create_project("N", narrative_engine="novel").id
    h, (a, b, c) = _hist("first", "second", "third", project_id=pid)
    h.edit(b.id, "SECOND-EDITED")
    text = h.concat_text([c.id, a.id, b.id])        # selection order ignored
    assert text == "first SECOND-EDITED third"      # visible order + edits
    ctx, editor = _editor_ctx(db, pid)
    ok, _msg, op = commit_transcript_op(text, T_CURSOR, ctx)
    assert ok is True
    assert editor.toPlainText() == "first SECOND-EDITED third"
    h.mark_committed([a.id, b.id, c.id], T_CURSOR, op.id)
    assert all(e.status == vh.S_COMMITTED for e in (a, b, c))
    assert all(e.committed_target == T_CURSOR for e in (a, b, c))
    assert all(e.commit_operation_id == op.id for e in (a, b, c))


def test_failed_commit_leaves_segments_pending():
    db = Database()
    pid = db.create_project("N", narrative_engine="novel").id
    h, (a,) = _hist("text", project_id=pid)
    ctx = VoiceCommitContext(db=db, project_id=pid, writing_mode="novel",
                             has_active_editor=False)     # cursor unavailable
    ok, _msg, op = commit_transcript_op(h.concat_text([a.id]), T_CURSOR, ctx)
    assert ok is False and op is None
    assert a.status == vh.S_PENDING                  # untouched


def test_mark_failed_records_error():
    h, (a,) = _hist("text")
    h.mark_failed(a.id, "boom")
    assert a.status == vh.S_FAILED and a.error == "boom"
    assert h.error_count == 1


# ==========================================================================
# 16-20  Project safety
# ==========================================================================


def test_cross_project_segments_block_commit():
    h = VoiceTranscriptHistory()
    h.start_session(1)
    a = h.add_final_segment(_seg("from project 1"), project_id=1,
                            writing_mode="novel")
    ok, msg = h.check_same_project([a.id], 2)        # now in project 2
    assert ok is False
    assert msg == ("This transcript was captured in another project. "
                   "Switch back or explicitly retarget.")
    assert h.check_same_project([a.id], 1) == (True, "")


def test_session_stale_after_project_switch():
    h, _entries = _hist("words", project_id=1)
    h.mark_session_stale()
    assert h.session.status == "stale"
    assert h.entries                                  # history kept, frozen


# ==========================================================================
# 21-25  Undo last voice commit
# ==========================================================================


def test_undo_cursor_commit_restores_editor():
    db = Database()
    pid = db.create_project("N", narrative_engine="novel").id
    ctx, editor = _editor_ctx(db, pid)
    editor.setPlainText("before ")
    cur = editor.textCursor()
    cur.movePosition(cur.MoveOperation.End)
    editor.setTextCursor(cur)
    ok, _msg, op = commit_transcript_op("VOICE TEXT", T_CURSOR, ctx)
    assert ok and "VOICE TEXT" in editor.toPlainText()
    assert can_undo(op, ctx) == (True, "")
    ok, msg = undo_commit(op, ctx)
    assert ok is True and "undone" in msg.lower()
    assert editor.toPlainText() == "before "


def test_undo_blocked_after_unrelated_edit():
    db = Database()
    pid = db.create_project("N", narrative_engine="novel").id
    ctx, editor = _editor_ctx(db, pid)
    _ok, _msg, op = commit_transcript_op("VOICE TEXT", T_CURSOR, ctx)
    editor.textCursor().insertText(" user typed more")   # unrelated edit
    ok, reason = can_undo(op, ctx)
    assert ok is False and "changed" in reason.lower()
    ok, _msg = undo_commit(op, ctx)
    assert ok is False
    assert "user typed more" in editor.toPlainText()     # nothing reverted


def test_undo_gn_field_restores_previous_value():
    db = Database()
    pid = db.create_project("G", narrative_engine="graphic_novel").id
    sid = ss.create_scene(db, pid, act="Act 1", chapter="Chapter 1",
                          title="S").id
    gno.add_page(db, sid); gno.add_panel(db, sid, 0)
    gno.set_panel_field(db, sid, 0, 0, "dialogue", "KEEP ME")
    ctx = VoiceCommitContext(db=db, project_id=pid,
                             writing_mode="graphic_novel",
                             gn_panel_ref=(sid, 0, 0))
    ok, _msg, op = commit_transcript_op("appended line", T_GN_DIALOGUE, ctx)
    assert ok is True
    panel = gnb.load_scene_script(db, sid).pages[0].panels[0]
    assert panel.dialogue == "KEEP ME\nappended line"
    ok, _msg = undo_commit(op, ctx)
    assert ok is True
    panel = gnb.load_scene_script(db, sid).pages[0].panels[0]
    assert panel.dialogue == "KEEP ME"                    # previous value back


def test_undo_note_and_psyke_delete_created_entries_only():
    db = Database()
    pid = db.create_project("N", narrative_engine="novel").id
    ctx = VoiceCommitContext(db=db, project_id=pid, writing_mode="novel")
    ok, _m, op_note = commit_transcript_op("a fleeting idea", T_NOTE, ctx)
    assert ok and len(db.get_all_notes(pid)) == 1
    assert undo_commit(op_note, ctx) == (True, "Voice commit undone.")
    assert db.get_all_notes(pid) == []
    ok, _m, op_psyke = commit_transcript_op("lore fragment", T_PSYKE, ctx)
    assert ok and len(db.get_all_psyke_entries(pid)) == 1
    assert undo_commit(op_psyke, ctx)[0] is True
    assert db.get_all_psyke_entries(pid) == []


def test_undo_note_blocked_if_note_changed():
    db = Database()
    pid = db.create_project("N", narrative_engine="novel").id
    ctx = VoiceCommitContext(db=db, project_id=pid, writing_mode="novel")
    _ok, _m, op = commit_transcript_op("original body", T_NOTE, ctx)
    note = db.get_all_notes(pid)[0]
    db.update_note(note.id, note.title, content="user edited this note")
    ok, reason = can_undo(op, ctx)
    assert ok is False and "changed" in reason.lower()
    assert len(db.get_all_notes(pid)) == 1               # nothing deleted


def test_undo_blocked_on_project_mismatch_and_none():
    db = Database()
    a = db.create_project("A", narrative_engine="novel").id
    b = db.create_project("B", narrative_engine="novel").id
    ctx_a = VoiceCommitContext(db=db, project_id=a, writing_mode="novel")
    _ok, _m, op = commit_transcript_op("note in A", T_NOTE, ctx_a)
    ctx_b = VoiceCommitContext(db=db, project_id=b, writing_mode="novel")
    ok, reason = can_undo(op, ctx_b)
    assert ok is False and "project" in reason.lower()
    assert can_undo(None, ctx_a) == (False, "Nothing to undo.")


# ==========================================================================
# 26-29  Retry transcription (local only)
# ==========================================================================


class _StubTranscriber:
    def __init__(self, text="", error=""):
        self._text, self._error = text, error
        self.calls = 0

    def transcribe(self, pcm, *, sample_rate, language=None):
        self.calls += 1
        return TranscriptSegment(text=self._text, error=self._error)


def test_retry_enabled_only_with_audio():
    h, (with_audio,) = _hist("rough words", audio=b"\x01\x02")
    assert h.can_retry(with_audio) == (True, "")
    h2, (no_audio,) = _hist("no audio kept")
    ok, reason = h2.can_retry(no_audio)
    assert ok is False and reason == "Audio segment no longer available."


def test_retry_replaces_text_keeps_original_local_only():
    h, (entry,) = _hist("mangled trnscrpt", audio=b"\x01\x02")
    stub = _StubTranscriber(text="clean transcript")
    ok, msg = h.retry_transcription(entry.id, stub)
    assert ok is True and stub.calls == 1            # local transcriber only
    assert entry.text == "clean transcript"
    assert entry.original_text == "mangled trnscrpt"  # provenance kept
    assert entry.status == vh.S_EDITED


def test_retry_failure_keeps_previous_transcript():
    h, (entry,) = _hist("keep me", audio=b"\x01")
    ok, _msg = h.retry_transcription(entry.id, _StubTranscriber(error="boom"))
    assert ok is False
    assert entry.text == "keep me"


# ==========================================================================
# 30-33  Merge / split
# ==========================================================================


def test_merge_adjacent_uncommitted_segments():
    h, (a, b, c) = _hist("one", "two", "three")
    merged = h.merge([a.id, b.id])
    assert merged is not None
    assert merged.text == "one two"
    assert merged.merged_from == [a.id, b.id]
    assert [e.text for e in h.entries] == ["one two", "three"]


def test_merge_rejects_committed_and_non_adjacent():
    h, (a, b, c) = _hist("one", "two", "three")
    h.mark_committed([b.id], T_NOTE)
    assert h.merge([a.id, b.id]) is None             # committed member
    assert h.merge([a.id, c.id]) is None             # not adjacent
    assert [e.text for e in h.entries] == ["one", "two", "three"]


def test_split_uncommitted_segment_into_two():
    h, (a,) = _hist("first half second half")
    result = h.split(a.id, len("first half "))
    assert result is not None
    first, second = result
    assert first.text == "first half" and second.text == "second half"
    assert first.split_from == a.id and second.split_from == a.id
    assert [e.text for e in h.entries] == ["first half", "second half"]


def test_split_rejects_empty_halves_and_committed():
    h, (a,) = _hist("words")
    assert h.split(a.id, 0) is None
    assert h.split(a.id, len("words")) is None
    h.mark_committed([a.id], T_NOTE)
    assert h.split(a.id, 2) is None


# ==========================================================================
# 34-39  Panel UI integration
# ==========================================================================


def _ui_window(engine="novel"):
    from logosforge.settings import get_manager
    mgr = get_manager()
    mgr.set("enable_voice_mode", True)
    mgr.set("voice_backend_mode", "mock")
    from logosforge.ui.main_window import MainWindow
    db = Database()
    pid = db.create_project("P", narrative_engine=engine,
                            default_writing_format=engine).id
    win = MainWindow(db, pid)
    win._toggle_voice_panel()
    return db, pid, win


def test_ui_final_segment_lands_in_history_list():
    _db, pid, win = _ui_window()
    panel = win._voice_panel
    panel._apply_final_segment(_seg("dictated words", audio=b"\x01"))
    assert panel._history.segment_count == 1
    assert panel._history_list.count() == 1
    assert "[pending]" in panel._history_list.item(0).text()
    assert panel._history.entries[0].project_id_at_capture == pid


def test_ui_checked_segments_commit_via_router_in_order():
    db, pid, win = _ui_window()
    panel = win._voice_panel
    panel._apply_final_segment(_seg("alpha"))
    panel._apply_final_segment(_seg("beta"))
    from PySide6.QtCore import Qt
    for i in range(panel._history_list.count()):
        panel._history_list.item(i).setCheckState(Qt.CheckState.Checked)
    idx = panel._target_combo.findData(T_NOTE)
    panel._target_combo.setCurrentIndex(idx)
    win._dirty = False
    assert panel.commit() is True
    notes = db.get_all_notes(pid)
    assert len(notes) == 1 and notes[0].content == "alpha beta"
    assert all(e.status == vh.S_COMMITTED for e in panel._history.entries)
    assert "→ note" in panel._history_list.item(0).text()
    assert win._dirty is True


def test_ui_edit_apply_flow_commits_edited_text():
    db, pid, win = _ui_window()
    panel = win._voice_panel
    panel._apply_final_segment(_seg("teh raw text"))
    panel._history_list.setCurrentRow(0)
    panel._on_hist_edit()
    panel._preview.setPlainText("the corrected text")
    panel._on_hist_apply_edit()
    entry = panel._history.entries[0]
    assert entry.status == vh.S_EDITED
    from PySide6.QtCore import Qt
    panel._history_list.item(0).setCheckState(Qt.CheckState.Checked)
    idx = panel._target_combo.findData(T_NOTE)
    panel._target_combo.setCurrentIndex(idx)
    assert panel.commit() is True
    assert db.get_all_notes(pid)[0].content == "the corrected text"


def test_ui_undo_button_reverts_last_commit():
    db, pid, win = _ui_window()
    panel = win._voice_panel
    panel._apply_final_segment(_seg("note body"))
    from PySide6.QtCore import Qt
    panel._history_list.item(0).setCheckState(Qt.CheckState.Checked)
    idx = panel._target_combo.findData(T_NOTE)
    panel._target_combo.setCurrentIndex(idx)
    assert panel.commit() is True
    assert len(db.get_all_notes(pid)) == 1
    assert panel._undo_btn.isEnabled() is True
    panel._on_undo_commit()
    assert db.get_all_notes(pid) == []
    assert panel._undo_btn.isEnabled() is False      # single-level undo spent
    assert "Nothing to undo." in panel._undo_btn.toolTip()


def test_ui_retry_status_reason_when_audio_unavailable():
    _db, _pid, win = _ui_window()
    panel = win._voice_panel
    panel._apply_final_segment(_seg("no audio kept"))
    panel._history_list.setCurrentRow(0)
    panel._on_hist_retry()
    assert "Audio segment no longer available." in panel._status_label.text()


def test_ui_retry_with_audio_uses_mock_backend():
    _db, _pid, win = _ui_window()
    panel = win._voice_panel
    panel._apply_final_segment(_seg("garbled", audio=b"\x01\x02" * 8000))
    panel._history_list.setCurrentRow(0)
    panel._on_hist_retry()
    entry = panel._history.entries[0]
    assert "mock transcript" in entry.text           # local mock transcriber
    assert entry.original_text == "garbled"


def test_ui_discard_and_clear_uncommitted():
    _db, _pid, win = _ui_window()
    panel = win._voice_panel
    panel._apply_final_segment(_seg("one"))
    panel._apply_final_segment(_seg("two"))
    panel._history_list.setCurrentRow(0)
    panel._on_hist_discard()
    assert panel._history.entries[0].status == vh.S_DISCARDED
    assert "[discarded]" in panel._history_list.item(0).text()
    panel._on_clear_uncommitted()
    assert [e.status for e in panel._history.entries] == [vh.S_DISCARDED]


def test_ui_project_switch_freezes_history_and_blocks_commit():
    db, pid, win = _ui_window()
    b = db.create_project("B", narrative_engine="novel").id
    panel = win._voice_panel
    panel._apply_final_segment(_seg("captured in A"))
    win._switch_project(b)
    assert panel._history.session.status == "stale"
    assert panel._history.entries                    # kept, frozen
    from PySide6.QtCore import Qt
    panel._refresh_history_ui()
    panel._history_list.item(0).setCheckState(Qt.CheckState.Checked)
    idx = panel._target_combo.findData(T_NOTE)
    if idx < 0:
        panel._refresh_targets()
        idx = panel._target_combo.findData(T_NOTE)
    panel._target_combo.setCurrentIndex(idx)
    assert panel.commit() is False
    assert "another project" in panel._status_label.text()
    assert db.get_all_notes(b) == []                 # no leak into B


def test_ui_preview_commit_marks_fed_segments_committed():
    db, pid, win = _ui_window()
    panel = win._voice_panel
    panel._apply_final_segment(_seg("flows into preview"))
    assert panel._preview.toPlainText() == "flows into preview"
    idx = panel._target_combo.findData(T_NOTE)
    panel._target_combo.setCurrentIndex(idx)
    assert panel.commit() is True                    # nothing checked: preview
    assert panel._history.entries[0].status == vh.S_COMMITTED


def test_ui_history_creates_no_new_top_level_windows():
    _db, _pid, win = _ui_window()
    panel = win._voice_panel
    before = set(QApplication.topLevelWidgets())
    panel._apply_final_segment(_seg("row one"))
    panel._history_list.setCurrentRow(0)
    panel._on_hist_edit()
    panel._on_hist_apply_edit()
    new_visible = [w for w in (set(QApplication.topLevelWidgets()) - before)
                   if w.isVisible()]
    assert new_visible == []
