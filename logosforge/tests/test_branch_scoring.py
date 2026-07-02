"""Tests for the branch scoring engine (scoring.py).

Covers deterministic ranking, factor computation, weight customization,
apply_scores write-back, and edge cases.
"""

import pytest

from logosforge.quantum_outliner.psyke_adapter import PsykeSignals
from logosforge.quantum_outliner.scoring import (
    DEFAULT_WEIGHTS,
    ScoredBranch,
    _softmax,
    apply_scores,
    compute_factors,
    compute_probabilities,
    score_branches,
)
from logosforge.quantum_outliner.state import (
    Branch,
    QuantumPossibility,
    StateDelta,
    Wavefunction,
)


def _make_branch(**kwargs) -> Branch:
    defaults = {"title": "Test", "description": "Desc"}
    defaults.update(kwargs)
    return Branch.new(**defaults)


def _make_wf(*branches, **kwargs) -> Wavefunction:
    return Wavefunction.new(anchor="Test", branches=list(branches), **kwargs)


class TestScoreBranches:
    def test_returns_sorted_high_to_low(self):
        high = _make_branch(
            title="War erupts suddenly",
            description="Fight and danger threaten all",
            stakes="sacrifice demanded",
            consequence="desperate loss",
        )
        low = _make_branch(title="Calm day", description="Nothing happens")
        wf = _make_wf(high, low)

        scored = score_branches(wf)
        assert len(scored) == 2
        assert scored[0].score >= scored[1].score

    def test_probabilities_sum_to_one(self):
        b1 = _make_branch(title="A conflict", description="fight and war")
        b2 = _make_branch(title="B peace", description="calm and serene")
        b3 = _make_branch(title="C secret", description="betray and lie")
        wf = _make_wf(b1, b2, b3)

        scored = score_branches(wf)
        total = sum(s.probability for s in scored)
        assert abs(total - 1.0) < 0.01

    def test_single_branch_gets_probability_one(self):
        b = _make_branch(title="Solo", description="only path")
        wf = _make_wf(b)

        scored = score_branches(wf)
        assert len(scored) == 1
        assert scored[0].probability == 1.0

    def test_scored_branch_ids_match_input(self):
        b1 = _make_branch(title="A", description="D")
        b2 = _make_branch(title="B", description="D")
        wf = _make_wf(b1, b2)

        scored = score_branches(wf)
        scored_ids = {s.branch_id for s in scored}
        assert scored_ids == {b1.id, b2.id}

    def test_scores_are_clamped_0_to_1(self):
        b = _make_branch(
            title="Extreme",
            description="fight war danger threat desperate sacrifice loss pain",
            stakes="must cannot refused demanded",
            consequence="conflict risk betray secret fear afraid",
        )
        wf = _make_wf(b)

        scored = score_branches(wf)
        assert 0.0 <= scored[0].score <= 1.0

    def test_deterministic_ranking(self):
        """Same inputs always produce the same ranking order."""
        tense = _make_branch(
            title="Betrayal revealed",
            description="She suddenly shouted the secret",
            stakes="fear and danger",
            consequence="sacrifice demanded",
        )
        calm = _make_branch(
            title="Morning walk",
            description="Birds singing in the park",
        )
        wf = _make_wf(tense, calm)

        results = [score_branches(wf) for _ in range(5)]
        first_order = [s.branch_id for s in results[0]]
        for r in results[1:]:
            assert [s.branch_id for s in r] == first_order

    def test_factors_visible_in_breakdown(self):
        b = _make_branch(
            title="Conflict rises",
            description="fight and danger",
        )
        wf = _make_wf(b)

        scored = score_branches(wf)
        factors = scored[0].factors
        assert set(factors.keys()) == {
            "structure_fit", "psyke_consistency", "tension_gain",
            "novelty", "goal_alignment",
        }
        for v in factors.values():
            assert 0.0 <= v <= 1.0


class TestCustomWeights:
    def test_custom_weights_change_ranking(self):
        tense = _make_branch(
            title="War fight danger",
            description="sacrifice and loss",
            stakes="desperate",
            consequence="pain",
        )
        novel = _make_branch(
            title="War",
            description="new path emerges",
        )
        wf = _make_wf(tense, novel)

        tension_heavy = {
            "structure_fit": 0.0,
            "psyke_consistency": 0.0,
            "tension_gain": 1.0,
            "novelty": 0.0,
            "goal_alignment": 0.0,
        }
        scored_tension = score_branches(wf, weights=tension_heavy)
        assert scored_tension[0].branch_id == tense.id

        novelty_heavy = {
            "structure_fit": 0.0,
            "psyke_consistency": 0.0,
            "tension_gain": 0.0,
            "novelty": 1.0,
            "goal_alignment": 0.0,
        }
        scored_novelty = score_branches(wf, weights=novelty_heavy)
        assert scored_novelty[0].branch_id == novel.id


