# Memory Review UI — Implementation Plan

> **Phase 8 — implementation planning only. No UI/service code is written by
> this document.** It maps the Phase-7 `MEMORY_REVIEW_UI_SPEC.md` to the
> *existing* LogosForge architecture (the real `main_window` content routing,
> the `safe_dialogs` pattern, the settings system, and the
> `memory_arch`/`assistant_arch` backend) so a later implementation is a
> wiring exercise that cannot regress the Alpha.

Principle (unchanged): **the model generates; LogosForge remembers, retrieves,
structures, updates, and syncs.** The automatic policy pipeline writes safe
memory (`MEMORY_ARCHITECTURE.md` → *Direction Correction*); Memory Review is a
local, read/curate **audit & exception** surface gated behind a default-off
flag. It performs **no provider call** and makes no durable write of its own
beyond the user's explicit review actions (approve / reject / edit / supersede).

---

## 1. Goal recap

The future Memory Review UI lets the user: view proposed candidates / active /
(diagnostic) rejected·deprecated·superseded·contradicted; filter by scope /
type / status / project / workspace / confidence / tags·entities; search; view
a safe source preview; approve / reject / edit / supersede / mark speculative;
review contradictions; export selected memory to Markdown; preview an optional
GitHub export; and later see sync status / local-vs-cloud. It must **not** make
memory active automatically, mix Project ↔ Assistant memory, trigger cloud
sync or GitHub commits, call providers, store secrets/raw-audio, show unrelated
project memory, or expose raw chat logs by default.

## 2. How this maps to the existing app

| Need | Existing mechanism (real code) |
|---|---|
| A new screen | A `QWidget` view mounted in `MainWindow.content_area` via a `_show_memory_review()` method, mirroring `_show_notes` / `_show_plan` (swap content, no new window) |
| Reaching it | A button in `SettingsDialog` (`ui/settings_dialog.py`) → "Assistant Memory", and/or a sidebar entry gated by the existing `nav_available` property |
| Hiding it by default | `nav_available=False` + the `memory_review_ui_enabled` flag (default off) |
| Confirms / prompts | `ui/safe_dialogs.py` (`question` / `information` / `warning` / `get_text`) — window-modal, parented to the top-level window, no window-state calls (the documented macOS fullscreen-glitch cure) |
| Settings flags | `logosforge/settings.py` `DEFAULTS` + `get_manager().get/set` |
| Memory reads/writes | `MemoryCandidateReviewService` (`memory_arch/review.py`) over `LocalSQLiteMemoryStore` (`memory_arch/local_store.py`); `AssistantTools` (`assistant_arch/tools.py`); export via `tools.export_memory_to_markdown` |
| Disabled sync/GitHub | `MemorySyncService` / `GitHubMemoryExportService` (status/preview only) |

**No new backend doors.** The UI talks to a thin `MemoryReviewService` that
wraps the already-tested review service + store.

## 3. Route / entry-point plan

- **MVP route name:** `memory_review` (content-area route key, consistent with
  existing `_show_*` keys).
- **Form factor:** a **content-area page** (a `QWidget` swapped into
  `content_area`), **not** a separate window, **not** an application-modal
  dialog. Detail/source/export previews are **in-page panels**, not new
  windows. Any confirmation (e.g., supersede) uses `safe_dialogs.question(...)`.
- **Why safer than main navigation:** it reuses the proven content-swap path
  (same as Notes/Plan), so it inherits correct parenting and fullscreen
  behavior; it stays out of the primary creative flow; and it is invisible
  until the flag is on.
- **Feature flag:** `memory_review_ui_enabled` (**default `false`**). Optional
  `memory_review_diagnostics_enabled` (**default `false`**) for the diagnostic
  view. Both added to `settings.py` `DEFAULTS` when Stage 2 lands.
- **Local-only:** yes (Stage 1–4). **Project-aware:** yes — reads the active
  `project_id` the shell already tracks; project scope requires it.
- **Fullscreen / Pages safety:** never create parentless or
  application-modal windows; never call window-state methods; reuse
  `content_area`; do **not** reuse any old standalone Pages/Graphic-Novel
  window pattern.
- **Alpha scope:** off by default → zero impact on the current Alpha; ships
  dark until explicitly enabled.

## 4. Data-flow plan

1. UI opens → 2. requests state via `MemoryReviewService.get_review_state(filters)`
→ 3. service queries the configured `MemoryStore` (local SQLite) through
`MemoryCandidateReviewService` → 4. UI receives a `MemoryReviewViewModel`
→ 5. user filters/searches → 6. selects a card → 7. UI shows a **safe
(redacted) source preview** → 8. user acts (approve / reject / edit / supersede
/ mark speculative / export) → 9. service validates → 10. store updates
status/history (audited; no delete) → 11. UI refreshes → 12. the context
builder continues to use **active memory only** by default. **No provider call,
no cloud sync, no GitHub write anywhere in this flow.**

