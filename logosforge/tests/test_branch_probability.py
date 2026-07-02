"""Tests for probability weighting fields on Branch."""

import json

import pytest

from logosforge.db import Database
from logosforge.quantum_outliner import (
    Branch,
    StateDelta,
    Wavefunction,
    get_state,
    reset_state,
)
from logosforge.quantum_outliner.core import _wf_summary
from logosforge.quantum_outliner.persistence import load_state, save_state
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
    return db.create_project("Probability Test")


@pytest.fixture(autouse=True)
def _reset():
    _STATES.clear()
    yield
    _STATES.clear()


class TestBranchFields:
    def test_default_values(self):
        b = Branch.new(title="Test", description="Desc")
        assert b.score == 0.0
        assert b.probability == 0.0
        assert b.factors == {}

    def test_explicit_values(self):
        b = Branch.new(
            title="Conflict",
            description="They fight.",
            score=0.85,
            probability=0.4,
            factors={"tension": 0.6, "character_fit": 0.25},
        )
        assert b.score == 0.85
        assert b.probability == 0.4
        assert b.factors == {"tension": 0.6, "character_fit": 0.25}

    def test_factors_default_is_independent(self):
        b1 = Branch.new(title="A", description="D")
        b2 = Branch.new(title="B", description="D")
        b1.factors["x"] = 1.0
        assert b2.factors == {}

    def test_score_and_probability_are_floats(self):
        b = Branch.new(title="T", description="D", score=1, probability=0)
        assert isinstance(b.score, (int, float))
        assert isinstance(b.probability, (int, float))


class TestSerialization:
    def test_serialize_includes_new_fields(self, project):
        state = get_state(project.id)
        b = Branch.new(
            title="Conflict",
            description="Fight.",
            score=0.72,
            probability=0.35,
            factors={"psyke": 0.4, "structure": 0.32},
        )
        wf = Wavefunction.new(anchor="Test", branches=[b])
        state.add(wf)

        raw = serialize_state(state)
        data = json.loads(raw)

        branch_data = data["wavefunctions"][0]["branches"][0]
        assert branch_data["score"] == 0.72
        assert branch_data["probability"] == 0.35
        assert branch_data["factors"] == {"psyke": 0.4, "structure": 0.32}

    def test_deserialize_with_new_fields(self, project):
        raw = json.dumps({
            "project_id": project.id,
            "wavefunctions": [{
                "id": "wf1",
                "anchor": "Test",
                "branches": [{
                    "id": "b1",
                    "title": "Conflict",
                    "description": "Fight.",
                    "score": 0.9,
                    "probability": 0.45,
                    "factors": {"tension": 0.5, "arc": 0.4},
                }],
            }],
        })
        restored = deserialize_state(raw, project.id)
        b = restored.wavefunctions["wf1"].branches[0]
        assert b.score == 0.9
        assert b.probability == 0.45
        assert b.factors == {"tension": 0.5, "arc": 0.4}

    def test_deserialize_old_data_without_fields(self, project):
        raw = json.dumps({
            "project_id": project.id,
            "wavefunctions": [{
                "id": "wf1",
                "anchor": "Test",
                "branches": [{
                    "id": "b1",
                    "title": "Old Branch",
                    "description": "No score fields.",
                }],
            }],
        })
        restored = deserialize_state(raw, project.id)
        b = restored.wavefunctions["wf1"].branches[0]
        assert b.score == 0.0
        assert b.probability == 0.0
        assert b.factors == {}

    def test_deserialize_invalid_factors(self, project):
        raw = json.dumps({
            "project_id": project.id,
            "wavefunctions": [{
                "id": "wf1",
                "anchor": "Test",
                "branches": [{
                    "id": "b1",
                    "title": "Bad",
                    "description": "D",
                    "factors": "not a dict",
                }],
            }],
        })
        restored = deserialize_state(raw, project.id)
        b = restored.wavefunctions["wf1"].branches[0]
        assert b.factors == {}

    def test_roundtrip_preserves_all(self, project):
        state = get_state(project.id)
        b = Branch.new(
            title="Test",
            description="D",
            score=0.65,
            probability=0.28,
            factors={"a": 0.1, "b": 0.55},
        )
        wf = Wavefunction.new(anchor="RT", branches=[b])
        state.add(wf)

        raw = serialize_state(state)
        restored = deserialize_state(raw, project.id)

        rb = restored.wavefunctions[wf.id].branches[0]
        assert rb.score == 0.65
        assert rb.probability == 0.28
        assert rb.factors == {"a": 0.1, "b": 0.55}


class TestDBPersistence:
    def test_save_load_with_probability(self, db, project):
        state = get_state(project.id)
        b = Branch.new(
            title="Weighted",
            description="D",
            score=0.8,
            probability=0.5,
            factors={"psyke": 0.3, "rag": 0.5},
        )
        wf = Wavefunction.new(anchor="Persist", branches=[b])
        state.add(wf)

        save_state(db, project.id)
        reset_state(project.id)
        loaded = load_state(db, project.id)

        lb = loaded.wavefunctions[wf.id].branches[0]
        assert lb.score == 0.8
        assert lb.probability == 0.5
        assert lb.factors == {"psyke": 0.3, "rag": 0.5}

    def test_old_db_without_fields_loads_clean(self, db, project):
        state = get_state(project.id)
        b = Branch.new(title="Plain", description="D")
        wf = Wavefunction.new(anchor="Old", branches=[b])
        state.add(wf)

        save_state(db, project.id)
        reset_state(project.id)
        loaded = load_state(db, project.id)

        lb = loaded.wavefunctions[wf.id].branches[0]
        assert lb.score == 0.0
        assert lb.probability == 0.0
        assert lb.factors == {}


class TestWfSummaryPayload:
    def test_payload_includes_probability_fields(self):
        b = Branch.new(
            title="Scored",
            description="D",
            score=0.7,
            probability=0.33,
            factors={"tension": 0.7},
        )
        wf = Wavefunction.new(anchor="Test", branches=[b])
        summary = _wf_summary(wf)

        branch_data = summary["branches"][0]
        assert branch_data["score"] == 0.7
        assert branch_data["probability"] == 0.33
        assert branch_data["factors"] == {"tension": 0.7}

    def test_payload_defaults_for_unscored(self):
        b = Branch.new(title="Plain", description="D")
        wf = Wavefunction.new(anchor="Test", branches=[b])
        summary = _wf_summary(wf)

        branch_data = summary["branches"][0]
        assert branch_data["score"] == 0.0
        assert branch_data["probability"] == 0.0
        assert branch_data["factors"] == {}
