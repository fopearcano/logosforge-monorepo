"""Tests for Hybrid Quantum/Classical output format."""

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
    _format_hybrid,
    _format_quantum,
    _format_wavefunction,
    _pick_collapse_candidate,
)
from logosforge.quantum_outliner.state import Branch, Wavefunction, _STATES
from logosforge.quantum_outliner.writing_methods_rag import reload as rag_reload


@pytest.fixture
def db(tmp_path):
    return Database(str(tmp_path / "test.db"))


@pytest.fixture
def project(db):
    return db.create_project("Hybrid Format Test")


@pytest.fixture(autouse=True)
def _reset():
    _STATES.clear()
    rag_reload()
    yield
    _STATES.clear()


def _wf_with_structure():
    b1 = Branch.new(
        title="False Victory",
        description="The hero wins, but the cost is hidden.",
        stakes="Hidden cost of success",
        consequence="Overconfidence leads to Act 3 disaster",
        structure_method="Save the Cat",
        structure_beat="Midpoint",
        branch_type="intensification",
    )
    b2 = Branch.new(
        title="False Defeat",
        description="The hero seems to lose everything.",
        stakes="Morale and trust",
        consequence="Forces a new strategy",
        structure_method="Save the Cat",
        structure_beat="Midpoint",
        branch_type="alternative",
    )
    b3 = Branch.new(
        title="Betrayal Revealed",
        description="An ally switches sides at the worst moment.",
        stakes="Team cohesion",
        consequence="Isolation forces solo action",
        structure_method="Save the Cat",
        structure_beat="Midpoint",
        branch_type="deviation",
    )
    wf = Wavefunction.new(anchor="Midpoint of the heist story", branches=[b1, b2, b3])
    wf.structure_method = "Save the Cat"
    wf.structure_beat = "Midpoint"
    wf.expected_function = "false victory / false defeat"
    wf.effective_mode = "hybrid"
    return wf


def _wf_quantum_only():
    b1 = Branch.new(
        title="Conflict", description="Open hostility.",
        stakes="Trust", consequence="Severed ties",
    )
    b2 = Branch.new(
        title="Alliance", description="Unexpected agreement.",
        stakes="Independence", consequence="Compromise",
    )
    wf = Wavefunction.new(anchor="Hero meets enemy", branches=[b1, b2])
    wf.effective_mode = "quantum"
    return wf


class TestHybridFormat:
    def test_has_three_sections(self):
        wf = _wf_with_structure()
        body = _format_hybrid(wf)
        assert "Classical Axis:" in body
        assert "Quantum Branches:" in body
        assert "Collapse Candidates:" in body

    def test_classical_axis_content(self):
        wf = _wf_with_structure()
        body = _format_hybrid(wf)
        assert "Method: Save the Cat" in body
        assert "Beat: Midpoint" in body
        assert "Function: false victory / false defeat" in body

    def test_branches_listed_with_type(self):
        wf = _wf_with_structure()
        body = _format_hybrid(wf)
        assert "(intensification)" in body
        assert "(alternative)" in body
        assert "(deviation)" in body

    def test_branch_stakes_and_consequence(self):
        wf = _wf_with_structure()
        body = _format_hybrid(wf)
        assert "Stakes:" in body
        assert "Consequence:" in body

    def test_collapse_recommendation_present(self):
        wf = _wf_with_structure()
        body = _format_hybrid(wf)
        assert "Recommended:" in body
        assert "Reason:" in body

    def test_collapse_instruction_at_end(self):
        wf = _wf_with_structure()
        body = _format_hybrid(wf)
        assert "/quantum collapse" in body

    def test_branch_metadata_in_payload(self):
        wf = _wf_with_structure()
        result = _format_wavefunction("Test", wf)
        for b in result.payload["branches"]:
            assert b["structure_method"] == "Save the Cat"
            assert b["structure_beat"] == "Midpoint"
            assert b["branch_type"] is not None


class TestQuantumFormat:
    def test_no_classical_axis(self):
        wf = _wf_quantum_only()
        body = _format_quantum(wf)
        assert "Classical Axis:" not in body
        assert "Collapse Candidates:" not in body

    def test_has_option_labels(self):
        wf = _wf_quantum_only()
        body = _format_quantum(wf)
        assert "Option 1:" in body
        assert "Option 2:" in body

    def test_no_structure_in_payload(self):
        wf = _wf_quantum_only()
        result = _format_wavefunction("Test", wf)
        for b in result.payload["branches"]:
            assert b["structure_method"] is None
            assert b["branch_type"] is None


