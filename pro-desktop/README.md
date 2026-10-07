# @logosforge/pro-desktop

LogosForge **Studio (Pro)** — the Electron desktop shell. It owns no UI of its
own: it **spawns the logosforge core API** and composes the
`@logosforge/pro-shared-ui` panels into a workspace, injecting a real
`ApiClient` (`createHttpApiClient`) and a desktop `PlatformAdapter`.

## Layout

```
electron/                 main process (CommonJS → dist-electron/)
  core-manager.ts         connect to / spawn `python -m logosforge.api --mode desktop`
  mcp-runtime.ts          private runtime descriptor for the packaged MCP gateway
  file-manager.ts         open/save dialogs + per-project layout persistence
  preload.ts              flat `window.logosforge` bridge (contextBridge)
  main.ts                 window + IPC + lifecycle
renderer/                 the React app (Vite)
  src/App.tsx             StudioProvider + createHttpApiClient + the panels
  src/platform.ts         PlatformAdapter over the preload bridge
```

The renderer registers dirty scenes and editable Project, Outline, Note, PSYKE
and Structure fields with a shared save barrier. Panel, structure-tab and project
navigation commit active inline fields, then drain that barrier before changing
context; Electron's window-close/quit handshake waits for it too. Sensitive AI
Settings remain explicit: navigation stops until the writer chooses Save or
Revert. A failed close-time save offers Retry, Keep Open, or an explicit Close
Without Saving choice.

Scene DTOs carry a content-addressed revision. Manuscript autosave, Controlled
Apply and Voice return that token on updates and reject a stale write with an
explicit conflict instead of silently replacing newer text. The editor preserves
the local draft and offers deliberate Reload or Overwrite recovery.

The Format Structure authoring tabs use keyed latest-request gates. Scene, page,
panel, Stage and Series loads publish only if they still belong to the current
selection; multi-endpoint views update as one snapshot, and load/mutation errors
remain visible instead of being rendered as empty data.

That rule also covers the main authoring surfaces: scene and outline
create/delete/reorder failures are shown in place, manual Save reports a failed
barrier, and composite Bible/Series views never translate a failed secondary
endpoint into a believable empty relation, progression, season or arc list.

Destructive controls use a consistent two-step inline confirmation. It covers
Outline nodes, Notes, PSYKE entries/relations/progressions, Characters and the
Graphic Novel, Stage and Series records in Format Structure. The first click
only arms confirm/cancel controls and stops row-click propagation; unlinking and
removing a scene from the non-destructive Timeline remain immediate.

Interactive cards, filters, toggles and authoring commands use native controls
(or a keyboard-complete ARIA button for spatial cards), with visible
`:focus-visible` styling and accessible names for every form field. The AI dock
divider is an adjustable separator: Left/Right resize it, Shift changes the step,
and Home/End jump to its limits. Pointer cancellation restores drag state, and
the shell honors the operating system's reduced-motion preference. The command
palette and Controlled Apply are true modal dialogs: focus stays inside while
open, the workspace behind them is inert, Escape closes when safe, and focus
returns to the originating control.

Runtime rendering faults are isolated at the workspace, active-panel and
individual-AI-tool levels. A failed area shows its actual error and a local Retry
action instead of blanking the entire application; switching project/panel also
resets the corresponding recovery boundary.

The desktop host also reports synchronous window errors and genuinely unhandled
Promise rejections in a dismissible banner. Intentional `AbortError`/`ABORT_ERR`
cancellation is ignored, repeated identical faults are rate-limited, and errors
already captured by a panel boundary are not reported twice.

Long-lived browser resources have explicit ownership. Bootstrap retries are
cancelled or invalidated when the core identity changes, late startup responses
cannot populate the replacement core, and the initial blank-project decision is
shielded from concurrent UI actions. Shared mounted-state guards reopen correctly
during React Strict Mode's effect probe. Voice capture releases every media track,
audio node and `AudioContext` after stop/cancel and after partial setup failures.

The production workspace remains non-interactive until its current Core has
published an authoritative project. Same-Core project refreshes are
latest-request-wins, writing-mode changes remain owned by the Core generation
that started them, and one-shot navigation targets are routed only to their
owning mounted panel. Decision Radar deep links therefore move keyboard focus to
the exact authoritative Graph node or Continuity issue instead of letting a
hidden surface consume or steal the handoff. Continuity repair also reselects
Billy, preserves an existing draft behind an explicit choice, and rereads the
exact repair Scene before sending so its Controlled Apply snapshot is current.

The desktop host records the last active project in its stable Electron user-data
directory and reopens it through the normal project handoff lifecycle on the next
launch. Corrupt, obsolete, or missing session state falls back to the first project
without blocking the workspace.

