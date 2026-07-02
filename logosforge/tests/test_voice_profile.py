"""Tests for VoiceProfile model — create, update, serialize, deserialize."""

import json

from logosforge.db import Database
from logosforge.models import (
    VOICE_SENTENCE_LENGTHS,
    VOICE_TONES,
    VOICE_VOCABULARY_LEVELS,
    VoiceProfile,
)


def _setup():
    db = Database()
    proj = db.create_project("VoiceTest")
    char = db.create_character(proj.id, "Alice")
    return db, proj, char


# -- Constants -----------------------------------------------------------------

def test_tone_values():
    assert "formal" in VOICE_TONES
    assert "neutral" in VOICE_TONES
    assert "casual" in VOICE_TONES
    assert "abrasive" in VOICE_TONES
    assert "polite" in VOICE_TONES


def test_sentence_length_values():
    assert VOICE_SENTENCE_LENGTHS == ("short", "medium", "long")


def test_vocabulary_level_values():
    assert VOICE_VOCABULARY_LEVELS == ("simple", "standard", "elevated")


# -- Create --------------------------------------------------------------------

def test_create_voice_profile_defaults():
    db, proj, char = _setup()
    profile = db.create_voice_profile(char.id)
    assert profile.character_id == char.id
    assert profile.tone == "neutral"
    assert profile.sentence_length == "medium"
    assert profile.vocabulary_level == "standard"
    assert json.loads(profile.quirks_json) == []
    assert json.loads(profile.punctuation_style_json) == {}
    assert json.loads(profile.dialogue_markers_json) == []
    assert profile.id is not None


def test_create_voice_profile_custom():
    db, proj, char = _setup()
    profile = db.create_voice_profile(
        char.id,
        tone="formal",
        sentence_length="long",
        vocabulary_level="elevated",
        quirks=["avoids contractions", "uses archaic words"],
        punctuation_style={"ellipses": True, "exclamations": "low"},
        dialogue_markers=["Indeed", "I daresay"],
    )
    assert profile.tone == "formal"
    assert profile.sentence_length == "long"
    assert profile.vocabulary_level == "elevated"
    assert json.loads(profile.quirks_json) == [
        "avoids contractions", "uses archaic words",
    ]
    assert json.loads(profile.punctuation_style_json) == {
        "ellipses": True, "exclamations": "low",
    }
    assert json.loads(profile.dialogue_markers_json) == ["Indeed", "I daresay"]


def test_create_voice_profile_persists():
    db, proj, char = _setup()
    db.create_voice_profile(char.id, tone="casual")
    retrieved = db.get_voice_profile(char.id)
    assert retrieved is not None
    assert retrieved.tone == "casual"


# -- Read ----------------------------------------------------------------------

def test_get_voice_profile_none():
    db, proj, char = _setup()
    assert db.get_voice_profile(char.id) is None


def test_get_voice_profile_exists():
    db, proj, char = _setup()
    db.create_voice_profile(char.id, tone="abrasive")
    profile = db.get_voice_profile(char.id)
    assert profile is not None
    assert profile.tone == "abrasive"


# -- Update --------------------------------------------------------------------

def test_update_voice_profile_tone():
    db, proj, char = _setup()
    db.create_voice_profile(char.id, tone="neutral")
    updated = db.update_voice_profile(char.id, tone="polite")
    assert updated is not None
    assert updated.tone == "polite"
    assert updated.sentence_length == "medium"


def test_update_voice_profile_partial():
    db, proj, char = _setup()
    db.create_voice_profile(
        char.id,
        tone="formal",
        quirks=["old quirk"],
    )
    updated = db.update_voice_profile(char.id, quirks=["new quirk"])
    assert updated.tone == "formal"
    assert json.loads(updated.quirks_json) == ["new quirk"]


