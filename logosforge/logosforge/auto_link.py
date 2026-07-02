"""Auto-link suggestion engine between manuscript text and PSYKE entries.

Detects potential new entities, alias variants, relations, and memory/state
changes from scene text and produces a list of non-blocking Suggestion objects.
The caller is responsible for presenting suggestions and for committing any
chosen action: the engine NEVER writes to the database.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Iterable

STOP_WORDS: frozenset[str] = frozenset({
    "The", "A", "An",
    "He", "She", "It", "They", "We", "I", "You",
    "His", "Her", "Their", "My", "Your", "Its", "Our",
    "Him", "Them", "Us", "Me",
    "But", "And", "Or", "Nor", "So", "Yet",
    "Not", "No", "Yes",
    "If", "When", "Then", "While", "Before", "After", "Until",
    "As", "At", "By", "For", "From", "In", "Of", "On", "To", "With",
    "Into", "Onto", "Upon", "Over", "Under",
    "This", "That", "These", "Those",
    "What", "Which", "Who", "Whom", "Whose", "Why", "Where", "How",
    "There", "Here",
    "Mr", "Mrs", "Ms", "Dr", "Sir", "Lady", "Lord",
    "Chapter", "Scene", "Act", "Part",
    "Monday", "Tuesday", "Wednesday", "Thursday", "Friday",
    "Saturday", "Sunday",
    "January", "February", "March", "April", "May", "June", "July",
    "August", "September", "October", "November", "December",
})

_MIN_OCCURRENCES = 2
_MIN_ALIAS_PREFIX = 3

_TOKEN_RE = re.compile(
    r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})\b",
)

_STATE_VERBS: tuple[str, ...] = (
    "became", "felt", "realized", "discovered", "learned",
    "decided", "swore", "vowed", "remembered", "forgot",
    "fell in love", "lost", "gained", "accepted", "rejected",
    "died", "survived", "escaped", "returned", "arrived",
)

_STATE_PATTERN = re.compile(
    r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s+("
    + "|".join(re.escape(v) for v in _STATE_VERBS)
    + r")\b([^.!?]*)",
)


@dataclass(frozen=True)
class Suggestion:
    """One non-blocking suggestion offered to the user."""

    kind: str  # "create" | "alias" | "relation" | "memory"
    label: str
    data: dict = field(default_factory=dict)

    @property
    def entity_key(self) -> str:
        """Stable identifier used for the ignore-list."""
        if self.kind == "create":
            return f"create:{self.data.get('name', '').lower()}"
        if self.kind == "alias":
            return (
                f"alias:{self.data.get('entry_id')}:"
                f"{self.data.get('alias', '').lower()}"
            )
        if self.kind == "relation":
            a = self.data.get("entry_id")
            b = self.data.get("related_entry_id")
            lo, hi = sorted([a or 0, b or 0])
            return f"relation:{lo}:{hi}"
        if self.kind == "memory":
            return (
                f"memory:{self.data.get('entry_id')}:"
                f"{self.data.get('scene_id')}:"
                f"{self.data.get('text', '')[:40].lower()}"
            )
        return f"{self.kind}:unknown"


def extract_capitalized_tokens(text: str) -> list[tuple[str, int]]:
    """Return (token, char_offset) for every capitalized token in text.

    Filters out stop words.  Sentence-start false positives ("Running felt...")
    are handled downstream by the ≥2-occurrence threshold rather than a
    position filter, so real proper nouns at the start of a sentence survive.
    """
    if not text:
        return []

    results: list[tuple[str, int]] = []
    for m in _TOKEN_RE.finditer(text):
        token = m.group(1)
        if token in STOP_WORDS:
            continue
        head = token.split()[0]
        if head in STOP_WORDS:
            continue
        results.append((token, m.start()))
    return results


class AutoLinkSuggester:
    """Builds non-blocking suggestions from project scenes + PSYKE entries."""

    def __init__(self, db, project_id: int) -> None:
        self._db = db
        self._project_id = project_id

    # -- Public API -----------------------------------------------------------

    def suggest_for_project(
        self,
        ignored_keys: Iterable[str] = (),
        per_scene_limit: int = 1,
    ) -> dict[int, list[Suggestion]]:
        """Return suggestions keyed by scene_id, capped per scene."""
        ignored = set(ignored_keys)
        scenes = self._db.get_all_scenes(self._project_id)
        entries = self._db.get_all_psyke_entries(self._project_id)

        known_terms: dict[str, int] = {}
        entry_names: dict[int, str] = {}
        for e in entries:
            entry_names[e.id] = e.name
            if e.name.strip():
                known_terms[e.name.lower()] = e.id
            if e.aliases:
                for alias in e.aliases.split(","):
                    alias = alias.strip().lower()
                    if alias:
                        known_terms[alias] = e.id

        tokens_per_scene: dict[int, list[tuple[str, int]]] = {}
        occurrences: Counter[str] = Counter()
        for scene in scenes:
            toks = extract_capitalized_tokens(scene.content or "")
            tokens_per_scene[scene.id] = toks
            for t, _ in toks:
                occurrences[t.lower()] += 1

        existing_relations = self._load_existing_relations(entries)

        grouped: dict[int, list[Suggestion]] = defaultdict(list)

        for scene in scenes:
            tokens = tokens_per_scene.get(scene.id, [])
            if not tokens:
                continue

            suggestions: list[Suggestion] = []

            suggestions.extend(
                self._suggest_creates(tokens, known_terms, occurrences)
            )
            suggestions.extend(
                self._suggest_aliases(tokens, known_terms, entry_names)
            )
            suggestions.extend(
                self._suggest_relations(
                    scene.id, tokens, known_terms, existing_relations,
                )
            )
            suggestions.extend(
                self._suggest_memory(scene, known_terms)
            )

            seen: set[str] = set()
            unique: list[Suggestion] = []
            for s in suggestions:
                if s.entity_key in ignored or s.entity_key in seen:
                    continue
                seen.add(s.entity_key)
                unique.append(s)

            if unique:
                grouped[scene.id] = unique[:per_scene_limit]

        return dict(grouped)

    # -- Detectors ------------------------------------------------------------

    @staticmethod
    def _suggest_creates(
        tokens: list[tuple[str, int]],
        known_terms: dict[str, int],
        occurrences: Counter,
    ) -> list[Suggestion]:
        seen: set[str] = set()
        out: list[Suggestion] = []
        for token, _ in tokens:
            key = token.lower()
            if key in known_terms or key in seen:
                continue
            if occurrences[key] < _MIN_OCCURRENCES:
                continue
            seen.add(key)
            out.append(Suggestion(
                kind="create",
                label=f"Create PSYKE entry for “{token}”?",
                data={"name": token, "occurrences": occurrences[key]},
            ))
        return out

    @staticmethod
    def _suggest_aliases(
        tokens: list[tuple[str, int]],
        known_terms: dict[str, int],
        entry_names: dict[int, str],
    ) -> list[Suggestion]:
        out: list[Suggestion] = []
        seen: set[str] = set()
        for token, _ in tokens:
            key = token.lower()
            if key in known_terms or key in seen:
                continue

            for entry_id, name in entry_names.items():
                name_lower = name.lower()
                if key == name_lower:
                    continue

                is_alias = False
                if len(token) == 1 and name:
                    initials = "".join(
                        p[0] for p in name.split() if p
                    )
                    if token.upper() == initials.upper():
                        is_alias = True
                elif (
                    len(key) >= _MIN_ALIAS_PREFIX
                    and len(name_lower) >= _MIN_ALIAS_PREFIX
                    and (
                        key.startswith(name_lower[:_MIN_ALIAS_PREFIX])
                        or name_lower.startswith(key[:_MIN_ALIAS_PREFIX])
                    )
                    and key != name_lower
                ):
                    is_alias = True

                if is_alias:
                    seen.add(key)
                    out.append(Suggestion(
                        kind="alias",
                        label=(
                            f"Link “{token}” as alias of {name}?"
                        ),
                        data={
                            "entry_id": entry_id,
                            "entry_name": name,
                            "alias": token,
                        },
                    ))
                    break
        return out

    @staticmethod
    def _suggest_relations(
        scene_id: int,
        tokens: list[tuple[str, int]],
        known_terms: dict[str, int],
        existing_relations: set[tuple[int, int]],
    ) -> list[Suggestion]:
        present_ids: list[int] = []
        present_names: dict[int, str] = {}
        for token, _ in tokens:
            eid = known_terms.get(token.lower())
            if eid is not None and eid not in present_names:
                present_ids.append(eid)
                present_names[eid] = token

        out: list[Suggestion] = []
        for i, a in enumerate(present_ids):
            for b in present_ids[i + 1:]:
                pair = tuple(sorted([a, b]))
                if pair in existing_relations:
                    continue
                out.append(Suggestion(
                    kind="relation",
                    label=(
                        f"Link {present_names[a]} ↔ "
                        f"{present_names[b]}?"
                    ),
                    data={
                        "entry_id": a,
                        "related_entry_id": b,
                        "entry_name": present_names[a],
                        "related_name": present_names[b],
                        "scene_id": scene_id,
                    },
                ))
        return out

    @staticmethod
    def _suggest_memory(
        scene,
        known_terms: dict[str, int],
    ) -> list[Suggestion]:
        text = scene.content or ""
        if not text:
            return []

        out: list[Suggestion] = []
        seen: set[tuple[int, str]] = set()
        for m in _STATE_PATTERN.finditer(text):
            name = m.group(1)
            verb = m.group(2)
            rest = m.group(3).strip(" ,;:")
            eid = known_terms.get(name.lower())
            if eid is None:
                continue
            snippet = f"{verb} {rest}".strip()
            if not snippet or len(snippet) > 120:
                snippet = snippet[:120]
            key = (eid, snippet.lower())
            if key in seen:
                continue
            seen.add(key)
            out.append(Suggestion(
                kind="memory",
                label=(
                    f"Record for {name}: “{snippet}”?"
                ),
                data={
                    "entry_id": eid,
                    "entry_name": name,
                    "scene_id": scene.id,
                    "text": snippet,
                },
            ))
        return out

    # -- Helpers --------------------------------------------------------------

    def _load_existing_relations(
        self, entries: list
    ) -> set[tuple[int, int]]:
        pairs: set[tuple[int, int]] = set()
        for e in entries:
            for related in self._db.get_related_psyke_entries(e.id):
                pair = tuple(sorted([e.id, related.id]))
                pairs.add(pair)
        return pairs
