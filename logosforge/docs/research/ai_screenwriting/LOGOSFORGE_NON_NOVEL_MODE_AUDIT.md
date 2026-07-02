# Logosforge Non-Novel Writing Mode Audit

**Type:** Codebase audit only. No code changed, no fixes implemented, no redesign.
**Scope:** The four non-novel writing modes — **Screenplay, Graphic Novel,
Stage Script, Series**. Novel mode is excluded except as a reference point.
**Method:** Read-only inspection of the live source tree at
`/home/user/logosforge/logosforge` with file:line evidence. Findings below
were gathered by four parallel read-only sweeps and reconciled.

**Status legend**

| Token | Meaning |
|---|---|
| **IMPL** | Implemented and wired into a reachable surface |
| **PART** | Partially implemented (real logic exists but incomplete or not fully surfaced) |
| **GEN** | Generic-only (mode runs through shared/generic logic; no mode-specific behavior) |
| **PLACE** | Placeholder (models/units defined but never reach the surface in question) |
| **LIB** | Library-only (real engine exists but is **not** reachable from the UI) |
| **ABSENT** | Not present |

> **Headline.** The non-novel modes have **far more real backend depth than the
> two primary writing surfaces expose.** Dedicated data models
> (`GraphicNovelPage/Panel`, `Episode/Season/EpisodePlotline/SeriesArc`,
> `StageEntranceExit/Cue/Business`, rich `Scene` screenplay fields) and dedicated
> subsystems (`psyke_visual/theatre/series`, `*_plot.py`, `*_review.py`,
> `screenplay_graph`) exist and are largely real. But the **Outline collapses to
> Act→Scene for every non-novel mode**, and the **Manuscript labels every unit
> "Scene"** and stores prose in a generic `Scene.content`. The result is a
> **split-brain architecture**: Screenplay is deep on Assistant/Logos/Graph/Export;
> Graphic Novel / Series / Stage are deep on PSYKE/Plot/Timeline/Review; and **no**
> mode is deep on the two surfaces a writer actually lives in (Outline + Manuscript
> unit model).

---

## Audit Matrix

> `Implemented?` summarizes the row. `Gaps / Risk / Recommendation` are the
> diagnostic columns. Evidence is in the per-area notes that follow the table.

