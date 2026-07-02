# Decision Radar (Phase 10N)

A ranked, deterministic list of the most important current decisions for a
project — part of the Project Intelligence Dashboard (see
docs/ProjectIntelligence.md). Every card is **traceable to existing data**; there
are no hallucinated cards.

## Card (`DecisionCard`)

- `id`, `category` (structure / psyke / continuity / rewrite / apply / export /
  production / graph / notes / assistant / writing_mode)
- `severity` — `blocking` / `warning` / `suggestion` / `opportunity` / `info`
- `confidence` — `confirmed` / `likely` / `possible` / `unknown`
- `title`, `explanation`, `suggested_action`
- `related_section` (+ optional target type/id), `created_from`

## Ranking

Blocking → warning → suggestion → opportunity → info; then capped (default top
10). The Logos `Decision Radar` action and the Assistant `[Project Intelligence]`
block surface the top cards.

## Example cards

- "14 scenes but only 3 have summaries." (structure / suggestion)
- "Character exists in PSYKE but has empty notes." (psyke / suggestion)
- "A preferred rewrite variant has not been applied." (rewrite / warning)
- "A Controlled Apply operation is pending." (apply / warning)
- "Fountain export has blocking issues." (export / blocking, screenplay)
- "Production draft active but no revision set." (production / suggestion)
- "Isolated graph node(s)." (graph / opportunity)

## Severity & confidence

`severity` ranks the card; `confidence` states how data-backed it is (a confirmed
warning is a hard, data-backed issue; a possible opportunity is a soft hint).
Cards never assert certainty beyond the underlying data.

## Safety

Deterministic; reads only; no mutation; no LLM. AI interpretation of the radar is
a separate, manual `Explain Dashboard` action. Card "dismiss" is a UI-only state
(deferred) — never deletes data.

## Deferred

Radar UI with filters + per-card actions (open section / send to Assistant /
create from suggestion); persistent dismiss state.

## Knowledge Graph cards (Phase 10P)

The Narrative Knowledge Graph contributes a dedicated, deterministic card feed
via `knowledge_graph.build_graph_decision_cards` (isolated PSYKE/elements, scenes
without PSYKE links, undefined note terms, many inferred edges to review, a theme
not tied to scenes, a risk touching a central node). It is surfaced through the
`Generate Decision Cards from Graph` Logos action and kept separate from the core
10N radar so this radar's capped/fixed-id contract is unchanged. See
docs/NarrativeKnowledgeGraph.md.

## Continuity cards (Phase 10Q)

The Semantic Continuity Engine contributes a dedicated, deterministic card feed
(`continuity.build_continuity_decision_cards`, category `continuity`) ranked by
severity and traceable to specific issues, surfaced via the `Continuity Decision
Cards` Logos action. Kept separate from the core 10N radar so its capped/fixed-id
contract is unchanged. See docs/SemanticContinuityEngine.md.
