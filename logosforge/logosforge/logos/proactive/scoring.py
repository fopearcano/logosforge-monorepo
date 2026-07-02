"""Deterministic confidence scoring for proactive Logos suggestions.

Confidence is intentionally simple and *explainable from evidence* — no invented
precision. Each detector picks a base score for the rule and may bump it up with
concrete evidence (e.g. "appears in N scenes"). Scores are clamped to [0, 1].
"""

from __future__ import annotations

# Default visibility threshold — suggestions below this are not shown by default.
DEFAULT_CONFIDENCE_THRESHOLD = 0.65

# Base confidences per rule strength (deterministic).
BASE_HIGH = 0.85      # the evidence is unambiguous (empty field, isolated node)
BASE_MEDIUM = 0.70    # likely an issue, some judgement involved
BASE_LOW = 0.55       # weak signal — below default threshold, hidden by default


def clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def scale_by_prevalence(base: float, count: int, *, per_unit: float = 0.03,
                        cap: float = 0.12) -> float:
    """Raise *base* a little when an issue is more prevalent / impactful.

    e.g. a relationless character that appears in many scenes is a more
    confident problem than one that appears once. The bump is deterministic
    and capped so it never manufactures false certainty.
    """
    bump = min(cap, max(0, count) * per_unit)
    return clamp(base + bump)
