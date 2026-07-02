"""Tests for beat-phase weight biasing.

Covers:
- Beat-to-phase mapping
- Phase multiplier application and renormalization
- Same branches at different beats → different ranking
- Unknown beats pass through unchanged
- Bias composes with user presets
"""

import pytest

from logosforge.db import Database
from logosforge.quantum_outliner.scoring import (
    BEAT_PHASE_MAP,
    DEFAULT_WEIGHTS,
    PHASE_MULTIPLIERS,
    SCORING_PRESETS,
    apply_beat_bias,
    get_beat_phase,
    score_branches,
)
from logosforge.quantum_outliner.core import _format_wavefunction
from logosforge.quantum_outliner.state import Branch, Wavefunction, _STATES


@pytest.fixture
def db(tmp_path):
    return Database(str(tmp_path / "test.db"))


@pytest.fixture
def project(db):
    return db.create_project("Beat Bias Test")


@pytest.fixture(autouse=True)
def _reset():
    _STATES.clear()
    yield
    _STATES.clear()


# ---------------------------------------------------------------------------
# Beat-to-phase mapping
# ---------------------------------------------------------------------------


class TestBeatPhaseMapping:
    def test_midpoint_maps_to_midpoint(self):
        assert get_beat_phase("Midpoint") == "midpoint"

    def test_all_is_lost_maps_to_crisis(self):
        assert get_beat_phase("All Is Lost") == "crisis"

    def test_setup_maps_to_setup(self):
        assert get_beat_phase("Set-Up") == "setup"

    def test_catalyst_maps_to_catalyst(self):
        assert get_beat_phase("Catalyst") == "catalyst"

    def test_finale_maps_to_climax(self):
        assert get_beat_phase("Finale") == "climax"

    def test_final_image_maps_to_resolution(self):
        assert get_beat_phase("Final Image") == "resolution"

    def test_fun_and_games_maps_to_development(self):
        assert get_beat_phase("Fun and Games") == "development"

    def test_case_insensitive(self):
        assert get_beat_phase("MIDPOINT") == "midpoint"
        assert get_beat_phase("all is lost") == "crisis"

    def test_strips_whitespace(self):
        assert get_beat_phase("  Midpoint  ") == "midpoint"

    def test_none_returns_none(self):
        assert get_beat_phase(None) is None

    def test_empty_returns_none(self):
        assert get_beat_phase("") is None

    def test_unknown_beat_returns_none(self):
        assert get_beat_phase("Completely Unknown Beat") is None

    def test_all_mapped_beats_resolve_to_known_phase(self):
        known_phases = set(PHASE_MULTIPLIERS.keys())
        for beat, phase in BEAT_PHASE_MAP.items():
            assert phase in known_phases, f"{beat} → {phase} not in phases"


# ---------------------------------------------------------------------------
# Multiplier application and normalization
# ---------------------------------------------------------------------------


