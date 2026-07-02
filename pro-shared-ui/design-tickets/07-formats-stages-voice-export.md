# Ticket 07 — Format engines, Stages, Voice, Export & cross-cutting

> Brief: §4.5 (engines), §4.10–4.15, §6 (re-skin). Fills `src/components/formats.tsx`.

## Goal
Make the workspace **re-skin per writing mode**, and cover the remaining surfaces:
versioning, voice, export, and the cross-cutting screens.

## Screens / panels
- **Mode re-skin (§6)** — design how the shell adapts per mode: Novel /
  Screenplay / Graphic Novel / Stage Script / Series — vocabulary, the scene-body
  editor, structure labels (e.g. GN: Act→Page→Scene→Panel; Series: Season→
  Episode→…), and the accent band. One parametric system, not five apps.
- **Mode Review Dashboard** — per-mode status aggregation (a themable pattern).
- **Planning Pipeline Confirm** — the confirm-before-apply scene-planning dialog
  (per mode).
- **GN Page Canvas** — graphic-novel page/panel layout + preview.
- **Stages** — version/branch timeline (git-graph-like, story-framed) with
  restore (**non-destructive — restore makes a new project**) + diff.
- **Voice HUD (Dexter's Room)** — *desktop-only* dictation HUD: level/waveform,
  live transcript, intent **preview**, commit target (preview-first commit).
- **Export Dialog** — format (json/md/csv/docx/fountain/pdf/html/fdx) + scope +
  style profile, with a validation pre-flight.
- **Cross-cutting** — Projects browser / New Project (mode+format) / Welcome;
  global **Search** (filter by entity type); **Settings** (3 palettes + AI
  provider, local on desktop / remote on web).

## Key interactions
- Switch mode → shell re-skins; run a mode pipeline (confirmed); branch/restore a
  Stage; dictate → preview → commit; export with a pre-flight; search & jump.

## Data
`WritingModeDTO` (re-skin metadata), `ExportRequestDTO`/`ExportResponseDTO`,
plus the per-mode review aggregations.

## Acceptance
The same workspace convincingly becomes five products; Stages reads as
story-versioning; Voice is a desktop HUD; Export is a clear, validated flow.
