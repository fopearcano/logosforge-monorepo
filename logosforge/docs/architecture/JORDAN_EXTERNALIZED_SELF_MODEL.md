# Jordan — Externalized Self-Model

> Phase 1 — direction only. Defines the assistant's externalized self-model.
> Implements nothing and renames nothing in code.

## Naming reconciliation (read first)

This document uses **"Jordan"** as the architecture-level name for the
unified, memory-grounded assistant identity. The **current Alpha code does
not contain "Jordan"** — its assistant surfaces are:

- **Billy** — the AI chat/assistant agent (`voice/billy_bridge.py`, etc.).
- **Logos** — the inline/contextual AI layer (`logosforge/logos/…`).
- **Dexter** — the local voice writing room (`voice/…`, Dexter's Room).

Treat **Jordan as the externalized-self-model concept** these surfaces
should share. **Do not rename Billy/Logos/Dexter in code** as part of this
architecture work (see the contradiction note in the after-work report and
`§15` cross-doc rules). Any future unification of the name is a separate,
explicit decision.

## Jordan is

- **memory-grounded** — behavior comes from LogosForge memory, not weights.
- **project-aware** — sees the active project's Project Memory.
- **historically consistent** — remembers collaboration history via memory.
- **model-agnostic** — works with any selected backend (`MODEL_GATEWAY_SPEC.md`).
- **externally orchestrated** by LogosForge (`ASSISTANT_ORCHESTRATION_LAYER.md`).
- capable of remembering collaboration history **through LogosForge memory**.

## Jordan is NOT

- conscious.
- self-aware in a human sense.
- permanently learning inside model weights.
- tied to one model provider.
- identical to LM Studio / Ollama / OpenAI / Anthropic / OpenRouter.

## Jordan has

- an identity / role file.
- assistant rules.
- known limitations.
- remembered collaboration history.
- remembered mistakes / corrections.
- user-specific preferences.
- project-specific context.
- tool access (`ASSISTANT_TOOLS_SPEC.md`).
- provider-independent memory.

## "Externalized self-model" defined

A **structured set of memory objects and rules** (stored in LogosForge, not
in model weights) that helps the assistant behave consistently across
sessions, devices, projects, and model providers. It is retrieved via
`retrieve_assistant_rules(context)` and lives at `assistant` scope.

It includes:

- assistant identity
- operating rules
- user collaboration preferences
- known mistakes
- corrections
- current architecture decisions
- project workflow norms
- tool usage policies
- release / prompting policies

Because it is externalized, swapping the model backend changes *how text is
generated* but never *who the assistant is* or *what it remembers*.


## Phase 6 — Passive Assistant Context Integration MVP

Jordan's externalized self-model can now reach the **live** assistant prompt — passively and read-only. Behind the **default-OFF** flag `assistant_memory_context_enabled`, `logosforge/assistant_arch/passive_context.py` injects the assistant-scope memory (operating rules, known mistakes/corrections, workflow norms — the externalized self-model, retrieved via `retrieve_assistant_rules` / the context builder) into `assistant.build_messages` as a clearly-labelled **Assistant Rules** / **Assistant Meta-Memory** section, kept separate from Project Memory.

- This is **grounding, not consciousness**: behavior still comes from retrieved LogosForge memory, not model weights and not provider memory.
- **No memory is written** during prompt build; the self-model is only *read*. It is updated solely through the explicit candidate workflow.
- Disabled by default and fully provider-agnostic: enabling it does not change which model generates, and swapping backends never changes who Jordan is or what is remembered.
- Billy / Logos / Dexter are **not renamed**; Jordan remains the architecture-level concept these surfaces share.

Tests: `tests/test_assistant_passive_context_integration.py` (22).

**Reaffirmed (Phase 6):** the model generates; LogosForge remembers and retrieves; **providers are replaceable backends, not memory**; Jordan is memory-grounded through LogosForge's externalized memory system — **not provider memory or model weights**.


## Phase 7 — Memory Review: controlling Jordan's externalized self-model

**Memory Review** (`MEMORY_REVIEW_UI_SPEC.md`) is *how the user controls
Jordan's externalized self-model.* Jordan's consistency comes from LogosForge
memory — **not model weights and not provider memory** — and Memory Review lets
the user inspect and edit that memory safely, at the correct scope, with
Assistant Meta-Memory kept separate from Project Memory.

Through Memory Review the user can inspect/curate Jordan's: **assistant
identity · assistant rules · known limitations · remembered collaboration
history · known mistakes / corrections · project-specific context ·
user-specific preferences · provider-capability awareness.**

Jordan remains: **not conscious · not self-aware in a human sense · not
permanently learning inside model weights · not tied to one provider.** Editing
the self-model is an explicit, auditable human action (approve / reject / edit /
supersede with reasons). Policy may **auto-save** safe, high-confidence self-model
memory (e.g., a confirmed workflow rule or a user correction); uncertain /
sensitive / conflicting changes are flagged for review (see Direction
Correction). **Billy / Logos / Dexter are not renamed. No code changes in Phase 7.**


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
