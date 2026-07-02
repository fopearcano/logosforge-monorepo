"""Plugin Registry — registers, lists, and retrieves plugins.

Central registry for all Logosforge plugins. Plugins register themselves
on import. The registry provides listing and lookup by name.
"""

from __future__ import annotations

from logosforge.plugin_base import LogosforgePlugin


_PLUGINS: dict[str, LogosforgePlugin] = {}


def register_plugin(plugin: LogosforgePlugin) -> None:
    _PLUGINS[plugin.name] = plugin


def get_plugin(name: str) -> LogosforgePlugin | None:
    return _PLUGINS.get(name)


def list_plugins() -> list[LogosforgePlugin]:
    return list(_PLUGINS.values())


def list_plugin_names() -> list[str]:
    return list(_PLUGINS.keys())


def list_plugins_by_category(category: str) -> list[LogosforgePlugin]:
    return [p for p in _PLUGINS.values() if p.category == category]


def describe_plugin(name: str) -> dict[str, str] | None:
    plugin = _PLUGINS.get(name)
    if plugin is None:
        return None
    return {
        "name": plugin.name,
        "description": plugin.description,
        "category": plugin.category,
        "requires_scene": str(plugin.requires_scene),
    }


def describe_all_plugins() -> list[dict[str, str]]:
    return [describe_plugin(name) for name in _PLUGINS]


def clear_registry() -> None:
    """Clear all registered plugins (for testing)."""
    _PLUGINS.clear()
