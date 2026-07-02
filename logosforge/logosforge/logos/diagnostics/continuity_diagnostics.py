"""Continuity diagnostics — progression / state consistency."""

from __future__ import annotations

from logosforge.logos.diagnostics.diagnostic import (
    CAT_CONTINUITY,
    SEVERITY_INFO,
    SEVERITY_WARNING,
    NarrativeDiagnostic,
)
from logosforge.logos.diagnostics.model import ProjectFacts


def detect_continuity(facts: ProjectFacts) -> list[NarrativeDiagnostic]:
    out: list[NarrativeDiagnostic] = []
    scene_ids = {s.id for s in facts.scenes}

    for e in facts.entries:
        progressions = facts.progressions.get(e.id, [])
        # Progression state changes that are not anchored to a scene.
        unanchored = [p for p in progressions if p.scene_id is None]
        if len(progressions) >= 2 and unanchored:
            out.append(NarrativeDiagnostic(
                category=CAT_CONTINUITY, section_name="PSYKE",
                title=f"'{e.name}' has progression(s) with no scene link",
                message="A state change is recorded without a linked scene.",
                evidence=f"{len(unanchored)} of {len(progressions)} "
                         "progression(s) have no scene_id.",
                confidence=0.7, severity=SEVERITY_INFO,
                target_type="psyke_entry", target_id=str(e.id),
                related_psyke_entry_ids=[e.id],
                suggested_actions=["check_continuity", "suggest_progression"],
            ))
        # Progression points to a scene that no longer exists.
        dangling = [p for p in progressions
                    if p.scene_id is not None and p.scene_id not in scene_ids]
        if dangling:
            out.append(NarrativeDiagnostic(
                category=CAT_CONTINUITY, section_name="PSYKE",
                title=f"'{e.name}' has a progression to a missing scene",
                message="A progression references a scene that no longer exists.",
                evidence=f"{len(dangling)} progression(s) point to deleted scenes.",
                confidence=0.85, severity=SEVERITY_WARNING,
                target_type="psyke_entry", target_id=str(e.id),
                related_psyke_entry_ids=[e.id],
                suggested_actions=["check_continuity"],
            ))
    return out