| Area | Screenplay | Graphic Novel | Stage Script | Series | Implemented? | Gaps | Risk | Recommendation |
|---|---|---|---|---|---|---|---|---|
| **1. Writing-mode source of truth** | IMPL | IMPL | IMPL | IMPL | **Yes** — single canonical field `Project.narrative_engine`; thin facade in `writing_modes.py` (consts L43-47, getter/setter L185-211) | None structurally. `narrative_engine` vs `default_writing_format` vs `format_mode` is a 3-name surface | Low | Keep. Document the 3 aliases so future code doesn't fork the source of truth |
| **2. Primary writing unit** | PART | PART (label wrong) | PART | PART (label wrong) | **Partly** — rich per-mode models exist; UI unit label is "Scene" for all non-novel modes (`primary_unit_label` L158) | GN should read "Page", Series "Episode"; Scene is the storage unit even where `Episode`/`Page` tables are the true primary | Med — label/data mismatch confuses users & AI context | Decide per mode whether Scene is canonical or a façade over Page/Episode; align label to the real unit |
| **3. Outline** | PART | PLACE | PLACE | PLACE | **No (collapses)** — `outline_unit_labels()` returns Act→Scene for all non-novel (`outline_actions.py` L515-521); `PlanView` hardcodes Act→Chapter | Engines define Act→Sequence→Scene→Beat / Issue→…→Panel / Act→Scene→Beat→Entrance / Season→Episode→Act→Scene but **none reach the Outline UI** | **High** — outline is the structural backbone; all mode structure is lost here | Generalize Outline to consult `engine_structural_units(engine)`; render the engine hierarchy instead of hardcoded Act→Chapter |
| **4. Manuscript** | IMPL | PART | IMPL | PART | **Yes (formatting); No (unit model)** — `writing_formats.py` defines real per-mode elements + block grammar (`writing_core_view.py` L187-236); `_show_manuscript` always builds `WritingCoreView` (`main_window.py` L876-889) | Unit label "Scene" for all; GN Page/Panel & Series Episode tables not edited here; `graphic_novel_manuscript.py` is a one-way scaffold, not live-bound | Med — formatting is good; unit story is generic | Keep the format engine (strong). Decide if Manuscript should bind to Page/Episode for GN/Series or stay scene-prose with a correct label |
| **5. Assistant** | IMPL | GEN | GEN | GEN | **Screenplay only** — 6+ dedicated context blocks (`assistant_context_policy.py` L148-314); others get only the generic `[Project Mode]` block (`writing_modes.py` L137-152) | No GN panel/motif block, no Stage entrances/blocking block, no Series continuity/arc block | **High** for GN/Stage/Series — AI gives generic film advice for non-film media | Add per-mode Assistant context blocks mirroring the screenplay pattern; the constraint strings already exist (L102-113) |
| **6. Logos** | IMPL | ABSENT | ABSENT | ABSENT | **Screenplay only** — 15+ actions tagged `modes=("screenplay",)` (`logos/actions.py` L519+); infra is mode-aware (`applies_to_mode` L54-61) | Zero GN/Stage/Series mode-specific inline actions; only generic manuscript actions surface | Med — inline help is film-centric or generic | Register mode-specific Logos actions (infra already supports `modes=`); route mode into `list_actions_for_section()` consistently |
| **7. PSYKE** | GEN | IMPL | IMPL | IMPL | **3 of 4** — `psyke_visual.py` (346L), `psyke_theatre.py` (194L), `psyke_series.py` (238L) are real; Screenplay has no dedicated PSYKE module | Console wiring (`psyke_console.py`) is mode-agnostic — dedicated context builders exist but the omnibox doesn't select them by mode | Med — strong logic underused because console isn't mode-routed | Route PSYKE console/context to `build_visual/theatre/series_memory_context()` by mode; add screenplay PSYKE parity |
| **8. Plot / Canvas Plot** | PLACE | IMPL | IMPL | IMPL | **3 of 4 (separate from Canvas)** — `graphic_novel_plot.py`, `stage_script_plot.py`, `series_plot.py` produce real mode blocks; Canvas Plot itself is generic free blocks (no causality) | Canvas Plot has no causality/dependency model; screenplay has no `*_plot.py`; mode plot modules feed Timeline, not Canvas | Med — "Plot" means two different things (free canvas vs mode plot blocks) | Clarify Canvas Plot (visual board) vs mode plot models; consider causality/dependency edges on Canvas; add screenplay plot parity |
| **9. Timeline** | GEN | IMPL | IMPL | IMPL | **3 of 4 + generic lanes** — `TimelineLane/Link` + `TIMELINE_LINK_TYPES` generic (`models.py` L1081-1123); `get_gn/stage/series_timeline()` are real and mode-dispatched (`timeline_view.py`) | Screenplay uses generic lanes only; typed links (causality/setup_payoff/echo…) exist but mode coverage is uneven | Low–Med | Add screenplay timeline parity; ensure all modes can use typed inter-event links |
| **10. Graph** | IMPL | PLACE | PLACE | PART | **Screenplay only** — `screenplay_graph.py` (14 node + 12 edge types) + `screenplay_setup_payoff.py` real & gated in KG builder (`knowledge_graph/builder.py` L45); others generic KG | No GN/Stage graph; Series arcs exist (`get_series_arcs`) but not surfaced as graph edges; KG `writing_mode` stored but not used for filtering (`models.py` L78) | Med — causal/setup-payoff intelligence is film-only | Generalize setup/payoff & causal edges; surface Series arcs as graph edges; use KG `writing_mode` to select extractors |
| **11. Export** | IMPL (LIB pro) | PART | PART | PART | **Screenplay full; others generic text** — Fountain/FDX/DOCX/PDF (`screenplay_*_export.py`); GN/Stage/Series only generic `_fmt_*_text()` | Pro screenplay variants are **library-only** (UI dialog calls generic `export_fountain/fdx`); no GN panel-script, no Stage play markup, no Series episode outline/season bible/scene list; `graphic_novel_ai_export` ComfyUI is a disabled stub | **High** for GN/Stage/Series — no professional deliverable | Wire pro screenplay exporters into the dialog; add GN panel script, Stage play format, Series episode/season exports |
| **12. Revision / Feedback** | IMPL (LIB) | IMPL (`/gn`) | LIB (not wired) | IMPL (`/series`) | **Engines real; wiring uneven** — `*_review.py` exist for GN/Stage/Series; GN & Series wired via chat commands (`chat_view.py`), Stage review NOT wired; Counterpart, continuity, rewrite-sandbox, controlled-apply all LIB | Counterpart (external critic, never rewrites) not UI-reachable; screenplay diagnostics/subtext/setup-payoff LIB only; no internal/character-perspective ("experience") critic anywhere | **High** — strong critique engines mostly unreachable | Wire Stage review to a command; expose Counterpart; surface screenplay diagnostics; consider an "experience-role" critic (cf. DuoDrama) |

