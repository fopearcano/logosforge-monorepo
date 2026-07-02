# Ticket 02 — Manuscript editor, writing intelligence, outline & structure

> Brief: §4.1 (manuscript), §4.2 (outline/structure). Fills
> `src/components/editing.tsx`.

## Goal
The writing core: a focused manuscript editor surrounded by live, non-intrusive
intelligence, plus the Act→Chapter→Scene structure (which is **scene-derived** —
there are no Act/Chapter tables).

## Screens / panels
- **Manuscript Editor** — continuous scene/prose editor. Inline: `[[Entity]]`
  link chips + hover cards (PSYKE data), an **energy heatline** (tension/pacing/
  conflict), a floating format toolbar on selection, an **inline AI edit bar**
  for selection rewrites. Grammar is **deferred/disabled** — show style flags,
  not grammar.
- **Story Grid** — 3-column block grid grouped by Acts (bird's-eye manuscript).
- **Outline Panel** — Act→Chapter→Scene tree/board with template presets and
  AI-generated outlines that land via the Diff/Impact Confirm modal (Ticket 06).
- **Structure Panel** — the spine + a structure-health sidebar (orphans,
  "Unassigned" bucket).
- **Notes Panel** — notes with PSYKE/scene links + pinning.

## Key interactions
- Type/edit; select → format/AI bar; click an entity chip → jump/inspect; drag to
  reorder scenes; pick a template; accept a generated outline (diff-confirmed).

## Data
`SceneDTO` (full record incl. `goal/conflict/outcome/beat/tags/plotline`),
`OutlineNodeDTO` (nested), `NoteDTO`. Paragraph-energy/style come from analysis.

## Acceptance
A serious long-form editor that feels alive but quiet; the structure reads as
scene-derived; AI changes are always preview-then-confirm.
