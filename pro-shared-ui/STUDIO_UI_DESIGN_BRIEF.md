# LogosForge **Studio** — UI Design Brief

> **Purpose of this document.** A complete, design-ready extraction of the
> LogosForge **core** (`logosforge`) for building the **Studio (Pro)** line UI
> in Claude Design, then recoding it in Claude Code. It describes *what the
> product does* (every feature), *the data it operates on*, and *the panels /
> interactions the Studio UI must provide* — written for a UI designer.
>
> **Source.** Extracted 2026-06-25 from the `logosforge` Python core
> (82 UI views, 138 logic modules, 18 subpackages). The existing PyQt app is the
> reference implementation of the *complete* product; Studio is a fresh,
> redesigned UI over the **same core API** (`logosforge.api`).
>
> **Hard rules (from `logosforge-architecture`):**
> - Studio (Pro) and Whiteboard (Free) **never share UI**. This is a distinct
>   visual identity — do **not** reuse Whiteboard components or styling.
> - The UI owns **no product logic**. All behaviour lives in the core and is
>   consumed only through its API layer. Panels render core data and invoke core
>   actions; they never reimplement them.
> - Two consumers share this UI: **pro-desktop** (Electron, local AI) and
>   **pro-web** (browser, remote AI). Every component must be platform-neutral;
>   platform behaviour (files, dialogs) is injected via adapters.

---

## 1. Product vision

**Whiteboard is the minimal product. Studio is the complete one** — the
power-user writing workstation. Where Whiteboard is a calm single document,
Studio is a **dockable, panel-based workspace** — think *a DAW / IDE for
storytelling* — dense, cinematic, and HUD-like, that surfaces the core's full
depth: a manuscript editor surrounded by live intelligence panels (structure,
PSYKE story-bible, timeline, knowledge graph, analytics, AI).

Its organising metaphor is the **Project Operating System** — a deterministic,
pull-based loop the whole UI should make legible:

```
Understand  →  Decide  →  Act (guided)  →  Verify  →  Apply safely
(Project       (Decision   (Guided          (completion  (Controlled Apply /
 Intelligence)  Radar)      Workflows)        checks)      Rewrite Sandbox)
```

The OS *proposes*; the user *disposes*. Nothing runs in the background, nothing
calls an LLM on its own, nothing mutates the manuscript without an explicit
confirm-before-apply step. **The UI's job is to make a deep, deterministic
system feel like a single calm cockpit** — never a wall of buttons.

The mutation contract is concrete and worth holding in mind everywhere:
**Controlled Apply is the single gate** — `build_apply_preview` produces a
diff + conflict list (severities **blocking / error / warning**) with **no
mutation**; `apply_operation(confirmed=True)` only runs *after* a STAGE
checkpoint, guarded against blocking conflicts and stale sources (with a
`force=True` override), and logs to an apply history. Quantum collapse, Rewrite
Sandbox, Logos ops, voice commits, and every per-mode rewrite all funnel through
it. Restore is likewise non-destructive — restoring a version always creates a
**new project** after a pre-restore safety snapshot. The Studio UI should make
this trustworthiness *visible* (confidence badges, "advisory only", provenance,
a visible checkpoint/safety affordance).

