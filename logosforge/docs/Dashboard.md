# Dashboard

## Project Intelligence + Decision Radar (Phase 10N)

A read-only Project Intelligence service aggregates project status,
structure, PSYKE, workflow (rewrite/apply/revision), and export/production
readiness into a `ProjectIntelligenceReport` + a ranked **Decision Radar**.
It creates no data and mutates nothing. Surfaced via Logos status actions
and a capped `[Project Intelligence]` Assistant block; the interactive
Dashboard UI overhaul is deferred. See docs/ProjectIntelligence.md and
docs/DecisionRadar.md.

## Narrative Knowledge Graph (Phase 10P)

The Knowledge Graph (docs/NarrativeKnowledgeGraph.md) adds a deterministic,
graph-derived decision-card feed (`build_graph_decision_cards`) — isolated
PSYKE/elements, scenes without PSYKE links, undefined note terms, weak/inferred
links to review, risks touching central nodes — surfaced via the
`Generate Decision Cards from Graph` Logos action. The core Project
Intelligence radar contract is unchanged.

## Semantic Continuity (Phase 10Q)

The Semantic Continuity Engine (docs/SemanticContinuityEngine.md) adds a
deterministic, traceable continuity decision-card feed
(`build_continuity_decision_cards`, category `continuity`) — dangling
setup/payoff links, location jumps, production-continuity risks, character
state drift — surfaced via the `Continuity Decision Cards` Logos action. The
core Project Intelligence radar contract is unchanged.
