# Assistant Tools Spec

> Phase 1 — interface **direction** for LogosForge-internal assistant tools.
> These are **LogosForge tools, not provider-specific tools** — the model
> may *request* them, but LogosForge owns and executes them. No
> implementation here.

Conventions for every tool below: **purpose · inputs · outputs · scope
rules · safety rules · persistence rules · MVP behavior · future SaaS
behavior.**

---

### `search_memory(query, scope, project_id, filters)`
- **Purpose:** retrieve curated memory objects relevant to a query.
- **Inputs:** query text; `scope`; `project_id`; `filters` (type, status,
  tags, date).
- **Outputs:** ranked memory objects (active by default).
- **Scope:** never returns another project's/user's objects unless
  `visibility` permits; `assistant` scope excluded from creative output.
- **Safety:** read-only; no secrets returned.
- **Persistence:** none (read).
- **MVP:** keyword/structured filter over the local DB.
- **SaaS:** + cloud semantic index, permission-filtered.

### `retrieve_project_state(project_id)`
- **Purpose:** current Project Memory snapshot (structure + key facts).
- **Inputs:** `project_id`. **Outputs:** scenes/chapters/PSYKE/continuity
  summary. **Scope:** project only. **Safety:** read-only.
- **MVP:** read from project DB. **SaaS:** + synced project memory.

### `retrieve_user_preferences(task_type)`
- **Purpose:** user-scope preferences relevant to a task.
- **Inputs:** `task_type`. **Outputs:** preference objects. **Scope:** user.
- **Safety:** read-only; no secrets. **MVP:** local. **SaaS:** synced.

### `retrieve_assistant_rules(context)`
- **Purpose:** operating rules / known mistakes / corrections for the
  current context (the externalized self-model — `JORDAN_EXTERNALIZED_SELF_MODEL.md`).
- **Inputs:** `context`. **Outputs:** `assistant_rule` / `mistake_correction`
  / `workflow_rule` objects. **Scope:** assistant. **Safety:** read-only.

### `write_memory_candidate(content, type, scope, confidence, source)`
- **Purpose:** propose a durable memory (does not become active by itself).
- **Inputs:** content; `type`; `scope`; `confidence`; `source` event id.
- **Outputs:** candidate id with `status = proposed` (or `speculative`).
- **Scope:** defaults per `ASSISTANT_MEMORY_SPEC.md`. **Safety:** rejects
  secrets/raw-audio/debug; runs contradiction check.
- **Persistence:** writes a **proposed** object only. **MVP:** local table,
  manual approval. **SaaS:** + policy auto-approve for high-confidence ops.

### `approve_memory_candidate(memory_id)`
- **Purpose:** promote a candidate to `active`.
- **Safety:** re-runs contradiction detection; supersedes conflicts.
- **Persistence:** flips status to `active`, bumps `version`.

### `update_memory(memory_id, patch, reason)`
- **Purpose:** revise an object with an audit reason.
- **Persistence:** new `version`; `updated_at`; keeps history.

### `supersede_memory(old_id, new_id, reason)`
- **Purpose:** mark `old_id` `superseded` by `new_id` (never silent delete).
- **Persistence:** sets `supersedes`/`contradicted_by` + reason; old object
  retained for audit.

### `find_contradictions(topic, project_id)`
- **Purpose:** detect conflicting active memory on a topic.
- **Outputs:** conflicting object pairs. **Safety:** read-only; must run
  before any active write. **MVP:** heuristic/keyword. **SaaS:** semantic.

### `summarize_session(session_id)`
- **Purpose:** produce a `session_summary` candidate from an event-log
  session. **Persistence:** writes a **proposed** summary only.

### `export_memory_to_markdown(scope)`
- **Purpose:** human-readable export of a memory scope. **Safety:** strips
  secrets; labels scope. **Persistence:** none (returns/export only).

