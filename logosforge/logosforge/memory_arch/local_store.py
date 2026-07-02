"""Local-first SQLite memory store (Phase 3 MVP).

A concrete `MemoryStore` backed by **isolated stdlib `sqlite3`** — entirely
separate from the app's SQLModel project database (no shared engine, no
migrations to existing tables, no startup coupling). It persists structured
memory objects + event-log entries locally only:

- **No network, no cloud sync, no GitHub, no embeddings, no provider calls.**
- **No destructive delete** (supersede preserves history).
- Candidates persist as `proposed`/`speculative`; activation is explicit.
- The writer policy rejects obvious secrets / raw audio before any write.

The database file is created **only when this store is instantiated** with a
path — nothing here runs at import or app startup. Use `:memory:` (default)
or `default_memory_db_path()` for an app-data-local file.
"""

from __future__ import annotations

import json
import sqlite3
import time

from logosforge.memory_arch.policy import MemoryWriterPolicy
from logosforge.memory_arch.schema import (
    EventLogEntry,
    MemoryObject,
    MemoryScope,
    MemoryStatus,
    SyncState,
)
from logosforge.memory_arch.store import MemoryStore

_MEMORY_DB_FILENAME = "logosforge_memory.sqlite3"


def default_memory_db_path() -> str:
    """App-data-local memory DB path (``~/.logosforge/...``). Returning the
    path does **not** create the file — only instantiating the store does."""
    from logosforge import settings
    return str(settings.CONFIG_DIR / _MEMORY_DB_FILENAME)


_SCHEMA = """
CREATE TABLE IF NOT EXISTS memory_events (
    id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    content TEXT NOT NULL,
    user_id TEXT,
    project_id TEXT,
    workspace_id TEXT,
    session_id TEXT,
    source TEXT,
    created_at REAL,
    metadata_json TEXT
);
CREATE TABLE IF NOT EXISTS memory_objects (
    id TEXT PRIMARY KEY,
    scope TEXT NOT NULL,
    type TEXT NOT NULL,
    content TEXT NOT NULL,
    source_event TEXT,
    project_id TEXT,
    user_id TEXT,
    workspace_id TEXT,
    confidence REAL,
    status TEXT NOT NULL,
    created_at REAL,
    updated_at REAL,
    supersedes TEXT,
    contradicted_by_json TEXT,
    tags_json TEXT,
    entities_json TEXT,
    visibility TEXT,
    sync_state TEXT,
    version INTEGER,
    extra_json TEXT
);
CREATE TABLE IF NOT EXISTS memory_relations (
    id TEXT PRIMARY KEY,
    source_memory_id TEXT NOT NULL,
    target_memory_id TEXT NOT NULL,
    relation_type TEXT,
    reason TEXT,
    created_at REAL
);
"""


