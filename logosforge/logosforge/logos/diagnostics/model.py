"""ProjectFacts — a cheap, read-only snapshot the diagnostics share.

Built once per scan from the authoritative Database (never UI caches). It pulls
scenes, PSYKE entries/relations/progressions, notes, the link graph, the
controlling idea, and a PSYKE-entry → ordered-scene-appearance map (reusing the
narrative-dashboard term/alias mention scan). Detectors read this snapshot so a
project scan touches the DB a bounded number of times.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class ProjectFacts:
    db: object
    project_id: int
    scenes: list = field(default_factory=list)              # ordered by sort_order
    entries: list = field(default_factory=list)             # all PsykeEntry
    details: dict = field(default_factory=dict)             # entry_id -> details dict
    relations: dict = field(default_factory=dict)           # entry_id -> [(entry, rtype)]
    progressions: dict = field(default_factory=dict)        # entry_id -> [PsykeProgression]
    appearances: dict = field(default_factory=dict)         # entry_id -> [scene sort_order]
    notes: list = field(default_factory=list)
    adjacency: dict = field(default_factory=dict)           # lower(name) -> set(lower names)
    controlling_idea: object = None

    # -- convenience views ---------------------------------------------------

    @property
    def total_scenes(self) -> int:
        return len(self.scenes)

    def entries_of_type(self, *types: str) -> list:
        return [e for e in self.entries if e.entry_type in types]

    def scene_sort_orders(self) -> list[int]:
        return [s.sort_order for s in self.scenes]


def _build_terms_pattern(terms: list[str]):
    terms = [re.escape(t) for t in terms if t]
    if not terms:
        return None
    terms.sort(key=len, reverse=True)
    return re.compile(r"\b(" + "|".join(terms) + r")\b", re.IGNORECASE)


def build_facts(db, project_id: int) -> ProjectFacts:
    facts = ProjectFacts(db=db, project_id=project_id)
    facts.scenes = db.get_all_scenes(project_id)
    facts.entries = db.get_all_psyke_entries(project_id)
    facts.notes = db.get_all_notes(project_id)

    for e in facts.entries:
        facts.details[e.id] = db.get_psyke_entry_details(e.id)
        facts.relations[e.id] = db.get_typed_related_psyke_entries(e.id)
        facts.progressions[e.id] = db.get_psyke_progressions(e.id)

    facts.appearances = _compute_appearances(facts)
    facts.adjacency = _build_adjacency(db, project_id)
    facts.controlling_idea = _load_controlling_idea(db, project_id)
    return facts


def _compute_appearances(facts: ProjectFacts) -> dict[int, list[int]]:
    """entry_id -> ordered list of scene sort_orders the entry is mentioned in.

    Mirrors the narrative-dashboard mention scan (name + aliases in scene text),
    which is the reliable way to map PSYKE entries — whose names need not match
    Character rows — onto scenes.
    """
    term_map: dict[str, int] = {}
    for e in facts.entries:
        if (e.name or "").strip():
            term_map[e.name.lower()] = e.id
        for alias in (e.aliases or "").split(","):
            a = alias.strip().lower()
            if a:
                term_map[a] = e.id
    pattern = _build_terms_pattern(list(term_map.keys()))

    out: dict[int, list[int]] = {e.id: [] for e in facts.entries}
    if pattern is None:
        return out
    for scene in facts.scenes:
        text = " ".join(filter(None, [
            scene.title, scene.summary, scene.synopsis, scene.goal,
            scene.conflict, scene.outcome, scene.content,
        ])).lower()
        if not text:
            continue
        seen: set[int] = set()
        for m in pattern.finditer(text):
            eid = term_map.get(m.group().lower())
            if eid is not None and eid not in seen:
                seen.add(eid)
                out[eid].append(scene.sort_order)
    return out


def _build_adjacency(db, project_id: int) -> dict[str, set[str]]:
    try:
        _nodes, edges = db.build_link_graph(project_id)
    except Exception:
        return {}
    adj: dict[str, set[str]] = {}
    for src, tgt in edges:
        adj.setdefault(src.lower(), set()).add(tgt.lower())
        adj.setdefault(tgt.lower(), set()).add(src.lower())
    return adj


def _load_controlling_idea(db, project_id: int):
    try:
        from logosforge.controlling_idea import load as load_ci
        return load_ci(db, project_id)
    except Exception:
        return None


# -- shared helpers used by detectors ----------------------------------------

def max_consecutive_absent(present_orders: list[int], total: int) -> int:
    """Largest run of scene indices in which an entity is absent."""
    if not present_orders or total <= 0:
        return 0
    present = set(present_orders)
    longest = run = 0
    lo, hi = min(present_orders), max(present_orders)
    for i in range(lo, hi + 1):
        if i in present:
            run = 0
        else:
            run += 1
            longest = max(longest, run)
    return longest


def scene_act_for_order(facts: ProjectFacts, order: int) -> str:
    for s in facts.scenes:
        if s.sort_order == order:
            return (s.act or "").strip()
    return ""
