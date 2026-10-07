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
- `related_section` (+ optional target type/id/key), `created_from`
- optional canonical Graph navigation (`graph_focus_key`, `graph_view_mode`,
  `graph_include_inferred`, `graph_depth`)
- `evidence_total` plus up to five structured evidence rows. Each row can carry
  its own section and typed id/key destination. Graph evidence preserves exact
  node/edge identities; Continuity evidence preserves canonical issue keys and
  only project-owned scene ids.

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

## UI

The Pro Dashboard merges the stable core, Knowledge Graph, and Semantic
Continuity feeds, severity-ranks once, and keeps a single ten-card display cap.
Canonical cards have explicit origin badges, expandable bounded evidence, and
exact deep links. Graph rows focus their canonical nodes; Continuity rows open
their canonical issue or project-owned manuscript scene. Legacy graph isolation
advice is suppressed when the canonical graph reports the same class of issue.
Persistent dismiss and custom filters remain deferred.

## Knowledge Graph cards (Phase 10P)

The Narrative Knowledge Graph contributes a dedicated, deterministic card feed
via `knowledge_graph.build_graph_decision_cards` (isolated PSYKE/elements, scenes
without PSYKE links, undefined note terms, many inferred edges to review, a theme
not tied to scenes, a risk touching a central node). HTTP exposes that feed as
`knowledge_graph_cards` alongside an explicit availability flag; it remains
separate from the core 10N radar so that feed's capped/fixed-id contract is
unchanged. The Pro Dashboard performs the bounded merge described above. The
same cards remain available through the `Generate Decision Cards from Graph`
Logos action. See docs/NarrativeKnowledgeGraph.md.

## Continuity cards (Phase 10Q)

The Semantic Continuity Engine contributes a dedicated, deterministic card feed
(`continuity.build_continuity_decision_cards`, category `continuity`) ranked by
severity and traceable to specific issues. HTTP exposes at most eight cards in
`continuity_cards` with an independent availability flag, one canonical issue
key per card, the authoritative evidence total, and up to five issue/detail/
project-owned scene facts. The Pro Dashboard merges them without changing the
core 10N feed. **Open Continuity Issue** focuses the exact issue after the
authoritative report loads; scene facts open the exact Manuscript scene. A stale
or resolved key is reported and consumed rather than matched approximately. The
`Continuity Decision Cards` Logos action remains available. See
docs/SemanticContinuityEngine.md.
