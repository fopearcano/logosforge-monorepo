"""Setup / payoff diagnostics — inferred lightly from objects, notes, relations.

Explicit setup/payoff fields are limited, so these are *low-to-medium* confidence
inferences (objects that never recur, notes tagged setup/payoff without a
counterpart). Confidence is deliberately conservative.
"""

from __future__ import annotations

from logosforge.logos.diagnostics.diagnostic import (
    CAT_SETUP_PAYOFF,
    SEVERITY_INFO,
    NarrativeDiagnostic,
)
from logosforge.logos.diagnostics.model import ProjectFacts

_SETUP_TAGS = {"setup", "plant", "promise"}
_PAYOFF_TAGS = {"payoff", "resolution", "reveal"}


def detect_setup_payoff(facts: ProjectFacts) -> list[NarrativeDiagnostic]:
    out: list[NarrativeDiagnostic] = []

    # Object/lore introduced but apparently never reused (appears 0–1 times).
    for e in facts.entries_of_type("object", "lore"):
        appears = facts.appearances.get(e.id, [])
        relations = facts.relations.get(e.id, [])
        has_payoff_rel = any(rt in ("payoff", "supports_setup") for _x, rt in relations)
        if len(appears) <= 1 and not has_payoff_rel and (e.notes or "").strip():
            out.append(NarrativeDiagnostic(
                category=CAT_SETUP_PAYOFF, section_name="PSYKE",
                title=f"'{e.name}' may be set up but never paid off",
                message="This object/lore is introduced but rarely recurs.",
                evidence=f"Appears in {len(appears)} scene(s); "
                         "no setup/payoff relation.",
                confidence=0.6, severity=SEVERITY_INFO,
                target_type="psyke_entry", target_id=str(e.id),
                related_psyke_entry_ids=[e.id],
                suggested_actions=["suggest_setup_payoff_link", "suggest_relations"],
            ))

    # Notes tagged setup/payoff with no matching counterpart note.
    setups, payoffs = [], []
    for n in facts.notes:
        tags = {t.strip().lower() for t in (n.tags or "").split(",") if t.strip()}
        if tags & _SETUP_TAGS:
            setups.append(n)
        if tags & _PAYOFF_TAGS:
            payoffs.append(n)
    if setups and not payoffs:
        out.append(NarrativeDiagnostic(
            category=CAT_SETUP_PAYOFF, section_name="Plot",
            title="Setup notes have no payoff",
            message="Notes tagged as setups have no matching payoff note.",
            evidence=f"{len(setups)} setup-tagged note(s); 0 payoff-tagged.",
            confidence=0.6, severity=SEVERITY_INFO,
            target_type="notes", target_id="setup_without_payoff",
            suggested_actions=["suggest_setup_payoff_link"],
        ))
    if payoffs and not setups:
        out.append(NarrativeDiagnostic(
            category=CAT_SETUP_PAYOFF, section_name="Plot",
            title="Payoff notes have no setup",
            message="Notes tagged as payoffs have no matching setup note.",
            evidence=f"{len(payoffs)} payoff-tagged note(s); 0 setup-tagged.",
            confidence=0.6, severity=SEVERITY_INFO,
            target_type="notes", target_id="payoff_without_setup",
            suggested_actions=["suggest_setup_payoff_link"],
        ))
    return out
