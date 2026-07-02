from __future__ import annotations

from typing import Dict, List, Set

from .models import DomainActivation, DomainSystem, Method, RequestState
from .trigger_map import TriggerMap
from .utils import ensure_list, normalize_text, tokenize


class DomainRouter:
    def __init__(self, trigger_map: TriggerMap) -> None:
        self.trigger_map = trigger_map

    def activate(self, system: DomainSystem, state: RequestState) -> DomainActivation:
        cfg = self.trigger_map.domain_config(system.domain)
        tokens = tokenize(state.text)
        normalized = normalize_text(state.text)
        matched_triggers: List[str] = []
        method_ids: List[str] = []

        for trigger in system.triggers:
            mapping = cfg.get(trigger.condition, {})
            if not self._trigger_matches(mapping, tokens, normalized, state):
                continue
            matched_triggers.append(trigger.id)
            for method_id in trigger.apply_methods:
                method = system.methods[method_id]
                if self._method_applies(method, state.target_forms):
                    if method_id not in method_ids:
                        method_ids.append(method_id)

        if not method_ids:
            compatible = [
                method for method in system.methods.values()
                if self._method_applies(method, state.target_forms)
            ]
            compatible.sort(key=lambda item: item.priority, reverse=True)
            method_ids = [method.id for method in compatible[:3]]

        methods = [system.methods[method_id] for method_id in method_ids]
        checks = [check for check in system.checks if self._check_applies(check.applies_to, state.target_forms)]
        return DomainActivation(
            domain=system.domain,
            matched_triggers=matched_triggers,
            activated_methods=method_ids,
            methods=methods,
            checks=checks,
        )

    def _trigger_matches(self, mapping: Dict, tokens: List[str], normalized: str, state: RequestState) -> bool:
        if not mapping:
            return False
        keywords = mapping.get("keywords", [])
        target_forms = set(mapping.get("target_forms", []))
        modes = set(mapping.get("modes", []))
        psyche_signals = mapping.get("psyche_signals", [])

        keyword_hit = False
        token_set = set(tokens)
        for keyword in keywords:
            parts = keyword.lower().split()
            if len(parts) == 1 and parts[0] in token_set:
                keyword_hit = True
                break
            if len(parts) > 1 and keyword.lower() in normalized:
                keyword_hit = True
                break

        target_ok = not target_forms or bool(set(state.target_forms) & target_forms)
        mode_ok = not modes or state.mode in modes
        psyche_ok = all(state.psyche.get("signals", {}).get(signal) for signal in psyche_signals)
        return keyword_hit and target_ok and mode_ok and psyche_ok

    def _method_applies(self, method: Method, target_forms: Set[str]) -> bool:
        applies_to = ensure_list(method.applies_to)
        if not applies_to:
            return True
        applies_set = {str(item).lower() for item in applies_to}
        return bool(applies_set & {item.lower() for item in target_forms})

    def _check_applies(self, applies_to, target_forms: Set[str]) -> bool:
        applies_set = {str(item).lower() for item in ensure_list(applies_to)}
        return not applies_set or bool(applies_set & {item.lower() for item in target_forms | {"analysis"}})
