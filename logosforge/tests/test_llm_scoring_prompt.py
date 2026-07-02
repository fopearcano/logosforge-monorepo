"""Tests for the standardised LLM scoring prompt and parser."""

import json
from unittest.mock import patch

import pytest

from logosforge.quantum_outliner.llm_evaluator import (
    _FACTOR_KEYS,
    _SYSTEM_PROMPT,
    _extract_json_object,
    _parse_factors,
    _strip_fences,
    build_eval_prompt,
    evaluate_branches,
    score_with_llm,
)
from logosforge.quantum_outliner.state import Branch


def _branch(bid="x", title="Test", desc="desc", stakes="", consequence=""):
    return Branch(
        id=bid, title=title, description=desc,
        stakes=stakes, consequence=consequence,
    )


_VALID_FACTORS = {
    "structure_fit": 0.8,
    "psyke_consistency": 0.6,
    "tension_gain": 0.9,
    "novelty": 0.4,
    "goal_alignment": 0.7,
}


# ---------------------------------------------------------------------------
# System prompt content
# ---------------------------------------------------------------------------


class TestSystemPrompt:
    def test_mentions_all_five_factors(self):
        for key in _FACTOR_KEYS:
            assert key in _SYSTEM_PROMPT

    def test_requests_json_only(self):
        lower = _SYSTEM_PROMPT.lower()
        assert "json only" in lower or "only json" in lower or "only the json" in lower

    def test_describes_criteria(self):
        assert "structure_fit" in _SYSTEM_PROMPT
        assert "tension" in _SYSTEM_PROMPT
        assert "novelty" in _SYSTEM_PROMPT
        assert "goal" in _SYSTEM_PROMPT
        assert "consistency" in _SYSTEM_PROMPT.lower() or "psyke_consistency" in _SYSTEM_PROMPT

    def test_no_markdown_instruction(self):
        lower = _SYSTEM_PROMPT.lower()
        assert "no markdown" in lower


# ---------------------------------------------------------------------------
# build_eval_prompt — structured context
# ---------------------------------------------------------------------------


class TestBuildEvalPrompt:
    def test_includes_branch_title_and_description(self):
        b = _branch(title="The Betrayal", desc="Hero is betrayed by ally")
        prompt = build_eval_prompt(b)
        assert "The Betrayal" in prompt
        assert "Hero is betrayed by ally" in prompt

    def test_includes_stakes_and_consequence(self):
        b = _branch(stakes="Alliance lost", consequence="War begins")
        prompt = build_eval_prompt(b)
        assert "Alliance lost" in prompt
        assert "War begins" in prompt

    def test_omits_empty_stakes(self):
        b = _branch(stakes="", consequence="")
        prompt = build_eval_prompt(b)
        assert "Stakes:" not in prompt
        assert "Consequence:" not in prompt

    def test_includes_beat(self):
        b = _branch()
        prompt = build_eval_prompt(b, beat="Midpoint")
        assert "Beat: Midpoint" in prompt

    def test_includes_method(self):
        b = _branch()
        prompt = build_eval_prompt(b, method="Save the Cat")
        assert "Method: Save the Cat" in prompt

    def test_includes_psyke_brief(self):
        b = _branch()
        prompt = build_eval_prompt(b, psyke_brief="Characters:\n- Alice: protagonist")
        assert "Story bible:" in prompt
        assert "Alice" in prompt

    def test_full_structured_context(self):
        b = _branch(title="Escape", desc="Hero escapes the dungeon",
                    stakes="Freedom", consequence="Pursuit begins")
        prompt = build_eval_prompt(
            b, beat="Break Into Three", method="Save the Cat",
            psyke_brief="Characters:\n- Hero: brave knight",
        )
        assert "Context:" in prompt
        assert "Beat: Break Into Three" in prompt
        assert "Method: Save the Cat" in prompt
        assert "brave knight" in prompt
        assert "Option:" in prompt
        assert "Escape" in prompt
        assert "Freedom" in prompt

    def test_no_context_section_when_no_context(self):
        b = _branch(title="Simple")
        prompt = build_eval_prompt(b)
        assert "Context:" not in prompt
        assert "Option:" in prompt


# ---------------------------------------------------------------------------
# _strip_fences
# ---------------------------------------------------------------------------