class TestModeRouting:
    def test_hybrid_mode_shows_gravity(self):
        wf = _wf_with_structure()
        result = _format_wavefunction("Test", wf)
        assert "Gravity: Save the Cat" in result.body
        assert "QUANTUM FIELD" in result.body

    def test_quantum_mode_uses_quantum_format(self):
        wf = _wf_quantum_only()
        result = _format_wavefunction("Test", wf)
        assert "Option 1:" in result.body
        assert "Gravity:" not in result.body

    def test_classical_mode_shows_gravity(self):
        wf = _wf_with_structure()
        wf.effective_mode = "classical"
        result = _format_wavefunction("Test", wf)
        assert "Gravity: Save the Cat" in result.body

    def test_no_structure_method_no_gravity(self):
        wf = _wf_with_structure()
        wf.effective_mode = "hybrid"
        wf.structure_method = None
        wf.structure_beat = None
        result = _format_wavefunction("Test", wf)
        assert "Option 1:" in result.body
        assert "Gravity:" not in result.body


class TestCollapseCandidate:
    def test_recommends_intensification(self):
        wf = _wf_with_structure()
        rec = _pick_collapse_candidate(wf)
        assert rec is not None
        assert rec[0] == "False Victory"
        assert "structural beat" in rec[2]

    def test_recommends_beat_anchored_when_no_intensification(self):
        b1 = Branch.new(
            title="A", description="D",
            structure_beat="Midpoint", branch_type="deviation",
        )
        b2 = Branch.new(title="B", description="D")
        wf = Wavefunction.new(anchor="test", branches=[b1, b2])
        rec = _pick_collapse_candidate(wf)
        assert rec is not None
        assert rec[0] == "A"

    def test_fallback_to_first_branch(self):
        b1 = Branch.new(title="First", description="D")
        b2 = Branch.new(title="Second", description="D")
        wf = Wavefunction.new(anchor="test", branches=[b1, b2])
        rec = _pick_collapse_candidate(wf)
        assert rec is not None
        assert rec[0] == "First"
        assert "first generated" in rec[2]

    def test_empty_branches_returns_none(self):
        wf = Wavefunction.new(anchor="test", branches=[])
        assert _pick_collapse_candidate(wf) is None


class TestEndToEnd:
    def test_hybrid_request_shows_gravity(self, db, project):
        state = get_state(project.id)
        state.outline_mode = OutlineMode.LAMBDA
        state.structure_mode = "hybrid"

        with patch(
            "logosforge.quantum_outliner.possibilities.chat_completion"
        ) as mock:
            mock.side_effect = ConnectionError("offline")
            result = generate_branches(
                db, project.id, "Save the Cat Midpoint scene",
            )

        assert "QUANTUM FIELD" in result.body
        assert "Gravity:" in result.body
        assert "Superposition:" in result.body

    def test_classical_request_shows_gravity(self, db, project):
        state = get_state(project.id)
        state.outline_mode = OutlineMode.LAMBDA
        state.structure_mode = "classical"

        with patch(
            "logosforge.quantum_outliner.possibilities.chat_completion"
        ) as mock:
            mock.side_effect = ConnectionError("offline")
            result = generate_branches(
                db, project.id, "Three-Act Structure midpoint",
            )

        assert "QUANTUM FIELD" in result.body
        assert "Gravity:" in result.body

    def test_quantum_request_has_no_gravity(self, db, project):
        state = get_state(project.id)
        state.outline_mode = OutlineMode.LAMBDA
        state.structure_mode = "quantum"

        with patch(
            "logosforge.quantum_outliner.possibilities.chat_completion"
        ) as mock:
            mock.side_effect = ConnectionError("offline")
            result = generate_branches(db, project.id, "The village burns")

        assert "Option 1:" in result.body
        assert "Gravity:" not in result.body

    def test_outline_hybrid_has_structure(self, db, project):
        state = get_state(project.id)
        state.outline_mode = OutlineMode.LAMBDA
        state.structure_mode = "hybrid"

        with patch(
            "logosforge.quantum_outliner.possibilities.chat_completion"
        ) as mock:
            mock.side_effect = ConnectionError("offline")
            result = generate_outline(
                db, project.id, "Hero's Journey opening act",
            )

        assert "Gravity:" in result.body
        assert result.payload.get("structure_method") is not None

    def test_branch_metadata_present_in_hybrid(self, db, project):
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

        has_method = any(
            b["structure_method"] is not None
            for b in result.payload["branches"]
        )
        assert has_method
