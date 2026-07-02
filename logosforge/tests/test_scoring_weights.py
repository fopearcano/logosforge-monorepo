"""Tests for user-tunable scoring weights.

Covers:
- DB persistence (get/set per project, fallback to defaults)
- Normalization (sliders normalize to sum=1)
- UI popover (sliders present, values update, reset works)
- Persist after reload
"""

import pytest

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QSlider

from logosforge.db import Database
from logosforge.quantum_outliner.scoring import DEFAULT_WEIGHTS, FACTOR_LABELS
from logosforge.quantum_outliner.state import (
    Branch,
    OutlineMode,
    Wavefunction,
    _STATES,
    get_state,
)
from logosforge.ui.quantum_timeline import (
    QuantumTimelineWidget,
    ScoringWeightsPopover,
)


@pytest.fixture
def db(tmp_path):
    return Database(str(tmp_path / "test.db"))


@pytest.fixture
def project(db):
    return db.create_project("Weights Test")


@pytest.fixture(autouse=True)
def _reset():
    _STATES.clear()
    yield
    _STATES.clear()


def _branch(title="Test", **kw):
    return Branch.new(title=title, description=f"Desc for {title}", **kw)


def _wf(branches, source_scene_id=None):
    return Wavefunction.new(
        anchor="Test", branches=branches, source_scene_id=source_scene_id,
    )


# ---------------------------------------------------------------------------
# DB Persistence
# ---------------------------------------------------------------------------


class TestDBPersistence:
    def test_default_weights_on_fresh_project(self, db, project):
        weights = db.get_scoring_weights(project.id)
        assert weights == DEFAULT_WEIGHTS

    def test_set_and_get_weights(self, db, project):
        custom = {
            "structure_fit": 0.10,
            "psyke_consistency": 0.10,
            "tension_gain": 0.50,
            "novelty": 0.20,
            "goal_alignment": 0.10,
        }
        db.set_scoring_weights(project.id, custom)
        result = db.get_scoring_weights(project.id)
        assert result == custom

    def test_weights_persist_across_db_instances(self, tmp_path):
        path = str(tmp_path / "persist.db")
        db1 = Database(path)
        p = db1.create_project("Persist")
        custom = {
            "structure_fit": 0.40,
            "psyke_consistency": 0.10,
            "tension_gain": 0.10,
            "novelty": 0.30,
            "goal_alignment": 0.10,
        }
        db1.set_scoring_weights(p.id, custom)

        db2 = Database(path)
        result = db2.get_scoring_weights(p.id)
        assert result == custom

    def test_invalid_stored_json_falls_back(self, db, project):
        from sqlmodel import Session
        with Session(db._engine) as session:
            p = session.get(type(project), project.id)
            p.settings_json = "not-json"
            session.commit()

        weights = db.get_scoring_weights(project.id)
        assert weights == DEFAULT_WEIGHTS

    def test_partial_stored_weights_falls_back(self, db, project):
        settings = {"scoring_weights": {"structure_fit": 0.5}}
        db.save_project_settings(project.id, settings)

        weights = db.get_scoring_weights(project.id)
        assert weights == DEFAULT_WEIGHTS

    def test_other_settings_preserved(self, db, project):
        db.save_project_settings(project.id, {"theme": "dark", "other": 42})
        custom = {
            "structure_fit": 0.20,
            "psyke_consistency": 0.20,
            "tension_gain": 0.20,
            "novelty": 0.20,
            "goal_alignment": 0.20,
        }
        db.set_scoring_weights(project.id, custom)

        settings = db.get_project_settings(project.id)
        assert settings["theme"] == "dark"
        assert settings["other"] == 42
        assert settings["scoring_weights"] == custom

    def test_per_project_isolation(self, db):
        p1 = db.create_project("Project A")
        p2 = db.create_project("Project B")
        custom = {
            "structure_fit": 0.50,
            "psyke_consistency": 0.10,
            "tension_gain": 0.10,
            "novelty": 0.10,
            "goal_alignment": 0.20,
        }
        db.set_scoring_weights(p1.id, custom)

        assert db.get_scoring_weights(p1.id) == custom
        assert db.get_scoring_weights(p2.id) == DEFAULT_WEIGHTS


# ---------------------------------------------------------------------------
# Popover Widget
# ---------------------------------------------------------------------------


