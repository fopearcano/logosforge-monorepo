"""Tests for adaptive weight learning from collapse choices.

Covers:
- adapt_weights algorithm: signal computation, clamping, renormalization
- Repeated choices shift weights toward preferred factor pattern
- Disable learning → no weight change
- Learning toggle persistence
- Integration with collapse_branch flow
"""

import pytest

from logosforge.db import Database
from logosforge.quantum_outliner import (
    Branch,
    LEARNING_RATE,
    Wavefunction,
    adapt_weights,
    collapse_branch,
)
from logosforge.quantum_outliner.scoring import (
    DEFAULT_WEIGHTS,
    SCORING_PRESETS,
    apply_scores,
    score_branches,
)
from logosforge.quantum_outliner.state import _STATES, get_state


@pytest.fixture
def db(tmp_path):
    return Database(str(tmp_path / "test.db"))


@pytest.fixture
def project(db):
    return db.create_project("Adapt Test")


@pytest.fixture(autouse=True)
def _reset():
    _STATES.clear()
    yield
    _STATES.clear()


def _scored_wf(branches, **kw):
    wf = Wavefunction.new(anchor="Test", branches=branches)
    for k, v in kw.items():
        setattr(wf, k, v)
    scored = score_branches(wf)
    apply_scores(wf, scored)
    return wf


# ---------------------------------------------------------------------------
# adapt_weights algorithm
# ---------------------------------------------------------------------------


