# Export

LogosForge exports project data in several formats (`logosforge/export.py`).
Project metadata (JSON/Markdown/data export) always includes the canonical
`writing_mode` (see docs/WritingModes.md).

## Screenplay export (Phases 10A–10F)

For screenplay projects the exporters are screenplay-aware: scene bodies are
parsed into blocks (`screenplay_blocks`) so character cues / transitions / scene
headings are uppercased and parentheticals normalized — **text-preserving**.

### Targets

| Function | Output |
|---|---|
| `export_screenplay` | screenplay plain text (slug + classified body) with a `Writing Mode` header |
| `export_screenplay_fountain` / `export_screenplay_fountain_result` | **canonical** `.fountain` (Phase 10G) via `screenplay_fountain.serialize_screenplay_to_fountain` — title page, forced elements, grouped dialogue, option-gated notes; result carries `.fountain` filename + warnings |
| `export_fountain` | screenplay projects now delegate to the canonical serializer; other modes keep the legacy multi-mode Fountain text path |
| `export_fountain_validation_json` | Fountain validation report (schema_version / writing_mode / exported_at / filename) |
| `export_screenplay_preview_html` | conservative screenplay **preview HTML** (not page-accurate) |
| `export_screenplay_export_validation_json` | export-readiness report (`schema_version`, `writing_mode`, `exported_at`) |
| `export_screenplay_diagnostics_json` / `export_screenplay_graph_json` / `export_story_links_json` / `export_setup_payoff_report_json` / `export_subtext_report_json` | structured screenplay reports |
| `export_pdf` / `export_fdx` | **basic** existing exporters — *not* page-accurate / production drafts |

### Title page metadata

Stored in project settings (`screenplay_title_page`; no schema change) via
`screenplay_render.get_title_page` / `set_title_page`. Fields: `title, credit,
author, source, draft_date, contact, notes`. Falls back to the project title.
Included at the top of Fountain export when `include_title_page` is on.

### Export preferences

`screenplay_render.get_export_prefs` / `set_export_prefs` (project settings,
conservative defaults): `show_notes_in_export` (default **off** — production
export hides notes), `uppercase_scene_headings`, `uppercase_character_cues`,
`include_title_page`, `include_diagnostics_report`, `export_target`
(`fountain` / `plain_text` / `preview_html`), `approximate_page_estimate`.

### Render model

`screenplay_render.build_render_document` produces a serializable
`ScreenplayRenderDocument` (blocks with style + `export_text`, title page,
**approximate** page/minute estimate, warnings) — the foundation for future
PDF/FDX. Read-only, no LLM.

### Export readiness validation

`screenplay_export_validation.validate_screenplay_export` returns a deterministic
report separating **blocking errors** (empty screenplay, unsupported target)
from **warnings** (missing title/headings, orphan dialogue/parentheticals) and
**suggestions** (note inclusion). It blocks export only when truly unsafe. Logos
surfaces this via `Validate Screenplay Export` / `Generate Export Readiness
Report` / `Check Production Polish` (deterministic, no LLM). The Assistant gets a
capped `[Screenplay Export Readiness]` block.

## Approximate vs professional

Page/minute counts are **approximate** (~1 page/minute, ~55 lines/page) and
labelled as such — never professional page-accurate pagination.

## Fountain vs Markdown (Phase 10G)

**Fountain (`.fountain`) is the canonical screenplay interchange format** — it is
screenplay-specific markup, *not* generic Markdown. The generic `export_markdown`
remains for documents/outline/notes and is a **separate serializer**; screenplay
export never uses it. `screenplay_fountain` also provides a Fountain **parser**
(`parse_fountain_to_screenplay_blocks`) and roundtrip (blocks → `.fountain` →
blocks preserves standard elements + title page); the parser is exposed as a
service (import UI is deferred to 10H).

## Professional output (Phase 10H)

Derived professional formats built on the render model (see
**docs/ProfessionalScreenplayOutput.md**): `export_screenplay_docx` (**stable**),
`export_screenplay_pdf` (reportlab, **approximate** pagination),
`export_professional_preview_html` (print-to-PDF path),
`export_screenplay_fdx_experimental` (**experimental**, gated by
`experimental_export_acknowledged`), and `export_screenplay_output_validation_json`
(compatibility levels stable/preview/experimental/deferred). Fountain stays the
canonical interchange format.

## Production export (Phase 10J)

`export_production_fountain(db, pid, include_omitted=True)` emits Fountain
with persistent `#N#` scene numbers and `OMITTED` markers for an active
production draft (opt-in; default Fountain unchanged; never Markdown). See
**docs/ProductionDrafts.md**.

## Export integrity (Phase 10I)

A no-text-loss harness (`tests/helpers/screenplay_export_fixtures.py`) verifies a
representative screenplay (title page, headings, ambiguous ALL-CAPS action,
character + `(V.O.)`, multiline dialogue, parenthetical, transition, note,
accented/special chars) survives every text-bearing target: **Fountain (+
roundtrip), DOCX, HTML preview, FDX**; PDF is checked for a valid `%PDF-` file
(no text-extraction dependency available). Verified invariants:

- One source of truth: `Scenes → ScreenplayBlocks → ScreenplayRenderDocument →`
  {Fountain (canonical), DOCX, HTML, PDF, FDX}. Reports take `(db, project_id)`,
  read-only, no LLM/Assistant/DB-mutation.
- **Fix:** the render model now injects a scene heading from the slug/title when
  a scene's content has none — so DOCX/PDF/preview/FDX never drop headings
  (previously only the Fountain path injected them). No duplicate when the
  content already opens with a heading.
- Fountain and Markdown are **separate** serializers (correct `.fountain` /
  `.md` / `.fdx` extensions); screenplay never routes through Markdown.
- Screenplay Logos/export actions are hidden in Novel / Graphic Novel / Stage
  Script / Series; Novel export is unaffected.
- Assistant export context is capped, never dumps the scene body, and does not
  leak across a project switch.
- The plain-text `export_screenplay` path and the render-model exports are
  documented as two paths sharing the same blocks; consolidation is deferred
  (low value / non-trivial) — both preserve text.

## Deferred (future)

- Export **menu / options dialog** UI (export functions + Logos actions exist).
- True page-accurate PDF pagination + production-grade / verified FDX.
- Title-page / export-preferences **editor UI** (storage + service API exist).
- Fountain **import UI** (parser round-trip exists; project import UI deferred).
- PDF text-extraction integrity test (no extractor dependency available).
- Production UI controls + true page locking (production *data/export* layer
  shipped in Phase 10J — see docs/ProductionDrafts.md); locked pages out of scope.

## Limitations

Screenplay block types are derived from flat scene text (not persisted), so
export classification is heuristic; a hand-typed novelistic block may export as
action. Novel and other-mode exports are unchanged.

## Alpha export hardening (Step 18)

The manuscript export menu (`MainWindow._on_export`) now wraps every export in a
try/except: failures show a readable **"Export failed"** dialog instead of a
traceback. PDF/DOCX failures (when their optional libraries are missing) report a
clear "install … or use Markdown/TXT/Fountain/JSON" message — no crash.

See **docs/Interchange.md** for the full Alpha Export Matrix and honest
formatting-preservation notes.
