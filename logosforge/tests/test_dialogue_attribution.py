"""Tests for dialogue speaker attribution."""

from types import SimpleNamespace

from logosforge.dialogue_attribution import DialogueSegment, attribute_dialogue


def _chars(*names_and_ids):
    """Build lightweight character stubs: _chars(("Alice", 1), ("Bob", 2))."""
    return [SimpleNamespace(id=cid, name=name) for name, cid in names_and_ids]


# -- Quote detection -----------------------------------------------------------

def test_detects_straight_quotes():
    chars = _chars(("Alice", 1))
    text = 'Alice said, "Hello there."'
    segs = attribute_dialogue(text, chars)
    assert len(segs) == 1
    assert segs[0].text == "Hello there."


def test_detects_curly_quotes():
    chars = _chars(("Alice", 1))
    text = "Alice said, “Hello there.”"
    segs = attribute_dialogue(text, chars)
    assert len(segs) == 1
    assert segs[0].text == "Hello there."


def test_detects_single_curly_quotes():
    chars = _chars(("Alice", 1))
    text = "Alice said, ‘Hello there.’"
    segs = attribute_dialogue(text, chars)
    assert len(segs) == 1
    assert segs[0].text == "Hello there."


def test_positions_are_correct():
    chars = _chars(("Alice", 1))
    text = 'Alice said, "Hello."'
    segs = attribute_dialogue(text, chars)
    assert text[segs[0].start_pos : segs[0].end_pos] == '"Hello."'


# -- Speech tag attribution ----------------------------------------------------

def test_name_verb_before_quote():
    chars = _chars(("John", 1))
    text = 'John said, "I agree."'
    segs = attribute_dialogue(text, chars)
    assert segs[0].speaker_id == 1


def test_name_verb_after_quote():
    chars = _chars(("Mary", 2))
    text = '"Stop right there," Mary warned.'
    segs = attribute_dialogue(text, chars)
    assert segs[0].speaker_id == 2


def test_verb_name_order():
    chars = _chars(("Tom", 3))
    text = '"Run!" shouted Tom.'
    segs = attribute_dialogue(text, chars)
    assert segs[0].speaker_id == 3


def test_case_insensitive_verb_match():
    chars = _chars(("Alice", 1))
    text = 'Alice Asked, "Why?"'
    segs = attribute_dialogue(text, chars)
    assert segs[0].speaker_id == 1


# -- Proximity attribution ----------------------------------------------------

def test_name_on_same_line_no_verb():
    chars = _chars(("Clara", 4))
    text = 'Clara turned to face him. "We need to talk."'
    segs = attribute_dialogue(text, chars)
    assert segs[0].speaker_id == 4


def test_first_name_match():
    chars = _chars(("John Smith", 5))
    text = 'John smiled. "Good morning."'
    segs = attribute_dialogue(text, chars)
    assert segs[0].speaker_id == 5


# -- Continuity (turn-taking) -------------------------------------------------

def test_alternating_speakers():
    chars = _chars(("Alice", 1), ("Bob", 2))
    text = (
        'Alice said, "Hello."\n'
        'Bob replied, "Hi."\n'
        '"How are you?"'
    )
    segs = attribute_dialogue(text, chars)
    assert len(segs) == 3
    assert segs[0].speaker_id == 1
    assert segs[1].speaker_id == 2
    assert segs[2].speaker_id == 1  # alternation: back to Alice


def test_continuity_requires_two_known_speakers():
    chars = _chars(("Alice", 1))
    text = (
        'Alice said, "Hello."\n'
        '"Who are you?"'
    )
    segs = attribute_dialogue(text, chars)
    assert segs[0].speaker_id == 1
    assert segs[1].speaker_id is None  # only one prior speaker, can't alternate


# -- Multi-speaker paragraph --------------------------------------------------

