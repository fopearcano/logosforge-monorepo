"""LogosForge MCP server — exposes the bridge operations to LibreChat (or any
MCP client) as named tools, delegating to the existing FastAPI connector
endpoints via :class:`LogosForgeApiClient`.

Design:

* Tools map 1:1 to the :class:`logosforge.librechat.bridge.LogosForgeBridge`
  operations (read context · propose · apply confirmed).
* Reads and applies go through the safe connector layer over HTTP; the server
  never touches the database directly.
* ``propose_*`` tools validate against the live action registry and return an
  un-applied proposal. ``apply_confirmed_action`` requires ``confirmed=true``
  AND is still gated by the desktop connector write settings on the API side.

The tool specs + handlers below are plain, fully-testable Python. The actual
MCP transport (the ``mcp`` SDK) is imported lazily in :func:`build_server` /
:func:`main`, so this module imports and tests cleanly even when ``mcp`` is not
installed. Install it with ``pip install mcp`` to run the server.

Run (after starting the LogosForge API — ``python -m logosforge.api``):

    LOGOSFORGE_API_URL=http://127.0.0.1:8765 LOGOSFORGE_PROJECT_ID=1 \
        python -m logosforge.librechat.mcp_server
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from logosforge.librechat.api_client import (
    DEFAULT_BASE_URL,
    LogosForgeApiClient,
    LogosForgeApiError,
)

SERVER_NAME = "logosforge"


class McpToolError(RuntimeError):
    """A tool-level error surfaced back to the MCP client."""


@dataclass
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Callable[[LogosForgeApiClient, dict[str, Any]], Any]


def _obj(properties: dict[str, Any], required: list[str] | None = None) -> dict:
    return {
        "type": "object",
        "properties": properties,
        "required": required or [],
        "additionalProperties": False,
    }


# -- Validation of untrusted tool input -------------------------------------

def _need_str(args: dict, key: str, max_len: int = 20_000) -> str:
    val = args.get(key)
    if not isinstance(val, str) or not val.strip():
        raise McpToolError(f"'{key}' must be a non-empty string.")
    if len(val) > max_len:
        raise McpToolError(f"'{key}' is too long (>{max_len}).")
    return val


def _need_int(args: dict, key: str) -> int:
    val = args.get(key)
    if isinstance(val, bool) or not isinstance(val, (int, str)):
        raise McpToolError(f"'{key}' must be an integer.")
    try:
        return int(val)
    except (TypeError, ValueError):
        raise McpToolError(f"'{key}' must be an integer.") from None


# -- Tool handlers (delegate to the connector API) --------------------------

def _h_get_project(client: LogosForgeApiClient, args: dict) -> Any:
    return client.execute("get_project")


def _h_list_outline(client: LogosForgeApiClient, args: dict) -> Any:
    return client.execute("list_scenes")


def _h_get_scene(client: LogosForgeApiClient, args: dict) -> Any:
    return client.execute("get_scene", {"scene_id": _need_int(args, "scene_id")})


def _h_search(client: LogosForgeApiClient, args: dict) -> Any:
    return client.execute("search", {"query": _need_str(args, "query", 500)})


def _h_list_characters(client: LogosForgeApiClient, args: dict) -> Any:
    return client.execute("list_characters")


def _h_list_psyke(client: LogosForgeApiClient, args: dict) -> Any:
    res = client.execute("list_psyke_entries")
    etype = str(args.get("entry_type") or "").strip().lower()
    if not etype or etype == "all" or not res.get("ok"):
        return res
    wanted = etype.rstrip("s")
    entries = [
        e for e in (res.get("result") or [])
        if str(e.get("entry_type", "")).lower() == wanted
    ]
    return {"ok": True, "action": "list_psyke_entries", "result": entries, "error": ""}


def _h_get_current_scene(client: LogosForgeApiClient, args: dict) -> Any:
    return client.execute("get_active_scene")


def _h_get_current_selection(client: LogosForgeApiClient, args: dict) -> Any:
    return client.execute("get_current_selection")


def _h_get_live_context(client: LogosForgeApiClient, args: dict) -> Any:
    return client.execute("get_live_context")


def _proposal(client: LogosForgeApiClient, action: str, args: dict) -> dict:
    """Validate a write action against the live registry and return an
    un-applied proposal (nothing is mutated)."""
    try:
        catalog = {a.get("name"): a for a in client.list_actions()}
    except LogosForgeApiError as exc:
        raise McpToolError(str(exc)) from exc
    defn = catalog.get(action)
    if defn is None:
        raise McpToolError(f"Unknown action: {action!r}")
    if defn.get("category") != "write":
        raise McpToolError(f"{action!r} is not a write action.")
    return {
        "proposal": {"action": action, "args": args},
        "requires_confirmation": True,
        "note": (
            "Not applied. Review with the user, then call "
            "logosforge_apply_confirmed_action with confirmed=true to apply "
            "(still subject to LogosForge connector write settings)."
        ),
    }


def _h_propose_psyke(client: LogosForgeApiClient, args: dict) -> Any:
    payload: dict[str, Any] = {
        "name": _need_str(args, "name"),
        "entry_type": str(args.get("entry_type") or "other"),
    }
    if "notes" in args:
        payload["notes"] = _need_str(args, "notes")
    return _proposal(client, "create_psyke_entry", payload)


def _h_propose_scene(client: LogosForgeApiClient, args: dict) -> Any:
    payload: dict[str, Any] = {"title": _need_str(args, "title")}
    for key in ("chapter", "plotline"):
        if key in args:
            payload[key] = _need_str(args, key)
    return _proposal(client, "create_scene", payload)


def _h_propose_rename_scene(client: LogosForgeApiClient, args: dict) -> Any:
    return _proposal(client, "update_scene_title", {
        "scene_id": _need_int(args, "scene_id"),
        "title": _need_str(args, "title"),
    })


def _h_apply_confirmed(client: LogosForgeApiClient, args: dict) -> Any:
    action = _need_str(args, "action", 80)
    payload = args.get("args") or {}
    if not isinstance(payload, dict):
        raise McpToolError("'args' must be an object.")
    if not bool(args.get("confirmed")):
        return {
            "ok": False,
            "error": "Refused: set confirmed=true only after explicit user "
                     "confirmation. Writes also require LogosForge connector "
                     "settings to allow them.",
        }
    return client.execute(action, payload)


TOOL_SPECS: list[ToolSpec] = [
    ToolSpec("logosforge_get_project_context",
             "Get the current LogosForge project (id, title, description).",
             _obj({}), _h_get_project),
    ToolSpec("logosforge_get_outline_context",
             "List all scenes in the project (the outline).",
             _obj({}), _h_list_outline),
    ToolSpec("logosforge_get_live_context",
             "Get the user's LIVE editing context: current project id, the "
             "scene open in the editor, and whether text is selected. Only "
             "populated when LogosForge hosts the API in-process.",
             _obj({}), _h_get_live_context),
    ToolSpec("logosforge_get_current_scene",
             "Get the scene the user currently has OPEN in the editor (live), "
             "with all structured fields.",
             _obj({}), _h_get_current_scene),
    ToolSpec("logosforge_get_current_selection",
             "Get the text the user currently has SELECTED in the editor (live).",
             _obj({}), _h_get_current_selection),
    ToolSpec("logosforge_get_scene",
             "Get one scene by id with all structured fields.",
             _obj({"scene_id": {"type": "integer"}}, ["scene_id"]), _h_get_scene),
    ToolSpec("logosforge_search",
             "Full-text search across the project (scenes, notes, story bible).",
             _obj({"query": {"type": "string"}}, ["query"]), _h_search),
    ToolSpec("logosforge_list_characters",
             "List the project's characters.",
             _obj({}), _h_list_characters),
    ToolSpec("logosforge_list_psyke_entries",
             "List story-bible (PSYKE) entries, optionally filtered by type "
             "(character/place/object/lore/theme/other).",
             _obj({"entry_type": {"type": "string"}}), _h_list_psyke),
    ToolSpec("logosforge_propose_psyke_entry",
             "Propose creating a story-bible entry (NOT applied; returns a "
             "proposal to confirm).",
             _obj({"name": {"type": "string"},
                   "entry_type": {"type": "string"},
                   "notes": {"type": "string"}}, ["name"]), _h_propose_psyke),
    ToolSpec("logosforge_propose_scene",
             "Propose creating a scene (NOT applied; returns a proposal).",
             _obj({"title": {"type": "string"},
                   "chapter": {"type": "string"},
                   "plotline": {"type": "string"}}, ["title"]), _h_propose_scene),
    ToolSpec("logosforge_propose_rename_scene",
             "Propose renaming a scene (NOT applied; returns a proposal).",
             _obj({"scene_id": {"type": "integer"},
                   "title": {"type": "string"}}, ["scene_id", "title"]),
             _h_propose_rename_scene),
    ToolSpec("logosforge_apply_confirmed_action",
             "Apply a previously-confirmed connector action. Requires "
             "confirmed=true and is still gated by LogosForge connector "
             "write settings.",
             _obj({"action": {"type": "string"},
                   "args": {"type": "object"},
                   "confirmed": {"type": "boolean"}}, ["action", "confirmed"]),
             _h_apply_confirmed),
]

HANDLERS: dict[str, ToolSpec] = {spec.name: spec for spec in TOOL_SPECS}


def call_tool(client: LogosForgeApiClient, name: str, arguments: dict | None) -> Any:
    """Dispatch a tool call (testable, transport-agnostic).

    Validation and API errors are returned as a structured ``{ok, error}``
    result rather than raised, so a bad tool call never crashes the server."""
    spec = HANDLERS.get(name)
    if spec is None:
        return {"ok": False, "error": f"Unknown tool: {name!r}"}
    try:
        return spec.handler(client, arguments or {})
    except (McpToolError, LogosForgeApiError) as exc:
        return {"ok": False, "error": str(exc)}


# -- Config + MCP transport (lazy mcp import) --------------------------------

@dataclass
class McpConfig:
    base_url: str = DEFAULT_BASE_URL
    project_id: int = 1
    auth_token: str = ""
    timeout: float = 15.0

    @classmethod
    def from_env(cls) -> "McpConfig":
        try:
            pid = int(os.environ.get("LOGOSFORGE_PROJECT_ID", "1"))
        except ValueError:
            pid = 1
        return cls(
            base_url=os.environ.get("LOGOSFORGE_API_URL", DEFAULT_BASE_URL),
            project_id=pid,
            auth_token=os.environ.get("LOGOSFORGE_API_TOKEN", ""),
        )


def make_client(config: McpConfig | None = None) -> LogosForgeApiClient:
    cfg = config or McpConfig.from_env()
    return LogosForgeApiClient(
        base_url=cfg.base_url, project_id=cfg.project_id,
        auth_token=cfg.auth_token, timeout=cfg.timeout,
    )


def build_server(client: LogosForgeApiClient):
    """Build the MCP ``Server`` wired to the connector-backed handlers.

    Imports the ``mcp`` SDK lazily so this module is importable/testable without
    it. Raises a clear error if ``mcp`` is not installed.
    """
    try:
        from mcp.server import Server
        import mcp.types as types
    except ImportError as exc:  # pragma: no cover — requires the optional SDK
        raise RuntimeError(
            "The 'mcp' package is required to run the LogosForge MCP server. "
            "Install it with: pip install mcp"
        ) from exc

    server = Server(SERVER_NAME)

    @server.list_tools()
    async def _list_tools() -> list:  # noqa: ANN202
        return [
            types.Tool(
                name=spec.name,
                description=spec.description,
                inputSchema=spec.input_schema,
            )
            for spec in TOOL_SPECS
        ]

    @server.call_tool()
    async def _call_tool(name: str, arguments: dict | None) -> list:  # noqa: ANN202
        result = call_tool(client, name, arguments)
        return [types.TextContent(type="text", text=json.dumps(result, default=str))]

    return server


def main() -> int:  # pragma: no cover — needs the SDK + a live API
    import asyncio

    client = make_client()
    server = build_server(client)

    async def _run() -> None:
        from mcp.server.stdio import stdio_server
        async with stdio_server() as (read, write):
            await server.run(read, write, server.create_initialization_options())

    asyncio.run(_run())
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