class TestAdaptWeights:
    def test_returns_original_if_no_unchosen(self):
        w = dict(DEFAULT_WEIGHTS)
        result = adapt_weights(w, {"tension_gain": 0.9}, [])
        assert result == w

    def test_returns_original_if_no_chosen(self):
        w = dict(DEFAULT_WEIGHTS)
        result = adapt_weights(w, {}, [{"tension_gain": 0.3}])
        assert result == w

    def test_boosts_factor_where_chosen_exceeds_unchosen(self):
        w = dict(DEFAULT_WEIGHTS)
        chosen = {"tension_gain": 0.9, "novelty": 0.3,
                  "structure_fit": 0.2, "psyke_consistency": 0.2,
                  "goal_alignment": 0.2}
        unchosen = [{"tension_gain": 0.2, "novelty": 0.8,
                     "structure_fit": 0.5, "psyke_consistency": 0.5,
                     "goal_alignment": 0.5}]
        result = adapt_weights(w, chosen, unchosen)
        assert result["tension_gain"] > DEFAULT_WEIGHTS["tension_gain"]

    def test_reduces_factor_where_chosen_below_unchosen(self):
        w = dict(DEFAULT_WEIGHTS)
        chosen = {"tension_gain": 0.9, "novelty": 0.1,
                  "structure_fit": 0.1, "psyke_consistency": 0.1,
                  "goal_alignment": 0.1}
        unchosen = [{"tension_gain": 0.2, "novelty": 0.8,
                     "structure_fit": 0.7, "psyke_consistency": 0.7,
                     "goal_alignment": 0.7}]
        result = adapt_weights(w, chosen, unchosen)
        assert result["novelty"] < DEFAULT_WEIGHTS["novelty"]

    def test_result_sums_to_one(self):
        w = dict(DEFAULT_WEIGHTS)
        chosen = {"tension_gain": 1.0, "novelty": 0.0,
                  "structure_fit": 0.0, "psyke_consistency": 0.0,
                  "goal_alignment": 0.0}
        unchosen = [{"tension_gain": 0.0, "novelty": 1.0,
                     "structure_fit": 0.5, "psyke_consistency": 0.5,
                     "goal_alignment": 0.5}]
        result = adapt_weights(w, chosen, unchosen)
        assert abs(sum(result.values()) - 1.0) < 0.01

    def test_weights_clamped_at_zero(self):
        w = {"tension_gain": 0.01, "novelty": 0.49,
             "structure_fit": 0.2, "psyke_consistency": 0.2,
             "goal_alignment": 0.1}
        chosen = {"tension_gain": 0.0, "novelty": 1.0,
                  "structure_fit": 0.5, "psyke_consistency": 0.5,
                  "goal_alignment": 0.5}
        unchosen = [{"tension_gain": 1.0, "novelty": 0.0,
                     "structure_fit": 0.5, "psyke_consistency": 0.5,
                     "goal_alignment": 0.5}]
        result = adapt_weights(w, chosen, unchosen, learning_rate=0.5)
        for v in result.values():
            assert v >= 0.0

    def test_weights_clamped_at_one(self):
        w = {"tension_gain": 0.8, "novelty": 0.05,
             "structure_fit": 0.05, "psyke_consistency": 0.05,
             "goal_alignment": 0.05}
        chosen = {"tension_gain": 1.0, "novelty": 0.0,
                  "structure_fit": 0.0, "psyke_consistency": 0.0,
                  "goal_alignment": 0.0}
        unchosen = [{"tension_gain": 0.0, "novelty": 1.0,
                     "structure_fit": 1.0, "psyke_consistency": 1.0,
                     "goal_alignment": 1.0}]
        result = adapt_weights(w, chosen, unchosen, learning_rate=0.5)
        for v in result.values():
            assert v <= 1.0

    def test_custom_learning_rate(self):
        w = dict(DEFAULT_WEIGHTS)
        chosen = {"tension_gain": 1.0, "novelty": 0.0,
                  "structure_fit": 0.0, "psyke_consistency": 0.0,
                  "goal_alignment": 0.0}
        unchosen = [{"tension_gain": 0.0, "novelty": 1.0,
                     "structure_fit": 0.5, "psyke_consistency": 0.5,
                     "goal_alignment": 0.5}]

        small = adapt_weights(w, chosen, unchosen, learning_rate=0.01)
        large = adapt_weights(w, chosen, unchosen, learning_rate=0.20)

        small_shift = abs(small["tension_gain"] - DEFAULT_WEIGHTS["tension_gain"])
        large_shift = abs(large["tension_gain"] - DEFAULT_WEIGHTS["tension_gain"])
        assert large_shift > small_shift

    def test_averages_multiple_unchosen(self):
        w = dict(DEFAULT_WEIGHTS)
        chosen = {"tension_gain": 0.9, "novelty": 0.5,
                  "structure_fit": 0.3, "psyke_consistency": 0.3,
                  "goal_alignment": 0.3}
        unchosen = [
            {"tension_gain": 0.2, "novelty": 0.8,
             "structure_fit": 0.5, "psyke_consistency": 0.5,
             "goal_alignment": 0.5},
            {"tension_gain": 0.4, "novelty": 0.6,
             "structure_fit": 0.4, "psyke_consistency": 0.4,
             "goal_alignment": 0.4},
        ]
        result = adapt_weights(w, chosen, unchosen)
        assert result["tension_gain"] > DEFAULT_WEIGHTS["tension_gain"]

    def test_no_change_when_factors_equal(self):
        w = dict(DEFAULT_WEIGHTS)
        factors = {"tension_gain": 0.5, "novelty": 0.5,
                   "structure_fit": 0.5, "psyke_consistency": 0.5,
                   "goal_alignment": 0.5}
        result = adapt_weights(w, factors, [dict(factors)])
        assert result == DEFAULT_WEIGHTS

    def test_preserves_all_factor_keys(self):
        w = dict(DEFAULT_WEIGHTS)
        chosen = {"tension_gain": 0.9, "novelty": 0.5,
                  "structure_fit": 0.3, "psyke_consistency": 0.3,
                  "goal_alignment": 0.3}
        unchosen = [{"tension_gain": 0.2, "novelty": 0.8,
                     "structure_fit": 0.5, "psyke_consistency": 0.5,
                     "goal_alignment": 0.5}]
        result = adapt_weights(w, chosen, unchosen)
        assert set(result.keys()) == set(DEFAULT_WEIGHTS.keys())


# ---------------------------------------------------------------------------
# Repeated choices shift weights
# ---------------------------------------------------------------------------


