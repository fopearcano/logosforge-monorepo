"""Voice MVP Phase 4 — Voice Intent Router: preview-first confirmed ops.

Dictation stays the default; Intent mode is explicit opt-in. Intents are a
fixed allowlist (cleanup / insert-cleaned / AI rewrite-selection / AI
summarize-to-Note / PSYKE draft / GN panel field; Outline draft listed
disabled). Listing and previews never mutate; apply re-validates project,
target existence and the expected before-text; stale previews are blocked;
applied intents produce the Phase 3 undo records. AI runs only through the
injected existing-provider callable (text-only), and without one the
AI-backed intents disable with the documented message. No shell, no cloud,
no audio to AI, no auto-apply.
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
from logosforge.voice import intent_router as ir
from logosforge.voice.commit_router import (
    T_NOTE,
    VoiceCommitContext,
    can_undo,
    undo_commit,
)
from logosforge.voice.editor_commit import EditorCommitTarget
from logosforge.voice.intent_router import (
    AI_UNAVAILABLE,
    I_CLEANUP,
    I_GN_PANEL_FIELD,
    I_INSERT_CLEANED,
    I_OUTLINE_DRAFT,
    I_PSYKE_DRAFT,
    I_REWRITE_SELECTION,
    I_SUMMARIZE_TO_NOTE,
    NO_SELECTION,
    STALE_PREVIEW,
    apply_intent_preview,
    build_intent_preview,
    get_available_voice_intents,
    rule_based_cleanup,
    validate_intent_preview,
)


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


def _by_id(intents, iid):
    return next(i for i in intents if i.id == iid)


def _gn_with_panel(db):
    pid = _project(db, "graphic_novel")
    sid = ss.create_scene(db, pid, act="Act 1", chapter="Chapter 1",
                          title="S").id
    gno.add_page(db, sid)
    gno.add_panel(db, sid, 0)
    return pid, sid


# ==========================================================================
# 1-10  Router basics + safety
# ==========================================================================


def test_intent_listing_is_allowlist_and_read_only():
    db = Database()
    pid = _project(db)
    before_notes = len(db.get_all_notes(pid))
    ctx, _ed = _ctx(db, pid)
    intents = get_available_voice_intents(ctx)
    ids = {i.id for i in intents}
    assert ids == {I_CLEANUP, I_INSERT_CLEANED, I_REWRITE_SELECTION,
                   I_SUMMARIZE_TO_NOTE, I_OUTLINE_DRAFT, I_PSYKE_DRAFT}
    assert all(i.requires_confirmation for i in intents)
    assert len(db.get_all_notes(pid)) == before_notes


def test_preview_generation_does_not_mutate():
    db = Database()
    pid = _project(db)
    ctx, _ed = _ctx(db, pid)
    build_intent_preview(I_PSYKE_DRAFT, "a lantern in the marsh", ctx)
    build_intent_preview(I_CLEANUP, "messy  text", ctx)
    assert db.get_all_notes(pid) == []
    assert db.get_all_psyke_entries(pid) == []


def test_apply_mutates_only_after_confirmation():
    db = Database()
    pid = _project(db)
    ctx, _ed = _ctx(db, pid)
    preview = build_intent_preview(I_PSYKE_DRAFT, "the drowned chapel", ctx)
    assert preview.can_apply is True
    assert db.get_all_psyke_entries(pid) == []      # preview alone: nothing
    ok, _msg, op = apply_intent_preview(preview, ctx)
    assert ok is True and op is not None
    assert len(db.get_all_psyke_entries(pid)) == 1  # only the explicit apply


def test_stale_preview_blocked_after_project_switch():
    db = Database()
    a = _project(db)
    b = _project(db)
    ctx_a, _ed = _ctx(db, a)
    preview = build_intent_preview(I_PSYKE_DRAFT, "entry", ctx_a)
    ctx_b, _ed2 = _ctx(db, b)
    ok, reason = validate_intent_preview(preview, ctx_b)
    assert ok is False and reason == STALE_PREVIEW
    ok, _msg, _op = apply_intent_preview(preview, ctx_b)
    assert ok is False
    assert db.get_all_psyke_entries(b) == []


def test_stale_preview_blocked_when_selection_changed():
    db = Database()
    pid = _project(db)
    ctx, editor = _ctx(db, pid, ai=lambda p: "REWRITTEN", editor=True)
    editor.setPlainText("the original words")
    _select_all(editor)
    preview = build_intent_preview(I_REWRITE_SELECTION, "tighter", ctx)
    assert preview.can_apply is True
    editor.setPlainText("user changed everything")   # target drifted
    _select_all(editor)
    ok, reason = validate_intent_preview(preview, ctx)
    assert ok is False and reason == STALE_PREVIEW


def test_deleted_gn_target_blocks_apply():
    db = Database()
    pid, sid = _gn_with_panel(db)
    ctx, _ed = _ctx(db, pid, "graphic_novel", gn_panel_ref=(sid, 0, 0))
    preview = build_intent_preview(I_GN_PANEL_FIELD, "into the panel", ctx)
    assert preview.can_apply is True
    gno.delete_panel(db, sid, 0, 0)                  # target deleted
    ok, reason = validate_intent_preview(preview, ctx)
    assert ok is False and reason == STALE_PREVIEW


def test_ai_unavailable_disables_ai_intents_with_message():
    db = Database()
    pid = _project(db)
    ctx, _ed = _ctx(db, pid, ai=None, editor=True)
    intents = get_available_voice_intents(ctx)
    summarize = _by_id(intents, I_SUMMARIZE_TO_NOTE)
    assert summarize.enabled is False
    assert summarize.reason_if_disabled == AI_UNAVAILABLE
    rewrite = _by_id(intents, I_REWRITE_SELECTION)
    assert rewrite.enabled is False                  # no AI (even w/ editor)


def test_rule_based_cleanup_available_without_ai():
    db = Database()
    pid = _project(db)
    ctx, _ed = _ctx(db, pid, ai=None)
    assert _by_id(get_available_voice_intents(ctx), I_CLEANUP).enabled
    preview = build_intent_preview(I_CLEANUP, "hello   world", ctx)
    assert preview.can_apply is True
    assert preview.after_text == "Hello world."


def test_outline_draft_intent_listed_disabled():
    db = Database()
    pid = _project(db)
    ctx, _ed = _ctx(db, pid)
    outline = _by_id(get_available_voice_intents(ctx), I_OUTLINE_DRAFT)
    assert outline.enabled is False
    assert outline.reason_if_disabled == \
        "Outline voice target not available yet."


# ==========================================================================
# 11-15  Rule-based cleanup
# ==========================================================================


def test_cleanup_trims_and_normalizes_spaces():
    assert rule_based_cleanup("  too    many   spaces  ") == \
        "Too many spaces."


def test_cleanup_spoken_punctuation():
    out = rule_based_cleanup(
        "hello comma world period new paragraph next part")
    assert out == "Hello, world.\n\nNext part."


def test_cleanup_capitalizes_after_sentences():
    assert rule_based_cleanup("first part. second part") == \
        "First part. Second part."


def test_cleanup_does_not_fabricate_content():
    out = rule_based_cleanup("just these words")
    assert out == "Just these words."
    # Every word in the output came from the input (plus final punctuation).
    assert [w.strip(".,").lower() for w in out.split()] == \
        ["just", "these", "words"]


def test_empty_cleanup_cannot_apply():
    db = Database()
    pid = _project(db)
    ctx, _ed = _ctx(db, pid)
    preview = build_intent_preview(I_CLEANUP, "    ", ctx)
    assert preview.can_apply is False
    ok, _msg, _op = apply_intent_preview(preview, ctx)
    assert ok is False


# ==========================================================================
# 16-20  Rewrite selected text (AI)
# ==========================================================================


def test_rewrite_disabled_without_selection():
    db = Database()
    pid = _project(db)
    ctx, editor = _ctx(db, pid, ai=lambda p: "X", editor=True)
    editor.setPlainText("words")                     # no selection made
    rewrite = _by_id(get_available_voice_intents(ctx), I_REWRITE_SELECTION)
    assert rewrite.enabled is False
    assert rewrite.reason_if_disabled == NO_SELECTION
    preview = build_intent_preview(I_REWRITE_SELECTION, "shorter", ctx)
    assert preview.can_apply is False


def test_rewrite_preview_has_before_after_and_diff():
    db = Database()
    pid = _project(db)
    calls = []

    def fake_ai(prompt):
        calls.append(prompt)
        return "SHORTER VERSION"

    ctx, editor = _ctx(db, pid, ai=fake_ai, editor=True)
    editor.setPlainText("a very long paragraph that rambles")
    _select_all(editor)
    preview = build_intent_preview(I_REWRITE_SELECTION,
                                   "rewrite this shorter", ctx)
    assert preview.before_text == "a very long paragraph that rambles"
    assert preview.after_text == "SHORTER VERSION"
    assert preview.diff and "-a very long" in preview.diff
    assert preview.risk_level == "medium"
    # The instruction + selected TEXT went to AI — never audio.
    assert "rewrite this shorter" in calls[0]
    assert isinstance(calls[0], str)


def test_rewrite_apply_replaces_selection_only_and_undo_restores():
    db = Database()
    pid = _project(db)
    ctx, editor = _ctx(db, pid, ai=lambda p: "NEW MIDDLE", editor=True)
    editor.setPlainText("keep OLD keep")
    cur = editor.textCursor()
    cur.setPosition(5)
    cur.setPosition(8, cur.MoveMode.KeepAnchor)      # select "OLD"
    editor.setTextCursor(cur)
    preview = build_intent_preview(I_REWRITE_SELECTION, "replace it", ctx)
    ok, _msg, op = apply_intent_preview(preview, ctx)
    assert ok is True
    assert editor.toPlainText() == "keep NEW MIDDLE keep"
    assert can_undo(op, ctx) == (True, "")
    assert undo_commit(op, ctx)[0] is True
    assert editor.toPlainText() == "keep OLD keep"


def test_rewrite_apply_blocked_when_ai_empty():
    db = Database()
    pid = _project(db)
    ctx, editor = _ctx(db, pid, ai=lambda p: "", editor=True)
    editor.setPlainText("text")
    _select_all(editor)
    preview = build_intent_preview(I_REWRITE_SELECTION, "rewrite", ctx)
    assert preview.can_apply is False
    assert preview.reason_if_blocked == "AI returned no text."


# ==========================================================================
# 21-26  Note / PSYKE intents
# ==========================================================================


def test_summarize_creates_preview_only_then_note_on_apply():
    db = Database()
    pid = _project(db)
    ctx, _ed = _ctx(db, pid, ai=lambda p: "A tight summary.")
    preview = build_intent_preview(I_SUMMARIZE_TO_NOTE,
                                   "long rambling transcript", ctx)
    assert preview.created_note_preview["content"] == "A tight summary."
    assert db.get_all_notes(pid) == []               # preview only
    ok, _msg, op = apply_intent_preview(preview, ctx)
    assert ok is True
    notes = db.get_all_notes(pid)
    assert len(notes) == 1 and notes[0].content == "A tight summary."
    # Created-note undo works through the shared op record.
    assert undo_commit(op, ctx)[0] is True
    assert db.get_all_notes(pid) == []


def test_psyke_draft_requires_explicit_type_default_other():
    db = Database()
    pid = _project(db)
    ctx, _ed = _ctx(db, pid)
    preview = build_intent_preview(I_PSYKE_DRAFT,
                                   "Character: Maria the wanderer", ctx)
    assert preview.created_psyke_entry_preview["entry_type"] == "other"
    apply_intent_preview(preview, ctx)
    entries = db.get_all_psyke_entries(pid)
    assert entries[0].entry_type == "other"          # never auto-classified
    ctx.psyke_entry_type = "lore"
    preview2 = build_intent_preview(I_PSYKE_DRAFT, "the broken bell", ctx)
    assert preview2.created_psyke_entry_preview["entry_type"] == "lore"
    apply_intent_preview(preview2, ctx)
    assert {e.entry_type for e in db.get_all_psyke_entries(pid)} == \
        {"other", "lore"}


# ==========================================================================
# 27-35  Graphic Novel panel-field intents
# ==========================================================================


def test_gn_intent_disabled_without_panel():
    db = Database()
    pid, _sid = _gn_with_panel(db)
    ctx, _ed = _ctx(db, pid, "graphic_novel", gn_panel_ref=None)
    gn = _by_id(get_available_voice_intents(ctx), I_GN_PANEL_FIELD)
    assert gn.enabled is False
    assert gn.reason_if_disabled == "Select a Panel first."


@pytest.mark.parametrize("field", [f for f, _l in ir.GN_FIELD_CHOICES])
def test_gn_field_preview_apply_and_mirror(field):
    db = Database()
    pid, sid = _gn_with_panel(db)
    ctx, _ed = _ctx(db, pid, "graphic_novel", gn_panel_ref=(sid, 0, 0),
                    gn_field_choice=field)
    preview = build_intent_preview(I_GN_PANEL_FIELD, "spoken content", ctx)
    assert preview.can_apply is True
    assert preview.before_text == "" and preview.after_text == "spoken content"
    ok, _msg, op = apply_intent_preview(preview, ctx)
    assert ok is True
    panel = gnb.load_scene_script(db, sid).pages[0].panels[0]
    assert getattr(panel, field) == "spoken content"
    # Mirror: the Manuscript script block shows it too (same shared body).
    from logosforge.ui.graphic_novel_manuscript_view import (
        GraphicNovelManuscriptView)
    view = GraphicNovelManuscriptView(db, pid, on_data_changed=lambda: None)
    view.select_scene(sid)
    assert "spoken content" in view._field_editors[("panel", sid, 0, 0)].toPlainText()
    # Undo restores the previous (empty) field value.
    assert undo_commit(op, ctx)[0] is True
    panel = gnb.load_scene_script(db, sid).pages[0].panels[0]
    assert getattr(panel, field) == ""


def test_gn_intent_appends_to_existing_field():
    db = Database()
    pid, sid = _gn_with_panel(db)
    gno.set_panel_field(db, sid, 0, 0, "dialogue", "FIRST")
    ctx, _ed = _ctx(db, pid, "graphic_novel", gn_panel_ref=(sid, 0, 0),
                    gn_field_choice="dialogue")
    preview = build_intent_preview(I_GN_PANEL_FIELD, "SECOND", ctx)
    assert preview.before_text == "FIRST"
    apply_intent_preview(preview, ctx)
    panel = gnb.load_scene_script(db, sid).pages[0].panels[0]
    assert panel.dialogue == "FIRST\nSECOND"


# ==========================================================================
# 36-41  Panel UI integration
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


def test_ui_dictation_mode_is_default_with_commit_targets():
    _db, _pid, win = _ui_window()
    panel = win._voice_panel
    assert panel.voice_mode() == "dictation"
    assert panel._target_combo.isVisibleTo(panel) is True
    assert panel._intent_combo.isVisibleTo(panel) is False


def test_ui_intent_mode_shows_intent_controls():
    _db, _pid, win = _ui_window()
    panel = win._voice_panel
    panel._mode_combo.setCurrentIndex(1)             # Intent (opt-in)
    assert panel.voice_mode() == "intent"
    assert panel._intent_combo.isVisibleTo(panel) is True
    assert panel._intent_preview_btn.isVisibleTo(panel) is True
    ids = {panel._intent_combo.itemData(i)
           for i in range(panel._intent_combo.count())}
    assert I_CLEANUP in ids and I_PSYKE_DRAFT in ids


def test_ui_no_source_blocks_preview():
    _db, _pid, win = _ui_window()
    panel = win._voice_panel
    panel._mode_combo.setCurrentIndex(1)
    idx = panel._intent_combo.findData(I_CLEANUP)
    panel._intent_combo.setCurrentIndex(idx)
    panel._on_intent_preview()                       # nothing selected/typed
    assert panel._intent_apply_btn.isEnabled() is False
    assert "Select a transcript segment first." in \
        panel._intent_preview_area.toPlainText()


def test_ui_cleanup_preview_apply_updates_segment_without_mutation():
    db, pid, win = _ui_window()
    panel = win._voice_panel
    from logosforge.voice.types import TranscriptSegment
    panel._apply_final_segment(TranscriptSegment(
        text="hello   comma world period"))
    panel._mode_combo.setCurrentIndex(1)
    from PySide6.QtCore import Qt
    panel._history_list.item(0).setCheckState(Qt.CheckState.Checked)
    idx = panel._intent_combo.findData(I_CLEANUP)
    panel._intent_combo.setCurrentIndex(idx)
    win._dirty = False
    panel._on_intent_preview()
    assert panel._intent_apply_btn.isEnabled() is True
    assert "Hello, world." in panel._intent_preview_area.toPlainText()
    panel._on_intent_apply()
    assert panel._history.entries[0].text == "Hello, world."
    assert win._dirty is False                       # transcript-only op
    assert db.get_all_notes(pid) == []


def test_ui_psyke_intent_apply_marks_dirty_and_segments():
    db, pid, win = _ui_window()
    panel = win._voice_panel
    from logosforge.voice.types import TranscriptSegment
    panel._apply_final_segment(TranscriptSegment(text="a strange relic"))
    panel._mode_combo.setCurrentIndex(1)
    from PySide6.QtCore import Qt
    panel._history_list.item(0).setCheckState(Qt.CheckState.Checked)
    idx = panel._intent_combo.findData(I_PSYKE_DRAFT)
    panel._intent_combo.setCurrentIndex(idx)
    win._dirty = False
    panel._on_intent_preview()
    panel._on_intent_apply()
    assert len(db.get_all_psyke_entries(pid)) == 1
    assert win._dirty is True
    assert panel._history.entries[0].status == "committed"
    assert panel._undo_btn.isEnabled() is True       # intent undo wired


def test_ui_cancel_discards_preview_without_mutation():
    db, pid, win = _ui_window()
    panel = win._voice_panel
    from logosforge.voice.types import TranscriptSegment
    panel._apply_final_segment(TranscriptSegment(text="draft entry"))
    panel._mode_combo.setCurrentIndex(1)
    from PySide6.QtCore import Qt
    panel._history_list.item(0).setCheckState(Qt.CheckState.Checked)
    idx = panel._intent_combo.findData(I_PSYKE_DRAFT)
    panel._intent_combo.setCurrentIndex(idx)
    panel._on_intent_preview()
    panel._on_intent_cancel()
    assert panel._pending_intent_preview is None
    assert panel._intent_apply_btn.isEnabled() is False
    assert db.get_all_psyke_entries(pid) == []


def test_ui_intent_mode_creates_no_new_windows():
    _db, _pid, win = _ui_window()
    panel = win._voice_panel
    before = set(QApplication.topLevelWidgets())
    panel._mode_combo.setCurrentIndex(1)
    panel._on_intent_preview()
    new_visible = [w for w in (set(QApplication.topLevelWidgets()) - before)
                   if w.isVisible()]
    assert new_visible == []


# ==========================================================================
# 42-46  Safety guards
# ==========================================================================


def test_intent_router_has_no_shell_or_cloud_refs():
    import inspect
    src = inspect.getsource(ir).lower()
    for banned in ("subprocess", "os.system", "popen", "shutil.rmtree",
                   "openai", "requests.", "urllib.request", "ngrok",
                   "comfyui", "img2img", "txt2img"):
        assert banned not in src, banned


def test_ai_receives_text_only_never_bytes():
    db = Database()
    pid = _project(db)
    prompts = []
    ctx, editor = _ctx(db, pid, ai=lambda p: prompts.append(p) or "OUT",
                       editor=True)
    editor.setPlainText("selected words")
    _select_all(editor)
    build_intent_preview(I_REWRITE_SELECTION, "instruction", ctx)
    build_intent_preview(I_SUMMARIZE_TO_NOTE, "transcript text", ctx)
    assert prompts and all(isinstance(p, str) for p in prompts)


def test_no_auto_apply_every_intent_requires_confirmation():
    db = Database()
    pid = _project(db)
    ctx, _ed = _ctx(db, pid, ai=lambda p: "X", editor=True)
    for intent in get_available_voice_intents(ctx):
        assert intent.requires_confirmation is True
