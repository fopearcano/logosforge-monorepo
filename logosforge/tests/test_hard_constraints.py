"""Tests for hard constraints in scoring.

Covers:
- Constraint parsing (prefix stripping, keyword extraction)
- Constraint checking against branch text
- Violating branches get score=0 and probability=0
- Non-violating branches unaffected
- Violations shown in explanation
- DB persistence for constraints
- Integration with full scoring pipeline
"""

import pytest

from logosforge.db import Database
from logosforge.quantum_outliner import (
    Branch,
    Wavefunction,
    check_constraints,
    parse_constraint,
)
from logosforge.quantum_outliner.core import (
    _format_lambda,
    _format_wavefunction,
)
from logosforge.quantum_outliner.scoring import (
    apply_scores,
    explain_wavefunction,
    score_branches,
)
from logosforge.quantum_outliner.state import _STATES


@pytest.fixture
def db(tmp_path):
    return Database(str(tmp_path / "test.db"))


@pytest.fixture
def project(db):
    return db.create_project("Constraint Test")


@pytest.fixture(autouse=True)
def _reset():
    _STATES.clear()
    yield
    _STATES.clear()


# ---------------------------------------------------------------------------
# parse_constraint
# ---------------------------------------------------------------------------


class TestParseConstraint:
    def test_strips_no_prefix(self):
        assert parse_constraint("No betrayal") == ["betrayal"]

    def test_strips_never_prefix(self):
        assert parse_constraint("Never kill anyone") == ["kill", "anyone"]

    def test_strips_forbid_prefix(self):
        assert parse_constraint("Forbid death") == ["death"]

    def test_strips_ban_prefix(self):
        assert parse_constraint("Ban violence") == ["violence"]

    def test_strips_dont_prefix(self):
        assert parse_constraint("Don't betray") == ["betray"]

    def test_strips_do_not_prefix(self):
        assert parse_constraint("Do not kill Mary") == ["kill", "mary"]

    def test_removes_stop_words(self):
        assert parse_constraint("No betrayal of the alliance") == ["betrayal", "alliance"]

    def test_lowercases(self):
        assert parse_constraint("No BETRAYAL") == ["betrayal"]

    def test_strips_whitespace(self):
        assert parse_constraint("  No betrayal  ") == ["betrayal"]

    def test_no_prefix_keeps_all_content_words(self):
        assert parse_constraint("betrayal") == ["betrayal"]

    def test_positive_prefix_not_stripped(self):
        result = parse_constraint("Keep Mary alive")
        assert "keep" in result
        assert "mary" in result

    def test_empty_string(self):
        assert parse_constraint("") == []

    def test_only_stop_words_after_prefix(self):
        assert parse_constraint("No the") == []


# ---------------------------------------------------------------------------
# check_constraints
# ---------------------------------------------------------------------------


class TestCheckConstraints:
    def test_no_constraints_no_violations(self):
        b = Branch.new(title="War erupts", description="battle begins")
        assert check_constraints(b, []) == []

    def test_matching_keyword_violates(self):
        b = Branch.new(
            title="Marcus betrays the alliance",
            description="A shocking betrayal unfolds.",
        )
        violations = check_constraints(b, ["No betrayal"])
        assert "No betrayal" in violations

    def test_non_matching_keyword_no_violation(self):
        b = Branch.new(
            title="Marcus joins the alliance",
            description="A new partnership forms.",
        )
        violations = check_constraints(b, ["No betrayal"])
        assert violations == []

    def test_substring_matching(self):
        b = Branch.new(
            title="The betrayal shocks everyone",
            description="Trust is broken.",
        )
        violations = check_constraints(b, ["No betray"])
        assert "No betray" in violations

    def test_multi_keyword_all_must_match(self):
        b = Branch.new(
            title="Mary dies in battle",
            description="A tragic loss.",
        )
        violations = check_constraints(b, ["Mary dies"])
        assert "Mary dies" in violations

    def test_multi_keyword_partial_no_violation(self):
        b = Branch.new(
            title="Mary wins the battle",
            description="A great victory.",
        )
        violations = check_constraints(b, ["Mary dies"])
        assert violations == []

    def test_checks_all_text_fields(self):
        b = Branch.new(
            title="Peaceful morning",
            description="All is calm.",
            stakes="alliance",
            consequence="betrayal follows",
        )
        violations = check_constraints(b, ["No betrayal"])
        assert "No betrayal" in violations

    def test_multiple_constraints(self):
        b = Branch.new(
            title="Marcus betrays and kills",
            description="Violence and betrayal.",
        )
        violations = check_constraints(b, ["No betrayal", "No killing"])
        assert "No betrayal" in violations

    def test_case_insensitive(self):
        b = Branch.new(
            title="BETRAYAL at dawn",
            description="shocking events",
        )
        violations = check_constraints(b, ["No betrayal"])
        assert len(violations) == 1

    def test_none_constraints_no_error(self):
        b = Branch.new(title="Test", description="desc")
        assert check_constraints(b, []) == []


