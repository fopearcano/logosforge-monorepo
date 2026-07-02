"""Dialogue Tension Plugin — analyzes dialogue density and tension signals.

Examines the active scene content for dialogue patterns and checks whether
dialogue carries tension given the scene's conflict and character states.
"""

from __future__ import annotations

import re

from logosforge.plugin_base import (
    LogosforgePlugin,
    PluginContext,
    PluginResult,
    Suggestion,
)
from logosforge.plugin_registry import register_plugin


_SPEECH_VERBS = (
    "said|asked|replied|whispered|shouted|muttered|snapped|"
    "snarled|growled|called|screamed|yelled|cried|exclaimed|"
    "demanded|pleaded|groaned|sighed|murmured|hissed|barked|"
    "stammered|declared|announced|added|continued|insisted|"
    "answered|responded|warned|promised|threatened|mocked|"
    "suggested|agreed|protested|urged|scoffed|laughed"
)


class DialogueTensionPlugin(LogosforgePlugin):

    @property
    def name(self) -> str:
        return "dialogue_tension"

    @property
    def description(self) -> str:
        return "Analyzes dialogue density and tension signals in the active scene."

    @property
    def category(self) -> str:
        return "analysis"

    def execute(self, context: PluginContext) -> PluginResult:
        scene = context.active_scene
        if scene is None:
            return PluginResult(
                plugin_name=self.name,
                summary="No active scene.",
            )

        content = scene.content
        if not content or len(content.strip()) < 20:
            return PluginResult(
                plugin_name=self.name,
                summary="Scene has insufficient content for analysis.",
            )

        lines = content.split("\n")
        total_lines = len([l for l in lines if l.strip()])
        dialogue_lines = self._count_dialogue_lines(lines)
        dialogue_ratio = dialogue_lines / max(total_lines, 1)

        suggestions: list[Suggestion] = []

        # Dialogue density check
        if dialogue_ratio > 0.7:
            suggestions.append(Suggestion(
                text="Scene is heavily dialogue-driven (>{:.0%}). Consider adding beats, action, or interiority between exchanges.".format(dialogue_ratio),
                category="pacing",
                severity="info",
            ))
        elif dialogue_ratio < 0.1 and total_lines > 5:
            suggestions.append(Suggestion(
                text="Very little dialogue detected. If characters are present, silence may need justification.",
                category="pacing",
                severity="info",
            ))

        # Tension indicators in dialogue
        tension_signals = self._detect_tension_signals(content)
        if scene.conflict and not tension_signals:
            suggestions.append(Suggestion(
                text=f"Scene has conflict (\"{scene.conflict[:50]}...\") but dialogue lacks tension markers (interruptions, short replies, questions).",
                category="tension",
                severity="warning",
            ))

        # Flat dialogue check: all lines similar length
        if dialogue_lines >= 4:
            lengths = self._dialogue_lengths(lines)
            if lengths:
                avg = sum(lengths) / len(lengths)
                variance = sum((l - avg) ** 2 for l in lengths) / len(lengths)
                if avg > 0 and variance / (avg ** 2) < 0.1:
                    suggestions.append(Suggestion(
                        text="Dialogue lines are very uniform in length. Varied rhythm (short bursts + longer replies) creates more tension.",
                        category="rhythm",
                        severity="info",
                    ))

        # Characters without dialogue
        if scene.character_names and dialogue_lines > 0:
            speaking = self._detect_speakers(content, scene.character_names)
            silent = [n for n in scene.character_names if n not in speaking]
            if silent:
                suggestions.append(Suggestion(
                    text=f"Characters present but silent: {', '.join(silent)}. Silent presence can be powerful — or an oversight.",
                    category="character",
                    severity="info",
                    target=", ".join(silent),
                ))

        summary = (
            f"Dialogue: {dialogue_lines}/{total_lines} lines ({dialogue_ratio:.0%}). "
            f"Tension signals: {'present' if tension_signals else 'absent'}."
        )

        return PluginResult(
            plugin_name=self.name,
            suggestions=suggestions,
            summary=summary,
            metadata={
                "dialogue_lines": dialogue_lines,
                "total_lines": total_lines,
                "dialogue_ratio": round(dialogue_ratio, 2),
                "tension_signals": tension_signals,
            },
        )

    def _count_dialogue_lines(self, lines: list[str]) -> int:
        count = 0
        for line in lines:
            stripped = line.strip()
            if self._is_dialogue(stripped):
                count += 1
        return count

    def _is_dialogue(self, line: str) -> bool:
        if not line:
            return False
        if line.startswith('"') or line.startswith('“'):
            return True
        if line.startswith('—') or line.startswith('--'):
            return True
        if re.match(rf'^[A-Z][a-z]+\s+({_SPEECH_VERBS})', line):
            return True
        if '"' in line or '“' in line:
            quote_chars = line.count('"') + line.count('“') + line.count('”')
            if quote_chars >= 2:
                return True
        return False

    def _detect_tension_signals(self, content: str) -> bool:
        patterns = [
            r'\.\.\.',
            r'—$',
            r'--$',
            r'\?\s*"',
            r'!\s*"',
            r'"[^"\n]{1,15}"',  # Short, clipped replies (single line)
        ]
        for pattern in patterns:
            if re.search(pattern, content, re.MULTILINE):
                return True
        return False

    def _dialogue_lengths(self, lines: list[str]) -> list[int]:
        lengths = []
        for line in lines:
            if self._is_dialogue(line.strip()):
                lengths.append(len(line.strip()))
        return lengths

    def _detect_speakers(self, content: str, names: list[str]) -> set[str]:
        speakers: set[str] = set()
        lines = content.split("\n")
        for name in names:
            pattern = rf'{re.escape(name)}\s+({_SPEECH_VERBS})'
            if re.search(pattern, content):
                speakers.add(name)
                continue
            for line in lines:
                if name in line and ('”' in line or '“' in line or '”' in line):
                    speakers.add(name)
                    break
        return speakers


register_plugin(DialogueTensionPlugin())
