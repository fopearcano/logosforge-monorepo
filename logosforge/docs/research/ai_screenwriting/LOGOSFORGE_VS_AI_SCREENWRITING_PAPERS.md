# Logosforge vs. AI Screenwriting Papers — Comparative Analysis

**Type:** Analysis only. No code changed, no fixes implemented, no new systems.
**Inputs:**
1. `AI_SCREENWRITING_RESEARCH_SUMMARY.md` (R², DSR, DuoDrama)
2. `LOGOSFORGE_NON_NOVEL_MODE_AUDIT.md` (12-area, 4-mode audit)
3. Current Logosforge codebase (`/home/user/logosforge`)

**Modes compared:** Screenplay, Graphic Novel, Stage Script, Series.

**Classification legend**

| Symbol | Meaning |
|---|---|
| ✅ | Aligned — Logosforge does what the paper argues for |
| ⚠️ | Partially aligned — present but incomplete, generic, or not surfaced |
| ❌ | Missing — concept absent for this mode/surface |
| 🧪 | Experimental / unstable — exists but gated, stubbed, or library-only |
| ⏳ | Deferred — intentionally out of alpha scope |

> The three papers were sourced from arXiv for the summary; the original PDFs are
> now also present in this folder (`2503.15655v1.pdf`, `2510.23163v3.pdf`,
> `2602.05854v1.pdf`) and are consistent with the summary used here.

---

## 1. Executive Summary

Logosforge and the three papers **agree on the most important thing**: good
screenwriting is a *decomposed, human-controlled, reflection-friendly pipeline*,
not one-shot generation. Where they diverge is **depth and reach**, not philosophy.

