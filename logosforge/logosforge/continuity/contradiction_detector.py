"""Contradiction / structural-break detection (Phase 10Q).

Only emits issues backed by structured evidence. ``blocking`` is reserved for
confirmed structural breaks (e.g. a setup/payoff link pointing at a scene that
does not exist); softer signals are ``warning``/``suggestion`` with
``likely``/``possible`` confidence. Never hallucinates contradictions.
"""

from __future__ import annotations

from logosforge.continuity import models as M
from logosforge.continuity.facts import ProjectFacts

_CAP = 50


def detect_contradictions(db, project_id: int, pf: ProjectFacts, writing_mode: str,
                          ) -> list[M.ContinuityIssueData]:
    issues: list[M.ContinuityIssueData] = []
    scene_ids = {getattr(s, "id", None) for s in pf.scenes}
    titles = {getattr(s, "id", None): (getattr(s, "title", "") or "")
              for s in pf.scenes}

    # 1. Dangling setup/payoff scene links = confirmed continuity gap (blocking).
    for scene in pf.scenes:
        raw = (getattr(scene, "setup_payoff_links", "") or "").strip()
        for tok in raw.split(","):
            tok = tok.strip()
            if tok.isdigit() and int(tok) not in scene_ids:
                issues.append(M.ContinuityIssueData(
                    issue_type=M.IT_CONTINUITY_GAP, dimension=M.DIM_PLOT,
                    severity=M.SEV_BLOCKING, confidence=M.CONF_CONFIRMED,
                    title=f"'{getattr(scene, 'title', '') or 'A scene'}' links to a "
                          f"missing scene (#{tok}).",
                    explanation="A setup/payoff scene link points to a scene that "
                                "no longer exists.",
                    suggested_action="Repoint or remove the broken scene link.",
                    evidence=[f"setup_payoff_links references #{tok}"],
                    related_scene_ids=[getattr(scene, "id", None)]))
            if len(issues) >= _CAP:
                return issues

    # 2. Setup/payoff chains (screenplay candidate analysis = inferred → softer).
    if writing_mode == "screenplay":
        try:
            from logosforge.screenplay_setup_payoff import analyze_setup_payoff
            report = analyze_setup_payoff(db, project_id)
        except Exception:
            report = None
        if report is not None:
            for cand in (report.unresolved_setups or [])[:10]:
                issues.append(M.ContinuityIssueData(
                    issue_type=M.IT_UNRESOLVED_SETUP, dimension=M.DIM_PLOT,
                    severity=M.SEV_SUGGESTION, confidence=M.CONF_POSSIBLE,
                    title=f"Possible unresolved setup: {getattr(cand, 'label', '')}",
                    explanation=(getattr(cand, "evidence", "")
                                 or "A setup appears to have no payoff."),
                    suggested_action="Add a payoff or confirm this is intentional.",
                    evidence=[getattr(cand, "evidence", "")][:1],
                    related_scene_ids=[getattr(cand, "scene_id", None)]
                    if getattr(cand, "scene_id", None) else []))
            for cand in (report.possible_payoffs or [])[:10]:
                if getattr(cand, "metadata", {}).get("orphan_payoff"):
                    issues.append(M.ContinuityIssueData(
                        issue_type=M.IT_PAYOFF_WITHOUT_SETUP, dimension=M.DIM_PLOT,
                        severity=M.SEV_SUGGESTION, confidence=M.CONF_POSSIBLE,
                        title=f"Possible payoff without setup: "
                              f"{getattr(cand, 'label', '')}",
                        explanation=getattr(cand, "evidence", ""),
                        suggested_action="Plant an earlier setup or confirm intent.",
                        related_scene_ids=[getattr(cand, "scene_id", None)]
                        if getattr(cand, "scene_id", None) else []))
            if len(issues) >= _CAP:
                return issues[:_CAP]

    return issues[:_CAP]
