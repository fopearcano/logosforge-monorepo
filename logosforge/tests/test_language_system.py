"""Multi-language infrastructure — registry, project language, AI/Dexter/
grammar coordination, Unicode/script safety, software UI language.

Four distinct concepts, kept separate end-to-end: Project Writing Language
(per project, full Whisper list), Dexter Language (project / auto / explicit
transcription mode), Grammar Language (project default, honest support
levels, graceful degradation) and Software UI Language (global, partial
Italian translation over an English default). Storage/editor/export preserve
Unicode (CJK, RTL, emoji); no cloud calls anywhere in the language system.
"""

from __future__ import annotations

import json
import warnings

import pytest
from PySide6.QtWidgets import QApplication, QComboBox

warnings.filterwarnings("ignore")

from logosforge.db import Database
from logosforge import export as X
from logosforge import languages as L
from logosforge import story_structure as ss
from logosforge import i18n


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
    from logosforge import assistant as A
    A.set_active_project_language("")
    yield
    A.set_active_project_language("")
    settings._instance = None


def _project(db, title="P", engine="novel"):
    return db.create_project(title, narrative_engine=engine,
                             default_writing_format=engine).id


_SAMPLES = {
    "zh": "灰狗在雨中的教堂前停下。🐕 — “他忘了自己的名字。”",
    "ja": "犬は雨の中で立ち止まった。「ザンパノ」",
    "ar": "توقف الكلب أمام الكنيسة تحت المطر.",
    "he": "הכלב עצר מול הכנסייה בגשם.",
    "emoji": "Smart “quotes” — em dash… 🎭🔥 ¡señor! Привет",
}


# ==========================================================================
# 1-7  Language registry
# ==========================================================================


def test_registry_includes_all_whisper_codes_and_auto():
    assert len(L.WHISPER_LANGUAGES) == 101          # auto + 100 languages
    assert "auto" in L.WHISPER_LANGUAGES
    from logosforge.voice.types import WHISPER_LANGUAGES as VOICE_LIST
    assert VOICE_LIST is L.WHISPER_LANGUAGES        # single source of truth


def test_registry_includes_required_scripts():
    for code in ("zh", "yue", "ja", "ko", "ar", "he", "hi", "bn", "bo",
                 "th", "el", "ru", "uk", "bg", "sr", "ta", "te", "ml",
                 "kn", "gu", "pa", "mr"):
        assert code in L.WHISPER_LANGUAGES, code
        assert L.get_language(code).supports_whisper


def test_aliases_resolve_including_new_ones():
    for alias, expected in (("Mandarin", "zh"), ("Cantonese", "yue"),
                            ("Castilian", "es"), ("Valencian", "ca"),
                            ("Flemish", "nl"), ("Haitian", "ht"),
                            ("Burmese", "my"), ("Pushto", "ps"),
                            ("Sinhalese", "si"),
                            ("Bahasa Indonesia", "id"), ("Indonesian", "id"),
                            ("Bahasa Melayu", "ms"), ("Malay", "ms")):
        assert L.normalize_language(alias) == expected, alias
    # Aliases are internal only — the selector shows no duplicates.
    labels = [label for _c, label in L.selector_choices()]
    assert len(labels) == len(set(labels)) == 101


def test_rtl_direction_and_script_metadata():
    for code in ("ar", "he", "fa", "ur", "ps", "sd", "yi"):
        assert L.direction_for(code) == "rtl", code
        assert L.get_language(code).direction == "rtl"
    assert L.direction_for("en") == "ltr" and L.direction_for("zh") == "ltr"
    assert L.script_for("zh") == "han" and L.script_for("ja") == "japanese"
    assert L.script_for("ko") == "hangul" and L.script_for("he") == "hebrew"
    assert L.script_for("hi") == "devanagari" and L.script_for("bo") == "tibetan"
    assert L.script_for("th") == "thai" and L.script_for("ru") == "cyrillic"
    assert L.script_for("en") == "latin"


def test_cjk_style_scripts_need_no_word_spaces():
    for code in ("zh", "yue", "ja", "th", "km", "lo", "my", "bo"):
        assert not L.uses_word_spaces(code), code
    for code in ("en", "it", "ko", "ru", "hi", "ar"):
        assert L.uses_word_spaces(code), code


def test_invalid_codes_fall_back_safely():
    for bad in ("klingon", "; rm -rf /", "", None, "zz", "EN GLISH"):
        assert L.normalize_language(bad) in L.WHISPER_LANGUAGES
    assert L.get_language("nonsense").code == "auto"


def test_language_definition_fields():
    d = L.get_language("it")
    assert d.name_en == "Italian" and d.whisper_code == "it"
    assert d.supports_grammar and d.supports_ui and d.ui_locale == "it"
    z = L.get_language("zh")
    assert z.supports_whisper and not z.supports_grammar and not z.supports_ui
    assert z.grammar_code == "" and "approximate" in z.notes
    assert "mandarin" in z.aliases


# ==========================================================================
# 8-13  Project writing language
# ==========================================================================


def test_new_project_has_default_writing_language():
    db = Database()
    pid = _project(db)
    assert L.get_project_writing_language(db, pid) == "en"
    assert L.get_project_writing_language_source(db, pid) == "default"


