"""Tests for scoring integration into possibility generation.

Verifies that every generated possibility gets scored and assigned a
probability, output is sorted by probability desc, classical mode is
unchanged, and the formatted body includes probability percentages.
"""

from unittest.mock import patch

import pytest

from logosforge.db import Database
from logosforge.quantum_outliner import (
    Branch,
    OutlineMode,
    Wavefunction,
    generate_branches,
    generate_outline,
    get_state,
)
from logosforge.quantum_outliner.core import (
    _format_lambda,
    _format_wavefunction,
)
from logosforge.quantum_outliner.state import StateDelta, _STATES
from logosforge.quantum_outliner.writing_methods_rag import reload as rag_reload


@pytest.fixture
def db(tmp_path):
    return Database(str(tmp_path / "test.db"))


@pytest.fixture
def project(db):
    return db.create_project("Scoring Integration Test")


@pytest.fixture(autouse=True)
def _reset():
    _STATES.clear()
    rag_reload()
    yield
    _STATES.clear()


def _offline():
    return patch(
        "logosforge.quantum_outliner.possibilities.chat_completion",
        side_effect=ConnectionError("offline"),
    )


class TestScoringAppliedOnGeneration:
    def test_branches_have_scores_after_generate(self, db, project):
        state = get_state(project.id)
        state.outline_mode = OutlineMode.LAMBDA
        state.structure_mode = "quantum"

        with _offline():
            result = generate_branches(db, project.id, "Hero meets enemy")

        for b in result.payload["branches"]:
            assert b["score"] > 0
            assert b["probability"] > 0
            assert isinstance(b["factors"], dict)
            assert len(b["factors"]) == 5

    def test_outline_branches_have_scores(self, db, project):
        state = get_state(project.id)
        state.outline_mode = OutlineMode.LAMBDA
        state.structure_mode = "quantum"

        with _offline():
            result = generate_outline(db, project.id, "A knight discovers a curse")

        for b in result.payload["branches"]:
            assert b["score"] > 0
            assert b["probability"] > 0

    def test_probabilities_sum_to_one(self, db, project):
        state = get_state(project.id)
        state.outline_mode = OutlineMode.LAMBDA

        with _offline():
            result = generate_branches(db, project.id, "Hero meets enemy")

        total = sum(b["probability"] for b in result.payload["branches"])
        assert abs(total - 1.0) < 0.02

    def test_factors_present_in_payload(self, db, project):
        state = get_state(project.id)
        state.outline_mode = OutlineMode.LAMBDA

        with _offline():
            result = generate_branches(db, project.id, "Hero meets enemy")

        expected_factors = {
            "structure_fit", "psyke_consistency", "tension_gain",
            "novelty", "goal_alignment",
        }
        for b in result.payload["branches"]:
            assert set(b["factors"].keys()) == expected_factors


class TestSortedByProbability:
    def test_payload_branches_sorted_desc(self, db, project):
        state = get_state(project.id)
        state.outline_mode = OutlineMode.LAMBDA

        with _offline():
            result = generate_branches(db, project.id, "Hero meets enemy")

        probs = [b["probability"] for b in result.payload["branches"]]
        assert probs == sorted(probs, reverse=True)

    def test_format_wavefunction_sorts_branches(self):
        b_low = Branch.new(
            title="Calm morning", description="peaceful walk",
        )
        b_high = Branch.new(
            title="Sudden war erupts",
            description="fight and danger threaten sacrifice",
            stakes="desperate loss",
            consequence="pain and fear",
        )
        wf = Wavefunction.new(anchor="Test", branches=[b_low, b_high])

        result = _format_wavefunction("Test", wf)
        branches = result.payload["branches"]
        assert branches[0]["probability"] >= branches[1]["probability"]

    def test_state_branches_also_sorted(self, db, project):
        state = get_state(project.id)
        state.outline_mode = OutlineMode.LAMBDA

        with _offline():
            generate_branches(db, project.id, "Hero meets enemy")

        wf = state.active()[0]
        probs = [b.probability for b in wf.branches]
        assert probs == sorted(probs, reverse=True)


class TestClassicalUnchanged:
    def test_classical_mode_no_scoring(self, db, project):
        state = get_state(project.id)
        state.outline_mode = OutlineMode.CLASSICAL

        result = generate_branches(db, project.id, "Save the Cat midpoint")

        assert result.kind == "classical_outline"
        assert "QUANTUM FIELD" not in result.body
        assert "%" not in result.body

    def test_classical_outline_no_scoring(self, db, project):
        state = get_state(project.id)
        state.outline_mode = OutlineMode.CLASSICAL

        result = generate_outline(db, project.id, "Three-Act Structure opening")

        assert result.kind == "classical_outline"


