"""Tests for voice profile learning — inference, merge, and evolution."""

import json

from logosforge.db import Database
from logosforge.dialogue_attribution import DialogueSegment
from logosforge.voice_learner import (
    VoiceAnalysis,
    _EXISTING_WEIGHT,
    _LEARNED_WEIGHT,
    analyze_voice,
    learn_voice_profile,
)


def _seg(text: str, speaker_id: int | None, pos: int = 0) -> DialogueSegment:
    return DialogueSegment(
        text=text,
        start_pos=pos,
        end_pos=pos + len(text),
        speaker_id=speaker_id,
    )


def _setup():
    db = Database()
    proj = db.create_project("VoiceLearnerTest")
    char = db.create_character(proj.id, "Alice")
    return db, proj, char


# -- analyze_voice: sentence length -------------------------------------------

def test_short_sentences():
    segs = [_seg("Go now.", 1), _seg("Run fast.", 1), _seg("Stop.", 1)]
    a = analyze_voice(segs, 1)
    assert a.sentence_length == "short"


def test_medium_sentences():
    segs = [
        _seg("I think we should probably head out soon.", 1),
        _seg("The weather looks like it might clear up.", 1),
        _seg("Let me grab my coat before we leave.", 1),
    ]
    a = analyze_voice(segs, 1)
    assert a.sentence_length == "medium"


def test_long_sentences():
    segs = [
        _seg(
            "I have been thinking about this for quite a long time and I believe "
            "that we should carefully consider all of our options before making "
            "any kind of decision about the matter at hand.",
            1,
        ),
        _seg(
            "Furthermore it seems to me that the situation requires a great deal "
            "more deliberation than we have thus far been willing to undertake "
            "in our previous discussions on this topic.",
            1,
        ),
    ]
    a = analyze_voice(segs, 1)
    assert a.sentence_length == "long"


# -- analyze_voice: tone ------------------------------------------------------

def test_casual_tone():
    segs = [
        _seg("I'm gonna go. You're not coming?", 1),
        _seg("Can't believe it. Won't do it.", 1),
        _seg("Don't care. I'm out.", 1),
        _seg("Ain't that fun? Let's go.", 1),
    ]
    a = analyze_voice(segs, 1)
    assert a.tone == "casual"


def test_formal_tone():
    segs = [
        _seg(
            "I believe we should proceed with caution regarding this matter.",
            1,
        ),
        _seg(
            "It would be prudent to consider the ramifications of such actions.",
            1,
        ),
        _seg(
            "I must insist that we adhere to the established protocols at once.",
            1,
        ),
        _seg(
            "One cannot simply disregard the consequences of such decisions.",
            1,
        ),
    ]
    a = analyze_voice(segs, 1)
    assert a.tone == "formal"


def test_neutral_tone():
    segs = [
        _seg("I think we should head out before noon.", 1),
        _seg("The weather looks fine for a walk.", 1),
        _seg("We can grab lunch on the way there.", 1),
    ]
    a = analyze_voice(segs, 1)
    assert a.tone == "neutral"


# -- analyze_voice: vocabulary -------------------------------------------------

def test_elevated_vocabulary():
    segs = [
        _seg("Nevertheless, I find this matter most concerning.", 1),
        _seg("Furthermore, the consequences are undoubtedly severe.", 1),
        _seg("Consequently, we shall proceed with utmost care.", 1),
        _seg("Indeed, one must endeavour to persevere.", 1),
    ]
    a = analyze_voice(segs, 1)
    assert a.vocabulary_level == "elevated"


def test_simple_vocabulary():
    segs = [
        _seg("Yeah dude, that's totally cool stuff.", 1),
        _seg("Nah, gonna pass on that.", 1),
        _seg("Hey yo, lemme get that thing.", 1),
        _seg("Nope, ain't gonna happen, dunno why.", 1),
    ]
    a = analyze_voice(segs, 1)
    assert a.vocabulary_level == "simple"


def test_standard_vocabulary():
    segs = [
        _seg("I think the meeting went well today.", 1),
        _seg("We should plan for the presentation.", 1),
        _seg("The report is ready for review.", 1),
    ]
    a = analyze_voice(segs, 1)
    assert a.vocabulary_level == "standard"


# -- analyze_voice: punctuation ------------------------------------------------

def test_punctuation_exclamations():
    segs = [
        _seg("Watch out!", 1),
        _seg("Run! Now!", 1),
        _seg("Incredible!", 1),
        _seg("This is amazing!", 1),
    ]
    a = analyze_voice(segs, 1)
    assert a.punctuation_style["exclamations"] == 1.0


def test_punctuation_questions():
    segs = [
        _seg("Where are you going?", 1),
        _seg("What time is it?", 1),
        _seg("I have no idea.", 1),
    ]
    a = analyze_voice(segs, 1)
    assert a.punctuation_style["questions"] > 0.5


