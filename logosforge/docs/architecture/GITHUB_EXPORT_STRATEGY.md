# GitHub Export Strategy

> Phase 1 — direction only. **GitHub is optional, never the default.** No
> export automation is implemented here (and none until Phase 5, manual push
> only).

## GitHub may be used for

- developers and power users
- backup / export
- markdown memory archive
- Claude Code workflows
- repository-linked projects
- versioning architecture docs
- project memory snapshots **if explicitly enabled**

## GitHub must NOT be

- required for normal users
- the default memory backend
- the default sync backend
- used for automatic commits without user approval
- used to store secrets
- used to store raw private chat logs by default
- used to store raw audio

## Export types

- memory snapshot (markdown)
- architecture decision log
- assistant meta-memory changelog
- project memory summary
- session summary
- prompt history archive
- Claude Code workflow notes

## Safety

- **explicit opt-in** per export type
- **clear preview** before any write
- **no secrets** (provider keys, tokens) ever exported
- **no automatic push** unless explicitly enabled by the user
- every artifact carries **project / user / workspace scope labels**
- **sensitive-memory warning** before exporting anything visibility-limited

## Relationship to sync

GitHub is an **archive/export layer on top of** local + cloud memory
(`SYNC_STRATEGY.md`), not a replacement for either. The canonical shared
state is the cloud account/workspace memory (future); GitHub is an optional
human-readable/versioned mirror for those who want it.


## Phase 2 — implemented interface locations

Interfaces/stubs only (no DB, no cloud sync, no GitHub commits, no vector runtime, no external provider calls, no UI wiring, no automatic durable writes). New isolated packages:

- `logosforge/memory_arch/` — `schema.py` (MemoryObject, EventLogEntry, enums), `store.py` (`MemoryStore` ABC + `InMemoryMemoryStore`), `policy.py` (`MemoryWriterPolicy`), `retrieval.py`, `contradictions.py`, `sync.py` (disabled), `github_export.py` (disabled).
- `logosforge/assistant_arch/` — `model_gateway.py` (`ProviderCapability`/`ModelRequest`/`ModelResponse`/`ModelProvider`/`ModelGateway` + `DummyModelProvider`), `context_builder.py` (`AssistantContextBuilder`, `ContextBundle`, `MemoryCandidateExtractor`), `orchestration.py` (`AssistantOrchestrator`), `tools.py` (`AssistantTools`).

Tests: `tests/test_memory_architecture_stubs.py` (21). The Alpha assistant (`assistant.py`, Billy/Logos/Dexter) and `providers.py` are unchanged.


## Phase 3 — Local MVP Memory Store

**Implemented now** (`logosforge/memory_arch/local_store.py` — isolated stdlib `sqlite3`, separate from the app's SQLModel project DB):

- `LocalSQLiteMemoryStore(path)` implementing the full `MemoryStore` ABC; tables `memory_events`, `memory_objects`, `memory_relations` (JSON-as-text columns for lists).
- local structured memory persistence + event log; explicit approval workflow (candidates stay proposed/speculative; `approve_candidate` activates); `update` requires a reason; `supersede` preserves the old object (marked superseded + linked) — **no destructive delete**.
- simple substring/scope/project/type/status search; safe scoped/grouped markdown export (no secrets / raw audio / DB internals).
- writer-policy enforcement on write (rejects obvious secrets + raw-audio paths; enforces explicit scope, project/user ids, and the Project↔Assistant separation).
- DB path is opt-in (`:memory:` default; `default_memory_db_path()` → `~/.logosforge/logosforge_memory.sqlite3`). **No DB is created on import or app startup**; nothing is wired into the running app/UI/providers; the file is git-ignored.

**Still NOT implemented:** automatic memory extraction from chats; vector embeddings; cloud sync; GitHub auto-export; memory-approval UI; model-provider memory; provider calls; full contradiction reasoning (`find_contradictions` only surfaces already-flagged `contradicted` rows).

**Reaffirmed:** the model generates, LogosForge remembers; GitHub is optional only; Project Memory and Assistant Meta-Memory stay separate; Jordan has an externalized self-model, not consciousness.


## Phase 7 — GitHub export UI strategy (future; preview-first, optional)

The future GitHub export UI (`MEMORY_REVIEW_UI_SPEC.md`, `MEMORY_UI_ROADMAP.md`
Stage 5) must be: **optional · advanced/power-user · preview-first · manual ·
scope-labelled · redaction-aware · never default · never automatic without
explicit user approval.**

**Exportable (preview-first):** memory snapshot markdown · architecture decision
log · assistant meta-memory changelog · project memory summary · session
summary · Claude Code prompt-history archive.

**Not exportable by default:** raw private chat logs · raw audio · API keys ·
provider secrets · unrelated project data · hidden device-local cache.

This is the UI layer over the disabled `GitHubMemoryExportService` (markdown-only
stub today). No export automation is implemented and **no code changes are made
in Phase 7** — this is UX direction only.
