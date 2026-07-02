# Non-Novel Modes — Implementation Roadmap

**Type:** Roadmap only. No code, no implementation, no new features in this document.
**Inputs:**
1. `AI_SCREENWRITING_RESEARCH_SUMMARY.md` (R², DSR, DuoDrama)
2. `LOGOSFORGE_NON_NOVEL_MODE_AUDIT.md` (12-area, 4-mode audit)
3. `LOGOSFORGE_VS_AI_SCREENWRITING_PAPERS.md` (8-dimension comparison)

**Modes:** Screenplay, Graphic Novel, Stage Script, Series.

---

## Guiding Architecture Principle

**One narrative engine, four medium skins.** Do **not** build four parallel apps.
Build **shared narrative infrastructure** once, then attach **thin mode-specific
layers** that vary only where the medium genuinely differs.

```
                    ┌─────────────────────────────────────────────┐
                    │              SHARED CORE (Phase B)            │
                    │  primary-unit adapter · Outline hierarchy ·   │
                    │  scene/beat planning · Canvas Plot (causal) · │
                    │  Timeline (chronological) · PSYKE memory ·    │
                    │  Assistant context policy · Logos feedback ·  │
                    │  Counterpart reflection · validate-before-apply│
                    └───────────────┬─────────────────────────────┘
                                    │ parameterized by writing_mode
        ┌───────────────┬──────────┴──────────┬──────────────────┐
   Screenplay (C)   Graphic Novel (D)    Stage Script (E)     Series (F)
   format/Fountain  page/panel breakdown  staging/entrances   season/episode
   action/dialogue  caption/balloon/SFX   playable action     A/B/C threads
   causal links     page-turn rhythm      prop continuity     cross-ep arcs
```

**Rule of thumb for every phase:** if a capability is medium-*agnostic* (a graph
edge, a confirm gate, a validation pass, a planning row), it belongs in the shared
core and is *parameterized* by `writing_mode`. If it is medium-*defining* (a Fountain
serializer, a panel balloon-count check, an entrance/exit cue, an A/B/C plot label),
it belongs in a mode layer. **Generalize the mechanism; specialize the vocabulary.**

**Research basis for the principle:** all three papers describe screenplay, but their
core mechanisms — decomposition (DSR), causal structure (R²), reflective dual-
perspective feedback (DuoDrama), validate-before-trust (R² HAR) — are medium-agnostic.
Only *format adherence* (DSR §5) is inherently mode-specific. The roadmap mirrors that
split.

---

## Phase Dependency & Sequencing

```
A (stabilize) ─► B (shared core) ─┬─► C (Screenplay)
                                  ├─► D (Graphic Novel)
                                  ├─► E (Stage Script)
                                  └─► F (Series)
                                         │
                  G (reflection/refine) ─┘  (cuts across C–F; needs B)
                                         │
                  H (commercial transfer) ─ planning runs in parallel; build last
```

- **A is a precondition gate.** No new mode work until A's acceptance criteria hold.
- **B is the leverage phase.** Every mode phase (C–F) is cheap *only if* B lands first.
- **C–F are independent** once B exists and may be reordered by product priority.
  Recommended order: **C → F → D → E** (screenplay is most mature → series has the
  richest existing backend → graphic novel → stage, which is the most stranded).
- **G is cross-cutting**, applied per mode as each of C–F matures.
- **H is design-now, build-last**: its decisions constrain B's API shape, so its
  *boundaries* must be drawn early even though the work happens last.

---

## Phase A — Stabilization Before New Work

**Goal.** Guarantee the foundation is safe before any non-novel feature work begins:
project data isolation, a stable Manuscript, no outline-into-manuscript leakage,
working Undo/Redo, autosave + close-save prompt, and data safety.

**Why it matters.** The comparison's #1 risk is reintroducing the hard-won
outline→manuscript leak and breaking project isolation. Every later phase writes to
the same surfaces; if those aren't stable, new work compounds instability. The papers'
human-control principle (DuoDrama §7) is meaningless if data can be silently lost or
cross-contaminated.

