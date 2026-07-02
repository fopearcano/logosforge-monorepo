# Logosforge — Session Resume State (Audit)

**Generated:** 2026-06-06 · **Type:** Orientation / state audit only — *no feature code changed.*
**Auditor note:** This document reconstructs the *actual* repo state from code + tests, not from
assumptions in the resume prompt. Where the live state contradicts the resume prompt, the **code +
passing tests win** and the contradiction is called out explicitly.

---

## 0. Headline (read this first)

The repo is **ahead of the checkpoint described in the resume prompt**, not behind it. The two
"prompts that were not run" are **largely already implemented and committed**, and so are several
items the prompt told me not to assume:

| Resume prompt assumed… | Reality in code (verified) |
|---|---|
| Timeline Plottr-like lanes/links **not** implemented | **Implemented & wired** (`PlotTimelineView`): coloured lanes, aligned event cards, event↔event links, event→Act/Chapter/Scene links, drag-move, double-click-to-open |
| Notes linking **not** implemented | **Implemented & wired** (`NotesView`): link to Act/Chapter/Scene/PSYKE as removable chips |
| Fullscreen "Create New" bug still present | **Fix present** (`_do_new_project`): no window-state calls + single lifecycle signal; *runtime click-confirm on macOS still pending* |
| Outline upgrade (movable cards / auto-renumber / double-click → Manuscript) not run | **Partially**: the block/card planner exists; the *drag-reorder + auto-renumber + double-click-to-Manuscript* sub-features are **not** present |

Because the live state materially differs from the prompt's expected checkpoint, the final
classification is **C** (see §11) — but note: "C" here means *re-align the plan to the true state*,
**not** that anything is broken. The code is healthy and the full P0 test subset is green.

---

## 1. Current commit and branch

- **Local branch (checked out):** `claude/sweet-sagan-0Zwgc`  ← the designated development branch
- **HEAD commit:** `d11aad9` — `Add files via upload` (uploads `timeline_target.png` + `timeline2_target.png`)
- **Working tree:** clean (`nothing to commit`)
- **Latest 10 commits:**
  ```
  d11aad9 Add files via upload                                  (reference PNGs only)
  60d73d6 Align Manuscript & Outline with reference targets; rename section markers
  44ce73a Add files via upload                                  (reference PNGs only)
  2802b71 Runtime proof: diagnostics report + visible dev markers (Manuscript/Outline/Timeline)
  ba4bcd4 Wiring guard: diagnostic markers + section-routing smoke tests
  abc383f Timeline: colored lane lines + event→Act/Chapter links + badges
  aa4ff57 Notes: simplify UI + link notes to Acts/Chapters/Scenes
  5eb6ed6 UI/UX: lighter writing-first Manuscript + mode-aware block Outline
  c35912d P0 fix: fullscreen Create New no longer flashes/minimizes
  18c06b5 Manuscript = selected-unit editor; Outline block planner; defer Canvas Plot
  ```

### Branch / remote reconciliation (important)
- The remote (`git ls-remote origin`) currently has:
  - `claude/setup-logosforge-app-5cVxF` → **`d11aad9`** (the *same commit* as local HEAD)
  - `claude/fervent-hamilton-HPAd8` → `61d15e8` (a **separate** branch not present locally — likely a parallel session; left untouched)
  - **`claude/sweet-sagan-0Zwgc` does not exist on the remote** (a `fetch` of it returns "couldn't find remote ref")
- Local remote-tracking refs: `origin/claude/sweet-sagan-0Zwgc` = `d11aad9` (== HEAD), `origin/claude/setup-logosforge-app-5cVxF` = `fc921a3` (stale from clone).
- **Net:** local `sweet-sagan` and remote `setup-logosforge-app` point at the **same content** (`d11aad9`); only the branch *name* differs. Pushing `claude/sweet-sagan-0Zwgc` will **create** that branch on the remote (no upstream is currently set).
- The branch named in the task header (`setup-logosforge-app-5cVxF`) and the branch named in the dev-requirements (`sweet-sagan-0Zwgc`) are therefore the same checkpoint — there is **no content divergence** between them (`git log A..B` is empty in both directions for the shared history; `sweet-sagan` is a strict superset that the remote `setup-logosforge` has since caught up to).

---

## 2. Runtime / entrypoint