**Tone / identity:** dark-first, cinematic, "minimal-cyber / terminal" (the
core's own icon language). Three palettes exist in the core — **Dark** (primary),
**Light (Green)**, **Light (Warm)**. High information density, but composed:
every panel earns its space. A **unified severity/confidence visual grammar**
(severity chip + confidence dot/badge) recurs across Decision Radar, Continuity,
Health, Logos suggestions, graph edges, and screenplay diagnostics — design it
once and reuse it everywhere.

---

## 2. Information architecture & the workspace

Studio is a **single project workspace** with a dockable layout. The current
core is a single-window, single-active-project, modal-dialog model orchestrated
entirely by **`MainWindow`** (`ui/main_window.py`, ~4060 lines — there is *no*
separate "workspace manager"; `MainWindow` **is** the workspace). It owns the
collapsible icon sidebar (groups **Plan / Structure / Analytics**, ~25 sections,
several mode-dependent — Pages/Chapters/Scenes/Series Navigator), the menu bar,
the autosave/version managers, the project event-bus subscriptions, and the
atomic project-switch pipeline. The dockable `AssistantDock` (dock/float/pin/
collapse) already proves the docking pattern Studio should generalise. Suggested
regions (a designer should explore docking/tiling, but this is the model):

- **Left rail — Navigator.** Icon rail + collapsible tree to switch *sections*:
  Dashboard, Manuscript, Structure/Outline, Scenes, Timeline/Plot, PSYKE,
  Graph, Stages (versions), Notes, Search, Reviews (mode dashboards), Plugins,
  Settings. (Maps to `main_window` sidebar + `sidebar_icons`; the menu bar's
  **Navigate** group binds Dashboard/Scenes/Manuscript/Timeline/Notes/PSYKE to
  Ctrl+1..6, and group expand/collapse state persists via
  `sidebar_groups_expanded`.)
- **Center — the active editor** (manuscript / scene / outline / canvas),
  re-skinned by the active **writing mode** (see §6).
- **Right dock — intelligence panels** (tabbed/stacked, user-arrangeable):
  Assistant (Billy), PSYKE inspector, Story Health, Pacing, Decision Radar,
  Knowledge Graph focus, Continuity.
- **Bottom dock — analysis & timeline strips**: Plot-lane Timeline, Beat/Act
  analysis, Tag analysis, Voice dictation transcript. (In the core, Logos
  drawers — suggestions / diagnostics / health — already live as togglable
  bottom HUD strips; View menu binds diagnostics Ctrl+Shift+D, health
  Ctrl+Shift+H, Focus Ctrl+Shift+F, Dexter's Room Ctrl+Shift+V.)
- **Two omni-surfaces, always available:**
  - **Command Palette** — a `/`-triggered floating popup (Popup+Frameless,
    keyboard-driven Up/Down/Enter/Esc) of writing actions (`command_palette`).
    The core ships a fixed 10: New Scene, New Chapter, Insert PSYKE Entry,
    Rewrite, Expand, Dialogue, Suggest Beats, Style Improve, Voice Rewrite,
    Focus Mode (emits `command_selected(key)`). Studio should promote this into
    a Cmd/Ctrl+K **omnibox** fusing navigation (all `_nav_section_handlers`
    keys), AI presets, inline `search_project` results, recent projects, and
    `CommandRegistry`/`SystemCommandHandlers` system commands — fuzzy,
    keyboard-first, results grouped by source, with the validator's CONFIRM step
    rendered as an inline affordance, not a blocking `QMessageBox`.
  - **PSYKE Console** — an omnibox with live search + commands (`/create`,
    `/open`, `/go`, `/ai`, …), keyboard-driven (`psyke_console`). In the core
    this is a global `/`-activated command line (an app-level `eventFilter`
    catches `/` unless a text widget has focus), validated by
    `psyke_command_validator` (ERROR / CONFIRM / OK statuses), resolved through
    `CommandRegistry`, run by `SystemCommandHandlers`. This is the keyboard-first
    surface the Studio command bar should grow from.
- **Mode Strip** — a compact, always-visible indicator of the current adaptive
  AI mode, with manual override (`mode_strip`, `mode_suggestions_view`). Note
  this is the *Adaptive AI mode* (Structure / Balance / Refinement), **not** the
  writing mode — a colored-dot badge (Structure indigo / Balance amber /
  Refinement green) with a dropdown override (Auto/Structure/Balance/Refinement)
  + Reset + a one-line hint.
- **Context Hint / Suggestion banners** — thin, non-intrusive strips above the
  editor for proactive (but dismissible) suggestions
  (`context_hint_banner`, `suggestion_banner`).

The workspace must support **focus** (collapse all panels to just the editor)
and **cockpit** (everything visible) layouts, and remember per-project layout.
Persist layouts the way the core already persists graph state — `graph_state` /
`graph_presets` (named save/load/delete) show the pattern.

---

## 3. Global data model (what panels render)

All entities are project-scoped (one SQLite DB per project, via the API).

- **Project** (`models/models.py`) — `id`, `title`, `description`,
  `format_mode` (legacy, "novel"), **`narrative_engine`** (= the writing mode:
  novel · screenplay · graphic_novel · stage_script · series),
  `default_writing_format`, `settings_json`, `created_at`, `updated_at`. The
  per-project `settings_json` carries `source_path` (used to de-dupe on open),
  `writing_language_code`, `scoring_weights` / `scoring_preset` /
  `weight_learning`, `act_summaries` / `chapter_summaries`, `outline_template`,
  and the per-mode planning artifacts (see below). Accessed via
  `get_project_settings` / `save_project_settings`.
- **Structure (canonical):** **Act → Chapter → Scene** is the single ordered
  spine (`story_structure`). **There are no Act/Chapter tables** — Act/Chapter
  are *string labels* on `Scene`, and `Scene.sort_order` is the one global
  order. `story_structure.py` is the sole place that derives the ordered tree and
  canonical numbers. Each format re-labels it (see §6).
- **Scene** (the load-bearing record) — `id`, `title`, `act`, `chapter`,
  `plotline`, `beat`, `tags`, `sort_order`, `summary`, `synopsis`, `goal`,
  `conflict`, `outcome`, `content` (format-specific blocks), `color_label`,
  `character_ids`, `place_ids`, `character_states` `[(char_id, state)]`. Planning
  **status** rides as a `status:` tag (Draft / Edited / Needs Work / Complete);
  **manual tension** as a `tension:N` tag. Screenplay extras:
  `slugline`/`location`/`interior_exterior`/`time_of_day`/
  `estimated_duration_minutes`/`dramatic_turn`/`setup_payoff_links`/
  `montage_group`/`cinematic_pacing`/`emotional_turn`/`visible_conflict`/
  `hidden_conflict`/`who_knows_what`/`visual_symbolism`. Stage extras:
  `stage_location`/`scene_objective`/`entrance_exit_notes`/`prop_notes`/
  `cue_notes`/`offstage_events`/`performance_duration_minutes`. Series link
  `episode_id`; comics link `gn_page_start`.
- **Chapter** (additive store, Novel-only primary unit) — `id`, `title`,
  `summary`, `content`, `sort_order`.
- **PSYKE entry** (story bible) — `id`, `project_id`, `name`, `entry_type`
  (character · place · object · lore · theme · other), `aliases`
  (comma-separated), `notes`, `details_json`, `is_global` (cross-project), plus
  **relations** (`PsykeRelation`, stored both directions with an inverse),
  **progressions** (`PsykeProgression`: `text`, optional `scene_id`,
  `sort_order` — entry state across scenes/time), and **scene references** (where
  an entry appears). The per-type `details_json` follows a dynamic schema
  (`models/psyke_details.py`) — e.g. *character* has ~30 fields across Identity /
  Appearance / Psychology (incl. needs, misbelief/Lie) / Background / Voice & Arc
  / Screenplay sections — plus nested **`visual` / `series` / `theatre`** memory
  blocks surfaced per engine.
- **Plotlines / plot lanes** (`TimelineLane`: name matched to `Scene.plotline`,
  `color_label`, `order_index`, `collapsed`), **typed timeline links**
  (`TimelineLink`: source/target scene, `link_type` ∈ custom / causality /
  setup_payoff / echo / conflict / dependency, `color_label`, `label`),
  **structure links** (`TimelineStructureLink`: event → Act/Chapter by name),
  **canvas plot** nodes/links/frames (`CanvasPlotNode/Link/Frame`), **Timeline**
  (story-order vs structural order), **Notes**, **Tags**, **Beats**.
- **Stages / Versions** — narrative versioning + **branching** (capture,
  restore, diff) and timestamped JSON snapshots (`VersionInfo`: `path`,
  `timestamp`, `reason` ∈ autosave / periodic / manual / pre-restore-safety,
  `label`; derived `display_time`, `file_size_kb`).
- **Knowledge-Graph nodes & edges** — derived (typed, confidence-scored,
  provenanced) from PSYKE, structure, notes, revisions, workflows. `KGNode`
  (22 node types) / `KGEdge` (20 edge types, `confidence` ∈ confirmed/likely/
  possible/unknown, `source_system` of 16, `provenance`, `is_user_confirmed`,
  `is_hidden`, derived `is_inferred`). A parallel rich **visual** graph
  (`GraphData` of `GraphNode`/`GraphEdge`) drives the cinematic canvas.
- **Memory objects** — extracted continuity facts (`StoryMemoryEntry`:
  character_state / key_event / relationship / decision) scored by priority ×
  recency × relevance, plus the curated **`memory_arch`** store
  (`MemoryObject`: 5 scopes × 20 types, `status`, `confidence`, supersede chains,
  policy decision, risk level).
- **Workflow state** — `WorkflowRun` / `WorkflowStepState` / `WorkflowEvent`
  (status active/paused/completed/cancelled; events started/step_completed/
  step_skipped/step_auto_completed/paused/resumed/cancelled/completed).

> The UI reads these via `logosforge.api` (projects, scenes, outline, plot,
> timeline, psyke, notes, assistant, connector, export, events). A live
> **event bus** (`/events`, `project_events.py`) pushes change notifications for
> reactive panels. The catch-all `project_data_changed()` plus typed signals
> (`scene_changed` / `scenes_changed` / `outline_changed` / `psyke_changed` /
> `psyke_list_changed` / `notes_changed` / `plot_changed` /
> `assistant_action_completed`, and lifecycle `project_loaded(int)` /
> `project_created(int)`) are how every panel stays live; a
> `CONCEPTUAL_EVENT_MAP` maps spec-level events (manuscript_changed,
> timeline_changed, graph_changed, strategy_changed, health_report_changed) onto
> the real coarse signals. **Project switch is an atomic pipeline** (stop voice →
> release lock → `clear_project_caches(old_id)` lifecycle hooks → swap id into
> autosave/versions/assistant/console/system-commands → rebuild Logos engines
> (proactive/diagnostics/health/strategy) → repair Act→Chapter→Scene structure →
> recompute mode-dependent nav → acquire new lock → rebuild section); panels must
> never let one project's state leak into another.

---

## 4. Feature design specs

Each section: **what it is → what the user does → panels & interactions** for
Studio. Module/view names in `code` are the authoritative source.

### 4.1 Manuscript writing core
*The continuous prose/scene editor* (`writing_core_view`, `scenes_view`,
`chapters_view`, `story_grid_view`, `structure_view`, `manuscript_highlighter`,
`format_toolbar`; engines `story_structure`, `grammar_checker`, `style_analysis`,
`paragraph_energy`, `dialogue_attribution`, `voice_consistency`, `voice_learner`,
`writing_formats`).

**`WritingCoreView`** is the immersive continuous editor: a single centered
**≤720 px column** rendering Act headers, Chapter headings, a dominant per-scene
`_SceneEditor` (auto-height, borderless `QTextEdit`, focus-fade overlay dimming
non-active blocks), a per-scene **summary/navigation rail** (`_SummaryRailLabel`),
and inline "+ New Scene / + New Chapter". Top bar: word count · **format badge**
(engine·format, links to Project Settings) · **element combo** · an **A–P**
typography menu (bold/italic/underline/strike, align L/C/R/justify, indent ±,
bullet/numbered list) · **Review** menu · **Focus** · **Text/Bg** menu (14 font
presets, sizes 14–24, color palettes, first-line indent, smart quotes).

- **Markdown-like live styling** via `ManuscriptHighlighter` (emphasis/headings/
  quote/list/separator) painted *on top of* PSYKE terms; a floating
  **`FormatToolbar`** on selection (B/I/H/quote + Rewrite/Expand/Dialogue).
- **PSYKE-aware editing:** the **PSYKE highlighter** underlines/colors entry
  names + aliases by type (character/place/object distinct colors, accent
  fallback), Ctrl+Click jumps to the entry (`psyke_highlighter`), an **entity
  hover** card shows name/type/temporal state/notes excerpt (`entity_hover`),
  and you can **quick-create** a PSYKE entry from a selection.
- **Inline AI** (`inline_assistant`, `inline_edit_bar`, Ctrl+K): selection
  actions **Rewrite / Expand / Tighten / Dialogue / Tension** and slash commands
  `/rewrite /expand /tighten /dialogue /tension /summarize`, scene templates
  from `PRESET_ACTIONS`, plus **Suggest Beats** (structured direction). Results
  show as Original/Proposed **diff** with Replace (selection-verified) / Insert /
  Compare; **selection-drift detection** refuses an unsafe replace. Context is
  composable (outline, story memory, Story Bible, graph context, adaptive AI mode
  block, 3-entry session memory) with a **"Show context sent to model"** viewer.
- **Editing intelligence (live, non-blocking, off-thread, cancelable, cached,
  generation-counted):** grammar/spell (`grammar_checker` → `Issue(start, end,
  type ∈ spelling/grammar/style, message, suggestions)` over 6 languages —
  **deliberately deferred after Alpha; the toggle is present but disabled**);
  style (`style_analysis` → `clarity / concision / rhythm / tone_consistency /
  dialogue_naturalness` 0–1 + inline `StyleHint`s, sensitivity low/med/high);
  **paragraph energy** (`paragraph_energy` → per-paragraph `tension / pacing /
  conflict / emotional_shift` 0–1 + `FlowHint`s flat / pacing-spike / pacing-drop
  / no-emotion); dialogue speaker attribution (`dialogue_attribution` →
  `DialogueSegment(text, start, end, speaker_id)` via 40+ speech-tag verbs +
  proximity + turn-taking); **voice consistency** (`voice_consistency` →
  `VoiceDeviation(segment, score, reasons≤2)` vs each speaker's `VoiceProfile`,
  thresholds low 0.60 / med 0.45 / high 0.30 — the worker **re-adjusts each
  profile by that scene's PSYKE character states before checking**). Debounce
  timers (the contract the dockable HUD should consume): grammar 800 ms, style
  900 ms, voice 1100 ms, energy 600 ms, auto-link 1500 ms, context-assist
  2000 ms, language-detect 3000 ms.
- **Auto-format / smart typography:** `--`→em-dash, `..`+`.`→ellipsis, smart
  curly quotes; per-format block classification
  (`classify_screenplay/series/stage_script/graphic_novel_elements`) so flat
  Fountain-style text renders correctly indented; **Tab cycles** to the next
  element type per `_ELEMENT_TRANSITIONS`.
- **Decorations in the canvas:** grammar/voice/style **ExtraSelection
  underlines** (wave/dash/dot, distinct theme colors, non-overlapping priority
  grammar > voice > style); the left **`_EnergyGutter`** (8 px: per-paragraph
  tension dots green→red, diamond flow-hint markers, hover tooltip of
  tension/pacing/conflict); floating popups `_GrammarPopup` (suggestion buttons +
  Ignore), `_StyleSuggestionPopup` (bullets + Apply rewrite), `_VoiceRewritePopup`
  (label + italic preview + Apply). The **Review menu** toggles a **Review
  Metrics overlay** (`reviewOverlay`, ~260 px top-right: words/scenes/avg/
  shortest/longest, pacing S/M/L balance, flagged scenes, structural issues +
  suggestions, from `creative_layer.compute_review_metrics` +
  `structural_intelligence.StructuralCache`), Style Feedback, Voice Consistency,
  Energy View (each with sensitivity), and a disabled Grammar.
- **`ScenesView`** — the planning + writing form: left list (Chapter/Plotline/Tag
  filters + Move Up/Down); right form (Title, Chapter, Plotline, Act, Beat, Tags,
  Summary, Synopsis, Goal, Conflict, Outcome, Content) with live scene stats
  (words/paragraphs/sentences/dialogue%), embedded `InlineAssistantPanel` +
  `InlineEditBar`, PSYKE highlight/click/quick-create, character link checkboxes,
  **per-character states**, places, link preview + backlinks, and a **Focus
  Mode** (hides chrome, 200% line spacing).
- **`ChaptersView`** — Novel-only chapter manager (Title/Summary/Chapter-text,
  New/Save/Open-in-Manuscript/Delete, reorder).
- **`StructureView`** — read-only HTML outline of the canonical tree with
  `[1.2.3]` numbers, per-scene beat tag, clickable scene links.
- **`StoryGridView`** — corkboard: 3-column 160 px `_SceneCard`s grouped by Act
  (or Chapter/Location), drag-and-drop reorder within/between acts, 3 zoom
  levels, **Color** modes (None/Plotline/Tag/Beat; +Pacing/Continuity in
  screenplay), a **Flow** overlay (tension bar, character dots, scene-type icon,
  pacing-warning highlight), screenplay metadata line (duration/location/INT-EXT/
  TOD, `↻` dramatic-turn, `⚓` setup/payoff), and a card context menu (Open in
  Manuscript, Edit Title/Summary, Move to Act, color label, Delete).

- **Studio panels & interactions:** a **Structure / Navigator dock** (live
  Act→Chapter→Scene tree with canonical numbers + beat badges, drag-reorder
  writing `sort_order`, inline orphan badges from `validate_structure` + a
  one-click "Repair structure" `ensure_valid_structure` banner, per-node
  word-count + energy sparkline). An **Editing-Intelligence HUD dock** (right
  rail, four live sub-panels): *Style meter* (radial/bar gauges for the five
  metrics + notes + sensitivity slider); *Energy strip* (promote the 8 px gutter
  into a full **scene energy timeline** — a horizontal sparkline of the four
  energy metrics per paragraph, plus a zoomed-out act band, clickable flow-hint
  markers); *Voice console* (`VoiceDeviation`s grouped by speaker with score +
  reasons, "Rewrite in voice" applying `generate_voice_rewrites`, and a
  per-character profile readout that **visibly shifts when the scene's PSYKE state
  is applied**); *Issues list* (grammar/style spans, filterable, deferred-grammar
  state shown explicitly, jump-to-span + bulk ignore). A **Review Dashboard
  canvas** (the overlay expanded: pacing-balance S/M/L bar, scene-length
  histogram with shortest/longest call-outs, flagged-scene cards, structural
  issues + suggestions; screenplay projects get duration/continuity views). A
  **format-aware composition surface** with an element-type ribbon driven by
  `WritingFormat.elements` (shortcuts, live `_ELEMENT_TRANSITIONS` Tab-cycle
  visualized, format-correct margins/caps per `ElementStyle`) and a cinematic
  focus/typewriter mode (reuse `set_focus_fade`). **Density/cinematic:** color
  the left tree and grid by the per-paragraph tension palette
  (`_tension_dot_color`, green→red) for a manuscript "heat" view; animate the
  energy timeline as a waveform; render the voice console as character-portrait
  chips.

### 4.2 Outline & story structure
(`plan_view`, `outline_view`, `structure_view`, `outline_confirm_dialog`,
`outline_templates`, `outline_actions`, `structural_intelligence`,
`story_structure`, `story_flow`, `quantum_outliner/`)

The architectural keystone: structure is **derived from `Scene` rows alone**.
`story_structure.py` is the single source of order/numbering:
`build_structure_tree(db, project_id)` → `[(act, [(chapter, [scene,…]),…]),…]`
(dedupes labels in first-seen `sort_order`; label-less scenes collect in an
"Unassigned" bucket that always sorts **last**, unnumbered);
`compute_structural_numbers(tree, is_novel)` → Act `"1"` · Chapter `"1.2"` ·
Scene `"1.2.3"` (novel) or flattened Act.Scene (other modes);
`get_unit_path` → readable `"Act 1 · Chapter 1.2 · Scene 1.2.1"`;
`canonical_scene_order` (shared with Timeline); invariant repair via
`is_orphan_scene` / `validate_structure` / `ensure_valid_structure` (fills
"Recovered Act"/"Recovered Chapter", idempotent); creation that never orphans
(`create_act` / `create_chapter` / `create_scene` seed valid starters via
`default_parent`).

- **`PlanView`** is the **live** Outline planner — a horizontal **board**: Act
  cards (badge + number + summary preview + `N ch · N,NNN w` meta) holding
  Chapter **columns** (Novel) or Scene cards directly (other modes). Scene cards
  show type badge, structural number, title, word count, summary preview, **status
  chip**, tag/character chips, color-label left border, linked-note `📝 N`. All
  reorg goes through a single source of truth (`move_act` / `move_chapter` /
  `move_chapter_to_act` / `move_scene` / `move_scene_to_chapter` →
  `_apply_tree_order` → relabel + `reorder_scenes`, touching only order/label,
  fanning out `scenes_changed`/`outline_changed`/`plot_changed`/
  `project_data_changed`). Rename rewrites the label across every scene; delete
  **detaches** (clears the label) rather than destroying bodies;
  `clear_outline_structure` deletes only *pure placeholder* scenes and detaches
  the rest to Unsorted. `⋯` context menus (rename/move/delete/summary/status/AI/
  Logos); header has Template selector, Generate Outline, **AI Generate ▾** (Full/
  Act/Chapter/Scene), + Add Act, Clear Outline, and a Classical/λ mode badge. The
  Graphic-Novel branch renders Act → Page → Scene → Panel through the same chrome.
- **`OutlineView`** — the older free-form `OutlineNode` tree+editor (no
  `node_type`; depth = nesting). Toolbar: Template+Apply, AI Generate /
  contextual AI Generate (relabels to the engine's unit), + section / + leaf,
  Delete, ▲▼ reorder, Export (Markdown/Text).
- **Templates** (`outline_templates`): 5 built-in `OutlineTemplate` presets as
  nested `TemplateBeat` trees — **Hero's Journey** (12), **Three-Act**, **Save
  the Cat** (15), **Dan Harmon's Story Circle** (8), **Five-Act / Freytag** —
  plus a plugin registry (`register_outline_template`, built-ins never
  overwritten).
- **AI outline generation & parsing** (`outline_actions`): scope-aware (`full` /
  `act` / `chapter` / `scene`) and engine-aware vocabulary builders
  (`build_outline_generation_prompt`, `engine_structural_units`), folding in
  template beats + PSYKE context; `parse_outline_response` is robust to Markdown
  headers / numbered-bulleted-indented lists / Act-Chapter-Scene-Beat keywords
  (tolerates `**Chapter 1:**`), folding dialogue/craft annotations into the
  parent description; `repair_outline_ops` fills empty descriptions, trims prose
  >400 chars, and **prunes non-structural meta-sections** ("Key Characters",
  "Themes", "Synopsis", preambles) returning warnings; `validate_outline_ops`
  rejects prose-as-outline; application is always **additive** (scenes or
  `OutlineNode`s, never overwriting). Screenplay-only "Generate Beat Plan" and
  Graphic-Novel-only "Generate Page Breakdown" produce separate planning
  artifacts, never the Manuscript body.
- **Structural Intelligence** (`structural_intelligence`) — read-only health:
  `compute_structural_analysis` → top-5 `StructuralIssue`s
  (`issue_type`, `category`, `severity` 0–1, `message`, `suggestion`, `data`)
  from **seven detectors**: act balance (underdeveloped acts <0.3× avg, thin
  middle), arc completion (static/abandoned arcs), climax preparation, tension
  curve (flat CV<0.2, no rising stakes), theme continuity, character presence
  (missing for ≥gap-threshold scenes), beat placement (missing/misplaced
  Save-the-Cat beats vs `_BEAT_POSITIONS`, e.g. Midpoint 0.40–0.60). Cached
  (`StructuralCache`, 30 s TTL); `gather_structural_context` injects into the
  Assistant.
- **Story flow** (`story_flow`) — `compute_tension(scene)` →
  `SceneTension(value 0–10, source)` (precedence manual `tension:N` → beat table
  → conflict-field/word boost → content ratio → default); `classify_scene_type`
  → dialogue/action/exposition/mixed; `detect_pacing_warnings` → monotone-low/
  monotone-high/no-variation over 4-scene windows; `tension_color` (green→red);
  `scene_type_icon` (💬 ⚡ 📖 ✦).
- **Quantum / Lambda outline** (`quantum_outliner/`) — `OutlineMode` Classical vs
  **Lambda** (relativistic POV, uncertainty, superposition); `generate_possibilities`
  → a `Wavefunction` of 3–5 distinct `Branch`es (stakes, consequence,
  `state_delta`, structure_method/beat, branch_type ∈ deviation/alternative/
  intensification/resolution, score/probability/factors, pareto/lookahead/
  unified scores); collapse to one branch. (Full AI detail in §4.6.)

- **Studio panels & interactions:** a **Structure Canvas** with switchable
  layouts — *Board* (kanban cards with full **inline** editing of summary/goal/
  conflict/outcome/status instead of menu dialogs), *Beatboard* (scenes on a
  normalized 0–1 story-position axis overlaying `_BEAT_POSITIONS` expected bands,
  so misplaced beats drift visibly outside their ghost slot), and *Outline-tree*
  (the `OutlineNode` tree). Live structural numbers retrack instantly on drag.
  A **Tension / Flow HUD** ribbon along the canvas baseline (the "story EKG"):
  `analyze_flow` as a continuous 0–10 curve colored by `tension_color`, climax
  peak marker, `PacingWarning` shaded bands, scene-type glyphs, tension *source*
  on hover. A **Structural Intelligence panel** grouping the seven issue
  categories with severity meters + jump-to links. An **act-balance / distribution
  strip** (proportional word-count bars, flagging <0.3× avg + thin middle, noting
  `inferred`-by-word-count acts). A **template gallery** that can apply a template
  as a translucent **scaffold/overlay** (ghost beat slots) rather than a
  destructive replace. An **AI Outline Studio** cockpit (scope selector,
  engine-aware labels, template + PSYKE toggles, instruction box) streaming into
  an `OutlineConfirmDialog`-style **diff/preview** with the repair warnings inline
  and per-node accept/reject before additive apply. A **Lambda / Quantum branch
  canvas** (radial superposition of 3–5 branches around an anchor; see §4.6). A
  **scene inspector dock** (all structural fields editable in place). A
  **mode-aware schema switcher** (Novel Act→Chapter→Scene; Screenplay
  Act→Sequence→Scene→Beat; Graphic Novel Act→Page→Scene→Panel). An **orphan /
  integrity HUD** (`validate_structure` → one-click `ensure_valid_structure`,
  visibly marking the "Unassigned" bucket). Everything is scene-derived, so every
  panel updates live off `build_structure_tree` + the event bus — real-time
  animated retracking (numbers, tension curve, balance bars, health flags) is
  cheap and a natural Studio showcase.

### 4.3 Timeline & plot
(`timeline_view`, `plot_timeline_view`, `canvas_plot_view`, `multi_plot_view`,
`story_flow`; engine row shapes in `graphic_novel_plot`, `stage_script_plot`,
`series_plot`)

Four distinct surfaces coexist, each a different mental model over the same
`Scene` data — the Timeline deliberately keeps its *own* ordering/membership so
reorganizing plot never silently rewrites the book.

- **`TimelineView`** — a **column grid**: **By Plotline** (one column per
  `Scene.plotline`) or **By Chapter** (one column per `Scene.chapter`), with a
  cross-axis filter and a **Focus Character** dropdown that adds a `→ <state>`
  line per card from `get_scene_character_states`. Drag a scene across columns to
  reassign plotline (`update_scene_plotline`) and across rows to reorder
  (`reorder_scene`); precise Move Up/Down; right-click color label; beat-coded
  cards (distinct styling for `KEY_BEATS` = Midpoint / All Is Lost / Finale /
  Climax / Break into Three). Screenplay cards add duration / location / INT-EXT
  + TOD / `↻ dramatic_turn` / `⚓ setup_payoff_links`. A **Graphic-Novel** variant
  swaps the table for a vertical **reading-flow strip** of page markers
  (`_GnTimelineMarker`: page number, panel count, density, reveal marker, `⟳`
  page-turn flag, rhythm chips, summary, motif markers, `@character` chips;
  expandable to `_GnPanelMarker` per-panel rows) with inline edits to summary /
  emotional beat / density / reveal / splash (`update_gn_page`). Stage and Series
  read-APIs exist data-only (`get_stage_timeline_rows` / progression /
  entrance-exit / cue markers; `get_series_timeline_rows` / season progression /
  setup-payoff chains).
- **`PlotTimelineView`** — the richest surface: a horizontal **plot-lane
  swimlane board**. Vertical axis = lanes/subplots (`TimelineLane`) + a virtual
  "Unassigned Events" inbox; horizontal axis = story-time columns with a numbered
  top ruler. **Two ordering modes**: **Structural** (follows the canonical Outline
  order) and **Custom Timeline Order** (timeline-local, opt-in, *never* mutates
  `Scene.sort_order`); any explicit move auto-switches to Custom. **Events are
  opt-in** — a scene appears only with a plotline or explicit membership; a dashed
  **"＋ N scenes off timeline"** affordance lists Outline scenes not yet on the
  board (add-one / add-all). Lane ops (add/rename/color/collapse/delete-keeps-
  events, "Create linked scene…" via `story_structure.create_scene`, "Add existing
  scene…"). **Event→event links** with typed relations (`TIMELINE_LINK_TYPES`:
  custom / causality / setup_payoff / echo / conflict / dependency), per-link color
  + label, two-step "Start link → Link to here", drawn as colored lines with end
  dots + midpoint label. **Event→structure links** to an Act/Chapter (`🔗 Act 1 /
  Ch 1.2` chip; a renamed/deleted target shows an amber `⚠` dangling chip). Cards
  show structural number prefix, title, Act·Chapter sub-line, **status chip**, link
  chips; lane bands tinted in lane color.
- **`CanvasPlotView`** — a free zoomable/pannable thinking board (QGraphicsView,
  0.25×–4× zoom, view transform **persisted per project**). **Blocks**
  (`CanvasPlotNode`: title/summary/category/color, move/edit/recolor/z-order/
  delete), **connections** (`CanvasPlotLink`: two-step connect, label, color,
  live re-route), and **frames/groups** (`CanvasPlotFrame`: titled colored
  rectangles behind blocks, title-strip-only interactive). Wholly independent of
  scene order (optional `scene_id` reference only).
- **`MultiPlotView`** — a perspective switcher over the same data: **Grid**
  (`StoryGridView`), **Timeline** (`_TimelineStrip`, L→R cards grouped by act/
  chapter), **Arc** (`_ArcLanes`, one lane per plotline), **Character**
  (`_CharLanes`, one lane per character with color dot + scene count), with
  unified `PlotFilters` (character / tag / plotline) and a writing-mode chip.
- **Story-flow analysis** (`story_flow`) is fully computed — `SceneTension`
  (value + source), `SceneType` (+ dialogue/action ratios), `PacingWarning`,
  `tension_color`, `scene_type_icon` — **but not yet surfaced in any of the four
  views** (a key Studio opportunity).

- **Studio panels & interactions:** a **Unified Plot Workspace** fusing the four
  surfaces into tabs/split-panes over **one selection model** (selecting an event
  highlights it everywhere) — left lane/outline rail, center plot-lane board,
  right inspector. A **cinematic Plot-Lane Board** (glowing lane bands, animated
  **bezier** causal links colored/labeled by `link_type`, the numbered ruler as a
  persistent top HUD, a minimap; drag events between lanes/columns; draw links by
  dragging between cards; Structural↔Custom toggle with a visible "off-Outline"
  badge; `🔗 Act/Ch` chips + amber dangling warnings inline). A **Tension/Pacing
  HUD overlay** (render `story_flow` as a tension **heat-ribbon** along the
  story-time axis, `PacingWarning` stretches as red monotone bands with reasons,
  `SceneType` icons per card, a floating **Story Pulse** HUD) — the biggest
  cinematic win, since the data exists and nothing renders it. An **inspector
  panel** exposing the *full* Scene surface the cards only hint at (goal/conflict/
  outcome, beat, all screenplay/stage fields, tension source, typed links list,
  structure links, character-state overlays) — eliminating today's `QInputDialog`
  micro-edits. A **causal-link / dependency graph view** (setup→payoff /
  causality / dependency chains + series setup_payoff_chains as a node-edge
  diagram, surfacing unresolved setups + broken dependencies). **Engine-aware
  timeline skins** for the data already exposed but unrendered: GN reading-flow
  ribbon (silence/action rhythm, page-turn setup→reveal connectors, density heat,
  splash markers, lazy panel expansion), Stage performance strip (entrance/exit
  markers, light/sound/music cue lanes, offstage flags, prop continuity), Series
  season/episode board (arc ribbons spanning episodes, setup/payoff chains,
  cliffhanger flags) — switched by a mode chip. **Canvas Plot as a premium
  ideation surface** (styled connector edges, frame auto-layout, snap/align
  guides, "seed from Outline" dropping scene-referencing blocks). **Cinematic
  flourishes:** lane-color glow + parallax depth, live link re-routing animation,
  a global **filter HUD** (character/tag/plotline/beat/tension-range) dimming
  non-matching cards across every pane, collapsed-lane "spark" summaries, and a
  "follow Outline" pulse when re-syncing Custom→Structural.

### 4.4 PSYKE — the story bible
(`psyke_view`, `psyke_console`, `psyke_highlighter`, `characters_view`,
`places_view`, `character_arc_view`, `character_balance_view`, `psyke_quick_create`,
`psyke_search`, `psyke_commands`/`_intents`/`_intent_llm`/`_suggestions`/
`_system_commands`/`_command_registry`, `temporal_psyke`, `auto_link`,
`controlling_idea`, `character_balance`, `psyke_visual`/`_series`/`_theatre`,
`models/psyke_details`, `api/routes/psyke`)

PSYKE is a **typed, relational, time-aware, medium-aware** knowledge base — far
more than a wiki. Every other craft feature (Character Arc, Balance, Controlling
Idea, Series/Visual/Theatre Memory) resolves *against* it. The headless REST
surface (`GET/POST /psyke/entries`, `GET/PATCH/DELETE /psyke/entries/{id}`,
`GET /psyke/search?q=`) means the Studio UI is a thin presentation layer over the
core.

- **Entry CRUD & typing** (`PsykeView`): 6 types
  (`character` 👤 / `place` 🏛 / `object` 💎 / `lore` 📜 / `theme` 🎭 / `other`
  📌); core fields name / entry_type / aliases / notes / `is_global` +
  `details_json`; a **per-type dynamic detail schema** (`get_detail_schema`) of
  dozens of typed fields grouped into named sections, each widget `line` /
  `multiline` / `combo` with `max_chars`. Duplicate-name detection warns
  (doesn't block).
- **Relations** (`PsykeRelation`): bidirectional, stored both ways with the
  correct inverse. **Typed** (`_RELATION_TYPE_CHOICES`: Associated / `Sets up →`
  / `Pays off →` / Thematic echo / Visual motif / Subtext opposition / Dominates
  / Submits to) plus a theatre vocabulary (pressures / confronts / avoids /
  dominates / submits / deceives / overhears / interrupts). Double-click a related
  entry to navigate.
- **Progressions** (`PsykeProgression`): per-entry ordered notes (`text`,
  optional `scene_id`, `sort_order`) describing change over time; add/update/
  delete, bind to a scene.
- **Temporal reasoning** (`temporal_psyke.TemporalGraph`): in-memory snapshot
  keyed by scene `sort_order`; `get_entry_state_at(entry_id, scene_order)`
  resolves the latest progression *before* a narrative point (anchored beats
  win); `get_active_related_entries` returns one-hop neighbors + their resolved
  state + `active` flag; `inspect()` is a full debug view.
- **Console / omnibox** (`psyke_console`, `psyke_commands`, `psyke_intents`): a
  slim always-on bar (24 px, opacity-fades idle↔active) with a results dropdown,
  keyboard nav, 100 ms debounce. Three modes: plain → **SEARCH**, `/command args`
  → **SYSTEM**, `/entityname action` → **ENTITY**. Built-ins: `create` / `open` /
  `go` / `ai` / `delete` / `rename` / `link` / `export` / `help` / `insert`
  (plugin-extensible). System handlers add `/idea …` (Controlling Idea) and
  `/strategy …` (router steering). **Natural-language intents** (regex + optional
  local-LLM fallback): "open scene 3", "create character john", "make it
  shorter/clearer/more dramatic" → confidence-scored, mapped to a slash command.
- **Search & suggestions** (`psyke_search`, `psyke_suggestions`):
  `PsykeSearchIndex` fuzzy over name + aliases (exact 1.0 → starts-with ~0.9 →
  contains ~0.6 → subsequence ~0.3 → initials 0.25); `resolve_entity` ≥0.6.
  `suggest()` mixes ranked `intent` (⚡) / `command` (⌘) / `entity` (type icon) /
  `entity_action` rows with a **scene-context boost** (entities in the active
  scene rank higher) and sub-arg completion.
- **Manuscript integration**: `PsykeHighlighter` (type-colored underlines) +
  `PsykeClickHandler` (Ctrl+Click jump); **`AutoLinkSuggester`** (`auto_link`)
  scans for capitalized proper nouns (stop-word filtered, ≥2 occurrences) and
  proposes non-blocking `Suggestion`s of kind `create` / `alias` / `relation`
  (co-occurrence) / `memory` (state-change verbs *became/realized/vowed/died* →
  progression) — **the engine never writes; the caller commits**, with an
  ignore-list keyed by `entity_key`. `find_psyke_scene_references` lists scenes
  mentioning an entry; `PsykeQuickCreateDialog` is a minimal name/type/aliases/
  notes/global modal from the scene context menu.
- **Medium-specific memory layers** (nested in `details_json`, schema-driven):
  **Visual Memory** (`psyke_visual`, GN — silhouette/shape-language/color-
  identity/costume-state/symbolism; derives motif recurrences/callbacks, object
  reappearances, `review_visual_memory` gap flags), **Series Memory**
  (`psyke_series` — per-character season/episode state, relationship-evolution
  beats, mystery threads, setup→payoff chains), **Theatre Memory**
  (`psyke_theatre` — objectives, subtext strategy, offstage knowledge,
  who-pressures-whom, props, entrances/exits). Each emits a compact
  `[Visual/Series/Theatre Memory]` block for the Assistant.
- **Controlling Idea** (`controlling_idea`): a McKee `VALUE + CAUSE` compass with
  value charge (positive/negative/ambiguous), counter-idea, per-scene + per-PSYKE
  alignment (supports/opposes/tests/transforms); auto-creates a linked *theme*
  entry; `check()` → coverage report + operational suggestions; `/idea` command;
  injects an `[Idea di Controllo]` block.
- **Character analysis**: **Character Arc** (`character_arc_view` — ordered
  scene-states of a character via `get_character_arc_by_name`, double-click opens
  scene); **Balance** (`character_balance` / `_view` — presence bars + per-arc/
  plotline presence, flags `dominant` (>60% & >2× avg) / `underused` (≤1 scene or
  <20% of max) / `thin` (single scene/act), each with color + plain-language
  `flag_help`).
- **Existing views**: `PsykeView` (left = search + type filter + list; right
  scrollable = core form + dynamic per-type Details + Visual Memory (GN) +
  Related Entries + Progressions + read-only Scene References); `PsykeConsole`
  (`_ResultsDropdown` accent-bar rows + fade animations + keyboard nav);
  legacy `CharactersView` / `PlacesView` (name+description + `BacklinksWidget`);
  `CharacterArcView`; `CharacterBalanceView` (`_PresenceRow`s); all subscribe to
  `psyke_changed` / `psyke_list_changed`.

- **Studio panels & interactions:** a **dockable Story-Bible Browser** (tri-pane:
  faceted filter sidebar — type / role / is_global / has-visual-series-theatre-
  memory / alignment — + virtualized list with type-icon glyphs + role badges +
  relation-count chips + a live count HUD; type-tinted accent bars). An **Entry
  Dossier** (center, tabbed: *Overview* / *Details* — the full section-grouped
  schema as a dense two-column form with live char-count meters / *Memory* —
  per-engine Visual/Series/Theatre / *Relations* / *Progressions/Timeline* /
  *Appearances*; a character **hero header** with role, archetype, and a
  want/need/lie/misbelief triptych from the Psychology fields). A **Relation Graph
  Canvas** (signature: force-directed, **typed directional edges** — supports_setup
  → payoff, dominates/submits, thematic_echo, visual_motif, subtext_opposition,
  theatre pressures/deceives/overhears; edge style encodes relation type; node
  size = scene presence; click-focus, hover-preview, drag-to-relate). A **Console
  Command Palette HUD** (Cmd-K overlay: ⚡/⌘/entity rows, sub-arg breadcrumbs,
  scene-context-boosted ordering, inline previews, recognized intent + confidence
  ghost hint). A **Temporal "State-at-Scene" Scrubber** (a scene timeline driven
  by `sort_order` + `get_entry_state_at` with a playhead; dragging shows each
  entry's resolved state and which related entries are `active`; per-character
  lanes as a "continuity piano-roll"; `inspect()` powers a debug overlay). A
  **Controlling-Idea Compass** (VALUE+CAUSE editor with charge selector +
  counter-idea + a scene-alignment ribbon supports/opposes/tests/transforms + a
  coverage HUD from `check()`; a literal compass/balance-scale for value charge).
  A **Balance & Arc Dashboard** (presence bars, flag legend, per-act presence
  sparklines, the arc scene-state list as a connected line). An **Auto-Link
  Inbox** (a non-blocking tray of `AutoLinkSuggester` + `review_visual_memory`
  output as accept/dismiss cards grouped by scene/kind, one-click commit, an
  ignore-list, and a "story health" pending-count badge). A **Series / Episode
  Memory Board** (Kanban episode columns: setup/paid-off/unresolved threads,
  mystery-thread tracker, per-character status timelines). A **Visual-Memory &
  Motif Wall** (GN: motif/recurrence grid, object reappearances with continuity-
  state badges, character visual-identity cards). All dock-friendly and
  event-driven.

### 4.5 The five format engines
Each writing mode is a *complete pipeline*. The workspace **re-skins** per mode
(§6). Every engine has the same shape — adapt the same panels:
- **Structure** (per-mode hierarchy), **Blocks** (per-mode scene-body model),
  **Planning Pipeline** (confirm-before-apply scene planning), **Diagnostics**
  (deterministic scene intelligence), **Reflection** (a Counterpart/Logos
  two-stance mirror), **Continuity** (multi-scene coherence), **Controlled
  Rewrite** (preview/diff/confirmed-apply), **Review Dashboard** (project status),
  **Export**.

A non-negotiable contract across all five: **the AI never writes the Manuscript
body directly.** Generation only ever produces a planning artifact or a draft
*preview*; nothing reaches `Scene.content` except through `controlled_apply`
after author confirmation (`confirmed=True`), a checkpoint, and rule-based
validation (**errors block, warnings allow**). Every analysis layer is pure logic
+ DB reads (no Qt, no LLM, no API keys); the UI owns the provider call and the
confirm dialogs.

- **Novel** — prose; Acts/Chapters/Scenes; chapter-rhythm focus.
- **Screenplay** — `screenplay*`, a numbered multi-phase pipeline (10A taxonomy →
  10B blocks → Phase 2 plan/draft → 10C diagnostics → 10D subtext + setup/payoff →
  Phase 5 reflection → Phase 6 rewrite → Phase 7 continuity → Phase 8 review →
  10E story graph → 10F render/title page → 10G Fountain → 10H pro output → 10J
  production). Canonical 8-element taxonomy (`scene_heading`/`action`/`character`/
  `dialogue`/`parenthetical`/`transition` + `shot`/`note`, with Ctrl+1..6
  shortcuts); a **beat plan** stored as a *third artifact* (`screenplay_beat_plans`
  in settings, separate from body and summary); deterministic **diagnostics**
  (scene economy, internal-state action, overwritten action, long monologue,
  parenthetical overuse, single-voice, unclear turn/objective, beat-plan
  alignment — each with severity/confidence/evidence/`target_block_index`/
  `logos_action_id`); a **subtext** tracker (on-the-nose, exposition risk,
  avoidance, objective gap); a **setup/payoff** tracker (~35 loaded objects +
  promises/threats/secrets, recurring motifs, unresolved setups); a two-stance
  **reflection** mirror; a **controlled rewrite** with 10 named instruction
  presets + index-surgery so only the targeted block/selection changes;
  **multi-scene continuity**; a **story-link graph** (14 node / 12 edge types,
  candidate→confirmed `StoryLink` rows); render → **Fountain / FDX / DOCX / PDF /
  HTML** with compatibility levels; and **production drafts** (persistent scene
  numbering `10A`/`10B`, omit/restore, dated coloured **revision sets**). Dialogs:
  `screenplay_review_view`, `_rewrite_dialog`, `_import_dialog`,
  `_pipeline_dialogs`. (Full detail in §4.5a.)
- **Graphic Novel** — `graphic_novel*` canonical **Act → Page → Scene → Panel**
  (`graphic_novel_structure`: a scene auto-chains onto pages or is **pinned** via
  `gn_page_start` / `set_scene_start_page`). Two coexisting models: a *lightweight
  body adapter* (`Page → Panel` with Visual/Caption/Dialogue/SFX/Notes, lossless
  parse⇄serialize, cursor↔panel mapping) and *rich DB tables*
  (`GraphicNovelIssue/Sequence/Page/Panel/ContinuityItem` with density level,
  reveal type, splash, shot/camera/transition, reading priority). A **page+panel**
  manager + a **Page Canvas/Preview** (`graphic_novel_pages_view`, `_page_canvas`,
  `_scene_pages_view`); AI **image-prompt export** (`graphic_novel_ai_export`:
  `build_gn_panel_prompt_package` composes positive/negative prompts from panel +
  PSYKE visual memory + project `gn_style`; **ComfyUI is stubbed** —
  `comfyui_available()` always False). (Full detail in §4.5b.)
- **Stage Script** — `stage_script*` theatrical structure (13 typed blocks:
  Scene/Act Heading, Stage Direction, Character, Dialogue, Parenthetical, Enter,
  Exit, Light Cue, Sound Cue, Set/Props, Transition, Note), blocking, performable
  dialogue; pipeline artifacts `StageBeatPlan` + `BlockingCuePlan`;
  `stage_script_review_view`. (Full detail in §4.5c.)
- **Series / Teleplay** — `series*` corrected **Season → Episode → Act → Chapter
  → Scene** with **real Season/Episode tables** above the scene-derived tree;
  **Series Navigator** (`series_navigator_view`) with full hierarchy CRUD and a
  legacy-migration (`migrate_legacy_series`, non-destructive dry-run);
  cross-episode continuity + long-form series memory; pipeline artifacts
  `SeasonArcPlan` (keyed by Act name) + `EpisodeBeatPlan` (keyed by Chapter name,
  with A/B/C-story coverage). (Full detail in §4.5d.)
- **Panels:** each mode gets its **Review Dashboard** (status aggregation), its
  pipeline confirm dialogs, its rewrite diff modal, its export dialog. Design one
  adaptable "Mode Review" dashboard + one "Pipeline confirm" pattern, themed per
  mode. Across all three script engines the Studio should **unify the Review +
  Continuity dashboards** into one dockable status console: summary cards as a
  compact metric HUD, a per-scene status table with severity color-coding
  (info/watch/weak/critical), a continuity-findings pane (visual flow / character
  / object-place / motif / setup-payoff / timeline / PSYKE) with per-finding
  suggested-action + "jump to scene", a recommended-fixes list, and the per-row
  **Next Action** as a one-click route into the relevant editor. All panels must
  be **dockable/tear-off**, theme-token-driven (replace inline `setStyleSheet`
  hex with the design system), and respect the cursor↔panel mapping so selection
  stays synchronized across canvas, inspector, script editor, and review table.

#### 4.5a Screenplay pipeline (detail)
- **Beat-plan → draft pipeline** (`screenplay_pipeline`): `ScreenplayBeatPlan`
  (objective, dramatic_question, conflict, turning_point, emotional_shift,
  visual_beats[], dialogue_intentions[], continuity_notes); apply modes
  `APPLY_TO_EMPTY` (only when body empty) / `APPLY_REPLACE` (double-confirm) /
  `APPLY_APPEND` / `APPLY_CANCEL`; `validate_draft_blocks` blocks on empty/fences/
  leaked-commentary/plan-as-body and warns on missing-heading/orphan-dialogue;
  `preview_draft_apply` (diff + conflicts, no mutation) then `apply_draft`.
- **Diagnostics** (`screenplay_diagnostics`) → `ScreenplaySceneReport` (counts,
  economy label, runtime ~1 page/min, extended metrics) + grouped issues (Format /
  Visual Writing / Dialogue Economy / Dramatic Function / Beat Plan Alignment /
  Continuity / Setup & Payoff); `screenplay_health_metrics` builds ~30
  `NarrativeHealthMetric`s (craft + format, **format capped at WATCH** so it never
  flips narrative health to critical).
- **Subtext** (`screenplay_subtext` → `SubtextSignal` with confidence) and
  **setup/payoff** (`screenplay_setup_payoff` → candidates setup/payoff/motif/
  promise/threat/object/callback/unresolved). **Reflection**
  (`screenplay_reflection` → `SceneReflectionReport`: Internal vs External
  perspective, Conflict/Objective/Obstacle, Visual/Dialogue notes, Beat-Plan
  alignment, Continuity/PSYKE risks, **reflective Questions** — never answers,
  never rewrites). **Controlled rewrite** (`screenplay_rewrite`: 10 presets — Make
  More Visual / Tighten Dialogue / Strengthen Conflict / Add Subtext / Reduce
  Exposition / Add Visible Turning Point / Reduce Monologue / Convert Emotion to
  Behavior / Make It More Filmable / Rewrite from Counterpart Notes + Custom;
  targets selection/block/scene; `diff_blocks`; `build_rewrite_preview` does index
  surgery so only the target changes). **Continuity** (`screenplay_continuity`)
  and **review** (`screenplay_review` → `SceneReviewRow`s with per-axis statuses +
  a computed **next action** worst-first + 8 filters). **Story-link graph**
  (`screenplay_graph`). Render/Fountain/interchange/output as above.
- **Existing surfaces:** `ScreenplayReviewView` (6 summary cards, 8-filter combo,
  10-column per-scene table, export-ready indicator, Save-as-Note);
  `BeatPlanPreviewDialog` / `DraftPreviewDialog` / `RewritePreviewDialog` /
  `FountainImportDialog`. **Studio:** a **Pipeline Status Rail** (per-scene stages
  Outline → Beat Plan → Draft → Diagnostics → Subtext → Reflection → Continuity →
  Export → Production as status pips with a script-wide health heat-strip); a
  **Beat Plan Studio** (8-field editor with visual_beats / dialogue_intentions as
  reorderable chips + a live alignment overlay + a beat filmstrip); a **Draft &
  Rewrite Canvas** (persistent side-by-side diff replacing the modals, colored
  block-diff gutter, the 10 presets as a palette, target scoping highlighted on
  the canvas, apply modes as a confirm bar); a **Diagnostics HUD** (economy gauge,
  runtime, metric readouts, 7-category issue list with jump-to-block + one-click
  `logos_action_id` fixes); a **Subtext & Dialogue Lens** (inline confidence-
  shaded flags); a **Setup/Payoff & Motif Board** (threads across the scene chain,
  unresolved setups glowing as open loops, inline confirm/dismiss writing a
  `StoryLink`); a **Story-Link Graph Canvas** (14 nodes / 12 edges, candidate
  dashed vs confirmed solid); a **Continuity & Scene-Chain Timeline**; a
  **Reflection Mirror** (Internal vs External + Questions); a **Pro Review
  Dashboard**; and an **Export & Production Console** (title-page form, format
  picker with compatibility badges, live readiness validation, Fountain import
  preview, a production sub-panel with scene-numbering grid + revision sets + the
  "page locking is approximate" caveat).

#### 4.5b Graphic Novel pipeline (detail)
- **Planning** (`graphic_novel_pipeline`): two settings-backed artifacts keyed by
  scene — `PageBreakdown` (with `target_page_count`) and `PanelPlan` — feeding a
  draft (system roles "graphic novel editor / artist-writer / scripter"), each
  validated + Controlled-Apply-gated. **Image-prompt** (`graphic_novel_ai_export`):
  project `gn_style` profile (art_style, linework, color_palette, rendering_style,
  aspect_ratio, panel_consistency_notes, negative_prompt_defaults);
  `GraphicNovelPromptPackage` (positive + negative prompt, resolved characters/
  locations/objects, style/continuity notes, camera/shot/tone, warnings) with
  guardrail warnings (>4 characters, char/motif not in PSYKE, no visual identity,
  no description/shot/camera). **Continuity** roll-up (visual flow, character,
  object-place, motif echo, setup/payoff, timeline, PSYKE).
- **Existing surfaces:** `GraphicNovelPagesView` (3-pane over the rich tables:
  Pages list with density/reveal/splash badges + Generate-Draft menu; panel editor
  with shot/camera/tone/transition/reading-priority + a Prompt export menu;
  `GraphicNovelPageCanvas` read-mostly 2:3 page with auto-grid/splash boxes);
  `GraphicNovelScenePagesView` (scene-centric over the shared body, collapsible
  `_PanelCard`s); `GraphicNovelReviewView` (8 cards, 13-column table); the three
  pipeline preview dialogs. **Studio:** a **GN Page Canvas** as the flagship
  cinematic layout stage (multi-page spread/thumbnail rail, zoomable page surface,
  density-driven layouts with real gutter/bleed, drag panels between pages via
  `move_panel_to_page`, **visually pin/release** a scene's start page; page-turn/
  reveal markers as spine breaks, splash pages full-bleed, density as heat tint);
  a **Panel Inspector** reconciling both GN models in one surface with character/
  motif PSYKE chips that light up green/amber; an **Image-Prompt HUD** (composed
  prompts + resolved visual identities + the guardrail warnings + a persistent
  **Style Profile** editor + a disabled-but-visible "Send to ComfyUI" reflecting
  the pipeline boundary); and the shared **Plan → Plan → Draft workflow rail**
  (Breakdown → Plan → Draft) with the Controlled-Apply gate inline.

#### 4.5c Stage Script pipeline (detail)
- **Blocks** (`stage_script_blocks`): 13 typed blocks with a human-editable
  labelled grammar (`SCENE:`/`STAGE:`/`CHARACTER:`/`ENTER:`/`LIGHT:`/`SOUND:`/
  `SET:`/`TRANSITION:`/`NOTE:`); bare cues + parentheticals auto-detected; bare
  prose → Stage Direction. Validation: empty cue, cue with no dialogue, dialogue
  with no cue, 6+ consecutive dialogue without action, long stage direction, "all
  talk". **Pipeline** (`stage_script_pipeline`): `StageBeatPlan` + `BlockingCuePlan`
  (staging-area notes, character positions, movement beats, entrance/exit plan,
  lighting/sound cues, prop/set/transition notes; roles dramaturg → stage director
  → playwright). **Existing:** `StageScriptReviewView` (8 cards, 13-col table).
  **Studio:** a **Stage blocking/cue board** — a top-down staging diagram driven
  by `BlockingCuePlan` (character positions, movement beats, entrance/exit plan)
  with lighting/sound/prop cues as a vertical cue-stack timeline alongside the
  dialogue, and the 13 block types color-coded in the script gutter.

#### 4.5d Series pipeline (detail)
- **Structure** (`series_structure`): real Season → Episode rows above the
  episode-scoped Act→Chapter→Scene tree; full CRUD; `assign_scene_to_episode`;
  `scene_series_path` ("Season 1 — Pilot · Episode 1 — Cold Open · Act 1 · Scene
  1.1"); `migrate_legacy_series(confirmed=)` (Act-as-Season/Chapter-as-Episode →
  real rows, non-destructive dry-run). **Blocks** reuse `screenplay_blocks` +
  serial markers Act Break / Teaser-Cold Open / Tag. **Pipeline**: `SeasonArcPlan`
  (premise, arc_question, episode_progression[], character_arcs[], motifs,
  setup_payoff/cliffhanger notes) + `EpisodeBeatPlan` (premise, objective,
  a_story/b_story/c_story, teaser/cold_open, act_breaks[], turning_points[],
  climax, tag/button, character_arc_beats[]; roles showrunner → TV story editor →
  episodic screenwriter; validation adds A/B/C coverage + serial-marker placement
  checks). **Existing:** `SeriesNavigatorView` (hierarchy-mode tree with full CRUD
  + Unassigned bucket; legacy-mode read-only with one-click Convert) and
  `SeriesReviewView` (8 cards, 11-col table keyed by "Episode · Scene"). **Studio:**
  a **showrunner board** — a Season/Episode card board exposing the rich fields
  not currently surfaced (season_arc, central_question, finale_payoff; episode
  logline, teaser, act_breaks, cliffhanger, estimated_runtime_minutes), A/B/C
  threads as horizontal swim-lanes across an episode's scenes, serial markers as
  timeline beats, `scene_series_path` as a breadcrumb HUD, with the legacy→
  hierarchy migration as a prominent, reversible-feeling confirm flow.

### 4.6 Assistant & AI surfaces
(`assistant_view`, `assistant_dock`, `chat_view`, `mode_strip`,
`mode_suggestions_view`, `quantum_timeline`; engines `assistant`, `counterpart`,
`adaptive_mode`, `assistant_context_policy`, `context_builder`, `providers`,
`irrational`, `creative_layer`; subpkgs `logos/`, `quantum_outliner/`,
`rewrite_sandbox/`, `controlled_apply/`, `revision_intelligence/`)

The whole domain is **one shared backend** (`assistant.chat_completion` /
`chat_completion_stream` over a single configured provider) consumed by several
distinct personas/modes that never duplicate the provider system. Every persona
builds its provider via `build_active_provider`; Logos/Quantum/Rewrite explicitly
inject `chat_fn`/`provider_resolver` to prove they own no provider system.
Response caching (TTL 300 s, 128-entry LRU) except streamed/Counterpart/Quantum.

- **Billy** (the **Assistant**) — generative writing: preset actions
  (`PRESET_ACTIONS`: Rewrite / Expand / Summarize / Dialogue / Tension / Pacing /
  Next Beat / Alternatives) + free-form **Generate** + structured **Suggest
  Beats**. Context source is selectable (**Selection / Current scene / Outline /
  Acts / Whole project**); output applies via **Copy / Replace / Insert / Append**,
  or **Apply to Outline** (parsing into acts/chapters/scenes). Section-aware system
  prompts (`SECTION_SYSTEM_PROMPTS` for Manuscript/Outline/Scenes/Characters/Plot/
  Acts/Beats/Dialogue/Notes/Places/Pacing/PSYKE) shape prose vs structure vs
  analysis; the writing-mode overlay folds in; direct-writing actions get a strict
  `output_contract` while analysis gets the full critique overlay. Surfaces: a
  docked side panel (`assistant_dock`/`assistant_view`), a full project **Chat**
  (`chat_view`), inline forms (§4.1).
- **Logos** — the *inline / contextual / section-aware* AI layer (~120 registered
  `LogosAction`s across Manuscript/Outline/PSYKE/Plot/Timeline/Graph + screenplay
  families), tagged **deterministic** (rule-based, no LLM) vs LLM and **diagnostic**
  vs **generative**, grouped into UX buckets (Planning/Checks/Reflection/Rewrite/
  Export/Other). Plus a **proactive engine** (`logos/proactive` → `LogosSuggestion`s
  with type/title/message/evidence/confidence/severity info-warning-important/
  suppression/dedupe — never LLM/blocking, **no UI today**), **narrative health**
  (`logos/health.HealthEngine.generate_report` → per-category metrics, overall
  label, top risks, strengths, prioritized `HealthRecommendation`s), and a
  **strategy router** (`logos/strategy` → deterministic dominant-strategy decision
  + included context blocks + reasoning notes).
- **Counterpart** — a **dialogic** reflective critique that **never rewrites**
  (modes Feedback / Critique / Interpret / Ask Back / Compare; apply disabled by
  contract).
- **Quantum Outliner** (`quantum_outliner/`) — a signature Studio feature:
  `generate_outline` / `generate_branches` (3–5 `Branch`es) / `reframe(scene, pov)`
  (relativity) / `detect_weak_scenes` (uncertainty) / `collapse_branch` (commits a
  branch as canonical, writes its `StateDelta` to PSYKE, archives the rest,
  emits confirmable proposals, and **adapts scoring weights** from the choice) /
  `compare_branches` / `explain_branches` / `get_decision_history`. **Scoring**:
  5 factors (structure_fit / psyke_consistency / tension_gain / novelty /
  goal_alignment), presets Balanced/Conservative/Bold/Character-driven/
  Plot-driven, beat-phase bias, goals, hard constraints ("no X"), Pareto mode,
  ensemble heuristic+LLM, lookahead cache. Structure modes auto/classical/quantum/
  hybrid; outline modes **CLASSICAL** (linear, RAG-backed) vs **LAMBDA**
  (superposition + collapse). View it as a **Quantum Timeline** (canon scenes as
  columns + branch lanes; Lambda = full branch fans with `⟨ψ⟩ N paths` uncertainty
  zones, per-branch nodes with probability/status/branch-type, a
  `ScoringWeightsPopover` of 5 normalized sliders).
- **Three mutation-safe pipelines**: **Rewrite Sandbox** (`rewrite_sandbox` —
  isolated sessions generate scored variants without touching canon; ~50 mode-aware
  strategies; deterministic `score_rewrite` with length/sentence/dialogue deltas +
  **PSYKE preserved/removed/added** + screenplay warnings; stale-source guard;
  `apply_rewrite_variant(confirm=True)` routed through Controlled Apply);
  **Controlled Apply** (`controlled_apply.service` — the single mutation gate,
  `ApplyPreview` with before/proposed/after + diff + conflicts blocking/error/
  warning + checkpoint + force override + history); **Revision Intelligence**
  (`revision_intelligence.impact_map.build_revision_impact_map` → impact level
  low/medium/high/critical + confidence, impacted scenes/PSYKE/setup-payoff/
  continuity/production, diff excerpts).
- **Adaptive Mode** (`adaptive_mode`) — `compute_mode` → `ModeResult(mode ∈
  STRUCTURE/BALANCE/REFINEMENT, stage EARLY/MID/LATE, health BALANCED/UNEVEN/
  FRAGMENTED, description)`, injected as `[AI Mode]` guidance; the **Mode Strip**
  shows/overrides it.
- **Irrational** (`irrational`) — "Go Irrational" injects surreal fragments
  (displacement / blend / inversion / echo / rupture), deterministic per-scene
  seed with re-roll, read-only, PSYKE-derived; the existing purple `#a855f7`
  accent.
- **Context assembly** (`assistant_context_policy.gather_injected_context`) is
  **layered, capped, conservative-by-default** (toggleable blocks: Project Mode,
  screenplay diagnostics/setup-payoff/subtext/links/export, production draft,
  revision impact, rewrite sandbox, controlled apply, project intelligence, guided
  workflow, knowledge graph, continuity, strategy, **health off by default —
  expensive**, diagnostics capped) plus `context_builder` scene/story/character-
  memory/PSYKE/notes/graph context. **Never a blind dump; project-switch never
  leaks.** An **output validation contract** (`assistant_contract.route/validate`):
  invalid output (planning leak where prose expected) → Apply disabled + raw
  shown; secret/raw-audio leak → response **withheld**.
- **Chat** (`chat_view`) — project-aware, **streaming** token preview,
  rolling-summary memory, **8 personalities** (default/mentor/skeptic/editor/
  brutal/whimsical/minimalist/philosopher), **action proposals** parsed from
  replies → Apply/Discard cards via `connector_executor`, slash commands
  `/context /memory /clear /summarize /series /gn`, per-project opacity + colors,
  detachable floating window.
- **Existing views:** `AssistantPanel` (dense dockable right panel: pin/collapse/
  undock/close header, a **3-way segmented** Assistant | Counterpart | Quantum
  selector, `ModeStrip`, context-source combo, per-mode action grids, Quantum
  Structure-mode buttons + **Lambda Mode** toggle + embedded `QuantumTimelineWidget`,
  collapsible Settings with the include-* toggles + **Go Irrational** purple
  checkbox + "show context sent to model" viewer + provider settings + API
  timeout, a response area + Apply row with validation gating); `AssistantDock`
  (responsive `[content | strip | panel]` host, auto-hide when cramped unless
  pinned); `ChatView`; `ModeStrip`; `ModeSuggestionsView` ("Adapt"); and
  `QuantumTimelineWidget` (+ `ScoringWeightsPopover`).

- **Studio panels & interactions:** the current cramped ~360 px panel should
  explode into a **multi-pane dockable command surface**. An **AI Command Rail /
  Persona Switcher** (Assistant · Counterpart · Quantum · Logos · Chat as
  first-class destinations, with an always-visible **provider + model + latency/
  cache** status chip + a live token-stream meter + per-persona in-flight
  spinner). A **Context Inspector** (glass HUD) — promote the hidden "show context
  sent to model" viewer into a permanent **layered, collapsible tree** of every
  injected block (Mode, Irrational, Story Memory, Controlling Idea, PSYKE, Notes,
  Graph, Structural, Outline, Scene + the 18 `assistant_context_policy` blocks),
  each with an on/off toggle wired to the real settings flags + caps, char/token
  count, source attribution, and a context "budget bar". The **Quantum Field
  canvas** (the cinematic centerpiece, not a 260 px strip): glowing wavefunction
  nodes, probability-weighted branch **fans** colored by `branch_type`, an inline
  **factor radar** per branch (5 factors), Pareto-front highlighting, the
  `ScoringWeightsPopover` as a docked side panel with live re-scoring + goals
  editor + hard-constraint chips + beat-phase indicator, **collapse** as a dramatic
  animation that shows the `psyke_summary` + confirmable proposals as cards +
  "Weights adjusted (learning ON)", and a **Decision History timeline**. A
  **Counterpart reflection pane** (calmer two-column text↔critique, 5 dialogic
  modes as tabs, explicitly apply-disabled). A **Logos action HUD** (a floating
  selection-anchored palette of `available_actions(section, writing_mode)` grouped
  with deterministic-vs-LLM badges) **+ a Proactive Suggestions tray** (the
  `LogosSuggestion` stream as severity-ranked chips with confidence meters,
  evidence on hover, run-suggested-action, dismiss/snooze — this layer has **no UI
  today**). A **Narrative Health dashboard** (per-category gauges, top-risks/
  strengths, recommendation cards problem/why/evidence/→action, a category
  heat-grid, JSON/Markdown export). A **Rewrite Sandbox studio** (source pane vs N
  variant columns, each with `score_rewrite` metrics + **PSYKE preserved/removed/
  added** chips + screenplay warnings + the producing strategy + a stale-source
  banner + a "preferred" star + a guarded Apply opening Controlled Apply). A
  **Controlled Apply diff modal/drawer** (a real before/after/proposed diff +
  conflict list with suggested resolutions + checkpoint indicator + apply/apply-
  partially/force + an Apply History log — the universal mutation gate used by
  Quantum, Rewrite, and Logos). A **Revision Impact map** (a radial center-scene →
  impacted scenes/PSYKE/setup-payoff/continuity/production rings, colored by
  impact_level + confidence). An **Adaptive Mode HUD** (always-visible Structure/
  Balance/Refinement with Stage•Health + one-click override + inline mode
  suggestions). An **Irrational mode** cinematic toggle (the 5 fragment kinds as
  surreal cards with re-roll + seed + source-entry links). **Chat as a docked
  panel** (streaming, action-cards, personality, a visible memory/summary
  inspector). The throughline: the core emits richly-structured render-ready
  payloads (probabilities, factor dicts, confidence, severity, diff/conflict
  structures, decision logs, weakness bars) that the current panel flattens into
  monospace text — Studio's job is to render them as **live graphs, gauges, fans,
  diffs, and heat-grids**.

### 4.7 Narrative intelligence & analytics
(`narrative_dashboard_view`+`narrative_dashboard`, `dashboard_widgets`,
`story_health_view`+`story_health`, `pacing_insights_view`+`pacing_insights`,
`beat_analysis_view`, `act_analysis_view`, `tag_analysis_view`, `analytics`,
`mode_suggestions`, `adaptive_mode`; the **Project OS** subpkgs in §4.9)

This is the **read-only analytical brain** — deterministic engines that observe
manuscript + PSYKE and surface structural truth (tension, pacing, balance,
continuity, health, risk) **without ever mutating content or calling an LLM** (the
lone exception: `narrative_suggestions.py`, the one LLM path). A consistent
contract: deterministic, evidence-backed, capped, **advisory-only**; issues carry
`severity` + `confidence`; nothing auto-fixes.

- **Lightweight analytics** (`analytics`): `compute_scene_stats` →
  `{words, paragraphs, sentences, dialogue_ratio, hint}` (hint ∈ short/long/
  dialogue-heavy/narrative-heavy); `compute_project_stats` → `{scene_count,
  avg_words, longest, shortest}`.
- **Story Health** (`story_health`): 4 `HealthSignal`s — Structure / Characters /
  Arc Coverage / Scene Density — each `label` + `level` (balanced/sparse/
  problematic) + `score` 0–1; `level_color` (`#4ade80`/`#f59e0b`/`#ef4444`);
  `signal_help` tooltips.
- **Pacing Insights** (`pacing_insights`): up to 5 `Insight`s
  (`text`/`severity`/`category`) from disappearance / monotony / stagnation /
  neglect / clustering detectors (activates ≥5 scenes); `insight_color` per
  category.
- **Narrative Dashboard** (`narrative_dashboard.compute_dashboard`): in one read
  pass — a **tension curve** (per-scene 0–100 = char_count + relation_pairs +
  keyword_hits + progression_count, 60+ tension keywords; flags flat/spike/weak-
  buildup), **character/theme presence** (over-dominant >80% / absent ≥3
  consecutive / underused <20%), **structure distribution** (act segments by
  scene+word count, infers 3 acts by word-count if no Act labels — `inferred=True`).
- **Narrative Suggestions** (`narrative_suggestions`, the one LLM call):
  `build_suggestion_messages` → exactly 5 typed structural beats — **Escalation /
  Reversal / Delay/Interruption / Internal Shift / Reveal** — compact directions,
  never prose; `format_suggestion_debug` shows the orchestration.
- **Adaptive Mode + Mode Suggestions** (`adaptive_mode`, `mode_suggestions`):
  `compute_mode` (Structure/Balance/Refinement from stage × health);
  `generate_mode_suggestions` → up to 5 tailored `ModeSuggestion`s (Structure:
  missing acts/plotlines, unlinked characters, scenes lacking goal/conflict;
  Balance: dominant/underused characters, thin arcs, plotline streaks, act
  imbalance; Refinement: dialogue-less/thin/stagnant/dense scenes, missing
  summaries).
- **Existing views**: `NarrativeDashboardView` (four custom-painted panels in
  `dashboard_widgets` — TensionCurvePanel with hover tooltips of the 4 score
  components + click-to-scene, CharacterPresencePanel strip timelines,
  StructurePanel segmented act bar, ThemeContinuityPanel + a "Flags" summary box +
  an "Acts inferred by word count" caveat); `StoryHealthView` (four `_HealthBar`s);
  `PacingInsightsView` (`_InsightRow`s, distinguishing "<5 scenes" from "even");
  `BeatAnalysisView` (HTML: phase coverage of 7 Save-the-Cat phases + beat summary
  + beat positions with `scene:<id>` links); `ActAnalysisView` (act table +
  per-act listing); `TagAnalysisView` (tag grouping + clickable scene lists).
  **Notably absent** (engines with no Qt view): Project Intelligence / Decision
  Radar, Guided Workflows, the Semantic Continuity Engine — the biggest greenfield
  surfaces (see §4.9).

- **Studio panels & interactions:** turn these engines into a **dockable analytics
  workbench** with a persistent intelligence HUD. A **Decision Radar Dock**
  (highest priority — see §4.9). A **Project Intelligence "Mission Control"** tile
  grid. A **Narrative Dashboard cinematic upgrade** (a scrubbable tension curve
  with a draggable playhead synced to manuscript scroll, hoverable score-component
  breakdown, flag pins, a heatmap variant; presence timelines as a stacked "scene
  reel"; a **tension overlay strip** docked above the editor; a stacked-area "what
  drives this peak" view from `SceneTension`'s 4 components). A **Continuity
  Inspector Dock** (§4.9). A **Guided Workflows Panel** (§4.9). An **Adaptive Mode
  HUD chip** (current mode + stage×health subtext, expanding to the 5 suggestions).
  A **Pacing / Health rail** (the four health bars + pacing dots, carrying the
  `level_color` / `insight_color` palette as the Studio severity language). And
  **Beat / Act / Tag canvases** (a beat-phase coverage **ring** with hollow
  missing phases, an act distribution bar with scene-range brackets, a tag
  co-occurrence/frequency cloud — all retaining scene-deep-linking). Cross-cutting:
  a unified severity/confidence grammar, deep-link plumbing (`related_section` /
  `scene:<id>` / `action_id`), live debounced recompute (`light=True` paths), and
  prominent "advisory only / routes through Controlled Apply" affordances. Heavy
  charting opportunity.

### 4.8 Knowledge Graph
(`graph_view`, `focus_graph_view`, `graph_analysis`/`_flow`/`_gravity`/`_meaning`/
`_suggestions`, subpkg `knowledge_graph/`)

There are **two parallel graph systems** a Studio UI must expose together:

1. The **Narrative Knowledge Graph** (`knowledge_graph/`, "Phase 10P") — a
   *traceable semantic map* built in-memory, deterministically, read-only,
   current-project-only, **on every request**. Nodes/edges carry **confidence,
   provenance, and source-system** metadata; **inferred** edges never masquerade
   as canonical. Only **user-confirmed / hidden** edge state persists (inferred
   edges regenerate). No LLM, no cloud, no external graph DB — the "explainable
   truth layer."
2. The **Live Visual Graph** (`graph_*` + `focus_graph_view`) — the rich
   interactive mind-map from `db.build_link_graph()` + PSYKE relations + scene/act/
   page metadata, with overlays for *story gravity*, *meaning*, *temporal flow*,
   and per-writing-mode views — the "cinematic canvas."

- **KG package**: `build_knowledge_graph` → `KnowledgeGraphResult`
  (`graph`, `undefined_terms`, `orphans`, `central`, counts, `summary_line()`)
  with toggleable source extractors (structure/psyke/notes/revision/rewrite/apply/
  workflows/setup_payoff; deferred systems recorded in `graph.unavailable`, caps
  in `graph.warnings`); a **query API** (`query_knowledge_graph` filtering by
  node_type/edge_type/`confidence_min`/`source_system`/depth/`include_inferred`);
  **scoring** (`orphan_nodes`, `high_centrality_nodes` — top-10 by plain degree,
  "no PageRank pretence" — `weak_link_edges` ranked weakest-first); **confirmable
  mutations** (`confirm_edge` / `hide_edge` / `unhide_edge`, and content mutations
  `convert_edge_to_psyke_relation` / `create_psyke_entry_from_term`);
  **serializers** (`explain_node` / `explain_edge` with provenance + "User-
  confirmed", `get_graph_summary_for_assistant`); and **decision cards**
  (`build_graph_decision_cards`: isolated PSYKE entry, plot block with no scenes,
  scenes with no PSYKE links, undefined terms, "≥10 inferred edges need review",
  central-node rewrite risk — each with severity/confidence/action + a target
  system label). **Node types (22)**, **edge types (20)**, **confidence**
  confirmed→likely→possible→unknown, **source systems (16)**.
- **Live visual graph**: `build_graph_data` → `GraphData{nodes, edges,
  adjacency}` (link graph + PSYKE relations + scene↔character/place participation +
  act-cluster nodes + mention edges); per-writing-mode enrichment injects extra
  nodes+typed edges (`enrich_screenplay_edges` / `enrich_graphic_novel_graph` /
  `enrich_stage_script_graph` / `enrich_series_graph`). **Story Gravity**
  (`graph_gravity`): per-node `StoryGravity{narrative, thematic, structural}`,
  `total = 0.45·narr + 0.35·them + 0.2·struct`, driving radius (+60%), glow halo
  (>0.55), and centre pull. **Meaning** (`graph_meaning`): `NodeMeaning{importance,
  state_warmth, is_dead_zone, psyke_glow, arc_group}` (character emotional state →
  warmth cool/warm/hot green/amber/red; dead-zone ≤1 connection; PSYKE glow ≥3).
  **Flow** (`graph_flow`): ordered `FlowSegment`s for **timeline / acts / arc**
  (Freytag curve) / **causal** (only `[[link]]`-connected), each scene tagged a
  band beginning/middle/ending (green/gold/violet). **Analysis** (`graph_analysis`):
  `analyze_node` → `NodeAnalysis{themes, relations, scenes, arcs, ci_alignment,
  ci_aligned_neighbours}`; `explain_structure`, `find_disconnected_nodes`,
  `suggest_missing_relations` (characters sharing ≥2 scenes but no relation),
  `find_weak_thematic_clusters`. **Suggestions** (`graph_suggestions`): 4
  categories Escalation / Reversal / Expansion / Internal-shift, each with `text` +
  `reason` + `trace_nodes` for highlighting. **There is no LLM in this domain — a
  deliberate, load-bearing property to surface in the UI** ("deterministic,
  traceable, no autonomous mutation").
- **Existing views**: `GraphView` (legacy — `[[link]]` entities on a circle,
  clickable colored nodes); **`FocusGraphView`** (~3.7k LOC, the workhorse): a top
  bar (search with no-match feedback, **Clear Focus**, a focus breadcrumb, and 5
  dropdowns — **Mode** of 32 `ModeProfile`s grouped by engine, **Filters** per-kind
  + 2-hop + hide-isolated + temporal + show-future + skeleton + mention-edges,
  **Layout** Auto/Hierarchical/Act-clusters/Timeline/Radial/Force + flow overlay,
  **Labels** None/Focus/Important/All + meaning overlay, **Actions** Fit/Reset/
  Refresh + gravity + suggestions/analysis panels + preset save/load); a
  `_ZoomGraphicsView` canvas (gravity halos, state-warmth coloring, dead-zone
  desaturation, constant-size labels, hover dims all but neighbors, flow arrows +
  arc links, progressive zoom-culling); and right docks (Suggestions panel "Next
  Narrative Possibilities", Analysis panel with focal-node Themes/Relations/Scenes/
  Arcs/**CI-alignment** + "Send to Assistant" + global Insights).

- **Studio panels & interactions:** a **Unified Graph Canvas** merging the visual
  graph with the Phase-10P confidence model (gravity halos as soft volumetric
  glows, state-warmth as emissive color, flow as an animated luminous path
  green→gold→violet, **inferred edges dashed/translucent vs confirmed solid**,
  progressive zoom-culling for hundreds of nodes, act/season "bands" as faint
  strata; click-focus, 1/2-hop expand, drag-pan, wheel-zoom, arrow-cycling, search-
  to-focus, marquee select). A **Mode Switcher HUD** (all 32 `ModeProfile`s grouped
  by engine with description tooltips + layout thumbnails, animated layout morphs).
  A **Layers / Filters dock** (per-kind toggles with shape+color swatches,
  skeleton-only, hide-isolated, mention-edges, a temporal scrubber bound to
  `set_temporal_max_order`, **plus the Phase-10P query controls** — `confidence_min`
  dial, `include_inferred`, source-system filters). An **Inspector panel**
  (`explain_node` / `explain_edge` with confidence chips + provenance + "User-
  confirmed" badge; inline **Confirm / Hide / Unhide** + the two content actions
  Convert-to-PSYKE-relation / Create-PSYKE-entry-from-term behind confirmation;
  `NodeAnalysis` incl. **CI alignment**; Send to Assistant). An **Insights /
  Decision-Radar dock** (`build_graph_decision_cards` + `GraphInsight`s as
  severity-coded cards with jump-to-system links + click-to-highlight; the "N
  inferred edges need review" card opens a **confirmation queue** worklist of
  `weak_link_edges`). A **Suggestions panel** (the 4 moves with trace-highlight
  on hover). A **Story-Gravity / Meaning HUD overlay** (legend + a "most-connected/
  highest-gravity" readout + a radial gravity-well minimap). A **Flow Timeline
  strip** (the four flow types as selectable ribbons; arc = Freytag curve; doubles
  as the temporal scrubber). A **Preset bar** (Save/load/delete named graph states
  as quick chips — "Theme audit", "Continuity check", "Character web"). And a
  **Build/Provenance status line** (`summary_line()` + `unavailable` + `warnings` +
  a "deterministic · no AI · rebuilt live" trust badge). Another signature
  cinematic surface.

### 4.9 The Project OS layer (Understand → Decide → Act → Verify → Apply)
(subpkgs `project_intelligence/`, `guided_workflows/`, `controlled_apply/`,
`rewrite_sandbox/`, `revision_intelligence/`, `continuity/`; docs:
ProjectOperatingSystem, DecisionRadar, GuidedWorkflows, ControlledApply)

- **Project Intelligence** (`project_intelligence/`) — one read-only aggregation:
  `build_project_intelligence_report(db, pid, light=)` → `ProjectIntelligenceReport
  (overview, psyke, structure, workflow, export, health, radar)` (`light=True`
  skips expensive Health + export validation). Collectors: `collect_overview`
  (title, mode, words, scene/chapter/act/note/psyke counts), `collect_psyke_summary`
  (by_type, empty_notes, no_relations, global_count), `collect_structure_summary`
  (scenes without chapter/summary, outline nodes, link-graph nodes/edges/isolated),
  `collect_workflow_status`, `collect_export_readiness` (Fountain validation),
  `collect_health_summary`.
- **Decision Radar** (`build_decision_radar`) — ranked `DecisionCard`s
  (`severity` blocking→warning→suggestion→opportunity→info, `confidence`,
  `category`, `title`, `explanation`, `suggested_action`, `related_section`,
  `related_target_type/id`, `rank`), capped 10, from ~15 deterministic rules
  (missing title/description, scenes without summary/chapter, isolated graph nodes,
  empty PSYKE notes/relations, unapplied preferred rewrite, stale rewrite, pending
  apply, high-impact revision, production numbering, export blockers, health
  risks). `summary_line()`, `top_cards(n)`.
- **Guided Workflows** (`guided_workflows/`) — 11 built-in templates (A–K: Project
  Setup, PSYKE Story Bible, Classical Outline, Scene Drafting, Rewrite, Screenplay
  Production Prep, Export Readiness, Decision Radar Fix, Knowledge Graph Cleanup,
  Continuity Review, Screenplay Continuity Pass), each an ordered `WorkflowStep`
  set (`kind` ∈ creative/check/manual, `section_name`, `action_id`,
  `completion_check`). Engine: `start_workflow` / `complete_workflow_step` /
  `skip_workflow_step` / `advance_workflow_step` / `pause/resume/cancel` /
  `refresh_workflow_run` (auto-ticks only deterministic `check` steps — **never**
  auto-completes creative steps). `WorkflowRunView` exposes total/completed steps,
  `is_complete`, `current_step`, `progress_line()`. ~20 yes/no
  `completion_checks` over the PI report; `build_workflow_recommendations` maps
  radar categories → recommended templates (cap 4).
- **Controlled Apply / Rewrite Sandbox / Revision Intelligence** — the **only**
  paths to content mutation: preview → **diff** → confirmed apply, with a **Change
  Impact Map** (`build_revision_impact_map` → impact level low/medium/high/critical
  + confidence, impacted scenes/PSYKE/setup-payoff/continuity/production, diff
  excerpts) shown before applying. (Engines detailed in §4.6.)
- **Semantic Continuity Engine** (`continuity/`) — `build_continuity_report(db,
  pid, scope=, scene_id=)` → `ContinuityReport(issues, facts, states, unavailable,
  warnings)` capped 120, status-merged from persisted dismiss/resolve/defer.
  Detectors: **contradictions** (dangling setup/payoff links → blocking/confirmed;
  screenplay unresolved-setups / orphan-payoffs), **missing transitions** (location
  jumps with no travel cue), **production** (scenes missing slugline/INT-EXT/TOD),
  **character drift** (single-appearance; recurring char absent from final ~40%),
  **scenes missing PSYKE**. Plus `check_scene_continuity` (neighbor-scoped),
  `validate_continuity_change` (a pre-apply **preview** of a rewrite's continuity
  risk → `is_safe`, warnings, `suggested_apply_mode` replace/manual_copy),
  `get_continuity_issues(severity=, dimension=, status=)`, `set_issue_status`,
  `build_continuity_decision_cards` (feeds the radar), `most_affected_scenes`,
  `issues_by_dimension`. UI legend enumerations: **10 dimensions** (character/
  temporal/spatial/object/plot/lore/theme/dialogue/production/mode_specific), **13
  issue types**, **4 severities**, **4 confidences**, **11 fact types**.

- **Studio panels & interactions:** a **Decision Radar Dock** (*highest priority —
  no view exists today*) — a ranked, filterable card stack from
  `ProjectIntelligenceReport.radar`, each card a severity chip + confidence badge +
  title + expandable explanation + `suggested_action` + a "Go to {related_section}"
  deep-link / "Start workflow" button; group-by-category; severity counts in the
  header; a pulsing red count for blocking issues + a radar-sweep micro-animation on
  refresh; pin as an always-on right-rail HUD. A **Project Intelligence "Mission
  Control"** (a dense tile grid of overview + the four collector summaries — words,
  scenes, chapters/acts, a PSYKE by-type donut, graph nodes/edges/isolated, workflow
  status, export readiness — with `summary_line()` as a status bar, cheap `light`
  recompute). A **Continuity Inspector Dock** (*no view exists*) — issues grouped by
  `dimension` (10-dimension legend) + `severity` with confidence badges, evidence
  excerpts, related-scene chips, dismiss/resolve/defer; a **"most affected scenes"
  heat strip**; an `issues_by_dimension` radial; a **per-scene continuity gutter**
  in the editor; and a **rewrite-safety inline panel** invoking
  `validate_continuity_change` before any Controlled Apply (showing `is_safe` +
  warnings + `suggested_apply_mode`). A **Guided Workflows Panel** (*no view
  exists*) — a left-rail stepper of active runs with progress bars, current step
  highlighted, step-kind icons (creative manual-only, check auto-verifiable with a
  live green tick when its `completion_check` passes, manual ack), `section_name`
  deep-links, `action_id` "run suggestion" buttons, a mode-filtered template
  gallery, a "recommended next workflow" banner, and a per-run event timeline (a
  compact "quest log"). And an **Adaptive Mode HUD** (§4.6). Cross-cutting: a
  unified severity/confidence grammar, deep-link plumbing, live `light=True`
  recompute, and prominent "advisory only / routes through Controlled Apply"
  affordances so the Studio's power never feels like it edits behind the writer's
  back. This loop is the spine of Studio — make it the calm cockpit, not
  notification spam.

### 4.10 Stages — versioning & branching
(`stages_view`, `stages`, `version_history_dialog`, `version_manager`, `autosave`,
`cloud_storage`, `recent_projects`)

- **Versioning** (`version_manager`): timestamped JSON snapshots under
  `~/.logosforge/versions/<project_id>/`, `MAX_VERSIONS=50` with auto-retention,
  a periodic interval `SNAPSHOT_INTERVAL_MS = 5 min` while dirty.
  `create_snapshot(reason=, label=)` (reasons `autosave` / `periodic` / `manual` /
  `pre-restore safety snapshot`); `list_versions()` → `VersionInfo[]`
  (`path`, `timestamp`, `reason`, `label`; derived `display_time`, `file_size_kb`);
  `load_version_data` / `restore_version` (**creates a safety snapshot first**,
  then `import_json` as a **new project** — never destructive) / `delete_version`.
- **Autosave** (`autosave`): debounced (`_DEBOUNCE_MS = 3000`) non-blocking save;
  `mark_dirty` / `mark_clean` / `save_now` / `force_next_save`; **external-change
  detection** via `FileFingerprint` (mtime/size) blocks save + emits
  `external_change_detected`; `write_conflict_copy_now()` writes a sibling
  `<stem>_conflict_<device>_<ts>.json`; a status signal emits "Saving… / Saved /
  Save failed / Save blocked: external changes". Note `_modified_since_save` (not
  `_dirty`) drives the close prompt.
- **Cloud-sync awareness** (`cloud_storage`): `atomic_write_text` (temp+fsync+
  replace); per-project **lock files** (`LockInfo`: device, user, timestamp,
  app_version, pid; `is_same_machine`, `is_stale`); `detect_cloud_folders` /
  `classify_path` (Dropbox / Google Drive / OneDrive / iCloud / NAS / Local).
- **Existing view**: `VersionHistoryDialog` — a flat 4-column table (Timestamp,
  Reason, Label, Size KB) with Restore/Delete Selected (each confirmed) + Close.

- **Studio panels & interactions:** a **Version Timeline HUD (canvas)** — replace
  the flat table with a horizontal **cinematic timeline** of `VersionInfo` ticks
  colored by `reason` (autosave / periodic / manual / pre-restore safety), labeled
  snapshots called out, `file_size_kb` as tick weight, hover-scrub to preview,
  click to diff-against-current, drag to restore (the core already does this safely
  via a pre-restore snapshot + new-project import). A live **"next autosave in
  N:NN" countdown** tied to the 5-min interval + dirty state. And a **Save / Sync
  status HUD** — a persistent corner widget surfacing autosave `status_changed`,
  the storage provider badge (`classify_path`), lock state, and **conflict
  resolution UI** for `external_change_detected` (currently only a signal + console
  text): a non-modal banner with "Keep mine (`force_next_save`) / Save a conflict
  copy (`write_conflict_copy_now`) / Reload disk version", since the core already
  exposes all three operations. Frame the branch/version timeline as git-graph-like
  but story-framed.

### 4.11 Voice — Dexter's Room
(subpkg `voice/` — `service`/`session`/`types`/`history`/`commit_router`/
`intent_router`/`billy_bridge`/`glossary`/`room`/`setup`/`transcriber`/
`lan_server`; `voice_panel`, `voice_setup_dialog`, `librechat_view`)

Local-first, buffered, near-live **dictation** — *not* realtime, not voice-to-
voice, not an autonomous agent. The philosophy: **the model generates; LogosForge
remembers, retrieves, structures, and acts only with explicit confirmation; raw
audio and secrets never leave the device.** The canonical headless API is
`VoiceRoomService`; all behavior is pure-Python and JSON-safe so any frontend wraps
it.

- **Lifecycle & capture**: start/stop/pause/resume (idempotent); a `VoiceStatus`
  (disabled · off · listening · processing · transcript_ready · error) plus a
  richer **14-state** room machine (`VoiceRoomStateMachine`: idle · checking_backend
  · ready · listening · segment_buffering · transcribing · transcript_ready ·
  choosing_target · sending_to_billy · proposal_ready · applying · applied · error ·
  stopped; invalid transitions return False, never crash). Two audio models
  (frontend-segmented `transcribe_segment`, or core `AudioBuffer` `feed_chunk` +
  `flush` segmenting on silence/max-duration); live int16-RMS mic level via
  `on_level`.
- **Backends** (`transcriber`, `lan_server`, `setup`): `local_process`
  (faster-whisper, **local model path only, never auto-downloads**), `whisper_cpp`,
  `lan_server` (private/loopback hosts only, no DNS, redirects refused, optional
  static auth header, payload guards), `mock`. `build_backend_profile` →
  `VoiceBackendProfile` (status ids ready / missing_dependency / missing_executable
  / missing_model / error / disabled / not_configured); `microphone_diagnostics`;
  `run_test_transcription` (never retained); performance profiles fast_draft /
  balanced / accurate / custom (mapping silence_ms + max_segment_seconds +
  beam_size). Language mode auto / project / explicit, tracking selected vs detected
  vs project codes + `language_source`.
- **Transcript history** (`history`, **session-only, in-memory, never persisted**):
  edit / merge (adjacent same-session) / split / discard / restore_original /
  **retry_transcription** (re-run on kept PCM) / clear. Segment states pending ·
  edited · committed · discarded · failed · corrected; provenance merged_from /
  split_from / original_text. **Audio is kept session-only for Retry; dropped on
  discard/clear/commit; never written to disk, never uploaded.**
- **Commit targets** (`commit_router`, mode-aware, **explicit only**): universal
  `active_cursor` / `note` / `psyche_draft_entry` (+ disabled-with-reason
  `manuscript_append`, `outline_draft_item`); mode-specific screenplay Action/
  Dialogue, GN Panel Visual/Caption/Dialogue/SFX/Notes, stage Stage-Direction/
  Dialogue, series Episode-Outline (disabled). `commit_transcript_op` validates the
  live target (project-id check prevents cross-project commits) and returns a
  `CommitOperation` undo record; **single-level undo** (`can_undo` / `undo_commit`,
  editor-undo revision-guarded, created Note/PSYKE deletion).
- **Intents** (`intent_router`, **preview-first, fixed allowlist**):
  `cleanup_transcript` (rule-based, never adds content), `insert_cleaned`,
  `rewrite_selection` (AI), `summarize_to_note` (AI), `send_to_psyke_draft`,
  `send_to_panel_field` (GN). `build_intent_preview` (before/after/diff, no
  mutation) → `apply_intent_preview` (re-validates live target). AI intents
  disabled with a clear reason when no provider.
- **Billy bridge** (`billy_bridge`): transcript → assistant proposal → confirmed
  apply (`billy_ask` / `billy_rewrite_selection` / `billy_continue_cursor` /
  `billy_summarize_note` / `billy_psyke_draft` / `billy_gn_panel_field`). **Text-
  only safe context** (never API keys, audio, or other projects). A **dangerous-
  instruction refusal** ("delete the project / run this command / comfyui / rm -rf
  / open terminal") returns a chat-only "I can't perform that action from voice in
  Alpha" **without even calling the provider**.
- **Proposal queue** (`room.ProposalQueue`): session-scoped Intent previews + Billy
  proposals with states draft · ready · applied · cancelled · **stale** · failed;
  `on_project_switch` marks project-bound proposals stale so they can never apply.
- **Glossary** (`glossary`, review-first): `suggest_transcript_corrections`
  (known misrecognitions → spoken forms → canonical-case → spoken punctuation →
  cautious fuzzy ≥0.84 off by default; whole-word, **never silent**),
  `apply_selected_corrections` (drift-guarded), `learn_correction`,
  `import_candidates` (read-only from PSYKE/characters/outline).
- **Existing view**: `VoicePanel` (~1700 lines — the entire room in one widget:
  room/status labels + live level meter + processing timer + privacy note; backend
  combo + config + "Check LAN server" + "Voice Setup…"; a **Mode combo** Dictation/
  Intent/Billy; commit row (target/PSYKE-type/character); intent + Billy rows with
  preview areas; a **proposal queue** list; a glossary section; a live transcript
  preview; a **history** list with per-segment Edit/Merge/Split/Discard/Restore/
  Retry + Undo-last-commit; transport Start/Stop/Pause + auto-commit-after-pause)
  and `VoiceSetupDialog`.

- **Studio panels & interactions:** a **Dexter's Room cockpit** (the primary
  cinematic surface) — a **listening HUD / waveform canvas** (full-width live
  waveform + RMS meter from `on_level`, a large state ring reflecting the 14-state
  machine, a segmentation timeline forming as audio buffers; dim/ambient idle,
  pulsing listening, glowing on transcript-ready); a **mode rail** (four-way
  Dictation · Intent · Ask Billy · Edit with Billy, never inferred, Billy/AI greyed
  with reason when no provider); a **context ribbon** (`context_summary_line` —
  "project · mode · Panel 2 on Page 1 · field · text selected"). A **transcript
  history canvas** (a rich segment table with status chips, confidence, duration, a
  language badge flagged when selected≠detected, a `has_audio` indicator gating
  Retry, merged/split provenance edges; inline edit / adjacent-merge / split-at-
  cursor; a "filmstrip" of segments). A **commit & proposal HUD** (a target picker
  rendering disabled-with-reason rows so the UI explains itself, mode-specific
  sub-pickers, a **preview/diff canvas** with a risk-level badge, a **proposal
  queue dock** with stale items visibly locked + their reason, an always-visible
  **Undo last commit** reflecting `can_undo`). A **glossary / correction overlay**
  (suggestions highlighted inline with source + reason on hover, per-suggestion
  accept/reject, a term manager + an "import from PSYKE/Characters/Outline" wizard).
  And a **Voice Setup & Diagnostics console** (a backend-status board with a live
  status lamp, model/executable validation, a mic meter, the performance-profile
  selector showing the concrete values it writes, a LAN panel with health-probe +
  the **private-host security explainer**, a file-based test playground, a copyable
  diagnostics summary, and strong "local-only, audio never leaves the device"
  trust messaging). *(Desktop-only feature; web Studio uses remote STT or omits
  it.)*

### 4.12 Memory architecture
(subpkg `memory_arch/` — `schema`/`candidates`/`policy`/`store`/`local_store`/
`review`/`contradictions`/`retrieval`/`github_export`; `memory_manager`,
`story_memory`, `chat_memory`)

Two layers: a **live story-memory layer** feeding the AI context window, and a
**curated memory architecture** (Phase 2–4, isolated/not yet wired into the running
Alpha) — a scoped, versioned, policy-governed memory-object store. All of it is
**deterministic and rule-based** (no model, no embeddings, no network).

- **Live story memory** (`story_memory`, `memory_manager`): `extract_scene_memory`
  / `extract_project_memory` from structured fields (goal/conflict/outcome) +
  character states → `StoryMemoryEntry` types character_state · key_event ·
  relationship · decision (dedup + min-length filter); `score_memories` (priority ×
  recency × relevance with per-level decay), `supersede_old_states`,
  `get_active_memories` (**top-20 context limit**), `format_managed_context`,
  `memory_stats` (total / high / medium / low / superseded / active_in_context).
- **Memory architecture** (`memory_arch/`): candidate extraction (deterministic,
  marker-based classification correction → release_blocker → architecture →
  deferred → workflow → project_decision → preference → speculative; unmarked chat
  never becomes memory; scope/id integrity); a **writer policy** (`evaluate` →
  `PolicyDecision`: auto_save_active · save_proposed · save_speculative ·
  require_review · ignore · reject · flag_contradiction · flag_sensitive ·
  needs_scope_confirmation; **rejects hard secrets/raw-audio** `sk-…`,
  `.wav/.mp3`, tracebacks; routes SSN/medical/salary to review; auto-saves only
  high-confidence durable types); a **store** (SQLite at
  `~/.logosforge/logosforge_memory.sqlite3`; `save_active`, `approve_candidate`,
  `search`, `update` (reason required), **`supersede` — no destructive delete,
  preserves history + links**, `find_contradictions`, `export_markdown`); a
  **review service** (`list_candidates` / approve / reject / edit / supersede /
  mark_speculative / mark_contradicted — all auditable, nothing deleted); a
  **contradiction checker** (keyword-overlap + opposing-polarity, surfaces only);
  **retrieval** (multi-scope, degrades to empty when no store); and **GitHub
  export** (markdown preview only; push disabled/opt-in). `MemoryObject` carries
  5 scopes × 20 types, `status` (active/proposed/review_required/speculative/
  rejected/deprecated/superseded/contradicted), confidence, supersede chains,
  policy_decision, risk_level, sensitive_flags.

- **Studio panels & interactions:** a **Memory workbench** (two-pane, governance-
  forward). A **live story-memory** pane (the scored-memory list with priority/
  recency/relevance bars + superseded "(past)" styling, `memory_stats` gauges
  against the 20-cap, and a "what's in the AI context window" preview). A **curated
  memory** pane (the `memory_arch` store, **currently headless — high-value Studio
  build**): a candidate **review queue** (proposed/speculative/review_required) with
  policy-decision + risk-level + sensitive-flags badges; per-object scope/type chips
  (20 types × 5 scopes); approve/reject/edit/supersede/mark-contradicted (reason
  required); a **contradiction graph** of opposing-polarity conflicts as linked
  nodes; a version/audit trail (supersede chains, never-deleted history); a
  markdown/GitHub **export preview** (push disabled, clearly opt-in); a scope×type
  matrix heatmap and a memory timeline.

### 4.13 Plugins, connectors & integrations
(subpkgs `plugins/`, `librechat/`; `plugins_view`, `librechat_view`,
`plugin_base`/`_registry`, `connector_registry`/`_actions`/`_executor`,
`cloud_storage`)

- **Plugins** (`plugin_base`, `plugin_registry`, `plugins/`): analysis plugins that
  read narrative context and emit suggestions — they receive an immutable
  `PluginContext`, **never touch the DB or mutate state**, and return a
  `PluginResult` (suggestions + summary + metadata). Built-ins:
  **DialogueTensionPlugin** (dialogue density, tension markers, flat rhythm, silent
  characters) and **CharacterPresencePlugin** (presence map, disappearance,
  clustering, under/over-representation, empty scenes). `Suggestion` carries
  `severity` info/warning/critical + a `target`.
- **Connectors** (`connector_registry`, `connector_actions`, `connector_executor`):
  the safe allow-listed read/write action surface for local AI. **17 actions** —
  reads (`get_project` / `list_scenes` / `get_scene` / `list_characters` /
  `list_psyke_entries` / `get_psyke_entry` / `list_notes` / `get_note` / `search` /
  `list_available_actions` / `get_live_context` / `get_current_selection` /
  `get_active_scene`) and writes (`create_scene` / `update_scene_title` /
  `create_psyke_entry` / `create_note`). `execute_action` enforces
  `connector_enabled` / `connector_disabled_actions` / `connector_allow_writes`,
  validates/coerces args, **never crashes** (always `{ok, error}`), and emits
  `emit_action_completed` on writes so the UI refreshes.
- **LibreChat / MCP** (`librechat/`): an optional external chat sidecar reached only
  through the **bridge / MCP** boundary. `LibreChatService` (`check_connection` →
  disabled / invalid_url / connected / unreachable; optional localhost-only
  process start/stop); a **bridge** (read context, **propose** writes →
  `ActionProposal`, `apply_confirmed_action(confirmed=True)` still gated by connector
  write settings); an **MCP server** exposing **13 tools** 1:1 with bridge ops over
  the FastAPI connector layer.
- **Cloud-safe storage** (`cloud_storage`) — provider-neutral safe primitives (no
  OAuth/provider APIs); see §4.10.
- **Existing views**: `PluginsView` (left plugin list `name [loaded/disabled/error]`
  + Refresh + Plugin Docs; right detail pane name/version/author/description/path +
  status + an Enabled checkbox "changes take effect on next launch" + a Logs area)
  and `LibreChatView` (status label + chip buttons Open/Retry/Open-in-browser/
  Settings; a `QStackedWidget` switching a message panel and an embedded
  `QWebEngineView` when connected + prefer-embedded + WebEngine available, else
  system-browser fallback).

- **Studio panels & interactions:** a **Plugins gallery** (a card grid grouped by
  category, each card with description / requires-scene / an enable toggle
  "effective next launch" / a last-run summary / a results panel rendering
  `Suggestion`s with severity color-coding + click-to-target, plus a "run all"
  overview). A **Connector & integrations control room** — a connector **action
  catalog** table (the 17 actions with read/write category badges + param schemas)
  gated by master switches (enabled / allow-writes / per-action disable list) as a
  **permissions dashboard**; an action-proposal inspector (propose → confirm →
  apply, with the write-settings gate shown); a **LibreChat dock** (embedded
  `QWebEngineView` when reachable, with a connection-state banner + retry + open-in-
  browser + optional localhost launch/stop, plus an MCP-tools panel listing the 13
  tools); and a **cloud-storage status strip** (detected provider for the project
  path, lock state "may be open on <device>", external-change/conflict indicator) —
  ambient systems telemetry a Studio line should expose densely. Every mutating
  surface must visibly carry the core's preview → confirm → apply → undo guarantees.

### 4.14 Import / Export
(`export`, `data_export`, `import_data`, `export_data_dialog`, the per-mode
exporters; plus `writing_modes`, `writing_formats`, `narrative_engines/`,
`project_compat`)

Two distinct exporters plus a JSON importer that round-trips full projects.

- **Manuscript export** (`export`, format-aware via `_get_fmt`): `export_json`,
  `export_markdown` / `export_outline_markdown`, `export_csv_scenes`, formatted
  text (`export_manuscript` novel / `export_screenplay` + per-format `_fmt_*`),
  **DOCX** (`export_docx_manuscript` — Times for prose, Courier for scripts, title
  page + page breaks, industry margins), **PDF** (`export_pdf`, reportlab), **HTML**
  (format-aware CSS), **FDX**, and the **Fountain pipeline** (`export_fountain` /
  `export_screenplay_fountain_result` with warnings / `export_production_fountain`
  with scene numbers `#N#` + OMITTED). A **professional-output layer**
  (`export_screenplay_docx` / `_fdx_experimental` / `_pdf` returning
  `estimated_pages`; `export_professional_preview_html` with dark-mode). Plus
  **diagnostic/validation JSON exports** (diagnostics / setup-payoff / subtext /
  graph / story-links / fountain-validation / export-validation / output-validation
  — all read-only, stamping `writing_mode` / `exported_at` / `schema_version`).
- **Structured-data export** (`data_export`, separate from manuscript): an
  `ExportOptions` dataclass (9 section toggles — project_metadata / outline / plot /
  timeline / scenes / psyke_entries / psyke_relations / psyke_progressions / notes —
  + 3 field toggles include_ids / include_internal_metadata / summaries_only +
  `export_type` + `fmt` json/markdown/csv); presets `story_elements_options` /
  `psyke_data_options`; builders `build_story_elements` / `build_psyke_data` /
  `build_full_export` (import-compatible round-trip); serializers `to_json` /
  `to_markdown` / `to_csv_files` (a multi-file map); `write_export` (single file or
  sibling `_csv` folder). `SCHEMA_VERSION=1`.
- **Import** (`import_data`): `validate_import_data(raw)` requires
  `{project, characters, places, notes, scenes}`; `import_json` rebuilds the entire
  project (project + characters/places mirrored as PSYKE entries + notes + scenes in
  order with character/place name→id resolution + character_states + all screenplay
  fields + PSYKE entries/relations/progressions + outline tree + quantum_state +
  continuity items + chapters + timeline lanes/links). Tolerant of legacy/partial
  JSON.
- **Existing surfaces**: `ExportDataDialog` (a 2-column grid of the 9 section
  checkboxes + a format combo + 3 option checkboxes; locked-on sections in
  full-project mode; returns `ExportOptions` + format) and the `main_window` wiring
  (a sidebar **Export** button + **File ▸ Export** submenu Manuscript / Story
  Elements / PSYKE Data / Full Project, a `QFileDialog` with 9 filters dispatching
  to the matching `export_*`; import via `validate_import_data` → `import_json`;
  graceful reportlab/python-docx failure).

- **Studio panels & interactions:** an **Export Studio** (full-screen modal or
  dock) unifying the two exporters — a left rail target picker grouped **Manuscript**
  (PDF/DOCX/TXT/Fountain/FDX/HTML, mode-labelled) and **Data** (JSON/Markdown/CSV via
  `ExportOptions`); a center **live preview** (reuse `export_professional_preview_html`
  / `export_screenplay_preview_html` for scripts, rendered Markdown for data); a
  right controls pane (the 9 sections + 3 field toggles, locked-on in full-project
  mode); and a **validation strip** driven by the `*_validation_json` exporters
  showing pass/warn rows *before* export — a high-value "pre-flight" panel. Expose
  `export_production_fountain` (scene numbers + OMITTED) as a production toggle and
  `estimated_pages` as a live page-count HUD. Plus an **import preview canvas** —
  run `validate_import_data` and render a diff/preview tree of what will be created
  (counts of scenes/characters/places/PSYKE/outline/timeline/chapters), flagging
  legacy JSONs missing screenplay fields and warning if the detected mode/format
  differs from the current project.

### 4.15 Cross-cutting: Workspace, Projects, Search, Settings, Welcome
(`main_window`, `projects_view`, `dashboard_view`, `welcome_view`,
`new_project_dialog`, `project_settings_dialog`, `settings_dialog`, `search_view`,
`recent_projects`, `settings`, `preferences`, `project_lifecycle`,
`db.search_project`)

- **Project lifecycle** (`MainWindow`): **create** (`_do_new_project` →
  `NewProjectDialog` collecting title + narrative engine + default writing format +
  writing language; `db.create_project`; lands on Dashboard); **open from file**
  (`_open_file` → JSON read, `validate_import_data`, lock check, **de-dupe via
  `db.get_project_by_source_path`** to re-activate rather than duplicate, else
  `import_json` + `set_project_source_path`); **open quietly on launch**
  (`load_file_quiet`, sets `_read_only` from foreign lock state); **save / save-as**
  (`atomic_write_text`, lock release/acquire, recent + storage indicator update);
  **move to folder** (`recent_projects.rename`, leaves the original for cloud sync);
  **open project folder**; **Project Settings** (re-enters the project so views
  rebuild against the new engine/format); and the canonical **switch** pipeline
  (described in §3).
- **Recent projects** (`recent_projects`): `add / remove / clean` (drops missing
  files) / `load_with_status` (path, exists) / `rename`; capped `MAX_RECENT=10`;
  stored `~/.logosforge/recent_projects.json`; surfaced in File→Recent + the
  Projects view.
- **Settings** (`settings`, global `~/.logosforge/settings.json`, **~120 keys**):
  a singleton `SettingsManager` (auto-saves on change) surfaced by `SettingsDialog`
  (Appearance Dark/Light-Green/Light-Warm; default writing language; AI Provider via
  `ProviderSettingsWidget` with per-provider memory; **Connector** enable/allow-
  writes/confirm-writes + per-action list; **LibreChat** enable/base-URL/local-
  remote/auto-connect/prefer-embedded/browser-fallback/startup-command/Test;
  **Project Storage** default folder + detected-cloud combo). Many keys are feature
  flags (`logos_enabled`, `logos_proactive_enabled`, `logos_confidence_threshold`,
  `health_enabled`, `strategy_enabled`, voice/Dexter config, `api_embedded_enabled/
  _port`, and ~15 `include_*_in_assistant_context` toggles + `max_*_in_context`
  caps controlling prompt assembly). **Preferences** (`preferences`, separate
  lightweight bool/string flags — `has_seen_onboarding`, `has_seen_timeline_hint`,
  `appearance`).
- **Search** (`search_view`, `db.search_project`): case-insensitive substring across
  **Character / Place / Note / Scene / PSYKE** → `{type, id, label, preview,
  [chapter, plotline, tags]}`. View filters: entity-type checkboxes (Character/Place/
  Note/Scene — **PSYKE is absent from the view's `ENTITY_TYPES` though the DB returns
  it**), scene-only Chapter/Plotline/Tag dropdowns, a "N of M results" status line,
  double-click to navigate. Related DB ops: `resolve_link`, `find_backlinks`
  (`[[name]]` wikilinks), `build_link_graph`.
- **Writing-language coordination**: per-project `writing_language_code` (set on
  create / in Project Settings) flows to AI writing context + Dexter transcription
  defaults — **explicitly never rewrites or translates text** (settings-only);
  `_sync_project_language_context()` re-resolves on every switch so project A's
  language can't leak into B.
- **Existing views**: `WelcomeView` (first-launch single-CTA, shown only when no
  scenes + `!has_seen_onboarding`); `ProjectsView` (Create/Open/Save-As/Refresh +
  Recent cards with name, shortened `~/…` path, "Modified <date>", Open + Remove +
  an empty state); `DashboardView` (title + "Last edited", engine·format +
  Structure chip, progress stat blocks, a "Continue writing" hero card, an optional
  Timeline hint, Quick actions, Stats — self-subscribing to the event bus);
  `NewProjectDialog` (engine combo auto-syncs default format via
  `default_format_for_engine`); `ProjectSettingsDialog` (narrative engine **LOCKED
  once content exists** via `can_change_writing_mode` + `MODE_LOCK_MESSAGE`, default
  format, writing language with "does not translate" hint); `SettingsDialog`
  (scrollable, sticky Close, screen-height-clamped ~85%); `SearchView`;
  `CommandPalette`.

- **Studio panels & interactions:** a **Project Hub / Launchpad canvas** (replaces
  `ProjectsView` + `DashboardView` + `WelcomeView`) — a full-bleed cinematic grid of
  project cards from `recent_projects.load_with_status()` + per-card
  `compute_project_stats` mini-sparklines (scene count, total words, longest/
  shortest); each card shows title, engine·format + structure chip, a
  `classify_path` **storage provider badge** (Dropbox/Drive/OneDrive/iCloud/Local +
  read-only state), last-modified, and the lock-holder if foreign; hover reveals
  Open / Save-As / Move / Open-folder / Version-history; switchable grid/list/
  timeline density; greyed "missing file" cards. A **persistent command bar /
  palette HUD** and a **faceted Global Search panel** (replace the basic
  `SearchView` with a dockable live-search faceted by type — **including PSYKE** —
  + scene Chapter/Plotline/Tag/Beat facets, type-ahead, grouped headers, match
  highlighting, jump-on-hover/open-on-enter, plus backlinks (`find_backlinks`) and
  link-graph (`build_link_graph`) tabs so search is also a navigation graph). A
  **Settings-as-dockable-searchable-workspace** (a left-rail categorized, searchable
  canvas — Appearance, AI Provider + provider-memory cards, **Connector action
  matrix**, Voice/Dexter, LibreChat, Embedded API, an **Assistant-context toggle
  board** surfacing the ~15 `include_*_in_assistant_context` flags as a visual "what
  the AI sees" board with live token-budget hints from `max_*_in_context`, Storage).
  And **Project Settings inline** (a dockable identity panel that visibly reflects
  the **mode-lock** state and shows the cascade — "changing engine affects
  Assistant, PSYKE, graph, plot, review" — with a cinematic confirm flow instead of
  a `QMessageBox`).

---

## 5. AI / assistant interaction model (summary)

Design four distinct but coherent AI presences over **one shared backend** (a
single configured provider; no persona owns its own provider system):
1. **Billy** (dock + full chat + inline) — conversational, project-aware,
   generative; preset actions + selectable context source + Copy/Replace/Insert/
   Append/Apply-to-Outline.
2. **Logos** (inline bar, command palette, action menus) — ~120 fast contextual
   actions, **deterministic where possible** (rule-based, no LLM), confirm-before-
   apply for edits; plus the proactive-suggestion stream + narrative-health +
   strategy-router.
3. **Counterpart** (panel) — reflective two-stance feedback (5 dialogic modes),
   **never edits** (apply disabled by contract).
4. **Quantum Outliner** (branching canvas / Quantum Timeline) — generate 3–5
   scored branches, compare, **collapse** (writes PSYKE deltas, adapts scoring
   weights, archives the rest).

All edits funnel through **preview → diff → confirm** (Controlled Apply: a STAGE
checkpoint, blocking/error/warning conflicts, force override, history log). Context
is assembled under an explicit, capped, **conservative-by-default** policy (the ~18
context blocks are individually toggleable; health is off by default; project-switch
never leaks), and every response is checked by an **output validation contract**
(planning-leak → Apply disabled; secret/audio-leak → response withheld). The **Mode
Strip** + **Decision Radar** keep the AI's "state of mind" and "what to do next"
always legible. **No silent AI** — every generative action is user-invoked, response
caching aside.

---

## 6. The five format engines — workspace re-skin

The active **writing mode** (= `Project.narrative_engine`, **not a separate column**)
changes vocabulary, the scene-body editor, the structure labels, the pipeline, and
which review dashboard/export is offered. It is intentionally a **one-way lock**:
`change_writing_mode` is guarded by `can_change_writing_mode` (returns True only on an
empty scaffold — `project_has_meaningful_content` scans scenes / planning stores /
timeline / notes / PSYKE / seasons-episodes), surfacing `MODE_LOCK_MESSAGE`;
conversion between modes is intentionally NOT implemented. Each mode cascades through
three orthogonal layers — a **NarrativeEngine** (how the story is *reasoned about*:
structural units, plot-block unit, timeline semantics, assistant priorities, PSYKE
rules, review checks, feedback patterns, system-prompt overlay), a **WritingFormat**
(how the manuscript is *rendered*: per-element `ElementStyle` typography — font_size,
caps, align, px margins calibrated to a 720 px column, color/background band keys),
and the **Adaptive AI Mode**. Design one parametric workspace, themed per mode:

| Mode | Structure spine | Scene body | Signature surfaces |
|---|---|---|---|
| **Novel** | Act → Chapter → Scene | prose | chapter rhythm, story grid |
| **Screenplay** | Act → Sequence → Scene (+ Beat) | screenplay elements (8-element taxonomy) | beat-plan studio, subtext & setup/payoff trackers, story-link graph, production drafts, Fountain/FDX |
| **Graphic Novel** | Act → Page → Scene → Panel | page/panel script (2 models) | Page Canvas/preview, panel inspector, image-prompt export (ComfyUI stubbed) |
| **Stage Script** | Act → Scene → Beat (+ Stage Directions) | performable dialogue + blocking (13 blocks) | blocking/cue board, theatrical review |
| **Series** | Season → Episode → Act → Chapter → Scene | teleplay blocks + serial markers | Series Navigator, showrunner board, A/B/C swim-lanes, cross-episode continuity |

Each mode shares the same panel *patterns* (pipeline confirm, mode review dashboard,
controlled rewrite diff, export) — only the content + theme change. The richest
under-exposed data here is per-engine **`feedback_patterns` + `review_checks`** (a
built-in mode-specific lint engine with zero current UI), the screenplay diagnostic
JSON family (graph/subtext/setup-payoff — natural canvases/heat-maps), and the
`ElementStyle` color/background-band system (the visual DNA for a cinematic, syntax-
highlighted script editor). Surface an **Engine Profile Inspector** that exposes the
full NarrativeEngine (structural-units ladder, assistant-priority chips, PSYKE rules,
review checks as a live lint checklist, feedback patterns as warning rows, the raw
`system_prompt_overlay` in a "How the AI reasons in this mode" reveal) — read-only,
perfect for a Studio "advanced" docker.

---

## 7. Design-language guidance for Claude Design

- **Identity:** dark-first, cinematic, "minimal-cyber / terminal" — precise,
  dense, composed. Distinct from Whiteboard's calm minimalism. Free to be
  dramatic (HUD overlays, graph canvases, branching timelines).
- **Layout:** a dockable, tile-able workspace with savable per-project layouts
  (mirror the core's `graph_state` / `graph_presets` persistence pattern);
  Focus ↔ Cockpit modes. Center editor, right intelligence dock, bottom analysis
  dock, left navigator rail.
- **Density done right:** lots of live signal (energy heatlines, health HUD,
  decision cards, graph) but quiet by default — proactive insight lives in thin,
  dismissible banners and dockable HUD widgets, never modal nags. The core's
  workers are **debounced, cancelable, generation-counted, and cached**, so panels
  stay live without blocking typing — consume that worker model, don't fight it.
- **One severity/confidence grammar everywhere:** a severity chip
  (blocking → error/warning → suggestion → opportunity → info) + a confidence
  dot/badge, reused across Decision Radar, Continuity, Health, Logos suggestions,
  graph edges, and screenplay diagnostics. Carry the core's color tokens
  (`level_color` `#4ade80`/`#f59e0b`/`#ef4444`, `insight_color`, `tension_color`
  green→red, the Irrational purple `#a855f7`) as the Studio palette.
- **Signature surfaces to make beautiful:** the **Canvas Plot** board, the
  **Knowledge Graph** (gravity-sized, flow-overlaid, confidence-aware), the
  **Quantum Timeline / Field** (superposed probability-weighted branches), the
  **Decision Radar**, the **Tension/Story-Pulse** ribbon, the **PSYKE relation
  graph + temporal scrubber**, the **GN Page Canvas**, and **Dexter's Room** voice
  HUD.
- **Two omni-inputs:** Command Palette (`/` → Cmd/Ctrl+K omnibox) and PSYKE Console
  (omnibox) — make Studio keyboard-first and fast; render the command validator's
  CONFIRM step as an inline affordance, never a blocking modal.
- **Confirm-before-apply** is a core interaction primitive — design one excellent
  **diff + conflict + impact** modal (Controlled Apply) reused everywhere content
  changes, with a visible checkpoint/safety affordance and an Apply History log.
  Make non-destructiveness legible (restore → new project; open → de-dupe;
  supersede → never delete).
- **Mode-aware:** the whole shell re-skins per writing mode (a one-way lock with a
  cinematic "this would reinterpret your manuscript" warning); design the
  parametric system, not five apps.
- **Trust as a visual:** "advisory only", "deterministic · no AI · rebuilt live",
  "audio/secrets stay local", provenance + "User-confirmed" badges — the core's
  safety posture is a feature; surface it.

---

## 8. Suggested top-level navigation (designer's starting point)

`Dashboard · Write (Manuscript) · Structure · Scenes · Plot/Timeline · PSYKE ·
Graph · Quantum · Stages · Reviews (mode) · Notes · Search · Voice · Plugins ·
Settings` — with the **Assistant**, **Decision Radar**, **Continuity**, and
**Story Health** docks available from any section, the **Mode Strip** + **Save/Sync
status HUD** always visible, and the Command Palette / PSYKE Console always one
keystroke away.

> Build the brief into screens in Claude Design, then we recode the approved
> design in Claude Code as `pro-shared-ui` (consumed by pro-desktop + pro-web),
> wiring each panel to the existing `logosforge.api`.
