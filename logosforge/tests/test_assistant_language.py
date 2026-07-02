"""Tests for centralized assistant response language injection."""

from logosforge.assistant import (
    _detect_response_language,
    _inject_language_instruction,
    _LANGUAGE_NAMES,
    build_messages,
)


# -- _detect_response_language ------------------------------------------------

def test_detect_english():
    messages = [
        {"role": "system", "content": "You are a helper."},
        {"role": "user", "content": "The old man sat by the window and watched the rain fall softly on the street."},
    ]
    assert _detect_response_language(messages) == "en"


def test_detect_italian():
    messages = [
        {"role": "system", "content": "You are a helper."},
        {"role": "user", "content": "Il vecchio sedeva vicino alla finestra e guardava la pioggia cadere dolcemente sulla strada."},
    ]
    assert _detect_response_language(messages) == "it"


def test_detect_spanish():
    messages = [
        {"role": "system", "content": "You are a helper."},
        {"role": "user", "content": "Los niños jugaban en el parque mientras sus padres hablaban tranquilamente en los bancos cercanos."},
    ]
    assert _detect_response_language(messages) == "es"


def test_detect_french():
    messages = [
        {"role": "system", "content": "You are a helper."},
        {"role": "user", "content": "Le vieil homme était assis près de la fenêtre et regardait la pluie tomber doucement sur la rue."},
    ]
    assert _detect_response_language(messages) == "fr"


def test_detect_german():
    messages = [
        {"role": "system", "content": "You are a helper."},
        {"role": "user", "content": "Der alte Mann saß am Fenster und beobachtete den Regen, der leise auf die Straße fiel."},
    ]
    assert _detect_response_language(messages) == "de"


def test_detect_short_text_defaults_english():
    messages = [
        {"role": "system", "content": "You are a helper."},
        {"role": "user", "content": "Ciao"},
    ]
    assert _detect_response_language(messages) == "en"


def test_detect_no_user_message_defaults_english():
    messages = [{"role": "system", "content": "You are a helper."}]
    assert _detect_response_language(messages) == "en"


def test_detect_empty_user_defaults_english():
    messages = [
        {"role": "system", "content": "You are a helper."},
        {"role": "user", "content": ""},
    ]
    assert _detect_response_language(messages) == "en"


# -- _inject_language_instruction ---------------------------------------------

def test_inject_skips_english():
    messages = [
        {"role": "system", "content": "Be helpful."},
        {"role": "user", "content": "Hello"},
    ]
    result = _inject_language_instruction(messages, "en")
    assert result is messages


def test_inject_modifies_system_for_italian():
    messages = [
        {"role": "system", "content": "Be helpful."},
        {"role": "user", "content": "Ciao"},
    ]
    result = _inject_language_instruction(messages, "it")
    assert result is not messages
    assert "Italian" in result[0]["content"]
    assert result[0]["content"].startswith("Be helpful.")
    assert result[1] == messages[1]


def test_inject_modifies_system_for_spanish():
    messages = [
        {"role": "system", "content": "Be helpful."},
        {"role": "user", "content": "Hola"},
    ]
    result = _inject_language_instruction(messages, "es")
    assert "Spanish" in result[0]["content"]


def test_inject_preserves_user_message():
    messages = [
        {"role": "system", "content": "Be helpful."},
        {"role": "user", "content": "Some text here."},
    ]
    result = _inject_language_instruction(messages, "fr")
    assert result[1]["content"] == "Some text here."


def test_inject_contains_safety_note():
    messages = [
        {"role": "system", "content": "System."},
        {"role": "user", "content": "User."},
    ]
    result = _inject_language_instruction(messages, "de")
    system = result[0]["content"]
    assert "JSON" in system
    assert "code" in system.lower()


def test_inject_all_supported_languages():
    messages = [
        {"role": "system", "content": "S"},
        {"role": "user", "content": "U"},
    ]
    for code, name in _LANGUAGE_NAMES.items():
        if code == "en":
            continue
        result = _inject_language_instruction(messages, code)
        assert name in result[0]["content"]


# -- Integration: build_messages + language injection -------------------------

def test_build_messages_system_prompt_unchanged_for_english():
    msgs = build_messages("Rewrite this.", "The dog ran across the field.")
    system = msgs[0]["content"]
    assert "IMPORTANT: Respond in" not in system


def test_language_names_cover_all_detected():
    from logosforge.grammar_checker import _TRIGRAM_PROFILES
    for lang_code in _TRIGRAM_PROFILES:
        assert lang_code in _LANGUAGE_NAMES, f"Missing name for {lang_code}"


# -- Edge cases ---------------------------------------------------------------

def test_inject_unknown_language_uses_code():
    messages = [
        {"role": "system", "content": "S"},
        {"role": "user", "content": "U"},
    ]
    result = _inject_language_instruction(messages, "ja")
    assert "ja" in result[0]["content"]


def test_inject_no_system_message():
    messages = [{"role": "user", "content": "Hello"}]
    result = _inject_language_instruction(messages, "it")
    assert len(result) == 1
    assert result[0]["content"] == "Hello"


def test_detect_uses_first_user_message():
    messages = [
        {"role": "system", "content": "System prompt."},
        {"role": "user", "content": "Il vecchio guardava la pioggia cadere dolcemente sulla strada che conduceva alla casa."},
        {"role": "assistant", "content": "Response."},
        {"role": "user", "content": "The man walked home through the rain."},
    ]
    lang = _detect_response_language(messages)
    assert lang == "it"
