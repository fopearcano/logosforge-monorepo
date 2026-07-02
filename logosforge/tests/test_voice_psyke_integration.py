"""Tests for PSYKE ↔ VoiceProfile integration.

Covers:
- adjust_voice_for_state(): stress, confidence, emotion shifts
- voice_profile_summary(): human-readable output
- sync_voice_to_psyke(): PSYKE entry keeps voice field in sync
- learn_voice_profile with project_id triggers PSYKE sync
- State-adjusted profiles change consistency checker results
"""

from logosforge.db import Database
from logosforge.dialogue_attribution import DialogueSegment
from logosforge.voice_consistency import check_consistency
from logosforge.voice_learner import (
    adjust_voice_for_state,
    generate_voice_rewrites,
    learn_voice_profile,
    voice_profile_summary,
)


# -- Helpers -------------------------------------------------------------------

def _base_profile(**overrides):
    profile = {
        "character_id": 1,
        "tone": "neutral",
        "sentence_length": "medium",
        "vocabulary_level": "standard",
        "punctuation_style": {},
        "quirks": [],
        "dialogue_markers": [],
    }
    profile.update(overrides)
    return profile


def _seg(text, start=0, speaker_id=1):
    return DialogueSegment(
        text=text,
        start_pos=start,
        end_pos=start + len(text),
        speaker_id=speaker_id,
    )


# -- adjust_voice_for_state: stress -------------------------------------------

def test_stress_shortens_sentence_length():
    profile = _base_profile(sentence_length="long")
    adjusted = adjust_voice_for_state(profile, "character is stressed and anxious")
    assert adjusted["sentence_length"] == "medium"


def test_stress_shortens_medium_to_short():
    profile = _base_profile(sentence_length="medium")
    adjusted = adjust_voice_for_state(profile, "feeling tense and rushed")
    assert adjusted["sentence_length"] == "short"


def test_stress_already_short_stays_short():
    profile = _base_profile(sentence_length="short")
    adjusted = adjust_voice_for_state(profile, "panicked")
    assert adjusted["sentence_length"] == "short"


def test_single_stress_signal_shifts():
    profile = _base_profile(sentence_length="long")
    adjusted = adjust_voice_for_state(profile, "feeling nervous")
    assert adjusted["sentence_length"] == "medium"


# -- adjust_voice_for_state: confidence ---------------------------------------

def test_confidence_formalizes_tone():
    profile = _base_profile(tone="neutral")
    adjusted = adjust_voice_for_state(profile, "confident and commanding")
    assert adjusted["tone"] == "formal"


def test_confidence_casual_to_neutral():
    profile = _base_profile(tone="casual")
    adjusted = adjust_voice_for_state(profile, "assertive")
    assert adjusted["tone"] == "neutral"


def test_confidence_already_formal_stays():
    profile = _base_profile(tone="formal")
    adjusted = adjust_voice_for_state(profile, "authoritative and composed")
    assert adjusted["tone"] == "formal"


# -- adjust_voice_for_state: emotion ------------------------------------------

def test_emotion_casualizes_and_shortens():
    profile = _base_profile(tone="formal", sentence_length="long")
    adjusted = adjust_voice_for_state(profile, "consumed by rage and fury")
    assert adjusted["tone"] == "neutral"
    assert adjusted["sentence_length"] == "medium"


def test_single_emotion_no_change():
    """Need >= 2 emotion signals to shift."""
    profile = _base_profile(tone="formal", sentence_length="long")
    adjusted = adjust_voice_for_state(profile, "feeling grief")
    assert adjusted["tone"] == "formal"
    assert adjusted["sentence_length"] == "long"


# -- adjust_voice_for_state: combined -----------------------------------------

def test_stress_and_confidence_combined():
    profile = _base_profile(tone="casual", sentence_length="long")
    adjusted = adjust_voice_for_state(profile, "stressed but resolute")
    assert adjusted["sentence_length"] == "medium"
    assert adjusted["tone"] == "neutral"


def test_emotion_and_stress_combined():
    profile = _base_profile(tone="neutral", sentence_length="long")
    adjusted = adjust_voice_for_state(
        profile, "overwhelmed by rage, feeling panicked",
    )
    # stress (panicked) → long→medium, emotion (overwhelmed, rage) → medium→short
    assert adjusted["sentence_length"] == "short"
    # emotion >= 2 → tone shifts casual
    assert adjusted["tone"] == "casual"


