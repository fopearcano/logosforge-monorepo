# Pro session — Import a LogosForge Project Bundle (Whiteboard → Pro migration)

**Paste this into a Pro-focused session.** It is self-contained. Do the work in the **Pro tier** (`pro-shared-ui`, `pro-desktop`, and — only if you add the optional consolidated endpoint — the shared core `logosforge/`). **Do NOT touch the Whiteboard tier** (`whiteboard-desktop/`); the bundle format below is a fixed contract already produced by Whiteboard.

## Status: the Whiteboard export side is DONE ✅

Whiteboard already ships the export half:
- Backend: `GET /api/export/project?doc=<id>` (`whiteboard-desktop/backend/app/routers/export.py`) assembles the whole bundle in one pass.
- UI: **File → Export → "Export Project (.lfbundle)…"** (one click) writes a `.lfbundle` file.

So you can generate a **real test bundle** immediately: open the Whiteboard app, pick a project that has characters + an outline + comments, File → Export → Export Project, save the `.lfbundle`. Verify your Pro import against that, not just a hand-authored file.

## Why this exists

Whiteboard and Pro are **two separate installed apps with two separate databases** (Whiteboard: `~/.logosforge/whiteboard.db` + JSON files under `~/.logosforge/`; Pro: `%APPDATA%\LogosForge Pro\logosforge.db`). They cannot share storage, so migration crosses an app boundary via a **file**. Whiteboard stores manuscript as **blocks**; Pro stores it as **scenes**. A per-project, manuscript-only converter already exists (see "Reuse"). This task adds a **complete single-project import**: one `.lfbundle` → one new Pro project, carrying the **manuscript AND the PSYKE bible** (Phase 1). The bundle also carries outline + comments for a later Phase 2.

## The bundle format — CONTRACT (this is the exact shape Whiteboard emits)

Extension **`.lfbundle`**, a single JSON object:

```jsonc
{
  "format": "logosforge-project-bundle",
  "version": "1.0",
  "exportedAt": "2026-07-03T15:51:40.885556+00:00",
  "source": { "app": "logosforge-whiteboard" },
  "project": {
    "id": "7",                        // source doc/project id (string) — informational only
    "title": "The Sounding",
    "mode": "novel",                  // novel | screenplay | scene | graphic_novel | stage_script
    "manuscript": {
      "blocks": [                     // Whiteboard blocks, VERBATIM — this is what the converter eats
        { "id": "b0", "type": "heading", "text": "Chapter One", "level": 1 },
        { "id": "b1", "type": "paragraph", "text": "The hull settled in the dark…" }
        // type: "heading" | "paragraph". Optional per block: level (1–3, headings),
        // sp (screenplay element type), marks (inline bold/italic runs). Absent fields are omitted.
      ]
    },
    "outline": [                      // manual outliner nodes, VERBATIM (Phase 2 target)
      { "id": "96315f31-…", "parentId": null, "type": "act", "title": "Act I", "order": 0,
        "collapsed": false, "completed": false, "status": "none", "tags": [],
        "colorLabel": "none", "linkedLineId": null, "createdAt": "…", "updatedAt": "…" }
      // type ∈ act|part|chapter|sequence|scene|beat|custom. Tree is parentId + order.
    ],
    "comments": [                     // inline comments, VERBATIM incl. anchor (Phase 2 target)
      { "id": "…",
        "anchor": { "block_index": 3, "from_offset": 0, "to_offset": 9,
                    "end_block_index": null, "prefix": "", "suffix": "" },
        "quote": "the knock", "body": "foreshadow?", "resolved": false,
        "replies": [], "created_at": "…", "updated_at": "…" }
      // NOTE: snake_case anchor. Anchored by block_index (+ quote/prefix/suffix) — Pro must
      // re-anchor to a scene position after the blocks→scenes conversion.
    ],
    "psyke": {                        // the story bible — same core subsystem as Pro
      "elements": [
        { "id": "1", "name": "Mara", "entry_type": "character",
          "aliases": [], "description": "sonar tech", "notes": "",
          "created_at": null, "updated_at": null }
        // NOTE: field is "entry_type" (NOT "type"). entry_type ∈ character|place|object|lore|theme|other.
        // On import create a fresh entry: map entry_type→type; carry name/description/notes/aliases.
        // Ignore id + timestamps (Pro assigns new ones under the new project).
      ]
    }
  }
}
```