class TestStripFences:
    def test_strips_json_fences(self):
        raw = '```json\n{"a": 1}\n```'
        assert _strip_fences(raw) == '{"a": 1}'

    def test_strips_plain_fences(self):
        raw = '```\n{"a": 1}\n```'
        assert _strip_fences(raw) == '{"a": 1}'

    def test_no_fences_unchanged(self):
        raw = '{"a": 1}'
        assert _strip_fences(raw) == '{"a": 1}'

    def test_strips_whitespace(self):
        raw = '  \n{"a": 1}\n  '
        assert _strip_fences(raw) == '{"a": 1}'


# ---------------------------------------------------------------------------
# _extract_json_object
# ---------------------------------------------------------------------------


class TestExtractJsonObject:
    def test_extracts_from_surrounding_text(self):
        raw = 'Here are the scores: {"structure_fit": 0.5} that is all'
        assert _extract_json_object(raw) == '{"structure_fit": 0.5}'

    def test_handles_nested_braces(self):
        raw = '{"a": {"b": 1}}'
        assert _extract_json_object(raw) == '{"a": {"b": 1}}'

    def test_returns_none_for_no_braces(self):
        assert _extract_json_object("no json here") is None

    def test_returns_none_for_unclosed_brace(self):
        assert _extract_json_object('{"a": 1') is None


# ---------------------------------------------------------------------------
# _parse_factors — malformed JSON handled
# ---------------------------------------------------------------------------


class TestParseFactorsMalformed:
    def test_valid_json(self):
        result = _parse_factors(json.dumps(_VALID_FACTORS))
        assert result is not None
        assert result["tension_gain"] == 0.9

    def test_trailing_comma(self):
        raw = '{"structure_fit": 0.5, "psyke_consistency": 0.5, "tension_gain": 0.5, "novelty": 0.5, "goal_alignment": 0.5,}'
        result = _parse_factors(raw)
        assert result is not None

    def test_single_quotes(self):
        raw = "{'structure_fit': 0.5, 'psyke_consistency': 0.5, 'tension_gain': 0.5, 'novelty': 0.5, 'goal_alignment': 0.5}"
        result = _parse_factors(raw)
        assert result is not None

    def test_markdown_json_fence(self):
        raw = "```json\n" + json.dumps(_VALID_FACTORS) + "\n```"
        result = _parse_factors(raw)
        assert result is not None

    def test_plain_markdown_fence(self):
        raw = "```\n" + json.dumps(_VALID_FACTORS) + "\n```"
        result = _parse_factors(raw)
        assert result is not None

    def test_surrounding_explanation(self):
        raw = "Here are the scores:\n" + json.dumps(_VALID_FACTORS) + "\nDone."
        result = _parse_factors(raw)
        assert result is not None

    def test_completely_invalid(self):
        assert _parse_factors("I can't do that") is None

    def test_empty_string(self):
        assert _parse_factors("") is None

    def test_array_instead_of_object(self):
        assert _parse_factors("[0.5, 0.5, 0.5]") is None

    def test_missing_key(self):
        partial = {k: 0.5 for k in list(_FACTOR_KEYS)[:3]}
        assert _parse_factors(json.dumps(partial)) is None

    def test_non_numeric_value(self):
        bad = dict(_VALID_FACTORS)
        bad["tension_gain"] = "high"
        assert _parse_factors(json.dumps(bad)) is None

    def test_null_value(self):
        bad = dict(_VALID_FACTORS)
        bad["novelty"] = None
        assert _parse_factors(json.dumps(bad)) is None

    def test_nested_wrapper(self):
        wrapped = {"result": _VALID_FACTORS, "structure_fit": 0.8,
                   "psyke_consistency": 0.6, "tension_gain": 0.9,
                   "novelty": 0.4, "goal_alignment": 0.7}
        result = _parse_factors(json.dumps(wrapped))
        assert result is not None

    def test_extra_keys_ignored(self):
        extended = dict(_VALID_FACTORS)
        extended["reasoning"] = "this branch is strong"
        result = _parse_factors(json.dumps(extended))
        assert result is not None
        assert "reasoning" not in result


# ---------------------------------------------------------------------------
# _parse_factors — values clamped
# ---------------------------------------------------------------------------


