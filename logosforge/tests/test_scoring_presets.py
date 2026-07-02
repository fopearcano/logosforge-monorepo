"""Tests for scoring presets — dropdown selection, weight updates, persistence.

Covers:
- All 5 presets produce valid normalized weights
- Selecting a preset updates sliders
- Manual slider tweak switches to Custom
- Preset persists per project
- Switching presets changes branch rankings
"""

import pytest

from PySide6.QtWidgets import QComboBox, QSlider

from logosforge.db import Database
from logosforge.quantum_outliner.scoring import (
    DEFAULT_WEIGHTS,
    PRESET_NAMES,
    SCORING_PRESETS,
    score_branches,
)
from logosforge.quantum_outliner.state import Branch, Wavefunction, _STATES
from logosforge.quantum_outliner.core import _format_wavefunction
from logosforge.ui.quantum_timeline import ScoringWeightsPopover


@pytest.fixture
def db(tmp_path):
    return Database(str(tmp_path / "test.db"))


@pytest.fixture
def project(db):
    return db.create_project("Preset Test")


@pytest.fixture(autouse=True)
def _reset():
    _STATES.clear()
    yield
    _STATES.clear()


def _branch(**kw):
    defaults = {"title": "Test", "description": "Desc"}
    defaults.update(kw)
    return Branch.new(**defaults)


# ---------------------------------------------------------------------------
# Preset definitions
# ---------------------------------------------------------------------------


class TestPresetDefinitions:
    def test_five_presets_exist(self):
        assert len(SCORING_PRESETS) == 5

    def test_preset_names_list_matches(self):
        assert PRESET_NAMES == list(SCORING_PRESETS.keys())

    def test_all_presets_have_five_factors(self):
        for name, weights in SCORING_PRESETS.items():
            assert set(weights.keys()) == set(DEFAULT_WEIGHTS.keys()), name

    def test_all_presets_sum_to_one(self):
        for name, weights in SCORING_PRESETS.items():
            assert abs(sum(weights.values()) - 1.0) < 0.01, name

    def test_balanced_equals_default(self):
        assert SCORING_PRESETS["Balanced"] == DEFAULT_WEIGHTS

    def test_conservative_has_high_structure_and_psyke(self):
        c = SCORING_PRESETS["Conservative"]
        assert c["structure_fit"] >= 0.30
        assert c["psyke_consistency"] >= 0.30

    def test_bold_has_high_novelty_and_tension(self):
        b = SCORING_PRESETS["Bold"]
        assert b["novelty"] >= 0.30
        assert b["tension_gain"] >= 0.30

    def test_character_driven_has_high_psyke_and_goal(self):
        cd = SCORING_PRESETS["Character-driven"]
        assert cd["psyke_consistency"] >= 0.30
        assert cd["goal_alignment"] >= 0.30

    def test_plot_driven_has_high_structure_and_tension(self):
        pd = SCORING_PRESETS["Plot-driven"]
        assert pd["structure_fit"] >= 0.30
        assert pd["tension_gain"] >= 0.30


# ---------------------------------------------------------------------------
# Popover preset dropdown
# ---------------------------------------------------------------------------


