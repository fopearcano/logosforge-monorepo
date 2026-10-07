# Guided Workflows (Phase 10O engine / Pro roadmap Phase 7A)

Resumable, writing-mode-aware, step-by-step workflows that guide the user
through the existing systems without ever acting autonomously. A workflow is a
**recommended path**, not an automation: it tells you *what to do next* and can
*verify* deterministic steps, but it never writes your story for you.

## What it is

`logosforge/guided_workflows/` — a Qt-free, deterministic engine over four
persisted tables. It threads Project Intelligence, Decision Radar, Writing
Modes, PSYKE, Outline, Manuscript, Rewrite Sandbox, Controlled Apply, Revision
Intelligence, Export and Production Draft into named workflows.

“Phase 10O” is the historical Core feature label. “Phase 7A” is the later Pro
roadmap milestone that made the engine a complete HTTP-controlled Studio
cockpit; they describe different planning layers of the same system.

## Built-in templates (A–K)

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
| I | Knowledge Graph Cleanup | all | review orphans, inferred edges, notes, and structure |
| J | Continuity Review | all | inspect issues, repair transitions/setups, and re-check |
| K | Screenplay Continuity Pass | **screenplay** | heading data, continuity, and export validation |

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

The canonical command refresh proves only checks that can be evaluated inside
the same `BEGIN IMMEDIATE` SQL transaction as the workflow update — no LLM and
no content mutation. Aggregate graph, Radar, and export checks fail closed for
now instead of completing from a torn multi-session report. A later refresh can
complete them when their engines expose a coherent transaction-bound snapshot.
Creative/manual steps are always left for the user.

## Engine compatibility API (`engine.py`)

`start_workflow`, `get_active_workflows`, `get_all_workflows`,
`get_workflow_run_view`, `complete_workflow_step`, `skip_workflow_step`,
`advance_workflow_step`, `pause_workflow`, `resume_workflow`,
`cancel_workflow`, `refresh_workflow_run`, `check_step_completion`,
`workflow_status_summary`.

A `WorkflowRunView` bundles the run row, ordered step states and the template,
with `current_step`, `completed_steps`, `is_complete`, `progress_line()`.
Legacy mutators delegate to the same atomic database command boundary as the
HTTP surface; they are compatibility functions, not a second write path.

## HTTP 1.13.0 control plane

The Pro client uses these project-owned routes:

```text
GET  /api/projects/{project_id}/workflow-templates
GET  /api/projects/{project_id}/workflow-recommendations
GET  /api/projects/{project_id}/workflows
GET  /api/projects/{project_id}/workflows/{run_id}
GET  /api/projects/{project_id}/workflows/{run_id}/events?limit=40
POST /api/projects/{project_id}/workflows/commands
GET  /api/projects/{project_id}/workflows/command-receipt
```

The command union is `start_workflow`, `complete_step`, `skip_step`, `advance`,
`refresh`, `pause`, `resume`, and `cancel`. All commands require an
`Idempotency-Key`; every command except start also requires the authoritative
run revision returned by the latest coherent read.

## Persistence

Four idempotent SQLModel tables (added via `create_all`; old DBs gain empty
tables):

- `WorkflowRun` — template id, title, writing mode, status
  (`active`/`paused`/`completed`/`cancelled`/`blocked`), current step.
- `WorkflowStepState` — per-step status
  (`pending`/`active`/`completed`/`skipped`/`blocked`), section, action, notes.
- `WorkflowEvent` — an audit trail (`started`, `step_completed`,
  `step_auto_completed`, `step_skipped`, `advanced`, `paused`, `resumed`,
  `blocked`, `cancelled`, `completed`).
- `WorkflowCommandReceipt` — a project-scoped SHA-256 hash of the caller's
  capability key, exact request digest, original outcome and applied revision.
  The raw idempotency key is never stored.

Reads/writes are per-`project_id`, so switching projects never leaks state.

## Recommendations

`recommendations.py::build_workflow_recommendations` maps Decision Radar
categories to templates (deterministic, severity-ranked, mode-filtered) and
bootstraps *Project Setup* for empty projects. The user always chooses whether
to start one. Templates that already have an active, paused, or blocked run are
suppressed.

## Pro Studio panel

The production panel catalog contains a live, right-dock-preferred **Guided
Workflows** cockpit. It shows authoritative runs and progress, a mode-filtered
template gallery, a recommendation banner, current step kinds, and the newest
40 audit events. The user can Complete, Skip, Advance, Verify, Pause, Resume,
or cancel with a second confirmation. Section links use a fixed allowlist and
preserve a verified scene target when one exists. An `action_id` opens Logos as
a review surface only; it never executes the suggestion automatically.

Runtime DTO validation rejects foreign projects/runs, malformed revisions,
duplicate steps, incoherent lifecycle pointers, and oversized event responses.
`workflow_changed` invalidates the relevant live resources.

## Transaction and recovery guarantees

- When a command changes state, its transition and audit row commit atomically
  with the durable receipt; a no-op commits the receipt without inventing an
  event.
- Revisions bind logical run/step state, row-incarnation identity, and the
  applicable built-in template semantics.
- Exact delivery replay returns the current coherent run plus the original
  applied revision without repeating the transition or publishing another
  change event.
- After an ambiguous timeout/5xx/408/429, Pro checks the same receipt first. A
  proven receipt miss permits one explicit resend of the exact command and key;
  after that, recovery is receipt-only. A new key cannot be minted while the
  outcome remains unresolved.
- Definite conflicts reconcile from an authoritative read and are never retried
  blindly.

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
