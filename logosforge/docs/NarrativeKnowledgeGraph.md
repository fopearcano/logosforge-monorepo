# Narrative Knowledge Graph (Phase 10P)

A **traceable semantic map** of a project — not a decorative visualization. It
connects PSYKE entries, scenes, chapters, acts, notes, plot blocks, timeline
order, the existing Graph section's links, setup/payoff, and
revision/rewrite/apply findings into one typed graph where **every edge is
traceable to real data**.

It helps answer: which characters appear in which scenes? which elements are
isolated or central? which scenes depend on others? which rewrite/revision risks
touch which elements? which links are confirmed vs only inferred?

## Service (`logosforge/knowledge_graph/`)

Qt-free, LLM-free, read-only by default, deterministic, current-project-only,
capped.

- `build_knowledge_graph(db, project_id, *, options=None) -> KnowledgeGraphResult`
- `query_knowledge_graph(db, project_id, GraphQuery)` / `get_node_neighborhood`,
  `get_scene_context_graph`, `get_psyke_entry_context_graph`,
  `get_orphan_nodes`, `get_high_centrality_nodes`, `get_weak_links`,
  `get_scenes_without_psyke`
- `get_graph_summary_for_assistant(...)`, `explain_node`, `explain_edge`
- `build_graph_decision_cards(...)`
- transactional HTTP edge review: `confirm_edge`, `hide_edge`, `unhide_edge`
  with revision guards, durable command receipts, and exact-retry recovery;
- legacy in-process confirmable writes: `confirm_edge`, `hide_edge`, `unhide_edge`,
  `convert_edge_to_psyke_relation`, `create_psyke_entry_from_term`

The live graph is **computed in-memory each build**. Only **user-confirmed /
hidden** edges (and their endpoint nodes) are persisted; a rebuild regenerates
inferred edges and merges persisted state back in.

## Node types

`project, act, chapter, scene, screenplay_block, psyke_entry, character, place,
object, lore, theme, motif, note, plot_block, timeline_event, setup, payoff,
revision_impact, rewrite_variant, controlled_apply_operation, decision_card,
workflow_run`. PSYKE `entry_type` maps to the typed node (character/place/…).

## Edge types

`contains, appears_in, mentions, relates_to, depends_on, precedes, follows,
causes, contrasts, resolves, sets_up, pays_off, contradicts, revises, risks,
belongs_to, derived_from, inferred_from, suggested_by`.

Every edge carries **confidence**, **provenance**, **source system** and an
**explanation**.

## Confidence levels

`confirmed` (explicit data / user) · `likely` · `possible` · `unknown`.
Positional adjacency (scene order, wikilinks) is at most `likely` — **never fake
causality**. Inferred edges never masquerade as canonical: `is_inferred` is true
unless the edge is `confirmed` or user-confirmed.

## Provenance examples

explicit PSYKE relation · PSYKE progression · global PSYKE entry · scene text
match · outline/chapter/act membership · plot block membership · scene order ·
note reference/wikilink · revision impact report · rewrite session target ·
controlled apply target/conflict · confirmed story link · setup/payoff link ·
guided workflow run · user-created graph link.

## Confirmed vs inferred

- **Confirmed**: explicit PSYKE relations, name/alias text matches, chapter/act/
  plot membership, explicit `setup_payoff_links`, confirmed `StoryLink`s, applied
  Controlled-Apply operations, and anything the user confirms.
- **Inferred**: scene order (`likely`), link-graph wikilinks (`likely`),
  setup/payoff candidates (`possible`), note→PSYKE mentions (`likely`).

Confirmed/user edges **survive a rebuild**; inferred edges are **regenerated**.

## PSYKE extraction

Entries → typed nodes; explicit relations → `confirmed relates_to`; progressions
→ scene references; **global entries attach to the project, not flooded across
every scene**. Scene mentions reuse the existing matcher
(`revision_intelligence.psyke_impact`) — aliases map to one node. No PSYKE
mutation; orphans are detected, never deleted; relations/mentions are capped.

## Structure extraction

Outline (acts/chapters), Manuscript (scene `contains`, scene order = `precedes`
likely), Plot (`plotline` blocks), Timeline (scene order), and the existing
Graph section (link-graph wikilinks = likely; confirmed `StoryLink`s = confirmed,
user-confirmed). Missing sections are listed in `graph.unavailable`, not faked.