def test_punctuation_ellipses():
    segs = [
        _seg("Well... I suppose...", 1),
        _seg("Maybe... if you say so...", 1),
        _seg("I guess that works.", 1),
    ]
    a = analyze_voice(segs, 1)
    assert a.punctuation_style["ellipses"] > 0.5


def test_punctuation_dashes():
    segs = [
        _seg("Listen — I need to tell you something.", 1),
        _seg("It was — well — complicated.", 1),
        _seg("Fine then.", 1),
    ]
    a = analyze_voice(segs, 1)
    assert a.punctuation_style["dashes"] > 0.5


# -- analyze_voice: quirks -----------------------------------------------------

def test_quirk_avoids_contractions():
    segs = [
        _seg("I will not do that.", 1),
        _seg("She does not understand.", 1),
        _seg("We cannot go there.", 1),
        _seg("It is simply not possible.", 1),
    ]
    a = analyze_voice(segs, 1)
    assert "avoids contractions" in a.quirks


def test_quirk_heavy_contractions():
    segs = [
        _seg("I'm don't won't can't.", 1),
        _seg("She's he's it's they're.", 1),
        _seg("We've I'll you'd she'll.", 1),
    ]
    a = analyze_voice(segs, 1)
    assert "heavy contraction use" in a.quirks


def test_quirk_trails_off():
    segs = [
        _seg("Well... I suppose...", 1),
        _seg("Maybe... just maybe...", 1),
        _seg("I thought... never mind...", 1),
        _seg("Sure thing.", 1),
    ]
    a = analyze_voice(segs, 1)
    assert "trails off frequently" in a.quirks


def test_quirk_exclamatory():
    segs = [
        _seg("Amazing!", 1),
        _seg("Incredible!", 1),
        _seg("Wow!", 1),
        _seg("Yes!", 1),
    ]
    a = analyze_voice(segs, 1)
    assert "exclamatory speaker" in a.quirks


# -- analyze_voice: dialogue markers -------------------------------------------

def test_dialogue_markers_detected():
    segs = [
        _seg("Well, I think so.", 1),
        _seg("Well, that makes sense.", 1),
        _seg("Well, if you say so.", 1),
        _seg("Something else entirely.", 1),
    ]
    a = analyze_voice(segs, 1)
    assert "Well" in a.dialogue_markers


def test_no_markers_below_threshold():
    segs = [
        _seg("Look, we should go.", 1),
        _seg("I have no idea.", 1),
        _seg("The sky is blue.", 1),
        _seg("Let me think.", 1),
        _seg("Tomorrow is fine.", 1),
        _seg("Maybe so.", 1),
        _seg("Not sure about that.", 1),
        _seg("Could be worse.", 1),
        _seg("Fair enough.", 1),
        _seg("Absolutely.", 1),
    ]
    a = analyze_voice(segs, 1)
    assert "Look" not in a.dialogue_markers


# -- analyze_voice: confidence -------------------------------------------------

def test_confidence_zero_with_no_samples():
    a = analyze_voice([], 1)
    assert a.confidence == 0.0
    assert a.sample_count == 0


def test_confidence_low_with_few_samples():
    segs = [_seg("Hello.", 1)]
    a = analyze_voice(segs, 1)
    assert 0.0 < a.confidence < 0.3


def test_confidence_moderate():
    segs = [_seg("Hello.", 1) for _ in range(5)]
    a = analyze_voice(segs, 1)
    assert 0.3 <= a.confidence < 1.0


def test_confidence_caps_at_one():
    segs = [_seg("Hello.", 1) for _ in range(50)]
    a = analyze_voice(segs, 1)
    assert a.confidence == 1.0


def test_only_counts_matching_speaker():
    segs = [
        _seg("Hello from Alice.", 1),
        _seg("Hello from Bob.", 2),
        _seg("Another from Alice.", 1),
    ]
    a = analyze_voice(segs, 1)
    assert a.sample_count == 2


# -- learn_voice_profile: creates if missing -----------------------------------

def test_learn_creates_profile():
    db, proj, char = _setup()
    segs = [
        _seg("I'm gonna go now.", char.id),
        _seg("Can't stop won't stop.", char.id),
        _seg("Don't worry about it.", char.id),
    ]
    analysis = learn_voice_profile(db, char.id, segs)
    assert analysis.confidence > 0

    profile = db.get_voice_profile_data(char.id)
    assert profile is not None
    assert profile["tone"] == analysis.tone


# -- learn_voice_profile: merges with existing ---------------------------------

