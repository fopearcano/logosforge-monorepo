"""CONNECTOR Action Registry — defines and registers available actions.

Central registry of all actions exposed to local AI models. Each action
has a name, parameter schema, classification (read/write), and handler.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class ActionParam:
    name: str
    param_type: str  # "int", "str", "bool"
    required: bool = True
    default: Any = None


@dataclass
class ActionDef:
    name: str
    description: str
    category: str  # "read" or "write"
    params: list[ActionParam] = field(default_factory=list)
    handler: Callable[..., Any] | None = None


_REGISTRY: dict[str, ActionDef] = {}


def register(action_def: ActionDef) -> ActionDef:
    _REGISTRY[action_def.name] = action_def
    return action_def


def get_action(name: str) -> ActionDef | None:
    return _REGISTRY.get(name)


def list_actions() -> list[ActionDef]:
    return list(_REGISTRY.values())


def list_action_names() -> list[str]:
    return list(_REGISTRY.keys())


def describe_action(name: str) -> dict[str, Any] | None:
    action = _REGISTRY.get(name)
    if action is None:
        return None
    return {
        "name": action.name,
        "description": action.description,
        "category": action.category,
        "params": [
            {
                "name": p.name,
                "type": p.param_type,
                "required": p.required,
            }
            for p in action.params
        ],
    }


def describe_all_actions() -> list[dict[str, Any]]:
    return [describe_action(name) for name in _REGISTRY]
