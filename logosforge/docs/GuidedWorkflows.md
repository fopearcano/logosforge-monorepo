# Guided Workflows (Phase 10O)

Resumable, writing-mode-aware, step-by-step workflows that guide the user
through the existing systems without ever acting autonomously. A workflow is a
**recommended path**, not an automation: it tells you *what to do next* and can
*verify* deterministic steps, but it never writes your story for you.

## What it is

`logosforge/guided_workflows/` — a Qt-free, deterministic engine over three
persisted tables. It threads Project Intelligence, Decision Radar, Writing
Modes, PSYKE, Outline, Manuscript, Rewrite Sandbox, Controlled Apply, Revision
Intelligence, Export and Production Draft into named workflows.

## Built-in templates (A–H)

| # | Template | Modes | Focus |
|---|----------|-------|-------|
| A | Project Setup | all | title, logline, mode, first scenes |
| B | PSYKE Story Bible | all | entries, notes, relations |
| C | Classical Outline | all | structure, chapters, scene summaries |
| D | Scene Drafting | all | draft → (economy) → summary → continuity |
| E | Rewrite | all | select → strategy → generate → compare → apply |
| F | Screenplay Production Prep | **screenplay** | draft, numbering, revision set, validate |
| G | Export Readiness | all | validate, clear warnings, preview, sign-off |
| H | Decision Radar Fix | all | work down blocking/warning decisions |

Templates are **data-driven** (`templates.py`): each is an ordered list of
`WorkflowStep`s with an `id`, `title`, `kind`, optional `section_name`,
optional Logos `action_id`, optional `completion_check` and optional `modes`.
Mode-specific steps and templates are filtered out for the project's writing
mode (e.g. the screenplay economy step in *Scene Drafting* only appears for
screenplays; *Screenplay Production Prep* is offered only in screenplay mode).

## Step kinds & completion

- **creative** — user judgement (drafting, comparing, reviewing). **Never
  auto-completed.** Only the user marks these done.
- **check** — has a deterministic completion check (e.g. *every scene has a
  summary*, *export is safe*). May be auto-ticked by `refresh_workflow_run`.
- **manual** — a simple acknowledgement the user ticks (no auto-check).

Completion checks (`completion_checks.py`) read only the deterministic Project
Intelligence report — no LLM, no mutation. `refresh_workflow_run` re-evaluates
checks and auto-completes only passing **check** steps; creative/manual steps
are left for the user.

## Engine API (`engine.py`)

`start_workflow`, `get_active_workflows`, `get_all_workflows`,
`get_workflow_run_view`, `complete_workflow_step`, `skip_workflow_step`,
`advance_workflow_step`, `pause_workflow`, `resume_workflow`,
`cancel_workflow`, `refresh_workflow_run`, `check_step_completion`,
`workflow_status_summary`.

A `WorkflowRunView` bundles the run row, ordered step states and the template,
with `current_step`, `completed_steps`, `is_complete`, `progress_line()`.

## Persistence

Three idempotent SQLModel tables (added via `create_all`; old DBs gain empty
tables):

- `WorkflowRun` — template id, title, writing mode, status
  (`active`/`paused`/`completed`/`cancelled`/`blocked`), current step.
- `WorkflowStepState` — per-step status
  (`pending`/`active`/`completed`/`skipped`/`blocked`), section, action, notes.
- `WorkflowEvent` — an audit trail (`started`, `step_completed`,
  `step_auto_completed`, `step_skipped`, `paused`, `resumed`, `cancelled`,
  `completed`).

Reads/writes are per-`project_id`, so switching projects never leaks state.

## Recommendations

`recommendations.py::build_workflow_recommendations` maps Decision Radar
categories to templates (deterministic, severity-ranked, mode-filtered) and
bootstraps *Project Setup* for empty projects. The user always chooses whether
to start one.

## Logos (deterministic, no LLM)

- `Active Workflows` (`wf_active_workflows`) — active runs + current step.
- `Recommend Workflows` (`wf_recommend_workflows`) — radar-driven suggestions.
- `Explain Workflow Step` (`wf_explain_next_step`) — *generative*, advisory; the
  Assistant explains the current step but never marks it done.

## Assistant context

`[Guided Workflow]` block — only emitted when a workflow is active. Names the
workflow, progress and current step, and instructs the Assistant to help with
the step but **never mark steps done**. Capped; deterministic; no LLM/DB write;
no cross-project leak. Disable via
`include_guided_workflow_in_assistant_context`.

## Safety

- The engine mutates **only workflow state** — never scenes, PSYKE, outline,
  production drafts or any project content.
- Creative steps are never auto-completed.
- No background scans; no autonomous agent behavior; no LLM in the engine.
- Any real content change a step implies (apply a rewrite, accept a merge)
  routes through **Controlled Apply / Rewrite Sandbox**, which require their own
  confirmation. The workflow only points you there.

## Deferred

- A dedicated Workflow **UI** panel (the engine + Logos + Assistant context are
  the current surface).
- Custom user-authored templates; per-step reminders; multi-project dashboards.

## Knowledge Graph Cleanup (Phase 10P)

Template **I — Knowledge Graph Cleanup** (mode-agnostic): build the graph →
review orphan PSYKE entries → confirm important inferred edges → connect notes
to PSYKE → clean the structure graph → review a scene neighborhood before
rewrite. Guides graph cleanup without mutating anything automatically;
PSYKE-relation creation / edge confirmation require confirmation. See
docs/NarrativeKnowledgeGraph.md.

## Continuity workflows (Phase 10Q)

Template **J — Continuity Review** (mode-agnostic): run a continuity check →
review issues → resolve missing transitions → resolve setups → re-check.
Template **K — Screenplay Continuity Pass** (screenplay): check → fix heading
data → validate export. Both guide the user; no automatic mutation — fixes route
through Controlled Apply. See docs/SemanticContinuityEngine.md.
