"""Tests for Quantum Outliner persistence — state survives save/load/export/import."""

import json
from unittest.mock import patch

import pytest

from logosforge.db import Database
from logosforge.export import export_json
from logosforge.import_data import import_json, validate_import_data
from logosforge.quantum_outliner import (
    Branch,
    NarrativeState,
    OutlineMode,
    StateDelta,
    Wavefunction,
    collapse_branch,
    generate_branches,
    generate_outline,
    get_state,
    reset_state,
)
from logosforge.quantum_outliner.persistence import (
    export_quantum_state,
    import_quantum_state,
    load_state,
    save_state,
)
from logosforge.quantum_outliner.state import (
    _STATES,
    deserialize_state,
    serialize_state,
)


@pytest.fixture
def db(tmp_path):
    return Database(str(tmp_path / "test.db"))


@pytest.fixture
def project(db):
    return db.create_project("Persistence Test")


@pytest.fixture(autouse=True)
def _reset(project):
    _STATES.clear()
    yield
    _STATES.clear()


# --- Serialization round-trip ---

class TestSerialization:
    def test_empty_state_round_trips(self, project):
        state = NarrativeState(project_id=project.id)
        raw = serialize_state(state)
        restored = deserialize_state(raw, project.id)
        assert restored is not None
        assert restored.project_id == project.id
        assert restored.wavefunctions == {}

    def test_state_with_branches_round_trips(self, project):
        state = NarrativeState(project_id=project.id)
        delta = StateDelta(
            character_changes=[{"name": "Alice", "note": "wary"}],
            new_relations=[{"from": "Alice", "to": "Bob"}],
        )
        b1 = Branch.new(title="Conflict", description="They fight.",
                        stakes="trust", consequence="severed", state_delta=delta)
        b2 = Branch.new(title="Alliance", description="They unite.",
                        stakes="freedom", consequence="joined")
        wf = Wavefunction.new(anchor="Hero meets enemy", branches=[b1, b2])
        state.add(wf)
        state.selected_pov = "Alice"
        state.linked_scene_id = 42

        raw = serialize_state(state)
        restored = deserialize_state(raw, project.id)

        assert restored is not None
        assert len(restored.wavefunctions) == 1
        rwf = list(restored.wavefunctions.values())[0]
        assert rwf.id == wf.id
        assert rwf.anchor == "Hero meets enemy"
        assert len(rwf.branches) == 2
        assert rwf.branches[0].title == "Conflict"
        assert rwf.branches[0].state_delta.character_changes[0]["name"] == "Alice"
        assert restored.selected_pov == "Alice"
        assert restored.linked_scene_id == 42

    def test_collapsed_wavefunction_round_trips(self, project):
        state = NarrativeState(project_id=project.id)
        b = Branch.new(title="X", description="y")
        wf = Wavefunction.new(anchor="test", branches=[b])
        wf.collapsed_branch_id = b.id
        state.add(wf)

        raw = serialize_state(state)
        restored = deserialize_state(raw, project.id)
        rwf = list(restored.wavefunctions.values())[0]
        assert rwf.is_collapsed()
        assert rwf.collapsed_branch_id == b.id

    def test_deserialize_invalid_json(self, project):
        assert deserialize_state("not json", project.id) is None
        assert deserialize_state("", project.id) is None
        assert deserialize_state("null", project.id) is None

    def test_deserialize_ignores_bad_branches(self, project):
        raw = json.dumps({
            "project_id": project.id,
            "wavefunctions": [{
                "id": "abc",
                "anchor": "x",
                "branches": ["not a dict", {"id": "b1", "title": "A", "description": "d"}],
            }],
        })
        restored = deserialize_state(raw, project.id)
        wf = list(restored.wavefunctions.values())[0]
        assert len(wf.branches) == 1


# --- DB persistence ---

class TestDBPersistence:
    def test_save_and_load_state(self, db, project):
        state = get_state(project.id)
        b = Branch.new(title="Conflict", description="They fight.", stakes="honor")
        wf = Wavefunction.new(anchor="Scene 1", branches=[b])
        state.add(wf)

        save_state(db, project.id)
        reset_state(project.id)
        assert project.id not in _STATES

        loaded = load_state(db, project.id)
        assert len(loaded.wavefunctions) == 1
        lwf = list(loaded.wavefunctions.values())[0]
        assert lwf.anchor == "Scene 1"
        assert lwf.branches[0].title == "Conflict"
        assert lwf.branches[0].stakes == "honor"

    def test_load_empty_db_returns_fresh_state(self, db, project):
        loaded = load_state(db, project.id)
        assert loaded.project_id == project.id
        assert loaded.wavefunctions == {}

    def test_save_overwrites_previous(self, db, project):
        state = get_state(project.id)
        wf1 = Wavefunction.new(anchor="first")
        state.add(wf1)
        save_state(db, project.id)

        wf2 = Wavefunction.new(anchor="second")
        state.add(wf2)
        save_state(db, project.id)

        reset_state(project.id)
        loaded = load_state(db, project.id)
        assert len(loaded.wavefunctions) == 2

    def test_save_with_no_state_is_noop(self, db, project):
        reset_state(project.id)
        save_state(db, project.id)
        raw = db.get_quantum_state_json(project.id)
        assert raw == ""

    def test_metadata_persists(self, db, project):
        state = get_state(project.id)
        state.selected_pov = "antagonist"
        state.linked_scene_id = 7
        save_state(db, project.id)

        reset_state(project.id)
        loaded = load_state(db, project.id)
        assert loaded.selected_pov == "antagonist"
        assert loaded.linked_scene_id == 7


