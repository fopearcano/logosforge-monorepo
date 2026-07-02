"""Opt-in Assistant context from a strategy decision.

Produces a short, read-only ``[Strategy]`` block the host *could* fold into the
Assistant prompt. It is intentionally NOT wired into AssistantPanel here — the
caller decides whether to include it — so AssistantPanel behaviour is untouched.
"""

from __future__ import annotations


def gather_strategy_context(db, project_id: int, section_name: str = "") -> str:
    """A compact '[Strategy]' block describing the active reasoning, or ''."""
    try:
        from logosforge.settings import get_manager
        if not bool(get_manager().get("strategy_enabled")):
            return ""
    except Exception:
        pass
    try:
        from logosforge.logos.strategy.router import StrategyRouter
        decision = StrategyRouter(db, project_id).decide(section_name)
    except Exception:
        return ""
    if not decision.dominant_strategy:
        return ""
    lines = [f"[Strategy] {decision.explanation}"]
    return "\n".join(lines)
