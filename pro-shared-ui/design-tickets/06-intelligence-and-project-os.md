# Ticket 06 — Narrative intelligence & the Project OS

> Brief: §4.7 (analytics), §4.9 (Project OS). Fills `src/components/intelligence.tsx`
> + the Project-OS parts of `ai.tsx` (DecisionRadar, GuidedWorkflowStepper,
> DiffConfirmModal, ContinuityPanel). **Design the Diff/Impact Confirm modal here
> — many tickets reuse it.**

## Goal
Make the deterministic "Project Operating System" loop legible as a calm cockpit:
**Understand → Decide → Act → Verify → Apply safely.** Much of this has **no UI
today** — it's the greenfield heart of Studio.

## Screens / panels
- **Narrative Dashboard** + small HUD widgets — **Story Health**, **Pacing
  Insights**, **Beat/Act/Tag** coverage, **Character Arc & Balance**. Heavy,
  beautiful charting; quiet by default.
- **Decision Radar** — a ranked dock of **severity-colored** decision cards
  (blocking→warning→suggestion→opportunity→info), each traceable to its source.
- **Guided Workflow Stepper** — resumable, mode-aware step path; deterministic
  steps auto-tick, creative steps stay the user's; jump to the relevant panel.
- **Continuity Panel** — contradictions / structural breaks / missing transitions,
  with most-affected scenes; feeds Decision Radar.
- **Diff / Impact Confirm modal (the universal apply path)** — preview → **diff**
  → **Change Impact Map** (scene dependencies, setup/payoff, PSYKE & continuity
  impact) → confirm. STAGE checkpoint + force-override affordances. **Every**
  content mutation (rewrites, applies, generated outlines) routes through this.

## Key interactions
- Scan the radar; start a workflow; tick/verify steps; open a continuity issue;
  and — everywhere — preview→diff→impact→confirm before any change lands.

## Acceptance
The OS reads as one calm conductor, not notification spam. The Diff/Impact modal
is excellent and obviously reusable. Severity/confidence grammar is consistent.
