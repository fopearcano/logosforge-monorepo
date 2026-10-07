# Dashboard

## Project Intelligence + Decision Radar (Phase 10N)

A read-only Project Intelligence service aggregates project status,
structure, PSYKE, workflow (rewrite/apply/revision), and export/production
readiness into a `ProjectIntelligenceReport` + a ranked **Decision Radar**.
It creates no data and mutates nothing. Surfaced via Logos status actions
and a capped `[Project Intelligence]` Assistant block. The Pro Decision Radar
panel now merges the stable feed with canonical Knowledge Graph and Semantic
Continuity decisions under one ten-card display cap. See docs/ProjectIntelligence.md and
docs/DecisionRadar.md.

## Narrative Knowledge Graph (Phase 10P)

The Knowledge Graph (docs/NarrativeKnowledgeGraph.md) adds a deterministic,
graph-derived decision-card feed (`build_graph_decision_cards`) — isolated
PSYKE/elements, scenes without PSYKE links, undefined note terms, weak/inferred
links to review, risks touching central nodes. The Decision Radar endpoint
exposes these separately with an availability flag, exact graph targets, and
bounded structured evidence; the Pro UI merges/ranks them while preserving the
core Project Intelligence radar contract. The `Generate Decision Cards from
Graph` Logos action remains available.

## Semantic Continuity (Phase 10Q)

The Semantic Continuity Engine (docs/SemanticContinuityEngine.md) adds a
deterministic, traceable continuity decision-card feed
(`build_continuity_decision_cards`, category `continuity`) — dangling
setup/payoff links, location jumps, production-continuity risks, character
state drift — surfaced via the `Continuity Decision Cards` Logos action. The
Decision Radar endpoint also exposes them in a separate, failure-isolated feed
with canonical issue keys and bounded issue/scene evidence. The Pro UI can open
the exact Continuity issue or a referenced project-owned Manuscript scene. The
core Project Intelligence radar contract is unchanged.
