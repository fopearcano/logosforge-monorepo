# LibreChat integration (optional advanced chat sidecar)

LibreChat is an **optional** advanced conversational workspace that LogosForge
can detect, connect to, embed (or open in the browser), and connect to the Pro
API through the LogosForge MCP gateway. It is **off by default**; LogosForge
behaves exactly as before until you enable it, and stays fully functional if
LibreChat is never installed.

It does **not** replace the existing **Chat** section, the AI Assistant, Billy,
Logos, COUNTERPART, inline editing, or any narrative-aware AI feature. A new
**LibreChat** button sits directly **below Chat** in the left sidebar.

---

## 1. Architectural boundary

| LogosForge (authority) | LibreChat (interface) |
|---|---|
| Narrative brain, project memory, context engine | Advanced general-purpose chat UX |
| PSYKE / story-bible authority | Conversation history, branching, agents, MCP, files |
| Safe **propose → confirm → apply** action authority | Provider selection (its own AI keys) |
| Owns the SQLite project database | **Never** touches the LogosForge database |

All project reads/writes continue to flow through the existing Python services,
FastAPI endpoints, DTOs, and the safe connector action layer. LibreChat is a
**sidecar service**, not a fork — LogosForge embeds a *view of* the running
LibreChat web app (or opens it in the browser); it does not vendor LibreChat's
React code or its infrastructure (MongoDB / Meilisearch / Docker / Redis).

```
┌────────────────────────── LogosForge (PySide6 + Python core) ──────────────────────────┐
│  Sidebar: … Chat · LibreChat                                                            │
│                                                                                         │
│  LibreChatView ──uses──> LibreChatService ──HTTP probe──> LibreChat (separate process)  │
│        │                       │                                                        │
│        └─ embedded QWebEngineView OR system browser ─────────────────────────────────►  │
│                                                                                         │
│  bridge.LogosForgeBridge (adapter boundary)  ──>  connector_registry / connector_executor│
│        (desktop/internal adapter)                         (the existing safe action layer)│
└─────────────────────────────────────────────────────────────────────────────────────────┘
                                   ▲
        LibreChat/Codex ──MCP stdio gateway──> Pro API (validated reads and proposals)
```

---

## 2. Configuration

Settings → **LibreChat** (persisted as flat `librechat_*` keys in
`~/.logosforge/settings.json`; see `logosforge/librechat/config.py`):

| Setting | Key | Default | Meaning |
|---|---|---|---|
| Enable integration | `librechat_enabled` | `false` | Master switch (off = no change to LogosForge). |
| Base URL | `librechat_base_url` | `http://localhost:3080` | Where LibreChat is served. |
| Instance mode | `librechat_mode` | `local` | `local` \| `remote` (informational/UX). |
| Auto-connect on launch | `librechat_auto_connect` | `false` | If a startup command is set, start it after launch. |
| Prefer embedded workspace | `librechat_prefer_embedded` | `true` | Embed via Qt WebEngine when available. |
| Open in external browser fallback | `librechat_browser_fallback` | `true` | Use the system browser if embedding is unavailable. |
| Startup command | `librechat_startup_command` | `""` | Optional local command to launch LibreChat (advanced). |
| Show sidebar button | `librechat_button_visible` | `true` | Hides the button **only** through this explicit setting. |

There is a **Test connection** button in settings. LogosForge stores **no
AI-provider API keys** for LibreChat — LibreChat manages its own providers.

---

## 3. Local vs remote connection modes

* **Local** (default): connect to `http://localhost:3080`. Local integrations
  bind to localhost. If you provide a startup command and turn on auto-connect,
  LogosForge can start a *local* instance after launch (see §6).
* **Remote**: point the base URL at a LibreChat instance you host. LogosForge
  only connects; it never launches a non-localhost instance.

Whether embedded or browser-based depends on availability:

1. **Embedded** — when LibreChat is reachable, *Prefer embedded* is on, and Qt
   WebEngine is importable, LibreChat renders inside the LogosForge workspace
   panel (`QWebEngineView`).
2. **Browser** — otherwise (WebEngine missing, embedding disabled, or you click
   *Open in browser*), LibreChat opens in your system browser.

---

## 4. What happens when LibreChat is unavailable

The LibreChat section always opens and shows a clear status with actions
(**Open LibreChat**, **Retry connection**, **Open in browser**, **LibreChat
settings**):

* **Disabled** — integration off; prompts you to enable it in settings.
* **Invalid URL** — the configured base URL is malformed.
* **Not running** — enabled and valid, but nothing answers; start your instance
  and retry, or open in the browser.
* **Connected** — embeds or offers to open LibreChat.

