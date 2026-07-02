"""Proactive Context-Aware Assistant — lightweight heuristic suggestion engine.

Detects what the user is writing and surfaces non-intrusive hints based on
writing mode, structural signals, and PSYKE temporal state.  Never writes
to the database — produces ContextHint objects for the UI to present.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ContextHint:
    """One non-intrusive context hint offered to the user."""

    hint_type: str
    message: str
    priority: int  # 1=high, 3=low
    action: str | None = None  # "open_progression" | "focus_conflict" | None
    data: dict = field(default_factory=dict)
    scene_id: int = 0

    @property
    def dedup_key(self) -> str:
        core = self.data.get("_dedup", "")
        return f"{self.hint_type}:{self.scene_id}:{core}"


# -- Writing mode detection regexes ------------------------------------------

_DIALOGUE_RE = re.compile(
    r'^[A-Z][A-Z\s]{1,30}$'
    r'|^"[^"]{4,}'
    r"|^'[^']{4,}"
    r'|^“',  # opening smart quote
    re.MULTILINE,
)

_ADJECTIVE_SUFFIXES = ("ous", "ful", "ive", "ing", "ent", "ant", "ble", "tic")

_SHORT_THRESHOLD = 40
_LONG_THRESHOLD = 360
_STALE_PROGRESSION_GAP = 5
_COOCCURRENCE_GAP = 6
_MONOTONE_THRESHOLD = 0.15


class ContextAssistant:
    """Heuristic engine that produces context hints for a single scene."""

    def __init__(self, db: Any, project_id: int) -> None:
        self._db = db
        self._project_id = project_id

    def analyze_scene(
        self,
        scene_id: int,
        temporal_graph: Any | None = None,
    ) -> list[ContextHint]:
        scene = self._db.get_scene_by_id(scene_id)
        if scene is None:
            return []

        hints: list[ContextHint] = []
        content = scene.content or ""
        words = content.split()
        word_count = len(words)

        hints.extend(self._detect_writing_mode(scene, content, word_count))
        hints.extend(self._detect_structural(scene, content, word_count))
        if temporal_graph is not None:
            hints.extend(
                self._detect_psyke_temporal(scene, content, temporal_graph)
            )

        hints.sort(key=lambda h: h.priority)
        return hints

    # -- Layer 1: Writing mode detection --------------------------------------

    def _detect_writing_mode(
        self, scene: Any, content: str, word_count: int,
    ) -> list[ContextHint]:
        hints: list[ContextHint] = []

        if word_count < 20:
            return hints

        paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
        if not paragraphs:
            return hints

        last_para = paragraphs[-1]

        if self._is_dialogue_block(last_para) and word_count > _SHORT_THRESHOLD:
            if not scene.conflict and not scene.goal:
                text_lower = content.lower()
                tension_words = {
                    "but", "however", "refused", "argued", "demanded",
                    "lied", "betrayed", "confronted", "denied",
                }
                if not any(w in text_lower for w in tension_words):
                    hints.append(ContextHint(
                        hint_type="dialogue_no_tension",
                        message=(
                            "This dialogue has no tension yet "
                            "— what does each character want?"
                        ),
                        priority=3,
                        scene_id=scene.id,
                        data={"_dedup": "dialogue_tension"},
                    ))

        if len(paragraphs) >= 3:
            lengths = [len(p.split()) for p in paragraphs]
            mean = sum(lengths) / len(lengths)
            if mean > 0:
                variance = sum((l - mean) ** 2 for l in lengths) / len(lengths)
                cv = (variance ** 0.5) / mean
                if cv < _MONOTONE_THRESHOLD:
                    hints.append(ContextHint(
                        hint_type="rhythm_monotone",
                        message="Paragraph lengths are very uniform — vary the pacing?",
                        priority=3,
                        scene_id=scene.id,
                        data={"_dedup": "rhythm"},
                    ))

        return hints

    @staticmethod
    def _is_dialogue_block(text: str) -> bool:
        lines = text.strip().split("\n")
        dialogue_lines = sum(
            1 for line in lines if _DIALOGUE_RE.match(line.strip())
        )
        return dialogue_lines >= 2 or (
            len(lines) <= 3 and dialogue_lines >= 1
        )

    # -- Layer 2: Structural signals ------------------------------------------

    def _detect_structural(
        self, scene: Any, content: str, word_count: int,
    ) -> list[ContextHint]:
        hints: list[ContextHint] = []

        has_metadata = any([scene.goal, scene.conflict, scene.outcome, scene.synopsis])
        if has_metadata and word_count == 0:
            hints.append(ContextHint(
                hint_type="empty_scene_body",
                message="Scene has metadata but no content yet.",
                priority=2,
                scene_id=scene.id,
                data={"_dedup": "empty_body"},
            ))

        if word_count > _SHORT_THRESHOLD and not scene.conflict and not scene.goal:
            text_lower = content.lower()
            conflict_words = {
                "but", "however", "against", "refused", "fought",
                "argued", "clash",
            }
            if not any(w in text_lower for w in conflict_words):
                hints.append(ContextHint(
                    hint_type="missing_conflict",
                    message="No conflict or goal defined — add one in the sidebar?",
                    priority=2,
                    action="focus_conflict",
                    scene_id=scene.id,
                    data={"_dedup": "conflict"},
                ))

        if word_count > _LONG_THRESHOLD:
            hints.append(ContextHint(
                hint_type="long_scene",
                message=f"Long scene ({word_count} words) — consider splitting.",
                priority=3,
                scene_id=scene.id,
                data={"_dedup": f"long_{word_count // 100}"},
            ))

        if 0 < word_count < _SHORT_THRESHOLD:
            hints.append(ContextHint(
                hint_type="short_scene",
                message="Very short scene — placeholder?",
                priority=3,
                scene_id=scene.id,
                data={"_dedup": "short"},
            ))

        return hints

    # -- Layer 3: PSYKE temporal signals --------------------------------------

    def _detect_psyke_temporal(
        self, scene: Any, content: str, tg: Any,
    ) -> list[ContextHint]:
        hints: list[ContextHint] = []
        if not content.strip():
            return hints

        text_lower = content.lower()
        scene_order = getattr(scene, "sort_order", 0)

        entries = self._db.get_all_psyke_entries(self._project_id)
        char_entries = [
            e for e in entries
            if e.entry_type == "character" and not e.is_global
        ]

        mentioned_ids: list[int] = []
        for entry in char_entries:
            name_lower = entry.name.lower()
            if name_lower in text_lower:
                mentioned_ids.append(entry.id)
                continue
            if entry.aliases:
                for alias in entry.aliases.split(","):
                    alias = alias.strip().lower()
                    if alias and alias in text_lower:
                        mentioned_ids.append(entry.id)
                        break

        for eid in mentioned_ids:
            state = tg.get_entry_state_at(eid, scene_order)
            if state is None:
                continue
            if not state.has_progression:
                continue
            prog_order = state.progression_scene_order
            if prog_order is not None:
                gap = scene_order - prog_order
                if gap >= _STALE_PROGRESSION_GAP:
                    hints.append(ContextHint(
                        hint_type="character_state_stale",
                        message=(
                            f"{state.name}’s last progression was "
                            f"{gap} scenes ago — update their arc?"
                        ),
                        priority=1,
                        action="open_progression",
                        scene_id=scene.id,
                        data={
                            "entry_id": eid,
                            "entry_name": state.name,
                            "_dedup": f"stale_{eid}",
                        },
                    ))

        if len(mentioned_ids) >= 2:
            all_scenes = self._db.get_all_scenes(self._project_id)
            scene_texts: dict[int, str] = {}
            for s in all_scenes:
                scene_texts[s.id] = (s.content or "").lower()

            for entry in entries:
                if entry.id not in mentioned_ids:
                    continue
                related = tg._relations.get(entry.id, [])
                for rid in related:
                    if rid not in mentioned_ids:
                        continue
                    if rid <= entry.id:
                        continue

                    related_entry = tg._entries.get(rid)
                    if related_entry is None:
                        continue

                    last_together = None
                    for s in all_scenes:
                        if s.sort_order >= scene_order:
                            break
                        st = scene_texts.get(s.id, "")
                        e_name = entry.name.lower()
                        r_name = related_entry.name.lower()
                        if e_name in st and r_name in st:
                            last_together = s.sort_order

                    if last_together is not None:
                        gap = scene_order - last_together
                        if gap >= _COOCCURRENCE_GAP:
                            hints.append(ContextHint(
                                hint_type="related_entries_absent",
                                message=(
                                    f"{entry.name} and {related_entry.name} are "
                                    f"linked but haven’t co-occurred in {gap} scenes."
                                ),
                                priority=2,
                                scene_id=scene.id,
                                data={
                                    "entry_a": entry.id,
                                    "entry_b": rid,
                                    "_dedup": f"cooccur_{min(entry.id, rid)}_{max(entry.id, rid)}",
                                },
                            ))

        return hints


# -- Rate limiter -------------------------------------------------------------

_TYPE_COOLDOWN = 60.0
_GLOBAL_COOLDOWN = 15.0


class HintRateLimiter:
    """Controls hint display frequency to avoid nagging the writer."""

    def __init__(self) -> None:
        self._type_shown: dict[tuple[int, str], float] = {}
        self._last_shown: float = 0.0
        self._seen_keys: dict[int, set[str]] = {}

    def filter(self, hints: list[ContextHint]) -> ContextHint | None:
        now = time.monotonic()

        if now - self._last_shown < _GLOBAL_COOLDOWN:
            return None

        for hint in hints:
            type_key = (hint.scene_id, hint.hint_type)
            last_type = self._type_shown.get(type_key, 0.0)
            if now - last_type < _TYPE_COOLDOWN:
                continue

            scene_seen = self._seen_keys.get(hint.scene_id, set())
            if hint.dedup_key in scene_seen:
                continue

            return hint

        return None

    def mark_shown(self, hint: ContextHint) -> None:
        now = time.monotonic()
        self._type_shown[(hint.scene_id, hint.hint_type)] = now
        self._last_shown = now
        self._seen_keys.setdefault(hint.scene_id, set()).add(hint.dedup_key)

    def on_scene_changed(self, scene_id: int) -> None:
        self._last_shown = 0.0
        self._seen_keys.pop(scene_id, None)
        to_remove = [k for k in self._type_shown if k[0] == scene_id]
        for k in to_remove:
            del self._type_shown[k]

    def reset(self) -> None:
        self._type_shown.clear()
        self._last_shown = 0.0
        self._seen_keys.clear()
