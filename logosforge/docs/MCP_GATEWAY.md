# LogosForge Pro MCP gateway

The Pro MCP gateway lets a local MCP client, including Codex, inspect and
orchestrate a LogosForge project through the supported FastAPI boundary. The
gateway never opens the SQLite database itself. It uses stdio for MCP traffic
and HTTP only for the configured LogosForge API.

The gateway is intentionally stateful. Reads are immediate, while every
project mutation follows this lifecycle:

1. The client reads the current project data and its revision or state guard.
2. A focused `logosforge_propose_*` tool validates the intended mutation and
   stores its exact HTTP method, path, body, project id, guard, and a bounded
   review/diff under an opaque proposal id.
3. The client presents that proposal for review. Proposing does **not** change
   the project.
4. `logosforge_apply_proposal` accepts only the proposal id. It rechecks the
   proposal's lifetime and stale-state guard, then applies the stored request.
5. A proposal is single-use. It cannot be replayed, and its payload cannot be
   replaced at apply time.

There is deliberately no generic “action + arguments + `confirmed=true`” MCP
tool. A boolean supplied by the same model that requested a change is not a
meaningful confirmation boundary.

## Installed LogosForge Pro

The native Pro package contains a console MCP companion. Start LogosForge Pro
once and wait for its workspace to connect. The app atomically installs or
updates the companion in its stable per-user data directory, including when
Pro itself is a portable EXE or AppImage. While the GUI is running it writes a
private runtime descriptor containing the dynamic loopback port and
per-process token. The descriptor is created only after nonce-bound core
health succeeds and is removed during normal shutdown.

That descriptor bearer authenticates ordinary API/MCP requests. It is not the
separate live-context publication capability, which is shared only between
Electron main and its core API process and never appears in the descriptor,
renderer, health response, or MCP configuration. MCP clients can read validated
live connector results but cannot publish snapshots or choose their source and
revision.

Launch that companion from an MCP client. The descriptor, both owning process
ids, and the live core identity are revalidated before MCP starts. No API
token or temporary package-extraction path belongs in client configuration.

## Source checkout

Install the core with the optional MCP dependency:

```powershell
cd C:\path\to\logosforge-monorepo\logosforge
python -m pip install -e ".[mcp]"
```

Start the LogosForge API in one process. Use the same token in both processes
when writes are enabled:

```powershell
$env:API_AUTH_TOKEN = "replace-with-a-long-random-token"
python -m logosforge.api
```

The MCP client starts the stdio server. Running it directly is useful only for
diagnosis because stdin and stdout belong to the MCP protocol:

```powershell
$env:LOGOSFORGE_API_URL = "http://127.0.0.1:8765"
$env:LOGOSFORGE_API_TOKEN = "replace-with-the-same-token"
$env:LOGOSFORGE_PROJECT_ID = "1"
$env:LOGOSFORGE_MCP_ALLOW_WRITES = "0"
python -m logosforge.librechat.mcp_server
```

`LOGOSFORGE_PROJECT_ID` is optional. A client can use
`logosforge_list_projects` followed by `logosforge_select_project` instead.

## Environment variables

| Variable | Default | Purpose |
|---|---:|---|
| `LOGOSFORGE_API_URL` | `http://127.0.0.1:8765` | Base URL of the Pro API. Loopback is required unless remote access is explicitly enabled. |
| `LOGOSFORGE_PROJECT_ID` | unset | Optional initial project id. It can be selected during the MCP session. |
| `LOGOSFORGE_API_TOKEN` | unset | Bearer token sent to the API. Required for writes by default. |
| `LOGOSFORGE_API_TIMEOUT` | `15` | HTTP request timeout in seconds. |
| `LOGOSFORGE_MCP_ALLOW_WRITES` | `0` | Server-side mutation gate. Set to `1` only for a reviewed write-capable session. |
| `LOGOSFORGE_MCP_REQUIRE_AUTH_FOR_WRITES` | `1` | Keep token authentication mandatory for mutation. |
| `LOGOSFORGE_MCP_PROPOSAL_TTL_SECONDS` | `900` | Lifetime of pending proposals. |
| `LOGOSFORGE_MCP_ALLOW_REMOTE` | `0` | Permit a non-loopback API URL. Remote mode also requires HTTPS and a token. |
| `LOGOSFORGE_MCP_CONNECTION_FILE` | unset | Private packaged-Pro runtime descriptor. The installed launcher supplies this automatically. |
| `LOGOSFORGE_MCP_REQUIRE_CONNECTION` | `0` | Fail unless a packaged runtime descriptor is configured. The installed launcher sets this to `1`. |