def test_project_language_saves_and_reloads(tmp_path):
    path = str(tmp_path / "lang.db")
    db = Database(path)
    pid = _project(db)
    L.set_project_writing_language(db, pid, "ja")
    db2 = Database(path)
    assert L.get_project_writing_language(db2, pid) == "ja"
    assert L.get_project_writing_language_source(db2, pid) == "user_selected"


def test_project_languages_do_not_leak_between_projects():
    db = Database()
    a = _project(db, "A")
    b = _project(db, "B")
    L.set_project_writing_language(db, a, "ar")
    assert L.get_project_writing_language(db, b) == "en"
    assert L.project_language_for_ai(db, b) == ""


def test_changing_project_language_never_mutates_body():
    db = Database()
    pid = _project(db)
    s = ss.create_scene(db, pid, act="Act 1", chapter="Chapter 1", title="S")
    db.update_scene_content(s.id, _SAMPLES["he"])
    before = db.get_scene_by_id(s.id).content
    L.set_project_writing_language(db, pid, "zh")
    L.set_project_writing_language(db, pid, "he")
    L.set_project_writing_language(db, pid, "en")
    assert db.get_scene_by_id(s.id).content == before   # text untouched


def test_project_settings_dialog_shows_and_saves_language():
    db = Database()
    pid = _project(db)
    from logosforge.ui.project_settings_dialog import ProjectSettingsDialog
    dlg = ProjectSettingsDialog(db, pid)
    combo = dlg._language_combo
    assert combo.count() == 101                       # Auto + full list
    assert combo.currentData() == "en"
    idx_it = combo.findData("it")
    assert combo.itemText(idx_it) == "Italian (it)"   # friendly names
    combo.setCurrentIndex(idx_it)
    dlg._on_accept()
    assert L.get_project_writing_language(db, pid) == "it"


def test_new_project_dialog_language_default_and_choice():
    from logosforge.settings import get_manager
    from logosforge.ui.new_project_dialog import NewProjectDialog
    dlg = NewProjectDialog()
    assert dlg.get_writing_language() == "en"          # global default
    get_manager().set("default_writing_language", "it")
    dlg2 = NewProjectDialog()
    assert dlg2.get_writing_language() == "it"
    dlg2._language_combo.setCurrentIndex(dlg2._language_combo.findData("zh"))
    assert dlg2.get_writing_language() == "zh"


def test_project_switch_updates_language_context():
    from logosforge import assistant as A
    from logosforge.settings import get_manager
    get_manager().set("enable_voice_mode", True)
    get_manager().set("voice_backend_mode", "mock")
    from logosforge.ui.main_window import MainWindow
    db = Database()
    a = _project(db, "A")
    b = _project(db, "B")
    L.set_project_writing_language(db, a, "it")
    win = MainWindow(db, a)
    assert A.get_active_project_language() == "it"
    assert win._project_dexter_language() == "it"
    win._switch_project(b)
    assert A.get_active_project_language() == ""       # B chose nothing
    assert win._project_dexter_language() == "en"
    win._switch_project(a)
    assert A.get_active_project_language() == "it"     # A's context returns


# ==========================================================================
# 14-17  AI coordination
# ==========================================================================


def test_ai_instruction_preserves_language_and_mentions_script():
    text = L.ai_language_instruction("it")
    assert "Italian (it)" in text
    assert "Preserve this language" in text
    assert "Never translate the user's text on your own" in text
    assert "right-to-left" in L.ai_language_instruction("ar")
    assert "does not separate words" in L.ai_language_instruction("zh")
    assert L.ai_language_instruction("en") == ""
    assert L.ai_language_instruction("auto") == ""


def test_chat_completion_priority_explicit_project_detect(monkeypatch):
    from logosforge import assistant as A
    captured = {}

    def fake_openai(messages, provider, api_key, timeout):
        captured["system"] = messages[0]["content"]
        return "ok"
    monkeypatch.setattr(A, "_openai_completion", fake_openai)
    msgs = [{"role": "system", "content": "S."},
            {"role": "user", "content": "Hello there my good friend."}]
    # Project language drives the instruction…
    A.set_active_project_language("it")
    A.chat_completion([dict(m) for m in msgs], use_cache=False)
    assert "Italian (it)" in captured["system"]
    # …explicit response_language outranks it…
    A.chat_completion([dict(m) for m in msgs], use_cache=False,
                      response_language="de")
    assert "German (de)" in captured["system"]
    # …and with no project language English text stays uninstrumented.
    A.set_active_project_language("")
    A.chat_completion([dict(m) for m in msgs], use_cache=False)
    assert "Preserve this language" not in captured["system"]


def test_billy_voice_prompts_get_project_language(monkeypatch):
    # The voice → Billy path goes through chat_completion, so the active
    # project language reaches Billy proposals without extra wiring.
    from logosforge import assistant as A
    captured = {}

    def fake_openai(messages, provider, api_key, timeout):
        captured["system"] = messages[0]["content"]
        return "rewritten"
    monkeypatch.setattr(A, "_openai_completion", fake_openai)
    A.set_active_project_language("yue")
    A.chat_completion([{"role": "system", "content": "Billy."},
                       {"role": "user", "content": "Rewrite my line."}],
                      use_cache=False)
    assert "Cantonese (yue)" in captured["system"]
    assert "unless the user explicitly asks to translate" in captured["system"]


