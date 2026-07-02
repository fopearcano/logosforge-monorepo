# Non-Novel Modes — Implementation Backlog

**Type:** Backlog only. No code, no implementation. This document is a set of
**GitHub-ready issue specs** derived from the comparative analysis and roadmap.
**Inputs:**
- `LOGOSFORGE_VS_AI_SCREENWRITING_PAPERS.md` (8-dimension comparison)
- `NON_NOVEL_MODES_IMPLEMENTATION_ROADMAP.md` (phases A–H)

**How to use.** Each entry below is a self-contained issue spec with the fields
GitHub issues need. IDs (`NNM-###`) are stable handles for the **Dependencies** field
— copy a spec into an issue when the milestone is approved for build. This file does
not open issues automatically.

**Conventions**
- **Priority:** `P0` (blocker / must precede others) · `P1` (high) · `P2` (medium) ·
  `P3` (low / nice-to-have).
- **Risk:** `Low` / `Med` / `High` (likelihood × blast-radius on existing data/UX).
- **Defer marker:** issues that must **not** ship in the PySide alpha are tagged
  **⏳ Defer to React/Electron commercial UI** in their title and Priority.
- **Milestone → roadmap phase:** M1=A, M2=B, M3=C, M4=D, M5=E, M6=F, M7=G,
  M8=(export slice of C–F), M9=H.

**Recommended build order (from roadmap):** M1 → M2 → then M3 ▶ M6 ▶ M4 ▶ M5 (each
with its M8 export slice), with M7 layered onto each mode as it matures; M9 boundaries
decided during M2, M9 code last.

---

## Milestone 1 — P0 Stabilization
*Roadmap Phase A. Mostly a verification + regression-lock gate; per session history
the behavior largely exists. No new mode work merges until this milestone is green.*

### NNM-001 — Lock project-isolation regression tests
- **Objective.** Guarantee switching/creating/opening projects leaves no stale data
  from a prior project (outline, manuscript, PSYKE, console).
- **Systems affected.** `ui/main_window.py` (`_switch_project`), subsystem caches,
  `db/database.py`, `psyke_console.py`, `assistant_view.py`.
- **Research basis.** DuoDrama §7 (preserve user authority / no silent data bleed).
- **Implementation notes.** Verification + test-hardening, not new build. Extend
  existing isolation tests with unique sentinels per project.
- **Acceptance criteria.** A→B→A switch shows zero cross-project content on every
  surface; new project = empty outline/scenes/chapters.
- **Tests.** Isolation sweep across Outline, Manuscript, PSYKE, Assistant context.
- **Risk level.** Low. **Priority.** P0. **Dependencies.** none.

### NNM-002 — Lock outline→manuscript leak guard
- **Objective.** Prove generated/planned outline text never renders as manuscript body.
- **Systems affected.** `outline_actions.py`, `writing_core_view.py`, `plan_view.py`.
- **Research basis.** DSR §4 (planning vs. body separation).
- **Implementation notes.** Confirm body = `scene.content` only; placeholder
  "Start writing…"; planning writes `summary` only.
- **Acceptance criteria.** No `_SceneEditor` body ever contains outline `summary` text.
- **Tests.** Generate outline → assert empty bodies; summary-not-shown-as-body.
- **Risk level.** Low. **Priority.** P0. **Dependencies.** none.

### NNM-003 — Verify Undo/Redo focus routing
- **Objective.** Edit-menu Undo/Redo/Cut/Copy/Paste act on the focused editor.
- **Systems affected.** `ui/main_window.py` (`_on_focus_changed`, `_run_edit_op`).
- **Research basis.** DuoDrama §7 (user control).
- **Implementation notes.** Confirm `_last_edit_widget` tracking survives menu focus theft.
- **Acceptance criteria.** Undo via menu works for each editor type.
- **Tests.** Menu undo/redo per editor; focus-tracking unit test.
- **Risk level.** Low. **Priority.** P0. **Dependencies.** none.

### NNM-004 — Verify autosave + close-save prompt
- **Objective.** Autosave does not suppress the unsaved-changes close prompt.
- **Systems affected.** `autosave.py`, `ui/main_window.py` (`closeEvent`,
  `_modified_since_save`).
- **Research basis.** DuoDrama §7 (never lose user decisions).
- **Implementation notes.** Confirm `_modified_since_save` cleared only by explicit
  save/switch, not autosave.
- **Acceptance criteria.** Editing then closing prompts Save/Don't Save/Cancel.
- **Tests.** Edit→close prompt fires; autosave→close still prompts.
- **Risk level.** Low. **Priority.** P0. **Dependencies.** none.

