"""Tests for Classical Mode outline generation."""

from unittest.mock import patch

import pytest

from logosforge.db import Database
from logosforge.quantum_outliner import (
    generate_branches,
    generate_outline,
    get_state,
)
from logosforge.quantum_outliner.core import _format_classical, _generate_classical_outline
from logosforge.quantum_outliner.state import OutlineMode, _STATES
from logosforge.quantum_outliner.writing_methods_rag import (
    extract_beats,
    reload as rag_reload,
)


@pytest.fixture
def db(tmp_path):
    return Database(str(tmp_path / "test.db"))


@pytest.fixture
def project(db):
    return db.create_project("Classical Mode Test")


@pytest.fixture(autouse=True)
def _reset():
    _STATES.clear()
    rag_reload()
    yield
    _STATES.clear()


class TestExtractBeats:
    def test_save_the_cat_beats(self):
        snippet = (
            "Beats: Opening Image, Theme Stated, Set-Up, Catalyst, "
            "Debate, Break into Two, B Story, Fun and Games, Midpoint."
        )
        beats = extract_beats(snippet)
        assert "Opening Image" in beats
        assert "Midpoint" in beats
        assert len(beats) >= 8

    def test_stages_label(self):
        snippet = "Stages: Ordinary World, Call to Adventure, Refusal of the Call."
        beats = extract_beats(snippet)
        assert beats[0] == "Ordinary World"
        assert len(beats) == 3

    def test_points_label(self):
        snippet = "Points: Hook (opposite of Resolution), Plot Turn 1, Midpoint."
        beats = extract_beats(snippet)
        assert "Hook (opposite of Resolution)" in beats

    def test_parts_label(self):
        snippet = "Parts: Ki (introduction), Ten (twist), Ketsu (conclusion)."
        beats = extract_beats(snippet)
        assert len(beats) >= 3

    def test_no_label_returns_empty(self):
        snippet = "This method has no labeled beats."
        assert extract_beats(snippet) == []

    def test_empty_string(self):
        assert extract_beats("") == []


class TestFormatClassical:
    def test_has_method_name(self):
        body = _format_classical("Save the Cat", ["Midpoint", "Crisis"], "Act 2")
        assert "Method: Save the Cat" in body

    def test_has_numbered_beats(self):
        body = _format_classical("Hero's Journey", ["Call", "Ordeal", "Return"], "Quest")
        assert "1. Call" in body
        assert "2. Ordeal" in body
        assert "3. Return" in body

    def test_has_anchor(self):
        body = _format_classical("Three-Act", ["Setup"], "My story premise")
        assert "My story premise" in body

    def test_mentions_lambda(self):
        body = _format_classical("X", ["A"], "test")
        assert "Lambda Mode" in body

    def test_no_beats_shows_message(self):
        body = _format_classical("Unknown", [], "test")
        assert "No beats extracted" in body


class TestClassicalOutlineGeneration:
    def test_classical_mode_produces_classical_result(self, db, project):
        state = get_state(project.id)
        state.outline_mode = OutlineMode.CLASSICAL
        result = generate_outline(db, project.id, "Save the Cat story")
        assert result.kind == "classical_outline"
        assert "Method:" in result.body

    def test_classical_outline_has_beats(self, db, project):
        state = get_state(project.id)
        state.outline_mode = OutlineMode.CLASSICAL
        result = generate_outline(db, project.id, "Save the Cat adventure")
        assert "Beats:" in result.body
        assert result.payload.get("structure_method") is not None
        assert len(result.payload.get("beats", [])) > 0

    def test_classical_outline_single_branch(self, db, project):
        state = get_state(project.id)
        state.outline_mode = OutlineMode.CLASSICAL
        result = generate_outline(db, project.id, "Hero's Journey epic")
        wf_id = result.payload.get("wavefunction_id")
        assert wf_id is not None
        wf = state.get(wf_id)
        assert wf is not None
        assert len(wf.branches) == 1

    def test_classical_branch_has_structure_metadata(self, db, project):
        state = get_state(project.id)
        state.outline_mode = OutlineMode.CLASSICAL
        result = generate_outline(db, project.id, "Save the Cat midpoint")
        wf_id = result.payload["wavefunction_id"]
        wf = state.get(wf_id)
        branch = wf.branches[0]
        assert branch.structure_method is not None
        assert wf.structure_method is not None

    def test_classical_outline_deterministic(self, db, project):
        state = get_state(project.id)
        state.outline_mode = OutlineMode.CLASSICAL
        r1 = generate_outline(db, project.id, "Three-Act Structure drama")
        _STATES.clear()
        state2 = get_state(project.id)
        state2.outline_mode = OutlineMode.CLASSICAL
        r2 = generate_outline(db, project.id, "Three-Act Structure drama")
        assert r1.payload["structure_method"] == r2.payload["structure_method"]
        assert r1.payload["beats"] == r2.payload["beats"]

    def test_classical_fallback_when_no_rag_match(self, db, project):
        state = get_state(project.id)
        state.outline_mode = OutlineMode.CLASSICAL
        result = generate_outline(db, project.id, "xyzzy foobar unknown method")
        assert result.kind == "classical_outline"
        assert result.payload.get("structure_method") is not None

    def test_empty_premise_returns_error(self, db, project):
        state = get_state(project.id)
        state.outline_mode = OutlineMode.CLASSICAL
        result = generate_outline(db, project.id, "   ")
        assert result.kind == "error"