def test_language_context_line_for_packaging():
    db = Database()
    pid = _project(db)
    assert L.language_context_line(db, pid) == ""      # nothing chosen
    L.set_project_writing_language(db, pid, "he")
    line = L.language_context_line(db, pid)
    assert line.startswith("[Writing Language] Hebrew (he)")
    assert "preserve" in line.lower()


# ==========================================================================
# 18-22  Dexter coordination
# ==========================================================================


def test_dexter_default_mode_uses_project_language():
    from logosforge.voice.types import VoiceSettings
    s = VoiceSettings()                                # fresh defaults
    assert s.resolved_language_mode() == "project"
    s.project_language_code = "ja"
    assert s.effective_language() == "ja"


def test_dexter_auto_and_explicit_modes_map_to_backend():
    from logosforge.voice.types import VoiceSettings
    assert VoiceSettings(language_mode="auto",
                         language="it").effective_language() == "auto"
    assert VoiceSettings(language_mode="explicit",
                         language="yue").effective_language() == "yue"
    # Back-compat: a concrete saved language without a mode stays explicit.
    assert VoiceSettings(language="it").resolved_language_mode() == "explicit"


def test_dexter_project_auto_falls_through_to_auto():
    from logosforge.voice.types import VoiceSettings
    s = VoiceSettings(language_mode="project", project_language_code="auto")
    assert s.effective_language() == "auto"


def test_dexter_invalid_values_fall_back_safely():
    from logosforge.voice.types import VoiceSettings
    s = VoiceSettings(language_mode="project",
                      project_language_code="; rm -rf /")
    assert s.effective_language() == "auto"            # injection-proof
    s2 = VoiceSettings(language_mode="explicit", language="auto")
    assert s2.effective_language() == "auto"
    s3 = VoiceSettings(language_mode="weird", language="auto")
    assert s3.resolved_language_mode() == "project"    # unknown mode → infer


def test_transcript_metadata_records_project_and_mode():
    import array
    from logosforge.voice.recorder import MockRecorder
    from logosforge.voice.session import VoiceSessionController
    from logosforge.voice.transcriber import MockTranscriber
    from logosforge.voice.types import VoiceSettings
    finals = []
    s = VoiceSettings(enabled=True, backend_mode="mock",
                      language_mode="project", project_language_code="it",
                      silence_ms=300)
    c = VoiceSessionController(s, MockRecorder(), MockTranscriber(),
                               on_final_transcript=finals.append)
    c.start_voice_session()
    speech = array.array(
        "h", [6000 if i % 2 else -6000 for i in range(8000)]).tobytes()
    c._recorder.feed_chunk(speech)
    c._recorder.feed_chunk(b"\x00\x00" * 8000)
    c.stop_voice_session()
    seg = finals[0]
    assert seg.project_language_code == "it"
    assert seg.dexter_language_mode == "project"
    assert seg.selected_language_code == "it"
    assert seg.language_source == "project_language"
    # CJK code passes through the same path without crashing.
    finals.clear()
    s2 = VoiceSettings(enabled=True, backend_mode="mock",
                       language_mode="project", project_language_code="zh",
                       silence_ms=300)
    c2 = VoiceSessionController(s2, MockRecorder(), MockTranscriber(),
                                on_final_transcript=finals.append)
    c2.start_voice_session()
    c2._recorder.feed_chunk(speech)
    c2._recorder.feed_chunk(b"\x00\x00" * 8000)
    c2.stop_voice_session()
    assert finals[0].selected_language_code == "zh"


def test_voice_panel_fills_project_language():
    from logosforge.ui.voice_panel import VoicePanel
    panel = VoicePanel(project_language_getter=lambda: "he")
    settings = panel._load_settings()
    assert settings.project_language_code == "he"
    assert settings.effective_language() == "he"       # default project mode
    broken = VoicePanel(project_language_getter=lambda: 1 / 0)
    assert broken._load_settings().project_language_code == "auto"


# ==========================================================================
# 23-27  Grammar
# ==========================================================================


def test_grammar_uses_project_language_by_default():
    db = Database()
    pid = _project(db)
    L.set_project_writing_language(db, pid, "it")
    assert L.grammar_language_for_project(db, pid) == "it"
    from logosforge.ui.writing_core_view import WritingCoreView
    v = WritingCoreView(db, pid, on_data_changed=lambda: None)
    assert v._project_grammar_language() == "it"


def test_unsupported_language_degrades_gracefully():
    from logosforge.grammar_checker import check_text, grammar_status
    for code in ("zh", "ja", "ar", "he", "th"):
        level, msg = grammar_status(code)
        assert level == "none"
        assert "not available" in msg and "AI review" in msg
        assert check_text("文字 文字 文字。", language=code) == []


def test_grammar_override_per_project():
    db = Database()
    pid = _project(db)
    L.set_project_writing_language(db, pid, "zh")
    L.set_project_override(db, pid, L.KEY_GRAMMAR_OVERRIDE, "en")
    assert L.grammar_language_for_project(db, pid) == "en"
    L.set_project_override(db, pid, L.KEY_GRAMMAR_OVERRIDE, "")
    assert L.grammar_language_for_project(db, pid) == "zh"