### NNM-005 — Verify data-safety / source-path de-duplication
- **Objective.** Repeated open/import of the same file does not duplicate projects.
- **Systems affected.** `db/database.py` (`get/set_project_by_source_path`),
  `import_data.py`, project lifecycle.
- **Research basis.** DuoDrama §7.
- **Implementation notes.** Verification of existing de-dupe path.
- **Acceptance criteria.** Re-import of same source path reuses the project.
- **Tests.** Import twice → one project; backup/restore round-trip.
- **Risk level.** Low. **Priority.** P0. **Dependencies.** none.

**Milestone exit criteria.** NNM-001…005 green; full suite green; **gate** for M2+.

---

## Milestone 2 — Shared Non-Novel Core
*Roadmap Phase B. Highest-leverage milestone: build shared infra once so M3–M6 stay
thin. Blocks all mode milestones.*

### NNM-010 — Primary-unit adapter (true unit vocabulary per mode)
- **Objective.** Each mode reports its real primary unit (Screenplay=Scene, GN=Page/
  Panel, Stage=Scene, Series=Episode) for labels/buttons, while storage is unchanged.
- **Systems affected.** `writing_modes.py` (`primary_unit_label`,
  `current_add_button_label`, new unit-type accessor).
- **Research basis.** DSR §1; mode-transfer §8 (audit: label/data mismatch).
- **Implementation notes.** Adapter returns label + canonical unit type; storage stays
  on existing tables (Scene/Episode/Page). No destructive migration.
- **Acceptance criteria.** Correct unit label/type returned for all four modes.
- **Tests.** Adapter unit tests per mode; add-button label per mode.
- **Risk level.** Low. **Priority.** P1. **Dependencies.** M1 exit.

### NNM-011 — Engine-driven Outline hierarchy
- **Objective.** Outline renders each mode's engine hierarchy instead of hardcoded
  Act→Chapter/Scene.
- **Systems affected.** `ui/plan_view.py` (`build_plan_tree`, `PlanView`),
  `narrative_engines/*` (already define hierarchies), `outline_actions.py`
  (`outline_unit_labels`).
- **Research basis.** R²/DSR §4 (structure stage must carry real hierarchy); audit's
  central gap (Outline collapse).
- **Implementation notes.** Depth-flexible tree from `engine_structural_units(engine)`;
  degrade gracefully for sparse projects; keep scene-derived fallback.
- **Acceptance criteria.** Screenplay shows Act→Sequence→Scene→Beat; GN Issue→…→Panel;
  Stage Act→Scene→Beat→Entrance/Cue; Series Season→Episode→Act→Scene.
- **Tests.** Hierarchy render per mode; mode switch re-derives with no stale nodes.
- **Risk level.** **High** (load-bearing surface). **Priority.** P1.
- **Dependencies.** NNM-010.

### NNM-012 — Shared scene/beat planning layer
- **Objective.** One planning-row model (summary/goal/beat) any mode populates; never
  touches `content`.
- **Systems affected.** `outline_actions.py`, `db/database.py`, planning row schema
  (additive only).
- **Research basis.** R² §4 (scene plan as intermediate object).
- **Implementation notes.** Reuse Scene `summary`/structure fields; additive, no
  destructive migration.
- **Acceptance criteria.** Planning rows carry structure with empty `content` for all
  modes.
- **Tests.** Plan-row creation per mode; body stays empty.
- **Risk level.** Med. **Priority.** P1. **Dependencies.** NNM-011.

### NNM-013 — Shared validate-before-apply contract
- **Objective.** Mode-parameterized validation usable by every generation path.
- **Systems affected.** `outline_actions.py` (`validate_mode_outline`,
  `repair_outline_ops`), generation callers.
- **Research basis.** R² §3 (HAR: validate generated structure before it lands).
- **Implementation notes.** Generalize existing validate/repair into a single contract
  (reject prose-as-structure, empty nodes, AI preamble).
- **Acceptance criteria.** Each mode's generated structure passes/fails the same
  contract.
- **Tests.** Reject prose/empty/preamble per mode hierarchy.
- **Risk level.** Med. **Priority.** P1. **Dependencies.** NNM-012.

### NNM-014 — Planning-vs-body invariant + shared test fixture
- **Objective.** Encode "structure→`summary`, prose→`content`" as one enforced contract
  inherited by all modes.
- **Systems affected.** Test infra; `outline_actions.py`, `writing_core_view.py`.
- **Research basis.** DSR §4.
- **Implementation notes.** Single fixture all mode tests reuse; prevents M3–M6
  regressing the leak guard.
