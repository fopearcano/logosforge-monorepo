"""Tests for inline voice consistency hints — rendering, overlap, toggle."""

from PySide6.QtGui import QTextCharFormat

from logosforge.db import Database
from logosforge.dialogue_attribution import DialogueSegment
from logosforge.grammar_checker import Issue as GrammarIssue
from logosforge.style_analysis import StyleHint
from logosforge.voice_consistency import VoiceDeviation
from logosforge.ui.writing_core_view import WritingCoreView


def _setup():
    db = Database()
    proj = db.create_project("VoiceHintTest")
    s1 = db.create_scene(proj.id, "Scene", content="Hello world.")
    return db, proj, s1


def _make_deviation(start, end, text, reasons=None):
    seg = DialogueSegment(
        text=text, start_pos=start, end_pos=end, speaker_id=1,
    )
    return VoiceDeviation(
        segment=seg,
        deviation_score=0.6,
        reasons=reasons or ["too formal for this character"],
    )


# -- Hints appear only when needed -------------------------------------------

def test_voice_hint_shown_when_enabled():
    db, proj, s1 = _setup()
    view = WritingCoreView(db, proj.id)
    editor = list(view._editors.values())[0]
    editor.setPlainText("She said hello to the world.")

    editor._voice_deviations = [_make_deviation(0, 10, "She said h")]
    editor._voice_hints_enabled = True
    editor.apply_grammar_underlines()
    sels = editor.extraSelections()
    assert len(sels) == 1
    assert "too formal" in sels[0].format.toolTip()


def test_voice_hint_hidden_when_disabled():
    db, proj, s1 = _setup()
    view = WritingCoreView(db, proj.id)
    editor = list(view._editors.values())[0]
    editor.setPlainText("She said hello to the world.")

    editor._voice_deviations = [_make_deviation(0, 10, "She said h")]
    editor._voice_hints_enabled = False
    editor.apply_grammar_underlines()
    sels = editor.extraSelections()
    assert len(sels) == 0


def test_voice_hint_uses_dash_underline():
    db, proj, s1 = _setup()
    view = WritingCoreView(db, proj.id)
    editor = list(view._editors.values())[0]
    editor.setPlainText("She said hello to the world.")

    editor._voice_deviations = [_make_deviation(0, 10, "She said h")]
    editor._voice_hints_enabled = True
    editor.apply_grammar_underlines()
    sels = editor.extraSelections()
    assert len(sels) == 1
    assert sels[0].format.underlineStyle() == QTextCharFormat.UnderlineStyle.DashUnderline


def test_voice_hint_tooltip_shows_reason():
    db, proj, s1 = _setup()
    view = WritingCoreView(db, proj.id)
    editor = list(view._editors.values())[0]
    editor.setPlainText("She said hello to the world.")

    editor._voice_deviations = [
        _make_deviation(0, 10, "She said h",
                        reasons=["sentence length unusually long"]),
    ]
    editor._voice_hints_enabled = True
    editor.apply_grammar_underlines()
    sels = editor.extraSelections()
    assert "sentence length unusually long" in sels[0].format.toolTip()


def test_voice_hint_tooltip_multiple_reasons():
    db, proj, s1 = _setup()
    view = WritingCoreView(db, proj.id)
    editor = list(view._editors.values())[0]
    editor.setPlainText("She said hello to the world.")

    editor._voice_deviations = [
        _make_deviation(0, 10, "She said h",
                        reasons=["too formal for this character",
                                 "sentence length unusually long"]),
    ]
    editor._voice_hints_enabled = True
    editor.apply_grammar_underlines()
    sels = editor.extraSelections()
    tip = sels[0].format.toolTip()
    assert "too formal" in tip
    assert "sentence length" in tip


def test_no_deviations_no_hints():
    db, proj, s1 = _setup()
    view = WritingCoreView(db, proj.id)
    editor = list(view._editors.values())[0]
    editor.setPlainText("She said hello to the world.")

    editor._voice_deviations = []
    editor._voice_hints_enabled = True
    editor.apply_grammar_underlines()
    assert len(editor.extraSelections()) == 0


def test_multiple_voice_hints():
    db, proj, s1 = _setup()
    view = WritingCoreView(db, proj.id)
    editor = list(view._editors.values())[0]
    editor.setPlainText("She said hello to the world today.")

    editor._voice_deviations = [
        _make_deviation(0, 10, "She said h"),
        _make_deviation(20, 30, "world toda"),
    ]
    editor._voice_hints_enabled = True
    editor.apply_grammar_underlines()
    sels = editor.extraSelections()
    assert len(sels) == 2


# -- No overlap issues with grammar/style highlights -------------------------

def test_grammar_suppresses_overlapping_voice_hint():
    db, proj, s1 = _setup()
    view = WritingCoreView(db, proj.id)
    editor = list(view._editors.values())[0]
    editor.setPlainText("quikc brown fox jumps quickly")

    editor._grammar_issues = [
        GrammarIssue(start=0, end=5, issue_type="spelling",
                     message="Unknown word", suggestions=["quick"]),
    ]
    editor._voice_deviations = [_make_deviation(0, 5, "quikc")]
    editor._voice_hints_enabled = True
    editor.apply_grammar_underlines()
    sels = editor.extraSelections()
    assert len(sels) == 1
    assert "Unknown word" in sels[0].format.toolTip()


