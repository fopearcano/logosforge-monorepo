# Project Intelligence Dashboard (Phase 10N)

The project command center. It **reads** existing systems, summarizes them, and
helps the user decide what to do next. It **creates no narrative data, mutates
nothing, and calls no LLM** by default.

## What it answers

What is this project? What mode is it in? What's complete / missing /
structurally weak? Which PSYKE entries are underdeveloped? What open risks and
pending decisions exist? What exports are ready? What should I do next?

## Service (`logosforge/project_intelligence/`)

`build_project_intelligence_report(db, project_id, *, light=False)` →
`ProjectIntelligenceReport`:

- **overview** — title, writing mode, words/scenes/chapters/acts/notes/PSYKE.
- **psyke** — counts by type, global count, empty-notes, no-relations.
- **structure** — scenes without chapter/summary, outline nodes, graph
  nodes/edges/isolated.
- **workflow** — Rewrite Sandbox / Controlled Apply / Revision Intelligence /
  Production Draft status (each "available: False" when deferred).
- **export** — mode-aware export readiness (screenplay → fountain validation).
- **health** — top narrative-health risks (skipped in `light` mode).
- **radar** — the Decision Radar (see docs/DecisionRadar.md).

`light=True` skips the expensive Health + export-validation passes — used by the
Assistant context block so it stays cheap.

Qt-free, read-only, deterministic, current-project-only, capped.

## Metrics

Simple, explainable completeness/consistency/workflow/risk/opportunity signals
only. **No fake "quality score", commercial-viability, or bestseller
prediction.**

## Writing-mode awareness

Novel shows chapters/scenes/PSYKE depth; Screenplay adds Fountain/DOCX/export +
production-draft + scene-numbering + revision status; Graphic Novel / Stage /
Series show mode-specific signals or clean "deferred" placeholders. Screenplay
production/export cards never appear in Novel.

## Logos (deterministic, no LLM)

`Project Intelligence` (status) and `Decision Radar` (ranked cards) — mode-
agnostic, read-only. `Explain Dashboard` is generative (advisory, explicit).

## Assistant context

`[Project Intelligence]` block — uses the **light** report (mode + top decisions).
Capped; no full dashboard dump; no LLM/DB; no cross-project leak. Disable via
`include_project_intelligence_in_assistant_context`.

## Refresh / project switch

Reads are per-`project_id`, so no stale data leaks across a project switch; the
report rebuilds for the current project. (The interactive Dashboard UI overhaul
is deferred — see below.)

## Deferred (future)

- Dashboard **UI** overhaul (the existing `DashboardView` is unchanged); Decision
  Radar UI with severity/category/confidence filters + card actions.
- AI "turn this into a work plan" action; card dismiss-state persistence;
  Counterpart wiring.

## Limitations

Aggregation is deterministic and capped; some subsystem signals are heuristic
(graph isolation, PSYKE relevance). No project-quality score by design. No UI yet
— driven by the service API + Logos status + `[Project Intelligence]` Assistant
context.

## Narrative Knowledge Graph (Phase 10P)

A traceable semantic graph (`logosforge/knowledge_graph/`) consolidates PSYKE,
structure, notes, plot/timeline, the link graph, setup/payoff and
revision/rewrite/apply findings, with confidence + provenance on every edge and
confirmed-vs-inferred distinction. It powers graph-derived decision cards and a
scene-scoped `[Narrative Knowledge Graph]` Assistant block. See
docs/NarrativeKnowledgeGraph.md.
