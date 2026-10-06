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

The canonical HTTP 1.9.0 read surface is
`GET /api/projects/{project_id}/knowledge-graph`. Its `view_mode` selects one of
four Core-owned projections:

- `project_map`: every canonical node and visible edge from available sources;
- `structure`: project/act/chapter/scene/plot-block/timeline-event nodes and
  `contains`/`belongs_to`/`precedes`/`follows` edges;
- `recorded_risk`: endpoints of recorded `risks`/`contradicts` evidence, not a
  prediction that the manuscript is safe or unsafe; and
- `revision_impact`: endpoints of revision-system `revises`/`risks` evidence.

`include_inferred` is an independent evidence scope for every view: false is
Confirmed only, true is Inferred + Confirmed. Core projects the complete graph
by both choices before focus traversal and response caps. A `focus_key` then
selects a one-/two-hop neighborhood inside that projection; a key outside it is
indistinguishable from an unknown key. Per-node `degree` is calculated across
the complete selected view before focus or truncation, so it can change when
the view or evidence scope changes. Responses carry exact
requested/returned/total counts, truncation state, and warnings for unavailable
source systems. Nodes and edges remain deterministic, project-scoped, and
endpoint-complete.

Every returned node has required nullable `story_gravity` in `[0,1]`, paired
with response-level `story_gravity_available`. Gravity is project-wide and is
bridged from the existing deterministic visual-graph calculation only when one
legacy node has one unique exact canonical identity: Scene by `(scene,id)`, Note
by `(note,id)`, PSYKE by `(psyke,id)`, or Act by `(act,name)`. It never equates a
Character/Place database row with a typed PSYKE entry and never guesses by
label. A successful calculation can therefore still leave unsupported or
ambiguous nodes null. Any construction/calculation failure returns
`story_gravity_available=false` with all values null while preserving the
canonical graph response; no partial gravity map or internal failure detail is
exposed. Hidden-edge pages use null node values and do not compute a separate
gravity map.

Derived manuscript-adjacency `precedes` edges carry a complete metadata tuple:
zero-based source `story_order_index`, full-manuscript `story_order_total`,
`story_order_band` (`beginning`/`middle`/`ending`), and `act_boundary`. This is
manuscript sequence, not causality. The edges remain likely/inferred unless a
writer confirms them, and the metadata is returned only when the edge survives
the active view, evidence scope, focus, and response bound.

Authoritative orphan and weak-link story diagnostics apply only to Project Map,
advertised by `story_diagnostics_available=true`. Specialty views return that
flag false with zero/empty story diagnostics; this absence must not be read as
"connected" or "risk-free." Every read still returns the project-global
`hidden_edge_count`, but specialty views do not inject hidden edges or their
endpoints into the projection. The complete restore queue is reachable through
deterministic, dense pages at
`GET .../knowledge-graph/hidden-edges?offset=&limit=`; it is independent of view,
evidence scope, focus, and caps, and each page contains its exact unique endpoint
nodes.

Every read also returns the same project-wide review `revision` semantics. The
token is computed in one SQLite snapshot from all persisted endpoint/edge rows
plus the project's id and immutable creation timestamp; changing `view_mode` or
`include_inferred` does not redefine it. It intentionally does not claim that
the legacy multi-extractor live graph is one database snapshot: source edits may
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

MCP gateway 1.8.0 exposes the same boundary through
`logosforge_get_knowledge_graph`,
`logosforge_get_knowledge_graph_hidden_edges`, and
`logosforge_propose_knowledge_graph_command`. Its read accepts the same strict
four-value `view_mode` and independent `include_inferred` evidence scope as the
HTTP surface, defaulting to Project Map, and returns the additive gravity and
story-order data without adding tools. Confirm/Hide proposal preflight and every
apply/recovery result map are deliberately pinned to Project Map. The hidden-edge
read takes bounded `offset`/`limit` arguments, so Restore preflight can find every
persisted hide decision rather than depending on the default map's diagnostic
subset. Each proposal stores exactly one `confirm_edge`, `hide_edge`, or `unhide_edge`
command under an opaque proposal id; only the shared reviewed apply tool can
mutate. Restore proposals additionally require the `hidden_edge_offset` from
the page containing the target. The gateway refetches that 100-edge page and
requires the exact project, revision, and directional identity before it stores
the proposal; Confirm/Hide reject the page-only offset. That proposal id is
also the Core `Idempotency-Key`. A lost apply can recover the exact durable
receipt, and a fresh MCP process can reconstruct the applied proposal while
returning the current coherent Project Map and original `applied_revision`.
Only a proved `knowledge_graph_receipt_not_found` permits one bounded
same-command/same-key resend; ambiguous or conflicting receipt evidence fails
closed.

