"""Branch scoring engine — compute weighted score per quantum possibility.

Each branch is evaluated on five factors (0–1 each), combined via
configurable weights into a final score and probability.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from logosforge.quantum_outliner.psyke_adapter import PsykeSignals
from logosforge.quantum_outliner.state import Branch, QuantumPossibility, Wavefunction

if TYPE_CHECKING:
    pass

_TENSION_KEYWORDS = frozenset({
    "but", "however", "suddenly", "fight", "argued", "shouted",
    "betray", "lie", "secret", "fear", "afraid", "danger",
    "must", "cannot", "refused", "demanded", "conflict", "risk",
    "threat", "desperate", "sacrifice", "loss", "pain", "war",
})

DEFAULT_WEIGHTS: dict[str, float] = {
    "structure_fit": 0.25,
    "psyke_consistency": 0.25,
    "tension_gain": 0.20,
    "novelty": 0.15,
    "goal_alignment": 0.15,
}

SCORING_PRESETS: dict[str, dict[str, float]] = {
    "Balanced": {
        "structure_fit": 0.25,
        "psyke_consistency": 0.25,
        "tension_gain": 0.20,
        "novelty": 0.15,
        "goal_alignment": 0.15,
    },
    "Conservative": {
        "structure_fit": 0.35,
        "psyke_consistency": 0.35,
        "tension_gain": 0.10,
        "novelty": 0.10,
        "goal_alignment": 0.10,
    },
    "Bold": {
        "structure_fit": 0.10,
        "psyke_consistency": 0.10,
        "tension_gain": 0.35,
        "novelty": 0.35,
        "goal_alignment": 0.10,
    },
    "Character-driven": {
        "structure_fit": 0.10,
        "psyke_consistency": 0.35,
        "tension_gain": 0.10,
        "novelty": 0.10,
        "goal_alignment": 0.35,
    },
    "Plot-driven": {
        "structure_fit": 0.35,
        "psyke_consistency": 0.10,
        "tension_gain": 0.35,
        "novelty": 0.10,
        "goal_alignment": 0.10,
    },
}

PRESET_NAMES: list[str] = list(SCORING_PRESETS.keys())


# ---------------------------------------------------------------------------
# Beat-phase bias: adjust weights by story position
# ---------------------------------------------------------------------------

BEAT_PHASE_MAP: dict[str, str] = {
    # Setup — establishing the world
    "opening image": "setup",
    "theme stated": "setup",
    "set-up": "setup",
    "setup": "setup",
    "ordinary world": "setup",
    "hook": "setup",
    "ki": "setup",
    "you": "setup",
    # Catalyst — call to action
    "catalyst": "catalyst",
    "call to adventure": "catalyst",
    "refusal of the call": "catalyst",
    "crossing the first threshold": "catalyst",
    "need": "catalyst",
    "go": "catalyst",
    "plot turn 1": "catalyst",
    "break into two": "catalyst",
    # Development — exploring the new world
    "fun and games": "development",
    "b story": "development",
    "tests/allies/enemies": "development",
    "debate": "development",
    "search": "development",
    "shō": "development",
    "meeting the mentor": "development",
    "pinch 1": "development",
    # Midpoint — reversal territory
    "midpoint": "midpoint",
    "midpoint reversal": "midpoint",
    "approach to the inmost cave": "midpoint",
    "find": "midpoint",
    "ten": "midpoint",
    # Crisis — darkest hour
    "bad guys close in": "crisis",
    "all is lost": "crisis",
    "dark night of the soul": "crisis",
    "ordeal": "crisis",
    "pinch 2": "crisis",
    "take": "crisis",
    # Climax — peak confrontation
    "break into three": "climax",
    "finale": "climax",
    "resurrection": "climax",
    "plot turn 2": "climax",
    "climax": "climax",
    "confrontation": "climax",
    # Resolution — wrapping up
    "final image": "resolution",
    "return with the elixir": "resolution",
    "resolution": "resolution",
    "the road back": "resolution",
    "return": "resolution",
    "change": "resolution",
    "ketsu": "resolution",
    "reward": "resolution",
}

PHASE_MULTIPLIERS: dict[str, dict[str, float]] = {
    "setup": {
        "structure_fit": 1.4,
        "psyke_consistency": 1.0,
        "tension_gain": 0.8,
        "novelty": 1.0,
        "goal_alignment": 1.0,
    },
    "catalyst": {
        "structure_fit": 1.0,
        "psyke_consistency": 1.0,
        "tension_gain": 1.0,
        "novelty": 1.4,
        "goal_alignment": 1.0,
    },
    "development": {
        "structure_fit": 1.0,
        "psyke_consistency": 1.3,
        "tension_gain": 0.9,
        "novelty": 1.0,
        "goal_alignment": 1.3,
    },
    "midpoint": {
        "structure_fit": 1.0,
        "psyke_consistency": 1.0,
        "tension_gain": 1.4,
        "novelty": 1.3,
        "goal_alignment": 0.9,
    },
    "crisis": {
        "structure_fit": 0.9,
        "psyke_consistency": 1.4,
        "tension_gain": 1.0,
        "novelty": 0.9,
        "goal_alignment": 1.3,
    },
    "climax": {
        "structure_fit": 1.3,
        "psyke_consistency": 1.0,
        "tension_gain": 1.4,
        "novelty": 0.9,
        "goal_alignment": 1.0,
    },
    "resolution": {
        "structure_fit": 1.3,
        "psyke_consistency": 1.0,
        "tension_gain": 0.8,
        "novelty": 0.9,
        "goal_alignment": 1.4,
    },
}


def get_beat_phase(beat: str | None) -> str | None:
    """Map a beat name to its narrative phase, or None if unrecognized."""
    if not beat:
        return None
    return BEAT_PHASE_MAP.get(beat.strip().lower())


def apply_beat_bias(
    weights: dict[str, float], beat: str | None,
) -> dict[str, float]:
    """Apply phase-based multipliers to weights and renormalize to sum=1."""
    phase = get_beat_phase(beat)
    if not phase:
        return weights

    multipliers = PHASE_MULTIPLIERS.get(phase)
    if not multipliers:
        return weights

    biased = {k: weights.get(k, 0.0) * multipliers.get(k, 1.0) for k in weights}
    total = sum(biased.values())
    if total <= 0:
        return weights
    return {k: round(v / total, 4) for k, v in biased.items()}


# ---------------------------------------------------------------------------
# Weight adaptation — learn from user collapse choices
# ---------------------------------------------------------------------------

LEARNING_RATE: float = 0.05


def adapt_weights(
    current_weights: dict[str, float],
    chosen_factors: dict[str, float],
    unchosen_factors: list[dict[str, float]],
    learning_rate: float = LEARNING_RATE,
) -> dict[str, float]:
    """Nudge weights toward the factor pattern of the chosen branch.

    For each factor, the signal is (chosen - mean_unchosen). Positive signal
    means the user preferred a branch strong on that factor, so we increase
    its weight. Result is clamped to [0, 1] and renormalized to sum = 1.
    """
    if not unchosen_factors or not chosen_factors:
        return current_weights

    n = len(unchosen_factors)
    updated = {}
    for k, w in current_weights.items():
        chosen_val = chosen_factors.get(k, 0.0)
        mean_unchosen = sum(f.get(k, 0.0) for f in unchosen_factors) / n
        signal = chosen_val - mean_unchosen
        updated[k] = max(0.0, min(w + learning_rate * signal, 1.0))

    total = sum(updated.values())
    if total <= 0:
        return current_weights
    return {k: round(v / total, 4) for k, v in updated.items()}


# ---------------------------------------------------------------------------
# Hard constraints — forbid certain narrative outcomes
# ---------------------------------------------------------------------------

_NEGATIVE_PREFIXES = (
    "no ", "never ", "forbid ", "ban ", "don't ", "do not ", "not ",
)

_STOP_WORDS = frozenset({
    "the", "a", "an", "is", "of", "to", "and", "in", "for",
    "that", "this", "with", "any", "all", "be", "or",
})


def parse_constraint(raw: str) -> list[str]:
    """Extract forbidden keywords from a constraint string."""
    text = raw.strip().lower()
    for prefix in _NEGATIVE_PREFIXES:
        if text.startswith(prefix):
            text = text[len(prefix):]
            break
    return [w for w in text.split() if w not in _STOP_WORDS]


def check_constraints(
    branch: "Branch", constraints: list[str],
) -> list[str]:
    """Return list of constraints violated by this branch."""
    if not constraints:
        return []

    text = (
        f"{branch.title} {branch.description} "
        f"{branch.stakes} {branch.consequence}"
    ).lower()
    words = text.split()

    violated: list[str] = []
    for constraint in constraints:
        keywords = parse_constraint(constraint)
        if not keywords:
            continue
        if all(any(kw in w for w in words) for kw in keywords):
            violated.append(constraint)
    return violated


# ---------------------------------------------------------------------------
# Goal-driven optimization model
# ---------------------------------------------------------------------------

_GOAL_OBJECTIVE_KEYS = frozenset({
    "tension", "consistency", "novelty", "structure", "character_focus",
})

_DEFAULT_OBJECTIVES: dict[str, float] = {
    "tension": 0.2,
    "consistency": 0.2,
    "novelty": 0.2,
    "structure": 0.2,
    "character_focus": 0.2,
}


GOAL_FACTOR_MAP: dict[str, str] = {
    "tension": "tension_gain",
    "consistency": "psyke_consistency",
    "novelty": "novelty",
    "structure": "structure_fit",
    "character_focus": "goal_alignment",
}

_GOAL_PENALTY = 0.0

GOAL_PRESETS: dict[str, dict] = {
    "Balanced": {
        "objectives": {"tension": 0.2, "consistency": 0.2, "novelty": 0.2,
                       "structure": 0.2, "character_focus": 0.2},
        "min_constraints": {},
        "horizon": 1,
    },
    "High Tension": {
        "objectives": {"tension": 0.5, "consistency": 0.1, "novelty": 0.15,
                       "structure": 0.1, "character_focus": 0.15},
        "min_constraints": {"tension_gain": 0.3},
        "horizon": 2,
    },
    "Character-first": {
        "objectives": {"tension": 0.1, "consistency": 0.3, "novelty": 0.1,
                       "structure": 0.1, "character_focus": 0.4},
        "min_constraints": {"psyke_consistency": 0.5},
        "horizon": 1,
    },
    "Experimental": {
        "objectives": {"tension": 0.15, "consistency": 0.05, "novelty": 0.5,
                       "structure": 0.1, "character_focus": 0.2},
        "min_constraints": {},
        "horizon": 2,
    },
}

GOAL_PRESET_NAMES: list[str] = list(GOAL_PRESETS.keys())


def goals_from_preset(name: str) -> QuantumGoals:
    """Create a QuantumGoals instance from a named preset."""
    preset = GOAL_PRESETS.get(name)
    if preset is None:
        return QuantumGoals()
    return QuantumGoals(
        objectives=dict(preset["objectives"]),
        min_constraints=dict(preset["min_constraints"]),
        horizon=preset["horizon"],
    ).validate()


def parse_goal_constraint(text: str) -> tuple[str, float] | None:
    """Parse 'factor >= threshold' into (factor_key, threshold).

    Accepts objective names (tension, consistency, etc.) or factor names
    (tension_gain, psyke_consistency, etc.). Returns None on parse failure.
    """
    text = text.strip()
    if ">=" not in text:
        return None
    parts = text.split(">=")
    if len(parts) != 2:
        return None
    name = parts[0].strip().lower().replace(" ", "_")
    try:
        val = float(parts[1].strip())
    except ValueError:
        return None
    val = max(0.0, min(val, 1.0))

    if name in GOAL_FACTOR_MAP:
        return GOAL_FACTOR_MAP[name], val
    if name in GOAL_FACTOR_MAP.values():
        return name, val
    return None


def format_goals_panel(goals: QuantumGoals) -> str:
    """Render a compact text panel showing current goal configuration."""
    lines = ["═══ GOALS ═══", ""]
    lines.append("Objectives:")
    for key in ("tension", "consistency", "novelty", "structure", "character_focus"):
        val = goals.objectives.get(key, 0.2)
        bar_len = int(val * 20)
        bar = "█" * bar_len + "░" * (20 - bar_len)
        lines.append(f"  {key:<16} {bar} {val:.0%}")
    lines.append("")

    if goals.min_constraints:
        lines.append("Constraints:")
        for k, v in goals.min_constraints.items():
            lines.append(f"  {k} >= {v:.2f}")
        lines.append("")

    lines.append(f"Horizon: {goals.horizon}")
    lines.append("")

    matched = None
    for name, preset in GOAL_PRESETS.items():
        pg = goals_from_preset(name)
        if (pg.objectives == goals.objectives
                and pg.min_constraints == goals.min_constraints
                and pg.horizon == goals.horizon):
            matched = name
            break
    if matched:
        lines.append(f"Preset: {matched}")
    else:
        lines.append("Preset: Custom")

    return "\n".join(lines)


@dataclass
class QuantumGoals:
    objectives: dict[str, float] = field(default_factory=lambda: dict(_DEFAULT_OBJECTIVES))
    min_constraints: dict[str, float] = field(default_factory=dict)
    horizon: int = 1

    def validate(self) -> "QuantumGoals":
        """Clamp and normalize values in-place, return self."""
        for k in list(self.objectives):
            if k not in _GOAL_OBJECTIVE_KEYS:
                del self.objectives[k]
        for k in _GOAL_OBJECTIVE_KEYS:
            self.objectives.setdefault(k, 0.2)
        for k in self.objectives:
            self.objectives[k] = max(0.0, min(float(self.objectives[k]), 1.0))
        total = sum(self.objectives.values())
        if total > 0:
            self.objectives = {k: round(v / total, 4) for k, v in self.objectives.items()}

        for k in list(self.min_constraints):
            self.min_constraints[k] = max(0.0, min(float(self.min_constraints[k]), 1.0))

        self.horizon = max(1, min(int(self.horizon), 3))
        return self


def compute_goal_score(
    factors: dict[str, float],
    goals: QuantumGoals,
) -> tuple[float, bool]:
    """Compute goal_score and goal_valid from factors and goals.

    Returns (goal_score, goal_valid).
    goal_score = sum(objective_weight * mapped_factor).
    goal_valid = False if any min_constraint is violated.
    """
    score = 0.0
    for obj_key, weight in goals.objectives.items():
        factor_key = GOAL_FACTOR_MAP.get(obj_key)
        if factor_key:
            score += weight * factors.get(factor_key, 0.0)

    valid = True
    for factor_key, threshold in goals.min_constraints.items():
        if factors.get(factor_key, 0.0) < threshold:
            valid = False
            break

    if not valid:
        score = _GOAL_PENALTY

    return round(score, 4), valid


# ---------------------------------------------------------------------------
# Lookahead evaluation — lightweight simulation of future steps
# ---------------------------------------------------------------------------

from logosforge.quantum_outliner.lookahead_cache import (
    MAX_BRANCHES_PER_NODE,
    MAX_DEPTH,
)

_LOOKAHEAD_FIRST_BREADTH = 3
_LOOKAHEAD_DEEP_BREADTH = 2
_LOOKAHEAD_BLEND = 0.4

_FACTOR_DRIFT: dict[str, float] = {
    "tension_gain": -0.05,
    "psyke_consistency": 0.0,
    "novelty": -0.1,
    "structure_fit": -0.05,
    "goal_alignment": 0.0,
}

_VARIANT_SPREAD = 0.15


def _project_factors(
    factors: dict[str, float], variant_idx: int, breadth: int,
) -> dict[str, float]:
    """Project factors one step forward with deterministic variation."""
    center = (breadth - 1) / 2.0
    offset = (variant_idx - center) / max(center, 1.0) if breadth > 1 else 0.0

    projected: dict[str, float] = {}
    for k, v in factors.items():
        drift = _FACTOR_DRIFT.get(k, 0.0)
        spread = offset * _VARIANT_SPREAD
        projected[k] = max(0.0, min(1.0, v + drift + spread))
    return projected


def _simulate_ahead(
    factors: dict[str, float],
    goals: QuantumGoals,
    remaining: int,
    total_horizon: int,
    _depth: int = 0,
) -> float:
    """Recursively simulate future steps, return average expected value."""
    if _depth >= MAX_DEPTH:
        s, valid = compute_goal_score(factors, goals)
        return s if valid else 0.0

    is_first_level = remaining == total_horizon - 1
    breadth = min(
        _LOOKAHEAD_FIRST_BREADTH if is_first_level else _LOOKAHEAD_DEEP_BREADTH,
        MAX_BRANCHES_PER_NODE,
    )

    projections = [_project_factors(factors, i, breadth) for i in range(breadth)]

    scores: list[float] = []
    for proj in projections:
        if remaining > 1:
            scores.append(
                _simulate_ahead(proj, goals, remaining - 1, total_horizon, _depth + 1),
            )
        else:
            s, valid = compute_goal_score(proj, goals)
            scores.append(s if valid else 0.0)

    return sum(scores) / len(scores) if scores else 0.0


def evaluate_lookahead(
    factors: dict[str, float],
    goals: QuantumGoals,
) -> float:
    """Compute expected future value via lightweight simulation.

    Returns the immediate goal_score when horizon=1 (no extra lookahead).
    For horizon=2+, simulates follow-up steps and returns the average
    expected value over projected paths. Depth is hard-capped at MAX_DEPTH.
    """
    extra_steps = min(goals.horizon - 1, MAX_DEPTH)
    if extra_steps <= 0:
        score, valid = compute_goal_score(factors, goals)
        return score if valid else 0.0

    return round(_simulate_ahead(factors, goals, extra_steps, goals.horizon), 4)


def compute_blended_goal_score(
    factors: dict[str, float],
    goals: QuantumGoals,
) -> tuple[float, float, bool]:
    """Compute immediate goal_score, lookahead_score, and blend them.

    Returns (blended_goal_score, lookahead_score, goal_valid).
    When horizon=1, blended = immediate (no lookahead effect).
    Uses the global lookahead cache for horizon >= 2.
    """
    from logosforge.quantum_outliner.lookahead_cache import evaluate_lookahead_cached

    immediate, valid = compute_goal_score(factors, goals)
    if not valid:
        return 0.0, 0.0, False

    if goals.horizon <= 1:
        return immediate, immediate, valid

    lookahead = evaluate_lookahead_cached(factors, goals)
    blended = round(
        (1 - _LOOKAHEAD_BLEND) * immediate + _LOOKAHEAD_BLEND * lookahead, 4,
    )
    return blended, lookahead, valid


# ---------------------------------------------------------------------------
# Unified scoring — blend probability + goal + lookahead
# ---------------------------------------------------------------------------

UNIFIED_WEIGHTS: dict[str, float] = {
    "probability": 0.5,
    "goal_score": 0.3,
    "lookahead_score": 0.2,
}


def compute_unified_score(
    probability: float,
    goal_score: float,
    lookahead_score: float,
    *,
    weights: dict[str, float] | None = None,
) -> float:
    """Compute final unified score from all sub-scores.

    Falls back gracefully: if goal/lookahead are 0 (no goals configured),
    the score is driven by probability alone (normalized).
    """
    w = weights or UNIFIED_WEIGHTS
    w_prob = w.get("probability", 0.5)
    w_goal = w.get("goal_score", 0.3)
    w_look = w.get("lookahead_score", 0.2)

    raw = w_prob * probability + w_goal * goal_score + w_look * lookahead_score
    return round(max(0.0, min(raw, 1.0)), 4)


# ---------------------------------------------------------------------------
# Multi-objective scoring — Pareto front
# ---------------------------------------------------------------------------

PARETO_OBJECTIVES: list[str] = [
    "structure_fit",
    "psyke_consistency",
    "tension_gain",
    "novelty",
    "goal_alignment",
]

EXTENDED_PARETO_OBJECTIVES: list[str] = [
    "goal_score",
    "lookahead_score",
    "psyke_consistency",
]


def _dominates(
    a: dict[str, float],
    b: dict[str, float],
    objectives: list[str] | None = None,
) -> bool:
    """Return True if *a* dominates *b* (>= on all objectives, > on at least one)."""
    keys = objectives or PARETO_OBJECTIVES
    dominated, better = True, False
    for k in keys:
        va, vb = a.get(k, 0.0), b.get(k, 0.0)
        if va < vb:
            dominated = False
            break
        if va > vb:
            better = True
    return dominated and better


def compute_pareto_front(
    scored: list["ScoredBranch"],
    *,
    objectives: list[str] | None = None,
) -> list[str]:
    """Return branch IDs that belong to the Pareto-optimal (non-dominated) set.

    Violated branches (score=0 due to constraints) are excluded from the front.
    When *objectives* is provided, dominance is computed over those keys
    (looked up in each ScoredBranch's factors + goal_score/lookahead_score).
    """
    candidates = [s for s in scored if not s.violations]
    if not candidates:
        return []

    use_extended = objectives is not None

    def _vector(s: "ScoredBranch") -> dict[str, float]:
        v = dict(s.factors)
        if use_extended:
            v["goal_score"] = s.goal_score
            v["lookahead_score"] = s.lookahead_score
        return v

    vectors = [_vector(s) for s in candidates]
    keys = objectives or PARETO_OBJECTIVES

    front: list[str] = []
    for i, a_vec in enumerate(vectors):
        is_dominated = False
        for j, b_vec in enumerate(vectors):
            if i == j:
                continue
            if _dominates(b_vec, a_vec, keys):
                is_dominated = True
                break
        if not is_dominated:
            front.append(candidates[i].branch_id)
    return front


FACTOR_LABELS: dict[str, str] = {
    "structure_fit": "aligns with structural beat",
    "psyke_consistency": "consistent with story bible",
    "tension_gain": "raises narrative tension",
    "novelty": "offers fresh direction",
    "goal_alignment": "advances protagonist's goal",
}

_FACTOR_LABELS = FACTOR_LABELS

FACTOR_CHIP_LABELS: dict[str, str] = {
    "structure_fit": "structure",
    "psyke_consistency": "consistency",
    "tension_gain": "tension",
    "novelty": "novelty",
    "goal_alignment": "goal",
}

_CHIP_THRESHOLD = 0.1


def compute_tradeoff_chips(
    branch_factors: dict[str, float],
    all_factors: list[dict[str, float]],
    *,
    max_chips: int = 3,
) -> list[str]:
    """Return compact tradeoff chips like '↑ tension', '↓ consistency'.

    Compares one branch's factors against the mean across all branches.
    Only factors deviating by more than _CHIP_THRESHOLD are shown.
    """
    if not all_factors or not branch_factors:
        return []

    n = len(all_factors)
    means = {
        k: sum(f.get(k, 0.0) for f in all_factors) / n
        for k in PARETO_OBJECTIVES
    }

    deltas: list[tuple[float, str]] = []
    for k in PARETO_OBJECTIVES:
        delta = branch_factors.get(k, 0.0) - means[k]
        if abs(delta) >= _CHIP_THRESHOLD:
            deltas.append((delta, k))

    deltas.sort(key=lambda d: abs(d[0]), reverse=True)

    chips: list[str] = []
    for delta, k in deltas[:max_chips]:
        arrow = "↑" if delta > 0 else "↓"
        chips.append(f"{arrow} {FACTOR_CHIP_LABELS[k]}")
    return chips


def format_branch_chips(
    branch_factors: dict[str, float],
    all_factors: list[dict[str, float]],
    *,
    is_pareto: bool = False,
    max_chips: int = 3,
) -> str:
    """Format chips + optional Pareto badge into a single inline string."""
    chips = compute_tradeoff_chips(
        branch_factors, all_factors, max_chips=max_chips,
    )
    parts: list[str] = []
    if is_pareto:
        parts.append("●")
    parts.extend(chips)
    return "  ".join(parts) if parts else ""


def _factor_descriptor(value: float) -> str:
    if value >= 0.7:
        return "high"
    if value >= 0.4:
        return "strong"
    if value >= 0.2:
        return "moderate"
    return "some"


def explain_factors(
    factors: dict[str, float] | list[tuple[str, float]],
    top_n: int = 2,
) -> str:
    """Concise explanation from the top contributing factors.

    >>> explain_factors({"tension_gain": 0.9, "novelty": 0.5, "structure_fit": 0.1})
    'high tension_gain + strong novelty'
    """
    if isinstance(factors, dict):
        items = sorted(factors.items(), key=lambda kv: kv[1], reverse=True)[:top_n]
    else:
        items = list(factors)[:top_n]
    parts = [f"{_factor_descriptor(v)} {k}" for k, v in items if v > 0]
    return " + ".join(parts) if parts else "balanced across all factors"


@dataclass(frozen=True)
class CollapseRecommendation:
    branch_id: str
    title: str
    probability: float
    reason: str
    top_factors: list[tuple[str, float]]

    def explain(self) -> str:
        """Format as 'Recommended: Title (pct)\\n  because: ...'."""
        return format_recommendation(self)


SELECTION_MODES: tuple[str, ...] = ("weighted", "pareto")


def format_recommendation(
    rec: CollapseRecommendation,
    *,
    goals: "QuantumGoals | None" = None,
    branch: "Branch | None" = None,
) -> str:
    """Format a recommendation with factor-based explanation."""
    lines = [f"Recommended: {rec.title}  ({rec.probability:.0%})"]
    lines.append("  because:")
    lines.append(f"    - {explain_factors(rec.top_factors)}")
    if goals is not None and branch is not None:
        for reason in explain_goal_reasoning(branch, goals):
            lines.append(f"    - {reason}")
    return "\n".join(lines)


def recommend_pareto(wf: "Wavefunction", *, max_candidates: int = 3) -> list[CollapseRecommendation]:
    """Return up to *max_candidates* Pareto-optimal branches as recommendations.

    Unlike recommend_collapse (single best), this presents the non-dominated
    set without forcing a ranking.
    """
    candidates = [
        b for b in wf.branches
        if b.is_pareto_optimal and b.probability > 0 and not b.violations
    ]
    if not candidates:
        return []

    candidates.sort(key=lambda b: b.probability, reverse=True)
    candidates = candidates[:max_candidates]

    recs: list[CollapseRecommendation] = []
    for b in candidates:
        top_factors = sorted(b.factors.items(), key=lambda kv: kv[1], reverse=True)[:2]
        explanation = explain_factors(top_factors)
        recs.append(CollapseRecommendation(
            branch_id=b.id,
            title=b.title,
            probability=b.probability,
            reason=explanation,
            top_factors=top_factors,
        ))
    return recs


def format_pareto_recommendation(candidates: list[CollapseRecommendation]) -> str:
    """Format Pareto candidates as a multi-line recommendation block."""
    if not candidates:
        return "No Pareto-optimal candidates available."
    lines = ["Pareto-optimal candidates:"]
    for rec in candidates:
        explanation = explain_factors(rec.top_factors)
        lines.append(f"  ● {rec.title}  [{rec.branch_id}]  — {explanation}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# A/B/C comparison — side-by-side top branches
# ---------------------------------------------------------------------------

_COMPARISON_LABELS = ("A", "B", "C")

MAX_COMPARE = 3


@dataclass(frozen=True)
class ComparisonEntry:
    label: str
    branch_id: str
    title: str
    description: str
    probability: float
    factors: dict[str, float]
    is_pareto_optimal: bool
    violations: list[str]


@dataclass(frozen=True)
class ComparisonTable:
    entries: list[ComparisonEntry]
    factor_deltas: dict[str, list[str]]


def select_comparison_branches(
    wf: "Wavefunction",
    branch_ids: list[str] | None = None,
    *,
    max_branches: int = MAX_COMPARE,
) -> list[Branch]:
    """Pick up to *max_branches* branches for comparison.

    If *branch_ids* is given, use those (in order).  Otherwise pick the
    top branches by probability, preferring non-violated ones.
    """
    cap = min(max_branches, MAX_COMPARE)
    if branch_ids:
        by_id = {b.id: b for b in wf.branches}
        return [by_id[bid] for bid in branch_ids[:cap] if bid in by_id]

    viable = sorted(
        [b for b in wf.branches if not b.violations],
        key=lambda b: b.probability, reverse=True,
    )
    return viable[:cap]


def build_comparison(
    wf: "Wavefunction",
    branch_ids: list[str] | None = None,
) -> ComparisonTable:
    """Build a structured comparison of up to 3 branches."""
    selected = select_comparison_branches(wf, branch_ids)
    if not selected:
        return ComparisonTable(entries=[], factor_deltas={})

    entries: list[ComparisonEntry] = []
    for idx, b in enumerate(selected):
        entries.append(ComparisonEntry(
            label=_COMPARISON_LABELS[idx],
            branch_id=b.id,
            title=b.title,
            description=b.description,
            probability=b.probability,
            factors=dict(b.factors),
            is_pareto_optimal=b.is_pareto_optimal,
            violations=list(b.violations),
        ))

    factor_deltas: dict[str, list[str]] = {}
    if len(entries) >= 2:
        for k in PARETO_OBJECTIVES:
            vals = [e.factors.get(k, 0.0) for e in entries]
            hi, lo = max(vals), min(vals)
            arrows: list[str] = []
            for v in vals:
                if hi - lo < 0.05:
                    arrows.append("=")
                elif v == hi:
                    arrows.append("↑")
                elif v == lo:
                    arrows.append("↓")
                else:
                    arrows.append("–")
            factor_deltas[k] = arrows

    return ComparisonTable(entries=entries, factor_deltas=factor_deltas)


def format_comparison(table: ComparisonTable) -> str:
    """Render a compact text comparison table."""
    if not table.entries:
        return "No branches available for comparison."

    lines: list[str] = ["═══ COMPARE ═══", ""]

    for e in table.entries:
        pareto_mark = "  ●" if e.is_pareto_optimal else ""
        lines.append(f"  [{e.label}] {e.title}  [{e.branch_id}]  {e.probability:.0%}{pareto_mark}")
        lines.append(f"      {e.description}")
        lines.append("")

    if table.factor_deltas:
        header_labels = "  ".join(f"[{e.label}]" for e in table.entries)
        lines.append(f"  Factor            {header_labels}")
        lines.append(f"  {'─' * (20 + 5 * len(table.entries))}")
        for k in PARETO_OBJECTIVES:
            arrows = table.factor_deltas.get(k, [])
            chip = FACTOR_CHIP_LABELS.get(k, k)
            padded = chip.ljust(16)
            cols = "  ".join(f" {a} " for a in arrows)
            lines.append(f"  {padded}  {cols}")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Ensemble scoring — combine heuristic + LLM evaluator
# ---------------------------------------------------------------------------

ENSEMBLE_ALPHA: float = 0.7


def score_with_heuristic(
    branch: Branch,
    wf: Wavefunction,
    *,
    psyke: PsykeSignals | None = None,
    protagonist_goal: str = "",
    sibling_titles: set[str] | None = None,
) -> dict[str, float]:
    """Compute heuristic factor scores for a single branch (wrapper around compute_factors)."""
    return compute_factors(
        branch, wf,
        psyke=psyke,
        protagonist_goal=protagonist_goal,
        sibling_titles=sibling_titles,
    )


def ensemble_combine(
    heuristic: dict[str, float],
    llm: dict[str, float] | None,
    alpha: float = ENSEMBLE_ALPHA,
) -> dict[str, float]:
    """Blend heuristic and LLM factor scores: α·heuristic + (1-α)·llm.

    If *llm* is None, returns heuristic unchanged.
    """
    if llm is None:
        return heuristic
    a = max(0.0, min(alpha, 1.0))
    return {
        k: round(a * heuristic.get(k, 0.0) + (1 - a) * llm.get(k, 0.0), 4)
        for k in heuristic
    }


def explain_goal_reasoning(
    branch: "Branch",
    goals: "QuantumGoals",
) -> list[str]:
    """Produce concise goal-aware explanation lines for a branch."""
    lines: list[str] = []
    reverse_map = {v: k for k, v in GOAL_FACTOR_MAP.items()}

    top_obj = sorted(goals.objectives.items(), key=lambda kv: kv[1], reverse=True)
    for obj_key, weight in top_obj:
        if weight < 0.15:
            continue
        factor_key = GOAL_FACTOR_MAP.get(obj_key, "")
        val = branch.factors.get(factor_key, 0.0)
        if val >= 0.4:
            descriptor = "high" if val >= 0.7 else "strong"
            lines.append(f"aligns with goal: {descriptor} {obj_key.replace('_', ' ')}")
            break

    for factor_key, threshold in goals.min_constraints.items():
        val = branch.factors.get(factor_key, 0.0)
        obj_name = reverse_map.get(factor_key, factor_key)
        if val >= threshold:
            lines.append(f"maintains {obj_name.replace('_', ' ')} ≥ {threshold:.1f}")

    if goals.horizon > 1 and branch.lookahead_score > 0:
        lines.append(f"strong lookahead outcome ({goals.horizon}-step)")

    return lines


def explain_wavefunction(
    wf: "Wavefunction",
    *,
    goals: "QuantumGoals | None" = None,
) -> str:
    """Per-branch factor explanation, sorted by probability."""
    branches = sorted(wf.branches, key=lambda b: b.probability, reverse=True)
    scored = [b for b in branches if b.factors]
    if not scored:
        return "No scoring data available. Generate branches first."

    lines: list[str] = []
    for b in scored:
        if b.violations:
            lines.append(f"{b.title}  [{b.id}]  (0%)")
            for v in b.violations:
                lines.append(f"  BLOCKED: violates \"{v}\"")
        else:
            lines.append(f"{b.title}  [{b.id}]  ({b.probability:.0%})")
            lines.append(f"  because:")
            explanation = explain_factors(b.factors)
            lines.append(f"    - {explanation}")
            if goals is not None:
                for reason in explain_goal_reasoning(b, goals):
                    lines.append(f"    - {reason}")
    return "\n".join(lines)


@dataclass(frozen=True)
class ScoredBranch:
    branch_id: str
    score: float
    probability: float
    factors: dict[str, float]
    violations: list[str] = field(default_factory=list)
    is_pareto_optimal: bool = False
    goal_score: float = 0.0
    goal_valid: bool = True
    lookahead_score: float = 0.0
    unified_score: float = 0.0


def score_branches(
    wf: Wavefunction,
    *,
    psyke: PsykeSignals | None = None,
    protagonist_goal: str = "",
    weights: dict[str, float] | None = None,
    constraints: list[str] | None = None,
    llm_scores: dict[str, dict[str, float]] | None = None,
    ensemble_alpha: float = ENSEMBLE_ALPHA,
    goals: QuantumGoals | None = None,
    unified_weights: dict[str, float] | None = None,
) -> list[ScoredBranch]:
    """Score all branches in a wavefunction. Returns sorted high-to-low.

    When *llm_scores* maps branch-id → factor dict, each branch's heuristic
    factors are blended with the LLM factors using *ensemble_alpha*.

    When *goals* is provided, each branch also receives a goal_score
    (weighted by objectives), goal_valid flag, lookahead_score, and
    unified_score blending all sub-scores.

    Pareto front uses extended objectives (goal_score, lookahead_score,
    psyke_consistency) when goals are active.
    """
    w = apply_beat_bias(weights or DEFAULT_WEIGHTS, wf.structure_beat)

    scored: list[ScoredBranch] = []
    existing_titles = {b.title.lower() for b in wf.branches}

    for b in wf.branches:
        others = existing_titles - {b.title.lower()}
        heuristic = compute_factors(
            b, wf,
            psyke=psyke,
            protagonist_goal=protagonist_goal,
            sibling_titles=others,
        )
        llm = llm_scores.get(b.id) if llm_scores else None
        factors = ensemble_combine(heuristic, llm, ensemble_alpha)

        raw = sum(factors[k] * w.get(k, 0.0) for k in factors)
        score = max(0.0, min(raw, 1.0))

        violations = check_constraints(b, constraints or [])
        if violations:
            score = 0.0

        goal_score = 0.0
        goal_valid = True
        lookahead_score = 0.0
        if goals is not None:
            goal_score, lookahead_score, goal_valid = compute_blended_goal_score(
                factors, goals,
            )

        scored.append(ScoredBranch(
            branch_id=b.id,
            score=round(score, 4),
            probability=0.0,
            factors={k: round(v, 4) for k, v in factors.items()},
            violations=violations,
            goal_score=goal_score,
            goal_valid=goal_valid,
            lookahead_score=lookahead_score,
        ))

    probs = _softmax([s.score for s in scored])
    # Zero probability for violated branches, renormalize
    probs = [0.0 if s.violations else p for s, p in zip(scored, probs)]
    total_p = sum(probs)
    if total_p > 0:
        probs = [round(p / total_p, 4) for p in probs]

    scored = [
        ScoredBranch(
            branch_id=s.branch_id,
            score=s.score,
            probability=p,
            factors=s.factors,
            violations=s.violations,
            goal_score=s.goal_score,
            goal_valid=s.goal_valid,
            lookahead_score=s.lookahead_score,
            unified_score=(
                0.0 if s.violations else
                compute_unified_score(
                    p, s.goal_score, s.lookahead_score,
                    weights=unified_weights,
                )
            ) if goals is not None else p,
        )
        for s, p in zip(scored, probs)
    ]

    pareto_objs = EXTENDED_PARETO_OBJECTIVES if goals is not None else None
    pareto_ids = set(compute_pareto_front(scored, objectives=pareto_objs))
    scored = [
        ScoredBranch(
            branch_id=s.branch_id,
            score=s.score,
            probability=s.probability,
            factors=s.factors,
            violations=s.violations,
            is_pareto_optimal=s.branch_id in pareto_ids,
            goal_score=s.goal_score,
            goal_valid=s.goal_valid,
            lookahead_score=s.lookahead_score,
            unified_score=s.unified_score,
        )
        for s in scored
    ]

    scored.sort(key=lambda s: s.unified_score, reverse=True)
    return scored


def apply_scores(wf: Wavefunction, scored: list[ScoredBranch]) -> None:
    """Write scoring results back onto the Branch objects."""
    by_id = {s.branch_id: s for s in scored}
    for b in wf.branches:
        s = by_id.get(b.id)
        if s:
            b.score = s.score
            b.probability = s.probability
            b.factors = dict(s.factors)
            b.violations = list(s.violations)
            b.is_pareto_optimal = s.is_pareto_optimal
            b.goal_score = s.goal_score
            b.goal_valid = s.goal_valid
            b.lookahead_score = s.lookahead_score
            b.unified_score = s.unified_score


def recommend_collapse(wf: Wavefunction) -> CollapseRecommendation | None:
    """Pick the highest-probability branch as collapse recommendation.

    Returns None if fewer than 2 branches or none are scored.
    """
    candidates = [b for b in wf.branches if b.probability > 0]
    if len(candidates) < 2:
        return None

    best = max(candidates, key=lambda b: b.probability)

    runner_up = max(
        (b for b in candidates if b.id != best.id),
        key=lambda b: b.probability,
    )
    is_tie = abs(best.probability - runner_up.probability) < 0.01

    top_factors = sorted(best.factors.items(), key=lambda kv: kv[1], reverse=True)[:2]

    parts = [_FACTOR_LABELS.get(k, k) for k, _ in top_factors if _ > 0]
    if is_tie:
        parts = [f"near-tie with {runner_up.title}"] + parts[:1]
    reason = "; ".join(parts) if parts else "highest overall score"

    return CollapseRecommendation(
        branch_id=best.id,
        title=best.title,
        probability=best.probability,
        reason=reason,
        top_factors=top_factors,
    )


def compute_probabilities(
    possibilities: list[QuantumPossibility],
    *,
    temperature: float = 1.0,
) -> None:
    """Normalize scores to probabilities via softmax. Mutates in place."""
    probs = _softmax([p.score for p in possibilities], temperature=temperature)
    for p, prob in zip(possibilities, probs):
        p.probability = prob


def _softmax(
    scores: list[float], *, temperature: float = 1.0,
) -> list[float]:
    """Softmax normalization returning probabilities that sum to 1."""
    if not scores:
        return []

    n = len(scores)
    if all(s == 0.0 for s in scores):
        uniform = round(1.0 / n, 4)
        return [uniform] * n

    t = max(temperature, 1e-9)
    max_s = max(scores)
    exps = [math.exp((s - max_s) / t) for s in scores]
    total = sum(exps)
    return [round(e / total, 4) for e in exps]


def compute_factors(
    branch: Branch,
    wf: Wavefunction,
    *,
    psyke: PsykeSignals | None = None,
    protagonist_goal: str = "",
    sibling_titles: set[str] | None = None,
) -> dict[str, float]:
    """Compute individual factor scores (0–1) for a single branch."""
    return {
        "structure_fit": _score_structure_fit(branch, wf),
        "psyke_consistency": _score_psyke_consistency(branch, psyke),
        "tension_gain": _score_tension_gain(branch),
        "novelty": _score_novelty(branch, sibling_titles or set()),
        "goal_alignment": _score_goal_alignment(branch, protagonist_goal),
    }


def _score_structure_fit(branch: Branch, wf: Wavefunction) -> float:
    score = 0.0
    if branch.structure_beat and wf.structure_beat:
        if branch.structure_beat == wf.structure_beat:
            score += 0.5
        else:
            b_words = set(branch.structure_beat.lower().split())
            w_words = set(wf.structure_beat.lower().split())
            if b_words and w_words:
                overlap = len(b_words & w_words) / max(len(b_words | w_words), 1)
                score += overlap * 0.3
    if branch.structure_method and wf.structure_method:
        if branch.structure_method == wf.structure_method:
            score += 0.3
        elif branch.structure_method.lower() in wf.structure_method.lower():
            score += 0.15
    if branch.branch_type == "intensification":
        score += 0.2
    elif branch.branch_type in ("alternative", "resolution"):
        score += 0.1
    return min(score, 1.0)


def _score_psyke_consistency(
    branch: Branch, psyke: PsykeSignals | None,
) -> float:
    if not psyke or not psyke.keywords:
        return 0.5

    text = f"{branch.title} {branch.description} {branch.stakes} {branch.consequence}".lower()
    words = set(text.split())
    _stop = {"the", "a", "an", "is", "of", "to", "and", "in", "for"}

    score = 0.0

    char_names = {c["name"].lower() for c in psyke.characters}
    name_hits = char_names & words
    if name_hits:
        score += min(len(name_hits) * 0.2, 0.4)

    kw_hits = psyke.keywords & words
    if kw_hits:
        score += min(len(kw_hits) * 0.05, 0.3)

    for rel in psyke.relations:
        pair = {rel["from"].lower(), rel["to"].lower()}
        if pair & words:
            score += 0.15
            break

    for arc in psyke.unresolved_arcs:
        arc_words = set(arc["arc"].lower().split()) - _stop
        if arc_words & words:
            score += 0.15
            break

    for prog in psyke.progressions:
        prog_words = set(prog["text"].lower().split()) - _stop
        if prog_words & words:
            score += min(len(prog_words & words) * 0.1, 0.2)
            break

    return min(score, 1.0)


def _score_tension_gain(branch: Branch) -> float:
    text = f"{branch.description} {branch.stakes} {branch.consequence}".lower()
    words = set(text.split())
    hits = _TENSION_KEYWORDS & words
    if not hits:
        return 0.1
    return min(len(hits) * 0.15, 1.0)


def _score_novelty(branch: Branch, sibling_titles: set[str]) -> float:
    if not sibling_titles:
        return 0.8

    title_words = set(branch.title.lower().split())
    desc_words = set(branch.description.lower().split())
    branch_words = title_words | desc_words

    max_overlap = 0.0
    for sib in sibling_titles:
        sib_words = set(sib.split())
        if not sib_words:
            continue
        overlap = len(branch_words & sib_words) / max(len(sib_words), 1)
        if overlap > max_overlap:
            max_overlap = overlap

    return max(1.0 - max_overlap, 0.0)


def _score_goal_alignment(branch: Branch, goal: str) -> float:
    if not goal.strip():
        return 0.5

    goal_words = set(goal.lower().split()) - {"the", "a", "an", "is", "to", "of"}
    text = f"{branch.title} {branch.description} {branch.consequence}".lower()
    branch_words = set(text.split())

    if not goal_words:
        return 0.5

    hits = goal_words & branch_words
    return min(len(hits) / len(goal_words), 1.0)