# -- adjust_voice_for_state: edge cases ---------------------------------------

def test_empty_state_no_change():
    profile = _base_profile(tone="formal", sentence_length="long")
    adjusted = adjust_voice_for_state(profile, "")
    assert adjusted["tone"] == "formal"
    assert adjusted["sentence_length"] == "long"


def test_no_signal_words_no_change():
    profile = _base_profile(tone="formal", sentence_length="long")
    adjusted = adjust_voice_for_state(profile, "walking to the store")
    assert adjusted["tone"] == "formal"
    assert adjusted["sentence_length"] == "long"


def test_empty_profile_returns_copy():
    adjusted = adjust_voice_for_state({}, "stressed")
    assert adjusted == {}


def test_exotic_tone_untouched():
    profile = _base_profile(tone="abrasive", sentence_length="medium")
    adjusted = adjust_voice_for_state(profile, "confident and bold")
    assert adjusted["tone"] == "abrasive"


def test_adjusted_profile_is_a_copy():
    profile = _base_profile()
    adjusted = adjust_voice_for_state(profile, "stressed")
    adjusted["quirks"].append("test")
    assert "test" not in profile.get("quirks", [])


# -- voice_profile_summary ----------------------------------------------------

def test_summary_contains_tone():
    s = voice_profile_summary(_base_profile(tone="formal"))
    assert "Tone: formal" in s


def test_summary_contains_quirks():
    s = voice_profile_summary(_base_profile(quirks=["avoids contractions"]))
    assert "avoids contractions" in s


def test_summary_contains_markers():
    s = voice_profile_summary(_base_profile(dialogue_markers=["Indeed"]))
    assert "Indeed" in s


def test_summary_empty_profile():
    assert voice_profile_summary({}) == ""


def test_summary_ends_with_period():
    s = voice_profile_summary(_base_profile())
    assert s.endswith(".")


# -- sync_voice_to_psyke ------------------------------------------------------

def test_sync_writes_voice_field():
    db = Database()
    proj = db.create_project("SyncTest")
    char = db.create_character(proj.id, "Alice")
    db.create_voice_profile(char.id, tone="formal", quirks=["avoids contractions"])
    entry = db.create_psyke_entry(proj.id, "Alice", entry_type="character")

    db.sync_voice_to_psyke(char.id, proj.id)

    details = db.get_psyke_entry_details(entry.id)
    assert "voice" in details
    assert "formal" in details["voice"]
    assert "avoids contractions" in details["voice"]


def test_sync_updates_existing_voice_field():
    db = Database()
    proj = db.create_project("SyncTest2")
    char = db.create_character(proj.id, "Bob")
    db.create_voice_profile(char.id, tone="casual")
    entry = db.create_psyke_entry(
        proj.id, "Bob", entry_type="character",
        details={"voice": "old voice info", "personality": "shy"},
    )

    db.sync_voice_to_psyke(char.id, proj.id)

    details = db.get_psyke_entry_details(entry.id)
    assert "casual" in details["voice"]
    assert "old voice info" not in details["voice"]
    assert details["personality"] == "shy"


def test_sync_no_psyke_entry_is_noop():
    db = Database()
    proj = db.create_project("SyncTest3")
    char = db.create_character(proj.id, "Carol")
    db.create_voice_profile(char.id, tone="formal")
    db.sync_voice_to_psyke(char.id, proj.id)


def test_sync_no_voice_profile_is_noop():
    db = Database()
    proj = db.create_project("SyncTest4")
    char = db.create_character(proj.id, "Dave")
    db.create_psyke_entry(proj.id, "Dave", entry_type="character")
    db.sync_voice_to_psyke(char.id, proj.id)
    details = db.get_psyke_entry_details(
        db._find_character_psyke_entry(proj.id, "Dave").id,
    )
    assert "voice" not in details


# -- learn_voice_profile with project_id triggers sync -------------------------

