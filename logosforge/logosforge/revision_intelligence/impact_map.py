"""Change Impact Map builder (Phase 10K).

Combines the diff, PSYKE impact, scene dependency, setup/payoff and continuity
layers into one deterministic, confidence-aware report for a scene change.
No LLM by default; no DB mutation unless ``save_report=True``; current project
only; capped output. Safe when ``before_text`` is missing (partial map).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from logosforge.revision_intelligence.diff import create_scene_diff
from logosforge.revision_intelligence.psyke_impact import detect_psyke_impact
from logosforge.revision_intelligence.scene_impact import (
    detect_scene_impacts, detect_setup_payoff_impacts, detect_continuity_impacts,
)


@dataclass
class RevisionImpactMapResult:
    scene_id: int | None = None
    revision_set_id: int | None = None
    draft_id: int | None = None
    summary: str = ""
    impact_level: str = "low"          # low | medium | high | critical
    confidence: str = "possible"
    direct_changes: dict = field(default_factory=dict)
    impacted_psyke_entries: list[dict] = field(default_factory=list)
    impacted_scenes: list[dict] = field(default_factory=list)
    setup_payoff_impacts: list[dict] = field(default_factory=list)
    continuity_impacts: list[dict] = field(default_factory=list)
    production_impacts: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    created_report_id: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "scene_id": self.scene_id, "revision_set_id": self.revision_set_id,
            "draft_id": self.draft_id, "summary": self.summary,
            "impact_level": self.impact_level, "confidence": self.confidence,
            "direct_changes": dict(self.direct_changes),
            "impacted_psyke_entries": list(self.impacted_psyke_entries),
            "impacted_scenes": list(self.impacted_scenes),
            "setup_payoff_impacts": list(self.setup_payoff_impacts),
            "continuity_impacts": list(self.continuity_impacts),
            "production_impacts": list(self.production_impacts),
            "warnings": list(self.warnings), "limitations": list(self.limitations),
            "created_report_id": self.created_report_id,
        }


def _impact_level(n_scenes: int, n_psyke: int, n_sp: int, severities: list[str]) -> str:
    if "blocking" in severities or "error" in severities:
        return "critical"
    total = n_scenes + n_psyke + n_sp
    if total >= 8 or "warning" in severities and total >= 5:
        return "high"
    if total >= 3:
        return "medium"
    return "low"


def build_revision_impact_map(
    db, project_id: int, *, scene_id: int, before_text: str | None = None,
    after_text: str | None = None, revision_set_id: int | None = None,
    draft_id: int | None = None, options: dict | None = None,
    save_report: bool = False,
) -> RevisionImpactMapResult:
    """Build (and optionally persist) a change-impact map for *scene_id*."""
    options = options or {}
    result = RevisionImpactMapResult(scene_id=scene_id,
                                     revision_set_id=revision_set_id, draft_id=draft_id)

    scene = None
    try:
        scene = db.get_scene_by_id(scene_id)
    except Exception:
        scene = None
    current = getattr(scene, "content", "") if scene is not None else ""
    after = after_text if after_text is not None else current
    if before_text is None:
        result.limitations.append(
            "No previous snapshot — partial map from the current scene only.")

    diff = create_scene_diff(before_text, after)
    result.direct_changes = diff.to_dict()

    result.impacted_psyke_entries = [
        i.to_dict() for i in detect_psyke_impact(db, project_id, before_text, after)]
    scene_impacts = detect_scene_impacts(db, project_id, scene_id, after_text=after)
    result.impacted_scenes = [s.to_dict() for s in scene_impacts]
    result.setup_payoff_impacts = detect_setup_payoff_impacts(db, project_id, scene_id)
    result.continuity_impacts = detect_continuity_impacts(
        db, project_id, scene_id, diff_result=diff)

    # Production context (only when a draft is active).
    try:
        draft = db.get_active_production_draft(project_id)
        if draft is not None:
            from logosforge.screenplay_production import scene_number_map
            info = scene_number_map(db, project_id).get(scene_id, {})
            result.production_impacts.append({
                "label": f"Scene number {info.get('number', '—')}"
                         + (" (OMITTED)" if info.get("omitted") else ""),
                "impact_kind": "production_risk",
                "severity": "warning" if info.get("omitted") else "info",
                "confidence": "confirmed",
                "explanation": "Active production draft.",
            })
            result.draft_id = result.draft_id or draft.id
    except Exception:
        pass

    severities = ([i["severity"] for i in result.setup_payoff_impacts]
                  + [s["severity"] for s in result.impacted_scenes]
                  + [c["severity"] for c in result.continuity_impacts]
                  + [p["severity"] for p in result.production_impacts])
    result.impact_level = _impact_level(
        len(scene_impacts), len(result.impacted_psyke_entries),
        len(result.setup_payoff_impacts), severities)
    confidences = [s["confidence"] for s in result.impacted_scenes]
    result.confidence = ("confirmed" if "confirmed" in confidences
                         else "likely" if "likely" in confidences else "possible")
    if diff.is_empty_change:
        result.warnings.append("No textual change detected for this scene.")
    result.summary = (
        f"Impact: {result.impact_level} ({result.confidence}). "
        f"{len(result.impacted_scenes)} scene(s), "
        f"{len(result.impacted_psyke_entries)} PSYKE entr(y/ies), "
        f"{len(result.setup_payoff_impacts)} setup/payoff risk(s)."
    )

    if save_report:
        items: list[dict] = []
        for p in result.impacted_psyke_entries:
            items.append({"target_type": "psyke_entry", "target_id": str(p["entry_id"]),
                          "label": p["name"], "impact_kind": p["impact_kind"],
                          "severity": "info", "confidence": p["confidence"],
                          "explanation": p["explanation"]})
        for s in result.impacted_scenes:
            items.append({"target_type": "scene", "target_id": str(s["scene_id"]),
                          "label": s["label"], "impact_kind": s["impact_kind"],
                          "severity": s["severity"], "confidence": s["confidence"],
                          "explanation": s["explanation"],
                          "suggested_action": s.get("suggested_action", "")})
        for sp in result.setup_payoff_impacts:
            items.append({"target_type": "setup_payoff", "target_id": "",
                          "label": sp["label"], "impact_kind": sp["impact_kind"],
                          "severity": sp["severity"], "confidence": sp["confidence"],
                          "explanation": sp.get("explanation", ""),
                          "suggested_action": sp.get("suggested_action", "")})
        report = db.create_revision_impact_report(
            project_id, scene_id=scene_id, revision_set_id=revision_set_id,
            draft_id=result.draft_id, title=f"Impact: scene {scene_id}",
            summary=result.summary, impact_level=result.impact_level,
            confidence=result.confidence, items=items,
            diff={"scene_id": scene_id, "revision_set_id": revision_set_id,
                  "before_hash": diff.before_hash, "after_hash": diff.after_hash,
                  "before_excerpt": diff.before_excerpt,
                  "after_excerpt": diff.after_excerpt})
        result.created_report_id = report.id
    return result