class TestRepeatedChoicesShiftWeights:
    def test_repeated_tension_choices_boost_tension(self):
        w = dict(DEFAULT_WEIGHTS)
        chosen = {"tension_gain": 0.9, "novelty": 0.3,
                  "structure_fit": 0.2, "psyke_consistency": 0.2,
                  "goal_alignment": 0.2}
        unchosen = [{"tension_gain": 0.2, "novelty": 0.8,
                     "structure_fit": 0.6, "psyke_consistency": 0.5,
                     "goal_alignment": 0.5}]

        for _ in range(10):
            w = adapt_weights(w, chosen, unchosen)

        assert w["tension_gain"] > DEFAULT_WEIGHTS["tension_gain"] + 0.05

    def test_repeated_novelty_choices_boost_novelty(self):
        w = dict(DEFAULT_WEIGHTS)
        chosen = {"tension_gain": 0.2, "novelty": 0.9,
                  "structure_fit": 0.2, "psyke_consistency": 0.2,
                  "goal_alignment": 0.2}
        unchosen = [{"tension_gain": 0.7, "novelty": 0.2,
                     "structure_fit": 0.5, "psyke_consistency": 0.5,
                     "goal_alignment": 0.5}]

        for _ in range(10):
            w = adapt_weights(w, chosen, unchosen)

        assert w["novelty"] > DEFAULT_WEIGHTS["novelty"] + 0.05

    def test_weights_stay_normalized_after_many_iterations(self):
        w = dict(DEFAULT_WEIGHTS)
        chosen = {"tension_gain": 1.0, "novelty": 0.0,
                  "structure_fit": 0.0, "psyke_consistency": 0.0,
                  "goal_alignment": 0.0}
        unchosen = [{"tension_gain": 0.0, "novelty": 1.0,
                     "structure_fit": 0.5, "psyke_consistency": 0.5,
                     "goal_alignment": 0.5}]

        for _ in range(50):
            w = adapt_weights(w, chosen, unchosen)

        assert abs(sum(w.values()) - 1.0) < 0.01
        for v in w.values():
            assert 0.0 <= v <= 1.0

    def test_convergence_slows_as_weights_approach_limit(self):
        w = dict(DEFAULT_WEIGHTS)
        chosen = {"tension_gain": 1.0, "novelty": 0.0,
                  "structure_fit": 0.0, "psyke_consistency": 0.0,
                  "goal_alignment": 0.0}
        unchosen = [{"tension_gain": 0.0, "novelty": 1.0,
                     "structure_fit": 0.5, "psyke_consistency": 0.5,
                     "goal_alignment": 0.5}]

        shifts = []
        for _ in range(20):
            prev = w["tension_gain"]
            w = adapt_weights(w, chosen, unchosen)
            shifts.append(abs(w["tension_gain"] - prev))

        assert shifts[-1] <= shifts[0]


# ---------------------------------------------------------------------------
# Learning toggle
# ---------------------------------------------------------------------------


class TestLearningToggle:
    def test_learning_on_by_default(self, db, project):
        assert db.get_weight_learning(project.id) is True

    def test_disable_learning(self, db, project):
        db.set_weight_learning(project.id, False)
        assert db.get_weight_learning(project.id) is False

    def test_enable_learning(self, db, project):
        db.set_weight_learning(project.id, False)
        db.set_weight_learning(project.id, True)
        assert db.get_weight_learning(project.id) is True

    def test_toggle_persists(self, tmp_path):
        path = str(tmp_path / "toggle.db")
        db1 = Database(path)
        p = db1.create_project("P")
        db1.set_weight_learning(p.id, False)

        db2 = Database(path)
        assert db2.get_weight_learning(p.id) is False

    def test_per_project_isolation(self, db):
        p1 = db.create_project("A")
        p2 = db.create_project("B")
        db.set_weight_learning(p1.id, False)

        assert db.get_weight_learning(p1.id) is False
        assert db.get_weight_learning(p2.id) is True


# ---------------------------------------------------------------------------
# Integration: collapse_branch triggers adaptation
# ---------------------------------------------------------------------------


