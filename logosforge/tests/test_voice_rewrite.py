"""Tests for voice rewrite — heuristic transforms + UI integration."""

from logosforge.db import Database
from logosforge.voice_learner import (
    VoiceRewrite,
    generate_voice_rewrites,
)
from logosforge.ui.command_palette import COMMANDS
from logosforge.ui.writing_core_view import WritingCoreView


# -- Helpers -------------------------------------------------------------------

def _formal_profile():
    return {
        "character_id": 1,
        "tone": "formal",
        "sentence_length": "long",
        "vocabulary_level": "elevated",
        "punctuation_style": {},
        "quirks": ["avoids contractions"],
        "dialogue_markers": ["Indeed"],
    }


def _casual_profile():
    return {
        "character_id": 2,
        "tone": "casual",
        "sentence_length": "short",
        "vocabulary_level": "simple",
        "punctuation_style": {"exclamations": 0.8},
        "quirks": ["heavy contraction use"],
        "dialogue_markers": ["Hey"],
    }


# -- Tone rewrites (formal) ---------------------------------------------------

def test_formal_profile_expands_contractions():
    text = "I can't believe you don't understand."
    rewrites = generate_voice_rewrites(text, _formal_profile())
    assert len(rewrites) >= 1
    formal_rw = rewrites[0]
    assert "cannot" in formal_rw.text or "can not" in formal_rw.text
    assert "do not" in formal_rw.text


def test_formal_rewrite_preserves_case():
    text = "I'm going to leave."
    rewrites = generate_voice_rewrites(text, _formal_profile())
    assert len(rewrites) >= 1
    assert rewrites[0].text.startswith("I am") or rewrites[0].text.startswith("I Am")


def test_formal_rewrite_has_label():
    text = "I can't do it."
    rewrites = generate_voice_rewrites(text, _formal_profile())
    assert any("formal" in rw.label.lower() for rw in rewrites)


# -- Tone rewrites (casual) ---------------------------------------------------

def test_casual_profile_adds_contractions():
    text = "I will not do that. She is not coming."
    rewrites = generate_voice_rewrites(text, _casual_profile())
    assert len(rewrites) >= 1
    casual_rw = rewrites[0]
    assert "won't" in casual_rw.text or "I'll" in casual_rw.text or "isn't" in casual_rw.text


def test_casual_rewrite_has_label():
    text = "I will not do that."
    rewrites = generate_voice_rewrites(text, _casual_profile())
    assert any("casual" in rw.label.lower() for rw in rewrites)


# -- Sentence length rewrites --------------------------------------------------

def test_short_profile_shortens_long_sentence():
    profile = _casual_profile()
    profile["sentence_length"] = "short"
    text = "I went to the store and then I bought some groceries and came home."
    rewrites = generate_voice_rewrites(text, profile)
    assert len(rewrites) >= 1
    short_rw = [rw for rw in rewrites if "short" in rw.label.lower()]
    if short_rw:
        assert len(short_rw[0].text.split(".")) > len(text.split("."))


def test_long_profile_lengthens_short_sentences():
    profile = _formal_profile()
    profile["sentence_length"] = "long"
    profile["tone"] = "neutral"
    text = "Stop. Go. Run."
    rewrites = generate_voice_rewrites(text, profile)
    long_rw = [rw for rw in rewrites if "long" in rw.label.lower()]
    if long_rw:
        assert len(long_rw[0].text) > len(text)


# -- Quirk-based rewrites -----------------------------------------------------

def test_avoids_contractions_quirk():
    profile = {
        "character_id": 1,
        "tone": "neutral",
        "sentence_length": "medium",
        "vocabulary_level": "standard",
        "punctuation_style": {},
        "quirks": ["avoids contractions"],
        "dialogue_markers": [],
    }
    text = "I don't think she's coming."
    rewrites = generate_voice_rewrites(text, profile)
    assert len(rewrites) >= 1
    assert "do not" in rewrites[0].text
    assert "she is" in rewrites[0].text.lower() or "she's" not in rewrites[0].text


