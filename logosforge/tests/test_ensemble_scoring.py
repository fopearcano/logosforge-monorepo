"""Tests for ensemble scoring (heuristic + LLM evaluator)."""

import json
from unittest.mock import patch

import pytest

from logosforge.db import Database
from logosforge.quantum_outliner.llm_evaluator import (
    _parse_factors,
    score_with_llm,
    evaluate_branches,
)
from logosforge.quantum_outliner.scoring import (
    ENSEMBLE_ALPHA,
    apply_scores,
    ensemble_combine,
    score_branches,
    score_with_heuristic,
)
from logosforge.quantum_outliner.state import Branch, Wavefunction, _STATES


@pytest.fixture(autouse=True)
def _reset():
    _STATES.clear()
    yield
    _STATES.clear()


@pytest.fixture
def db(tmp_path):
    return Database(str(tmp_path / "test.db"))


@pytest.fixture
def project(db):
    return db.create_project("Ensemble Test")


def _branch(bid, title, desc="desc", stakes="", consequence="", branch_type="alternative"):
    return Branch(
        id=bid, title=title, description=desc,
        stakes=stakes, consequence=consequence,
        branch_type=branch_type,
    )


def _factors(**overrides):
    base = {
        "structure_fit": 0.5,
        "psyke_consistency": 0.5,
        "tension_gain": 0.5,
        "novelty": 0.5,
        "goal_alignment": 0.5,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# ENSEMBLE_ALPHA constant
# ---------------------------------------------------------------------------


class TestEnsembleAlpha:
    def test_default_value(self):
        assert ENSEMBLE_ALPHA == 0.7

    def test_db_default(self, db, project):
        assert db.get_ensemble_alpha(project.id) == 0.7

    def test_db_set_and_get(self, db, project):
        db.set_ensemble_alpha(project.id, 0.5)
        assert db.get_ensemble_alpha(project.id) == 0.5

    def test_db_clamps_high(self, db, project):
        db.set_ensemble_alpha(project.id, 1.5)
        assert db.get_ensemble_alpha(project.id) == 1.0

    def test_db_clamps_low(self, db, project):
        db.set_ensemble_alpha(project.id, -0.2)
        assert db.get_ensemble_alpha(project.id) == 0.0

    def test_db_persists(self, tmp_path):
        path = str(tmp_path / "persist.db")
        db1 = Database(path)
        p = db1.create_project("Persist")
        db1.set_ensemble_alpha(p.id, 0.3)
        db2 = Database(path)
        assert db2.get_ensemble_alpha(p.id) == 0.3


# ---------------------------------------------------------------------------
# score_with_heuristic
# ---------------------------------------------------------------------------


class TestScoreWithHeuristic:
    def test_returns_five_factors(self):
        wf = Wavefunction.new(anchor="test")
        b = _branch("a", "Test", desc="sudden fight danger")
        wf.branches = [b]
        factors = score_with_heuristic(b, wf)
        assert set(factors.keys()) == {
            "structure_fit", "psyke_consistency", "tension_gain",
            "novelty", "goal_alignment",
        }

    def test_values_in_range(self):
        wf = Wavefunction.new(anchor="test")
        b = _branch("a", "Test", desc="sudden fight danger")
        wf.branches = [b]
        factors = score_with_heuristic(b, wf)
        for v in factors.values():
            assert 0.0 <= v <= 1.0

    def test_matches_compute_factors(self):
        from logosforge.quantum_outliner.scoring import compute_factors
        wf = Wavefunction.new(anchor="test")
        b = _branch("a", "Test", desc="fight danger must")
        wf.branches = [b]
        heuristic = score_with_heuristic(b, wf)
        direct = compute_factors(b, wf)
        assert heuristic == direct


# ---------------------------------------------------------------------------
# ensemble_combine
# ---------------------------------------------------------------------------


class TestEnsembleCombine:
    def test_none_llm_returns_heuristic(self):
        h = _factors(tension_gain=0.9)
        result = ensemble_combine(h, None)
        assert result == h

    def test_alpha_one_pure_heuristic(self):
        h = _factors(tension_gain=0.9)
        l = _factors(tension_gain=0.1)
        result = ensemble_combine(h, l, alpha=1.0)
        assert result["tension_gain"] == pytest.approx(0.9, abs=0.001)

    def test_alpha_zero_pure_llm(self):
        h = _factors(tension_gain=0.1)
        l = _factors(tension_gain=0.9)
        result = ensemble_combine(h, l, alpha=0.0)
        assert result["tension_gain"] == pytest.approx(0.9, abs=0.001)

    def test_default_alpha_blends(self):
        h = _factors(tension_gain=1.0)
        l = _factors(tension_gain=0.0)
        result = ensemble_combine(h, l, alpha=0.7)
        assert result["tension_gain"] == pytest.approx(0.7, abs=0.001)

    def test_all_factors_blended(self):
        h = _factors(structure_fit=1.0, novelty=0.0)
        l = _factors(structure_fit=0.0, novelty=1.0)
        result = ensemble_combine(h, l, alpha=0.5)
        assert result["structure_fit"] == pytest.approx(0.5, abs=0.001)
        assert result["novelty"] == pytest.approx(0.5, abs=0.001)

    def test_alpha_clamped_above_one(self):
        h = _factors(tension_gain=0.8)
        l = _factors(tension_gain=0.2)
        result = ensemble_combine(h, l, alpha=1.5)
        assert result["tension_gain"] == pytest.approx(0.8, abs=0.001)

    def test_alpha_clamped_below_zero(self):
        h = _factors(tension_gain=0.2)
        l = _factors(tension_gain=0.8)
        result = ensemble_combine(h, l, alpha=-0.5)
        assert result["tension_gain"] == pytest.approx(0.8, abs=0.001)


# ---------------------------------------------------------------------------
# LLM evaluator — _parse_factors
# ---------------------------------------------------------------------------


class TestParseFactors:
    def test_valid_json(self):
        raw = json.dumps({
            "structure_fit": 0.8, "psyke_consistency": 0.6,
            "tension_gain": 0.9, "novelty": 0.4, "goal_alignment": 0.7,
        })
        result = _parse_factors(raw)
        assert result is not None
        assert result["tension_gain"] == 0.9

    def test_strips_markdown_fences(self):
        raw = "```json\n" + json.dumps({
            "structure_fit": 0.5, "psyke_consistency": 0.5,
            "tension_gain": 0.5, "novelty": 0.5, "goal_alignment": 0.5,
        }) + "\n```"
        assert _parse_factors(raw) is not None

    def test_clamps_values(self):
        raw = json.dumps({
            "structure_fit": 1.5, "psyke_consistency": -0.3,
            "tension_gain": 0.5, "novelty": 0.5, "goal_alignment": 0.5,
        })
        result = _parse_factors(raw)
        assert result["structure_fit"] == 1.0
        assert result["psyke_consistency"] == 0.0

    def test_missing_key_returns_none(self):
        raw = json.dumps({
            "structure_fit": 0.5, "tension_gain": 0.5,
        })
        assert _parse_factors(raw) is None

    def test_invalid_json_returns_none(self):
        assert _parse_factors("not json at all") is None

    def test_non_numeric_value_returns_none(self):
        raw = json.dumps({
            "structure_fit": "high", "psyke_consistency": 0.5,
            "tension_gain": 0.5, "novelty": 0.5, "goal_alignment": 0.5,
        })
        assert _parse_factors(raw) is None

    def test_array_returns_none(self):
        assert _parse_factors("[1, 2, 3]") is None


# ---------------------------------------------------------------------------
# score_with_llm — mocked
# ---------------------------------------------------------------------------


_GOOD_RESPONSE = json.dumps({
    "structure_fit": 0.8, "psyke_consistency": 0.7,
    "tension_gain": 0.9, "novelty": 0.3, "goal_alignment": 0.6,
})


def _mock_chat_success(messages, **kwargs):
    return (_GOOD_RESPONSE, False)


def _mock_chat_failure(messages, **kwargs):
    raise ConnectionError("offline")


class TestScoreWithLLM:
    @patch("logosforge.quantum_outliner.llm_evaluator.chat_completion", side_effect=_mock_chat_success)
    def test_returns_factors_on_success(self, mock_cc):
        b = _branch("a", "Test Branch", desc="something happens")
        result = score_with_llm(b, "story context")
        assert result is not None
        assert set(result.keys()) == {
            "structure_fit", "psyke_consistency", "tension_gain",
            "novelty", "goal_alignment",
        }
        assert result["tension_gain"] == 0.9

    @patch("logosforge.quantum_outliner.llm_evaluator.chat_completion", side_effect=_mock_chat_failure)
    def test_returns_none_on_failure(self, mock_cc):
        b = _branch("a", "Test Branch", desc="something happens")
        result = score_with_llm(b, "story context")
        assert result is None

    @patch("logosforge.quantum_outliner.llm_evaluator.chat_completion",
           return_value=("not valid json", False))
    def test_returns_none_on_bad_json(self, mock_cc):
        b = _branch("a", "Test Branch", desc="something happens")
        result = score_with_llm(b, "story context")
        assert result is None


# ---------------------------------------------------------------------------
# evaluate_branches — mocked
# ---------------------------------------------------------------------------


class TestEvaluateBranches:
    @patch("logosforge.quantum_outliner.llm_evaluator.chat_completion", side_effect=_mock_chat_success)
    def test_returns_all_on_success(self, mock_cc):
        branches = [
            _branch("a", "Alpha", desc="fight danger"),
            _branch("b", "Beta", desc="calm walk"),
        ]
        results = evaluate_branches(branches, "context")
        assert "a" in results
        assert "b" in results

    @patch("logosforge.quantum_outliner.llm_evaluator.chat_completion", side_effect=_mock_chat_failure)
    def test_returns_empty_on_all_failures(self, mock_cc):
        branches = [_branch("a", "Alpha")]
        results = evaluate_branches(branches, "context")
        assert results == {}

    @patch("logosforge.quantum_outliner.llm_evaluator.chat_completion")
    def test_partial_failure(self, mock_cc):
        call_count = [0]
        def _alternating(messages, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return (_GOOD_RESPONSE, False)
            raise ConnectionError("offline")
        mock_cc.side_effect = _alternating
        branches = [
            _branch("a", "Alpha"),
            _branch("b", "Beta"),
        ]
        results = evaluate_branches(branches, "context")
        assert "a" in results
        assert "b" not in results


# ---------------------------------------------------------------------------
# Ensemble changes ranking in score_branches
# ---------------------------------------------------------------------------


class TestEnsembleChangesRanking:
    def test_llm_scores_shift_ranking(self):
        wf = Wavefunction.new(anchor="test")
        wf.branches = [
            _branch("a", "Tension Path",
                    desc="sudden fight danger risk must conflict",
                    stakes="desperate sacrifice",
                    consequence="war threat"),
            _branch("b", "Calm Path",
                    desc="a quiet peaceful stroll through the garden"),
        ]

        heuristic_only = score_branches(wf)
        h_ranking = [s.branch_id for s in heuristic_only]

        llm_scores = {
            "a": _factors(tension_gain=0.1, novelty=0.1, structure_fit=0.1,
                         psyke_consistency=0.1, goal_alignment=0.1),
            "b": _factors(tension_gain=0.9, novelty=0.9, structure_fit=0.9,
                         psyke_consistency=0.9, goal_alignment=0.9),
        }
        ensemble = score_branches(wf, llm_scores=llm_scores, ensemble_alpha=0.3)
        e_ranking = [s.branch_id for s in ensemble]

        assert e_ranking != h_ranking

    def test_no_llm_scores_same_as_heuristic(self):
        wf = Wavefunction.new(anchor="test")
        wf.branches = [
            _branch("a", "Alpha", desc="sudden fight danger"),
            _branch("b", "Beta", desc="calm walk"),
        ]
        h = score_branches(wf)
        e = score_branches(wf, llm_scores=None)
        assert [s.score for s in h] == [s.score for s in e]

    def test_alpha_one_ignores_llm(self):
        wf = Wavefunction.new(anchor="test")
        wf.branches = [
            _branch("a", "Alpha", desc="sudden fight danger"),
        ]
        h = score_branches(wf)

        llm_scores = {"a": _factors(tension_gain=0.0)}
        e = score_branches(wf, llm_scores=llm_scores, ensemble_alpha=1.0)

        assert h[0].score == e[0].score

    def test_ensemble_preserves_constraints(self):
        wf = Wavefunction.new(anchor="test")
        wf.branches = [
            _branch("a", "Safe path", desc="a safe journey"),
            _branch("b", "Betrayal", desc="betrayal and lies"),
        ]
        llm_scores = {
            "a": _factors(tension_gain=0.5),
            "b": _factors(tension_gain=0.9),
        }
        result = score_branches(
            wf, llm_scores=llm_scores, constraints=["No betrayal"],
        )
        by_id = {s.branch_id: s for s in result}
        assert by_id["b"].score == 0.0
        assert by_id["b"].violations == ["No betrayal"]

    def test_ensemble_with_partial_llm(self):
        wf = Wavefunction.new(anchor="test")
        wf.branches = [
            _branch("a", "Alpha", desc="sudden fight danger"),
            _branch("b", "Beta", desc="calm walk"),
        ]
        llm_scores = {"a": _factors(tension_gain=0.0)}
        result = score_branches(wf, llm_scores=llm_scores, ensemble_alpha=0.5)
        by_id = {s.branch_id: s for s in result}
        assert by_id["a"].factors["tension_gain"] != by_id["b"].factors["tension_gain"]


# ---------------------------------------------------------------------------
# Failure fallback — LLM fails, heuristic-only
# ---------------------------------------------------------------------------


class TestFailureFallback:
    @patch("logosforge.quantum_outliner.llm_evaluator.chat_completion", side_effect=_mock_chat_failure)
    def test_evaluate_returns_empty_then_heuristic_only(self, mock_cc):
        wf = Wavefunction.new(anchor="test")
        wf.branches = [
            _branch("a", "Alpha", desc="sudden fight danger"),
            _branch("b", "Beta", desc="calm walk"),
        ]
        llm_scores = evaluate_branches(wf.branches, "context")
        assert llm_scores == {}

        h = score_branches(wf)
        e = score_branches(wf, llm_scores=llm_scores)
        assert [s.score for s in h] == [s.score for s in e]

    @patch("logosforge.quantum_outliner.llm_evaluator.chat_completion", side_effect=_mock_chat_failure)
    def test_fallback_still_produces_valid_ranking(self, mock_cc):
        wf = Wavefunction.new(anchor="test")
        wf.branches = [
            _branch("a", "Alpha", desc="sudden fight danger"),
            _branch("b", "Beta", desc="calm walk"),
            _branch("c", "Gamma", desc="desperate risk"),
        ]
        llm_scores = evaluate_branches(wf.branches, "context")
        result = score_branches(wf, llm_scores=llm_scores)
        total_prob = sum(s.probability for s in result)
        assert abs(total_prob - 1.0) < 0.01
        assert result[0].score >= result[-1].score

    def test_none_llm_scores_is_same_as_empty(self):
        wf = Wavefunction.new(anchor="test")
        wf.branches = [_branch("a", "Alpha", desc="sudden fight danger")]
        r1 = score_branches(wf, llm_scores=None)
        r2 = score_branches(wf, llm_scores={})
        assert r1[0].score == r2[0].score
