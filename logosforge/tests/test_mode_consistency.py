"""Tests for mode-switching consistency — no data loss across toggles."""

from unittest.mock import patch

import pytest

from logosforge.db import Database
from logosforge.quantum_outliner import (
    Branch,
    OutlineMode,
    StateDelta,
    Wavefunction,
    collapse_branch,
    generate_branches,
    generate_outline,
    get_state,
    reset_state,
)
from logosforge.quantum_outliner.persistence import load_state, save_state
from logosforge.quantum_outliner.state import (
    NarrativeState,
    _STATES,
    deserialize_state,
    serialize_state,
)


@pytest.fixture
def db(tmp_path):
    return Database(str(tmp_path / "test.db"))


@pytest.fixture
def project(db):
    return db.create_project("Mode Consistency Test")


@pytest.fixture(autouse=True)
def _reset():
    _STATES.clear()
    yield
    _STATES.clear()


def _generate_lambda_branches(db, project_id, situation):
    with patch(
        "logosforge.quantum_outliner.possibilities.chat_completion"
    ) as mock:
        mock.side_effect = ConnectionError("offline")
        return generate_branches(db, project_id, situation)


# --- Core: mode switch preserves wavefunctions ---


class TestModeSwitchPreservesData:
    def test_lambda_branches_survive_switch_to_classical(self, db, project):
        state = get_state(project.id)
        state.outline_mode = OutlineMode.LAMBDA

        result = _generate_lambda_branches(db, project.id, "Hero meets enemy")
        wf_id = result.payload["wavefunction_id"]
        branch_count = len(result.payload["branches"])

        state.outline_mode = OutlineMode.CLASSICAL

        assert wf_id in state.wavefunctions
        assert len(state.wavefunctions[wf_id].branches) == branch_count

    def test_classical_outline_survives_switch_to_lambda(self, db, project):
        state = get_state(project.id)
        state.outline_mode = OutlineMode.CLASSICAL

        result = generate_branches(db, project.id, "Save the Cat midpoint")
        wf_id = result.payload["wavefunction_id"]

        state.outline_mode = OutlineMode.LAMBDA

        assert wf_id in state.wavefunctions

    def test_collapsed_branch_survives_mode_switch(self, db, project):
        state = get_state(project.id)
        state.outline_mode = OutlineMode.LAMBDA

        result = _generate_lambda_branches(db, project.id, "Hero meets enemy")
        wf_id = result.payload["wavefunction_id"]
        branch_id = result.payload["branches"][0]["id"]

        collapse_branch(db, project.id, wf_id, branch_id)

        assert state.wavefunctions[wf_id].collapsed_branch_id == branch_id

        state.outline_mode = OutlineMode.CLASSICAL
        assert state.wavefunctions[wf_id].collapsed_branch_id == branch_id

        state.outline_mode = OutlineMode.LAMBDA
        assert state.wavefunctions[wf_id].collapsed_branch_id == branch_id

    def test_multiple_wavefunctions_survive_toggle(self, db, project):
        state = get_state(project.id)
        state.outline_mode = OutlineMode.LAMBDA

        r1 = _generate_lambda_branches(db, project.id, "Hero meets enemy")
        r2 = _generate_lambda_branches(db, project.id, "The village burns")
        r3 = _generate_lambda_branches(db, project.id, "A betrayal unfolds")

        wf_ids = {
            r1.payload["wavefunction_id"],
            r2.payload["wavefunction_id"],
            r3.payload["wavefunction_id"],
        }
        assert len(wf_ids) == 3

        state.outline_mode = OutlineMode.CLASSICAL
        assert set(state.wavefunctions.keys()) == wf_ids

        state.outline_mode = OutlineMode.LAMBDA
        assert set(state.wavefunctions.keys()) == wf_ids

    def test_state_delta_survives_mode_switch(self, db, project):
        state = get_state(project.id)
        state.outline_mode = OutlineMode.LAMBDA

        delta = StateDelta(
            character_changes=[{"name": "Alice", "note": "wary"}],
            new_relations=[{"from": "Alice", "to": "Bob"}],
        )
        b = Branch.new(
            title="Conflict", description="Fight.", state_delta=delta,
        )
        wf = Wavefunction.new(anchor="Test", branches=[b])
        state.add(wf)

        state.outline_mode = OutlineMode.CLASSICAL
        restored_branch = state.wavefunctions[wf.id].branches[0]
        assert restored_branch.state_delta.character_changes[0]["name"] == "Alice"
        assert restored_branch.state_delta.new_relations[0]["from"] == "Alice"

        state.outline_mode = OutlineMode.LAMBDA
        assert restored_branch.state_delta.character_changes[0]["name"] == "Alice"


