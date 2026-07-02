# Memory UI — Roadmap (MVP → Pro → Team)

> **Phase 7 — roadmap specification. No UI is implemented by this document.**
> It stages the Memory Review experience from a local desktop MVP to a
> team/studio governance surface, and an optional GitHub export layer. Each
> stage builds only on capabilities the backend already supports or has a clear
> contract for (`MEMORY_REVIEW_UI_SPEC.md`, `SYNC_STRATEGY.md`,
> `GITHUB_EXPORT_STRATEGY.md`).

Principle: **the model generates; LogosForge remembers, retrieves, structures,
updates, and syncs.** The roadmap never compromises: explicit approval,
scope separation, local-first, providers-are-not-memory.

---

## Stage 1 — Local MVP (desktop, offline)

Backed entirely by the existing local store + review service.

- Local **Memory Review** page (behind a default-off `memory_review_ui_enabled`
  flag; dev/settings entry first).
- **Candidate queue** (proposed + speculative).
- **Approve / Reject / Edit** with reasons.
- **Simple filters** (scope / status / type / project) + search.
- **Local Markdown export** (`tools.export_memory_to_markdown`).
- **No cloud. No GitHub write. No vector-DB UI.**

## Stage 2 — Assistant-integrated MVP

Connects Memory Review to the live assistant (still local, still opt-in).

- Assistant panel shows **"memory candidates proposed"** (count badge).
- Explicit **Review** button → Memory Review.
- **Context-bundle diagnostics** (the Phase-6 `assistant_memory_context_diagnostics_enabled`
  view): what memory was included and why.
- **"Why did Jordan remember this?"** — source-event/session preview (redacted).
- **"Why was this memory used?"** — retrieval explanation (ranking signals from
  `AssistantContextBuilder`: match, scope, status, confidence, recency).

## Stage 3 — Pro / SaaS

Introduces accounts and multi-device (cloud ownership lives in future repos per
`CLAUDE.md`; this repo owns the durable contracts).

- **Account memory**, **cloud sync**, **multi-device continuation**.
- **Project / workspace memory** surfaced with ownership.
- **Permissions** model; **sync-conflict UI** (driven by `sync_state` +
  contradiction detection; `SYNC_STRATEGY.md`).
- **Cloud embedding / index status** (read-only badges; embeddings remain out of
  scope for the desktop MVP).

## Stage 4 — Team / Studio

Collaborative governance.

- **Workspace memory** with **role-based approvals**.
- **Shared project assistant**; **audit logs**; **versioned memory**.
- **Collaborator memory governance** (who proposed/approved/superseded what).

## Stage 5 — Optional GitHub export

A manual, preview-first mirror for power users (`GITHUB_EXPORT_STRATEGY.md`).

- **Markdown snapshots**; **architecture decision logs**; **assistant
  meta-memory changelog**; **project memory summaries**; **session summaries**;
  **Claude Code prompt-history archive**.
- **Manual push / commit only** — never automatic; preview-first; scope-labelled;
  redaction-aware.

---

## Cross-stage invariants

Across all stages: candidates never auto-activate; Project and Assistant memory
never mix; cloud sync is opt-in/permissioned; GitHub is optional/preview-first;
secrets/raw-audio are never stored or exported; superseded/contradicted memory
stays auditable and out of normal context; the user can always inspect what is
remembered; the memory UI never changes provider behavior.

**Reaffirmed:** the model generates; LogosForge remembers and retrieves;
providers are replaceable backends, not memory; Jordan is memory-grounded
through LogosForge's externalized memory, not conscious. **No implementation in
this document.**


## Phase 8 — Implementation plan for Stage 1

`MEMORY_REVIEW_UI_IMPLEMENTATION_PLAN.md` turns this roadmap into a concrete
plan: **Stage 1 = a headless `MemoryReviewService` + view models (no UI, tests
only)**, then a default-off content-area route (`memory_review_ui_enabled`),
editing/supersession, export preview, and assistant-panel integration — each
mapped to existing app patterns. **No code implemented in Phase 8.**


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
