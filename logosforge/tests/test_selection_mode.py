"""Tests for Weighted vs Pareto selection mode."""

import pytest

from logosforge.db import Database
from logosforge.quantum_outliner.core import _format_lambda, _format_wavefunction
from logosforge.quantum_outliner.scoring import (
    SELECTION_MODES,
    CollapseRecommendation,
    apply_scores,
    format_pareto_recommendation,
    recommend_collapse,
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
    return db.create_project("Selection Mode Test")


def _branch(bid, title, desc="desc", stakes="", consequence="", branch_type="alternative"):
    return Branch(
        id=bid, title=title, description=desc,
        stakes=stakes, consequence=consequence,
        branch_type=branch_type,
    )


def _scored_wf():
    """Create a wavefunction with divergent branches and apply scores."""
    wf = Wavefunction.new(anchor="selection mode test")
    wf.branches = [
        _branch("a", "Tension Path",
                desc="sudden fight danger risk must conflict",
                stakes="desperate sacrifice",
                consequence="war threat"),
        _branch("b", "Novel Path",
                desc="an unexpected twist in a fresh new direction",
                consequence="everything changes"),
        _branch("c", "Calm Path",
                desc="a quiet peaceful stroll through the garden"),
    ]
    scored = score_branches(wf)
    apply_scores(wf, scored)
    wf.branches.sort(key=lambda b: b.probability, reverse=True)
    return wf


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


class TestSelectionModes:
    def test_two_modes(self):
        assert "weighted" in SELECTION_MODES
        assert "pareto" in SELECTION_MODES
        assert len(SELECTION_MODES) == 2


# ---------------------------------------------------------------------------
# DB persistence
# ---------------------------------------------------------------------------


class TestSelectionModePersistence:
    def test_default_is_weighted(self, db, project):
        assert db.get_selection_mode(project.id) == "weighted"

    def test_set_to_pareto(self, db, project):
        db.set_selection_mode(project.id, "pareto")
        assert db.get_selection_mode(project.id) == "pareto"

    def test_set_back_to_weighted(self, db, project):
        db.set_selection_mode(project.id, "pareto")
        db.set_selection_mode(project.id, "weighted")
        assert db.get_selection_mode(project.id) == "weighted"

    def test_invalid_mode_falls_back(self, db, project):
        db.set_selection_mode(project.id, "invalid")
        assert db.get_selection_mode(project.id) == "weighted"

    def test_persists_across_instances(self, tmp_path):
        path = str(tmp_path / "persist.db")
        db1 = Database(path)
        p = db1.create_project("Persist Test")
        db1.set_selection_mode(p.id, "pareto")
        db2 = Database(path)
        assert db2.get_selection_mode(p.id) == "pareto"

    def test_per_project_isolation(self, db):
        p1 = db.create_project("P1")
        p2 = db.create_project("P2")
        db.set_selection_mode(p1.id, "pareto")
        assert db.get_selection_mode(p1.id) == "pareto"
        assert db.get_selection_mode(p2.id) == "weighted"


# ---------------------------------------------------------------------------
# recommend_pareto
# ---------------------------------------------------------------------------


class TestRecommendPareto:
    def test_returns_pareto_optimal_branches(self):
        wf = _scored_wf()
        recs = recommend_pareto(wf)
        assert len(recs) >= 1
        rec_ids = {r.branch_id for r in recs}
        for b in wf.branches:
            if b.is_pareto_optimal and b.probability > 0:
                assert b.id in rec_ids

    def test_max_three_candidates(self):
        wf = _scored_wf()
        recs = recommend_pareto(wf, max_candidates=3)
        assert len(recs) <= 3

    def test_each_has_top_factors(self):
        wf = _scored_wf()
        recs = recommend_pareto(wf)
        for r in recs:
            assert len(r.top_factors) > 0
            assert isinstance(r.top_factors[0], tuple)

    def test_sorted_by_probability(self):
        wf = _scored_wf()
        recs = recommend_pareto(wf)
        if len(recs) >= 2:
            probs = [r.probability for r in recs]
            assert probs == sorted(probs, reverse=True)

    def test_empty_for_unscored_wf(self):
        wf = Wavefunction.new(anchor="empty")
        wf.branches = [_branch("a", "Unscored")]
        recs = recommend_pareto(wf)
        assert recs == []

    def test_excludes_violated_branches(self):
        wf = Wavefunction.new(anchor="constraints")
        wf.branches = [
            _branch("a", "Safe path", desc="a safe journey"),
            _branch("b", "Betrayal path", desc="betrayal and lies"),
        ]
        scored = score_branches(wf, constraints=["No betrayal"])
        apply_scores(wf, scored)
        recs = recommend_pareto(wf)
        rec_ids = {r.branch_id for r in recs}
        assert "b" not in rec_ids


# ---------------------------------------------------------------------------
# format_pareto_recommendation
# ---------------------------------------------------------------------------


class TestFormatParetoRecommendation:
    def test_shows_pareto_header(self):
        wf = _scored_wf()
        recs = recommend_pareto(wf)
        text = format_pareto_recommendation(recs)
        assert "Pareto-optimal candidates:" in text

    def test_shows_bullet_per_candidate(self):
        wf = _scored_wf()
        recs = recommend_pareto(wf)
        text = format_pareto_recommendation(recs)
        bullet_count = text.count("●")
        assert bullet_count == len(recs)

    def test_shows_branch_ids(self):
        wf = _scored_wf()
        recs = recommend_pareto(wf)
        text = format_pareto_recommendation(recs)
        for r in recs:
            assert r.branch_id in text

    def test_empty_shows_fallback(self):
        text = format_pareto_recommendation([])
        assert "No Pareto-optimal candidates" in text


# ---------------------------------------------------------------------------
# Switching mode changes recommendation display
# ---------------------------------------------------------------------------


class TestModeChangesDisplay:
    def test_weighted_shows_recommended(self):
        wf = _scored_wf()
        body = _format_lambda(wf, selection_mode="weighted")
        assert "Recommended:" in body
        assert "Pareto-optimal candidates:" not in body

    def test_pareto_shows_pareto_candidates(self):
        wf = _scored_wf()
        body = _format_lambda(wf, selection_mode="pareto")
        assert "Pareto-optimal candidates:" in body
        assert "●" in body

    def test_pareto_does_not_show_weighted_recommended(self):
        wf = _scored_wf()
        body = _format_lambda(wf, selection_mode="pareto")
        lines = body.split("\n")
        rec_lines = [l for l in lines if l.startswith("Recommended:")]
        assert len(rec_lines) == 0

    def test_weighted_does_not_show_pareto_candidates(self):
        wf = _scored_wf()
        body = _format_lambda(wf, selection_mode="weighted")
        assert "Pareto-optimal candidates:" not in body

    def test_pareto_mode_shows_mode_label(self):
        wf = _scored_wf()
        body = _format_lambda(wf, selection_mode="pareto")
        assert "Mode: Pareto" in body

    def test_weighted_mode_no_mode_label(self):
        wf = _scored_wf()
        body = _format_lambda(wf, selection_mode="weighted")
        assert "Mode: Pareto" not in body


# ---------------------------------------------------------------------------
# Pareto mode groups branches
# ---------------------------------------------------------------------------


class TestParetoGrouping:
    def test_pareto_branches_listed_first(self):
        wf = _scored_wf()
        body = _format_lambda(wf, selection_mode="pareto")
        lines = body.split("\n")
        option_lines = [l for l in lines if l.startswith("▸ Option")]
        pareto_ids = {b.id for b in wf.branches if b.is_pareto_optimal and not b.violations}
        first_non_pareto = None
        last_pareto = None
        for line in option_lines:
            for b in wf.branches:
                if f"[{b.id}]" in line:
                    if b.id in pareto_ids:
                        last_pareto = line
                    elif first_non_pareto is None:
                        first_non_pareto = line
        if first_non_pareto and last_pareto:
            assert option_lines.index(last_pareto) < option_lines.index(first_non_pareto)

    def test_separator_between_groups(self):
        wf = _scored_wf()
        body = _format_lambda(wf, selection_mode="pareto")
        pareto_count = sum(1 for b in wf.branches if b.is_pareto_optimal and not b.violations)
        non_pareto_count = sum(1 for b in wf.branches if not b.is_pareto_optimal or b.violations)
        if pareto_count > 0 and non_pareto_count > 0:
            assert "─ ─ ─" in body

    def test_no_separator_in_weighted_mode(self):
        wf = _scored_wf()
        body = _format_lambda(wf, selection_mode="weighted")
        assert "─ ─ ─" not in body


# ---------------------------------------------------------------------------
# Pareto mode always shows chips and badges
# ---------------------------------------------------------------------------


class TestParetoChipsAlwaysVisible:
    def test_pareto_mode_shows_chips_without_toggle(self):
        wf = _scored_wf()
        body = _format_lambda(wf, selection_mode="pareto", show_tradeoffs=False)
        assert "↑" in body or "↓" in body or "●" in body

    def test_weighted_mode_hides_chips_without_toggle(self):
        wf = _scored_wf()
        body = _format_lambda(wf, selection_mode="weighted", show_tradeoffs=False)
        assert "●" not in body


# ---------------------------------------------------------------------------
# Full pipeline via _format_wavefunction
# ---------------------------------------------------------------------------


class TestFormatWavefunctionSelectionMode:
    def test_weighted_mode_from_db(self, db, project):
        db.set_selection_mode(project.id, "weighted")
        wf = Wavefunction.new(anchor="pipeline test")
        wf.branches = [
            _branch("a", "Tension Path",
                    desc="sudden fight danger risk must conflict",
                    stakes="desperate sacrifice",
                    consequence="war threat"),
            _branch("b", "Calm Path",
                    desc="a quiet peaceful stroll through the garden"),
        ]
        result = _format_wavefunction("Test", wf, db=db, project_id=project.id)
        assert "Recommended:" in result.body
        assert "Pareto-optimal candidates:" not in result.body

    def test_pareto_mode_from_db(self, db, project):
        db.set_selection_mode(project.id, "pareto")
        wf = Wavefunction.new(anchor="pipeline test")
        wf.branches = [
            _branch("a", "Tension Path",
                    desc="sudden fight danger risk must conflict",
                    stakes="desperate sacrifice",
                    consequence="war threat"),
            _branch("b", "Calm Path",
                    desc="a quiet peaceful stroll through the garden"),
        ]
        result = _format_wavefunction("Test", wf, db=db, project_id=project.id)
        assert "Pareto-optimal candidates:" in result.body
        assert "Mode: Pareto" in result.body

    def test_switching_mode_changes_output(self, db, project):
        wf_args = dict(anchor="switch test")
        branches = [
            _branch("a", "Tension Path",
                    desc="sudden fight danger risk must conflict",
                    stakes="desperate sacrifice",
                    consequence="war threat"),
            _branch("b", "Calm Path",
                    desc="a quiet peaceful stroll through the garden"),
        ]

        db.set_selection_mode(project.id, "weighted")
        wf1 = Wavefunction.new(**wf_args)
        wf1.branches = [_branch(b.id, b.title, b.description, b.stakes, b.consequence) for b in branches]
        r1 = _format_wavefunction("Test", wf1, db=db, project_id=project.id)

        db.set_selection_mode(project.id, "pareto")
        wf2 = Wavefunction.new(**wf_args)
        wf2.branches = [_branch(b.id, b.title, b.description, b.stakes, b.consequence) for b in branches]
        r2 = _format_wavefunction("Test", wf2, db=db, project_id=project.id)

        assert "Recommended:" in r1.body
        assert "Pareto-optimal candidates:" in r2.body
        assert r1.body != r2.body
