"""Tests for decision logging on collapse."""

import pytest

from logosforge.db import Database
from logosforge.quantum_outliner.core import (
    _build_decision_entry,
    _format_decision_log,
    collapse_branch,
    explain_branches,
    get_decision_history,
)
from logosforge.quantum_outliner.scoring import apply_scores, score_branches
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
    return db.create_project("Decision Log Test")


def _branch(bid, title, desc="desc", stakes="", consequence="", branch_type="alternative"):
    return Branch(
        id=bid, title=title, description=desc,
        stakes=stakes, consequence=consequence,
        branch_type=branch_type,
    )


def _scored_wf(branches, constraints=None):
    wf = Wavefunction.new(anchor="log test")
    wf.branches = list(branches)
    scored = score_branches(wf, constraints=constraints or [])
    apply_scores(wf, scored)
    wf.branches.sort(key=lambda b: b.probability, reverse=True)
    return wf


# ---------------------------------------------------------------------------
# DB: decision log persistence
# ---------------------------------------------------------------------------


class TestDecisionLogDB:
    def test_empty_by_default(self, db, project):
        assert db.get_decision_log(project.id) == []

    def test_append_and_retrieve(self, db, project):
        entry = {"chosen_id": "a", "mode": "weighted"}
        db.append_decision(project.id, entry)
        log = db.get_decision_log(project.id)
        assert len(log) == 1
        assert log[0]["chosen_id"] == "a"

    def test_append_multiple(self, db, project):
        db.append_decision(project.id, {"chosen_id": "a"})
        db.append_decision(project.id, {"chosen_id": "b"})
        log = db.get_decision_log(project.id)
        assert len(log) == 2
        assert log[0]["chosen_id"] == "a"
        assert log[1]["chosen_id"] == "b"

    def test_clear(self, db, project):
        db.append_decision(project.id, {"chosen_id": "a"})
        db.clear_decision_log(project.id)
        assert db.get_decision_log(project.id) == []

    def test_persists_across_reads(self, db, project):
        db.append_decision(project.id, {"chosen_id": "x", "probability": 0.75})
        log = db.get_decision_log(project.id)
        assert log[0]["probability"] == 0.75

    def test_does_not_corrupt_other_settings(self, db, project):
        db.set_selection_mode(project.id, "pareto")
        db.append_decision(project.id, {"chosen_id": "a"})
        assert db.get_selection_mode(project.id) == "pareto"


# ---------------------------------------------------------------------------
# _build_decision_entry
# ---------------------------------------------------------------------------


class TestBuildDecisionEntry:
    def test_captures_all_fields(self, db, project):
        wf = _scored_wf([
            _branch("a", "Hero path",
                    desc="sudden fight danger risk must conflict",
                    stakes="desperate",
                    consequence="war threat"),
            _branch("b", "Safe path", desc="a quiet stroll"),
        ])
        _STATES[wf.id] = wf
        chosen = next(b for b in wf.branches if b.id == "a")
        entry = _build_decision_entry(db, project.id, wf.id, chosen)
        assert entry["chosen_id"] == "a"
        assert entry["chosen_title"] == "Hero path"
        assert isinstance(entry["probability"], float)
        assert isinstance(entry["top_factors"], list)
        assert entry["mode"] == "weighted"
        assert entry["wavefunction_id"] == wf.id
        assert "timestamp" in entry

    def test_respects_selection_mode(self, db, project):
        db.set_selection_mode(project.id, "pareto")
        wf = _scored_wf([_branch("a", "A", desc="x")])
        _STATES[wf.id] = wf
        chosen = wf.branches[0]
        entry = _build_decision_entry(db, project.id, wf.id, chosen)
        assert entry["mode"] == "pareto"

    def test_top_factors_capped_at_3(self, db, project):
        wf = _scored_wf([
            _branch("a", "A",
                    desc="sudden fight danger risk must conflict betrayal",
                    stakes="desperate sacrifice",
                    consequence="war threat destruction"),
        ])
        _STATES[wf.id] = wf
        chosen = wf.branches[0]
        entry = _build_decision_entry(db, project.id, wf.id, chosen)
        assert len(entry["top_factors"]) <= 3

    def test_no_factors_empty_list(self, db, project):
        b = _branch("a", "Empty", desc="x")
        entry = _build_decision_entry(db, project.id, "wf1", b)
        assert entry["top_factors"] == []


