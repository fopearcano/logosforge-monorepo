# Ticket 04 — PSYKE story bible

> Brief: §4.4. Fills `src/components/psyke.tsx` (PsykeBible, PsykeInspector) and
> the **PSYKE Console** in `workspace.tsx`. One of Studio's richest surfaces.

## Goal
The story bible: characters, places, objects, lore, themes — with relations,
progressions, and scene references — plus an omnibox console to drive it all.

## Screens / panels
- **PSYKE Bible** — browser with search/filter by type; an entry editor (name,
  type, aliases, notes, per-type `details` fields); the entry's **relations**
  and **progressions** (state across scenes); scene references.
- **PSYKE Inspector** — a docked panel for the *current* entry: a compact
  relations graph + a progression timeline; quick edit.
- **PSYKE Console** — an omnibox: live fuzzy search dropdown + natural-language
  commands and system commands (`/create`, `/open`, `/go`, `/ai`); keyboard-first.

## Key interactions
- Search/filter; create/edit (per-type detail forms); add a typed relation
  between two entries; add a progression pinned to a scene; click through
  relations; run console commands.

## Data
`PsykeEntryDTO` (type ∈ character/place/object/lore/theme/other; `details` varies
by type), `PsykeRelationDTO` (typed edges), `PsykeProgressionDTO` (scene-pinned).

## Acceptance
A bible that scales to hundreds of entries; relations + progressions are the
stars; the console makes it fast and keyboard-driven.