class TestScoringWeightsPopover:
    def test_has_five_sliders(self):
        popover = ScoringWeightsPopover(DEFAULT_WEIGHTS)
        sliders = popover.findChildren(QSlider)
        assert len(sliders) == 5

    def test_slider_names_match_factors(self):
        popover = ScoringWeightsPopover(DEFAULT_WEIGHTS)
        names = {s.objectName() for s in popover.findChildren(QSlider)}
        expected = {f"weightSlider_{k}" for k in DEFAULT_WEIGHTS}
        assert names == expected

    def test_initial_values_from_weights(self):
        custom = {
            "structure_fit": 0.40,
            "psyke_consistency": 0.10,
            "tension_gain": 0.20,
            "novelty": 0.10,
            "goal_alignment": 0.20,
        }
        popover = ScoringWeightsPopover(custom)
        for key, slider in popover._sliders.items():
            assert slider.value() == int(custom[key] * 100)

    def test_slider_change_normalizes(self):
        popover = ScoringWeightsPopover(DEFAULT_WEIGHTS)
        received = []
        popover.weights_changed.connect(received.append)

        popover._sliders["tension_gain"].setValue(80)

        assert len(received) == 1
        weights = received[0]
        total = sum(weights.values())
        assert abs(total - 1.0) < 0.01

    def test_all_sliders_zero_gives_uniform(self):
        popover = ScoringWeightsPopover(DEFAULT_WEIGHTS)
        received = []
        popover.weights_changed.connect(received.append)

        for slider in popover._sliders.values():
            slider.blockSignals(True)
            slider.setValue(0)
            slider.blockSignals(False)

        popover._sliders["structure_fit"].setValue(1)
        popover._sliders["structure_fit"].setValue(0)

        weights = received[-1]
        assert all(abs(v - 0.2) < 0.01 for v in weights.values())

    def test_get_weights_returns_current(self):
        popover = ScoringWeightsPopover(DEFAULT_WEIGHTS)
        popover._sliders["novelty"].setValue(80)
        weights = popover.get_weights()
        assert weights["novelty"] > DEFAULT_WEIGHTS["novelty"]
        assert abs(sum(weights.values()) - 1.0) < 0.01

    def test_reset_restores_defaults(self):
        popover = ScoringWeightsPopover(DEFAULT_WEIGHTS)
        popover._sliders["tension_gain"].setValue(100)

        received = []
        popover.weights_changed.connect(received.append)
        popover._reset_defaults()

        assert len(received) == 1
        assert received[0] == DEFAULT_WEIGHTS
        for key, slider in popover._sliders.items():
            assert slider.value() == int(DEFAULT_WEIGHTS[key] * 100)

    def test_value_labels_update(self):
        popover = ScoringWeightsPopover(DEFAULT_WEIGHTS)
        popover._sliders["structure_fit"].setValue(50)
        popover._sliders["psyke_consistency"].setValue(50)

        for key, lbl in popover._value_labels.items():
            text = lbl.text()
            assert "%" in text

    def test_tooltips_show_factor_description(self):
        popover = ScoringWeightsPopover(DEFAULT_WEIGHTS)
        labels = [
            lbl for lbl in popover.findChildren(QLabel)
            if lbl.toolTip() and lbl.objectName() not in ("weightsTitle", "weightsValue")
        ]
        tips = {lbl.toolTip() for lbl in labels}
        for desc in FACTOR_LABELS.values():
            assert desc in tips


# ---------------------------------------------------------------------------
# Timeline Integration
# ---------------------------------------------------------------------------


class TestTimelineWeightsButton:
    def test_weights_button_visible_in_lambda(self, db, project):
        scene = db.create_scene(project.id, title="S1")
        state = get_state(project.id)
        state.outline_mode = OutlineMode.LAMBDA
        wf = _wf([_branch("A")], source_scene_id=scene.id)
        state.wavefunctions[wf.id] = wf

        widget = QuantumTimelineWidget(db, project.id)
        widget.refresh()
        assert not widget._weights_btn.isHidden()

    def test_weights_button_hidden_in_classical(self, db, project):
        scene = db.create_scene(project.id, title="S1")
        state = get_state(project.id)
        state.outline_mode = OutlineMode.CLASSICAL
        wf = _wf([_branch("A")], source_scene_id=scene.id)
        state.wavefunctions[wf.id] = wf

        widget = QuantumTimelineWidget(db, project.id)
        widget.refresh()
        assert widget._weights_btn.isHidden()

    def test_weights_button_hidden_when_empty(self, db, project):
        widget = QuantumTimelineWidget(db, project.id)
        widget.refresh()
        assert widget._weights_btn.isHidden()

    def test_popover_saves_to_db(self, db, project):
        widget = QuantumTimelineWidget(db, project.id)
        custom = {
            "structure_fit": 0.30,
            "psyke_consistency": 0.30,
            "tension_gain": 0.10,
            "novelty": 0.10,
            "goal_alignment": 0.20,
        }
        widget._on_weights_changed(custom)

        stored = db.get_scoring_weights(project.id)
        assert stored == custom

    def test_popover_loads_persisted_weights(self, db, project):
        custom = {
            "structure_fit": 0.50,
            "psyke_consistency": 0.10,
            "tension_gain": 0.10,
            "novelty": 0.10,
            "goal_alignment": 0.20,
        }
        db.set_scoring_weights(project.id, custom)

        widget = QuantumTimelineWidget(db, project.id)
        weights = db.get_scoring_weights(project.id)
        popover = ScoringWeightsPopover(weights)

        for key, slider in popover._sliders.items():
            assert slider.value() == int(custom[key] * 100)


# ---------------------------------------------------------------------------
# Slider → weight update round-trip
# ---------------------------------------------------------------------------


class TestSliderRoundTrip:
    def test_adjust_slider_updates_and_persists(self, db, project):
        widget = QuantumTimelineWidget(db, project.id)
        weights = db.get_scoring_weights(project.id)
        popover = ScoringWeightsPopover(weights)
        popover.weights_changed.connect(widget._on_weights_changed)

        popover._sliders["tension_gain"].setValue(80)

        stored = db.get_scoring_weights(project.id)
        assert stored["tension_gain"] > DEFAULT_WEIGHTS["tension_gain"]
        assert abs(sum(stored.values()) - 1.0) < 0.01

    def test_persist_after_reload(self, tmp_path):
        path = str(tmp_path / "reload.db")
        db1 = Database(path)
        p = db1.create_project("Reload Test")

        widget = QuantumTimelineWidget(db1, p.id)
        popover = ScoringWeightsPopover(db1.get_scoring_weights(p.id))
        popover.weights_changed.connect(widget._on_weights_changed)
        popover._sliders["novelty"].setValue(70)

        db2 = Database(path)
        reloaded = db2.get_scoring_weights(p.id)
        assert reloaded["novelty"] > DEFAULT_WEIGHTS["novelty"]
        assert abs(sum(reloaded.values()) - 1.0) < 0.01
