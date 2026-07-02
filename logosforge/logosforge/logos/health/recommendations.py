"""Deterministic health recommendations derived from diagnostics.

Each recommendation is built from a high-severity diagnostic: the problem, why
it matters, the evidence, the suggested Logos action, and the target. No LLM —
explanations come from the diagnostic, not a model.
"""

from __future__ import annotations

from logosforge.logos.health.report import HealthRecommendation

# Why each diagnostic category matters (deterministic copy).
_WHY = {
    "structure": "Weak structure leaves scenes without escalation or turns.",
    "character": "Underdeveloped characters flatten the emotional arc.",
    "relationship": "Missing relationships make the cast feel disconnected.",
    "theme": "An absent or thin theme weakens what the story is about.",
    "continuity": "Unanchored state changes break the reader's trust.",
    "timeline": "Gaps in the timeline confuse cause and effect.",
    "setup_payoff": "Setups without payoffs feel like broken promises.",
    "graph": "Isolated entities suggest the story web has loose ends.",
    "psyke": "Incomplete bible entries starve the rest of the tools of context.",
}

_MAX_RECOMMENDATIONS = 8


def build_recommendations(diagnostics) -> list[HealthRecommendation]:
    """Top, prioritized recommendations from the most severe diagnostics."""
    from logosforge.logos.actions import get_action

    ranked = sorted(
        diagnostics,
        key=lambda d: (d.severity_rank, d.confidence),
        reverse=True,
    )
    out: list[HealthRecommendation] = []
    seen: set[str] = set()
    for d in ranked:
        # Only actionable, meaningfully-severe diagnostics become recommendations.
        if d.severity_rank < 1:  # skip pure info
            continue
        key = (d.category, d.target_type, d.target_id)
        if key in seen:
            continue
        seen.add(key)
        action = d.suggested_actions[0] if d.suggested_actions else ""
        action_obj = get_action(action) if action else None
        out.append(HealthRecommendation(
            problem=d.title,
            why=_WHY.get(d.category, "This may weaken the narrative."),
            evidence=d.evidence,
            suggested_action=action,
            action_label=action_obj.label if action_obj else action,
            target_type=d.target_type,
            target_id=d.target_id,
            category=d.category,
        ))
        if len(out) >= _MAX_RECOMMENDATIONS:
            break
    return out