**Research basis.** DSR §4 (planning vs. body separation must hold); DuoDrama §7
(preserve user authority / never lose user decisions); R² §3 (don't let
inconsistencies propagate).

**Affected Logosforge systems.** `main_window.py` (`_switch_project`, `closeEvent`,
focus-tracking, `_modified_since_save`), `writing_core_view.py`, `plan_view.py`,
`outline_actions.py`, `autosave.py`, `db/database.py`, project lifecycle/events.

**Implementation tasks.** *(Per session history, most of these are already DONE; this
phase is a verification + regression-lock gate, not new build.)*
- Confirm `_switch_project` clears all caches/subsystems and rebuilds per project.
- Confirm Manuscript body = `scene.content` only; placeholder is "Start writing…".
- Confirm Outline writes `summary`/structure only, never `content`.
- Confirm Edit-menu Undo/Redo route via `_last_edit_widget` focus tracking.
- Confirm autosave does not clear `_modified_since_save`; close prompt fires.
- Confirm source-path de-duplication prevents duplicate imports.

**Tests required.**
- Project isolation: switch A→B→A leaves no stale outline/manuscript/PSYKE.
- Leak guard: generated outline never appears in any `_SceneEditor` body.
- Undo/Redo via menu while focus is on each editor type.
- Close with unsaved edits prompts Save/Don't Save/Cancel.
- New project = empty Outline, empty chapters, empty scenes.
- *(These largely exist: `test_outline_consolidation.py`, `test_mode_aware_units.py`,
  etc. — extend rather than rewrite.)*

**Risks.** Treating A as "already done" and skipping the regression lock; a later
phase silently regresses isolation or the leak guard.

**Defer list.** Any new mode capability; any new AI surface; any data-model change.

**Acceptance criteria.**
- ✅ Full existing test suite green.
- ✅ Project-isolation, leak-guard, undo/redo, and close-save tests all pass.
- ✅ No new mode code merged until the above hold.

---

## Phase B — Shared Non-Novel Core *(the leverage phase)*

**Goal.** Build the medium-agnostic narrative infrastructure that all four modes
consume: a **primary-unit adapter**, an **engine-driven Outline hierarchy**, a
**scene/beat planning layer**, **AI-output validation**, and an enforced
**planning-text vs. body-text separation**.

**Why it matters.** This is the single highest-leverage phase. The audit's central
finding is that rich mode logic exists below the surface but the **Outline collapses
to Act→Scene** and the **unit label is generic**. Fixing the shared core once makes
C–F small. Skipping B forces every mode to reinvent structure → four divergent apps.

**Research basis.** DSR §1 (decompose structure from prose); R²/DSR §4 (scene outline
is an intermediate object before writing); R² §3 (validate generated structure before
it lands).

**Affected systems.** `writing_modes.py` (`engine_structural_units`, primary-unit
adapter), `outline_actions.py` (`outline_unit_labels`, `validate_mode_outline`,
`build_mode_outline_prompt`), `ui/plan_view.py` (`build_plan_tree`, `PlanView`),
`narrative_engines/*` (already define hierarchies), `db/database.py` (planning rows).

**Implementation tasks.**
1. **Primary-unit adapter (shared).** Extend the existing
   `primary_unit_label`/`current_add_button_label` so each mode reports its *true*
   unit vocabulary (Screenplay=Scene, GN=Page/Panel, Stage=Scene, Series=Episode),
   while storage stays on the existing tables. Adapter returns labels + the canonical
   unit type per mode.
2. **Engine-driven Outline hierarchy (shared).** Make `PlanView`/`build_plan_tree`
   consult `engine_structural_units(engine)` instead of hardcoding Act→Chapter.
   Render the engine's hierarchy generically (depth-flexible tree).
