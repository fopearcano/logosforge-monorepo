"""Tests for goal-aware scoring — compute_goal_score and score_branches integration."""

import pytest

from logosforge.quantum_outliner.scoring import (
    GOAL_FACTOR_MAP,
    QuantumGoals,
    apply_scores,
    compute_goal_score,
    score_branches,
)
from logosforge.quantum_outliner.state import Branch, Wavefunction, _STATES


@pytest.fixture(autouse=True)
def _reset():
    _STATES.clear()
    yield
    _STATES.clear()


def _branch(bid, title, desc="desc", stakes="", consequence="", branch_type="alternative"):
    return Branch(
        id=bid, title=title, description=desc,
        stakes=stakes, consequence=consequence,
        branch_type=branch_type,
    )


# ---------------------------------------------------------------------------
# compute_goal_score unit tests
# ---------------------------------------------------------------------------


class TestComputeGoalScore:
    def test_balanced_goals_averages_factors(self):
        factors = {
            "structure_fit": 0.8,
            "psyke_consistency": 0.6,
            "tension_gain": 0.4,
            "novelty": 0.2,
            "goal_alignment": 0.5,
        }
        goals = QuantumGoals()  # all 0.2
        score, valid = compute_goal_score(factors, goals)
        expected = 0.2 * (0.8 + 0.6 + 0.4 + 0.2 + 0.5)
        assert abs(score - round(expected, 4)) < 0.01
        assert valid is True

    def test_tension_heavy_goals_favors_tension(self):
        factors_tense = {
            "structure_fit": 0.3, "psyke_consistency": 0.3,
            "tension_gain": 0.9, "novelty": 0.3, "goal_alignment": 0.3,
        }
        factors_calm = {
            "structure_fit": 0.3, "psyke_consistency": 0.3,
            "tension_gain": 0.1, "novelty": 0.3, "goal_alignment": 0.3,
        }
        goals = QuantumGoals(objectives={
            "tension": 0.6, "consistency": 0.1, "novelty": 0.1,
            "structure": 0.1, "character_focus": 0.1,
        }).validate()

        score_tense, _ = compute_goal_score(factors_tense, goals)
        score_calm, _ = compute_goal_score(factors_calm, goals)
        assert score_tense > score_calm

    def test_min_constraint_violated_returns_zero(self):
        factors = {
            "structure_fit": 0.8, "psyke_consistency": 0.3,
            "tension_gain": 0.5, "novelty": 0.5, "goal_alignment": 0.5,
        }
        goals = QuantumGoals(min_constraints={"psyke_consistency": 0.6})
        score, valid = compute_goal_score(factors, goals)
        assert valid is False
        assert score == 0.0

    def test_min_constraint_satisfied_keeps_score(self):
        factors = {
            "structure_fit": 0.8, "psyke_consistency": 0.7,
            "tension_gain": 0.5, "novelty": 0.5, "goal_alignment": 0.5,
        }
        goals = QuantumGoals(min_constraints={"psyke_consistency": 0.6})
        score, valid = compute_goal_score(factors, goals)
        assert valid is True
        assert score > 0.0

    def test_multiple_min_constraints_all_must_pass(self):
        factors = {
            "structure_fit": 0.8, "psyke_consistency": 0.7,
            "tension_gain": 0.2, "novelty": 0.5, "goal_alignment": 0.5,
        }
        goals = QuantumGoals(min_constraints={
            "psyke_consistency": 0.6,
            "tension_gain": 0.5,
        })
        score, valid = compute_goal_score(factors, goals)
        assert valid is False
        assert score == 0.0

    def test_empty_factors_returns_zero(self):
        goals = QuantumGoals()
        score, valid = compute_goal_score({}, goals)
        assert score == 0.0
        assert valid is True

    def test_no_goals_constraints_always_valid(self):
        factors = {
            "structure_fit": 0.1, "psyke_consistency": 0.1,
            "tension_gain": 0.1, "novelty": 0.1, "goal_alignment": 0.1,
        }
        goals = QuantumGoals(min_constraints={})
        _, valid = compute_goal_score(factors, goals)
        assert valid is True

    def test_exact_threshold_passes(self):
        factors = {"psyke_consistency": 0.6, "structure_fit": 0.5,
                   "tension_gain": 0.5, "novelty": 0.5, "goal_alignment": 0.5}
        goals = QuantumGoals(min_constraints={"psyke_consistency": 0.6})
        _, valid = compute_goal_score(factors, goals)
        assert valid is True

    def test_just_below_threshold_fails(self):
        factors = {"psyke_consistency": 0.59, "structure_fit": 0.5,
                   "tension_gain": 0.5, "novelty": 0.5, "goal_alignment": 0.5}
        goals = QuantumGoals(min_constraints={"psyke_consistency": 0.6})
        _, valid = compute_goal_score(factors, goals)
        assert valid is False


