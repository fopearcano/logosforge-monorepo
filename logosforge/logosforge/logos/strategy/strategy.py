"""NarrativeStrategy + StrategyDecision — the deterministic strategy contract.

A *strategy* is a named reasoning profile (e.g. "Screenplay", "Go McKee") that
declares when it activates and what it prefers/suppresses. A *decision* is the
resolved outcome for a given situation: which strategies are active, which one
dominates, which context blocks to include, and a human explanation.

Both are plain, serializable value objects — no Qt, no ORM, no secrets, no LLM.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class NarrativeStrategy:
    id: str
    name: str
    description: str = ""
    applies_to_modes: tuple[str, ...] = ()      # narrative engines; () = any
    priority: int = 0                           # higher wins ties
    enabled: bool = True
    context_rules: list[str] = field(default_factory=list)   # context block ids
    diagnostic_rules: list[str] = field(default_factory=list)  # diagnostic categories
    action_rules: list[str] = field(default_factory=list)    # preferred logos action ids
    conflict_rules: dict[str, str] = field(default_factory=dict)  # principle -> stance

    def applies_to(self, engine: str) -> bool:
        return not self.applies_to_modes or engine in self.applies_to_modes

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "applies_to_modes": list(self.applies_to_modes),
            "priority": self.priority,
            "enabled": self.enabled,
            "context_rules": list(self.context_rules),
            "diagnostic_rules": list(self.diagnostic_rules),
            "action_rules": list(self.action_rules),
            "conflict_rules": dict(self.conflict_rules),
        }


@dataclass
class StrategyDecision:
    project_id: int
    section_name: str = ""
    narrative_engine: str = ""
    writing_format: str = ""
    outline_template: str = ""
    active_strategies: list[str] = field(default_factory=list)   # strategy ids
    dominant_strategy: str = ""
    suppressed_strategies: list[str] = field(default_factory=list)
    included_context_blocks: list[str] = field(default_factory=list)
    active_diagnostics: list[str] = field(default_factory=list)  # diagnostic categories
    recommended_logos_actions: list[str] = field(default_factory=list)
    reasoning_notes: list[str] = field(default_factory=list)
    explanation: str = ""
    user_override: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "section_name": self.section_name,
            "narrative_engine": self.narrative_engine,
            "writing_format": self.writing_format,
            "outline_template": self.outline_template,
            "active_strategies": list(self.active_strategies),
            "dominant_strategy": self.dominant_strategy,
            "suppressed_strategies": list(self.suppressed_strategies),
            "included_context_blocks": list(self.included_context_blocks),
            "active_diagnostics": list(self.active_diagnostics),
            "recommended_logos_actions": list(self.recommended_logos_actions),
            "reasoning_notes": list(self.reasoning_notes),
            "explanation": self.explanation,
            "user_override": self.user_override,
        }
