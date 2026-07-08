# Pro session — Project Bundle import, PHASE 3 (outline ↔ manuscript section links)

**Paste into a Pro-focused session.** Prerequisites: **Phase 1** (`PRO_IMPORT_BUNDLE_PROMPT.md`, manuscript→scenes + PSYKE) and **Phase 2** (`PRO_IMPORT_BUNDLE_PHASE2_PROMPT.md`, outline + comments) are done. Phase 3 reconstructs the **hard link** Whiteboard now records from each outline node to a place in the manuscript, so a migrated Pro project keeps its "this section lives *here* in the draft" association. Stay in the **Pro tier**; do NOT edit the Whiteboard tier; the bundle format is a fixed contract.

---

## What's new in the bundle (the source data)

Whiteboard's manual outline gained an optional **hard link** per node. It's already carried in `.lfbundle` (the exporter dumps the outline verbatim — no format/version bump; still `version: "1.0"`). Each `project.outline[]` node MAY now have:

```jsonc
{
  "id": "…", "parentId": "…", "type": "chapter", "title": "Chapter One",
  "order": 0, "status": "…", "colorLabel": "…", "tags": [], "completed": false,
  "link": { "blockIndex": 12, "quote": "By the time the ferry reached the far shore…" }
  //  ^ NEW — optional. Absent or null on unlinked nodes.
}
```

- `link.blockIndex` — a 0-based index into **`project.manuscript.blocks`** (the same block array Phase 1 turns into scenes).
- `link.quote` — a snapshot of that block's text at link time (Whiteboard uses it to re-anchor after edits; here it's a **validation/disambiguation** aid, not the primary key).
- Semantics: "this outline node *owns* the manuscript starting at that block." In Whiteboard it drives a ⚓ badge (jump-to-passage) and a "you are here" breadcrumb as the caret moves.

## The mapping problem (why this needs a small core change)

Pro's manuscript unit is a **scene**, not a block. Phase 1 runs the block→scene segmentation (`logosforge/logosforge/whiteboard_import.py` `blocks_to_scenes`, mode-aware), so **many blocks collapse into one scene** and a raw `blockIndex` has no direct Pro target. To resolve a link you need a **`block_index → scene`** map for the imported manuscript — the *exact same* map the Phase 2 comments fallback called for.

`api.importWhiteboard` currently returns only `{ project_id, title, mode, scenes_created }` — no per-block mapping. So Phase 3's one unavoidable core touch is to **expose that mapping**:

- Extend `blocks_to_scenes` to also return `block_index → scene_index` (0-based scene ordinal), and surface it through `POST /import/whiteboard` → the contract → `api.importWhiteboard`'s result (e.g. `scene_index_by_block: number[]`, or `scene_ids_by_block: number[]` if the route creates the scenes and knows their ids). Follow `logosforge/CLAUDE.md` and cascade `core → @logosforge/ui-contracts → pro-shared-ui`.
- With that map: `sceneOrdinal = sceneIndexByBlock[link.blockIndex]` → the new scene id from the Phase‑1 import (the import creates scenes in order, so ordinal → id is a simple lookup you already build, or read back via `api.getScenes(projectId)`).

## What Pro has for the *target* — VERIFY FIRST, then pick

Phase 2 established Pro's `OutlineNodeDTO` = `{ id, parent_id, title, description, sort_order, children }` — **no scene reference field**. Before building, re-verify in-session whether Pro's outline-node or scene DTO already carries a cross-reference (a `scene_id`, `anchor`, etc.). If it genuinely doesn't, choose one:

### Option 1 — Full feature (recommended if Pro wants section↔scene navigation)
Give Pro's outline node a real scene link, mirroring what Whiteboard has:
- Core + contracts: add an optional `scene_id: number | null` (or a small `link` object) to the outline-node DTO + create/update bodies + the `/outline/nodes` routes.
- Import: after creating each node (Phase 2 Task A) and resolving `blockIndex → scene id`, set the node's `scene_id`.
- UI (`pro-shared-ui` `OutlinePanel` / manuscript): surface it like Whiteboard — a jump-to-scene affordance on linked nodes, and optionally a "you are here" indicator driven by the active scene. Respect the pro-shared-ui rules (platform-neutral, `data-screen-label`, accent via `var(--accent)`).
- This is the honest, non-lossy migration and unlocks the feature for Pro-native use too.

### Option 2 — Lossy stopgap (no core change, visible-not-functional)
Fold the resolved target into the node's `description` (same pattern Phase 2 uses for type/status/colour/tags), e.g. append `· → "<scene title>"` (or `→ Scene N`). The association is *visible* to the writer but not clickable. Cheap; a reasonable interim if Option 1 is out of scope for this pass.

### Option 3 — Defer
Skip links, and (like comments) report **"N section links not migrated"** so nothing is dropped silently. Choose this only if the block→scene map work isn't wanted yet.

## Import wiring (in `pro-shared-ui/src/adapters/projectBundle.ts`)
- Extend `ProjectBundleOutlineNode` with `link?: { blockIndex: number; quote: string } | null` (currently it's silently ignored — confirmed inert, so this is purely additive).
- Thread the Phase‑1 `block_index → scene` map into `importProjectBundle`, and in the existing outline loop attach the link per the chosen option. Keep it best-effort: a link that can't resolve (out-of-range index, or `quote` mismatches the mapped scene's text — a cheap sanity check) is skipped, not fatal, and counted for the summary.
- Validate with `link.quote`: if the mapped scene's text doesn't contain the quote, treat the link as unresolved (the bundle may predate an edit). Report the count.

## Constraints
- **Pro tier only. No Whiteboard edits.** Bundle format is a fixed contract (unchanged — `link` is additive/optional; do not bump `version`).
- The only sanctioned core change is exposing the `block_index → scene` mapping (and, for Option 1, the outline-node `scene_id`). Follow `logosforge/CLAUDE.md`; cascade through `@logosforge/ui-contracts`. No React/UI/Electron in the core.
- Everything else is client-side orchestration in `pro-shared-ui` over existing endpoints.

## Acceptance criteria
- A `.lfbundle` **exported from the real Whiteboard app** with at least one linked outline node imports into Pro such that the node's manuscript association is preserved per the chosen option: Option 1 = a working jump-to-scene (correct scene) + surfaced link; Option 2 = the target scene visible in the node description; Option 3 = an explicit "N section links not migrated" message.
- Unlinked nodes and unresolved links degrade cleanly (no crash, counted).
- The `block_index → scene` mapping is verified correct against a multi-scene manuscript (a link deep inside scene 3 resolves to scene 3, not scene 1).
- No regression to Phase 1/2 (scenes, PSYKE, outline structure, comments-deferred message all still correct).
