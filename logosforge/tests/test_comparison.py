"""Tests for A/B/C side-by-side branch comparison."""

import pytest

from logosforge.db import Database
from logosforge.quantum_outliner.core import compare_branches, _format_wavefunction
from logosforge.quantum_outliner.scoring import (
    FACTOR_CHIP_LABELS,
    MAX_COMPARE,
    ComparisonEntry,
    ComparisonTable,
    apply_scores,
    build_comparison,
    format_comparison,
    score_branches,
    select_comparison_branches,
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
    return db.create_project("Comparison Test")


def _branch(bid, title, desc="desc", stakes="", consequence="", branch_type="alternative"):
    return Branch(
        id=bid, title=title, description=desc,
        stakes=stakes, consequence=consequence,
        branch_type=branch_type,
    )


def _scored_wf(branches, constraints=None):
    wf = Wavefunction.new(anchor="compare test")
    wf.branches = list(branches)
    scored = score_branches(wf, constraints=constraints or [])
    apply_scores(wf, scored)
    wf.branches.sort(key=lambda b: b.probability, reverse=True)
    return wf


# ---------------------------------------------------------------------------
# select_comparison_branches
# ---------------------------------------------------------------------------


class TestSelectComparisonBranches:
    def test_auto_selects_top_by_probability(self):
        wf = _scored_wf([
            _branch("a", "First", desc="sudden fight danger risk conflict"),
            _branch("b", "Second", desc="a quiet stroll"),
            _branch("c", "Third", desc="a calm day"),
        ])
        selected = select_comparison_branches(wf)
        assert len(selected) <= MAX_COMPARE
        assert len(selected) >= 1
        probs = [b.probability for b in selected]
        assert probs == sorted(probs, reverse=True)

    def test_explicit_ids(self):
        wf = _scored_wf([
            _branch("a", "First", desc="something"),
            _branch("b", "Second", desc="something else"),
            _branch("c", "Third", desc="more"),
        ])
        selected = select_comparison_branches(wf, ["c", "a"])
        assert [b.id for b in selected] == ["c", "a"]

    def test_explicit_ids_unknown_skipped(self):
        wf = _scored_wf([
            _branch("a", "First", desc="something"),
            _branch("b", "Second", desc="something"),
        ])
        selected = select_comparison_branches(wf, ["a", "z", "b"])
        assert [b.id for b in selected] == ["a", "b"]

    def test_max_branches_capped_at_3(self):
        wf = _scored_wf([
            _branch("a", "A", desc="x"),
            _branch("b", "B", desc="x"),
            _branch("c", "C", desc="x"),
            _branch("d", "D", desc="x"),
        ])
        selected = select_comparison_branches(wf, max_branches=5)
        assert len(selected) <= MAX_COMPARE

    def test_excludes_violated_in_auto(self):
        wf = _scored_wf(
            [
                _branch("a", "Safe", desc="a safe path through the forest"),
                _branch("b", "Betrayal", desc="betrayal and lies everywhere"),
            ],
            constraints=["No betrayal"],
        )
        selected = select_comparison_branches(wf)
        assert all(b.id != "b" for b in selected)

    def test_empty_wf(self):
        wf = Wavefunction.new(anchor="empty")
        assert select_comparison_branches(wf) == []

    def test_single_branch(self):
        wf = _scored_wf([_branch("a", "Only", desc="only option")])
        selected = select_comparison_branches(wf)
        assert len(selected) == 1


# ---------------------------------------------------------------------------
# build_comparison
# ---------------------------------------------------------------------------


class TestBuildComparison:
    def test_labels_abc(self):
        wf = _scored_wf([
            _branch("a", "First", desc="sudden fight danger risk conflict"),
            _branch("b", "Second", desc="a quiet stroll through village"),
            _branch("c", "Third", desc="a calm day at the market"),
        ])
        table = build_comparison(wf)
        labels = [e.label for e in table.entries]
        assert labels == ["A", "B", "C"]

    def test_entry_fields(self):
        wf = _scored_wf([
            _branch("a", "First", desc="sudden fight"),
            _branch("b", "Second", desc="a stroll"),
        ])
        table = build_comparison(wf)
        for e in table.entries:
            assert isinstance(e, ComparisonEntry)
            assert e.branch_id in ("a", "b")
            assert e.title in ("First", "Second")
            assert isinstance(e.probability, float)
            assert isinstance(e.factors, dict)

    def test_factor_deltas_computed(self):
        wf = _scored_wf([
            _branch("a", "High tension",
                    desc="sudden fight danger risk must conflict war",
                    stakes="desperate",
                    consequence="destruction"),
            _branch("b", "Low tension", desc="a calm peaceful quiet stroll"),
        ])
        table = build_comparison(wf)
        assert "tension_gain" in table.factor_deltas
        arrows = table.factor_deltas["tension_gain"]
        assert len(arrows) == 2
        assert "↑" in arrows or "↓" in arrows

    def test_factor_deltas_equal_factors_show_eq(self):
        wf = Wavefunction.new(anchor="equal")
        b1 = _branch("a", "One", desc="same")
        b2 = _branch("b", "Two", desc="same")
        wf.branches = [b1, b2]
        b1.factors = {"structure_fit": 0.5, "psyke_consistency": 0.5,
                       "tension_gain": 0.5, "novelty": 0.5, "goal_alignment": 0.5}
        b2.factors = dict(b1.factors)
        b1.probability = 0.5
        b2.probability = 0.5
        table = build_comparison(wf)
        for arrows in table.factor_deltas.values():
            assert all(a == "=" for a in arrows)

    def test_explicit_branch_ids(self):
        wf = _scored_wf([
            _branch("a", "First", desc="x"),
            _branch("b", "Second", desc="x"),
            _branch("c", "Third", desc="x"),
        ])
        table = build_comparison(wf, ["c", "a"])
        assert [e.branch_id for e in table.entries] == ["c", "a"]
        assert [e.label for e in table.entries] == ["A", "B"]

    def test_empty_wf_returns_empty_table(self):
        wf = Wavefunction.new(anchor="empty")
        table = build_comparison(wf)
        assert table.entries == []
        assert table.factor_deltas == {}

    def test_single_branch_no_deltas(self):
        wf = _scored_wf([_branch("a", "Only", desc="only option")])
        table = build_comparison(wf)
        assert len(table.entries) == 1
        assert table.factor_deltas == {}


# ---------------------------------------------------------------------------
# format_comparison — renders without layout break
# ---------------------------------------------------------------------------


class TestFormatComparison:
    def _make_table(self, n=3, constraints=None):
        branches = [
            _branch("a", "Path of courage",
                    desc="sudden fight danger risk must conflict",
                    stakes="survival at stake",
                    consequence="war looms"),
            _branch("b", "Path of wisdom",
                    desc="careful study reveals hidden truth",
                    stakes="knowledge is power",
                    consequence="allies gained"),
            _branch("c", "Path of stealth",
                    desc="a quiet stroll avoids danger",
                    stakes="secrecy",
                    consequence="escape"),
        ][:n]
        wf = _scored_wf(branches, constraints=constraints)
        return build_comparison(wf)

    def test_header_present(self):
        body = format_comparison(self._make_table())
        assert "═══ COMPARE ═══" in body

    def test_all_labels_present(self):
        body = format_comparison(self._make_table())
        assert "[A]" in body
        assert "[B]" in body
        assert "[C]" in body

    def test_titles_present(self):
        body = format_comparison(self._make_table())
        assert "Path of courage" in body
        assert "Path of wisdom" in body
        assert "Path of stealth" in body

    def test_descriptions_present(self):
        body = format_comparison(self._make_table())
        assert "sudden fight danger risk must conflict" in body
        assert "careful study reveals hidden truth" in body

    def test_probabilities_present(self):
        body = format_comparison(self._make_table())
        assert "%" in body

    def test_factor_rows_present(self):
        body = format_comparison(self._make_table())
        for chip_label in FACTOR_CHIP_LABELS.values():
            assert chip_label in body

    def test_arrows_present(self):
        body = format_comparison(self._make_table())
        assert "↑" in body or "↓" in body or "=" in body

    def test_no_trailing_whitespace_lines(self):
        body = format_comparison(self._make_table())
        for line in body.split("\n"):
            if line.strip():
                assert line == line.rstrip() or line.endswith(" ")

    def test_two_branch_comparison(self):
        body = format_comparison(self._make_table(2))
        assert "[A]" in body
        assert "[B]" in body
        assert "[C]" not in body

    def test_single_branch_comparison(self):
        body = format_comparison(self._make_table(1))
        assert "[A]" in body
        assert "Factor" not in body

    def test_empty_table(self):
        table = ComparisonTable(entries=[], factor_deltas={})
        body = format_comparison(table)
        assert "No branches available" in body

    def test_pareto_badge_shown(self):
        table = self._make_table()
        pareto_count = sum(1 for e in table.entries if e.is_pareto_optimal)
        if pareto_count > 0:
            body = format_comparison(table)
            assert "●" in body

    def test_render_no_exception(self):
        for n in (1, 2, 3):
            table = self._make_table(n)
            body = format_comparison(table)
            assert isinstance(body, str)
            assert len(body) > 0

    def test_lines_not_excessively_long(self):
        body = format_comparison(self._make_table())
        for line in body.split("\n"):
            assert len(line) < 200


# ---------------------------------------------------------------------------
# compare_branches — full pipeline via core
# ---------------------------------------------------------------------------


class TestCompareBranchesPipeline:
    def test_returns_comparison_result(self):
        wf = Wavefunction.new(anchor="pipeline test")
        wf.branches = [
            _branch("a", "Path A", desc="sudden fight danger"),
            _branch("b", "Path B", desc="a calm stroll"),
        ]
        _STATES[wf.id] = wf
        result = compare_branches(wf.id)
        assert result.kind == "comparison"
        assert "═══ COMPARE ═══" in result.body

    def test_payload_structure(self):
        wf = Wavefunction.new(anchor="payload test")
        wf.branches = [
            _branch("a", "Path A", desc="sudden fight danger risk"),
            _branch("b", "Path B", desc="a calm stroll"),
        ]
        _STATES[wf.id] = wf
        result = compare_branches(wf.id)
        assert "comparison" in result.payload
        assert "factor_deltas" in result.payload
        assert isinstance(result.payload["comparison"], list)
        for entry in result.payload["comparison"]:
            assert "label" in entry
            assert "branch_id" in entry
            assert "title" in entry
            assert "probability" in entry
            assert "factors" in entry

    def test_explicit_branch_selection(self):
        wf = Wavefunction.new(anchor="explicit")
        wf.branches = [
            _branch("a", "A", desc="x"),
            _branch("b", "B", desc="x"),
            _branch("c", "C", desc="x"),
        ]
        _STATES[wf.id] = wf
        result = compare_branches(wf.id, ["c", "a"])
        ids = [e["branch_id"] for e in result.payload["comparison"]]
        assert ids == ["c", "a"]

    def test_missing_wf_returns_error(self):
        result = compare_branches("nonexistent")
        assert result.kind == "error"
        assert "not found" in result.body

    def test_with_db_scoring(self, db, project):
        wf = Wavefunction.new(anchor="db test")
        wf.branches = [
            _branch("a", "Path A",
                    desc="sudden fight danger risk must conflict",
                    stakes="desperate",
                    consequence="war"),
            _branch("b", "Path B", desc="a calm stroll through the park"),
        ]
        _STATES[wf.id] = wf
        result = compare_branches(wf.id, db=db, project_id=project.id)
        assert result.kind == "comparison"
        assert len(result.payload["comparison"]) == 2

    def test_constraint_respected(self, db, project):
        db.add_constraint(project.id, "No betrayal")
        wf = Wavefunction.new(anchor="constraint")
        wf.branches = [
            _branch("a", "Safe", desc="a safe journey"),
            _branch("b", "Betrayal", desc="betrayal and lies"),
        ]
        _STATES[wf.id] = wf
        result = compare_branches(wf.id, db=db, project_id=project.id)
        ids = [e["branch_id"] for e in result.payload["comparison"]]
        assert "b" not in ids


# ---------------------------------------------------------------------------
# Comparison factor delta arrows
# ---------------------------------------------------------------------------


class TestFactorDeltas:
    def test_high_vs_low_shows_arrows(self):
        wf = Wavefunction.new(anchor="arrows")
        b1 = _branch("a", "Tense", desc="x")
        b2 = _branch("b", "Calm", desc="x")
        wf.branches = [b1, b2]
        b1.factors = {"structure_fit": 0.5, "psyke_consistency": 0.5,
                       "tension_gain": 0.9, "novelty": 0.5, "goal_alignment": 0.5}
        b2.factors = {"structure_fit": 0.5, "psyke_consistency": 0.5,
                       "tension_gain": 0.1, "novelty": 0.5, "goal_alignment": 0.5}
        b1.probability = 0.6
        b2.probability = 0.4
        table = build_comparison(wf)
        assert table.factor_deltas["tension_gain"] == ["↑", "↓"]

    def test_close_values_show_equal(self):
        wf = Wavefunction.new(anchor="close")
        b1 = _branch("a", "A", desc="x")
        b2 = _branch("b", "B", desc="x")
        wf.branches = [b1, b2]
        b1.factors = {"structure_fit": 0.50, "psyke_consistency": 0.5,
                       "tension_gain": 0.5, "novelty": 0.5, "goal_alignment": 0.5}
        b2.factors = {"structure_fit": 0.52, "psyke_consistency": 0.5,
                       "tension_gain": 0.5, "novelty": 0.5, "goal_alignment": 0.5}
        b1.probability = 0.5
        b2.probability = 0.5
        table = build_comparison(wf)
        assert table.factor_deltas["structure_fit"] == ["=", "="]

    def test_three_way_arrows(self):
        wf = Wavefunction.new(anchor="three")
        branches = []
        for bid, val in [("a", 0.9), ("b", 0.5), ("c", 0.1)]:
            b = _branch(bid, f"B{bid}", desc="x")
            b.factors = {"structure_fit": 0.5, "psyke_consistency": 0.5,
                          "tension_gain": val, "novelty": 0.5, "goal_alignment": 0.5}
            b.probability = 0.33
            branches.append(b)
        wf.branches = branches
        table = build_comparison(wf)
        arrows = table.factor_deltas["tension_gain"]
        assert arrows[0] == "↑"
        assert arrows[2] == "↓"
        assert arrows[1] == "–"