def test_learn_merges_tone():
    db, proj, char = _setup()
    db.create_voice_profile(char.id, tone="neutral")

    segs = [
        _seg("I'm gonna go. You're not coming?", char.id),
        _seg("Can't believe it. Won't do it.", char.id),
        _seg("Don't care. I'm out.", char.id),
        _seg("Ain't that fun? Let's go.", char.id),
    ]
    learn_voice_profile(db, char.id, segs)

    profile = db.get_voice_profile_data(char.id)
    assert profile["tone"] == "casual"


def test_learn_merges_quirks():
    db, proj, char = _setup()
    db.create_voice_profile(char.id, quirks=["uses archaic words"])

    segs = [
        _seg("Well... maybe...", char.id),
        _seg("I suppose... perhaps...", char.id),
        _seg("Could be... not sure...", char.id),
        _seg("Hmm... let me think...", char.id),
    ]
    learn_voice_profile(db, char.id, segs)

    profile = db.get_voice_profile_data(char.id)
    assert "uses archaic words" in profile["quirks"]
    assert "trails off frequently" in profile["quirks"]


def test_learn_merges_punctuation_weighted():
    db, proj, char = _setup()
    db.create_voice_profile(
        char.id,
        punctuation_style={"exclamations": 0.8},
    )

    segs = [
        _seg("Sure thing.", char.id),
        _seg("Okay then.", char.id),
        _seg("Fine by me.", char.id),
    ]
    learn_voice_profile(db, char.id, segs)

    profile = db.get_voice_profile_data(char.id)
    excl = profile["punctuation_style"]["exclamations"]
    expected = round(0.8 * _EXISTING_WEIGHT + 0.0 * _LEARNED_WEIGHT, 3)
    assert excl == expected


def test_learn_merges_dialogue_markers():
    db, proj, char = _setup()
    db.create_voice_profile(char.id, dialogue_markers=["Indeed"])

    segs = [
        _seg("Well, I think so.", char.id),
        _seg("Well, obviously.", char.id),
        _seg("Well, if you insist.", char.id),
    ]
    learn_voice_profile(db, char.id, segs)

    profile = db.get_voice_profile_data(char.id)
    assert "Indeed" in profile["dialogue_markers"]
    assert "Well" in profile["dialogue_markers"]


# -- learn_voice_profile: user_locked -----------------------------------------

def test_locked_tone_not_overwritten():
    db, proj, char = _setup()
    db.create_voice_profile(char.id, tone="polite")

    segs = [
        _seg("I'm gonna go. You're not coming?", char.id),
        _seg("Can't believe it. Won't do it.", char.id),
        _seg("Don't care. I'm out.", char.id),
        _seg("Ain't that fun? Let's go.", char.id),
    ]
    learn_voice_profile(db, char.id, segs, user_locked=("tone",))

    profile = db.get_voice_profile_data(char.id)
    assert profile["tone"] == "polite"


def test_locked_vocabulary_not_overwritten():
    db, proj, char = _setup()
    db.create_voice_profile(char.id, vocabulary_level="elevated")

    segs = [
        _seg("Yeah dude, totally cool.", char.id),
        _seg("Nah, gonna pass.", char.id),
        _seg("Hey yo, lemme go.", char.id),
        _seg("Nope, ain't happening, dunno why.", char.id),
    ]
    learn_voice_profile(db, char.id, segs, user_locked=("vocabulary_level",))

    profile = db.get_voice_profile_data(char.id)
    assert profile["vocabulary_level"] == "elevated"


def test_locked_quirks_not_overwritten():
    db, proj, char = _setup()
    db.create_voice_profile(char.id, quirks=["original quirk"])

    segs = [
        _seg("Well... maybe...", char.id),
        _seg("I suppose... perhaps...", char.id),
        _seg("Could be... not sure...", char.id),
        _seg("Hmm... let me think...", char.id),
    ]
    learn_voice_profile(db, char.id, segs, user_locked=("quirks",))

    profile = db.get_voice_profile_data(char.id)
    assert profile["quirks"] == ["original quirk"]


def test_locked_punctuation_not_overwritten():
    db, proj, char = _setup()
    db.create_voice_profile(
        char.id,
        punctuation_style={"exclamations": 1.0},
    )

    segs = [
        _seg("Sure thing.", char.id),
        _seg("Okay then.", char.id),
        _seg("Fine.", char.id),
    ]
    learn_voice_profile(
        db, char.id, segs, user_locked=("punctuation_style",),
    )

    profile = db.get_voice_profile_data(char.id)
    assert profile["punctuation_style"]["exclamations"] == 1.0


# -- profiles evolve with more text -------------------------------------------