class TestComputeFactors:
    def test_all_five_factors_present(self):
        b = _make_branch(title="Test", description="Desc")
        wf = _make_wf(b)
        factors = compute_factors(b, wf)
        assert set(factors.keys()) == {
            "structure_fit", "psyke_consistency", "tension_gain",
            "novelty", "goal_alignment",
        }

    def test_factor_values_in_range(self):
        b = _make_branch(title="Conflict", description="fight danger war")
        wf = _make_wf(b)
        factors = compute_factors(b, wf)
        for v in factors.values():
            assert 0.0 <= v <= 1.0


class TestStructureFit:
    def test_matching_beat_and_method(self):
        b = _make_branch(
            title="T", description="D",
            structure_beat="Midpoint",
            structure_method="Save the Cat",
            branch_type="intensification",
        )
        wf = _make_wf(b)
        wf.structure_beat = "Midpoint"
        wf.structure_method = "Save the Cat"

        factors = compute_factors(b, wf)
        assert factors["structure_fit"] == 1.0

    def test_no_structure_info(self):
        b = _make_branch(title="T", description="D")
        wf = _make_wf(b)
        factors = compute_factors(b, wf)
        assert factors["structure_fit"] == 0.0

    def test_partial_match_beat_only(self):
        b = _make_branch(
            title="T", description="D",
            structure_beat="Climax",
        )
        wf = _make_wf(b)
        wf.structure_beat = "Climax"
        factors = compute_factors(b, wf)
        assert factors["structure_fit"] == 0.5

    def test_branch_type_alternative(self):
        b = _make_branch(title="T", description="D", branch_type="alternative")
        wf = _make_wf(b)
        factors = compute_factors(b, wf)
        assert factors["structure_fit"] == 0.1

    def test_branch_type_resolution(self):
        b = _make_branch(title="T", description="D", branch_type="resolution")
        wf = _make_wf(b)
        factors = compute_factors(b, wf)
        assert factors["structure_fit"] == 0.1


class TestPsykeConsistency:
    def test_no_psyke_returns_neutral(self):
        b = _make_branch(title="T", description="D")
        wf = _make_wf(b)
        factors = compute_factors(b, wf, psyke=None)
        assert factors["psyke_consistency"] == 0.5

    def test_empty_keywords_returns_neutral(self):
        psyke = PsykeSignals(characters=[], keywords=frozenset())
        b = _make_branch(title="T", description="D")
        wf = _make_wf(b)
        factors = compute_factors(b, wf, psyke=psyke)
        assert factors["psyke_consistency"] == 0.5

    def test_character_name_hit(self):
        psyke = PsykeSignals(
            characters=[{"name": "Alice"}],
            keywords=frozenset({"alice", "brave"}),
        )
        b = _make_branch(title="Alice returns", description="She is back")
        wf = _make_wf(b)
        factors = compute_factors(b, wf, psyke=psyke)
        assert factors["psyke_consistency"] > 0.0

    def test_keyword_hits_increase_score(self):
        psyke = PsykeSignals(
            characters=[],
            keywords=frozenset({"dragon", "sword", "quest", "knight"}),
        )
        b_many = _make_branch(
            title="Dragon quest",
            description="sword and knight",
        )
        b_few = _make_branch(title="Rain day", description="nothing")
        wf = _make_wf(b_many, b_few)

        f_many = compute_factors(b_many, wf, psyke=psyke)
        f_few = compute_factors(b_few, wf, psyke=psyke)
        assert f_many["psyke_consistency"] > f_few["psyke_consistency"]

    def test_relation_hit(self):
        psyke = PsykeSignals(
            characters=[{"name": "Alice"}, {"name": "Bob"}],
            relations=[{"from": "Alice", "to": "Bob"}],
            keywords=frozenset({"alice", "bob"}),
        )
        b = _make_branch(title="Alice meets Bob", description="reunion")
        wf = _make_wf(b)
        factors = compute_factors(b, wf, psyke=psyke)
        assert factors["psyke_consistency"] > 0.0

    def test_unresolved_arc_hit(self):
        psyke = PsykeSignals(
            characters=[{"name": "Alice"}],
            unresolved_arcs=[{"name": "Alice", "arc": "find the lost crown"}],
            keywords=frozenset({"alice", "crown"}),
        )
        b = _make_branch(title="The crown appears", description="Alice finds crown")
        wf = _make_wf(b)
        factors = compute_factors(b, wf, psyke=psyke)
        assert factors["psyke_consistency"] > 0.0


