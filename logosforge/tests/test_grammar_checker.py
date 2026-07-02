"""Tests for grammar_checker — language detection, spelling, grammar, style."""

from logosforge.grammar_checker import (
    Issue,
    RuleBasedChecker,
    check_text,
    detect_language,
)


# -- Language detection -------------------------------------------------------

def test_detect_english():
    text = "The quick brown fox jumped over the lazy dog and ran across the field."
    assert detect_language(text) == "en"


def test_detect_spanish():
    text = "El rápido zorro marrón saltó sobre el perro perezoso en el campo."
    assert detect_language(text) == "es"


def test_detect_french():
    text = "Le renard brun rapide a sauté par-dessus le chien paresseux dans le champ."
    assert detect_language(text) == "fr"


def test_detect_german():
    text = "Der schnelle braune Fuchs sprang über den faulen Hund auf dem Feld."
    assert detect_language(text) == "de"


def test_detect_short_text_defaults_english():
    assert detect_language("Hello") == "en"
    assert detect_language("") == "en"


# -- Issue dataclass ----------------------------------------------------------

def test_issue_creation():
    issue = Issue(start=0, end=5, issue_type="spelling", message="test")
    assert issue.start == 0
    assert issue.end == 5
    assert issue.issue_type == "spelling"
    assert issue.suggestions == []


def test_issue_with_suggestions():
    issue = Issue(start=0, end=5, issue_type="grammar", message="test",
                  suggestions=["fix"])
    assert issue.suggestions == ["fix"]


def test_issue_is_frozen():
    issue = Issue(start=0, end=5, issue_type="spelling", message="test")
    try:
        issue.start = 10
        assert False, "Should not allow mutation"
    except AttributeError:
        pass


# -- Spelling checks ----------------------------------------------------------

def test_spelling_detects_unknown_word():
    issues = check_text("The quikc brown fox jumped over the lazy dog.")
    spelling = [i for i in issues if i.issue_type == "spelling"]
    words = [i.message for i in spelling]
    assert any("quikc" in w for w in words)


def test_spelling_accepts_common_words():
    issues = check_text("The man walked to the door and opened it slowly.")
    spelling = [i for i in issues if i.issue_type == "spelling"]
    assert len(spelling) == 0


def test_spelling_accepts_contractions():
    issues = check_text("She didn't know what he couldn't understand.")
    spelling = [i for i in issues if i.issue_type == "spelling"]
    assert len(spelling) == 0


def test_spelling_accepts_possessives():
    issues = check_text("The man's hat was on the table.")
    spelling = [i for i in issues if i.issue_type == "spelling"]
    words = [i.message for i in spelling]
    assert not any("man's" in w.lower() for w in words)


def test_spelling_accepts_suffixed_forms():
    issues = check_text("He walked slowly and carefully through the opening.")
    spelling = [i for i in issues if i.issue_type == "spelling"]
    assert len(spelling) == 0


def test_spelling_skips_capitalized_names():
    issues = check_text("John walked to Elizabeth and said hello.")
    spelling = [i for i in issues if i.issue_type == "spelling"]
    words = [i.message for i in spelling]
    assert not any("John" in w for w in words)
    assert not any("Elizabeth" in w for w in words)


# -- Grammar checks -----------------------------------------------------------

def test_grammar_detects_doubled_word():
    issues = check_text("He went to the the store.")
    grammar = [i for i in issues if i.issue_type == "grammar"]
    assert any("Repeated word" in i.message for i in grammar)


def test_grammar_doubled_word_has_suggestion():
    issues = check_text("He went to the the store.")
    grammar = [i for i in issues if i.issue_type == "grammar" and "Repeated" in i.message]
    assert grammar[0].suggestions == ["the"]


def test_grammar_detects_capitalization():
    issues = check_text("Hello world. this is wrong.")
    grammar = [i for i in issues if i.issue_type == "grammar"]
    assert any("capital" in i.message for i in grammar)


def test_grammar_capitalization_has_suggestion():
    issues = check_text("Hello world. this is wrong.")
    grammar = [i for i in issues if "capital" in i.message]
    assert grammar[0].suggestions == ["T"]


def test_grammar_correct_text_no_issues():
    issues = check_text("He went to the store. She went home.")
    grammar = [i for i in issues if i.issue_type == "grammar"]
    assert len(grammar) == 0


# -- Style checks -------------------------------------------------------------

def test_style_detects_passive_voice():
    issues = check_text("The ball was thrown by the boy.")
    style = [i for i in issues if i.issue_type == "style"]
    assert any("Passive" in i.message for i in style)


def test_style_detects_long_sentence():
    words = " ".join(["word"] * 45)
    issues = check_text(f"This is a {words} sentence.")
    style = [i for i in issues if i.issue_type == "style"]
    assert any("long sentence" in i.message.lower() for i in style)


def test_style_normal_sentence_no_issue():
    issues = check_text("The dog ran across the field quickly.")
    style = [i for i in issues if i.issue_type == "style"]
    assert len(style) == 0


# -- check_text API -----------------------------------------------------------

def test_check_text_empty():
    assert check_text("") == []
    assert check_text("   ") == []


def test_check_text_returns_issues():
    issues = check_text("He went to the the store.")
    assert len(issues) > 0
    assert all(isinstance(i, Issue) for i in issues)


def test_check_text_positions_are_valid():
    text = "He went to the the store."
    issues = check_text(text)
    for issue in issues:
        assert 0 <= issue.start < len(text)
        assert issue.start < issue.end <= len(text)


def test_check_text_issue_types():
    valid_types = {"spelling", "grammar", "style"}
    issues = check_text("The quikc boy was thrown. He went to the the store. this is bad.")
    for issue in issues:
        assert issue.issue_type in valid_types


def test_check_text_custom_backend():
    class NullBackend:
        def check(self, text, language):
            return [Issue(start=0, end=1, issue_type="grammar", message="custom")]

    issues = check_text("Hello world.", backend=NullBackend())
    assert len(issues) == 1
    assert issues[0].message == "custom"


def test_check_text_clean_prose():
    text = (
        "The old man sat by the window and watched the rain fall. "
        "He thought about the past and smiled. "
        "The house was quiet."
    )
    issues = check_text(text)
    grammar = [i for i in issues if i.issue_type == "grammar"]
    spelling = [i for i in issues if i.issue_type == "spelling"]
    assert len(grammar) == 0
    assert len(spelling) == 0
