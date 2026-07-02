# Assistant Orchestration Layer (Assistant Engine)

> Phase 1 — direction only. The Alpha seeds this in `assistant.py`,
> `assistant_context_policy.py`, `context_assistant.py`, `memory_context.py`,
> `memory_manager.py`, `story_memory.py`. This document defines the target
> shape; it implements nothing.

The Assistant Engine is the orchestration layer between the user, LogosForge
memory, and the selected model backend. **It always uses LogosForge
memory/context tools before calling the model.**

## Components

- **prompt builder** — assembles the final prompt/context bundle.
- **context selector** — picks relevant document + memory.
- **memory retriever** — reads Project/User/Workspace/Assistant memory.
- **memory writer** — proposes/writes durable memory per policy.
- **contradiction checker** — detects conflicts before active writes.
- **model router** — selects the provider/model for the task.
- **tool caller** — executes LogosForge assistant tools.
- **provider capability selector** — matches task needs to provider
  capabilities (`MODEL_GATEWAY_SPEC.md`).
- **session summarizer** — produces session summaries.
- **memory candidate extractor** — turns events into proposed memory.
- **safety / privacy guard** — blocks secrets/raw-audio/out-of-scope leaks.
- **sync coordinator** — local/cloud/GitHub per settings (`SYNC_STRATEGY.md`).

## Request flow

1. User asks something.
2. LogosForge reads current document/editor state.
3. Retrieve relevant **Project Memory**.
4. Retrieve relevant **User Memory**.
5. Retrieve relevant **Assistant Meta-Memory**.
6. Retrieve applicable **assistant rules** (externalized self-model).
7. Check **provider capabilities**.
8. Build the **prompt/context bundle**.
9. The **selected model backend generates** the response.
10. LogosForge receives the response.
11. LogosForge **proposes/extracts memory candidates**.
12. LogosForge **updates local memory per policy** (no destructive writes;
    contradictions checked).
13. LogosForge **syncs** memory per settings.
14. **Optional GitHub export** happens only if enabled.

## Final target

A user opens LogosForge on any device (local or cloud). The assistant
retrieves: current document context · project memory · user memory ·
assistant meta-memory · relevant previous decisions · model/provider
capabilities. It answers through the **selected** model backend. After the
interaction, LogosForge decides what should become durable memory and syncs
it locally / cloud / GitHub depending on settings — the backend can be
swapped at any time without losing assistant memory.

## Roadmap (mirrors `MEMORY_ARCHITECTURE.md`)

- **Early MVP:** local-first memory; structured tables; optional vector
  store (pgvector/Chroma/Qdrant); local models via LM Studio/Ollama; cloud
  via gateway; candidate-extraction + retrieval **placeholders**; no
  destructive writes; no GitHub auto-commit.
- **SaaS/Pro:** accounts; cloud sync; project/workspace memory; permissions;
  shared memory; cloud index; optional GitHub export.
- **Team/Studio:** workspace memory; role-based permissions; shared project
  assistant; project-level assistant history; versioned memory; audit.

## Implementation phases (Claude Code)

1. Architecture docs (this set). 2. Minimal interfaces/stubs (provider
abstraction, schema, local store interface, context-builder interface,
retrieval + candidate-extraction placeholders; no destructive writes; no
GitHub auto-commit). 3. Local MVP. 4. Cloud sync. 5. Optional GitHub export
(manual push only). No runtime/assistant behavior changes in Phase 1–2.


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

**The "remember" loop is now concrete and deterministic** (`logosforge/memory_arch/candidates.py`, `review.py`) — still **no model call / no embeddings / no network**, and still **not wired into the running assistant**:

1. **Interaction event** → `process_event_for_memory_candidates(store, event)`.
2. **Extract** marked spans only (ordered marker heuristic; unmarked chat is discarded — no auto-save).
3. **Classify** type + scope + confidence (low/medium/high → 0.3 / 0.6 / 0.9) + status.
4. **Guard**: drop forbidden content; skip-with-warning when a project/user span lacks its required id (no mis-filing); honor Project↔Assistant separation.
5. **Contradiction-check** (heuristic, non-blocking) → warnings only.
6. **Write proposed/speculative** candidates — **never active**.
7. **Human review** via `MemoryCandidateReviewService` (approve / reject / edit / supersede / mark_speculative / mark_contradicted) — every transition explicit, reasoned, and **non-destructive**.

`summarize_session(session_id)` closes the loop with a deterministic, redaction-safe **proposed** `session_summary` at assistant scope. The Phase-2 `MemoryCandidateExtractor` placeholder in `context_builder.py` is intentionally **unchanged** (still returns `[]`); the real heuristic lives in the new `candidates.py` so the two never collide.

Tests: `tests/test_memory_candidate_workflow.py` (31). Dev demo: `scripts/memory_candidates_demo.py`.