- **Acceptance criteria.** Shared fixture passes for every mode.
- **Tests.** Parameterized invariant test across modes.
- **Risk level.** Low. **Priority.** P1. **Dependencies.** NNM-013, NNM-002.

### NNM-015 — Shared causal-link model (infra only)
- **Objective.** A typed, weighted, **acyclic** event-dependency model connected to
  scenes — shared, mode-parameterized; not yet populated.
- **Systems affected.** `models.py` (`TimelineLink`/`TIMELINE_LINK_TYPES` generalize),
  `knowledge_graph/*`, Canvas/Graph layers.
- **Research basis.** R² §2 (causal plot graph as first-class object).
- **Implementation notes.** Define the edge model + cycle-prevention; **do not** build
  auto-extraction (deferred). Populated per mode in NNM-024 / NNM-051.
- **Acceptance criteria.** Causal edges can be created/queried with cycle prevention;
  no generation logic yet.
- **Tests.** Edge CRUD; cycle rejection; mode-tagged queries.
- **Risk level.** Med. **Priority.** P2. **Dependencies.** NNM-012.

**Milestone exit criteria.** All four modes render engine hierarchy; one shared
validate/apply + planning/body invariant; adapter live; causal-link model exists.

---

## Milestone 3 — Screenplay Mode
*Roadmap Phase C. Proving ground for the shared core; causal links already half-exist.*

### NNM-020 — Outline → scene-plan → formatted screenplay flow
- **Objective.** Plan scenes (goal/place/character experience), then write, then format
  — on the shared planning layer.
- **Systems affected.** `outline_actions.py`, `writing_core_view.py`,
  `writing_formats.py` (screenplay elements).
- **Research basis.** DSR §1/§5; R² §4.
- **Implementation notes.** Scene plan is format-free; body written separately; keep
  format out of the planning stage.
- **Acceptance criteria.** A screenplay can be planned then written with no
  planning→body leak.
- **Tests.** Plan→write flow; body empty until written.
- **Risk level.** Med. **Priority.** P1. **Dependencies.** M2 exit.

### NNM-021 — Wire professional Fountain exporter into export dialog
- **Objective.** Export dialog calls `export_screenplay_fountain_result()` (pro) instead
  of the generic exporter.
- **Systems affected.** `ui/export_data_dialog.py`/export wiring, `screenplay_fountain.py`.
- **Research basis.** DSR §5 (format as a separate conversion stage).
- **Implementation notes.** Surface existing library-only pro exporter; label FDX 🧪.
- **Acceptance criteria.** Pro Fountain reachable from UI; round-trips.
- **Tests.** UI export → Fountain; validation report present.
- **Risk level.** Low. **Priority.** P1. **Dependencies.** NNM-020.

### NNM-022 — Surface dialogue/action separation check
- **Objective.** Flag dialogue dominance / parenthetical overuse.
- **Systems affected.** `screenplay_diagnostics.py`, Logos/Assistant surface.
- **Research basis.** DSR §5 (performable dialogue, action economy).
- **Implementation notes.** Surface existing deterministic diagnostics.
- **Acceptance criteria.** Checks reachable in-app with confidence labels.
- **Tests.** Diagnostic fires on dialogue-heavy sample.
- **Risk level.** Low. **Priority.** P2. **Dependencies.** NNM-020.

### NNM-023 — Surface visual-action / "show don't tell" check
- **Objective.** Flag internal-state language in action lines.
- **Systems affected.** `screenplay_diagnostics.py`.
- **Research basis.** DSR §5 (externalize internal state as visible action).
- **Implementation notes.** Surface existing internal-state detection.
- **Acceptance criteria.** Internal-state-in-action flagged.
- **Tests.** Flag on "he felt afraid" action line.
- **Risk level.** Low. **Priority.** P2. **Dependencies.** NNM-020.

### NNM-024 — Setup/payoff causal links via shared infra
- **Objective.** Expose `screenplay_setup_payoff` edges through the NNM-015 causal model.
- **Systems affected.** `screenplay_graph.py`, `screenplay_setup_payoff.py`, causal-link
  model, `ui/graph_view.py`.
- **Research basis.** R² §2.
- **Implementation notes.** Map screenplay candidates → shared edges; no auto-generation.
- **Acceptance criteria.** Setup/payoff edges visible as shared causal links.
- **Tests.** Candidate → edge mapping; acyclic guarantee holds.
- **Risk level.** Med. **Priority.** P2. **Dependencies.** NNM-015.

---

## Milestone 4 — Graphic Novel Mode
*Roadmap Phase D. Deepest visual model, least reach.*

