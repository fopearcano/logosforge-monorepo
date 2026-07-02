# Memory Review — UI / Product Spec

> **Phase 7 — specification only. No UI is implemented by this document.**
> It defines the *future* user-facing workflow for reviewing memory candidates
> and inspecting durable memory. It maps every UI affordance to the **existing,
> tested backend** so implementation later is a wiring exercise, not a redesign.

Core principle (unchanged): **the model generates; LogosForge remembers,
retrieves, structures, updates, and syncs.** Memory becomes active
**automatically when confidence and policy allow it** (see
`MEMORY_ARCHITECTURE.md` → *Direction Correction*); Memory Review is the
**optional, exception-based** layer where the user audits auto-saved memory and
resolves the cases the policy flags (uncertain / sensitive / contradictory /
scope-ambiguous). It is **not** a gate on every memory.

---

## 1. Product name

**Working / recommended Alpha label: `Memory Review`.**

Alternative labels (documented; not chosen): *Assistant Memory Review*,
*Jordan Memory Review*, *Memory Inbox*, *Memory Candidates*, *Memory Control
Room*. Rationale for "Memory Review": neutral, action-oriented, scope-agnostic
(works for User / Project / Workspace / Assistant memory), and does not imply
the assistant is conscious or that providers own memory.

## 2. Purpose

A place where the user can **inspect and curate what LogosForge remembers** —
audit auto-saved memory and review the flagged exceptions (proposed /
review-required / sensitive / contradictions), then correct, revoke, or
supersede anything. It is an **optional audit & control layer** over the
automatic memory-writer pipeline, **not a mandatory gate**.

## 3. Backend grounding (this spec is not inventing a new model)

The UI is a thin, read/curate surface over already-implemented code:

| UI concept | Backend (already exists) |
|---|---|
| Candidate queue / lists | `MemoryCandidateReviewService.list_candidates(scope, project_id, status)` ; `AssistantTools.list_memory_candidates(...)` |
| A memory item | `memory_arch.schema.MemoryObject` (id, scope, type, content, confidence, status, source_event, project_id/user_id/workspace_id, created_at/updated_at, supersedes, contradicted_by, tags, entities, visibility, sync_state, version) |
| Status set | `MemoryStatus` = `active` · `proposed` · `speculative` · `rejected` · `deprecated` · `superseded` · `contradicted` |
| Scope set | `MemoryScope` = `user` · `project` · `workspace` · `assistant` · `device` |
| Approve | `review.approve(id)` → `active` |
| Reject | `review.reject(id, reason)` → `rejected` (kept, not deleted) |
| Edit | `review.edit(id, patch, reason)` (refuses status changes; scope re-validated) |
| Supersede | `review.supersede(old_id, new_id, reason)` (old → `superseded`, linked) |
| Mark speculative / contradicted | `review.mark_speculative(id, reason)` / `review.mark_contradicted(id, reason, contradicted_by)` |
| Contradiction surface | `review.contradictions_for(id)` ; `tools.find_contradictions(topic, project_id)` (metadata) |
| Search / filter | `store.search(query, scope, project_id, filters={"type","status"})` |
| Markdown export | `tools.export_memory_to_markdown(scope, project_id)` |
| Source preview | `store.get_event(source_event)` / `store.list_events(session_id)` (redacted) |
| Sync / GitHub status | `MemorySyncService` (disabled) ; `GitHubMemoryExportService` (disabled, preview-only) |

The UI must **not** add side doors around these — all reads/writes go through
this service/tool layer, behind the existing `assistant_memory_context_*`
flags and (future) a `memory_review_ui_enabled` flag.

## 4. Required UI surface (capabilities)

The Memory Review surface must support: (1) candidate queue; (2) active
memories; (3) proposed; (4) speculative; (5) rejected; (6) superseded; (7)
contradicted; (8) scope filters; (9) type filters; (10) project filters; (11)
confidence filters; (12) search; (13) source-event preview (redacted); (14)
approval; (15) rejection; (16) edit-before-approval; (17) supersede; (18)
contradiction review; (19) markdown export; (20) local-only mode; (21) future
cloud-sync status (read-only badge); (22) future optional GitHub export
**preview** (no write).

Status grouping for lists:
- **Review queue** = `proposed` + `speculative` (the default landing view).
- **Active** = `active` (what the assistant actually uses).
- **Archive** = `rejected` + `deprecated` + `superseded` + `contradicted`
  (auditable history; never silently deleted).

