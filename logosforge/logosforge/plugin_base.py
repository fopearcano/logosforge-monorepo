"""Logosforge Plugin System — PSYKE-aware plugin interfaces.

Defines the core plugin interfaces: base class, context model, result model.
Plugins receive structured narrative context and return suggestions/annotations.
They never access the database or mutate state directly.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class SceneSnapshot:
    id: int
    title: str
    chapter: str
    plotline: str
    act: str
    goal: str
    conflict: str
    outcome: str
    content: str
    character_names: list[str]
    sort_order: int


@dataclass
class CharacterSnapshot:
    id: int
    name: str
    description: str
    scene_count: int
    flag: str


@dataclass
class PsykeSnapshot:
    id: int
    name: str
    entry_type: str
    notes: str
    is_global: bool
    progression_text: str


@dataclass
class MemorySnapshot:
    memory_type: str
    target: str
    value: str
    scene_label: str
    relevance: float
    superseded: bool


@dataclass
class PluginContext:
    """Immutable narrative context provided to plugins.

    Contains structured data from all context systems.
    Plugins cannot modify this or access the database.
    """

    project_id: int
    project_title: str

    # Active scene
    active_scene: SceneSnapshot | None = None

    # Nearby scenes (for structural analysis)
    scenes: list[SceneSnapshot] = field(default_factory=list)

    # Characters with presence data
    characters: list[CharacterSnapshot] = field(default_factory=list)

    # PSYKE entries (resolved at current temporal position)
    psyke_entries: list[PsykeSnapshot] = field(default_factory=list)

    # Story memory (scored and filtered)
    memories: list[MemorySnapshot] = field(default_factory=list)

    # Pre-formatted context strings (for plugins that want raw text)
    scene_context_text: str = ""
    psyke_context_text: str = ""
    memory_context_text: str = ""
    graph_context_text: str = ""
    outline_context_text: str = ""


@dataclass
class Suggestion:
    """A single plugin suggestion or annotation."""

    text: str
    category: str = "general"
    severity: str = "info"  # "info", "warning", "critical"
    target: str = ""  # What this suggestion applies to (character name, scene title, etc.)
    detail: str = ""


@dataclass
class PluginResult:
    """Structured output from a plugin execution."""

    plugin_name: str
    suggestions: list[Suggestion] = field(default_factory=list)
    summary: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class LogosforgePlugin(ABC):
    """Base class for all Logosforge plugins.

    Plugins analyze narrative context and produce suggestions.
    They NEVER access the database or mutate project state.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique plugin identifier."""

    @property
    @abstractmethod
    def description(self) -> str:
        """Short description of what this plugin does."""

    @property
    def category(self) -> str:
        """Plugin category for UI grouping."""
        return "analysis"

    @property
    def requires_scene(self) -> bool:
        """Whether this plugin requires an active scene."""
        return True

    @abstractmethod
    def execute(self, context: PluginContext) -> PluginResult:
        """Execute the plugin on the given context.

        Args:
            context: Immutable narrative snapshot

        Returns:
            Structured result with suggestions
        """