## Graph section (UI)

The Pro Graph panel now renders the canonical, API-backed **Project Map**,
**Structure**, **Recorded Risk**, and **Saved Revision Impact** views. A separate
Evidence selector applies **Confirmed only** or **Inferred + Confirmed** to any
view. Structure isolates hierarchy and recorded order; Recorded Risk shows only
saved risk/contradiction evidence; Saved Revision Impact shows saved
revision-intelligence links. An empty specialty view is described as missing
matching evidence, never as proof that the story is connected or risk-free.

Node type, minimum-confidence, and source-system filters remain live on top of
the server projection; selecting a node can focus its one-/two-hop neighborhood
or publish context to Studio tools. The panel presents Core-authoritative orphan
and weak-link diagnostics only in Project Map, while the complete project-global
hidden-edge queue remains available from every view. Loading/error/empty/retry
states and explicit size-cap/truncation status cover every projection.

The **Node sizing** control defaults to **Story Gravity** and can switch to
**View Links**. Gravity sizing uses the project-wide bounded value directly;
nodes with no exact bridge use the neutral minimum, not their link degree, and
mapped values at or above 0.55 receive a halo. If Core reports gravity
unavailable, the requested gravity mode visibly falls back to view-scoped link
sizing. The inspector and accessible node names expose the effective basis and
the mapped percentage/null state.

The optional **Story-order flow** overlay draws curved returned manuscript-order
segments colored beginning→middle→ending (green→gold→violet), emphasizes act
boundaries, and reports gaps in the returned sequence. It consumes only Core
metadata on edges still present after the server projection and the UI's node,
confidence, and source filters. It does not resurrect missing edges: Confirmed
only normally removes the inferred chain, risk/revision specialty views exclude
it, and focused or capped results may show a partial/gapped chain. Empty overlay
status states this active-scope boundary and the legend explicitly says order is
not causality.

Explicit **Confirm / Hide / Restore** review actions remain backed by the same
transactional HTTP contract and project-wide review revision. The same guarded
review actions remain available to MCP clients through proposal/review/apply and
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
view mode, and evidence scope; a delayed response from a previous project or
superseded projection/focus request cannot repopulate the active panel. Runtime
validation also rejects malformed graph payloads, mismatched projection
metadata, and dangling references before render.

## Limitations & deferred

- The canonical panel exposes only the returned manuscript-order overlay, not
  the legacy visual graph's causal, Freytag-arc, or temporal-scrubber modes.
- Story Gravity is available only for unique exact Scene, Note, PSYKE, and Act
  bridges; unsupported or ambiguous canonical nodes deliberately remain null.
- No force-directed render.
- No external graph DB / Neo4j, no cloud sync, no collaboration, no AI-only
  semantic inference, no unbounded whole-project expansion.
- Centrality = plain degree (explainable), not PageRank.
- Undefined-term detection is heuristic (capitalized proper-noun candidates).
- Timeline = manuscript scene order (no separate timeline table in this build).

## Next recommended phase

Surface deterministic Knowledge Graph decision cards in the Dashboard Decision
Radar, preserving their traceable source evidence and adding graph deep links.

## Semantic Continuity (Phase 10Q)

The Semantic Continuity Engine (docs/SemanticContinuityEngine.md) builds on this
graph + PSYKE + scenes to detect contradictions, missing transitions and
unresolved commitments, and to validate proposed rewrite / controlled-apply
changes before they become canonical. Dedicated Continuity-Risk / Character-State
/ Setup-Payoff Graph visualization modes remain deferred beyond the four current
canonical views.