**The strong alignments (Logosforge is already on the papers' side):**
- **Scene-outline-before-scene-writing (R²/DSR §4)** is Logosforge's single
  cleanest win. Outline produces structured scene planning rows (`summary`), the
  Manuscript body is strictly `content`, and the two are provably separated by
  tests. The historical "outline text leaking into manuscript" bug was fixed, which
  is exactly the failure mode DSR warns about.
- **Human-in-the-loop control (DuoDrama §7)** is a first-class principle:
  confirm-gated outline apply, `controlled_apply` preview/confirm, `rewrite_sandbox`
  generation that never mutates canonical content, and an Assistant that routes
  Outline edits through an apply path rather than mutating directly.
- **Outline ↔ Manuscript ↔ Export are genuinely separate surfaces** — the spine of
  DSR's decomposition thesis.

**The structural divergences (where the papers exceed Logosforge):**
- **R²'s causal plot graph (§2)** is the biggest conceptual gap. Logosforge's
  "Plot" is a *free visual canvas with untyped links and no causality*; only the
  Screenplay **Graph** models setup/payoff and causal edges. There is no
  Reader-style automatic causal extraction and no Rewriter-style generation *from* a
  graph in any mode.
- **DSR's "rich prose intermediate" (§1/§5)** has no analog. Logosforge goes
  Outline (structure) → Manuscript (prose **with format applied live**) → Export
  (format). The Manuscript *mixes formatting into the drafting surface* via block
  grammar — the opposite of DSR's "keep format out of the creative stage."
- **DuoDrama's dual-perspective critic (§6)** is half-present: `counterpart.py` is a
  pure *external/evaluation* critic and is **not even wired into the UI**. There is
  **no internal/"experience-role" critic** that inhabits a character to ground
  feedback.
- **Hallucination-aware refinement (R² §3)** exists only as outline validation +
  several **library-only** consistency engines (continuity, revision_intelligence).
  There is no iterative re-grounding loop, and most checkers can't be reached.

**Mode-transfer reality:** the papers are screenplay-centric, but Logosforge's
*non-screenplay* modes are where these ideas are least delivered. Graphic Novel,
Stage, and Series have rich **data/PSYKE/plot/review** depth (often exceeding what
the screenplay-only papers contemplate) but almost none of it reaches the
generation/feedback/format surfaces the papers care about.

**One-line verdict:** Logosforge has the *correct decomposition and the correct
control posture*, but it under-delivers the papers' two highest-value mechanisms —
**causal structure** (R²) and **dual-perspective reflective feedback** (DuoDrama) —
and it partially violates DSR by **welding format onto the drafting surface**.

---

## 2. Comparative Matrix

Per research dimension × mode. The right column is the cross-mode architectural read.

| # | Research dimension | Screenplay | Graphic Novel | Stage Script | Series | Architectural read |
|---|---|---|---|---|---|---|
| 1 | **Decomposed generation** (DSR) | ⚠️ | ⚠️ | ⚠️ | ⚠️ | Outline/Manuscript/Export *are* separate ✅, but no rich-prose intermediate and format is applied during drafting |
| 2 | **Causal plot graph** (R²) | ⚠️ | ❌ | ❌ | ⚠️ | Screenplay Graph models setup/payoff; Canvas Plot has no causality; no auto-extraction or generate-from-graph anywhere |
| 3 | **Hallucination-aware refinement** (R²) | ⚠️ | ⚠️ | ⚠️ | ⚠️ | Outline validate/repair ✅; continuity & revision-intelligence real but 🧪 library-only; no iterative re-ground loop |
| 4 | **Scene outline before writing** (R²/DSR) | ✅ | ✅ | ✅ | ⚠️ | Strongest alignment; Series weaker because Episode is the true primary unit, not Scene |
| 5 | **Format vs. creative content** (DSR) | ⚠️ | ⚠️ | ⚠️ | ⚠️ | Export separate ✅; but Manuscript enforces mode formatting live → format mixed into drafting |
| 6 | **Reflection-oriented feedback** (DuoDrama) | ⚠️ | ⚠️ | ⚠️ | ⚠️ | Counterpart = external critic 🧪 (unwired); review engines real (GN/Series wired, Stage not); no internal/experience critic |
| 7 | **Human-in-the-loop control** (DuoDrama) | ✅ | ✅ | ✅ | ✅ | Confirm-gated apply, non-mutating sandbox, Logos non-invasive — uniformly strong |
| 8 | **Mode transfer** (panels/stage/episodes) | n/a | ⚠️ | ⚠️ | ⚠️ | Rich mode *models* exist; concepts don't reach Outline/Assistant/Format/Export for non-screenplay modes |

**Reading the matrix:** the two **green columns are dimensions 4 and 7** (outline-first
and human control) — Logosforge's philosophical core. Every other dimension is amber
or worse, and the **causal-graph row (2)** is the only one with hard ❌s.

---

## 3. Screenplay Mode Analysis

Screenplay is the mode the papers describe and the mode Logosforge supports most
deeply — yet it still only *partially* matches the papers.

- **Decomposed generation (DSR) ⚠️.** Outline (structure) → Manuscript (prose) →
  Export (Fountain/FDX/DOCX) is a real three-stage separation
  (`outline_actions.py`, `writing_core_view.py`, `screenplay_*_export.py`). **But**
  there is no DSR-style "screenplay-oriented novelization" intermediate, and the
  Manuscript applies screenplay block grammar *as you type* (`writing_core_view.py`
  L187-236) — so the creative stage is already format-aware, which DSR explicitly
  argues against.
- **Causal plot graph (R²) ⚠️.** This is Logosforge's closest approach to R².
  `screenplay_graph.py` (14 node types incl. setup/payoff/motif/promise/threat; 12
  edge types incl. `setup_to_payoff`, `object_plant_to_use`) plus
  `screenplay_setup_payoff.py` give real causal/dependency structure. **But** it is
  *analysis over existing scenes*, not R²'s *Reader that extracts a causal DAG from
  source* nor a *Rewriter that generates scenes from the graph*. No cycle-breaking,
  no graph-driven outline generation.
- **Hallucination-aware refinement (R²) ⚠️/🧪.** Outline generation is validated
  and repaired (`repair_outline_ops`, `validate_mode_outline`). Screenplay
  diagnostics, subtext, and continuity exist but are **library-only**. No iterative
  refine-against-source loop like HAR.
- **Scene outline before writing (R²/DSR) ✅.** `apply_outline_as_scenes` writes
  `summary` with empty `content`; Manuscript renders only `content`. Clean.
- **Format vs. creative (DSR) ⚠️.** Export is fully separate and professional
  (though the *pro* exporters are 🧪 library-only; the dialog calls the generic ones).
  The drafting surface itself is format-enforcing — partial misalignment with DSR.
- **Reflection (DuoDrama) ⚠️/🧪.** Logos has 15+ screenplay-specific actions
  (`logos/actions.py`); Assistant has 6+ screenplay context blocks. Counterpart
  (external critic) exists but is unwired. No experience-role critic.
- **Human control (DuoDrama) ✅.** Outline confirm dialog, controlled_apply,
  rewrite_sandbox apply-gate.

**Screenplay verdict:** the richest mode, and the only one with real causal-graph
machinery — but it is *analytic, not generative-from-graph*, its best engines are
unreachable, and it mixes format into drafting.

---

## 4. Graphic Novel Mode Analysis

Graphic Novel has the **deepest visual data model** of any mode and the **least
reach into the paper-relevant surfaces**.

- **Decomposed generation ⚠️.** Outline collapses to Act→Scene (no
  Issue→Sequence→Page→Panel); `graphic_novel_manuscript.py` `generate_draft` is a
  **one-way scaffold**, not a live decomposition pipeline.
- **Causal plot graph ❌.** No `graphic_novel_graph`. `graphic_novel_plot.py` models
  *visual pacing* (density→rhythm, page-turn setup/reveal, motif recurrence) — a
  *rhythm* graph, not a *causal* one. Close in spirit to R²'s "interesting/transition"
  axes, but not causality.
- **Hallucination-aware refinement ⚠️.** `graphic_novel_review.py` is a real
  deterministic critic (visual clutter, balloon overload, internal-state-without-
  visual, splash justification) **wired via `/gn`** — effectively a
  consistency/quality checker, though not an AI re-grounding loop.
- **Scene outline before writing ✅ (data) / ⚠️ (surface).** `Page/Panel` tables
  are real and editable in a *separate* `GraphicNovelPagesView`, but the **Outline**
  doesn't express the panel hierarchy.
- **Format vs. creative ⚠️.** `writing_formats.py` defines 11 GN elements
  (panel/caption/sfx/art_direction…) applied live in Manuscript; export is only
  generic PAGE-N text. `graphic_novel_ai_export` (ComfyUI) is a 🧪 disabled stub.
- **Reflection ⚠️.** Strong `psyke_visual.py` (silhouette, color identity, motif
  recurrence, visual callbacks) — excellent *character/world external state* — but
  no Assistant/Logos mode blocks, so it doesn't reach the writer as feedback.
- **Mode transfer (§8) ⚠️.** Panels/page-turns/image-text balance are modeled
  (this is genuinely *beyond* what the screenplay papers cover) but stranded below
  the Outline/Assistant/Format/Export line.

**GN verdict:** the model layer arguably *exceeds* the papers (visual rhythm + motif
memory); the delivery layer is the weakest after Stage.

---

## 5. Stage Script Mode Analysis

Stage Script is the **most stranded** mode: strong logic, least reach.

- **Decomposed generation ⚠️.** Outline collapses to Act→Scene (ignores
  `beat`/`entrance_exit`/`cue`). Three-surface separation holds generically.
- **Causal plot graph ❌.** No `stage_script_graph`. `stage_script_plot.py` models
  *theatrical pressure* (scene objective, dramatic turn, entrances/exits, props) —
  dependency-ish (prop continuity, motivated exits) but not a causal DAG.
- **Hallucination-aware refinement ⚠️/🧪.** `stage_script_review.py` is a real
  critic (playable objective, motivated exit, prop continuity, blocking) — but
  **NOT wired to any command** (unlike `/gn` and `/series`). Strong logic, zero reach.
- **Scene outline before writing ✅ (data).** Scene + `StageEntranceExit/Cue/Business`
  tables; planning separable from body. Outline surface doesn't express the
  entrance/cue layer.
- **Format vs. creative ⚠️.** 10 stage elements (stage_direction/aside/cue) applied
  live; export is generic ACT/SCENE text only — no play-format markup or cue scripts.
- **Reflection ⚠️.** `psyke_theatre.py` models objectives, who-pressures-whom,
  entrances/exits, props — a genuine *performance/relational* state layer (resonates
  with DuoDrama's character-experience idea) — but no Assistant/Logos delivery and
  the review engine is unwired.
- **Mode transfer (§8) ⚠️.** Performance logic (entrances/exits, playable action) is
  modeled but not surfaced anywhere a writer interacts.

**Stage verdict:** the clearest "value built, value not delivered" case in the codebase.

---

## 6. Series Mode Analysis

Series has the **strongest cross-episode/continuity logic** and the best feedback
wiring after screenplay — but the Outline/format mismatch is acute.

- **Decomposed generation ⚠️.** Outline collapses to Act→Scene (no
  Season→Episode→Act→Scene). The true primary unit (`Episode`) isn't the Outline's or
  Manuscript's unit.
- **Causal plot graph ⚠️.** `SeriesArc` models setup→payoff *across episodes*
  (`get_setup_payoff_chains`, mystery threads) — the closest thing to R²'s
  cross-scene causal lines in any non-screenplay mode — **but** arcs are not surfaced
  as Graph edges (`get_series_arcs` exists; KG doesn't emit arc edges).
- **Hallucination-aware refinement ⚠️.** `series_review.py` (A/B/C balance,
  cliffhanger presence, unresolved payoff, arc movement, character isolation) is a
  real critic **wired via `/series`**. Effectively a continuity/consistency checker.
- **Scene outline before writing ⚠️.** Episode/plotline planning exists, but because
  Outline is Act→Scene and Manuscript labels units "Scene," the **episode-level
  planning↔writing relationship isn't expressed** in the two core surfaces.
- **Format vs. creative ⚠️.** 16 series elements (season/episode headers, A/B/C
  plots, teaser, cliffhanger) applied live; export is generic screenplay-ish text —
  **no episode outline, season bible, or scene list** (the canonical Series
  deliverables).
- **Reflection ⚠️.** `psyke_series.py` is the richest character-state layer:
  season_arc, episode_state, long_term_goal, unresolved_conflicts, relationship
  history, continuity flags. This is exactly DuoDrama-style *internal/relational
  state* — but it feeds `/series` checks, not an Assistant reflection surface.
- **Mode transfer (§8) ⚠️.** Episode arcs, continuity, recurring threads, season
  logic are all modeled (arguably the most paper-relevant non-screenplay work) but
  blocked at the Outline/format boundary.

**Series verdict:** best continuity/causality-across-time logic in the app; crippled
by the Outline collapse and missing episode/season exports.

---

## 7. Architecture Gaps

Ranked by how central the gap is to the papers' theses.

1. **No causal structure object (R² §2) — central gap.** "Plot" = free canvas with
   untyped links; causality lives only in screenplay analysis and series arcs, and is
   never *generated from* or *generated into*. Timeline has typed link types
   (causality/setup_payoff/dependency) that are largely unused outside screenplay.
2. **Outline collapses below the engine hierarchy (DSR §1, R² §4).** All non-novel
   modes flatten to Act→Scene even though engines define Sequence/Page/Panel /
   Beat/Entrance / Season/Episode. The *structure stage* discards mode structure.
3. **Format welded onto the drafting surface (DSR §5).** Manuscript applies mode
   block grammar live; DSR argues the creative stage must be format-free with format
   as a separate conversion. No "rich prose intermediate."
4. **Reflective feedback is half-built and under-wired (DuoDrama §6).** Counterpart
   (external critic) unwired; Stage review unwired; screenplay diagnostics
   library-only; **no internal/experience-role critic** at all.
5. **Mode intelligence doesn't reach the writer (§8).** PSYKE/plot/review depth for
   GN/Stage/Series is real but absent from Assistant, Logos, Outline, and Export.
6. **Pro/format deliverables missing or unreachable (DSR §5).** GN panel script,
   Stage play format, Series episode/season exports absent; pro screenplay exporters
   library-only.

---

## 8. What Logosforge Already Does Well

- ✅ **Outline-before-writing with strict body isolation (R²/DSR §4).** Planning
   (`summary`) and prose (`content`) are separated and test-guarded; the leak bug is
   fixed. This is the textbook behavior both R² and DSR prescribe.
- ✅ **Human-in-the-loop control (DuoDrama §7).** Confirm-gated outline apply,
   `controlled_apply` preview→confirm, non-mutating `rewrite_sandbox`, non-invasive
   Logos, Assistant that doesn't mutate canonical content directly. The app preserves
   user authority by construction.
- ✅ **Genuine surface decomposition.** Outline / Manuscript / Export are distinct —
   the backbone of DSR.
- ✅ **Outline validation/repair (partial HAR, R² §3).** `repair_outline_ops` +
   `validate_mode_outline` reject prose/empty/preamble outlines — a real (if narrow)
   anti-hallucination guard.
- ✅ **Mode-specific *models* and *critics*** that in places exceed the
   screenplay-only papers: visual rhythm + motif memory (GN), performance/relational
   state (Stage), cross-episode arcs + continuity (Series).
- ✅ **Screenplay causal/setup-payoff graph** — the one place R²-style causal
   structure genuinely exists.

---

## 9. What Logosforge Is Missing

- ❌ **A causal plot graph as a first-class, mode-general object** (R² §2): typed,
   weighted, acyclic event dependencies connected to scenes, usable by both planning
   and feedback. Today only screenplay analysis approximates it.
- ❌ **Generate-from-structure / structure-from-source** (R² Reader/Rewriter): no
   automatic causal extraction, no graph-driven outline/scene generation.
- ❌ **A rich-prose intermediate + pure format-conversion stage** (DSR §1/§5):
   Manuscript is format-aware; there is no "novelize then convert."
- ❌ **An internal/experience-role critic** (DuoDrama §6): all critique is external/
   structural; nothing inhabits a character to ground feedback.
- ❌ **Mode-aware Assistant/Logos for GN/Stage/Series**: generic `[Project Mode]`
   block only; no panel/blocking/episode context blocks; no non-screenplay Logos
   actions.
- ❌ **Professional non-screenplay exports**: GN panel script, Stage play format,
   Series episode outline/season bible/scene list.
- ⚠️ **Outline hierarchy per mode**: defined in engines, not rendered.
- 🧪 **Reachability**: Counterpart, Stage review, screenplay diagnostics, pro
   exporters, controlled_apply are built but not (fully) surfaced.

---

## 10. Recommended Implementation Priorities

*Analysis-level recommendations only — not a commitment, not a design.* Ordered by
**value-to-papers ÷ structural risk**, biased toward surfacing existing logic before
building new logic.

1. **Surface what already exists (lowest risk, high value).**
   - Wire `stage_script_review.py` to a `/stage` command (parity with `/gn`, `/series`).
   - Route the **professional** screenplay exporters into the export dialog.
   - Expose Counterpart as a read-only reflection panel (it never mutates).
   These deliver DuoDrama §6 and DSR §5 value with little architectural change.

2. **Generalize the Outline to the engine hierarchy (R²/DSR §1/§4).** Make
   `PlanView` consult `engine_structural_units(engine)` instead of hardcoding
   Act→Chapter. Highest *structural* payoff; addresses the most central gap below the
   causal graph.

3. **Per-mode Assistant context blocks (DuoDrama §6, §8).** Mirror the screenplay
   block pattern for GN (panels/motifs), Stage (entrances/blocking), Series
   (arcs/continuity). The PSYKE context builders (`build_visual/theatre/series_memory_context`)
   already exist — this is mostly *routing*, not new logic.

4. **Make causal/setup-payoff links mode-general (R² §2).** Lift screenplay
   setup/payoff + the existing `TIMELINE_LINK_TYPES` (causality/dependency) into a
   shared, mode-parameterized layer; surface Series arcs as graph edges. This is the
   first real step toward R² without building a Reader/Rewriter.

5. **Mode-aware Logos actions (DuoDrama §6).** The `modes=` infra already supports it;
   register GN/Stage/Series actions and always pass `writing_mode`.

---

## 11. What Should Be Deferred

- ⏳ **R² Reader/Rewriter auto-generation** (extract causal DAG from source; generate
   scenes from graph). High complexity, high hallucination surface, and it cuts
   against the app's human-control posture. Defer until the causal *object* (priority
   4) exists and is trusted.
- ⏳ **DSR rich-prose intermediate + learned format conversion.** Requires a
   training/data pipeline and a second model stage; out of scope for an alpha and
   redundant with the live format engine for now.
- ⏳ **Internal/experience-role critic (DuoDrama).** Valuable, but build *after*
   Counterpart (external) is actually wired and the PSYKE state layer is surfaced —
   otherwise there's no grounded state to inhabit.
- ⏳ **ComfyUI / image-generation export for GN.** Currently a disabled stub; a whole
   external-connector concern. Defer.
- ⏳ **Graph-driven outline generation for any mode.** Depends on priorities 2 and 4
   landing first.

---

## 12. Risks If Implemented Too Early

- **Causal graph before data trust → garbage edges (R²).** R² needed HAR + cycle-
   breaking precisely because naive causal extraction hallucinates. Shipping a causal
   graph without validation would manufacture false dependencies and undermine the
   Outline's current cleanliness.
- **Reader/Rewriter auto-generation → control regression (DuoDrama §7).** The app's
   strongest alignment is human authority. Autonomous generation-from-graph risks the
   exact "AI replaces the writer's decision" failure the papers caution against, and
   could reintroduce the outline→manuscript leakage that was hard-won to fix.
- **Decoupling format from Manuscript → UX disruption (DSR §5).** DSR's separation is
   right *for training pipelines*; ripping live formatting out of the drafting surface
   could break the editing experience writers already rely on. The paper's point can
   be honored by keeping *planning* format-free (already true) and *export* separate
   (already true) without destabilizing the editor.
- **Per-mode Assistant/Logos surge → mode drift & test load.** Adding mode-specific
   context everywhere risks inconsistent behavior across modes and a combinatorial
   test burden; it should follow, not precede, Outline generalization.
- **Surfacing library-only engines → exposing unstable output.** Counterpart, FDX
   (experimental), and diagnostics were kept internal for a reason; surfacing them
   without confidence/labeling could present 🧪 output as authoritative.
- **Episode/Page as Outline/Manuscript unit → data-model churn.** Realigning the
   primary unit for GN/Series touches the most load-bearing surfaces; premature change
   risks project-data regressions the alpha rules explicitly forbid.

---

## Appendix — Dimension → Evidence Index

| Dim | Paper | Logosforge evidence (file) |
|---|---|---|
| 1 Decomposed | DSR | `outline_actions.py`, `writing_core_view.py` L187-236, `export.py`, `screenplay_*_export.py` |
| 2 Causal graph | R² | `screenplay_graph.py`, `screenplay_setup_payoff.py`, `canvas_plot_view.py`, `models.py` TIMELINE_LINK_TYPES L1081, `series_plot.py` arcs |
| 3 HAR | R² | `outline_actions.py` (repair/validate), `continuity/`, `revision_intelligence/`, `controlled_apply/`, `rewrite_sandbox/` |
| 4 Outline-first | R²/DSR | `outline_actions.py` apply_outline_as_scenes, `writing_core_view.py` body=content, tests `test_outline_consolidation.py` |
| 5 Format vs creative | DSR | `writing_formats.py`, `screenplay_fountain.py`, `export.py` `_fmt_*_text` |
| 6 Reflection | DuoDrama | `counterpart.py`, `logos/actions.py`, `psyke_visual/theatre/series.py`, `*_review.py`, `chat_view.py` commands |
| 7 Human control | DuoDrama | `outline_confirm_dialog.py`, `controlled_apply/service.py`, `rewrite_sandbox/engine.py`, Assistant apply guards |
| 8 Mode transfer | all | `graphic_novel_*`, `stage_script_*`, `series_*`, `models.py` mode tables |

---

*End of comparative analysis. No code was modified; no fixes implemented; no new
systems created. Classifications reflect the live source tree at analysis time.*
