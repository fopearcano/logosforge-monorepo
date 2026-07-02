"""Tests for voice consistency checker."""

from logosforge.dialogue_attribution import DialogueSegment
from logosforge.voice_consistency import (
    VoiceDeviation,
    _score_segment,
    check_consistency,
)


def _seg(text: str, speaker_id: int | None = 1, pos: int = 0) -> DialogueSegment:
    return DialogueSegment(
        text=text,
        start_pos=pos,
        end_pos=pos + len(text),
        speaker_id=speaker_id,
    )


def _casual_profile(cid: int = 1) -> dict:
    return {
        "character_id": cid,
        "tone": "casual",
        "sentence_length": "short",
        "vocabulary_level": "simple",
        "punctuation_style": {
            "exclamations": 0.6,
            "questions": 0.2,
            "ellipses": 0.1,
            "dashes": 0.0,
        },
        "quirks": ["heavy contraction use"],
        "dialogue_markers": ["Hey"],
    }


def _formal_profile(cid: int = 1) -> dict:
    return {
        "character_id": cid,
        "tone": "formal",
        "sentence_length": "long",
        "vocabulary_level": "elevated",
        "punctuation_style": {
            "exclamations": 0.0,
            "questions": 0.3,
            "ellipses": 0.0,
            "dashes": 0.0,
        },
        "quirks": ["avoids contractions"],
        "dialogue_markers": ["Indeed"],
    }


# -- Matching lines pass (no deviation) ---------------------------------------

def test_casual_line_matches_casual_profile():
    profiles = {1: _casual_profile()}
    segs = [_seg("Can't wait! Let's go!")]
    devs = check_consistency(segs, profiles)
    assert devs == []


def test_formal_line_matches_formal_profile():
    profiles = {1: _formal_profile()}
    segs = [_seg(
        "I must insist that we proceed with the utmost caution in this matter."
    )]
    devs = check_consistency(segs, profiles)
    assert devs == []


def test_neutral_line_on_neutral_profile():
    profiles = {1: {
        "character_id": 1,
        "tone": "neutral",
        "sentence_length": "medium",
        "vocabulary_level": "standard",
        "punctuation_style": {},
        "quirks": [],
        "dialogue_markers": [],
    }}
    segs = [_seg("I think we should head out before noon.")]
    devs = check_consistency(segs, profiles)
    assert devs == []


# -- Clear mismatches get flagged ----------------------------------------------

def test_formal_line_on_casual_profile_flagged():
    profiles = {1: _casual_profile()}
    segs = [_seg(
        "I must insist that we proceed with the utmost caution regarding "
        "this matter, for the consequences would be most severe."
    )]
    devs = check_consistency(segs, profiles)
    assert len(devs) == 1
    assert devs[0].deviation_score > 0
    assert any("formal" in r for r in devs[0].reasons)


def test_casual_line_on_formal_profile_flagged():
    profiles = {1: _formal_profile()}
    segs = [_seg("Can't. Don't. Won't. I'm out.")]
    devs = check_consistency(segs, profiles)
    assert len(devs) == 1
    assert any("casual" in r for r in devs[0].reasons)


def test_long_sentence_on_short_profile_flagged():
    profiles = {1: _casual_profile()}
    segs = [_seg(
        "I think we should probably consider all of the different options "
        "that are available to us before making any kind of final decision "
        "about what exactly we want to do next."
    )]
    devs = check_consistency(segs, profiles)
    assert len(devs) == 1
    assert any("sentence length" in r for r in devs[0].reasons)


def test_short_sentence_on_long_profile_flagged():
    profiles = {1: _formal_profile()}
    segs = [_seg("Nah. Nope. Done.")]
    devs = check_consistency(segs, profiles)
    assert len(devs) == 1
    assert any("sentence length" in r or "casual" in r for r in devs[0].reasons)


# -- Deviation score -----------------------------------------------------------

def test_deviation_score_between_zero_and_one():
    profiles = {1: _casual_profile()}
    segs = [_seg(
        "I must endeavour to proceed with the utmost formality in this matter."
    )]
    devs = check_consistency(segs, profiles)
    assert len(devs) == 1
    assert 0.0 <= devs[0].deviation_score <= 1.0


def test_perfect_match_score_near_zero():
    profile = _casual_profile()
    score, reasons = _score_segment("Can't wait! Let's go!", profile)
    assert score < 0.3


def test_extreme_mismatch_score_high():
    profile = _casual_profile()
    score, reasons = _score_segment(
        "I must insist that we endeavour to proceed with the utmost caution "
        "regarding this exceedingly important matter, for the consequences "
        "would undoubtedly be most severe and remarkably far-reaching.",
        profile,
    )
    assert score >= 0.45


# -- Reasons -------------------------------------------------------------------

def test_reasons_max_two():
    profiles = {1: _casual_profile()}
    segs = [_seg(
        "I must insist that we endeavour to proceed with the utmost caution "
        "regarding this exceedingly important matter."
    )]
    devs = check_consistency(segs, profiles)
    if devs:
        assert len(devs[0].reasons) <= 2


