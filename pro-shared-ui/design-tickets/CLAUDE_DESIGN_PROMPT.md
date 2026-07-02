# Prompt to paste into a new Claude Design session

> Link the **`pro-shared-ui`** folder to the session first (it contains the
> brief, the tickets, and the design tokens). Then paste the prompt below.

---

You are designing the UI for **LogosForge Studio** — the "Pro" / power-user line
of a local-first writing app. I've linked the `pro-shared-ui` folder; everything
you need is in it.

**Read first (in the linked folder):**
- `STUDIO_UI_DESIGN_BRIEF.md` — the complete spec: product vision, information
  architecture, data model, per-feature panel detail, the five writing-mode
  re-skin, and design-language guidance (~1,800 lines).
- `design-tickets/00-INDEX.md` — the work split into 7 focused tickets + the
  global design directives. Each ticket names the screens to design.
- `src/theme/tokens.ts` — starting design tokens (dark-first palette;
  severity/confidence/per-mode colors; spacing, type, z-index).

**What Studio is:** the *complete*, dense, cinematic writing **workstation** — a
dockable, panel-based "DAW / IDE for storytelling": a manuscript editor ringed by
live intelligence panels (structure, PSYKE story-bible, timeline/plot canvas,
knowledge graph, quantum branching, AI assistants, decision radar, analytics,
voice). It's organized around a deterministic "Project Operating System" loop:
Understand → Decide → Act → Verify → Apply.

**Identity & constraints — keep true in every frame:**
- Dark-first, cinematic, **minimal-cyber / terminal** — precise, dense, composed.
  A workstation, not a calm document.
- A **distinct visual identity** — do NOT resemble or reuse the minimal
  "Whiteboard" (Free) product; the two lines never share UI.
- **Platform-neutral** — it runs in both an Electron desktop and a browser;
  design layouts that work in both (no OS-chrome assumptions).
- **Workspace model:** left Navigator rail · center editor · right intelligence
  dock · bottom analysis dock; **Focus ↔ Cockpit** layouts; two always-on
  omni-inputs (Command Palette `/`, PSYKE Console omnibox); the shell **re-skins
  per writing mode** (novel / screenplay / graphic-novel / stage-script / series)
  via accent bands.
- **Shared primitives — design once, reuse:** the **severity grammar**
  (blocking → warning → suggestion → opportunity → info), the **confidence
  grammar**, and the **universal Diff / Impact Confirm modal** (every content
  change previews → diffs → shows impact → confirms).
- **Density done right:** rich live signal, quiet by default — insight in thin
  dismissible banners + dockable HUD widgets, never modal nags. Keyboard-first.

**Deliverables:** Figma frames, one ticket at a time. **Start with Ticket 01
(the workspace shell)** — everything docks into it — then follow the recommended
order in `00-INDEX.md`. Design the **Diff/Impact Confirm** modal early (Ticket
06); many surfaces reuse it. Use the tokens as a palette baseline (refine freely
— you own the final visual). For each ticket, design the named screens/panels;
the index maps each to a `src/components/*` file for the later code step.

Begin by reading `STUDIO_UI_DESIGN_BRIEF.md` and `design-tickets/00-INDEX.md`,
then design **Ticket 01 — Workspace shell & navigation**.