The HTTP client owns an abort controller and every live transport. Replacing the
core disposes the old client after a StrictMode-safe lease handoff, aborting its
in-flight fetches and closing polling/SSE. Transport limits are classed by work:
health 5 s, ordinary reads 30 s, and explicitly long AI/voice/export requests
15 min. Mutations have no client-side abort by default because a timeout after a
server commit has an ambiguous outcome and can violate serialized PATCH order;
hosts can opt into a write limit, whose structured error warns users to refresh
before retrying.

Concurrent identical GETs are coalesced only while the network request is in
flight, which prevents the always-mounted panels and AI tools from multiplying
the same scene/bible refresh. Every consumer receives a deep-cloned JSON graph,
there is no settled-response cache, and mutations invalidate coalescing both when
they start and when they settle so a post-write refresh cannot attach to a stale
pre-write request.

The continuous Manuscript scales without mounting one ProseMirror instance per
scene. One `IntersectionObserver` keeps visible/nearby scenes live; the active
scene, six most-recently used scenes, and every dirty/saving/error scene stay
mounted. Other scenes remain fully readable as lightweight text and activate on
click or jump. Their React state and save queues never unmount. Off-screen layout
also uses `content-visibility`, and only the active scene's draft is lifted for
FORMAT preview instead of duplicating the entire manuscript in parent state.

AI panels use the same generation discipline: Billy chat generations, Logos
catalog/run/proactive scans, Quantum/Counterpart results, Grammar checks and the
Adaptive strip reject stale responses. PATCH requests to one resource are
serialized by the HTTP adapter, while the core writes global AI settings through
an atomic, locked settings snapshot. Core validator profile v3 also rejects empty
direct output and unmistakable cross-mode Dialogue formatting before display,
cache, or apply; a direct-writing Chat request without a target returns a short
clarification instead. The deterministic Writer QA release gate covers 69
section/mode/action/target/response scenarios and currently reports zero findings.

Long-running Extraction jobs are resumable across panel remounts and explicitly
cancellable; a late cancelled result is discarded instead of becoming
applicable. Dexter's Room serializes its stateful operations per project and its
shared speech model globally. Microphone startup, transcription and Voice
preview/apply operations participate in the project handoff barrier. Session
history is canonical in the core, including cleanup, Billy and commit state, so
reopening the panel cannot revert the visible transcript state.

The rail's Project mode is the selected project's persisted narrative engine,
not a display-only preference. Creating a project stores that mode in the core;
switching projects changes the shell and editor mode atomically. The core permits
mode changes only while a project is an empty scaffold. The workspace is also
remounted at the project boundary, so drafts, chat results and loading-state data
from one project can never appear inside another.

Each project also owns a versioned workspace layout. Left, center, right and
bottom docks keep independently active tab stacks; panels can be moved by
drag/drop or keyboard-accessible controls, torn into modeless floating windows,
resized, minimized, collapsed, restored and docked again. Focus is a
non-destructive manuscript-only projection of the saved Cockpit arrangement.
Layout writes use the same project handoff/close barrier as editor drafts and an
atomic host-side file replacement. Each normal replacement retains the prior
generation; shared UI validates primary and backup separately, repairs from a
known-good backup without rotating corruption over it, and leaves newer-schema
layouts untouched. Moving a panel changes its grid placement under one stable
React parent, so editor and AI session state does not remount during workspace
rearrangement.

The packaged Windows, Intel macOS and Linux release gates also launch the
unpacked native app through Playwright's Electron transport with an isolated
profile. Linux runs that journey in one 1600x1000 Xvfb display while retaining
Chromium's sandbox; the harness rejects any packaged launch carrying
`--no-sandbox`.
`npm run test:packaged-workspace` uses real mouse input to author and arrange a
Canvas Plot, tear off, move, resize, minimize, restore and dock a panel, resize
and collapse a dock, close through the production save handshake, then relaunch
the same project and verify the persisted board, placement and dock width.
Failure diagnostics stay inside the explicitly validated run directory;
successful temporary runs remove only that exact directory. Windows failures
and Linux failures are uploaded by Actions, while Monterey failures are retained
under the self-hosted runner's `macos-build-drop/` directory. Successful macOS
candidates are transferred without JavaScript actions through a private,
digest-addressed GHCR handoff. A hosted Ubuntu job validates the DMG and its
source-bound evidence before creating the normal Actions downloads used by the
hosted release publisher.

The shared package + contracts are aliased straight to source (vite + tsconfig
`paths`), so there's no build/link step in dev and HMR works across the
monorepo. Their own dependencies still need installing in a fresh checkout.

## Run (dev)

