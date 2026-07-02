# Memory Privacy & Governance

> **Phase 7 — governance specification. No code is changed by this document.**
> It states the privacy and governance rules the memory system and the future
> Memory Review UI must uphold. Most are **already enforced** in code today
> (`MemoryWriterPolicy`, `MemoryCandidateReviewService`, `AssistantContextBuilder`,
> the disabled sync/GitHub services); this doc makes them the explicit contract.

Principle: **the model generates; LogosForge remembers.** Memory is the user's,
held by LogosForge — never by a model provider — and the user is always in
control of what becomes durable.

---

## Governance rules

1. **No raw chat spam as durable fact.** Only explicitly *marked* spans become
   candidates; everything else is discarded. (`candidates.py` marker heuristic.)
2. **No raw audio storage.** Dexter works on transcripts; raw audio is never a
   memory object. (`MemoryWriterPolicy` forbidden patterns.)
3. **No API keys** stored or shown. (Forbidden-content guard + redaction.)
4. **No provider secrets** stored or shown.
5. **No private logs by default** — raw event logs are not durable memory and
   are shown only via a redacted source preview, opt-in.
6. **Policy-governed activation** — durable memory is governed by
   `MemoryWriterPolicy`: safe, high-confidence, durable, in-scope memory may
   **auto-save as active**; uncertain / sensitive / contradictory /
   scope-ambiguous memory becomes `review_required` / `proposed` / `speculative`
   and needs explicit `review.approve(...)`. **Nothing unsafe ever
   auto-activates**, and the user can always inspect / revoke / supersede.
7. **Scope clarity before activation** — a candidate's scope (and required
   `project_id`/`user_id`/`workspace_id`) must be unambiguous; ambiguous-scope
   candidates are flagged (`NEEDS_SCOPE_CONFIRMATION`) and cannot be silently
   misfiled.
8. **Project facts stay project-scoped** (`scope=project`).
9. **Assistant rules stay assistant-scoped** (`scope=assistant`).
10. **User preferences stay user-scoped** (`scope=user`).
11. **Workspace memories require a permission model** (future) before sharing.
12. **Contradictions must be visible** — surfaced, never hidden or auto-resolved.
13. **Superseded memories must not silently disappear** — retained, linked, and
    auditable (`supersedes`, `memory_relations`, `status=superseded`).
14. **Rejected candidates remain auditable** if policy allows (status →
    `rejected`; source event kept).
15. **GitHub export is explicit, preview-first, and optional** — never
    automatic. (`GITHUB_EXPORT_STRATEGY.md`.)
16. **Cloud sync respects user/account/workspace permissions** (future);
    disabled until accounts exist. (`SYNC_STRATEGY.md`.)
17. **Memory export supports redaction** — secrets / raw-audio / unrelated
    project data are stripped before any export or display.
18. **The user can always inspect what the assistant remembers** — Memory
    Review provides full visibility into active + candidate + archived memory,
    per scope.

## The two-memory-systems boundary (hard rule)

Project Memory (the *story* — characters, continuity, plot, codex) and
Assistant Meta-Memory (how *Jordan* works — rules, corrections, workflow) are
**distinct systems** and must never be mixed in storage, retrieval, the prompt,
the UI, or any export. This is enforced today by `MemoryWriterPolicy.validate_scope`
and by the separate `ContextBundle` sections.

## Sensitive-content handling

- The writer policy rejects obvious secrets (`sk-…`, `api_key:`…), raw-audio
  paths (`*.wav/.mp3/…`), and transient debug (`traceback`, `stack trace`)
  **before** any write.
- The Review UI shows a **sensitive-content warning** state and blocks approval
  until the user acknowledges, for anything that *looks* sensitive.
- All display/export passes content through redaction (`[redacted]`), so a
  secret that ever slipped in is never surfaced.

## Auditability

- `version`, `created_at`, `updated_at`, the event log, and `memory_relations`
  provide an append-only history. Edits require a reason; supersede/reject keep
  the prior object. **No destructive delete** exists in the MVP store contract.

## Data-residency posture

- **Local-first**: by default memory lives only on the user's device
  (`~/.logosforge/logosforge_memory.sqlite3`, git-ignored), created only when
  a store is explicitly instantiated.
- **Cloud** (future/pro) is opt-in and permissioned; **GitHub** (optional) is a
  preview-first manual mirror. Model providers are **never** a memory store.

---

**Reaffirmed:** the model generates; LogosForge remembers and retrieves;
providers are replaceable backends, not memory; the user controls durable
memory; Jordan is memory-grounded, not conscious. **No implementation here.**


## Direction Correction — Memory Review is optional & exception-based

> **This section supersedes any earlier wording implying every memory must be
> approved in this UI.**

The **default** memory experience is the automatic, policy-governed pipeline
(`MEMORY_ARCHITECTURE.md` → *Direction Correction*): safe, high-confidence,
durable memory **auto-saves as active**; only uncertain / sensitive /
contradictory / scope-ambiguous memory is flagged. **Memory Review is therefore
an optional audit / control / exception-resolution layer — not a mandatory gate
for every memory.**

The default Memory Review queue shows only: `review_required` · `proposed` ·
sensitive-flagged · contradictions · low-confidence · scope-ambiguous (and
`speculative` / recently auto-saved memory only when the user enables those
views). Ordinary safe auto-saved memory is **not** forced into review; it is
visible in an audit/active view. All other guarantees stand: explicit action for
any change; Project ↔ Assistant separation; secrets/raw-audio redacted; GitHub
preview-first/optional; cloud sync future/pro; no provider calls; auto-active
memory remains auditable, reversible, and supersedable.


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
