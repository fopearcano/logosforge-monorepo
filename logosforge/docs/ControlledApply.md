# Controlled Apply / Merge Tools (Phase 10M)

The single gate every canonical mutation passes through. Generated variants,
Assistant edits, Logos operations, Counterpart proposals and Rewrite Sandbox
outputs **never overwrite canonical content blindly** — they pass through
preview → diff → conflict detection → explicit confirmation → (optional)
rollback checkpoint.

## Why

"Here is a proposed change. Here is what it touches and replaces. Here are the
conflicts. Here is the rollback point. Apply / cancel." The AI proposes; the user
confirms.

## Data model (`models.py`, idempotent `create_all`)

`ControlledApplyOperation` (source/target/mode/status + before/after hashes +
excerpts + diff/conflict JSON + checkpoint stage id) and
`ControlledApplyConflict`. References + hashes only — **no full snapshots**. Old
DBs gain empty tables.

## Service (`controlled_apply/service.py`)

- `build_apply_preview(...)` → `ApplyPreview` (before/proposed/after, diff,
  conflicts, `can_apply`, `rollback_available`). **No mutation.** `save=True`
  persists a draft operation.
- `create_apply_operation(...)` — persist a previewed operation.
- `apply_operation(..., confirmed=True, force=…)` — mutates the target through a
  validated adapter **only after** confirmation; blocking conflicts (incl. stale
  source) require `force=True`; creates a STAGE checkpoint when available; emits
  `project_data_changed`.
- `cancel_operation`, `get_apply_history`.

Deterministic, no LLM, no Qt, current project only.

## Diff (`controlled_apply/diff.py`)

Line/term diff (reuses the 10K diff): added/removed lines + terms, change size,
empty-change detection, accent-safe.

## Conflicts (`controlled_apply/conflicts.py`)

| Conflict | Severity |
|---|---|
| `stale_source` (target changed since proposal) | **blocking** |
| `target_missing` | **blocking** |
| empty proposal / disallowed mode (`format_mismatch`) | **blocking** |
| `psyke_reference_loss` (drops a PSYKE name) | warning |
| `screenplay_block_invalid` (orphan dialogue, screenplay mode) | warning |
| `production_risk` (active production draft) | warning |

Blocking conflicts prevent direct apply; warnings allow apply with explicit
confirmation. Blocking can be overridden only with `force=True`.

## Target adapters (`controlled_apply/targets.py`)

`scene` / `manuscript` / `screenplay_block` (scene content), `outline_node`
(description), `psyke_entry` (**notes only** — name/type/aliases/relations
preserved), `note` (**body only** — title/tags/pinned preserved). Each validates
allowed modes (`replace` / `append` / `insert_*` / `manual_copy`) and writes
through the Database service layer (no raw SQL, no broad object mutation).
`plot_block` / `timeline_event` / `graph_node` are deferred (clean "deferred").

## Rewrite Sandbox integration

`apply_rewrite_variant` now routes its mutation through
`controlled_apply.service.apply_operation` (diff + conflicts + checkpoint +
event), records a `ControlledApplyOperation` (`source_type="rewrite_variant"`),
and preserves the 10L contract (stale-guard, `RewriteApplyRecord`, variant →
applied). Generation stays isolated; cancelled/rejected variants never mutate.

## Assistant / Logos / Counterpart

- **Assistant** proposes edits → a preview (or the Sandbox); it never applies
  directly.
- **Logos**: deterministic `Apply History` + `Explain Apply Conflicts`
  (read-only, no LLM, all modes); mutating apply via the service + confirmation.
- **Counterpart**: critique only (hook via the shared backend; wiring deferred).
- No autonomous loop — every canonical mutation ends at a confirmed apply.

## Assistant context

`[Controlled Apply]` block — only when a pending (draft/previewed) operation
exists; shows source→target, blocked/not, and conflicts. Capped, **never dumps
proposed text**, no LLM/DB, no cross-project leak.

## Versioning / rollback

`apply_operation` creates a STAGE checkpoint when `create_stage` exists and links
its id; rollback via the existing STAGES system. Without versioning, only
before-hash/excerpt are stored (limited rollback). Preview never autosaves;
apply triggers normal autosave; cancel leaves content unchanged.

## Refresh / project switch

Apply emits `project_data_changed`. Reads are per-`project_id`; pending previews
from another project never appear (Assistant context / history are
project-scoped).

## Deferred (future)

- Apply Preview **UI** dialog (resizable, scrollable, conflict-gated buttons) —
  service API + Logos status shipped.
- Advanced **partial-line merge** (current modes: replace / append / insert /
  manual copy).
- Outline **structural** apply through the outline parser (single-node text apply
  is supported; multi-node structural apply uses the existing outline pipeline).
- `plot_block` / `timeline_event` / `graph_node` adapters; Counterpart critique
  wiring; force-override UI for blocking conflicts.

## Limitations

Field-level replace (not selection-range merge in core); screenplay-block
validity is heuristic; production attachment to a revision set is a documented
follow-up. No UI yet — driven by the service API + Logos status + `[Controlled
Apply]` Assistant context.
