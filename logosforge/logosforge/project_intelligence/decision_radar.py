"""Decision Radar — ranked, deterministic, traceable decision cards (Phase 10N).

Every card derives from existing collected data; no hallucinated cards. Ranked
blocking → warning → suggestion → opportunity → info, then capped.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

SEV_BLOCKING, SEV_WARNING, SEV_SUGGESTION, SEV_OPPORTUNITY, SEV_INFO = (
    "blocking", "warning", "suggestion", "opportunity", "info")
_SEV_RANK = {SEV_BLOCKING: 0, SEV_WARNING: 1, SEV_SUGGESTION: 2,
             SEV_OPPORTUNITY: 3, SEV_INFO: 4}


@dataclass
class DecisionCard:
    id: str
    category: str
    severity: str
    confidence: str
    title: str
    explanation: str = ""
    suggested_action: str = ""
    related_section: str = ""
    related_target_type: str = ""
    related_target_id: int | None = None
    created_from: str = "deterministic"

    @property
    def rank(self) -> int:
        return _SEV_RANK.get(self.severity, 5)

    def to_dict(self) -> dict[str, Any]:
        # Give every card a navigable destination: explicit section wins; else a
        # per-card override (the panel that actually resolves THAT card); else a
        # per-category fallback; else the Dashboard.
        section = (self.related_section
                   or _CARD_SECTION.get(self.id)
                   or ("Health" if self.id.startswith("health_") else "")
                   or _CATEGORY_SECTION.get(self.category, "Dashboard"))
        return {
            "id": self.id, "category": self.category, "severity": self.severity,
            "confidence": self.confidence, "title": self.title,
            "explanation": self.explanation, "suggested_action": self.suggested_action,
            "related_section": section,
            "related_target_type": self.related_target_type or ("section" if section else ""),
            "related_target_id": self.related_target_id,
            "created_from": self.created_from,
        }


# Category -> the workspace section (nav label) that resolves that kind of card.
_CATEGORY_SECTION = {
    "structure": "Structure", "graph": "Graph", "psyke": "PSYKE",
    "rewrite": "Manuscript", "apply": "Manuscript", "continuity": "Continuity",
    "production": "Export", "export": "Export",
}

# Per-card override: the exact panel that resolves a specific card (sharper than
# the category default — e.g. a missing logline is fixed in Projects, not the
# generic Structure panel).
_CARD_SECTION = {
    "missing_title": "Projects", "missing_description": "Projects",
    "scenes_no_summary": "Manuscript", "scenes_no_chapter": "Manuscript",
    "graph_isolated": "Graph",
    "psyke_empty": "PSYKE", "psyke_no_relations": "PSYKE", "psyke_empty_project": "PSYKE",
    "rewrite_preferred": "Manuscript", "rewrite_stale": "Manuscript",
    "apply_pending": "Manuscript",
    "revision_high": "Continuity",
    "prod_numbering": "Export", "prod_no_revset": "Export",
    "export_blocked": "Export", "export_warn": "Export",
}


def build_decision_radar(overview: dict, psyke: dict, structure: dict,
                         workflow: dict, export: dict,
                         health: dict | None = None, *, cap: int = 10) -> list[DecisionCard]:
    cards: list[DecisionCard] = []

    def add(cid, cat, sev, conf, title, expl="", action="", section=""):
        cards.append(DecisionCard(cid, cat, sev, conf, title, expl, action, section))

    # --- Overview ---
    if not overview.get("title") or overview["title"] == "Untitled":
        add("missing_title", "structure", SEV_WARNING, "confirmed",
            "Project has no title.", "", "Set a project title.", "Projects")
    if not overview.get("description_present"):
        add("missing_description", "structure", SEV_SUGGESTION, "confirmed",
            "Project has no description.", "", "Add a short logline/description.",
            "Projects")

    # --- Structure ---
    sc = structure.get("total_scenes", 0)
    no_sum = structure.get("scenes_without_summary", 0)
    if sc and no_sum:
        add("scenes_no_summary", "structure", SEV_SUGGESTION, "confirmed",
            f"{no_sum} of {sc} scene(s) have no summary.",
            "Summaries power Outline/Plot/Timeline and Assistant context.",
            "Add scene summaries.", "Manuscript")
    if structure.get("scenes_without_chapter"):
        add("scenes_no_chapter", "structure", SEV_INFO, "confirmed",
            f"{structure['scenes_without_chapter']} scene(s) have no chapter.",
            "", "Assign chapters/acts for structure.", "Outline")
    if structure.get("graph_available") and structure.get("graph_isolated_nodes"):
        add("graph_isolated", "graph", SEV_OPPORTUNITY, "likely",
            f"{structure['graph_isolated_nodes']} isolated graph node(s).",
            "Isolated entities have no relationships.",
            "Link related entities in the Graph.", "Graph")

    # --- PSYKE ---
    if psyke.get("available"):
        if psyke.get("empty_notes"):
            add("psyke_empty", "psyke", SEV_SUGGESTION, "confirmed",
                f"{psyke['empty_notes']} PSYKE entr(y/ies) have empty notes.",
                "Under-developed entries weaken continuity.",
                "Add notes/details to key entries.", "PSYKE")
        if psyke.get("no_relations") and psyke.get("total", 0) > 1:
            add("psyke_no_relations", "psyke", SEV_OPPORTUNITY, "likely",
                f"{psyke['no_relations']} PSYKE entr(y/ies) have no relations.",
                "", "Connect related characters/objects.", "PSYKE")
    elif overview.get("total_scenes"):
        add("psyke_empty_project", "psyke", SEV_OPPORTUNITY, "possible",
            "No PSYKE entries yet.", "", "Create characters/places in PSYKE.", "PSYKE")

    # --- Workflow ---
    rw = workflow.get("rewrite", {})
    if rw.get("active"):
        if rw.get("preferred"):
            add("rewrite_preferred", "rewrite", SEV_WARNING, "confirmed",
                "A preferred rewrite variant has not been applied.", "",
                "Review and apply (or discard) the preferred variant.", "Manuscript")
        if rw.get("stale"):
            add("rewrite_stale", "rewrite", SEV_WARNING, "confirmed",
                "Rewrite variants are stale (source changed).", "",
                "Regenerate variants from the current source.", "Manuscript")
    ca = workflow.get("controlled_apply", {})
    if ca.get("available") and ca.get("pending"):
        add("apply_pending", "apply", SEV_WARNING, "confirmed",
            f"{ca['pending']} controlled-apply operation(s) pending.", "",
            "Review the preview and apply or cancel.", "Manuscript")
    rev = workflow.get("revision", {})
    if rev.get("available") and rev.get("high_impact"):
        add("revision_high", "continuity", SEV_WARNING, "likely",
            f"{rev['high_impact']} high-impact revision report(s).", "",
            "Review the change impact map.", "Manuscript")

    # --- Production / Export (screenplay) ---
    if overview.get("writing_mode") == "screenplay":
        prod = workflow.get("production", {})
        if prod.get("active"):
            if prod.get("scene_numbering_enabled") and prod.get("warnings"):
                add("prod_numbering", "production", SEV_WARNING, "confirmed",
                    "Scene numbering has issues.",
                    "; ".join(prod["warnings"][:2]),
                    "Re-assign / validate scene numbers.", "Manuscript")
            if not prod.get("revision_sets"):
                add("prod_no_revset", "production", SEV_SUGGESTION, "confirmed",
                    "Production draft active but no revision set.", "",
                    "Create a revision set before issuing.", "Manuscript")
        if export.get("checked") and not export.get("is_export_safe", True):
            add("export_blocked", "export", SEV_BLOCKING, "confirmed",
                "Fountain export has blocking issues.",
                "; ".join(export.get("blocking", [])[:2]),
                "Resolve export blockers.", "Export")
        elif export.get("checked") and export.get("warnings"):
            add("export_warn", "export", SEV_SUGGESTION, "confirmed",
                "Fountain export has warnings.",
                "; ".join(export.get("warnings", [])[:2]),
                "Review export warnings.", "Export")

    # --- Health (when available) ---
    if health and health.get("available"):
        for i, risk in enumerate(health.get("top_risks", [])[:3]):
            add(f"health_{i}", "continuity", SEV_WARNING, "likely",
                risk, "", "Open Narrative Health for details.", "Health")

    cards.sort(key=lambda c: c.rank)
    return cards[:cap]
