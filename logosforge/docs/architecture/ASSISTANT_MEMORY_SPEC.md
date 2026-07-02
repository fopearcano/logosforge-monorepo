# Assistant Memory Spec

> Phase 1 — direction only. Defines the two memory systems, the memory
> scopes, and the **memory writer policy**. Implements nothing.

Core principle: **the model generates; LogosForge remembers, retrieves,
structures, updates, and syncs.** (`MEMORY_ARCHITECTURE.md`.)

## Two separate memory systems

LogosForge keeps **two** memory systems that must never be mixed.

### A. Project Memory — belongs to the writing project

The content and structure of one creative work. Examples:

- scenes, chapters, drafts, notes
- characters, locations
- codex / story bible (PSYKE)
- plotlines, continuity, themes
- screenplay structure
- graphic novel pages / panels
- series seasons / episodes

In the current Alpha this lives in the project database + PSYKE; it is the
canonical creative content.

### B. Assistant Meta-Memory — belongs to the collaboration layer

How the assistant has worked with this user / project. Examples:

- "user prefers a GitHub-first workflow"
- "desktop alpha first, cloud later"
- "local Whisper buffering for desktop voice"
- Claude Code prompts that worked or failed
- architecture decisions; repo structure
- known mistakes and their corrections
- model / backend preferences
- workflow rules
- assistant self-description and operating rules
- previous implementation choices
- release-blocker rules; deferred features
- repeated user corrections

### Hard separation rule

**Do not mix Project Memory and Assistant Meta-Memory.**

- Project facts must **not** be written into global user memory unless they
  are explicitly reusable across projects.
- Assistant workflow rules must **not** be stored as fiction/codex facts.
- A project fact defaults to **project** scope; a workflow rule defaults to
  **assistant** scope; a user preference defaults to **user** scope.

## Memory scopes

1. **Personal / User Memory** — follows the user across projects and devices.
2. **Project Memory** — belongs to one writing project.
3. **Workspace / Team Memory** — shared across collaborators or a writing
   room.
4. **Assistant Meta-Memory** — how the assistant has worked with the
   user/project.
5. **Device-local Cache** — fast offline access and local-first UX.

(The canonical `scope` enum is in `MEMORY_OBJECT_SCHEMA.md`:
`user | project | workspace | assistant | device`.)

## Memory writer policy

The assistant **does not save everything automatically as fact.** Durable
writes follow this policy.

### Save (candidates for durable memory)

- stable preferences
- project decisions
- technical constraints
- user corrections
- reusable workflows
- long-term project facts
- assistant mistakes and corrections
- repo / architecture decisions
- release rules
- mode-specific structural decisions
- model / backend preferences
- durable workflow decisions

### Do not blindly save

- temporary moods
- random chat fragments
- speculative ideas **as facts** (store them with `status = speculative`)
- outdated implementation assumptions
- project facts into the wrong project namespace
- one-off phrasing unless explicitly requested
- private/sensitive material without explicit reason and scope
- cloud/API secrets
- raw audio paths
- transient debug logs

### Rules

1. Memory candidates are usually **proposed before** becoming durable.
2. High-confidence operational facts may be saved automatically **only if
   policy allows** it.
3. Project facts default to **project** scope.
4. User preferences default to **user** scope.
5. Assistant operating rules default to **assistant** scope.
6. Device-only facts default to **device** scope.
7. **Contradictions must be detected before writing active memory.**
8. Superseded memory **remains available** for audit/history — it is marked
   `superseded`, never silently deleted.

## Retrieval expectation

Before calling the model, the Assistant Engine retrieves, in order: current
document/editor state → relevant Project Memory → relevant User Memory →
relevant Assistant Meta-Memory → applicable assistant rules
(`ASSISTANT_ORCHESTRATION_LAYER.md`). The assistant uses LogosForge
memory/context tools (`ASSISTANT_TOOLS_SPEC.md`) **before** the model call,
never instead of LogosForge memory.


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

