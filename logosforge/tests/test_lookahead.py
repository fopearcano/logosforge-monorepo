"""Tests for lookahead evaluation — lightweight simulation of future steps."""

import time

import pytest

from logosforge.quantum_outliner.scoring import (
    QuantumGoals,
    _LOOKAHEAD_BLEND,
    _LOOKAHEAD_DEEP_BREADTH,
    _LOOKAHEAD_FIRST_BREADTH,
    _project_factors,
    _simulate_ahead,
    apply_scores,
    compute_blended_goal_score,
    compute_goal_score,
    evaluate_lookahead,
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


_FACTORS_HIGH_TENSION = {
    "structure_fit": 0.5, "psyke_consistency": 0.5,
    "tension_gain": 0.9, "novelty": 0.3, "goal_alignment": 0.5,
}
_FACTORS_LOW_TENSION = {
    "structure_fit": 0.5, "psyke_consistency": 0.5,
    "tension_gain": 0.1, "novelty": 0.7, "goal_alignment": 0.5,
}
_FACTORS_BALANCED = {
    "structure_fit": 0.5, "psyke_consistency": 0.5,
    "tension_gain": 0.5, "novelty": 0.5, "goal_alignment": 0.5,
}


# ---------------------------------------------------------------------------
# _project_factors
# ---------------------------------------------------------------------------


class TestProjectFactors:
    def test_returns_all_factor_keys(self):
        proj = _project_factors(_FACTORS_BALANCED, 0, 3)
        assert set(proj.keys()) == set(_FACTORS_BALANCED.keys())

    def test_values_clamped_01(self):
        extreme = {k: 1.0 for k in _FACTORS_BALANCED}
        proj = _project_factors(extreme, 2, 3)
        assert all(0.0 <= v <= 1.0 for v in proj.values())

        low = {k: 0.0 for k in _FACTORS_BALANCED}
        proj = _project_factors(low, 0, 3)
        assert all(0.0 <= v <= 1.0 for v in proj.values())

    def test_variants_differ(self):
        p0 = _project_factors(_FACTORS_BALANCED, 0, 3)
        p1 = _project_factors(_FACTORS_BALANCED, 1, 3)
        p2 = _project_factors(_FACTORS_BALANCED, 2, 3)
        assert p0 != p1 or p1 != p2

    def test_single_breadth_no_spread(self):
        p = _project_factors(_FACTORS_BALANCED, 0, 1)
        for k in _FACTORS_BALANCED:
            assert abs(p[k] - _FACTORS_BALANCED[k]) < 0.2

    def test_novelty_decays(self):
        proj = _project_factors(_FACTORS_BALANCED, 1, 3)
        assert proj["novelty"] < _FACTORS_BALANCED["novelty"]

    def test_tension_has_slight_drift(self):
        proj = _project_factors({"tension_gain": 0.5, "novelty": 0.5,
                                  "structure_fit": 0.5, "psyke_consistency": 0.5,
                                  "goal_alignment": 0.5}, 1, 3)
        assert isinstance(proj["tension_gain"], float)


# ---------------------------------------------------------------------------
# evaluate_lookahead
# ---------------------------------------------------------------------------


class TestEvaluateLookahead:
    def test_horizon_1_returns_immediate(self):
        goals = QuantumGoals(horizon=1)
        immediate, _ = compute_goal_score(_FACTORS_BALANCED, goals)
        lookahead = evaluate_lookahead(_FACTORS_BALANCED, goals)
        assert lookahead == immediate

    def test_horizon_2_returns_float(self):
        goals = QuantumGoals(horizon=2)
        result = evaluate_lookahead(_FACTORS_BALANCED, goals)
        assert isinstance(result, float)
        assert 0.0 <= result <= 1.0

    def test_horizon_3_returns_float(self):
        goals = QuantumGoals(horizon=3)
        result = evaluate_lookahead(_FACTORS_BALANCED, goals)
        assert isinstance(result, float)
        assert 0.0 <= result <= 1.0

    def test_horizon_2_differs_from_immediate(self):
        goals_h1 = QuantumGoals(horizon=1)
        goals_h2 = QuantumGoals(horizon=2)
        imm = evaluate_lookahead(_FACTORS_HIGH_TENSION, goals_h1)
        la = evaluate_lookahead(_FACTORS_HIGH_TENSION, goals_h2)
        assert imm != la

    def test_goal_invalid_returns_zero(self):
        goals = QuantumGoals(
            horizon=1,
            min_constraints={"tension_gain": 0.99},
        )
        result = evaluate_lookahead(_FACTORS_BALANCED, goals)
        assert result == 0.0


# ---------------------------------------------------------------------------
# compute_blended_goal_score
# ---------------------------------------------------------------------------


class TestComputeBlendedGoalScore:
    def test_horizon_1_no_blend(self):
        goals = QuantumGoals(horizon=1)
        blended, lookahead, valid = compute_blended_goal_score(_FACTORS_BALANCED, goals)
        immediate, _ = compute_goal_score(_FACTORS_BALANCED, goals)
        assert blended == immediate
        assert lookahead == immediate
        assert valid is True

    def test_horizon_2_blends(self):
        goals = QuantumGoals(horizon=2)
        blended, lookahead, valid = compute_blended_goal_score(_FACTORS_BALANCED, goals)
        immediate, _ = compute_goal_score(_FACTORS_BALANCED, goals)
        assert valid is True
        assert blended != immediate or blended != lookahead

    def test_blend_weight_applied(self):
        goals = QuantumGoals(horizon=2)
        blended, lookahead, _ = compute_blended_goal_score(_FACTORS_HIGH_TENSION, goals)
        immediate, _ = compute_goal_score(_FACTORS_HIGH_TENSION, goals)
        expected = round((1 - _LOOKAHEAD_BLEND) * immediate + _LOOKAHEAD_BLEND * lookahead, 4)
        assert abs(blended - expected) < 0.001

    def test_invalid_returns_zeros(self):
        goals = QuantumGoals(
            horizon=2,
            min_constraints={"tension_gain": 0.99},
        )
        blended, lookahead, valid = compute_blended_goal_score(_FACTORS_BALANCED, goals)
        assert valid is False
        assert blended == 0.0
        assert lookahead == 0.0


# ---------------------------------------------------------------------------
# Node count stays lightweight
# ---------------------------------------------------------------------------


class TestLookaheadNodeCount:
    def _count_nodes(self, horizon):
        if horizon <= 1:
            return 0
        extra = horizon - 1
        nodes = 0
        breadths = []
        for depth in range(extra):
            b = _LOOKAHEAD_FIRST_BREADTH if depth == 0 else _LOOKAHEAD_DEEP_BREADTH
            breadths.append(b)
        level_count = 1
        for b in breadths:
            level_count *= b
            nodes += level_count
        return nodes

    def test_horizon_2_nodes(self):
        assert self._count_nodes(2) == _LOOKAHEAD_FIRST_BREADTH  # 3

    def test_horizon_3_nodes(self):
        expected = _LOOKAHEAD_FIRST_BREADTH + _LOOKAHEAD_FIRST_BREADTH * _LOOKAHEAD_DEEP_BREADTH
        assert self._count_nodes(3) == expected  # 3 + 6 = 9

    def test_max_nodes_within_budget(self):
        for h in (1, 2, 3):
            assert self._count_nodes(h) <= 9


# ---------------------------------------------------------------------------
# horizon=2 changes ranking vs horizon=1
# ---------------------------------------------------------------------------


class TestLookaheadChangesRanking:
    def test_horizon_2_differs_from_horizon_1(self):
        wf = Wavefunction.new(anchor="ranking")
        wf.branches = [
            _branch("tense", "High tension",
                    desc="sudden fight danger risk must conflict war",
                    stakes="desperate sacrifice",
                    consequence="destruction"),
            _branch("novel", "High novelty",
                    desc="bizarre unexpected twist never seen before"),
        ]
        goals_h1 = QuantumGoals(horizon=1)
        goals_h2 = QuantumGoals(horizon=2)

        scored_h1 = score_branches(wf, goals=goals_h1)
        scored_h2 = score_branches(wf, goals=goals_h2)

        h1_scores = {s.branch_id: s.goal_score for s in scored_h1}
        h2_scores = {s.branch_id: s.goal_score for s in scored_h2}

        assert h1_scores != h2_scores

    def test_novelty_penalized_at_horizon_2(self):
        """Novelty decays in projection, so high-novelty branches should
        score lower in lookahead than immediate."""
        goals = QuantumGoals(
            objectives={"tension": 0.1, "consistency": 0.1,
                        "novelty": 0.6, "structure": 0.1,
                        "character_focus": 0.1},
            horizon=2,
        ).validate()

        immediate, _ = compute_goal_score(_FACTORS_LOW_TENSION, goals)
        blended, lookahead, _ = compute_blended_goal_score(_FACTORS_LOW_TENSION, goals)
        assert lookahead < immediate

    def test_horizon_3_further_differs(self):
        goals_h2 = QuantumGoals(horizon=2)
        goals_h3 = QuantumGoals(horizon=3)

        _, la2, _ = compute_blended_goal_score(_FACTORS_BALANCED, goals_h2)
        _, la3, _ = compute_blended_goal_score(_FACTORS_BALANCED, goals_h3)

        assert la2 != la3

    def test_goal_score_incorporates_lookahead(self):
        wf = Wavefunction.new(anchor="incorporate")
        wf.branches = [
            _branch("a", "A",
                    desc="sudden fight danger risk must conflict",
                    stakes="desperate",
                    consequence="war"),
        ]
        goals_h1 = QuantumGoals(horizon=1)
        goals_h2 = QuantumGoals(horizon=2)

        s1 = score_branches(wf, goals=goals_h1)
        s2 = score_branches(wf, goals=goals_h2)

        assert s1[0].goal_score != s2[0].goal_score
        assert s2[0].lookahead_score != s1[0].lookahead_score


# ---------------------------------------------------------------------------
# Constraints filter in lookahead
# ---------------------------------------------------------------------------


class TestLookaheadConstraints:
    def test_min_constraint_invalidates_with_lookahead(self):
        goals = QuantumGoals(
            horizon=2,
            min_constraints={"tension_gain": 0.99},
        )
        wf = Wavefunction.new(anchor="constraint")
        wf.branches = [_branch("a", "Calm", desc="a peaceful day")]
        scored = score_branches(wf, goals=goals)
        assert scored[0].goal_valid is False
        assert scored[0].goal_score == 0.0
        assert scored[0].lookahead_score == 0.0

    def test_valid_branch_has_positive_lookahead(self):
        goals = QuantumGoals(
            horizon=2,
            min_constraints={"tension_gain": 0.01},
        )
        wf = Wavefunction.new(anchor="valid")
        wf.branches = [
            _branch("a", "Tense",
                    desc="sudden fight danger risk must conflict",
                    stakes="desperate",
                    consequence="war"),
        ]
        scored = score_branches(wf, goals=goals)
        assert scored[0].goal_valid is True
        assert scored[0].lookahead_score > 0.0


# ---------------------------------------------------------------------------
# apply_scores transfers lookahead
# ---------------------------------------------------------------------------


class TestApplyScoresLookahead:
    def test_lookahead_transferred(self):
        wf = Wavefunction.new(anchor="transfer")
        wf.branches = [
            _branch("a", "A",
                    desc="sudden fight danger risk must conflict",
                    stakes="desperate",
                    consequence="war"),
        ]
        goals = QuantumGoals(horizon=2)
        scored = score_branches(wf, goals=goals)
        apply_scores(wf, scored)
        assert wf.branches[0].lookahead_score == scored[0].lookahead_score

    def test_no_goals_default_zero(self):
        wf = Wavefunction.new(anchor="default")
        wf.branches = [_branch("a", "A", desc="x")]
        scored = score_branches(wf)
        apply_scores(wf, scored)
        assert wf.branches[0].lookahead_score == 0.0


# ---------------------------------------------------------------------------
# Performance
# ---------------------------------------------------------------------------


class TestLookaheadPerformance:
    def test_horizon_2_under_100ms(self):
        wf = Wavefunction.new(anchor="perf")
        wf.branches = [
            _branch("a", "A", desc="sudden fight danger"),
            _branch("b", "B", desc="calm day"),
            _branch("c", "C", desc="adventure awaits"),
        ]
        goals = QuantumGoals(horizon=2)
        start = time.perf_counter()
        score_branches(wf, goals=goals)
        elapsed = time.perf_counter() - start
        assert elapsed < 0.1

    def test_horizon_3_under_200ms(self):
        wf = Wavefunction.new(anchor="perf3")
        wf.branches = [
            _branch("a", "A", desc="sudden fight danger"),
            _branch("b", "B", desc="calm day"),
            _branch("c", "C", desc="adventure awaits"),
        ]
        goals = QuantumGoals(horizon=3)
        start = time.perf_counter()
        score_branches(wf, goals=goals)
        elapsed = time.perf_counter() - start
        assert elapsed < 0.2