def test_no_silent_english_spelling_on_non_english_project():
    from logosforge.grammar_checker import check_text
    italian = "Il vecchio guardava la pioggia cadere sulla strada deserta."
    issues = check_text(italian, language="it")
    assert not any(i.issue_type == "spelling" for i in issues)
    # English projects keep the full rule set.
    assert any(i.issue_type == "spelling"
               for i in check_text("xqzv blorp", language="en"))


def test_legacy_paths_unchanged_without_project_language():
    db = Database()
    pid = _project(db)                                 # default source
    assert L.grammar_language_for_project(db, pid) == ""   # legacy detect
    from logosforge.grammar_checker import check_text
    assert check_text("the the cat")                   # detection still works


def test_grammar_note_shown_in_project_settings():
    # Alpha scope: the note is the static DEFERRAL statement — no
    # per-language grammar-support claims anywhere in the UI.
    db = Database()
    pid = _project(db)
    from logosforge.ui.project_settings_dialog import ProjectSettingsDialog
    dlg = ProjectSettingsDialog(db, pid)
    note = dlg._grammar_note.text()
    assert "deferred" in note and "Review/Correction" in note
    for code in ("ja", "en", "zh"):
        dlg._language_combo.setCurrentIndex(dlg._language_combo.findData(code))
        assert dlg._grammar_note.text() == note        # static, no claims


# ==========================================================================
# 28-38  Unicode / script support
# ==========================================================================


@pytest.mark.parametrize("key", sorted(_SAMPLES))
def test_unicode_save_reload(key, tmp_path):
    path = str(tmp_path / f"{key}.db")
    db = Database(path)
    pid = _project(db)
    s = ss.create_scene(db, pid, act="Act 1", chapter="Chapter 1", title=key)
    db.update_scene_content(s.id, _SAMPLES[key])
    db2 = Database(path)
    assert db2.get_scene_by_id(s.id).content == _SAMPLES[key]


def test_markdown_txt_export_utf8(tmp_path):
    db = Database()
    pid = _project(db, "多语言 פרויקט")
    for key, text in _SAMPLES.items():
        s = ss.create_scene(db, pid, act="Act 1", chapter="Chapter 1",
                            title=key)
        db.update_scene_content(s.id, text)
    md = X.export_markdown(db, pid)
    for text in _SAMPLES.values():
        assert text in md
    out = tmp_path / "out.md"
    out.write_text(md, encoding="utf-8")
    assert _SAMPLES["zh"] in out.read_text(encoding="utf-8")


def test_json_export_preserves_unicode_unescaped():
    db = Database()
    pid = _project(db)
    s = ss.create_scene(db, pid, act="Act 1", chapter="Chapter 1", title="一")
    db.update_scene_content(s.id, _SAMPLES["zh"])
    js = X.export_json(db, pid)
    assert _SAMPLES["zh"] in js                        # ensure_ascii=False
    assert "\\u7070" not in js                         # no needless escapes
    assert json.loads(js)


def test_fountain_export_preserves_unicode():
    db = Database()
    pid = _project(db, "SP", engine="screenplay")
    s = ss.create_scene(db, pid, act="Act 1", chapter="Chapter 1", title="一")
    db.update_scene_content(s.id, "INT. 教堂 - NIGHT\n\nザンパノ\nこんにちは。")
    ftn = X.export_screenplay(db, pid)
    assert "教堂" in ftn and "ザンパノ" in ftn


def test_docx_pdf_unicode_or_graceful_limitation(tmp_path):
    db = Database()
    pid = _project(db)
    s = ss.create_scene(db, pid, act="Act 1", chapter="Chapter 1", title="一")
    db.update_scene_content(s.id, _SAMPLES["zh"])
    # Optional backends: with the library absent the app raises its
    # documented readable error instead of corrupting anything; with it
    # present the export must not crash on CJK input.
    for fn in (getattr(X, "export_docx", None), getattr(X, "export_pdf", None)):
        if fn is None:
            continue
        try:
            fn(db, pid, str(tmp_path / "_lang_x.bin"))
        except Exception as exc:                       # graceful, readable
            msg = str(exc).lower()
            assert any(hint in msg for hint in
                       ("install", "no module", "reportlab", "docx",
                        "not available")), msg


def test_search_handles_cjk_and_rtl():
    db = Database()
    pid = _project(db)
    s = ss.create_scene(db, pid, act="Act 1", chapter="Chapter 1",
                        title="教堂场景")
    db.update_scene_summary(s.id, "הכלב עצר מול הכנסייה")
    assert db.search_project(pid, "教堂")
    assert db.search_project(pid, "הכלב")
    assert db.search_project(pid, "🦄") == []          # emoji query, no crash


def test_word_count_labels_cjk_as_approximate():
    db = Database()
    pid = _project(db)
    s = ss.create_scene(db, pid, act="Act 1", chapter="Chapter 1", title="一")
    db.update_scene_content(s.id, "灰狗在雨中。")
    L.set_project_writing_language(db, pid, "zh")
    from logosforge.ui.writing_core_view import WritingCoreView
    v = WritingCoreView(db, pid, on_data_changed=lambda: None)
    label = v._word_count_label.text()
    assert label.startswith("≈") and "characters" in label
    L.set_project_writing_language(db, pid, "it")
    v2 = WritingCoreView(db, pid, on_data_changed=lambda: None)
    assert "words" in v2._word_count_label.text()


