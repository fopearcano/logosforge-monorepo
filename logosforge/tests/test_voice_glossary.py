"""Voice MVP Phase 7 — Project Voice Glossary + local correction layer.

Project-scoped glossary terms (names/places/lore/invented words + known
Whisper slips + spoken punctuation) drive conservative, review-first
transcript corrections: suggestions never mutate, applying changes the
TRANSCRIPT text only (commits still go through the router), learning a
correction pair is always confirmed, PSYKE/Outline imports are read-only
on their sources, and nothing crosses projects. All local — no AI needed,
no audio, no secrets.
"""

from __future__ import annotations

import warnings

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

warnings.filterwarnings("ignore")

from logosforge.db import Database
from logosforge import story_structure as ss
from logosforge.ui import safe_dialogs
from logosforge.voice import glossary as vg
from logosforge.voice.glossary import (
    apply_selected_corrections,
    build_import_candidates,
    diff_correction_pairs,
    import_candidates,
    learn_correction,
    suggest_transcript_corrections,
    validate_glossary_term,
)
from logosforge.voice.history import S_CORRECTED, VoiceTranscriptHistory
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


# ==========================================================================
# 1-8  Glossary model
# ==========================================================================


def test_term_crud_and_fields():
    db = Database()
    pid = _project(db)
    term = db.create_voice_glossary_term(
        pid, "Zampanò", spoken_forms="zampano\nzampanoh",
        common_misrecognitions="Zampano", category="character",
        source="manual")
    assert term.id and term.project_id == pid
    loaded = db.get_voice_glossary_terms(pid)[0]
    assert loaded.canonical_text == "Zampanò"
    assert vg._forms(loaded.spoken_forms) == ["zampano", "zampanoh"]
    assert vg._forms(loaded.common_misrecognitions) == ["Zampano"]
    assert loaded.category == "character" and loaded.source == "manual"
    db.update_voice_glossary_term(term.id, canonical_text="Zampanò!",
                                  enabled=False)
    updated = db.get_voice_glossary_terms(pid)[0]
    assert updated.canonical_text == "Zampanò!" and updated.enabled is False
    db.delete_voice_glossary_term(term.id)
    assert db.get_voice_glossary_terms(pid) == []


def test_terms_do_not_leak_across_projects():
    db = Database()
    a = _project(db)
    b = _project(db)
    db.create_voice_glossary_term(a, "Fossapicca",
                                  common_misrecognitions="Fossapika")
    assert db.get_voice_glossary_terms(b) == []
    assert suggest_transcript_corrections(db, b, "Fossapika at dawn") == []


def test_validate_glossary_term():
    assert validate_glossary_term("Zampanò") == (True, "")
    ok, reason = validate_glossary_term("   ")
    assert ok is False and reason


# ==========================================================================
# 9-18  Correction engine
# ==========================================================================


def test_exact_misrecognition_suggestion():
    db = Database()
    pid = _project(db)
    db.create_voice_glossary_term(pid, "Fossapicca",
                                  common_misrecognitions="Fossapika")
    suggestions = suggest_transcript_corrections(
        db, pid, "Zampano walks into Fossapika.",
        spoken_punctuation=False)
    assert [(s.original_text, s.replacement_text, s.source)
            for s in suggestions] == \
        [("Fossapika", "Fossapicca", "misrecognition")]


def test_spoken_form_suggestion():
    db = Database()
    pid = _project(db)
    db.create_voice_glossary_term(pid, "Zampanò", spoken_forms="zampano")
    suggestions = suggest_transcript_corrections(
        db, pid, "then Zampano barked", spoken_punctuation=False)
    assert suggestions[0].replacement_text == "Zampanò"
    assert suggestions[0].source == "spoken_form"


def test_whole_word_only_avoids_inside_word_mutation():
    db = Database()
    pid = _project(db)
    db.create_voice_glossary_term(pid, "Ana", common_misrecognitions="ana")
    suggestions = suggest_transcript_corrections(
        db, pid, "banana bandana ana", spoken_punctuation=False)
    assert len(suggestions) == 1
    assert suggestions[0].start_offset == len("banana bandana ")


def test_canonical_case_normalization():
    db = Database()
    pid = _project(db)
    db.create_voice_glossary_term(pid, "Bagnaskiz")
    suggestions = suggest_transcript_corrections(
        db, pid, "bagnaskiz rises", spoken_punctuation=False)
    assert suggestions[0].source == "canonical_case"
    assert suggestions[0].replacement_text == "Bagnaskiz"


