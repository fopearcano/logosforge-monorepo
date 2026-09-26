# LogosForge Whiteboard — backend (core wrapper)

A thin FastAPI **wrapper** over the LogosForge core API. It does **not**
reimplement core logic (the previous standalone backend's drift) — it imports
`logosforge` in-process, builds the core API with `create_api(...)`, and calls
it over in-process ASGI. One process, one port (8777), one SQLite database.

The Whiteboard frontend is project-agnostic; the core is project-scoped. Each
Whiteboard document is one core project id, giving every document an isolated
PSYKE bible while the wrapper translates between the two DTO contracts.

When launched by Electron, every `/api/*` request is protected by an in-memory
per-process Bearer token and the health handshake carries a random instance
nonce. Neither value is persisted. A manually launched browser-development
backend remains tokenless unless `LOGOSFORGE_WHITEBOARD_AUTH_TOKEN` is set.

## Setup (local, editable core)

```sh
python -m venv .venv
. .venv/Scripts/activate           # Windows; use bin/activate on POSIX
pip install -e ../../logosforge    # the headless core + API (no PySide6)
pip install -r requirements.txt    # fastapi / uvicorn / httpx / MCP SDK
```

## Run

```sh
python -m uvicorn app.main:app --host 127.0.0.1 --port 8777
# GET /health -> {"status":"ok", ...}
```

The Electron `backend-manager` spawns this exactly as it spawned the old
backend; only the venv (now has `logosforge`) and the wrapped routes differ.

## Endpoint coverage

| Frontend route | Status | How |
|---|---|---|
| `/health`, `/api/version` | ✅ | mapped from core `/api/health` |
| `/api/documents` | ✅ | core project CRUD; document id = core project id |
| `/api/writing-modes` | ✅ | imports core `logosforge.writing_modes` |
| `/api/psyke/search`, `/elements`, `/relations`, `/progressions` | ✅ | wraps project-scoped core PSYKE routes; all reads publish one aggregate revision and MCP writes use conditional create/patch |
| `/api/littleboy/billy/chat`, `/logos/inline` | ✅ | prompt orchestration → core Assistant/Logos; manual Whiteboard outline added to AI grounding |
| `/api/settings/ai`, `/test` | ✅ | global provider settings passthrough + actionable connection test |
| `/api/whiteboard`, `/api/outline/items`, `/api/comments` | ✅ | per-document atomic JSON with fsync, transaction-wide locks, two rotating backups, quarantine + recovery; manuscript, outline, and comment collaboration writes support conditional resource revisions |
| `/api/export/project` | ✅ | complete-or-failed `.lfbundle` (manuscript + document settings + outline + comments + PSYKE entries, relations, and progressions) |
| `/api/recovery/notices` | ✅ | one-shot notices when a local state backup was restored |

## Verification

```sh
# Full backend regression suite
.venv/Scripts/python -m pytest tests -q

# Provider transport, error translation, manual-outline + PSYKE grounding
.venv/Scripts/python tests/test_ai_grounding.py

# Complete project-bundle export
.venv/Scripts/python tests/test_export.py
```

All tests use temporary data/DB state; the AI test uses loopback mock OpenAI
and Anthropic servers and never needs or reads a real API key. Recovery tests
exercise backup rotation, quarantine, fail-closed autosave, and complete export.

## Conditional manuscript, outline, comment, and PSYKE writes

Manuscripts and manual outlines each own an independent opaque 32-hex
`revision`. Their GET responses include that value in the JSON body and publish
a strong ETag with this exact shape:

```text
"lfwb:<whiteboard|outline|comments|psyke>:<document-incarnation>:<revision>"
```

An explicit-document `PUT` (`?doc=<id>`) must echo the document incarnation in
`X-LogosForge-Document-Incarnation` and the complete tag in `If-Match`. A
missing precondition returns HTTP 428, malformed/weak/wildcard tags return HTTP
400, and a stale tag returns HTTP 409 with the structured code
`revision_conflict`, the current revision, and the current ETag. The write is
not attempted. The legacy default-document route may omit `If-Match`; when it
is supplied it is enforced normally.

The legacy doc-omitted `POST /api/whiteboard` is create-only: it can initialize
a missing local manuscript for the default core project and returns HTTP 409
with `resource_already_exists` instead of replacing an existing manuscript.
Explicit multi-document creation remains exclusively `POST /api/documents`, so
a delayed headerless request cannot attach content to a reused numeric id. If a
backup is recovered, the restored manuscript or outline is immediately saved
with a fresh revision and cleared retry metadata (without changing manuscript
`updated_at`), so every ETag issued before recovery becomes stale.

Desktop persistence may also attach `X-LogosForge-Mutation-Id`. The store saves
the last id and a canonical request fingerprint inside its private on-disk
envelope. Retrying the exact request returns its prior successful revision
without another write; reusing the id for a different request returns HTTP 409
with `mutation_id_conflict`. These internal fields are never part of an API or
MCP response. Main-process persistence-order no-ops are valid only while the
current revision still belongs to the latest ordered lineage; an ordinary API
write or recovery forces delayed writes through the conditional revision check.
`ETag` is CORS-exposed for the browser-development client.

`GET /api/psyke/search`, `/api/psyke/relations`, and
`/api/psyke/progressions` return one shared opaque revision for the complete
PSYKE story bible and publish the same strong ETag, even when `q` filters the
returned entries. The aggregate digest covers entries, relationships, and
progression beats. The core database remains the source of truth; a durable
sidecar binds an opaque revision to each observed full-bible digest so an
observed A→B→A content transition cannot revive a stale validator.

Existing PSYKE entry `POST`/`PATCH` requests carrying neither conditional
header remain valid for legacy UI compatibility; explicit-document URLs still
require their normal document-incarnation header. Supplying either `If-Match`
or `X-LogosForge-Mutation-Id` activates conditional mode: the complete pair and
`X-LogosForge-Document-Incarnation` are then required. Relationship and
progression mutations are MCP-only and always require that complete conditional
triplet. Under the document lock, the wrapper validates the full aggregate
story bible before writing. An exact retry returns the saved successful DTO and
revision without another core write; reusing the mutation id for a different
request returns HTTP 409 with `mutation_id_conflict`.

Project-bundle export reads all three core-owned PSYKE collections and aborts
the whole request if any transport or DTO check fails. Bundle version 1.0 now
uses additive `project.psyke.relations` and `project.psyke.progressions` arrays
alongside the existing frontend-shaped `project.psyke.elements`; no graph or arc
data is silently omitted from the advertised complete backup. The Pro bundle
importer recreates entries, then restores relationships and ordered progression
beats through source-to-destination entry-ID remapping. A progression's scene
anchor is restored only when its scene title has one unique imported match;
missing or ambiguous matches remain safely unlinked and are reported.

`GET /api/comments` returns `{comments, revision}` and publishes the comment
collection's strong ETag. Existing comment mutations carrying neither
`If-Match` nor `X-LogosForge-Mutation-Id` retain the Whiteboard UI's legacy
behavior. Every successful legacy mutation still rotates the collection
revision and clears any conditional retry receipt.

For `PUT /api/comments/{comment_id}` and
`POST /api/comments/{comment_id}/replies`, supplying either conditional header
activates conditional mode and requires the complete pair plus
`X-LogosForge-Document-Incarnation`. Conditional `PUT` accepts exactly one
boolean `resolved` field; comment body and anchor changes are rejected.
Conditional replies must contain exactly one nonblank, bounded `body` string
and reject `@Billy` and `@Logos`. The backend forces the author to
`MCP assistant`, derives the reply id from the mutation-id header, and never
invokes an AI provider. An exact retry returns the stored comment and revision
without another write; mutation-id reuse with different content returns HTTP
409. Headerless UI replies keep their existing author/client-id and
provider-backed mention behavior.

## MCP companion

Whiteboard ships a separate stdio server named `logosforge-whiteboard`.
Contract version `1.4.0` exposes 24 tools with the stable
`logosforge_whiteboard_` prefix. Eleven bounded read tools cover documents,
manuscripts, outlines, revisioned comments, PSYKE entries, relationships,
progressions, and search. Nine proposal builders capture an exact manuscript
patch, full-outline replacement, PSYKE entry creation/patch, relationship
creation, progression creation/patch, comment reply, or comment
resolution/reopening against the resource's current revision; four lifecycle
tools list, inspect, discard, or apply those in-memory proposals. Apply is
disabled unless
`LOGOSFORGE_WHITEBOARD_MCP_ALLOW_WRITES=1`, accepts only a proposal id, sends the
original document-incarnation header, strong `If-Match`, and mutation id, and
consumes the proposal before network I/O. Proposal reviews include bounded
head/tail change samples plus an exact request body that can be paged by byte
offset and verified with its SHA-256 digest before apply. Manuscript replacements
enforce the renderer's block and inline-mark contract, while full outline
replacements enforce its node, parent, cycle, depth, and canonical-order
invariants. PSYKE proposals enforce bounded entry, relation, and progression
schemas and return bounded before/after review fields. Comment proposals can
only add a bounded, non-AI reply or toggle one thread's resolution state. There
are no document lifecycle, anchored comment creation, comment body/anchor
editing, comment/reply deletion, PSYKE entry/relation/progression deletion,
settings, AI-call, import/export, generic HTTP, filesystem, SQLite, or
command-execution mutation tools.

The installed app publishes `mcp-runtime-v1.json` inside its product-specific
Electron user-data directory after the nonce-bound `/health` check succeeds.
The private descriptor schema is:

```json
{
  "schema_version": 1,
  "base_url": "http://127.0.0.1:<port>",
  "auth_token": "<per-process secret>",
  "instance_nonce": "<per-process nonce>",
  "app_pid": 123,
  "backend_pid": 456,
  "created_at": "<UTC ISO-8601>"
}
```

The companion accepts only a plain-HTTP loopback URL, verifies both live PIDs
and the health nonce, and sends the token only to named `/api/*` operations.
Tests may
override discovery with `LOGOSFORGE_WHITEBOARD_MCP_CONNECTION_FILE`, provided
the value is absolute and retains the `mcp-runtime-v1.json` basename; the
installed executable is `logosforge-whiteboard-mcp` (`.exe` on Windows).

Build and smoke-test both frozen executables from this directory:

```sh
pyinstaller logosforge-whiteboard-backend.spec
pyinstaller logosforge-whiteboard-mcp.spec
python smoke-frozen-mcp.py \
  dist/logosforge-whiteboard-backend/logosforge-whiteboard-backend \
  dist/logosforge-whiteboard-mcp
```

After Electron packaging, exercise descriptor publication, stable companion
installation, backend identity, default-gated reads, and disposable
write-enabled manuscript, PSYKE entry/relationship/progression, and comment
reply/resolution proposal/apply round trips end to end:

```sh
python smoke-packaged-mcp.py <unpacked-exe-or-AppImage-or-DMG>
# Add --codex-command codex for a real local Codex tool-call check.
```

Run the focused contract, descriptor-security, and real-stdio tests with:

```sh
python -m pytest \
  tests/test_whiteboard_mcp.py \
  tests/test_whiteboard_mcp_route_integration.py \
  tests/test_whiteboard_mcp_runtime.py -q
```