class TestProbabilityInOutput:
    def test_body_shows_percentage(self, db, project):
        state = get_state(project.id)
        state.outline_mode = OutlineMode.LAMBDA

        with _offline():
            result = generate_branches(db, project.id, "Hero meets enemy")

        assert "%" in result.body

    def test_format_lambda_shows_percentage_when_scored(self):
        b = Branch.new(
            title="Test", description="Desc",
            score=0.7, probability=0.45,
        )
        wf = Wavefunction.new(anchor="Test", branches=[b])
        body = _format_lambda(wf)
        assert "45%" in body

    def test_format_lambda_hides_percentage_when_unscored(self):
        b = Branch.new(title="Test", description="Desc")
        wf = Wavefunction.new(anchor="Test", branches=[b])
        body = _format_lambda(wf)
        assert "%" not in body

    def test_format_wavefunction_always_shows_percentage(self):
        b = Branch.new(
            title="Fight", description="danger and war",
            stakes="sacrifice", consequence="loss",
        )
        wf = Wavefunction.new(anchor="Test", branches=[b])
        result = _format_wavefunction("Test", wf)
        assert "%" in result.body


class TestHybridUsesStructureAndScoring:
    def test_hybrid_has_structure_fit_in_factors(self, db, project):
        state = get_state(project.id)
        state.outline_mode = OutlineMode.LAMBDA
        state.structure_mode = "hybrid"

        with _offline():
            result = generate_branches(
                db, project.id, "Save the Cat midpoint scene",
            )

        for b in result.payload["branches"]:
            assert "structure_fit" in b["factors"]
            assert b["probability"] > 0

    def test_hybrid_branches_scored_and_sorted(self, db, project):
        state = get_state(project.id)
        state.outline_mode = OutlineMode.LAMBDA
        state.structure_mode = "hybrid"

        with _offline():
            result = generate_branches(
                db, project.id, "Save the Cat midpoint scene",
            )

        probs = [b["probability"] for b in result.payload["branches"]]
        assert probs == sorted(probs, reverse=True)

    def test_hybrid_still_shows_gravity(self, db, project):
        state = get_state(project.id)
        state.outline_mode = OutlineMode.LAMBDA
        state.structure_mode = "hybrid"

        with _offline():
            result = generate_branches(
                db, project.id, "Save the Cat midpoint scene",
            )

        assert "Gravity:" in result.body
        assert "%" in result.body


class TestThreePossibilitiesExample:
    """Demonstrates 3-branch scoring with concrete output."""

    def test_three_branch_example(self):
        b1 = Branch.new(
            title="Betrayal at the Gate",
            description="The trusted ally suddenly betrays the hero.",
            stakes="The hero must fight alone against danger.",
            consequence="Trust is severed, desperate sacrifice ahead.",
            branch_type="intensification",
            structure_beat="Midpoint",
            structure_method="Save the Cat",
        )
        b2 = Branch.new(
            title="Fragile Alliance",
            description="Former enemies agree to cooperate.",
            stakes="Independence is at risk.",
            consequence="Both sides must compromise.",
            branch_type="alternative",
        )
        b3 = Branch.new(
            title="Quiet Retreat",
            description="The hero withdraws to regroup.",
            stakes="Momentum is lost.",
            consequence="Time passes without progress.",
        )
        wf = Wavefunction.new(
            anchor="Hero arrives at the enemy fortress",
            branches=[b1, b2, b3],
        )
        wf.structure_method = "Save the Cat"
        wf.structure_beat = "Midpoint"

        result = _format_wavefunction("Possibilities", wf)

        branches = result.payload["branches"]
        assert len(branches) == 3

        total = sum(b["probability"] for b in branches)
        assert abs(total - 1.0) < 0.02

        probs = [b["probability"] for b in branches]
        assert probs == sorted(probs, reverse=True)

        for b in branches:
            assert b["score"] > 0
            assert b["probability"] > 0
            assert len(b["factors"]) == 5

        assert branches[0]["probability"] > branches[2]["probability"]

        assert "%" in result.body
        assert "QUANTUM FIELD" in result.body
        assert "Option 1:" in result.body
        assert "Option 2:" in result.body
        assert "Option 3:" in result.body

    def test_three_branch_example_with_psyke(self, db, project):
        db.create_psyke_entry(
            project.id, "Marcus", "character", notes="The hero, brave warrior",
        )
        db.create_psyke_entry(
            project.id, "Lyra", "character", notes="The spy, cunning agent",
        )

        b1 = Branch.new(
            title="Marcus fights alone",
            description="Marcus charges into danger, suddenly betrayed.",
            stakes="His life and sacrifice demanded.",
            consequence="Desperate loss threatens all.",
        )
        b2 = Branch.new(
            title="Lyra reveals the secret",
            description="Lyra exposes the hidden lie.",
            stakes="Truth surfaces but fear spreads.",
            consequence="New alliances form from betrayal.",
        )
        b3 = Branch.new(
            title="Peaceful negotiation",
            description="Both sides talk calmly.",
            stakes="Time.",
            consequence="A fragile truce.",
        )
        wf = Wavefunction.new(
            anchor="The fortress confrontation",
            branches=[b1, b2, b3],
        )

        result = _format_wavefunction(
            "Possibilities", wf, db=db, project_id=project.id,
        )

        branches = result.payload["branches"]
        total = sum(b["probability"] for b in branches)
        assert abs(total - 1.0) < 0.02

        probs = [b["probability"] for b in branches]
        assert probs == sorted(probs, reverse=True)

        psyke_scores = [b["factors"]["psyke_consistency"] for b in branches]
        assert branches[2]["factors"]["psyke_consistency"] < max(psyke_scores)


