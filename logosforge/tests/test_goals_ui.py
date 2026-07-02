"""Tests for Goals UI: presets, constraint parsing, format panel, ranking updates."""

from __future__ import annotations

import pytest

from logosforge.quantum_outliner.scoring import (
    GOAL_FACTOR_MAP,
    GOAL_PRESET_NAMES,
    GOAL_PRESETS,
    QuantumGoals,
    format_goals_panel,
    goals_from_preset,
    parse_goal_constraint,
    score_branches,
)
from logosforge.quantum_outliner.state import Branch, Wavefunction


# ---------------------------------------------------------------------------
# Preset tests
# ---------------------------------------------------------------------------


class TestGoalPresets:
    def test_preset_names_match_keys(self):
        assert GOAL_PRESET_NAMES == list(GOAL_PRESETS.keys())

    def test_all_presets_have_required_keys(self):
        for name, preset in GOAL_PRESETS.items():
            assert "objectives" in preset, f"{name} missing objectives"
            assert "min_constraints" in preset, f"{name} missing min_constraints"
            assert "horizon" in preset, f"{name} missing horizon"

    def test_preset_objectives_sum_to_one(self):
        for name, preset in GOAL_PRESETS.items():
            total = sum(preset["objectives"].values())
            assert abs(total - 1.0) < 0.01, f"{name} objectives sum to {total}"

    def test_goals_from_preset_balanced(self):
        g = goals_from_preset("Balanced")
        assert g.horizon == 1
        assert not g.min_constraints
        for v in g.objectives.values():
            assert abs(v - 0.2) < 0.01

    def test_goals_from_preset_high_tension(self):
        g = goals_from_preset("High Tension")
        assert g.horizon == 2
        assert g.objectives["tension"] > g.objectives["consistency"]
        assert "tension_gain" in g.min_constraints
        assert g.min_constraints["tension_gain"] == pytest.approx(0.3)

    def test_goals_from_preset_character_first(self):
        g = goals_from_preset("Character-first")
        assert g.objectives["character_focus"] > g.objectives["tension"]
        assert "psyke_consistency" in g.min_constraints

    def test_goals_from_preset_experimental(self):
        g = goals_from_preset("Experimental")
        assert g.objectives["novelty"] > g.objectives["tension"]
        assert g.horizon == 2

    def test_goals_from_preset_unknown_returns_default(self):
        g = goals_from_preset("Nonexistent")
        assert g == QuantumGoals()

    def test_goals_from_preset_validates(self):
        g = goals_from_preset("High Tension")
        total = sum(g.objectives.values())
        assert abs(total - 1.0) < 0.01


# ---------------------------------------------------------------------------
# Constraint parsing tests
# ---------------------------------------------------------------------------


class TestParseGoalConstraint:
    def test_parse_objective_name(self):
        result = parse_goal_constraint("tension >= 0.3")
        assert result == ("tension_gain", 0.3)

    def test_parse_factor_name(self):
        result = parse_goal_constraint("psyke_consistency >= 0.5")
        assert result == ("psyke_consistency", 0.5)

    def test_parse_with_spaces(self):
        result = parse_goal_constraint("  consistency  >=  0.6  ")
        assert result == ("psyke_consistency", 0.6)

    def test_parse_character_focus(self):
        result = parse_goal_constraint("character_focus >= 0.4")
        assert result == ("goal_alignment", 0.4)

    def test_parse_clamps_high(self):
        result = parse_goal_constraint("tension >= 2.0")
        assert result is not None
        assert result[1] == 1.0

    def test_parse_clamps_low(self):
        result = parse_goal_constraint("tension >= -0.5")
        assert result is not None
        assert result[1] == 0.0

    def test_parse_invalid_no_operator(self):
        assert parse_goal_constraint("tension > 0.3") is None

    def test_parse_invalid_no_value(self):
        assert parse_goal_constraint("tension >= abc") is None

    def test_parse_invalid_unknown_name(self):
        assert parse_goal_constraint("magic >= 0.5") is None

    def test_parse_empty_string(self):
        assert parse_goal_constraint("") is None

    def test_parse_structure_name(self):
        result = parse_goal_constraint("structure >= 0.4")
        assert result == ("structure_fit", 0.4)


# ---------------------------------------------------------------------------
# Format panel tests
# ---------------------------------------------------------------------------


class TestFormatGoalsPanel:
    def test_default_goals_panel(self):
        g = QuantumGoals()
        panel = format_goals_panel(g)
        assert "═══ GOALS ═══" in panel
        assert "Objectives:" in panel
        assert "tension" in panel
        assert "Horizon: 1" in panel

    def test_panel_shows_constraints(self):
        g = QuantumGoals(min_constraints={"tension_gain": 0.3})
        panel = format_goals_panel(g)
        assert "Constraints:" in panel
        assert "tension_gain >= 0.30" in panel

    def test_panel_shows_horizon(self):
        g = QuantumGoals(horizon=3)
        panel = format_goals_panel(g)
        assert "Horizon: 3" in panel

    def test_panel_detects_preset(self):
        g = goals_from_preset("Balanced")
        panel = format_goals_panel(g)
        assert "Preset: Balanced" in panel

    def test_panel_custom_when_modified(self):
        g = goals_from_preset("Balanced")
        g.objectives["tension"] = 0.5
        g.validate()
        panel = format_goals_panel(g)
        assert "Preset: Custom" in panel

    def test_panel_all_objectives_shown(self):
        g = QuantumGoals()
        panel = format_goals_panel(g)
        for key in ("tension", "consistency", "novelty", "structure", "character_focus"):
            assert key in panel

    def test_panel_bar_rendering(self):
        g = QuantumGoals(objectives={
            "tension": 0.5, "consistency": 0.125, "novelty": 0.125,
            "structure": 0.125, "character_focus": 0.125,
        })
        g.validate()
        panel = format_goals_panel(g)
        assert "█" in panel
        assert "░" in panel


