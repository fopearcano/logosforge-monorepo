from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, Optional

from .service import GoMcKeeService


class GoMcKeePlugin:
    def __init__(self, api: Any, plugin_root: Path) -> None:
        self.api = api
        self.plugin_root = Path(plugin_root)
        self.service = GoMcKeeService(self.plugin_root)
        self.enabled = True
        self.last_result = None

    def register(self) -> None:
        self.api.log("Go McKee plugin loaded.")
        self.api.register_menu_action("Go McKee: Enable", self.enable)
        self.api.register_menu_action("Go McKee: Disable", self.disable)
        self.api.register_menu_action("Go McKee: Explain Current Project", self.explain_project)
        self.api.register_menu_action("Go McKee: Run Checks on Current Project", self.check_project)
        self.api.register_menu_action("Go McKee: Story Focus", lambda: self.force_domain("story"))
        self.api.register_menu_action("Go McKee: Character Focus", lambda: self.force_domain("character"))
        self.api.register_menu_action("Go McKee: Dialogue Focus", lambda: self.force_domain("dialogue"))
        self.api.register_menu_action("Go McKee: All Domains", lambda: self.force_domain("all"))

    def enable(self) -> None:
        self.enabled = True
        self._persist_enabled(True)
        self.api.show_message(
            "Go McKee",
            "Go McKee is ON — it now shapes Assistant suggestions for this "
            "project.",
        )

    def disable(self) -> None:
        self.enabled = False
        self._persist_enabled(False)
        self.api.show_message(
            "Go McKee",
            "Go McKee is OFF — Assistant suggestions return to standard.",
        )

    def _persist_enabled(self, enabled: bool) -> None:
        """Persist the real toggle so is_gomckee_enabled() (and the Assistant
        context) genuinely follow these menu actions, not just a local flag."""
        setter = getattr(self.api, "set_self_enabled", None)
        if callable(setter):
            try:
                setter(enabled)
            except Exception as exc:  # pragma: no cover - defensive
                self.api.log(f"Go McKee: could not persist enabled state: {exc}")

    def explain_project(self) -> None:
        result = self.service.evaluate("/gomckee explain", enabled=self.enabled, project_data=self._project_data())
        self.last_result = result
        self.api.show_message("Go McKee Explain", result.explanation or "No explanation available.")

    def check_project(self) -> None:
        prompt = self._default_scene_prompt()
        result = self.service.evaluate(prompt + " /gomckee check", enabled=self.enabled, project_data=self._project_data())
        self.last_result = result
        text = self._format_check_results(result)
        self.api.show_message("Go McKee Checks", text)

    def force_domain(self, domain: str) -> None:
        cmd = f"/gomckee {domain}"
        result = self.service.evaluate(cmd, enabled=self.enabled, project_data=self._project_data())
        self.last_result = result
        body = result.explanation or result.command_effect or f"Forced domain: {domain}"
        self.api.show_message("Go McKee", body)

    def evaluate_prompt(self, prompt: str, forced_domains=None):
        """Future assistant hook entrypoint. Not wired by the current Logosforge example API."""
        self.last_result = self.service.evaluate(
            prompt,
            enabled=self.enabled,
            forced_domains=forced_domains,
            project_data=self._project_data(),
        )
        return self.last_result

    def _project_data(self) -> Dict[str, Any]:
        data = {
            "project_title": self._safe_call("get_project_title"),
            "scene_count": self._safe_call("get_scene_count"),
        }
        # These are optional future-facing PSYKE hooks. Missing methods are tolerated.
        optional_map = {
            "current_scene": "get_current_scene",
            "nearby_scenes": "get_nearby_scenes",
            "psyke_entries": "get_psyke_entries",
            "character_states": "get_character_states",
            "relations": "get_relations",
            "story_memory": "get_story_memory",
        }
        for key, attr in optional_map.items():
            data[key] = self._safe_call(attr)
        return data

    def _default_scene_prompt(self) -> str:
        title = self._safe_call("get_project_title") or "Untitled"
        count = self._safe_call("get_scene_count") or 0
        return f"This scene feels flat in project {title}. There are {count} scenes."

    def _safe_call(self, attr: str):
        fn = getattr(self.api, attr, None)
        if callable(fn):
            try:
                return fn()
            except Exception as exc:
                self.api.log(f"Go McKee optional API call failed: {attr}: {exc}")
        return None

    def _format_check_results(self, result) -> str:
        if not result.checks:
            return result.explanation or "No checks were produced."
        lines = [result.command_effect or "Go McKee checks"]
        for item in result.checks:
            lines.append(f"{item.domain}/{item.check_id}: {item.status} — {item.rationale}")
        return "\n".join(lines)
