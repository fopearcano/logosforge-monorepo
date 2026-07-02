from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from .checks import CheckRunner
from .classifier import DomainClassifier
from .commands import parse_gomckee_command
from .loader import CanonicalLoader
from .models import EngineResult
from .psyche import build_psyche_snapshot
from .resolver import ConflictResolver
from .router import DomainRouter
from .trigger_map import TriggerMap


class GoMcKeeService:
    def __init__(self, plugin_root: Path) -> None:
        self.plugin_root = Path(plugin_root)
        self.loader = CanonicalLoader(self.plugin_root)
        self.systems = self.loader.load_all()
        self.classifier = DomainClassifier(self.plugin_root)
        self.trigger_map = TriggerMap(self.plugin_root)
        self.router = DomainRouter(self.trigger_map)
        self.resolver = ConflictResolver()
        self.checks = CheckRunner()

    def evaluate(
        self,
        text: str,
        enabled: bool = True,
        forced_domains: Optional[List[str]] = None,
        project_data: Optional[Dict[str, Any]] = None,
    ) -> EngineResult:
        command, command_forced_domains = parse_gomckee_command(text)
        forced = forced_domains or command_forced_domains
        psyche = build_psyche_snapshot(project_data)
        state = self.classifier.classify(
            text=text,
            enabled=enabled,
            forced_domains=forced,
            command=command,
            psyche=psyche,
        )

        if command == "off":
            return EngineResult(
                enabled=False,
                command_effect="Go McKee disabled.",
                active_domains=[],
                activations=[],
                resolved_methods={},
                checks=[],
                constraints=[],
                explanation="Go McKee is OFF. Assistant behavior should remain standard.",
                state_snapshot=psyche,
            )

        if not enabled and command not in {"on", "check", "explain", "story", "character", "dialogue", "all"}:
            return EngineResult(
                enabled=False,
                command_effect=None,
                active_domains=[],
                activations=[],
                resolved_methods={},
                checks=[],
                constraints=[],
                explanation="Go McKee is OFF. Assistant behavior should remain standard.",
                state_snapshot=psyche,
            )

        active_domains = state.active_domains or ["story"]
        activations = []
        resolved_methods = {}
        constraints = []
        check_results = []

        for domain in active_domains:
            system = self.systems[domain]
            activation = self.router.activate(system, state)
            activation.methods = self.resolver.resolve(activation.methods, system.conflicts)
            activations.append(activation)
            resolved_methods[domain] = activation.methods
            constraints.extend(self._render_constraints(domain, activation.methods, psyche))
            if state.run_checks or command == "check":
                check_results.extend(self.checks.run(activation, state))

        explanation = None
        if state.explain or command in {"on", "story", "character", "dialogue", "all"}:
            explanation = self._explain(active_domains, activations, check_results, enabled=True)

        command_effect = None
        if command == "on":
            command_effect = "Go McKee enabled."
        elif command in {"story", "character", "dialogue", "all"}:
            command_effect = f"Forced domains: {', '.join(active_domains)}"
        elif command == "check":
            command_effect = "Go McKee checks executed."
        elif command == "explain":
            command_effect = "Go McKee explanation generated."

        return EngineResult(
            enabled=True,
            command_effect=command_effect,
            active_domains=active_domains,
            activations=activations,
            resolved_methods=resolved_methods,
            checks=check_results,
            constraints=constraints,
            explanation=explanation,
            state_snapshot=psyche,
        )

    def _render_constraints(self, domain: str, methods, psyche: Dict[str, Any]) -> List[str]:
        constraints = []
        for method in methods:
            if method.rules:
                constraints.append(f"[{domain}:{method.id}:{method.name}] " + " ".join(method.rules))
            else:
                constraints.append(f"[{domain}:{method.id}:{method.name}] apply craft pressure.")
        if domain == "character" and psyche.get("signals", {}).get("has_progression"):
            constraints.append("[character:PSYKE] Respect character progression state and active contradictions.")
        if domain == "dialogue" and psyche.get("signals", {}).get("has_relations"):
            constraints.append("[dialogue:PSYKE] Reflect active relationships and emotional state in line pressure.")
        if domain == "story" and psyche.get("signals", {}).get("has_current_scene"):
            constraints.append("[story:PSYKE] Use current scene context and nearby scenes for structural diagnosis.")
        return constraints

    def _explain(self, domains, activations, checks, enabled: bool) -> str:
        lines = [f"Go McKee enabled: {enabled}", f"Active domains: {', '.join(domains) if domains else 'none'}"]
        for activation in activations:
            method_names = ", ".join(f"{m.id}:{m.name}" for m in activation.methods[:6]) or "none"
            triggers = ", ".join(activation.matched_triggers) or "none"
            lines.append(f"- {activation.domain}: triggers={triggers}; methods={method_names}")
        if checks:
            lines.append("Checks:")
            for item in checks[:9]:
                lines.append(f"  - {item.domain}/{item.check_id}: {item.status} — {item.rationale}")
        return "\n".join(lines)
