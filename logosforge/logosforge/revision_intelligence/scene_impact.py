"""Scene dependency + setup/payoff + continuity impact (Phase 10K).

Finds scenes and chains that may be affected by a change to one scene. Confirmed
links are data-backed (StoryLinks, setup/payoff, same act, adjacency); inferred
links (shared character / location) are ``likely``/``possible``. Deterministic,
read-only, capped. No fake causality.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

_MAX_SCENES = 20
_HEADING_RE = re.compile(r"^(INT\.|EXT\.|INT\./EXT\.|EST\.|I/E\.)\s*(.+?)(?:\s*[-—].*)?$",
                         re.IGNORECASE | re.MULTILINE)


@dataclass
class SceneImpact:
    scene_id: int
    label: str
    impact_kind: str          # depends_on | mentions | setup_payoff | adjacent | ...
    confidence: str           # confirmed | likely | possible
    severity: str = "info"    # info | warning | error | blocking
    explanation: str = ""
    suggested_action: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"scene_id": self.scene_id, "label": self.label,
                "impact_kind": self.impact_kind, "confidence": self.confidence,
                "severity": self.severity, "explanation": self.explanation,
                "suggested_action": self.suggested_action}


def _scene_location(scene) -> str:
    head = (getattr(scene, "slugline", "") or "")
    m = _HEADING_RE.search(head or (getattr(scene, "content", "") or ""))
    return (m.group(2).strip().lower() if m else "")


def _character_cues(text: str):
    try:
        from logosforge import screenplay_blocks as sb
        return set(sb.character_cues(sb.parse_screenplay_text(text or "")))
    except Exception:
        return set()


def detect_scene_impacts(db, project_id: int, scene_id: int,
                         after_text: str | None = None) -> list[SceneImpact]:
    """Return capped affected-scene impacts for a change to *scene_id*."""
    try:
        scenes = db.get_all_scenes(project_id)
    except Exception:
        return []
    by_id = {s.id: s for s in scenes}
    src = by_id.get(scene_id)
    if src is None:
        return []
    impacts: dict[int, SceneImpact] = {}

    def add(sid, kind, conf, sev, expl, action=""):
        if sid == scene_id or sid not in by_id or sid in impacts:
            return
        impacts[sid] = SceneImpact(
            sid, getattr(by_id[sid], "title", "") or f"Scene {sid}",
            kind, conf, sev, expl, action)

    # --- Confirmed: StoryLinks referencing this scene ---
    try:
        for link in db.get_story_links(project_id):
            if link.status == "dismissed":
                continue
            if link.source_scene_id == scene_id and link.target_scene_id:
                add(link.target_scene_id, "depends_on", "confirmed", "warning",
                    f"Confirmed story link ({link.link_type}).",
                    "Re-check this linked scene.")
            elif link.target_scene_id == scene_id and link.source_scene_id:
                add(link.source_scene_id, "depends_on", "confirmed", "warning",
                    f"Confirmed story link ({link.link_type}).",
                    "Re-check this linked scene.")
    except Exception:
        pass

    # --- Confirmed: setup/payoff chains touching this scene ---
    try:
        from logosforge.screenplay_setup_payoff import analyze_setup_payoff
        sp = analyze_setup_payoff(db, project_id)
        for c in sp.possible_payoffs:
            if c.linked_scene_id == scene_id and c.scene_id:
                add(c.scene_id, "setup_payoff", "likely", "warning",
                    f"Possible payoff of a setup in the changed scene: {c.label}.",
                    "Confirm the payoff still lands.")
            elif c.scene_id == scene_id and c.linked_scene_id:
                add(c.linked_scene_id, "setup_payoff", "likely", "warning",
                    "Changed scene may pay off an earlier setup.",
                    "Confirm the setup still matches.")
    except Exception:
        pass

    # --- Same act (confirmed structural) ---
    src_act = (getattr(src, "act", "") or "").strip()
    if src_act:
        for s in scenes:
            if (getattr(s, "act", "") or "").strip() == src_act:
                add(s.id, "same_act", "possible", "info",
                    f"Same act ('{src_act}').")

    # --- Adjacency (positional context, capped) ---
    ordered = [s.id for s in scenes]
    if scene_id in ordered:
        i = ordered.index(scene_id)
        for j in (i - 1, i + 1):
            if 0 <= j < len(ordered):
                add(ordered[j], "adjacent", "possible", "info",
                    "Immediately adjacent scene.")

    # --- Likely: shared characters / location ---
    cues = _character_cues(after_text if after_text is not None
                           else getattr(src, "content", ""))
    loc = _scene_location(src)
    for s in scenes:
        if s.id == scene_id or s.id in impacts:
            continue
        if cues and _character_cues(getattr(s, "content", "")) & cues:
            add(s.id, "shared_character", "likely", "info",
                "Shares a character with the changed scene.")
        elif loc and _scene_location(s) == loc:
            add(s.id, "shared_location", "likely", "info",
                "Shares a location with the changed scene.")

    # Order: confirmed first, then by severity.
    order = {"confirmed": 0, "likely": 1, "possible": 2}
    items = sorted(impacts.values(), key=lambda x: order.get(x.confidence, 3))
    return items[:_MAX_SCENES]


# ---------------------------------------------------------------------------
# Setup/payoff + continuity impact
# ---------------------------------------------------------------------------


def detect_setup_payoff_impacts(db, project_id: int, scene_id: int) -> list[dict]:
    """Setup/payoff risks connected to the changed scene (deferred-safe)."""
    out: list[dict] = []
    try:
        from logosforge.screenplay_setup_payoff import analyze_setup_payoff
        sp = analyze_setup_payoff(db, project_id)
    except Exception:
        return [{"label": "Setup/Payoff analysis unavailable.",
                 "impact_kind": "broken_setup", "severity": "info",
                 "confidence": "unknown", "explanation": "Deferred/unavailable."}]
    for c in sp.unresolved_setups:
        if c.scene_id == scene_id:
            out.append({"label": c.label, "impact_kind": "broken_setup",
                        "severity": "warning", "confidence": "likely",
                        "explanation": "Changed scene contains an unresolved setup.",
                        "suggested_action": "Ensure it still pays off later."})
    for c in sp.possible_payoffs:
        if c.scene_id == scene_id or c.linked_scene_id == scene_id:
            out.append({"label": c.label, "impact_kind": "missing_payoff",
                        "severity": "warning", "confidence": "likely",
                        "explanation": "Change touches a setup/payoff chain.",
                        "suggested_action": "Confirm the payoff still lands."})
    return out[:15]


def detect_continuity_impacts(db, project_id: int, scene_id: int,
                              diff_result=None) -> list[dict]:
    """Lightweight continuity risks using only existing data (no hallucination)."""
    out: list[dict] = []
    # Omitted-but-referenced: if production numbering marks this scene omitted
    # yet later scenes still reference its characters/location.
    try:
        from logosforge.screenplay_production import scene_number_map
        nm = scene_number_map(db, project_id)
        if nm.get(scene_id, {}).get("omitted"):
            out.append({"label": "Omitted scene still in project",
                        "impact_kind": "continuity_risk", "severity": "warning",
                        "confidence": "possible",
                        "explanation": "Scene is marked OMITTED in the production draft.",
                        "suggested_action": "Confirm dependents don't rely on it."})
    except Exception:
        pass
    # Location change risk (slugline/location term removed in the diff).
    if diff_result is not None and getattr(diff_result, "removed_terms", None):
        loc_terms = {"int", "ext", "day", "night"}
        if any(t in loc_terms for t in diff_result.removed_terms):
            out.append({"label": "Scene heading/time changed",
                        "impact_kind": "continuity_risk", "severity": "info",
                        "confidence": "possible",
                        "explanation": "A scene-heading/time term changed.",
                        "suggested_action": "Check temporal/location continuity."})
    if not out:
        out.append({"label": "No deterministic continuity risk detected",
                    "impact_kind": "continuity_risk", "severity": "info",
                    "confidence": "unknown",
                    "explanation": "Limited to existing project data."})
    return out
