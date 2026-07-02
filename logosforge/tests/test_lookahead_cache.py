"""Tests for lookahead performance safeguards: caps, caching, async, invalidation."""

from __future__ import annotations

import time

import pytest

from logosforge.quantum_outliner.lookahead_cache import (
    MAX_BRANCHES_PER_NODE,
    MAX_DEPTH,
    LookaheadCache,
    _make_cache_key,
    evaluate_lookahead_cached,
    get_cache,
    invalidate_lookahead,
    submit_lookahead_async,
)
from logosforge.quantum_outliner.scoring import (
    QuantumGoals,
    _simulate_ahead,
    apply_scores,
    compute_blended_goal_score,
    evaluate_lookahead,
    goals_from_preset,
    score_branches,
)
from logosforge.quantum_outliner.state import Branch, Wavefunction


_SAMPLE_FACTORS: dict[str, float] = {
    "tension_gain": 0.7,
    "psyke_consistency": 0.5,
    "novelty": 0.6,
    "structure_fit": 0.4,
    "goal_alignment": 0.5,
}


# ---------------------------------------------------------------------------
# Hard-cap tests
# ---------------------------------------------------------------------------


class TestSimulationCaps:
    def test_max_branches_per_node_is_3(self):
        assert MAX_BRANCHES_PER_NODE == 3

    def test_max_depth_is_3(self):
        assert MAX_DEPTH == 3

    def test_simulate_ahead_respects_depth_cap(self):
        goals = QuantumGoals(
            objectives={"tension": 0.5, "consistency": 0.1, "novelty": 0.15,
                        "structure": 0.1, "character_focus": 0.15},
            min_constraints={},
            horizon=10,
        )
        goals.horizon = 10
        result = _simulate_ahead(_SAMPLE_FACTORS, goals, 9, 10, _depth=0)
        assert isinstance(result, float)
        assert 0 <= result <= 1

    def test_depth_cap_terminates_immediately_at_max(self):
        goals = goals_from_preset("High Tension")
        result = _simulate_ahead(_SAMPLE_FACTORS, goals, 5, 6, _depth=MAX_DEPTH)
        direct_score, _ = __import__(
            "logosforge.quantum_outliner.scoring", fromlist=["compute_goal_score"]
        ).compute_goal_score(_SAMPLE_FACTORS, goals)
        assert result == pytest.approx(direct_score if direct_score > 0 else 0.0, abs=0.01)

    def test_evaluate_lookahead_caps_extra_steps(self):
        goals = QuantumGoals(
            objectives={"tension": 0.2, "consistency": 0.2, "novelty": 0.2,
                        "structure": 0.2, "character_focus": 0.2},
            min_constraints={},
            horizon=1,
        ).validate()
        goals.horizon = 100
        result = evaluate_lookahead(_SAMPLE_FACTORS, goals)
        assert isinstance(result, float)
        assert 0 <= result <= 1


# ---------------------------------------------------------------------------
# No-UI-freeze test: scoring completes within a tight budget
# ---------------------------------------------------------------------------


class TestNoUIFreeze:
    def test_scoring_completes_under_100ms(self):
        wf = Wavefunction.new(anchor="perf test")
        wf.branches = [
            Branch.new(
                title=f"Branch {i}",
                description=f"description for path {i} with conflict and danger",
                stakes="high risk",
                consequence="major consequence",
            )
            for i in range(6)
        ]
        goals = goals_from_preset("High Tension")

        start = time.monotonic()
        scored = score_branches(wf, goals=goals)
        elapsed = time.monotonic() - start

        assert len(scored) == 6
        assert elapsed < 0.1, f"Scoring took {elapsed:.3f}s — over 100ms budget"

    def test_scoring_with_horizon_3_under_100ms(self):
        wf = Wavefunction.new(anchor="deep lookahead test")
        wf.branches = [
            Branch.new(
                title=f"Option {i}",
                description="desperate fight with fear and danger suddenly",
                stakes="loss and pain",
                consequence="sacrifice war threat",
            )
            for i in range(6)
        ]
        goals = QuantumGoals(
            objectives={"tension": 0.4, "consistency": 0.15, "novelty": 0.15,
                        "structure": 0.15, "character_focus": 0.15},
            min_constraints={},
            horizon=3,
        ).validate()

        start = time.monotonic()
        scored = score_branches(wf, goals=goals)
        elapsed = time.monotonic() - start

        assert len(scored) == 6
        assert elapsed < 0.1, f"Scoring took {elapsed:.3f}s — over 100ms budget"


# ---------------------------------------------------------------------------
# Cache tests
# ---------------------------------------------------------------------------


