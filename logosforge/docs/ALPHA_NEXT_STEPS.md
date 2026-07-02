# Alpha — Next Steps

**Status:** Post-consolidation / post-rollback stable checkpoint.
**Gate:** see `docs/research/ai_screenwriting/P0_STABILIZATION_GATE.md`.
**Backlog:** see `docs/research/ai_screenwriting/NON_NOVEL_MODES_BACKLOG.md`.

This is the short, operational summary. The full reasoning lives in the
`docs/research/ai_screenwriting/` chain (Research Summary → Audit → Comparison →
Roadmap → Backlog → P0 Gate).

---

## Do Immediately (the P0 gate)

1. **Run the full automated suite and keep it green.** This is the unlock condition for
   any non-novel mode work. The targeted P0 subset
   (isolation / manuscript / outline-leak / autosave / editing-integrity / PSYKE /
   projects-section / refresh) is the fast gate; the full suite is the merge gate.
2. **Do a one-pass manual smoke** of the two environment-sensitive behaviors:
   - **Undo/Redo via the Edit menu** while the cursor is in each editor (Manuscript
     scene editor, Outline fields, PSYKE console). Confirm the focused editor responds.
   - **Close a project with unsaved edits** → confirm the Save / Don't Save / Cancel
     prompt appears, Cancel aborts the close, and autosave does **not** suppress it.
3. **Confirm the gate's acceptance criteria 1–9** (P0 doc §C). Criteria 1–8 are met in
   code + tests today; criterion 9 is this run/click confirmation.

When the suite is green and the smoke pass is done, the gate is **OPEN**.

---

## Do NOT Touch (until the gate is OPEN)

- ❌ Manuscript — **no** further refactor; it was rolled back to a safe state.
- ❌ The Chapter/Scene primary-unit adapter — **only** touch if a failing test proves
  it broken (it passes today).
- ❌ Separate Chapters/Scenes main sections — they are consolidated into Outline; keep
  them as node types, not sections.
- ❌ Timeline / Canvas Plot redesigns.
- ❌ New storage migrations (additive `create_all` only; nothing destructive).
- ❌ New AI agents/systems; Control Room / Showrunner / Director features.
- ❌ New Screenplay / Graphic Novel / Stage / Series feature expansion.

Rationale: these are exactly the surfaces whose stability is the app's strongest match
to the research (outline-before-writing + leak-free, human-controlled editing).

---

## Test Manually (focused smoke list)

| Behavior | What to check |
|---|---|
| **Project switch** | A→B→A shows no stale Outline / Manuscript / PSYKE / Assistant / Logos data |
| **New project** | Empty Outline, no chapters, no scenes, clean PSYKE/Assistant |
| **Outline → Manuscript** | Generate/edit Outline → Manuscript body stays empty until written; no summary shown as body |
| **Undo/Redo (menu)** | Works in the focused editor even after the menu takes focus |
| **Dirty close** | Save / Don't Save / Cancel prompt; Cancel aborts; autosave doesn't suppress |
| **Save As** | Clears the dirty `*`; new card appears in the project list |
| **PSYKE refresh** | Console input cleared, dropdown hidden, index rebuilt on switch |
| **Export** | Reads active project only; warnings inform but don't block |

---

## Implement ONLY After Stabilization

In dependency order (backlog IDs in parentheses). All stay in the **Python core/API**:

1. **Outline canonical structure** — render the engine hierarchy in Outline
   (`NNM-010`, `NNM-011`). No new sections.
2. **Shared scene/beat planning layer** — additive planning rows + shared
   validate-before-apply + planning/body invariant (`NNM-012`, `NNM-013`, `NNM-014`).
3. **Screenplay mode** — outline → scene plan → formatted draft; wire the pro Fountain
   exporter; surface dialogue/action + visual-action checks (`NNM-020…024`).
4. **Graphic Novel mode** — page/panel unit + Outline hierarchy; panel-script export
   (`NNM-030…033`).
5. **Stage Script mode** — Outline hierarchy; **wire `/stage` review** (low-risk early
   win, `NNM-041`); entrances/exits + prop checks; play-format export (`NNM-040…044`).
6. **Series mode** — season/episode hierarchy + Episode unit; arcs as causal/graph
   edges; episode/season exports (`NNM-050…054`).
7. **Reflection** (cross-cutting) — surface Counterpart (read-only); per-mode Assistant
   context; mode-aware Logos; confirm-gated apply everywhere (`NNM-060…064`).
8. **React/Electron transfer** — enforce headless core + API apply gate now
   (`NNM-080…082`); **defer** the UI build, ComfyUI, cloud sync, and the autonomous
   experience-role critic (`NNM-065/073/083/084`).

**Deferred to React/Electron commercial UI:** `NNM-065`, `NNM-073`, `NNM-083`,
`NNM-084` — do not build in the PySide alpha.

---

## Recommended Next Implementation Prompt

> "IMPLEMENT — Milestone 2 / NNM-011: Make the Outline (PlanView) render each writing
> mode's engine hierarchy via `engine_structural_units(engine)` instead of hardcoded
> Act→Chapter. Non-destructive; keep the scene-derived fallback; Chapters/Scenes remain
> node types inside Outline (no new sections); preserve the Chapter/Scene adapter; add
> per-mode hierarchy-render tests. Do not touch Manuscript. Do not migrate storage."

(Only issue this **after** the P0 gate is OPEN. `NNM-010` may precede it if the
unit-label adapter needs the true per-mode vocabulary first.)

---

*This document is operational guidance only; it changes no runtime behavior.*
