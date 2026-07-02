"""Tests for QuantumGoals model — save/load and defaults."""

import pytest

from logosforge.db import Database
from logosforge.quantum_outliner.scoring import QuantumGoals, _GOAL_OBJECTIVE_KEYS


@pytest.fixture
def db(tmp_path):
    return Database(str(tmp_path / "test.db"))


@pytest.fixture
def project(db):
    return db.create_project("Goals Test")


# ---------------------------------------------------------------------------
# QuantumGoals dataclass defaults
# ---------------------------------------------------------------------------


class TestQuantumGoalsDefaults:
    def test_default_objectives_balanced(self):
        g = QuantumGoals()
        assert set(g.objectives.keys()) == _GOAL_OBJECTIVE_KEYS
        vals = list(g.objectives.values())
        assert all(v == 0.2 for v in vals)

    def test_default_min_constraints_empty(self):
        g = QuantumGoals()
        assert g.min_constraints == {}

    def test_default_horizon_one(self):
        g = QuantumGoals()
        assert g.horizon == 1

    def test_objectives_sum_to_one(self):
        g = QuantumGoals()
        assert abs(sum(g.objectives.values()) - 1.0) < 0.01


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


class TestQuantumGoalsValidation:
    def test_clamps_objectives_to_01(self):
        g = QuantumGoals(objectives={"tension": 2.0, "consistency": -1.0,
                                      "novelty": 0.5, "structure": 0.3,
                                      "character_focus": 0.2})
        g.validate()
        for v in g.objectives.values():
            assert 0.0 <= v <= 1.0

    def test_normalizes_objectives(self):
        g = QuantumGoals(objectives={"tension": 0.8, "consistency": 0.8,
                                      "novelty": 0.8, "structure": 0.8,
                                      "character_focus": 0.8})
        g.validate()
        assert abs(sum(g.objectives.values()) - 1.0) < 0.01

    def test_unknown_keys_removed(self):
        g = QuantumGoals(objectives={"tension": 0.5, "bogus": 0.3,
                                      "consistency": 0.2, "novelty": 0.2,
                                      "structure": 0.2, "character_focus": 0.2})
        g.validate()
        assert "bogus" not in g.objectives
        assert set(g.objectives.keys()) == _GOAL_OBJECTIVE_KEYS

    def test_missing_keys_filled(self):
        g = QuantumGoals(objectives={"tension": 0.5})
        g.validate()
        assert set(g.objectives.keys()) == _GOAL_OBJECTIVE_KEYS

    def test_min_constraints_clamped(self):
        g = QuantumGoals(min_constraints={"psyke_consistency": 1.5, "tension_gain": -0.2})
        g.validate()
        assert g.min_constraints["psyke_consistency"] == 1.0
        assert g.min_constraints["tension_gain"] == 0.0

    def test_horizon_clamped_low(self):
        g = QuantumGoals(horizon=0)
        g.validate()
        assert g.horizon == 1

    def test_horizon_clamped_high(self):
        g = QuantumGoals(horizon=10)
        g.validate()
        assert g.horizon == 3

    def test_horizon_valid_range(self):
        for h in (1, 2, 3):
            g = QuantumGoals(horizon=h)
            g.validate()
            assert g.horizon == h

    def test_validate_returns_self(self):
        g = QuantumGoals()
        assert g.validate() is g


# ---------------------------------------------------------------------------
# DB persistence — get/set
# ---------------------------------------------------------------------------


