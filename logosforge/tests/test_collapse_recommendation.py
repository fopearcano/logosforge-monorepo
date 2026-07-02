"""Tests for probability-based collapse recommendation.

Covers: picking highest probability, reason from top factors,
ties, PSYKE state changes, edge cases, and output integration.
"""

from unittest.mock import patch

import pytest

from logosforge.db import Database
from logosforge.quantum_outliner import (
    Branch,
    CollapseRecommendation,
    OutlineMode,
    Wavefunction,
    generate_branches,
    get_state,
    recommend_collapse,
)
from logosforge.quantum_outliner.core import _format_lambda, _format_wavefunction, _wf_summary
from logosforge.quantum_outliner.psyke_adapter import PsykeSignals
from logosforge.quantum_outliner.scoring import (
    apply_scores,
    score_branches,
)
from logosforge.quantum_outliner.state import StateDelta, _STATES
from logosforge.quantum_outliner.writing_methods_rag import reload as rag_reload


@pytest.fixture
def db(tmp_path):
    return Database(str(tmp_path / "test.db"))


@pytest.fixture
def project(db):
    return db.create_project("Recommendation Test")


@pytest.fixture(autouse=True)
def _reset():
    _STATES.clear()
    rag_reload()
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


def _scored_wf(branches, **kw):
    """Build wf, score it, return wf with probabilities applied."""
    wf = _wf(branches, **kw)
    scored = score_branches(wf, **{k: v for k, v in kw.items()
                                    if k in ("psyke", "protagonist_goal", "weights")})
    apply_scores(wf, scored)
    wf.branches.sort(key=lambda b: b.probability, reverse=True)
    return wf


class TestRecommendCollapse:
    def test_picks_highest_probability(self):
        wf = _wf([
            _branch("Low", probability=0.2, score=0.3,
                    factors={"tension_gain": 0.3, "novelty": 0.2,
                             "structure_fit": 0.1, "psyke_consistency": 0.1,
                             "goal_alignment": 0.1}),
            _branch("High", probability=0.8, score=0.9,
                    factors={"tension_gain": 0.9, "novelty": 0.8,
                             "structure_fit": 0.7, "psyke_consistency": 0.6,
                             "goal_alignment": 0.5}),
        ])
        rec = recommend_collapse(wf)
        assert rec is not None
        assert rec.title == "High"
        assert rec.probability == 0.8

    def test_returns_none_for_single_branch(self):
        wf = _wf([_branch("Solo", probability=1.0, score=0.5,
                           factors={"a": 0.5})])
        assert recommend_collapse(wf) is None

    def test_returns_none_for_empty(self):
        wf = _wf([])
        assert recommend_collapse(wf) is None

    def test_returns_none_for_unscored(self):
        wf = _wf([_branch("A"), _branch("B")])
        assert recommend_collapse(wf) is None

    def test_reason_uses_top_two_factors(self):
        wf = _wf([
            _branch("Winner", probability=0.6, score=0.8,
                    factors={"tension_gain": 0.9, "structure_fit": 0.7,
                             "novelty": 0.3, "psyke_consistency": 0.2,
                             "goal_alignment": 0.1}),
            _branch("Loser", probability=0.4, score=0.5,
                    factors={"tension_gain": 0.3, "structure_fit": 0.2,
                             "novelty": 0.5, "psyke_consistency": 0.4,
                             "goal_alignment": 0.3}),
        ])
        rec = recommend_collapse(wf)
        assert "tension" in rec.reason.lower()
        assert "structural" in rec.reason.lower() or "structure" in rec.reason.lower()

    def test_top_factors_are_sorted_desc(self):
        wf = _wf([
            _branch("A", probability=0.6, score=0.7,
                    factors={"tension_gain": 0.2, "novelty": 0.9,
                             "structure_fit": 0.5, "psyke_consistency": 0.1,
                             "goal_alignment": 0.3}),
            _branch("B", probability=0.4, score=0.5, factors={"a": 0.1}),
        ])
        rec = recommend_collapse(wf)
        assert rec.top_factors[0][1] >= rec.top_factors[1][1]

    def test_is_frozen_dataclass(self):
        wf = _wf([
            _branch("A", probability=0.6, score=0.7, factors={"x": 0.5}),
            _branch("B", probability=0.4, score=0.5, factors={"x": 0.3}),
        ])
        rec = recommend_collapse(wf)
        with pytest.raises(AttributeError):
            rec.title = "changed"