class TestParseFactorsClamped:
    def test_clamps_above_one(self):
        over = dict(_VALID_FACTORS)
        over["structure_fit"] = 1.5
        result = _parse_factors(json.dumps(over))
        assert result is not None
        assert result["structure_fit"] == 1.0

    def test_clamps_below_zero(self):
        under = dict(_VALID_FACTORS)
        under["psyke_consistency"] = -0.3
        result = _parse_factors(json.dumps(under))
        assert result is not None
        assert result["psyke_consistency"] == 0.0

    def test_boundary_one_preserved(self):
        exact = {k: 1.0 for k in _FACTOR_KEYS}
        result = _parse_factors(json.dumps(exact))
        assert all(v == 1.0 for v in result.values())

    def test_boundary_zero_preserved(self):
        exact = {k: 0.0 for k in _FACTOR_KEYS}
        result = _parse_factors(json.dumps(exact))
        assert all(v == 0.0 for v in result.values())

    def test_integer_values_accepted(self):
        ints = {k: 1 for k in _FACTOR_KEYS}
        result = _parse_factors(json.dumps(ints))
        assert result is not None
        assert all(v == 1.0 for v in result.values())


# ---------------------------------------------------------------------------
# _parse_factors maps to exactly 5 factors
# ---------------------------------------------------------------------------


class TestParseFactorsMapping:
    def test_returns_exactly_five_keys(self):
        result = _parse_factors(json.dumps(_VALID_FACTORS))
        assert set(result.keys()) == _FACTOR_KEYS

    def test_values_are_floats(self):
        result = _parse_factors(json.dumps(_VALID_FACTORS))
        for v in result.values():
            assert isinstance(v, float)


# ---------------------------------------------------------------------------
# score_with_llm — structured context passed to LLM
# ---------------------------------------------------------------------------


def _mock_chat_success(messages, **kwargs):
    return (json.dumps(_VALID_FACTORS), False)


class TestScoreWithLLMPrompt:
    @patch("logosforge.quantum_outliner.llm_evaluator.chat_completion",
           side_effect=_mock_chat_success)
    def test_structured_context_in_prompt(self, mock_cc):
        b = _branch(title="Escape", desc="Hero runs away")
        score_with_llm(b, beat="Midpoint", method="Save the Cat",
                       psyke_brief="Characters:\n- Hero: brave knight")
        call_args = mock_cc.call_args[0][0]
        system_msg = call_args[0]["content"]
        user_msg = call_args[1]["content"]
        assert system_msg == _SYSTEM_PROMPT
        assert "Beat: Midpoint" in user_msg
        assert "Method: Save the Cat" in user_msg
        assert "brave knight" in user_msg
        assert "Escape" in user_msg

    @patch("logosforge.quantum_outliner.llm_evaluator.chat_completion",
           side_effect=_mock_chat_success)
    def test_plain_context_fallback(self, mock_cc):
        b = _branch(title="Test")
        score_with_llm(b, "some plain context")
        user_msg = mock_cc.call_args[0][0][1]["content"]
        assert "some plain context" in user_msg
        assert "Test" in user_msg

    @patch("logosforge.quantum_outliner.llm_evaluator.chat_completion",
           side_effect=_mock_chat_success)
    def test_structured_overrides_plain(self, mock_cc):
        b = _branch(title="Test")
        score_with_llm(b, "plain context", beat="Midpoint")
        user_msg = mock_cc.call_args[0][0][1]["content"]
        assert "Beat: Midpoint" in user_msg
        assert "plain context" not in user_msg

    @patch("logosforge.quantum_outliner.llm_evaluator.chat_completion",
           side_effect=_mock_chat_success)
    def test_no_context_still_includes_option(self, mock_cc):
        b = _branch(title="Test", desc="something happens")
        score_with_llm(b)
        user_msg = mock_cc.call_args[0][0][1]["content"]
        assert "Option:" in user_msg
        assert "Test" in user_msg


# ---------------------------------------------------------------------------
# evaluate_branches — structured context forwarded
# ---------------------------------------------------------------------------


class TestEvaluateBranchesStructured:
    @patch("logosforge.quantum_outliner.llm_evaluator.chat_completion",
           side_effect=_mock_chat_success)
    def test_forwards_structured_context(self, mock_cc):
        branches = [_branch("a", "Alpha"), _branch("b", "Beta")]
        evaluate_branches(
            branches, beat="Midpoint", psyke_brief="Characters:\n- X",
        )
        for call in mock_cc.call_args_list:
            user_msg = call[0][0][1]["content"]
            assert "Beat: Midpoint" in user_msg

    @patch("logosforge.quantum_outliner.llm_evaluator.chat_completion",
           side_effect=_mock_chat_success)
    def test_plain_context_still_works(self, mock_cc):
        branches = [_branch("a", "Alpha")]
        evaluate_branches(branches, "story context")
        user_msg = mock_cc.call_args[0][0][1]["content"]
        assert "story context" in user_msg
