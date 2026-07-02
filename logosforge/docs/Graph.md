# Screenplay Story-Link Graph (Phase 10E)

`logosforge/screenplay_graph.py` turns existing screenplay data into a
lightweight node/edge graph for screenplay projects (`writing_mode ==
"screenplay"`).

## Graph is not a source of truth

The graph **references** existing entities by id — it never copies scene content,
PSYKE entry text, outline hierarchy, or screenplay block text. It is rebuilt
deterministically from the real data each time:

> scenes / blocks · PSYKE entries · setup/payoff candidates · subtext signals ·
> diagnostics · **confirmed `StoryLink` rows**

`build_screenplay_graph(db, project_id, *, scene_id=None, include_candidates=True,
include_confirmed=True)` is read-only (no DB mutation), no LLM, no stale-project
leak, and dedupes nodes by id.

## Candidate vs confirmed links

- **Candidate** edges are generated dynamically from the engines (setup→payoff,
  motif recurrence, character-in-scene, psyke→scene, subtext→character, …) and
  are **never persisted automatically**.
- **Confirmed** links are persisted in the `StoryLink` table only when the user
  explicitly confirms one (`confirm_candidate`), and can be `dismissed` /
  `resolved` (`dismiss_link` / `resolve_link`). Dismissed links are excluded
  from the graph. Confirmed/resolved edges are visually distinct (status field).

## Node / edge types

Nodes: `scene, act, sequence, character, psyke_entry, setup, payoff, motif,
object, promise, threat, subtext, objective, diagnostic`.
Edges: `setup_to_payoff, motif_recurrence, promise_to_consequence,
threat_to_consequence, object_plant_to_use, character_in_scene, objective_to_turn,
subtext_to_character, psyke_to_scene, scene_to_sequence, sequence_to_act,
diagnostic_to_scene`.

## Persistence

`StoryLink` (SQLModel table) stores **references only** (ids, scene/block indices,
link_type, label, evidence, status, confidence) — no manuscript text. It is
created idempotently by `SQLModel.create_all` on DB open, so existing projects
gain it empty and never break. There is no auto-confirmation.

## Surfaces

- **Logos** (deterministic, no LLM): `Show Story Link Graph`, `Explain This Link`.
- **Assistant**: capped `[Screenplay Story Links]` block (≤3 confirmed / candidate
  setup-payoff / motif) via `include_screenplay_links_in_assistant_context`.
- **Narrative Health**: `Confirmed Setup/Payoff Coverage` (confirmed links weigh
  more) and `Unresolved Candidate Density` (cautious warning, not a failure).
- **Export**: `export_screenplay_graph_json` and `export_story_links_json`
  (both carry `schema_version` + writing mode).

## Deferred to Phase 10F

- Interactive screenplay graph **widget** (node groups, edge/status/scope
  filters, evidence panel, 13-inch layout) — today the graph is exposed via the
  builder, Logos summary, Assistant context, and JSON export.
- UI confirmation flow buttons + mutating Logos actions (Confirm/Dismiss/Resolve,
  Add to Graph, Create PSYKE from candidate) — the persistence + service API
  exist (`confirm_candidate` / `dismiss_link` / `resolve_link`); wiring them to
  preview/confirm UI is 10F.
- Strategy-explanation enrichment from live graph state; Cinematic Continuity.

## Limitations

Candidate links are heuristic (lexical setup/payoff + structural inference);
confidence is honest and modest. Confirmed links persist, but generating them
still requires a human decision. The existing relationship `GraphView` is
unchanged — the screenplay graph is a separate, additive data/report layer.

## Revision impact (Phase 10K)

The Change Impact Map (`revision_intelligence`) produces node/edge-style
impact data (changed scene → impacted scenes / PSYKE / setup-payoff). A
dedicated Graph **visualization mode** for it is deferred; the data is
available via the impact map result. See **docs/RevisionIntelligence.md**.

## Narrative Knowledge Graph (Phase 10P)

A project-wide, traceable semantic graph (`logosforge/knowledge_graph/`)
consolidates PSYKE, scenes, structure, notes, plot/timeline, the link graph +
confirmed StoryLinks, setup/payoff, and revision/rewrite/apply findings into one
typed graph with confidence + provenance on every edge. Confirmed vs inferred
edges are distinguished; confirmed/user edges survive rebuilds. This Graph
section is unchanged; the multi-mode Graph UI upgrade is deferred. See
**docs/NarrativeKnowledgeGraph.md**.