def test_editor_detection_prefers_selected_project_language():
    db = Database()
    pid = _project(db)
    s = ss.create_scene(db, pid, act="Act 1", chapter="Chapter 1", title="S")
    db.update_scene_content(
        s.id, "The old man watched the rain fall on the road to the house.")
    L.set_project_writing_language(db, pid, "it")
    from logosforge.ui.writing_core_view import WritingCoreView
    v = WritingCoreView(db, pid, on_data_changed=lambda: None)
    v._run_language_detection()
    assert v.current_language == "it"                  # not trigram-guessed


# ==========================================================================
# 39-44  Software UI language
# ==========================================================================


def test_ui_language_english_only_while_localization_deferred():
    # Alpha scope: localization is deferred — the UI resolves to English
    # no matter what the (kept, dormant) setting says.
    from logosforge.settings import get_manager
    assert i18n.UI_LOCALIZATION_ENABLED is False
    assert i18n.ui_language() == "en"                  # default
    get_manager().set("ui_language_code", "it")
    assert i18n.ui_language() == "en"                  # forced English
    import logosforge.settings as settings
    settings._instance = None                          # reload from disk
    assert get_manager().get("ui_language_code") == "it"   # setting persists
    assert i18n.ui_language() == "en"                  # …but stays dormant


def test_ui_language_independent_of_project_language():
    from logosforge.settings import get_manager
    db = Database()
    pid = _project(db)
    L.set_project_writing_language(db, pid, "zh")
    get_manager().set("ui_language_code", "it")
    assert L.get_project_writing_language(db, pid) == "zh"   # untouched
    L.set_project_writing_language(db, pid, "ar")
    assert get_manager().get("ui_language_code") == "it"     # untouched


def test_english_default_means_untranslated_passthrough():
    assert i18n.tr("Writing Language:") == "Writing Language:"
    assert i18n.tr("Anything at all") == "Anything at all"


def test_no_partial_translation_ships_in_alpha_ui():
    # The Italian catalog remains DORMANT scaffolding: even with the setting
    # forced to "it", every label renders English — no mixed-language UI.
    from logosforge.settings import get_manager
    get_manager().set("ui_language_code", "it")
    assert i18n.tr("Writing Language:") == "Writing Language:"
    assert i18n.tr("Use project language") == "Use project language"
    assert i18n.coverage("it") > 0                     # scaffolding kept…
    db = Database()
    pid = _project(db)
    from logosforge.ui.project_settings_dialog import ProjectSettingsDialog
    dlg = ProjectSettingsDialog(db, pid)
    from PySide6.QtWidgets import QLabel
    texts = [w.text() for w in dlg.findChildren(QLabel)]
    assert "Writing Language:" in texts                # …but not user-facing
    assert not any("Lingua" in t for t in texts)


def test_no_ui_language_selector_in_alpha_preferences():
    # No UI-language selector ships in Alpha; the Language section keeps the
    # (multilingual) default WRITING language and states English-only UI.
    from logosforge.ui.settings_dialog import SettingsDialog
    dlg = SettingsDialog(on_theme_changed=lambda n: None)
    assert dlg.findChild(QComboBox, "prefsUiLanguage") is None
    assert dlg.findChild(QComboBox, "prefsDefaultWritingLanguage") is not None
    from PySide6.QtWidgets import QLabel
    note = dlg.findChild(QLabel, "prefsUiLanguageNote")
    assert note is not None
    assert "English-only" in note.text()
    assert "deferred" in note.text()


def test_unsupported_ui_language_falls_back_to_english():
    from logosforge.settings import get_manager
    get_manager().set("ui_language_code", "fr")        # no catalog
    assert i18n.ui_language() == "en"
    assert i18n.tr("Writing Language:") == "Writing Language:"


# ==========================================================================
# 45-59  Regression guards
# ==========================================================================


def test_language_system_is_local_only_no_cloud():
    import inspect
    for mod_name in ("logosforge.languages", "logosforge.i18n"):
        import importlib
        src = inspect.getsource(importlib.import_module(mod_name))
        for banned in ("urllib", "requests", "http://", "https://",
                       "socket", "subprocess"):
            assert banned not in src, (mod_name, banned)


def test_grammar_checker_stays_offline():
    import inspect
    from logosforge import grammar_checker as gc
    src = inspect.getsource(gc)
    for banned in ("urllib", "requests", "http", "socket"):
        assert banned not in src, banned


def test_voice_defaults_keep_voice_off_and_local():
    from logosforge.settings import get_manager
    assert get_manager().get("enable_voice_mode") is False
    assert get_manager().get("voice_backend_mode") == "disabled"
    assert get_manager().get("voice_language_mode") == ""   # infer (project)


def test_gn_canonical_structure_untouched():
    from logosforge import graphic_novel_structure as gns
    from logosforge import graphic_novel_outline as gno
    db = Database()
    pid = _project(db, "GN", engine="graphic_novel")
    s = ss.create_scene(db, pid, act="Act 1", title="一")
    gno.add_page(db, s.id)
    gno.add_panel(db, s.id, 0, visual_description=_SAMPLES["ja"])
    L.set_project_writing_language(db, pid, "ja")
    view = gns.act_view(db, pid)
    assert view[0][0] == "Act 1" and view[0][1][0][0] == 1
    md = gns.export_structure_markdown(db, pid)
    assert _SAMPLES["ja"].split("。")[0] in md          # unicode export intact