LogosForge never blocks, never reloads/resets your project, and never requires
LibreChat to launch.

---

## 5. The LogosForge bridge and Pro MCP gateway

`logosforge/librechat/bridge.py` remains the validated in-process adapter used
by desktop integration. External agents use the dedicated, stateful MCP server
in `logosforge/librechat/mcp_server.py`. It delegates to the supported FastAPI
routes through `logosforge/librechat/api_client.py`; it never opens the SQLite
database or exposes arbitrary HTTP, filesystem, or Python execution.

MCP reads cover complete revisioned scenes, outline and PSYKE data, notes,
complete comment threads, search, events, diagnostics, exports, and desktop
live context when available. The 40-tool surface includes
`logosforge_list_comments` (paged, with an optional resolved-thread filter),
`logosforge_propose_comment_reply`, and
`logosforge_propose_comment_resolution` (Resolve or Reopen). Writes use focused
`logosforge_propose_*` tools. Each proposal stores the exact validated request
and stale-state guard under an opaque, expiring id. Only
`logosforge_apply_proposal(proposal_id)` can apply that stored request, and a
proposal is single-use. There is no generic action tool and no
`confirmed=true` shortcut.

The same surface exposes `logosforge_get_timeline` and
`logosforge_propose_timeline_command`. An agent can read the canonical board and
prepare exactly one lane, event-membership, or ordering command against its
current revision. The core rechecks that revision atomically on apply. Timeline
revisions include immutable project/scene/lane identity to reject stale work
even if SQLite reuses a deleted row's numeric ID, while unrelated prose/title
edits do not invalidate a safe board operation. Lane deletion preserves its
events as Unassigned, and event removal preserves the manuscript scene.

`logosforge_search` delegates to the core's typed, project-scoped search route
in one authenticated request. Results remain bounded and include authoritative
comment revision/resolution metadata; the gateway does not fetch and combine
whole scene, note, PSYKE, and comment collections itself.

Writes are disabled by default. They require the explicit MCP write gate and,
by default, a shared API token; scene writes also require the current revision
so the API can reject stale prose atomically. Configure the MCP client to ask
for approval before invoking the apply tool.

Comment mutations have the same stronger boundary: reply and Resolve/Reopen
proposals require the exact current thread revision, which the API rechecks in
the same database transaction as apply. Any intervening root, reply,
resolution, anchor, or deletion change rejects the stale proposal. Replies are
stored as `MCP assistant` and never invoke the app's AI-provider mention
workflow. Comment quotes, bodies, replies, scene titles, and lane labels are
user-authored project data, not instructions to the agent. Anchored comment
creation, anchor/root-body editing, and reply/thread deletion remain available
only in Pro's own UI.

If apply receives an explicit HTTP 4xx rejection, the proposal is terminally
failed and the agent must reread before proposing again. If the response is
lost or otherwise cannot prove rejection (including HTTP 5xx), the proposal is
terminally `indeterminate`; inspect current state and never retry it because the
mutation may already have committed.

See [Pro MCP gateway](docs/MCP_GATEWAY.md) for the complete tool model,
environment variables, Codex setup, remote-host restrictions, and checkpoint
limitations.

Native Pro packages already contain this gateway. On launch, Pro installs a
small console companion at a stable per-user path, so this also works when the
GUI is a portable EXE or AppImage. With the Pro GUI running, a local MCP client
launches that companion; Pro supplies its dynamic loopback endpoint and
per-process token through a private, nonce-verified runtime descriptor. The
source commands below remain useful for development and for a separately
hosted API.

**Run it** (install the optional dependency with `pip install -e ".[mcp]"`):

```bash
# 1. Start the LogosForge API (separate process; localhost, desktop mode):
python -m logosforge.api

# 2. Run the MCP server (stdio), pointed at that API + a project id:
LOGOSFORGE_API_URL=http://127.0.0.1:8765 \
LOGOSFORGE_PROJECT_ID=1 LOGOSFORGE_MCP_ALLOW_WRITES=0 \
python -m logosforge.librechat.mcp_server
```

**Register it in LibreChat** (`librechat.yaml`):

```yaml
mcpServers:
  logosforge:
    command: python
    args: ["-m", "logosforge.librechat.mcp_server"]
    env:
      LOGOSFORGE_API_URL: "http://127.0.0.1:8765"
      LOGOSFORGE_PROJECT_ID: "1"
      LOGOSFORGE_MCP_ALLOW_WRITES: "0"
      # LOGOSFORGE_API_TOKEN: "<token>"
```

Then attach these tools to a LibreChat **Agent**.

