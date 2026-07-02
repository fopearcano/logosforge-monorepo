# Logos — the inline, contextual assistant

Logos is LogosForge's **inline / contextual** AI layer. It is distinct from
the chat **Assistant** but shares the same backend.

## Assistant vs Logos

| | **Assistant** | **Logos** |
|---|---|---|
| Surface | Chat panel (`AssistantPanel` in `AssistantDock`) | Inline toolbar, suggestion pills, diagnostics/health drawers |
| Interaction | Conversational, persistent | Selection-/section-aware, one-shot actions |
| Provider/model/API settings | **Owns** them (the only provider UI) | **Never** — reuses the same backend |
| Mutation | Via its own apply paths | Preview + confirm only (`LogosApplyPreview`) |

There is exactly **one** AI provider/chat path. Logos never creates a second
backend, never stores API keys, and never duplicates provider settings.

## Shared backend path

```
LogosController.run()
  → prompt_builder.build_logos_messages(db, ctx, action)   # context_builder + assistant.build_messages
  → provider_resolver()   # default: ui.outline_ai.build_provider (reads ai_provider/ai_base_url/ai_model/ai_api_key)
  → chat_fn(messages, provider)   # default: assistant.chat_completion  (the ONLY HTTP LLM caller)
```

Both `provider_resolver` and `chat_fn` are injectable (used by tests); the
defaults are the shared Assistant backend. Timeouts come from
`assistant.get_configured_timeout`; provider errors raise clean exceptions that
the controller/toolbar catch and surface as a `LogosResult` error.

## Context flow

`MainWindow._build_logos_context()` captures a lightweight, serializable
`LogosContext` from live UI state on **every** call (current `project_id`,
`current_section`, selection, active scene/editor, selected PSYKE entry, graph
node, etc.). It holds no ORM rows, widgets, or secrets. The controller turns it
into messages via the shared `context_builder` gatherers (scene/outline/psyke/
notes) — it does not invent a second context system.

## Phases (modules under `logosforge/logos/`)