class TestPopoverPresetDropdown:
    def test_combo_has_presets_plus_custom(self):
        popover = ScoringWeightsPopover(DEFAULT_WEIGHTS)
        combo = popover.findChild(QComboBox, "weightsPresetCombo")
        assert combo is not None
        items = [combo.itemText(i) for i in range(combo.count())]
        assert items == PRESET_NAMES + ["Custom"]

    def test_initial_preset_selected(self):
        popover = ScoringWeightsPopover(DEFAULT_WEIGHTS, preset="Bold")
        assert popover.get_preset() == "Bold"

    def test_initial_unknown_preset_shows_custom(self):
        popover = ScoringWeightsPopover(DEFAULT_WEIGHTS, preset="Nonexistent")
        assert popover.get_preset() == "Custom"

    def test_selecting_preset_updates_sliders(self):
        popover = ScoringWeightsPopover(DEFAULT_WEIGHTS, preset="Balanced")
        received = []
        popover.weights_changed.connect(received.append)

        combo = popover._preset_combo
        bold_idx = PRESET_NAMES.index("Bold")
        combo.setCurrentIndex(bold_idx)

        assert len(received) == 1
        weights = received[0]
        assert weights == SCORING_PRESETS["Bold"]

        for key, slider in popover._sliders.items():
            expected = int(SCORING_PRESETS["Bold"][key] * 100)
            assert slider.value() == expected

    def test_selecting_preset_emits_preset_changed(self):
        popover = ScoringWeightsPopover(DEFAULT_WEIGHTS, preset="Balanced")
        presets = []
        popover.preset_changed.connect(presets.append)

        combo = popover._preset_combo
        combo.setCurrentIndex(PRESET_NAMES.index("Conservative"))

        assert presets == ["Conservative"]

    def test_manual_slider_switches_to_custom(self):
        popover = ScoringWeightsPopover(
            SCORING_PRESETS["Bold"], preset="Bold",
        )
        presets = []
        popover.preset_changed.connect(presets.append)

        popover._sliders["novelty"].setValue(90)

        assert popover.get_preset() == "Custom"
        assert "Custom" in presets

    def test_reset_returns_to_balanced(self):
        popover = ScoringWeightsPopover(
            SCORING_PRESETS["Bold"], preset="Bold",
        )
        presets = []
        popover.preset_changed.connect(presets.append)

        popover._reset_defaults()

        assert popover.get_preset() == "Balanced"
        assert popover.get_weights() == DEFAULT_WEIGHTS
        assert "Balanced" in presets

    def test_tweak_after_preset_preserves_slider_values(self):
        popover = ScoringWeightsPopover(DEFAULT_WEIGHTS, preset="Balanced")
        popover._preset_combo.setCurrentIndex(PRESET_NAMES.index("Bold"))

        popover._sliders["novelty"].setValue(50)

        w = popover.get_weights()
        assert abs(sum(w.values()) - 1.0) < 0.01
        assert popover.get_preset() == "Custom"


# ---------------------------------------------------------------------------
# DB persistence
# ---------------------------------------------------------------------------


class TestPresetPersistence:
    def test_default_preset_is_balanced(self, db, project):
        assert db.get_scoring_preset(project.id) == "Balanced"

    def test_set_and_get_preset(self, db, project):
        db.set_scoring_preset(project.id, "Bold")
        assert db.get_scoring_preset(project.id) == "Bold"

    def test_preset_persists_across_instances(self, tmp_path):
        path = str(tmp_path / "preset.db")
        db1 = Database(path)
        p = db1.create_project("P")
        db1.set_scoring_preset(p.id, "Character-driven")

        db2 = Database(path)
        assert db2.get_scoring_preset(p.id) == "Character-driven"

    def test_preset_and_weights_stored_together(self, db, project):
        db.set_scoring_preset(project.id, "Bold")
        db.set_scoring_weights(project.id, SCORING_PRESETS["Bold"])

        assert db.get_scoring_preset(project.id) == "Bold"
        assert db.get_scoring_weights(project.id) == SCORING_PRESETS["Bold"]

    def test_per_project_preset_isolation(self, db):
        p1 = db.create_project("A")
        p2 = db.create_project("B")
        db.set_scoring_preset(p1.id, "Bold")

        assert db.get_scoring_preset(p1.id) == "Bold"
        assert db.get_scoring_preset(p2.id) == "Balanced"


# ---------------------------------------------------------------------------
# Switching presets changes rankings
# ---------------------------------------------------------------------------