class TestLookaheadCache:
    def setup_method(self):
        self.cache = LookaheadCache(max_size=16)

    def test_cache_miss_returns_none(self):
        goals = goals_from_preset("Balanced")
        assert self.cache.get(_SAMPLE_FACTORS, goals) is None

    def test_put_and_get(self):
        goals = goals_from_preset("Balanced")
        self.cache.put(_SAMPLE_FACTORS, goals, 0.42)
        assert self.cache.get(_SAMPLE_FACTORS, goals) == 0.42

    def test_different_factors_different_key(self):
        goals = goals_from_preset("Balanced")
        other_factors = {**_SAMPLE_FACTORS, "tension_gain": 0.9}
        self.cache.put(_SAMPLE_FACTORS, goals, 0.42)
        self.cache.put(other_factors, goals, 0.55)
        assert self.cache.get(_SAMPLE_FACTORS, goals) == 0.42
        assert self.cache.get(other_factors, goals) == 0.55

    def test_different_goals_different_key(self):
        g1 = goals_from_preset("Balanced")
        g2 = goals_from_preset("High Tension")
        self.cache.put(_SAMPLE_FACTORS, g1, 0.42)
        self.cache.put(_SAMPLE_FACTORS, g2, 0.55)
        assert self.cache.get(_SAMPLE_FACTORS, g1) == 0.42
        assert self.cache.get(_SAMPLE_FACTORS, g2) == 0.55

    def test_invalidate_clears_all(self):
        goals = goals_from_preset("Balanced")
        self.cache.put(_SAMPLE_FACTORS, goals, 0.42)
        assert self.cache.size() == 1
        self.cache.invalidate()
        assert self.cache.size() == 0
        assert self.cache.get(_SAMPLE_FACTORS, goals) is None

    def test_invalidate_increments_generation(self):
        gen_before = self.cache.generation
        self.cache.invalidate()
        assert self.cache.generation == gen_before + 1

    def test_lru_eviction(self):
        goals = goals_from_preset("Balanced")
        small_cache = LookaheadCache(max_size=3)
        for i in range(5):
            f = {**_SAMPLE_FACTORS, "tension_gain": i * 0.1}
            small_cache.put(f, goals, float(i))
        assert small_cache.size() == 3
        oldest = {**_SAMPLE_FACTORS, "tension_gain": 0.0}
        assert small_cache.get(oldest, goals) is None

    def test_evaluate_cached_populates_cache(self):
        goals = goals_from_preset("High Tension")
        assert self.cache.get(_SAMPLE_FACTORS, goals) is None
        result = self.cache.evaluate_cached(_SAMPLE_FACTORS, goals)
        assert isinstance(result, float)
        assert self.cache.get(_SAMPLE_FACTORS, goals) == result


class TestRepeatedQueriesHitCache:
    def test_second_call_returns_cached(self):
        cache = LookaheadCache()
        goals = goals_from_preset("High Tension")
        r1 = cache.evaluate_cached(_SAMPLE_FACTORS, goals)
        r2 = cache.evaluate_cached(_SAMPLE_FACTORS, goals)
        assert r1 == r2
        assert cache.size() == 1

    def test_global_cache_hit_on_repeat(self):
        invalidate_lookahead()
        goals = goals_from_preset("High Tension")
        r1 = evaluate_lookahead_cached(_SAMPLE_FACTORS, goals)
        cache = get_cache()
        assert cache.get(_SAMPLE_FACTORS, goals) == r1
        r2 = evaluate_lookahead_cached(_SAMPLE_FACTORS, goals)
        assert r1 == r2

    def test_blended_score_uses_cache(self):
        invalidate_lookahead()
        goals = QuantumGoals(
            objectives={"tension": 0.4, "consistency": 0.15, "novelty": 0.15,
                        "structure": 0.15, "character_focus": 0.15},
            min_constraints={},
            horizon=2,
        ).validate()
        r1 = compute_blended_goal_score(_SAMPLE_FACTORS, goals)
        cache = get_cache()
        assert cache.size() >= 1
        r2 = compute_blended_goal_score(_SAMPLE_FACTORS, goals)
        assert r1 == r2


# ---------------------------------------------------------------------------
# Async worker tests
# ---------------------------------------------------------------------------


class TestAsyncWorker:
    def test_submit_returns_future(self):
        invalidate_lookahead()
        goals = goals_from_preset("High Tension")
        future = submit_lookahead_async(_SAMPLE_FACTORS, goals)
        result = future.result(timeout=5)
        assert isinstance(result, float)
        assert 0 <= result <= 1

    def test_submit_cached_resolves_immediately(self):
        invalidate_lookahead()
        goals = goals_from_preset("High Tension")
        evaluate_lookahead_cached(_SAMPLE_FACTORS, goals)
        start = time.monotonic()
        future = submit_lookahead_async(_SAMPLE_FACTORS, goals)
        result = future.result(timeout=1)
        elapsed = time.monotonic() - start
        assert elapsed < 0.01
        assert isinstance(result, float)

    def test_submit_populates_cache(self):
        invalidate_lookahead()
        goals = goals_from_preset("Experimental")
        future = submit_lookahead_async(_SAMPLE_FACTORS, goals)
        future.result(timeout=5)
        cache = get_cache()
        assert cache.get(_SAMPLE_FACTORS, goals) is not None


