"""Registry of available narrative strategies.

Holds the built-in strategies (Default, the five mediums, Go McKee, Idea di
Controllo, PSYKE Continuity, Narrative Health, Quantum Classical/Lambda) plus
any registered at runtime. Strategy *activation* is decided by the router; the
registry only declares what exists and its static rules.
"""

from __future__ import annotations

from logosforge.logos.strategy import medium_profiles as mp
from logosforge.logos.strategy.strategy import NarrativeStrategy

# Strategy ids.
S_DEFAULT = "default"
S_NOVEL = "novel"
S_SCREENPLAY = "screenplay"
S_GRAPHIC_NOVEL = "graphic_novel"
S_STAGE_SCRIPT = "stage_script"
S_SERIES = "series"
S_GOMCKEE = "go_mckee"
S_CONTROLLING_IDEA = "controlling_idea"
S_PSYKE_CONTINUITY = "psyke_continuity"
S_NARRATIVE_HEALTH = "narrative_health"
S_QUANTUM_CLASSICAL = "quantum_classical"
S_QUANTUM_LAMBDA = "quantum_lambda"

# Medium strategy id per engine.
MEDIUM_STRATEGY = {
    mp.NOVEL: S_NOVEL,
    mp.SCREENPLAY: S_SCREENPLAY,
    mp.GRAPHIC_NOVEL: S_GRAPHIC_NOVEL,
    mp.STAGE_SCRIPT: S_STAGE_SCRIPT,
    mp.SERIES: S_SERIES,
}

_REGISTRY: dict[str, NarrativeStrategy] = {}


def register(strategy: NarrativeStrategy) -> NarrativeStrategy:
    _REGISTRY[strategy.id] = strategy
    return strategy


def get_strategy(strategy_id: str) -> NarrativeStrategy | None:
    return _REGISTRY.get(strategy_id)


def list_strategies() -> list[NarrativeStrategy]:
    return list(_REGISTRY.values())


def _build_medium_strategy(engine: str, priority: int) -> NarrativeStrategy:
    profile = mp.get_profile(engine)
    return NarrativeStrategy(
        id=MEDIUM_STRATEGY[engine], name=f"{profile.name} Strategy",
        description=f"Medium reasoning for {profile.name}: "
                    + ", ".join(profile.priorities[:4]) + ".",
        applies_to_modes=(engine,), priority=priority,
        context_rules=list(profile.context_blocks),
        diagnostic_rules=list(profile.diagnostic_categories),
        action_rules=list(profile.preferred_actions),
        conflict_rules=dict(profile.principles),
    )


# -- Built-ins ---------------------------------------------------------------

register(NarrativeStrategy(
    id=S_DEFAULT, name="Default Logos Strategy", priority=0,
    description="Balanced reasoning used when no medium dominates.",
    context_rules=[mp.CTX_SCENE, mp.CTX_PSYKE, mp.CTX_OUTLINE],
    diagnostic_rules=["structure", "character", "continuity"],
))

# Medium strategies (priority 50 — project mode is a strong default).
for _eng in (mp.NOVEL, mp.SCREENPLAY, mp.GRAPHIC_NOVEL, mp.STAGE_SCRIPT, mp.SERIES):
    register(_build_medium_strategy(_eng, priority=50))

register(NarrativeStrategy(
    id=S_GOMCKEE, name="Go McKee Strategy", priority=70, enabled=False,
    description="Conflict-centric craft pressure; activates only when the Go "
                "McKee plugin is enabled.",
    context_rules=[mp.CTX_SCENE, mp.CTX_PSYKE],
    diagnostic_rules=["conflict", "structure", "setup_payoff"],
    action_rules=["identify_weakness", "strengthen_conflict"],
    conflict_rules={"conflict": "emphasize"},
))

register(NarrativeStrategy(
    id=S_CONTROLLING_IDEA, name="Idea di Controllo Strategy", priority=65,
    enabled=False,
    description="Aligns scenes to the project's controlling idea; activates "
                "when a Controlling Idea is enabled.",
    context_rules=[mp.CTX_SCENE, mp.CTX_PSYKE],
    diagnostic_rules=["theme", "structure"],
    action_rules=["check_thematic_cluster"],
    conflict_rules={"thematic_alignment": "emphasize"},
))

register(NarrativeStrategy(
    id=S_PSYKE_CONTINUITY, name="PSYKE Continuity Strategy", priority=40,
    description="Prioritizes character/relationship/continuity coherence.",
    context_rules=[mp.CTX_PSYKE, mp.CTX_GRAPH],
    diagnostic_rules=["character", "relationship", "continuity", "psyke"],
    action_rules=["check_continuity", "suggest_relations", "suggest_progression"],
))

register(NarrativeStrategy(
    id=S_NARRATIVE_HEALTH, name="Narrative Health Strategy", priority=45,
    description="Surfaces top project risks from the health report.",
    context_rules=[mp.CTX_HEALTH],
    diagnostic_rules=["structure", "character", "continuity", "theme"],
))

register(NarrativeStrategy(
    id=S_QUANTUM_CLASSICAL, name="Quantum Classical Strategy", priority=30,
    description="Enforces linear causality and stable structure.",
    conflict_rules={"causality": "emphasize", "superposition": "suppress"},
))

register(NarrativeStrategy(
    id=S_QUANTUM_LAMBDA, name="Quantum Lambda Strategy", priority=35,
    enabled=False,
    description="Allows superposition / alternate timelines; activates only "
                "when Lambda mode is on.",
    conflict_rules={"causality": "allow", "superposition": "emphasize"},
))