Prereqs: **Node.js 22.12+**, plus the **logosforge core venv** at
`../logosforge/venv`. The app falls back to system `python` if the venv is not
present, so the `logosforge` package must then be installed there.

```bash
# From the repository root
(cd logosforge-ui-contracts && npm install)
(cd pro-shared-ui && npm install)
(cd pro-desktop && npm install && npm run dev)
```

This starts Vite (`:5173`) and Electron together. On launch the app starts a
per-process authenticated core from the core's venv, verifies its one-time
service nonce, then auto-selects its first project. If default `:8765` is
occupied, it selects another free local port; an explicit `LOGOSFORGE_PORT`
remains strict. The renderer talks to the verified core directly — no proxy.

Env overrides: `LOGOSFORGE_PORT`, `LOGOSFORGE_HOST`, `LOGOSFORGE_CORE_DIR`,
`LOGOSFORGE_PYTHON`. `LOGOSFORGE_HOST` is a source-development escape hatch for
experimental LAN access; production and packaged launches always bind the core
to `127.0.0.1`.

## Packaged Codex / MCP bridge

Native packages include a small console MCP companion. Start the Pro GUI once;
it atomically installs/updates that companion under the stable per-user
`LogosForge Pro/mcp/` directory, including when the GUI itself is a portable
EXE or AppImage. While Pro is running it publishes the dynamic loopback URL and
random API token through a private, versioned runtime descriptor only after
core identity verification. Configure Codex to launch the companion directly;
no token or changing package-extraction path belongs in Codex configuration.
Writes remain disabled unless the MCP client explicitly sets
`LOGOSFORGE_MCP_ALLOW_WRITES=1`.

Gateway version 1.11.0 keeps the surface at 46 named tools. In addition to
paged/filterable comment-thread reads and revision-bound Reply/Resolve/Reopen proposals, it can
read the canonical Timeline, Canvas Plot, and bounded Narrative Knowledge Graph
plus the deterministic Semantic Continuity report, and propose strict guarded
commands for all four transactional surfaces. Knowledge Graph tools also page
through the complete hidden-edge restore queue. A Continuity proposal can Defer,
Dismiss, or Resolve one open issue and must bind both the report revision and the
exact finding fingerprint. It changes review status only; manuscript repair
remains a separate Billy → Controlled Apply flow. The core rechecks board,
graph-review, Continuity review/finding, and comment revisions atomically with
apply, rejecting intervening changes. Canvas node deletion
removes incident Canvas links but preserves linked manuscript scenes. Timeline
lane deletion preserves events as Unassigned and event removal preserves the
manuscript scene. The same Timeline read/proposal tools now expose persisted
scene links and scene-to-Act/Chapter links plus six create/update/delete
commands. Scene links display their stored source→target orientation but remain
unique per unordered scene pair; dangling structure targets are explicit and
repairable. New link creation requires current Timeline events, while dormant
legacy rows remain readable, editable, and deletable. Timeline receipt payload
v2 records relationship outcomes and retains v1 decoding.

HTTP 1.15.0 adds Phase 7C read-only `story_flow` and discriminated
`mode_projection` data to that same Timeline snapshot. Pro renders an accessible
numeric/semantic ribbon behind a **FLOW** toggle, a **Story Pulse** summary,
contiguous warning spans, per-event scene-type labels, and a read-only **MODE
LENS** for Novel, Screenplay, Graphic Novel, Stage Script, or Series. Flow points
map one-to-one to effective Timeline events/order and exclude off-Timeline
scenes. The analysis uses English keywords and simple markers or a manual
`tension:N` tag, so it is guidance rather than semantic truth. No schema
migration, Timeline command/topology revision change, or receipt v2 change was
introduced. The MCP read carries the same data without adding to the 46-tool
surface; mode-lens text is project data, never agent instructions.

HTTP 1.16.0 adds Phase 7D durable live-event recovery for changed Timeline,
Canvas Plot, Knowledge Graph, Semantic Continuity, and Guided Workflow
commands. A compact invalidation row commits atomically with each mutation and
receipt; the single-process broker reconciles and acknowledges pending rows
after commit and at API-process startup. Poll responses expose
`broker_instance_id` plus a bounded-ring reset flag, SSE sends a full
`connected` message (including on a live ring gap) and ids for domain events,
and Pro refetches authoritative surfaces after recovery, broker replacement,
cursor regression, or truncation. Token-checked acknowledgement distinguishes
reused SQLite row generations, and live invalidations prevent a post-boundary
refetch from joining a stale in-flight GET. Legacy mutation routes remain best-effort;
this is not multi-process fan-out or a background-delivery/LAN guarantee. MCP
remains 1.11.0 with the same 46 tools. Full-suite and packaged Phase 7D
validation are pending.