class TestTensionGain:
    def test_no_tension_keywords(self):
        b = _make_branch(title="Calm", description="peaceful morning")
        wf = _make_wf(b)
        factors = compute_factors(b, wf)
        assert factors["tension_gain"] == 0.1

    def test_many_tension_keywords(self):
        b = _make_branch(
            title="T",
            description="fight danger war threat",
            stakes="desperate sacrifice",
            consequence="loss pain",
        )
        wf = _make_wf(b)
        factors = compute_factors(b, wf)
        assert factors["tension_gain"] > 0.5

    def test_tension_capped_at_one(self):
        all_keywords = " ".join([
            "but", "however", "suddenly", "fight", "argued", "shouted",
            "betray", "lie", "secret", "fear", "afraid", "danger",
            "must", "cannot", "refused", "demanded",
        ])
        b = _make_branch(title="T", description=all_keywords)
        wf = _make_wf(b)
        factors = compute_factors(b, wf)
        assert factors["tension_gain"] <= 1.0


class TestNovelty:
    def test_no_siblings_high_novelty(self):
        b = _make_branch(title="Unique path", description="novel")
        wf = _make_wf(b)
        factors = compute_factors(b, wf, sibling_titles=set())
        assert factors["novelty"] == 0.8

    def test_identical_sibling_low_novelty(self):
        b = _make_branch(title="same words here", description="same words here")
        wf = _make_wf(b)
        factors = compute_factors(b, wf, sibling_titles={"same words here"})
        assert factors["novelty"] < 0.3

    def test_different_sibling_high_novelty(self):
        b = _make_branch(title="Dragon quest", description="epic journey")
        wf = _make_wf(b)
        factors = compute_factors(b, wf, sibling_titles={"peaceful morning walk"})
        assert factors["novelty"] > 0.5


class TestGoalAlignment:
    def test_no_goal_returns_neutral(self):
        b = _make_branch(title="T", description="D")
        wf = _make_wf(b)
        factors = compute_factors(b, wf, protagonist_goal="")
        assert factors["goal_alignment"] == 0.5

    def test_goal_match(self):
        b = _make_branch(
            title="Find the treasure",
            description="dig for gold",
            consequence="treasure found",
        )
        wf = _make_wf(b)
        factors = compute_factors(b, wf, protagonist_goal="find the treasure")
        assert factors["goal_alignment"] > 0.5

    def test_no_goal_overlap(self):
        b = _make_branch(title="Morning walk", description="birds")
        wf = _make_wf(b)
        factors = compute_factors(b, wf, protagonist_goal="defeat the dragon")
        assert factors["goal_alignment"] == 0.0


class TestApplyScores:
    def test_writes_back_to_branches(self):
        b1 = _make_branch(title="A", description="fight danger")
        b2 = _make_branch(title="B", description="calm day")
        wf = _make_wf(b1, b2)

        scored = score_branches(wf)
        apply_scores(wf, scored)

        for b in wf.branches:
            assert b.score > 0.0 or b.score == 0.0
            assert isinstance(b.probability, float)
            assert isinstance(b.factors, dict)

    def test_probabilities_match_scoring(self):
        b1 = _make_branch(title="Fight war", description="danger threat")
        b2 = _make_branch(title="Peace calm", description="serene quiet")
        wf = _make_wf(b1, b2)

        scored = score_branches(wf)
        by_id = {s.branch_id: s for s in scored}
        apply_scores(wf, scored)

        for b in wf.branches:
            assert b.score == by_id[b.id].score
            assert b.probability == by_id[b.id].probability
            assert b.factors == by_id[b.id].factors

    def test_missing_branch_id_is_safe(self):
        b = _make_branch(title="A", description="D")
        wf = _make_wf(b)
        fake = ScoredBranch(
            branch_id="nonexistent",
            score=0.9,
            probability=1.0,
            factors={"x": 0.5},
        )
        apply_scores(wf, [fake])
        assert b.score == 0.0


class TestScoredBranchDataclass:
    def test_is_frozen(self):
        sb = ScoredBranch(
            branch_id="abc",
            score=0.5,
            probability=0.3,
            factors={"a": 0.1},
        )
        with pytest.raises(AttributeError):
            sb.score = 0.9

    def test_fields(self):
        sb = ScoredBranch(
            branch_id="abc",
            score=0.75,
            probability=0.42,
            factors={"tension": 0.6, "novelty": 0.15},
        )
        assert sb.branch_id == "abc"
        assert sb.score == 0.75
        assert sb.probability == 0.42
        assert sb.factors == {"tension": 0.6, "novelty": 0.15}