### `sync_memory_to_cloud()`
- **Purpose:** push/pull durable memory to the cloud account/workspace.
- **Scope:** respects permissions. **Safety:** no secrets; conflict →
  contradiction handling (`SYNC_STRATEGY.md`). **MVP:** no-op/disabled.
  **SaaS:** full sync.

### `optional_sync_memory_to_github()`
- **Purpose:** opt-in export/commit of memory snapshots to a repo.
- **Safety:** **explicit opt-in, manual push only, no secrets, no raw chat
  by default** (`GITHUB_EXPORT_STRATEGY.md`). **MVP:** disabled.

---

**Global tool rules:** read tools never persist; write tools only ever
create `proposed`/`speculative` unless policy explicitly auto-approves;
every active write is contradiction-checked; nothing writes secrets, raw
audio paths, or transient logs.


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


## Phase 4 — Memory Candidate Workflow MVP

**Tool surface extended** (`logosforge/assistant_arch/tools.py`, backed by `memory_arch/candidates.py` + `review.py`) — deterministic, local-only, **no model call / no network**:

- `process_event_for_memory_candidates(event, context)` — extract → classify → forbidden-check → scope-check → contradiction-check → write **proposed/speculative only**; returns `written` / `skipped` (with reasons) / `warnings`. Only *marked* spans become candidates.
- `list_memory_candidates(scope, project_id, status)` — the review queue (proposed + speculative by default).
- `reject_memory_candidate(memory_id, reason)` — status → `rejected` (kept for audit; **no delete**); reason required.
- `summarize_session(session_id)` — now **deterministic** (event counts + redacted excerpts); writes **one proposed** `session_summary` at assistant scope (previously a `not_implemented` placeholder).
- `find_contradictions(topic, project_id)` — now returns **candidate metadata** dicts (`{"kind", "reason", "memories": [...]}`) combining already-flagged `contradicted` rows with heuristic same-scope opposing-polarity pairs. Read-only.
- `log_event(...)` convenience — appends to the raw event log (history, **not** durable memory).
- The full review surface is available as `tools.review` (`MemoryCandidateReviewService`: approve / reject / edit / supersede / mark_speculative / mark_contradicted).

**Global tool rules (unchanged, now enforced in code):** read tools never persist; write tools only ever create `proposed`/`speculative`; activation/rejection/supersede are explicit and reasoned; secrets / raw audio / debug are dropped; Project Memory and Assistant Meta-Memory stay separate.

Tests: `tests/test_memory_candidate_workflow.py` (31). Dev demo: `scripts/memory_candidates_demo.py`.

**Still NOT implemented:** model-driven extraction/classification; semantic contradiction/retrieval; auto-approval; cloud sync; GitHub auto-export; memory-approval UI; any wiring into the running Alpha assistant/providers.

**Reaffirmed (Phase 4):** the model generates, LogosForge remembers, retrieves, structures, updates, and syncs; nothing becomes durable/active without explicit approval; GitHub is optional only; Project Memory and Assistant Meta-Memory stay separate; Jordan has an externalized self-model, not consciousness.


## Phase 5 — Context Builder Retrieval MVP

**Retrieval tools refined** (`logosforge/assistant_arch/tools.py`) and consumed by `AssistantContextBuilder` (`context_builder.py`) — local-only, **no provider call / no memory write**:

- `search_memory(query, scope, project_id, filters)` — local store; supports `type`/`status` filters.
- `retrieve_project_state(project_id)` — returns **active** project memory + a structure placeholder.
- `retrieve_user_preferences(task_type)` — **active** user `preference` / `model_preference` / `workflow_rule` / `procedural_rule`.
- `retrieve_assistant_rules(context)` — **active** assistant `assistant_rule` / `procedural_rule` / `workflow_rule` (the externalized self-model view).
- `AssistantContextBuilder.build_context(...)` composes the scoped `ContextBundle` (separate Project / User / Workspace / Assistant sections + assistant rules), deterministic ranking, character-budget placeholder, provider-capability inclusion, and `to_prompt_sections` / `to_prompt_text` / `to_dict` serialization (scope-labeled; secrets / raw-audio redacted).

