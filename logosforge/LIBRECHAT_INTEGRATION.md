# LibreChat integration (optional advanced chat sidecar)

LibreChat is an **optional** advanced conversational workspace that LogosForge
can detect, connect to, embed (or open in the browser), and — in a future
phase — let talk back to LogosForge through a safe bridge. It is **off by
default**; LogosForge behaves exactly as before until you enable it, and stays
fully functional if LibreChat is never installed.

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
│        (read context · propose · apply confirmed)        (the existing safe action layer)│
└─────────────────────────────────────────────────────────────────────────────────────────┘
                                   ▲ (future)
        LibreChat Agent ──OpenAPI / MCP──┘  calls the same bridge operations
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

## 5. The LogosForge bridge (future OpenAPI / MCP boundary)

`logosforge/librechat/bridge.py` defines `LogosForgeBridge` — the **only**
sanctioned surface a future LibreChat agent will use. `LocalBridge` implements
it as a **thin, validated adapter over the existing safe connector layer**
(`connector_registry` + `connector_executor`, wrapped by
`logosforge.api.actions.run_action`). Operations:

* **Read context** — `get_project_context`, `get_current_scene`,
  `get_current_selection`, `search_psyke`, `get_entity_context`,
  `get_outline_context` → registered **read** actions (always permitted).
* **Propose (validated, NOT applied)** — `propose_edit`,
  `propose_outline_change`, `propose_psyke_entry` → return an `ActionProposal`
  validated against the registry.
* **Apply** — `apply_confirmed_action(action, args, confirmed=True)` runs a
  previously-confirmed action through the connector, which still enforces the
  desktop write settings (`connector_enabled` / `connector_allow_writes` /
  `connector_confirm_writes`).

So a write needs **both** explicit confirmation **and** the connector
write-settings gate — the bridge never bypasses propose → confirm → apply, and
never exposes filesystem access, direct DB access, arbitrary Python, or
unconfirmed destructive actions. All input from LibreChat is treated as
untrusted and validated.

A **read-only proof of concept already works over the existing OpenAPI**: the
FastAPI server (`python -m logosforge.api`, `127.0.0.1:8765`, desktop mode =
localhost-only CORS) exposes `POST /projects/{id}/connector/execute` and
`GET /projects/{id}/connector/actions`, which run the same registry actions.

### LogosForge MCP server (scaffolded)

`logosforge/librechat/mcp_server.py` is a small **MCP server** that exposes the
bridge operations to LibreChat as named tools. It **delegates to the FastAPI
connector endpoints** over localhost (via `logosforge/librechat/api_client.py`),
so it never touches the database directly and reuses the safe action layer — and
the desktop app stays the single DB owner.

**Tools (1:1 with the bridge):** `logosforge_get_project_context`,
`logosforge_get_outline_context`, `logosforge_get_scene`, `logosforge_search`,
`logosforge_list_characters`, `logosforge_list_psyke_entries`,
`logosforge_propose_psyke_entry`, `logosforge_propose_scene`,
`logosforge_propose_rename_scene`, `logosforge_apply_confirmed_action`.

`propose_*` tools return an **un-applied** proposal. `apply_confirmed_action`
requires `confirmed=true` **and** is still gated by the connector write settings
on the API side — so an external agent cannot mutate the project unconfirmed.

**Run it** (the `mcp` SDK is optional — `pip install mcp`):

```bash
# 1. Start the LogosForge API (separate process; localhost, desktop mode):
python -m logosforge.api

# 2. Run the MCP server (stdio), pointed at that API + a project id:
LOGOSFORGE_API_URL=http://127.0.0.1:8765 LOGOSFORGE_PROJECT_ID=1 \
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
      # LOGOSFORGE_API_TOKEN: "<token>"   # only if the API is started with one
```

Then attach these tools to a LibreChat **Agent**.

**Alternative (OpenAPI Action):** for a quick smoke test you can instead register
a LibreChat Agent "OpenAPI Action" against `http://127.0.0.1:8765` using the
connector endpoints directly — but the MCP server gives the agent better,
named, per-operation tools and is the recommended durable path.

### In-process API hosting + LIVE context

To give the agent the user's **live** editing state — not just persisted data —
LogosForge can host the FastAPI server **inside the desktop process**. This is
optional and **off by default** (setting `api_embedded_enabled`); when off,
nothing changes and startup is byte-for-byte identical.

When on, `MainWindow` starts `logosforge/api/embedded.py::EmbeddedApiServer`
in a **daemon thread**, handing it the desktop's *own* `Database` instance
(`check_same_thread=False` + per-request sessions make this safe across the Qt
thread and the uvicorn worker thread — no second connection). A low-cadence
(750 ms) GUI-thread timer **pushes** plain values — current project id, active
scene id, current selection — into a lock-protected registry
(`logosforge/live_context.py`); the API worker thread only ever **reads** that
plain data, so it never touches Qt cross-thread. The server is bound to
`127.0.0.1` (desktop CORS) and shut down cleanly on exit (only the instance
LogosForge started).

This adds three **read-only** connector actions (and matching MCP tools), so the
agent can ask about live state through the same safe layer:

| Connector action | MCP tool | Returns |
|---|---|---|
| `get_live_context` | `logosforge_get_live_context` | project id · active scene id · has-selection |
| `get_current_selection` | `logosforge_get_current_selection` | the selected text (live) |
| `get_active_scene` | `logosforge_get_current_scene` | the scene open in the editor (live) |

When the API runs as a *separate* process (`python -m logosforge.api`) the
registry is empty, so these report `available: false` and the agent falls back
to persisted data — no error, no special-casing.

**Settings:** `api_embedded_enabled` (default `false`) and `api_embedded_port`
(default `8765`, matching the MCP server's default URL). Takes effect on app
start. If you also run the standalone API on the same port, they conflict —
use one or the other.

**Net:** turn on `api_embedded_enabled`, point the MCP server at
`http://127.0.0.1:8765`, and the agent gets persisted data, safe writes **and**
the user's live project / scene / selection — all through the one safe layer.

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
the Python services / FastAPI / connector layer (rather than the SQLite file)
guarantees: input validation, the registered-action allow-list, the
read/write-settings gate, propose → confirm → apply confirmation, and event
publication on change. Direct DB access would bypass every one of these
safeguards and let an external chat tool silently corrupt or exfiltrate project
data. The bridge boundary keeps LibreChat as an *interface*, never an
*authority*.

---

## 8. Current limitations

* The embedded view shows the LibreChat web app as-is; visual theming matches
  LogosForge only at the panel chrome level (no LibreChat fork).
* The bridge is wired in-process and over the existing OpenAPI for reads; the
  dedicated **MCP server** and a LibreChat-side **OpenAPI Action** package are
  future work (see §5).
* Auto-launch covers only a simple local startup command; Docker-stack
  orchestration is deferred (§6).
* `get_entity_context` for non-character PSYKE types filters the full entry
  list client-side; richer per-type/timeline endpoints can be added to the
  registry later.
