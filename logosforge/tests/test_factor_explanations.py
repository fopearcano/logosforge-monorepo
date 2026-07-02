"""Tests for factor-based explanations.

Covers:
- explain_factors returns top 2 factors with qualitative descriptors
- format_recommendation produces the required format
- explain_wavefunction covers all scored branches
- Inline recommendation uses the "because:" format
- Explanation reflects actual computed factors
- explain_branches public API
"""

import pytest

from logosforge.db import Database
from logosforge.quantum_outliner import (
    Branch,
    CollapseRecommendation,
    Wavefunction,
    explain_branches,
    explain_factors,
    explain_wavefunction,
    format_recommendation,
    recommend_collapse,
)
from logosforge.quantum_outliner.core import (
    _format_lambda,
    _format_wavefunction,
)
from logosforge.quantum_outliner.scoring import (
    apply_scores,
    score_branches,
)
from logosforge.quantum_outliner.state import _STATES


@pytest.fixture
def db(tmp_path):
    return Database(str(tmp_path / "test.db"))


@pytest.fixture
def project(db):
    return db.create_project("Explain Test")


@pytest.fixture(autouse=True)
def _reset():
    _STATES.clear()
    yield
    _STATES.clear()


def _branch(title="Test", probability=0.0, score=0.0, factors=None, **kw):
    return Branch.new(
        title=title, description=kw.pop("description", f"Desc for {title}"),
        score=score, probability=probability,
        factors=factors or {}, **kw,
    )


def _wf(branches, **kw):
    wf = Wavefunction.new(anchor="Test", branches=branches)
    for k, v in kw.items():
        setattr(wf, k, v)
    return wf


# ---------------------------------------------------------------------------
# explain_factors
# ---------------------------------------------------------------------------


class TestExplainFactors:
    def test_shows_top_two(self):
        factors = {
            "tension_gain": 0.9,
            "structure_fit": 0.7,
            "novelty": 0.3,
            "psyke_consistency": 0.2,
            "goal_alignment": 0.1,
        }
        result = explain_factors(factors)
        assert "tension_gain" in result
        assert "structure_fit" in result
        assert "novelty" not in result

    def test_uses_high_descriptor(self):
        result = explain_factors({"tension_gain": 0.9, "novelty": 0.1})
        assert "high tension_gain" in result

    def test_uses_strong_descriptor(self):
        result = explain_factors({"novelty": 0.5, "tension_gain": 0.1})
        assert "strong novelty" in result

    def test_uses_moderate_descriptor(self):
        result = explain_factors({"structure_fit": 0.3, "tension_gain": 0.1})
        assert "moderate structure_fit" in result

    def test_uses_some_descriptor(self):
        result = explain_factors({"goal_alignment": 0.15, "tension_gain": 0.01})
        assert "some goal_alignment" in result

    def test_joined_with_plus(self):
        factors = {"tension_gain": 0.9, "novelty": 0.5, "structure_fit": 0.3}
        result = explain_factors(factors)
        assert " + " in result

    def test_accepts_list_of_tuples(self):
        items = [("tension_gain", 0.9), ("novelty", 0.7)]
        result = explain_factors(items)
        assert "tension_gain" in result
        assert "novelty" in result

    def test_custom_top_n(self):
        factors = {
            "tension_gain": 0.9,
            "structure_fit": 0.7,
            "novelty": 0.5,
        }
        result = explain_factors(factors, top_n=3)
        assert "tension_gain" in result
        assert "structure_fit" in result
        assert "novelty" in result

    def test_empty_factors_fallback(self):
        result = explain_factors({})
        assert "balanced" in result.lower()

    def test_zero_values_excluded(self):
        result = explain_factors({"tension_gain": 0.0, "novelty": 0.0})
        assert "balanced" in result.lower()


# ---------------------------------------------------------------------------
# format_recommendation
# ---------------------------------------------------------------------------


