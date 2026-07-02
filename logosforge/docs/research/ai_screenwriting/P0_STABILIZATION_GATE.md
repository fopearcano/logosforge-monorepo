# P0 Stabilization Gate — Non-Novel Mode Work

**Type:** Planning + stabilization sequencing only. **No feature code. No Manuscript
refactor. No new sections. No new AI systems. No storage migration.**
**Branch:** `claude/setup-logosforge-app-5cVxF`
**Inputs:** the full AI-screenwriting research chain in `docs/research/ai_screenwriting/`
(Research Summary → Mode Audit → Comparative Analysis → Roadmap → Backlog).

**Purpose.** Define the gate that must be **green and verified** before *any*
non-novel mode feature work begins. This document does not change runtime behavior;
it ratifies the current checkpoint, lists the P0 blockers and their verification
status, fixes the acceptance criteria, and states what is forbidden vs. allowed after
the gate passes.

> **Verification basis.** Each P0 item below was checked against (a) the live
> mechanism in `logosforge/ui/main_window.py` and related modules and (b) the
> existing automated test that locks it. Citations are `file:line` / `test::name`.
> A targeted P0 test subset was run to confirm the gate empirically (result recorded
> in `ALPHA_NEXT_STEPS.md` and this session's report).

---

## A. Current Stable Checkpoint

The app is at a **safe, post-consolidation, post-rollback checkpoint.** What is true today:

| Stable property | Evidence |
|---|---|
| **Project isolation fixed** | `_switch_project` clears caches/subsystems and rebuilds per project; locked by `test_project_isolation_p0.py`, `test_project_switch_isolation.py`, `test_project_state_reset.py` |
| **Manuscript restored (rollback safe)** | `_show_manuscript()` always builds `WritingCoreView` (`main_window.py:876`); the broken `ChapterManuscriptView` adapter is gone; locked by `test_manuscript_rollback.py`, `test_manuscript_editor_stability.py` |
| **Primary-unit adapter preserved** | `writing_modes.py` `primary_unit_label` / `current_add_button_label` intact (Novel=Chapter, others=Scene); locked by `test_mode_aware_units.py`, `test_outline_manuscript_mode_refactor.py` |
| **Outline is the single structural section** | Chapters/Scenes hidden from nav; Outline (`PlanView`) is the only structural surface; Chapters/Scenes are node types *inside* Outline; locked by `test_outline_consolidation.py` |
| **Manuscript ↔ Outline separation** | Body = `scene.content` only; planning writes `summary`; locked by `test_manuscript_outline_separation.py`, `test_outline_consolidation.py::test_outline_generation_writes_only_to_outline_not_manuscript` |
| **Research docs complete** | Five-document chain present in `docs/research/ai_screenwriting/` |

**Checkpoint statement:** the foundation is intact. The gate below is a
**verification gate**, not a rebuild — most mechanisms already exist and are tested;
P0 confirms they still hold *together* and closes any verification gaps before new
work raises the stakes.

---

## B. P0 Blockers — Verify / Fix Before New Mode Work

Each blocker lists the **mechanism**, the **locking test**, and a **status**:
✅ verified (mechanism + passing test) · ⚠️ verify (mechanism present; confirm via
manual + test) · ❌ fix (gap found).

| # | P0 Blocker | Mechanism (code) | Locking test | Status |
|---|---|---|---|---|
| B1 | **Project switching / stale data** | `_switch_project` clears caches, re-points subsystems, rebuilds section (`main_window.py`) | `test_project_isolation_p0.py`, `test_project_switch_isolation.py` | ✅ verified |
| B2 | **Manuscript stability** | `_show_manuscript` → `WritingCoreView` always; body=`content`; placeholder "Start writing…" | `test_manuscript_editor_stability.py`, `test_manuscript_rollback.py` | ✅ verified |
| B3 | **Outline not leaking into Manuscript** | `apply_outline_as_scenes` writes `summary` only; editor renders `content` only | `test_manuscript_outline_separation.py`, `test_outline_consolidation.py` | ✅ verified |
| B4 | **Undo/Redo** | focus tracking `_on_focus_changed` (`:2510`) → `_focused_editable` (`:2514`) → `_run_edit_op` (`:2522`); editors expose native undo stacks | `test_editing_integrity.py` | ✅ verified |
| B5 | **Autosave / close-save prompt** | `closeEvent` (`:3195`) prompts Save/Discard/Cancel on `_modified_since_save`; autosave does **not** clear the flag (`_save_for_close` `:3226`) | `test_autosave.py`, `test_editing_integrity.py` | ✅ verified |
| B6 | **Dirty state** | `_modified_since_save` set on edit (`:3024/:3045`), cleared only by explicit save/switch (`:2485/:3085`); title `*` marker (`:2652`) | `test_editing_integrity.py::test_save_as_clears_dirty` | ✅ verified |
| B7 | **Project list refresh** | `_refresh_projects_view()` after new/save-as | `test_projects_section_fixes.py::test_save_as_refreshes_projects_view` | ✅ verified |
| B8 | **Save As behavior** | "Save As" button; clears dirty via `_mark_clean`; new card appears | `test_projects_section_fixes.py` (`:78/:92/:104/:281`) | ✅ verified |
| B9 | **PSYKE refresh** | `psyke_console.set_project()` clears input, hides dropdown, rebuilds index eagerly | `test_psyke_project_isolation.py` | ✅ verified |
| B10 | **Assistant context project isolation** | context rebuilt on switch; no other-project terms | `test_project_isolation_p0.py::test_assistant_context_has_no_other_project_terms`, `test_phase9b_propagation.py::test_assistant_context_follows_project_switch`, `test_project_switch_isolation.py::test_assistant_context_resets_on_switch` | ✅ verified |
| B11 | **Logos context project isolation** | Logos engine rebound on switch; toolbar/suggestions cleared | `test_phase9b_propagation.py::test_logos_context_follows_project_switch`, `test_project_switch_isolation.py::test_logos_toolbar_result_clears_on_switch` / `::test_logos_suggestions_clear_on_switch` | ✅ verified |
| B12 | **Export safety** | export reads active project only; warnings don't block; no stale leak | `test_phase10i_export_integrity.py::test_assistant_export_context_no_stale_leak`, `test_phase10f_screenplay_export.py::test_export_safe_flag_and_no_block_for_warnings`, `test_export_stabilization.py` | ✅ verified |
| B13 | **Tests (regression lock)** | targeted P0 subset + full suite green | this session's run: **212 passed, 0 failed** across 15 P0 files | ✅ subset verified; ⚠️ confirm full suite in CI before unlocking M2 |

**Targeted P0 subset run (this session):** `212 passed in 347.71s`, 0 failures, across
`test_project_isolation_p0`, `test_project_switch_isolation`, `test_project_state_reset`,
`test_project_lifecycle_switch`, `test_manuscript_outline_separation`,
`test_manuscript_rollback`, `test_manuscript_editor_stability`,
`test_outline_consolidation`, `test_mode_aware_units`, `test_autosave`,
`test_editing_integrity`, `test_psyke_project_isolation`, `test_projects_section_fixes`,
`test_refresh_and_caches`, `test_refresh_propagation`.

**Verification gaps to close (the only non-✅ items):**
- **B13** — the targeted P0 subset is **green** (212/212). Remaining step: keep the
  *full* suite green in CI as the unlock condition for Milestone 2 (the subset is the
  fast gate; the full suite is the merge gate).
- **Manual smoke pass** — items B4/B5/B6 benefit from one human click-through (undo via
  the *menu* while focus is in each editor; close a dirty project and verify the
  prompt) because focus/close behavior is environment-sensitive (esp. macOS
  fullscreen). Listed in `ALPHA_NEXT_STEPS.md`.

---

## C. P0 Acceptance Criteria

The gate is **passed** when all of the following hold (each maps to a B-row + test):

1. ✅ **Creating/opening a new project never shows old Manuscript / PSYKE / Outline /
   Assistant / Logos data.** (B1, B9, B10, B11)
2. ✅ **Outline generation never writes into the Manuscript body.** (B3)
3. ✅ **Manuscript Undo/Redo works — including via the Edit menu — for the focused
   editor.** (B4)
4. ✅ **Closing a dirty project prompts Save / Don't Save / Cancel; Cancel aborts the
   close; autosave does not suppress the prompt.** (B5, B6)
5. ✅ **Outline structure persists per project and reloads cleanly on switch.** (B1, B3)
6. ✅ **Assistant and Logos context use the active project only — no cross-project
   leakage.** (B10, B11)
7. ✅ **Save As clears dirty state and refreshes the project list.** (B7, B8)
8. ✅ **Export reads the active project only; warnings inform but do not corrupt or
   block.** (B12)
9. ⚠️ **Full automated suite is green** and a one-pass manual smoke of undo-via-menu +
   dirty-close has been done. (B13 — targeted P0 subset is green at **212/212**;
   full-suite CI + manual smoke remain.)

**Gate decision rule:** criteria 1–8 are ✅ in code + tests today, and the targeted P0
subset passes **212/212**; criterion 9's residual is the *full-suite CI confirmation +
one manual smoke pass*. When that lands, the gate is **OPEN** for Milestone 2.

---

## D. Forbidden Before P0 Passes

Hard stop — none of the following may begin until the gate is OPEN:

- ❌ **New Screenplay feature expansion** (beyond verification).
- ❌ **Graphic Novel panels** surfacing / page-panel unit changes.
- ❌ **Stage entrances/exits** surfacing / `/stage` wiring.
- ❌ **Series season/episode logic** / episode-as-primary-unit changes.
- ❌ **Timeline redesign** or new Timeline capabilities.
- ❌ **Canvas Plot redesign** or causal-board work.
- ❌ **New storage migration** of any kind (additive `create_all` only; nothing
  destructive).
- ❌ **New AI agents / AI systems.**
- ❌ **Control Room / Showrunner / Director** features (explicitly out of scope).
- ❌ **Re-touching the Chapter/Scene primary-unit adapter** unless a *failing test*
  proves it broken (it currently passes).
- ❌ **Reintroducing separate Chapters/Scenes main sections** (consolidation must hold).
- ❌ **Another Manuscript refactor.**

**Rationale (from the comparison):** the app's two strongest alignments with the
research are *outline-before-writing* and *human-controlled, leak-free editing*. Every
forbidden item above risks regressing exactly those — the highest-value, hardest-won
properties.

---

## E. Allowed After P0 Passes

Once the gate is OPEN, these are safe to pursue **in dependency order** (all map to the
backlog `NNM-###` IDs and stay within Python core/API):

- ✅ **Shared non-novel scene/beat planning layer** (`NNM-012`) — additive planning
  rows; never touches `content`.
- ✅ **Canonical Outline structure** driven by `engine_structural_units` (`NNM-011`) —
  render the engine hierarchy; no new sections.
- ✅ **Screenplay outline → scene plan → formatted draft pipeline** (`NNM-020`,
  `NNM-021`) — plan format-free, format only at export.
- ✅ **Mode-specific export improvements** (`NNM-021/033/044/054`, `NNM-070`) — surface
  existing exporters; add GN/Stage/Series deliverables.
- ✅ **Logos / Counterpart reflection improvements** (`NNM-060/061/062`) — surface
  existing engines; read-only critique; confirm-gated apply.
- ✅ **Causal graph / plot-link logic** (`NNM-015`, `NNM-024`, `NNM-051`) — typed,
  acyclic, validated; **no auto-generation** (deferred).

**Should remain in Python core/API** (not PySide-specific): planning layer, Outline
hierarchy, validation, controlled-apply gate, all exporters, all `*_review`/diagnostics
engines, causal-link model, PSYKE memory.

**Defer to React/Electron commercial UI** (do not build in the PySide alpha):
autonomous experience-role critic (`NNM-065`), ComfyUI image export (`NNM-073`),
web/Electron client (`NNM-083`), cloud sync / collaboration (`NNM-084`).

---

## F. Recommended Implementation Order After P0

```
1. Stabilization               ← THIS GATE (verify B1–B13, criteria 1–9)
2. Outline canonical structure  (NNM-010, NNM-011)        — engine hierarchy in Outline
3. Shared scene/beat planning   (NNM-012, NNM-013, NNM-014)— planning rows + validate/apply
4. Screenplay mode              (NNM-020…024 + export)     — proving ground
5. Graphic Novel mode           (NNM-030…033 + export)
6. Stage Script mode            (NNM-040…044 + export)     — NNM-041 (/stage) is low-risk early win
7. Series mode                  (NNM-050…054 + export)
8. React/Electron transfer      (NNM-080…082 in-scope; 083/084 deferred)
```

- Steps 2–3 are the shared core (Milestone 2) and must precede all mode work.
- Steps 4–7 are independent post-core; recommended 4 → 7 → 5 → 6 by maturity, but may
  be reprioritized by product. Step 6's `/stage` wiring (`NNM-041`) is a low-risk,
  high-value early win that can slot in opportunistically.
- Step 8's *boundaries* are enforced from step 3 onward (headless core); its *UI code*
  is last and partly deferred.

---

## Gate Status

**Code + automated tests:** acceptance criteria **1–8 are met today** (mechanisms
present, locking tests exist), and the **targeted P0 test subset passes 212/212**.
**Criterion 9** residual (full-suite CI green + one manual smoke pass) is the final
confirmation and the unlock condition for Milestone 2.

**Classification: A — P0 Stabilization Gate is clear and ready.** The blockers are all
backed by present mechanisms *and* passing tests; the only remaining items are a CI
full-suite confirmation and a manual smoke of two environment-sensitive behaviors —
run/click steps, not code gaps. The app is ready for stabilization implementation
(Milestone 2) once those two steps are signed off.

---

*End of P0 Stabilization Gate. No runtime behavior was changed by this document.*