For the source-checkout form, the API itself must be configured to accept the same token. Do not put a real
token in a committed configuration file; prefer the process environment or a
local secret manager. Packaged descriptor mode rejects `LOGOSFORGE_API_URL` and
`LOGOSFORGE_API_TOKEN`: its nonce-verified endpoint and token are authoritative.

## Local Codex configuration

On Windows, point Codex at the companion installed under the Pro user-data
directory (replace the username or use the actual resolved absolute path):

```toml
[mcp_servers.logosforge]
command = "C:\\Users\\YOUR_NAME\\AppData\\Roaming\\LogosForge Pro\\mcp\\logosforge-mcp.exe"
args = []
required = true

[mcp_servers.logosforge.env]
LOGOSFORGE_MCP_ALLOW_WRITES = "0"
```

The equivalent default paths are
`~/Library/Application Support/LogosForge Pro/mcp/logosforge-mcp` on macOS and
`${XDG_CONFIG_HOME:-~/.config}/LogosForge Pro/mcp/logosforge-mcp` on Linux.
In every case the Pro GUI must already be running. `LOGOSFORGE_PROJECT_ID`
remains optional; tools can list and select a project during the session.

For a source checkout, Codex can launch the gateway directly over stdio. Add
an MCP server entry to your local Codex `config.toml`, adapting the Python
executable and checkout path to your machine:

```toml
[mcp_servers.logosforge]
command = "python"
args = ["-m", "logosforge.librechat.mcp_server"]
cwd = "C:\\path\\to\\logosforge-monorepo\\logosforge"
required = true

[mcp_servers.logosforge.env]
LOGOSFORGE_API_URL = "http://127.0.0.1:8765"
LOGOSFORGE_PROJECT_ID = "1"
LOGOSFORGE_API_TOKEN = "replace-with-the-api-token"
LOGOSFORGE_MCP_ALLOW_WRITES = "0"
```

Start with `LOGOSFORGE_MCP_ALLOW_WRITES = "0"` and verify reads first. For a
write session, set it to `"1"` and configure Codex to require approval for the
`logosforge_apply_proposal` tool. Proposal tools are review preparation; only
the apply tool mutates project state.

For a one-off validation, Codex can also be launched with an isolated config
using `codex exec --ignore-user-config` plus equivalent `-c
mcp_servers.logosforge...` overrides. This avoids changing the user's normal
Codex configuration.

## Tool surface

The exact schemas are reported by MCP discovery. The surface is grouped by
responsibility rather than exposing arbitrary HTTP requests. Gateway version
1.10.0 keeps the surface at 46 named tools:

- Project and manuscript reads: list/select project, project context and
  snapshot, scene list/full scene, outline, notes, complete comment threads,
  search, events, and export. Comment listing is paged, can exclude resolved
  threads, and returns the revision for every thread.
- Story intelligence reads: PSYKE entries, characters, relations,
  progressions, diagnostics, the canonical revisioned Timeline and Canvas Plot
  boards, bounded Knowledge Graph maps plus the paged hidden-edge queue, and the
  revisioned deterministic Semantic Continuity report.
- Desktop-aware reads: live panel/context, current scene, and current selection.
  Packaged Pro publishes authenticated, revision-ordered snapshots; they report
  unavailable (or a safe no-fresh-scene error for current scene) when no
  matching update arrived within 30 seconds, after project close, when no scene
  is open, or when the selected MCP project differs. Selection text is capped
  at 20,000 characters
  and must be treated as untrusted project content. A bare
  `python -m logosforge.api` has no editor publisher, so these reads remain
  unavailable unless the API is hosted by the legacy embedded desktop or an
  authorized desktop publisher.