Status policy: **active by default**; `include_proposed` surfaces candidates; every exclusion carries a reason. Tests: `tests/test_assistant_context_builder.py` (26).

**Still NOT implemented:** embeddings/vector retrieval; cloud sync; GitHub export automation; full UI memory review; active assistant-runtime integration; LLM-based extraction; full contradiction reasoning.

**Reaffirmed (Phase 5):** the model generates; LogosForge remembers and retrieves; **providers are not memory** (LM Studio / Ollama / vLLM / OpenAI / Anthropic / OpenRouter are generation backends only); Project Memory and Assistant Meta-Memory stay separate; Jordan is memory-grounded through LogosForge's externalized memory system, not conscious.


## Phase 6 — Passive Assistant Context Integration MVP

The **read** tools now have a passive consumer: `logosforge/assistant_arch/passive_context.py` composes a read-only ContextBundle and injects it into `assistant.build_messages` behind the **default-OFF** flag `assistant_memory_context_enabled`.

- Only **read** tools / retrieval are exercised (`search_memory`, `retrieve_project_state`, `retrieve_user_preferences`, `retrieve_assistant_rules` via the context builder). **No write tool** (`write_memory_candidate`, `approve_memory_candidate`, `update_memory`, `supersede_memory`, `summarize_session`) and **no** `sync_memory_to_cloud` / `optional_sync_memory_to_github` are called during prompt build — verified by test.
- Injected sections are labelled and separate (Project / User / Workspace / Assistant Meta-Memory + Assistant Rules + Provider Capabilities); archived + proposed/speculative excluded by default; secrets / raw-audio / raw events never appear.
- Global tool rules still hold: read tools never persist; durable writes stay explicit via the candidate workflow.

Tests: `tests/test_assistant_passive_context_integration.py` (22).

**Still NOT implemented:** automatic durable memory writing; full memory approval UI; embeddings/vector retrieval; cloud sync; GitHub export automation; provider-specific memory; LLM-based memory extraction; full assistant-runtime replacement.

**Reaffirmed (Phase 6):** the model generates; LogosForge remembers and retrieves; **providers are replaceable backends, not memory**; Jordan is memory-grounded through LogosForge's externalized memory system — **not provider memory or model weights**.


## Phase 7 — Memory Review actions → tools mapping (documentation only)

The future Memory Review UI is a **thin surface over the existing tools / review
service — no new backend doors** (`MEMORY_REVIEW_UI_SPEC.md`):

- queue / list → `list_memory_candidates` · `MemoryCandidateReviewService.list_candidates`
- approve → `approve_memory_candidate` · `review.approve`
- reject → `reject_memory_candidate` · `review.reject(reason)`
- edit → `update_memory` · `review.edit(patch, reason)` (status-change refused; scope re-validated)
- supersede → `supersede_memory` · `review.supersede(old, new, reason)`
- mark speculative / contradicted → `review.mark_speculative` · `review.mark_contradicted`
- contradictions → `find_contradictions` · `review.contradictions_for`
- search / filter → `search_memory` (type/status filters)
- export → `export_memory_to_markdown` ; source preview → `get_event` / `list_events` (redacted)
- sync / GitHub → `sync_memory_to_cloud` / `optional_sync_memory_to_github` (disabled / preview-first)

Global tool rules unchanged: read tools never persist; durable writes stay
explicit; no provider / cloud / GitHub calls. **No code changes in Phase 7.**


## Phase 8 — `MemoryReviewService` wraps these tools (plan only)

`MEMORY_REVIEW_UI_IMPLEMENTATION_PLAN.md` specifies a thin, UI-facing
`MemoryReviewService` (pure Python) that **composes the existing review service
+ tools** — approve / reject / edit / supersede / mark / list / search / export
/ source-preview — into serializable view models. It adds **no new backend
doors** and makes **no provider / cloud / GitHub calls**. **No code changes in
Phase 8.**


## Direction Correction — Automatic, policy-governed memory (supersedes the approval-first framing)