class TestTieHandling:
    def test_tie_mentions_runner_up(self):
        wf = _wf([
            _branch("Alpha", probability=0.5, score=0.6,
                    factors={"tension_gain": 0.8, "novelty": 0.5,
                             "structure_fit": 0.3, "psyke_consistency": 0.2,
                             "goal_alignment": 0.1}),
            _branch("Beta", probability=0.5, score=0.6,
                    factors={"tension_gain": 0.7, "novelty": 0.6,
                             "structure_fit": 0.4, "psyke_consistency": 0.3,
                             "goal_alignment": 0.2}),
        ])
        rec = recommend_collapse(wf)
        assert rec is not None
        assert "near-tie" in rec.reason.lower()
        assert "Beta" in rec.reason or "Alpha" in rec.reason

    def test_near_tie_threshold(self):
        wf = _wf([
            _branch("A", probability=0.504, score=0.6,
                    factors={"tension_gain": 0.8, "novelty": 0.5,
                             "structure_fit": 0.3, "psyke_consistency": 0.2,
                             "goal_alignment": 0.1}),
            _branch("B", probability=0.496, score=0.58,
                    factors={"tension_gain": 0.7, "novelty": 0.6,
                             "structure_fit": 0.4, "psyke_consistency": 0.3,
                             "goal_alignment": 0.2}),
        ])
        rec = recommend_collapse(wf)
        assert "near-tie" in rec.reason.lower()

    def test_clear_winner_no_tie_label(self):
        wf = _wf([
            _branch("Winner", probability=0.7, score=0.8,
                    factors={"tension_gain": 0.9, "novelty": 0.7,
                             "structure_fit": 0.5, "psyke_consistency": 0.3,
                             "goal_alignment": 0.2}),
            _branch("Loser", probability=0.3, score=0.4,
                    factors={"tension_gain": 0.3, "novelty": 0.4,
                             "structure_fit": 0.2, "psyke_consistency": 0.1,
                             "goal_alignment": 0.1}),
        ])
        rec = recommend_collapse(wf)
        assert "near-tie" not in rec.reason.lower()

    def test_three_way_tie(self):
        factors = {"tension_gain": 0.5, "novelty": 0.5,
                   "structure_fit": 0.3, "psyke_consistency": 0.2,
                   "goal_alignment": 0.1}
        wf = _wf([
            _branch("A", probability=0.334, score=0.5, factors=dict(factors)),
            _branch("B", probability=0.333, score=0.5, factors=dict(factors)),
            _branch("C", probability=0.333, score=0.5, factors=dict(factors)),
        ])
        rec = recommend_collapse(wf)
        assert rec is not None
        assert "near-tie" in rec.reason.lower()