class TestClassicalBranches:
    def test_branches_in_classical_mode_produces_outline(self, db, project):
        state = get_state(project.id)
        state.outline_mode = OutlineMode.CLASSICAL
        result = generate_branches(db, project.id, "Save the Cat midpoint")
        assert result.kind == "classical_outline"
        assert "Beats:" in result.body

    def test_branches_empty_situation_returns_error(self, db, project):
        state = get_state(project.id)
        state.outline_mode = OutlineMode.CLASSICAL
        result = generate_branches(db, project.id, "  ")
        assert result.kind == "error"


class TestLambdaModePreserved:
    def test_lambda_mode_generates_wavefunctions(self, db, project):
        state = get_state(project.id)
        state.outline_mode = OutlineMode.LAMBDA

        with patch(
            "logosforge.quantum_outliner.possibilities.chat_completion"
        ) as mock:
            mock.side_effect = ConnectionError("offline")
            result = generate_outline(db, project.id, "Hero's Journey epic")

        assert result.kind == "possibilities"
        assert len(state.active()) == 1
        wf = state.active()[0]
        assert len(wf.branches) >= 3

    def test_lambda_branches_generate_multiple(self, db, project):
        state = get_state(project.id)
        state.outline_mode = OutlineMode.LAMBDA

        with patch(
            "logosforge.quantum_outliner.possibilities.chat_completion"
        ) as mock:
            mock.side_effect = ConnectionError("offline")
            result = generate_branches(db, project.id, "Hero meets enemy")

        assert result.kind == "possibilities"

    def test_classical_vs_lambda_different_output(self, db, project):
        state = get_state(project.id)
        state.outline_mode = OutlineMode.CLASSICAL
        classical = generate_outline(db, project.id, "Save the Cat story")

        _STATES.clear()
        state2 = get_state(project.id)
        state2.outline_mode = OutlineMode.LAMBDA
        with patch(
            "logosforge.quantum_outliner.possibilities.chat_completion"
        ) as mock:
            mock.side_effect = ConnectionError("offline")
            quantum = generate_outline(db, project.id, "Save the Cat story")

        assert classical.kind == "classical_outline"
        assert quantum.kind == "possibilities"


class TestPayloadStructure:
    def test_payload_has_required_fields(self, db, project):
        state = get_state(project.id)
        state.outline_mode = OutlineMode.CLASSICAL
        result = generate_outline(db, project.id, "Save the Cat midpoint")
        assert "structure_method" in result.payload
        assert "beats" in result.payload
        assert "anchor" in result.payload
        assert "wavefunction_id" in result.payload

    def test_beats_are_list_of_strings(self, db, project):
        state = get_state(project.id)
        state.outline_mode = OutlineMode.CLASSICAL
        result = generate_outline(db, project.id, "Hero's Journey quest")
        beats = result.payload["beats"]
        assert isinstance(beats, list)
        assert all(isinstance(b, str) for b in beats)