class TestUserWeightsInScoring:
    """Demonstrates that per-project user weights change branch ranking."""

    def _make_branches(self):
        b_tense = Branch.new(
            title="War erupts at the gate",
            description="A desperate fight breaks out suddenly. Fear and danger threaten all.",
            stakes="survival of the desperate army",
            consequence="Sacrifice and pain follow the war.",
            branch_type="intensification",
        )
        b_novel = Branch.new(
            title="Crystalline portal opens",
            description="An iridescent shimmer reveals a pathway to an alien dimension.",
            stakes="curiosity",
            consequence="Uncharted territory beckons.",
            branch_type="alternative",
        )
        b_overlap = Branch.new(
            title="War continues at the gate",
            description="The desperate fight at the gate grinds on without resolution.",
            stakes="survival of the desperate army",
            consequence="Sacrifice and pain deepen.",
        )
        return b_tense, b_novel, b_overlap

    def test_default_weights_produce_ranking(self, db, project):
        b_tense, b_novel, b_overlap = self._make_branches()
        wf = Wavefunction.new(anchor="Fork", branches=[b_tense, b_novel, b_overlap])

        result = _format_wavefunction(
            "Test", wf, db=db, project_id=project.id,
        )
        probs = [b["probability"] for b in result.payload["branches"]]
        assert probs == sorted(probs, reverse=True)

    def test_tension_weight_favors_tense_branch(self, db, project):
        b_tense, b_novel, b_overlap = self._make_branches()

        db.set_scoring_weights(project.id, {
            "structure_fit": 0.05,
            "psyke_consistency": 0.05,
            "tension_gain": 0.75,
            "novelty": 0.10,
            "goal_alignment": 0.05,
        })

        wf = Wavefunction.new(anchor="Fork", branches=[b_tense, b_novel, b_overlap])
        result = _format_wavefunction(
            "Test", wf, db=db, project_id=project.id,
        )
        branches = result.payload["branches"]
        assert branches[0]["title"] == "War erupts at the gate"

    def test_novelty_weight_favors_novel_branch(self, db, project):
        b_tense, b_novel, b_overlap = self._make_branches()

        db.set_scoring_weights(project.id, {
            "structure_fit": 0.05,
            "psyke_consistency": 0.05,
            "tension_gain": 0.05,
            "novelty": 0.80,
            "goal_alignment": 0.05,
        })

        wf = Wavefunction.new(anchor="Fork", branches=[b_tense, b_novel, b_overlap])
        result = _format_wavefunction(
            "Test", wf, db=db, project_id=project.id,
        )
        branches = result.payload["branches"]
        assert branches[0]["title"] == "Crystalline portal opens"

    def test_different_weights_different_ranking(self, db, project):
        b_tense, b_novel, b_overlap = self._make_branches()

        db.set_scoring_weights(project.id, {
            "structure_fit": 0.05,
            "psyke_consistency": 0.05,
            "tension_gain": 0.75,
            "novelty": 0.10,
            "goal_alignment": 0.05,
        })
        wf1 = Wavefunction.new(anchor="Fork", branches=[b_tense, b_novel, b_overlap])
        r1 = _format_wavefunction("Test", wf1, db=db, project_id=project.id)
        ranking_tension = [b["title"] for b in r1.payload["branches"]]

        b_tense2, b_novel2, b_overlap2 = self._make_branches()
        db.set_scoring_weights(project.id, {
            "structure_fit": 0.05,
            "psyke_consistency": 0.05,
            "tension_gain": 0.05,
            "novelty": 0.80,
            "goal_alignment": 0.05,
        })
        wf2 = Wavefunction.new(anchor="Fork", branches=[b_tense2, b_novel2, b_overlap2])
        r2 = _format_wavefunction("Test", wf2, db=db, project_id=project.id)
        ranking_novelty = [b["title"] for b in r2.payload["branches"]]

        assert ranking_tension != ranking_novelty
        assert ranking_tension[0] == "War erupts at the gate"
        assert ranking_novelty[0] == "Crystalline portal opens"

    def test_no_stored_weights_uses_defaults(self):
        b = Branch.new(
            title="Fight", description="danger and war",
            stakes="sacrifice", consequence="loss",
        )
        wf = Wavefunction.new(anchor="Test", branches=[b])
        result = _format_wavefunction("Test", wf)
        assert result.payload["branches"][0]["score"] > 0

    def test_deterministic_given_same_inputs(self, db, project):
        db.set_scoring_weights(project.id, {
            "structure_fit": 0.30,
            "psyke_consistency": 0.10,
            "tension_gain": 0.30,
            "novelty": 0.20,
            "goal_alignment": 0.10,
        })

        results = []
        for _ in range(3):
            bt, bn, bo = self._make_branches()
            wf = Wavefunction.new(anchor="Fork", branches=[bt, bn, bo])
            r = _format_wavefunction("Test", wf, db=db, project_id=project.id)
            results.append([b["probability"] for b in r.payload["branches"]])

        assert results[0] == results[1] == results[2]