- Focused proposals: create a project or scene; patch a revisioned scene;
  create/patch outline nodes, PSYKE entries, relations, progressions, and
  notes; reply to a comment as `MCP assistant`; Resolve/Reopen a comment; or
  submit one strict revision-bound Timeline, Canvas Plot, Knowledge Graph, or
  Semantic Continuity status command.
- Proposal management: list, inspect, discard, and apply a stored proposal.

The three comment-specific tools are `logosforge_list_comments`,
`logosforge_propose_comment_reply`, and
`logosforge_propose_comment_resolution`. The last tool proposes either Resolve
(`resolved: true`) or Reopen (`resolved: false`); neither proposal tool changes
the thread until `logosforge_apply_proposal` succeeds.

`logosforge_search(query)` uses the same typed, project-scoped search endpoint
as the Pro workspace. It returns bounded matches from scenes, notes, PSYKE, and
user-authored comment threads without loading those domains separately through
the gateway. Comment matches retain their exact thread `revision` and
`resolved` state so an agent can follow with a current full-thread read before
preparing a proposal. The selected MCP project is authoritative; callers cannot
override it with a project id in the search arguments.

Scene edits require the current scene `revision`. The API performs the final
atomic stale-revision check, so newer prose cannot be silently overwritten.
Comment reply and Resolve/Reopen proposals likewise require the exact
per-thread `revision` returned by a current read. The API checks that revision
inside the same database transaction as the mutation, so a root edit, reply,
resolution change, reanchor, or deletion made after the read makes apply fail
instead of overwriting or appending to stale context. Reread the thread and
create a fresh proposal after a conflict.

Timeline orchestration uses `logosforge_get_timeline` followed by
`logosforge_propose_timeline_command`. The proposal tool accepts exactly one of
12 commands: create/update/delete a lane, place/remove a scene event, switch
between structural and custom ordering, create/update/delete a scene link, or
create/update/delete a scene-to-structure link. No new MCP tool was added for
Phase 7B; the existing read and proposal schemas were extended. Command `index`
values and lane
`order_index` values are zero-based; the snapshot's event `order_index` is a
one-based display value. Every command
must set `expected_revision` to the exact 64-character `revision` returned by
the current Timeline read. Proposal creation validates the target and produces
a bounded before/after review but does not mutate the project.

The Timeline snapshot includes persisted `links` and `structure_links` in the
same coherent revision as lanes, events, and off-Timeline scenes. Scene links
use one of `custom`, `causality`, `setup_payoff`, `echo`, `conflict`, or
`dependency`; the stored source→target orientation is returned, while the
legacy uniqueness rule permits only one row for an unordered scene pair
regardless of direction or type. Structure links target an `act` or `chapter`
by name and return `target_exists`; false means the link is intentionally kept
visible as dangling for warning, repair, or deletion. Creating a scene link
requires both endpoints to be current Timeline events, and creating a structure
link requires its source to be a current event. Dormant legacy relationship
rows remain readable and may be updated or deleted.

The core repeats the revision comparison atomically with apply. That revision
tracks Timeline topology, persisted relationships, and immutable
project/scene/lane/link identity, preventing
stale proposals from targeting replacement rows whose numeric IDs were reused.
Unrelated prose and scene-title edits intentionally do not stale a safe
Timeline command. Deleting a lane keeps its events as Unassigned; removing an
event keeps the manuscript scene off-Timeline. Both operations are identified
as destructive in the proposal review so their preservation effects are clear.

Canvas Plot orchestration uses `logosforge_get_canvas_plot` followed by
`logosforge_propose_canvas_plot_command`. The proposal tool accepts exactly
one of nine commands: create/update/delete a node, link, or frame. Node
`index` values are zero-based. Every command must set `expected_revision` to
the exact 64-character `revision` returned by the current Canvas Plot read.
The read returns bounded node-body previews, lengths, and SHA-256 digests by
default; pass `include_bodies: true` only when complete Canvas card text is
actually required. Board topology, geometry, links, frames, and revision are
always returned.
Proposal creation validates target IDs, scene ownership, index bounds,
self-links, duplicate undirected links, and no-op updates. It stores the exact
unwrapped command and produces a bounded before/after review without changing
the board.