3. **Scene/beat planning layer (shared).** A common planning row model
   (`summary`/goal/beat) that any mode populates; never touches `content`.
4. **AI-output validation (shared).** Generalize `validate_mode_outline` +
   `repair_outline_ops` into a mode-parameterized validate-before-apply contract
   usable by every generation path (reject prose-as-structure, empty nodes, preamble).
5. **Planning vs. body invariant (shared).** Encode the "structure→`summary`,
   prose→`content`" rule as a single enforced contract with a test fixture all modes
   inherit.

**Tests required.**
- Adapter returns correct unit label/type per mode.
- Outline renders the *engine* hierarchy per mode (not Act→Scene) for all four modes.
- Planning rows carry `summary`/structure with empty `content` across all modes.
- Validation rejects prose/empty/preamble for each mode's hierarchy.
- Switching modes re-derives hierarchy with no stale nodes.

**Risks.** Outline hierarchy change touches the most load-bearing surface — risk of
visual regressions or breaking existing scene-derived trees. Depth-flexible rendering
must degrade gracefully for sparse projects.

**Defer list.** Mode-specific *vocabulary* polish (lands in C–F); causal-graph
generation (Phase B only standardizes the *planning* object, not causal edges —
those are introduced as shared infra but populated per mode in C/F); any export.

**Acceptance criteria.**
- ✅ All four modes show their engine hierarchy in Outline.
- ✅ One shared validate-before-apply path; planning/body separation test passes for
  every mode.
- ✅ No regression in Phase A criteria.
- ✅ Adding a new mode requires only a vocabulary table, not new Outline code.

---

## Phase C — Screenplay Mode

**Goal.** Realize the full DSR/R² screenplay pipeline on the shared core:
**Outline → scene plan → formatted screenplay**, Fountain export, dialogue/action
separation, visual-action checks, and causal scene links.

**Why it matters.** Screenplay is the papers' home turf and Logosforge's most mature
mode — it's the proving ground for the shared core and the place causal links already
half-exist (`screenplay_graph`, `screenplay_setup_payoff`).

**Research basis.** DSR §1/§5 (decompose, then convert to format); R² §2 (causal scene
links); R² §4 (scene plan before scene); DSR §5 ("show, don't tell" / visual action).

**Affected systems.** `writing_formats.py` (screenplay elements), `screenplay_fountain.py`,
`screenplay_fdx_export.py`, `screenplay_docx_export.py`, `screenplay_graph.py`,
`screenplay_setup_payoff.py`, `screenplay_diagnostics.py`, `screenplay_subtext.py`,
`ui/export_data_dialog.py`/export wiring.

**Implementation tasks.**
1. **Outline→scene-plan→screenplay flow** on the Phase-B planning layer (scene plan =
   goal/place/character experience; body generated/written separately).
2. **Wire the professional Fountain exporter** (`export_screenplay_fountain_result`)
   into the export dialog (today the dialog calls the generic one).
3. **Dialogue/action separation** surfaced as a check (action vs. dialogue ratio,
   parenthetical overuse — `screenplay_diagnostics.py` already computes these).
4. **Visual-action / "show don't tell" check** (DSR): flag internal-state language in
   action lines (logic exists in diagnostics — surface it).
5. **Causal scene links (shared infra, screenplay vocabulary):** expose
   `screenplay_setup_payoff` edges through the shared causal-link layer introduced in B.

**Tests required.**
- Outline→scene-plan produces planning rows; manuscript body stays empty until written.
- Fountain export round-trips; professional exporter reachable from UI.
- Diagnostics flag dialogue dominance / on-the-nose / internal-state in action.
- Setup/payoff edges appear as shared causal links.

**Risks.** Surfacing experimental exporters (FDX 🧪) as if authoritative; mixing format
into the planning stage (must keep scene-plan format-free per DSR).

