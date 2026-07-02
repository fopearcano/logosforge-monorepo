"""Character Presence Analyzer Plugin — tracks character distribution patterns.

Analyzes how characters are distributed across scenes, identifies gaps,
clustering, and underrepresentation relative to story structure.
"""

from __future__ import annotations

from logosforge.plugin_base import (
    LogosforgePlugin,
    PluginContext,
    PluginResult,
    Suggestion,
)
from logosforge.plugin_registry import register_plugin


class CharacterPresencePlugin(LogosforgePlugin):

    @property
    def name(self) -> str:
        return "character_presence"

    @property
    def description(self) -> str:
        return "Analyzes character distribution and identifies presence gaps or clustering."

    @property
    def category(self) -> str:
        return "structure"

    @property
    def requires_scene(self) -> bool:
        return False

    def execute(self, context: PluginContext) -> PluginResult:
        if len(context.scenes) < 3:
            return PluginResult(
                plugin_name=self.name,
                summary="Need at least 3 scenes for presence analysis.",
            )

        if not context.characters:
            return PluginResult(
                plugin_name=self.name,
                summary="No characters in project.",
            )

        suggestions: list[Suggestion] = []
        total_scenes = len(context.scenes)

        # Build presence map: character -> list of scene indices where present
        presence_map: dict[str, list[int]] = {}
        for char in context.characters:
            presence_map[char.name] = []

        for i, scene in enumerate(context.scenes):
            for name in scene.character_names:
                if name in presence_map:
                    presence_map[name].append(i)

        # Analyze each character
        for char in context.characters:
            indices = presence_map.get(char.name, [])
            scene_count = len(indices)
            ratio = scene_count / total_scenes

            # Disappearance: character appears early then vanishes
            if scene_count >= 2:
                last_appearance = max(indices)
                gap_from_end = total_scenes - 1 - last_appearance
                if gap_from_end >= 3 and gap_from_end / total_scenes > 0.3:
                    suggestions.append(Suggestion(
                        text=f"{char.name} last appears in scene {last_appearance + 1} but {gap_from_end} scenes remain. Unresolved absence?",
                        category="continuity",
                        severity="warning",
                        target=char.name,
                    ))

            # Clustering: all appearances in a narrow band
            if scene_count >= 3:
                span = max(indices) - min(indices) + 1
                if span <= total_scenes * 0.3 and total_scenes >= 6:
                    suggestions.append(Suggestion(
                        text=f"{char.name} appears in {scene_count} scenes but all within a {span}-scene span. Consider spreading presence.",
                        category="distribution",
                        severity="info",
                        target=char.name,
                    ))

            # Underrepresentation
            if char.flag == "underused":
                suggestions.append(Suggestion(
                    text=f"{char.name} is underused ({scene_count}/{total_scenes} scenes, {ratio:.0%}). Either develop or justify their minor role.",
                    category="balance",
                    severity="warning",
                    target=char.name,
                ))

            # Dominance
            if char.flag == "dominant" and total_scenes >= 5:
                suggestions.append(Suggestion(
                    text=f"{char.name} dominates ({scene_count}/{total_scenes} scenes, {ratio:.0%}). Other characters may lack space to develop.",
                    category="balance",
                    severity="info",
                    target=char.name,
                ))

        # Scene with no characters
        empty_scenes = [s for s in context.scenes if not s.character_names]
        if empty_scenes and len(empty_scenes) <= 3:
            titles = [s.title for s in empty_scenes[:3]]
            suggestions.append(Suggestion(
                text=f"Scenes without characters: {', '.join(titles)}. Assign characters for continuity tracking.",
                category="completeness",
                severity="info",
            ))

        # Active scene: who's missing that was recently present?
        if context.active_scene is not None:
            active_idx = next(
                (i for i, s in enumerate(context.scenes) if s.id == context.active_scene.id),
                None,
            )
            if active_idx is not None and active_idx >= 2:
                recent_chars: set[str] = set()
                for s in context.scenes[max(0, active_idx - 3):active_idx]:
                    recent_chars.update(s.character_names)
                current_chars = set(context.active_scene.character_names)
                dropped = recent_chars - current_chars
                if dropped and len(dropped) <= 3:
                    suggestions.append(Suggestion(
                        text=f"Recently present but absent now: {', '.join(sorted(dropped))}. Intentional departure or oversight?",
                        category="continuity",
                        severity="info",
                    ))

        summary = (
            f"Analyzed {len(context.characters)} characters across "
            f"{total_scenes} scenes. {len(suggestions)} observations."
        )

        return PluginResult(
            plugin_name=self.name,
            suggestions=suggestions,
            summary=summary,
            metadata={
                "total_characters": len(context.characters),
                "total_scenes": total_scenes,
                "presence_ratios": {
                    name: len(indices) / total_scenes
                    for name, indices in presence_map.items()
                },
            },
        )


register_plugin(CharacterPresencePlugin())