def test_disabled_term_produces_no_suggestion():
    db = Database()
    pid = _project(db)
    term = db.create_voice_glossary_term(pid, "Fossapicca",
                                         common_misrecognitions="Fossapika")
    db.update_voice_glossary_term(term.id, enabled=False)
    assert suggest_transcript_corrections(
        db, pid, "Fossapika", spoken_punctuation=False) == []


def test_punctuation_phrase_suggestions():
    db = Database()
    pid = _project(db)
    suggestions = suggest_transcript_corrections(
        db, pid, "hello comma world period new paragraph done")
    sources = {s.source for s in suggestions}
    assert sources == {"punctuation"}
    text = apply_selected_corrections(
        "hello comma world period new paragraph done", suggestions)
    assert text == "hello, world.\n\ndone"


def test_fuzzy_disabled_by_default_enabled_is_cautious():
    db = Database()
    pid = _project(db)
    db.create_voice_glossary_term(pid, "Fossapicca")
    assert suggest_transcript_corrections(
        db, pid, "Fossapica gate", spoken_punctuation=False) == []
    fuzzy = suggest_transcript_corrections(
        db, pid, "Fossapica gate", spoken_punctuation=False, fuzzy=True)
    assert fuzzy and fuzzy[0].source == "fuzzy"
    assert fuzzy[0].replacement_text == "Fossapicca"
    assert fuzzy[0].confidence and fuzzy[0].confidence >= 0.84


def test_apply_only_selected_and_drift_guard():
    db = Database()
    pid = _project(db)
    db.create_voice_glossary_term(pid, "Zampanò",
                                  common_misrecognitions="Zampano")
    db.create_voice_glossary_term(pid, "Fossapicca",
                                  common_misrecognitions="Fossapika")
    text = "Zampano walks into Fossapika."
    suggestions = suggest_transcript_corrections(db, pid, text,
                                                 spoken_punctuation=False)
    assert len(suggestions) == 2
    only_first = [suggestions[0]]
    out = apply_selected_corrections(text, only_first)
    assert out == "Zampanò walks into Fossapika."     # second untouched
    assert suggestions[0].applied is True
    # Drift guard: applying the (now stale) second suggestion to OTHER text
    # changes nothing.
    assert apply_selected_corrections("totally different", [suggestions[1]]) \
        == "totally different"


def test_rejecting_suggestions_mutates_nothing():
    db = Database()
    pid = _project(db)
    db.create_voice_glossary_term(pid, "Zampanò",
                                  common_misrecognitions="Zampano")
    text = "Zampano speaks"
    _ = suggest_transcript_corrections(db, pid, text,
                                       spoken_punctuation=False)
    assert text == "Zampano speaks"                    # untouched


# ==========================================================================
# 19-23  Transcript history integration
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


def test_final_transcript_generates_suggestions_and_count_label():
    db, pid, win = _ui_window()
    db.create_voice_glossary_term(pid, "Zampanò",
                                  common_misrecognitions="Zampano")
    panel = win._voice_panel
    panel._apply_final_segment(TranscriptSegment(text="Zampano arrives"))
    entry = panel._history.entries[0]
    assert len(entry.corrections) == 1
    assert "1 suggestion(s)" in panel._history_list.item(0).text()
    panel._history_list.setCurrentRow(0)
    assert "1 glossary suggestion(s)" in panel._glossary_info.text()


def test_apply_corrections_marks_corrected_and_commit_uses_text():
    from logosforge.voice.commit_router import T_NOTE
    db, pid, win = _ui_window()
    db.create_voice_glossary_term(pid, "Zampanò",
                                  common_misrecognitions="Zampano")
    panel = win._voice_panel
    panel._apply_final_segment(TranscriptSegment(text="Zampano arrives"))
    panel._history_list.setCurrentRow(0)
    panel._on_corrections_apply()                      # all checked by default
    entry = panel._history.entries[0]
    assert entry.status == S_CORRECTED
    assert entry.text == "Zampanò arrives"
    assert entry.original_text == "Zampano arrives"    # original preserved
    panel._history_list.item(0).setCheckState(Qt.CheckState.Checked)
    idx = panel._target_combo.findData(T_NOTE)
    panel._target_combo.setCurrentIndex(idx)
    assert panel.commit() is True
    assert db.get_all_notes(pid)[0].content == "Zampanò arrives"


def test_committed_segment_not_auto_mutated():
    db, pid, win = _ui_window()
    panel = win._voice_panel
    h = panel._history
    entry = h.add_final_segment(TranscriptSegment(text="locked words"),
                                project_id=pid, writing_mode="novel")
    h.mark_committed([entry.id], "note")
    assert h.apply_corrections(entry.id, "changed") is False
    assert entry.text == "locked words"


