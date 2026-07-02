"""Theme / controlling-idea diagnostics (PSYKE themes)."""

from __future__ import annotations

from logosforge.logos.diagnostics.diagnostic import (
    CAT_THEME,
    SEVERITY_IMPORTANT,
    SEVERITY_INFO,
    SEVERITY_WARNING,
    NarrativeDiagnostic,
)
from logosforge.logos.diagnostics.model import ProjectFacts, scene_act_for_order

_THEME_KEYS = ("statement", "argument", "positive", "negative", "symbols",
               "manifestation", "manifestations")


def detect_themes(facts: ProjectFacts) -> list[NarrativeDiagnostic]:
    out: list[NarrativeDiagnostic] = []
    themes = facts.entries_of_type("theme")
    for e in themes:
        details = facts.details.get(e.id, {})
        appears = facts.appearances.get(e.id, [])
        n = len(appears)

        # No manifestations / details.
        has_manifest = bool((e.notes or "").strip()) or any(
            str(details.get(k, "")).strip() for k in _THEME_KEYS
        )
        if not has_manifest:
            out.append(NarrativeDiagnostic(
                category=CAT_THEME, section_name="PSYKE",
                title=f"Theme '{e.name}' has no manifestations",
                message="This theme has no statement, symbols, or detail fields.",
                evidence="No theme detail fields and no notes.",
                confidence=0.78, severity=SEVERITY_WARNING,
                target_type="psyke_entry", target_id=str(e.id),
                related_psyke_entry_ids=[e.id],
                suggested_actions=["check_thematic_cluster", "suggest_details"],
            ))

        # Theme linked to no scenes at all.
        if n == 0:
            out.append(NarrativeDiagnostic(
                category=CAT_THEME, section_name="PSYKE",
                title=f"Theme '{e.name}' has no linked scenes",
                message="This theme never appears in any scene text.",
                evidence="0 scene appearances by name/alias.",
                confidence=0.72, severity=SEVERITY_INFO,
                target_type="psyke_entry", target_id=str(e.id),
                related_psyke_entry_ids=[e.id],
                suggested_actions=["check_thematic_cluster"],
            ))
        elif n == 1:
            out.append(NarrativeDiagnostic(
                category=CAT_THEME, section_name="PSYKE",
                title=f"Theme '{e.name}' appears only once",
                message="A theme that surfaces in a single scene rarely lands.",
                evidence="Appears in 1 linked scene only.",
                confidence=0.7, severity=SEVERITY_INFO,
                target_type="psyke_entry", target_id=str(e.id),
                related_psyke_entry_ids=[e.id],
                suggested_actions=["check_thematic_cluster", "suggest_relations"],
            ))
        else:
            # Theme present early and late but missing in the middle act.
            acts = {scene_act_for_order(facts, o) for o in appears}
            acts.discard("")
            if _has_act(acts, "I") and _has_act(acts, "III") and not _has_act(acts, "II"):
                out.append(NarrativeDiagnostic(
                    category=CAT_THEME, section_name="PSYKE",
                    title=f"Theme '{e.name}' vanishes in the middle",
                    message="Theme appears in the first and last acts but not the middle.",
                    evidence=f"Present in acts {sorted(acts)}; absent from Act II.",
                    confidence=0.7, severity=SEVERITY_WARNING,
                    target_type="psyke_entry", target_id=str(e.id),
                    related_psyke_entry_ids=[e.id],
                    suggested_actions=["check_thematic_cluster", "strengthen_conflict"],
                ))

    out.extend(_controlling_idea(facts))
    return out


def _controlling_idea(facts: ProjectFacts) -> list[NarrativeDiagnostic]:
    ci = facts.controlling_idea
    if ci is None or not getattr(ci, "enabled", False):
        return []
    alignment = getattr(ci, "scene_alignment", {}) or {}
    if not any(alignment.values()):
        statement = (getattr(ci, "statement", "") or "").strip()
        if statement:
            return [NarrativeDiagnostic(
                category=CAT_THEME, section_name="PSYKE",
                title="Controlling Idea not reflected in scenes",
                message="A Controlling Idea is defined but no scene is aligned to it.",
                evidence="Controlling Idea enabled with a statement; "
                         "0 scenes marked support/oppose/test.",
                confidence=0.75, severity=SEVERITY_IMPORTANT,
                target_type="controlling_idea", target_id="project",
                suggested_actions=["check_thematic_cluster", "counterpart_critique"],
            )]
    return []


def _has_act(acts: set[str], roman: str) -> bool:
    target = roman.upper()
    for a in acts:
        au = a.upper()
        if au.endswith(target) or au == f"ACT {target}" or au == target:
            return True
    return False
