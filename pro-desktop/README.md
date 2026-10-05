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
an atomic, locked settings snapshot.

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

The packaged Windows and Intel macOS release gates also launch the unpacked
native app through Playwright's Electron transport with an isolated profile.
`npm run test:packaged-workspace` uses real mouse input to author and arrange a
Canvas Plot, tear off, move, resize, minimize, restore and dock a panel, resize
and collapse a dock, close through the production save handshake, then relaunch
the same project and verify the persisted board, placement and dock width.
Failure diagnostics stay inside the explicitly validated run directory;
successful temporary runs remove only that exact directory. Windows failures
are uploaded by Actions, while Monterey build-only failures are retained under
the self-hosted runner's `macos-build-drop/` directory.

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

Gateway version 1.5 exposes 42 named tools. In addition to paged/filterable
comment-thread reads and revision-bound Reply/Resolve/Reopen proposals, it can
read the canonical Timeline and Canvas Plot and propose strict revision-bound
commands for either board. The core rechecks board and comment revisions
atomically with apply, rejecting intervening changes. Canvas node deletion
removes incident Canvas links but preserves linked manuscript scenes. Timeline
lane deletion preserves events as Unassigned and event removal preserves the
manuscript scene. Timeline and Canvas Plot proposals use their opaque proposal
id for a durable core receipt, so an ambiguous board apply can recover the
exact committed outcome across an MCP companion restart without duplicating
the command. Other proposal families keep their terminal
indeterminate-response rule.
Canvas reads use bounded node-body previews by default and require an explicit
`include_bodies` opt-in for complete card text. All project text is
user-authored data, never agent instructions.
Anchored comment creation, anchor/root-body edits, and thread/reply deletion
remain in the Pro UI and are not MCP tools.

The required packaged-Windows CI gate builds the core and MCP sidecars from a
clean checkout, verifies that the native companion is present in the Electron
package, then exercises authenticated reads, applied Timeline and Canvas Plot
commands with rejected stale siblings, durable Timeline and Canvas Plot receipt
recovery from a fresh MCP process, Canvas persistence across that restart, a
revision-guarded comment reply and resolution, stale-write rejection, and
single-use proposal replay protection. The optional Codex subprocess used by
the smoke remains read-only.

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
- The renderer uses bundled/local assets and runs under a restrictive CSP.
