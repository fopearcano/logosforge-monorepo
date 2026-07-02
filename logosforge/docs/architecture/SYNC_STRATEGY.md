# Sync Strategy

> Phase 1 — direction only. **Local-first is the default; cloud sync is
> future/pro.** No sync is implemented here. Cloud/infra ownership lives in
> future repos (per `CLAUDE.md`); this repo owns the durable contracts
> (schema, sync_state, conflict semantics).

## Tier hierarchy

**Local memory** — the default and the source of immediate UX:
- active working memory; fast offline access; immediate UX.
- SQLite (desktop) / Postgres (server) in MVP.

**Cloud account memory** *(future / pro)*:
- sync; multi-device continuation; shared project memory.
- canonical shared state for an account/workspace; permissions;
  embeddings/index updates.

**GitHub** *(optional, power-user)*:
- archive / export / versioning layer; **not** the default backend for all
  users; useful for developers, backups, markdown memory archives, Claude
  Code workflows, repository-linked projects (`GITHUB_EXPORT_STRATEGY.md`).

**Model providers** — replaceable reasoning/generation engines; never a sync
target for memory.

## Multi-device flow

**Device A:** edits project → talks to assistant → memory candidates
extracted → **local memory updates immediately** → cloud sync uploads
durable changes.

**Cloud:** stores account/project/workspace memory → keeps canonical shared
state → updates/searches embeddings → resolves sync state.

**Device B:** opens same account/project → downloads latest state →
rebuilds local cache → assistant continues with the **same** memory context.

## Conflict handling

- **Last-write-wins** only for safe, non-semantic fields (e.g. cosmetic
  tags, `updated_at`).
- **Semantic memory conflicts** require **contradiction detection**
  (`find_contradictions`, `MEMORY_OBJECT_SCHEMA.md`) — never a blind
  overwrite.
- **Supersede rather than silently delete** old decisions (`supersedes` /
  `contradicted_by`, `status = superseded`).
- **Keep audit / history** (`version`, event log).
- `sync_state` (`local_only` · `pending_sync` · `synced` · `conflict`)
  tracks each object; `conflict` blocks active use until reconciled.

## Defaults

Local-first everywhere; cloud sync **off** until accounts exist; GitHub
export **off** and opt-in. Nothing about sync is required for the desktop
Alpha to function offline.


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


## Phase 7 — Sync status in Memory Review (future; still disabled)

The future Memory Review UI (`MEMORY_REVIEW_UI_SPEC.md`, `MEMORY_UI_ROADMAP.md`
Stage 3) surfaces sync state as **read-only badges only** — `local_only` ·
`pending_sync` · `synced` · `conflict` (from each object's `sync_state`). A
`conflict` badge routes the user to **contradiction review** (supersede, never
blind overwrite).

Cloud sync remains **disabled until accounts exist**, and **opt-in /
permissioned** thereafter (respecting user/account/workspace permissions). No
sync is implemented and **no code changes are made in Phase 7** — this is UX
direction only.
