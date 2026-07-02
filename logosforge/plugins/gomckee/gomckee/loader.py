from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

from .errors import ValidationError
from .models import Check, Conflict, DomainSystem, Method, Trigger


class CanonicalLoader:
    def __init__(self, plugin_root: Path) -> None:
        self.plugin_root = Path(plugin_root)

    def load_all(self) -> Dict[str, DomainSystem]:
        systems = {}
        for filename in ("story_system.json", "character_system.json", "dialogue_system.json"):
            system = self._load_one(self.plugin_root / filename)
            systems[system.domain] = system
        return systems

    def _load_one(self, path: Path) -> DomainSystem:
        data = json.loads(path.read_text(encoding="utf-8"))
        required = ["domain", "principles", "methods", "triggers", "checks", "conflicts", "meta"]
        missing = [key for key in required if key not in data]
        if missing:
            raise ValidationError(f"{path.name}: missing keys: {missing}")

        methods: Dict[str, Method] = {}
        for raw in data["methods"]:
            method = Method(
                id=raw["id"],
                name=raw["name"],
                goal=raw["goal"],
                rules=list(raw.get("rules", [])),
                applies_to=raw.get("applies_to"),
                priority=int(raw.get("priority", 0)),
            )
            if method.id in methods:
                raise ValidationError(f"{path.name}: duplicate method id {method.id}")
            methods[method.id] = method

        triggers: List[Trigger] = []
        for raw in data["triggers"]:
            trigger = Trigger(
                id=raw["id"],
                condition=raw["condition"],
                apply_methods=list(raw.get("apply_methods", [])),
            )
            for method_id in trigger.apply_methods:
                if method_id not in methods:
                    raise ValidationError(
                        f"{path.name}: trigger {trigger.id} references missing method {method_id}"
                    )
            triggers.append(trigger)

        checks: List[Check] = [
            Check(
                id=raw["id"],
                applies_to=raw.get("applies_to"),
                questions=list(raw.get("questions", [])),
            )
            for raw in data["checks"]
        ]

        conflicts: List[Conflict] = []
        for raw in data["conflicts"]:
            method_a = raw.get("method_a")
            method_b = raw.get("method_b")
            resolution = raw.get("resolution", "")
            for method_id in (method_a, method_b):
                if method_id not in methods:
                    raise ValidationError(
                        f"{path.name}: conflict references missing method {method_id}"
                    )
            conflicts.append(
                Conflict(method_a=method_a, method_b=method_b, resolution=resolution)
            )

        return DomainSystem(
            domain=data["domain"],
            principles=list(data["principles"]),
            methods=methods,
            triggers=triggers,
            checks=checks,
            conflicts=conflicts,
            meta=dict(data.get("meta", {})),
        )
