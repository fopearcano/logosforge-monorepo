# Project Operating System (Phase 10O)

The "Project OS" is the layer that ties Logosforge's individual intelligences
into a coherent way of *operating* a project over time. It is not a new app or a
task manager bolted onto storytelling — it is a thin, deterministic conductor
over systems that already exist.

## The loop

1. **Understand** — Project Intelligence reads the project (mode, structure,
   PSYKE, workflow status, export readiness, health).
2. **Decide** — the Decision Radar ranks what matters now (blocking → warning →
   suggestion → opportunity → info).
3. **Act (guided)** — Guided Workflows turn those decisions into a resumable,
   mode-aware, step-by-step path (see docs/GuidedWorkflows.md).
4. **Verify** — deterministic completion checks tick off the *verifiable* steps;
   creative steps stay the user's call.
5. **Apply safely** — any real content change routes through Controlled Apply /
   Rewrite Sandbox with confirmation.

The loop is entirely **pull-based and deterministic**: nothing runs in the
background, nothing calls an LLM on its own, nothing mutates content without the
user. The OS proposes; the user disposes.

## How the pieces connect

- **Writing Modes** decide which workflows/steps are even offered (e.g.
  screenplay-only Production Prep).
- **Project Intelligence + Decision Radar** drive workflow *recommendations* and
  *completion checks* (one read-only report, reused).
- **Logos** exposes the OS deterministically (`Active Workflows`,
  `Recommend Workflows`) plus one advisory generative action
  (`Explain Workflow Step`).
- **Assistant** receives a small `[Guided Workflow]` context block so it can help
  with the *current* step — and is explicitly told never to mark steps done.
- **Rewrite Sandbox / Controlled Apply** are the only paths to actual content
  mutation; workflows point at them but never bypass their confirmation.

## What it deliberately is NOT

- Not autonomous: no background LLM scans, no auto-apply, no agent behavior.
- Not a generic task manager: every step maps to a storytelling system.
- Not a content mutator: the engine writes only workflow state.
- Not cloud/collaboration: single-user, local, per-project.

## Persistence & isolation

State lives in three idempotent tables (`WorkflowRun`, `WorkflowStepState`,
`WorkflowEvent`) keyed by `project_id`. Switching projects never leaks state;
old databases gain the empty tables via `create_all`.

## See also

- docs/GuidedWorkflows.md — the workflow engine, templates and safety contract.
- docs/ProjectIntelligence.md — the read-only aggregation service.
- docs/DecisionRadar.md — the ranked decision cards.
- docs/ControlledApply.md, docs/AdaptiveRewriteSandbox.md — the safe mutation
  paths workflows route through.