class TestApplyBeatBias:
    def test_unknown_beat_returns_original(self):
        result = apply_beat_bias(DEFAULT_WEIGHTS, "Unknown Beat XYZ")
        assert result == DEFAULT_WEIGHTS

    def test_none_beat_returns_original(self):
        result = apply_beat_bias(DEFAULT_WEIGHTS, None)
        assert result == DEFAULT_WEIGHTS

    def test_biased_weights_sum_to_one(self):
        for phase in PHASE_MULTIPLIERS:
            beat = next(b for b, p in BEAT_PHASE_MAP.items() if p == phase)
            result = apply_beat_bias(DEFAULT_WEIGHTS, beat)
            assert abs(sum(result.values()) - 1.0) < 0.01, phase

    def test_midpoint_boosts_tension(self):
        result = apply_beat_bias(DEFAULT_WEIGHTS, "Midpoint")
        assert result["tension_gain"] > DEFAULT_WEIGHTS["tension_gain"]

    def test_midpoint_boosts_novelty(self):
        result = apply_beat_bias(DEFAULT_WEIGHTS, "Midpoint")
        assert result["novelty"] > DEFAULT_WEIGHTS["novelty"]

    def test_setup_boosts_structure_fit(self):
        result = apply_beat_bias(DEFAULT_WEIGHTS, "Set-Up")
        assert result["structure_fit"] > DEFAULT_WEIGHTS["structure_fit"]

    def test_crisis_boosts_psyke_and_goal(self):
        result = apply_beat_bias(DEFAULT_WEIGHTS, "All Is Lost")
        assert result["psyke_consistency"] > DEFAULT_WEIGHTS["psyke_consistency"]
        assert result["goal_alignment"] > DEFAULT_WEIGHTS["goal_alignment"]

    def test_climax_boosts_tension_and_structure(self):
        result = apply_beat_bias(DEFAULT_WEIGHTS, "Finale")
        assert result["tension_gain"] > DEFAULT_WEIGHTS["tension_gain"]
        assert result["structure_fit"] > DEFAULT_WEIGHTS["structure_fit"]

    def test_resolution_boosts_goal_alignment(self):
        result = apply_beat_bias(DEFAULT_WEIGHTS, "Final Image")
        assert result["goal_alignment"] > DEFAULT_WEIGHTS["goal_alignment"]

    def test_catalyst_boosts_novelty(self):
        result = apply_beat_bias(DEFAULT_WEIGHTS, "Catalyst")
        assert result["novelty"] > DEFAULT_WEIGHTS["novelty"]

    def test_development_boosts_psyke_and_goal(self):
        result = apply_beat_bias(DEFAULT_WEIGHTS, "Fun and Games")
        assert result["psyke_consistency"] > DEFAULT_WEIGHTS["psyke_consistency"]
        assert result["goal_alignment"] > DEFAULT_WEIGHTS["goal_alignment"]

    def test_bias_is_modest(self):
        for phase in PHASE_MULTIPLIERS:
            beat = next(b for b, p in BEAT_PHASE_MAP.items() if p == phase)
            result = apply_beat_bias(DEFAULT_WEIGHTS, beat)
            for k in DEFAULT_WEIGHTS:
                ratio = result[k] / DEFAULT_WEIGHTS[k] if DEFAULT_WEIGHTS[k] > 0 else 1.0
                assert 0.5 < ratio < 2.0, f"{phase}/{k}: ratio={ratio:.2f}"

    def test_composes_with_preset(self):
        bold = SCORING_PRESETS["Bold"]
        result = apply_beat_bias(bold, "Midpoint")
        assert abs(sum(result.values()) - 1.0) < 0.01
        assert result["tension_gain"] > bold["tension_gain"]


# ---------------------------------------------------------------------------
# Same branches, different beats → different ranking
# ---------------------------------------------------------------------------


