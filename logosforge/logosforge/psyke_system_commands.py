"""PSYKE system command handlers — /create, /open, /go, /ai.

All data operations route through the Connector executor for
validation, structured results, and consistent error handling.
UI navigation callbacks remain separate — they are view concerns.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from logosforge.assistant import PRESET_ACTIONS
from logosforge.connector_executor import execute_action
from logosforge.psyke_command_registry import CommandContext, CommandRegistry

if TYPE_CHECKING:
    from logosforge.db import Database

_AI_ACTIONS = {k.lower(): k for k in PRESET_ACTIONS}


class SystemCommandHandlers:
    """Stateful handler set — routes data through Connector, UI through callbacks."""

    def __init__(
        self,
        db: Database,
        project_id: int,
        *,
        open_scene: Any | None = None,
        open_psyke_entry: Any | None = None,
        get_active_scene_id: Any | None = None,
        get_selected_text: Any | None = None,
        run_ai_action: Any | None = None,
        on_data_changed: Any | None = None,
    ) -> None:
        self._db = db
        self._project_id = project_id
        self._open_scene = open_scene
        self._open_psyke_entry = open_psyke_entry
        self._get_active_scene_id = get_active_scene_id
        self._get_selected_text = get_selected_text
        self._run_ai_action = run_ai_action
        self._on_data_changed = on_data_changed

    def set_project(self, project_id: int) -> None:
        self._project_id = project_id

    def _exec(self, action: str, args: dict | None = None) -> dict:
        return execute_action(
            self._db, self._project_id,
            {"action": action, "args": args or {}},
            enforce_settings=False,
        )

    def register_all(self, registry: CommandRegistry) -> None:
        registry.register("create", self.handle_create, description="Create a PSYKE entry")
        registry.register("open", self.handle_open, description="Open a scene or entry")
        registry.register("go", self.handle_go, description="Navigate scenes", aliases=["goto"])
        registry.register(
            "ai", self.handle_ai,
            description="AI writing actions",
            aliases=["ask"],
        )
        registry.register(
            "idea", self.handle_idea,
            description="Controlling Idea — set / explain / check / link / scene",
        )
        registry.register(
            "strategy", self.handle_strategy,
            description="Strategy router — explain / mode <engine> / off / on",
        )

    def handle_strategy(self, ctx: CommandContext) -> dict:
        """`/strategy [explain|mode <engine>|off|on]` — inspect/steer routing."""
        from logosforge.logos.strategy.router import StrategyRouter

        args = [a.strip() for a in (ctx.args or []) if a.strip()]
        sub = args[0].lower() if args else "explain"
        try:
            from logosforge.settings import get_manager
            mgr = get_manager()
        except Exception:
            mgr = None

        if sub == "off":
            if mgr:
                mgr.set("strategy_enabled", False)
            return {"ok": True, "show_message": True,
                    "message": "Strategy layer disabled."}
        if sub == "on":
            if mgr:
                mgr.set("strategy_enabled", True)
            return {"ok": True, "show_message": True,
                    "message": "Strategy layer enabled."}
        if sub == "mode":
            from logosforge.logos.strategy.registry import MEDIUM_STRATEGY
            engine = args[1].lower() if len(args) > 1 else ""
            if engine not in MEDIUM_STRATEGY and engine != "":
                return {"ok": False,
                        "error": f"Unknown mode '{engine}'. Valid: "
                                 + ", ".join(MEDIUM_STRATEGY)}
            if mgr:
                mgr.set("strategy_user_mode_override", engine)
            label = engine or "auto (project mode)"
            return {"ok": True, "show_message": True,
                    "message": f"Strategy override set to: {label}."}

        # Default / explain: report the active decision.
        decision = StrategyRouter(self._db, self._project_id).decide()
        if self._on_data_changed is not None:
            self._on_data_changed()
        return {"ok": True, "show_message": True, "message": decision.explanation}

    def handle_idea(self, ctx: CommandContext) -> dict:
        from logosforge.controlling_idea import handle_command
        result = handle_command(self._db, self._project_id, ctx.args)
        if self._on_data_changed is not None:
            self._on_data_changed()
        return {
            "ok": result["status"] == "ok",
            "message": result["message"],
            "error": "" if result["status"] == "ok" else result["message"],
        }

    def handle_create(self, ctx: CommandContext) -> dict:
        entry_type = ctx.first_arg.lower() if ctx.first_arg else "other"
        valid_types = ("character", "place", "object", "lore", "theme", "other")
        if entry_type not in valid_types:
            return {"ok": False, "error": f"Unknown type '{entry_type}'. Use: {', '.join(valid_types)}"}

        name = ctx.arg_text_after(1) if len(ctx.args) > 1 else ""
        if not name:
            name = f"New {entry_type.title()}"

        result = self._exec("create_psyke_entry", {
            "name": name,
            "entry_type": entry_type,
        })
        if not result["ok"]:
            return result

        entry_data = result["result"]
        if self._on_data_changed:
            self._on_data_changed()
        if self._open_psyke_entry:
            self._open_psyke_entry(entry_data["id"])
        return {
            "ok": True,
            "entry_id": entry_data["id"],
            "name": entry_data["name"],
            "type": entry_data["entry_type"],
        }

    def handle_open(self, ctx: CommandContext) -> dict:
        if not ctx.args:
            return {"ok": False, "error": "Usage: /open scene <id> | /open psyke <name>"}

        target = ctx.args[0].lower()
        rest = ctx.args[1:]

        if target == "scene":
            return self._open_scene_by_arg(rest)

        if target == "psyke":
            return self._open_psyke_by_arg(rest)

        return {"ok": False, "error": f"Unknown target '{target}'. Use: scene, psyke"}

    def handle_go(self, ctx: CommandContext) -> dict:
        if not ctx.args:
            return {"ok": False, "error": "Usage: /go scene next|previous|<id>"}

        target = ctx.args[0].lower()
        rest = ctx.args[1:]

        if target == "scene":
            return self._go_scene(rest)

        return {"ok": False, "error": f"Unknown target '{target}'. Use: scene"}

    def _open_scene_by_arg(self, args: list[str]) -> dict:
        if not args:
            return {"ok": False, "error": "Usage: /open scene <id>"}

        try:
            scene_id = int(args[0])
        except ValueError:
            return {"ok": False, "error": f"Invalid scene id: '{args[0]}'"}

        result = self._exec("get_scene", {"scene_id": scene_id})
        if not result["ok"]:
            return {"ok": False, "error": f"Scene {scene_id} not found"}

        if self._open_scene:
            self._open_scene(scene_id)
        return {"ok": True, "scene_id": scene_id}

    def _open_psyke_by_arg(self, args: list[str]) -> dict:
        if not args:
            return {"ok": False, "error": "Usage: /open psyke <name>"}

        query = " ".join(args).strip()
        from logosforge.psyke_search import PsykeSearchIndex

        index = PsykeSearchIndex(self._db, self._project_id)
        resolved = index.resolve_entity(query)
        if resolved is None:
            return {"ok": False, "error": f"No entry matching '{query}'"}

        result = self._exec("get_psyke_entry", {"entry_id": resolved.entry_id})
        if not result["ok"]:
            return {"ok": False, "error": f"Entry {resolved.entry_id} not found"}

        if self._open_psyke_entry:
            self._open_psyke_entry(resolved.entry_id)
        return {"ok": True, "entry_id": resolved.entry_id, "name": resolved.name}

    def _go_scene(self, args: list[str]) -> dict:
        if not args:
            return {"ok": False, "error": "Usage: /go scene next|previous|<id>"}

        direction = args[0].lower()

        if direction not in ("next", "previous", "prev"):
            try:
                scene_id = int(direction)
            except ValueError:
                return {"ok": False, "error": f"Unknown direction '{direction}'. Use: next, previous, or a scene id"}
            result = self._exec("get_scene", {"scene_id": scene_id})
            if not result["ok"]:
                return {"ok": False, "error": f"Scene {scene_id} not found"}
            if self._open_scene:
                self._open_scene(scene_id)
            return {"ok": True, "scene_id": scene_id}

        result = self._exec("list_scenes")
        if not result["ok"]:
            return result
        scenes = result["result"]
        if not scenes:
            return {"ok": False, "error": "No scenes in project"}

        current_id = self._get_active_scene_id() if self._get_active_scene_id else None
        if current_id is None:
            target = scenes[0]
        else:
            ids = [s["id"] for s in scenes]
            try:
                idx = ids.index(current_id)
            except ValueError:
                target = scenes[0]
                idx = -1

            if direction == "next":
                idx = min(idx + 1, len(scenes) - 1)
            else:
                idx = max(idx - 1, 0)
            target = scenes[idx]

        if self._open_scene:
            self._open_scene(target["id"])
        return {"ok": True, "scene_id": target["id"]}

    def handle_ai(self, ctx: CommandContext) -> dict:
        action = ctx.first_arg.lower() if ctx.first_arg else ""
        if not action:
            available = ", ".join(sorted(_AI_ACTIONS.keys()))
            return {"ok": False, "error": f"Usage: /ai <action>. Available: {available}"}

        if action not in _AI_ACTIONS:
            available = ", ".join(sorted(_AI_ACTIONS.keys()))
            return {"ok": False, "error": f"Unknown action '{action}'. Available: {available}"}

        if not self._run_ai_action:
            return {"ok": False, "error": "AI assistant not available"}

        selected = self._get_selected_text() if self._get_selected_text else ""
        started = self._run_ai_action(action, selected)
        if not started:
            return {"ok": False, "error": "AI is busy or no context available"}
        return {"ok": True, "action": action}