def test_writing_mode_lock_unchanged_by_language():
    from logosforge.writing_modes import can_change_writing_mode
    db = Database()
    pid = _project(db)
    s = ss.create_scene(db, pid, act="Act 1", chapter="Chapter 1", title="S")
    db.update_scene_content(s.id, "Meaningful content " * 30)
    assert can_change_writing_mode(db, pid) is False
    L.set_project_writing_language(db, pid, "it")      # settings-only write
    assert can_change_writing_mode(db, pid) is False   # still locked
    assert "Meaningful content" in db.get_scene_by_id(s.id).content


def test_series_hierarchy_unaffected():
    db = Database()
    pid = _project(db, "S", engine="series")
    season = db.create_season(pid, title="Season 1")
    episode = db.create_episode(season.id, title="Episode 1")
    s = ss.create_scene(db, pid, act="Act 1", chapter="Chapter 1", title="話")
    db.set_scene_episode(s.id, episode.id)
    L.set_project_writing_language(db, pid, "ja")
    assert db.get_scenes_for_episode(episode.id)[0].id == s.id


# ==========================================================================
# Post-implementation regression gate pins (2026-06-11)
# ==========================================================================

_GATE_STRINGS = {
    "zh": "这是一个测试场景。角色走进房间。",
    "ja": "これはテストシーンです。登場人物が部屋に入る。",
    "ko": "이것은 테스트 장면입니다. 인물이 방에 들어간다.",
    "ar": "هذا مشهد اختبار. تدخل الشخصية إلى الغرفة.",
    "he": "זו סצנת בדיקה. הדמות נכנסת לחדר.",
    "hi": "यह एक परीक्षण दृश्य है। पात्र कमरे में प्रवेश करता है।",
    "bn": "এটি একটি পরীক্ষামূলক দৃশ্য। চরিত্রটি ঘরে প্রবেশ করে।",
    "th": "นี่คือฉากทดสอบ ตัวละครเดินเข้าไปในห้อง",
    "mixed": "“Curly quotes”, em dash — ellipsis … emoji 🐕, accented "
             "text: Zampanò, città, perché.",
}


def test_gate_registry_full_code_list_fields():
    for code in ("zh", "yue", "ja", "ko", "ar", "he", "hi", "bn", "bo",
                 "th", "ru", "uk", "el", "ta", "te", "ml", "kn", "gu",
                 "pa"):
        d = L.get_language(code)
        assert d.whisper_code == code and d.name_en
        assert d.script and d.direction in ("ltr", "rtl")
        assert d.supports_whisper
    assert L.get_language("it").ui_locale == "it"
    assert L.get_language("fr").ui_locale == ""        # no UI translation
    assert L.get_language("en").grammar_code == "en"
    assert L.get_language("th").grammar_code == ""     # unsupported → empty


def test_gate_invalid_stored_project_language_is_safe():
    # Corrupt / hand-edited stored value: everything degrades to auto/none,
    # nothing crashes and the AI never receives a hostile string.
    db = Database()
    pid = _project(db)
    s = db.get_project_settings(pid) or {}
    s[L.KEY_WRITING_LANGUAGE] = "klingon; rm -rf /"
    s[L.KEY_WRITING_SOURCE] = "user_selected"
    db.save_project_settings(pid, s)
    assert L.get_project_writing_language(db, pid) == "auto"
    assert L.project_language_for_ai(db, pid) == ""
    assert L.grammar_language_for_project(db, pid) == ""
    assert L.dexter_language_for_project(db, pid) == "auto"


def test_gate_dexter_project_override_wins_and_clears():
    db = Database()
    pid = _project(db)
    L.set_project_writing_language(db, pid, "it")
    L.set_project_override(db, pid, L.KEY_DEXTER_OVERRIDE, "yue")
    assert L.dexter_language_for_project(db, pid) == "yue"   # override wins
    L.set_project_override(db, pid, L.KEY_DEXTER_OVERRIDE, "")
    assert L.dexter_language_for_project(db, pid) == "it"    # back to project