class TestPsykeStateChangesRecommendation:
    def test_psyke_characters_shift_recommendation(self):
        """PSYKE state gives a relative advantage to the matching branch."""
        psyke = PsykeSignals(
            characters=[{"name": "Marcus"}],
            keywords=frozenset({"marcus", "warrior", "fight",
                                "danger", "sacrifice", "desperate", "alone"}),
            relations=[],
            unresolved_arcs=[{"name": "Marcus", "arc": "fight alone in danger"}],
        )

        wf_no = _wf([
            _branch(title="Marcus fight alone",
                    description="Marcus charges into danger sacrifice.",
                    stakes="sacrifice desperate", consequence="loss"),
            _branch(title="Peaceful negotiation",
                    description="Both sides talk calmly.",
                    stakes="time", consequence="a fragile truce"),
        ])
        scored_no = score_branches(wf_no)
        apply_scores(wf_no, scored_no)

        wf_with = _wf([
            _branch(title="Marcus fight alone",
                    description="Marcus charges into danger sacrifice.",
                    stakes="sacrifice desperate", consequence="loss"),
            _branch(title="Peaceful negotiation",
                    description="Both sides talk calmly.",
                    stakes="time", consequence="a fragile truce"),
        ])
        scored_with = score_branches(wf_with, psyke=psyke)
        apply_scores(wf_with, scored_with)

        marcus_with = next(b for b in wf_with.branches if "Marcus" in b.title)
        peaceful_with = next(b for b in wf_with.branches if "Peaceful" in b.title)
        assert marcus_with.factors["psyke_consistency"] > peaceful_with.factors["psyke_consistency"]

        marcus_no = next(b for b in wf_no.branches if "Marcus" in b.title)
        peaceful_no = next(b for b in wf_no.branches if "Peaceful" in b.title)
        assert marcus_no.factors["psyke_consistency"] == peaceful_no.factors["psyke_consistency"]

    def test_adding_psyke_relation_boosts_branch(self):
        b_related = _branch(
            title="Alice confronts Bob",
            description="Alice and Bob face each other.",
            stakes="trust", consequence="betrayal",
        )
        b_unrelated = _branch(
            title="Sunrise over mountains",
            description="Morning light spreads.",
        )

        psyke_no_rel = PsykeSignals(
            characters=[{"name": "Alice"}, {"name": "Bob"}],
            keywords=frozenset({"alice", "bob"}),
            relations=[],
            unresolved_arcs=[],
        )
        wf1 = _wf([b_related, b_unrelated])
        scored1 = score_branches(wf1, psyke=psyke_no_rel)
        apply_scores(wf1, scored1)
        score_no_rel = next(b for b in wf1.branches if "Alice" in b.title).factors["psyke_consistency"]

        b_related2 = _branch(
            title="Alice confronts Bob",
            description="Alice and Bob face each other.",
            stakes="trust", consequence="betrayal",
        )
        b_unrelated2 = _branch(
            title="Sunrise over mountains",
            description="Morning light spreads.",
        )
        psyke_with_rel = PsykeSignals(
            characters=[{"name": "Alice"}, {"name": "Bob"}],
            keywords=frozenset({"alice", "bob"}),
            relations=[{"from": "Alice", "to": "Bob"}],
            unresolved_arcs=[],
        )
        wf2 = _wf([b_related2, b_unrelated2])
        scored2 = score_branches(wf2, psyke=psyke_with_rel)
        apply_scores(wf2, scored2)
        score_with_rel = next(b for b in wf2.branches if "Alice" in b.title).factors["psyke_consistency"]

        assert score_with_rel > score_no_rel


class TestRecommendationInOutput:
    def test_format_lambda_shows_recommended(self):
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
        assert "Recommended: Fight" in body
        assert "60%" in body

    def test_format_lambda_no_recommendation_for_unscored(self):
        b1 = _branch("A")
        b2 = _branch("B")
        wf = _wf([b1, b2])
        body = _format_lambda(wf)
        assert "Recommended:" not in body

    def test_format_lambda_no_recommendation_for_single(self):
        b = _branch("Solo", probability=1.0, score=0.5,
                     factors={"x": 0.5})
        wf = _wf([b])
        body = _format_lambda(wf)
        assert "Recommended:" not in body

    def test_format_wavefunction_includes_recommendation(self):
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
        assert "Recommended:" in result.body

    def test_payload_has_recommendation(self):
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
        result = _format_wavefunction("Test", wf)
        rec = result.payload["recommendation"]
        assert rec is not None
        assert "branch_id" in rec
        assert "title" in rec
        assert "probability" in rec
        assert "reason" in rec
        assert "top_factors" in rec

    def test_payload_recommendation_none_for_single(self):
        b = Branch.new(title="Solo", description="only one")
        wf = Wavefunction.new(anchor="Test", branches=[b])
        result = _format_wavefunction("Test", wf)
        assert result.payload["recommendation"] is None


class TestEndToEnd:
    def test_generated_output_has_recommendation(self, db, project):
        state = get_state(project.id)
        state.outline_mode = OutlineMode.LAMBDA

        with patch(
            "logosforge.quantum_outliner.possibilities.chat_completion",
            side_effect=ConnectionError("offline"),
        ):
            result = generate_branches(db, project.id, "Hero meets enemy")

        assert "Recommended:" in result.body
        assert result.payload["recommendation"] is not None
        assert result.payload["recommendation"]["probability"] > 0

    def test_classical_mode_no_recommendation(self, db, project):
        state = get_state(project.id)
        state.outline_mode = OutlineMode.CLASSICAL

        result = generate_branches(db, project.id, "Save the Cat midpoint")
        assert "Recommended:" not in result.body

    def test_recommendation_does_not_auto_collapse(self, db, project):
        state = get_state(project.id)
        state.outline_mode = OutlineMode.LAMBDA

        with patch(
            "logosforge.quantum_outliner.possibilities.chat_completion",
            side_effect=ConnectionError("offline"),
        ):
            result = generate_branches(db, project.id, "Hero meets enemy")

        wf_id = result.payload["wavefunction_id"]
        wf = state.get(wf_id)
        assert not wf.is_collapsed()
        assert wf.collapsed_branch_id is None