> **This section supersedes any earlier wording implying every memory needs
> manual approval.** Core principle unchanged: *the model generates; LogosForge
> remembers, retrieves, structures, updates, and syncs.*

**New principle:** *LogosForge remembers automatically when confidence and
policy allow it, and asks the user only when memory is uncertain, sensitive,
contradictory, or scope-ambiguous.*

The **default** is an automatic RAG/memory pipeline: 1) observe events →
2) extract candidates → 3) classify (scope/type/confidence/status/risk) →
4) **policy decision** → 5) durable write → 6) retrieval (active only) →
7) **optional, exception-based** review for flagged cases.

**Policy decisions** (`MemoryWriterPolicy.decide` → `PolicyDecision`):
`AUTO_SAVE_ACTIVE` · `SAVE_PROPOSED` · `SAVE_SPECULATIVE` · `REQUIRE_REVIEW` ·
`IGNORE` · `REJECT` · `FLAG_CONTRADICTION` · `FLAG_SENSITIVE` ·
`NEEDS_SCOPE_CONFIRMATION`.

- **Auto-save active** when ALL hold: high confidence; durable/safe type; clear
  scope; not sensitive; no contradiction; no secret/raw-audio; not speculative.
  Examples that may auto-save: an explicit stable user preference; a confirmed
  project / architecture / repo / workflow decision; a user correction of the
  assistant; a confirmed release-blocker rule; a confirmed model/backend
  preference; "desktop alpha first, cloud later"; "local Whisper buffering for
  desktop voice"; "Graphic Novel uses Act → Page → Scene → Panel"; "GitHub is
  optional export/archive, not the default backend".
- **Require review** when: low/medium confidence; sensitive-looking; possible
  secret/private path; contradiction with active memory; ambiguous scope;
  workspace/team memory; major assistant-identity/rule change; speculative-but-
  maybe; or a project fact appearing outside its project.
- **Speculative** for clear maybes/ideas; **ignore** transient mood/jokes/
  duplicates/noise; **reject** API keys/secrets/passwords/raw audio/raw paths.

Auto-active memory is **auditable** (`source_event`, `version`, `auto_saved`,
`policy_decision`, `risk_level`, `review_reason`), **reversible** (edit/reject),
and **supersedable** — and never holds secrets/raw-audio. **Memory Review is now
an optional, exception-based audit/control layer**, not a mandatory gate for
every item.

**Status model:** `active · proposed · review_required · speculative · rejected
· deprecated · superseded · contradicted`. Retrieval returns **active only** by
default (auto-saved + approved); `review_required`/`proposed`/`speculative`/
archived are excluded from normal context and shown only in review/diagnostic
mode.

**Unchanged:** Project Memory and Assistant Meta-Memory stay separate; providers
(LM Studio / Ollama / vLLM / OpenAI / Anthropic / OpenRouter) are generation
backends, **not memory**; GitHub is optional; cloud sync is future/pro;
local-first is default; raw chat spam is not durable memory; Jordan is
memory-grounded through LogosForge, **not conscious and not provider-bound**.

**Implemented now (still isolated; no provider/cloud/GitHub/UI):** `PolicyDecision`
+ `PolicyResult` + `MemoryWriterPolicy.evaluate`/`decide`;
`MemoryStatus.REVIEW_REQUIRED`; `MemoryObject` policy metadata (incl.
`sensitive_flags`); `MemoryStore.save_active`. **`write_memory_candidate` now
routes through the policy** — it may auto-save active, save proposed/
review_required/speculative, or reject — and `find_contradictions` includes
review-required memory. `process_event_for_memory_candidates` is likewise
policy-routed. The pipeline is not yet wired to live app events — the running
Alpha still auto-saves nothing until a store + event source are explicitly
wired. Tests: `tests/test_memory_policy_direction.py`,
`tests/test_automatic_memory_policy.py`.


## Controlled Passive Runtime Integration

