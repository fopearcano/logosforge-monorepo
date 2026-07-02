"""Tests for unified grammar + voice + style underline stacking.

Priority order: grammar (errors) > voice (character) > style (quality).
No overlapping/duplicate highlights — higher-priority layers suppress
lower ones on the same span.
"""

from PySide6.QtGui import QTextCharFormat

from logosforge.db import Database
from logosforge.dialogue_attribution import DialogueSegment
from logosforge.grammar_checker import Issue as GrammarIssue
from logosforge.style_analysis import StyleHint
from logosforge.voice_consistency import VoiceDeviation
from logosforge.ui.writing_core_view import WritingCoreView
from logosforge.ui import theme


# -- Helpers -------------------------------------------------------------------

def _setup(text="aa bb cc dd ee ff gg hh ii jj kk ll mm nn oo pp"):
    db = Database()
    proj = db.create_project("UnifiedTest")
    s1 = db.create_scene(proj.id, "Scene", content=text)
    return db, proj, s1


def _dev(start, end, text, reasons=None):
    seg = DialogueSegment(text=text, start_pos=start, end_pos=end, speaker_id=1)
    return VoiceDeviation(
        segment=seg, deviation_score=0.6,
        reasons=reasons or ["voice mismatch"],
    )


def _grammar(start, end, msg="Spelling error", issue_type="spelling"):
    return GrammarIssue(
        start=start, end=end, issue_type=issue_type,
        message=msg, suggestions=["fix"],
    )


def _style(start, end, msg="Style issue"):
    return StyleHint(start=start, end=end, hint_type="clarity", message=msg)


def _get_editor(db, proj):
    view = WritingCoreView(db, proj.id)
    return view, list(view._editors.values())[0]


def _tips(editor):
    sels = editor.extraSelections()
    return [s.format.toolTip() for s in sels]


def _underline_styles(editor):
    sels = editor.extraSelections()
    return [s.format.underlineStyle() for s in sels]


# -- All three layers, non-overlapping -----------------------------------------

def test_all_three_non_overlapping():
    db, proj, s1 = _setup()
    view, editor = _get_editor(db, proj)
    editor.setPlainText("aa bb cc dd ee ff gg hh ii jj kk ll mm nn oo pp")

    editor._grammar_issues = [_grammar(0, 2, "g1")]
    editor._style_hints = [_style(6, 8, "s1")]
    editor._style_hints_enabled = True
    editor._voice_deviations = [_dev(3, 5, "bb", ["v1"])]
    editor._voice_hints_enabled = True

    editor.apply_grammar_underlines()
    tips = _tips(editor)

    assert len(tips) == 3
    assert any("g1" in t for t in tips)
    assert any("v1" in t for t in tips)
    assert any("s1" in t for t in tips)


def test_all_three_non_overlapping_underline_styles():
    db, proj, s1 = _setup()
    view, editor = _get_editor(db, proj)
    editor.setPlainText("aa bb cc dd ee ff gg hh ii jj kk ll mm nn oo pp")

    editor._grammar_issues = [_grammar(0, 2, "g1")]
    editor._voice_deviations = [_dev(3, 5, "bb", ["v1"])]
    editor._voice_hints_enabled = True
    editor._style_hints = [_style(6, 8, "s1")]
    editor._style_hints_enabled = True

    editor.apply_grammar_underlines()
    sels = editor.extraSelections()
    styles = {s.format.toolTip(): s.format.underlineStyle() for s in sels}

    assert styles["g1  →  fix"] == QTextCharFormat.UnderlineStyle.WaveUnderline
    assert styles["v1"] == QTextCharFormat.UnderlineStyle.DashUnderline
    assert styles["s1"] == QTextCharFormat.UnderlineStyle.DotLine


# -- Priority: grammar > voice -------------------------------------------------

def test_grammar_suppresses_voice_same_span():
    db, proj, s1 = _setup()
    view, editor = _get_editor(db, proj)
    editor.setPlainText("quikc brown fox jumps")

    editor._grammar_issues = [_grammar(0, 5, "g1")]
    editor._voice_deviations = [_dev(0, 5, "quikc", ["v1"])]
    editor._voice_hints_enabled = True

    editor.apply_grammar_underlines()
    tips = _tips(editor)
    assert len(tips) == 1
    assert "g1" in tips[0]
    assert "v1" not in tips


def test_grammar_suppresses_voice_partial_overlap():
    db, proj, s1 = _setup()
    view, editor = _get_editor(db, proj)
    editor.setPlainText("quikc brown fox jumps quickly")

    editor._grammar_issues = [_grammar(3, 8, "g1")]
    editor._voice_deviations = [_dev(5, 15, "brown fox", ["v1"])]
    editor._voice_hints_enabled = True

    editor.apply_grammar_underlines()
    tips = _tips(editor)
    assert len(tips) == 1
    assert "g1" in tips[0]


