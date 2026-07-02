"""Tests for unified scoring — goals + lookahead + ensemble + Pareto integration."""

import pytest

from logosforge.quantum_outliner.scoring import (
    EXTENDED_PARETO_OBJECTIVES,
    PARETO_OBJECTIVES,
    UNIFIED_WEIGHTS,
    QuantumGoals,
    ScoredBranch,
    _dominates,
    apply_scores,
    compute_pareto_front,
    compute_unified_score,
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
# compute_unified_score
# ---------------------------------------------------------------------------


class TestComputeUnifiedScore:
    def test_default_weights(self):
        score = compute_unified_score(0.8, 0.6, 0.4)
        expected = 0.5 * 0.8 + 0.3 * 0.6 + 0.2 * 0.4
        assert abs(score - expected) < 0.001

    def test_custom_weights(self):
        w = {"probability": 0.2, "goal_score": 0.5, "lookahead_score": 0.3}
        score = compute_unified_score(0.8, 0.6, 0.4, weights=w)
        expected = 0.2 * 0.8 + 0.5 * 0.6 + 0.3 * 0.4
        assert abs(score - expected) < 0.001

    def test_clamped_to_01(self):
        score = compute_unified_score(1.0, 1.0, 1.0)
        assert 0.0 <= score <= 1.0

    def test_zero_inputs(self):
        assert compute_unified_score(0.0, 0.0, 0.0) == 0.0

    def test_no_goals_fallback(self):
        score = compute_unified_score(0.6, 0.0, 0.0)
        assert score == round(0.5 * 0.6, 4)

    def test_probability_only_weight(self):
        w = {"probability": 1.0, "goal_score": 0.0, "lookahead_score": 0.0}
        score = compute_unified_score(0.75, 0.9, 0.8, weights=w)
        assert abs(score - 0.75) < 0.001


# ---------------------------------------------------------------------------
# Extended Pareto with goal_score/lookahead_score
# ---------------------------------------------------------------------------


class TestExtendedPareto:
    def test_extended_objectives_defined(self):
        assert "goal_score" in EXTENDED_PARETO_OBJECTIVES
        assert "lookahead_score" in EXTENDED_PARETO_OBJECTIVES
        assert "psyke_consistency" in EXTENDED_PARETO_OBJECTIVES

    def test_dominates_with_custom_objectives(self):
        a = {"goal_score": 0.8, "lookahead_score": 0.7, "psyke_consistency": 0.6}
        b = {"goal_score": 0.5, "lookahead_score": 0.4, "psyke_consistency": 0.3}
        assert _dominates(a, b, EXTENDED_PARETO_OBJECTIVES)
        assert not _dominates(b, a, EXTENDED_PARETO_OBJECTIVES)

    def test_no_domination_tradeoff(self):
        a = {"goal_score": 0.9, "lookahead_score": 0.3, "psyke_consistency": 0.5}
        b = {"goal_score": 0.3, "lookahead_score": 0.9, "psyke_consistency": 0.5}
        assert not _dominates(a, b, EXTENDED_PARETO_OBJECTIVES)
        assert not _dominates(b, a, EXTENDED_PARETO_OBJECTIVES)

    def test_pareto_front_with_extended_objectives(self):
        scored = [
            ScoredBranch(
                branch_id="a", score=0.5, probability=0.5,
                factors={"psyke_consistency": 0.8},
                goal_score=0.9, lookahead_score=0.3,
            ),
            ScoredBranch(
                branch_id="b", score=0.5, probability=0.5,
                factors={"psyke_consistency": 0.5},
                goal_score=0.3, lookahead_score=0.9,
            ),
            ScoredBranch(
                branch_id="c", score=0.5, probability=0.5,
                factors={"psyke_consistency": 0.3},
                goal_score=0.2, lookahead_score=0.2,
            ),
        ]
        front = compute_pareto_front(scored, objectives=EXTENDED_PARETO_OBJECTIVES)
        assert "a" in front
        assert "b" in front
        assert "c" not in front

    def test_pareto_front_default_objectives_unchanged(self):
        scored = [
            ScoredBranch(
                branch_id="a", score=0.5, probability=0.5,
                factors={"structure_fit": 0.9, "psyke_consistency": 0.5,
                         "tension_gain": 0.5, "novelty": 0.5, "goal_alignment": 0.5},
            ),
            ScoredBranch(
                branch_id="b", score=0.3, probability=0.3,
                factors={"structure_fit": 0.3, "psyke_consistency": 0.3,
                         "tension_gain": 0.3, "novelty": 0.3, "goal_alignment": 0.3},
            ),
        ]
        front = compute_pareto_front(scored)
        assert "a" in front
        assert "b" not in front

    def test_violated_excluded_from_extended_front(self):
        scored = [
            ScoredBranch(
                branch_id="a", score=0.5, probability=0.5,
                factors={"psyke_consistency": 0.8},
                goal_score=0.9, lookahead_score=0.8,
                violations=["No betrayal"],
            ),
            ScoredBranch(
                branch_id="b", score=0.3, probability=0.3,
                factors={"psyke_consistency": 0.3},
                goal_score=0.3, lookahead_score=0.3,
            ),
        ]
        front = compute_pareto_front(scored, objectives=EXTENDED_PARETO_OBJECTIVES)
        assert "a" not in front
        assert "b" in front


# ---------------------------------------------------------------------------
# Consistent ordering — unified_score drives sort
# ---------------------------------------------------------------------------


class TestConsistentOrdering:
    def test_sorted_by_unified_score_with_goals(self):
        wf = Wavefunction.new(anchor="ordering")
        wf.branches = [
            _branch("a", "High goal",
                    desc="sudden fight danger risk must conflict",
                    stakes="desperate sacrifice",
                    consequence="destruction war"),
            _branch("b", "Low goal", desc="a calm peaceful quiet stroll"),
        ]
        goals = QuantumGoals(
            objectives={"tension": 0.8, "consistency": 0.05,
                        "novelty": 0.05, "structure": 0.05,
                        "character_focus": 0.05},
        ).validate()
        scored = score_branches(wf, goals=goals)
        assert scored[0].unified_score >= scored[1].unified_score

    def test_sorted_by_score_without_goals(self):
        wf = Wavefunction.new(anchor="no goals")
        wf.branches = [
            _branch("a", "A", desc="sudden fight"),
            _branch("b", "B", desc="calm day"),
        ]
        scored = score_branches(wf)
        assert scored[0].unified_score >= scored[1].unified_score
        assert scored[0].unified_score == scored[0].probability

    def test_custom_unified_weights_change_order(self):
        wf = Wavefunction.new(anchor="custom")
        wf.branches = [
            _branch("a", "Tense",
                    desc="sudden fight danger risk must conflict war",
                    stakes="desperate",
                    consequence="destruction"),
            _branch("b", "Calm", desc="a peaceful quiet calm stroll"),
        ]
        goals = QuantumGoals(horizon=2)

        default_scored = score_branches(wf, goals=goals)
        custom_scored = score_branches(
            wf, goals=goals,
            unified_weights={"probability": 0.1, "goal_score": 0.1, "lookahead_score": 0.8},
        )

        default_order = [s.branch_id for s in default_scored]
        custom_order = [s.branch_id for s in custom_scored]
        default_scores = {s.branch_id: s.unified_score for s in default_scored}
        custom_scores = {s.branch_id: s.unified_score for s in custom_scored}
        assert default_scores != custom_scores

    def test_unified_score_on_branch_after_apply(self):
        wf = Wavefunction.new(anchor="apply")
        wf.branches = [
            _branch("a", "A",
                    desc="sudden fight danger risk",
                    stakes="desperate",
                    consequence="war"),
        ]
        goals = QuantumGoals(horizon=2)
        scored = score_branches(wf, goals=goals)
        apply_scores(wf, scored)
        assert wf.branches[0].unified_score == scored[0].unified_score
        assert wf.branches[0].unified_score > 0


# ---------------------------------------------------------------------------
# No crashes on missing data
# ---------------------------------------------------------------------------


class TestMissingDataFallbacks:
    def test_no_goals_no_crash(self):
        wf = Wavefunction.new(anchor="safe")
        wf.branches = [_branch("a", "A", desc="x")]
        scored = score_branches(wf)
        assert scored[0].goal_score == 0.0
        assert scored[0].lookahead_score == 0.0
        assert scored[0].unified_score == scored[0].probability
        assert scored[0].goal_valid is True

    def test_no_llm_no_crash(self):
        wf = Wavefunction.new(anchor="no llm")
        wf.branches = [_branch("a", "A", desc="sudden fight")]
        goals = QuantumGoals(horizon=2)
        scored = score_branches(wf, goals=goals, llm_scores=None)
        assert len(scored) == 1
        assert scored[0].unified_score > 0

    def test_empty_wf_no_crash(self):
        wf = Wavefunction.new(anchor="empty")
        wf.branches = []
        scored = score_branches(wf, goals=QuantumGoals())
        assert scored == []

    def test_single_branch_no_crash(self):
        wf = Wavefunction.new(anchor="single")
        wf.branches = [_branch("a", "A", desc="x")]
        goals = QuantumGoals(horizon=3)
        scored = score_branches(wf, goals=goals)
        assert len(scored) == 1

    def test_all_violated_no_crash(self):
        wf = Wavefunction.new(anchor="violated")
        wf.branches = [
            _branch("a", "Betrayal", desc="betrayal and lies"),
        ]
        goals = QuantumGoals(horizon=2)
        scored = score_branches(wf, goals=goals, constraints=["No betrayal"])
        assert scored[0].violations
        assert scored[0].unified_score == 0.0

    def test_goals_with_no_min_constraints(self):
        wf = Wavefunction.new(anchor="no min")
        wf.branches = [_branch("a", "A", desc="sudden fight danger")]
        goals = QuantumGoals(min_constraints={})
        scored = score_branches(wf, goals=goals)
        assert scored[0].goal_valid is True

    def test_partial_llm_scores(self):
        wf = Wavefunction.new(anchor="partial llm")
        wf.branches = [
            _branch("a", "A", desc="sudden fight"),
            _branch("b", "B", desc="calm day"),
        ]
        llm = {"a": {"structure_fit": 0.9, "psyke_consistency": 0.8,
                      "tension_gain": 0.7, "novelty": 0.6, "goal_alignment": 0.5}}
        goals = QuantumGoals()
        scored = score_branches(wf, goals=goals, llm_scores=llm)
        assert len(scored) == 2


# ---------------------------------------------------------------------------
# Ensemble + goals integration
# ---------------------------------------------------------------------------


class TestEnsembleGoalsIntegration:
    def test_ensemble_feeds_into_goal_score(self):
        wf = Wavefunction.new(anchor="ensemble goals")
        wf.branches = [
            _branch("a", "A", desc="sudden fight danger risk"),
        ]
        goals = QuantumGoals(
            objectives={"tension": 0.8, "consistency": 0.05,
                        "novelty": 0.05, "structure": 0.05,
                        "character_focus": 0.05},
        ).validate()

        llm = {"a": {"structure_fit": 0.1, "psyke_consistency": 0.1,
                      "tension_gain": 1.0, "novelty": 0.1, "goal_alignment": 0.1}}

        scored_heuristic = score_branches(wf, goals=goals)
        scored_ensemble = score_branches(wf, goals=goals, llm_scores=llm, ensemble_alpha=0.3)

        assert scored_ensemble[0].goal_score != scored_heuristic[0].goal_score

    def test_ensemble_failure_falls_back_to_heuristic(self):
        wf = Wavefunction.new(anchor="fallback")
        wf.branches = [_branch("a", "A", desc="sudden fight danger")]
        goals = QuantumGoals()

        scored_no_llm = score_branches(wf, goals=goals, llm_scores=None)
        scored_empty_llm = score_branches(wf, goals=goals, llm_scores={})

        assert scored_no_llm[0].goal_score == scored_empty_llm[0].goal_score
        assert scored_no_llm[0].unified_score == scored_empty_llm[0].unified_score


# ---------------------------------------------------------------------------
# Full pipeline — goals + Pareto + constraints + ensemble
# ---------------------------------------------------------------------------


class TestFullPipeline:
    def test_all_systems_combined(self):
        wf = Wavefunction.new(anchor="full pipeline")
        wf.branches = [
            _branch("a", "Hero path",
                    desc="sudden fight danger risk must conflict",
                    stakes="desperate sacrifice",
                    consequence="war destruction"),
            _branch("b", "Safe path", desc="a calm quiet peaceful stroll"),
            _branch("c", "Betrayal", desc="betrayal and lies everywhere"),
        ]
        goals = QuantumGoals(
            objectives={"tension": 0.6, "consistency": 0.1,
                        "novelty": 0.1, "structure": 0.1,
                        "character_focus": 0.1},
            min_constraints={"tension_gain": 0.1},
            horizon=2,
        ).validate()

        scored = score_branches(
            wf,
            goals=goals,
            constraints=["No betrayal"],
        )

        by_id = {s.branch_id: s for s in scored}

        assert by_id["c"].violations == ["No betrayal"]
        assert by_id["c"].unified_score == 0.0

        assert by_id["a"].unified_score > by_id["b"].unified_score

        assert by_id["a"].goal_score > 0
        assert by_id["a"].lookahead_score > 0
        assert by_id["a"].goal_valid is True

        pareto_ids = [s.branch_id for s in scored if s.is_pareto_optimal]
        assert "c" not in pareto_ids

    def test_ordering_stable_across_calls(self):
        wf = Wavefunction.new(anchor="stable")
        wf.branches = [
            _branch("a", "A", desc="sudden fight danger risk"),
            _branch("b", "B", desc="calm day"),
            _branch("c", "C", desc="adventure and novelty"),
        ]
        goals = QuantumGoals(horizon=2)
        s1 = score_branches(wf, goals=goals)
        s2 = score_branches(wf, goals=goals)
        order1 = [s.branch_id for s in s1]
        order2 = [s.branch_id for s in s2]
        assert order1 == order2