### NNM-030 — Page/panel primary unit + GN Outline hierarchy
- **Objective.** GN plans in Issue→Sequence→Page→Panel; unit label "Page"/"Panel".
- **Systems affected.** `ui/plan_view.py`, `writing_modes.py` adapter, `models.py` GN
  tables, `ui/graphic_novel_pages_view.py`.
- **Research basis.** DSR §1; mode-transfer §8.
- **Implementation notes.** Surface existing Page/Panel tables in Outline; keep
  scene-prose fallback so existing GN projects don't break.
- **Acceptance criteria.** GN Outline shows page/panel hierarchy; existing projects OK.
- **Tests.** GN hierarchy render; legacy scene-prose GN still loads.
- **Risk level.** **High** (unit-model change). **Priority.** P1.
- **Dependencies.** NNM-010, NNM-011.

### NNM-031 — Caption / dialogue / visual-beat planning separation
- **Objective.** Panel planning keeps caption, dialogue, and visual beat distinct.
- **Systems affected.** `graphic_novel_plot.py`, planning layer, `writing_formats.py`
  (GN elements).
- **Research basis.** DSR §5 (visual vs. text); mode-transfer §8.
- **Implementation notes.** Use existing GN element vocabulary; map to planning rows.
- **Acceptance criteria.** Panel plan separates the three streams.
- **Tests.** Panel plan field separation.
- **Risk level.** Med. **Priority.** P2. **Dependencies.** NNM-030.

### NNM-032 — Surface image-text balance + page-turn checks
- **Objective.** Surface balloon-overload / text-heavy / page-turn setup-reveal checks.
- **Systems affected.** `graphic_novel_review.py`, `graphic_novel_plot.py`, chat/Logos.
- **Research basis.** R² (transition/interest axes) ↔ page-turn rhythm.
- **Implementation notes.** `/gn` is wired; extend coverage/surfacing.
- **Acceptance criteria.** Checks reachable in-app.
- **Tests.** Checks fire on cluttered/text-heavy page samples.
- **Risk level.** Low. **Priority.** P2. **Dependencies.** NNM-030.

### NNM-033 — GN panel-script export
- **Objective.** Real panel-script / visual breakdown export (replace generic PAGE-N).
- **Systems affected.** `export.py`, new GN export path, `ui/export_data_dialog.py`.
- **Research basis.** DSR §5 (mode-specific deliverable).
- **Implementation notes.** Mode-specific layer over shared export pipeline.
- **Acceptance criteria.** Panel-script export produced from UI.
- **Tests.** Export structure round-trip.
- **Risk level.** Med. **Priority.** P2. **Dependencies.** NNM-030. *(See also M8.)*

---

## Milestone 5 — Stage Script Mode
*Roadmap Phase E. Strong logic, mostly unwired — high value-per-effort.*

### NNM-040 — Stage Outline hierarchy
- **Objective.** Outline shows Act→Scene→Beat→Entrance/Cue.
- **Systems affected.** `ui/plan_view.py`, `narrative_engines/stage_script.py`.
- **Research basis.** R²/DSR §4; mode-transfer §8.
- **Implementation notes.** Surface engine units; stage metadata optional.
- **Acceptance criteria.** Stage hierarchy renders; generic scene projects OK.
- **Tests.** Stage hierarchy render.
- **Risk level.** Med. **Priority.** P2. **Dependencies.** NNM-011.

### NNM-041 — Wire `stage_script_review` to a `/stage` command
- **Objective.** Stage review reachable (parity with `/gn`, `/series`).
- **Systems affected.** `ui/chat_view.py`, `stage_script_review.py`.
- **Research basis.** DuoDrama §6 (reflective feedback).
- **Implementation notes.** Pure wiring of an existing real engine.
- **Acceptance criteria.** `/stage` returns checks.
- **Tests.** Command returns playable-objective / motivated-exit / prop checks.
- **Risk level.** Low. **Priority.** P1 (high value, low risk). **Dependencies.** none
  (independent of M2, but recommended after M1).

### NNM-042 — Surface entrances/exits + prop-continuity checks
- **Objective.** Surface stage entrance/exit and prop-continuity validation.
- **Systems affected.** `stage_script_plot.py`, `stage_script_review.py`, `models.py`
  (`StageEntranceExit/Cue/Business`).
- **Research basis.** R² §2 (dependency/continuity); mode-transfer §8.
- **Implementation notes.** Surface existing logic.
- **Acceptance criteria.** Checks reachable.
- **Tests.** Entrance/exit + prop continuity fire on samples.
- **Risk level.** Low. **Priority.** P2. **Dependencies.** NNM-041.