def test_grammar_suppresses_voice_enclosing():
    db, proj, s1 = _setup()
    view, editor = _get_editor(db, proj)
    editor.setPlainText("abcdefghijklmnop")

    editor._grammar_issues = [_grammar(2, 12, "g1")]
    editor._voice_deviations = [_dev(4, 8, "efgh", ["v1"])]
    editor._voice_hints_enabled = True

    editor.apply_grammar_underlines()
    tips = _tips(editor)
    assert len(tips) == 1
    assert "g1" in tips[0]


# -- Priority: voice > style --------------------------------------------------

def test_voice_suppresses_style_same_span():
    db, proj, s1 = _setup()
    view, editor = _get_editor(db, proj)
    editor.setPlainText("She said hello to the world.")

    editor._voice_deviations = [_dev(0, 10, "She said h", ["v1"])]
    editor._voice_hints_enabled = True
    editor._style_hints = [_style(0, 10, "s1")]
    editor._style_hints_enabled = True

    editor.apply_grammar_underlines()
    tips = _tips(editor)
    assert "v1" in tips
    assert "s1" not in tips


def test_voice_suppresses_style_partial_overlap():
    db, proj, s1 = _setup()
    view, editor = _get_editor(db, proj)
    editor.setPlainText("She said hello to the world.")

    editor._voice_deviations = [_dev(3, 12, "said hello", ["v1"])]
    editor._voice_hints_enabled = True
    editor._style_hints = [_style(5, 8, "s1")]
    editor._style_hints_enabled = True

    editor.apply_grammar_underlines()
    tips = _tips(editor)
    assert "v1" in tips
    assert "s1" not in tips


def test_voice_suppresses_style_enclosing():
    db, proj, s1 = _setup()
    view, editor = _get_editor(db, proj)
    editor.setPlainText("She said hello to the world.")

    editor._voice_deviations = [_dev(0, 20, "She said hello to th", ["v1"])]
    editor._voice_hints_enabled = True
    editor._style_hints = [_style(5, 10, "s1")]
    editor._style_hints_enabled = True

    editor.apply_grammar_underlines()
    tips = _tips(editor)
    assert "v1" in tips
    assert "s1" not in tips


# -- Priority: grammar > style (unchanged) ------------------------------------

def test_grammar_suppresses_style():
    db, proj, s1 = _setup()
    view, editor = _get_editor(db, proj)
    editor.setPlainText("quikc brown fox jumps")

    editor._grammar_issues = [_grammar(0, 5, "g1")]
    editor._style_hints = [_style(0, 5, "s1")]
    editor._style_hints_enabled = True

    editor.apply_grammar_underlines()
    tips = _tips(editor)
    assert "g1" in tips[0]
    assert "s1" not in tips


# -- All three overlapping on same span ----------------------------------------

def test_all_three_same_span_grammar_wins():
    db, proj, s1 = _setup()
    view, editor = _get_editor(db, proj)
    editor.setPlainText("quikc brown fox jumps quickly")

    editor._grammar_issues = [_grammar(0, 5, "g1")]
    editor._voice_deviations = [_dev(0, 5, "quikc", ["v1"])]
    editor._voice_hints_enabled = True
    editor._style_hints = [_style(0, 5, "s1")]
    editor._style_hints_enabled = True

    editor.apply_grammar_underlines()
    tips = _tips(editor)
    assert len(tips) == 1
    assert "g1" in tips[0]


# -- Mixed overlapping and non-overlapping -------------------------------------

def test_grammar_voice_overlap_style_separate():
    db, proj, s1 = _setup()
    view, editor = _get_editor(db, proj)
    editor.setPlainText("aa bb cc dd ee ff gg hh ii jj kk ll mm nn oo pp")

    editor._grammar_issues = [_grammar(0, 2, "g1")]
    editor._voice_deviations = [_dev(0, 2, "aa", ["v1"])]
    editor._voice_hints_enabled = True
    editor._style_hints = [_style(6, 8, "s1")]
    editor._style_hints_enabled = True

    editor.apply_grammar_underlines()
    tips = _tips(editor)
    assert len(tips) == 2
    assert any("g1" in t for t in tips)
    assert any("s1" in t for t in tips)
    assert not any("v1" in t for t in tips)


def test_voice_style_overlap_grammar_separate():
    db, proj, s1 = _setup()
    view, editor = _get_editor(db, proj)
    editor.setPlainText("aa bb cc dd ee ff gg hh ii jj kk ll mm nn oo pp")

    editor._grammar_issues = [_grammar(0, 2, "g1")]
    editor._voice_deviations = [_dev(6, 8, "cc", ["v1"])]
    editor._voice_hints_enabled = True
    editor._style_hints = [_style(6, 8, "s1")]
    editor._style_hints_enabled = True

    editor.apply_grammar_underlines()
    tips = _tips(editor)
    assert len(tips) == 2
    assert any("g1" in t for t in tips)
    assert any("v1" in t for t in tips)
    assert not any("s1" in t for t in tips)


# -- Disabled layers don't render ----------------------------------------------

