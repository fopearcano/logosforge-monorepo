"""Tests for classical structure metadata on Quantum models."""

import json

import pytest

from logosforge.db import Database
from logosforge.quantum_outliner.state import (
    Branch,
    NarrativeState,
    StateDelta,
    Wavefunction,
    _STATES,
    deserialize_state,
    get_state,
    serialize,
    serialize_state,
)
from logosforge.quantum_outliner.persistence import load_state, save_state


@pytest.fixture
def db(tmp_path):
    return Database(str(tmp_path / "test.db"))


@pytest.fixture
def project(db):
    return db.create_project("Structure Metadata Test")


@pytest.fixture(autouse=True)
def _reset():
    _STATES.clear()
    yield
    _STATES.clear()


class TestBranchStructureFields:
    def test_branch_defaults_to_none(self):
        b = Branch.new(title="Test", description="Desc")
        assert b.structure_method is None
        assert b.structure_beat is None
        assert b.branch_type is None

    def test_branch_accepts_structure_fields(self):
        b = Branch.new(
            title="Midpoint Twist",
            description="Everything changes",
            structure_method="Save the Cat",
            structure_beat="Midpoint",
            branch_type="deviation",
        )
        assert b.structure_method == "Save the Cat"
        assert b.structure_beat == "Midpoint"
        assert b.branch_type == "deviation"

    def test_branch_type_values(self):
        for btype in ("deviation", "alternative", "intensification", "resolution"):
            b = Branch.new(title="T", description="D", branch_type=btype)
            assert b.branch_type == btype

    def test_branch_serializes_with_structure_fields(self):
        b = Branch.new(
            title="Hero Departs",
            description="Crossing the threshold",
            structure_method="Hero's Journey",
            structure_beat="Crossing the First Threshold",
            branch_type="intensification",
        )
        wf = Wavefunction.new(anchor="Test", branches=[b])
        raw = json.loads(serialize(wf))
        branch_data = raw["branches"][0]
        assert branch_data["structure_method"] == "Hero's Journey"
        assert branch_data["structure_beat"] == "Crossing the First Threshold"
        assert branch_data["branch_type"] == "intensification"

    def test_branch_serializes_none_fields(self):
        b = Branch.new(title="Plain", description="No structure")
        wf = Wavefunction.new(anchor="Test", branches=[b])
        raw = json.loads(serialize(wf))
        branch_data = raw["branches"][0]
        assert branch_data["structure_method"] is None
        assert branch_data["structure_beat"] is None
        assert branch_data["branch_type"] is None


class TestWavefunctionStructureFields:
    def test_wavefunction_defaults_to_none(self):
        wf = Wavefunction.new(anchor="Test")
        assert wf.structure_method is None
        assert wf.structure_beat is None
        assert wf.expected_function is None

    def test_wavefunction_accepts_structure_fields(self):
        wf = Wavefunction(
            id="abc",
            anchor="Act II begins",
            structure_method="Three-Act Structure",
            structure_beat="Act II",
            expected_function="escalation",
        )
        assert wf.structure_method == "Three-Act Structure"
        assert wf.structure_beat == "Act II"
        assert wf.expected_function == "escalation"

    def test_wavefunction_serializes_with_structure_fields(self):
        wf = Wavefunction(
            id="xyz",
            anchor="The Twist",
            structure_method="Kishōtenketsu",
            structure_beat="Ten",
            expected_function="recontextualize",
        )
        raw = json.loads(serialize(wf))
        assert raw["structure_method"] == "Kishōtenketsu"
        assert raw["structure_beat"] == "Ten"
        assert raw["expected_function"] == "recontextualize"


class TestBackwardCompatibility:
    def test_deserialize_old_branch_without_fields(self):
        old_data = json.dumps({
            "project_id": 1,
            "selected_pov": "",
            "linked_scene_id": None,
            "wavefunctions": [{
                "id": "wf01",
                "anchor": "Old story",
                "branches": [{
                    "id": "br01",
                    "title": "Old branch",
                    "description": "No structure fields",
                    "stakes": "low",
                    "consequence": "",
                    "state_delta": {
                        "character_changes": [],
                        "new_relations": [],
                        "arc_updates": [],
                        "notes": "",
                    },
                }],
                "collapsed_branch_id": None,
                "created_at": 1000000.0,
                "source_scene_id": None,
                "source_scene_order": None,
                "target_scene_id": None,
            }],
        })

        state = deserialize_state(old_data, 1)
        assert state is not None
        wf = list(state.wavefunctions.values())[0]
        branch = wf.branches[0]

        assert branch.structure_method is None
        assert branch.structure_beat is None
        assert branch.branch_type is None
        assert wf.structure_method is None
        assert wf.structure_beat is None
        assert wf.expected_function is None

    def test_deserialize_new_branch_with_fields(self):
        new_data = json.dumps({
            "project_id": 1,
            "selected_pov": "",
            "linked_scene_id": None,
            "wavefunctions": [{
                "id": "wf02",
                "anchor": "New story",
                "branches": [{
                    "id": "br02",
                    "title": "Structured branch",
                    "description": "Has metadata",
                    "stakes": "high",
                    "consequence": "war",
                    "state_delta": {
                        "character_changes": [],
                        "new_relations": [],
                        "arc_updates": [],
                        "notes": "",
                    },
                    "structure_method": "Save the Cat",
                    "structure_beat": "All Is Lost",
                    "branch_type": "resolution",
                }],
                "collapsed_branch_id": None,
                "created_at": 2000000.0,
                "source_scene_id": 5,
                "source_scene_order": 4,
                "target_scene_id": None,
                "structure_method": "Save the Cat",
                "structure_beat": "Break into Three",
                "expected_function": "synthesis",
            }],
        })

        state = deserialize_state(new_data, 1)
        assert state is not None
        wf = list(state.wavefunctions.values())[0]
        branch = wf.branches[0]

        assert branch.structure_method == "Save the Cat"
        assert branch.structure_beat == "All Is Lost"
        assert branch.branch_type == "resolution"
        assert wf.structure_method == "Save the Cat"
        assert wf.structure_beat == "Break into Three"
        assert wf.expected_function == "synthesis"