Core repeats the Canvas Plot revision comparison inside the same database
transaction as the mutation. The revision covers the persisted nodes, links,
frames, their ordering and immutable creation identities, so stale proposals
cannot partly apply or target replacement rows whose numeric IDs were reused.
The local pan/zoom viewport is intentionally not project data and neither
appears in the MCP snapshot nor changes the board revision. Deleting a node
also deletes its incident Canvas Plot links (including hidden same-project
legacy rows) but never deletes its linked manuscript scene. Deleting a link
also cleans up hidden same-project legacy reverse/duplicate rows for that
undirected pair. Deleting a frame does not delete nodes, links, or scenes. All
three delete operations are identified as destructive in the proposal review.

Knowledge Graph orchestration uses `logosforge_get_knowledge_graph` for a
bounded Project Map or focused one-/two-hop neighborhood and
`logosforge_get_knowledge_graph_hidden_edges` for deterministic pages through
the complete restore queue. Follow either current read with
`logosforge_propose_knowledge_graph_command`. Its exact directional edge
identity is `(source, target, edge_type)`, and every command must carry the
current 64-character review `revision`. The three supported commands are
`confirm_edge`, `hide_edge`, and `unhide_edge` (Restore). Confirm and Hide are
valid only for a visible unconfirmed inferred edge; Restore is valid only for a
persisted hidden decision. Proposal creation performs the same eligibility
preflight and stores the exact command plus bounded evidence and an explicit
effect review, but does not mutate the graph. An `unhide_edge` proposal must
also provide the
non-negative `hidden_edge_offset` of the current hidden-edge page containing
that identity. The gateway refetches a 100-edge page at that offset, verifies
its project and exact revision, and refuses a Restore target absent from that
page. The offset is rejected for Confirm/Hide.

Core rechecks that review revision and edge eligibility inside the same
transaction as the mutation and durable receipt. The revision deliberately
covers the persisted review layer rather than every source used to rebuild the
live derived map. Recovery therefore returns the current coherent Project Map
while preserving the original command's `applied_revision`. The complete
hidden queue remains available even when the default Project Map is truncated
or an inferred basis later disappears.

Semantic Continuity orchestration reuses
`logosforge_get_story_diagnostics` with `report: "continuity"`, followed by
`logosforge_propose_continuity_command`. The three commands are `defer_issue`,
`dismiss_issue`, and `resolve_issue`. Each must copy the report's exact
64-character `review_revision`, the open issue's canonical 16-character id, and
its 64-character `review_fingerprint`. The revision guards the complete
persisted review layer; the fingerprint binds the exact derived finding,
including its wording, evidence, severity/confidence, suggested action, and
related scenes/nodes. A stable issue key does not make changed evidence safe to
approve. Proposal creation rereads the report, requires one exact open match,
and stores a bounded issue/effect review without changing status.

Applying a Continuity proposal changes only the issue's persisted status from
`open` to `deferred`, `dismissed`, or `resolved`. It never edits manuscript or
other story content, invokes an LLM, or performs a repair. Pro's separate
**Repair with Billy** handoff and Controlled Apply confirmation remain the prose
workflow.

Timeline, Canvas Plot, Knowledge Graph, and Continuity proposals have durable core
receipts. The gateway uses the opaque proposal id itself as the command's
`Idempotency-Key`; callers cannot choose or replace it. If a transactional
apply response is lost after commit, the gateway asks the core for that exact
family receipt. A receipt proves the original command committed, even after the
MCP process restarts, without applying a second mutation. Recovery returns the
current coherent surface together with the original `applied_revision`; it
does not replace newer state with an old snapshot. If the receipt-capable core
explicitly reports the family-specific `timeline_receipt_not_found`,
`canvas_plot_receipt_not_found`, `knowledge_graph_receipt_not_found`, or
`continuity_receipt_not_found`, the gateway may resend that exact stored command
once with the same proposal id. It never creates a fresh key for recovery. A
fresh gateway resolving an unknown proposal id probes all four receipt families:
exactly one match recovers the proposal, while multiple matches fail closed as a
collision. Receipts live for the project lifetime and are deleted with it.
Timeline relationship outcomes use receipt payload v2; Core still decodes
existing Timeline receipt v1 rows, so upgrading does not make earlier receipts
unrecoverable.