**Implemented now** (`logosforge/memory_arch/candidates.py`, `review.py`; `contradictions.py` upgraded to a heuristic; `assistant_arch/tools.py` extended) — deterministic, local-only, **no model call / no embeddings / no network**:

- **Extract → classify → propose.** `extract_candidates(...)` and `process_event_for_memory_candidates(store, event)` turn an interaction event into candidates via an ordered **marker** heuristic (correction → release_blocker → architecture → deferred → workflow → project_decision → preference → speculative). Only *marked* spans become candidates — **raw chat is never auto-saved as fact**; per-event and per-candidate caps add anti-spam guards.
- **Candidates (Phase 4).** Every write was `proposed`/`speculative`; **superseded by the Direction Correction** — policy now auto-saves safe, high-confidence, durable memory as active and flags only the uncertain/sensitive/conflicting cases. Confidence is tiered low/medium/high → 0.3 / 0.6 / 0.9.
- **Scope integrity.** Project-scope spans without a `project_id` (and user-scope spans without a `user_id`) are **skipped with a warning**, never mis-filed; Project Memory and Assistant Meta-Memory stay separate.
- **Safety.** Secrets / raw-audio / debug spans are dropped by the writer policy before any write; the session summary redacts forbidden excerpts.
- **Review service** (`MemoryCandidateReviewService`): `list_candidates` / `get` / `approve` / `reject` / `edit` / `supersede` / `mark_speculative` / `mark_contradicted`. **No destructive delete** — `reject` (new `MemoryStatus.REJECTED`) and `supersede` preserve the object for audit; transitions require a reason; `edit` refuses to change status.
- **Deterministic `summarize_session(session_id)`** — event counts + redacted excerpts → **one proposed** `session_summary` candidate at **assistant** scope (no model).
- **Heuristic contradiction surface** — `contradicts()` / `pairwise_contradictions()` flag same-scope statements with high keyword overlap + opposing polarity; surfaced as warnings/metadata only, **never auto-superseded**.

Tests: `tests/test_memory_candidate_workflow.py` (31). Dev demo: `scripts/memory_candidates_demo.py`.

**Still NOT implemented:** model-driven extraction/classification; semantic (embedding) contradiction or retrieval; auto-approval; cloud sync; GitHub auto-export; memory-approval UI; any wiring into the running Alpha assistant/providers.

**Reaffirmed (Phase 4):** the model generates, LogosForge remembers, retrieves, structures, updates, and syncs; nothing becomes durable/active without explicit approval; GitHub is optional only; Project Memory and Assistant Meta-Memory stay separate; Jordan has an externalized self-model, not consciousness.


## Phase 5 — Context Builder Retrieval MVP

**Implemented now** (`logosforge/assistant_arch/context_builder.py`; `assistant_arch/tools.py` retrieval refined) — local-only, provider-agnostic, **no provider call / no memory write / no embeddings**:

- **Local scoped memory retrieval** from the `MemoryStore`, composed into **separate** sections — Project / User / Workspace / Assistant memory are never merged into one generic blob.
- **Assistant rules** retrieved as a focused sub-view (`assistant_rule` / `procedural_rule` / `workflow_rule`); `tools.retrieve_user_preferences` / `retrieve_assistant_rules` now return **active** memory of the relevant types by default.
- **Provider capability inclusion** (size / tool-strategy hints) — capabilities are *not* memory and are never stored.
- **Deterministic selection/ranking** (keyword/tag/entity match, project match, active status, confidence, type/mode/entity signals; recency tiebreak) — no embeddings, no vector DB.
- **Character-budget placeholder** with safe truncation and over-budget exclusions (objects never mutated).
- **Prompt-section serialization** — every scope labeled; secrets / raw-audio paths redacted; archived statuses hidden unless diagnostic; no raw source events, no provider keys.
- Status policy: **active by default**; `include_proposed` / `review_mode` surface candidates; `diagnostic` surfaces archived **with labels**; every exclusion carries a reason.

Tests: `tests/test_assistant_context_builder.py` (26).

