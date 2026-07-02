"""PSYKE impact detection for revision intelligence (Phase 10K).

Given a scene's before/after text, find which PSYKE entries are mentioned,
added, or removed, and which related entries are *likely* touched. Deterministic,
read-only, capped, accent-safe. Direct name/alias matches are ``confirmed``;
relation-pulled entries are ``likely``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

_MAX = 25


@dataclass
class PsykeImpact:
    entry_id: int
    name: str
    impact_kind: str          # changed | added | removed | related
    confidence: str           # confirmed | likely
    explanation: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"entry_id": self.entry_id, "name": self.name,
                "impact_kind": self.impact_kind, "confidence": self.confidence,
                "explanation": self.explanation}


def _names(entry) -> list[str]:
    out = [(getattr(entry, "name", "") or "").strip()]
    aliases = getattr(entry, "aliases", "") or ""
    out += [a.strip() for a in re.split(r"[;,]", aliases) if a.strip()]
    return [n for n in out if len(n) >= 2]


def _mentioned(entry, text_low: str) -> bool:
    for n in _names(entry):
        if re.search(rf"\b{re.escape(n.lower())}\b", text_low):
            return True
    return False


def detect_psyke_impact(db, project_id: int, before_text: str | None,
                        after_text: str | None) -> list[PsykeImpact]:
    """Return capped PSYKE impacts for a before/after scene change."""
    try:
        entries = db.get_all_psyke_entries(project_id)
    except Exception:
        return []
    before_low = (before_text or "").lower()
    after_low = (after_text or "").lower()

    impacts: list[PsykeImpact] = []
    direct_ids: set[int] = set()
    for e in entries:
        in_b = _mentioned(e, before_low) if before_low else False
        in_a = _mentioned(e, after_low) if after_low else False
        if not (in_a or in_b):
            continue
        direct_ids.add(e.id)
        if in_a and not in_b:
            kind, expl = "added", "Introduced in the revised scene."
        elif in_b and not in_a:
            kind, expl = "removed", "No longer mentioned after the change."
        else:
            kind, expl = "changed", "Mentioned in the changed scene."
        impacts.append(PsykeImpact(e.id, getattr(e, "name", "") or "", kind,
                                   "confirmed", expl))

    # Relation-pulled (likely) — entries related to a directly-impacted one.
    seen = set(direct_ids)
    for eid in list(direct_ids):
        try:
            related = db.get_related_psyke_entries(eid)
        except Exception:
            related = []
        for r in related:
            if r.id in seen:
                continue
            seen.add(r.id)
            impacts.append(PsykeImpact(
                r.id, getattr(r, "name", "") or "", "related", "likely",
                "Related (via PSYKE relation) to a changed entry."))
            if len(impacts) >= _MAX:
                return impacts[:_MAX]
    return impacts[:_MAX]