**Defer list.** R² Reader/Rewriter *auto-generation* from graph (Phase deferred —
see Phase G/deferred); page-accurate PDF pagination.

**Acceptance criteria.**
- ✅ A screenplay can be planned (scene plan), then written, then exported to Fountain
  from the UI, with planning never leaking into body.
- ✅ Visual-action and dialogue/action checks reachable.
- ✅ Setup/payoff causal links visible via shared infra.

---

## Phase D — Graphic Novel Mode

**Goal.** Scene → **page/panel breakdown**; separation of **caption / dialogue /
visual beat**; **image-text balance**; **page-turn logic**.

**Why it matters.** GN has the deepest visual model (`GraphicNovelPage/Panel`,
`psyke_visual`, page-turn rhythm) but the least reach into Outline/Assistant/Export.
It's the clearest case of "value built, not delivered."

**Research basis.** DSR §1 (decompose to the medium's unit); R²'s "interesting/
transition" axes ↔ page-turn rhythm; DSR §5 (visual, not internal, expression).
Mode-transfer §8 (panels/page-turns/image-text balance).

**Affected systems.** `graphic_novel_plot.py`, `graphic_novel_manuscript.py`,
`graphic_novel_review.py`, `ui/graphic_novel_pages_view.py`,
`ui/graphic_novel_page_canvas.py`, `writing_formats.py` (GN elements),
`models.py` GN tables.

**Implementation tasks.**
1. **Page/panel as the GN primary unit** via the Phase-B adapter (label "Page"/"Panel",
   surface the GN hierarchy in Outline: Issue→Sequence→Page→Panel).
2. **Caption/dialogue/visual-beat separation** in the planning layer (panel = visual
   beat + dialogue refs + caption, kept distinct).
3. **Image-text balance + page-turn checks** surfaced from `graphic_novel_review.py`
   and `graphic_novel_plot.py` (balloon overload, text-heavy panels, page-turn
   setup/reveal).
4. **GN panel-script export** (mode-specific layer) — a real deliverable, replacing
   generic PAGE-N text.

**Tests required.**
- GN Outline shows page/panel hierarchy.
- Panel planning separates caption vs. dialogue vs. visual beat.
- Review checks (clutter, balloon overload, page-turn) reachable.
- Panel-script export produces a structured visual breakdown.

**Risks.** Page/panel-as-unit touches the unit model — data-model churn risk; must not
break existing scene-prose projects. ComfyUI image export remains a stub (do not wire).

**Defer list.** ⏳ Image generation / ComfyUI connector; automated layout suggestion.

**Acceptance criteria.**
- ✅ GN projects plan in pages/panels via Outline; panel-script export available.
- ✅ Image-text balance + page-turn checks reachable; no regression to scene-prose GN.

---

## Phase E — Stage Script Mode

**Goal.** Acts/scenes; **stage directions**; **entrances/exits**; **actor intention**;
**playable action**; **prop continuity**.

**Why it matters.** Stage is the most stranded mode — `psyke_theatre`,
`stage_script_plot`, and `stage_script_review` are real but the review engine isn't
even wired. High value-per-effort because the logic already exists.

**Research basis.** DuoDrama §6 (actor intention ↔ character experience/internal
state); R² §2 (prop continuity / motivated exits ↔ dependency links); mode-transfer §8
(performance logic, entrances/exits, playable action).

**Affected systems.** `stage_script_plot.py`, `stage_script_review.py`, `psyke_theatre.py`,
`writing_formats.py` (stage elements), `models.py` (`StageEntranceExit/Cue/Business`),
`ui/chat_view.py` (command wiring).

**Implementation tasks.**
1. **Stage hierarchy in Outline** (Act→Scene→Beat→Entrance/Cue) via Phase-B core.
2. **Wire `stage_script_review.py` to a `/stage` command** (parity with `/gn`, `/series`).
3. **Entrances/exits + prop continuity** surfaced as checks (logic exists).
4. **Actor intention / playable action** surfaced from `psyke_theatre` objectives
   (stage_objective, subtext_strategy) into the planning layer.
5. **Stage play-format export** (mode layer) replacing generic ACT/SCENE text.

**Tests required.**
- `/stage` command returns review checks.
- Entrance/exit + prop continuity checks reachable.
- Outline shows the stage hierarchy.
- Play-format export produces stage-appropriate markup.

**Risks.** Lowest-risk mode (mostly wiring existing logic); main risk is leaving it
unwired again. Keep stage metadata optional so generic scene projects still work.

**Defer list.** ⏳ Technical cue-sheet generation; lighting/sound plot exports.

**Acceptance criteria.**
- ✅ Stage review reachable via command; entrances/exits + props checkable; play-format
  export available; Outline shows stage hierarchy.

---

## Phase F — Series Mode

**Goal.** **Season/episode structure**; **recurring threads**; **A/B/C plots**;
**episode arcs**; **continuity across episodes**.

**Why it matters.** Series has the richest cross-time logic (`SeriesArc`,
`psyke_series`, `series_plot`, wired `/series` review) — the closest thing to R²'s
cross-scene causal lines — but the Outline collapse and missing episode/season exports
cripple it.

**Research basis.** R² §2 (setup→payoff across episodes ↔ causal lines); DuoDrama §6
(`psyke_series` long-term goals/unresolved conflicts ↔ character internal state);
mode-transfer §8 (episode arcs, continuity, recurring threads, season logic).

**Affected systems.** `series_plot.py`, `series_review.py`, `psyke_series.py`,
`writing_formats.py` (series elements), `models.py` (`Season/Episode/EpisodePlotline/
SeriesArc`), `knowledge_graph/*` (arc edges), export.

**Implementation tasks.**
1. **Season→Episode→Act→Scene hierarchy in Outline** via Phase-B core; Episode as the
   true primary unit through the adapter.
2. **Surface SeriesArc setup/payoff as shared causal links** (cross-episode) and as
   Graph edges (KG currently omits arc edges).
3. **A/B/C plot + recurring-thread planning** surfaced (logic exists in `series_plot`).
4. **Continuity-across-episodes** checks via wired `/series` review (already wired —
   extend coverage).
5. **Series exports** (mode layer): episode outline, season bible, scene list.

**Tests required.**
- Outline shows season/episode hierarchy; Episode is the primary unit.
- Arc setup/payoff appears as causal links + graph edges.
- A/B/C plots + threads plannable.
- Episode-outline / season-bible / scene-list exports produced.

**Risks.** Episode-as-primary-unit is the largest unit-model realignment — highest
data-model churn risk; stage behind Phase-B adapter and keep Scene fallback.

**Defer list.** ⏳ Cross-season bible automation; automated arc-balancing suggestions.

**Acceptance criteria.**
- ✅ Series projects plan in seasons/episodes; arcs surface as causal/graph links;
  episode/season/scene-list exports available; continuity checks reachable.

---

## Phase G — Reflection and Refinement *(cross-cutting C–F)*

**Goal.** Deliver reflective, human-confirmed feedback across all modes:
**Counterpart**, **Logos inline feedback**, **internal/external perspective checks**,
**PSYKE consistency checks**, and **human-confirmed apply**.

**Why it matters.** DuoDrama's core result: for professionals, *reflective feedback
beats more generated text*. Logosforge has the engines (Counterpart, reviews,
continuity, controlled_apply) but most are library-only or screenplay-only. This phase
is mostly *surfacing + parameterizing*, not new logic.

**Research basis.** DuoDrama §6 (experience-role vs. evaluation-role; reflection over
generation); DuoDrama §7 + R² §3 (human-confirmed, validated apply); R² §3 (consistency
checking).

**Affected systems.** `counterpart.py`, `logos/actions.py` (mode-aware actions),
`assistant_context_policy.py` (per-mode context blocks), `continuity/*`,
`revision_intelligence/*`, `controlled_apply/*`, `rewrite_sandbox/*`, PSYKE context
builders (`build_visual/theatre/series_memory_context`).

**Implementation tasks.**
1. **Surface Counterpart** as a read-only reflection panel (external/evaluation role;
   it never mutates).
2. **Per-mode Assistant context blocks** mirroring the screenplay pattern — mostly
   *routing* the existing PSYKE context builders by mode.
3. **Mode-aware Logos actions** (the `modes=` infra already supports it).
4. **PSYKE consistency checks** surfaced via continuity/revision_intelligence
   (currently library-only).
5. **Internal/external perspective checks:** treat Counterpart as the *external*
   evaluator; use PSYKE character-state (goals/knowledge/unresolved conflicts) as the
   *internal* lens for feedback. (An autonomous "experience-role" generator is
   **deferred** — see below — but the *internal-state-grounded critique* can be built
   from existing PSYKE data.)
6. **Human-confirmed apply everywhere:** ensure all AI mutations route through
   `controlled_apply`/confirm gates (validate-before-apply from Phase B).

**Tests required.**
- Counterpart panel returns critique without mutating content.
- Each mode's Assistant context includes mode-specific blocks.
- Mode-aware Logos actions surface only in their mode.
- PSYKE-grounded consistency checks reachable per mode.
- No AI action mutates data without explicit confirm.

**Risks.** Exposing 🧪 engines as authoritative; an internal-perspective critic with no
grounded state producing hallucinated character feedback (mitigated by sourcing from
PSYKE data, not free generation); over-prompting the user with feedback.

**Defer list.** ⏳ DuoDrama-style *autonomous experience-role generation* (inhabit a
character to *generate* reactions) — build only after PSYKE state is fully surfaced and
Counterpart (external) is trusted. ⏳ Any auto-apply.

**Acceptance criteria.**
- ✅ Counterpart reachable; per-mode Assistant + Logos feedback live; PSYKE consistency
  checks reachable; every AI mutation is confirm-gated and validated.

---

## Phase H — Commercial React/Electron/Web Transfer *(design now, build last)*

**Goal.** Define the boundary between the **Python core/API** (durable narrative
engine) and a future **React/Electron/Web UI**, so PySide isn't over-built and the
core is UI-agnostic.

**Why it matters.** The shared core (Phase B) is the long-term asset. If business
logic leaks into PySide views, a future web/Electron client must reimplement it. H's
boundary decisions constrain B's API shape, so they must be *decided early* even though
the build is last.

**Research basis.** Architectural, not paper-specific — but DSR's decomposition implies
clean stage boundaries (structure/prose/format) that map naturally to API endpoints;
DuoDrama §7's human-control implies the *apply gate* must live in the core, not the UI.

**Affected systems.** `api/*`, all core modules (must stay UI-free), all `ui/*` (must
stay logic-free), export/validation/apply services.

**Implementation tasks (planning/boundary-drawing, not UI build).**
1. **Stay in Python core/API:** primary-unit adapter, Outline hierarchy, planning
   layer, causal-link model, Timeline model, PSYKE memory, validation,
   controlled-apply, all exporters, all `*_review`/diagnostics engines. These must be
   callable headlessly via the API with no Qt dependency.
2. **Move to React UI (future):** rendering of Outline tree, Manuscript editor, Canvas
   Plot board, Timeline board, panels for Assistant/Counterpart/Logos. UI = views over
   API responses; **no business logic**.
3. **Do not over-build in PySide:** treat PySide views as a *reference client*. Avoid
   embedding mode rules, validation, or apply logic in views; route through the core.
4. **API contract for the apply gate:** preview→confirm→apply must be an API
   transaction so any client preserves human authority identically.

**Tests required.**
- Core modules import with no Qt dependency (headless import test).
- API can drive plan→write→validate→export for each mode without the UI.
- Apply gate enforced at the API layer (confirm required), not just in PySide.

**Risks.** Premature React build before the core API stabilizes; logic duplicated
across PySide and web; the apply gate enforced only in UI (a web client could bypass
it). Over-investing in PySide polish that a web client will discard.

**Defer list.** ⏳ Actual React/Electron implementation; cloud sync/multi-user;
real-time collaboration. (Boundaries decided now; code built after C–G.)

**Acceptance criteria.**
- ✅ Core runs headless (no Qt) and exposes plan/write/validate/export/apply via API.
- ✅ The apply gate is enforced in the core/API.
- ✅ A documented contract states what stays in Python vs. moves to React, with no
  business logic in PySide views.

---

## Cross-Phase Summary

| Phase | Theme | New logic vs. surfacing | Primary risk | Gate to next |
|---|---|---|---|---|
| **A** | Stabilize | Verify/lock (mostly done) | Skipping the regression lock | Tests green |
| **B** | Shared core | New (high leverage) | Outline surface churn | All modes show engine hierarchy + shared validate/apply |
| **C** | Screenplay | Mostly surfacing | Exposing 🧪 exporters | Plan→write→Fountain w/o leak |
| **D** | Graphic Novel | Surfacing + unit change | Unit-model churn | Page/panel Outline + panel-script export |
| **E** | Stage Script | Mostly wiring | Leaving it unwired | `/stage` + play-format export |
| **F** | Series | Surfacing + unit change | Episode-as-unit churn | Season/episode Outline + exports |
| **G** | Reflection | Surfacing + routing | 🧪 output as authoritative | Counterpart + per-mode feedback, all confirm-gated |
| **H** | Commercial | Boundary design | Premature web build / logic leak | Headless core + API apply gate |

**Sequencing discipline.** A → B are sequential and mandatory. C–F are independent
post-B (recommended C → F → D → E). G is layered onto each mode as it matures. H's
*boundaries* are drawn during B; H's *code* is last.

---

## Consolidated Deferral List ⏳

- R² Reader/Rewriter **auto-generation** (extract causal DAG from source; generate
  scenes from graph) — needs a trusted causal object + HAR-equivalent first.
- DSR **rich-prose intermediate + learned format conversion** — training/data pipeline,
  out of alpha scope; live format engine suffices near-term.
- DuoDrama **autonomous experience-role generator** — build only after PSYKE state is
  surfaced and external Counterpart is trusted.
- **ComfyUI / image generation** for Graphic Novel.
- **Auto-apply** of any AI suggestion (violates human-control principle).
- **React/Electron/Web build, cloud sync, real-time collaboration** (Phase H code).
- Cross-season bible automation; automated arc-balancing; technical cue-sheets;
  page-accurate PDF pagination.

---

## Consolidated Risk Register

1. **Reintroducing the outline→manuscript leak** (every write-path phase) — mitigated
   by the Phase-B planning/body invariant test inherited by all modes.
2. **Project-isolation regression** — mitigated by Phase-A gate + isolation tests.
3. **Causal edges before validation → hallucinated dependencies** (R² lesson) —
   mitigated by validate-before-apply in B and confirm gates in G.
4. **Unit-model churn** (GN page/panel, Series episode) — staged behind the Phase-B
   adapter with Scene fallback; never destructive.
5. **Exposing experimental/library-only engines as authoritative** — label
   confidence; gate 🧪 features.
6. **Format welded into drafting** (DSR violation) — keep planning format-free; format
   only at export; do not destabilize the live editor.
7. **Logic leaking into PySide** (Phase H) — enforce headless-core rule from B onward.
8. **Autonomy creep** (DuoDrama §7) — every mutation stays confirm-gated; no auto-apply.

---

*End of roadmap. No code was written; no features were added; nothing was implemented.
This document sequences existing research/audit findings into safe, dependency-ordered
phases for a future, separately-approved implementation effort.*