- **Core** (`context`, `actions`, `controller`, `prompt_builder`, `result`) —
  section-aware actions (Manuscript / Outline / PSYKE / Plot / Timeline / Graph).
  Actions may be **mode-restricted** via `LogosAction.modes` (Phase 10A/10B):
  screenplay-only actions (e.g. Convert Prose to Visual Action, Check Scene Turn,
  Strengthen Setup/Payoff, Detect Overwritten Action, Check Sequence Logic,
  Track Setup/Payoff) appear and sort first only when `writing_mode ==
  "screenplay"`, and stay hidden in Novel. `LogosController.available_actions`
  filters + medium-orders; the toolbar passes the live `writing_mode`.
  Actions may also be **deterministic** (`LogosAction.deterministic`, Phase 10C):
  the controller routes these to `logosforge/logos/deterministic.py` and runs a
  rule-based handler with **no provider/LLM call** (e.g. `Diagnose Scene Economy`
  runs the screenplay diagnostics engine). Generative actions still call the
  shared backend only on explicit invocation, through preview/confirm. Phase 10D
  adds deterministic setup/payoff + subtext actions (`Detect Setup/Payoff
  Candidates`, `Track Unresolved Setups`, `Find Possible Payoffs`, `Check
  Dialogue Subtext`, `Find Exposition in Dialogue`) and generative subtext
  rewrites — all screenplay-only and report-only (no PSYKE/Graph auto-mutation).
  Phase 10E adds deterministic story-link graph actions (`Show Story Link
  Graph`, `Explain This Link`) over `screenplay_graph.build_screenplay_graph`;
  confirmed-link persistence (`StoryLink`) is explicit/user-invoked via the
  service API, and the mutating Logos actions + graph widget are Phase 10F. Phase 10F adds deterministic export-polish
  actions (Validate Screenplay Export, Export Readiness Report, Preview Render,
  Find Orphan Dialogue/Parentheticals, Check Production Polish) — read-only. Phase 10G adds deterministic Fountain actions
  (Validate Fountain Export, Preview Fountain Output, Check Fountain Compatibility,
  Find Ambiguous Fountain Elements, Explain Fountain Warning, Prepare for Fountain). Phase 10H adds deterministic professional-output
  actions (Validate Professional Output, Output Readiness Report, Preview Output,
  Check PDF Readiness, Check FDX Feasibility, Explain Export Warnings, Prepare for
  Professional Export) — read-only; DOCX/PDF/FDX file writes are export functions. Phase 10J adds deterministic production-draft status
  actions (Explain/Validate Production Draft, Check Duplicate Scene Numbers,
  Summarize Revision Set, Explain Page Locking, Prepare for Production Export);
  production mutations are an explicit service API. Phase 10K adds deterministic revision-intelligence
  actions (Generate Revision Impact Map, Check PSYKE/Setup-Payoff/Continuity/
  Impacted-Scenes, Prepare Revision Follow-up); saving reports / graph-link
  conversion are explicit, confirmed service calls. Phase 10L adds writing-mode-aware
  rewrite-sandbox status actions (Rewrite Sandbox status, Explain Rewrite
  Tradeoffs, Score Variants, Check PSYKE Preservation) + a generative Suggest
  Rewrite Strategy; variant generation and confirmed apply use the engine API. Phase 10M adds deterministic Controlled Apply
  status actions (Apply History, Explain Apply Conflicts); every canonical
  mutation routes through the Controlled Apply service (preview + diff +
  conflicts + confirmed apply + checkpoint). See docs/ControlledApply.md. Phase 10N adds read-only Project Intelligence
  + Decision Radar actions (Project Intelligence status, Decision Radar) and a
  generative Explain Dashboard. See docs/ProjectIntelligence.md. Phase 10O adds read-only Guided Workflow
  actions (Active Workflows, Recommend Workflows) and a generative Explain
  Workflow Step; the workflow engine mutates only workflow state and routes any
  content change through Controlled Apply / Rewrite Sandbox. See
  docs/GuidedWorkflows.md and docs/ProjectOperatingSystem.md. Phase 10P adds read-only Narrative Knowledge
  Graph actions (Build/Refresh Knowledge Graph, Show Scene/PSYKE Neighborhood,
  Find Orphan Nodes/Weak Links/Undefined Terms, Generate Decision Cards from
  Graph) + a generative Explain Knowledge Graph; confirm/hide/convert/create are
  confirmable service calls. See docs/NarrativeKnowledgeGraph.md. Phase 10Q adds read-only Semantic Continuity
  actions (Run Continuity Check, Check Current Scene Continuity, Show Continuity
  Issues, Continuity Decision Cards) + a generative Explain Continuity Issue;
  dismiss/resolve are issue-metadata writes and change-validation is a service
  call (preview-only). See docs/SemanticContinuityEngine.md.
- **operations** — controlled, validated apply ops (manuscript replace/insert,
  outline scene create/update, PSYKE notes/progression/relation). Every mutation
  is previewed and confirmed; nothing auto-applies.
- **proactive/** — rule-based proactive suggestions (no background LLM); a
  bounded, dismissible/snoozable pill bar.
- **diagnostics/** — PSYKE-aware narrative diagnostics (character/theme/
  relationship/continuity/structure/setup-payoff/graph/notes).
- **health/** — explainable project-level Narrative Health report (status
  labels, no fake percentages; `unknown` when data is missing).
- **strategy/** — the medium-aware strategy router (see `StrategyLayer.md`).

## Preview / apply

Generative Logos actions return a `LogosResult` with `proposed_operations`.
`LogosApplyPreview` shows a resizable, scrollable dialog and returns a finalized,
validated operation **only on confirm**. `MainWindow._logos_request_apply`
applies it through existing services, emits the relevant bus events, and marks
the project dirty (autosave + versioning). Cancel = no mutation.

## What is intentionally **not** automated

- No background LLM calls — proactive scans, diagnostics, health and strategy
  routing are deterministic and rule-based.
- No automatic text rewrite / node creation / relation creation — all mutations
  require explicit confirmation.
- The Assistant prompt is **not** auto-fed Health/Diagnostics/Strategy context;
  those are separate drawers / opt-in hooks, keeping the Assistant decoupled.