class TestBeatChangesRanking:
    def _make_branches(self):
        b_mid = Branch.new(
            title="The reversal hits hard",
            description="A sudden twist changes everything at this critical juncture.",
            stakes="survival",
            consequence="New direction forced by conflict.",
            branch_type="intensification",
            structure_beat="Midpoint",
        )
        b_setup = Branch.new(
            title="The world takes shape",
            description="Establishing the ordinary world and its rules carefully.",
            stakes="understanding",
            consequence="Foundation laid for what follows.",
            branch_type="intensification",
            structure_beat="Set-Up",
        )
        b_finale = Branch.new(
            title="The finale resolves everything",
            description="All threads come together for the ultimate conclusion.",
            stakes="closure",
            consequence="The story reaches its end.",
            branch_type="intensification",
            structure_beat="Final Image",
        )
        return b_mid, b_setup, b_finale

    def _rank(self, beat, db=None, project_id=None):
        b_mid, b_setup, b_finale = self._make_branches()
        wf = Wavefunction.new(anchor="Fork", branches=[b_mid, b_setup, b_finale])
        wf.structure_beat = beat
        if db and project_id:
            result = _format_wavefunction("Test", wf, db=db, project_id=project_id)
            return [b["title"] for b in result.payload["branches"]]
        scored = score_branches(wf)
        by_id = {b.id: b.title for b in wf.branches}
        return [by_id[s.branch_id] for s in scored]

    def test_midpoint_vs_setup_different_ranking(self):
        rank_mid = self._rank("Midpoint")
        rank_setup = self._rank("Set-Up")
        assert rank_mid != rank_setup

    def test_midpoint_favors_matching_branch(self):
        b_mid, b_setup, b_finale = self._make_branches()
        wf = Wavefunction.new(anchor="Fork", branches=[b_mid, b_setup, b_finale])
        wf.structure_beat = "Midpoint"
        scored = score_branches(wf)
        top = scored[0]
        wf_branch = wf.get_branch(top.branch_id)
        assert wf_branch.title == "The reversal hits hard"

    def test_finale_vs_midpoint_different_ranking(self):
        rank_finale = self._rank("Final Image")
        rank_mid = self._rank("Midpoint")
        assert rank_finale != rank_mid

    def test_no_beat_uses_unbiased_weights(self):
        rank_none = self._rank(None)
        b_mid, b_setup, b_finale = self._make_branches()
        wf = Wavefunction.new(anchor="Fork", branches=[b_mid, b_setup, b_finale])
        scored = score_branches(wf, weights=DEFAULT_WEIGHTS)
        by_id = {b.id: b.title for b in wf.branches}
        rank_explicit = [by_id[s.branch_id] for s in scored]
        assert rank_none == rank_explicit

    def test_unknown_beat_same_as_no_beat(self):
        rank_unknown = self._rank("Totally Unknown Beat")
        rank_none = self._rank(None)
        assert rank_unknown == rank_none

    def test_beat_bias_with_user_weights(self, db, project):
        db.set_scoring_weights(project.id, SCORING_PRESETS["Balanced"])
        rank_mid = self._rank("Midpoint", db=db, project_id=project.id)
        rank_setup = self._rank("Set-Up", db=db, project_id=project.id)
        assert rank_mid != rank_setup

    def test_beat_bias_with_bold_preset(self, db, project):
        db.set_scoring_weights(project.id, SCORING_PRESETS["Bold"])
        b_mid, b_setup, b_finale = self._make_branches()

        wf_mid = Wavefunction.new(anchor="Fork", branches=[b_mid, b_setup, b_finale])
        wf_mid.structure_beat = "Midpoint"
        r_mid = _format_wavefunction("Test", wf_mid, db=db, project_id=project.id)
        top_mid = r_mid.payload["branches"][0]["title"]

        b_m2, b_s2, b_f2 = self._make_branches()
        wf_res = Wavefunction.new(anchor="Fork", branches=[b_m2, b_s2, b_f2])
        wf_res.structure_beat = "Final Image"
        r_res = _format_wavefunction("Test", wf_res, db=db, project_id=project.id)
        top_res = r_res.payload["branches"][0]["title"]

        assert top_mid != top_res

    def test_deterministic_with_same_beat(self):
        results = []
        for _ in range(3):
            results.append(self._rank("Midpoint"))
        assert results[0] == results[1] == results[2]

    def test_all_phases_produce_valid_probabilities(self, db, project):
        phases_seen = set()
        for beat, phase in BEAT_PHASE_MAP.items():
            if phase in phases_seen:
                continue
            phases_seen.add(phase)

            b_mid, b_setup, b_finale = self._make_branches()
            wf = Wavefunction.new(anchor="Fork", branches=[b_mid, b_setup, b_finale])
            wf.structure_beat = beat
            result = _format_wavefunction("Test", wf, db=db, project_id=project.id)
            probs = [b["probability"] for b in result.payload["branches"]]
            assert abs(sum(probs) - 1.0) < 0.02, f"{beat} ({phase})"
            assert probs == sorted(probs, reverse=True), f"{beat} ({phase})"