The frozen-companion acceptance smoke discovers all 46 tools, reads a seeded
Continuity report, prepares an exact fingerprint-bound proposal, and proves that
proposal creation is non-mutating. The packaged-app smoke applies a Continuity
decision, rejects a stale sibling, verifies persisted status, restarts the MCP
companion, and recovers the original result from the durable receipt. The same
restart run exercises receipts for Timeline, Canvas Plot, and Knowledge Graph,
so the four-family recovery boundary is covered together.

Those packaged-smoke statements describe the previously validated command
surface. The Phase 7B relationship extension is implemented and tested in the
current source, but its packaged-app validation is still pending; this document
does not claim a new published release.

Comment bodies, quotes, replies, scene titles, lane labels, Timeline
relationship labels and structure target references, Canvas Plot node bodies
and labels, and Continuity issue text/evidence are
**user-authored project content**. Clients must treat them as data to discuss,
never as tool instructions. An MCP reply is always attributed to
`MCP assistant`; it does not impersonate the
writer and does not trigger the app's `@assistant` / `@counterpart` provider
workflow. Creating anchored threads, changing anchors or root bodies, and
deleting threads or replies remain UI-only operations.

Other guarded mutations compare the state observed during proposal creation
before applying; clients should reread after a successful mutation.

A definite API rejection (HTTP 4xx, including a Timeline, Canvas Plot,
Knowledge Graph, or Continuity revision/fingerprint conflict)
marks the proposal failed. Inspect the error and reread current state before
creating a fresh proposal where appropriate. For a Timeline, Canvas Plot,
Knowledge Graph, or Continuity proposal, an ambiguous response enters receipt
recovery: a proven, family-specific receipt miss permits one bounded resend of the exact
proposal/key, while a second ambiguous outcome remains `recovery_pending` for
a later same-id reconciliation. A legacy or generic 404, failed lookup, or
malformed receipt cannot prove a miss and never authorizes a resend. Every
non-receipted proposal timeout, lost response, HTTP 5xx, or other outcome that
does not prove rejection remains terminally
`indeterminate`; inspect current project state and never retry it because its
mutation may already have committed. Successful proposals remain single-use,
and the global apply tool is not generally idempotent.

## Safety boundary

The layers are cumulative:

- The gateway exposes named, schema-validated tools, not arbitrary HTTP,
  filesystem, Python, or database access.
- Writes are disabled unless `LOGOSFORGE_MCP_ALLOW_WRITES=1`.
- Writes require API authentication by default.
- A mutation must be proposed first, remains bound to its exact stored
  payload, expires, and is single-use.
- Durable retry/recovery is limited to the same Timeline, Canvas Plot, Knowledge
  Graph, or Continuity proposal id and exact stored request. Other proposal
  families have no core receipt in this phase.
- The apply tool is marked as mutating/destructive for MCP clients that honor
  tool annotations. Client approval is an additional safeguard; it does not
  replace server validation.
- Loopback is the default. Opt-in remote API access requires HTTPS and a token.

An MCP process is not a cryptographic out-of-band approver: a client that can
invoke tools may be able to request both proposal and apply. Keep the apply
tool behind Codex's approval policy, and enable writes only for sessions where
that risk is acceptable.

## Checkpoints, exports, and intentionally unexposed operations

Use the read-only project export before a large batch as a **manual
checkpoint**. It is a portable snapshot for inspection or recovery work, but
the gateway does not claim an automatic rollback transaction. Verify the
export before proceeding with consequential edits.

Manuscript import and delete operations are intentionally not exposed as MCP
tools. Comment creation, anchor/root-body editing, and thread/reply deletion
are also intentionally unavailable through MCP. Perform those operations in
LogosForge's own review-oriented UI/API workflow. Web releases remain a
separate deployment concern; the gateway does not publish or deploy a web
application.
