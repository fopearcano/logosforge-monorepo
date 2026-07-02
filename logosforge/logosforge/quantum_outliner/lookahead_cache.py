"""Lookahead cache and async worker — performance safeguards.

Prevents UI slowdown by:
- Hard-capping simulations (max 3 branches/node, max depth 3)
- Caching results keyed on (factors, goals, horizon)
- Running computation in a background thread (single reusable worker)
- Invalidating cache on PSYKE or goals change
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from concurrent.futures import Future, ThreadPoolExecutor
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from logosforge.quantum_outliner.scoring import QuantumGoals

MAX_BRANCHES_PER_NODE: int = 3
MAX_DEPTH: int = 3
_CACHE_MAX_SIZE: int = 256


def _make_cache_key(
    factors: dict[str, float],
    goals: "QuantumGoals",
) -> tuple:
    factor_items = tuple(sorted((k, round(v, 4)) for k, v in factors.items()))
    obj_items = tuple(sorted((k, round(v, 4)) for k, v in goals.objectives.items()))
    con_items = tuple(sorted((k, round(v, 4)) for k, v in goals.min_constraints.items()))
    return (factor_items, obj_items, con_items, goals.horizon)


class LookaheadCache:
    """Thread-safe LRU cache for lookahead results with async worker."""

    def __init__(self, max_size: int = _CACHE_MAX_SIZE) -> None:
        self._max_size = max_size
        self._cache: OrderedDict[tuple, float] = OrderedDict()
        self._lock = threading.Lock()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="lookahead")
        self._generation: int = 0

    @property
    def generation(self) -> int:
        return self._generation

    def get(self, factors: dict[str, float], goals: "QuantumGoals") -> float | None:
        key = _make_cache_key(factors, goals)
        with self._lock:
            val = self._cache.get(key)
            if val is not None:
                self._cache.move_to_end(key)
            return val

    def put(self, factors: dict[str, float], goals: "QuantumGoals", value: float) -> None:
        key = _make_cache_key(factors, goals)
        with self._lock:
            self._cache[key] = value
            self._cache.move_to_end(key)
            while len(self._cache) > self._max_size:
                self._cache.popitem(last=False)

    def invalidate(self) -> None:
        with self._lock:
            self._cache.clear()
            self._generation += 1

    def size(self) -> int:
        with self._lock:
            return len(self._cache)

    def submit(
        self,
        factors: dict[str, float],
        goals: "QuantumGoals",
    ) -> Future[float]:
        """Submit lookahead computation to background worker.

        Returns a Future. If the result is already cached, the Future
        resolves immediately.
        """
        cached = self.get(factors, goals)
        if cached is not None:
            f: Future[float] = Future()
            f.set_result(cached)
            return f

        gen = self._generation
        return self._executor.submit(self._compute, factors, goals, gen)

    def _compute(
        self,
        factors: dict[str, float],
        goals: "QuantumGoals",
        generation: int,
    ) -> float:
        from logosforge.quantum_outliner.scoring import evaluate_lookahead

        result = evaluate_lookahead(factors, goals)

        if generation == self._generation:
            self.put(factors, goals, result)

        return result

    def evaluate_cached(
        self,
        factors: dict[str, float],
        goals: "QuantumGoals",
    ) -> float:
        """Synchronous evaluate with cache. Used in scoring hot path."""
        cached = self.get(factors, goals)
        if cached is not None:
            return cached

        from logosforge.quantum_outliner.scoring import evaluate_lookahead

        result = evaluate_lookahead(factors, goals)
        self.put(factors, goals, result)
        return result

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False)


_global_cache = LookaheadCache()


def get_cache() -> LookaheadCache:
    return _global_cache


def invalidate_lookahead(reason: str = "") -> None:
    """Invalidate the global lookahead cache. Call on PSYKE or goals change."""
    _global_cache.invalidate()


def evaluate_lookahead_cached(
    factors: dict[str, float],
    goals: "QuantumGoals",
) -> float:
    """Evaluate lookahead using the global cache."""
    return _global_cache.evaluate_cached(factors, goals)


def submit_lookahead_async(
    factors: dict[str, float],
    goals: "QuantumGoals",
) -> Future[float]:
    """Submit lookahead to background worker, return Future."""
    return _global_cache.submit(factors, goals)
