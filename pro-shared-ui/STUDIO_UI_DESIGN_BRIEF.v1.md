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

**Tone / identity:** dark-first, cinematic, "minimal-cyber / terminal" (the
core's own icon language). Three palettes exist in the core — **Dark** (primary),
**Light (Green)**, **Light (Warm)**. High information density, but composed:
every panel earns its space.

---

## 2. Information architecture & the workspace

Studio is a **single project workspace** with a dockable layout. Suggested
regions (a designer should explore docking/tiling, but this is the model):

- **Left rail — Navigator.** Icon rail + collapsible tree to switch *sections*:
  Dashboard, Manuscript, Structure/Outline, Scenes, Timeline/Plot, PSYKE,
  Graph, Stages (versions), Notes, Search, Reviews (mode dashboards), Plugins,
  Settings. (Maps to `main_window` sidebar + `sidebar_icons`.)
- **Center — the active editor** (manuscript / scene / outline / canvas),
  re-skinned by the active **writing mode** (see §6).
- **Right dock — intelligence panels** (tabbed/stacked, user-arrangeable):
  Assistant (Billy), PSYKE inspector, Story Health, Pacing, Decision Radar,
  Knowledge Graph focus, Continuity.
- **Bottom dock — analysis & timeline strips**: Plot-lane Timeline, Beat/Act
  analysis, Tag analysis, Voice dictation transcript.
- **Two omni-surfaces, always available:**
  - **Command Palette** — a `/`-triggered popup of writing actions
    (`command_palette`).
  - **PSYKE Console** — an omnibox with live search + commands (`/create`,
    `/open`, `/go`, `/ai`, …), keyboard-driven (`psyke_console`).
- **Mode Strip** — a compact, always-visible indicator of the current adaptive
  AI mode, with manual override (`mode_strip`, `mode_suggestions_view`).
- **Context Hint / Suggestion banners** — thin, non-intrusive strips above the
  editor for proactive (but dismissible) suggestions
  (`context_hint_banner`, `suggestion_banner`).

The workspace must support **focus** (collapse all panels to just the editor)
and **cockpit** (everything visible) layouts, and remember per-project layout.

---

## 3. Global data model (what panels render)

All entities are project-scoped (one SQLite DB per project, via the API).

- **Project** — `title`, `narrative_engine` (= writing mode: novel · screenplay ·
  graphic_novel · stage_script · series), `default_writing_format`, settings.
- **Structure (canonical):** **Act → Chapter → Scene** is the single ordered
  spine (`story_structure`). Each format re-labels it (see §6).
- **Scene** — title, act/chapter, **body** (format-specific blocks), summary,
  tags, plotline, order, per-mode coordinates (e.g. graphic-novel page offset).
- **PSYKE entry** (story bible) — `name`, `type`
  (character · place · object · lore · theme · other), `aliases`, `notes`,
  `details` (per-type schema), `is_global`; plus **relations** (typed edges
  between entries), **progressions** (state of an entry across scenes/time),
  and **scene references** (where an entry appears).
- **Plotlines / plot lanes**, **Timeline** (story-order vs chapter-order),
  **Notes**, **Tags**, **Beats**.
- **Stages / Versions** — narrative versioning + **branching** (capture,
  restore, diff) and timestamped JSON snapshots.
- **Knowledge-Graph nodes & edges** — derived (typed, confidence-scored,
  provenanced) from PSYKE, structure, notes, revisions, workflows.
- **Memory objects** — extracted continuity facts, candidates, review state.
- **Workflow state** — `WorkflowRun` / `WorkflowStepState` / `WorkflowEvent`.

> The UI reads these via `logosforge.api` (projects, scenes, outline, plot,
> timeline, psyke, notes, assistant, connector, export, events). A live
> **event bus** (`/events`) pushes change notifications for reactive panels.

---

## 4. Feature design specs

Each section: **what it is → what the user does → panels & interactions** for
Studio. Module/view names in `code` are the authoritative source.

### 4.1 Manuscript writing core
*The continuous prose/scene editor* (`writing_core_view`, `scenes_view`,
`chapters_view`, `story_grid_view`, `manuscript_highlighter`, `format_toolbar`).
- Continuous manuscript editor with Markdown-like live styling; a floating
  **format toolbar** on selection.
- **PSYKE-aware editing:** `[[Entity]]` links render as clickable chips
  (`link_preview`), a **PSYKE highlighter** + Ctrl+Click jump
  (`psyke_highlighter`), and an **entity hover** card (`entity_hover`) showing
  bible data inline.
- **Inline AI:** an embedded **inline assistant** (`inline_assistant`) and a
  selection-based **inline edit bar** (`inline_edit_bar`) for quick rewrites.
- **Editing intelligence (live, non-blocking):** grammar/spell
  (`grammar_checker`), style analysis (`style_analysis`), **paragraph energy**
  (tension/pacing/conflict/emotional-shift heat, `paragraph_energy`), dialogue
  speaker attribution (`dialogue_attribution`), **voice consistency** flags
  (`voice_consistency`).
- **Panels:** the editor canvas; a right-dock "writing intelligence" panel with
  energy heatline, style/grammar flags, dialogue attribution; the inline bar +
  hover cards as floating overlays. **Story Grid** = a 3-column block grid
  grouped by Acts for a bird's-eye manuscript view (`story_grid_view`).

### 4.2 Outline & story structure
(`outline_view`, `plan_view`, `structure_view`, `chapter_outline_view`,
`outline_templates`, `outline_actions`, `structural_intelligence`, `story_structure`)
- Edit the **Act → Chapter → Scene** hierarchy; **plan view** = hierarchical
  outline; **structure view** = the spine; **template presets** for common
  story structures; AI outline generation with a **confirm-before-apply** dialog
  (`outline_ai`, `outline_confirm_dialog`).
- **Structural Intelligence** = PSYKE-driven analysis of the structure.
- **Panels:** a tree/board outline editor, a template picker, a generated-outline
  diff/confirm modal, a structure-health sidebar.

### 4.3 Timeline & plot
(`timeline_view`, `plot_timeline_view`, `canvas_plot_view`, `multi_plot_view`,
`story_flow`)
- **Plot-lane Timeline** — horizontal, scrollable lanes per plotline
  (`plot_timeline_view`); **Timeline** — plotline-column or chapter-column
  overview with light editing.
- **Canvas Plot** — a free, zoomable, pannable **visual plotting board**
  (`canvas_plot_view`) — a signature Studio surface (cinematic, spatial).
- **Multi-View Plotting** — switch story *perspectives* dynamically
  (`multi_plot_view`).
- **Story Flow** layer — tension/pacing/scene-type overlay you can paint onto
  lanes (`story_flow`).
- **Panels:** a bottom-dock timeline strip + a full-screen canvas board; lane
  drag/zoom/pan; overlay toggles (tension/pacing/POV).

### 4.4 PSYKE — the story bible
(`psyke_view`, `psyke_console`, `characters_view`, `places_view`,
`character_arc_view`, `character_balance_view`, `psyke_quick_create`,
`psyke_search`, `psyke_commands`/`_intents`/`_intent_llm`/`_suggestions`/
`_system_commands`, `temporal_psyke`, `auto_link`, `controlling_idea`,
`models/psyke_details`)
- Central **Story Bible**: list with search/filter, an entry editor, **relations**,
  **progressions**, and **scene references** (`psyke_view`).
- **PSYKE Console** — omnibox: live fuzzy search dropdown + natural-language
  commands (rule-based intents with an **LLM fallback**), system commands
  (`/create`, `/open`, `/go`, `/ai`), context-aware suggestions.
- **Character Arc** — ordered states of a character across scenes; **Character &
  Arc Balance** — distribution/presence visualization.
- **Temporal PSYKE** — time-aware reasoning over entries; **Auto-Link** —
  suggests links between manuscript text and bible entries; **Controlling Idea**
  — a McKee-style thematic compass.
- **Per-mode memory layers:** `psyke_visual` (graphic novel), `psyke_theatre`
  (stage), `psyke_series` (series long-form memory).
- **Panels:** a full Bible browser; a docked **PSYKE inspector** (current entry +
  relations graph + progression timeline); the omnibox console; quick-create
  modal; arc/balance charts. This is one of Studio's richest surfaces — design
  for relations graphs and progression timelines.

### 4.5 The five format engines
Each writing mode is a *complete pipeline*. The workspace **re-skins** per mode
(§6). Every engine has the same shape — adapt the same panels:
- **Structure** (per-mode hierarchy), **Blocks** (per-mode scene-body model),
  **Planning Pipeline** (confirm-before-apply scene planning), **Diagnostics**
  (deterministic scene intelligence), **Reflection** (a Counterpart/Logos
  two-stance mirror), **Continuity** (multi-scene coherence), **Controlled
  Rewrite** (preview/diff/confirmed-apply), **Review Dashboard** (project status),
  **Export**.
- **Novel** — prose; Acts/Chapters/Scenes; chapter-rhythm focus.
- **Screenplay** — `screenplay*` (element taxonomy, Fountain/FDX/DOCX/HTML
  export, **subtext** + **setup/payoff** trackers, scene-economy diagnostics,
  **production drafts**, story-link graph, professional output styles +
  validation). Dialogs: `screenplay_review_view`, `_rewrite_dialog`,
  `_import_dialog`, `_pipeline_dialogs`.
- **Graphic Novel** — `graphic_novel*` canonical **Act → Page → Scene → Panel**;
  **Page & Panel** management + a **Page Canvas/Preview** (`graphic_novel_pages_view`,
  `_page_canvas`, `_scene_pages_view`); AI/ComfyUI **image-prompt export**.
- **Stage Script** — `stage_script*` theatrical structure, blocking, performable
  dialogue; `stage_script_review_view`.
- **Series / Teleplay** — `series*` corrected **Season → Episode → Act → Chapter
  → Scene**; **Series Navigator** (`series_navigator_view`); cross-episode
  continuity + long-form series memory.
- **Panels:** each mode gets its **Review Dashboard** (status aggregation), its
  pipeline confirm dialogs, its rewrite diff modal, its export dialog. Design one
  adaptable "Mode Review" dashboard + one "Pipeline confirm" pattern, themed per
  mode.

### 4.6 Assistant & AI surfaces
(`assistant_view`, `assistant_dock`, `chat_view`, `inline_assistant`,
`inline_edit_bar`, `assistant`, `assistant_context_policy`, `assistant_contract`,
`context_builder`, `providers`, `provider_settings`, subpkgs `logos/`,
`assistant_arch/`, `quantum_outliner/`, `counterpart`, `creative_layer`,
`irrational`)
- **Billy** — the writing assistant: a docked side panel (`assistant_dock`/
  `assistant_view`), a full **Project Chat** (project-aware long-form,
  `chat_view`), and inline forms in the editor. Context is assembled from the
  project under a **controlled context policy** (what's injected is explicit).
- **Logos** — the *inline / contextual* AI layer: a registry of actions
  (rewrite, expand, explain, connect-to-PSYKE, …) with **deterministic handlers**
  where possible and a **controlled-apply** path; also exposes the Project OS
  (Active/Recommend Workflows, Explain Step). Surfaces: inline edit bar, command
  palette, action menus.
- **Counterpart** — a **dialogic** assistant giving reflective two-stance
  feedback (not edits). A distinct conversational panel.
- **Quantum Outliner** — a signature Studio feature: generate **3–5 plausible
  narrative branches** from a point, score them, view them as a **Quantum
  Timeline** (canon + active branches in parallel, `quantum_timeline`), reframe
  a scene from another POV (relativity), find weak/predictable scenes
  (uncertainty), then **collapse** to one branch (archive the rest, update
  PSYKE). Design a branching/superposition canvas — cinematic, high-impact.
- **Adaptive Mode** — AI behaviour adapts to story state; the **Mode Strip**
  shows/overrides it.
- **Provider settings** — local (LM Studio/Ollama) on desktop, remote (OpenAI/
  Anthropic/OpenRouter) on web; configured via `provider_settings` /
  `settings_dialog`.

### 4.7 Narrative intelligence & analytics
(`narrative_dashboard_view`+`narrative_dashboard`, `story_health_view`+
`story_health`, `pacing_insights_view`+`pacing_insights`, `beat_analysis_view`,
`act_analysis_view`, `tag_analysis_view`, `character_arc_view`,
`character_balance_view`, `analytics`, `dashboard_widgets`)
- **Narrative Dashboard** — visual story intelligence at a glance (tension,
  presence, structure) with custom-painted widgets.
- **Story Health** — high-level status indicators (a compact HUD panel).
- **Pacing Insights** — subtle rhythm analysis; **Beat / Act / Tag analysis** —
  coverage and distribution views; **Character Balance** — presence distribution.
- **Panels:** a rich Dashboard "home" + small dockable HUD widgets (health,
  pacing) that live alongside the editor. Heavy charting opportunity.

### 4.8 Knowledge Graph
(`graph_view`, `focus_graph_view`, `graph_analysis`/`_flow`/`_gravity`/`_meaning`/
`_suggestions`, subpkg `knowledge_graph/`)
- **Relationship graph** of `[[link]]` connections (`graph_view`) and a
  controlled **Graph Focus** explorer (`focus_graph_view`).
- The **Narrative Knowledge Graph** (`knowledge_graph/`) builds a typed,
  provenanced graph from PSYKE/structure/notes/revisions/workflows, with
  **Story Gravity** (importance weights), **Meaning** (insight from structure),
  **Flow** (story-order overlay), and graph-driven **Suggestions** + **Decision
  cards**. Scoring surfaces orphans, centrality, weak links.
- **Panels:** an interactive force/graph canvas with focus mode, gravity-sized
  nodes, flow overlay, and a side list of orphans/weak-links → actionable cards.
  Another signature cinematic surface.

### 4.9 The Project OS layer (Understand → Decide → Act → Verify → Apply)
(subpkgs `project_intelligence/`, `guided_workflows/`, `controlled_apply/`,
`rewrite_sandbox/`, `revision_intelligence/`, `continuity/`; docs:
ProjectOperatingSystem, DecisionRadar, GuidedWorkflows, ControlledApply)
- **Project Intelligence** — one read-only aggregation of mode/structure/PSYKE/
  workflow/export-readiness/health.
- **Decision Radar** — ranked, deterministic, traceable **decision cards**
  (blocking → warning → suggestion → opportunity → info). A primary Studio HUD.
- **Guided Workflows** — turn decisions into resumable, mode-aware, step-by-step
  paths (templates A–H); deterministic **completion checks** tick verifiable
  steps; creative steps stay the user's.
- **Controlled Apply / Rewrite Sandbox / Revision Intelligence** — the **only**
  paths to content mutation: preview → **diff** → confirmed apply, with a
  **Change Impact Map** (scene dependencies, setup/payoff, PSYKE & continuity
  impact) shown before applying.
- **Semantic Continuity Engine** (`continuity/`) — extracts facts, detects
  contradictions / structural breaks / missing transitions, scores most-affected
  scenes, and feeds Decision Radar cards.
- **Panels:** a **Decision Radar** dock (ranked cards with severity color); a
  **Guided Workflow** stepper panel; a universal **diff/impact confirm** modal
  (used by every rewrite path); a Continuity issues panel. This loop is the
  spine of Studio — make it the calm cockpit, not a notification spam.

### 4.10 Stages — versioning & branching
(`stages_view`, `stages`, `version_history_dialog`, `version_manager`)
- **Stages** — capture/restore/diff narrative versions **and branch** them
  (central panel). **Version History** — browse/restore/delete timestamped
  snapshots.
- **Panels:** a branch/version timeline (git-graph-like, but story-framed) with
  restore/diff; a snapshot list dialog.

### 4.11 Voice — Dexter's Room
(subpkg `voice/`, `voice_panel`, `voice_setup_dialog`, `voice_glossary_dialog`)
- Local-first **dictation**: a docked panel + a floating Voice Dictation window;
  near-live buffered transcription (recorder → audio buffer → silence detection
  → transcriber), local GPU Whisper or LAN Whisper backends.
- **Preview-first commit:** transcripts route through a **commit router** +
  **intent router** (mode-aware, confirm-before-apply edit targets) and a
  **Billy voice bridge** (voice → Billy proposal → confirmed apply).
- **Glossary** — per-project correction layer; **History** — session transcript
  review; **Setup** — backend profiles + diagnostics.
- **Panels:** a dictation HUD (waveform/level, live transcript, intent preview,
  commit target), a setup/diagnostics dialog, a glossary manager.
- *(Desktop-only feature; web Studio uses remote STT or omits it.)*

### 4.12 Memory architecture
(subpkg `memory_arch/`, `memory_manager`, `memory_context`, `story_memory`,
`chat_memory`)
- Story memory extraction (continuity facts from scenes) with priority/decay/
  dedup; a human-in-the-loop **candidate review** workflow (extract → classify →
  propose → review). Local-first SQLite store.
- **Panels:** a memory review queue (accept/reject candidates), a memory inspector
  showing what context is fed to the AI.

### 4.13 Plugins, connectors & integrations
(subpkgs `plugins/`, `librechat/`; `plugins_view`, `librechat_view`,
`plugin_manager`/`_executor`/`_registry`/`_base`, `connector_actions`/`_executor`/
`_registry`, `gomckee_bridge`, `cloud_storage`)
- **Plugins** — discover/enable/disable PSYKE-aware plugins (e.g. Character
  Presence, Dialogue Tension); a plugin browser with details.
- **Connectors** — safe app actions exposed to local AI (validated executor +
  registry). **LibreChat / MCP** — an optional bridge + MCP server exposing
  LogosForge to external chat clients (`librechat_view`).
- **Cloud-safe storage** primitives (provider-neutral).
- **Panels:** plugins manager; an integrations/connectors settings area; a
  LibreChat workspace panel.

### 4.14 Import / Export
(`export`, `data_export`, `import_data`, `export_data_dialog`, the per-mode
exporters)
- Export to **JSON · Markdown · CSV · DOCX · Fountain · PDF · HTML · FDX**;
  structured data export; import from the app's JSON format; screenplay Fountain
  import; graphic-novel image-prompt export.
- **Panels:** an export dialog (format + scope + style profile), an import preview.

### 4.15 Cross-cutting: Projects, Search, Settings, Welcome
- **Projects** browser (`projects_view`) + **New Project** (mode + format)
  (`new_project_dialog`); **Dashboard** home (`dashboard_view`); **Welcome**
  first-launch (`welcome_view`).
- **Global Search** across all project entities with filtering (`search_view`).
- **Settings** — appearance (3 palettes) + AI provider (`settings_dialog`),
  per-project settings (`project_settings_dialog`).

---

## 5. AI / assistant interaction model (summary)

Design four distinct but coherent AI presences:
1. **Billy** (dock + full chat + inline) — conversational help, project-aware.
2. **Logos** (inline bar, command palette, action menus) — fast contextual
   actions, deterministic where possible, confirm-before-apply for edits.
3. **Counterpart** (panel) — reflective, two-stance feedback (never edits).
4. **Quantum Outliner** (branching canvas / Quantum Timeline) — generate, score,
   compare, collapse narrative branches.
All edits funnel through **preview → diff → confirm** (Controlled Apply). The
**Mode Strip** + **Decision Radar** keep the AI's "state of mind" and "what to do
next" always legible. **No silent AI** — every generative action is user-invoked.

---

## 6. The five format engines — workspace re-skin

The active **writing mode** changes vocabulary, the scene-body editor, the
structure labels, the pipeline, and which review dashboard/export is offered.
Design one parametric workspace, themed per mode:

| Mode | Structure spine | Scene body | Signature surfaces |
|---|---|---|---|
| **Novel** | Act → Chapter → Scene | prose | chapter rhythm, story grid |
| **Screenplay** | Act → Sequence → Scene | screenplay elements | subtext & setup/payoff trackers, production drafts, Fountain/FDX |
| **Graphic Novel** | Act → Page → Scene → Panel | page/panel script | Page Canvas/preview, image-prompt export |
| **Stage Script** | Act → Scene → Beat | performable dialogue + blocking | theatrical review, blocking |
| **Series** | Season → Episode → Act → Chapter → Scene | teleplay blocks | Series Navigator, cross-episode continuity |

Each mode shares the same panel *patterns* (pipeline confirm, mode review
dashboard, controlled rewrite diff, export) — only the content + theme change.

---

## 7. Design-language guidance for Claude Design

- **Identity:** dark-first, cinematic, "minimal-cyber / terminal" — precise,
  dense, composed. Distinct from Whiteboard's calm minimalism. Free to be
  dramatic (HUD overlays, graph canvases, branching timelines).
- **Layout:** a dockable, tile-able workspace with savable per-project layouts;
  Focus ↔ Cockpit modes. Center editor, right intelligence dock, bottom analysis
  dock, left navigator rail.
- **Density done right:** lots of live signal (energy heatlines, health HUD,
  decision cards, graph) but quiet by default — proactive insight lives in thin,
  dismissible banners and dockable HUD widgets, never modal nags.
- **Signature surfaces to make beautiful:** the **Canvas Plot** board, the
  **Knowledge Graph** (gravity-sized, flow-overlaid), the **Quantum Timeline**
  (superposed branches), the **Decision Radar**, the **PSYKE inspector**
  (relations + progressions), and **Dexter's Room** voice HUD.
- **Two omni-inputs:** Command Palette (`/`) and PSYKE Console (omnibox) — make
  Studio keyboard-first and fast.
- **Confirm-before-apply** is a core interaction primitive — design one excellent
  **diff + impact** modal reused everywhere content changes.
- **Mode-aware:** the whole shell re-skins per writing mode; design the
  parametric system, not five apps.

---

## 8. Suggested top-level navigation (designer's starting point)

`Dashboard · Write (Manuscript) · Structure · Scenes · Plot/Timeline · PSYKE ·
Graph · Quantum · Stages · Reviews (mode) · Notes · Search · Voice · Plugins ·
Settings` — with the **Assistant**, **Decision Radar**, and **Story Health**
docks available from any section, and the Command Palette / PSYKE Console always
one keystroke away.

> Build the brief into screens in Claude Design, then we recode the approved
> design in Claude Code as `pro-shared-ui` (consumed by pro-desktop + pro-web),
> wiring each panel to the existing `logosforge.api`.