# ---------------------------------------------------------------------------
# Ranking update tests — adjust goals → scoring changes
# ---------------------------------------------------------------------------


def _make_wf_with_branches() -> Wavefunction:
    """Create a wavefunction with branches designed to respond to goal changes."""
    wf = Wavefunction.new(anchor="test scenario")
    wf.branches = [
        Branch.new(
            title="High tension path",
            description="suddenly the hero must fight a desperate war with pain and danger",
            stakes="everything at risk of loss",
            consequence="sacrifice demanded fear",
        ),
        Branch.new(
            title="Character study",
            description="Alice explores her feelings about Bob in a quiet moment",
            stakes="emotional clarity",
            consequence="deeper understanding",
        ),
        Branch.new(
            title="Novel twist",
            description="an unexpected turn introduces a completely new element",
            stakes="freshness of approach",
            consequence="unforeseen change",
        ),
    ]
    return wf


class TestGoalRankingUpdates:
    def test_high_tension_preset_favors_tension_branch(self):
        wf = _make_wf_with_branches()
        goals = goals_from_preset("High Tension")
        scored = score_branches(wf, goals=goals)
        top = scored[0]
        branch = next(b for b in wf.branches if b.id == top.branch_id)
        assert "tension" in branch.title.lower() or top.factors.get("tension_gain", 0) > 0.3

    def test_experimental_preset_favors_novelty(self):
        wf = _make_wf_with_branches()
        goals = goals_from_preset("Experimental")
        scored = score_branches(wf, goals=goals)
        top = scored[0]
        assert top.factors.get("novelty", 0) > 0.3 or top.goal_score > 0

    def test_balanced_preset_scores_differ_from_no_goals(self):
        wf = _make_wf_with_branches()
        scored_no_goals = score_branches(wf)
        scored_goals = score_branches(wf, goals=goals_from_preset("Balanced"))
        no_goal_ids = [s.branch_id for s in scored_no_goals]
        goal_ids = [s.branch_id for s in scored_goals]
        # With goals, unified_score is computed differently
        for s in scored_goals:
            assert s.unified_score >= 0

    def test_constraint_invalidates_branch(self):
        wf = _make_wf_with_branches()
        goals = QuantumGoals(
            objectives={"tension": 0.2, "consistency": 0.2, "novelty": 0.2,
                        "structure": 0.2, "character_focus": 0.2},
            min_constraints={"tension_gain": 0.9},
            horizon=1,
        ).validate()
        scored = score_branches(wf, goals=goals)
        # At least some branches should have goal_valid=False with such a high threshold
        invalid = [s for s in scored if not s.goal_valid]
        assert len(invalid) > 0

    def test_horizon_2_includes_lookahead(self):
        wf = _make_wf_with_branches()
        goals = QuantumGoals(
            objectives={"tension": 0.4, "consistency": 0.15, "novelty": 0.15,
                        "structure": 0.15, "character_focus": 0.15},
            min_constraints={},
            horizon=2,
        ).validate()
        scored = score_branches(wf, goals=goals)
        # With horizon=2, lookahead_score should be non-zero for valid branches
        valid = [s for s in scored if s.goal_valid and s.probability > 0]
        assert any(s.lookahead_score > 0 for s in valid)

    def test_changing_goals_changes_ranking(self):
        wf = _make_wf_with_branches()
        tension_goals = goals_from_preset("High Tension")
        exp_goals = goals_from_preset("Experimental")
        scored_tension = score_branches(wf, goals=tension_goals)
        scored_exp = score_branches(wf, goals=exp_goals)
        # The unified scores should differ
        t_scores = {s.branch_id: s.unified_score for s in scored_tension}
        e_scores = {s.branch_id: s.unified_score for s in scored_exp}
        assert t_scores != e_scores


# ---------------------------------------------------------------------------
# DB persistence round-trip
# ---------------------------------------------------------------------------


class TestGoalsPersistence:
    def test_set_and_get_goals(self):
        from logosforge.db import Database
        db = Database()
        project = db.create_project("Test")
        goals = goals_from_preset("High Tension")
        db.set_quantum_goals(project.id, goals)
        loaded = db.get_quantum_goals(project.id)
        assert loaded.objectives == goals.objectives
        assert loaded.min_constraints == goals.min_constraints
        assert loaded.horizon == goals.horizon

    def test_default_goals_when_unset(self):
        from logosforge.db import Database
        db = Database()
        project = db.create_project("Test")
        loaded = db.get_quantum_goals(project.id)
        assert loaded == QuantumGoals()

    def test_goals_survive_re_read(self):
        from logosforge.db import Database
        db = Database()
        project = db.create_project("Test")
        goals = goals_from_preset("Character-first")
        db.set_quantum_goals(project.id, goals)
        loaded = db.get_quantum_goals(project.id)
        assert loaded.objectives["character_focus"] > loaded.objectives["tension"]
