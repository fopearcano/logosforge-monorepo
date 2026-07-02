"""The bridge boundary between LibreChat (external) and LogosForge.

This is the **only** sanctioned surface through which a future LibreChat agent
(via the LogosForge OpenAPI/FastAPI interface or an MCP server) reaches project
state. It is a thin, validated adapter over the EXISTING safe connector layer
(:mod:`logosforge.connector_registry` + :mod:`logosforge.connector_executor`,
wrapped by :func:`logosforge.api.actions.run_action`). It deliberately:

* never touches the SQLite DB, filesystem, or Python ``exec`` directly;
* treats every argument as untrusted external input and validates it;
* exposes only the registered, allow-listed connector actions;
* returns *proposals* for writes — applying one requires explicit confirmation
  AND still passes through the connector write-settings gate
  (``connector_enabled`` / ``connector_allow_writes`` / ``connector_confirm_writes``).

So the existing propose → confirm → apply guarantees hold unchanged; LibreChat
can never become authoritative for project state or mutate it unconfirmed.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from logosforge.db import Database

# Defensive caps for untrusted external input.
_MAX_STR = 20_000
_MAX_QUERY = 500


class BridgeValidationError(ValueError):
    """Raised when external (LibreChat) input fails validation."""


@dataclass
class BridgeResult:
    ok: bool
    data: Any = None
    error: str = ""


@dataclass
class ActionProposal:
    """A validated but UNEXECUTED write proposal.

    Applying it requires :meth:`LogosForgeBridge.apply_confirmed_action` with
    ``confirmed=True`` (explicit user confirmation) — and that call still routes
    through the connector write-settings gate.
    """

    action: str
    args: dict[str, Any]
    category: str
    label: str
    requires_confirmation: bool = True

    def as_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "args": self.args,
            "category": self.category,
            "label": self.label,
            "requires_confirmation": self.requires_confirmation,
        }


class LogosForgeBridge(ABC):
    """Operations a future LibreChat MCP/OpenAPI client may invoke."""

    # -- Read (context) ---------------------------------------------------
    @abstractmethod
    def get_project_context(self) -> BridgeResult: ...
    @abstractmethod
    def get_current_scene(self, scene_id: int | None = None) -> BridgeResult: ...
    @abstractmethod
    def get_current_selection(self) -> BridgeResult: ...
    @abstractmethod
    def search_psyke(self, query: str) -> BridgeResult: ...
    @abstractmethod
    def get_entity_context(self, entity_type: str) -> BridgeResult: ...
    @abstractmethod
    def get_outline_context(self) -> BridgeResult: ...

    # -- Propose (validated, NOT applied) ---------------------------------
    @abstractmethod
    def propose_edit(self, scene_id: int, title: str) -> ActionProposal: ...
    @abstractmethod
    def propose_outline_change(self, title: str, **fields: Any) -> ActionProposal: ...
    @abstractmethod
    def propose_psyke_entry(self, name: str, entry_type: str = "other", **fields: Any) -> ActionProposal: ...

    # -- Apply (only a previously-confirmed safe action) ------------------
    @abstractmethod
    def apply_confirmed_action(self, action: str, args: dict[str, Any], confirmed: bool = False) -> BridgeResult: ...


# Entity type → read action. Non-character types come from list_psyke_entries
# (filtered client-side by the returned "type" field).
_PSYKE_TYPES = {"character", "place", "object", "lore", "theme", "other"}


class LocalBridge(LogosForgeBridge):
    """In-process implementation backed by the safe connector layer.

    ``selection_provider`` / ``active_scene_provider`` let the desktop app feed
    the *current* editor selection / scene without the bridge reaching into UI
    state. Both are optional (default to "nothing selected / no active scene").
    """

    def __init__(
        self,
        db: Database,
        project_id: int,
        selection_provider: Callable[[], str | None] | None = None,
        active_scene_provider: Callable[[], int | None] | None = None,
    ) -> None:
        self._db = db
        self._project_id = int(project_id)
        self._selection = selection_provider or (lambda: None)
        self._active_scene = active_scene_provider or (lambda: None)

    # -- Read --------------------------------------------------------------

    def get_project_context(self) -> BridgeResult:
        return self._run("get_project")

    def get_current_scene(self, scene_id: int | None = None) -> BridgeResult:
        sid = scene_id if scene_id is not None else self._active_scene()
        if sid is None:
            return BridgeResult(False, error="No active scene.")
        return self._run("get_scene", {"scene_id": _require_int(sid, "scene_id")})

    def get_current_selection(self) -> BridgeResult:
        text = self._selection() or ""
        return BridgeResult(True, {"text": str(text)[:_MAX_STR]})

    def search_psyke(self, query: str) -> BridgeResult:
        q = _require_str(query, "query", max_len=_MAX_QUERY)
        return self._run("search", {"query": q})

    def get_entity_context(self, entity_type: str) -> BridgeResult:
        etype = _require_str(entity_type, "entity_type", max_len=40).lower()
        if etype in ("character", "characters"):
            return self._run("list_characters")
        res = self._run("list_psyke_entries")
        if not res.ok or etype in ("", "all"):
            return res
        wanted = etype.rstrip("s")
        entries = [
            e for e in (res.data or [])
            if str(e.get("type", "")).lower() == wanted
        ]
        return BridgeResult(True, entries)

    def get_outline_context(self) -> BridgeResult:
        return self._run("list_scenes")

    # -- Propose -----------------------------------------------------------

    def propose_edit(self, scene_id: int, title: str) -> ActionProposal:
        return self._propose("update_scene_title", {
            "scene_id": _require_int(scene_id, "scene_id"),
            "title": _require_str(title, "title"),
        })

    def propose_outline_change(self, title: str, **fields: Any) -> ActionProposal:
        args: dict[str, Any] = {"title": _require_str(title, "title")}
        for key in ("chapter", "plotline"):
            if key in fields:
                args[key] = _require_str(fields[key], key)
        return self._propose("create_scene", args)

    def propose_psyke_entry(self, name: str, entry_type: str = "other", **fields: Any) -> ActionProposal:
        etype = _require_str(entry_type, "entry_type", max_len=40).lower()
        if etype not in _PSYKE_TYPES:
            etype = "other"
        args: dict[str, Any] = {
            "name": _require_str(name, "name"),
            "entry_type": etype,
        }
        if "notes" in fields:
            args["notes"] = _require_str(fields["notes"], "notes")
        return self._propose("create_psyke_entry", args)

    # -- Apply -------------------------------------------------------------

    def apply_confirmed_action(self, action: str, args: dict[str, Any], confirmed: bool = False) -> BridgeResult:
        name = _require_str(action, "action", max_len=80)
        payload = _require_dict(args, "args")
        defn = _get_action_def(name)
        if defn is None:
            return BridgeResult(False, error=f"Unknown action: {name!r}")
        if defn.category != "read" and not confirmed:
            # Mirrors the existing safe layer: no write without confirmation.
            return BridgeResult(
                False, error="This action requires explicit user confirmation.",
            )
        return self._run(name, payload)

    # -- Internals ---------------------------------------------------------

    def _run(self, action: str, args: dict[str, Any] | None = None) -> BridgeResult:
        # run_action enforces the registry allow-list + read/write settings.
        from logosforge.api.actions import run_action
        try:
            res = run_action(self._db, self._project_id, action, args or {})
        except Exception as exc:  # never leak internals to the external caller
            return BridgeResult(False, error=f"{type(exc).__name__}: {exc}")
        return BridgeResult(
            bool(res.get("ok")), res.get("result"), str(res.get("error", "")),
        )

    def _propose(self, action: str, args: dict[str, Any]) -> ActionProposal:
        defn = _get_action_def(action)
        if defn is None:
            raise BridgeValidationError(f"Unknown action: {action!r}")
        if defn.category != "write":
            raise BridgeValidationError(f"{action!r} is not a write action.")
        return ActionProposal(
            action=action, args=args, category=defn.category,
            label=defn.description or action,
        )


def _get_action_def(name: str):
    import logosforge.connector_actions  # noqa: F401  (populate the registry)
    from logosforge.connector_registry import get_action
    return get_action(name)


# -- Validation of untrusted external input ---------------------------------

def _require_str(value: Any, field_name: str, max_len: int = _MAX_STR) -> str:
    if not isinstance(value, str):
        raise BridgeValidationError(f"{field_name} must be a string.")
    if len(value) > max_len:
        raise BridgeValidationError(f"{field_name} is too long (>{max_len}).")
    return value


def _require_int(value: Any, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise BridgeValidationError(f"{field_name} must be an integer.")
    try:
        return int(value)
    except (TypeError, ValueError):
        raise BridgeValidationError(f"{field_name} must be an integer.") from None


def _require_dict(value: Any, field_name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise BridgeValidationError(f"{field_name} must be an object.")
    return value