# ---------------------------------------------------------------------------
# Scoring integration
# ---------------------------------------------------------------------------


class TestConstraintsInScoring:
    def _make_wf(self):
        b_clean = Branch.new(
            title="Alliance strengthens",
            description="The partnership grows stronger.",
            branch_type="intensification",
        )
        b_violating = Branch.new(
            title="Marcus betrays the alliance",
            description="A shocking betrayal unfolds.",
            branch_type="intensification",
        )
        b_neutral = Branch.new(
            title="Storm approaches the city",
            description="Dark clouds gather on the horizon.",
            branch_type="alternative",
        )
        return Wavefunction.new(
            anchor="Test", branches=[b_clean, b_violating, b_neutral],
        )

    def test_violating_branch_gets_zero_score(self):
        wf = self._make_wf()
        scored = score_branches(wf, constraints=["No betrayal"])
        violating = next(s for s in scored if "betray" in s.branch_id
                         or any(v for v in s.violations))
        assert violating.score == 0.0

    def test_violating_branch_gets_zero_probability(self):
        wf = self._make_wf()
        scored = score_branches(wf, constraints=["No betrayal"])
        violating = next(s for s in scored if s.violations)
        assert violating.probability == 0.0

    def test_non_violating_branches_unaffected(self):
        wf = self._make_wf()
        scored_with = score_branches(wf, constraints=["No betrayal"])
        clean_with = [s for s in scored_with if not s.violations]

        wf2 = self._make_wf()
        scored_without = score_branches(wf2)
        clean_without = [s for s in scored_without
                         if s.branch_id in {c.branch_id for c in clean_with}]

        for sw, swo in zip(
            sorted(clean_with, key=lambda s: s.branch_id),
            sorted(clean_without, key=lambda s: s.branch_id),
        ):
            assert sw.score == swo.score

    def test_violating_branch_ranks_last(self):
        wf = self._make_wf()
        scored = score_branches(wf, constraints=["No betrayal"])
        assert scored[-1].violations

    def test_probabilities_renormalized(self):
        wf = self._make_wf()
        scored = score_branches(wf, constraints=["No betrayal"])
        probs = [s.probability for s in scored]
        assert abs(sum(probs) - 1.0) < 0.01
        violating = next(s for s in scored if s.violations)
        assert violating.probability == 0.0

    def test_violations_stored_on_scored_branch(self):
        wf = self._make_wf()
        scored = score_branches(wf, constraints=["No betrayal"])
        violating = next(s for s in scored if s.violations)
        assert "No betrayal" in violating.violations

    def test_apply_scores_transfers_violations(self):
        wf = self._make_wf()
        scored = score_branches(wf, constraints=["No betrayal"])
        apply_scores(wf, scored)
        violating = next(b for b in wf.branches if b.violations)
        assert "No betrayal" in violating.violations
        assert violating.probability == 0.0

    def test_no_constraints_no_violations(self):
        wf = self._make_wf()
        scored = score_branches(wf)
        assert all(not s.violations for s in scored)

    def test_all_branches_violated_uniform_zero(self):
        b1 = Branch.new(title="Betray A", description="betrayal")
        b2 = Branch.new(title="Betray B", description="betrayal")
        wf = Wavefunction.new(anchor="Test", branches=[b1, b2])
        scored = score_branches(wf, constraints=["No betrayal"])
        assert all(s.probability == 0.0 for s in scored)

    def test_multiple_constraints_all_checked(self):
        b = Branch.new(
            title="Marcus kills and betrays",
            description="Violence and betrayal.",
        )
        wf = Wavefunction.new(
            anchor="Test",
            branches=[b, Branch.new(title="Peace", description="calm")],
        )
        scored = score_branches(wf, constraints=["No betrayal", "No kills"])
        violating = next(s for s in scored if s.violations)
        assert "No betrayal" in violating.violations
        assert "No kills" in violating.violations


