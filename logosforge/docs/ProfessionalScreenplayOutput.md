# Professional Screenplay Output (Phase 10H)

The professional output layer sits on top of the screenplay block engine and the
Fountain pipeline. **Fountain (`.fountain`) remains the canonical plain-text
interchange format**; DOCX / PDF / FDX are *derived* outputs.

## Output chain

```
ScreenplayBlocks → ScreenplayRenderDocument → {
    Fountain (.fountain)   — canonical interchange (Phase 10G)
    HTML preview           — readable, print-to-PDF path
    DOCX (.docx)           — clean, structurally faithful (stable)
    PDF (.pdf)             — reportlab, APPROXIMATE pagination
    FDX (.fdx)             — EXPERIMENTAL, gated, unverified
}
```

## Style profiles (`screenplay_output_styles.py`)

`ScreenplayOutputStyle` (pure data) defines page size, font, margins, and
per-element styling. Fonts degrade safely: **Courier Prime → Courier New →
Courier → monospace** (no platform/font assumptions). `get_style("standard")`
is the default; notes excluded, sections/synopses off, page numbers on.

## DOCX (`screenplay_docx_export.py`) — **stable**

`export_screenplay_docx(db, pid, path)` writes a screenplay-styled `.docx`
(title page, scene headings, action, character cues, parentheticals, dialogue,
transitions) via python-docx. Notes are excluded by default (`style.include_notes`)
with a warning. Degrades cleanly if python-docx is missing. No DB mutation/LLM.

## PDF — **preview-level (approximate)**

`export_screenplay_pdf(db, pid, path)` renders via reportlab from the render
model. **Pagination is approximate, not page-accurate** — always labelled as
such. For best fidelity, use the **HTML preview** and print to PDF.

## HTML preview (`screenplay_html_preview.py`)

`export_professional_preview_html(db, pid, dark=…)` — self-contained, no remote
assets, light/dark + print CSS. The recommended path to a clean PDF.

## FDX (`screenplay_fdx_export.py`) — **experimental**

`export_screenplay_fdx_experimental(db, pid, options={"experimental_export_acknowledged": True})`
maps the standard six elements + a basic title page to Final Draft XML. It is
**gated** (no output without the acknowledgement flag) and **labelled
experimental** — Final Draft compatibility is not verified in CI. Notes are
omitted (FDX `ScriptNote` deferred); scene/page numbers, dual dialogue,
revisions, sections/synopses are deferred. **Use `.fountain` for reliable Final
Draft import.**

## Validation (`screenplay_output_validation.py`)

`validate_professional_output(db, pid, target_format=…)` returns blocking errors
vs warnings vs suggestions with a **compatibility level**:

| Target | Level |
|---|---|
| fountain, docx | `stable` |
| preview, html, pdf | `preview` (PDF pagination approximate) |
| fdx | `experimental` |
| unknown | `deferred` |

Deterministic; reuses the Fountain content validator; never blocks on warnings.

## Logos (deterministic, no LLM)

Validate Professional Output, Generate Output Readiness Report, Preview
Screenplay Output, Check PDF Readiness, Check FDX Feasibility, Explain Export
Warnings, Prepare Screenplay for Professional Export. Screenplay-only; hidden in
Novel; read-only.

## Assistant

`[Professional Output Readiness]` block — **opt-in** (`include_professional_output_in_assistant_context`,
default off) to avoid prompt bloat. Capped, deterministic, no LLM/DB.

## Narrative Health

`Professional Output Readiness` and `FDX Compatibility Risk` (always *Needs
Attention* — experimental) are **format health**, capped at *Needs Attention* so
they never flip the narrative overall status. Novel/other modes unaffected.

## Phase 10I integrity

All output targets pass a no-text-loss harness (Fountain + roundtrip / DOCX /
HTML / FDX; PDF validated as a real `%PDF-` file). The render model now injects a
scene heading from the slug/title when a scene has none, so DOCX/PDF/preview/FDX
stay consistent with Fountain and never drop headings. Fountain and Markdown
remain separate; screenplay exports are hidden in non-screenplay modes; Assistant
export context is capped with no scene-body dump and no cross-project leak.

## Deferred (future)

- Export **menu / options dialog** UI (functions + Logos + options exist).
- Page-accurate PDF pagination; verified Final Draft FDX compatibility.
- FDX notes / scene numbers / sections / dual dialogue; revision colors; locked
  pages; Cinematic Continuity detector.

## Limitations

Block types derive from flat scene text (heuristic). PDF pagination and
page/minute estimates are approximate. FDX is experimental and unverified. No UI
export menu yet — outputs are exposed as export functions + Logos actions.
