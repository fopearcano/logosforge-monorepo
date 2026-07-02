"""Guided Workflow template model (Phase 10O).

Pure data: a :class:`WorkflowTemplate` is an ordered list of
:class:`WorkflowStep` descriptors. Templates are **data-driven and
serializable** — every field is a primitive or list of primitives, and the
deterministic "is this step done?" logic is referenced by *name* (a key into
the completion-check registry) rather than embedded as a callable.

Nothing here touches Qt, the LLM backend, or the database. A template only
*describes* a recommended path through existing systems; the engine turns it
into persisted :class:`~logosforge.models.models.WorkflowRun` state.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Step kinds. ``creative`` steps are user-judgement steps (drafting, revising)
# and are NEVER auto-completed — only the user can mark them done. ``check``
# steps have a deterministic completion check that may auto-complete them.
# ``manual`` steps are simple acknowledgements (no auto-check) the user ticks.
KIND_CREATIVE = "creative"
KIND_CHECK = "check"
KIND_MANUAL = "manual"
STEP_KINDS = (KIND_CREATIVE, KIND_CHECK, KIND_MANUAL)


@dataclass
class WorkflowStep:
    """One step in a workflow template (a recommendation, not an action)."""

    id: str
    title: str
    description: str = ""
    kind: str = KIND_CHECK
    # Which section the user should open to do this step (display only).
    section_name: str = ""
    # Optional Logos action that helps with this step (deterministic or
    # generative — surfaced as a suggestion, never run automatically).
    action_id: str = ""
    # Optional completion-check key (see completion_checks.py). ``""`` means the
    # step has no deterministic check and is never auto-completed.
    completion_check: str = ""
    # Writing modes this step applies to. Empty = all modes.
    modes: tuple[str, ...] = ()

    def applies_to(self, mode: str) -> bool:
        return not self.modes or mode in self.modes

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "title": self.title, "description": self.description,
            "kind": self.kind, "section_name": self.section_name,
            "action_id": self.action_id, "completion_check": self.completion_check,
            "modes": list(self.modes),
        }


@dataclass
class WorkflowTemplate:
    """A named, ordered, mode-aware workflow (e.g. "Project Setup")."""

    id: str
    title: str
    description: str = ""
    category: str = "general"
    # Writing modes this template is offered for. Empty = all modes.
    modes: tuple[str, ...] = ()
    steps: list[WorkflowStep] = field(default_factory=list)

    def applies_to(self, mode: str) -> bool:
        return not self.modes or mode in self.modes

    def steps_for_mode(self, mode: str) -> list[WorkflowStep]:
        """Steps relevant to *mode* (mode-specific steps filtered out)."""
        return [s for s in self.steps if s.applies_to(mode)]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "title": self.title, "description": self.description,
            "category": self.category, "modes": list(self.modes),
            "steps": [s.to_dict() for s in self.steps],
        }