# ---------------------------------------------------------------------------
# collapse_branch logs decision
# ---------------------------------------------------------------------------


class TestCollapseLogsDecision:
    def test_collapse_creates_log_entry(self, db, project):
        wf = _scored_wf([
            _branch("a", "Chosen",
                    desc="sudden fight danger risk",
                    stakes="high",
                    consequence="aftermath"),
            _branch("b", "Other", desc="a calm day"),
        ])
        _STATES[wf.id] = wf
        from logosforge.quantum_outliner.state import get_state
        state = get_state(project.id)
        state.add(wf)

        result = collapse_branch(db, project.id, wf.id, "a")
        assert result.kind == "collapse"

        log = db.get_decision_log(project.id)
        assert len(log) == 1
        assert log[0]["chosen_id"] == "a"
        assert log[0]["chosen_title"] == "Chosen"
        assert log[0]["mode"] == "weighted"
        assert isinstance(log[0]["probability"], float)
        assert isinstance(log[0]["top_factors"], list)

    def test_collapse_includes_decision_in_payload(self, db, project):
        wf = _scored_wf([
            _branch("a", "A", desc="sudden fight"),
            _branch("b", "B", desc="calm day"),
        ])
        _STATES[wf.id] = wf
        from logosforge.quantum_outliner.state import get_state
        state = get_state(project.id)
        state.add(wf)

        result = collapse_branch(db, project.id, wf.id, "a")
        assert "decision" in result.payload
        assert result.payload["decision"]["chosen_id"] == "a"

    def test_multiple_collapses_accumulate(self, db, project):
        from logosforge.quantum_outliner.state import get_state
        state = get_state(project.id)

        wf1 = _scored_wf([
            _branch("a", "First", desc="sudden fight danger"),
            _branch("b", "Other", desc="calm day"),
        ])
        _STATES[wf1.id] = wf1
        state.add(wf1)
        collapse_branch(db, project.id, wf1.id, "a")

        wf2 = _scored_wf([
            _branch("c", "Second", desc="new adventure risk"),
            _branch("d", "Alt", desc="quiet stroll"),
        ])
        _STATES[wf2.id] = wf2
        state.add(wf2)
        collapse_branch(db, project.id, wf2.id, "c")

        log = db.get_decision_log(project.id)
        assert len(log) == 2
        assert log[0]["chosen_id"] == "a"
        assert log[1]["chosen_id"] == "c"

    def test_collapse_pareto_mode_logged(self, db, project):
        db.set_selection_mode(project.id, "pareto")
        wf = _scored_wf([
            _branch("a", "A", desc="sudden fight"),
            _branch("b", "B", desc="calm day"),
        ])
        _STATES[wf.id] = wf
        from logosforge.quantum_outliner.state import get_state
        state = get_state(project.id)
        state.add(wf)

        collapse_branch(db, project.id, wf.id, "a")
        log = db.get_decision_log(project.id)
        assert log[0]["mode"] == "pareto"

    def test_failed_collapse_no_log(self, db, project):
        result = collapse_branch(db, project.id, "nonexistent", "a")
        assert result.kind == "error"
        assert db.get_decision_log(project.id) == []


# ---------------------------------------------------------------------------
# _format_decision_log
# ---------------------------------------------------------------------------


class TestFormatDecisionLog:
    def test_empty_returns_empty(self):
        assert _format_decision_log([]) == ""

    def test_single_entry(self):
        log = [{
            "chosen_id": "a",
            "chosen_title": "Hero path",
            "probability": 0.75,
            "top_factors": [("tension_gain", 0.9), ("novelty", 0.7)],
            "mode": "weighted",
            "wavefunction_id": "wf1",
        }]
        text = _format_decision_log(log)
        assert "Decision history:" in text
        assert "Hero path" in text
        assert "75%" in text
        assert "weighted" in text
        assert "tension_gain" in text

    def test_filter_by_wf_id(self):
        log = [
            {"wavefunction_id": "wf1", "chosen_title": "A", "probability": 0.5,
             "top_factors": [], "mode": "weighted"},
            {"wavefunction_id": "wf2", "chosen_title": "B", "probability": 0.6,
             "top_factors": [], "mode": "pareto"},
        ]
        text = _format_decision_log(log, wf_id="wf1")
        assert "A" in text
        assert "B" not in text

    def test_no_match_returns_empty(self):
        log = [{"wavefunction_id": "wf1", "chosen_title": "A",
                "probability": 0.5, "top_factors": [], "mode": "weighted"}]
        assert _format_decision_log(log, wf_id="other") == ""

    def test_missing_factors_shows_dash(self):
        log = [{"chosen_title": "X", "probability": 0.5,
                "top_factors": [], "mode": "weighted",
                "wavefunction_id": "wf1"}]
        text = _format_decision_log(log)
        assert "—" in text


