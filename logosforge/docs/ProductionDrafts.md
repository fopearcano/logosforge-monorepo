# Screenplay Production Drafts (Phase 10J)

An **optional, screenplay-only** production-draft layer: persistent scene
numbering, omitted-scene tracking, dated/coloured revision sets, and
production-readiness validation. It does **not** make Logosforge a Final Draft
production system — page locking is awareness-only and several production
features are deferred.

## Spec Draft vs Production Draft

| | Spec Draft | Production Draft |
|---|---|---|
| Scene numbers | none required; scenes move freely | assigned + **persistent** |
| Omitted scenes | n/a | tracked, number kept, never reused |
| Revisions | n/a | grouped into dated/coloured **revision sets** |
| Page locking | n/a | **approximate awareness only** (deferred) |
| Export | creative WIP | stricter validation; `#N#` scene numbers |

Production mode is **opt-in** — no screenplay project is forced into it.

## Data model (`models.py`, idempotent `create_all`)

`ProductionDraft`, `ProductionSceneNumber`, `RevisionSet`,
`RevisionChange` (scene-level). Created automatically for new and existing DBs
(old DBs gain empty tables; no existing data touched). **`LockedPageMap` is
deferred** (page locking is approximate). Block-level revision tracking is
deferred (blocks aren't persisted) — changes are tracked per scene via text
hashes.

## Service layer (`screenplay_production.py`)

- `enable_production_mode` / `is_production_mode`
- `assign_scene_numbers` — sequential `1,2,3…`; preserves existing numbers and
  omitted markers; new scenes get the next free number.
- `insert_scene_number` — inserted scenes use a letter suffix (`10` → `10A` →
  `10B`).
- `omit_scene` / `restore_scene` — omitted scenes **keep their number**
  (marked `OMITTED`), never reused.
- `validate_scene_numbers` — flags duplicates / empties.
- `create_revision_set` — next colour (White → Blue → Pink → Yellow → Green →
  Goldenrod → Buff → Salmon → Cherry → Tan → Ivory); records scene-level changes
  by **text-hash diff** vs the previous set. **No per-keystroke auto-revision** —
  always an explicit action.
- `production_status` / `validate_production_draft` — readiness levels: `spec`,
  `production-ready-structural`, `production-ready-numbered`,
  `production-ready-revised`, `production-output-limited`, `unsupported`.

All mutations are explicit (the caller obtains user confirmation); deterministic;
no LLM; no auto-mutation of PSYKE/Plot/Timeline/Graph.

## Page locking

**Approximate awareness only.** Pagination is line-count based, not
page-accurate, so `ProductionDraft.page_locking_status` is `disabled` /
`approximate` (never `stable`). True page locking, stable page labels, and `10A`
page inserts are **deferred**. Validation surfaces an "approximate" warning.

## Export

- `export_production_fountain(db, pid, include_omitted=True)` — Fountain with
  `#N#` scene numbers and `OMITTED` markers. **Opt-in**; default
  `export_screenplay_fountain` is unchanged. Generic Markdown is never used.
- DOCX/preview show scene numbers when a production draft is active (via the
  render model). FDX production metadata is deferred (FDX is experimental).

## Logos (deterministic, no LLM)

Explain Production Draft Status, Validate Production Draft, Check Duplicate Scene
Numbers, Summarize Revision Set, Explain Page Locking Status, Check Fountain
Production Export, Prepare Screenplay for Production Export. Screenplay-only;
hidden in other modes. **Mutating operations** (assign numbers, omit/restore,
create revision set) are the explicit service API — Logos surfaces status only;
UI buttons are deferred.

## Assistant

`[Production Draft Status]` block — emitted **only when production mode is
active** (`include_production_draft_in_assistant_context`, default on). Capped,
deterministic, no scene-body dump, no cross-project leak, no LLM/DB.

## Narrative Health

`Production Draft Readiness`, `Scene Numbering Integrity`, `Revision Set
Integrity` — **only when production mode is active**, capped at *Needs Attention*
so a production-format issue never flips the narrative overall status. Duplicate
scene numbers are a **production blocking error** in the validator, but health
stays capped (output health ≠ story health). Non-screenplay projects show none.

## STAGES / versioning

Revision sets are kept as **lightweight metadata** (scene-level text hashes) and
are intentionally not coupled to the STAGES/versioning snapshot system; deeper
integration (snapshot references) is deferred. Autosave/versioning is unaffected
— editing never auto-creates a revision.

## Revision Intelligence (Phase 10K)

Production revision sets are explained by the Revision Intelligence layer
(Change Impact Map): a saved RevisionChange can seed an impact report that
lists affected scenes/PSYKE/setup-payoff/continuity. See
**docs/RevisionIntelligence.md**.

## Deferred (future)

- Production UI controls (enable mode, assign numbers, revision sets, omit/
  restore, validate, export) — service API + Logos status exist.
- Real page locking + `LockedPageMap` + stable page labels / `10A` page inserts.
- Block-level revision tracking; FDX production metadata; deep STAGES coupling.

## Limitations

Scene numbering and omitted tracking are robust and persistent; page locking is
approximate; revision tracking is scene-level (hash-based), not block- or
page-level. No production UI yet — driven by the service API + Logos status
actions + `export_production_fountain`.
