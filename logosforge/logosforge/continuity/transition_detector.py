"""Missing-transition detection (Phase 10Q).

A missing transition is not always an error, so these are ``suggestion``/
``warning`` with ``possible``/``likely`` confidence — never blocking. Each issue
carries evidence and a suggested action; the user can dismiss/defer.
"""

from __future__ import annotations

import re

from logosforge.continuity import models as M
from logosforge.continuity.facts import ProjectFacts

_CAP = 30
_TRAVEL = re.compile(
    r"\b(travel|travell|journey|walk|walked|drove|drive|flew|fly|ran|run|"
    r"arrive|arrived|left|leave|return|returned|went|go to|head|headed|"
    r"road|train|car|ship|boat|plane|horse|march)\w*\b", re.I)


def _scene_text(scene) -> str:
    return " ".join(getattr(scene, f, "") or "" for f in
                    ("content", "summary", "synopsis")).strip()


def detect_missing_transitions(pf: ProjectFacts, writing_mode: str,
                               ) -> list[M.ContinuityIssueData]:
    issues: list[M.ContinuityIssueData] = []

    # Spatial: consecutive scenes at different explicit locations with no travel
    # cue in the later scene → possible missing transition.
    prev = None
    for scene in pf.scenes:
        loc = (getattr(scene, "location", "") or
               getattr(scene, "stage_location", "") or "").strip()
        if prev is not None and loc and prev[1] and \
                loc.lower() != prev[1].lower():
            later_text = _scene_text(scene)
            if not _TRAVEL.search(later_text):
                issues.append(M.ContinuityIssueData(
                    issue_type=M.IT_LOCATION_JUMP, dimension=M.DIM_SPATIAL,
                    severity=M.SEV_SUGGESTION, confidence=M.CONF_POSSIBLE,
                    title=f"Location change '{prev[1]}' → '{loc}' with no travel cue.",
                    explanation="Consecutive scenes change location and the later "
                                "scene has no transition/travel cue.",
                    suggested_action="Add a transition beat or confirm the jump is "
                                     "intentional.",
                    evidence=[f"{prev[2]} @ {prev[1]}",
                              f"{getattr(scene, 'title', '')} @ {loc}"],
                    related_scene_ids=[prev[0], getattr(scene, "id", None)]))
        prev = (getattr(scene, "id", None), loc, getattr(scene, "title", "") or "")
        if len(issues) >= _CAP:
            break

    return issues[:_CAP]
