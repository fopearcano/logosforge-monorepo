"""Tests for goal-aware explain output."""

from __future__ import annotations

import pytest

from logosforge.quantum_outliner.scoring import (
    QuantumGoals,
    explain_goal_reasoning,
    explain_wavefunction,
    format_recommendation,
    goals_from_preset,
    recommend_collapse,
    score_branches,
    apply_scores,
)
from logosforge.quantum_outliner.state import Branch, Wavefunction


def _make_scored_wf(goals: QuantumGoals) -> Wavefunction:
    """Create a wavefunction with scored branches under given goals."""
    wf = Wavefunction.new(anchor="test")
    wf.branches = [
        Branch.new(
            title="Tension path",
            description="suddenly the hero must fight a desperate war danger fear",
            stakes="everything at risk of loss and pain",
            consequence="sacrifice demanded fear threat",
        ),
        Branch.new(
            title="Quiet moment",
            description="Alice reflects calmly on her situation",
            stakes="understanding",
            consequence="clarity",
        ),
    ]
    scored = score_branches(wf, goals=goals)
    apply_scores(wf, scored)
    wf.branches.sort(key=lambda b: b.probability, reverse=True)
    return wf


class TestExplainGoalReasoning:
    def test_high_tension_goal_shows_tension_alignment(self):
        goals = goals_from_preset("High Tension")
        wf = _make_scored_wf(goals)
        top = max(wf.branches, key=lambda b: b.probability)
        reasons = explain_goal_reasoning(top, goals)
        goal_lines = [r for r in reasons if "goal" in r.lower()]
        assert len(goal_lines) > 0
        assert any("tension" in r for r in goal_lines)

    def test_constraint_maintained_shown(self):
        goals = QuantumGoals(
            objectives={"tension": 0.4, "consistency": 0.15, "novelty": 0.15,
                        "structure": 0.15, "character_focus": 0.15},
            min_constraints={"tension_gain": 0.1},
            horizon=1,
        ).validate()
        wf = _make_scored_wf(goals)
        tension_branch = next(b for b in wf.branches if "Tension" in b.title)
        reasons = explain_goal_reasoning(tension_branch, goals)
        constraint_lines = [r for r in reasons if "≥" in r]
        assert len(constraint_lines) > 0

    def test_lookahead_shown_when_horizon_gt_1(self):
        goals = QuantumGoals(
            objectives={"tension": 0.4, "consistency": 0.15, "novelty": 0.15,
                        "structure": 0.15, "character_focus": 0.15},
            min_constraints={},
            horizon=2,
        ).validate()
        wf = _make_scored_wf(goals)
        top = max(wf.branches, key=lambda b: b.probability)
        reasons = explain_goal_reasoning(top, goals)
        lookahead_lines = [r for r in reasons if "lookahead" in r.lower()]
        assert len(lookahead_lines) > 0
        assert "2-step" in lookahead_lines[0]

    def test_no_lookahead_when_horizon_1(self):
        goals = goals_from_preset("Balanced")
        assert goals.horizon == 1
        wf = _make_scored_wf(goals)
        top = max(wf.branches, key=lambda b: b.probability)
        reasons = explain_goal_reasoning(top, goals)
        lookahead_lines = [r for r in reasons if "lookahead" in r.lower()]
        assert len(lookahead_lines) == 0

    def test_no_reasons_when_low_factors(self):
        goals = goals_from_preset("Balanced")
        branch = Branch.new(
            title="Bland",
            description="nothing happens",
            stakes="",
            consequence="",
        )
        branch.factors = {
            "tension_gain": 0.1,
            "psyke_consistency": 0.1,
            "novelty": 0.1,
            "structure_fit": 0.1,
            "goal_alignment": 0.1,
        }
        branch.lookahead_score = 0.0
        reasons = explain_goal_reasoning(branch, goals)
        assert not any("lookahead" in r for r in reasons)


class TestExplainWavefunctionWithGoals:
    def test_explain_includes_goal_lines(self):
        goals = goals_from_preset("High Tension")
        wf = _make_scored_wf(goals)
        output = explain_wavefunction(wf, goals=goals)
        assert "because:" in output
        assert "goal" in output.lower()

    def test_explain_without_goals_has_basic_format(self):
        wf = _make_scored_wf(goals_from_preset("Balanced"))
        output = explain_wavefunction(wf, goals=None)
        assert "because:" in output
        assert "goal" not in output.lower() or "goal_alignment" in output.lower()

    def test_explain_with_horizon_2_shows_lookahead(self):
        goals = QuantumGoals(
            objectives={"tension": 0.4, "consistency": 0.15, "novelty": 0.15,
                        "structure": 0.15, "character_focus": 0.15},
            min_constraints={},
            horizon=2,
        ).validate()
        wf = _make_scored_wf(goals)
        output = explain_wavefunction(wf, goals=goals)
        assert "lookahead" in output.lower()

    def test_explain_with_constraint_shows_maintains(self):
        goals = QuantumGoals(
            objectives={"tension": 0.4, "consistency": 0.15, "novelty": 0.15,
                        "structure": 0.15, "character_focus": 0.15},
            min_constraints={"tension_gain": 0.1},
            horizon=1,
        ).validate()
        wf = _make_scored_wf(goals)
        output = explain_wavefunction(wf, goals=goals)
        assert "≥" in output


class TestFormatRecommendationWithGoals:
    def test_recommendation_includes_goal_reasoning(self):
        goals = goals_from_preset("High Tension")
        wf = _make_scored_wf(goals)
        rec = recommend_collapse(wf)
        assert rec is not None
        branch = wf.get_branch(rec.branch_id)
        output = format_recommendation(rec, goals=goals, branch=branch)
        assert "Recommended:" in output
        assert "because:" in output
        lines = output.split("\n")
        bullet_lines = [l for l in lines if l.strip().startswith("- ")]
        assert len(bullet_lines) >= 1

    def test_recommendation_without_goals_still_works(self):
        wf = _make_scored_wf(goals_from_preset("Balanced"))
        rec = recommend_collapse(wf)
        assert rec is not None
        output = format_recommendation(rec)
        assert "Recommended:" in output
        assert "because:" in output

    def test_recommendation_shows_lookahead_for_horizon_2(self):
        goals = QuantumGoals(
            objectives={"tension": 0.4, "consistency": 0.15, "novelty": 0.15,
                        "structure": 0.15, "character_focus": 0.15},
            min_constraints={},
            horizon=2,
        ).validate()
        wf = _make_scored_wf(goals)
        rec = recommend_collapse(wf)
        assert rec is not None
        branch = wf.get_branch(rec.branch_id)
        output = format_recommendation(rec, goals=goals, branch=branch)
        assert "lookahead" in output.lower()

    def test_recommendation_shows_constraint(self):
        goals = QuantumGoals(
            objectives={"tension": 0.4, "consistency": 0.15, "novelty": 0.15,
                        "structure": 0.15, "character_focus": 0.15},
            min_constraints={"tension_gain": 0.1},
            horizon=1,
        ).validate()
        wf = _make_scored_wf(goals)
        rec = recommend_collapse(wf)
        assert rec is not None
        branch = wf.get_branch(rec.branch_id)
        output = format_recommendation(rec, goals=goals, branch=branch)
        assert "≥" in output