### NNM-043 — Actor-intention / playable-action planning
- **Objective.** Bring `psyke_theatre` objectives (stage_objective, subtext) into the
  planning layer.
- **Systems affected.** `psyke_theatre.py`, planning layer.
- **Research basis.** DuoDrama §6 (internal/character state grounds feedback).
- **Implementation notes.** Route existing theatre PSYKE into planning context.
- **Acceptance criteria.** Scene plan carries actor intention/objective.
- **Tests.** Objective surfaces in plan.
- **Risk level.** Med. **Priority.** P3. **Dependencies.** NNM-040.

### NNM-044 — Stage play-format export
- **Objective.** Play-format markup export (replace generic ACT/SCENE text).
- **Systems affected.** `export.py`, new stage export path.
- **Research basis.** DSR §5.
- **Implementation notes.** Mode-specific export layer.
- **Acceptance criteria.** Play-format export from UI.
- **Tests.** Export structure.
- **Risk level.** Med. **Priority.** P3. **Dependencies.** NNM-040. *(See also M8.)*

---

## Milestone 6 — Series Mode
*Roadmap Phase F. Richest cross-time logic; crippled by Outline collapse + missing exports.*

### NNM-050 — Season/episode Outline hierarchy + Episode primary unit
- **Objective.** Outline shows Season→Episode→Act→Scene; Episode is the primary unit.
- **Systems affected.** `ui/plan_view.py`, adapter, `models.py`
  (`Season/Episode/EpisodePlotline`).
- **Research basis.** R²/DSR §4; mode-transfer §8.
- **Implementation notes.** Largest unit realignment — stage behind adapter; keep Scene
  fallback; **non-destructive**.
- **Acceptance criteria.** Series Outline shows season/episode; Episode is primary.
- **Tests.** Series hierarchy render; legacy series projects load.
- **Risk level.** **High** (unit-model change). **Priority.** P1.
- **Dependencies.** NNM-010, NNM-011.

### NNM-051 — SeriesArc setup/payoff as causal + graph edges
- **Objective.** Surface cross-episode arcs (`get_setup_payoff_chains`) as shared causal
  links and KG graph edges.
- **Systems affected.** `series_plot.py`, `psyke_series.py`, `knowledge_graph/*`,
  causal-link model.
- **Research basis.** R² §2 (cross-scene causal lines).
- **Implementation notes.** KG currently omits arc edges; map arcs → edges.
- **Acceptance criteria.** Arc setup/payoff visible as links + graph edges.
- **Tests.** Arc → edge mapping; cross-episode chain query.
- **Risk level.** Med. **Priority.** P2. **Dependencies.** NNM-015, NNM-050.

### NNM-052 — A/B/C plot + recurring-thread planning
- **Objective.** Plan A/B/C plots and recurring threads per episode.
- **Systems affected.** `series_plot.py`, planning layer.
- **Research basis.** mode-transfer §8.
- **Implementation notes.** Surface existing `EpisodePlotline` typing.
- **Acceptance criteria.** A/B/C plots plannable per episode.
- **Tests.** Plotline typing persists per episode.
- **Risk level.** Low. **Priority.** P2. **Dependencies.** NNM-050.

### NNM-053 — Continuity-across-episodes checks (extend `/series`)
- **Objective.** Extend wired `/series` review coverage (unresolved payoff, character
  isolation, arc movement).
- **Systems affected.** `series_review.py`, `ui/chat_view.py`.
- **Research basis.** R² §3 (consistency); DuoDrama §6.
- **Implementation notes.** `/series` already wired; extend checks.
- **Acceptance criteria.** Continuity checks reachable and accurate.
- **Tests.** Checks fire on dangling-arc sample.
- **Risk level.** Low. **Priority.** P2. **Dependencies.** none (post-M1).

### NNM-054 — Series exports (episode outline, season bible, scene list)
- **Objective.** Produce the canonical series deliverables.
- **Systems affected.** `export.py`, new series export paths.
- **Research basis.** DSR §5.
- **Implementation notes.** Mode-specific export layer over shared pipeline.
- **Acceptance criteria.** Episode outline / season bible / scene list export from UI.
- **Tests.** Each export structure round-trips.
- **Risk level.** Med. **Priority.** P2. **Dependencies.** NNM-050. *(See also M8.)*

---

## Milestone 7 — Reflection / Revision Intelligence
*Roadmap Phase G. Cross-cuts M3–M6; mostly surfacing + routing existing engines.*