- **Launch command:** `python run.py` (from repo root). Also `python -m logosforge.diagnostics` prints the runtime report with no GUI.
- **Source resolution:** **local source**, *not* an installed/stale package. Verified by `logosforge.diagnostics`:
  ```
  package         : /home/user/logosforge/logosforge/__init__.py
  main_window     : /home/user/logosforge/logosforge/ui/main_window.py
  manuscript view : logosforge.ui.writing_core_view.WritingCoreView  <- .../writing_core_view.py
  outline view    : logosforge.ui.plan_view.PlanView                 <- .../plan_view.py
  timeline view   : logosforge.ui.plot_timeline_view.PlotTimelineView<- .../plot_timeline_view.py
  commit          : d11aad9
  ```
- **App factory:** `logosforge/app.py::create_app()` → `MainWindow(db, project_id)`; single SQLite DB at `logosforge.db` (CWD). Lands on **Projects** at startup (`show_initial_section`).
- **Env deps:** `PySide6 6.8.3`, `sqlmodel`, `pytest 9.0.3` were installed in this container to run tests (they were absent on clone). Qt offscreen also needs system `libEGL.so.1` (installed via `apt`).

---

## 3. Section registration

Sidebar layout (`main_window.py:411`): top-level **Projects · Dashboard · Notes · Manuscript**, then
group **Plan** = `[Outline, Chapters, Scenes, Timeline, Plot, Pages]`, plus Structure/Analytics/etc.
Nav "section IDs" are the string labels themselves; handlers live in `_nav_section_handlers` (`:507`).

| Section | Sidebar label | Active file → class | Section ID | objectName marker (runtime proof) | Intended current? | Old/duplicate impls still in tree |
|---|---|---|---|---|---|---|
| Projects | "Projects" | `projects_view.py` → `ProjectsView` | `Projects` | — | ✅ yes | — |
| Manuscript | "Manuscript" | `writing_core_view.py` → `WritingCoreView` (`structured_list=True`) | `Manuscript` | `manuscript_target_writing_page_view` | ✅ yes | — |
| Outline | "Outline" | `plan_view.py` → `PlanView` | `Outline` | `outline_target_block_card_planner_view` | ✅ yes | `outline_view.py::OutlineView` (orphan); `chapter_outline_view.py::ChapterOutlineView` (referenced only in a dead `isinstance` branch) |
| Timeline | "Timeline" | `plot_timeline_view.py` → `PlotTimelineView` | `Timeline` | `timeline_target_colored_lane_link_view` | ✅ yes | `timeline_view.py::TimelineView` (**dead import** at `main_window.py:83`, never instantiated); `quantum_timeline.py` (separate λ/Lambda surface, not the main Timeline) |
| Notes | "Notes" | `notes_view.py` → `NotesView` | `Notes` | — | ✅ yes | — |
| Canvas Plot | "Canvas Plot" *(hidden)* | `canvas_plot_view.py` → `CanvasPlotView` | `Plot` | — | ✅ deferred/hidden (correct) | — |
| *(Chapters)* | *hidden* | `chapters_view.py` → `ChaptersView` | `Chapters` | — | ✅ hidden (correct) | — |
| *(Scenes)* | *hidden* | `scenes_view.py` → `ScenesView` | `Scenes` | — | ✅ hidden (correct) | — |

**Consolidation/deferral confirmed in code:**
- `_apply_unit_section_availability()` (`:1287`) removes **Chapters** and **Scenes** from `_nav_labels` (handlers/widgets kept for legacy/data reachability). → matches "Chapters/Scenes are node types inside Outline, not sections."
- `_apply_canvas_plot_availability()` (`:1318`) removes **Plot/Canvas Plot** from `_nav_labels` (data untouched). → matches "Canvas Plot deferred/hidden."
- Display-name map (`:96`) renames `"Plot"` → `"Canvas Plot"`.

**Duplicate cleanup opportunity (non-blocking):** `outline_view.py`, `timeline_view.py`,
`chapter_outline_view.py` are dead/orphan and could be removed later. They do **not** affect runtime
(never instantiated in the active nav). Do not delete as part of this orientation pass.

---

## 4. Current Manuscript state — `WritingCoreView` (`writing_core_view.py`, ~4020 lines)