def test_voice_suppresses_overlapping_style_hint():
    db, proj, s1 = _setup()
    view = WritingCoreView(db, proj.id)
    editor = list(view._editors.values())[0]
    editor.setPlainText("She said hello to the world.")

    editor._style_hints = [
        StyleHint(start=0, end=10, hint_type="clarity", message="Style hint"),
    ]
    editor._style_hints_enabled = True
    editor._voice_deviations = [_make_deviation(0, 10, "She said h")]
    editor._voice_hints_enabled = True
    editor.apply_grammar_underlines()
    sels = editor.extraSelections()
    tips = [s.format.toolTip() for s in sels]
    assert any("too formal" in t for t in tips)
    assert not any("Style hint" in t for t in tips)


def test_voice_hint_shown_when_no_overlap():
    db, proj, s1 = _setup()
    view = WritingCoreView(db, proj.id)
    editor = list(view._editors.values())[0]
    editor.setPlainText("quikc brown fox jumps quickly more")

    editor._grammar_issues = [
        GrammarIssue(start=0, end=5, issue_type="spelling",
                     message="Spelling", suggestions=["quick"]),
    ]
    editor._style_hints = [
        StyleHint(start=6, end=11, hint_type="clarity",
                  message="Style issue"),
    ]
    editor._style_hints_enabled = True
    editor._voice_deviations = [_make_deviation(20, 27, "quickly")]
    editor._voice_hints_enabled = True
    editor.apply_grammar_underlines()
    sels = editor.extraSelections()
    tips = [s.format.toolTip() for s in sels]
    assert len(sels) == 3
    assert any("Spelling" in t for t in tips)
    assert any("Style issue" in t for t in tips)
    assert any("too formal" in t for t in tips)


def test_grammar_and_style_and_voice_all_different_spans():
    db, proj, s1 = _setup()
    view = WritingCoreView(db, proj.id)
    editor = list(view._editors.values())[0]
    editor.setPlainText("aa bb cc dd ee ff gg hh ii jj kk ll")

    editor._grammar_issues = [
        GrammarIssue(start=0, end=2, issue_type="spelling", message="g1"),
    ]
    editor._style_hints = [
        StyleHint(start=3, end=5, hint_type="clarity", message="s1"),
    ]
    editor._style_hints_enabled = True
    editor._voice_deviations = [_make_deviation(6, 8, "cc")]
    editor._voice_hints_enabled = True
    editor.apply_grammar_underlines()
    sels = editor.extraSelections()
    tips = [s.format.toolTip() for s in sels]
    assert len(sels) == 3
    assert "g1" in tips
    assert "s1" in tips
    assert any("too formal" in t for t in tips)


def test_voice_hint_partial_overlap_with_grammar():
    db, proj, s1 = _setup()
    view = WritingCoreView(db, proj.id)
    editor = list(view._editors.values())[0]
    editor.setPlainText("quikc brown fox jumps quickly")

    editor._grammar_issues = [
        GrammarIssue(start=3, end=8, issue_type="grammar", message="g1"),
    ]
    editor._voice_deviations = [_make_deviation(5, 15, "brown fox")]
    editor._voice_hints_enabled = True
    editor.apply_grammar_underlines()
    sels = editor.extraSelections()
    assert len(sels) == 1
    assert "g1" in sels[0].format.toolTip()


def test_voice_hint_enclosing_style_suppresses_style():
    db, proj, s1 = _setup()
    view = WritingCoreView(db, proj.id)
    editor = list(view._editors.values())[0]
    editor.setPlainText("She said hello to the world.")

    editor._style_hints = [
        StyleHint(start=5, end=8, hint_type="rhythm", message="s1"),
    ]
    editor._style_hints_enabled = True
    editor._voice_deviations = [_make_deviation(3, 12, "said hello")]
    editor._voice_hints_enabled = True
    editor.apply_grammar_underlines()
    sels = editor.extraSelections()
    tips = [s.format.toolTip() for s in sels]
    assert any("too formal" in t for t in tips)
    assert "s1" not in tips


# -- Toggle persistence ------------------------------------------------------

def test_voice_toggle_persists():
    db, proj, s1 = _setup()
    view = WritingCoreView(db, proj.id)
    assert view._voice_hints_checking is False

    view._toggle_voice_hints()
    assert view._voice_hints_checking is True

    settings = db.get_project_settings(proj.id)
    assert settings.get("voice_hints") is True


def test_voice_toggle_clears_deviations_on_disable():
    db, proj, s1 = _setup()
    view = WritingCoreView(db, proj.id)
    editor = list(view._editors.values())[0]

    editor._voice_deviations = [_make_deviation(0, 5, "hello")]
    editor._voice_hints_enabled = True
    view._voice_hints_checking = True

    view._toggle_voice_hints()
    assert editor._voice_deviations == []
    assert editor._voice_hints_enabled is False


def test_voice_toggle_enables_on_editors():
    db, proj, s1 = _setup()
    view = WritingCoreView(db, proj.id)
    editor = list(view._editors.values())[0]
    assert editor._voice_hints_enabled is False

    view._toggle_voice_hints()
    assert editor._voice_hints_enabled is True
