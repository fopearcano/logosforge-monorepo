"""Voice MVP Phase 5 — Billy Voice Bridge: transcript → proposal → confirm.

Billy (the Assistant chat agent) receives TEXT only — transcript + a
minimal safe context (never audio, never API keys/provider settings, never
other-project data). Operations are a fixed allowlist; every response is a
preview-only proposal applied solely on explicit confirm, routed through
the existing Intent/Commit routers (inheriting live re-validation + Phase 3
undo records). Dangerous spoken "commands" are never executed — they come
back chat-only. With no provider configured, every Billy action disables
with the documented message.
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
from logosforge.voice import billy_bridge as bb
from logosforge.voice.billy_bridge import (
    BILLY_CANT_DO_THAT,
    BILLY_PROJECT_CHANGED,
    BILLY_TARGET_CHANGED,
    BILLY_UNCONFIGURED,
    OP_ASK,
    OP_CONTINUE_CURSOR,
    OP_GN_PANEL_FIELD,
    OP_OUTLINE_ITEM,
    OP_PSYKE_DRAFT,
    OP_REWRITE_SELECTION,
    OP_SUMMARIZE_NOTE,
    P_CHAT_ONLY,
    apply_billy_voice_proposal,
    build_billy_voice_context,
    cancel_billy_voice_proposal,
    get_available_billy_operations,
    request_billy_proposal,
    validate_billy_proposal,
)
from logosforge.voice.commit_router import VoiceCommitContext, undo_commit
from logosforge.voice.editor_commit import EditorCommitTarget


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


def _select_all(editor):
    cur = editor.textCursor()
    cur.select(cur.SelectionType.Document)
    editor.setTextCursor(cur)


def _ops(ctx):
    return {o[0]: o for o in get_available_billy_operations(ctx)}


def _gn_with_panel(db):
    pid = _project(db, "graphic_novel")
    sid = ss.create_scene(db, pid, act="Act 1", chapter="Chapter 1",
                          title="S").id
    gno.add_page(db, sid)
    gno.add_panel(db, sid, 0)
    return pid, sid


# ==========================================================================
# 1-10  Bridge basics
# ==========================================================================


def test_context_packaging_text_only_no_secrets():
    db = Database()
    pid = _project(db)
    from logosforge.settings import get_manager
    get_manager().set("ai_api_key", "SECRET-KEY-123")
    get_manager().set("voice_lan_auth_token", "LAN-SECRET")
    ctx, editor = _ctx(db, pid, ai=lambda p: "x", editor=True,
                       extras={"project_title": "My Book"})
    editor.setPlainText("chosen words")
    _select_all(editor)
    packaged = build_billy_voice_context("make it tense", ctx)
    flat = repr(packaged)
    assert packaged["transcript"] == "make it tense"
    assert packaged["selected_text"] == "chosen words"
    assert packaged["project_title"] == "My Book"
    assert "SECRET-KEY-123" not in flat and "LAN-SECRET" not in flat
    assert "audio" not in flat.lower()
    assert not any(isinstance(v, (bytes, bytearray))
                   for v in packaged.values())          # text only, no audio


def test_context_excludes_other_projects():
    db = Database()
    a = _project(db)
    b = db.create_project("OTHER SECRET PROJECT", narrative_engine="novel").id
    sb = ss.create_scene(db, b, act="Act 1", chapter="Chapter 1",
                         title="OtherScene", content="OTHER-BODY").id
    assert sb
    ctx, _ed = _ctx(db, a, ai=lambda p: "x")
    packaged = build_billy_voice_context("hello", ctx)
    flat = repr(packaged)
    assert "OTHER SECRET PROJECT" not in flat
    assert "OTHER-BODY" not in flat
    assert packaged["project_id"] == a


def test_no_provider_disables_all_billy_ops():
    db = Database()
    pid = _project(db)
    ctx, _ed = _ctx(db, pid, ai=None, editor=True)
    for op_id, _label, enabled, reason in get_available_billy_operations(ctx):
        assert enabled is False
        assert reason == BILLY_UNCONFIGURED
    proposal = request_billy_proposal(OP_ASK, "hello", ctx)
    assert proposal.reason_if_blocked == BILLY_UNCONFIGURED


def test_configured_provider_enables_ops():
    db = Database()
    pid = _project(db)
    ctx, editor = _ctx(db, pid, ai=lambda p: "answer", editor=True)
    editor.setPlainText("words")
    _select_all(editor)
    ops = _ops(ctx)
    assert ops[OP_ASK][2] is True
    assert ops[OP_REWRITE_SELECTION][2] is True
    assert ops[OP_CONTINUE_CURSOR][2] is True
    assert ops[OP_SUMMARIZE_NOTE][2] is True
    assert ops[OP_PSYKE_DRAFT][2] is True
    assert ops[OP_OUTLINE_ITEM][2] is False             # still deferred


def test_proposal_is_preview_only_no_mutation():
    db = Database()
    pid = _project(db)
    ctx, _ed = _ctx(db, pid, ai=lambda p: "a body")
    request_billy_proposal(OP_PSYKE_DRAFT, "a relic idea", ctx)
    request_billy_proposal(OP_SUMMARIZE_NOTE, "long talk", ctx)
    assert db.get_all_notes(pid) == []
    assert db.get_all_psyke_entries(pid) == []


def test_apply_mutates_only_after_confirmation_and_cancel_never():
    db = Database()
    pid = _project(db)
    ctx, _ed = _ctx(db, pid, ai=lambda p: "summary text")
    proposal = request_billy_proposal(OP_SUMMARIZE_NOTE, "summarize this", ctx)
    assert proposal.can_apply is True
    cancel_billy_voice_proposal(proposal)               # user cancels
    ok, _msg, _op = apply_billy_voice_proposal(proposal, ctx)
    assert ok is False
    assert db.get_all_notes(pid) == []
    proposal2 = request_billy_proposal(OP_SUMMARIZE_NOTE, "again", ctx)
    ok, msg, op = apply_billy_voice_proposal(proposal2, ctx)
    assert ok is True and op is not None
    assert len(db.get_all_notes(pid)) == 1
    assert proposal2.applied is True and proposal2.applied_at is not None


# ==========================================================================
# 11-15  Project / stale safety
# ==========================================================================


def test_project_mismatch_blocks_apply():
    db = Database()
    a = _project(db)
    b = _project(db)
    ctx_a, _ed = _ctx(db, a, ai=lambda p: "body")
    proposal = request_billy_proposal(OP_PSYKE_DRAFT, "idea", ctx_a)
    ctx_b, _ed2 = _ctx(db, b, ai=lambda p: "body")
    ok, reason = validate_billy_proposal(proposal, ctx_b)
    assert ok is False and reason == BILLY_PROJECT_CHANGED
    ok, _msg, _op = apply_billy_voice_proposal(proposal, ctx_b)
    assert ok is False and db.get_all_psyke_entries(b) == []


def test_changed_selection_blocks_rewrite_apply():
    db = Database()
    pid = _project(db)
    ctx, editor = _ctx(db, pid, ai=lambda p: "REWRITTEN", editor=True)
    editor.setPlainText("original words here")
    _select_all(editor)
    proposal = request_billy_proposal(OP_REWRITE_SELECTION, "shorter", ctx)
    assert proposal.can_apply is True
    editor.setPlainText("user typed something else")    # selection drifted
    _select_all(editor)
    ok, reason = validate_billy_proposal(proposal, ctx)
    assert ok is False and reason == BILLY_TARGET_CHANGED


def test_deleted_panel_blocks_gn_apply():
    db = Database()
    pid, sid = _gn_with_panel(db)
    ctx, _ed = _ctx(db, pid, "graphic_novel", ai=lambda p: "new visual",
                    gn_panel_ref=(sid, 0, 0))
    proposal = request_billy_proposal(OP_GN_PANEL_FIELD, "more cinematic",
                                      ctx)
    assert proposal.can_apply is True
    gno.delete_panel(db, sid, 0, 0)                     # target deleted
    ok, reason = validate_billy_proposal(proposal, ctx)
    assert ok is False and reason == BILLY_TARGET_CHANGED


# ==========================================================================
# 16-24  Proposal types
# ==========================================================================


def test_chat_only_proposal_never_mutates():
    db = Database()
    pid = _project(db)
    ctx, _ed = _ctx(db, pid, ai=lambda p: "Here is my advice.")
    proposal = request_billy_proposal(OP_ASK, "how do I pace this scene", ctx)
    assert proposal.proposal_type == P_CHAT_ONLY
    assert proposal.response_text == "Here is my advice."
    assert proposal.can_apply is False                  # nothing to apply
    ok, _msg, _op = apply_billy_voice_proposal(proposal, ctx)
    assert ok is False
    assert db.get_all_notes(pid) == []


def test_replace_selection_proposal_apply_and_undo():
    db = Database()
    pid = _project(db)
    ctx, editor = _ctx(db, pid, ai=lambda p: "TENSE VERSION", editor=True)
    editor.setPlainText("calm words")
    _select_all(editor)
    proposal = request_billy_proposal(OP_REWRITE_SELECTION,
                                      "make this more tense", ctx)
    assert proposal.before_text == "calm words"
    assert proposal.after_text == "TENSE VERSION"
    assert proposal.diff and "-calm words" in proposal.diff
    ok, _msg, op = apply_billy_voice_proposal(proposal, ctx)
    assert ok is True and editor.toPlainText() == "TENSE VERSION"
    assert undo_commit(op, ctx)[0] is True              # Phase 3 undo record
    assert editor.toPlainText() == "calm words"


def test_insert_at_cursor_proposal_apply():
    db = Database()
    pid = _project(db)
    ctx, editor = _ctx(db, pid, ai=lambda p: "and the rain kept falling.",
                       editor=True)
    editor.setPlainText("She opened the door ")
    cur = editor.textCursor()
    cur.movePosition(cur.MoveOperation.End)
    editor.setTextCursor(cur)
    proposal = request_billy_proposal(OP_CONTINUE_CURSOR, "continue softly",
                                      ctx)
    assert proposal.proposal_type == bb.P_INSERT_AT_CURSOR
    ok, _msg, op = apply_billy_voice_proposal(proposal, ctx)
    assert ok is True and op is not None
    assert editor.toPlainText() == \
        "She opened the door and the rain kept falling."


def test_note_draft_proposal_creates_note_only_on_apply():
    db = Database()
    pid = _project(db)
    ctx, _ed = _ctx(db, pid, ai=lambda p: "A crisp summary.")
    proposal = request_billy_proposal(OP_SUMMARIZE_NOTE, "sum it up", ctx)
    assert proposal.note_preview["content"] == "A crisp summary."
    assert db.get_all_notes(pid) == []
    ok, _msg, op = apply_billy_voice_proposal(proposal, ctx)
    assert ok is True
    assert db.get_all_notes(pid)[0].content == "A crisp summary."
    assert undo_commit(op, ctx)[0] is True              # created-note undo
    assert db.get_all_notes(pid) == []


def test_outline_proposal_disabled():
    db = Database()
    pid = _project(db)
    ctx, _ed = _ctx(db, pid, ai=lambda p: "x")
    proposal = request_billy_proposal(OP_OUTLINE_ITEM, "add a beat", ctx)
    assert proposal.can_apply is False
    assert proposal.reason_if_blocked == \
        "Outline voice target not available yet."


def test_psyke_proposal_requires_type_default_other():
    db = Database()
    pid = _project(db)
    ctx, _ed = _ctx(db, pid, ai=lambda p: "Entry body about the lantern.")
    proposal = request_billy_proposal(
        OP_PSYKE_DRAFT, "Character: clearly a character idea", ctx)
    assert proposal.psyke_preview["entry_type"] == "other"   # never guessed
    apply_billy_voice_proposal(proposal, ctx)
    assert db.get_all_psyke_entries(pid)[0].entry_type == "other"
    ctx.psyke_entry_type = "place"
    proposal2 = request_billy_proposal(OP_PSYKE_DRAFT, "a chapel idea", ctx)
    assert proposal2.psyke_preview["entry_type"] == "place"


# ==========================================================================
# 25-32  Graphic Novel panel proposals
# ==========================================================================


from logosforge.voice.intent_router import GN_FIELD_CHOICES


@pytest.mark.parametrize("field", [f for f, _l in GN_FIELD_CHOICES])
def test_gn_panel_field_proposal_apply_and_mirror(field):
    db = Database()
    pid, sid = _gn_with_panel(db)
    gno.set_panel_field(db, sid, 0, 0, field, "old value")
    ctx, _ed = _ctx(db, pid, "graphic_novel", ai=lambda p: "billy value",
                    gn_panel_ref=(sid, 0, 0), gn_field_choice=field)
    proposal = request_billy_proposal(OP_GN_PANEL_FIELD,
                                      "make it more cinematic", ctx)
    assert proposal.before_text == "old value"
    assert proposal.after_text == "billy value"
    ok, _msg, op = apply_billy_voice_proposal(proposal, ctx)
    assert ok is True
    panel = gnb.load_scene_script(db, sid).pages[0].panels[0]
    assert getattr(panel, field) == "billy value"       # replace, previewed
    # Mirror: Manuscript script block shows it (same shared body).
    from logosforge.ui.graphic_novel_manuscript_view import (
        GraphicNovelManuscriptView)
    view = GraphicNovelManuscriptView(db, pid, on_data_changed=lambda: None)
    view.select_scene(sid)
    assert "billy value" in view._field_editors[("panel", sid, 0, 0)].toPlainText()
    # Undo restores the previous value.
    assert undo_commit(op, ctx)[0] is True
    panel = gnb.load_scene_script(db, sid).pages[0].panels[0]
    assert getattr(panel, field) == "old value"


def test_gn_proposal_disabled_without_panel_and_no_image_prompts():
    db = Database()
    pid, _sid = _gn_with_panel(db)
    prompts = []
    ctx, _ed = _ctx(db, pid, "graphic_novel",
                    ai=lambda p: prompts.append(p) or "v",
                    gn_panel_ref=None)
    ops = _ops(ctx)
    assert ops[OP_GN_PANEL_FIELD][2] is False
    assert ops[OP_GN_PANEL_FIELD][3] == "Select a Panel first."
    # And the prompt template for panel fields forbids image prompts.
    ctx.gn_panel_ref = None
    proposal = request_billy_proposal(OP_GN_PANEL_FIELD, "x", ctx)
    assert proposal.can_apply is False


# ==========================================================================
# 33-37  Voice history integration
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


def test_history_tracks_billy_usage_no_secrets_no_audio():
    db, pid, win = _ui_window()
    panel = win._voice_panel
    from logosforge.voice.types import TranscriptSegment
    panel._apply_final_segment(TranscriptSegment(text="summarize my idea",
                                                 audio_bytes=b"\x01"))
    from PySide6.QtCore import Qt
    panel._history_list.item(0).setCheckState(Qt.CheckState.Checked)
    idx = panel._billy_op_combo.findData(OP_SUMMARIZE_NOTE)
    panel._billy_op_combo.setCurrentIndex(idx)
    panel._on_billy_generate()
    entry = panel._history.entries[0]
    assert entry.sent_to_billy is True
    assert entry.billy_proposal_id
    assert entry.billy_state == "proposed"
    panel._on_billy_apply()
    assert entry.billy_state == "applied"
    assert entry.status == "committed"
    assert entry.audio_bytes is None                    # dropped on commit
    flat = repr(vars(entry))
    assert "api_key" not in flat and "token" not in flat


def test_history_cancelled_state():
    _db, _pid, win = _ui_window()
    panel = win._voice_panel
    from logosforge.voice.types import TranscriptSegment
    panel._apply_final_segment(TranscriptSegment(text="an idea"))
    from PySide6.QtCore import Qt
    panel._history_list.item(0).setCheckState(Qt.CheckState.Checked)
    idx = panel._billy_op_combo.findData(OP_PSYKE_DRAFT)
    panel._billy_op_combo.setCurrentIndex(idx)
    panel._on_billy_generate()
    panel._on_billy_cancel()
    assert panel._history.entries[0].billy_state == "cancelled"
    assert panel._pending_billy_proposal is None


# ==========================================================================
# 38-44  UI states
# ==========================================================================


def test_ui_billy_disabled_without_provider():
    from logosforge.settings import get_manager
    _db, _pid, win = _ui_window(ai=False)
    # Simulate a truly unconfigured provider (the default is "LM Studio").
    get_manager().set("ai_provider", "")
    get_manager().set("ai_base_url", "")
    panel = win._voice_panel
    panel._refresh_billy_ops()
    assert panel._billy_generate_btn.isEnabled() is False
    assert BILLY_UNCONFIGURED in panel._billy_generate_btn.toolTip()


def test_ui_no_transcript_blocks_generate():
    _db, _pid, win = _ui_window()
    panel = win._voice_panel
    idx = panel._billy_op_combo.findData(OP_ASK)
    panel._billy_op_combo.setCurrentIndex(idx)
    panel._on_billy_generate()                          # nothing selected
    assert "Select a transcript segment first." in \
        panel._billy_preview_area.toPlainText()
    assert panel._billy_apply_btn.isEnabled() is False


def test_ui_proposal_ready_enables_apply_and_applies_note():
    db, pid, win = _ui_window()
    panel = win._voice_panel
    from logosforge.voice.types import TranscriptSegment
    panel._apply_final_segment(TranscriptSegment(text="note this down"))
    from PySide6.QtCore import Qt
    panel._history_list.item(0).setCheckState(Qt.CheckState.Checked)
    idx = panel._billy_op_combo.findData(OP_SUMMARIZE_NOTE)
    panel._billy_op_combo.setCurrentIndex(idx)
    win._dirty = False
    panel._on_billy_generate()
    assert panel._billy_apply_btn.isEnabled() is True
    assert "BILLY-OUT" in panel._billy_preview_area.toPlainText()
    panel._on_billy_apply()
    assert len(db.get_all_notes(pid)) == 1
    assert win._dirty is True
    assert panel._undo_btn.isEnabled() is True          # undo wired


def test_ui_billy_creates_no_new_windows():
    _db, _pid, win = _ui_window()
    panel = win._voice_panel
    before = set(QApplication.topLevelWidgets())
    panel._refresh_billy_ops()
    panel._on_billy_generate()
    new_visible = [w for w in (set(QApplication.topLevelWidgets()) - before)
                   if w.isVisible()]
    assert new_visible == []


# ==========================================================================
# 45-49  Safety
# ==========================================================================


@pytest.mark.parametrize("bad", [
    "delete the project",
    "move all scenes to act three",
    "send this to ComfyUI",
    "run this command for me",
    "open terminal and upload this",
])
def test_dangerous_transcripts_become_chat_only(bad):
    db = Database()
    pid = _project(db)
    calls = []
    ctx, editor = _ctx(db, pid, ai=lambda p: calls.append(p) or "X",
                       editor=True)
    editor.setPlainText("text")
    _select_all(editor)
    for op in (OP_ASK, OP_REWRITE_SELECTION, OP_SUMMARIZE_NOTE,
               OP_PSYKE_DRAFT):
        proposal = request_billy_proposal(op, bad, ctx)
        assert proposal.proposal_type == P_CHAT_ONLY
        assert proposal.response_text == BILLY_CANT_DO_THAT
        assert proposal.can_apply is False
    assert calls == []                                  # provider never called
    assert db.get_all_notes(pid) == []
    assert db.get_all_psyke_entries(pid) == []


def test_bridge_module_has_no_shell_cloud_or_image_refs():
    import inspect
    src = inspect.getsource(bb).lower()
    for banned in ("subprocess", "os.system", "popen", "openai",
                   "requests.", "urllib.request", "ngrok", "img2img",
                   "txt2img", "websocket"):
        assert banned not in src, banned


def test_ai_receives_text_prompts_only():
    db = Database()
    pid = _project(db)
    prompts = []
    ctx, _ed = _ctx(db, pid, ai=lambda p: prompts.append(p) or "ok")
    request_billy_proposal(OP_ASK, "a question", ctx)
    request_billy_proposal(OP_SUMMARIZE_NOTE, "material", ctx)
    assert prompts and all(isinstance(p, str) for p in prompts)
    assert all("audio" not in p.lower() for p in prompts)


def test_no_auto_apply_anywhere():
    db = Database()
    pid = _project(db)
    ctx, editor = _ctx(db, pid, ai=lambda p: "OUT", editor=True)
    editor.setPlainText("body")
    _select_all(editor)
    for op in (OP_REWRITE_SELECTION, OP_SUMMARIZE_NOTE, OP_PSYKE_DRAFT,
               OP_CONTINUE_CURSOR):
        request_billy_proposal(op, "instruction", ctx)
    assert editor.toPlainText() == "body"               # untouched
    assert db.get_all_notes(pid) == []
    assert db.get_all_psyke_entries(pid) == []