The named MCP surface is preferred to registering the full OpenAPI surface as
an agent action: its schemas are narrower, it separates review from mutation,
and it keeps pending proposal state inside the gateway process.

### Desktop API hosting + LIVE context

The three read-only connector actions (and matching MCP tools) can expose the
user's current editing state in addition to persisted project data:

| Connector action | MCP tool | Returns |
|---|---|---|
| `get_live_context` | `logosforge_get_live_context` | project · panel · scene · selection section/length · publication revision when available |
| `get_current_selection` | `logosforge_get_current_selection` | selected text · panel · selection section · publication revision when available |
| `get_active_scene` | `logosforge_get_current_scene` | persisted metadata summary for the scene currently open in the editor |

There are two supported desktop publication paths:

* **Packaged Electron Pro** launches the bundled API as a separate process.
  Electron main sends authenticated, revision-ordered snapshots when the
  project, Studio panel, scene, or selection changes, refreshes them with a
  heartbeat, and sends an ordered clear when the project/window closes.
  Selected text is capped at 20,000 characters and snapshots expire after 30
  seconds without a refresh. A dedicated publication capability is shared only
  between Electron main and its core API process; it is omitted from the
  renderer, health response, MCP runtime descriptor, and MCP client config.
* **Legacy Qt desktop** can enable the optional in-process API with
  `api_embedded_enabled` (default `false`). `MainWindow` starts
  `logosforge/api/embedded.py::EmbeddedApiServer` in a daemon thread with the
  desktop's own `Database` instance. A 750 ms GUI-thread timer pushes plain
  current-project, scene, and selection values into the lock-protected
  registry; the API thread only reads those values and never touches Qt.

In both cases the connector fails closed if the MCP-selected project differs,
the active scene does not belong to that project, or the snapshot expires.
The context and selection tools return `available: false`; the current-scene
tool returns a safe no-fresh-scene error. An agent can then fall back to
persisted project data. Packaged Electron results carry an ordered revision;
the legacy Qt publisher is revisionless and returns `revision: null`.

A bare standalone API (`python -m logosforge.api`) does not invent editor
state. Without a valid owning desktop publisher its live registry remains
empty, so the context and selection tools report unavailable and current-scene
reports no fresh scene. The packaged publication capability is intentionally
not part of normal MCP or standalone API configuration.

For the legacy Qt path, `api_embedded_port` defaults to `8765` and changes take
effect on app start. Do not run the standalone API on the same port. Both
desktop paths bind their production API to loopback and shut down only the
process/server they started.

---

## 6. Process management (optional, isolated)

LibreChat is **never** a launch dependency. If you configure a localhost
startup command and enable auto-connect, `LibreChatService` (in
`logosforge/librechat/service.py`):

* detects an already-running instance (HTTP probe) and **never starts a
  duplicate**;
* tracks **only** the process LogosForge itself started;
* shuts down **only** that process on exit (never an independently-launched
  one — e.g. your own `docker compose up`);
* captures startup errors and lets LogosForge exit cleanly.

**Container-based auto-launch is intentionally out of scope** for this phase:
the typical LibreChat deployment uses Docker + MongoDB + Meilisearch, which
must not be embedded in the LogosForge Python core. Run that stack yourself
(e.g. `docker compose up` in your LibreChat checkout) and point the base URL at
it; LogosForge detects and connects. A robust container launcher can be added
later behind the same `LibreChatService` interface.

---

## 7. Why LibreChat does not access the LogosForge database

LogosForge stays the single source of truth for project state. Going through
the Python services and FastAPI layer (rather than the SQLite file) preserves
DTO validation, revision checks, service invariants, and event publication.
The MCP gateway adds its own named-tool allow-list and stateful propose → review
→ apply boundary. Direct DB access would bypass those safeguards and could let
an external chat tool silently corrupt or exfiltrate project data. The gateway
keeps LibreChat as an *interface*, never an *authority*.

---

## 8. Current limitations

* The embedded view shows the LibreChat web app as-is; visual theming matches
  LogosForge only at the panel chrome level (no LibreChat fork).
* The MCP gateway is stdio-only. The MCP client is responsible for launching
  it and keeping the process alive while proposals are pending.
* Project export is a manual checkpoint, not an automatic transactional
  rollback. Manuscript imports and delete operations are intentionally not
  exposed as MCP tools. Comment creation, anchor/root-body editing, and
  reply/thread deletion are likewise UI-only.
* Auto-launch covers only a simple local startup command; Docker-stack
  orchestration is deferred (§6).
* `get_entity_context` for non-character PSYKE types filters the full entry
  list client-side; richer per-type/timeline endpoints can be added to the
  registry later.