def test_reject_button_clears_suggestions():
    db, pid, win = _ui_window()
    db.create_voice_glossary_term(pid, "Zampanò",
                                  common_misrecognitions="Zampano")
    panel = win._voice_panel
    panel._apply_final_segment(TranscriptSegment(text="Zampano waits"))
    panel._history_list.setCurrentRow(0)
    panel._on_corrections_reject()
    assert panel._history.entries[0].corrections == []
    assert panel._history.entries[0].text == "Zampano waits"  # unchanged


# ==========================================================================
# 24-27  Learning
# ==========================================================================


def test_diff_correction_pairs():
    pairs = diff_correction_pairs("Bagnaskis walks home",
                                  "Bagnaskiz walks home")
    assert pairs == [("Bagnaskis", "Bagnaskiz")]
    assert diff_correction_pairs("same words", "same words") == []


def test_learn_correction_project_scoped_and_deduped():
    db = Database()
    a = _project(db)
    b = _project(db)
    term = learn_correction(db, a, "Bagnaskis", "Bagnaskiz",
                            category="character")
    assert term.source == "learned_from_correction"
    assert db.get_voice_glossary_terms(b) == []        # project-scoped
    again = learn_correction(db, a, "Bagnaskies", "Bagnaskiz")
    slips = vg._forms(again.common_misrecognitions)
    assert slips == ["Bagnaskis", "Bagnaskies"]        # appended, no dupe
    assert len(db.get_voice_glossary_terms(a)) == 1
    # The learned term now corrects future transcripts.
    suggestions = suggest_transcript_corrections(
        db, a, "Bagnaskis returns", spoken_punctuation=False)
    assert suggestions[0].replacement_text == "Bagnaskiz"


def test_learning_requires_confirmation(monkeypatch):
    db, pid, win = _ui_window()
    panel = win._voice_panel
    panel._apply_final_segment(TranscriptSegment(text="Bagnaskis speaks"))
    panel._history_list.setCurrentRow(0)
    panel._history.edit(panel._history.entries[0].id, "Bagnaskiz speaks")
    monkeypatch.setattr(safe_dialogs, "question", lambda *a, **k: False)
    panel._on_glossary_learn()                          # user declines
    assert db.get_voice_glossary_terms(pid) == []
    monkeypatch.setattr(safe_dialogs, "question", lambda *a, **k: True)
    panel._on_glossary_learn()                          # user confirms
    terms = db.get_voice_glossary_terms(pid)
    assert len(terms) == 1 and terms[0].canonical_text == "Bagnaskiz"


# ==========================================================================
# 28-32  Import from PSYKE / Outline (read-only on sources)
# ==========================================================================


def test_import_candidates_from_psyke_and_outline_no_mutation():
    db = Database()
    pid = _project(db)
    db.create_psyke_entry(pid, "Zampanò", entry_type="character")
    db.create_psyke_entry(pid, "Fossapicca", entry_type="place")
    db.create_character(pid, "Maria")
    ss.create_scene(db, pid, act="Act 1", chapter="Chapter 1",
                    title="The Drowned Chapel")
    before_psyke = len(db.get_all_psyke_entries(pid))
    before_scenes = len(ss.list_scenes(db, pid))
    candidates = build_import_candidates(db, pid)
    names = {c["canonical_text"] for c in candidates}
    assert {"Zampanò", "Fossapicca", "Maria", "The Drowned Chapel"} <= names
    by_name = {c["canonical_text"]: c for c in candidates}
    assert by_name["Zampanò"]["category"] == "character"
    assert by_name["Fossapicca"]["category"] == "place"
    assert by_name["The Drowned Chapel"]["source"] == "imported_from_outline"
    created = import_candidates(db, pid, candidates)
    assert created == len(candidates)
    # Sources untouched; re-import does not duplicate.
    assert len(db.get_all_psyke_entries(pid)) == before_psyke
    assert len(ss.list_scenes(db, pid)) == before_scenes
    assert build_import_candidates(db, pid) == []
    assert import_candidates(db, pid, candidates) == 0


