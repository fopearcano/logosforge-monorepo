"""Tests for Lambda Mode quantum field output format."""

from unittest.mock import patch

import pytest

from logosforge.db import Database
from logosforge.quantum_outliner import (
    OutlineMode,
    generate_branches,
    generate_outline,
    get_state,
)
from logosforge.quantum_outliner.core import (
    _extract_pov_frames,
    _format_lambda,
    _format_quantum,
    _format_wavefunction,
)
from logosforge.quantum_outliner.psyke_adapter import PsykeSignals
from logosforge.quantum_outliner.state import Branch, StateDelta, Wavefunction, _STATES
from logosforge.quantum_outliner.writing_methods_rag import reload as rag_reload


@pytest.fixture
def db(tmp_path):
    return Database(str(tmp_path / "test.db"))


@pytest.fixture
def project(db):
    return db.create_project("Lambda Output Test")


@pytest.fixture(autouse=True)
def _reset():
    _STATES.clear()
    rag_reload()
    yield
    _STATES.clear()


def _wf_quantum():
    delta = StateDelta(
        character_changes=[{"name": "Alice", "note": "wary"}],
        new_relations=[{"from": "Alice", "to": "Bob"}],
    )
    b1 = Branch.new(
        title="Conflict",
        description="Open hostility breaks out.",
        stakes="Trust",
        consequence="A relationship is severed.",
        state_delta=delta,
    )
    b2 = Branch.new(
        title="Alliance",
        description="An unexpected agreement forms.",
        stakes="Independence",
        consequence="Both sides must compromise.",
    )
    b3 = Branch.new(
        title="Deception",
        description="One side conceals their real intent.",
        stakes="Truth",
        consequence="A future betrayal seeds itself.",
    )
    wf = Wavefunction.new(anchor="Hero meets enemy", branches=[b1, b2, b3])
    wf.effective_mode = "quantum"
    return wf


class TestLambdaFormatHeader:
    def test_has_quantum_field_header(self):
        wf = _wf_quantum()
        body = _format_lambda(wf)
        assert "═══ QUANTUM FIELD ═══" in body

    def test_has_superposition_count(self):
        wf = _wf_quantum()
        body = _format_lambda(wf)
        assert "Superposition: 3 possible futures" in body

    def test_has_wavefunction_id(self):
        wf = _wf_quantum()
        body = _format_lambda(wf)
        assert f"Wavefunction {wf.id}" in body

    def test_has_anchor(self):
        wf = _wf_quantum()
        body = _format_lambda(wf)
        assert "Hero meets enemy" in body


class TestLambdaFormatBranches:
    def test_option_labels_present(self):
        wf = _wf_quantum()
        body = _format_lambda(wf)
        assert "▸ Option 1:" in body
        assert "▸ Option 2:" in body
        assert "▸ Option 3:" in body

    def test_branch_ids_shown(self):
        wf = _wf_quantum()
        body = _format_lambda(wf)
        for b in wf.branches:
            assert f"[{b.id}]" in body

    def test_stakes_shown(self):
        wf = _wf_quantum()
        body = _format_lambda(wf)
        assert "Stakes: Trust" in body
        assert "Stakes: Independence" in body

    def test_consequences_shown(self):
        wf = _wf_quantum()
        body = _format_lambda(wf)
        assert "Consequence: A relationship is severed." in body
        assert "Consequence: Both sides must compromise." in body

    def test_affects_line_when_state_delta(self):
        wf = _wf_quantum()
        body = _format_lambda(wf)
        assert "Affects: Alice" in body

    def test_no_affects_when_no_delta(self):
        b = Branch.new(title="Plain", description="Nothing special.")
        wf = Wavefunction.new(anchor="test", branches=[b])
        body = _format_lambda(wf)
        assert "Affects:" not in body


class TestLambdaFormatUncertainty:
    def test_uncertainty_line_present(self):
        wf = _wf_quantum()
        body = _format_lambda(wf)
        assert "Uncertainty:" in body
        assert "superposition" in body
        assert "collapsed" in body

    def test_uncertainty_count_matches_branches(self):
        wf = _wf_quantum()
        body = _format_lambda(wf)
        assert "3 branches in superposition" in body


class TestLambdaFormatCollapse:
    def test_collapse_instruction_present(self):
        wf = _wf_quantum()
        body = _format_lambda(wf)
        assert "/quantum collapse" in body
        assert wf.id in body

    def test_no_classical_axis(self):
        wf = _wf_quantum()
        body = _format_lambda(wf)
        assert "Classical Axis:" not in body
        assert "Collapse Candidates:" not in body