class TestFormatRecommendation:
    def test_includes_title_and_probability(self):
        rec = CollapseRecommendation(
            branch_id="abc",
            title="Fight",
            probability=0.42,
            reason="raises narrative tension",
            top_factors=[("tension_gain", 0.9), ("novelty", 0.7)],
        )
        result = format_recommendation(rec)
        assert "Recommended: Fight" in result
        assert "42%" in result

    def test_includes_because(self):
        rec = CollapseRecommendation(
            branch_id="abc",
            title="Fight",
            probability=0.6,
            reason="raises narrative tension",
            top_factors=[("tension_gain", 0.9), ("novelty", 0.7)],
        )
        result = format_recommendation(rec)
        assert "because:" in result

    def test_shows_factor_names(self):
        rec = CollapseRecommendation(
            branch_id="abc",
            title="Fight",
            probability=0.6,
            reason="raises narrative tension",
            top_factors=[("tension_gain", 0.9), ("structure_fit", 0.7)],
        )
        result = format_recommendation(rec)
        assert "tension_gain" in result
        assert "structure_fit" in result

    def test_explain_method_same_as_function(self):
        rec = CollapseRecommendation(
            branch_id="abc",
            title="Fight",
            probability=0.6,
            reason="raises narrative tension",
            top_factors=[("tension_gain", 0.9), ("novelty", 0.7)],
        )
        assert rec.explain() == format_recommendation(rec)


# ---------------------------------------------------------------------------
# explain_wavefunction
# ---------------------------------------------------------------------------


class TestExplainWavefunction:
    def test_covers_all_scored_branches(self):
        b1 = _branch("Fight", probability=0.6, score=0.8,
                      factors={"tension_gain": 0.9, "novelty": 0.7,
                               "structure_fit": 0.5, "psyke_consistency": 0.3,
                               "goal_alignment": 0.2})
        b2 = _branch("Retreat", probability=0.4, score=0.5,
                      factors={"tension_gain": 0.3, "novelty": 0.6,
                               "structure_fit": 0.2, "psyke_consistency": 0.1,
                               "goal_alignment": 0.1})
        wf = _wf([b1, b2])
        result = explain_wavefunction(wf)
        assert "Fight" in result
        assert "Retreat" in result

    def test_shows_because_for_each(self):
        b1 = _branch("A", probability=0.6, score=0.8,
                      factors={"tension_gain": 0.9, "novelty": 0.5})
        b2 = _branch("B", probability=0.4, score=0.5,
                      factors={"novelty": 0.8, "tension_gain": 0.3})
        wf = _wf([b1, b2])
        result = explain_wavefunction(wf)
        assert result.count("because:") == 2

    def test_sorted_by_probability(self):
        b1 = _branch("Low", probability=0.3, score=0.4,
                      factors={"novelty": 0.8})
        b2 = _branch("High", probability=0.7, score=0.8,
                      factors={"tension_gain": 0.9})
        wf = _wf([b1, b2])
        result = explain_wavefunction(wf)
        assert result.index("High") < result.index("Low")

    def test_unscored_returns_message(self):
        b1 = _branch("A")
        b2 = _branch("B")
        wf = _wf([b1, b2])
        result = explain_wavefunction(wf)
        assert "no scoring data" in result.lower()

    def test_shows_probabilities(self):
        b1 = _branch("Fight", probability=0.6, score=0.8,
                      factors={"tension_gain": 0.9})
        wf = _wf([b1])
        result = explain_wavefunction(wf)
        assert "60%" in result

    def test_shows_branch_ids(self):
        b1 = _branch("Fight", probability=0.6, score=0.8,
                      factors={"tension_gain": 0.9})
        wf = _wf([b1])
        result = explain_wavefunction(wf)
        assert b1.id in result


# ---------------------------------------------------------------------------
# Inline recommendation format
# ---------------------------------------------------------------------------


class TestInlineRecommendation:
    def test_format_lambda_uses_because(self):
        b1 = _branch("Fight", probability=0.6, score=0.8,
                      description="danger and war",
                      factors={"tension_gain": 0.9, "novelty": 0.7,
                               "structure_fit": 0.5, "psyke_consistency": 0.3,
                               "goal_alignment": 0.2})
        b2 = _branch("Retreat", probability=0.4, score=0.5,
                      factors={"tension_gain": 0.3, "novelty": 0.4,
                               "structure_fit": 0.2, "psyke_consistency": 0.1,
                               "goal_alignment": 0.1})
        wf = _wf([b1, b2])
        body = _format_lambda(wf)
        assert "because:" in body
        assert "Recommended: Fight" in body

    def test_format_lambda_shows_explain_hint(self):
        b1 = _branch("A", probability=0.6, score=0.8,
                      factors={"tension_gain": 0.9})
        b2 = _branch("B", probability=0.4, score=0.5,
                      factors={"tension_gain": 0.3})
        wf = _wf([b1, b2])
        body = _format_lambda(wf)
        assert "/quantum explain" in body

    def test_format_wavefunction_has_because(self):
        b1 = Branch.new(
            title="Sudden war",
            description="fight and danger threaten sacrifice",
            stakes="desperate loss", consequence="pain and fear",
        )
        b2 = Branch.new(
            title="Calm morning",
            description="peaceful walk in the park",
        )
        wf = Wavefunction.new(anchor="Test", branches=[b1, b2])
        result = _format_wavefunction("Test", wf)
        assert "because:" in result.body


