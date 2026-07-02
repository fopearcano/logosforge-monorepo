"""AI-based intent fallback — calls local LLM when rules fail."""

from __future__ import annotations

import json
import logging
from typing import Any

from logosforge.assistant import chat_completion
from logosforge.providers import ProviderConfig
from logosforge.psyke_intents import Intent

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You convert user input into structured command JSON.\n"
    "Return ONLY JSON — no explanation, no markdown, no extra text.\n"
    "\n"
    "Valid actions:\n"
    "  open_scene      — args: {id: int} or {direction: \"next\"|\"previous\"}\n"
    "  open_entry      — args: {name: string}\n"
    "  create_entry    — args: {entry_type: string, name: string}\n"
    "  go_scene        — args: {direction: \"next\"|\"previous\"} or {id: int}\n"
    "  insert_entity   — args: {name: string}\n"
    "  ai_action       — args: {action: \"rewrite\"|\"expand\"|\"summarize\"|\"condense\"|\"dialogue\"|\"tension\"|\"pacing\"}\n"
    "  delete_entry    — args: {name: string}\n"
    "  rename_entry    — args: {name: string, new_name: string}\n"
    "\n"
    "If the input doesn't match any action, return: {\"action\": null}\n"
    "\n"
    "Format: {\"action\": \"<action>\", \"args\": {<args>}}"
)

_VALID_ACTIONS = frozenset({
    "open_scene", "open_entry", "create_entry", "go_scene",
    "insert_entity", "ai_action", "delete_entry", "rename_entry",
})

_TIMEOUT = 10


def _build_provider() -> ProviderConfig:
    # Delegates to the single shared provider builder (Phase 8B).
    from logosforge.providers import build_active_provider
    return build_active_provider()


def detect_intent_llm(text: str) -> Intent | None:
    """Call local LLM to classify intent when rules fail.

    Returns an Intent on success, None if the LLM can't classify or
    is unreachable. Never raises — errors are logged and swallowed.
    """
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": text},
    ]

    try:
        provider = _build_provider()
        response, _cached = chat_completion(
            messages,
            provider=provider,
            timeout=_TIMEOUT,
            use_cache=True,
        )
    except (ConnectionError, RuntimeError, OSError) as exc:
        logger.debug("LLM intent detection unavailable: %s", exc)
        return None

    return _parse_response(response)


def _parse_response(response: str) -> Intent | None:
    """Validate LLM JSON response into an Intent."""
    response = response.strip()
    if response.startswith("```"):
        response = response.split("\n", 1)[-1]
        if response.endswith("```"):
            response = response[:-3].strip()

    try:
        data = json.loads(response)
    except json.JSONDecodeError:
        logger.debug("LLM returned invalid JSON: %s", response[:200])
        return None

    if not isinstance(data, dict):
        return None

    action = data.get("action")
    if action is None or action not in _VALID_ACTIONS:
        return None

    args = data.get("args", {})
    if not isinstance(args, dict):
        return None

    validated = _validate_args(action, args)
    if validated is None:
        return None

    return Intent(action=action, args=validated, confidence=0.6)


def _validate_args(action: str, args: dict[str, Any]) -> dict[str, str | int] | None:
    """Type-check and coerce args for known actions."""
    if action == "open_scene":
        if "id" in args:
            try:
                return {"id": int(args["id"])}
            except (ValueError, TypeError):
                return None
        if "direction" in args and args["direction"] in ("next", "previous"):
            return {"direction": args["direction"]}
        return None

    if action == "go_scene":
        if "id" in args:
            try:
                return {"id": int(args["id"])}
            except (ValueError, TypeError):
                return None
        if "direction" in args and args["direction"] in ("next", "previous"):
            return {"direction": args["direction"]}
        return None

    if action == "open_entry":
        name = args.get("name")
        if isinstance(name, str) and name.strip():
            return {"name": name.strip()}
        return None

    if action == "create_entry":
        entry_type = args.get("entry_type", "other")
        name = args.get("name", "")
        valid_types = ("character", "place", "object", "lore", "theme", "other")
        if entry_type not in valid_types:
            entry_type = "other"
        return {"entry_type": entry_type, "name": str(name).strip()}

    if action == "insert_entity":
        name = args.get("name")
        if isinstance(name, str) and name.strip():
            return {"name": name.strip()}
        return None

    if action == "ai_action":
        act = args.get("action", "")
        valid = ("rewrite", "expand", "summarize", "condense", "dialogue", "tension", "pacing")
        if act not in valid:
            return None
        return {"action": act}

    if action == "delete_entry":
        name = args.get("name")
        if isinstance(name, str) and name.strip():
            return {"name": name.strip()}
        return None

    if action == "rename_entry":
        name = args.get("name")
        new_name = args.get("new_name")
        if isinstance(name, str) and name.strip() and isinstance(new_name, str) and new_name.strip():
            return {"name": name.strip(), "new_name": new_name.strip()}
        return None

    return None