### NNM-060 — Surface Counterpart as read-only reflection panel
- **Objective.** Expose the external/evaluation critic (never mutates).
- **Systems affected.** `counterpart.py`, a new read-only UI panel.
- **Research basis.** DuoDrama §6 (evaluation role).
- **Implementation notes.** Counterpart is built but unwired; surface read-only.
- **Acceptance criteria.** Counterpart returns critique; mutates nothing.
- **Tests.** Panel returns feedback; no DB writes.
- **Risk level.** Med. **Priority.** P1. **Dependencies.** M2 exit.

### NNM-061 — Per-mode Assistant context blocks
- **Objective.** Mirror the screenplay context-block pattern for GN/Stage/Series.
- **Systems affected.** `assistant_context_policy.py`, PSYKE builders
  (`build_visual/theatre/series_memory_context`).
- **Research basis.** DuoDrama §6; mode-transfer §8.
- **Implementation notes.** Mostly *routing* existing PSYKE builders by mode.
- **Acceptance criteria.** Each mode's Assistant context includes mode-specific blocks.
- **Tests.** Context block present per mode.
- **Risk level.** Med. **Priority.** P1. **Dependencies.** NNM-010.

### NNM-062 — Mode-aware Logos actions
- **Objective.** Register GN/Stage/Series Logos actions (screenplay already has them).
- **Systems affected.** `logos/actions.py` (`modes=`), `ui/logos/*`.
- **Research basis.** DuoDrama §6.
- **Implementation notes.** Infra supports `modes=`; pass `writing_mode` into
  `list_actions_for_section()` consistently.
- **Acceptance criteria.** Mode actions surface only in their mode.
- **Tests.** Action visibility per mode.
- **Risk level.** Med. **Priority.** P2. **Dependencies.** NNM-061.

### NNM-063 — Surface PSYKE consistency checks
- **Objective.** Make continuity / revision_intelligence checks reachable per mode.
- **Systems affected.** `continuity/*`, `revision_intelligence/*`, surface.
- **Research basis.** R² §3.
- **Implementation notes.** Currently library-only; surface with confidence labels.
- **Acceptance criteria.** Consistency checks reachable per mode.
- **Tests.** Check reachable; flags contradiction sample.
- **Risk level.** Med. **Priority.** P2. **Dependencies.** NNM-014.

### NNM-064 — Human-confirmed apply everywhere
- **Objective.** Route every AI mutation through `controlled_apply` preview→confirm.
- **Systems affected.** `controlled_apply/*`, `rewrite_sandbox/*`, all AI apply paths.
- **Research basis.** DuoDrama §7; R² §3.
- **Implementation notes.** Validate-before-apply (NNM-013) + confirm gate; no auto-apply.
- **Acceptance criteria.** No AI action mutates without explicit confirm.
- **Tests.** Apply requires confirm; preview shows diff/conflicts.
- **Risk level.** Med. **Priority.** P1. **Dependencies.** NNM-013.

### NNM-065 — ⏳ Defer to React/Electron commercial UI — Autonomous experience-role critic
- **Objective.** A critic that *inhabits* a character to generate reactions, then
  evaluates (DuoDrama ExReflect).
- **Systems affected.** Future; depends on surfaced PSYKE state + trusted Counterpart.
- **Research basis.** DuoDrama §6 (experience role).
- **Implementation notes.** **Do not build in alpha.** Needs grounded state + trusted
  external critic first; high hallucination surface.
- **Acceptance criteria.** N/A in alpha (deferred).
- **Tests.** N/A in alpha.
- **Risk level.** High. **Priority.** ⏳ Deferred. **Dependencies.** NNM-060, NNM-063.

---

## Milestone 8 — Export / Interchange
*Export slices of C–F + cross-mode interchange. Format is the one inherently
mode-specific concern (DSR §5); the pipeline is shared.*

### NNM-070 — Export dialog routing to professional exporters per mode
- **Objective.** Route the export dialog to the correct pro exporter per mode.
- **Systems affected.** `ui/export_data_dialog.py`, `export.py`, mode export paths.
- **Research basis.** DSR §5.
- **Implementation notes.** Consolidates NNM-021/033/044/054 wiring into one dialog
  contract; label 🧪 targets (FDX).
- **Acceptance criteria.** Each mode offers its real deliverables from the dialog.
- **Tests.** Per-mode export availability + round-trip.
- **Risk level.** Med. **Priority.** P1. **Dependencies.** NNM-021 (and the per-mode
  export issues as they land).

### NNM-071 — Surface export-readiness validation reports
- **Objective.** Surface export/output validation (currently library-only) before export.
- **Systems affected.** `screenplay_export_validation.py`,
  `screenplay_output_validation.py`, export dialog.