# ---------------------------------------------------------------------------
# Explanation reflects actual factors (integration)
# ---------------------------------------------------------------------------


class TestExplanationReflectsFactors:
    def test_tension_branch_shows_tension_factor(self):
        b1 = Branch.new(
            title="War erupts",
            description="fight danger threat sacrifice desperate",
            stakes="desperate", consequence="loss and pain",
        )
        b2 = Branch.new(
            title="Calm morning",
            description="peaceful walk in the park",
        )
        wf = Wavefunction.new(anchor="Test", branches=[b1, b2])
        scored = score_branches(wf)
        apply_scores(wf, scored)

        rec = recommend_collapse(wf)
        explanation = format_recommendation(rec)
        assert "tension_gain" in explanation

    def test_structure_branch_shows_structure_factor(self):
        b1 = Branch.new(
            title="Midpoint reversal",
            description="Plan collapses at the midpoint.",
            structure_beat="Midpoint",
            structure_method="Save the Cat",
            branch_type="intensification",
        )
        b2 = Branch.new(
            title="Quiet aside",
            description="Nothing much happens.",
        )
        wf = Wavefunction.new(anchor="Test", branches=[b1, b2])
        wf.structure_beat = "Midpoint"
        wf.structure_method = "Save the Cat"
        scored = score_branches(wf)
        apply_scores(wf, scored)

        rec = recommend_collapse(wf)
        explanation = format_recommendation(rec)
        assert "structure_fit" in explanation

    def test_explain_wavefunction_reflects_actual_scores(self):
        b1 = Branch.new(
            title="War erupts",
            description="fight danger threat sacrifice desperate",
            stakes="desperate", consequence="loss and pain",
        )
        b2 = Branch.new(
            title="Calm morning",
            description="peaceful walk in the park",
        )
        wf = Wavefunction.new(anchor="Test", branches=[b1, b2])
        scored = score_branches(wf)
        apply_scores(wf, scored)

        result = explain_wavefunction(wf)
        assert "War erupts" in result
        assert "tension_gain" in result
        assert "because:" in result

    def test_full_pipeline_explanation(self, db, project):
        b1 = Branch.new(
            title="War erupts",
            description="fight danger threat sacrifice desperate",
            stakes="desperate", consequence="loss and pain",
        )
        b2 = Branch.new(
            title="Calm morning",
            description="peaceful walk in the park",
        )
        wf = Wavefunction.new(anchor="Test", branches=[b1, b2])
        result = _format_wavefunction("Test", wf, db=db, project_id=project.id)
        assert "because:" in result.body
        assert "Recommended:" in result.body

        rec = result.payload["recommendation"]
        assert rec is not None
        assert len(rec["top_factors"]) == 2


# ---------------------------------------------------------------------------
# explain_branches public API
# ---------------------------------------------------------------------------


class TestExplainBranchesAPI:
    def test_returns_explanation(self):
        from logosforge.quantum_outliner.state import get_state

        state = get_state(999)
        b1 = Branch.new(
            title="War erupts",
            description="fight danger threat sacrifice",
            stakes="desperate", consequence="loss",
        )
        b2 = Branch.new(
            title="Peace talks",
            description="calm negotiation",
        )
        wf = Wavefunction.new(anchor="Test", branches=[b1, b2])
        scored = score_branches(wf)
        apply_scores(wf, scored)
        state.add(wf)

        result = explain_branches(999, wf.id)
        assert result.kind == "explain"
        assert "War erupts" in result.body
        assert "because:" in result.body

    def test_missing_wavefunction(self):
        result = explain_branches(888, "nonexistent")
        assert "not found" in result.body.lower()