class TestRepeatedToggling:
    def test_ten_toggles_no_data_loss(self, db, project):
        state = get_state(project.id)
        state.outline_mode = OutlineMode.LAMBDA

        result = _generate_lambda_branches(db, project.id, "Hero meets enemy")
        wf_id = result.payload["wavefunction_id"]
        branch_ids = [b["id"] for b in result.payload["branches"]]

        for i in range(10):
            if i % 2 == 0:
                state.outline_mode = OutlineMode.CLASSICAL
            else:
                state.outline_mode = OutlineMode.LAMBDA

            assert wf_id in state.wavefunctions
            current_ids = [b.id for b in state.wavefunctions[wf_id].branches]
            assert current_ids == branch_ids

    def test_toggle_with_save_load_cycle(self, db, project):
        state = get_state(project.id)
        state.outline_mode = OutlineMode.LAMBDA

        result = _generate_lambda_branches(db, project.id, "Hero meets enemy")
        wf_id = result.payload["wavefunction_id"]
        branch_ids = [b["id"] for b in result.payload["branches"]]

        for mode in [OutlineMode.CLASSICAL, OutlineMode.LAMBDA, OutlineMode.CLASSICAL]:
            current = get_state(project.id)
            current.outline_mode = mode
            save_state(db, project.id)
            reset_state(project.id)
            loaded = load_state(db, project.id)

            assert loaded.outline_mode is mode
            assert wf_id in loaded.wavefunctions
            assert [b.id for b in loaded.wavefunctions[wf_id].branches] == branch_ids

    def test_toggle_with_generation_between(self, db, project):
        state = get_state(project.id)
        state.outline_mode = OutlineMode.LAMBDA

        r1 = _generate_lambda_branches(db, project.id, "Hero meets enemy")
        wf1 = r1.payload["wavefunction_id"]

        state.outline_mode = OutlineMode.CLASSICAL
        r2 = generate_branches(db, project.id, "Save the Cat midpoint")
        wf2 = r2.payload["wavefunction_id"]

        state.outline_mode = OutlineMode.LAMBDA
        r3 = _generate_lambda_branches(db, project.id, "The village burns")
        wf3 = r3.payload["wavefunction_id"]

        assert wf1 in state.wavefunctions
        assert wf2 in state.wavefunctions
        assert wf3 in state.wavefunctions
        assert len(state.wavefunctions) == 3


class TestPersistenceAcrossRestart:
    def test_mode_persists_to_db(self, db, project):
        state = get_state(project.id)
        state.outline_mode = OutlineMode.LAMBDA
        save_state(db, project.id)

        reset_state(project.id)
        loaded = load_state(db, project.id)
        assert loaded.outline_mode is OutlineMode.LAMBDA

    def test_classical_mode_persists_to_db(self, db, project):
        state = get_state(project.id)
        state.outline_mode = OutlineMode.CLASSICAL
        save_state(db, project.id)

        reset_state(project.id)
        loaded = load_state(db, project.id)
        assert loaded.outline_mode is OutlineMode.CLASSICAL

    def test_full_state_survives_save_load_in_lambda(self, db, project):
        state = get_state(project.id)
        state.outline_mode = OutlineMode.LAMBDA

        result = _generate_lambda_branches(db, project.id, "Hero meets enemy")
        wf_id = result.payload["wavefunction_id"]
        branch_id = result.payload["branches"][0]["id"]

        collapse_branch(db, project.id, wf_id, branch_id)

        save_state(db, project.id)
        reset_state(project.id)
        loaded = load_state(db, project.id)

        assert loaded.outline_mode is OutlineMode.LAMBDA
        assert wf_id in loaded.wavefunctions
        assert loaded.wavefunctions[wf_id].collapsed_branch_id == branch_id
        assert len(loaded.wavefunctions[wf_id].branches) >= 3

    def test_full_state_survives_save_load_in_classical(self, db, project):
        state = get_state(project.id)
        state.outline_mode = OutlineMode.LAMBDA

        result = _generate_lambda_branches(db, project.id, "Hero meets enemy")
        wf_id = result.payload["wavefunction_id"]

        state.outline_mode = OutlineMode.CLASSICAL
        save_state(db, project.id)
        reset_state(project.id)
        loaded = load_state(db, project.id)

        assert loaded.outline_mode is OutlineMode.CLASSICAL
        assert wf_id in loaded.wavefunctions
        assert len(loaded.wavefunctions[wf_id].branches) >= 3

    def test_serialization_roundtrip_preserves_all(self, db, project):
        state = get_state(project.id)
        state.outline_mode = OutlineMode.LAMBDA
        state.selected_pov = "villain"
        state.linked_scene_id = 42

        b = Branch.new(
            title="Conflict", description="Fight.",
            stakes="Trust", consequence="Severed",
            structure_method="Save the Cat", structure_beat="Midpoint",
            branch_type="intensification",
            state_delta=StateDelta(
                character_changes=[{"name": "Alice", "note": "wary"}],
            ),
        )
        wf = Wavefunction.new(anchor="Test", branches=[b])
        wf.structure_method = "Save the Cat"
        wf.structure_beat = "Midpoint"
        wf.effective_mode = "hybrid"
        state.add(wf)

        raw = serialize_state(state)
        restored = deserialize_state(raw, project.id)

        assert restored.outline_mode is OutlineMode.LAMBDA
        assert restored.selected_pov == "villain"
        assert restored.linked_scene_id == 42

        rwf = restored.wavefunctions[wf.id]
        assert rwf.structure_method == "Save the Cat"
        assert rwf.structure_beat == "Midpoint"
        assert rwf.effective_mode == "hybrid"
        assert rwf.branches[0].structure_method == "Save the Cat"
        assert rwf.branches[0].branch_type == "intensification"
        assert rwf.branches[0].state_delta.character_changes[0]["name"] == "Alice"


