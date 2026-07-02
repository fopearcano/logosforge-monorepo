# LogosForge Studio — Design Tickets (for Claude Design)

These tickets trim `STUDIO_UI_DESIGN_BRIEF.md` into **focused design tasks** — one
sitting per ticket. Read the brief first (it has the full feature detail); each
ticket scopes *what to design* and which `pro-shared-ui` components it fills.

## How to use
1. Read `STUDIO_UI_DESIGN_BRIEF.md` (the full spec) and `src/theme/tokens.ts`
   (starting design tokens).
2. Pick a ticket below. Design its screens/panels as Figma frames.
3. Keep the **global directives** (next section) true in every frame.
4. Each ticket names the `src/components/*` stub(s) the recode step will fill.

## Global directives (apply to every ticket)
- **Identity:** dark-first, cinematic, dense, **minimal-cyber / terminal** — a
  *writing workstation*, not a calm doc. **Never resemble the Whiteboard (Free)
  line**; the two lines share no UI.
- **Workspace model (Ticket 01 owns it):** dockable, tile-able panels — left
  **Navigator** rail, center **editor**, right **intelligence dock**, bottom
  **analysis dock**; **Focus ↔ Cockpit** layouts; two always-on omni-inputs
  (**Command Palette** `/`, **PSYKE Console** omnibox).
- **Shared primitives (design once, reuse):**
  - **Severity grammar** (blocking→warning→suggestion→opportunity→info) — used by
    Decision Radar, Continuity, validations. Tokens in `theme/tokens.ts`.
  - **Confidence grammar** (high/medium/low) — derived facts (graph, continuity).
  - **The universal Diff / Impact Confirm modal** — *every* content change
    (rewrites, applies, generated outlines) goes through preview → diff → impact
    → confirm. One excellent modal, reused everywhere.
  - **Per-mode accent bands** — the shell re-skins by writing mode (novel /
    screenplay / graphic_novel / stage_script / series).
- **Density done right:** rich live signal, quiet by default — insight lives in
  thin dismissible banners + dockable HUD widgets, never modal nags.
- **Keyboard-first:** Command Palette + PSYKE Console drive everything.

## Code conventions (scaffolded — design to match)
- **Frame labels = screen ids.** Each panel's component carries a kebab-case
  `data-screen-label` (e.g. `manuscript-editor`, `decision-radar`); label the
  matching Figma frame the same so design comments map straight to code. The
  stub `screenLabel`s in `src/components/*` are the canonical ids.
- **One accent variable per mode.** Accents are `var(--accent)`, scoped from the
  active writing mode — so the per-mode accent bands are driven by a single
  variable. Design the bands knowing they're one swappable token.

## Tickets
| # | Area | Brief § | pro-shared-ui components |
|---|---|---|---|
| **01** | Workspace shell & navigation | §2, §8 | `workspace.tsx` (WorkspaceShell, Navigator, CommandPalette, ModeStrip) |
| **02** | Manuscript editor & writing intelligence + outline/structure/notes | §4.1–4.2 | `editing.tsx` (ManuscriptEditor, StoryGrid, OutlinePanel, StructurePanel, NotesPanel) |
| **03** | Timeline, Plot & Knowledge Graph (the spatial canvases) | §4.3, §4.8 | `spatial.tsx` (TimelinePanel, CanvasPlot, KnowledgeGraph) |
| **04** | PSYKE story bible | §4.4 | `psyke.tsx` (PsykeBible, PsykeInspector) + `workspace.tsx` PsykeConsole |
| **05** | AI surfaces + Quantum Outliner | §4.6, §5 | `ai.tsx` (AssistantDock, ChatPanel, CounterpartPanel) + `spatial.tsx` QuantumOutliner |
| **06** | Narrative intelligence & the Project OS | §4.7, §4.9 | `intelligence.tsx` (all) + `ai.tsx` (DecisionRadar, GuidedWorkflowStepper, DiffConfirmModal, ContinuityPanel) |
| **07** | Format engines, Stages, Voice, Export & cross-cutting | §4.5, §4.10–4.15, §6 | `formats.tsx` (all) |

## Recommended order
01 (shell — everything docks into it) → 02 (the writing core) → 04 (PSYKE) →
03 (spatial canvases) → 05 (AI + Quantum) → 06 (intelligence + Project OS) →
07 (formats/stages/voice/export). Design the **Diff/Impact Confirm** modal early
(Ticket 06) — many tickets reuse it.