**Still NOT implemented:** embeddings/vector retrieval; cloud sync; GitHub export automation; full UI memory review; active assistant-runtime integration; LLM-based extraction; full contradiction reasoning.

**Reaffirmed (Phase 5):** the model generates; LogosForge remembers and retrieves; **providers are not memory** (LM Studio / Ollama / vLLM / OpenAI / Anthropic / OpenRouter are generation backends only); Project Memory and Assistant Meta-Memory stay separate; Jordan is memory-grounded through LogosForge's externalized memory system, not conscious.


## Phase 6 — Passive Assistant Context Integration MVP

**Implemented now** (`logosforge/assistant_arch/passive_context.py`; opt-in seam in `logosforge/assistant.build_messages`; settings flags `assistant_memory_context_enabled` / `assistant_memory_context_diagnostics_enabled`, both **default-OFF**) — read-only, local-only, **no provider call / no memory write**:

- **Optional context-bundle injection** into the shared prompt builder; gated by an explicit per-call param **and** the settings flag **and** an available memory store. Off → byte-identical prompt; default path imports no memory packages.
- **Separate, labelled sections** — Project / User / Workspace / Assistant Meta-Memory + a focused **Assistant Rules** section + a metadata-only **Provider Capabilities** section. Memory is never merged into one blob; this honors the spec's two-memory-systems separation at the prompt layer.
- **Reads only** — uses `AssistantContextBuilder` retrieval; the memory-writer policy and candidate workflow are untouched. No durable write happens during prompt build.
- **Safe fallback** — no store / missing project_id / failure → no block; secrets / raw-audio / raw events never appear; archived + proposed/speculative excluded by default; diagnostics add labelled warnings only.

Tests: `tests/test_assistant_passive_context_integration.py` (22). Billy/Logos/Dexter behavior is unchanged when the flag is off.

**Still NOT implemented:** automatic durable memory writing; full memory approval UI; embeddings/vector retrieval; cloud sync; GitHub export automation; provider-specific memory; LLM-based memory extraction; full assistant-runtime replacement.

**Reaffirmed (Phase 6):** the model generates; LogosForge remembers and retrieves; **providers are replaceable backends, not memory**; Jordan is memory-grounded through LogosForge's externalized memory system — **not provider memory or model weights**.


## Phase 7 — Memory Review (UI/UX spec; documentation only)

The future user-facing review surface is **specified, not implemented**, in:

- `MEMORY_REVIEW_UI_SPEC.md` — the Memory Review UI surface, scopes/tabs, candidate card, actions, states, acceptance criteria, and test plan.
- `MEMORY_CANDIDATE_REVIEW_WORKFLOW.md` — the review flows (create / approve / reject / supersede / diagnostic) and the status state-machine.
- `MEMORY_PRIVACY_AND_GOVERNANCE.md` — the 18 governance rules (two-memory-systems boundary, redaction, auditability, local-first).
- `MEMORY_UI_ROADMAP.md` — MVP → Pro → Team → optional GitHub-export stages.

These reaffirm this spec's **two memory systems**: Project Memory and Assistant Meta-Memory stay separate in storage, retrieval, prompt, UI, and export. (Activation policy: see the Direction Correction — safe memory auto-saves, review is the exception.) **No UI/code is implemented in Phase 7.**


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
+ the rich `PolicyResult` + `MemoryWriterPolicy.evaluate(candidate, existing)`
(decision · reason · confidence · risk_level · requires_review · auto_saved ·
sensitive_flags · contradiction_ids · suggested_status), with `decide()` kept as
a thin wrapper; `MemoryStatus.REVIEW_REQUIRED`; `MemoryObject` policy metadata
(incl. `sensitive_flags`); `MemoryStore.save_active`; policy-routed
`process_event_for_memory_candidates` **and** `AssistantTools.write_memory_candidate`
(safe high-confidence durable memory auto-saves active; the rest is flagged).
The pipeline is not yet wired to live app events — so the running Alpha still
auto-saves nothing until a store + event source are explicitly wired (a later
step). Tests: `tests/test_memory_policy_direction.py`,
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
