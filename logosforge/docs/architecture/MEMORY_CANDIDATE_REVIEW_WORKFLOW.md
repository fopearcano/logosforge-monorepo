# Memory Candidate Review — Workflow

> **Phase 7 — specification only. No code is changed by this document.**
> It describes the end-to-end review workflow and the status state-machine that
> the future Memory Review UI (`MEMORY_REVIEW_UI_SPEC.md`) drives. Every step
> maps to the already-implemented backend (`memory_arch.candidates`,
> `memory_arch.review`, `memory_arch.store`).

Principle: **the model generates; LogosForge remembers.** Curated memory is
*extracted from events*, proposed for review, and only becomes durable/active
on **explicit user approval**. Raw chat is never auto-saved as fact.

---

## Status state-machine

```
                 (extract + classify, marked spans only)
   interaction ───────────────────────────────────────────▶ proposed
   event                                                   │  speculative
                                                           │
        ┌──────────────── review (explicit, human) ────────┘
        │
        ├─ approve ───────────────▶ active ──┐
        │                                     │ supersede(old,new,reason)
        ├─ reject(reason) ────────▶ rejected  ▼
        ├─ mark_speculative ──────▶ speculative   old ─▶ superseded  (kept, linked)
        ├─ mark_contradicted ─────▶ contradicted
        └─ edit(patch,reason) ────▶ (same status; content/scope revised)

   active ──(later)── deprecate / supersede / mark_contradicted ──▶ archived
```

Backed by `MemoryStatus` = `active · proposed · speculative · rejected ·
deprecated · superseded · contradicted`. **No status transition deletes the
object or its source event** — history is preserved (`version`, event log,
`memory_relations`).

Context-eligibility (enforced today by `AssistantContextBuilder`): only
`active` memory feeds normal assistant context. `proposed`/`speculative` appear
only with `include_proposed`/`review_mode`; archived statuses only in
`diagnostic` mode (labelled). Rejected/superseded/contradicted never pollute
normal context.

---

## Flow A — Candidate creation (no UI; already implemented)

1. User interacts with the assistant or edits the project.
2. An event is logged (`store.add_event`) **or** passed straight into the
   processor.
3. `candidates.process_event_for_memory_candidates(store, event)` extracts
   **only marked spans** (ordered marker heuristic) and classifies type/scope/
   confidence.
4. `MemoryWriterPolicy` validates: drops secrets/raw-audio/debug; enforces scope
   + required ids (Project↔Assistant separation); skip-with-warning when an id
   is missing.
5. Candidate is stored as **`proposed`** (or **`speculative`** for speculative
   ideas) — **never active**.
6. Candidate appears in **Memory Review → Review queue**.
7. Candidate is **not** used in normal assistant context yet.

## Flow B — Approval

1. User opens Memory Review.
2. User filters by scope / project / type / status.
3. User inspects the candidate card (content, source preview, badges,
   contradictions).
4. User **approves** (optionally **edits then approves**) →
   `review.approve(id)` (after any `review.edit(id, patch, reason)`).
5. Candidate → `active`; `version` bumped; `updated_at` set.
6. The context builder may retrieve it in **future** assistant calls (it is now
   eligible for normal context).

## Flow C — Rejection

1. User **rejects** → `review.reject(id, reason)` (reason required).
2. Status → `rejected` (or `deprecated` per policy).
3. The **source event remains** available for audit.
4. Rejected candidate is **excluded from normal context** and moved to the
   Archive view.

## Flow D — Supersession

1. A candidate conflicts with an older active memory (surfaced by
   `review.contradictions_for` / `tools.find_contradictions`).
2. The UI shows the contradiction side-by-side.
3. User **approves the new + supersedes the old** →
   `review.supersede(old_id, new_id, reason)`.
4. Old memory → `superseded`, retained and linked (`supersedes`,
   `memory_relations`) — **never silently deleted**; visible in history.
5. The context builder **excludes superseded memory by default**.

## Flow E — Diagnostic review

1. User enables **diagnostic mode** (`assistant_memory_context_diagnostics_enabled`
   today; a future UI toggle).
2. The UI may show `proposed` / `speculative` / `deprecated` / `superseded` /
   `contradicted` items.
3. All non-active items are **clearly labelled** with their status.
4. Diagnostic mode is **read-only** and **must not** cause accidental context
   pollution — viewing archived/candidate items never makes them eligible for
   normal assistant context.

---

## Contradiction handling (detail)

`memory_arch.contradictions` provides a deterministic, local heuristic
(keyword-overlap + opposing polarity; no LLM, no embeddings). It only
**surfaces** conflicts. Resolution is always an explicit human choice in Flow D
/ the contradiction-review action: keep both · approve new + supersede old ·
reject new · mark both needing-review · edit candidate · mark old deprecated.

## Invariants the workflow must preserve

- No candidate becomes `active` without **either** an explicit approval **or** a
  policy `AUTO_SAVE_ACTIVE` decision (safe, high-confidence, durable memory
  auto-saves; uncertain/sensitive/conflicting/scope-ambiguous memory is flagged
  for review, never silently activated).
- No durable write happens during context build/retrieval (read-only).
- Project Memory and Assistant Meta-Memory never mix.
- Secrets / raw audio / raw audio paths are never stored or shown.
- Superseded/rejected/contradicted memory stays auditable, never deleted.
- Cloud sync and GitHub export remain disabled/opt-in/preview-first.

---

**Reaffirmed:** the model generates; LogosForge remembers, retrieves,
structures, updates; approval is always explicit; Jordan is memory-grounded,
not conscious. **No implementation in this document.**


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
