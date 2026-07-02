"""Tests for multi-objective Pareto front scoring."""

import pytest

from logosforge.quantum_outliner.scoring import (
    ScoredBranch,
    _dominates,
    compute_pareto_front,
    score_branches,
    apply_scores,
)
from logosforge.quantum_outliner.state import Branch, Wavefunction


def _sb(bid, **factors):
    """Helper to create a ScoredBranch with given factor values."""
    f = {
        "structure_fit": 0.0,
        "psyke_consistency": 0.0,
        "tension_gain": 0.0,
        "novelty": 0.0,
        "goal_alignment": 0.0,
    }
    f.update(factors)
    return ScoredBranch(
        branch_id=bid,
        score=sum(f.values()) / len(f),
        probability=0.0,
        factors=f,
    )


# ---------------------------------------------------------------------------
# _dominates helper
# ---------------------------------------------------------------------------


class TestDominates:
    def test_strictly_better_on_all(self):
        a = {"structure_fit": 0.9, "psyke_consistency": 0.8,
             "tension_gain": 0.7, "novelty": 0.6, "goal_alignment": 0.5}
        b = {"structure_fit": 0.1, "psyke_consistency": 0.1,
             "tension_gain": 0.1, "novelty": 0.1, "goal_alignment": 0.1}
        assert _dominates(a, b) is True

    def test_equal_on_all_does_not_dominate(self):
        a = {"structure_fit": 0.5, "psyke_consistency": 0.5,
             "tension_gain": 0.5, "novelty": 0.5, "goal_alignment": 0.5}
        assert _dominates(a, a) is False

    def test_better_on_some_worse_on_one(self):
        a = {"structure_fit": 0.9, "psyke_consistency": 0.9,
             "tension_gain": 0.9, "novelty": 0.9, "goal_alignment": 0.1}
        b = {"structure_fit": 0.5, "psyke_consistency": 0.5,
             "tension_gain": 0.5, "novelty": 0.5, "goal_alignment": 0.5}
        assert _dominates(a, b) is False

    def test_ge_all_gt_one(self):
        a = {"structure_fit": 0.5, "psyke_consistency": 0.5,
             "tension_gain": 0.5, "novelty": 0.5, "goal_alignment": 0.6}
        b = {"structure_fit": 0.5, "psyke_consistency": 0.5,
             "tension_gain": 0.5, "novelty": 0.5, "goal_alignment": 0.5}
        assert _dominates(a, b) is True


# ---------------------------------------------------------------------------
# compute_pareto_front — unit-level
# ---------------------------------------------------------------------------


class TestComputeParetoFront:
    def test_single_branch_is_pareto_optimal(self):
        branches = [_sb("a", structure_fit=0.5, tension_gain=0.5)]
        assert compute_pareto_front(branches) == ["a"]

    def test_dominated_branch_excluded(self):
        a = _sb("a", structure_fit=0.9, psyke_consistency=0.9,
                tension_gain=0.9, novelty=0.9, goal_alignment=0.9)
        b = _sb("b", structure_fit=0.1, psyke_consistency=0.1,
                tension_gain=0.1, novelty=0.1, goal_alignment=0.1)
        front = compute_pareto_front([a, b])
        assert front == ["a"]
        assert "b" not in front

    def test_multiple_pareto_optimal(self):
        a = _sb("a", structure_fit=0.9, tension_gain=0.1)
        b = _sb("b", structure_fit=0.1, tension_gain=0.9)
        front = compute_pareto_front([a, b])
        assert sorted(front) == ["a", "b"]

    def test_three_branches_one_dominated(self):
        a = _sb("a", structure_fit=0.9, tension_gain=0.3, novelty=0.5)
        b = _sb("b", structure_fit=0.3, tension_gain=0.9, novelty=0.5)
        c = _sb("c", structure_fit=0.2, tension_gain=0.2, novelty=0.4)
        front = compute_pareto_front([a, b, c])
        assert sorted(front) == ["a", "b"]

    def test_all_equal_all_pareto(self):
        a = _sb("a", structure_fit=0.5, tension_gain=0.5, novelty=0.5)
        b = _sb("b", structure_fit=0.5, tension_gain=0.5, novelty=0.5)
        front = compute_pareto_front([a, b])
        assert sorted(front) == ["a", "b"]

    def test_empty_input(self):
        assert compute_pareto_front([]) == []

    def test_violated_branch_excluded_from_front(self):
        a = _sb("a", structure_fit=0.9, tension_gain=0.9)
        b = ScoredBranch(
            branch_id="b", score=0.0, probability=0.0,
            factors={"structure_fit": 1.0, "psyke_consistency": 1.0,
                     "tension_gain": 1.0, "novelty": 1.0, "goal_alignment": 1.0},
            violations=["No betrayal"],
        )
        front = compute_pareto_front([a, b])
        assert front == ["a"]

    def test_five_way_tradeoff(self):
        branches = [
            _sb("a", structure_fit=1.0),
            _sb("b", psyke_consistency=1.0),
            _sb("c", tension_gain=1.0),
            _sb("d", novelty=1.0),
            _sb("e", goal_alignment=1.0),
        ]
        front = compute_pareto_front(branches)
        assert sorted(front) == ["a", "b", "c", "d", "e"]

    def test_chain_domination(self):
        a = _sb("a", structure_fit=0.9, psyke_consistency=0.9,
                tension_gain=0.9, novelty=0.9, goal_alignment=0.9)
        b = _sb("b", structure_fit=0.5, psyke_consistency=0.5,
                tension_gain=0.5, novelty=0.5, goal_alignment=0.5)
        c = _sb("c", structure_fit=0.1, psyke_consistency=0.1,
                tension_gain=0.1, novelty=0.1, goal_alignment=0.1)
        front = compute_pareto_front([a, b, c])
        assert front == ["a"]