## 5. Memory scopes in the UI (kept strictly separate)

Five tabs/sections — **Project Memory and Assistant Meta-Memory must never be
visually or functionally mixed**:

1. **User Memory** (`scope=user`) — follows the user across projects/devices:
   preferences, model/backend preferences, workflow habits, durable personal
   rules. (`preference`, `model_preference`, user-level `workflow_rule` /
   `procedural_rule`.)
2. **Project Memory** (`scope=project`, requires `project_id`) — belongs to one
   writing project: characters, scenes, continuity, plot decisions, themes,
   story-bible/codex facts, screenplay/graphic-novel/series structure.
   (`character_fact`, `continuity_fact`, `project_decision`, `session_summary`,
   project-specific `architecture_decision` / `release_blocker_rule`,
   `limitation`, `deferred_feature`.)
3. **Workspace / Team Memory** (`scope=workspace`, requires `workspace_id`) —
   shared across collaborators: project-room decisions, team rules; **gated by a
   future permission model**.
4. **Assistant Meta-Memory** (`scope=assistant`) — how Jordan works with the
   user: assistant rules, architecture decisions, prompt rules, known mistakes,
   corrections, release-blocker rules, repo/workflow decisions. (The
   externalized self-model — `JORDAN_EXTERNALIZED_SELF_MODEL.md`.)
5. **Device-local Cache** (`scope=device` / `sync_state`) — offline cache + sync
   status; **not necessarily canonical durable memory**.