## Notes extraction

Note nodes + tags; note→PSYKE `mentions` (likely; wikilinks confirmed);
note→scene wikilinks; **undefined-term detection** (capitalized proper-noun
candidates not in PSYKE) surfaced as suggestions only. Never auto-creates PSYKE.

## Revision / rewrite / apply extraction

Revision impact reports → `revision_impact` nodes that `revise`/`risk` scenes &
PSYKE; rewrite sessions/variants → `rewrite_variant` nodes `derived_from` their
source (rejected variants skipped); Controlled-Apply ops → nodes that `risk`
(pending) or `revise` (applied, confirmed) their target, with `contradicts` for
conflicts. Open/unapplied variants never change canonical meaning.

## Setup / payoff

Explicit links (scene `setup_payoff_links`, confirmed `StoryLink`s) = confirmed.
Inferred screenplay candidates = `possible`, clearly marked. Deferred cleanly in
non-screenplay modes.

## Query API

`GraphQuery(node_type, node_id, edge_type, confidence_min, source_system, depth,
limit, include_inferred, include_deferred)`. All queries are capped,
deterministic, read-only, current-project-only.

The canonical HTTP read surface is
`GET /api/projects/{project_id}/knowledge-graph`. It returns either a bounded
Project Map or a one-/two-hop neighborhood around `focus_key`, with explicit
requested/returned/total counts, truncation state, authoritative orphan and
weak-link diagnostics, and warnings for unavailable source systems. Response
nodes and edges are deterministic, project-scoped, and endpoint-complete.

Every read also returns a project-wide review `revision` and a bounded hidden
edge subset. The complete restore queue is reachable through deterministic,
dense pages at `GET .../knowledge-graph/hidden-edges?offset=&limit=`; each page
contains its exact unique endpoint nodes. The review revision is computed in
one SQLite snapshot from all persisted endpoint/edge rows plus the project's id
and immutable creation timestamp. It intentionally does not claim that the
legacy multi-extractor live graph is one database snapshot: source edits may
change derived nodes/edges without rotating this narrower review token.

`POST .../knowledge-graph/commands` accepts directional
`(source,target,edge_type)` actions `confirm_edge`, `hide_edge`, and
`unhide_edge`. Confirm/hide require a visible inferred edge; unhide requires a
persisted hidden decision. The required `Idempotency-Key` is hashed rather than
stored, and the mutation plus compact receipt commit atomically. Exact retries
resolve the receipt before live-edge preflight, return the current default map,
and preserve the original `applied_revision`; receipt lookup is separately
available at `GET .../knowledge-graph/command-receipt` with no-store/capability
cache headers. The receipt decoder rebinds its stored result to the canonical
request digest so semantically altered proof fails closed. Only a fresh changed
command emits `knowledge_graph_changed`. Logical duplicate persisted rows fail
closed instead of choosing an order-dependent winner.

MCP gateway 1.6 exposes the same boundary through
`logosforge_get_knowledge_graph`,
`logosforge_get_knowledge_graph_hidden_edges`, and
`logosforge_propose_knowledge_graph_command`. The hidden-edge read takes bounded
`offset`/`limit` arguments, so Restore preflight can find every persisted hide
decision rather than depending on the default map's diagnostic subset. The
proposal stores exactly one `confirm_edge`, `hide_edge`, or `unhide_edge`
command under an opaque proposal id; only the shared reviewed apply tool can
mutate. Restore proposals additionally require the `hidden_edge_offset` from
the page containing the target. The gateway refetches that 100-edge page and
requires the exact project, revision, and directional identity before it stores
the proposal; Confirm/Hide reject the page-only offset. That proposal id is
also the Core `Idempotency-Key`. A lost apply can
recover the exact durable receipt, and a fresh MCP process can reconstruct the
applied proposal while returning the current coherent Project Map and original
`applied_revision`. Only a proved `knowledge_graph_receipt_not_found` permits
one bounded same-command/same-key resend; ambiguous or conflicting receipt
evidence fails closed.

## Graph section (UI)

