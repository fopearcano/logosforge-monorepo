"""Deterministic screenplay setup/payoff tracker (Phase 10D).

Helps the writer *track* cinematic promises, planted objects, recurring motifs
and unresolved payoffs across scenes — it does not judge art. Rule-based, no LLM,
no DB writes, confidence-aware, cautious wording ("Possible setup", "Unresolved
setup candidate"). Persistence of confirmed links is deferred to Phase 10E; this
phase is report-only / in-memory.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from logosforge import screenplay_blocks as sb

# -- Severity (issue-local) ---------------------------------------------------
SEV_INFO = "info"
SEV_WATCH = "watch"
SEV_WEAK = "weak"

# -- Candidate types ----------------------------------------------------------
T_SETUP = "setup"
T_PAYOFF = "payoff"
T_MOTIF = "motif"
T_PROMISE = "promise"
T_THREAT = "threat"
T_OBJECT = "object"
T_CALLBACK = "callback"
T_UNRESOLVED = "unresolved"

# -- Marker lexicons (deterministic, documented) ------------------------------
PROMISE_MARKERS = (
    "i promise", "i swear", "you have my word", "i'll be back", "i will return",
    "i give you my word", "trust me",
)
THREAT_MARKERS = (
    "i'll kill", "you'll regret", "if you ever", "or else", "i'll destroy",
    "you're dead", "watch your back", "i'll make you pay", "you'll pay",
)
SECRET_MARKERS = (
    "don't tell", "between us", "no one can know", "keep this", "it's a secret",
    "promise you won't tell",
)
PLAN_MARKERS = (
    "here's the plan", "the plan is", "we'll meet", "at midnight", "rendezvous",
    "stick to the plan",
)
DEADLINE_MARKERS = (
    "by midnight", "before dawn", "you have until", "running out of time",
    "by tomorrow", "deadline", "before it's too late",
)
# Visually emphasized / loaded objects that often pay off.
LOADED_OBJECTS = (
    "gun", "pistol", "rifle", "knife", "blade", "bomb", "letter", "key", "ring",
    "photo", "photograph", "watch", "gift", "package", "document", "money",
    "cash", "weapon", "pill", "poison", "phone", "ticket", "map",
    "contract", "briefcase", "badge", "needle", "sword", "grenade",
    "diary", "journal", "envelope",
)
# (Common auxiliaries like "will"/"tape" are intentionally excluded — too noisy.)


def _norm(text: str) -> str:
    return (text or "").lower()


@dataclass
class SetupPayoffCandidate:
    id: str
    project_id: int
    scene_id: int | None
    block_index: int | None
    candidate_type: str
    label: str
    evidence: str = ""
    confidence: float = 0.0
    severity: str = SEV_INFO
    linked_psyke_entry_id: int | None = None
    linked_scene_id: int | None = None       # graph-hook source/target suggestion
    suggested_action: str = ""
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "scene_id": self.scene_id,
            "block_index": self.block_index,
            "candidate_type": self.candidate_type,
            "label": self.label,
            "evidence": self.evidence,
            "confidence": round(self.confidence, 2),
            "severity": self.severity,
            "linked_psyke_entry_id": self.linked_psyke_entry_id,
            "linked_scene_id": self.linked_scene_id,
            "suggested_action": self.suggested_action,
            "metadata": dict(self.metadata),
        }


@dataclass
class SetupPayoffReport:
    project_id: int
    scene_id: int | None = None
    candidates: list[SetupPayoffCandidate] = field(default_factory=list)
    unresolved_setups: list[SetupPayoffCandidate] = field(default_factory=list)
    possible_payoffs: list[SetupPayoffCandidate] = field(default_factory=list)
    recurring_motifs: list[SetupPayoffCandidate] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "scene_id": self.scene_id,
            "candidates": [c.to_dict() for c in self.candidates],
            "unresolved_setups": [c.to_dict() for c in self.unresolved_setups],
            "possible_payoffs": [c.to_dict() for c in self.possible_payoffs],
            "recurring_motifs": [c.to_dict() for c in self.recurring_motifs],
            "warnings": list(self.warnings),
            "summary": self.summary,
        }


def _cid(project_id: int, scene_id, block_index, kind: str, key: str) -> str:
    import hashlib
    raw = f"{project_id}:{scene_id}:{block_index}:{kind}:{key}"
    return "spx_" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


# ---------------------------------------------------------------------------
# Single-scene marker extraction (pure, testable)
# ---------------------------------------------------------------------------


def scene_candidates(
    blocks: list[sb.ScreenplayBlock],
    *,
    scene_id: int | None = None,
    project_id: int = 0,
    psyke_names: dict[str, int] | None = None,
) -> list[SetupPayoffCandidate]:
    """Detect in-scene setup candidates (promise/threat/secret/object…).

    Cross-scene recurrence/payoff resolution happens in :func:`analyze_setup_payoff`.
    *psyke_names* maps lowercased PSYKE entry name -> entry_id (any type).
    """
    out: list[SetupPayoffCandidate] = []
    psyke_names = psyke_names or {}

    def add(idx, ctype, label, evidence, conf, psyke_id=None, sev=SEV_INFO,
            action="Track this across scenes (Phase 10E persistence)."):
        out.append(SetupPayoffCandidate(
            id=_cid(project_id, scene_id, idx, ctype, label),
            project_id=project_id, scene_id=scene_id, block_index=idx,
            candidate_type=ctype, label=label, evidence=evidence,
            confidence=conf, severity=sev, linked_psyke_entry_id=psyke_id,
            suggested_action=action,
        ))

    marker_sets = [
        (PROMISE_MARKERS, T_PROMISE, "Possible promise (setup)"),
        (THREAT_MARKERS, T_THREAT, "Possible threat (setup)"),
        (SECRET_MARKERS, T_SETUP, "Possible secret (setup)"),
        (PLAN_MARKERS, T_SETUP, "Possible plan (setup)"),
        (DEADLINE_MARKERS, T_SETUP, "Possible deadline (setup)"),
    ]
    for idx, b in enumerate(blocks):
        if b.element_type not in ("action", "dialogue"):
            continue
        low = _norm(b.text)
        for markers, ctype, label in marker_sets:
            hit = next((m for m in markers if m in low), None)
            if hit:
                add(idx, ctype, label, f"Marker: “{hit}”.", 0.4, sev=SEV_WATCH)
        # Loaded objects.
        for obj in LOADED_OBJECTS:
            if re.search(rf"\b{re.escape(obj)}\b", low):
                pid_match = psyke_names.get(obj)
                conf = 0.5 if pid_match else 0.35
                add(idx, T_OBJECT, f"Possible object setup: {obj}",
                    f"Loaded object “{obj}” mentioned.", conf, psyke_id=pid_match)
        # PSYKE object/lore/theme names mentioned (potential motif/setup).
        for name_lc, pid_match in psyke_names.items():
            if name_lc in LOADED_OBJECTS:
                continue
            if len(name_lc) >= 3 and re.search(rf"\b{re.escape(name_lc)}\b", low):
                add(idx, T_OBJECT, f"PSYKE entity referenced: {name_lc}",
                    f"PSYKE entry “{name_lc}” mentioned in scene.", 0.5,
                    psyke_id=pid_match)
    return out


# ---------------------------------------------------------------------------
# Project-level analysis (cross-scene recurrence + unresolved)
# ---------------------------------------------------------------------------

_TRACK_TYPES = (T_OBJECT,)  # types whose recurrence implies payoff/motif


def _psyke_name_map(db, project_id: int) -> dict[str, int]:
    """Lowercased PSYKE entry name -> id, for object/place/lore/theme entries.

    Character entries are excluded: characters naturally recur across scenes and
    would create motif/payoff noise — they aren't planted props.
    """
    out: dict[str, int] = {}
    try:
        for e in db.get_all_psyke_entries(project_id):
            if (getattr(e, "entry_type", "") or "").lower() == "character":
                continue
            name = (getattr(e, "name", "") or "").strip().lower()
            if name:
                out[name] = e.id
    except Exception:
        return {}
    return out


def analyze_setup_payoff(db, project_id: int) -> SetupPayoffReport:
    """Project-level setup/payoff candidate report (read-only)."""
    report = SetupPayoffReport(project_id=project_id)
    try:
        scenes = db.get_all_scenes(project_id)
    except Exception:
        return report
    psyke_names = _psyke_name_map(db, project_id)

    all_candidates: list[SetupPayoffCandidate] = []
    # term -> ordered list of (scene_id, candidate) for recurrence analysis.
    term_scenes: dict[str, list[tuple[int, SetupPayoffCandidate]]] = {}

    for scene in scenes:
        blocks = sb.parse_screenplay_text(getattr(scene, "content", "") or "",
                                          scene_id=scene.id)
        cands = scene_candidates(blocks, scene_id=scene.id, project_id=project_id,
                                 psyke_names=psyke_names)
        for c in cands:
            all_candidates.append(c)
            if c.candidate_type in _TRACK_TYPES:
                term = c.label.split(":")[-1].strip().lower()
                term_scenes.setdefault(term, []).append((scene.id, c))

    motifs: list[SetupPayoffCandidate] = []
    payoffs: list[SetupPayoffCandidate] = []
    unresolved: list[SetupPayoffCandidate] = []

    for term, occ in term_scenes.items():
        scene_ids = sorted({sid for sid, _ in occ})
        if len(scene_ids) >= 2:
            first = scene_ids[0]
            # First occurrence becomes a recurring-motif candidate.
            base = occ[0][1]
            motifs.append(SetupPayoffCandidate(
                id=_cid(project_id, first, None, T_MOTIF, term),
                project_id=project_id, scene_id=first, block_index=base.block_index,
                candidate_type=T_MOTIF, label=f"Recurring motif candidate: {term}",
                evidence=f"“{term}” appears in {len(scene_ids)} scenes.",
                confidence=0.6, severity=SEV_WATCH,
                linked_psyke_entry_id=base.linked_psyke_entry_id,
                suggested_action="Confirm whether this recurrence is intentional.",
            ))
            # Later occurrences become possible payoffs/callbacks of the first.
            for sid in scene_ids[1:]:
                payoffs.append(SetupPayoffCandidate(
                    id=_cid(project_id, sid, None, T_PAYOFF, term),
                    project_id=project_id, scene_id=sid, block_index=None,
                    candidate_type=T_PAYOFF, label=f"Possible payoff: {term}",
                    evidence=f"“{term}” planted earlier (scene {first}) recurs here.",
                    confidence=0.5, severity=SEV_INFO, linked_scene_id=first,
                    linked_psyke_entry_id=base.linked_psyke_entry_id,
                    suggested_action="Confirm this resolves the earlier setup.",
                ))
        else:
            # Single occurrence of a loaded/PSYKE object → unresolved candidate.
            base = occ[0][1]
            unresolved.append(SetupPayoffCandidate(
                id=_cid(project_id, base.scene_id, base.block_index, T_UNRESOLVED, term),
                project_id=project_id, scene_id=base.scene_id,
                block_index=base.block_index, candidate_type=T_UNRESOLVED,
                label=f"Unresolved setup candidate: {term}",
                evidence=f"“{term}” is planted once and never recurs.",
                confidence=0.4, severity=SEV_WATCH,
                linked_psyke_entry_id=base.linked_psyke_entry_id,
                suggested_action="Pay this off later, or cut it.",
            ))

    # Promises/threats with no recurrence anywhere are also unresolved.
    for c in all_candidates:
        if c.candidate_type in (T_PROMISE, T_THREAT):
            unresolved.append(SetupPayoffCandidate(
                id=_cid(project_id, c.scene_id, c.block_index, T_UNRESOLVED, c.label),
                project_id=project_id, scene_id=c.scene_id, block_index=c.block_index,
                candidate_type=T_UNRESOLVED,
                label=f"Unresolved {c.candidate_type} candidate",
                evidence=c.evidence, confidence=0.35, severity=SEV_WATCH,
                suggested_action="Ensure this promise/threat pays off.",
            ))

    report.candidates = all_candidates
    report.recurring_motifs = motifs
    report.possible_payoffs = payoffs
    report.unresolved_setups = unresolved
    report.warnings = [c.label for c in unresolved]
    report.summary = (
        f"{len(all_candidates)} candidate(s); {len(unresolved)} unresolved, "
        f"{len(payoffs)} possible payoff(s), {len(motifs)} recurring motif(s)."
    )
    return report