# ---------------------------------------------------------------------------
# Invalidation integration tests
# ---------------------------------------------------------------------------


class TestInvalidationOnDBChange:
    def _make_db(self):
        from logosforge.db import Database
        db = Database()
        project = db.create_project("Cache Test")
        return db, project.id

    def test_set_goals_invalidates(self):
        db, pid = self._make_db()
        goals = goals_from_preset("High Tension")
        evaluate_lookahead_cached(_SAMPLE_FACTORS, goals)
        cache = get_cache()
        gen_before = cache.generation
        db.set_quantum_goals(pid, goals_from_preset("Experimental"))
        assert cache.generation == gen_before + 1
        assert cache.size() == 0

    def test_create_psyke_entry_invalidates(self):
        db, pid = self._make_db()
        goals = goals_from_preset("Balanced")
        evaluate_lookahead_cached(_SAMPLE_FACTORS, goals)
        cache = get_cache()
        gen_before = cache.generation
        db.create_psyke_entry(pid, "Alice", entry_type="character")
        assert cache.generation == gen_before + 1

    def test_update_psyke_entry_invalidates(self):
        db, pid = self._make_db()
        entry = db.create_psyke_entry(pid, "Bob", entry_type="character")
        goals = goals_from_preset("Balanced")
        evaluate_lookahead_cached(_SAMPLE_FACTORS, goals)
        cache = get_cache()
        gen_before = cache.generation
        db.update_psyke_entry(entry.id, "Bobby", entry_type="character")
        assert cache.generation == gen_before + 1

    def test_add_psyke_relation_invalidates(self):
        db, pid = self._make_db()
        a = db.create_psyke_entry(pid, "A", entry_type="character")
        b = db.create_psyke_entry(pid, "B", entry_type="character")
        goals = goals_from_preset("Balanced")
        evaluate_lookahead_cached(_SAMPLE_FACTORS, goals)
        cache = get_cache()
        gen_before = cache.generation
        db.add_psyke_relation(a.id, b.id)
        assert cache.generation == gen_before + 1

    def test_create_psyke_progression_invalidates(self):
        db, pid = self._make_db()
        entry = db.create_psyke_entry(pid, "Carol", entry_type="character")
        goals = goals_from_preset("Balanced")
        evaluate_lookahead_cached(_SAMPLE_FACTORS, goals)
        cache = get_cache()
        gen_before = cache.generation
        db.create_psyke_progression(entry.id, "Carol changed")
        assert cache.generation == gen_before + 1

    def test_update_psyke_progression_invalidates(self):
        db, pid = self._make_db()
        entry = db.create_psyke_entry(pid, "Dave", entry_type="character")
        prog = db.create_psyke_progression(entry.id, "Dave evolved")
        goals = goals_from_preset("Balanced")
        evaluate_lookahead_cached(_SAMPLE_FACTORS, goals)
        cache = get_cache()
        gen_before = cache.generation
        db.update_psyke_progression(prog.id, "Dave transformed")
        assert cache.generation == gen_before + 1


# ---------------------------------------------------------------------------
# Cache key correctness
# ---------------------------------------------------------------------------


class TestCacheKey:
    def test_same_inputs_same_key(self):
        goals = goals_from_preset("Balanced")
        k1 = _make_cache_key(_SAMPLE_FACTORS, goals)
        k2 = _make_cache_key(dict(_SAMPLE_FACTORS), goals)
        assert k1 == k2

    def test_different_horizon_different_key(self):
        g1 = goals_from_preset("Balanced")
        g2 = goals_from_preset("Balanced")
        g2.horizon = 3
        k1 = _make_cache_key(_SAMPLE_FACTORS, g1)
        k2 = _make_cache_key(_SAMPLE_FACTORS, g2)
        assert k1 != k2

    def test_different_objectives_different_key(self):
        g1 = goals_from_preset("Balanced")
        g2 = goals_from_preset("High Tension")
        k1 = _make_cache_key(_SAMPLE_FACTORS, g1)
        k2 = _make_cache_key(_SAMPLE_FACTORS, g2)
        assert k1 != k2

    def test_rounding_stabilizes_key(self):
        goals = goals_from_preset("Balanced")
        f1 = {**_SAMPLE_FACTORS, "tension_gain": 0.70001}
        f2 = {**_SAMPLE_FACTORS, "tension_gain": 0.70004}
        assert _make_cache_key(f1, goals) == _make_cache_key(f2, goals)
