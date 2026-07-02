"""Plugin manager — discovers, validates, and loads local plugins."""

from __future__ import annotations

import importlib.util
import json
import sys
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from logosforge.paths import get_plugins_path
from logosforge.settings import get_manager as get_settings

PLUGINS_DIR = get_plugins_path()


@dataclass
class PluginInfo:
    id: str
    name: str
    version: str
    author: str
    description: str
    path: Path
    entry_point: str = "plugin.py"
    enabled_by_default: bool = True
    enabled: bool = True
    loaded: bool = False
    error: str = ""
    logs: list[str] = field(default_factory=list)
    menu_actions: list[tuple[str, Callable]] = field(default_factory=list)


class PluginAPI:
    """Safe, minimal API surface exposed to plugins."""

    def __init__(self, plugin_info: PluginInfo, manager: PluginManager) -> None:
        self._info = plugin_info
        self._manager = manager

    def register_menu_action(self, name: str, callback: Callable) -> None:
        self._info.menu_actions.append((name, callback))

    def set_self_enabled(self, enabled: bool) -> None:
        """Persist this plugin's enabled toggle — the same source of truth as
        the Plugins-view checkbox (settings ``plugin_states``). Lets a plugin's
        own Enable/Disable actions genuinely gate its behaviour, not just flip a
        local flag."""
        self._manager.set_enabled(self._info.id, enabled)

    def is_self_enabled(self) -> bool:
        return self._manager.is_enabled(self._info.id)

    def log(self, message: str) -> None:
        self._info.logs.append(str(message))

    def show_message(self, title: str, message: str) -> None:
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.information(None, title, message)

    def get_project_title(self) -> str:
        if self._manager._db is None:
            return ""
        project = self._manager._db.get_project_by_id(self._manager._project_id)
        return project.title if project else ""

    def get_scene_titles(self) -> list[str]:
        if self._manager._db is None:
            return []
        scenes = self._manager._db.get_all_scenes(self._manager._project_id)
        return [s.title for s in scenes]

    def get_scene_count(self) -> int:
        if self._manager._db is None:
            return 0
        return len(self._manager._db.get_all_scenes(self._manager._project_id))


class PluginManager:
    def __init__(self) -> None:
        self._plugins: list[PluginInfo] = []
        self._db: Any = None
        self._project_id: int = 0

    def set_app_context(self, db: Any, project_id: int) -> None:
        self._db = db
        self._project_id = project_id

    @property
    def plugins(self) -> list[PluginInfo]:
        return list(self._plugins)

    def get_all_menu_actions(self) -> list[tuple[str, Callable]]:
        actions: list[tuple[str, Callable]] = []
        for p in self._plugins:
            if p.loaded:
                actions.extend(p.menu_actions)
        return actions

    def discover(self) -> None:
        self._plugins.clear()
        if not PLUGINS_DIR.is_dir():
            return
        for child in sorted(PLUGINS_DIR.iterdir()):
            if not child.is_dir():
                continue
            manifest_path = child / "plugin.json"
            if not manifest_path.is_file():
                continue
            info = self._parse_manifest(manifest_path, child)
            if info is not None:
                self._plugins.append(info)

    def load_enabled(self) -> None:
        for plugin in self._plugins:
            if plugin.enabled:
                self._load_plugin(plugin)

    def is_enabled(self, plugin_id: str) -> bool:
        states = get_settings().get("plugin_states")
        if isinstance(states, dict) and plugin_id in states:
            return bool(states[plugin_id])
        for p in self._plugins:
            if p.id == plugin_id:
                return p.enabled_by_default
        return True

    def set_enabled(self, plugin_id: str, enabled: bool) -> None:
        mgr = get_settings()
        states = mgr.get("plugin_states")
        if not isinstance(states, dict):
            states = {}
        states = dict(states)
        states[plugin_id] = enabled
        mgr.set("plugin_states", states)
        for p in self._plugins:
            if p.id == plugin_id:
                p.enabled = enabled
                break

    def _parse_manifest(self, path: Path, plugin_dir: Path) -> PluginInfo | None:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None

        required = ("id", "name", "version", "author", "description")
        for key in required:
            if key not in data:
                return None

        entry_point = data.get("entry_point", "plugin.py")
        entry_path = plugin_dir / entry_point
        if not entry_path.is_file():
            info = PluginInfo(
                id=data["id"],
                name=data["name"],
                version=data["version"],
                author=data["author"],
                description=data["description"],
                path=plugin_dir,
                entry_point=entry_point,
                enabled_by_default=data.get("enabled_by_default", True),
                error=f"Entry point '{entry_point}' not found.",
            )
            info.enabled = self.is_enabled(info.id)
            return info

        info = PluginInfo(
            id=data["id"],
            name=data["name"],
            version=data["version"],
            author=data["author"],
            description=data["description"],
            path=plugin_dir,
            entry_point=entry_point,
            enabled_by_default=data.get("enabled_by_default", True),
        )
        info.enabled = self.is_enabled(info.id)
        return info

    def _load_plugin(self, plugin: PluginInfo) -> None:
        if plugin.error:
            return
        entry_path = plugin.path / plugin.entry_point
        try:
            plugin_dir = str(plugin.path)
            if plugin_dir not in sys.path:
                sys.path.insert(0, plugin_dir)

            spec = importlib.util.spec_from_file_location(
                f"logosforge_plugin_{plugin.id}", str(entry_path),
            )
            if spec is None or spec.loader is None:
                plugin.error = "Could not create module spec."
                return
            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)

            register_fn = getattr(module, "register", None)
            if register_fn is None:
                plugin.error = "No register(api) function found."
                return

            api = PluginAPI(plugin, self)
            register_fn(api)
            plugin.loaded = True
        except Exception:
            plugin.error = traceback.format_exc()


_instance: PluginManager | None = None


def get_plugin_manager() -> PluginManager:
    global _instance
    if _instance is None:
        _instance = PluginManager()
    return _instance
