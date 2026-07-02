"""Voice MVP Phase 6 — Live Writer Room Alpha Shell.

One local, review-first session workflow over the whole voice stack: an
explicit crash-proof state machine, a safe refreshed VoiceRoomContext (no
keys, no audio, no other projects), a session-scoped ProposalQueue
(draft/ready/applied/cancelled/stale/failed — stale can never apply), and
four explicit workflow modes (Dictation default / Intent / Ask Billy /
Edit with Billy — never auto-detected). All in the existing safe floating
panel; nothing mutates without confirmation.
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
from logosforge.voice import room as vr
from logosforge.voice.billy_bridge import (
    OP_ASK,
    OP_REWRITE_SELECTION,
    OP_SUMMARIZE_NOTE,
    request_billy_proposal,
)
from logosforge.voice.commit_router import VoiceCommitContext, undo_commit
from logosforge.voice.editor_commit import EditorCommitTarget
from logosforge.voice.history import VoiceTranscriptHistory
from logosforge.voice.intent_router import (
    I_PSYKE_DRAFT,
    build_intent_preview,
)
from logosforge.voice.room import (
    ProposalQueue,
    VoiceRoomStateMachine,
    build_voice_room_context,
    context_summary_line,
)
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


def _project(db, engine="novel"):
    return db.create_project(engine, narrative_engine=engine,
                             default_writing_format=engine).id


def _ctx(db, pid, mode="novel", *, ai=None, editor=False, **over):
    kwargs = dict(db=db, project_id=pid, writing_mode=mode, ai_complete=ai)
    ed = None
    if editor:
        ed = QTextEdit()
        tgt = EditorCommitTarget()
        tgt.note_focus(ed)
        kwargs.update(has_active_editor=True,
                      insert_at_cursor=tgt.insert_as_plain_text,
                      active_editor_getter=tgt.active_editor)
    kwargs.update(over)
    return VoiceCommitContext(**kwargs), ed


def _gn_with_panel(db):
    pid = _project(db, "graphic_novel")
    sid = ss.create_scene(db, pid, act="Act 1", chapter="Chapter 1",
                          title="S").id
    gno.add_page(db, sid)
    gno.add_panel(db, sid, 0)
    return pid, sid


# ==========================================================================
# 1-10  Session state machine
# ==========================================================================


def test_happy_path_transitions():
    sm = VoiceRoomStateMachine()
    for state in ("ready", "listening", "transcribing", "transcript_ready",
                  "choosing_target", "applying", "applied"):
        assert sm.to(state) is True, state
    assert sm.state == "applied"


def test_billy_path_transitions():
    sm = VoiceRoomStateMachine()
    assert sm.to("checking_backend") and sm.to("ready") and sm.to("listening")
    assert sm.to("transcript_ready")
    assert sm.to("sending_to_billy")
    assert sm.to("proposal_ready")
    assert sm.to("applying") and sm.to("applied")


def test_invalid_transitions_do_not_crash_or_move():
    sm = VoiceRoomStateMachine()
    assert sm.to("applied") is False                  # idle -> applied invalid
    assert sm.state == "idle"
    assert sm.to("proposal_ready") is False
    assert sm.state == "idle"
    sm.to("ready")
    assert sm.to("applied") is False
    assert sm.state == "ready"


def test_stop_and_error_allowed_from_any_state():
    for target in ("stopped", "error"):
        sm = VoiceRoomStateMachine()
        sm.to("ready"); sm.to("listening"); sm.to("transcribing")
        assert sm.to(target) is True                  # safe app close / fail
    sm = VoiceRoomStateMachine()
    assert sm.to("stopped") is True                   # even from idle


def test_recovery_from_error_and_stopped():
    sm = VoiceRoomStateMachine()
    sm.to("ready"); sm.to("error")
    assert sm.to("ready") is True
    sm.to("stopped")
    assert sm.to("ready") is True


# ==========================================================================
# 11-18  Voice Room context
# ==========================================================================


def test_context_captures_project_mode_section_selection():
    db = Database()
    pid = _project(db)
    ctx, editor = _ctx(db, pid, ai=lambda p: "x", editor=True,
                       extras={"project_title": "My Book",
                               "active_section": "Manuscript"})
    editor.setPlainText("picked words")
    cur = editor.textCursor()
    cur.select(cur.SelectionType.Document)
    editor.setTextCursor(cur)
    room = build_voice_room_context(ctx)
    assert room.project_id == pid
    assert room.project_title == "My Book"
    assert room.writing_mode == "novel"
    assert room.active_section == "Manuscript"
    assert room.selected_text_snapshot == "picked words"
    assert room.billy_available is True
    line = context_summary_line(room)
    assert "My Book" in line and "Manuscript" in line
    assert "text selected" in line


def test_context_captures_gn_panel_and_field():
    db = Database()
    pid, sid = _gn_with_panel(db)
    ctx, _ed = _ctx(db, pid, "graphic_novel", gn_panel_ref=(sid, 0, 0),
                    gn_field_choice="dialogue")
    room = build_voice_room_context(ctx)
    assert room.current_scene_id == sid
    assert room.current_graphic_page_index == 0
    assert room.current_graphic_panel_index == 0
    assert room.selected_panel_field == "dialogue"
    assert "Panel 1 on Page 1" in context_summary_line(room)


def test_context_excludes_secrets_and_audio():
    db = Database()
    pid = _project(db)
    from logosforge.settings import get_manager
    get_manager().set("ai_api_key", "SECRET-XYZ")
    history = VoiceTranscriptHistory()
    history.start_session(pid)
    history.add_final_segment(
        TranscriptSegment(text="words", audio_bytes=b"\x01\x02"),
        project_id=pid, writing_mode="novel")
    ctx, _ed = _ctx(db, pid, ai=lambda p: "x")
    room = build_voice_room_context(ctx, history)
    flat = repr(vars(room))
    assert "SECRET-XYZ" not in flat
    assert "audio" not in flat.lower()
    assert "api_key" not in flat
    assert room.transcript_segment_ids == [history.entries[0].id]


def test_context_tracks_history_and_queue_ids():
    db = Database()
    pid = _project(db)
    history = VoiceTranscriptHistory()
    history.start_session(pid)
    queue = ProposalQueue()
    ctx, _ed = _ctx(db, pid)
    preview = build_intent_preview(I_PSYKE_DRAFT, "idea", ctx)
    item = queue.add_intent(preview)
    room = build_voice_room_context(ctx, history, queue)
    assert room.session_id == history.session.id
    assert room.pending_proposal_ids == [item.id]


# ==========================================================================
# 19-26  Proposal queue
# ==========================================================================


def test_billy_and_intent_proposals_enqueue_and_apply():
    db = Database()
    pid = _project(db)
    ctx, _ed = _ctx(db, pid, ai=lambda p: "the summary")
    queue = ProposalQueue()
    billy = request_billy_proposal(OP_SUMMARIZE_NOTE, "sum this", ctx)
    item_b = queue.add_billy(billy)
    assert item_b.status == vr.Q_READY
    intent = build_intent_preview(I_PSYKE_DRAFT, "an idea", ctx)
    item_i = queue.add_intent(intent)
    assert item_i.status == vr.Q_READY
    assert len(queue.pending()) == 2
    ok, _msg, op = queue.apply(item_b.id, ctx)
    assert ok is True and item_b.status == vr.Q_APPLIED
    assert item_b.operation_id == op.id               # op id stored
    assert len(db.get_all_notes(pid)) == 1
    ok, _msg, op2 = queue.apply(item_i.id, ctx)
    assert ok is True and len(db.get_all_psyke_entries(pid)) == 1
    assert undo_commit(op2, ctx)[0] is True           # undo where safe


def test_queue_cancel_and_no_reapply():
    db = Database()
    pid = _project(db)
    ctx, _ed = _ctx(db, pid, ai=lambda p: "body")
    queue = ProposalQueue()
    item = queue.add_billy(request_billy_proposal(OP_SUMMARIZE_NOTE, "x", ctx))
    assert queue.cancel(item.id) is True
    assert item.status == vr.Q_CANCELLED
    ok, _msg, _op = queue.apply(item.id, ctx)
    assert ok is False
    assert db.get_all_notes(pid) == []


def test_stale_proposal_cannot_apply():
    db = Database()
    a = _project(db)
    b = _project(db)
    ctx_a, _ed = _ctx(db, a, ai=lambda p: "body")
    queue = ProposalQueue()
    item = queue.add_billy(request_billy_proposal(OP_SUMMARIZE_NOTE, "x",
                                                  ctx_a))
    assert queue.on_project_switch(b) == 1            # marked stale
    assert item.status == vr.Q_STALE
    ctx_b, _ed2 = _ctx(db, b, ai=lambda p: "body")
    ok, msg, _op = queue.apply(item.id, ctx_b)
    assert ok is False and msg
    assert db.get_all_notes(b) == []


def test_live_validation_failure_marks_stale():
    db = Database()
    pid, sid = _gn_with_panel(db)
    ctx, _ed = _ctx(db, pid, "graphic_novel", ai=lambda p: "new visual",
                    gn_panel_ref=(sid, 0, 0))
    queue = ProposalQueue()
    item = queue.add_billy(request_billy_proposal(
        "billy_gn_panel_field", "more cinematic", ctx))
    gno.delete_panel(db, sid, 0, 0)                   # target vanishes
    ok, _msg, _op = queue.apply(item.id, ctx)
    assert ok is False and item.status == vr.Q_STALE


def test_blocked_proposal_enqueues_as_draft():
    db = Database()
    pid = _project(db)
    ctx, _ed = _ctx(db, pid, ai=None)                 # Billy unconfigured
    queue = ProposalQueue()
    item = queue.add_billy(request_billy_proposal(OP_ASK, "hello", ctx))
    assert item.status == vr.Q_DRAFT
    assert item.reason                                # the disable reason


# ==========================================================================
# 27-35  Modes + Graphic Novel (panel-level shell)
# ==========================================================================


def _ui_window(engine="novel", *, ai=True):
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
    if ai:
        win._voice_ai_complete_callable = lambda: (lambda p: "BILLY-OUT")
    return db, pid, win


def test_default_mode_is_dictation_with_four_modes():
    _db, _pid, win = _ui_window()
    panel = win._voice_panel
    assert panel.voice_mode() == "dictation"
    modes = {panel._mode_combo.itemData(i)
             for i in range(panel._mode_combo.count())}
    assert modes == {"dictation", "intent", "ask_billy", "edit_billy"}


def test_ask_billy_mode_presets_ask_and_chat_only():
    db, pid, win = _ui_window()
    panel = win._voice_panel
    panel._apply_final_segment(TranscriptSegment(text="how should I pace"))
    panel._mode_combo.setCurrentIndex(
        panel._mode_combo.findData("ask_billy"))
    assert panel._billy_op_combo.currentData() == OP_ASK
    from PySide6.QtCore import Qt
    panel._history_list.item(0).setCheckState(Qt.CheckState.Checked)
    panel._on_billy_generate()
    assert panel._pending_billy_proposal.proposal_type == "chat_only"
    assert "BILLY-OUT" in panel._billy_preview_area.toPlainText()
    assert db.get_all_notes(pid) == []                # chat never mutates


def test_edit_with_billy_mode_presets_rewrite_and_requires_selection():
    _db, _pid, win = _ui_window()
    panel = win._voice_panel
    panel._apply_final_segment(TranscriptSegment(text="make it tense"))
    panel._mode_combo.setCurrentIndex(
        panel._mode_combo.findData("edit_billy"))
    assert panel._billy_op_combo.currentData() == OP_REWRITE_SELECTION
    from PySide6.QtCore import Qt
    panel._history_list.item(0).setCheckState(Qt.CheckState.Checked)
    panel._on_billy_generate()                        # no selection anywhere
    assert panel._pending_billy_proposal.can_apply is False
    assert panel._billy_apply_btn.isEnabled() is False


def test_room_state_flows_through_billy_generate_and_apply():
    db, pid, win = _ui_window()
    panel = win._voice_panel
    panel._apply_final_segment(TranscriptSegment(text="note this"))
    from PySide6.QtCore import Qt
    panel._history_list.item(0).setCheckState(Qt.CheckState.Checked)
    panel._billy_op_combo.setCurrentIndex(
        panel._billy_op_combo.findData(OP_SUMMARIZE_NOTE))
    panel._on_billy_generate()
    assert panel._room.state == "proposal_ready"
    assert len(panel._queue.items) == 1
    assert panel._queue.items[0].status == vr.Q_READY
    panel._on_billy_apply()
    assert panel._room.state == "applied"
    assert panel._queue.items[0].status == vr.Q_APPLIED
    assert len(db.get_all_notes(pid)) == 1
    assert "[applied]" in panel._queue_list.item(0).text()


def test_room_label_and_queue_visible_in_shell():
    _db, _pid, win = _ui_window()
    panel = win._voice_panel
    assert "Dexter's Room" in panel._room_label.text()
    assert panel._queue_list.isVisibleTo(panel) is True
    assert panel._pause_btn.isVisibleTo(panel) is True


def test_project_switch_stales_queue_and_resets_room():
    db, pid, win = _ui_window()
    b = db.create_project("B", narrative_engine="novel").id
    panel = win._voice_panel
    panel._apply_final_segment(TranscriptSegment(text="an idea"))
    from PySide6.QtCore import Qt
    panel._history_list.item(0).setCheckState(Qt.CheckState.Checked)
    panel._billy_op_combo.setCurrentIndex(
        panel._billy_op_combo.findData(OP_SUMMARIZE_NOTE))
    panel._on_billy_generate()
    assert panel._queue.items[0].status == vr.Q_READY
    win._switch_project(b)
    assert panel._queue.items[0].status == vr.Q_STALE
    assert panel._pending_billy_proposal is None
    assert db.get_all_notes(b) == []


def test_gn_panel_proposal_through_queue_mirrors_and_undoes():
    db = Database()
    pid, sid = _gn_with_panel(db)
    gno.set_panel_field(db, sid, 0, 0, "visual_description", "old visual")
    ctx, _ed = _ctx(db, pid, "graphic_novel", ai=lambda p: "cinematic visual",
                    gn_panel_ref=(sid, 0, 0),
                    gn_field_choice="visual_description")
    queue = ProposalQueue()
    item = queue.add_billy(request_billy_proposal(
        "billy_gn_panel_field", "more cinematic", ctx))
    ok, _msg, op = queue.apply(item.id, ctx)
    assert ok is True
    panel = gnb.load_scene_script(db, sid).pages[0].panels[0]
    assert panel.visual_description == "cinematic visual"
    from logosforge.ui.graphic_novel_manuscript_view import (
        GraphicNovelManuscriptView)
    view = GraphicNovelManuscriptView(db, pid, on_data_changed=lambda: None)
    view.select_scene(sid)
    assert "cinematic visual" in \
        view._field_editors[("panel", sid, 0, 0)].toPlainText()
    assert undo_commit(op, ctx)[0] is True
    assert gnb.load_scene_script(db, sid).pages[0].panels[0] \
        .visual_description == "old visual"


def test_no_comfyui_or_image_fields_in_room():
    import inspect
    src = inspect.getsource(vr).lower()
    for banned in ("comfyui", "img2img", "txt2img", "image_prompt",
                   "subprocess", "os.system", "openai", "urllib.request"):
        assert banned not in src, banned
    room = vr.VoiceRoomContext()
    assert not any("image" in f or "comfy" in f for f in vars(room))


# ==========================================================================
# 36-41  Safety + shell UI
# ==========================================================================


def test_pause_keeps_history_and_queue():
    _db, _pid, win = _ui_window()
    panel = win._voice_panel
    panel._apply_final_segment(TranscriptSegment(text="kept words"))
    panel._on_pause()
    assert panel._room.state == "ready"
    assert panel._history.segment_count == 1          # nothing lost
    assert "paused" in panel._status_label.text().lower()


def test_queue_double_click_reactivates_ready_proposal():
    db, pid, win = _ui_window()
    panel = win._voice_panel
    panel._apply_final_segment(TranscriptSegment(text="note one"))
    from PySide6.QtCore import Qt
    panel._history_list.item(0).setCheckState(Qt.CheckState.Checked)
    panel._billy_op_combo.setCurrentIndex(
        panel._billy_op_combo.findData(OP_SUMMARIZE_NOTE))
    panel._on_billy_generate()
    panel._pending_billy_proposal = None              # user moved on
    panel._billy_apply_btn.setEnabled(False)
    panel._on_queue_activate(panel._queue_list.item(0))
    assert panel._pending_billy_proposal is not None
    assert panel._billy_apply_btn.isEnabled() is True
    panel._on_billy_apply()
    assert len(db.get_all_notes(pid)) == 1


def test_shell_creates_no_new_windows_and_no_auto_apply():
    db, pid, win = _ui_window()
    panel = win._voice_panel
    before = set(QApplication.topLevelWidgets())
    panel._apply_final_segment(TranscriptSegment(text="just speaking"))
    panel._mode_combo.setCurrentIndex(
        panel._mode_combo.findData("ask_billy"))
    new_visible = [w for w in (set(QApplication.topLevelWidgets()) - before)
                   if w.isVisible()]
    assert new_visible == []
    assert db.get_all_notes(pid) == []                # speaking mutates nothing
    assert db.get_all_psyke_entries(pid) == []


def test_dictation_still_works_without_billy():
    from logosforge.settings import get_manager
    db, pid, win = _ui_window(ai=False)
    get_manager().set("ai_provider", "")
    get_manager().set("ai_base_url", "")
    panel = win._voice_panel
    panel._refresh_billy_ops()
    assert panel._billy_generate_btn.isEnabled() is False
    editor = QTextEdit()
    win._voice_commit.note_focus(editor)
    panel._preview.setPlainText("dictated text")
    assert panel.commit() is True                     # dictation unaffected
    assert "dictated text" in editor.toPlainText()
