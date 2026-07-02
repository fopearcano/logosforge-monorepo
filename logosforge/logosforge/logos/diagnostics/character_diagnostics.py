"""Character-focused narrative diagnostics (PSYKE characters)."""

from __future__ import annotations

from logosforge.logos.diagnostics.diagnostic import (
    CAT_CHARACTER,
    SEVERITY_IMPORTANT,
    SEVERITY_INFO,
    SEVERITY_WARNING,
    NarrativeDiagnostic,
)
from logosforge.logos.diagnostics.model import ProjectFacts, max_consecutive_absent

# Core character detail keys that signal a developed character.
_CORE_KEYS = ("goals", "background", "personality", "voice", "arc", "desires", "needs")
_GAP_THRESHOLD = 4  # consecutive absent scenes that count as a disappearance


def detect_characters(facts: ProjectFacts) -> list[NarrativeDiagnostic]:
    out: list[NarrativeDiagnostic] = []
    chars = facts.entries_of_type("character")
    for e in chars:
        details = facts.details.get(e.id, {})
        appears = facts.appearances.get(e.id, [])
        progressions = facts.progressions.get(e.id, [])
        relations = facts.relations.get(e.id, [])
        n_app = len(appears)

        # Missing core details (more confident the more the character appears).
        has_core = bool((e.notes or "").strip()) or any(
            str(details.get(k, "")).strip() for k in _CORE_KEYS
        )
        if not has_core:
            conf = min(0.92, 0.7 + 0.04 * n_app)
            sev = SEVERITY_IMPORTANT if n_app >= 3 else SEVERITY_WARNING
            out.append(NarrativeDiagnostic(
                category=CAT_CHARACTER, section_name="PSYKE",
                title=f"'{e.name}' has no goals/background/voice",
                message="This character has no core detail fields filled in.",
                evidence=f"No goals/background/voice/arc; appears in {n_app} scene(s).",
                confidence=conf, severity=sev,
                target_type="psyke_entry", target_id=str(e.id),
                related_psyke_entry_ids=[e.id],
                suggested_actions=["find_missing_details", "suggest_details"],
            ))

        # No progression states for a recurring character.
        if n_app >= 3 and not progressions:
            out.append(NarrativeDiagnostic(
                category=CAT_CHARACTER, section_name="PSYKE",
                title=f"'{e.name}' has no arc movement",
                message="A recurring character with no progression entries.",
                evidence=f"0 progressions; appears in {n_app} scene(s).",
                confidence=0.75, severity=SEVERITY_WARNING,
                target_type="psyke_entry", target_id=str(e.id),
                related_psyke_entry_ids=[e.id],
                suggested_actions=["suggest_arc_development", "suggest_progression"],
            ))

        # Disappearance: appears early, then a long absence.
        if n_app >= 2:
            gap = max_consecutive_absent(appears, facts.total_scenes)
            if gap >= _GAP_THRESHOLD:
                out.append(NarrativeDiagnostic(
                    category=CAT_CHARACTER, section_name="PSYKE",
                    title=f"'{e.name}' disappears for {gap} scenes",
                    message="This character vanishes for a long stretch.",
                    evidence=f"Appears at scenes {_fmt(appears)}; "
                             f"absent for {gap} consecutive scene(s).",
                    confidence=min(0.9, 0.65 + 0.03 * gap),
                    severity=SEVERITY_WARNING,
                    target_type="psyke_entry", target_id=str(e.id),
                    related_psyke_entry_ids=[e.id],
                    suggested_actions=["suggest_arc_development", "counterpart_critique"],
                ))

        # Has relations but never appears in any scene.
        if relations and n_app == 0:
            out.append(NarrativeDiagnostic(
                category=CAT_CHARACTER, section_name="PSYKE",
                title=f"'{e.name}' is related but never appears",
                message="This character has relations but no scene appearances.",
                evidence=f"{len(relations)} relation(s); 0 scene appearances.",
                confidence=0.8, severity=SEVERITY_INFO,
                target_type="psyke_entry", target_id=str(e.id),
                related_psyke_entry_ids=[e.id],
                suggested_actions=["suggest_relations", "counterpart_critique"],
            ))
    return out


def _fmt(orders: list[int]) -> str:
    if not orders:
        return "—"
    head = ", ".join(str(o) for o in orders[:5])
    return head + ("…" if len(orders) > 5 else "")