**Implemented now** (`logosforge/assistant_arch/auto_memory.py`;
`AssistantTools.capture_interaction`; settings flags
`assistant_auto_memory_enabled` / `assistant_auto_memory_diagnostics_enabled`,
both **default-OFF**) — optional post-interaction memory processing, local-only,
**no provider / cloud / GitHub**:

- **Opt-in / default-off.** Disabled → a pure no-op; runtime behavior is exactly
  as before. Runs **after** a completed exchange — never before response
  generation, never blocking the reply.
- **Policy-governed.** A sanitized `EventLogEntry` (secrets / raw-audio /
  raw-audio paths redacted; capped excerpt; **no full transcript**) is logged,
  then `process_event_for_memory_candidates` applies the writer policy: safe
  high-confidence durable memory **auto-saves active**; uncertain / sensitive /
  contradictory / scope-ambiguous memory becomes `review_required` / `proposed`
  / `speculative`; secrets/raw-audio rejected; duplicates/noise ignored.
- **Fail-safe & local.** Missing/failed store → safe status, no crash. Uses the
  app-registered local store (`passive_context.register_memory_store`); none is
  wired in production, so enabling the flag alone is inert until a store is
  registered. **Never** calls a provider, cloud sync, or GitHub; never stores
  raw audio.
- **Scope-safe.** Project ↔ Assistant separation preserved; wrong-project memory
  is not written.
- **Safe diagnostics.** With the diagnostics flag, returns **counts only**
  (events_processed / candidates_extracted / auto_saved / review_required /
  proposed / speculative / ignored / rejected / contradiction) + redacted
  warnings — never secrets, raw chat, raw-audio paths, or provider keys.

**Feature flags (all default-off):** `assistant_memory_context_enabled`,
`assistant_auto_memory_enabled`, `assistant_auto_memory_diagnostics_enabled`.

Tests: `tests/test_assistant_auto_memory_runtime_integration.py`.

**Still NOT implemented:** Memory Review UI; cloud sync; GitHub export
automation; embeddings/vector DB; LLM-based extraction; team/workspace
permission model; full audit UI; and the live UI call-site wiring (the
capability is exposed via `AssistantTools.capture_interaction`, intentionally
not wired into UI workers — the running Alpha auto-saves nothing until a store +
call site are explicitly wired).


## Context-aware assistant output contracts (Assistant Behavior fix)

The assistant prompt builder is **section / writing-mode / action aware**
(`logosforge/assistant_contract.py`, wired in `ui/assistant_view.py`).
Direct manuscript-writing actions (Generate / Dialogue / Rewrite / Expand /
Continue / Tension) produce mode-formatted manuscript content via a strict
`output_contract(writing_mode, section, action)`; planning sections / analysis
actions keep structured output; PSYKE → codex; Notes → notes. For direct
writing, the engine's critique overlay is suppressed
(`NarrativeEngine.format_writing_block`). `validate_response(...)` flags
structure/analysis leakage (markdown headings, "Suggested Scene Structure",
"Production Notes", `[INTRODUCING]`, etc.) with a non-blocking warning; apply
stays explicit (preview-first). No provider/network/memory changes. Tests:
`tests/test_assistant_action_routing.py`.


## Assistant contract system (routing · validation · cache · apply)

`logosforge/assistant_contract.py` is the single source of truth for Assistant
behavior: `route(...)` → `AssistantTaskContract` (section × mode × action ×
target × request → output_kind / validator_profile / apply_allowed / cache key);
`validate(...)` → `AssistantValidationResult` (status / apply_allowed /
copy_allowed / cache_allowed / diagnostic_only / retry_recommended);
`cache_key(...)` (unique per request shape + contract/validator version);
`strict_retry_instruction(...)`. The panel enforces these: invalid output is not
shown/cached/applied (cached responses re-validated), secrets/raw-audio withheld,
hidden context never surfaced, modifiers can't change the output kind. No
provider/network/memory changes. Tests: `tests/test_assistant_routing_matrix.py`,
`tests/test_assistant_response_validation.py`, `tests/test_assistant_apply_safety.py`.
