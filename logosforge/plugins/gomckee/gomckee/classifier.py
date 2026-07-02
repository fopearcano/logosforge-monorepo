from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional, Set

from .models import RequestState
from .utils import keyword_score, normalize_text, tokenize


class DomainClassifier:
    def __init__(self, plugin_root: Path) -> None:
        cfg_path = Path(plugin_root) / "config" / "classifier_keywords.json"
        self.config = json.loads(cfg_path.read_text(encoding="utf-8"))

    def classify(
        self,
        text: str,
        enabled: bool,
        forced_domains: Optional[List[str]] = None,
        command: Optional[str] = None,
        psyche: Optional[Dict] = None,
    ) -> RequestState:
        normalized = normalize_text(text)
        tokens = tokenize(text)
        mode = self._detect_mode(tokens, normalized)
        target_forms = self._detect_target_forms(tokens, normalized)
        forced = forced_domains[:] if forced_domains else None

        if forced:
            active_domains = forced
        else:
            active_domains = self._detect_domains(tokens, normalized, target_forms)

        run_checks = mode in {"revision", "diagnosis"} or command == "check"
        explain = command == "explain"

        return RequestState(
            text=text,
            normalized_text=normalized,
            command=command,
            enabled=enabled,
            active_domains=active_domains,
            forced_domains=forced,
            mode=mode,
            target_forms=target_forms,
            run_checks=run_checks,
            explain=explain,
            psyche=psyche or {},
        )

    def _detect_mode(self, tokens: List[str], normalized: str) -> str:
        modes = self.config["modes"]
        scores = {
            "diagnosis": keyword_score(tokens, modes["diagnosis"]),
            "revision": keyword_score(tokens, modes["revision"]),
            "generation": keyword_score(tokens, modes["generation"]),
        }
        # Diagnosis wins over revision when the user is asking what is wrong.
        return max(scores, key=lambda key: (scores[key], {"diagnosis": 3, "revision": 2, "generation": 1}[key]))

    def _detect_target_forms(self, tokens: List[str], normalized: str) -> Set[str]:
        result: Set[str] = set()
        for target, phrases in self.config["target_forms"].items():
            if keyword_score(tokens, phrases):
                result.add(target)
        if not result:
            result.add("analysis")
        return result

    def _detect_domains(self, tokens: List[str], normalized: str, target_forms: Set[str]) -> List[str]:
        purity_rules = self.config["purity_rules"]

        if any(phrase in normalized for phrase in purity_rules["dialogue_only_phrases"]):
            return ["dialogue"]
        if any(phrase in normalized for phrase in purity_rules["character_only_phrases"]):
            return ["character"]

        if "dialogue" in target_forms and target_forms == {"dialogue"}:
            return ["dialogue"]
        if "character" in target_forms and target_forms == {"character"}:
            return ["character"]
        if "outline" in target_forms:
            return ["story", "character"]

        scores = {
            "story": keyword_score(tokens, self.config["story"]["keywords"]),
            "character": keyword_score(tokens, self.config["character"]["keywords"]),
            "dialogue": keyword_score(tokens, self.config["dialogue"]["keywords"]),
        }

        active = []
        if scores["story"] > 0:
            active.append("story")
        if scores["character"] > 0:
            active.append("character")
        if scores["dialogue"] > 0:
            active.append("dialogue")

        if not active:
            active = ["story"]

        ordered = [domain for domain in ("story", "character", "dialogue") if domain in active]
        if "scene" in target_forms and "story" in ordered and "character" not in ordered:
            ordered.append("character")
        if "scene" in target_forms and "diagnosis" in {self._detect_mode(tokens, normalized)} and "dialogue" not in ordered:
            ordered.append("dialogue")
        return [domain for domain in ("story", "character", "dialogue") if domain in ordered]