class TestDefaultWeights:
    def test_weights_sum_to_one(self):
        total = sum(DEFAULT_WEIGHTS.values())
        assert abs(total - 1.0) < 0.001

    def test_all_five_factors_have_weights(self):
        expected = {
            "structure_fit", "psyke_consistency", "tension_gain",
            "novelty", "goal_alignment",
        }
        assert set(DEFAULT_WEIGHTS.keys()) == expected


class TestQuantumPossibilityAlias:
    def test_alias_is_branch(self):
        assert QuantumPossibility is Branch

    def test_create_via_alias(self):
        p = QuantumPossibility.new(title="Path A", description="A choice")
        assert isinstance(p, Branch)
        assert p.score == 0.0
        assert p.probability == 0.0


class TestComputeProbabilities:
    def test_three_possibilities_sum_to_one(self):
        """Example: 3 possibilities with distinct scores → probabilities sum to 1."""
        p1 = _make_branch(title="High tension", description="D", score=0.8)
        p2 = _make_branch(title="Medium path", description="D", score=0.5)
        p3 = _make_branch(title="Low stakes", description="D", score=0.2)

        compute_probabilities([p1, p2, p3])

        total = p1.probability + p2.probability + p3.probability
        assert abs(total - 1.0) < 0.01
        assert p1.probability > p2.probability > p3.probability

    def test_equal_scores_equal_probability(self):
        p1 = _make_branch(title="A", description="D", score=0.5)
        p2 = _make_branch(title="B", description="D", score=0.5)
        p3 = _make_branch(title="C", description="D", score=0.5)

        compute_probabilities([p1, p2, p3])

        assert p1.probability == p2.probability == p3.probability
        total = p1.probability + p2.probability + p3.probability
        assert abs(total - 1.0) < 0.01

    def test_all_zero_scores_uniform(self):
        p1 = _make_branch(title="A", description="D", score=0.0)
        p2 = _make_branch(title="B", description="D", score=0.0)

        compute_probabilities([p1, p2])

        assert p1.probability == 0.5
        assert p2.probability == 0.5

    def test_empty_list_is_safe(self):
        compute_probabilities([])

    def test_single_possibility_gets_one(self):
        p = _make_branch(title="Solo", description="D", score=0.6)
        compute_probabilities([p])
        assert p.probability == 1.0

    def test_mutates_in_place(self):
        p = _make_branch(title="X", description="D", score=0.7)
        assert p.probability == 0.0

        compute_probabilities([p])
        assert p.probability == 1.0

    def test_temperature_sharpens_distribution(self):
        """Low temperature → winner-take-all; high temperature → uniform."""
        p1 = _make_branch(title="A", description="D", score=0.8)
        p2 = _make_branch(title="B", description="D", score=0.2)

        compute_probabilities([p1, p2], temperature=0.1)
        sharp_gap = p1.probability - p2.probability

        p1.score, p2.score = 0.8, 0.2
        compute_probabilities([p1, p2], temperature=5.0)
        flat_gap = p1.probability - p2.probability

        assert sharp_gap > flat_gap

    def test_three_possibilities_example(self):
        """Concrete example: 3 branches scored and normalized."""
        betrayal = _make_branch(title="Betrayal", description="D", score=0.75)
        alliance = _make_branch(title="Alliance", description="D", score=0.50)
        retreat = _make_branch(title="Retreat", description="D", score=0.25)

        compute_probabilities([betrayal, alliance, retreat])

        assert betrayal.probability > alliance.probability
        assert alliance.probability > retreat.probability

        total = betrayal.probability + alliance.probability + retreat.probability
        assert abs(total - 1.0) < 0.01

        for p in [betrayal, alliance, retreat]:
            assert 0.0 < p.probability < 1.0


class TestSoftmax:
    def test_empty_returns_empty(self):
        assert _softmax([]) == []

    def test_single_value(self):
        assert _softmax([0.5]) == [1.0]

    def test_equal_values_uniform(self):
        result = _softmax([0.3, 0.3, 0.3])
        assert all(abs(r - result[0]) < 0.001 for r in result)
        assert abs(sum(result) - 1.0) < 0.01

    def test_higher_score_higher_probability(self):
        result = _softmax([0.9, 0.1])
        assert result[0] > result[1]

    def test_all_zeros_uniform(self):
        result = _softmax([0.0, 0.0, 0.0])
        assert result == [0.3333, 0.3333, 0.3333]

    def test_sums_to_one(self):
        result = _softmax([0.2, 0.5, 0.8, 0.1])
        assert abs(sum(result) - 1.0) < 0.01

    def test_low_temperature_sharpens(self):
        sharp = _softmax([0.8, 0.2], temperature=0.01)
        assert sharp[0] > 0.99

    def test_high_temperature_flattens(self):
        flat = _softmax([0.8, 0.2], temperature=100.0)
        assert abs(flat[0] - flat[1]) < 0.01