def _make_scored_wf(project_id):
    """Create a wf with scored branches and register in state."""
    b_tense = Branch.new(
        title="War erupts",
        description="fight danger threat sacrifice desperate",
        stakes="desperate", consequence="loss and pain",
        branch_type="intensification",
    )
    b_calm = Branch.new(
        title="Peace talks",
        description="calm negotiation without conflict",
    )
    b_novel = Branch.new(
        title="Portal opens",
        description="an iridescent shimmer reveals alien dimension",
        branch_type="alternative",
    )
    wf = Wavefunction.new(anchor="Test", branches=[b_tense, b_calm, b_novel])
    scored = score_branches(wf)
    apply_scores(wf, scored)

    state = get_state(project_id)
    state.add(wf)
    return wf


class TestCollapseAdaptation:
    def test_collapse_adapts_weights(self, db, project):
        wf = _make_scored_wf(project.id)
        before = db.get_scoring_weights(project.id)

        tense = next(b for b in wf.branches if "War" in b.title)
        collapse_branch(db, project.id, wf.id, tense.id)

        after = db.get_scoring_weights(project.id)
        assert after != before

    def test_collapse_sets_preset_to_custom(self, db, project):
        wf = _make_scored_wf(project.id)
        assert db.get_scoring_preset(project.id) == "Balanced"

        tense = next(b for b in wf.branches if "War" in b.title)
        collapse_branch(db, project.id, wf.id, tense.id)

        assert db.get_scoring_preset(project.id) == "Custom"

    def test_collapse_boosts_chosen_factors(self, db, project):
        wf = _make_scored_wf(project.id)
        tense = next(b for b in wf.branches if "War" in b.title)

        before = db.get_scoring_weights(project.id)
        collapse_branch(db, project.id, wf.id, tense.id)
        after = db.get_scoring_weights(project.id)

        assert after["tension_gain"] > before["tension_gain"]

    def test_collapse_with_learning_off_no_change(self, db, project):
        db.set_weight_learning(project.id, False)
        wf = _make_scored_wf(project.id)
        before = db.get_scoring_weights(project.id)

        tense = next(b for b in wf.branches if "War" in b.title)
        collapse_branch(db, project.id, wf.id, tense.id)

        after = db.get_scoring_weights(project.id)
        assert after == before

    def test_collapse_shows_learning_note(self, db, project):
        wf = _make_scored_wf(project.id)
        tense = next(b for b in wf.branches if "War" in b.title)

        result = collapse_branch(db, project.id, wf.id, tense.id)
        assert "learning on" in result.body.lower()

    def test_collapse_no_learning_note_when_off(self, db, project):
        db.set_weight_learning(project.id, False)
        wf = _make_scored_wf(project.id)
        tense = next(b for b in wf.branches if "War" in b.title)

        result = collapse_branch(db, project.id, wf.id, tense.id)
        assert "learning" not in result.body.lower()

    def test_adapted_weights_sum_to_one(self, db, project):
        wf = _make_scored_wf(project.id)
        tense = next(b for b in wf.branches if "War" in b.title)
        collapse_branch(db, project.id, wf.id, tense.id)

        w = db.get_scoring_weights(project.id)
        assert abs(sum(w.values()) - 1.0) < 0.01

    def test_repeated_collapses_accumulate(self, db, project):
        initial = db.get_scoring_weights(project.id)

        for _ in range(5):
            wf = _make_scored_wf(project.id)
            tense = next(b for b in wf.branches if "War" in b.title)
            collapse_branch(db, project.id, wf.id, tense.id)

        final = db.get_scoring_weights(project.id)
        shift = final["tension_gain"] - initial["tension_gain"]
        assert shift > LEARNING_RATE * 0.5

    def test_different_choices_pull_differently(self, db, project):
        wf1 = _make_scored_wf(project.id)
        tense = next(b for b in wf1.branches if "War" in b.title)
        collapse_branch(db, project.id, wf1.id, tense.id)
        after_tense = db.get_scoring_weights(project.id)

        db.set_scoring_weights(project.id, dict(DEFAULT_WEIGHTS))
        wf2 = _make_scored_wf(project.id)
        calm = next(b for b in wf2.branches if "Peace" in b.title)
        collapse_branch(db, project.id, wf2.id, calm.id)
        after_calm = db.get_scoring_weights(project.id)

        assert after_tense["tension_gain"] > after_calm["tension_gain"]
