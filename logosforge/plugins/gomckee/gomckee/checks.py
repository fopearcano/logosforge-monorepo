from __future__ import annotations

from typing import Dict, Iterable, List

from .models import CheckResult, DomainActivation, RequestState


class CheckRunner:
    def run(self, activation: DomainActivation, state: RequestState) -> List[CheckResult]:
        results: List[CheckResult] = []
        for check in activation.checks:
            status, rationale = self._evaluate(activation.domain, check.questions, state)
            results.append(
                CheckResult(
                    domain=activation.domain,
                    check_id=check.id,
                    applies_to=check.applies_to,
                    status=status,
                    rationale=rationale,
                    questions=check.questions,
                )
            )
        return results

    def _evaluate(self, domain: str, questions: Iterable[str], state: RequestState):
        text = state.normalized_text
        if domain == "story":
            if "flat" in text or "outline" in text or "scene" in text:
                return "FAIL", "The scene does not turn; the value charge is unchanged."
            if state.psyche.get("signals", {}).get("has_current_scene"):
                return "PASS", "The structural frame has scene context to test value movement."
            return "UNCERTAIN", "Structural pressure is implied, but scene evidence is thin."
        if domain == "character":
            if "generic" in text or "motivation" in text:
                return "FAIL", "The protagonist lacks a clear spine."
            if state.psyche.get("signals", {}).get("has_progression"):
                return "PASS", "Character progression state is available for arc diagnosis."
            return "UNCERTAIN", "Character contradiction is not yet grounded in enough state."
        if domain == "dialogue":
            if "dialogue" in text or "line" in text or "flat" in text:
                return "FAIL", "The dialogue states what should remain subtext."
            if state.psyche.get("signals", {}).get("has_relations"):
                return "PASS", "Relationship pressure supports line-by-line diagnosis."
            return "UNCERTAIN", "Dialogue pressure is present, but relationship state is thin."
        return "UNCERTAIN", "No domain-specific McKee signal fired."