The Pro Graph panel now renders the canonical, API-backed **Project Map** and
focused one-/two-hop neighborhoods instead of a PSYKE-only projection. Node
type, minimum-confidence, and source-system filters are live; selecting a node
can focus its neighborhood or publish its context to the Studio tools. The
panel also presents Core-authoritative orphan and weak-link diagnostics,
loading/error/empty/retry states, and explicit size-cap/truncation status.

The initial Project Map is now paired with explicit **Confirm / Hide / Restore**
review actions backed by the transactional HTTP contract above. Richer
Structure/Risk/Revision/Confirmed-only modes remain deferred. The same guarded
review actions are available to MCP clients through proposal/review/apply and
durable receipt recovery.

## Logos (deterministic, no LLM)

`Build Knowledge Graph`, `Refresh Knowledge Graph` (records a snapshot),
`Show Scene Neighborhood`, `Show PSYKE Neighborhood`, `Find Orphan Nodes`,
`Find Weak Links`, `Find Undefined Terms`, `Generate Decision Cards from Graph` —
all deterministic, read-only. `Explain Knowledge Graph` is generative (advisory;
never confirms an edge). Confirm, Hide, and Restore are explicit transactional
UI actions backed by durable receipts; convert/create remain deferred service
actions.

## Assistant context

`[Narrative Knowledge Graph]` block — **scene-scoped** (only emits when a scene
is open, keeping it cheap): top related PSYKE, connected scenes, risks, and an
undefined-term note. Capped; deterministic; no LLM/DB write during assembly; no
cross-project leak; no full graph dump. Disable via
`include_knowledge_graph_in_assistant_context`.

## Dashboard / Decision Radar

`build_graph_decision_cards` produces deterministic, traceable cards — isolated
PSYKE/element, scenes with no PSYKE links, undefined note terms, weakly-connected
plot blocks, many inferred edges to review, a theme not tied to scenes, a
risk touching a central node. Surfaced via the `Generate Decision Cards from
Graph` Logos action (kept as a dedicated feed so the core 10N radar contract —
capped at 10, fixed card ids — is unchanged). No AI; no automatic fixes; actions
route through existing safe systems.

## Guided Workflows

A mode-agnostic **Knowledge Graph Cleanup** template (build → review orphans →
confirm inferred edges → connect notes → clean structure → review scene
neighborhood before rewrite). The workflow guides cleanup but mutates nothing
automatically; PSYKE-relation creation / edge confirmation require confirmation.

## Refresh / project switch

Reads are per-`project_id`, so no stale graph leaks across a switch. The graph
rebuilds on demand (no background LLM scan). Persisted confirm/hide state is
project-scoped. The UI request identity includes project, focus, depth, limit,
and inferred-edge mode; a delayed response from a previous project or
superseded focus request cannot repopulate the active panel. Runtime validation
also rejects malformed graph payloads and dangling references before render.

## Limitations & deferred

- The implemented Graph UI remains a bounded Project Map/neighborhood slice;
  richer graph modes are not yet exposed.
- Node size currently uses explainable full-project degree; Story Gravity
  sizing and the story-order flow overlay remain part of the richer Graph pass.
- No force-directed render.
- No external graph DB / Neo4j, no cloud sync, no collaboration, no AI-only
  semantic inference, no unbounded whole-project expansion.
- Centrality = plain degree (explainable), not PageRank.
- Undefined-term detection is heuristic (capitalized proper-noun candidates).
- Timeline = manuscript scene order (no separate timeline table in this build).

## Next recommended phase

Extend the bounded surface with richer Structure, Risk, Revision Impact,
Confirmed-only, and Inferred+Confirmed modes, Story Gravity sizing, and the
story-order flow overlay; optionally wire graph decision cards directly into
the Dashboard's radar panel.

## Semantic Continuity (Phase 10Q)

The Semantic Continuity Engine (docs/SemanticContinuityEngine.md) builds on this
graph + PSYKE + scenes to detect contradictions, missing transitions and
unresolved commitments, and to validate proposed rewrite / controlled-apply
changes before they become canonical. Dedicated Continuity-Risk / Character-State
/ Setup-Payoff Graph visualization modes remain deferred beyond the initial
Project Map/neighborhood slice.
