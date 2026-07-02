"""PSYKE adapter — bridge between Quantum Outliner and the story bible.

Reads characters/relations for prompt context, applies state deltas
to PSYKE entries when a wavefunction collapses.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from logosforge.quantum_outliner.state import Branch, StateDelta

if TYPE_CHECKING:
    from logosforge.db import Database


@dataclass(frozen=True)
class PsykeSignals:
    """Structured PSYKE state for collapse recommendation scoring."""

    characters: list[dict] = field(default_factory=list)
    relations: list[dict] = field(default_factory=list)
    unresolved_arcs: list[dict] = field(default_factory=list)
    keywords: frozenset[str] = field(default_factory=frozenset)
    progressions: list[dict] = field(default_factory=list)


def gather_psyke_signals(db: "Database", project_id: int) -> PsykeSignals:
    """Extract structured PSYKE state for recommendation scoring."""
    entries = db.get_all_psyke_entries(project_id)
    if not entries:
        return PsykeSignals()

    characters: list[dict] = []
    all_keywords: set[str] = set()
    unresolved_arcs: list[dict] = []

    for e in entries:
        if e.entry_type != "character":
            continue
        notes = (e.notes or "").strip()
        char_info: dict = {"name": e.name, "notes": notes}

        words = set(notes.lower().split())
        all_keywords.update(w for w in words if len(w) > 3)
        all_keywords.add(e.name.lower())

        for line in notes.split("\n"):
            if line.strip().startswith("[arc]"):
                arc_text = line.strip().removeprefix("[arc]").strip()
                unresolved_arcs.append({"name": e.name, "arc": arc_text})

        characters.append(char_info)

    relations: list[dict] = []
    seen_pairs: set[tuple[int, int]] = set()
    for e in entries:
        if e.entry_type != "character":
            continue
        related = db.get_related_psyke_entries(e.id)
        for r in related:
            pair = (min(e.id, r.id), max(e.id, r.id))
            if pair not in seen_pairs:
                seen_pairs.add(pair)
                relations.append({"from": e.name, "to": r.name})
                all_keywords.add(r.name.lower())

    progressions: list[dict] = []
    for e in entries:
        if e.entry_type != "character":
            continue
        progs = db.get_psyke_progressions(e.id)
        for p in progs:
            prog_words = set(p.text.lower().split())
            all_keywords.update(w for w in prog_words if len(w) > 3)
            progressions.append({"name": e.name, "text": p.text})

    return PsykeSignals(
        characters=characters,
        relations=relations,
        unresolved_arcs=unresolved_arcs,
        keywords=frozenset(all_keywords),
        progressions=progressions,
    )


def gather_psyke_brief(db: Database, project_id: int, max_entries: int = 12) -> str:
    """Compact textual summary of PSYKE characters/places for prompt grounding."""
    entries = db.get_all_psyke_entries(project_id)
    if not entries:
        return ""

    chars = [e for e in entries if e.entry_type == "character"][:max_entries]
    places = [e for e in entries if e.entry_type == "place"][: max(3, max_entries // 3)]

    lines: list[str] = []
    if chars:
        lines.append("Characters:")
        for c in chars:
            note = (c.notes or "").strip().splitlines()
            summary = note[0] if note else ""
            lines.append(f"- {c.name}: {summary}" if summary else f"- {c.name}")
    if places:
        lines.append("")
        lines.append("Places:")
        for p in places:
            lines.append(f"- {p.name}")

    return "\n".join(lines)


def find_entry_by_name(db: Database, project_id: int, name: str):
    """Lookup PSYKE entry by exact name (case-insensitive)."""
    target = name.strip().lower()
    if not target:
        return None
    for e in db.get_all_psyke_entries(project_id):
        if e.name.lower() == target:
            return e
    return None


def apply_collapse(
    db: Database,
    project_id: int,
    branch: Branch,
) -> dict:
    """Apply a branch's state delta to PSYKE.

    - character_changes: append note to existing entry, or create new "other" entry
    - new_relations: connect two named PSYKE entries (no-op if either missing)
    - arc_updates: append note to entry, prefixed with "[arc]"

    Returns a summary of what was actually written.
    """
    delta = branch.state_delta
    summary = {
        "characters_updated": [],
        "characters_created": [],
        "relations_added": [],
        "arcs_updated": [],
        "skipped": [],
    }

    for change in delta.character_changes:
        name = (change.get("name") or "").strip()
        note = (change.get("note") or "").strip()
        if not name or not note:
            summary["skipped"].append({"reason": "missing name or note", "data": change})
            continue
        entry = find_entry_by_name(db, project_id, name)
        if entry is None:
            new_entry = db.create_psyke_entry(
                project_id=project_id,
                name=name,
                entry_type="character",
                notes=note,
            )
            summary["characters_created"].append({"id": new_entry.id, "name": name})
        else:
            combined = (entry.notes + "\n\n" + note).strip() if entry.notes else note
            db.update_psyke_entry(
                entry_id=entry.id,
                name=entry.name,
                entry_type=entry.entry_type,
                aliases=entry.aliases or "",
                notes=combined,
                is_global=bool(entry.is_global),
            )
            summary["characters_updated"].append({"id": entry.id, "name": name})

    for relation in delta.new_relations:
        a = (relation.get("from") or "").strip()
        b = (relation.get("to") or "").strip()
        if not a or not b:
            summary["skipped"].append({"reason": "missing from/to", "data": relation})
            continue
        entry_a = find_entry_by_name(db, project_id, a)
        entry_b = find_entry_by_name(db, project_id, b)
        if entry_a is None or entry_b is None:
            summary["skipped"].append({"reason": "entry not found", "data": relation})
            continue
        db.add_psyke_relation(entry_a.id, entry_b.id)
        summary["relations_added"].append({
            "from_id": entry_a.id, "to_id": entry_b.id,
            "from": entry_a.name, "to": entry_b.name,
        })

    for arc in delta.arc_updates:
        name = (arc.get("name") or "").strip()
        note = (arc.get("note") or "").strip()
        if not name or not note:
            summary["skipped"].append({"reason": "missing name or note", "data": arc})
            continue
        entry = find_entry_by_name(db, project_id, name)
        if entry is None:
            summary["skipped"].append({"reason": "entry not found for arc", "data": arc})
            continue
        prefixed = f"[arc] {note}"
        combined = (entry.notes + "\n\n" + prefixed).strip() if entry.notes else prefixed
        db.update_psyke_entry(
            entry_id=entry.id,
            name=entry.name,
            entry_type=entry.entry_type,
            aliases=entry.aliases or "",
            notes=combined,
            is_global=bool(entry.is_global),
        )
        summary["arcs_updated"].append({"id": entry.id, "name": name})

    return summary