# ---------------------------------------------------------------------------
# Explanation includes violations
# ---------------------------------------------------------------------------


class TestConstraintsInExplanation:
    def test_explain_wavefunction_shows_blocked(self):
        b1 = Branch.new(
            title="Alliance holds",
            description="Partnership endures.",
            branch_type="intensification",
        )
        b2 = Branch.new(
            title="Marcus betrays everyone",
            description="A shocking betrayal.",
            branch_type="intensification",
        )
        wf = Wavefunction.new(anchor="Test", branches=[b1, b2])
        scored = score_branches(wf, constraints=["No betrayal"])
        apply_scores(wf, scored)

        result = explain_wavefunction(wf)
        assert "BLOCKED" in result
        assert "No betrayal" in result

    def test_format_lambda_shows_blocked(self):
        b1 = Branch.new(
            title="Alliance holds",
            description="Partnership endures.",
            probability=0.8, score=0.8,
            factors={"tension_gain": 0.5, "novelty": 0.5,
                     "structure_fit": 0.5, "psyke_consistency": 0.5,
                     "goal_alignment": 0.5},
        )
        b2 = Branch.new(
            title="Marcus betrays everyone",
            description="A shocking betrayal.",
            probability=0.0, score=0.0,
            factors={"tension_gain": 0.5, "novelty": 0.5,
                     "structure_fit": 0.5, "psyke_consistency": 0.5,
                     "goal_alignment": 0.5},
        )
        b2.violations = ["No betrayal"]
        wf = Wavefunction.new(anchor="Test", branches=[b1, b2])
        body = _format_lambda(wf)
        assert "BLOCKED" in body
        assert "No betrayal" in body

    def test_format_wavefunction_with_constraints(self, db, project):
        db.add_constraint(project.id, "No betrayal")
        b1 = Branch.new(
            title="Alliance holds",
            description="Partnership endures.",
            branch_type="intensification",
        )
        b2 = Branch.new(
            title="Marcus betrays everyone",
            description="A shocking betrayal.",
            branch_type="intensification",
        )
        wf = Wavefunction.new(anchor="Test", branches=[b1, b2])
        result = _format_wavefunction("Test", wf, db=db, project_id=project.id)
        assert "BLOCKED" in result.body


# ---------------------------------------------------------------------------
# DB persistence
# ---------------------------------------------------------------------------


class TestConstraintPersistence:
    def test_no_constraints_by_default(self, db, project):
        assert db.get_constraints(project.id) == []

    def test_set_and_get(self, db, project):
        db.set_constraints(project.id, ["No betrayal", "No death"])
        assert db.get_constraints(project.id) == ["No betrayal", "No death"]

    def test_add_constraint(self, db, project):
        db.add_constraint(project.id, "No betrayal")
        db.add_constraint(project.id, "No death")
        assert db.get_constraints(project.id) == ["No betrayal", "No death"]

    def test_add_duplicate_ignored(self, db, project):
        db.add_constraint(project.id, "No betrayal")
        db.add_constraint(project.id, "No betrayal")
        assert db.get_constraints(project.id) == ["No betrayal"]

    def test_remove_constraint(self, db, project):
        db.set_constraints(project.id, ["No betrayal", "No death"])
        db.remove_constraint(project.id, "No betrayal")
        assert db.get_constraints(project.id) == ["No death"]

    def test_remove_nonexistent_no_error(self, db, project):
        db.remove_constraint(project.id, "Nonexistent")
        assert db.get_constraints(project.id) == []

    def test_persists_across_instances(self, tmp_path):
        path = str(tmp_path / "c.db")
        db1 = Database(path)
        p = db1.create_project("P")
        db1.add_constraint(p.id, "No betrayal")

        db2 = Database(path)
        assert db2.get_constraints(p.id) == ["No betrayal"]

    def test_per_project_isolation(self, db):
        p1 = db.create_project("A")
        p2 = db.create_project("B")
        db.add_constraint(p1.id, "No betrayal")
        assert db.get_constraints(p1.id) == ["No betrayal"]
        assert db.get_constraints(p2.id) == []

    def test_strips_whitespace_on_add(self, db, project):
        db.add_constraint(project.id, "  No betrayal  ")
        assert db.get_constraints(project.id) == ["No betrayal"]