def test_gate_scripts_across_all_surfaces(tmp_path):
    """The gate's exact CJK/RTL/Indic/Thai/mixed strings survive every
    writing surface: scene bodies, Notes, PSYKE, Graphic Novel panel
    fields, Series scene bodies — through save, reload, search and
    Markdown/JSON exports."""
    from logosforge import graphic_novel_blocks as gnb
    from logosforge import graphic_novel_outline as gno
    from logosforge import graphic_novel_structure as gns
    path = str(tmp_path / "gate.db")
    db = Database(path)
    pid = _project(db, "Novel")
    scene_ids = {}
    for key, text in _GATE_STRINGS.items():
        s = ss.create_scene(db, pid, act="Act 1", chapter="Chapter 1",
                            title=text[:24])
        db.update_scene_content(s.id, text)
        scene_ids[key] = s.id
    db.create_note(pid, title=_GATE_STRINGS["ko"][:20],
                   content=_GATE_STRINGS["ar"])
    db.create_psyke_entry(pid, name="Zampanò 🐕", entry_type="character",
                          notes=_GATE_STRINGS["he"])
    gpid = _project(db, "GN", engine="graphic_novel")
    gs = ss.create_scene(db, gpid, act="Act 1",
                         title=_GATE_STRINGS["ja"][:12])
    gno.add_page(db, gs.id)
    gno.add_panel(db, gs.id, 0)
    for field, key in (("visual_description", "zh"), ("caption", "th"),
                       ("dialogue", "ko"), ("sfx", "mixed"),
                       ("notes", "hi")):
        gno.set_panel_field(db, gs.id, 0, 0, field, _GATE_STRINGS[key])
    spid = _project(db, "Series", engine="series")
    season = db.create_season(spid, title="시즌 1")
    episode = db.create_episode(season.id, title="エピソード1")
    ssc = ss.create_scene(db, spid, act="Act 1", chapter="Chapter 1",
                          title=_GATE_STRINGS["bn"][:16])
    db.set_scene_episode(ssc.id, episode.id)
    db.update_scene_content(ssc.id, _GATE_STRINGS["bn"])

    db2 = Database(path)                               # full reload
    for key, text in _GATE_STRINGS.items():
        assert db2.get_scene_by_id(scene_ids[key]).content == text, key
        assert db2.search_project(pid, text[:6]), key  # search, no crash
    panel = gnb.load_scene_script(db2, gs.id).pages[0].panels[0]
    assert panel.visual_description == _GATE_STRINGS["zh"]
    assert panel.caption == _GATE_STRINGS["th"]
    assert panel.dialogue == _GATE_STRINGS["ko"]
    assert panel.sfx == _GATE_STRINGS["mixed"]
    assert panel.notes == _GATE_STRINGS["hi"]
    assert db2.get_scene_by_id(ssc.id).content == _GATE_STRINGS["bn"]
    assert db2.get_scenes_for_episode(episode.id)[0].id == ssc.id
    md = X.export_markdown(db2, pid)
    js = X.export_json(db2, pid)
    for text in _GATE_STRINGS.values():
        assert text in md and text in js
    gn_md = gns.export_structure_markdown(db2, gpid)
    assert _GATE_STRINGS["ko"] in gn_md and _GATE_STRINGS["zh"] in gn_md


def test_gate_dexter_setup_label_stays_english_in_alpha():
    from logosforge.settings import get_manager
    get_manager().set("ui_language_code", "it")        # dormant setting
    get_manager().set("enable_voice_mode", True)
    get_manager().set("voice_backend_mode", "mock")
    from logosforge.ui.voice_setup_dialog import VoiceSetupDialog
    dlg = VoiceSetupDialog()
    assert dlg._language.itemText(0) == "Use project language"
    assert dlg._language.itemData(0) == "project"      # data stays stable
    get_manager().set("ui_language_code", "en")


def test_gate_exports_carry_no_language_settings_metadata():
    # Exports never include project settings (the same property that keeps
    # API keys out) — so language metadata is NOT in exports; the project
    # language travels only inside the database/backup, as documented.
    db = Database()
    pid = _project(db)
    L.set_project_writing_language(db, pid, "it")
    s = ss.create_scene(db, pid, act="Act 1", chapter="Chapter 1", title="S")
    db.update_scene_content(s.id, "Body.")
    js = X.export_json(db, pid)
    md = X.export_markdown(db, pid)
    for blob in (js, md):
        assert "writing_language_code" not in blob
        assert "dexter_language_override" not in blob


# ==========================================================================
# Final pre-Alpha scope cleanup pins (2026-06-11): Dexter = writing room;
# grammar/text correction deferred; UI English-only.
# ==========================================================================


def _setup_scene(db, pid):
    s = ss.create_scene(db, pid, act="Act 1", chapter="Chapter 1", title="S")
    db.update_scene_content(s.id, "Hello world.")
    return s


def test_grammar_checking_deferred_in_editor():
    # Even a previously stored opt-in is ignored: no grammar pass on load.
    db = Database()
    pid = _project(db)
    _setup_scene(db, pid)
    settings = db.get_project_settings(pid) or {}
    settings["grammar_checking"] = True                # legacy opt-in
    db.save_project_settings(pid, settings)
    from logosforge.ui.writing_core_view import WritingCoreView
    view = WritingCoreView(db, pid, on_data_changed=lambda: None)
    assert view._grammar_checking is False             # forced off (deferred)
    assert view._grammar_worker is None
    assert view._grammar_timer.isActive() is False
    for editor in view._editors.values():
        assert editor._grammar_enabled is False


def test_review_menu_grammar_entry_is_disabled_deferred_placeholder():
    db = Database()
    pid = _project(db)
    _setup_scene(db, pid)
    from logosforge.ui.writing_core_view import WritingCoreView
    view = WritingCoreView(db, pid, on_data_changed=lambda: None)
    view.on_open_review = lambda: None
    actions = view._build_review_menu().actions()
    grammar = next(a for a in actions if "Grammar" in a.text())
    assert "deferred" in grammar.text()                # clearly deferred
    assert grammar.isEnabled() is False                # no active route
    assert "Review/Correction" in grammar.toolTip()


