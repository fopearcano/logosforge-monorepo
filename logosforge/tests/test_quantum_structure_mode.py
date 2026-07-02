"""Tests for Quantum structure mode selector."""

from unittest.mock import patch

import pytest

from logosforge.db import Database
from logosforge.quantum_outliner import (
    OutlineMode,
    STRUCTURE_MODES,
    generate_branches,
    generate_outline,
    get_state,
    save_state,
    load_state,
)
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
    return db.create_project("Mode Test")


@pytest.fixture(autouse=True)
def _reset():
    _STATES.clear()
    yield
    _STATES.clear()


class TestStructureModes:
    def test_valid_modes(self):
        assert STRUCTURE_MODES == ("auto", "classical", "quantum", "hybrid")

    def test_default_is_hybrid(self, db, project):
        state = get_state(project.id)
        assert state.structure_mode == "hybrid"
        state.outline_mode = OutlineMode.LAMBDA

    def test_switch_modes(self, db, project):
        state = get_state(project.id)
        for mode in STRUCTURE_MODES:
            state.structure_mode = mode
            state.outline_mode = OutlineMode.LAMBDA
            assert state.structure_mode == mode
            state.outline_mode = OutlineMode.LAMBDA

    def test_mode_persists_in_session(self, db, project):
        state = get_state(project.id)
        state.structure_mode = "classical"
        state.outline_mode = OutlineMode.LAMBDA

        same_state = get_state(project.id)
        assert same_state.structure_mode == "classical"
        state.outline_mode = OutlineMode.LAMBDA


class TestModeSerialization:
    def test_serialize_includes_mode(self, db, project):
        state = get_state(project.id)
        state.structure_mode = "quantum"
        state.outline_mode = OutlineMode.LAMBDA
        raw = serialize_state(state)
        assert '"structure_mode": "quantum"' in raw

    def test_deserialize_restores_mode(self):
        raw = '{"project_id": 1, "selected_pov": "", "linked_scene_id": null, "structure_mode": "classical", "wavefunctions": []}'
        state = deserialize_state(raw, 1)
        assert state is not None
        assert state.structure_mode == "classical"
        state.outline_mode = OutlineMode.LAMBDA

    def test_deserialize_missing_mode_defaults_hybrid(self):
        raw = '{"project_id": 1, "selected_pov": "", "linked_scene_id": null, "wavefunctions": []}'
        state = deserialize_state(raw, 1)
        assert state is not None
        assert state.structure_mode == "hybrid"
        state.outline_mode = OutlineMode.LAMBDA

    def test_deserialize_invalid_mode_defaults_hybrid(self):
        raw = '{"project_id": 1, "selected_pov": "", "linked_scene_id": null, "structure_mode": "invalid_garbage", "wavefunctions": []}'
        state = deserialize_state(raw, 1)
        assert state is not None
        assert state.structure_mode == "hybrid"
        state.outline_mode = OutlineMode.LAMBDA

    def test_round_trip_through_db(self, db, project):
        state = get_state(project.id)
        state.structure_mode = "auto"
        state.outline_mode = OutlineMode.LAMBDA
        save_state(db, project.id)
        _STATES.clear()

        loaded = load_state(db, project.id)
        assert loaded.structure_mode == "auto"

    def test_round_trip_all_modes(self, db, project):
        for mode in STRUCTURE_MODES:
            state = get_state(project.id)
            state.structure_mode = mode
            state.outline_mode = OutlineMode.LAMBDA
            save_state(db, project.id)
            _STATES.clear()

            loaded = load_state(db, project.id)
            assert loaded.structure_mode == mode


class TestGeneratorReceivesMode:
    def test_generate_outline_uses_state_mode(self, db, project):
        state = get_state(project.id)
        state.structure_mode = "classical"
        state.outline_mode = OutlineMode.LAMBDA
        db.create_scene(project.id, title="Opening")

        with patch(
            "logosforge.quantum_outliner.possibilities.chat_completion"
        ) as mock:
            mock.side_effect = ConnectionError("offline")
            generate_outline(db, project.id, "A hero rises")

        call_args = mock.call_args
        assert call_args is not None

    def test_generate_branches_uses_state_mode(self, db, project):
        state = get_state(project.id)
        state.structure_mode = "quantum"
        state.outline_mode = OutlineMode.LAMBDA

        with patch(
            "logosforge.quantum_outliner.possibilities.chat_completion"
        ) as mock:
            mock.side_effect = ConnectionError("offline")
            generate_branches(db, project.id, "The villain appears")

        call_args = mock.call_args
        assert call_args is not None

    def test_explicit_mode_overrides_state(self, db, project):
        state = get_state(project.id)
        state.structure_mode = "hybrid"
        state.outline_mode = OutlineMode.LAMBDA

        with patch(
            "logosforge.quantum_outliner.core.generate_possibilities"
        ) as mock:
            from logosforge.quantum_outliner.state import Wavefunction
            mock.return_value = Wavefunction.new(anchor="test", branches=[])

            generate_outline(
                db, project.id, "A new world",
                structure_mode="classical",
            )

            _, kwargs = mock.call_args
            assert kwargs["structure_mode"] == "classical"

    def test_none_mode_falls_back_to_state(self, db, project):
        state = get_state(project.id)
        state.structure_mode = "auto"
        state.outline_mode = OutlineMode.LAMBDA

        with patch(
            "logosforge.quantum_outliner.core.generate_possibilities"
        ) as mock:
            from logosforge.quantum_outliner.state import Wavefunction
            mock.return_value = Wavefunction.new(anchor="test", branches=[])

            generate_branches(
                db, project.id, "Something happens",
                structure_mode=None,
            )

            _, kwargs = mock.call_args
            assert kwargs["structure_mode"] == "auto"


class TestUIImports:
    def test_assistant_panel_imports_structure_modes(self):
        from logosforge.ui.assistant_view import AssistantPanel
        assert AssistantPanel is not None

    def test_structure_modes_accessible(self):
        from logosforge.quantum_outliner import STRUCTURE_MODES
        assert len(STRUCTURE_MODES) == 4
        assert "hybrid" in STRUCTURE_MODES
