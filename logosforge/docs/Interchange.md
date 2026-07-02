# Interchange — Export / Import (Alpha)

How Logosforge gets work in and out. All exports build from a single read-only
gatherer (`export._gather_project_data` / `data_export`), are project-scoped,
contain **no API keys and no absolute paths**, and report failures as readable
dialogs (never tracebacks). See also docs/Export.md, docs/BackupRestore.md,
docs/DataSafety.md.

## Alpha Export Matrix

| Format | Entry point | Optional dep | Writing modes | Lossless? | Notes |
|--------|-------------|--------------|---------------|-----------|-------|
| **Markdown** (`.md`) | `export_markdown` | none | all | text | header includes Writing Mode |
| **Plain text** (`.txt`) | `export_formatted_text` | none | all (mode formatter) | text | novel/screenplay/GN/stage/series layout |
| **JSON project** (`.json`) | `export_json` | none | all | structured | includes `writing_mode`+`narrative_engine` |
| **Fountain** (`.fountain`) | `export_fountain` | none | screenplay (others → prose) | text-preserving | see Fountain notes |
| **Final Draft** (`.fdx`) | `export_fdx` | none (stdlib XML) | all | structured | standard FDX; advanced render-path FDX is experimental/gated |
| **HTML** (`.html`) | `export_html` | none | screenplay-oriented | preview | preview-grade styling |
| **CSV – scenes** (`.csv`) | `export_csv_scenes` | none | all | tabular | scene rows |
| **DOCX** (`.docx`) | `export_docx_manuscript` | **python-docx** | all | formatted | readable "Export failed" if lib missing |
| **PDF** (`.pdf`) | `export_pdf` | **reportlab** | all | formatted | readable "Export failed" if lib missing |
| **Outline (Markdown)** | `export_outline_markdown` | none | all | text | act/chapter/scene outline |
| **Story elements (JSON)** | `data_export.build_story_elements` | none | all | structured | project+outline+plot+timeline+`psyke`+notes |
| **PSYKE bible (JSON)** | `data_export.build_psyke_data` | none | all | structured | entries+relations+progressions |
| **Full project (JSON)** | `data_export.build_full_export` | none | all | structured | **import-compatible**; scenes/psyke/notes/outline/plot/timeline/settings/quantum |

## Import

- `import_data.validate_import_data(raw)` — validates JSON, returns a readable
  error string on failure.
- `import_data.import_json(db, data)` — creates a **new project** from a full/
  story-elements export. **Non-destructive** (never overwrites an existing
  project). A full-export → import roundtrip preserves scenes, PSYKE, notes and
  structure.

## Fountain — what maps, and limitations

`screenplay_fountain.to_fountain` parses each scene's **content** into screenplay
blocks and serializes them:

- **Scene heading** — `INT./EXT.` lines (kept as-is / uppercased). The heading is
  read from the scene **content** (as the editor writes it); the separate
  `slugline` metadata field is not re-injected.
- **Action** — prose lines.
- **Character cue** — uppercased (or `@forced` to preserve intentional mixed case).
- **Parenthetical** — auto-wrapped in `()`.
- **Dialogue** — grouped under its cue.
- **Transition** — e.g. `CUT TO:`.
- **Unrecognized lines degrade to action** — **no text is ever lost.**

**Limitations (honest):** block classification is heuristic (flat scene text, not
persisted block types), so a hand-typed novelistic paragraph may export as
action; **dual dialogue** and **title-page metadata** are minimal; HTML/PDF are
**preview-grade**; the advanced render-document FDX path is **experimental/gated**
(the menu FDX uses the stable stdlib XML builder).

## Safety guarantees

- **No API keys** in any export (keys live in app settings, never in project
  data). Verified by tests.
- **No absolute filesystem paths** in export payloads.
- **Missing optional systems** (empty PSYKE/outline/notes) serialize cleanly —
  exporting an empty project never raises.
- **Readable errors** — every manuscript and data export surfaces failures as a
  dialog, including a friendly hint when `reportlab`/`python-docx` is missing.

## Tests

`tests/test_export_stabilization.py`, `tests/test_data_export.py`,
`tests/test_versioning_backup.py`.