**Still NOT implemented:** model-driven extraction/classification; semantic contradiction/retrieval; auto-approval; cloud sync; GitHub auto-export; memory-approval UI; any wiring into the running Alpha assistant/providers.

**Reaffirmed (Phase 4):** the model generates, LogosForge remembers, retrieves, structures, updates, and syncs; nothing becomes durable/active without explicit approval; GitHub is optional only; Project Memory and Assistant Meta-Memory stay separate; Jordan has an externalized self-model, not consciousness.


## Phase 5 — Context Builder Retrieval MVP

**Implemented now** (`logosforge/assistant_arch/context_builder.py`; `assistant_arch/tools.py` retrieval refined) — local-only, provider-agnostic, **no provider call / no memory write / no embeddings**:

- **Local scoped memory retrieval** from the `MemoryStore`, composed into **separate** sections — Project / User / Workspace / Assistant memory are never merged into one generic blob.
- **Assistant rules** retrieved as a focused sub-view (`assistant_rule` / `procedural_rule` / `workflow_rule`).
- **Provider capability inclusion** (size / tool-strategy hints) from the model gateway — capabilities are *not* memory and are never stored.
- **Deterministic selection/ranking** (keyword/tag/entity match, project match, active status, confidence, type/mode/entity signals; recency tiebreak) — no embeddings, no vector DB.
- **Character-budget placeholder** with safe per-item truncation at render time and over-budget exclusions (objects are never mutated).
- **Prompt-section serialization** (`to_prompt_sections` / `to_prompt_text` / `to_dict`) — every scope labeled; secrets / raw-audio paths redacted; archived statuses hidden unless diagnostic; no raw source events, no provider keys.
- Status policy: **active by default**; `include_proposed` / `review_mode` surface candidates; `diagnostic` surfaces archived **with labels**; every exclusion carries a reason (wrong project/user/workspace, deprecated, superseded, contradicted, not-active, over budget).
- A generic, **test-only `DocumentContext` adapter** carries current mode / section / excerpt / selected ids / active entities — no UI or active-editor code is touched (future wiring: `chat_context.py` / `assistant_context_policy.py`).

Tests: `tests/test_assistant_context_builder.py` (26).

**Still NOT implemented:** embeddings/vector retrieval; cloud sync; GitHub export automation; full UI memory review; active assistant-runtime integration; LLM-based extraction; full contradiction reasoning.

**Reaffirmed (Phase 5):** the model generates; LogosForge remembers and retrieves; **providers are not memory** (LM Studio / Ollama / vLLM / OpenAI / Anthropic / OpenRouter are generation backends only); Project Memory and Assistant Meta-Memory stay separate; Jordan is memory-grounded through LogosForge's externalized memory system, not conscious.


## Phase 6 — Passive Assistant Context Integration MVP

**Implemented now** (`logosforge/assistant_arch/passive_context.py`; opt-in seam in `logosforge/assistant.build_messages`; settings flags `assistant_memory_context_enabled` / `assistant_memory_context_diagnostics_enabled`, both **default-OFF**) — read-only, local-only, **no provider call / no memory write**:

- **Optional context-bundle injection** into the **shared** prompt builder (`build_messages`, used by Billy / Logos / inline). Gated by an explicit per-call param **and** the settings flag **and** an available memory store; when off, the prompt is byte-identical and the default path imports no memory packages.
- **Separate, labelled sections** — Project / User / Workspace / Assistant Meta-Memory, a focused **Assistant Rules** section, and a metadata-only **Provider Capabilities** section. Never one generic memory blob.
- **Safe fallback** — no store, missing `project_id`, or any builder/store failure → no block, assistant never blocked. Secrets / raw-audio / raw events never appear; archived + proposed/speculative excluded by default; diagnostic mode adds labelled warnings only.
- **No automatic memory writes** — `add_event` / `write_candidate` / `approve_candidate` / `update` / `supersede` / sync / GitHub are never called during prompt build. Candidate capture stays separate and explicit.
- Production note: no concrete store is wired yet — enabling the flag alone changes nothing until a store is registered (`register_memory_store`).

Tests: `tests/test_assistant_passive_context_integration.py` (22). No UI / provider / runtime files changed; Billy/Logos/Dexter behavior is unchanged when the flag is off.

**Still NOT implemented:** automatic durable memory writing; full memory approval UI; embeddings/vector retrieval; cloud sync; GitHub export automation; provider-specific memory; LLM-based memory extraction; full assistant-runtime replacement.

**Reaffirmed (Phase 6):** the model generates; LogosForge remembers and retrieves; **providers are replaceable backends, not memory**; Jordan is memory-grounded through LogosForge's externalized memory system — **not provider memory or model weights**.


## Phase 7 — Memory Review: the human gate (documentation only)

