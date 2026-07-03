# Pro session — Project Bundle import, PHASE 2 (outline + comments)

**Paste into a Pro-focused session.** Prerequisite: **Phase 1 is done** (see `PRO_IMPORT_BUNDLE_PROMPT.md`) — importing a `.lfbundle` already creates a Pro project with scenes (from the manuscript) and the PSYKE bible. Phase 2 adds the remaining two sections the bundle already carries: the **manual outline** and **comments**. Stay in the **Pro tier**; do NOT touch the Whiteboard tier; the bundle format is a fixed contract.

The bundle's `project.outline` and `project.comments` shapes are documented in `PRO_IMPORT_BUNDLE_PROMPT.md` — read that first.

---

## What I verified about the Pro targets (read this — it reshapes the scope)

- **Outline → Pro HAS a core outline.** Adapter methods exist: `api.getOutline(p)`, `api.createOutlineNode(p, body)`, `api.updateOutlineNode`, `api.deleteOutlineNode` (routes `/api/projects/{p}/outline`, `/outline/nodes`). The node DTO is **simpler** than Whiteboard's:
  ```ts
  OutlineNodeDTO       { id: number; parent_id: number | null; title: string; description: string; sort_order: number; children: OutlineNodeDTO[] }
  OutlineNodeCreateDTO { title: string; description?: string; parent_id?: number | null; sort_order?: number }
  ```
  → Outline import is **feasible now**. Structure (title + hierarchy + order) maps cleanly; Whiteboard's extra metadata (type/status/colorLabel/tags/completed) has no field, so **fold it into `description`** rather than dropping it.

- **Comments → Pro has NO inline-comments subsystem.** The core exposes no comments route, and the Pro adapter has no comment methods — only entity/scene-linked **Notes** (`api.linkNoteScene` / `noteSceneLink`, `NotesPanel`). Whiteboard's inline comments (anchored to a text span via `block_index`) therefore have **no 1:1 target**. See Task B for the two honest options.

## Task A — Outline import (do this; it's the meat of Phase 2)

Runs right after the Phase 1 import, using the **new `projectId`**.

1. Read `bundle.project.outline` — a flat `OutlineNode[]` where each node has `{ id (string uuid), parentId (string|null), type, title, order, status, colorLabel, tags, completed, … }`, tree = `parentId` + `order`.
2. Create the Pro nodes **topologically** (parents before children) so parent ids exist. Keep an `idMap: Map<wbUuid, proNodeId>`:
   - sort the WB nodes so every node comes after its parent (or iterate roots→leaves);
   - for each: `const created = await api.createOutlineNode(projectId, { title: wb.title, description: foldMeta(wb), parent_id: wb.parentId ? idMap.get(wb.parentId) ?? null : null, sort_order: wb.order })`; then `idMap.set(wb.id, created.id)`.
   - `foldMeta(wb)` = a short human line preserving what Pro has no field for, e.g. `"Act · drafting · blue · #tag1 #tag2"` (only include the parts that are set). This keeps type/status/colour/tags visible instead of silently lost.
3. Idempotency / existing content: a freshly Phase-1-imported project has an empty outline, so append. If the project already has outline nodes, either skip (leave a toast) or append under a synthetic "Imported outline" root — your call; don't silently merge-collide.
4. Fire/observe `outline_changed` so the Pro outline panel refreshes.

## Task B — Comments (choose one; Pro has no inline-comments target)

**Recommended: DEFER.** Pro's inline-comments subsystem was decided but isn't built. The cleanest path is to import comments **only once Pro has an inline-comments core subsystem**, then anchor them properly (span-level). Until then, skip comments in the import and `log()`/toast that N comments were not migrated (don't drop them silently).

**Optional lossy fallback (only if the user explicitly wants comment *content* carried now):** map each comment → a scene-linked **Note**:
- Re-anchor `comment.anchor.block_index` → a scene by replaying the SAME block→scene segmentation the manuscript converter used (`logosforge/logosforge/whiteboard_import.py` `blocks_to_scenes`): compute which scene each block index falls into (extend `blocks_to_scenes` to also return a `block_index → scene_index` map, or recompute the boundaries), then map scene_index → the new scene id from the Phase-1 import.
- Create a Note with body `"> {quote}\n\n{body}"` (+ replies appended) and link it to that scene via `api.linkNoteScene`.
- This is **lossy** (a text-span comment becomes a scene-level note) — make that explicit in the UI/report. It is a stopgap, not the real thing.

## Constraints
- Pro tier only. No Whiteboard edits. Bundle format unchanged (fixed contract).
- If you must extend the core (e.g. a `block_index → scene` map on `blocks_to_scenes`, or the future inline-comments subsystem), follow `logosforge/CLAUDE.md` and cascade to `logosforge-ui-contracts`.
- Prefer client-side orchestration in `pro-shared-ui` where possible (outline import is all existing endpoints — no core change needed).

## Acceptance criteria
- After import, the Pro project's outline mirrors the bundle's outline: same titles, same hierarchy (parents/children), same order; the Whiteboard type/status/colour/tags are visible in each node's description.
- Comments: either explicitly deferred with a clear "N comments not migrated" message, or (if the fallback is chosen) each comment appears as a scene-linked note on the correct scene.
- Verified against a **real** `.lfbundle` exported from the Whiteboard app (File → Export → Export Project) that actually has an outline (and comments).