class TestPOVFrames:
    def test_pov_from_psyke(self):
        psyke = PsykeSignals(
            characters=[
                {"name": "Alice", "notes": "brave"},
                {"name": "Bob", "notes": "cunning"},
            ],
            relations=[],
            unresolved_arcs=[],
            keywords=frozenset({"alice", "bob"}),
        )
        wf = _wf_quantum()
        body = _format_lambda(wf, psyke=psyke)
        assert "POV Frames:" in body
        assert "Alice" in body
        assert "Bob" in body
        assert "/quantum reframe" in body

    def test_pov_from_state_delta(self):
        wf = _wf_quantum()
        body = _format_lambda(wf)
        assert "POV Frames:" in body
        assert "Alice" in body

    def test_no_pov_when_no_characters(self):
        b = Branch.new(title="Plain", description="Nothing.")
        wf = Wavefunction.new(anchor="test", branches=[b])
        body = _format_lambda(wf)
        assert "POV Frames:" not in body

    def test_extract_pov_deduplicates(self):
        psyke = PsykeSignals(
            characters=[{"name": "Alice", "notes": "brave"}],
            relations=[], unresolved_arcs=[],
            keywords=frozenset({"alice"}),
        )
        wf = _wf_quantum()
        names = _extract_pov_frames(wf, psyke)
        assert names.count("Alice") == 1

    def test_extract_pov_limits_to_six(self):
        chars = [{"name": f"Char{i}", "notes": ""} for i in range(10)]
        psyke = PsykeSignals(
            characters=chars, relations=[], unresolved_arcs=[],
            keywords=frozenset(),
        )
        wf = Wavefunction.new(anchor="test", branches=[])
        names = _extract_pov_frames(wf, psyke)
        assert len(names) <= 6


class TestBackwardCompat:
    def test_format_quantum_is_format_lambda(self):
        assert _format_quantum is _format_lambda

    def test_format_quantum_still_works(self):
        wf = _wf_quantum()
        body = _format_quantum(wf)
        assert "Option 1:" in body
        assert "QUANTUM FIELD" in body


class TestLambdaEndToEnd:
    def test_lambda_outline_shows_quantum_field(self, db, project):
        state = get_state(project.id)
        state.outline_mode = OutlineMode.LAMBDA
        state.structure_mode = "quantum"

        with patch(
            "logosforge.quantum_outliner.possibilities.chat_completion"
        ) as mock:
            mock.side_effect = ConnectionError("offline")
            result = generate_outline(
                db, project.id, "A knight discovers a curse.",
            )

        assert result.kind == "possibilities"
        assert "QUANTUM FIELD" in result.body
        assert "Superposition:" in result.body
        assert "Uncertainty:" in result.body

    def test_lambda_branches_shows_quantum_field(self, db, project):
        state = get_state(project.id)
        state.outline_mode = OutlineMode.LAMBDA
        state.structure_mode = "quantum"

        with patch(
            "logosforge.quantum_outliner.possibilities.chat_completion"
        ) as mock:
            mock.side_effect = ConnectionError("offline")
            result = generate_branches(
                db, project.id, "Hero meets enemy",
            )

        assert result.kind == "possibilities"
        assert "QUANTUM FIELD" in result.body
        assert "▸ Option 1:" in result.body
        assert "/quantum collapse" in result.body

    def test_lambda_with_psyke_shows_pov(self, db, project):
        db.create_psyke_entry(project.id, "John", "character", notes="Warrior")
        db.create_psyke_entry(project.id, "Mary", "character", notes="Spy")

        state = get_state(project.id)
        state.outline_mode = OutlineMode.LAMBDA
        state.structure_mode = "quantum"

        with patch(
            "logosforge.quantum_outliner.possibilities.chat_completion"
        ) as mock:
            mock.side_effect = ConnectionError("offline")
            result = generate_branches(
                db, project.id, "Hero meets enemy",
            )

        assert "POV Frames:" in result.body
        assert "John" in result.body
        assert "Mary" in result.body

    def test_lambda_hybrid_shows_gravity(self, db, project):
        state = get_state(project.id)
        state.outline_mode = OutlineMode.LAMBDA
        state.structure_mode = "hybrid"

        with patch(
            "logosforge.quantum_outliner.possibilities.chat_completion"
        ) as mock:
            mock.side_effect = ConnectionError("offline")
            result = generate_branches(
                db, project.id, "Save the Cat midpoint",
            )

        assert "QUANTUM FIELD" in result.body
        assert "Gravity:" in result.body

    def test_classical_mode_still_deterministic(self, db, project):
        state = get_state(project.id)
        state.outline_mode = OutlineMode.CLASSICAL

        result = generate_branches(
            db, project.id, "Save the Cat midpoint",
        )

        assert result.kind == "classical_outline"
        assert "QUANTUM FIELD" not in result.body

    def test_multiple_wavefunctions_in_lambda(self, db, project):
        state = get_state(project.id)
        state.outline_mode = OutlineMode.LAMBDA
        state.structure_mode = "quantum"

        with patch(
            "logosforge.quantum_outliner.possibilities.chat_completion"
        ) as mock:
            mock.side_effect = ConnectionError("offline")
            r1 = generate_branches(db, project.id, "Hero meets enemy")
            r2 = generate_branches(db, project.id, "The village burns")

        assert len(state.active()) == 2
        assert r1.payload["wavefunction_id"] != r2.payload["wavefunction_id"]
        assert "QUANTUM FIELD" in r1.body
        assert "QUANTUM FIELD" in r2.body