class TestQuantumGoalsDB:
    def test_default_returned_for_new_project(self, db, project):
        goals = db.get_quantum_goals(project.id)
        assert isinstance(goals, QuantumGoals)
        assert set(goals.objectives.keys()) == _GOAL_OBJECTIVE_KEYS
        assert goals.min_constraints == {}
        assert goals.horizon == 1

    def test_save_and_load(self, db, project):
        goals = QuantumGoals(
            objectives={"tension": 0.4, "consistency": 0.1, "novelty": 0.3,
                        "structure": 0.1, "character_focus": 0.1},
            min_constraints={"psyke_consistency": 0.6},
            horizon=2,
        )
        db.set_quantum_goals(project.id, goals)

        loaded = db.get_quantum_goals(project.id)
        assert loaded.horizon == 2
        assert loaded.min_constraints == {"psyke_consistency": 0.6}
        assert abs(sum(loaded.objectives.values()) - 1.0) < 0.01
        assert loaded.objectives["tension"] > loaded.objectives["consistency"]

    def test_overwrite(self, db, project):
        g1 = QuantumGoals(horizon=2)
        db.set_quantum_goals(project.id, g1)

        g2 = QuantumGoals(horizon=3, min_constraints={"tension_gain": 0.5})
        db.set_quantum_goals(project.id, g2)

        loaded = db.get_quantum_goals(project.id)
        assert loaded.horizon == 3
        assert loaded.min_constraints == {"tension_gain": 0.5}

    def test_does_not_corrupt_other_settings(self, db, project):
        db.set_selection_mode(project.id, "pareto")
        db.set_quantum_goals(project.id, QuantumGoals(horizon=2))
        assert db.get_selection_mode(project.id) == "pareto"

    def test_invalid_data_returns_defaults(self, db, project):
        settings = db.get_project_settings(project.id)
        settings["quantum_goals"] = "not a dict"
        db.save_project_settings(project.id, settings)

        goals = db.get_quantum_goals(project.id)
        assert isinstance(goals, QuantumGoals)
        assert goals.horizon == 1
        assert set(goals.objectives.keys()) == _GOAL_OBJECTIVE_KEYS

    def test_partial_data_filled(self, db, project):
        settings = db.get_project_settings(project.id)
        settings["quantum_goals"] = {"objectives": {"tension": 0.9}, "horizon": 2}
        db.save_project_settings(project.id, settings)

        goals = db.get_quantum_goals(project.id)
        assert goals.horizon == 2
        assert set(goals.objectives.keys()) == _GOAL_OBJECTIVE_KEYS
        assert abs(sum(goals.objectives.values()) - 1.0) < 0.01

    def test_project_isolation(self, db):
        p1 = db.create_project("P1")
        p2 = db.create_project("P2")
        db.set_quantum_goals(p1.id, QuantumGoals(horizon=3))
        db.set_quantum_goals(p2.id, QuantumGoals(horizon=1))

        assert db.get_quantum_goals(p1.id).horizon == 3
        assert db.get_quantum_goals(p2.id).horizon == 1

    def test_validates_on_set(self, db, project):
        goals = QuantumGoals(
            objectives={"tension": 5.0, "consistency": 5.0, "novelty": 5.0,
                        "structure": 5.0, "character_focus": 5.0},
            horizon=99,
        )
        db.set_quantum_goals(project.id, goals)
        loaded = db.get_quantum_goals(project.id)
        assert loaded.horizon == 3
        assert all(0 <= v <= 1.0 for v in loaded.objectives.values())

    def test_validates_on_get(self, db, project):
        settings = db.get_project_settings(project.id)
        settings["quantum_goals"] = {
            "objectives": {"tension": 99, "bogus_key": 1.0},
            "min_constraints": {"x": -5},
            "horizon": 0,
        }
        db.save_project_settings(project.id, settings)

        loaded = db.get_quantum_goals(project.id)
        assert loaded.horizon == 1
        assert "bogus_key" not in loaded.objectives
        assert set(loaded.objectives.keys()) == _GOAL_OBJECTIVE_KEYS
        assert loaded.min_constraints.get("x", 0) == 0.0


# ---------------------------------------------------------------------------
# Import from public API
# ---------------------------------------------------------------------------


class TestQuantumGoalsExport:
    def test_importable_from_package(self):
        from logosforge.quantum_outliner import QuantumGoals as QG
        g = QG()
        assert g.horizon == 1
