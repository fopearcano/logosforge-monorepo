"""Canonical memory object + event-log schema (Phase 2 stub).

Mirrors `docs/architecture/MEMORY_OBJECT_SCHEMA.md`. Plain dataclasses +
stdlib enums (the domain-object style used by ``providers.py`` /
``voice/types.py``); no Pydantic, no DB, no external deps.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum


class MemoryScope(str, Enum):
    USER = "user"
    PROJECT = "project"
    WORKSPACE = "workspace"
    ASSISTANT = "assistant"
    DEVICE = "device"


class MemoryType(str, Enum):
    PREFERENCE = "preference"
    PROJECT_DECISION = "project_decision"
    CORRECTION = "correction"
    PROCEDURAL_RULE = "procedural_rule"
    SESSION_SUMMARY = "session_summary"
    CHARACTER_FACT = "character_fact"
    CONTINUITY_FACT = "continuity_fact"
    ARCHITECTURE_DECISION = "architecture_decision"
    REPO_DECISION = "repo_decision"
    WORKFLOW_RULE = "workflow_rule"
    ASSISTANT_RULE = "assistant_rule"
    MISTAKE_CORRECTION = "mistake_correction"
    DEFERRED_FEATURE = "deferred_feature"
    LIMITATION = "limitation"
    MODEL_PREFERENCE = "model_preference"
    PROVIDER_CONFIG_NOTE = "provider_config_note"
    RELEASE_BLOCKER_RULE = "release_blocker_rule"
    SPECULATIVE_IDEA = "speculative_idea"
    OTHER = "other"


class MemoryStatus(str, Enum):
    ACTIVE = "active"
    PROPOSED = "proposed"
    REVIEW_REQUIRED = "review_required"  # auto-pipeline flagged it for the user
    SPECULATIVE = "speculative"
    REJECTED = "rejected"          # Phase 4: reviewed and declined (kept, not deleted)
    DEPRECATED = "deprecated"
    SUPERSEDED = "superseded"
    CONTRADICTED = "contradicted"


class SyncState(str, Enum):
    LOCAL_ONLY = "local_only"
    PENDING_SYNC = "pending_sync"
    SYNCED = "synced"
    CONFLICT = "conflict"


def _now() -> float:
    return time.time()


def _new_id() -> str:
    return uuid.uuid4().hex


@dataclass
class MemoryObject:
    """A single curated, scoped, versioned memory fact/decision/rule.

    Invariants (enforced in ``__post_init__``): ``scope`` and ``type`` are
    explicit; a project-scoped object needs ``project_id``; a user-scoped
    object needs ``user_id``; ``status`` defaults to **proposed** (never
    active unless explicitly constructed active)."""

    scope: MemoryScope
    type: MemoryType
    content: str
    id: str = field(default_factory=_new_id)
    source_event: str | None = None
    project_id: str | None = None
    user_id: str | None = None
    workspace_id: str | None = None
    confidence: float = 0.0
    status: MemoryStatus = MemoryStatus.PROPOSED
    created_at: float = field(default_factory=_now)
    updated_at: float = field(default_factory=_now)
    supersedes: str | None = None
    contradicted_by: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    entities: list[str] = field(default_factory=list)
    visibility: str = "private"
    sync_state: SyncState = SyncState.LOCAL_ONLY
    version: int = 1
    # -- automatic policy-governed pipeline metadata (Direction Correction) ---
    # Safe optional fields; defaults preserve every existing construction call.
    # auto_saved: written active directly by policy (not via manual approval).
    # requires_review: flagged for the user (uncertain/sensitive/conflicting).
    # policy_decision / risk_level / review_reason: audit of why it landed here.
    auto_saved: bool = False
    requires_review: bool = False
    policy_decision: str = ""
    risk_level: str = ""
    review_reason: str = ""
    sensitive_flags: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        # Coerce string values to enums so callers may pass either form.
        self.scope = MemoryScope(self.scope)
        self.type = MemoryType(self.type)
        self.status = MemoryStatus(self.status)
        self.sync_state = SyncState(self.sync_state)
        if not (self.content or "").strip():
            raise ValueError("MemoryObject.content must be non-empty.")
        if self.scope is MemoryScope.PROJECT and not self.project_id:
            raise ValueError("project scope requires project_id.")
        if self.scope is MemoryScope.USER and not self.user_id:
            raise ValueError("user scope requires user_id.")


@dataclass
class EventLogEntry:
    """Raw-ish interaction/change history. NOT automatically durable memory —
    curated memory objects are *extracted* from events, never auto-promoted.
    (Phase 2 defines the schema only; no logger records chats yet.)"""

    event_type: str
    content: str
    id: str = field(default_factory=_new_id)
    user_id: str | None = None
    project_id: str | None = None
    workspace_id: str | None = None
    session_id: str | None = None
    source: str = ""
    created_at: float = field(default_factory=_now)
    metadata: dict = field(default_factory=dict)