# ---------------------------------------------------------------------------
# Visible in explain
# ---------------------------------------------------------------------------


class TestExplainShowsDecisionLog:
    def test_explain_includes_history(self, db, project):
        from logosforge.quantum_outliner.state import get_state
        state = get_state(project.id)

        wf = _scored_wf([
            _branch("a", "Hero path",
                    desc="sudden fight danger risk",
                    stakes="desperate",
                    consequence="war"),
            _branch("b", "Safe path", desc="a calm day"),
        ])
        _STATES[wf.id] = wf
        state.add(wf)
        collapse_branch(db, project.id, wf.id, "a")

        wf2 = _scored_wf([
            _branch("c", "Next choice",
                    desc="new adventure with danger risk",
                    stakes="high",
                    consequence="change"),
            _branch("d", "Alt", desc="quiet day"),
        ])
        _STATES[wf2.id] = wf2
        state.add(wf2)

        result = explain_branches(project.id, wf2.id, db=db)
        assert "Next choice" in result.body
        assert "Decision history:" not in result.body

        result_wf1 = explain_branches(project.id, wf.id, db=db)
        assert "Decision history:" in result_wf1.body
        assert "Hero path" in result_wf1.body

    def test_explain_without_db_still_works(self):
        wf = _scored_wf([
            _branch("a", "A", desc="sudden fight danger"),
            _branch("b", "B", desc="calm day"),
        ])
        from logosforge.quantum_outliner.state import get_state
        state = get_state(999)
        state.add(wf)
        _STATES[wf.id] = wf

        result = explain_branches(999, wf.id)
        assert result.kind == "explain"
        assert "Decision history:" not in result.body

    def test_explain_payload_includes_log(self, db, project):
        from logosforge.quantum_outliner.state import get_state
        state = get_state(project.id)

        wf = _scored_wf([
            _branch("a", "A", desc="sudden fight"),
            _branch("b", "B", desc="calm day"),
        ])
        _STATES[wf.id] = wf
        state.add(wf)
        collapse_branch(db, project.id, wf.id, "a")

        result = explain_branches(project.id, wf.id, db=db)
        assert "decision_log" in result.payload
        assert len(result.payload["decision_log"]) == 1
        assert result.payload["decision_log"][0]["chosen_id"] == "a"


# ---------------------------------------------------------------------------
# get_decision_history
# ---------------------------------------------------------------------------


class TestGetDecisionHistory:
    def test_empty_project(self, db, project):
        result = get_decision_history(db, project.id)
        assert result.kind == "history"
        assert "No decisions recorded" in result.body
        assert result.payload["decision_log"] == []

    def test_with_entries(self, db, project):
        from logosforge.quantum_outliner.state import get_state
        state = get_state(project.id)

        wf = _scored_wf([
            _branch("a", "Chosen",
                    desc="sudden fight danger risk must conflict",
                    stakes="desperate",
                    consequence="war"),
            _branch("b", "Other", desc="a calm day"),
        ])
        _STATES[wf.id] = wf
        state.add(wf)
        collapse_branch(db, project.id, wf.id, "a")

        result = get_decision_history(db, project.id)
        assert result.kind == "history"
        assert "1 collapse" in result.body
        assert "Chosen" in result.body
        assert len(result.payload["decision_log"]) == 1

    def test_multiple_entries(self, db, project):
        from logosforge.quantum_outliner.state import get_state
        state = get_state(project.id)

        for bid, title in [("a", "First"), ("b", "Second")]:
            wf = _scored_wf([
                _branch(bid, title, desc="sudden fight danger"),
                _branch(f"{bid}x", "Alt", desc="calm day"),
            ])
            _STATES[wf.id] = wf
            state.add(wf)
            collapse_branch(db, project.id, wf.id, bid)

        result = get_decision_history(db, project.id)
        assert "2 collapse" in result.body
        assert "First" in result.body
        assert "Second" in result.body
