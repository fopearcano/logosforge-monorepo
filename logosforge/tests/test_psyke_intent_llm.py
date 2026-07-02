"""Tests for AI-based intent fallback (LLM response parsing/validation)."""

import json
from unittest.mock import patch

import pytest

from logosforge.psyke_intent_llm import _parse_response, _validate_args, detect_intent_llm
from logosforge.psyke_intents import Intent, detect_intent, intent_to_command


class TestParseResponse:
    """Test _parse_response handles all LLM output formats."""

    def test_valid_json(self):
        resp = '{"action": "open_scene", "args": {"id": 3}}'
        intent = _parse_response(resp)
        assert intent == Intent("open_scene", {"id": 3}, confidence=0.6)

    def test_json_with_whitespace(self):
        resp = '  \n{"action": "go_scene", "args": {"direction": "next"}}  \n'
        intent = _parse_response(resp)
        assert intent == Intent("go_scene", {"direction": "next"}, confidence=0.6)

    def test_json_in_code_block(self):
        resp = '```json\n{"action": "ai_action", "args": {"action": "rewrite"}}\n```'
        intent = _parse_response(resp)
        assert intent == Intent("ai_action", {"action": "rewrite"}, confidence=0.6)

    def test_null_action(self):
        resp = '{"action": null}'
        intent = _parse_response(resp)
        assert intent is None

    def test_unknown_action(self):
        resp = '{"action": "fly_to_moon", "args": {}}'
        intent = _parse_response(resp)
        assert intent is None

    def test_invalid_json(self):
        resp = "I think you want to open scene 3"
        intent = _parse_response(resp)
        assert intent is None

    def test_empty_response(self):
        intent = _parse_response("")
        assert intent is None

    def test_array_response(self):
        resp = '[{"action": "open_scene"}]'
        intent = _parse_response(resp)
        assert intent is None

    def test_missing_args(self):
        resp = '{"action": "open_scene"}'
        intent = _parse_response(resp)
        assert intent is None  # open_scene requires id or direction

    def test_args_not_dict(self):
        resp = '{"action": "ai_action", "args": "rewrite"}'
        intent = _parse_response(resp)
        assert intent is None


class TestValidateArgs:
    """Test arg validation for each action type."""

    def test_open_scene_id(self):
        result = _validate_args("open_scene", {"id": 5})
        assert result == {"id": 5}

    def test_open_scene_id_as_string(self):
        result = _validate_args("open_scene", {"id": "7"})
        assert result == {"id": 7}

    def test_open_scene_invalid_id(self):
        result = _validate_args("open_scene", {"id": "abc"})
        assert result is None

    def test_open_scene_direction(self):
        result = _validate_args("open_scene", {"direction": "next"})
        assert result == {"direction": "next"}

    def test_open_scene_bad_direction(self):
        result = _validate_args("open_scene", {"direction": "sideways"})
        assert result is None

    def test_go_scene_id(self):
        result = _validate_args("go_scene", {"id": 10})
        assert result == {"id": 10}

    def test_go_scene_direction(self):
        result = _validate_args("go_scene", {"direction": "previous"})
        assert result == {"direction": "previous"}

    def test_open_entry_name(self):
        result = _validate_args("open_entry", {"name": "John"})
        assert result == {"name": "John"}

    def test_open_entry_empty_name(self):
        result = _validate_args("open_entry", {"name": ""})
        assert result is None

    def test_create_entry(self):
        result = _validate_args("create_entry", {"entry_type": "character", "name": "Alice"})
        assert result == {"entry_type": "character", "name": "Alice"}

    def test_create_entry_bad_type_falls_back(self):
        result = _validate_args("create_entry", {"entry_type": "alien", "name": "Bob"})
        assert result == {"entry_type": "other", "name": "Bob"}

    def test_insert_entity(self):
        result = _validate_args("insert_entity", {"name": "Sword"})
        assert result == {"name": "Sword"}

    def test_ai_action_valid(self):
        result = _validate_args("ai_action", {"action": "expand"})
        assert result == {"action": "expand"}

    def test_ai_action_invalid(self):
        result = _validate_args("ai_action", {"action": "fly"})
        assert result is None

    def test_delete_entry(self):
        result = _validate_args("delete_entry", {"name": "Old Thing"})
        assert result == {"name": "Old Thing"}

    def test_rename_entry(self):
        result = _validate_args("rename_entry", {"name": "Old", "new_name": "New"})
        assert result == {"name": "Old", "new_name": "New"}

    def test_rename_entry_missing_new_name(self):
        result = _validate_args("rename_entry", {"name": "Old"})
        assert result is None


