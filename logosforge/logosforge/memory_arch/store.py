"""Memory store interface + in-memory test stub (Phase 2).

`MemoryStore` is the abstract contract from
`docs/architecture/ASSISTANT_TOOLS_SPEC.md`. `InMemoryMemoryStore` is a
**test-only**, non-persistent implementation — no SQLite, no migrations, no
network. There is deliberately **no delete** method (MVP keeps superseded
history for audit).
"""

from __future__ import annotations

import abc

from logosforge.memory_arch.schema import (
    EventLogEntry,
    MemoryObject,
    MemoryScope,
    MemoryStatus,
    MemoryType,
)


class MemoryStore(abc.ABC):
    """Durable-memory contract. No destructive delete in the MVP interface;
    no automatic active writes; updates require a reason; supersede preserves
    the old object."""

    @abc.abstractmethod
    def add_event(self, event: EventLogEntry) -> EventLogEntry: ...

    @abc.abstractmethod
    def get_event(self, event_id: str) -> EventLogEntry | None: ...

    @abc.abstractmethod
    def list_events(self, session_id: str | None = None,
                    project_id: str | None = None) -> list[EventLogEntry]: ...

    @abc.abstractmethod
    def write_candidate(self, memory: MemoryObject) -> MemoryObject: ...

    @abc.abstractmethod
    def save_active(self, memory: MemoryObject) -> MemoryObject:
        """Write an already-active memory (the automatic policy pipeline's
        auto-save path). Must be auditable, reversible, and supersedable; must
        never store secrets/raw-audio. Distinct from `write_candidate`, which
        only ever accepts non-active candidates."""

    @abc.abstractmethod
    def approve_candidate(self, memory_id: str) -> MemoryObject: ...

    @abc.abstractmethod
    def get(self, memory_id: str) -> MemoryObject | None: ...

    @abc.abstractmethod
    def search(self, query: str, scope: MemoryScope | None = None,
               project_id: str | None = None,
               filters: dict | None = None) -> list[MemoryObject]: ...

    @abc.abstractmethod
    def update(self, memory_id: str, patch: dict,
               reason: str) -> MemoryObject: ...

    @abc.abstractmethod
    def supersede(self, old_id: str, new_id: str,
                  reason: str) -> tuple[MemoryObject, MemoryObject]: ...

    @abc.abstractmethod
    def find_contradictions(self, topic: str,
                            project_id: str | None = None
                            ) -> list[MemoryObject]: ...

    @abc.abstractmethod
    def export_markdown(self, scope: MemoryScope | None = None,
                        project_id: str | None = None) -> str: ...


class InMemoryMemoryStore(MemoryStore):
    """Non-persistent store for tests/dev. Holds objects in dicts; nothing
    touches disk, network, or any provider."""

    def __init__(self) -> None:
        self._events: dict[str, EventLogEntry] = {}
        self._memories: dict[str, MemoryObject] = {}

    def add_event(self, event: EventLogEntry) -> EventLogEntry:
        self._events[event.id] = event
        return event

    def get_event(self, event_id: str) -> EventLogEntry | None:
        return self._events.get(event_id)

    def list_events(self, session_id: str | None = None,
                    project_id: str | None = None) -> list[EventLogEntry]:
        out = [
            ev for ev in self._events.values()
            if (session_id is None or ev.session_id == session_id)
            and (project_id is None or ev.project_id == project_id)
        ]
        return sorted(out, key=lambda e: e.created_at)

    def write_candidate(self, memory: MemoryObject) -> MemoryObject:
        # A candidate is never silently made active here: proposed / speculative
        # / review_required are accepted. Activation is explicit (approve) or via
        # the policy auto-save path (save_active).
        if memory.status not in (MemoryStatus.PROPOSED,
                                 MemoryStatus.SPECULATIVE,
                                 MemoryStatus.REVIEW_REQUIRED):
            raise ValueError(
                "write_candidate accepts proposed/speculative/review_required "
                "status only; use approve_candidate or save_active to activate.")
        self._memories[memory.id] = memory
        return memory

    def save_active(self, memory: MemoryObject) -> MemoryObject:
        # Automatic policy auto-save: store an active memory directly. The
        # caller (policy pipeline) has already gated safety; nothing here makes
        # memory active without a policy/approval decision upstream.
        memory.status = MemoryStatus.ACTIVE
        memory.auto_saved = True
        self._memories[memory.id] = memory
        return memory

    def approve_candidate(self, memory_id: str) -> MemoryObject:
        mem = self._require(memory_id)
        mem.status = MemoryStatus.ACTIVE
        mem.updated_at = _touch(mem)
        mem.version += 1
        return mem

    def get(self, memory_id: str) -> MemoryObject | None:
        return self._memories.get(memory_id)

    def search(self, query: str, scope: MemoryScope | None = None,
               project_id: str | None = None,
               filters: dict | None = None) -> list[MemoryObject]:
        q = (query or "").lower()
        filters = filters or {}
        want_type = filters.get("type")
        want_status = filters.get("status")
        out = []
        for mem in self._memories.values():
            if scope is not None and mem.scope is not MemoryScope(scope):
                continue
            if project_id is not None and mem.project_id != project_id:
                continue
            if q and q not in mem.content.lower():
                continue
            if want_type is not None and mem.type is not MemoryType(want_type):
                continue
            if want_status is not None \
                    and mem.status is not MemoryStatus(want_status):
                continue
            out.append(mem)
        return out

    def update(self, memory_id: str, patch: dict,
               reason: str) -> MemoryObject:
        if not (reason or "").strip():
            raise ValueError("update requires a non-empty reason.")
        mem = self._require(memory_id)
        for key, value in (patch or {}).items():
            if hasattr(mem, key):
                setattr(mem, key, value)
        mem.updated_at = _touch(mem)
        mem.version += 1
        return mem

    def supersede(self, old_id: str, new_id: str,
                  reason: str) -> tuple[MemoryObject, MemoryObject]:
        if not (reason or "").strip():
            raise ValueError("supersede requires a non-empty reason.")
        old = self._require(old_id)
        new = self._require(new_id)
        old.status = MemoryStatus.SUPERSEDED      # preserved, never deleted
        old.updated_at = _touch(old)
        old.version += 1
        new.supersedes = old_id
        return old, new

    def find_contradictions(self, topic: str,
                            project_id: str | None = None
                            ) -> list[MemoryObject]:
        # Stub: real contradiction detection lands in a later phase.
        return []

    def export_markdown(self, scope: MemoryScope | None = None,
                        project_id: str | None = None) -> str:
        rows = self.search("", scope=scope, project_id=project_id)
        lines = ["# Memory export", ""]
        for mem in rows:
            lines.append(f"- **[{mem.scope.value}/{mem.type.value}]** "
                         f"({mem.status.value}) {mem.content}")
        return "\n".join(lines) + "\n"

    def _require(self, memory_id: str) -> MemoryObject:
        mem = self._memories.get(memory_id)
        if mem is None:
            raise KeyError(f"memory not found: {memory_id}")
        return mem


def _touch(_mem: MemoryObject) -> float:
    import time
    return time.time()