class TestOutputConsistency:
    def test_lambda_output_has_quantum_field(self, db, project):
        state = get_state(project.id)
        state.outline_mode = OutlineMode.LAMBDA

        result = _generate_lambda_branches(db, project.id, "Hero meets enemy")
        assert result.kind == "possibilities"
        assert "QUANTUM FIELD" in result.body

    def test_classical_output_has_classical_outline(self, db, project):
        state = get_state(project.id)
        state.outline_mode = OutlineMode.CLASSICAL

        result = generate_branches(db, project.id, "Save the Cat midpoint")
        assert result.kind == "classical_outline"
        assert "Classical Outline" in result.body

    def test_switch_changes_output_kind(self, db, project):
        state = get_state(project.id)

        state.outline_mode = OutlineMode.LAMBDA
        r1 = _generate_lambda_branches(db, project.id, "Hero meets enemy")
        assert r1.kind == "possibilities"

        state.outline_mode = OutlineMode.CLASSICAL
        r2 = generate_branches(db, project.id, "Save the Cat midpoint")
        assert r2.kind == "classical_outline"

        state.outline_mode = OutlineMode.LAMBDA
        r3 = _generate_lambda_branches(db, project.id, "The village burns")
        assert r3.kind == "possibilities"

    def test_active_wavefunctions_visible_in_both_modes(self, db, project):
        state = get_state(project.id)
        state.outline_mode = OutlineMode.LAMBDA

        _generate_lambda_branches(db, project.id, "Hero meets enemy")
        assert len(state.active()) == 1

        state.outline_mode = OutlineMode.CLASSICAL
        assert len(state.active()) == 1

        state.outline_mode = OutlineMode.LAMBDA
        assert len(state.active()) == 1


class TestEdgeCases:
    def test_empty_state_toggle(self, db, project):
        state = get_state(project.id)
        assert state.wavefunctions == {}

        state.outline_mode = OutlineMode.LAMBDA
        assert state.wavefunctions == {}

        state.outline_mode = OutlineMode.CLASSICAL
        assert state.wavefunctions == {}

    def test_collapsed_and_active_coexist_across_toggle(self, db, project):
        state = get_state(project.id)
        state.outline_mode = OutlineMode.LAMBDA

        r1 = _generate_lambda_branches(db, project.id, "Hero meets enemy")
        wf1 = r1.payload["wavefunction_id"]
        b1 = r1.payload["branches"][0]["id"]
        collapse_branch(db, project.id, wf1, b1)

        r2 = _generate_lambda_branches(db, project.id, "The village burns")
        wf2 = r2.payload["wavefunction_id"]

        assert len(state.collapsed()) == 1
        assert len(state.active()) == 1

        state.outline_mode = OutlineMode.CLASSICAL
        assert len(state.collapsed()) == 1
        assert len(state.active()) == 1

        state.outline_mode = OutlineMode.LAMBDA
        assert len(state.collapsed()) == 1
        assert len(state.active()) == 1

    def test_default_mode_is_classical(self, db, project):
        state = get_state(project.id)
        assert state.outline_mode is OutlineMode.CLASSICAL

    def test_fresh_load_no_crash(self, db, project):
        loaded = load_state(db, project.id)
        assert loaded.outline_mode is OutlineMode.CLASSICAL
        assert loaded.wavefunctions == {}

        loaded.outline_mode = OutlineMode.LAMBDA
        save_state(db, project.id)

    def test_mode_independent_of_structure_mode(self, db, project):
        state = get_state(project.id)
        state.outline_mode = OutlineMode.LAMBDA
        state.structure_mode = "quantum"

        _generate_lambda_branches(db, project.id, "Hero meets enemy")

        state.outline_mode = OutlineMode.CLASSICAL
        assert state.structure_mode == "quantum"

        state.outline_mode = OutlineMode.LAMBDA
        assert state.structure_mode == "quantum"