# --- Generate + persist cycle ---

class TestGenerateAndPersist:
    def test_generate_save_reload(self, db, project):
        get_state(project.id).outline_mode = OutlineMode.LAMBDA
        with patch(
            "logosforge.quantum_outliner.possibilities.chat_completion"
        ) as mock:
            mock.side_effect = ConnectionError("offline")
            generate_branches(db, project.id, "Hero meets enemy")

        assert len(get_state(project.id).active()) == 1

        save_state(db, project.id)
        wf_id = list(get_state(project.id).wavefunctions.keys())[0]
        reset_state(project.id)

        loaded = load_state(db, project.id)
        assert len(loaded.active()) == 1
        assert wf_id in loaded.wavefunctions
        assert len(loaded.wavefunctions[wf_id].branches) >= 3

    def test_multiple_wavefunctions_persist(self, db, project):
        get_state(project.id).outline_mode = OutlineMode.LAMBDA
        with patch(
            "logosforge.quantum_outliner.possibilities.chat_completion"
        ) as mock:
            mock.side_effect = ConnectionError("offline")
            generate_outline(db, project.id, "A knight discovers a curse.")
            generate_branches(db, project.id, "Hero meets enemy")
            generate_branches(db, project.id, "Scene 3 ending")

        assert len(get_state(project.id).active()) == 3
        save_state(db, project.id)
        reset_state(project.id)

        loaded = load_state(db, project.id)
        assert len(loaded.active()) == 3

    def test_collapse_persists(self, db, project):
        get_state(project.id).outline_mode = OutlineMode.LAMBDA
        with patch(
            "logosforge.quantum_outliner.possibilities.chat_completion"
        ) as mock:
            mock.side_effect = ConnectionError("offline")
            result = generate_branches(db, project.id, "Hero meets enemy")

        wf_id = result.payload["wavefunction_id"]
        branch_id = result.payload["branches"][0]["id"]
        collapse_branch(db, project.id, wf_id, branch_id)
        save_state(db, project.id)

        reset_state(project.id)
        loaded = load_state(db, project.id)
        assert len(loaded.active()) == 0
        assert len(loaded.collapsed()) == 1
        assert loaded.wavefunctions[wf_id].collapsed_branch_id == branch_id


# --- Export/import round-trip ---

class TestExportImport:
    def test_quantum_state_in_export(self, db, project):
        get_state(project.id).outline_mode = OutlineMode.LAMBDA
        with patch(
            "logosforge.quantum_outliner.possibilities.chat_completion"
        ) as mock:
            mock.side_effect = ConnectionError("offline")
            generate_branches(db, project.id, "Hero meets enemy")

        save_state(db, project.id)
        exported = json.loads(export_json(db, project.id))
        assert "quantum_state" in exported
        assert len(exported["quantum_state"]["wavefunctions"]) == 1

    def test_export_without_quantum_state(self, db, project):
        exported = json.loads(export_json(db, project.id))
        assert "quantum_state" not in exported

    def test_import_restores_quantum_state(self, db, project):
        get_state(project.id).outline_mode = OutlineMode.LAMBDA
        with patch(
            "logosforge.quantum_outliner.possibilities.chat_completion"
        ) as mock:
            mock.side_effect = ConnectionError("offline")
            generate_branches(db, project.id, "Hero meets enemy")

        state = get_state(project.id)
        state.selected_pov = "villain"
        save_state(db, project.id)

        exported_json = export_json(db, project.id)
        data, _ = validate_import_data(exported_json)
        assert data is not None

        reset_state(project.id)
        new_pid = import_json(db, data)

        loaded = load_state(db, new_pid)
        assert len(loaded.active()) == 1
        assert loaded.selected_pov == "villain"

    def test_old_project_without_quantum_loads_fine(self, db):
        old_data = {
            "project": {"title": "Old Project", "description": ""},
            "characters": [],
            "places": [],
            "notes": [],
            "scenes": [],
        }
        new_pid = import_json(db, old_data)
        loaded = load_state(db, new_pid)
        assert loaded.wavefunctions == {}

    def test_import_with_corrupt_quantum_data(self, db):
        data = {
            "project": {"title": "Bad QS", "description": ""},
            "characters": [],
            "places": [],
            "notes": [],
            "scenes": [],
            "quantum_state": "not a dict",
        }
        new_pid = import_json(db, data)
        loaded = load_state(db, new_pid)
        assert loaded.wavefunctions == {}


# --- Old DB compatibility ---

class TestOldDBCompat:
    def test_new_table_created_automatically(self, tmp_path):
        db = Database(str(tmp_path / "fresh.db"))
        project = db.create_project("Fresh")
        raw = db.get_quantum_state_json(project.id)
        assert raw == ""

    def test_save_to_new_table(self, tmp_path):
        db = Database(str(tmp_path / "fresh.db"))
        project = db.create_project("Fresh")
        state = get_state(project.id)
        state.add(Wavefunction.new(anchor="test"))
        save_state(db, project.id)

        raw = db.get_quantum_state_json(project.id)
        assert "test" in raw
        reset_state(project.id)