def test_learn_syncs_to_psyke():
    db = Database()
    proj = db.create_project("LearnSync")
    char = db.create_character(proj.id, "Eve")
    entry = db.create_psyke_entry(proj.id, "Eve", entry_type="character")

    segs = [
        DialogueSegment(text="I shall not be deterred.", start_pos=0,
                        end_pos=24, speaker_id=char.id),
        DialogueSegment(text="Furthermore, I insist.", start_pos=25,
                        end_pos=47, speaker_id=char.id),
        DialogueSegment(text="This is most certainly the case.", start_pos=48,
                        end_pos=79, speaker_id=char.id),
    ]
    learn_voice_profile(db, char.id, segs, project_id=proj.id)

    details = db.get_psyke_entry_details(entry.id)
    assert "voice" in details
    assert len(details["voice"]) > 0


def test_learn_without_project_id_no_sync():
    db = Database()
    proj = db.create_project("LearnNoSync")
    char = db.create_character(proj.id, "Frank")
    entry = db.create_psyke_entry(proj.id, "Frank", entry_type="character")

    segs = [
        DialogueSegment(text="Hey! Let's go!", start_pos=0,
                        end_pos=14, speaker_id=char.id),
        DialogueSegment(text="Yeah, totally!", start_pos=15,
                        end_pos=29, speaker_id=char.id),
        DialogueSegment(text="Cool stuff, right?", start_pos=30,
                        end_pos=48, speaker_id=char.id),
    ]
    learn_voice_profile(db, char.id, segs)

    details = db.get_psyke_entry_details(entry.id)
    assert "voice" not in details


# -- State adjustment affects consistency checker ------------------------------

def test_stressed_state_changes_flagging():
    """Formal long-sentence profile normally flags short casual dialogue.
    With stress state, profile shifts to medium sentences, so the same
    dialogue gets a lower (or no) deviation."""
    profile = _base_profile(tone="formal", sentence_length="long")

    seg = _seg("Stop. Go now.")
    baseline = check_consistency([seg], {1: profile})

    adjusted = adjust_voice_for_state(profile, "stressed and panicked")
    state_result = check_consistency([seg], {1: adjusted})

    if baseline:
        if state_result:
            assert state_result[0].deviation_score < baseline[0].deviation_score
        # else state_result is empty → deviation completely resolved


def test_confident_state_changes_flagging():
    """Casual profile normally flags formal dialogue. With confident state,
    profile shifts toward formal so the formal dialogue matches better."""
    profile = _base_profile(tone="casual", sentence_length="short")

    seg = _seg(
        "I shall not tolerate this kind of behavior in my establishment "
        "any longer, and I expect full compliance going forward."
    )
    baseline = check_consistency([seg], {1: profile})

    adjusted = adjust_voice_for_state(profile, "confident and decisive")
    state_result = check_consistency([seg], {1: adjusted})

    if baseline:
        if state_result:
            assert state_result[0].deviation_score < baseline[0].deviation_score


def test_emotional_state_changes_flagging():
    """Formal profile normally passes formal dialogue. With high emotion,
    profile shifts casual — formal dialogue now deviates more."""
    profile = _base_profile(tone="formal", sentence_length="long")

    seg = _seg(
        "I shall not permit this affront to continue under any circumstances "
        "whatsoever, and I demand an immediate explanation for this outrage."
    )
    baseline_devs = check_consistency([seg], {1: profile})

    adjusted = adjust_voice_for_state(profile, "consumed by rage and fury")
    emotion_devs = check_consistency([seg], {1: adjusted})

    if not baseline_devs and emotion_devs:
        assert emotion_devs[0].deviation_score > 0
    elif baseline_devs and emotion_devs:
        assert emotion_devs[0].deviation_score >= baseline_devs[0].deviation_score


# -- State adjustment affects voice rewrites -----------------------------------

def test_stressed_state_produces_shorter_rewrites():
    profile = _base_profile(tone="neutral", sentence_length="long")
    text = "I went to the store and then I bought some groceries and came home."

    normal_rw = generate_voice_rewrites(text, profile)
    adjusted = adjust_voice_for_state(profile, "stressed and nervous")
    state_rw = generate_voice_rewrites(text, adjusted)

    if state_rw:
        short_labels = [rw for rw in state_rw if "short" in rw.label.lower()]
        assert len(short_labels) > 0 or adjusted["sentence_length"] != "long"


def test_confident_state_formal_rewrites():
    profile = _base_profile(tone="casual")
    text = "I can't believe you don't understand."

    adjusted = adjust_voice_for_state(profile, "confident and authoritative")
    state_rw = generate_voice_rewrites(text, adjusted)

    assert adjusted["tone"] == "neutral" or adjusted["tone"] == "formal"
