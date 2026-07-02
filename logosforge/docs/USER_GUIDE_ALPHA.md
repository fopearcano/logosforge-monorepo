# Logosforge — User Guide (Alpha)

Version **0.9.0-alpha**. A practical walkthrough of the desktop app. This is alpha
software — **export a backup before serious writing** (File → Export → JSON /
Full Project).

The left **sidebar** navigates sections; the **Assistant** docks on the right; a
slim **PSYKE console** sits at the bottom.

## Create / open a project

- **New:** Projects → *New Project*. Give it a title and pick a **Writing Mode**
  (see below). New projects open on the Dashboard.
- **Open:** Projects → *Open*, or pick from recent. A project already open
  elsewhere opens **read-only** (a lock protects your data).
- Switching projects clears all stale state automatically.

## Choose a Writing Mode

Each project declares one mode (it shapes every section and the AI):

- **Novel** — Acts / Chapters / Scenes
- **Screenplay** — Acts / Sequences / Scenes (Fountain-style export)
- **Graphic Novel** — Issues / Chapters / Pages / Panels (adds a **Pages** section)
- **Stage Script** — Acts / Scenes / Beats / Entrances·Exits / Cues
- **Series** — Seasons / Episodes / A·B·C plots / Arcs

Change it later in Project Settings; sections and the manuscript adapt. See
[WritingModes.md](WritingModes.md).

## Manuscript

The main editor — a continuous, distraction-free canvas of scenes.

- **Type freely.** Edits autosave on a short debounce; the editor never greys out
  or steals focus.
- **Toolbar:** format badge, element selector, A‑P (text/paragraph), Review,
  Focus, and **Text/Bg** (font, size, colour, background — including custom model
  fonts).
- **Focus mode** hides the chrome for deep work.
- **Grammar / Style** toggles live under the **Review** menu (basic, rule-based).
- Export from the toolbar / File → Export.

## Outline

Act/chapter/scene structure. The AI can **generate or extend** an outline
(engine-aware, template-driven); changes are previewed and confirmed before they
become scenes — nothing is applied silently.

## Plot

Multi-plot / plot-block view (derived from each scene's `plotline`). Edit plot
membership and see how threads run through the story.

## Timeline

Scene-order timeline with scene summaries. (Alpha: timeline is derived from scene
order — there is no separate event-date model yet.)

## PSYKE (Story Bible)

Characters, places, objects, lore, themes — with notes, aliases, relations and
temporal progressions. The Assistant and continuity checks read PSYKE. Use the
bottom **PSYKE console** to search entries quickly (type a name; characters and
places appear as suggestions). Creating/editing entries updates suggestions and
Assistant context immediately.

## Notes

Free-form project notes (with tags). Notes can feed Assistant context (toggle in
Assistant settings) and surface in the Knowledge Graph.

## Assistant

The explicit right-panel AI: chat, engine-aware critique, inline editing, and
**safe propose-then-confirm** actions (e.g. *Apply to Outline*). It uses one
shared provider (see [AI_SETUP.md](AI_SETUP.md)). The Assistant **responds in the
language you write in**. Context (PSYKE, outline, notes, …) is capped and
toggleable; nothing is auto-applied without your confirmation.

## Logos

The **inline, contextual** AI layer — a left-panel **ON/OFF toggle**, not a
separate page. When ON, it shows an inline toolbar + ambient suggestions scoped
to the section you're in (deterministic diagnostics, health, strategy). It
previews/confirms; it never auto-applies. Turn it off to write undisturbed.

## Counterpart

A **dialogic critic** mode inside the Assistant panel (the *Counterpart* button)
— pushes back on your choices rather than just agreeing.

## Connector

A local **app-control bridge** (run read actions by command). **Write actions are
OFF by default** — enable them only deliberately in Connector settings.

## Quantum

The **Quantum Outliner** (the *Quantum* button in the Assistant panel) explores
plotting/outline branches with lookahead scoring — a structural brainstorming
mode.

## Export

File → Export offers **Markdown, TXT, Fountain (screenplay), FDX, HTML, JSON,
CSV**, plus **PDF/DOCX** (need optional libraries). Data exports (Story Elements,
PSYKE, Full Project) are under the data-export menu. The export path is shown
after each export; failures show a readable message. Exports contain **no API
keys**. See [Interchange.md](Interchange.md).

## Backup / restore

- **Snapshots:** automatic + manual project version snapshots (Version History).
  Restore is explicit, takes a pre-restore safety snapshot, and loads the
  snapshot as a **new project** (never overwrites your current one).
- **Portable backup:** export *Full Project (JSON)* and keep copies. Re-import
  creates a new project.

See [BackupRestore.md](BackupRestore.md) and [AutosaveVersioning.md](AutosaveVersioning.md).

## Troubleshooting

Common issues (AI timeouts, provider setup, export failures, slow local models)
are covered in **[TROUBLESHOOTING.md](TROUBLESHOOTING.md)**.