def test_multi_speaker_paragraph():
    chars = _chars(("Alice", 1), ("Bob", 2), ("Clara", 3))
    text = (
        '"We should go," Alice whispered. '
        '"Not yet," Bob replied. '
        '"I agree with Bob," Clara added.'
    )
    segs = attribute_dialogue(text, chars)
    assert len(segs) == 3
    assert segs[0].speaker_id == 1
    assert segs[1].speaker_id == 2
    assert segs[2].speaker_id == 3


def test_multi_speaker_with_continuity():
    chars = _chars(("Alice", 1), ("Bob", 2))
    text = (
        'Alice said, "Let\'s go."\n'
        'Bob said, "Where?"\n'
        '"To the park."\n'
        '"Sounds good."'
    )
    segs = attribute_dialogue(text, chars)
    assert len(segs) == 4
    assert segs[0].speaker_id == 1
    assert segs[1].speaker_id == 2
    assert segs[2].speaker_id == 1  # alternation
    assert segs[3].speaker_id == 2  # alternation


# -- Missing tags handled (fallback to None) -----------------------------------

def test_no_tag_no_context_returns_none():
    chars = _chars(("Alice", 1), ("Bob", 2))
    text = '"What a strange day."'
    segs = attribute_dialogue(text, chars)
    assert len(segs) == 1
    assert segs[0].speaker_id is None


def test_unknown_name_returns_none():
    chars = _chars(("Alice", 1))
    text = 'Dave said, "Hello."'
    segs = attribute_dialogue(text, chars)
    assert segs[0].speaker_id is None


def test_no_characters_returns_empty():
    segs = attribute_dialogue('"Hello."', [])
    assert segs == []


def test_empty_text_returns_empty():
    chars = _chars(("Alice", 1))
    assert attribute_dialogue("", chars) == []


def test_no_dialogue_returns_empty():
    chars = _chars(("Alice", 1))
    text = "Alice walked down the street in silence."
    assert attribute_dialogue(text, chars) == []


# -- Mixed attribution --------------------------------------------------------

def test_mixed_tagged_and_untagged():
    chars = _chars(("Alice", 1), ("Bob", 2))
    text = (
        'Alice said, "First line."\n'
        '"Second line."\n'
        'Bob muttered, "Third line."'
    )
    segs = attribute_dialogue(text, chars)
    assert segs[0].speaker_id == 1
    assert segs[1].speaker_id is None  # only one known prev speaker
    assert segs[2].speaker_id == 2


def test_tagged_after_untagged_resets_continuity():
    chars = _chars(("Alice", 1), ("Bob", 2))
    text = (
        'Alice said, "One."\n'
        'Bob said, "Two."\n'
        '"Three."\n'
        '"Four."\n'
        '"Five."'
    )
    segs = attribute_dialogue(text, chars)
    assert segs[0].speaker_id == 1
    assert segs[1].speaker_id == 2
    assert segs[2].speaker_id == 1  # alternation from Bob
    assert segs[3].speaker_id == 2  # alternation from Alice (via continuity)
    assert segs[4].speaker_id == 1  # alternation continues


# -- Edge cases ----------------------------------------------------------------

def test_dialogue_segment_fields():
    seg = DialogueSegment(text="hi", start_pos=0, end_pos=4, speaker_id=None)
    assert seg.text == "hi"
    assert seg.start_pos == 0
    assert seg.end_pos == 4
    assert seg.speaker_id is None


def test_multiple_quotes_single_line():
    chars = _chars(("Alice", 1), ("Bob", 2))
    text = '"Hello," Alice said. "How are you?" Bob asked.'
    segs = attribute_dialogue(text, chars)
    assert len(segs) == 2
    assert segs[0].speaker_id == 1
    assert segs[1].speaker_id == 2


def test_name_inside_quote_not_matched_as_speaker():
    chars = _chars(("Alice", 1), ("Bob", 2))
    text = '"Tell Alice I said hello," Bob whispered.'
    segs = attribute_dialogue(text, chars)
    assert segs[0].speaker_id == 2  # Bob, not Alice