- **Research basis.** R² §3 (validate before output); DSR §5.
- **Implementation notes.** Show warnings pre-export; do not block.
- **Acceptance criteria.** Readiness warnings shown before export.
- **Tests.** Validation report rendered for a sample with issues.
- **Risk level.** Low. **Priority.** P2. **Dependencies.** NNM-070.

### NNM-072 — Interchange round-trip for new mode structures
- **Objective.** Ensure export/import preserves new hierarchy + causal links + planning.
- **Systems affected.** `export.py`, `import_data.py`, `data_export.py`.
- **Research basis.** DuoDrama §7 (no data loss).
- **Implementation notes.** Extend round-trip coverage for chapters/timeline/arcs/
  page-panel/episode structures.
- **Acceptance criteria.** Round-trip preserves all new structures.
- **Tests.** Export→import equality per mode.
- **Risk level.** Med. **Priority.** P1. **Dependencies.** NNM-011, NNM-015.

### NNM-073 — ⏳ Defer to React/Electron commercial UI — ComfyUI image export
- **Objective.** Real image-generation connector for GN panels.
- **Systems affected.** `graphic_novel_ai_export.py` (currently a disabled stub).
- **Research basis.** mode-transfer §8 (visual output).
- **Implementation notes.** **Do not build in alpha** — external connector concern.
- **Acceptance criteria.** N/A in alpha (deferred).
- **Tests.** N/A in alpha.
- **Risk level.** High. **Priority.** ⏳ Deferred. **Dependencies.** NNM-033.

---

## Milestone 9 — React/Electron/Web Future Transfer
*Roadmap Phase H. Boundaries decided during M2; code built last. Most build items here
are deferred, but the **headless-core boundary** must be enforced from M2 onward.*

### NNM-080 — Headless core boundary (no Qt) + import test
- **Objective.** Guarantee core narrative logic imports/runs with no Qt dependency.
- **Systems affected.** All core modules (`writing_modes`, `outline_actions`,
  `db`, `export`, `*_review`, `continuity`, etc.); `ui/*` stays logic-free.
- **Research basis.** Architectural (clean stage boundaries, DSR-aligned).
- **Implementation notes.** Add a headless-import CI test; refactor any Qt leakage out
  of core (audit needed). Enforced continuously, not just at M9.
- **Acceptance criteria.** Core imports + drives plan/write/validate/export without Qt.
- **Tests.** Headless import test; core-only pipeline test per mode.
- **Risk level.** Med. **Priority.** P1 (enforce early). **Dependencies.** M2 exit.

### NNM-081 — API contract for plan→write→validate→export→apply
- **Objective.** Define the headless API the future web/Electron client will call.
- **Systems affected.** `api/*`, core services.
- **Research basis.** DSR (stage boundaries); DuoDrama §7 (apply gate in core).
- **Implementation notes.** Contract/spec work; map each stage to an endpoint.
- **Acceptance criteria.** Documented API covering all stages for all modes.
- **Tests.** Contract tests per stage (headless).
- **Risk level.** Med. **Priority.** P2. **Dependencies.** NNM-080.

### NNM-082 — Apply gate enforced at the API layer
- **Objective.** preview→confirm→apply is an API transaction so any client preserves
  human authority identically.
- **Systems affected.** `controlled_apply/*`, `api/*`.
- **Research basis.** DuoDrama §7.
- **Implementation notes.** Gate must live in core/API, not only PySide.
- **Acceptance criteria.** API rejects apply without confirm.
- **Tests.** API apply requires confirm; bypass attempt fails.
- **Risk level.** Med. **Priority.** P1. **Dependencies.** NNM-064, NNM-081.

### NNM-083 — ⏳ Defer to React/Electron commercial UI — Web/Electron client build
- **Objective.** Build the React/Electron UI over the headless API.
- **Systems affected.** New frontend; PySide remains reference client.
- **Research basis.** Commercial transfer.
- **Implementation notes.** **Do not build in alpha.** PySide views are a reference
  client; do not over-polish them.
- **Acceptance criteria.** N/A in alpha (deferred).
- **Tests.** N/A in alpha.
- **Risk level.** High. **Priority.** ⏳ Deferred. **Dependencies.** NNM-081, NNM-082.

### NNM-084 — ⏳ Defer to React/Electron commercial UI — Cloud sync / realtime collaboration
- **Objective.** Multi-device sync and collaborative editing.
- **Systems affected.** Future backend/storage.
- **Research basis.** Commercial transfer.
- **Implementation notes.** **Do not build in alpha.**
- **Acceptance criteria.** N/A in alpha (deferred).
- **Tests.** N/A in alpha.
- **Risk level.** High. **Priority.** ⏳ Deferred. **Dependencies.** NNM-083.

