"""Structure diagnostics — outline / plot / act-level (scene-derived)."""

from __future__ import annotations

from logosforge.logos.diagnostics.diagnostic import (
    CAT_STRUCTURE,
    SEVERITY_INFO,
    SEVERITY_WARNING,
    NarrativeDiagnostic,
)
from logosforge.logos.diagnostics.model import ProjectFacts

_MAX_EMPTY = 6


def detect_structure(facts: ProjectFacts) -> list[NarrativeDiagnostic]:
    out: list[NarrativeDiagnostic] = []
    scenes = facts.scenes
    if not scenes:
        return out

    # Outline nodes (scenes) with no dramatic function.
    empty = [s for s in scenes if not (s.summary or "").strip()
             and not (s.goal or "").strip()]
    for s in empty[:_MAX_EMPTY]:
        out.append(NarrativeDiagnostic(
            category=CAT_STRUCTURE, section_name="Outline",
            title="Outline node lacks dramatic function",
            message=f"'{(s.title or 'Untitled')[:40]}' has no summary or goal.",
            evidence="No summary and no goal set.",
            confidence=0.7, severity=SEVERITY_INFO,
            target_type="scene", target_id=str(s.id),
            related_scene_ids=[s.id],
            suggested_actions=["summarize_node", "identify_structure_problem"],
        ))

    # Plotline (plot block) whose scenes never state conflict.
    blocks: dict[str, list] = {}
    for s in scenes:
        blocks.setdefault((s.plotline or "").strip() or "Unassigned", []).append(s)
    for plotline, block in blocks.items():
        no_conflict = [s for s in block if not (s.conflict or "").strip()
                       and not (s.summary or "").strip()]
        if len(block) >= 2 and len(no_conflict) == len(block):
            out.append(NarrativeDiagnostic(
                category=CAT_STRUCTURE, section_name="Plot",
                title=f"Plotline '{plotline}' has no stated conflict",
                message="None of this plotline's scenes describe conflict or summary.",
                evidence=f"{len(block)} scene(s); 0 with conflict/summary.",
                confidence=0.72, severity=SEVERITY_WARNING,
                target_type="plotline", target_id=plotline,
                related_scene_ids=[s.id for s in block],
                suggested_actions=["identify_weak_conflict", "suggest_conflict_upgrade"],
            ))

    # Act with several scenes but no scene marked as a turning point/midpoint.
    acts: dict[str, list] = {}
    for s in scenes:
        acts.setdefault((s.act or "").strip() or "Untitled Act", []).append(s)
    for act, block in acts.items():
        if len(block) < 4:
            continue
        has_turn = any(_looks_like_turn(s) for s in block)
        if not has_turn:
            out.append(NarrativeDiagnostic(
                category=CAT_STRUCTURE, section_name="Outline",
                title=f"Act '{act}' has no clear turning point",
                message="A long act with no scene marked as a turn/midpoint/climax.",
                evidence=f"{len(block)} scenes; none marked turn/midpoint/climax "
                         "in beat/title.",
                confidence=0.66, severity=SEVERITY_INFO,
                target_type="act", target_id=act,
                related_scene_ids=[s.id for s in block],
                suggested_actions=["identify_structure_problem", "suggest_next_beat"],
            ))
    return out


_TURN_WORDS = ("turn", "midpoint", "climax", "reversal", "twist", "crisis")


def _looks_like_turn(scene) -> bool:
    blob = " ".join(filter(None, [scene.beat, scene.title])).lower()
    return any(w in blob for w in _TURN_WORDS)