## 5. View-model plan (UI-facing, serializable, headless-testable)

- **`MemoryReviewViewModel`**: `candidates`, `active_memories`, `filters`,
  `counts_by_status`, `counts_by_scope`, `selected_scope`, `selected_project_id`,
  `selected_workspace_id`, `warnings`, `sync_status`, `github_export_status`,
  `diagnostics_enabled`, `local_only`.
- **`MemoryCardViewModel`**: `id`, `content_summary`, `content_full`, `scope`,
  `type`, `status`, `confidence`, `project_id`, `project_name`, `workspace_id`,
  `user_id`, `created_at`, `updated_at`, `tags`, `entities`,
  `source_event_summary`, `source_event_available`, `possible_contradictions`,
  `possible_supersedes`, `warning_badges`, `actions_available`, `can_approve`,
  `can_reject`, `can_edit`, `can_supersede`, `can_export`.
- **`MemoryReviewFilters`**: `scope`, `type`, `status`, `project_id`,
  `workspace_id`, `confidence_min`, `tags`, `entities`, `search_query`,
  `include_diagnostics`, `include_superseded`, `include_rejected`,
  `include_contradicted`, `include_speculative`.
- **`ActionResult`**: `success`, `memory_id`, `new_status`, `warnings`,
  `errors`, `refresh_required`.

All view-model content is built through the existing redaction
(`ContextBundle`/policy) so secrets / raw-audio paths never reach the view.
These are plain dataclasses (no Qt) → fully unit-testable headless.

## 6. Service / API plan (`MemoryReviewService`, pure Python, no Qt)

`get_review_state(filters)` · `list_candidates(filters)` · `list_active(filters)`
· `get_memory_card(memory_id)` · `approve(memory_id, reviewer_id=None,
reason=None)` · `reject(memory_id, reviewer_id=None, reason=None)` ·
`edit(memory_id, patch, reviewer_id=None, reason=None)` · `supersede(
new_memory_id, old_memory_id, reason, reviewer_id=None)` ·
`mark_speculative(memory_id, reason=None)` · `mark_contradicted(memory_id,
contradicted_by_id, reason=None)` · `preview_source_event(memory_id) →
SourcePreview` · `export_markdown(filters) → str` · `preview_github_export(
filters) → MarkdownExportPreview` · `get_sync_status() → SyncStatus`.

Each maps onto the existing backend: `approve→review.approve`,
`reject→review.reject(reason)`, `edit→review.edit(patch, reason)` (status-change
refused; scope re-validated), `supersede→review.supersede(old,new,reason)`,
`mark_*→review.mark_speculative/mark_contradicted`, list/filter→`store.search`
+ `review.list_candidates`, contradictions→`review.contradictions_for` /
`tools.find_contradictions`, export→`tools.export_memory_to_markdown`,
source→`store.get_event`/`list_events` (redacted), sync/github→disabled
services (status/preview only). **Rules:** approve is explicit; reject never
deletes the event; edit requires a reason for scope/type/content changes;
supersede preserves the old object; GitHub export is preview-only; sync is
local-only in MVP; **no provider/cloud calls**.

## 7. Component plan (Stage 2+, existing app style)

`MemoryReviewPage` (content-area `QWidget`, owns filters + selected id, calls
the service) → `MemoryScopeTabs` (User / Project / Workspace / Assistant /
Device — **Project and Assistant never mixed**) → `MemoryFilterBar` →
`MemoryCandidateList` → `MemoryCard` (summary, badges, metadata, actions) →
`MemoryDetailPanel` (full content, **in-page** source preview, contradictions,
supersession history, edit form) → `MemoryActionToolbar` (approve/reject/edit/
supersede/export) → `MemorySourcePreview` (redacted, in-page) →
`MemoryConflictPanel` → `MemoryExportPreview` (markdown + GitHub preview
placeholder, in-page) → `MemoryEmptyState` → `MemoryLocalOnlyBanner` →
`MemoryDiagnosticsPanel` (hidden unless the diagnostics flag is on). Confirms
use `safe_dialogs`; nothing opens a new top-level window.

## 8. UI safety plan