def test_update_voice_profile_all_fields():
    db, proj, char = _setup()
    db.create_voice_profile(char.id)
    updated = db.update_voice_profile(
        char.id,
        tone="abrasive",
        sentence_length="short",
        vocabulary_level="simple",
        quirks=["uses slang"],
        punctuation_style={"dashes": True},
        dialogue_markers=["Yo", "Look"],
    )
    assert updated.tone == "abrasive"
    assert updated.sentence_length == "short"
    assert updated.vocabulary_level == "simple"
    assert json.loads(updated.quirks_json) == ["uses slang"]
    assert json.loads(updated.punctuation_style_json) == {"dashes": True}
    assert json.loads(updated.dialogue_markers_json) == ["Yo", "Look"]


def test_update_voice_profile_nonexistent():
    db, proj, char = _setup()
    result = db.update_voice_profile(char.id, tone="formal")
    assert result is None


def test_update_voice_profile_updates_timestamp():
    db, proj, char = _setup()
    profile = db.create_voice_profile(char.id)
    original_ts = profile.updated_at
    updated = db.update_voice_profile(char.id, tone="casual")
    assert updated.updated_at >= original_ts


# -- Delete --------------------------------------------------------------------

def test_delete_voice_profile():
    db, proj, char = _setup()
    db.create_voice_profile(char.id)
    assert db.get_voice_profile(char.id) is not None
    db.delete_voice_profile(char.id)
    assert db.get_voice_profile(char.id) is None


def test_delete_voice_profile_nonexistent():
    db, proj, char = _setup()
    db.delete_voice_profile(char.id)


# -- Serialize / Deserialize ---------------------------------------------------

def test_serialize_voice_profile_data():
    db, proj, char = _setup()
    db.create_voice_profile(
        char.id,
        tone="casual",
        sentence_length="short",
        vocabulary_level="simple",
        quirks=["uses slang", "drops g's"],
        punctuation_style={"ellipses": True, "exclamations": "high"},
        dialogue_markers=["y'know", "like"],
    )
    data = db.get_voice_profile_data(char.id)
    assert data is not None
    assert data["character_id"] == char.id
    assert data["tone"] == "casual"
    assert data["sentence_length"] == "short"
    assert data["vocabulary_level"] == "simple"
    assert data["quirks"] == ["uses slang", "drops g's"]
    assert data["punctuation_style"] == {"ellipses": True, "exclamations": "high"}
    assert data["dialogue_markers"] == ["y'know", "like"]
    assert "last_updated" in data


def test_serialize_voice_profile_data_none():
    db, proj, char = _setup()
    assert db.get_voice_profile_data(char.id) is None


def test_serialize_empty_collections():
    db, proj, char = _setup()
    db.create_voice_profile(char.id)
    data = db.get_voice_profile_data(char.id)
    assert data["quirks"] == []
    assert data["punctuation_style"] == {}
    assert data["dialogue_markers"] == []


def test_deserialize_roundtrip():
    db, proj, char = _setup()
    original = {
        "tone": "polite",
        "sentence_length": "long",
        "vocabulary_level": "elevated",
        "quirks": ["never swears", "uses honorifics"],
        "punctuation_style": {"semicolons": True, "dashes": False},
        "dialogue_markers": ["If you please", "My dear"],
    }
    db.create_voice_profile(char.id, **original)
    data = db.get_voice_profile_data(char.id)
    for key in original:
        assert data[key] == original[key]


def test_json_fields_survive_special_characters():
    db, proj, char = _setup()
    db.create_voice_profile(
        char.id,
        quirks=["says \"indeed\"", "uses em—dashes"],
        dialogue_markers=["C'est la vie", "Très bien"],
    )
    data = db.get_voice_profile_data(char.id)
    assert data["quirks"] == ["says \"indeed\"", "uses em—dashes"]
    assert data["dialogue_markers"] == ["C'est la vie", "Très bien"]


def test_multiple_characters_separate_profiles():
    db = Database()
    proj = db.create_project("MultiVoice")
    alice = db.create_character(proj.id, "Alice")
    bob = db.create_character(proj.id, "Bob")
    db.create_voice_profile(alice.id, tone="formal")
    db.create_voice_profile(bob.id, tone="casual")
    assert db.get_voice_profile(alice.id).tone == "formal"
    assert db.get_voice_profile(bob.id).tone == "casual"


def test_model_has_last_updated():
    db, proj, char = _setup()
    profile = db.create_voice_profile(char.id)
    assert profile.updated_at is not None