| Audit check | Result | Evidence |
|---|---|---|
| Writing-focused | ✅ | `structured_list` mode = compact structure list (left) + single continuous **writing page** (right); comment `:1631` "focused continuous WRITING PAGE … no numbered gutter, no foldable blocks" |
| Avoids numbered gutter / hideable structural blocks | ✅ | explicit `:1634` / `:1797`. *(Note: a thin optional **paragraph-energy gutter** of dots/flow hints exists — `_EnergyGutter`, `:1189` — this is an analytics overlay, **not** a line-number/structure gutter, and is toggleable.)* |
| Avoids giant inline outline/planning blocks | ✅ | editor renders the selected unit only; no whole-project structure inline |
| Body text separate from outline descriptions | ✅ | body = `scene.content`; planning summaries live on `scene.summary` (locked by `test_manuscript_outline_separation.py`) |
| Uses primary-unit adapter | ✅ | `current_primary_unit_label` (`:1752`) drives the add-button label |
| Mode-aware (Novel=Chapter, non-Novel=Scene) | ✅ | "+ Chapter" in Novel, "+ Scene" otherwise (`:1745`); storage stays Scene-based |
| Visible/runtime marker | ✅ | `setObjectName("manuscript_target_writing_page_view")` (`:1340`); dev badge via `LOGOSFORGE_DEV_MARKERS=1` |
| Stable editor behavior | ✅ | locked by `test_manuscript_editor_stability.py`, `test_manuscript_rollback.py` (per P0 gate B2) |

**Verdict:** Matches the intended writing-first Manuscript. **Do not refactor** (per `ALPHA_NEXT_STEPS`/P0 gate).

---

## 5. Current Outline state — `PlanView` (`plan_view.py`, 1264 lines)

| Audit check | Result | Evidence / notes |
|---|---|---|
| Block/card based (not old/basic) | ✅ | Act sections → Chapter columns → Scene cards (`_build_act_section`/`_build_chapter_column`/`_build_scene_card`) |
| Manages Acts / Chapters / optional Scenes | ✅ | Novel = Act→Chapter→Scene; non-Novel = Act→Scene (chapter layer flattened, `_is_novel`) |
| Hides separate Chapter/Scene nav sections | ✅ | see §3 consolidation |
| Type badges | ✅ | ACT / CHAPTER / SCENE pills (`_type_badge`, `planTypeBadge`) |
| Add Act / Add Chapter / Add Scene | ✅ | mode-aware ("+ New Chapter" Novel / "+ New Scene" otherwise) |
| Delete / Clear outline | ✅ | delete act/chapter/scene + **safe** "Clear Outline" (placeholders deleted, prose/summaries preserved → Unsorted) |
| Status / tags / PSYKE chips | ✅ *(baseline)* | `_scene_chips`: tags + linked character/Codex chips + "status…" accent; note indicators "📝 N" |
| Summaries (Act/Chapter/Scene) | ✅ | auto-save `_SummaryEditor` |
| AI generation + templates | ✅ | full/act/chapter/scene generation; structural templates |
| **Movement / reorder (drag-drop)** | ❌ **not implemented** | cards are plain `QWidget`s; no `QDrag`/`setAcceptDrops` |
| **Automatic numbering / retracking** | ❌ **not implemented** | the `number` arg is computed but **not rendered** — `_build_scene_card` `:797-799` is a no-op (`title_txt = f"{title_txt}"`) |
| **Double-click card → Manuscript** | ❌ **not implemented** | open-in-Manuscript exists only via the ⋯ menu ("Open in Manuscript", `_on_open_scene`); no `mouseDoubleClickEvent` on cards |
| "smaller movable cards" | ⚠️ partial | cards exist and are reasonably compact, but are **not** movable |

**Verdict vs `outline_target.png`:** the **block/card planner foundation matches** the target
concept; the specific *Outline-upgrade* sub-features from the un-run prompt (drag-reorder,
auto-renumber, double-click-to-Manuscript) are **genuinely not present**. *(Reference image is a
conceptual target; not pixel-compared.)*

---

## 6. Current Timeline state — `PlotTimelineView` (`plot_timeline_view.py`, 782 lines)

| Audit check | Result | Evidence |
|---|---|---|
| Plottr-like (not old/basic) | ✅ | vertical axis = plot lanes; horizontal axis = shared story-time (`sort_order`); sticky lane headers |
| Lanes / tracks | ✅ | `TimelineLane` rows + virtual "— Unassigned" lane |
| Lane colours | ✅ | header coloured left edge + swatch from `lane.color_label` |
| Custom lane line colours | ✅ | per-lane coloured **band + centre line** drawn in `paintEvent` (`:263-274`); `_set_lane_color` menu |
| Event/block cards | ✅ | `_EventCard` (one per scene), elided title + Act/Chapter sub-line |
| Event colours | ✅ | coloured left stripe from `scene.color_label` |
| Event/block movement | ✅ | `QDrag` (`mouseMoveEvent`) + canvas `dropEvent` → `_handle_drop` (changes lane *and* reorders along story-time) |
| Event-to-event links | ✅ | start-link → finish-link (typed via `TIMELINE_LINK_TYPES`, coloured, end-dots) + direct "Link to Scene"; persisted as `TimelineLink` |
| Links to Acts / Chapters / Scenes | ✅ | "Link to… Act/Chapter/Scene" → `add_timeline_structure_link`; shown as "🔗 refs" on cards |
| Double-click event → open in Manuscript | ✅ | `mouseDoubleClickEvent` → `_open_scene` → `on_scene_selected` |
| Lane collapse / rename / delete | ✅ | `_toggle_lane`, `_rename_lane`, `_delete_lane` (keeps events) |
| Visible/runtime marker | ✅ | `setObjectName("timeline_target_colored_lane_link_view")` + dev badge |