Timeline, Canvas Plot, Knowledge Graph, and Continuity proposals use their
opaque proposal id for a durable core receipt, so an
ambiguous apply can recover the exact committed outcome across an MCP companion
restart without duplicating the command. A proven family-specific receipt miss
permits exactly one resend of that identical proposal/key; later ambiguous
outcomes are receipt-only. Unknown proposal recovery probes all four receipt
families and fails closed if more than one matches. Other proposal families keep
their terminal indeterminate-response rule.
Canvas reads use bounded node-body previews by default and require an explicit
`include_bodies` opt-in for complete card text. All project text is
user-authored data, never agent instructions.
Anchored comment creation, anchor/root-body edits, and thread/reply deletion
remain in the Pro UI and are not MCP tools.

The required packaged-Windows CI gate builds the core and MCP sidecars from a
clean checkout, verifies that the native companion is present in the Electron
package, then exercises authenticated reads, applied Timeline, Canvas Plot, and
Knowledge Graph commands plus an applied fingerprint-bound Continuity status
decision, with rejected stale siblings; durable receipt recovery for all four
surfaces from a fresh MCP process; Canvas, graph-review, and Continuity-status
persistence across that restart; a revision-guarded comment reply and
resolution; stale-write rejection; and single-use proposal replay protection.
The frozen-companion smoke separately verifies all 46 discovered tools and that
an exact Continuity proposal is non-mutating. The optional Codex subprocess used
by the packaged smoke remains read-only.

The exact Phase 7B `cfd4c7b` AppImage passed the full packaged workspace + MCP
journey on a clean Ubuntu 22.04 VM. The HTTP 1.15.0 / MCP 1.11.0 Phase 7C source
and its Pro FLOW / MODE LENS UI are implemented. The exact `33feac9` source also
passed the hosted Windows packaged pointer workspace, restart-persistence,
frozen-companion, and cross-product journey. Current-source Linux/Xvfb and Intel
macOS journeys remain pending; these statements are not a published-release
claim.

The packaged workspace acceptance exercises the production renderer rather than
the preview harness. It crosses the manuscript save barrier, follows Radar into
exact Graph and Continuity evidence, switches from Logos back to Billy, sends a
deterministic offline repair request, confirms its revision-bound Controlled
Apply Scene update, resolves the Continuity finding, authors Canvas content with
real pointer input, mutates the dock layout, closes through the save handshake,
and verifies all durable state after relaunch. Windows, Linux under Xvfb, and the
Intel macOS 12 runner invoke this same script. The exact Phase 7B `cfd4c7b`
AppImage passed it together with the packaged MCP journey on a clean Ubuntu
22.04 VM. The exact `33feac9` source passed the hosted Windows version of the
same journey; current-source Linux/Xvfb and Intel macOS validation remain
pending.

See [`../logosforge/docs/MCP_GATEWAY.md`](../logosforge/docs/MCP_GATEWAY.md) for
Codex configuration and the proposal/review/apply safety model.

## Status

- **Workspace** is a dockable, keyboard-accessible four-region shell with
  modeless floating panels, per-project versioned persistence, Focus/Cockpit
  projections and safe reset. Window bounds, z-order, minimization and every
  dock's active/collapsed state survive project changes and application restarts.
  At the supported 1024 px minimum window width, the Studio chrome reflows into
  two rows so the command palette, Adaptive mode, Focus/Cockpit controls and
  local-save status all remain visible and operable.
- **Packaging** is configured for self-contained Windows installer/portable,
  macOS 12+ Intel DMG, and Linux x64 AppImage builds. The Monterey build uses
  Electron 43, the final Electron line that supports macOS 12. Electron starts
  a per-process authenticated core and stores the SQLite database in the app's stable
  user-data directory. The same packages install a stable,
  descriptor-authenticated MCP companion for local Codex orchestration.
- **Phase 7C source status:** HTTP 1.15.0 and MCP 1.11.0 expose the read-only
  Timeline story-flow and mode projections, and Pro renders FLOW and MODE LENS.
  The exact `33feac9` source passed the hosted Windows packaged journey;
  Linux/Xvfb and Intel macOS remain pending.
- **Phase 7D source status:** HTTP 1.16.0 implements an atomic pending-event
  outbox and restart reconciliation for the five transactional command
  families. Pro recognizes broker replacement and recovery as authoritative
  refetch boundaries. Full validation and packaged evidence remain pending;
  legacy routes, multi-process fan-out, and independent background delivery are
  not covered. MCP remains 1.11.0 with 46 tools.
- The renderer uses bundled/local assets and runs under a restrictive CSP.
