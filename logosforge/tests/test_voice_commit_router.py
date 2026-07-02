"""Voice MVP Phase 2 — safe, mode-aware transcript commit targets.

The Voice Commit Router lists explicit commit destinations per writing mode
(disabled-with-reason when unavailable), validates against the live context,
and executes only on explicit commit: cursor insert, New Note, PSYKE draft
entry (user-chosen type, default Other, never classified), Graphic Novel
panel fields (selected Panel only), Screenplay Action / Dialogue and Stage
Direction / Dialogue (manually chosen character, never guessed). Listing
never mutates; a transcript can never commit into a different project than it
was captured in; Outline/append targets stay disabled with reasons. All
headless, mock backend only — no cloud, no audio leaves the machine.
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
from logosforge.voice import commit_router as router
from logosforge.voice.commit_router import (
    T_CURSOR,
    T_GN_CAPTION,
    T_GN_DIALOGUE,
    T_GN_NOTES,
    T_GN_SFX,
    T_GN_VISUAL,
    T_MANUSCRIPT_APPEND,
    T_NOTE,
    T_OUTLINE,
    T_PSYKE,
    T_SERIES_EPISODE_OUTLINE,
    T_SP_ACTION,
    T_SP_DIALOGUE,
    T_STAGE_DIALOGUE,
    T_STAGE_DIRECTION,
    VoiceCommitContext,
    commit_transcript,
    get_available_voice_commit_targets,
    preview_commit_target,
    validate_voice_commit_target,
)
from logosforge.voice.editor_commit import EditorCommitTarget
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


def _editor_ctx(db, pid, mode, **over):
    editor = QTextEdit()
    tgt = EditorCommitTarget()
    tgt.note_focus(editor)
    ctx = VoiceCommitContext(
        db=db, project_id=pid, writing_mode=mode,
        has_active_editor=True, insert_at_cursor=tgt.insert_as_plain_text,
        **over)
    return ctx, editor


def _ids(targets):
    return {t.id for t in targets}


def _by_id(targets, tid):
    return next(t for t in targets if t.id == tid)


def _gn_with_panel(db):
    pid = _project(db, "graphic_novel")
    sid = ss.create_scene(db, pid, act="Act 1", chapter="Chapter 1",
                          title="S").id
    gno.add_page(db, sid)
    gno.add_panel(db, sid, 0)
    return pid, sid


# ==========================================================================
# 1-7  Target listing per mode (read-only)
# ==========================================================================


def test_novel_targets_safe_set():
    db = Database()
    pid = _project(db, "novel")
    ctx, _ed = _editor_ctx(db, pid, "novel")
    targets = get_available_voice_commit_targets(ctx)
    assert {T_CURSOR, T_NOTE, T_PSYKE} <= _ids(targets)
    assert _by_id(targets, T_CURSOR).enabled is True
    assert _by_id(targets, T_NOTE).enabled is True
    assert _by_id(targets, T_PSYKE).enabled is True
    # Deferred targets are listed disabled WITH a reason — never hidden magic.
    assert _by_id(targets, T_OUTLINE).enabled is False
    assert "Outline voice target not available yet." == \
        _by_id(targets, T_OUTLINE).reason_if_disabled
    assert _by_id(targets, T_MANUSCRIPT_APPEND).enabled is False
    assert _by_id(targets, T_MANUSCRIPT_APPEND).reason_if_disabled


def test_screenplay_targets():
    db = Database()
    pid = _project(db, "screenplay")
    ctx, _ed = _editor_ctx(db, pid, "screenplay")
    targets = get_available_voice_commit_targets(ctx)
    assert _by_id(targets, T_SP_ACTION).enabled is True
    dlg = _by_id(targets, T_SP_DIALOGUE)
    assert dlg.enabled is False                     # no character chosen yet
    assert dlg.reason_if_disabled == "Pick a character first."
    ctx.character_name = "MARIA"
    assert _by_id(get_available_voice_commit_targets(ctx),
                  T_SP_DIALOGUE).enabled is True


def test_gn_targets_with_selected_panel():
    db = Database()
    pid, sid = _gn_with_panel(db)
    ctx = VoiceCommitContext(db=db, project_id=pid,
                             writing_mode="graphic_novel",
                             gn_panel_ref=(sid, 0, 0))
    targets = get_available_voice_commit_targets(ctx)
    for tid in (T_GN_VISUAL, T_GN_CAPTION, T_GN_DIALOGUE, T_GN_SFX,
                T_GN_NOTES):
        target = _by_id(targets, tid)
        assert target.enabled is True
        assert target.target_ref == (sid, 0, 0)


def test_gn_targets_disabled_without_panel():
    db = Database()
    pid, _sid = _gn_with_panel(db)
    ctx = VoiceCommitContext(db=db, project_id=pid,
                             writing_mode="graphic_novel", gn_panel_ref=None)
    targets = get_available_voice_commit_targets(ctx)
    for tid in (T_GN_VISUAL, T_GN_CAPTION, T_GN_DIALOGUE, T_GN_SFX,
                T_GN_NOTES):
        target = _by_id(targets, tid)
        assert target.enabled is False
        assert target.reason_if_disabled == "Select a Panel first."


def test_stage_targets():
    db = Database()
    pid = _project(db, "stage_script")
    ctx, _ed = _editor_ctx(db, pid, "stage_script")
    targets = get_available_voice_commit_targets(ctx)
    assert _by_id(targets, T_STAGE_DIRECTION).enabled is True
    assert _by_id(targets, T_STAGE_DIALOGUE).enabled is False
    ctx.character_name = "HELENA"
    assert _by_id(get_available_voice_commit_targets(ctx),
                  T_STAGE_DIALOGUE).enabled is True


def test_series_targets():
    db = Database()
    pid = _project(db, "series")
    ctx, _ed = _editor_ctx(db, pid, "series")
    targets = get_available_voice_commit_targets(ctx)
    assert _by_id(targets, T_CURSOR).enabled is True   # selected-scene editor
    ep = _by_id(targets, T_SERIES_EPISODE_OUTLINE)
    assert ep.enabled is False
    assert ep.reason_if_disabled == "Outline voice target not available yet."


def test_listing_and_preview_do_not_mutate():
    db = Database()
    pid, sid = _gn_with_panel(db)
    before_scene = db.get_scene_by_id(sid).content
    before_notes = len(db.get_all_notes(pid))
    ctx = VoiceCommitContext(db=db, project_id=pid,
                             writing_mode="graphic_novel",
                             gn_panel_ref=(sid, 0, 0))
    get_available_voice_commit_targets(ctx)
    validate_voice_commit_target(T_GN_VISUAL, ctx)
    preview_commit_target(T_NOTE, ctx)
    assert db.get_scene_by_id(sid).content == before_scene
    assert len(db.get_all_notes(pid)) == before_notes


# ==========================================================================
# 8-13  Commit safety (project id, deleted target, no editor, dirty, clear)
# ==========================================================================


def test_commit_validates_project_id_and_blocks_on_change():
    db = Database()
    pid_a = _project(db, "novel")
    pid_b = _project(db, "novel")
    ctx, ed = _editor_ctx(db, pid_b, "novel",
                          transcript_project_id=pid_a)   # captured in A
    ok, msg = commit_transcript("stale words", T_CURSOR, ctx)
    assert ok is False
    assert msg == ("Project changed since transcription. Review before "
                   "committing.")
    assert ed.toPlainText() == ""                  # nothing inserted


def test_commit_same_project_passes():
    db = Database()
    pid = _project(db, "novel")
    ctx, ed = _editor_ctx(db, pid, "novel", transcript_project_id=pid)
    ok, msg = commit_transcript("fresh words", T_CURSOR, ctx)
    assert ok is True and "fresh words" in ed.toPlainText()


def test_deleted_panel_blocks_commit():
    db = Database()
    pid, sid = _gn_with_panel(db)
    ctx = VoiceCommitContext(db=db, project_id=pid,
                             writing_mode="graphic_novel",
                             gn_panel_ref=(sid, 0, 5))   # no such panel
    ok, msg = commit_transcript("text", T_GN_VISUAL, ctx)
    assert ok is False and msg == "Select a Panel first."


def test_no_active_editor_disables_cursor_target():
    db = Database()
    pid = _project(db, "novel")
    ctx = VoiceCommitContext(db=db, project_id=pid, writing_mode="novel",
                             has_active_editor=False)
    target = _by_id(get_available_voice_commit_targets(ctx), T_CURSOR)
    assert target.enabled is False
    assert target.reason_if_disabled == "Click into an editor first."
    ok, _msg = commit_transcript("text", T_CURSOR, ctx)
    assert ok is False


def test_successful_db_commit_marks_segment_and_message():
    db = Database()
    pid = _project(db, "novel")
    ctx = VoiceCommitContext(db=db, project_id=pid, writing_mode="novel")
    seg = TranscriptSegment(text="remember the lighthouse")
    ok, msg = commit_transcript(seg, T_NOTE, ctx)
    assert ok is True
    assert "committed" in msg.lower()
    assert seg.committed is True
    assert seg.committed_target == T_NOTE
    assert seg.committed_at is not None


def test_empty_transcript_never_commits():
    db = Database()
    pid = _project(db, "novel")
    ctx = VoiceCommitContext(db=db, project_id=pid, writing_mode="novel")
    ok, msg = commit_transcript("   ", T_NOTE, ctx)
    assert ok is False and msg == "Nothing to commit."
    assert db.get_all_notes(pid) == []


# ==========================================================================
# 14-17  Notes / Outline / PSYKE
# ==========================================================================


def test_note_created_only_on_explicit_commit():
    db = Database()
    pid = _project(db, "novel")
    ctx = VoiceCommitContext(db=db, project_id=pid, writing_mode="novel")
    get_available_voice_commit_targets(ctx)        # listing creates nothing
    assert db.get_all_notes(pid) == []
    ok, _msg = commit_transcript("a thought worth keeping", T_NOTE, ctx)
    assert ok is True
    notes = db.get_all_notes(pid)
    assert len(notes) == 1
    assert notes[0].title.startswith("Voice note")
    assert notes[0].content == "a thought worth keeping"


def test_outline_draft_blocked_with_reason():
    db = Database()
    pid = _project(db, "novel")
    ctx = VoiceCommitContext(db=db, project_id=pid, writing_mode="novel")
    ok, msg = commit_transcript("beat idea", T_OUTLINE, ctx)
    assert ok is False
    assert msg == "Outline voice target not available yet."


def test_psyke_draft_defaults_other_and_respects_choice():
    db = Database()
    pid = _project(db, "novel")
    ctx = VoiceCommitContext(db=db, project_id=pid, writing_mode="novel")
    ok, _msg = commit_transcript("a mysterious lantern", T_PSYKE, ctx)
    assert ok is True
    entries = db.get_all_psyke_entries(pid)
    assert len(entries) == 1 and entries[0].entry_type == "other"
    ctx.psyke_entry_type = "place"
    commit_transcript("the drowned chapel", T_PSYKE, ctx)
    types = {e.entry_type for e in db.get_all_psyke_entries(pid)}
    assert types == {"other", "place"}


def test_psyke_never_auto_classifies():
    # A transcript that SCREAMS "character" still lands as the user's chosen
    # type (default Other) — content is never inspected for classification.
    db = Database()
    pid = _project(db, "novel")
    ctx = VoiceCommitContext(db=db, project_id=pid, writing_mode="novel")
    commit_transcript("Character: Maria, the protagonist of the story",
                      T_PSYKE, ctx)
    entries = db.get_all_psyke_entries(pid)
    assert entries[0].entry_type == "other"
    ctx.psyke_entry_type = "starship"               # unknown -> safe default
    commit_transcript("another entry", T_PSYKE, ctx)
    assert {e.entry_type for e in db.get_all_psyke_entries(pid)} == {"other"}


# ==========================================================================
# 18-23  Graphic Novel panel commits + mirroring
# ==========================================================================


@pytest.mark.parametrize("target_id,field", [
    (T_GN_VISUAL, "visual_description"),
    (T_GN_CAPTION, "caption"),
    (T_GN_DIALOGUE, "dialogue"),
    (T_GN_SFX, "sfx"),
    (T_GN_NOTES, "notes"),
])
def test_gn_panel_field_commit(target_id, field):
    db = Database()
    pid, sid = _gn_with_panel(db)
    ctx = VoiceCommitContext(db=db, project_id=pid,
                             writing_mode="graphic_novel",
                             gn_panel_ref=(sid, 0, 0))
    ok, msg = commit_transcript("spoken into the panel", target_id, ctx)
    assert ok is True and "committed" in msg.lower()
    panel = gnb.load_scene_script(db, sid).pages[0].panels[0]
    assert getattr(panel, field) == "spoken into the panel"


def test_gn_panel_commit_appends_not_overwrites():
    db = Database()
    pid, sid = _gn_with_panel(db)
    gno.set_panel_field(db, sid, 0, 0, "dialogue", "FIRST LINE")
    ctx = VoiceCommitContext(db=db, project_id=pid,
                             writing_mode="graphic_novel",
                             gn_panel_ref=(sid, 0, 0))
    commit_transcript("SECOND LINE", T_GN_DIALOGUE, ctx)
    panel = gnb.load_scene_script(db, sid).pages[0].panels[0]
    assert panel.dialogue == "FIRST LINE\nSECOND LINE"


def test_gn_commit_mirrors_in_manuscript_and_outline():
    db = Database()
    pid, sid = _gn_with_panel(db)
    ctx = VoiceCommitContext(db=db, project_id=pid,
                             writing_mode="graphic_novel",
                             gn_panel_ref=(sid, 0, 0))
    commit_transcript("MIRRORED-BY-VOICE", T_GN_VISUAL, ctx)
    # Manuscript script block shows it…
    from logosforge.ui.graphic_novel_manuscript_view import (
        GraphicNovelManuscriptView)
    view = GraphicNovelManuscriptView(db, pid, on_data_changed=lambda: None)
    view.select_scene(sid)
    block = view._field_editors[("panel", sid, 0, 0)]
    assert "MIRRORED-BY-VOICE" in block.toPlainText()
    # …and the Outline snippet reads the same shared body.
    script = gnb.load_scene_script(db, sid)
    assert gno.panel_snippet(script.pages[0].panels[0]).startswith(
        "MIRRORED-BY-VOICE"[:10])


def test_gn_manuscript_tracks_selected_panel_for_voice():
    db = Database()
    pid, sid = _gn_with_panel(db)
    gno.add_panel(db, sid, 0)                       # second panel
    from logosforge.ui.graphic_novel_manuscript_view import (
        GraphicNovelManuscriptView)
    view = GraphicNovelManuscriptView(db, pid, on_data_changed=lambda: None)
    view.select_scene(sid)
    assert view.current_panel_ref() is None         # nothing focused yet
    view.select_panel(0, 1)
    assert view.current_panel_ref() == (sid, 0, 1)


# ==========================================================================
# 24-27  Screenplay / Stage insertion formats
# ==========================================================================


def test_screenplay_raw_insert_works():
    db = Database()
    pid = _project(db, "screenplay")
    ctx, ed = _editor_ctx(db, pid, "screenplay")
    ok, _msg = commit_transcript("plain words", T_CURSOR, ctx)
    assert ok is True and ed.toPlainText() == "plain words"


def test_screenplay_action_insert():
    db = Database()
    pid = _project(db, "screenplay")
    ctx, ed = _editor_ctx(db, pid, "screenplay")
    ok, _msg = commit_transcript("She bolts the door.", T_SP_ACTION, ctx)
    assert ok is True
    assert "\n\nShe bolts the door.\n\n" in ed.toPlainText()


def test_screenplay_dialogue_requires_manual_character():
    db = Database()
    pid = _project(db, "screenplay")
    ctx, ed = _editor_ctx(db, pid, "screenplay")
    ok, msg = commit_transcript("We have to move.", T_SP_DIALOGUE, ctx)
    assert ok is False and msg == "Pick a character first."
    assert ed.toPlainText() == ""
    ctx.character_name = "Maria"
    ok, _msg = commit_transcript("We have to move.", T_SP_DIALOGUE, ctx)
    assert ok is True
    assert "MARIA\nWe have to move." in ed.toPlainText()   # cue + dialogue


def test_no_character_guessing_from_transcript():
    # Even a transcript that LOOKS like "NAME: line" is never split/guessed —
    # the chosen character is the only cue source.
    db = Database()
    pid = _project(db, "screenplay")
    ctx, ed = _editor_ctx(db, pid, "screenplay")
    ctx.character_name = "ZAMPANO"
    commit_transcript("MARIA: ignore this name", T_SP_DIALOGUE, ctx)
    text = ed.toPlainText()
    assert "ZAMPANO\nMARIA: ignore this name" in text


def test_stage_direction_and_dialogue_formats():
    db = Database()
    pid = _project(db, "stage_script")
    ctx, ed = _editor_ctx(db, pid, "stage_script")
    commit_transcript("Lights dim slowly.", T_STAGE_DIRECTION, ctx)
    assert "STAGE: Lights dim slowly." in ed.toPlainText()
    ctx.character_name = "Helena"
    commit_transcript("Who goes there?", T_STAGE_DIALOGUE, ctx)
    assert "CHARACTER: HELENA\nWho goes there?" in ed.toPlainText()


# ==========================================================================
# 28-32  Panel UI integration
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
    return db, pid, win


def test_ui_no_transcript_disables_commit_and_targets():
    _db, _pid, win = _ui_window()
    win._toggle_voice_panel()
    panel = win._voice_panel
    assert panel._commit_btn.isEnabled() is False
    assert panel._target_combo.isEnabled() is False


def test_ui_transcript_ready_enables_target_dropdown():
    _db, _pid, win = _ui_window()
    win._toggle_voice_panel()
    panel = win._voice_panel
    panel._preview.setPlainText("ready words")
    assert panel._target_combo.isEnabled() is True
    assert panel._target_combo.count() >= 5
    ids = {panel._target_combo.itemData(i)
           for i in range(panel._target_combo.count())}
    assert {T_CURSOR, T_NOTE, T_PSYKE} <= ids


def test_ui_unavailable_target_shown_disabled_with_reason():
    _db, _pid, win = _ui_window()
    win._toggle_voice_panel()
    panel = win._voice_panel
    panel._preview.setPlainText("ready words")
    idx = panel._target_combo.findData(T_OUTLINE)
    assert idx >= 0
    item = panel._target_combo.model().item(idx)
    assert not item.isEnabled()
    assert "Outline voice target not available yet." in item.toolTip()


def test_ui_commit_to_note_updates_status_and_marks_dirty():
    db, pid, win = _ui_window()
    win._toggle_voice_panel()
    panel = win._voice_panel
    panel._preview.setPlainText("note me")
    idx = panel._target_combo.findData(T_NOTE)
    panel._target_combo.setCurrentIndex(idx)
    win._dirty = False
    assert panel.commit() is True
    assert "committed" in panel._status_label.text().lower()
    assert len(db.get_all_notes(pid)) == 1
    assert win._dirty is True                       # dirty only AFTER commit


def test_ui_clear_does_not_mutate_project():
    db, pid, win = _ui_window()
    win._toggle_voice_panel()
    panel = win._voice_panel
    panel._preview.setPlainText("disposable")
    win._dirty = False
    panel.clear_preview()
    assert panel._preview.toPlainText() == ""
    assert win._dirty is False
    assert db.get_all_notes(pid) == []


def test_ui_psyke_selector_default_other_and_visibility():
    _db, _pid, win = _ui_window()
    win._toggle_voice_panel()
    panel = win._voice_panel
    panel._preview.setPlainText("an entry")
    assert panel._psyke_type.currentData() == "other"   # default Other
    idx = panel._target_combo.findData(T_PSYKE)
    panel._target_combo.setCurrentIndex(idx)
    assert panel._psyke_type.isVisibleTo(panel) is True
    idx = panel._target_combo.findData(T_NOTE)
    panel._target_combo.setCurrentIndex(idx)
    assert panel._psyke_type.isVisibleTo(panel) is False


def test_ui_cursor_target_keeps_mvp_behavior():
    _db, _pid, win = _ui_window()
    win._toggle_voice_panel()
    panel = win._voice_panel
    editor = QTextEdit()
    win._voice_commit.note_focus(editor)
    panel._preview.setPlainText("cursor words")
    idx = panel._target_combo.findData(T_CURSOR)
    panel._target_combo.setCurrentIndex(idx)
    assert panel.commit() is True
    assert editor.toPlainText() == "cursor words"


def test_ui_project_switch_blocks_stale_transcript():
    db, pid, win = _ui_window()
    b = db.create_project("B", narrative_engine="novel").id
    win._toggle_voice_panel()
    panel = win._voice_panel
    panel._apply_final_text("captured in project A")    # captures project id
    assert panel._transcript_project_id == pid
    win._switch_project(b)
    panel._preview.setPlainText("captured in project A")  # still pending
    panel._transcript_project_id = pid                   # (stale capture)
    idx = panel._target_combo.findData(T_NOTE)
    if idx < 0:
        panel._refresh_targets()
        idx = panel._target_combo.findData(T_NOTE)
    panel._target_combo.setCurrentIndex(idx)
    assert panel.commit() is False
    assert "Project changed" in panel._status_label.text()
    assert db.get_all_notes(b) == []                     # nothing leaked


def test_ui_copy_button_and_no_new_windows():
    _db, _pid, win = _ui_window()
    win._toggle_voice_panel()
    panel = win._voice_panel
    panel._preview.setPlainText("copy me")
    before = set(QApplication.topLevelWidgets())
    panel._copy_btn.click()
    assert QApplication.clipboard().text() == "copy me"
    new_visible = [w for w in (set(QApplication.topLevelWidgets()) - before)
                   if w.isVisible()]
    assert new_visible == []                             # no extra windows


def test_segment_model_fields_and_audio_retention():
    seg = TranscriptSegment(text="hello")
    assert seg.id and seg.created_at > 0
    assert seg.source == "local_whisper"
    assert seg.committed is False and seg.committed_target == ""
    # Phase 3 retry keeps the PCM in MEMORY only (session-scoped): default
    # None, repr-suppressed, and no path/file fields exist that could ever
    # persist audio to disk.
    assert seg.audio_bytes is None
    assert "audio_bytes" not in repr(seg)
    assert not any("path" in f or "file" in f for f in vars(seg))


def test_router_module_has_no_cloud_or_llm_refs():
    import inspect
    src = inspect.getsource(router).lower()
    for banned in ("openai", "anthropic", "requests.", "urllib.request",
                   "ngrok", "comfyui"):
        assert banned not in src, banned