def test_profile_evolves_over_multiple_rounds():
    db, proj, char = _setup()

    round_1 = [
        _seg("I think we should consider our options.", char.id),
        _seg("Perhaps that would be wise.", char.id),
        _seg("Let me think about it.", char.id),
    ]
    learn_voice_profile(db, char.id, round_1)

    profile_r1 = db.get_voice_profile_data(char.id)
    assert profile_r1 is not None
    tone_r1 = profile_r1["tone"]

    round_2 = [
        _seg("I'm gonna bail. Don't wait up.", char.id),
        _seg("Can't deal with this. I'm out.", char.id),
        _seg("Ain't nobody got time. Let's bounce.", char.id),
        _seg("Won't bother. Don't care.", char.id),
    ]
    learn_voice_profile(db, char.id, round_2)

    profile_r2 = db.get_voice_profile_data(char.id)
    assert profile_r2["tone"] == "casual"


def test_profile_accumulates_quirks():
    db, proj, char = _setup()

    round_1 = [
        _seg("Watch out!", char.id),
        _seg("Run!", char.id),
        _seg("Go! Go! Go!", char.id),
        _seg("Yes!", char.id),
    ]
    learn_voice_profile(db, char.id, round_1)

    profile_r1 = db.get_voice_profile_data(char.id)
    assert "exclamatory speaker" in profile_r1["quirks"]

    round_2 = [
        _seg("Well... maybe not...", char.id),
        _seg("I suppose... perhaps...", char.id),
        _seg("Could be... not sure...", char.id),
        _seg("Hmm... let me think...", char.id),
    ]
    learn_voice_profile(db, char.id, round_2)

    profile_r2 = db.get_voice_profile_data(char.id)
    assert "exclamatory speaker" in profile_r2["quirks"]
    assert "trails off frequently" in profile_r2["quirks"]


def test_profile_punctuation_evolves_weighted():
    db, proj, char = _setup()

    round_1 = [
        _seg("Wow!", char.id),
        _seg("Incredible!", char.id),
        _seg("Amazing!", char.id),
    ]
    learn_voice_profile(db, char.id, round_1)

    profile_r1 = db.get_voice_profile_data(char.id)
    excl_r1 = profile_r1["punctuation_style"]["exclamations"]
    assert excl_r1 == 1.0

    round_2 = [
        _seg("Okay.", char.id),
        _seg("Sure.", char.id),
        _seg("Fine.", char.id),
    ]
    learn_voice_profile(db, char.id, round_2)

    profile_r2 = db.get_voice_profile_data(char.id)
    excl_r2 = profile_r2["punctuation_style"]["exclamations"]
    assert excl_r2 < excl_r1
    assert excl_r2 == round(1.0 * _EXISTING_WEIGHT + 0.0 * _LEARNED_WEIGHT, 3)


def test_profile_markers_accumulate():
    db, proj, char = _setup()

    round_1 = [
        _seg("Look, we need to talk.", char.id),
        _seg("Look, this is important.", char.id),
        _seg("Look, just listen.", char.id),
    ]
    learn_voice_profile(db, char.id, round_1)

    profile_r1 = db.get_voice_profile_data(char.id)
    assert "Look" in profile_r1["dialogue_markers"]

    round_2 = [
        _seg("Well, I suppose.", char.id),
        _seg("Well, if you say so.", char.id),
        _seg("Well, that works.", char.id),
    ]
    learn_voice_profile(db, char.id, round_2)

    profile_r2 = db.get_voice_profile_data(char.id)
    assert "Look" in profile_r2["dialogue_markers"]
    assert "Well" in profile_r2["dialogue_markers"]


# -- edge cases ---------------------------------------------------------------

def test_learn_no_segments_no_change():
    db, proj, char = _setup()
    db.create_voice_profile(char.id, tone="formal")

    analysis = learn_voice_profile(db, char.id, [])
    assert analysis.confidence == 0.0

    profile = db.get_voice_profile_data(char.id)
    assert profile["tone"] == "formal"


def test_learn_no_matching_speaker():
    db, proj, char = _setup()
    db.create_voice_profile(char.id, tone="formal")

    segs = [_seg("Hello there.", 999)]
    analysis = learn_voice_profile(db, char.id, segs)
    assert analysis.confidence == 0.0

    profile = db.get_voice_profile_data(char.id)
    assert profile["tone"] == "formal"


def test_multiple_locked_fields():
    db, proj, char = _setup()
    db.create_voice_profile(
        char.id,
        tone="polite",
        sentence_length="long",
        vocabulary_level="elevated",
    )

    segs = [
        _seg("Yeah gonna go. Can't wait.", char.id),
        _seg("Nah don't care. I'm out.", char.id),
        _seg("Yo let's bounce. Ain't staying.", char.id),
    ]
    learn_voice_profile(
        db, char.id, segs,
        user_locked=("tone", "sentence_length", "vocabulary_level"),
    )

    profile = db.get_voice_profile_data(char.id)
    assert profile["tone"] == "polite"
    assert profile["sentence_length"] == "long"
    assert profile["vocabulary_level"] == "elevated"
