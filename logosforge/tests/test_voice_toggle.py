"""Tests for Voice Consistency toggle and sensitivity controls."""

from logosforge.db import Database
from logosforge.dialogue_attribution import DialogueSegment
from logosforge.voice_consistency import (
    VOICE_SENSITIVITY_LEVELS,
    VoiceDeviation,
    check_consistency,
    sensitivity_threshold,
)
from logosforge.ui.writing_core_view import WritingCoreView


# -- Helpers -------------------------------------------------------------------

def _setup():
    db = Database()
    proj = db.create_project("VoiceToggle")
    char = db.create_character(proj.id, "Alice")
    db.create_voice_profile(char.id, tone="formal", quirks=["avoids contractions"])
    s1 = db.create_scene(
        proj.id, "Scene",
        content="Hello world.",
        character_ids=[char.id],
    )
    return db, proj, char, s1


def _seg(text, speaker_id=1):
    return DialogueSegment(
        text=text, start_pos=0, end_pos=len(text), speaker_id=speaker_id,
    )


# -- Sensitivity levels exist -------------------------------------------------

def test_three_sensitivity_levels():
    assert VOICE_SENSITIVITY_LEVELS == ("low", "medium", "high")


def test_low_threshold_is_highest():
    assert sensitivity_threshold("low") > sensitivity_threshold("medium")


def test_high_threshold_is_lowest():
    assert sensitivity_threshold("high") < sensitivity_threshold("medium")


def test_unknown_level_returns_default():
    assert sensitivity_threshold("unknown") == 0.45


# -- Sensitivity affects flagging ----------------------------------------------

def test_high_sensitivity_flags_more():
    profile = {
        "character_id": 1,
        "tone": "formal",
        "sentence_length": "long",
        "vocabulary_level": "elevated",
        "punctuation_style": {},
        "quirks": [],
        "dialogue_markers": [],
    }
    seg = _seg("I think we should go now, it is getting late.")
    low_devs = check_consistency(
        [seg], {1: profile}, threshold=sensitivity_threshold("low"),
    )
    high_devs = check_consistency(
        [seg], {1: profile}, threshold=sensitivity_threshold("high"),
    )
    assert len(high_devs) >= len(low_devs)


def test_low_sensitivity_flags_fewer():
    profile = {
        "character_id": 1,
        "tone": "formal",
        "sentence_length": "medium",
        "vocabulary_level": "standard",
        "punctuation_style": {},
        "quirks": [],
        "dialogue_markers": [],
    }
    seg = _seg("Hey, let's go grab some stuff yeah?")
    medium_devs = check_consistency(
        [seg], {1: profile}, threshold=sensitivity_threshold("medium"),
    )
    low_devs = check_consistency(
        [seg], {1: profile}, threshold=sensitivity_threshold("low"),
    )
    assert len(low_devs) <= len(medium_devs)


def test_medium_sensitivity_between():
    thr_low = sensitivity_threshold("low")
    thr_med = sensitivity_threshold("medium")
    thr_high = sensitivity_threshold("high")
    assert thr_high < thr_med < thr_low


# -- Toggle is instant --------------------------------------------------------

def test_toggle_on_enables_editors():
    db, proj, char, s1 = _setup()
    view = WritingCoreView(db, proj.id)
    editor = list(view._editors.values())[0]

    assert view._voice_hints_checking is False
    assert editor._voice_hints_enabled is False

    view._toggle_voice_hints()

    assert view._voice_hints_checking is True
    assert editor._voice_hints_enabled is True


def test_toggle_off_clears_deviations():
    db, proj, char, s1 = _setup()
    view = WritingCoreView(db, proj.id)
    editor = list(view._editors.values())[0]

    seg = DialogueSegment(text="test", start_pos=0, end_pos=4, speaker_id=1)
    dev = VoiceDeviation(segment=seg, deviation_score=0.6, reasons=["test"])
    editor._voice_deviations = [dev]
    editor._voice_hints_enabled = True
    view._voice_hints_checking = True

    view._toggle_voice_hints()

    assert view._voice_hints_checking is False
    assert editor._voice_hints_enabled is False
    assert editor._voice_deviations == []


def test_toggle_on_off_on_cycle():
    db, proj, char, s1 = _setup()
    view = WritingCoreView(db, proj.id)
    editor = list(view._editors.values())[0]

    view._toggle_voice_hints()
    assert view._voice_hints_checking is True

    view._toggle_voice_hints()
    assert view._voice_hints_checking is False
    assert editor._voice_hints_enabled is False

    view._toggle_voice_hints()
    assert view._voice_hints_checking is True
    assert editor._voice_hints_enabled is True


# -- Toggle persists per project -----------------------------------------------

def test_toggle_persists():
    db, proj, char, s1 = _setup()
    view = WritingCoreView(db, proj.id)

    view._toggle_voice_hints()
    settings = db.get_project_settings(proj.id)
    assert settings.get("voice_hints") is True

    view._toggle_voice_hints()
    settings = db.get_project_settings(proj.id)
    assert settings.get("voice_hints") is False


# -- Sensitivity persists per project ------------------------------------------

def test_sensitivity_persists():
    db, proj, char, s1 = _setup()
    view = WritingCoreView(db, proj.id)

    view._set_voice_sensitivity("high")
    settings = db.get_project_settings(proj.id)
    assert settings.get("voice_sensitivity") == "high"


def test_sensitivity_default_is_medium():
    db, proj, char, s1 = _setup()
    view = WritingCoreView(db, proj.id)
    assert view._voice_sensitivity == "medium"


def test_sensitivity_loaded_from_settings():
    db, proj, char, s1 = _setup()
    settings = db.get_project_settings(proj.id)
    settings["voice_sensitivity"] = "low"
    db.save_project_settings(proj.id, settings)

    view = WritingCoreView(db, proj.id)
    assert view._voice_sensitivity == "low"


def test_invalid_sensitivity_defaults_to_medium():
    db, proj, char, s1 = _setup()
    settings = db.get_project_settings(proj.id)
    settings["voice_sensitivity"] = "extreme"
    db.save_project_settings(proj.id, settings)

    view = WritingCoreView(db, proj.id)
    assert view._voice_sensitivity == "medium"


# -- OFF → no checks ----------------------------------------------------------

def test_off_means_no_underlines():
    db, proj, char, s1 = _setup()
    view = WritingCoreView(db, proj.id)
    editor = list(view._editors.values())[0]

    seg = DialogueSegment(text="test", start_pos=0, end_pos=4, speaker_id=1)
    dev = VoiceDeviation(segment=seg, deviation_score=0.6, reasons=["issue"])
    editor._voice_deviations = [dev]
    editor._voice_hints_enabled = False

    editor.setPlainText("test text here.")
    editor.apply_grammar_underlines()
    sels = editor.extraSelections()
    assert len(sels) == 0


# -- ON → hints visible -------------------------------------------------------

def test_on_shows_underlines():
    db, proj, char, s1 = _setup()
    view = WritingCoreView(db, proj.id)
    editor = list(view._editors.values())[0]

    from logosforge.dialogue_attribution import DialogueSegment as DS
    from logosforge.voice_consistency import VoiceDeviation as VD

    editor.setPlainText("She said hello to the world.")
    seg = DS(text="She said h", start_pos=0, end_pos=10, speaker_id=1)
    dev = VD(segment=seg, deviation_score=0.6,
             reasons=["too formal for this character"])
    editor._voice_deviations = [dev]
    editor._voice_hints_enabled = True

    editor.apply_grammar_underlines()
    sels = editor.extraSelections()
    assert len(sels) == 1
    assert "too formal" in sels[0].format.toolTip()