Project ↔ Assistant memory visually separated; wrong-project memory hidden
(except global diagnostic mode); viewing a candidate never activates it;
approve/reject explicit; edit requires save; supersede requires a
`safe_dialogs.question` confirmation; contradicted labelled; superseded/rejected
excluded from normal context; secrets / raw-audio paths redacted; raw audio
never shown/stored; source preview summarized/redacted by default; GitHub export
preview-first; cloud-sync controls absent in the local MVP; UI never calls
providers; UI never triggers auto-extraction unless explicitly requested later.

## 9. Fullscreen / window safety plan

Use the existing `content_area` (or settings panel) — **never** parentless or
floating unmanaged windows; destructive confirms via `safe_dialogs` (window-
modal, parented to the top-level window); **no** standalone Pages/window
pattern; source/export previews are **in-page panels**, not separate windows;
route changes must not minimize/hide/raise the app (no window-state calls); in
fullscreen, Memory Review behaves like the existing safe content routes; any
necessary modal is parented correctly via `safe_dialogs`.

## 10. Backend safety plan

**Allowed:** `MemoryCandidateReviewService`, `LocalSQLiteMemoryStore`,
`MemoryWriterPolicy`, `export_memory_to_markdown`, disabled sync **status**,
disabled GitHub **preview**. **Forbidden:** provider generate/tool calls, cloud
sync, GitHub commit/push, embeddings, raw event dump by default, raw audio,
secrets.

## 11. Implementation phase breakdown

- **Stage 1 — Service + view-model layer (headless, tests only):** create
  `MemoryReviewService` + the four dataclasses; **no UI**; full headless tests.
- **Stage 2 — Hidden/dev UI:** `memory_review_ui_enabled=false`; add the
  content-area route + `nav_available`-gated entry; candidate list, filters,
  detail panel, approve/reject, local-only banner.
- **Stage 3 — Editing / supersession:** edit form, supersede (confirmed),
  contradiction panel, in-page source preview.
- **Stage 4 — Export:** markdown export preview + local save; GitHub export
  **preview only**.
- **Stage 5 — Assistant-panel integration:** "memory candidates proposed"
  badge + link to Memory Review; no auto-approval.
- **Stage 6 — Pro/SaaS (future):** cloud sync status, account/workspace memory,
  permissions, collaborator approvals.
- **Stage 7 — Team/Studio (future):** role-based approvals, audit logs,
  versioned memory, shared-assistant governance.

Stage 1 is the recommended next implementation step (pure Python, fully
testable, zero UI risk).

## 12. Future acceptance criteria

**PASS:** flag off by default; app startup unaffected; route visible only when
enabled; candidate queue + active memory shown; scope tabs separate
User/Project/Workspace/Assistant/Device; Project ↔ Assistant not mixed; filters
+ search work; approve/reject explicit; edit requires save; supersede preserves
old; contradictions labelled; source preview safe/redacted; local markdown
export works; GitHub export preview-only; cloud sync disabled; no provider
calls; no automatic active writes; no secrets/raw-audio shown; no fullscreen
minimize/disappear bug; assistant runtime unchanged when disabled; **alpha gate
passes.**

**FAIL:** memory auto-activates; scopes mixed; wrong-project leak; provider
calls; GitHub writes; cloud sync; secrets/raw-audio exposed; fullscreen
glitches; assistant behavior changes while disabled; existing Alpha navigation
breaks.

## 13. Future test plan

**Service/view-model (headless):** get_review_state returns candidates · scope
/ status / type / project / search filters · approve · reject · edit ·
supersede · source-preview redaction · markdown export · no provider calls · no
cloud sync · no GitHub writes. **UI (offscreen Qt):** flag hides/shows route ·
candidate list · active list · empty state · detail panel · approve/reject
buttons · edit form · supersede confirmation · contradiction warning ·
local-only banner · diagnostics hidden by default · wrong-project excluded ·
Assistant-meta not in Project tab · Project not in Assistant tab · secrets
redacted · raw-audio paths redacted · no unsafe windows · **alpha gate passes.**

## 14. Doc-consistency check

All memory architecture docs consistently assert: the model generates;
LogosForge remembers/retrieves/structures/updates/syncs; providers are not
memory; Project and Assistant memory are separate; GitHub is optional; cloud
sync is future/pro; local-first is default; approval is explicit; raw chat spam
is not durable memory; Jordan is externally memory-grounded, not conscious; no
model weights are updated; no automatic active writes; superseded memory is
preserved; contradictions are visible; the user can inspect what Jordan
remembers. **No contradictions found.**

---

**Reaffirmed:** the model generates; LogosForge remembers and retrieves;
providers are replaceable backends, not memory; Project Memory and Assistant
Meta-Memory stay separate; safe memory auto-saves as active while review is the
exception (see Direction Correction); Jordan is memory-grounded, not conscious.
**This document implements nothing.**


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
