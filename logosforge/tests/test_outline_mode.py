"""Tests for OutlineMode enum and NarrativeState integration."""

import json

import pytest

from logosforge.db import Database
from logosforge.quantum_outliner import (
    OUTLINE_MODES,
    OutlineMode,
    get_outline_mode,
    get_state,
    load_state,
    save_state,
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
    return db.create_project("Outline Mode Test")


@pytest.fixture(autouse=True)
def _reset():
    _STATES.clear()
    yield
    _STATES.clear()


class TestOutlineModeEnum:
    def test_has_classical_and_lambda(self):
        assert OutlineMode.CLASSICAL.value == "classical"
        assert OutlineMode.LAMBDA.value == "lambda"

    def test_is_str_enum(self):
        assert isinstance(OutlineMode.CLASSICAL, str)
        assert OutlineMode.CLASSICAL == "classical"
        assert OutlineMode.LAMBDA == "lambda"

    def test_only_two_values(self):
        assert len(OutlineMode) == 2

    def test_outline_modes_tuple(self):
        assert OUTLINE_MODES == ("classical", "lambda")

    def test_construct_from_string(self):
        assert OutlineMode("classical") is OutlineMode.CLASSICAL
        assert OutlineMode("lambda") is OutlineMode.LAMBDA

    def test_invalid_value_raises(self):
        with pytest.raises(ValueError):
            OutlineMode("invalid")


class TestNarrativeStateDefault:
    def test_default_is_classical(self, project):
        state = get_state(project.id)
        assert state.outline_mode is OutlineMode.CLASSICAL

    def test_get_outline_mode_returns_classical_by_default(self, project):
        assert get_outline_mode(project.id) is OutlineMode.CLASSICAL

    def test_set_to_lambda(self, project):
        state = get_state(project.id)
        state.outline_mode = OutlineMode.LAMBDA
        assert state.outline_mode is OutlineMode.LAMBDA
        assert get_outline_mode(project.id) is OutlineMode.LAMBDA

    def test_set_back_to_classical(self, project):
        state = get_state(project.id)
        state.outline_mode = OutlineMode.LAMBDA
        state.outline_mode = OutlineMode.CLASSICAL
        assert state.outline_mode is OutlineMode.CLASSICAL


class TestSerialization:
    def test_serialize_includes_outline_mode(self, project):
        state = get_state(project.id)
        state.outline_mode = OutlineMode.LAMBDA
        raw = serialize_state(state)
        data = json.loads(raw)
        assert data["outline_mode"] == "lambda"

    def test_serialize_classical_default(self, project):
        state = get_state(project.id)
        raw = serialize_state(state)
        data = json.loads(raw)
        assert data["outline_mode"] == "classical"

    def test_deserialize_classical(self, project):
        raw = json.dumps({
            "project_id": project.id,
            "outline_mode": "classical",
        })
        state = deserialize_state(raw, project.id)
        assert state is not None
        assert state.outline_mode is OutlineMode.CLASSICAL

    def test_deserialize_lambda(self, project):
        raw = json.dumps({
            "project_id": project.id,
            "outline_mode": "lambda",
        })
        state = deserialize_state(raw, project.id)
        assert state is not None
        assert state.outline_mode is OutlineMode.LAMBDA

    def test_deserialize_missing_defaults_to_classical(self, project):
        raw = json.dumps({"project_id": project.id})
        state = deserialize_state(raw, project.id)
        assert state is not None
        assert state.outline_mode is OutlineMode.CLASSICAL

    def test_deserialize_invalid_defaults_to_classical(self, project):
        raw = json.dumps({
            "project_id": project.id,
            "outline_mode": "warp_drive",
        })
        state = deserialize_state(raw, project.id)
        assert state is not None
        assert state.outline_mode is OutlineMode.CLASSICAL

    def test_round_trip(self, project):
        state = get_state(project.id)
        state.outline_mode = OutlineMode.LAMBDA
        raw = serialize_state(state)
        restored = deserialize_state(raw, project.id)
        assert restored is not None
        assert restored.outline_mode is OutlineMode.LAMBDA


class TestPersistence:
    def test_save_load_preserves_outline_mode(self, db, project):
        state = get_state(project.id)
        state.outline_mode = OutlineMode.LAMBDA
        save_state(db, project.id)
        _STATES.clear()

        loaded = load_state(db, project.id)
        assert loaded.outline_mode is OutlineMode.LAMBDA

    def test_save_load_default_classical(self, db, project):
        state = get_state(project.id)
        save_state(db, project.id)
        _STATES.clear()

        loaded = load_state(db, project.id)
        assert loaded.outline_mode is OutlineMode.CLASSICAL

    def test_outline_mode_independent_of_structure_mode(self, db, project):
        state = get_state(project.id)
        state.structure_mode = "quantum"
        state.outline_mode = OutlineMode.LAMBDA
        save_state(db, project.id)
        _STATES.clear()

        loaded = load_state(db, project.id)
        assert loaded.structure_mode == "quantum"
        assert loaded.outline_mode is OutlineMode.LAMBDA


class TestPublicAPI:
    def test_importable_from_package(self):
        from logosforge.quantum_outliner import OutlineMode, OUTLINE_MODES, get_outline_mode
        assert OutlineMode is not None
        assert OUTLINE_MODES is not None
        assert callable(get_outline_mode)

    def test_per_project_isolation(self, db):
        p1 = db.create_project("Project A")
        p2 = db.create_project("Project B")
        get_state(p1.id).outline_mode = OutlineMode.LAMBDA
        assert get_outline_mode(p1.id) is OutlineMode.LAMBDA
        assert get_outline_mode(p2.id) is OutlineMode.CLASSICAL