Cross-scope leakage is forbidden: a Project tab never shows assistant rules; an
Assistant tab never shows project fiction facts (enforced today by
`MemoryWriterPolicy.validate_scope` + `ContextBundle`'s separate sections).

## 6. Candidate card design

Each candidate/memory card shows (all sourced from `MemoryObject`):

- **content summary** (1–2 lines) with **full content expandable**;
- **scope**, **type**, **status**, **confidence** (with a visual tier:
  low ≤ 0.3 / medium ≈ 0.6 / high ≥ 0.9);
- **source event/session** (link → redacted preview), **project_id / project
  name** if available, **user_id** / **workspace_id** if relevant;
- **created_at**, **updated_at**, **version**;
- **tags**, **entities**;
- **possible contradictions** (from `contradictions_for`), **possible
  supersedes** (heuristic suggestion);
- **warning badges:** `speculative` · `low confidence` · `possible duplicate` ·
  `possible contradiction` · `scope uncertain` · `contains sensitive-looking
  content` · `requires approval`;
- **actions:** Approve · Reject · Edit · Mark speculative · Supersede existing ·
  View source · Export · Copy markdown.

The card must **never** expose: API keys, provider secrets, raw audio, raw
audio paths, hidden private logs (by default), or unrelated project data.
Content is rendered through the same redaction used by
`ContextBundle.to_prompt_sections` (forbidden content → `[redacted]`).

## 7. Candidate actions (behavior → backend)

- **Approve** → `review.approve(id)`: candidate → `active`; **requires explicit
  user action**; logs reviewer/reason if available; may update local
  `sync_state`; **does not call any model**.
- **Reject** → `review.reject(id, reason)`: → `rejected` (or `deprecated` per
  policy); **does not delete the source event**; keeps audit/history; reason
  required.
- **Edit** → `review.edit(id, patch, reason)`: edit content/scope/type/tags/
  confidence; **requires a reason**; **re-validates scope** before save (never
  silently turns Project Memory into User Memory); **status transitions are not
  allowed via edit** (use Approve/Reject/Mark).
- **Supersede** → `review.supersede(old_id, new_id, reason)`: user picks the old
  memory; old → `superseded` (kept + linked via `supersedes`); new →
  `active`/`proposed` per approval.
- **Contradiction review** → `review.contradictions_for(id)`: shows candidate +
  conflicting memory; user may **keep both**, **approve new + supersede old**,
  **reject new**, **mark both as needing review**, **edit candidate**, or **mark
  old deprecated/superseded**. Nothing is auto-applied.
- **Mark speculative** → `review.mark_speculative(id, reason)`: stays visible;
  **excluded from normal assistant context by default**; available in
  brainstorm/review mode later.
- **View source** → `store.get_event(...)` / `list_events(...)`: shows a
  **redacted/safe** session/event summary; never raw logs unless explicitly
  allowed by policy.
- **Export** → `tools.export_memory_to_markdown(...)`: exports the selected/
  filtered set to Markdown; **GitHub export stays optional + preview-first**
  (`GITHUB_EXPORT_STRATEGY.md`).

## 8. Entry points (future; none added now)

Recommended future entry points: (1) Settings → Assistant Memory; (2) Jordan/
Billy assistant panel → Memory Review; (3) Project sidebar → Project Memory;
(4) PSYKE/Codex → Project Memory link; (5) Dexter's Room → review
voice-*transcript*-derived candidates (text only, never raw audio);
(6) Developer/Advanced → Assistant Meta-Memory; (7) Cloud account settings →
Sync status; (8) Optional GitHub export → preview.

**MVP recommendation:** start with a single **hidden/dev or settings-based**
Memory Review page behind a `memory_review_ui_enabled` flag (default off) before
any main-navigation exposure. **Do not add UI now.**

## 9. UI states (must be handled)

1. **Empty** — no candidates yet. 2. **Local-only** — stored only on this
device. 3. **Sync-disabled** — cloud sync off. 4. **Sync-pending** — future
upload queued. 5. **Conflict** — candidate contradicts active memory.
6. **Scope-warning** — candidate may belong to another scope. 7. **Sensitive-
content-warning** — possible secret/private content (block approve until
acknowledged). 8. **Review-required** — cannot become active without approval.
9. **Offline** — local available, cloud unavailable. 10. **Diagnostic** — shows
excluded/superseded/deprecated/contradicted items, clearly labelled, and **must
not** cause accidental context pollution (diagnostic view is read-only and never
feeds normal assistant context).

## 10. Future implementation — acceptance criteria

**Must PASS:** (1) candidate queue visible; (2) filter by scope/status/type/
project; (3) Project/User/Assistant/Workspace visually separated; (4) explicit
approve; (5) explicit reject; (6) edit-before-approval; (7) supersede; (8)
contradictions visible; (9) superseded remains auditable; (10) rejected excluded
from normal context; (11) proposed/speculative excluded from normal context by
default; (12) GitHub export preview-first + optional; (13) cloud sync disabled
unless explicitly enabled; (14) no secrets/raw-audio/paths shown or exported;
(15) context builder uses approved **active** memory only by default; (16)
existing assistant behavior stays safe when the memory UI is disabled.

**Must FAIL (regressions):** (1) a candidate becomes active without approval;
(2) Project and Assistant memory mixed; (3) GitHub export commits automatically;
(4) cloud sync without opt-in; (5) secrets/raw-audio stored or exported;
(6) superseded/contradicted memory pollutes normal context; (7) the user cannot
inspect what Jordan remembers; (8) the memory UI changes provider behavior.

## 11. Future UI test plan (documented; not implemented now)

Candidate list loads · empty state · scope filter · type filter · status filter
· project filter · approve · reject · edit · supersede · contradiction warning ·
source preview (redacted) · markdown export · **no GitHub write by default** ·
**no cloud sync by default** · secrets redacted · raw-audio path redacted ·
proposed/speculative excluded from normal context · active included in context ·
wrong-project excluded · assistant meta-memory not shown as project fiction ·
project memory not shown as assistant rule · offline/local state · diagnostic
state · **no provider calls**. (Mirrors the already-passing backend tests:
`tests/test_assistant_context_builder.py`, `tests/test_memory_candidate_workflow.py`,
`tests/test_assistant_passive_context_integration.py`.)

---

**Reaffirmed:** the model generates; LogosForge remembers and retrieves;
providers are replaceable backends, not memory; Project Memory and Assistant
Meta-Memory stay separate; safe memory auto-saves as active while review is the
exception (see Direction Correction); Jordan is memory-grounded through LogosForge's externalized memory,
not conscious. **This document implements no UI.**


## Phase 8 — Implementation plan

A concrete, architecture-grounded plan for this spec now exists in
`MEMORY_REVIEW_UI_IMPLEMENTATION_PLAN.md`: route via the existing `main_window`
content area (not a new window); a headless `MemoryReviewService` + view models
over the existing review service/store; `ui/safe_dialogs.py` for fullscreen-safe
confirms; `memory_review_ui_enabled` (default off); staged rollout starting with
a pure-Python service/view-model layer. Still **no UI/code implemented**.


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
