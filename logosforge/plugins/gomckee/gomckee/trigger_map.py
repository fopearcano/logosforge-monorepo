from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict


class TriggerMap:
    def __init__(self, plugin_root: Path) -> None:
        cfg_path = Path(plugin_root) / "config" / "trigger_map.json"
        self.mapping: Dict[str, Dict[str, Any]] = json.loads(cfg_path.read_text(encoding="utf-8"))

    def domain_config(self, domain: str) -> Dict[str, Any]:
        return self.mapping.get(domain, {})
