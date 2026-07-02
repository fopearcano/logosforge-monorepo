"""PSYKE natural language intent detection — rule-based.

Converts plain English phrases into structured Intent objects
without requiring slash-command syntax.

Examples:
    "open scene 3"         → Intent("open_scene", {"id": 3})
    "create character john" → Intent("create_entry", {"entry_type": "character", "name": "john"})
    "insert john"          → Intent("insert_entity", {"name": "john"})
    "go to next scene"     → Intent("go_scene", {"direction": "next"})
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Intent:
    """Structured representation of a detected user intent."""

    action: str
    args: dict[str, str | int] = field(default_factory=dict)
    confidence: float = 1.0


_ENTRY_TYPES = ("character", "place", "object", "lore", "theme", "other")

_RULES: list[tuple[re.Pattern, callable]] = []


def _rule(pattern: str, flags: int = re.IGNORECASE):
    """Decorator that registers a regex rule with its handler."""
    compiled = re.compile(pattern, flags)

    def decorator(func):
        _RULES.append((compiled, func))
        return func

    return decorator


# --- Open rules ---

@_rule(r"^open\s+scene\s+(\d+)$")
def _open_scene_by_id(m: re.Match) -> Intent:
    return Intent("open_scene", {"id": int(m.group(1))})


@_rule(r"^(?:open|show|view)\s+(?:entry|psyke)\s+(.+)$")
def _open_entry(m: re.Match) -> Intent:
    return Intent("open_entry", {"name": m.group(1).strip()})


@_rule(r"^open\s+(.+)$")
def _open_generic(m: re.Match) -> Intent:
    name = m.group(1).strip()
    if name.isdigit():
        return Intent("open_scene", {"id": int(name)})
    return Intent("open_entry", {"name": name})


# --- Create rules ---

@_rule(r"^(?:create|new|add)\s+(character|place|object|lore|theme|other)\s+(.+)$")
def _create_typed(m: re.Match) -> Intent:
    return Intent("create_entry", {
        "entry_type": m.group(1).lower(),
        "name": m.group(2).strip(),
    })


@_rule(r"^(?:create|new|add)\s+(character|place|object|lore|theme|other)$")
def _create_typed_no_name(m: re.Match) -> Intent:
    return Intent("create_entry", {"entry_type": m.group(1).lower(), "name": ""})


@_rule(r"^(?:create|new|add)\s+(.+)$")
def _create_generic(m: re.Match) -> Intent:
    name = m.group(1).strip()
    return Intent("create_entry", {"entry_type": "other", "name": name}, confidence=0.7)


# --- Navigation rules ---

@_rule(r"^(?:go\s+to|goto|next)\s+scene$")
def _go_next_scene_short(m: re.Match) -> Intent:
    return Intent("go_scene", {"direction": "next"})


@_rule(r"^(?:go\s+to|goto|go)\s+(?:scene\s+)?(next|previous|prev)(?:\s+scene)?$")
def _go_scene_direction(m: re.Match) -> Intent:
    direction = m.group(1).lower()
    if direction == "prev":
        direction = "previous"
    return Intent("go_scene", {"direction": direction})


@_rule(r"^(?:go\s+to|goto|go)\s+scene\s+(\d+)$")
def _go_scene_by_id(m: re.Match) -> Intent:
    return Intent("go_scene", {"id": int(m.group(1))})


@_rule(r"^(?:previous|prev)\s+scene$")
def _prev_scene_short(m: re.Match) -> Intent:
    return Intent("go_scene", {"direction": "previous"})


# --- Insert rules ---

@_rule(r"^insert\s+(.+)$")
def _insert_entity(m: re.Match) -> Intent:
    return Intent("insert_entity", {"name": m.group(1).strip()})


@_rule(r"^(?:use|mention|add)\s+(.+?)(?:\s+here)?$")
def _insert_synonym(m: re.Match) -> Intent:
    return Intent("insert_entity", {"name": m.group(1).strip()}, confidence=0.6)


# --- AI action rules ---

@_rule(r"^(?:ai\s+)?(rewrite|expand|summarize|condense|elaborate)\s*(.*)$")
def _ai_action(m: re.Match) -> Intent:
    action = m.group(1).lower()
    context = m.group(2).strip()
    args: dict[str, str | int] = {"action": action}
    if context:
        args["context"] = context
    return Intent("ai_action", args, confidence=0.8)


@_rule(r"^(?:make\s+(?:it|this)\s+)(shorter|longer|clearer|more\s+dramatic)$")
def _ai_rephrase(m: re.Match) -> Intent:
    modifier = m.group(1).strip().replace(" ", "_")
    action_map = {
        "shorter": "condense",
        "longer": "expand",
        "clearer": "rewrite",
        "more_dramatic": "rewrite",
    }
    return Intent("ai_action", {"action": action_map.get(modifier, "rewrite")}, confidence=0.7)


# --- Delete / rename rules ---

@_rule(r"^(?:delete|remove)\s+(?:entry\s+)?(.+)$")
def _delete_entity(m: re.Match) -> Intent:
    return Intent("delete_entry", {"name": m.group(1).strip()})


@_rule(r"^rename\s+(.+?)\s+(?:to|as)\s+(.+)$")
def _rename_entity(m: re.Match) -> Intent:
    return Intent("rename_entry", {
        "name": m.group(1).strip(),
        "new_name": m.group(2).strip(),
    })


# --- Public API ---

def detect_intent(text: str, *, use_llm: bool = False) -> Intent | None:
    """Attempt to detect a structured intent from natural language.

    Rules are evaluated first (fast, deterministic). If none match and
    use_llm is True, falls back to a local LLM for classification.
    """
    text = text.strip()
    if not text:
        return None

    for pattern, handler in _RULES:
        m = pattern.match(text)
        if m:
            return handler(m)

    if use_llm:
        from logosforge.psyke_intent_llm import detect_intent_llm
        return detect_intent_llm(text)

    return None


_INTENT_TO_COMMAND: dict[str, callable] = {}


def _maps(action: str):
    """Register an intent-to-command mapping."""
    def decorator(func):
        _INTENT_TO_COMMAND[action] = func
        return func
    return decorator


@_maps("open_scene")
def _cmd_open_scene(args: dict) -> str:
    return f"/open scene {args['id']}"


@_maps("open_entry")
def _cmd_open_entry(args: dict) -> str:
    return f"/open psyke {args['name']}"


@_maps("create_entry")
def _cmd_create_entry(args: dict) -> str:
    entry_type = args.get("entry_type", "other")
    name = args.get("name", "")
    if name:
        return f"/create {entry_type} {name}"
    return f"/create {entry_type}"


@_maps("go_scene")
def _cmd_go_scene(args: dict) -> str:
    if "id" in args:
        return f"/go scene {args['id']}"
    return f"/go scene {args['direction']}"


@_maps("insert_entity")
def _cmd_insert_entity(args: dict) -> str:
    return f"/insert {args['name']}"


@_maps("ai_action")
def _cmd_ai_action(args: dict) -> str:
    return f"/ai {args['action']}"


@_maps("delete_entry")
def _cmd_delete_entry(args: dict) -> str:
    return f"/delete {args['name']}"


@_maps("rename_entry")
def _cmd_rename_entry(args: dict) -> str:
    return f"/rename {args['name']} to {args['new_name']}"


def intent_to_command(intent: Intent) -> str | None:
    """Convert a detected Intent into a slash-command string.

    Returns a command string that can be fed into the existing command
    parser, or None if the intent has no command mapping.
    """
    mapper = _INTENT_TO_COMMAND.get(intent.action)
    if mapper is None:
        return None
    return mapper(intent.args)