---

## Per-Area Evidence Notes

### 1. Writing-mode source of truth — **solid, single source**
- Canonical field: `Project.narrative_engine` (`models/models.py` L24).
  `writing_modes.py` is a thin facade — no duplicate column.
- Constants `NOVEL/SCREENPLAY/GRAPHIC_NOVEL/STAGE_SCRIPT/SERIES` (L43-47);
  `get_project_writing_mode(_by_id)` (L185-194), `set_project_writing_mode` (L202).
- Propagates to Assistant (`mode_context_block`), Logos
  (`logos/context.py` → `build_logos_context`), Manuscript label, dashboard, export.
- **Caveat:** three related names coexist — `narrative_engine` (engine/mode),
  `default_writing_format` / `format_mode` (Manuscript block grammar via
  `writing_formats.py`). They're consistent today but are a forking risk.

### 2. Primary writing unit — **rich models, generic label**
- `primary_unit_label(mode)` returns "Chapter" for novel, **"Scene" for everything
  else** (`writing_modes.py` L158); add-button label follows (`current_add_button_label`).
- Real per-mode storage exists:
  - **Screenplay:** `Scene` + screenplay fields (slugline, dramatic_turn,
    setup_payoff_links, subtext…) `models.py` L96-116. No separate `Sequence` table.
  - **Graphic Novel:** dedicated `GraphicNovelIssue/Sequence/Page/Panel`
    (`models.py` L807-918) — real; `Scene.content` optional.
  - **Stage Script:** `Scene` + stage fields + `StageEntranceExit/Cue/Business`
    (`models.py` L940-986).
  - **Series:** dedicated `Season/Episode/EpisodePlotline/SeriesArc`
    (`models.py` L1006-1078) — **Episode is the true primary**, `Scene` optional.
- **Mismatch:** GN should label "Page", Series "Episode"; both currently say "Scene".

### 3. Outline — **collapses for all non-novel modes**
- `outline_unit_labels(mode)` → `("Act","Chapter")` novel, **`("Act","Scene")` all
  others** (`outline_actions.py` L515-521).
- `PlanView` hardcodes Act→Chapter labels (`plan_view.py` ~L491/L551), ignoring the
  engine entirely. `ChapterOutlineView` is novel-only (`build_mode_outline_prompt("novel")`).
- **The narrative engines DO define rich hierarchies** but they never reach Outline:
  - Screenplay `("act","sequence","scene","beat")`,
  - Graphic Novel `("issue","chapter","sequence","page","panel")`,
  - Stage `("act","scene","beat","entrance_exit","cue")`,
  - Series `("series","season","episode","act","scene","plotline","arc")`.
  - The generation **prompt** does use these via `engine_structural_units()` +
    `build_outline_generation_prompt()` (`outline_actions.py` L356-422), but the
    **persisted/rendered outline flattens to scene rows.**
- This is the single biggest structural gap in the audit.