Robustness:
- Validate `format === "logosforge-project-bundle"`; reject other files with a friendly error.
- Treat a missing/empty `outline`, `comments`, or `psyke.elements` as empty (older/small bundles).
- Be tolerant of a future `version` bump (same top-level shape).

## Reuse — what already exists (don't reinvent)

- **Core converter:** `logosforge/logosforge/whiteboard_import.py` → `import_whiteboard_document(db, doc)` takes `{ title, mode, blocks }`, creates **one** new project, and segments blocks → scenes (heading/slug-aware). Returns the new `project_id`.
- **Route:** `POST /import/whiteboard` in `logosforge/logosforge/api/routes/imports.py` (body `WhiteboardImportDTO` with `blocks`, `title`, `mode`).
- **Pro adapter + UI:** `api.importWhiteboard(...)` in `pro-shared-ui/src/adapters/httpApiClient.ts`; the existing **"Import Whiteboard"** button + file picker in `pro-shared-ui/src/components/projectos/ProjectsPanel.tsx` (uses `platform.openFile`).
- **Pro PSYKE:** Pro already edits PSYKE (PsykeBible); the api adapter has PSYKE create/list against the core's `/api/projects/{id}/psyke/...` routes.

> Keep the converter engine and the existing "Import Whiteboard" button. This is **reuse, not replacement** — retiring the old button once the bundle import is proven is optional and cosmetic.

## Task — "Import Project (.lfbundle)" · Phase 1 = manuscript + PSYKE

Prefer **client-side orchestration in `pro-shared-ui` reusing existing endpoints** — Phase 1 needs **no core change**:

1. **UI:** add an **"Import Project (.lfbundle)"** action beside the existing "Import Whiteboard" in `ProjectsPanel.tsx`. File picker (`platform.openFile`, filter `lfbundle`/`json`), read the text.
2. **Parse + validate** the bundle (format/version; friendly error toast on mismatch / bad JSON).
3. **Manuscript → new project + scenes:** call `api.importWhiteboard({ title: project.title, mode: project.mode, blocks: project.manuscript.blocks })`. Capture the returned **new `projectId`**. (If `importWhiteboard` doesn't yet return the id, make it return it — a Pro-adapter/route tweak, not a Whiteboard change.)
4. **PSYKE → new project:** for each `project.psyke.elements[i]`, call the Pro PSYKE create endpoint scoped to `projectId`, mapping `{ type: el.entry_type, name: el.name, description: el.description, notes: el.notes, aliases: el.aliases }`. Sequential; skip (don't abort) any single failure.
5. **Finish:** refresh the project list, open the new project, toast `Imported "<title>" — N scenes, M characters`.
6. **Robustness:** try/catch; if the manuscript import fails, abort before PSYKE and report. (For all-or-nothing, add the optional consolidated core endpoint below.)

### Optional consolidated endpoint (only if you want atomicity)
Add `POST /import/project-bundle` in the core that calls `import_whiteboard_document` then creates the PSYKE entries in one transaction, returning `{ projectId, scenes, characters }`. Cleaner + atomic, but more surface. The client-orchestration path above is the low-risk default. If you touch the core, follow `logosforge/CLAUDE.md`.

## Deferred — Phase 2 (bundle already carries the data; don't do it yet unless asked)
- **Outline:** map `project.outline` (Whiteboard `OutlineNode[]`) into Pro's outline model.
- **Comments:** re-anchor each comment from `anchor.block_index` → the scene it landed in (reuse the same block→scene segmentation the converter applied), then create Pro comments.

## Files you'll likely touch (Pro tier)
- `pro-shared-ui/src/components/projectos/ProjectsPanel.tsx` — the new button + flow.
- `pro-shared-ui/src/adapters/httpApiClient.ts` (+ `api.ts` interface) — an `importProjectBundle(...)` helper or reuse of `importWhiteboard` + PSYKE create; ensure `importWhiteboard` returns the new project id.
- (optional) `logosforge/logosforge/whiteboard_import.py` + `api/routes/imports.py` — only if you add the consolidated endpoint.

## Acceptance criteria (Phase 1)
- Importing a real `.lfbundle` (exported from the Whiteboard app) produces **one new Pro project** whose scenes match the Whiteboard manuscript (headings became scene breaks) **and** whose PSYKE bible contains every character/place/etc. from the bundle.
- Wrong file / bad JSON → friendly error, no project created.
- No edits to the Whiteboard tier. Bundle format unchanged.