---

## Backlog Index

| ID | Title | Milestone | Priority | Risk | Depends on |
|---|---|---|---|---|---|
| NNM-001 | Lock project-isolation tests | M1 | P0 | Low | — |
| NNM-002 | Lock outline→manuscript leak guard | M1 | P0 | Low | — |
| NNM-003 | Verify Undo/Redo focus routing | M1 | P0 | Low | — |
| NNM-004 | Verify autosave + close prompt | M1 | P0 | Low | — |
| NNM-005 | Verify data-safety / dedupe | M1 | P0 | Low | — |
| NNM-010 | Primary-unit adapter | M2 | P1 | Low | M1 |
| NNM-011 | Engine-driven Outline hierarchy | M2 | P1 | High | 010 |
| NNM-012 | Shared scene/beat planning layer | M2 | P1 | Med | 011 |
| NNM-013 | Validate-before-apply contract | M2 | P1 | Med | 012 |
| NNM-014 | Planning-vs-body invariant fixture | M2 | P1 | Low | 013,002 |
| NNM-015 | Shared causal-link model (infra) | M2 | P2 | Med | 012 |
| NNM-020 | Outline→scene-plan→screenplay | M3 | P1 | Med | M2 |
| NNM-021 | Wire pro Fountain exporter | M3 | P1 | Low | 020 |
| NNM-022 | Dialogue/action check | M3 | P2 | Low | 020 |
| NNM-023 | Visual-action check | M3 | P2 | Low | 020 |
| NNM-024 | Setup/payoff causal links | M3 | P2 | Med | 015 |
| NNM-030 | Page/panel unit + GN Outline | M4 | P1 | High | 010,011 |
| NNM-031 | Caption/dialogue/beat separation | M4 | P2 | Med | 030 |
| NNM-032 | Image-text + page-turn checks | M4 | P2 | Low | 030 |
| NNM-033 | GN panel-script export | M4 | P2 | Med | 030 |
| NNM-040 | Stage Outline hierarchy | M5 | P2 | Med | 011 |
| NNM-041 | Wire `/stage` review | M5 | P1 | Low | — |
| NNM-042 | Entrances/exits + prop checks | M5 | P2 | Low | 041 |
| NNM-043 | Actor-intention planning | M5 | P3 | Med | 040 |
| NNM-044 | Stage play-format export | M5 | P3 | Med | 040 |
| NNM-050 | Season/episode Outline + unit | M6 | P1 | High | 010,011 |
| NNM-051 | SeriesArc causal/graph edges | M6 | P2 | Med | 015,050 |
| NNM-052 | A/B/C plot planning | M6 | P2 | Low | 050 |
| NNM-053 | Continuity checks (`/series`) | M6 | P2 | Low | — |
| NNM-054 | Series exports (bible/list) | M6 | P2 | Med | 050 |
| NNM-060 | Surface Counterpart panel | M7 | P1 | Med | M2 |
| NNM-061 | Per-mode Assistant context | M7 | P1 | Med | 010 |
| NNM-062 | Mode-aware Logos actions | M7 | P2 | Med | 061 |
| NNM-063 | PSYKE consistency checks | M7 | P2 | Med | 014 |
| NNM-064 | Human-confirmed apply everywhere | M7 | P1 | Med | 013 |
| NNM-065 | Autonomous experience-role critic | M7 | ⏳ Defer | High | 060,063 |
| NNM-070 | Export dialog pro routing | M8 | P1 | Med | 021 |
| NNM-071 | Export-readiness validation | M8 | P2 | Low | 070 |
| NNM-072 | Interchange round-trip | M8 | P1 | Med | 011,015 |
| NNM-073 | ComfyUI image export | M8 | ⏳ Defer | High | 033 |
| NNM-080 | Headless core boundary + test | M9 | P1 | Med | M2 |
| NNM-081 | API contract (all stages) | M9 | P2 | Med | 080 |
| NNM-082 | Apply gate at API layer | M9 | P1 | Med | 064,081 |
| NNM-083 | Web/Electron client build | M9 | ⏳ Defer | High | 081,082 |
| NNM-084 | Cloud sync / collaboration | M9 | ⏳ Defer | High | 083 |

**Deferred to React/Electron commercial UI:** NNM-065, NNM-073, NNM-083, NNM-084
(and the *build* of M9 generally — only the headless-core boundary and apply-gate
enforcement are in-scope for the alpha).

---

*End of backlog. No code was written; nothing was implemented; no GitHub issues were
opened. These are issue specs to be promoted to GitHub when each milestone is approved
for build.*