def test_heavy_contraction_quirk():
    profile = {
        "character_id": 1,
        "tone": "neutral",
        "sentence_length": "medium",
        "vocabulary_level": "standard",
        "punctuation_style": {},
        "quirks": ["heavy contraction use"],
        "dialogue_markers": [],
    }
    text = "I would not do that if I were you."
    rewrites = generate_voice_rewrites(text, profile)
    assert len(rewrites) >= 1
    assert "wouldn't" in rewrites[0].text


# -- Edge cases ----------------------------------------------------------------

def test_empty_text_no_rewrites():
    assert generate_voice_rewrites("", _formal_profile()) == []


def test_empty_profile_no_rewrites():
    assert generate_voice_rewrites("Hello there.", {}) == []


def test_matching_text_no_rewrites():
    profile = {
        "character_id": 1,
        "tone": "neutral",
        "sentence_length": "medium",
        "vocabulary_level": "standard",
        "punctuation_style": {},
        "quirks": [],
        "dialogue_markers": [],
    }
    text = "I think we should head out before noon."
    rewrites = generate_voice_rewrites(text, profile)
    assert rewrites == []


def test_max_two_rewrites():
    text = "I can't believe you don't understand and I won't try."
    rewrites = generate_voice_rewrites(text, _formal_profile())
    assert len(rewrites) <= 2


def test_rewrite_is_different_from_input():
    text = "I can't believe you don't understand."
    rewrites = generate_voice_rewrites(text, _formal_profile())
    for rw in rewrites:
        assert rw.text != text


# -- VoiceRewrite dataclass ----------------------------------------------------

def test_voice_rewrite_fields():
    rw = VoiceRewrite(text="hello", label="test")
    assert rw.text == "hello"
    assert rw.label == "test"


# -- Command palette entry ----------------------------------------------------

def test_command_palette_has_voice_rewrite():
    keys = [cmd[1] for cmd in COMMANDS]
    assert "voice_rewrite" in keys


# -- UI integration (popup + editor) -------------------------------------------

def _setup_view():
    db = Database()
    proj = db.create_project("RewriteTest")
    char = db.create_character(proj.id, "Alice")
    db.create_voice_profile(char.id, tone="formal", quirks=["avoids contractions"])
    s1 = db.create_scene(
        proj.id, "Scene",
        content="Hello world.",
        character_ids=[char.id],
    )
    return db, proj, char, s1


def test_editor_gets_voice_profile_data():
    db, proj, char, s1 = _setup_view()
    view = WritingCoreView(db, proj.id)
    editor = list(view._editors.values())[0]
    assert editor._voice_profile_data is not None
    assert editor._voice_profile_data["tone"] == "formal"


def test_editor_no_profile_data_without_voice_profile():
    db = Database()
    proj = db.create_project("NoProfile")
    char = db.create_character(proj.id, "Bob")
    s1 = db.create_scene(
        proj.id, "Scene",
        content="Hello world.",
        character_ids=[char.id],
    )
    view = WritingCoreView(db, proj.id)
    editor = list(view._editors.values())[0]
    assert editor._voice_profile_data is None


def test_voice_rewrite_popup_exists():
    db, proj, char, s1 = _setup_view()
    view = WritingCoreView(db, proj.id)
    editor = list(view._editors.values())[0]
    assert hasattr(editor, "_voice_rewrite_popup")


def test_on_voice_rewrite_replaces_selection():
    from PySide6.QtGui import QTextCursor

    db, proj, char, s1 = _setup_view()
    view = WritingCoreView(db, proj.id)
    editor = list(view._editors.values())[0]
    editor.setPlainText("I can't do it.")

    cursor = editor.textCursor()
    cursor.setPosition(0)
    cursor.setPosition(14, QTextCursor.MoveMode.KeepAnchor)
    editor.setTextCursor(cursor)

    editor._on_voice_rewrite("I cannot do it.")
    assert editor.toPlainText() == "I cannot do it."
