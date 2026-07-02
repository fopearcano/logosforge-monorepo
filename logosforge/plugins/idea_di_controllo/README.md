# Idea di Controllo

PSYKE-aware narrative compass for Logosforge. Implements McKee's **Controlling
Idea**: a single sentence of `VALUE + CAUSE` that the whole story turns on.

> *"Justice prevails when the hero sacrifices personal safety for truth."*

This plugin lets you define that idea once per project, then uses it as a
guiding constraint for the Assistant, PSYKE, and Plot/Manuscript views.

## What it adds

- **Project-level Controlling Idea** stored in `Project.settings_json`
  (no schema change). Fields: `value`, `cause`, `statement`, `counter_idea`,
  `value_charge` (positive | negative | ambiguous), `notes`, and alignment maps
  for scenes and PSYKE entries.
- **`/idea` slash commands** in the PSYKE console:
  - `/idea` — show current idea
  - `/idea set value="…" cause="…" counter_idea="…" notes="…"`
  - `/idea explain` — context block as the Assistant sees it
  - `/idea check` — alignment report (supports / opposes / tests /
    transforms / weak)
  - `/idea link [entry_id] [supports|opposes|tests|transforms]` —
    create or update the PSYKE *theme* entry, optionally tag another PSYKE
    entry's alignment
  - `/idea scene <scene_id> <supports|opposes|tests|transforms|clear>`
- **Assistant toggle** "Idea di Controllo" (in the settings panel, next to
  PSYKE / Story Memory / Go Irrational). Default ON when the plugin is
  enabled. When checked, the Assistant context includes a compact
  `[Idea di Controllo]` block.
- **Menu actions** (Plugins menu):
  - *Show* — display the current idea
  - *Check* — open the alignment report
  - *Create / Update PSYKE Theme* — sync a PSYKE entry of type `theme`

## PSYKE integration

The plugin creates **one** PSYKE entry of type `theme` named
`Controlling Idea — <value>`. It is stored like any other PSYKE entry — no
duplication. Its id is remembered in the CI settings so further updates
reuse it.

Per-PSYKE-entry alignment (supports / opposes / tests / transforms) is
stored on the CI side, not on PSYKE entries. The plugin never silently
rewrites PSYKE data.

## Go McKee

If the **Go McKee** plugin is loaded at runtime, the Assistant context
appends a single hint line telling the model to treat the Controlling
Idea as the highest-priority story constraint. The plugin works on its
own when Go McKee is absent.

## Safety

- All write actions are explicit (`/idea set`, `/idea link`, `/idea scene`,
  or menu actions).
- The Assistant uses the Controlling Idea operationally — to evaluate
  suggestions, not to lecture about theory.
- New projects start with no Controlling Idea; nothing leaks between
  projects.