class TestLLMIntegration:
    """Test detect_intent_llm with mocked chat_completion."""

    def test_successful_classification(self):
        mock_response = '{"action": "go_scene", "args": {"direction": "next"}}'
        with patch("logosforge.psyke_intent_llm.chat_completion") as mock:
            mock.return_value = (mock_response, False)
            result = detect_intent_llm("take me to the next scene")
        assert result == Intent("go_scene", {"direction": "next"}, confidence=0.6)

    def test_ai_rewrite_classification(self):
        mock_response = '{"action": "ai_action", "args": {"action": "rewrite"}}'
        with patch("logosforge.psyke_intent_llm.chat_completion") as mock:
            mock.return_value = (mock_response, False)
            result = detect_intent_llm("make this dialogue better")
        assert result == Intent("ai_action", {"action": "rewrite"}, confidence=0.6)

    def test_connection_error_returns_none(self):
        with patch("logosforge.psyke_intent_llm.chat_completion") as mock:
            mock.side_effect = ConnectionError("no server")
            result = detect_intent_llm("do something")
        assert result is None

    def test_runtime_error_returns_none(self):
        with patch("logosforge.psyke_intent_llm.chat_completion") as mock:
            mock.side_effect = RuntimeError("bad response")
            result = detect_intent_llm("do something")
        assert result is None

    def test_null_action_returns_none(self):
        mock_response = '{"action": null}'
        with patch("logosforge.psyke_intent_llm.chat_completion") as mock:
            mock.return_value = (mock_response, False)
            result = detect_intent_llm("gibberish words")
        assert result is None


class TestDetectIntentWithLLMFlag:
    """Test that detect_intent(use_llm=True) falls back to LLM."""

    def test_rule_match_skips_llm(self):
        with patch("logosforge.psyke_intent_llm.detect_intent_llm") as mock:
            result = detect_intent("open scene 3", use_llm=True)
        mock.assert_not_called()
        assert result == Intent("open_scene", {"id": 3})

    def test_no_rule_calls_llm(self):
        mock_response = '{"action": "ai_action", "args": {"action": "rewrite"}}'
        with patch("logosforge.psyke_intent_llm.chat_completion") as mock:
            mock.return_value = (mock_response, False)
            result = detect_intent("make this dialogue better", use_llm=True)
        assert result == Intent("ai_action", {"action": "rewrite"}, confidence=0.6)

    def test_no_rule_no_llm_flag(self):
        result = detect_intent("make this dialogue better", use_llm=False)
        assert result is None


class TestEndToEndComplexPhrasing:
    """Simulate complex phrasings that rules miss but LLM handles."""

    @pytest.mark.parametrize("text,expected_response,expected_intent", [
        (
            "take me to the next scene",
            '{"action": "go_scene", "args": {"direction": "next"}}',
            Intent("go_scene", {"direction": "next"}, confidence=0.6),
        ),
        (
            "make this dialogue better",
            '{"action": "ai_action", "args": {"action": "rewrite"}}',
            Intent("ai_action", {"action": "rewrite"}, confidence=0.6),
        ),
        (
            "I want to see scene number five",
            '{"action": "open_scene", "args": {"id": 5}}',
            Intent("open_scene", {"id": 5}, confidence=0.6),
        ),
        (
            "I need a new villain called Dark Lord",
            '{"action": "create_entry", "args": {"entry_type": "character", "name": "Dark Lord"}}',
            Intent("create_entry", {"entry_type": "character", "name": "Dark Lord"}, confidence=0.6),
        ),
        (
            "can you flesh this out more",
            '{"action": "ai_action", "args": {"action": "expand"}}',
            Intent("ai_action", {"action": "expand"}, confidence=0.6),
        ),
        (
            "put john's name here",
            '{"action": "insert_entity", "args": {"name": "john"}}',
            Intent("insert_entity", {"name": "john"}, confidence=0.6),
        ),
    ])
    def test_complex_phrasing(self, text, expected_response, expected_intent):
        with patch("logosforge.psyke_intent_llm.chat_completion") as mock:
            mock.return_value = (expected_response, False)
            result = detect_intent(text, use_llm=True)
        assert result == expected_intent

    @pytest.mark.parametrize("text,expected_response", [
        (
            "take me to the next scene",
            '{"action": "go_scene", "args": {"direction": "next"}}',
        ),
        (
            "make this dialogue better",
            '{"action": "ai_action", "args": {"action": "rewrite"}}',
        ),
    ])
    def test_llm_intent_maps_to_command(self, text, expected_response):
        with patch("logosforge.psyke_intent_llm.chat_completion") as mock:
            mock.return_value = (expected_response, False)
            intent = detect_intent(text, use_llm=True)
        assert intent is not None
        cmd_str = intent_to_command(intent)
        assert cmd_str is not None
        assert cmd_str.startswith("/")