Memory Review is the **explicit human gate** on top of the orchestration's
"remember" loop: candidates proposed by `process_event_for_memory_candidates`
are reviewed (approve / reject / edit / supersede / mark) before any become
`active`. Specified — not implemented — in `MEMORY_REVIEW_UI_SPEC.md`,
`MEMORY_CANDIDATE_REVIEW_WORKFLOW.md`, `MEMORY_PRIVACY_AND_GOVERNANCE.md`, and
`MEMORY_UI_ROADMAP.md`.

The orchestrator still performs **no automatic durable writes**; the context
builder still feeds **approved `active` memory only** by default (proposed/
speculative only on request; archived only in diagnostic mode, labelled). **No
code changes in Phase 7.**


## Phase 8 — Memory Review implementation plan (planning only)

`MEMORY_REVIEW_UI_IMPLEMENTATION_PLAN.md` maps the human-gate review surface
onto the existing app (content-area route, `ui/safe_dialogs.py`, a default-off
settings flag, the review service/store) with a staged rollout (headless
service/view-model layer first). The orchestrator and context builder are
unchanged; approval stays explicit. **No code implemented in Phase 8.**


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
+ `MemoryWriterPolicy.decide`; `MemoryStatus.REVIEW_REQUIRED`; `MemoryObject`
policy metadata; `MemoryStore.save_active`; policy-routed
`process_event_for_memory_candidates`. The pipeline is not yet wired to live app
events — so the running Alpha still auto-saves nothing until a store + event
source are explicitly wired (a later step). Tests:
`tests/test_memory_policy_direction.py`.


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

The Assistant Engine's prompt builder is **section / writing-mode / action
aware** (`logosforge/assistant_contract.py`, wired in `ui/assistant_view.py`):

- **Direct manuscript-writing actions** (Generate / Dialogue / Rewrite / Expand
  / Continue / Tension) in the Manuscript/Scenes section produce **manuscript
  content in the project's mode format** — screenplay text in Screenplay, prose
  in Novel, panel script (Act → Page → Scene → Panel) in Graphic Novel,
  stage-script text in Stage Script. The system prompt is a strict mode-specific
  **output contract** that forbids markdown headings, outlines, "Suggested Scene
  Structure", "Production Notes", "Key Questions", `[INTRODUCING]`-style labels,
  analysis, and meta-commentary.
- For direct-writing actions the engine's **critique overlay** ("key questions",
  review checks) is suppressed from context (`NarrativeEngine.format_writing_block`),
  because it induced analysis/structure output during writing.
- **Planning sections** (Outline / Plot / Acts / Beats) and **analysis actions**
  (Suggest / Summarize / Diagnose / Next Beat / Alternatives) keep structured
  output; PSYKE produces codex content; Notes produces note content.
- A response **validator** flags structure/analysis leakage in direct-writing
  responses with a non-blocking ⚠ warning; output stays **preview-first**
  (Copy / Replace / Insert / Append are explicit; no auto-apply).

No provider/network/memory changes. Tests:
`tests/test_assistant_action_routing.py`; manual:
`docs/ASSISTANT_BEHAVIOR_MANUAL_TEST.md`.


## Assistant contract system (routing · validation · cache · apply)

Every Assistant request is classified by `assistant_contract.route(...)` into an
**AssistantTaskContract** = section × writing mode × action × target × user
request → `output_kind` (direct_content / structure / codex / notes / timeline /
analysis / suggestions / answer / transcript / clarification), `validator_profile`,
`apply_allowed`, and `cache_key`. **No provider request is built without a
contract.** Action + section + explicit instruction drive the output kind;
assistant mode/personality are modifiers only and never change it.

- **Validation enforced, not advisory** (`validate` → `AssistantValidationResult`):
  invalid direct output (planning/meta/markdown/context dumps) is **not shown as
  valid, not cached as valid, and Apply is disabled** (in `AssistantPanel._on_response`
  + the central `_get_response_text` guard) — for cached responses too. Secrets /
  raw-audio output is **withheld**; hidden-context labels (PSYKE / memory / AI
  Mode) are invalid in any profile. A strict-retry directive
  (`strict_retry_instruction`) is available for one re-ask on direct-content
  leakage.
- **Cache safety:** `cache_key(...)` is unique per entry-point / section / mode /
  action / target / instruction / selected-text and per output-contract +
  validator version, so a result is never replayed for a different request shape.
- **Apply safety:** Replace/Insert/Append enabled only for valid, apply-eligible
  output; Copy per `copy_allowed`; suggestions/analysis don't apply as manuscript
  by default; Outline applies valid structure through its own pipeline.

No provider/network/memory changes. Tests: `tests/test_assistant_routing_matrix.py`,
`tests/test_assistant_response_validation.py`, `tests/test_assistant_apply_safety.py`.