class TestPresetRankingChanges:
    def _make_branches(self):
        b_tense = Branch.new(
            title="War erupts at the gate",
            description="A desperate fight breaks out suddenly. Fear and danger.",
            stakes="survival of the desperate army",
            consequence="Sacrifice and pain follow the war.",
            branch_type="intensification",
        )
        b_novel = Branch.new(
            title="Crystalline portal opens",
            description="An iridescent shimmer reveals a pathway to an alien dimension.",
            stakes="curiosity",
            consequence="Uncharted territory beckons.",
            branch_type="alternative",
        )
        b_struct = Branch.new(
            title="Midpoint reversal arrives",
            description="The hero's plan collapses in a desperate fight at the midpoint.",
            stakes="everything changes",
            consequence="Must find a new path despite the danger and risk.",
            structure_beat="midpoint reversal",
            structure_method="Save the Cat",
            branch_type="intensification",
        )
        return b_tense, b_novel, b_struct

    def test_bold_favors_tense_and_novel(self, db, project):
        b_tense, b_novel, b_struct = self._make_branches()
        db.set_scoring_weights(project.id, SCORING_PRESETS["Bold"])

        wf = Wavefunction.new(anchor="Fork", branches=[b_tense, b_novel, b_struct])
        result = _format_wavefunction("Test", wf, db=db, project_id=project.id)
        top = result.payload["branches"][0]["title"]
        assert top in ("War erupts at the gate", "Crystalline portal opens")

    def test_conservative_favors_structured(self, db, project):
        b_tense, b_novel, b_struct = self._make_branches()
        db.set_scoring_weights(project.id, SCORING_PRESETS["Conservative"])

        wf = Wavefunction.new(anchor="Fork", branches=[b_tense, b_novel, b_struct])
        wf.structure_beat = "midpoint reversal"
        wf.structure_method = "Save the Cat"

        result = _format_wavefunction("Test", wf, db=db, project_id=project.id)
        top = result.payload["branches"][0]["title"]
        assert top == "Midpoint reversal arrives"

    def test_bold_vs_conservative_different_ranking(self, db, project):
        b_tense, b_novel, b_struct = self._make_branches()

        db.set_scoring_weights(project.id, SCORING_PRESETS["Bold"])
        wf1 = Wavefunction.new(anchor="Fork", branches=[b_tense, b_novel, b_struct])
        wf1.structure_beat = "midpoint reversal"
        wf1.structure_method = "Save the Cat"
        r_bold = _format_wavefunction("Test", wf1, db=db, project_id=project.id)
        bold_ranking = [b["title"] for b in r_bold.payload["branches"]]

        b_t2, b_n2, b_s2 = self._make_branches()
        db.set_scoring_weights(project.id, SCORING_PRESETS["Conservative"])
        wf2 = Wavefunction.new(anchor="Fork", branches=[b_t2, b_n2, b_s2])
        wf2.structure_beat = "midpoint reversal"
        wf2.structure_method = "Save the Cat"
        r_cons = _format_wavefunction("Test", wf2, db=db, project_id=project.id)
        cons_ranking = [b["title"] for b in r_cons.payload["branches"]]

        assert bold_ranking != cons_ranking

    def test_plot_driven_favors_tense_structured(self, db, project):
        b_tense, b_novel, b_struct = self._make_branches()
        db.set_scoring_weights(project.id, SCORING_PRESETS["Plot-driven"])

        wf = Wavefunction.new(anchor="Fork", branches=[b_tense, b_novel, b_struct])
        wf.structure_beat = "midpoint reversal"
        wf.structure_method = "Save the Cat"

        result = _format_wavefunction("Test", wf, db=db, project_id=project.id)
        top = result.payload["branches"][0]["title"]
        assert top == "Midpoint reversal arrives"

    def test_each_preset_produces_valid_probabilities(self, db, project):
        b_tense, b_novel, b_struct = self._make_branches()

        for name, weights in SCORING_PRESETS.items():
            db.set_scoring_weights(project.id, weights)
            bt, bn, bs = self._make_branches()
            wf = Wavefunction.new(anchor="Fork", branches=[bt, bn, bs])
            r = _format_wavefunction("Test", wf, db=db, project_id=project.id)
            probs = [b["probability"] for b in r.payload["branches"]]
            assert abs(sum(probs) - 1.0) < 0.02, f"{name}: sum={sum(probs)}"
            assert probs == sorted(probs, reverse=True), name