# ---------------------------------------------------------------------------
# GOAL_FACTOR_MAP correctness
# ---------------------------------------------------------------------------


class TestGoalFactorMap:
    def test_all_objectives_mapped(self):
        from logosforge.quantum_outliner.scoring import _GOAL_OBJECTIVE_KEYS
        for key in _GOAL_OBJECTIVE_KEYS:
            assert key in GOAL_FACTOR_MAP

    def test_all_mapped_factors_are_valid(self):
        from logosforge.quantum_outliner.scoring import PARETO_OBJECTIVES
        for factor in GOAL_FACTOR_MAP.values():
            assert factor in PARETO_OBJECTIVES


# ---------------------------------------------------------------------------
# Different goals → different ranking
# ---------------------------------------------------------------------------


class TestGoalsChangeRanking:
    def test_tension_goals_rank_tense_higher(self):
        wf = Wavefunction.new(anchor="ranking test")
        wf.branches = [
            _branch("calm", "Calm path", desc="a peaceful quiet stroll"),
            _branch("tense", "Tense path",
                    desc="sudden fight danger risk must conflict war",
                    stakes="desperate sacrifice",
                    consequence="destruction threat"),
        ]
        tension_goals = QuantumGoals(objectives={
            "tension": 0.8, "consistency": 0.05, "novelty": 0.05,
            "structure": 0.05, "character_focus": 0.05,
        }).validate()

        scored = score_branches(wf, goals=tension_goals)
        by_id = {s.branch_id: s for s in scored}
        assert by_id["tense"].goal_score > by_id["calm"].goal_score

    def test_consistency_goals_rank_consistent_higher(self):
        wf = Wavefunction.new(anchor="consistency test")
        wf.branches = [
            _branch("novel", "Wild card",
                    desc="bizarre unexpected twist never seen before"),
            _branch("stable", "Steady path",
                    desc="follows established patterns naturally"),
        ]
        consistency_goals = QuantumGoals(objectives={
            "tension": 0.05, "consistency": 0.8, "novelty": 0.05,
            "structure": 0.05, "character_focus": 0.05,
        }).validate()

        scored = score_branches(wf, goals=consistency_goals)
        by_id = {s.branch_id: s for s in scored}
        assert by_id["stable"].goal_score >= by_id["novel"].goal_score

    def test_balanced_vs_skewed_produces_different_scores(self):
        wf = Wavefunction.new(anchor="compare goals")
        wf.branches = [
            _branch("a", "Mixed",
                    desc="sudden fight danger risk with quiet resolution",
                    stakes="moderate",
                    consequence="change"),
        ]
        balanced = QuantumGoals()
        skewed = QuantumGoals(objectives={
            "tension": 0.9, "consistency": 0.025, "novelty": 0.025,
            "structure": 0.025, "character_focus": 0.025,
        }).validate()

        scored_balanced = score_branches(wf, goals=balanced)
        scored_skewed = score_branches(wf, goals=skewed)

        assert scored_balanced[0].goal_score != scored_skewed[0].goal_score

    def test_without_goals_defaults_zero(self):
        wf = Wavefunction.new(anchor="no goals")
        wf.branches = [_branch("a", "A", desc="something")]
        scored = score_branches(wf)
        assert scored[0].goal_score == 0.0
        assert scored[0].goal_valid is True


# ---------------------------------------------------------------------------
# Goal constraints filter options
# ---------------------------------------------------------------------------


