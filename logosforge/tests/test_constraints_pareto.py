"""Tests for constraint integration into Pareto multi-objective mode."""

import pytest

from logosforge.db import Database
from logosforge.quantum_outliner.core import _format_lambda, _format_wavefunction
from logosforge.quantum_outliner.scoring import (
    apply_scores,
    compute_pareto_front,
    recommend_pareto,
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
    return db.create_project("Constraint Pareto Test")


def _branch(bid, title, desc="desc", stakes="", consequence="", branch_type="alternative"):
    return Branch(
        id=bid, title=title, description=desc,
        stakes=stakes, consequence=consequence,
        branch_type=branch_type,
    )


# ---------------------------------------------------------------------------
# Constraint removes options from Pareto set
# ---------------------------------------------------------------------------


class TestConstraintExcludesFromPareto:
    def test_violated_branch_not_in_pareto_front(self):
        wf = Wavefunction.new(anchor="test")
        wf.branches = [
            _branch("a", "Safe path", desc="a safe journey through the forest"),
            _branch("b", "Betrayal path", desc="betrayal and lies destroy trust"),
        ]
        scored = score_branches(wf, constraints=["No betrayal"])
        front = compute_pareto_front(scored)
        assert "b" not in front
        assert "a" in front

    def test_violated_branch_pareto_flag_false(self):
        wf = Wavefunction.new(anchor="test")
        wf.branches = [
            _branch("a", "Safe path", desc="a safe journey"),
            _branch("b", "Betrayal path", desc="betrayal and lies"),
        ]
        scored = score_branches(wf, constraints=["No betrayal"])
        by_id = {s.branch_id: s for s in scored}
        assert by_id["b"].is_pareto_optimal is False
        assert by_id["b"].violations == ["No betrayal"]

    def test_would_be_pareto_but_constraint_blocks(self):
        """A branch that dominates on all factors is still excluded if violated."""
        wf = Wavefunction.new(anchor="test")
        wf.branches = [
            _branch("a", "Weak path", desc="a quiet stroll"),
            _branch("b", "Strong betrayal",
                    desc="betrayal with sudden fight danger risk must conflict",
                    stakes="desperate sacrifice",
                    consequence="war threat"),
        ]
        no_constraint = score_branches(wf)
        assert any(s.branch_id == "b" and s.is_pareto_optimal for s in no_constraint)

        with_constraint = score_branches(wf, constraints=["No betrayal"])
        by_id = {s.branch_id: s for s in with_constraint}
        assert by_id["b"].is_pareto_optimal is False
        assert by_id["a"].is_pareto_optimal is True

    def test_multiple_constraints_exclude_multiple(self):
        wf = Wavefunction.new(anchor="test")
        wf.branches = [
            _branch("a", "Safe path", desc="a safe journey"),
            _branch("b", "Betrayal path", desc="betrayal and lies"),
            _branch("c", "Death path", desc="death awaits everyone"),
        ]
        scored = score_branches(
            wf, constraints=["No betrayal", "No death"],
        )
        front = compute_pareto_front(scored)
        assert "b" not in front
        assert "c" not in front
        assert "a" in front

    def test_all_branches_violated_empty_front(self):
        wf = Wavefunction.new(anchor="test")
        wf.branches = [
            _branch("a", "Betrayal one", desc="betrayal everywhere"),
            _branch("b", "Betrayal two", desc="more betrayal here"),
        ]
        scored = score_branches(wf, constraints=["No betrayal"])
        front = compute_pareto_front(scored)
        assert front == []

    def test_constraint_applied_after_scoring(self):
        """Violated branch keeps its factors but gets score=0 and probability=0."""
        wf = Wavefunction.new(anchor="test")
        wf.branches = [
            _branch("a", "Safe path", desc="a safe journey"),
            _branch("b", "Betrayal", desc="betrayal and sudden fight"),
        ]
        scored = score_branches(wf, constraints=["No betrayal"])
        by_id = {s.branch_id: s for s in scored}
        assert by_id["b"].score == 0.0
        assert by_id["b"].probability == 0.0
        assert by_id["b"].factors["tension_gain"] > 0


# ---------------------------------------------------------------------------
# Constraint + Pareto in recommend_pareto
# ---------------------------------------------------------------------------


class TestConstraintInParetoRecommendation:
    def test_violated_excluded_from_recommendation(self):
        wf = Wavefunction.new(anchor="test")
        wf.branches = [
            _branch("a", "Safe path", desc="a safe journey through forest"),
            _branch("b", "Betrayal path", desc="betrayal and lies"),
        ]
        scored = score_branches(wf, constraints=["No betrayal"])
        apply_scores(wf, scored)
        recs = recommend_pareto(wf)
        rec_ids = {r.branch_id for r in recs}
        assert "b" not in rec_ids

    def test_all_violated_empty_recommendation(self):
        wf = Wavefunction.new(anchor="test")
        wf.branches = [
            _branch("a", "Betrayal one", desc="betrayal here"),
            _branch("b", "Betrayal two", desc="betrayal there"),
        ]
        scored = score_branches(wf, constraints=["No betrayal"])
        apply_scores(wf, scored)
        recs = recommend_pareto(wf)
        assert recs == []


# ---------------------------------------------------------------------------
# UI: Pareto mode mutes violated branches
# ---------------------------------------------------------------------------


class TestParetoMutedViolations:
    def _make_wf(self, constraints):
        wf = Wavefunction.new(anchor="test muted")
        wf.branches = [
            _branch("a", "Safe path",
                    desc="a safe journey through the enchanted forest",
                    stakes="adventure awaits",
                    consequence="new allies found"),
            _branch("b", "Betrayal path",
                    desc="betrayal and lies destroy all trust",
                    stakes="everything is lost",
                    consequence="war begins"),
        ]
        scored = score_branches(wf, constraints=constraints)
        apply_scores(wf, scored)
        wf.branches.sort(key=lambda b: b.probability, reverse=True)
        return wf

    def test_pareto_mode_shows_invalid_label(self):
        wf = self._make_wf(["No betrayal"])
        body = _format_lambda(wf, selection_mode="pareto")
        assert "INVALID" in body
        assert "✗" in body

    def test_pareto_mode_hides_violated_description(self):
        wf = self._make_wf(["No betrayal"])
        body = _format_lambda(wf, selection_mode="pareto")
        assert "betrayal and lies destroy all trust" not in body

    def test_pareto_mode_hides_violated_stakes(self):
        wf = self._make_wf(["No betrayal"])
        body = _format_lambda(wf, selection_mode="pareto")
        assert "everything is lost" not in body

    def test_pareto_mode_shows_violated_constraint(self):
        wf = self._make_wf(["No betrayal"])
        body = _format_lambda(wf, selection_mode="pareto")
        assert 'violates "No betrayal"' in body

    def test_weighted_mode_still_shows_full_blocked(self):
        wf = self._make_wf(["No betrayal"])
        body = _format_lambda(wf, selection_mode="weighted")
        assert "⚠ BLOCKED" in body
        assert "betrayal and lies destroy all trust" in body

    def test_pareto_mode_safe_branch_shows_full_details(self):
        wf = self._make_wf(["No betrayal"])
        body = _format_lambda(wf, selection_mode="pareto")
        assert "a safe journey through the enchanted forest" in body
        assert "adventure awaits" in body

    def test_pareto_mode_excluded_count_shown(self):
        wf = self._make_wf(["No betrayal"])
        body = _format_lambda(wf, selection_mode="pareto")
        assert "1 option(s) excluded by constraints" in body

    def test_pareto_mode_no_excluded_count_without_violations(self):
        wf = self._make_wf([])
        body = _format_lambda(wf, selection_mode="pareto")
        assert "excluded by constraints" not in body

    def test_pareto_mode_multiple_excluded(self):
        wf = Wavefunction.new(anchor="test multi")
        wf.branches = [
            _branch("a", "Safe path", desc="a safe journey"),
            _branch("b", "Betrayal path", desc="betrayal here"),
            _branch("c", "Death path", desc="death awaits"),
        ]
        scored = score_branches(wf, constraints=["No betrayal", "No death"])
        apply_scores(wf, scored)
        body = _format_lambda(wf, selection_mode="pareto")
        assert "2 option(s) excluded by constraints" in body


# ---------------------------------------------------------------------------
# Violated branches grouped below separator in Pareto mode
# ---------------------------------------------------------------------------


class TestViolatedBranchGrouping:
    def test_violated_below_separator(self):
        wf = Wavefunction.new(anchor="test grouping")
        wf.branches = [
            _branch("a", "Safe path",
                    desc="a safe journey through the forest"),
            _branch("b", "Betrayal path",
                    desc="betrayal and lies everywhere"),
        ]
        scored = score_branches(wf, constraints=["No betrayal"])
        apply_scores(wf, scored)
        wf.branches.sort(key=lambda b: b.probability, reverse=True)
        body = _format_lambda(wf, selection_mode="pareto")
        lines = body.split("\n")

        separator_idx = None
        invalid_idx = None
        for i, line in enumerate(lines):
            if "─ ─ ─" in line:
                separator_idx = i
            if "INVALID" in line:
                invalid_idx = i

        if separator_idx is not None and invalid_idx is not None:
            assert invalid_idx > separator_idx

    def test_pareto_optimal_above_violated(self):
        wf = Wavefunction.new(anchor="test order")
        wf.branches = [
            _branch("a", "Safe path",
                    desc="sudden fight danger risk must conflict",
                    stakes="desperate",
                    consequence="war threat"),
            _branch("b", "Betrayal path",
                    desc="betrayal and lies everywhere"),
        ]
        scored = score_branches(wf, constraints=["No betrayal"])
        apply_scores(wf, scored)
        wf.branches.sort(key=lambda b: b.probability, reverse=True)
        body = _format_lambda(wf, selection_mode="pareto")
        safe_idx = body.find("Safe path")
        invalid_idx = body.find("INVALID")
        assert safe_idx < invalid_idx


# ---------------------------------------------------------------------------
# Full pipeline via _format_wavefunction with DB constraints
# ---------------------------------------------------------------------------


class TestFullPipelineConstraintsPareto:
    def test_db_constraints_respected_in_pareto(self, db, project):
        db.set_selection_mode(project.id, "pareto")
        db.add_constraint(project.id, "No betrayal")

        wf = Wavefunction.new(anchor="db pipeline test")
        wf.branches = [
            _branch("a", "Safe path", desc="a safe journey"),
            _branch("b", "Betrayal path", desc="betrayal and lies"),
        ]
        result = _format_wavefunction("Test", wf, db=db, project_id=project.id)
        assert "INVALID" in result.body
        assert "excluded by constraints" in result.body

        pareto_in_payload = [
            b for b in result.payload["branches"]
            if b["is_pareto_optimal"]
        ]
        violated_in_payload = [
            b for b in result.payload["branches"]
            if b.get("id") == "b"
        ]
        assert all(not b["is_pareto_optimal"] for b in violated_in_payload)

    def test_removing_constraint_restores_pareto(self, db, project):
        db.set_selection_mode(project.id, "pareto")
        db.add_constraint(project.id, "No betrayal")

        wf1 = Wavefunction.new(anchor="before")
        wf1.branches = [
            _branch("a", "Safe", desc="a safe journey"),
            _branch("b", "Betrayal strong",
                    desc="betrayal with sudden fight danger risk",
                    stakes="desperate sacrifice",
                    consequence="war threat"),
        ]
        r1 = _format_wavefunction("Test", wf1, db=db, project_id=project.id)
        assert "INVALID" in r1.body

        db.remove_constraint(project.id, "No betrayal")

        wf2 = Wavefunction.new(anchor="after")
        wf2.branches = [
            _branch("a", "Safe", desc="a safe journey"),
            _branch("b", "Betrayal strong",
                    desc="betrayal with sudden fight danger risk",
                    stakes="desperate sacrifice",
                    consequence="war threat"),
        ]
        r2 = _format_wavefunction("Test", wf2, db=db, project_id=project.id)
        assert "INVALID" not in r2.body