class TestPersistenceRoundTrip:
    def test_save_and_reload_with_structure_fields(self, db, project):
        state = get_state(project.id)
        b = Branch.new(
            title="Catalyst",
            description="The event that changes everything",
            structure_method="Save the Cat",
            structure_beat="Catalyst",
            branch_type="deviation",
        )
        wf = Wavefunction.new(anchor="Opening act", branches=[b])
        wf.structure_method = "Save the Cat"
        wf.structure_beat = "Set-Up"
        wf.expected_function = "establish normal world"
        state.add(wf)

        save_state(db, project.id)
        _STATES.clear()

        loaded = load_state(db, project.id)
        assert len(loaded.wavefunctions) == 1
        loaded_wf = list(loaded.wavefunctions.values())[0]
        loaded_branch = loaded_wf.branches[0]

        assert loaded_branch.structure_method == "Save the Cat"
        assert loaded_branch.structure_beat == "Catalyst"
        assert loaded_branch.branch_type == "deviation"
        assert loaded_wf.structure_method == "Save the Cat"
        assert loaded_wf.structure_beat == "Set-Up"
        assert loaded_wf.expected_function == "establish normal world"

    def test_save_and_reload_without_structure_fields(self, db, project):
        state = get_state(project.id)
        b = Branch.new(title="Plain", description="No metadata")
        wf = Wavefunction.new(anchor="Unstructured", branches=[b])
        state.add(wf)

        save_state(db, project.id)
        _STATES.clear()

        loaded = load_state(db, project.id)
        loaded_wf = list(loaded.wavefunctions.values())[0]
        loaded_branch = loaded_wf.branches[0]

        assert loaded_branch.structure_method is None
        assert loaded_branch.structure_beat is None
        assert loaded_branch.branch_type is None
        assert loaded_wf.structure_method is None
        assert loaded_wf.structure_beat is None
        assert loaded_wf.expected_function is None

    def test_mixed_branches_persist_correctly(self, db, project):
        state = get_state(project.id)
        b1 = Branch.new(
            title="Structured",
            description="Has fields",
            structure_method="Hero's Journey",
            structure_beat="Ordeal",
            branch_type="intensification",
        )
        b2 = Branch.new(title="Plain", description="No fields")
        wf = Wavefunction.new(anchor="Mixed", branches=[b1, b2])
        state.add(wf)

        save_state(db, project.id)
        _STATES.clear()

        loaded = load_state(db, project.id)
        loaded_wf = list(loaded.wavefunctions.values())[0]

        assert loaded_wf.branches[0].structure_method == "Hero's Journey"
        assert loaded_wf.branches[0].structure_beat == "Ordeal"
        assert loaded_wf.branches[0].branch_type == "intensification"
        assert loaded_wf.branches[1].structure_method is None
        assert loaded_wf.branches[1].structure_beat is None
        assert loaded_wf.branches[1].branch_type is None


class TestSerializeState:
    def test_full_state_round_trip(self):
        state = NarrativeState(project_id=99)
        b = Branch.new(
            title="Final Battle",
            description="Climax",
            structure_method="Seven-Point Story Structure",
            structure_beat="Resolution",
            branch_type="resolution",
        )
        wf = Wavefunction.new(anchor="Endgame", branches=[b])
        wf.structure_method = "Seven-Point Story Structure"
        wf.structure_beat = "Pinch 2"
        wf.expected_function = "darkest moment"
        state.add(wf)

        raw = serialize_state(state)
        restored = deserialize_state(raw, 99)
        assert restored is not None

        r_wf = list(restored.wavefunctions.values())[0]
        r_branch = r_wf.branches[0]

        assert r_branch.structure_method == "Seven-Point Story Structure"
        assert r_branch.structure_beat == "Resolution"
        assert r_branch.branch_type == "resolution"
        assert r_wf.structure_method == "Seven-Point Story Structure"
        assert r_wf.structure_beat == "Pinch 2"
        assert r_wf.expected_function == "darkest moment"
