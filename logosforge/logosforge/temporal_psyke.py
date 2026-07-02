"""Temporal PSYKE — lightweight time-aware reasoning over story bible entries.

Builds an in-memory snapshot from existing PSYKE data (entries, relations,
progressions, scenes) and answers temporal queries using scene sort_order
as the authoritative timeline.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass
class EntryState:
    """Resolved state of a PSYKE entry at a given narrative point."""

    entry_id: int
    name: str
    entry_type: str
    notes: str
    details: dict
    is_global: bool
    progression_text: str
    progression_scene_order: int | None
    progression_id: int | None
    has_progression: bool


@dataclass
class RelatedEntryState:
    """One-hop related entry with its resolved state."""

    entry_id: int
    name: str
    entry_type: str
    state: EntryState
    active: bool


@dataclass
class TemporalInspection:
    """Debug/inspection output for a temporal query."""

    entry_id: int
    entry_name: str
    query_scene_order: int
    selected_progression_id: int | None
    selected_progression_text: str
    selected_scene_order: int | None
    all_progressions: list[dict]
    related_entries: list[dict]


@dataclass
class _ProgInfo:
    prog_id: int
    entry_id: int
    text: str
    scene_id: int | None
    sort_order: int
    scene_sort_order: int | None


class TemporalGraph:
    """In-memory temporal snapshot of a project's PSYKE data."""

    def __init__(self, db: Any, project_id: int) -> None:
        self._entries: dict[int, Any] = {}
        self._progressions: dict[int, list[_ProgInfo]] = {}
        self._relations: dict[int, list[int]] = {}
        self._scene_order: dict[int, int] = {}
        self._build(db, project_id)

    def _build(self, db: Any, project_id: int) -> None:
        scenes = db.get_all_scenes(project_id)
        self._scene_order = {s.id: s.sort_order for s in scenes}

        entries = db.get_all_psyke_entries(project_id)
        for e in entries:
            self._entries[e.id] = e

        for e in entries:
            progs = db.get_psyke_progressions(e.id)
            prog_infos = []
            for p in progs:
                scene_so = None
                if p.scene_id and p.scene_id in self._scene_order:
                    scene_so = self._scene_order[p.scene_id]
                prog_infos.append(_ProgInfo(
                    prog_id=p.id,
                    entry_id=e.id,
                    text=p.text,
                    scene_id=p.scene_id,
                    sort_order=p.sort_order,
                    scene_sort_order=scene_so,
                ))
            self._progressions[e.id] = prog_infos

            related = db.get_related_psyke_entries(e.id)
            self._relations[e.id] = [r.id for r in related]

    def _parse_details(self, entry: Any) -> dict:
        try:
            return json.loads(entry.details_json) if entry.details_json else {}
        except (json.JSONDecodeError, TypeError):
            return {}

    def get_latest_progression_before(
        self, entry_id: int, scene_order: int,
    ) -> _ProgInfo | None:
        progs = self._progressions.get(entry_id, [])
        if not progs:
            return None

        anchored: list[_ProgInfo] = []
        unanchored: list[_ProgInfo] = []

        for p in progs:
            if p.scene_sort_order is not None:
                if p.scene_sort_order <= scene_order:
                    anchored.append(p)
            else:
                unanchored.append(p)

        if anchored:
            return max(anchored, key=lambda p: (p.scene_sort_order, p.sort_order))

        if unanchored:
            return max(unanchored, key=lambda p: p.sort_order)

        return None

    def get_entry_state_at(
        self, entry_id: int, scene_order: int,
    ) -> EntryState | None:
        entry = self._entries.get(entry_id)
        if entry is None:
            return None

        prog = self.get_latest_progression_before(entry_id, scene_order)

        return EntryState(
            entry_id=entry.id,
            name=entry.name,
            entry_type=entry.entry_type,
            notes=entry.notes,
            details=self._parse_details(entry),
            is_global=entry.is_global,
            progression_text=prog.text if prog else "",
            progression_scene_order=prog.scene_sort_order if prog else None,
            progression_id=prog.prog_id if prog else None,
            has_progression=prog is not None,
        )

    def get_active_related_entries(
        self, entry_id: int, scene_order: int,
    ) -> list[RelatedEntryState]:
        related_ids = self._relations.get(entry_id, [])
        results: list[RelatedEntryState] = []

        for rid in related_ids:
            state = self.get_entry_state_at(rid, scene_order)
            if state is None:
                continue
            progs = self._progressions.get(rid, [])
            if not progs:
                active = True
            else:
                active = state.has_progression
            results.append(RelatedEntryState(
                entry_id=rid,
                name=state.name,
                entry_type=state.entry_type,
                state=state,
                active=active,
            ))

        return results

    def inspect(
        self, entry_id: int, scene_order: int,
    ) -> TemporalInspection | None:
        entry = self._entries.get(entry_id)
        if entry is None:
            return None

        all_progs = []
        for p in self._progressions.get(entry_id, []):
            all_progs.append({
                "id": p.prog_id,
                "text": p.text,
                "scene_id": p.scene_id,
                "sort_order": p.sort_order,
                "scene_sort_order": p.scene_sort_order,
                "eligible": (
                    p.scene_sort_order is None
                    or p.scene_sort_order <= scene_order
                ),
            })

        prog = self.get_latest_progression_before(entry_id, scene_order)

        related_info = []
        for rel in self.get_active_related_entries(entry_id, scene_order):
            related_info.append({
                "entry_id": rel.entry_id,
                "name": rel.name,
                "active": rel.active,
                "progression": rel.state.progression_text,
                "progression_scene_order": rel.state.progression_scene_order,
            })

        return TemporalInspection(
            entry_id=entry_id,
            entry_name=entry.name,
            query_scene_order=scene_order,
            selected_progression_id=prog.prog_id if prog else None,
            selected_progression_text=prog.text if prog else "",
            selected_scene_order=prog.scene_sort_order if prog else None,
            all_progressions=all_progs,
            related_entries=related_info,
        )
