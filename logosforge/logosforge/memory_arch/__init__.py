"""LogosForge memory architecture — Phase 2 interfaces/stubs (isolated).

Core principle: **the model generates; LogosForge remembers, retrieves,
structures, updates, and syncs.** (`docs/architecture/MEMORY_ARCHITECTURE.md`.)

This package is **interfaces and non-destructive stubs only** — no SQLite
persistence, no migrations, no cloud sync, no GitHub commits, no vector
runtime, no external provider calls. Nothing here is wired into the running
Alpha; importing it must never affect app startup or provider behavior.

Project Memory and Assistant Meta-Memory are kept separate by scope (see
`schema.MemoryScope` and `policy.MemoryWriterPolicy`).
"""

from __future__ import annotations

from logosforge.memory_arch.schema import (
    EventLogEntry,
    MemoryObject,
    MemoryScope,
    MemoryStatus,
    MemoryType,
    SyncState,
)
from logosforge.memory_arch.store import InMemoryMemoryStore, MemoryStore
from logosforge.memory_arch.local_store import (
    LocalSQLiteMemoryStore,
    default_memory_db_path,
)
from logosforge.memory_arch.candidates import (
    ExtractionResult,
    PipelineResult,
    extract_candidates,
    process_event_for_memory_candidates,
    summarize_session,
)
from logosforge.memory_arch.review import MemoryCandidateReviewService

__all__ = [
    "EventLogEntry",
    "MemoryObject",
    "MemoryScope",
    "MemoryStatus",
    "MemoryType",
    "SyncState",
    "MemoryStore",
    "InMemoryMemoryStore",
    "LocalSQLiteMemoryStore",
    "default_memory_db_path",
    "ExtractionResult",
    "PipelineResult",
    "extract_candidates",
    "process_event_for_memory_candidates",
    "summarize_session",
    "MemoryCandidateReviewService",
]