def test_voice_disabled_style_renders():
    db, proj, s1 = _setup()
    view, editor = _get_editor(db, proj)
    editor.setPlainText("She said hello to the world.")

    editor._voice_deviations = [_dev(0, 10, "She said h", ["v1"])]
    editor._voice_hints_enabled = False
    editor._style_hints = [_style(0, 10, "s1")]
    editor._style_hints_enabled = True

    editor.apply_grammar_underlines()
    tips = _tips(editor)
    assert "s1" in tips
    assert "v1" not in tips


def test_style_disabled_voice_renders():
    db, proj, s1 = _setup()
    view, editor = _get_editor(db, proj)
    editor.setPlainText("She said hello to the world.")

    editor._voice_deviations = [_dev(0, 10, "She said h", ["v1"])]
    editor._voice_hints_enabled = True
    editor._style_hints = [_style(0, 10, "s1")]
    editor._style_hints_enabled = False

    editor.apply_grammar_underlines()
    tips = _tips(editor)
    assert "v1" in tips
    assert "s1" not in tips


def test_both_disabled_only_grammar():
    db, proj, s1 = _setup()
    view, editor = _get_editor(db, proj)
    editor.setPlainText("quikc brown fox jumps quickly")

    editor._grammar_issues = [_grammar(0, 5, "g1")]
    editor._voice_deviations = [_dev(6, 11, "brown", ["v1"])]
    editor._voice_hints_enabled = False
    editor._style_hints = [_style(12, 15, "s1")]
    editor._style_hints_enabled = False

    editor.apply_grammar_underlines()
    tips = _tips(editor)
    assert len(tips) == 1
    assert "g1" in tips[0]


# -- Multiple items per layer -------------------------------------------------

def test_multiple_grammar_multiple_voice_multiple_style():
    db, proj, s1 = _setup()
    view, editor = _get_editor(db, proj)
    editor.setPlainText("aa bb cc dd ee ff gg hh ii jj kk ll mm nn oo pp")

    editor._grammar_issues = [
        _grammar(0, 2, "g1"),
        _grammar(3, 5, "g2"),
    ]
    editor._voice_deviations = [
        _dev(6, 8, "cc", ["v1"]),
        _dev(9, 11, "dd", ["v2"]),
    ]
    editor._voice_hints_enabled = True
    editor._style_hints = [
        _style(12, 14, "s1"),
        _style(15, 17, "s2"),
    ]
    editor._style_hints_enabled = True

    editor.apply_grammar_underlines()
    tips = _tips(editor)
    assert len(tips) == 6
    for label in ("g1", "g2", "v1", "v2", "s1", "s2"):
        assert any(label in t for t in tips)


# -- Underline style consistency -----------------------------------------------

def test_grammar_always_wave():
    db, proj, s1 = _setup()
    view, editor = _get_editor(db, proj)
    editor.setPlainText("quikc brown fox jumps")

    editor._grammar_issues = [
        _grammar(0, 5, "spell", "spelling"),
        _grammar(6, 11, "gram", "grammar"),
    ]
    editor.apply_grammar_underlines()
    styles = _underline_styles(editor)
    assert all(s == QTextCharFormat.UnderlineStyle.WaveUnderline for s in styles)


def test_voice_always_dash():
    db, proj, s1 = _setup()
    view, editor = _get_editor(db, proj)
    editor.setPlainText("aa bb cc dd ee ff gg hh")

    editor._voice_deviations = [
        _dev(0, 2, "aa", ["v1"]),
        _dev(3, 5, "bb", ["v2"]),
    ]
    editor._voice_hints_enabled = True
    editor.apply_grammar_underlines()
    styles = _underline_styles(editor)
    assert all(s == QTextCharFormat.UnderlineStyle.DashUnderline for s in styles)


def test_style_always_dot():
    db, proj, s1 = _setup()
    view, editor = _get_editor(db, proj)
    editor.setPlainText("aa bb cc dd ee ff gg hh")

    editor._style_hints = [
        _style(0, 2, "s1"),
        _style(3, 5, "s2"),
    ]
    editor._style_hints_enabled = True
    editor.apply_grammar_underlines()
    styles = _underline_styles(editor)
    assert all(s == QTextCharFormat.UnderlineStyle.DotLine for s in styles)


# -- No duplicates within a layer ---------------------------------------------

def test_no_duplicate_grammar():
    db, proj, s1 = _setup()
    view, editor = _get_editor(db, proj)
    editor.setPlainText("quikc brown fox")

    editor._grammar_issues = [_grammar(0, 5, "g1")]
    editor.apply_grammar_underlines()
    tips = _tips(editor)
    assert tips.count("g1  →  fix") == 1


# -- Empty layers produce no selections ---------------------------------------

def test_all_empty():
    db, proj, s1 = _setup()
    view, editor = _get_editor(db, proj)
    editor.setPlainText("Hello world.")

    editor._grammar_issues = []
    editor._voice_deviations = []
    editor._voice_hints_enabled = True
    editor._style_hints = []
    editor._style_hints_enabled = True

    editor.apply_grammar_underlines()
    assert len(editor.extraSelections()) == 0