### 4. Manuscript — **format engine strong; unit model generic**
- `_show_manuscript()` **always** builds `WritingCoreView` (`main_window.py` L876-889);
  no mode-specific manuscript view.
- `writing_formats.py` defines real per-mode element sets + styling: Screenplay (6),
  Graphic Novel (11, incl. panel/caption/sfx/art_direction), Stage (10, incl.
  stage_direction/aside/cue), Series (16, incl. season/episode headers + A/B/C plots).
- Per-mode block grammar transitions (`writing_core_view.py` L187-236) are real and
  live. This is a genuine strength.
- **But:** add-button label "Scene" for all; `graphic_novel_manuscript.py`'s
  `generate_page_draft/generate_draft` is a **one-way scaffold** used for export/copy
  (`graphic_novel_pages_view.py` L253), **not** bound to live editing; Episodes are
  not edited in Manuscript.

### 5. Assistant — **screenplay-deep, others label-only**
- Generic block: `_project_mode_block` → `mode_context_block(mode)` →
  `[Project Mode]` + `medium_constraints(mode)` (`writing_modes.py` L137-152).
  The constraint strings are good (e.g. Series: "episode engine, A/B/C plots, season
  arc, recurring payoff, long-term continuity" L110-113) but they're just a sentence.
- Screenplay adds real intelligence: `_screenplay_scene_block`,
  `_screenplay_diagnostics_block`, `_screenplay_setup_payoff_block`,
  `_screenplay_subtext_block`, `_screenplay_links_block`, `_screenplay_export_block`
  (`assistant_context_policy.py` L148-314).
- **No** equivalent GN/Stage/Series context blocks exist.

### 6. Logos — **screenplay-only mode actions**
- Infra is mode-aware: `LogosAction.modes` + `applies_to_mode()`
  (`logos/actions.py` L43-61). 15+ actions tagged `modes=("screenplay",)` (L519+).
- No `("graphic_novel",)`, `("stage_script",)`, or `("series",)` actions registered.
- Generic manuscript actions (`modes=()`) apply everywhere; `LogosSuggestionBar`
  only filters by mode if the caller passes it.

### 7. PSYKE — **3 dedicated modules, mode-agnostic console**
- Real dedicated layers: `psyke_visual.py` (silhouette/color_identity/motif
  recurrence/visual callbacks; context at L211), `psyke_theatre.py`
  (objectives/entrances-exits/props/spatial; context at L90), `psyke_series.py`
  (season arcs/episode state/mystery threads/setup-payoff chains; context at L163).
- **Screenplay has no dedicated PSYKE module** (generic entries/relations/progressions;
  `temporal_psyke.py` mode-agnostic).
- `psyke_console.py` `suggest()` (L465) carries no mode context — the dedicated
  context builders aren't selected by mode at the console layer.

### 8. Plot / Canvas Plot — **two different things named "Plot"**
- **Canvas Plot** (`canvas_plot_view.py`, `CanvasPlotNode/Link/Frame`
  `models.py` L1125-1187) is a free spatial board: optional `scene_id`, untyped links,
  visual frames. **No causality / dependency / subplot model.**
- **Mode plot blocks** are real and separate: `graphic_novel_plot.py`
  (sequence/page blocks, density→rhythm pacing, motif recurrence, page-turn
  setup/reveal), `series_plot.py` (episode/season blocks, A/B/C colors, arc spanning),
  `stage_script_plot.py` (scene/act blocks, entrances/exits, props, dramatic pressure).
  These feed Timeline, not Canvas.
- **Screenplay has no `*_plot.py`** — generic `Scene.plotline`.

### 9. Timeline — **generic lanes + 3 dedicated builders**
- Generic: `TimelineLane`, `TimelineLink`, `TIMELINE_LINK_TYPES`
  (custom/causality/setup_payoff/echo/conflict/dependency) `models.py` L1081-1123.
- Mode-dispatched builders: `get_gn_timeline` (page-turn pairs, panel markers,
  silence/action), `get_stage_timeline` (entrances/exits, cues, prop continuity),
  `get_series_timeline` (episode order, arcs, cliffhangers) — wired via
  `timeline_view.py`.
- Screenplay uses generic lanes only.

### 10. Graph — **screenplay-deep, others thin**
- `screenplay_graph.py` (14 node types incl. setup/payoff/motif/promise/threat;
  12 edge types incl. setup_to_payoff, object_plant_to_use) + `screenplay_setup_payoff.py`
  (marker lexicons, candidate detection). Gated in KG: only screenplay gets
  `extract_setup_payoff` (`knowledge_graph/builder.py` L45,L77).
- GN/Stage: no dedicated graph module (generic KG only). Series: arcs exist
  (`db.get_series_arcs`) but not surfaced as explicit graph edges.
- KG stores `writing_mode` (`knowledge_graph/models.py` L78) **but doesn't use it to
  filter extractors** beyond the screenplay setup/payoff gate.

### 11. Export — **screenplay pro pipeline (mostly LIB), others generic text**
- Screenplay: Fountain (`screenplay_fountain.py`), FDX (experimental,
  `screenplay_fdx_export.py`), DOCX (`screenplay_docx_export.py`), PDF, HTML preview,
  validation + diagnostics JSON. **But the main export dialog calls the *generic*
  `export_fountain()`/`export_fdx()`, not the professional
  `export_screenplay_fountain_result()` etc.** — pro variants are library-only.
- Graphic Novel: only generic `_fmt_graphic_novel_text()` (PAGE N + content);
  `graphic_novel_ai_export.py` (ComfyUI prompt packets) has a **disabled `send_to_comfyui` stub**.
  No panel-script / visual breakdown export.
- Stage Script: only generic `_fmt_stage_script_text()` (ACT/SCENE). No play-format
  markup, cue scripts, or blocking notation.
- Series: only generic `_fmt_screenplay_text(fmt="series")`. **No episode outline,
  season bible, or per-episode scene list.**
- Structured data export (JSON/MD/CSV) is full and UI-reachable (`data_export.py`,
  `export_data_dialog.py`).

### 12. Revision / Feedback — **strong engines, uneven reach**
- **Review engines (real, deterministic):** `graphic_novel_review.py` (visual clutter,
  balloon overload, panel flow, splash justification…) — **wired via `/gn`**;
  `series_review.py` (A/B/C balance, cliffhanger, unresolved payoff, arc movement) —
  **wired via `/series`**; `stage_script_review.py` (playable objective, motivated
  exit, prop continuity, blocking) — **real but NOT wired** to any command.
- **Counterpart** (`counterpart.py`): explicit **external critic** ("second
  consciousness," never rewrites, never mutates) — built, **not UI-reachable**.
- Screenplay diagnostics/subtext/setup-payoff: real, deterministic, **library-only**.
- Continuity (`continuity/`), revision_intelligence (scene impact/causality),
  rewrite_sandbox (gated generation), controlled_apply (confirmed mutation),
  adaptive_mode (Structure/Balance/Refinement) — all real, all **library-only**.
- **No internal/character-"experience" perspective critic** exists anywhere — all
  critique is external/structural (relevant to the DuoDrama research direction).

---

## Synthesis

### Strongest existing Logosforge logic
1. **Mode source of truth** — one canonical field, clean facade, propagates widely
   (`writing_modes.py`). Low-risk foundation.
2. **Manuscript per-mode format engine** — real element sets + block grammar for all
   four modes (`writing_formats.py`, `writing_core_view.py`). Genuinely good.
3. **Screenplay vertical** — Assistant blocks + Logos actions + setup/payoff graph +
   diagnostics + pro export pipeline. The most complete mode by a wide margin.
4. **Mode data models** — GN Page/Panel, Series Episode/Season/Arc, Stage
   entrance/cue/business are real, normalized tables, not placeholders.
5. **Mode review engines** — `graphic_novel_review` / `series_review` are real
   deterministic critics already reachable via chat commands.

### Weakest non-novel mode logic
- **Stage Script** is the weakest *overall surface*: strong PSYKE/Plot/Timeline/Review
  logic, but **no Graph, no dedicated Assistant/Logos, review engine not wired, only
  generic export**, and Outline collapses. Most of its intelligence is unreachable.
- **Screenplay** is weakest precisely where others are strong: **no dedicated PSYKE,
  no `*_plot.py`, generic Timeline** — its plot/memory layer is thin even though its
  Assistant/Graph/Export are the richest.
- Across *all* non-novel modes the **Outline** is uniformly weakest (collapses to
  Act→Scene), and **professional Export** is missing for GN/Stage/Series.

### Cross-mode architectural problems
1. **Split-brain feature depth.** Screenplay owns Assistant/Logos/Graph/Export;
   GN/Series/Stage own PSYKE/Plot/Timeline/Review. No mode is strong on *both* axes,
   and the two central writer surfaces (Outline + Manuscript unit model) are generic
   for everyone.
2. **Outline ignores the engine hierarchy.** Rich `engine_structural_units()` data
   exists and even drives the *generation prompt*, but the *rendered/persisted* outline
   flattens to Act→Scene. Structure is computed then discarded.
3. **Label/data mismatch.** "Scene" is shown for modes whose true primary unit is
   `Page` (GN) or `Episode` (Series). This misleads both users and AI context.
4. **Library-vs-UI gap.** Many of the best engines (Counterpart, screenplay
   diagnostics, pro exporters, stage review, controlled_apply) are real but
   **not reachable** from the UI — value is built but not delivered.
5. **Mode not threaded through shared surfaces.** PSYKE console, Logos suggestion bar,
   and KG extractor selection don't consistently consume `writing_mode`, so
   mode-specific logic that exists isn't always invoked.
6. **"Plot" is overloaded** — the free Canvas board and the mode plot-block modules
   are unrelated systems sharing a name.

### Areas that should be generalized (shared, mode-parameterized)
- **Outline** → drive hierarchy from `engine_structural_units(engine)` for all modes
  instead of hardcoded Act→Chapter.
- **Assistant context** → a per-mode context-block registry mirroring the screenplay
  blocks (the constraint strings already exist).
- **Logos actions** → the `modes=` infra is already generic; just register the other
  three modes and always pass `writing_mode` into `list_actions_for_section()`.
- **Graph setup/payoff & causal edges** → lift out of screenplay-only into a
  mode-parameterized extractor; use KG `writing_mode` to select extractors.
- **PSYKE console routing** → select `build_visual/theatre/series_memory_context()`
  by mode at the console/context layer.
- **Export dialog** → route to the existing professional exporters per mode.

### Areas that should remain mode-specific
- **Manuscript element sets & block grammar** (`writing_formats.py`) — inherently
  medium-specific; keep per-mode.
- **PSYKE field schemas** (visual vs theatre vs series) — the *fields* differ by
  medium; keep dedicated, generalize only the *routing*.
- **Mode data models** (`Page/Panel`, `Episode/Season/Arc`, `Stage*`) — correctly
  medium-specific; keep.
- **Review checks** (panel clutter vs blocking vs A/B/C balance) — medium-specific by
  nature; keep dedicated, generalize only *wiring*.
- **Professional export targets** (Fountain/FDX vs panel script vs play format vs
  episode bible) — medium-specific deliverables; keep per-mode.

---

## Cross-reference to the AI screenwriting research

This audit pairs with `AI_SCREENWRITING_RESEARCH_SUMMARY.md`:
- **R²'s causal plot graph** ↔ screenplay-only `screenplay_graph` / `setup_payoff`
  (Area 10) — the research argues this should be a first-class, mode-general object.
- **DSR's "decompose structure → prose → format"** ↔ the Outline collapse (Area 3)
  and the library-only pro exporters (Area 11) — Logosforge *has* the stages but
  flattens structure and under-delivers format.
- **DuoDrama's experience-role vs evaluation-role critic** ↔ Counterpart is a pure
  *external/evaluation* critic (Area 12); there is **no internal/experience-role
  critic**, and Counterpart isn't even wired.

---

*End of audit. No code was modified; no fixes were implemented; no modes were
redesigned. Status tokens reflect the live source tree at audit time.*
