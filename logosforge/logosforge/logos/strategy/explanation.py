"""Human-readable explanations for a StrategyDecision."""

from __future__ import annotations

from logosforge.logos.strategy import registry as reg


def explain(decision) -> str:
    """A concise, plain-language account of why the active strategy was chosen."""
    dom = reg.get_strategy(decision.dominant_strategy)
    dom_name = dom.name if dom else (decision.dominant_strategy or "Default")
    parts = [
        f"{dom_name} is active because the project mode is "
        f"{decision.narrative_engine or 'novel'}"
    ]
    if decision.section_name:
        parts[0] += f" and the current section is {decision.section_name}"
    parts[0] += "."

    others = [s for s in decision.active_strategies if s != decision.dominant_strategy]
    if others:
        names = ", ".join(
            (reg.get_strategy(s).name if reg.get_strategy(s) else s) for s in others
        )
        parts.append(f"Also active: {names}.")

    if decision.suppressed_strategies:
        names = ", ".join(
            (reg.get_strategy(s).name if reg.get_strategy(s) else s)
            for s in decision.suppressed_strategies
        )
        parts.append(f"Suppressed: {names}.")

    if decision.recommended_logos_actions:
        parts.append(
            "Logos prioritizes: "
            + ", ".join(decision.recommended_logos_actions[:4]) + "."
        )
    if decision.included_context_blocks:
        parts.append(
            "Context included: " + ", ".join(decision.included_context_blocks) + "."
        )
    if decision.user_override:
        parts.append(f"(User override: {decision.user_override}.)")
    return " ".join(parts)