def test_tone_reason_content():
    profile = _casual_profile()
    score, reasons = _score_segment(
        "I believe we should proceed with caution regarding this matter at hand.",
        profile,
    )
    tone_reasons = [r for r in reasons if "formal" in r or "casual" in r]
    assert len(tone_reasons) >= 1


def test_punctuation_mismatch_reason():
    profile = {
        "character_id": 1,
        "tone": "neutral",
        "sentence_length": "medium",
        "vocabulary_level": "standard",
        "punctuation_style": {
            "exclamations": 1.0,
            "questions": 0.0,
            "ellipses": 1.0,
            "dashes": 0.0,
        },
        "quirks": [],
        "dialogue_markers": [],
    }
    score, reasons = _score_segment(
        "I think we should head out before it gets dark.",
        profile,
    )
    punct_reasons = [r for r in reasons if "punctuation" in r]
    assert len(punct_reasons) == 1


# -- Filtering behavior -------------------------------------------------------

def test_skips_segments_with_no_speaker():
    profiles = {1: _casual_profile()}
    segs = [_seg(
        "I must insist on proceeding with the utmost formality.",
        speaker_id=None,
    )]
    devs = check_consistency(segs, profiles)
    assert devs == []


def test_skips_segments_with_no_profile():
    profiles = {1: _casual_profile()}
    segs = [_seg(
        "I must insist on proceeding with the utmost formality.",
        speaker_id=99,
    )]
    devs = check_consistency(segs, profiles)
    assert devs == []


def test_skips_empty_text():
    profiles = {1: _casual_profile()}
    segs = [_seg("   ", speaker_id=1)]
    devs = check_consistency(segs, profiles)
    assert devs == []


# -- Threshold -----------------------------------------------------------------

def test_custom_threshold_low_catches_more():
    profiles = {1: _casual_profile()}
    segs = [_seg("I think we should consider our options carefully.")]
    devs_high = check_consistency(segs, profiles, threshold=0.8)
    devs_low = check_consistency(segs, profiles, threshold=0.1)
    assert len(devs_low) >= len(devs_high)


def test_threshold_zero_flags_everything():
    profiles = {1: _casual_profile()}
    segs = [_seg("Hey! Cool!")]
    devs = check_consistency(segs, profiles, threshold=0.0)
    assert len(devs) == 1


def test_threshold_one_flags_nothing():
    profiles = {1: _casual_profile()}
    segs = [_seg(
        "I must insist on the most formal proceedings.",
        speaker_id=1,
    )]
    devs = check_consistency(segs, profiles, threshold=1.01)
    assert devs == []


# -- Multi-speaker consistency ------------------------------------------------

def test_multi_speaker_independent():
    profiles = {
        1: _casual_profile(1),
        2: _formal_profile(2),
    }
    segs = [
        _seg("Can't wait! Let's go!", speaker_id=1),
        _seg(
            "I must insist that we proceed with the utmost caution in this matter.",
            speaker_id=2,
        ),
    ]
    devs = check_consistency(segs, profiles)
    assert devs == []


def test_multi_speaker_one_deviates():
    profiles = {
        1: _casual_profile(1),
        2: _formal_profile(2),
    }
    segs = [
        _seg("Can't wait! Let's go!", speaker_id=1),
        _seg("Yo, ain't nobody got time. Let's bounce.", speaker_id=2),
    ]
    devs = check_consistency(segs, profiles)
    assert len(devs) == 1
    assert devs[0].segment.speaker_id == 2


def test_multi_speaker_both_deviate():
    profiles = {
        1: _casual_profile(1),
        2: _formal_profile(2),
    }
    segs = [
        _seg(
            "I must insist that we proceed with the utmost caution regarding "
            "this exceedingly important matter at hand.",
            speaker_id=1,
        ),
        _seg("Nah. Can't. Won't. I'm out.", speaker_id=2),
    ]
    devs = check_consistency(segs, profiles)
    assert len(devs) == 2
    speaker_ids = {d.segment.speaker_id for d in devs}
    assert speaker_ids == {1, 2}


# -- VoiceDeviation dataclass --------------------------------------------------

def test_voice_deviation_fields():
    seg = _seg("Hello.", speaker_id=1)
    dev = VoiceDeviation(segment=seg, deviation_score=0.5, reasons=["test"])
    assert dev.segment is seg
    assert dev.deviation_score == 0.5
    assert dev.reasons == ["test"]


# -- Vocabulary mismatch -------------------------------------------------------

def test_elevated_vocab_on_simple_profile():
    profiles = {1: _casual_profile()}
    segs = [_seg(
        "Nevertheless, I find the consequences undoubtedly severe and "
        "furthermore the endeavour is exceedingly remarkable, "
        "thus we shall proceed hence.",
    )]
    devs = check_consistency(segs, profiles)
    assert len(devs) == 1
    all_reasons = " ".join(devs[0].reasons)
    assert "vocabulary" in all_reasons or "formal" in all_reasons


def test_simple_vocab_on_elevated_profile():
    profiles = {1: _formal_profile()}
    segs = [_seg("Yeah dude, gonna grab some cool stuff, dunno.")]
    devs = check_consistency(segs, profiles)
    assert len(devs) == 1
