"""Memory retrieval helper (Phase 2 placeholder).

A thin, store-backed retrieval surface used by the assistant context
builder. Safe when no store is configured (returns empty). No model calls,
no mutation, no network. Real semantic ranking is a later phase.
"""

from __future__ import annotations

from logosforge.memory_arch.schema import MemoryObject, MemoryScope
from logosforge.memory_arch.store import MemoryStore


class MemoryRetriever:
    def __init__(self, store: MemoryStore | None = None) -> None:
        self._store = store

    def retrieve(self, query: str, scopes: list[MemoryScope] | None = None,
                 project_id: str | None = None,
                 user_id: str | None = None,
                 workspace_id: str | None = None) -> list[MemoryObject]:
        """Return relevant memory across the requested scopes. Empty (never
        raises) when no store is configured — assistant flows must degrade
        gracefully if memory is unavailable."""
        if self._store is None:
            return []
        scopes = scopes or [MemoryScope.PROJECT, MemoryScope.USER,
                            MemoryScope.ASSISTANT]
        out: list[MemoryObject] = []
        seen: set[str] = set()
        for scope in scopes:
            pid = project_id if scope is MemoryScope.PROJECT else None
            for mem in self._store.search(query, scope=scope, project_id=pid):
                if mem.id not in seen:
                    seen.add(mem.id)
                    out.append(mem)
        return out
