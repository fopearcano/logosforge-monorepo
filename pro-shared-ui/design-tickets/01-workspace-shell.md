# Ticket 01 — Workspace shell & navigation

> Brief: §2 (IA), §8 (nav). Fills `src/components/workspace.tsx`. This ticket
> defines the frame every other panel docks into — do it first.

## Goal
The dockable Studio shell: a writing workstation that re-skins by writing mode,
with two always-on omni-inputs and Focus ↔ Cockpit layouts.

## Screens / panels
- **Workspace Shell** — left Navigator rail · center editor region · right
  intelligence dock (tabbed/stacked) · bottom analysis dock. Panels are
  movable/tile-able; layout persists per project. Provide **Focus** (editor only)
  and **Cockpit** (all docks) presets.
- **Navigator** — icon rail + collapsible section tree: Dashboard · Write ·
  Structure · Scenes · Plot/Timeline · PSYKE · Graph · Quantum · Stages · Reviews
  · Notes · Search · Voice · Plugins · Settings. Show the active **writing mode**.
- **Command Palette** — `/`-triggered popup of writing actions (fuzzy, keyboard).
- **Mode Strip** — compact adaptive-AI mode indicator with a manual override.

## Key interactions
- Drag-dock/tear-off panels; collapse the rail; switch Focus/Cockpit; remember
  layout. Keyboard: open palette (`/`), open PSYKE Console, jump sections.
- The shell's **accent band** changes with the writing mode (per-mode tokens).

## Data
`ProjectDTO` (active project + `narrative_engine`), `WritingModesResponseDTO`
(mode catalog/labels), live `EventMessage` stream (reactive panels).

## Acceptance
A believable empty-state workstation: docked panels, the two omni-inputs, the
mode-aware accent, Focus/Cockpit. Dense but calm.