class LocalSQLiteMemoryStore(MemoryStore):
    """Local durable memory store. ``path=":memory:"`` for an ephemeral
    in-process DB (tests); a filesystem path for persistence."""

    def __init__(self, path: str = ":memory:",
                 policy: MemoryWriterPolicy | None = None) -> None:
        self._path = path
        self._policy = policy or MemoryWriterPolicy()
        # check_same_thread=False keeps it usable from worker threads later;
        # this store is single-writer in the MVP.
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._ensure_columns()
        self._conn.commit()

    def _ensure_columns(self) -> None:
        """Additive migration for older DBs: add the policy-metadata column if a
        pre-existing database lacks it. New DBs already have it via _SCHEMA."""
        cols = {r["name"] for r in self._conn.execute(
            "PRAGMA table_info(memory_objects)")}
        if "extra_json" not in cols:
            self._conn.execute(
                "ALTER TABLE memory_objects ADD COLUMN extra_json TEXT")
            self._conn.commit()

    # ------------------------------------------------------------- events
    def add_event(self, event: EventLogEntry) -> EventLogEntry:
        self._conn.execute(
            "INSERT INTO memory_events (id, event_type, content, user_id, "
            "project_id, workspace_id, session_id, source, created_at, "
            "metadata_json) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (event.id, event.event_type, event.content, event.user_id,
             event.project_id, event.workspace_id, event.session_id,
             event.source, event.created_at, json.dumps(event.metadata)))
        self._conn.commit()
        return event

    def get_event(self, event_id: str) -> EventLogEntry | None:
        row = self._conn.execute(
            "SELECT * FROM memory_events WHERE id = ?", (event_id,)).fetchone()
        if row is None:
            return None
        return self._row_to_event(row)

    def list_events(self, session_id: str | None = None,
                    project_id: str | None = None) -> list[EventLogEntry]:
        sql = "SELECT * FROM memory_events WHERE 1=1"
        args: list = []
        if session_id is not None:
            sql += " AND session_id = ?"
            args.append(session_id)
        if project_id is not None:
            sql += " AND project_id = ?"
            args.append(project_id)
        sql += " ORDER BY created_at"
        rows = self._conn.execute(sql, args).fetchall()
        return [self._row_to_event(r) for r in rows]

    @staticmethod
    def _row_to_event(row: sqlite3.Row) -> EventLogEntry:
        return EventLogEntry(
            id=row["id"], event_type=row["event_type"], content=row["content"],
            user_id=row["user_id"], project_id=row["project_id"],
            workspace_id=row["workspace_id"], session_id=row["session_id"],
            source=row["source"] or "", created_at=row["created_at"],
            metadata=json.loads(row["metadata_json"] or "{}"))

    # ------------------------------------------------------------- memory
    def write_candidate(self, memory: MemoryObject) -> MemoryObject:
        # Candidates only — never silently active. proposed / speculative /
        # review_required are accepted. Policy guards secrets/raw-audio + scope.
        if memory.status not in (MemoryStatus.PROPOSED,
                                 MemoryStatus.SPECULATIVE,
                                 MemoryStatus.REVIEW_REQUIRED):
            raise ValueError(
                "write_candidate accepts proposed/speculative/review_required "
                "status only; use approve_candidate or save_active to activate.")
        forbidden = self._policy.check_forbidden_content(memory)
        if forbidden:
            raise ValueError(f"refused forbidden content: {forbidden}")
        self._policy.validate_scope(memory)
        self._insert(memory)
        return memory

    def save_active(self, memory: MemoryObject) -> MemoryObject:
        # Automatic policy auto-save: write an active memory directly. Still
        # forbidden-content + scope guarded (auto-active must never hold secrets
        # / raw audio, and must respect Project↔Assistant separation). Auditable
        # (source_event, version), reversible (update), supersedable (supersede).
        forbidden = self._policy.check_forbidden_content(memory)
        if forbidden:
            raise ValueError(f"refused forbidden content: {forbidden}")
        self._policy.validate_scope(memory)
        memory.status = MemoryStatus.ACTIVE
        memory.auto_saved = True
        self._insert(memory)
        return memory

    def approve_candidate(self, memory_id: str) -> MemoryObject:
        mem = self._require(memory_id)
        mem.status = MemoryStatus.ACTIVE
        mem.updated_at = time.time()
        mem.version += 1
        self._update_row(mem)
        return mem

    def get(self, memory_id: str) -> MemoryObject | None:
        row = self._conn.execute(
            "SELECT * FROM memory_objects WHERE id = ?",
            (memory_id,)).fetchone()
        return self._row_to_obj(row) if row is not None else None

    def search(self, query: str, scope: MemoryScope | None = None,
               project_id: str | None = None,
               filters: dict | None = None) -> list[MemoryObject]:
        sql = "SELECT * FROM memory_objects WHERE 1=1"
        args: list = []
        if query:
            sql += " AND lower(content) LIKE ?"
            args.append(f"%{query.lower()}%")
        if scope is not None:
            sql += " AND scope = ?"
            args.append(MemoryScope(scope).value)
        if project_id is not None:
            sql += " AND project_id = ?"
            args.append(project_id)
        filters = filters or {}
        if "type" in filters and filters["type"] is not None:
            sql += " AND type = ?"
            args.append(_enum_value(filters["type"]))
        if "status" in filters and filters["status"] is not None:
            sql += " AND status = ?"
            args.append(_enum_value(filters["status"]))
        sql += " ORDER BY created_at"
        rows = self._conn.execute(sql, args).fetchall()
        return [self._row_to_obj(r) for r in rows]

    def update(self, memory_id: str, patch: dict, reason: str) -> MemoryObject:
        if not (reason or "").strip():
            raise ValueError("update requires a non-empty reason.")
        mem = self._require(memory_id)
        for key, value in (patch or {}).items():
            if hasattr(mem, key):
                setattr(mem, key, value)
        # Re-coerce enums / re-validate invariants after the patch.
        mem.__post_init__()
        mem.updated_at = time.time()
        mem.version += 1
        self._update_row(mem)
        return mem

    def supersede(self, old_id: str, new_id: str,
                  reason: str) -> tuple[MemoryObject, MemoryObject]:
        if not (reason or "").strip():
            raise ValueError("supersede requires a non-empty reason.")
        old = self._require(old_id)
        new = self._require(new_id)
        old.status = MemoryStatus.SUPERSEDED          # preserved, not deleted
        old.updated_at = time.time()
        old.version += 1
        new.supersedes = old_id
        self._update_row(old)
        self._update_row(new)
        self._conn.execute(
            "INSERT INTO memory_relations (id, source_memory_id, "
            "target_memory_id, relation_type, reason, created_at) "
            "VALUES (?,?,?,?,?,?)",
            (f"{old_id}->{new_id}", old_id, new_id, "supersedes", reason,
             time.time()))
        self._conn.commit()
        return old, new

    def find_contradictions(self, topic: str,
                            project_id: str | None = None
                            ) -> list[MemoryObject]:
        # MVP: surfaces objects already flagged `contradicted` matching the
        # topic. Real semantic contradiction reasoning is a later phase.
        rows = self.search(topic, project_id=project_id,
                           filters={"status": MemoryStatus.CONTRADICTED})
        return rows

    def export_markdown(self, scope: MemoryScope | None = None,
                        project_id: str | None = None) -> str:
        rows = self.search("", scope=scope, project_id=project_id)
        lines = [
            "# LogosForge memory export",
            "",
            f"_Generated: {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}_",
            f"_Scope filter: {scope.value if scope else 'all'}_",
            f"_Project filter: {project_id or 'all'}_",
            "",
        ]
        # Group by scope → type → status.
        grouped: dict = {}
        for mem in rows:
            grouped.setdefault(mem.scope.value, {}).setdefault(
                mem.type.value, []).append(mem)
        for scope_name in sorted(grouped):
            lines.append(f"## Scope: {scope_name}")
            lines.append("")
            for type_name in sorted(grouped[scope_name]):
                lines.append(f"### {type_name}")
                lines.append("")
                for mem in grouped[scope_name][type_name]:
                    lines.append(f"- **{mem.content}**")
                    lines.append(f"  - id: `{mem.id}` · status: "
                                 f"{mem.status.value} · confidence: "
                                 f"{mem.confidence}")
                    lines.append(f"  - created_at: {mem.created_at} · "
                                 f"updated_at: {mem.updated_at}")
                    if mem.tags:
                        lines.append(f"  - tags: {', '.join(mem.tags)}")
                    if mem.entities:
                        lines.append(f"  - entities: {', '.join(mem.entities)}")
                    if mem.supersedes:
                        lines.append(f"  - supersedes: `{mem.supersedes}`")
                    if mem.contradicted_by:
                        lines.append("  - contradicted_by: "
                                     + ", ".join(f"`{c}`"
                                                 for c in mem.contradicted_by))
                lines.append("")
        return "\n".join(lines).rstrip() + "\n"

    def close(self) -> None:
        self._conn.close()

    # ------------------------------------------------------------- internals
    def _insert(self, mem: MemoryObject) -> None:
        self._conn.execute(
            "INSERT INTO memory_objects (id, scope, type, content, "
            "source_event, project_id, user_id, workspace_id, confidence, "
            "status, created_at, updated_at, supersedes, contradicted_by_json,"
            " tags_json, entities_json, visibility, sync_state, version, "
            "extra_json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            self._to_params(mem))
        self._conn.commit()

    def _update_row(self, mem: MemoryObject) -> None:
        self._conn.execute(
            "UPDATE memory_objects SET scope=?, type=?, content=?, "
            "source_event=?, project_id=?, user_id=?, workspace_id=?, "
            "confidence=?, status=?, created_at=?, updated_at=?, supersedes=?, "
            "contradicted_by_json=?, tags_json=?, entities_json=?, "
            "visibility=?, sync_state=?, version=?, extra_json=? WHERE id=?",
            self._to_params(mem)[1:] + (mem.id,))
        self._conn.commit()

    @staticmethod
    def _extra_json(mem: MemoryObject) -> str:
        return json.dumps({
            "auto_saved": getattr(mem, "auto_saved", False),
            "requires_review": getattr(mem, "requires_review", False),
            "policy_decision": getattr(mem, "policy_decision", ""),
            "risk_level": getattr(mem, "risk_level", ""),
            "review_reason": getattr(mem, "review_reason", ""),
            "sensitive_flags": getattr(mem, "sensitive_flags", []),
        })

    @staticmethod
    def _to_params(mem: MemoryObject) -> tuple:
        return (
            mem.id, mem.scope.value, mem.type.value, mem.content,
            mem.source_event, mem.project_id, mem.user_id, mem.workspace_id,
            mem.confidence, mem.status.value, mem.created_at, mem.updated_at,
            mem.supersedes, json.dumps(mem.contradicted_by),
            json.dumps(mem.tags), json.dumps(mem.entities), mem.visibility,
            mem.sync_state.value, mem.version,
            LocalSQLiteMemoryStore._extra_json(mem))

    @staticmethod
    def _row_to_obj(row: sqlite3.Row) -> MemoryObject:
        extra = {}
        keys = row.keys()
        if "extra_json" in keys and row["extra_json"]:
            try:
                extra = json.loads(row["extra_json"])
            except (TypeError, ValueError):
                extra = {}
        return MemoryObject(
            id=row["id"], scope=MemoryScope(row["scope"]),
            type=row["type"], content=row["content"],
            source_event=row["source_event"], project_id=row["project_id"],
            user_id=row["user_id"], workspace_id=row["workspace_id"],
            confidence=row["confidence"] or 0.0,
            status=MemoryStatus(row["status"]),
            created_at=row["created_at"], updated_at=row["updated_at"],
            supersedes=row["supersedes"],
            contradicted_by=json.loads(row["contradicted_by_json"] or "[]"),
            tags=json.loads(row["tags_json"] or "[]"),
            entities=json.loads(row["entities_json"] or "[]"),
            visibility=row["visibility"] or "private",
            sync_state=SyncState(row["sync_state"] or "local_only"),
            version=row["version"] or 1,
            auto_saved=bool(extra.get("auto_saved", False)),
            requires_review=bool(extra.get("requires_review", False)),
            policy_decision=extra.get("policy_decision", "") or "",
            risk_level=extra.get("risk_level", "") or "",
            review_reason=extra.get("review_reason", "") or "",
            sensitive_flags=list(extra.get("sensitive_flags", []) or []))

    def _require(self, memory_id: str) -> MemoryObject:
        mem = self.get(memory_id)
        if mem is None:
            raise KeyError(f"memory not found: {memory_id}")
        return mem


def _enum_value(v) -> str:
    return v.value if hasattr(v, "value") else str(v)