# ---------------------------------------------------------------------------
# Integration with score_branches
# ---------------------------------------------------------------------------


def _branch(bid, title, desc="desc", stakes="stakes", consequence="consequence",
            branch_type="alternative"):
    return Branch(
        id=bid, title=title, description=desc,
        stakes=stakes, consequence=consequence,
        branch_type=branch_type,
    )


class TestParetoInScoreBranches:
    def test_score_branches_marks_pareto(self):
        wf = Wavefunction.new(anchor="test")
        wf.branches = [
            _branch("a", "High tension fight",
                    desc="sudden fight danger risk must conflict",
                    stakes="desperate sacrifice",
                    consequence="war threat"),
            _branch("b", "Higher tension fight danger",
                    desc="sudden fight danger risk must conflict war",
                    stakes="desperate sacrifice threat",
                    consequence="war threat fear"),
        ]
        scored = score_branches(wf)
        pareto_ids = [s.branch_id for s in scored if s.is_pareto_optimal]
        assert len(pareto_ids) >= 1

    def test_violated_branch_not_pareto(self):
        wf = Wavefunction.new(anchor="test")
        wf.branches = [
            _branch("a", "Safe path", desc="a safe journey"),
            _branch("b", "Betrayal path", desc="betrayal and lies"),
        ]
        scored = score_branches(wf, constraints=["No betrayal"])
        by_id = {s.branch_id: s for s in scored}
        assert by_id["b"].is_pareto_optimal is False
        assert by_id["b"].violations == ["No betrayal"]

    def test_apply_scores_transfers_pareto_flag(self):
        wf = Wavefunction.new(anchor="test")
        wf.branches = [
            _branch("a", "Alpha", desc="sudden fight danger risk conflict"),
            _branch("b", "Beta", desc="calm peaceful stroll"),
        ]
        scored = score_branches(wf)
        apply_scores(wf, scored)
        by_id = {b.id: b for b in wf.branches}
        pareto_count = sum(1 for b in wf.branches if b.is_pareto_optimal)
        assert pareto_count >= 1
        for b in wf.branches:
            s = {s.branch_id: s for s in scored}[b.id]
            assert b.is_pareto_optimal == s.is_pareto_optimal


class TestParetoPreservesExistingScoring:
    def test_single_score_ranking_unchanged(self):
        wf = Wavefunction.new(anchor="test")
        wf.branches = [
            _branch("a", "Strong", desc="sudden fight danger must risk",
                    stakes="desperate conflict", consequence="war threat sacrifice"),
            _branch("b", "Weak", desc="a quiet afternoon walk"),
        ]
        scored = score_branches(wf)
        assert scored[0].score >= scored[1].score

    def test_probabilities_still_sum_to_one(self):
        wf = Wavefunction.new(anchor="test")
        wf.branches = [
            _branch("a", "One", desc="sudden fight"),
            _branch("b", "Two", desc="calm walk"),
            _branch("c", "Three", desc="danger risk"),
        ]
        scored = score_branches(wf)
        total = sum(s.probability for s in scored)
        assert abs(total - 1.0) < 0.01