def test_dexter_room_has_no_grammar_coupling():
    # Dexter's Room is the dynamic voice WRITING room: capture, transcript
    # review/format, routing and Billy proposals — never a grammar checker.
    import inspect
    import importlib
    voice_modules = (
        "logosforge.ui.voice_panel",
        "logosforge.ui.voice_setup_dialog",
        "logosforge.ui.voice_glossary_dialog",
        "logosforge.voice.room",
        "logosforge.voice.session",
        "logosforge.voice.commit_router",
        "logosforge.voice.intent_router",
        "logosforge.voice.billy_bridge",
        "logosforge.voice.setup",
    )
    for name in voice_modules:
        src = inspect.getsource(importlib.import_module(name))
        assert "grammar_checker" not in src, name      # no dependency
        low = src.lower()
        for banned in ("grammar check", "proofread", "correct grammar",
                       "automatic correction", "final correction",
                       "multilingual correction"):
            assert banned not in low, (name, banned)


def test_dexter_room_opens_without_grammar_and_stays_preview_first():
    from logosforge.settings import get_manager
    get_manager().set("enable_voice_mode", True)
    get_manager().set("voice_backend_mode", "mock")
    from logosforge.ui.main_window import MainWindow
    db = Database()
    pid = _project(db)
    win = MainWindow(db, pid)
    win._toggle_voice_panel()
    assert win._voice_window.isVisible()               # the room opens
    panel = win._voice_panel
    assert "Dexter's Room" in panel._room_label.text() # naming unchanged
    # Review-first invariants survive the re-scope.
    assert get_manager().get("voice_auto_commit") is False
    assert get_manager().get("voice_auto_apply_exact") is False


def test_grammar_module_needs_no_third_party_dependency():
    # Startup (and the future Review phase) require no grammar-only package.
    import ast
    tree = ast.parse(open("logosforge/grammar_checker.py", encoding="utf-8").read())
    ext = {n.names[0].name.split(".")[0] for n in ast.walk(tree)
           if isinstance(n, ast.Import)}
    ext |= {n.module.split(".")[0] for n in ast.walk(tree)
            if isinstance(n, ast.ImportFrom) and n.module}
    assert ext <= {"__future__", "math", "re", "collections", "dataclasses",
                   "typing", "logosforge"}


def test_docs_state_dexter_scope_and_deferrals():
    # Whitespace-normalized so doc line wrapping never breaks the pin.
    voice_doc = " ".join(open("docs/VOICE_MVP.md", encoding="utf-8").read().split())
    assert "not a grammar checker" in voice_doc
    limits = " ".join(open("docs/KNOWN_LIMITATIONS_ALPHA.md", encoding="utf-8").read().split())
    assert "deferred to a later Review/Correction phase" in limits
    assert "English-only" in limits


# ==========================================================================
# Dexter scope-cleanup certification gate pins (2026-06-11)
# ==========================================================================


def test_gate_dexter_unaffected_by_missing_grammar_module():
    """Dexter has no grammar dependency: even with the grammar module made
    unimportable, the voice panel constructs and resolves its language."""
    import sys
    from logosforge.settings import get_manager
    get_manager().set("enable_voice_mode", True)
    get_manager().set("voice_backend_mode", "mock")
    saved = sys.modules.get("logosforge.grammar_checker")
    sys.modules["logosforge.grammar_checker"] = None   # import would fail
    try:
        from logosforge.ui.voice_panel import VoicePanel
        panel = VoicePanel(project_language_getter=lambda: "it")
        settings = panel._load_settings()
        assert settings.effective_language() == "it"
        assert panel.is_enabled() is True
    finally:
        if saved is not None:
            sys.modules["logosforge.grammar_checker"] = saved
        else:
            sys.modules.pop("logosforge.grammar_checker", None)


def test_gate_writing_language_help_text_required_wording():
    from PySide6.QtWidgets import QLabel
    db = Database()
    pid = _project(db)
    from logosforge.ui.project_settings_dialog import ProjectSettingsDialog
    dlg = ProjectSettingsDialog(db, pid)
    texts = [w.text() for w in dlg.findChildren(QLabel)]
    hits = [t for t in texts
            if "AI writing context and Dexter transcription defaults" in t]
    assert hits, texts
    assert any("does not change the app interface language" in t
               for t in hits)


def test_gate_blocker_list_reflects_scope_policy():
    raw = open("docs/ALPHA_MANUAL_SMOKE_TEST.md", encoding="utf-8").read()
    smoke = " ".join(raw.replace("*", "").split())
    blockers = smoke[smoke.index("release blocker if any of these FAIL"):
                     smoke.index("Non-blocking")]
    nonblocking = smoke[smoke.index("Non-blocking"):
                        smoke.index("Blocker list")]
    # Deferred items are explicitly NON-blocking…
    assert "grammar" not in blockers.lower()
    assert "grammar checking deferred" in nonblocking
    assert "UI localization deferred" in nonblocking
    assert "Whisper transcription quality" in nonblocking
    # …while the hard safety blockers from the scope decision remain.
    for kept in ("Unicode text corrupts", "project language leaks",
                 "raw audio", "auto-applies", "fullscreen minimize",
                 "loses Panel data", "leaks API/provider secrets"):
        assert kept in blockers, kept