class TestGoalConstraintsFilter:
    def test_min_constraint_invalidates_branch(self):
        wf = Wavefunction.new(anchor="filter test")
        wf.branches = [
            _branch("high", "High consistency",
                    desc="follows established patterns carefully"),
            _branch("low", "Low consistency",
                    desc="sudden fight danger risk bizarre unexpected"),
        ]
        goals = QuantumGoals(min_constraints={"psyke_consistency": 0.7})
        scored = score_branches(wf, goals=goals)
        by_id = {s.branch_id: s for s in scored}
        low_valid = by_id["low"].goal_valid
        high_valid = by_id["high"].goal_valid
        assert not low_valid or high_valid
        invalid_count = sum(1 for s in scored if not s.goal_valid)
        assert invalid_count >= 1

    def test_strict_constraint_invalidates_most(self):
        wf = Wavefunction.new(anchor="strict")
        wf.branches = [
            _branch("a", "A", desc="a quiet stroll"),
            _branch("b", "B", desc="another quiet stroll"),
            _branch("c", "C", desc="yet another stroll"),
        ]
        goals = QuantumGoals(min_constraints={"tension_gain": 0.9})
        scored = score_branches(wf, goals=goals)
        invalid = [s for s in scored if not s.goal_valid]
        assert len(invalid) == 3

    def test_no_constraint_all_valid(self):
        wf = Wavefunction.new(anchor="none")
        wf.branches = [
            _branch("a", "A", desc="x"),
            _branch("b", "B", desc="y"),
        ]
        goals = QuantumGoals(min_constraints={})
        scored = score_branches(wf, goals=goals)
        assert all(s.goal_valid for s in scored)

    def test_goal_invalid_gets_zero_goal_score(self):
        wf = Wavefunction.new(anchor="zero")
        wf.branches = [
            _branch("a", "Calm", desc="a peaceful quiet day"),
        ]
        goals = QuantumGoals(min_constraints={"tension_gain": 0.9})
        scored = score_branches(wf, goals=goals)
        assert scored[0].goal_valid is False
        assert scored[0].goal_score == 0.0

    def test_goal_invalid_does_not_affect_regular_score(self):
        wf = Wavefunction.new(anchor="independent")
        wf.branches = [
            _branch("a", "Tense",
                    desc="sudden fight danger risk must conflict",
                    stakes="desperate",
                    consequence="war"),
        ]
        goals = QuantumGoals(min_constraints={"novelty": 0.99})
        scored = score_branches(wf, goals=goals)
        assert scored[0].goal_valid is False
        assert scored[0].score > 0.0
        assert scored[0].probability > 0.0


# ---------------------------------------------------------------------------
# apply_scores transfers goal fields
# ---------------------------------------------------------------------------


class TestApplyScoresGoalFields:
    def test_goal_fields_transferred_to_branch(self):
        wf = Wavefunction.new(anchor="apply")
        wf.branches = [
            _branch("a", "A",
                    desc="sudden fight danger risk must conflict",
                    stakes="desperate",
                    consequence="war"),
        ]
        goals = QuantumGoals(
            objectives={"tension": 0.8, "consistency": 0.05, "novelty": 0.05,
                        "structure": 0.05, "character_focus": 0.05},
            min_constraints={"tension_gain": 0.1},
        ).validate()
        scored = score_branches(wf, goals=goals)
        apply_scores(wf, scored)

        b = wf.branches[0]
        assert b.goal_score == scored[0].goal_score
        assert b.goal_valid == scored[0].goal_valid

    def test_goal_invalid_transferred(self):
        wf = Wavefunction.new(anchor="invalid transfer")
        wf.branches = [_branch("a", "A", desc="calm peaceful day")]
        goals = QuantumGoals(min_constraints={"tension_gain": 0.9})
        scored = score_branches(wf, goals=goals)
        apply_scores(wf, scored)
        assert wf.branches[0].goal_valid is False
        assert wf.branches[0].goal_score == 0.0

    def test_no_goals_defaults_preserved(self):
        wf = Wavefunction.new(anchor="defaults")
        wf.branches = [_branch("a", "A", desc="x")]
        scored = score_branches(wf)
        apply_scores(wf, scored)
        assert wf.branches[0].goal_score == 0.0
        assert wf.branches[0].goal_valid is True
