"""Tests for tradeoff chip visualization and Pareto badge."""

import pytest

from logosforge.db import Database
from logosforge.quantum_outliner.core import _format_lambda, _format_wavefunction
from logosforge.quantum_outliner.scoring import (
    FACTOR_CHIP_LABELS,
    PARETO_OBJECTIVES,
    _CHIP_THRESHOLD,
    apply_scores,
    compute_tradeoff_chips,
    format_branch_chips,
    score_branches,
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
    return db.create_project("Tradeoff Viz Test")


def _branch(bid, title, desc="desc", stakes="", consequence="", branch_type="alternative"):
    return Branch(
        id=bid, title=title, description=desc,
        stakes=stakes, consequence=consequence,
        branch_type=branch_type,
    )


# ---------------------------------------------------------------------------
# compute_tradeoff_chips — unit tests
# ---------------------------------------------------------------------------


class TestComputeTradeoffChips:
    def test_high_tension_shows_up_arrow(self):
        branch = {"tension_gain": 0.9, "structure_fit": 0.5,
                  "psyke_consistency": 0.5, "novelty": 0.5, "goal_alignment": 0.5}
        others = [
            {"tension_gain": 0.2, "structure_fit": 0.5,
             "psyke_consistency": 0.5, "novelty": 0.5, "goal_alignment": 0.5},
        ]
        all_factors = [branch] + others
        chips = compute_tradeoff_chips(branch, all_factors)
        assert any("↑" in c and "tension" in c for c in chips)

    def test_low_consistency_shows_down_arrow(self):
        branch = {"tension_gain": 0.5, "structure_fit": 0.5,
                  "psyke_consistency": 0.1, "novelty": 0.5, "goal_alignment": 0.5}
        others = [
            {"tension_gain": 0.5, "structure_fit": 0.5,
             "psyke_consistency": 0.8, "novelty": 0.5, "goal_alignment": 0.5},
        ]
        all_factors = [branch] + others
        chips = compute_tradeoff_chips(branch, all_factors)
        assert any("↓" in c and "consistency" in c for c in chips)

    def test_no_chips_when_all_equal(self):
        factors = {"tension_gain": 0.5, "structure_fit": 0.5,
                   "psyke_consistency": 0.5, "novelty": 0.5, "goal_alignment": 0.5}
        chips = compute_tradeoff_chips(factors, [factors, factors])
        assert chips == []

    def test_max_three_chips(self):
        branch = {"tension_gain": 0.9, "structure_fit": 0.9,
                  "psyke_consistency": 0.9, "novelty": 0.9, "goal_alignment": 0.9}
        other = {"tension_gain": 0.1, "structure_fit": 0.1,
                 "psyke_consistency": 0.1, "novelty": 0.1, "goal_alignment": 0.1}
        chips = compute_tradeoff_chips(branch, [branch, other], max_chips=3)
        assert len(chips) <= 3

    def test_sorted_by_magnitude(self):
        branch = {"tension_gain": 0.9, "structure_fit": 0.6,
                  "psyke_consistency": 0.5, "novelty": 0.5, "goal_alignment": 0.5}
        other = {"tension_gain": 0.1, "structure_fit": 0.5,
                 "psyke_consistency": 0.5, "novelty": 0.5, "goal_alignment": 0.5}
        chips = compute_tradeoff_chips(branch, [branch, other])
        assert chips[0] == "↑ tension"

    def test_empty_factors(self):
        assert compute_tradeoff_chips({}, []) == []
        assert compute_tradeoff_chips({"tension_gain": 0.5}, []) == []

    def test_threshold_respected(self):
        branch = {"tension_gain": 0.51, "structure_fit": 0.5,
                  "psyke_consistency": 0.5, "novelty": 0.5, "goal_alignment": 0.5}
        other = {"tension_gain": 0.49, "structure_fit": 0.5,
                 "psyke_consistency": 0.5, "novelty": 0.5, "goal_alignment": 0.5}
        chips = compute_tradeoff_chips(branch, [branch, other])
        assert chips == []

    def test_uses_correct_chip_labels(self):
        for key, label in FACTOR_CHIP_LABELS.items():
            assert key in PARETO_OBJECTIVES
            assert isinstance(label, str)
            assert len(label) < 15


class TestFormatBranchChips:
    def test_pareto_badge_when_optimal(self):
        factors = {"tension_gain": 0.5, "structure_fit": 0.5,
                   "psyke_consistency": 0.5, "novelty": 0.5, "goal_alignment": 0.5}
        result = format_branch_chips(factors, [factors], is_pareto=True)
        assert "●" in result

    def test_no_badge_when_not_optimal(self):
        factors = {"tension_gain": 0.5, "structure_fit": 0.5,
                   "psyke_consistency": 0.5, "novelty": 0.5, "goal_alignment": 0.5}
        result = format_branch_chips(factors, [factors], is_pareto=False)
        assert "●" not in result

    def test_combines_badge_and_chips(self):
        branch = {"tension_gain": 0.9, "structure_fit": 0.5,
                  "psyke_consistency": 0.5, "novelty": 0.5, "goal_alignment": 0.5}
        other = {"tension_gain": 0.1, "structure_fit": 0.5,
                 "psyke_consistency": 0.5, "novelty": 0.5, "goal_alignment": 0.5}
        result = format_branch_chips(branch, [branch, other], is_pareto=True)
        assert "●" in result
        assert "↑ tension" in result

    def test_empty_when_no_deltas_not_pareto(self):
        factors = {"tension_gain": 0.5, "structure_fit": 0.5,
                   "psyke_consistency": 0.5, "novelty": 0.5, "goal_alignment": 0.5}
        result = format_branch_chips(factors, [factors], is_pareto=False)
        assert result == ""


# ---------------------------------------------------------------------------
# Integration with _format_lambda
# ---------------------------------------------------------------------------


class TestChipsInFormatLambda:
    def _make_wf_with_tradeoffs(self):
        wf = Wavefunction.new(anchor="test tradeoffs")
        wf.branches = [
            _branch("a", "Tension Path",
                    desc="sudden fight danger risk must conflict",
                    stakes="desperate sacrifice",
                    consequence="war threat"),
            _branch("b", "Calm Path",
                    desc="a quiet peaceful stroll through the garden"),
        ]
        scored = score_branches(wf)
        apply_scores(wf, scored)
        wf.branches.sort(key=lambda b: b.probability, reverse=True)
        return wf

    def test_chips_hidden_by_default(self):
        wf = self._make_wf_with_tradeoffs()
        body = _format_lambda(wf)
        assert "↑" not in body
        assert "↓" not in body

    def test_chips_shown_when_toggled(self):
        wf = self._make_wf_with_tradeoffs()
        body = _format_lambda(wf, show_tradeoffs=True)
        assert "↑" in body or "↓" in body

    def test_pareto_badge_shown_when_toggled(self):
        wf = self._make_wf_with_tradeoffs()
        body = _format_lambda(wf, show_tradeoffs=True)
        pareto_branches = [b for b in wf.branches if b.is_pareto_optimal]
        assert len(pareto_branches) >= 1
        assert "●" in body

    def test_pareto_badge_hidden_by_default(self):
        wf = self._make_wf_with_tradeoffs()
        body = _format_lambda(wf)
        assert "●" not in body

    def test_violated_branch_no_chips(self):
        wf = Wavefunction.new(anchor="test")
        wf.branches = [
            _branch("a", "Safe path", desc="a safe journey"),
            _branch("b", "Betrayal path", desc="betrayal and lies"),
        ]
        scored = score_branches(wf, constraints=["No betrayal"])
        apply_scores(wf, scored)
        body = _format_lambda(wf, show_tradeoffs=True)
        betrayal_idx = body.find("Betrayal path")
        blocked_idx = body.find("BLOCKED", betrayal_idx)
        assert blocked_idx > betrayal_idx
        chip_section = body[betrayal_idx:blocked_idx]
        assert "↑" not in chip_section
        assert "↓" not in chip_section


# ---------------------------------------------------------------------------
# DB toggle
# ---------------------------------------------------------------------------


class TestShowTradeoffsToggle:
    def test_default_is_off(self, db, project):
        assert db.get_show_tradeoffs(project.id) is False

    def test_enable(self, db, project):
        db.set_show_tradeoffs(project.id, True)
        assert db.get_show_tradeoffs(project.id) is True

    def test_disable(self, db, project):
        db.set_show_tradeoffs(project.id, True)
        db.set_show_tradeoffs(project.id, False)
        assert db.get_show_tradeoffs(project.id) is False

    def test_persists_across_instances(self, tmp_path):
        path = str(tmp_path / "persist.db")
        db1 = Database(path)
        p = db1.create_project("Persist Test")
        db1.set_show_tradeoffs(p.id, True)

        db2 = Database(path)
        assert db2.get_show_tradeoffs(p.id) is True

    def test_per_project_isolation(self, db):
        p1 = db.create_project("P1")
        p2 = db.create_project("P2")
        db.set_show_tradeoffs(p1.id, True)
        assert db.get_show_tradeoffs(p1.id) is True
        assert db.get_show_tradeoffs(p2.id) is False


# ---------------------------------------------------------------------------
# Integration: _format_wavefunction respects toggle
# ---------------------------------------------------------------------------


class TestFormatWavefunctionToggle:
    def test_chips_when_toggle_on(self, db, project):
        db.set_show_tradeoffs(project.id, True)
        wf = Wavefunction.new(anchor="toggle test")
        wf.branches = [
            _branch("a", "Tension Path",
                    desc="sudden fight danger risk must conflict",
                    stakes="desperate sacrifice",
                    consequence="war threat"),
            _branch("b", "Calm Path",
                    desc="a quiet peaceful stroll through the garden"),
        ]
        result = _format_wavefunction("Test", wf, db=db, project_id=project.id)
        assert "↑" in result.body or "↓" in result.body or "●" in result.body

    def test_no_chips_when_toggle_off(self, db, project):
        db.set_show_tradeoffs(project.id, False)
        wf = Wavefunction.new(anchor="toggle test")
        wf.branches = [
            _branch("a", "Tension Path",
                    desc="sudden fight danger risk must conflict"),
            _branch("b", "Calm Path", desc="a quiet peaceful stroll"),
        ]
        result = _format_wavefunction("Test", wf, db=db, project_id=project.id)
        assert "↑" not in result.body
        assert "↓" not in result.body
        assert "●" not in result.body


# ---------------------------------------------------------------------------
# Payload includes Pareto flag
# ---------------------------------------------------------------------------


class TestPayloadParetoFlag:
    def test_payload_branches_have_pareto_flag(self, db, project):
        wf = Wavefunction.new(anchor="payload test")
        wf.branches = [
            _branch("a", "Alpha", desc="sudden fight danger conflict"),
            _branch("b", "Beta", desc="a calm stroll"),
        ]
        result = _format_wavefunction("Test", wf, db=db, project_id=project.id)
        for b_data in result.payload["branches"]:
            assert "is_pareto_optimal" in b_data
            assert isinstance(b_data["is_pareto_optimal"], bool)
