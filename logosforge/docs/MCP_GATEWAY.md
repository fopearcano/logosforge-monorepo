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
responsibility rather than exposing arbitrary HTTP requests:

- Project and manuscript reads: list/select project, project context and
  snapshot, scene list/full scene, outline, notes, search, events, and export.
- Story intelligence reads: PSYKE entries, characters, relations,
  progressions, and diagnostics.
- Desktop-aware reads: live context, current scene, and current selection.
  These report unavailable when the standalone API has no desktop context.
- Focused proposals: create a project or scene; patch a revisioned scene;
  create/patch outline nodes, PSYKE entries, relations, progressions, and
  notes.
- Proposal management: list, inspect, discard, and apply a stored proposal.

Scene edits require the current scene `revision`. The API performs the final
atomic stale-revision check, so newer prose cannot be silently overwritten.
Other guarded mutations compare the state observed during proposal creation
before applying; clients should reread after a successful mutation.

## Safety boundary

The layers are cumulative:

- The gateway exposes named, schema-validated tools, not arbitrary HTTP,
  filesystem, Python, or database access.
- Writes are disabled unless `LOGOSFORGE_MCP_ALLOW_WRITES=1`.
- Writes require API authentication by default.
- A mutation must be proposed first, remains bound to its exact stored
  payload, expires, and is single-use.
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
tools in this first Pro gateway. Perform those operations in LogosForge's own
review-oriented UI/API workflow. Web releases remain a separate deployment
concern; the gateway does not publish or deploy a web application.