def test_dialog_import_requires_confirmation(monkeypatch):
    db, pid, win = _ui_window()
    db.create_psyke_entry(pid, "Zampanò", entry_type="character")
    from logosforge.ui.voice_glossary_dialog import VoiceGlossaryDialog
    dlg = VoiceGlossaryDialog(db, pid, parent=win)
    monkeypatch.setattr(safe_dialogs, "question", lambda *a, **k: False)
    monkeypatch.setattr(safe_dialogs, "information", lambda *a, **k: None)
    dlg._on_import()                                    # declined
    assert db.get_voice_glossary_terms(pid) == []
    monkeypatch.setattr(safe_dialogs, "question", lambda *a, **k: True)
    dlg._on_import()                                    # confirmed
    assert len(db.get_voice_glossary_terms(pid)) == 1
    assert dlg.parent() is win                          # parented, safe


# ==========================================================================
# 33-40  Project safety + UI
# ==========================================================================


def test_project_mismatch_blocks_correction_apply():
    db, pid, win = _ui_window()
    b = db.create_project("B", narrative_engine="novel").id
    db.create_voice_glossary_term(pid, "Zampanò",
                                  common_misrecognitions="Zampano")
    panel = win._voice_panel
    panel._apply_final_segment(TranscriptSegment(text="Zampano arrives"))
    win._switch_project(b)
    panel._refresh_history_ui()
    panel._history_list.setCurrentRow(0)
    panel._on_corrections_apply()
    assert vg.PROJECT_MISMATCH_CORRECTIONS in panel._status_label.text()
    assert panel._history.entries[0].text == "Zampano arrives"  # unchanged


def test_project_b_does_not_use_project_a_glossary():
    db, pid, win = _ui_window()
    db.create_voice_glossary_term(pid, "Zampanò",
                                  common_misrecognitions="Zampano")
    b = db.create_project("B", narrative_engine="novel").id
    win._switch_project(b)
    panel = win._voice_panel
    panel._apply_final_segment(TranscriptSegment(text="Zampano arrives"))
    assert panel._history.entries[-1].corrections == []  # A's terms unused


def test_glossary_dialog_follows_project_switch():
    db, pid, win = _ui_window()
    panel = win._voice_panel
    panel._on_glossary_open()
    assert panel._glossary_dialog is not None
    assert panel._glossary_dialog._project_id == pid
    b = db.create_project("B", narrative_engine="novel").id
    win._switch_project(b)
    assert panel._glossary_dialog._project_id == b


def test_no_new_unsafe_windows_and_usable_without_terms():
    db, pid, win = _ui_window()
    panel = win._voice_panel
    before = set(QApplication.topLevelWidgets())
    panel._apply_final_segment(TranscriptSegment(text="plain words"))
    panel._history_list.setCurrentRow(0)
    panel._on_corrections_apply()                      # no terms: no-op
    panel._on_glossary_open()                          # parented dialog
    new_visible = [w for w in (set(QApplication.topLevelWidgets()) - before)
                   if w.isVisible() and w is not panel._glossary_dialog]
    assert new_visible == []
    # Parented chain: dialog -> voice window -> main window (never orphan).
    assert panel._glossary_dialog.parent() is win._voice_window
    assert win._voice_window.parent() is win
    assert panel._history.entries[0].text == "plain words"


def test_settings_defaults_are_review_first():
    from logosforge.settings import DEFAULTS
    assert DEFAULTS["enable_voice_glossary"] is True
    assert DEFAULTS["voice_spoken_punctuation"] is True
    assert DEFAULTS["voice_fuzzy_suggestions"] is False
    assert DEFAULTS["voice_auto_apply_exact"] is False
    assert DEFAULTS["voice_auto_apply_punctuation"] is False
    assert DEFAULTS["voice_learn_corrections"] == "ask"


def test_auto_apply_exact_when_explicitly_enabled():
    from logosforge.settings import get_manager
    db, pid, win = _ui_window()
    get_manager().set("voice_auto_apply_exact", True)  # explicit rule
    db.create_voice_glossary_term(pid, "Zampanò",
                                  common_misrecognitions="Zampano")
    panel = win._voice_panel
    panel._apply_final_segment(TranscriptSegment(text="Zampano arrives"))
    entry = panel._history.entries[0]
    assert entry.text == "Zampanò arrives"             # exact class auto-set
    assert entry.status == S_CORRECTED
    assert entry.original_text == "Zampano arrives"


def test_glossary_module_local_only():
    # Scan CODE only (docstrings state the "no audio" rule in prose).
    import ast
    import inspect
    tree = ast.parse(inspect.getsource(vg))
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if (isinstance(body, list) and body and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)):
            body[0].value.value = ""
    code = ast.unparse(tree).lower()
    for banned in ("urllib", "requests", "openai", "subprocess", "os.system",
                   "comfyui", "audio"):
        assert banned not in code, banned