**Verdict vs `timeline_target.png` / `timeline2_target.png`:** the Plottr-like target is
**substantially implemented** — colored lanes, aligned blocks, interlinked lanes, inter-lane event
links, and Outline-structure links all exist and persist. This **contradicts** the resume prompt's
"Timeline not implemented" assumption. *(Reference images are conceptual targets; not pixel-compared.)*

---

## 7. Current Notes state — `NotesView` (`notes_view.py`, 374 lines)

| Audit check | Result | Evidence |
|---|---|---|
| Simple (not cluttered) | ✅ | left note list + right editor (title/content/tags/pinned) |
| Can link to Acts / Chapters / Scenes | ✅ | "Link to…" menu → Act/Chapter/Scene **and** PSYKE; removable chips; missing-target flagged |
| Tags | ✅ | comma-separated tags field |
| Project-bound | ✅ | scoped by `project_id`; reloads on switch (locked by note-link tests) |
| Pinned (Assistant context) | ✅ | "Pinned (always include in Assistant context)" |

**Verdict:** Notes + Notes-linking are **already implemented** (contradicts the resume prompt's "do
not assume Notes linking"). Follow-up later is optional polish, not a gap.

---

## 8. Project stability checks (tests run this session)

Ran the audit-relevant suite headless (`QT_QPA_PLATFORM=offscreen`). **Result: 223 passed, 0 failed.**

| Area | Test file(s) | Result |
|---|---|---|
| Project isolation | `test_project_isolation_p0.py`, `test_project_switch_isolation.py` | ✅ |
| New-project flow / isolation | `test_new_project_flow.py` | ✅ |
| PSYKE project isolation | `test_psyke_project_isolation.py` | ✅ |
| Outline isolation/repair | `test_outline_isolation_and_repair.py` | ✅ |
| Manuscript ↔ Outline separation | `test_manuscript_outline_separation.py` | ✅ |
| Projects section (incl. Save-As/dirty) | `test_projects_section_fixes.py` | ✅ |
| Autosave | `test_autosave.py` | ✅ |
| Section routing | `test_section_routing.py` | ✅ |
| Timeline links | `test_timeline_links.py`, `test_plot_timeline.py` | ✅ |
| Outline block planner / delete / consolidation | `test_outline_block_planner.py`, `test_outline_delete.py`, `test_outline_consolidation.py` | ✅ |
| Note links | `test_note_links.py` | ✅ |
| Mode-aware units | `test_mode_aware_units.py` | ✅ |
| Canvas Plot deferred | `test_canvas_plot_deferred.py` | ✅ |
| Manuscript structured list | `test_manuscript_structured_list.py` | ✅ |
| Writing-mode integrity | `test_writing_mode_integrity.py` | ✅ |

- **Dirty close-save:** implemented in `closeEvent` (`:3266`) — Save / Discard / Cancel; `_modified_since_save` is **not** cleared by autosave; `_save_for_close` (`:3297`) handles Save-As when never saved. Covered by code + `test_editing_integrity.py`/`test_projects_section_fixes.py`. **Live GUI click-confirm not done in this headless env.**
- The repo's own **P0 Stabilization Gate** (`docs/research/ai_screenwriting/P0_STABILIZATION_GATE.md`) reports acceptance criteria **1–8 met**, with only criterion 9 (full-suite CI green + a one-pass manual smoke of undo-via-menu + dirty-close) residual.

**Not run here:** the *full* 263-file suite (only the targeted audit subset was executed) and any
GUI/manual smoke (headless container).

---

## 9. Fullscreen "Create New" issue

- **Status: fix is present in code** (commit `c35912d`), at `_do_new_project` (`:2477`):
  - Reentrancy guard `_creating_project` (`_on_new_project` `:2466`) blocks double-dialogs.
  - Explicit comment + behavior: **no `showNormal`/`showMinimized`/`showFullScreen` calls** in the flow, so the window can't slide Spaces / minimise.
  - **One** clean transition: `_set_active_section("Dashboard")` then `_switch_project(..., announce=False)` so only **one** lifecycle signal fires (the duplicate `project_loaded` + `project_created` double-fire was the documented cause of the rapid multi-view flashing).
  - Optional `LOGOSFORGE_DEBUG_PROJECT=1` logs window state at each stage.
- **Residual:** this is environment-sensitive (macOS fullscreen Spaces). A **manual click-through on
  macOS in fullscreen** is the only way to fully sign it off; it could not be reproduced/verified in
  this headless Linux container.
- **Likely files if it ever resurfaces:** `main_window.py::_do_new_project` / `_switch_project` /
  `_set_active_section`; `ui/new_project_dialog.py`; lifecycle signals in `project_events.py`.
- **Not fixed/changed in this pass** (audit only).

---

## 10. Current P0 blockers

**None that block continuation.** The app is at a ratified stable checkpoint:
- ✅ Project / PSYKE / Manuscript / Outline / Assistant / Logos isolation — verified by tests.
- ✅ Manuscript writing-first + primary-unit adapter — verified.
- ✅ Outline block planner + Chapters/Scenes consolidation — verified.
- ✅ Canvas Plot deferred — verified.
- ✅ Timeline (Plottr-like) + Notes linking — implemented & test-backed.
- ✅ Dirty close-save — implemented & test-backed.

**Open residuals (verification/UX, not blockers):**
1. **Full-suite CI green** + **one manual smoke** (undo-via-menu in each editor; dirty-close prompt) — the P0 gate's criterion 9.
2. **Fullscreen "Create New"** macOS click-confirm (code fix already in).
3. **Outline-upgrade sub-features** missing: drag-reorder, auto-renumber, double-click→Manuscript (this is *feature work*, not a stability blocker).
4. **Dead/orphan duplicates** (`outline_view.py`, `timeline_view.py`, `chapter_outline_view.py`) — cleanup-only.

---

## 11. Recommended next prompt

The repo's own planning chain (`ALPHA_NEXT_STEPS.md` + `P0_STABILIZATION_GATE.md`) already supersedes
the two "un-run" prompts. Because **Timeline is implemented and is explicitly on the "Do NOT redesign"
list**, and the Outline *block planner* already exists, the highest-value next step is the documented
Milestone-2 opener — **not** a Timeline build.

**Option A — follow the repo's documented roadmap (recommended):**
> "IMPLEMENT — Milestone 2 / NNM-011: Make the Outline (`PlanView`) render each writing mode's engine
> hierarchy via `engine_structural_units(engine)` instead of hardcoded Act→Chapter. Non-destructive;
> keep the scene-derived fallback; Chapters/Scenes remain node types inside Outline (no new sections);
> preserve the Chapter/Scene adapter; add per-mode hierarchy-render tests. Do not touch Manuscript.
> Do not migrate storage." *(Issue only after the P0 gate is OPEN — full-suite CI + manual smoke.)*

**Option B — if you specifically still want the Outline *interaction* upgrade** (the genuinely
un-run part):
> "CHECK/FIX — Upgrade `PlanView` Outline cards only: add drag-to-reorder within/between Chapters with
> automatic renumbering, render the scene number on each card, and add double-click → open in
> Manuscript (reuse `on_open_scene`). Keep it additive; do not touch storage, Manuscript, or Timeline;
> add tests for reorder + renumber + double-click."

Before either, the cheap unlock is the **P0 criterion 9**: run the full suite in CI and do the
two-item manual smoke (undo-via-menu, dirty-close), per `ALPHA_NEXT_STEPS.md`.

---

## Final classification

**C — Current repo state differs from the expected checkpoint; align the plan before coding.**

Clarification: "C" is chosen because the live code **materially contradicts the resume prompt's
assumptions** (Timeline, Notes-linking, and the fullscreen fix are already done; the Outline
*upgrade* is only partially done). It does **not** mean the repo is broken — the working tree is
clean, the app launches from local source, and the targeted P0 test subset is **223/223 green**. The
"correction" required is to the *plan/understanding*, after which it is safe to continue from this
checkpoint. If the Timeline/Notes/fullscreen items are accepted as done, this effectively becomes
**A (safe to continue)** with the single open decision being Option A vs Option B in §11.
