"""Continuity fact extraction (Phase 10Q).

Deterministic, read-only, no LLM. Reuses the existing PSYKE matcher
(``revision_intelligence.psyke_impact``). Facts are rebuilt each run — only
high-signal, structured facts are emitted; weak evidence is marked
``possible``/``unknown`` rather than invented.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from logosforge.continuity import models as M


@dataclass
class ProjectFacts:
    """Bundled extraction output the detectors consume."""
    scenes: list = field(default_factory=list)          # ordered Scene rows
    entries: list = field(default_factory=list)         # PSYKE entries
    entries_by_type: dict = field(default_factory=dict)  # type -> [entry]
    scene_appearances: dict = field(default_factory=dict)  # entry_id -> [order_index]
    facts: list = field(default_factory=list)           # list[ContinuityFact]
    unavailable: list = field(default_factory=list)


def _entry_type(e) -> str:
    return (getattr(e, "entry_type", "") or "other").lower()


def _scene_text(scene) -> str:
    return " ".join(
        getattr(scene, f, "") or "" for f in
        ("content", "summary", "synopsis", "goal", "conflict", "outcome")).strip()


def extract_facts(db, project_id: int) -> ProjectFacts:
    pf = ProjectFacts()
    try:
        pf.scenes = list(db.get_all_scenes(project_id))
    except Exception:
        pf.scenes = []
        pf.unavailable.append("manuscript")
    try:
        pf.entries = list(db.get_all_psyke_entries(project_id))
    except Exception:
        pf.entries = []
        pf.unavailable.append("psyke")

    for e in pf.entries:
        pf.entries_by_type.setdefault(_entry_type(e), []).append(e)

    try:
        from logosforge.revision_intelligence.psyke_impact import _mentioned
    except Exception:
        _mentioned = None

    # Character / object presence per scene (text match = confirmed mention).
    for idx, scene in enumerate(pf.scenes):
        text_low = _scene_text(scene).lower()
        # location_state fact
        loc = (getattr(scene, "location", "") or
               getattr(scene, "stage_location", "") or "").strip()
        if loc:
            pf.facts.append(M.ContinuityFact(
                M.FT_LOCATION_STATE, subject_type="scene", scene_id=scene.id,
                value=loc, confidence=M.CONF_CONFIRMED,
                provenance="scene location field", source_system="manuscript",
                order_index=idx))
        # temporal markers (screenplay-ish but mode-agnostic if present)
        tod = (getattr(scene, "time_of_day", "") or "").strip()
        ie = (getattr(scene, "interior_exterior", "") or "").strip()
        if tod or ie:
            pf.facts.append(M.ContinuityFact(
                M.FT_TEMPORAL_MARKER, subject_type="scene", scene_id=scene.id,
                value=f"{ie} {tod}".strip(), confidence=M.CONF_CONFIRMED,
                provenance="scene time markers", source_system="manuscript",
                order_index=idx, metadata={"time_of_day": tod, "int_ext": ie}))
        # PSYKE appearances
        if _mentioned and text_low:
            for e in pf.entries:
                if getattr(e, "is_global", False):
                    continue
                try:
                    hit = _mentioned(e, text_low)
                except Exception:
                    hit = False
                if hit:
                    pf.scene_appearances.setdefault(e.id, []).append(idx)
                    pf.facts.append(M.ContinuityFact(
                        M.FT_CHARACTER_STATE if _entry_type(e) == "character"
                        else M.FT_OBJECT_STATE,
                        subject_type="psyke", subject_id=e.id, scene_id=scene.id,
                        value="present", confidence=M.CONF_CONFIRMED,
                        provenance="scene text match", source_system="psyke",
                        order_index=idx))

    # Lore rules + motifs from PSYKE.
    for e in pf.entries:
        et = _entry_type(e)
        if et == "lore":
            pf.facts.append(M.ContinuityFact(
                M.FT_LORE_RULE, subject_type="psyke", subject_id=e.id,
                value=(getattr(e, "notes", "") or "")[:160],
                confidence=M.CONF_CONFIRMED, provenance="PSYKE lore entry",
                source_system="psyke"))
        elif et in ("theme", "motif"):
            pf.facts.append(M.ContinuityFact(
                M.FT_MOTIF, subject_type="psyke", subject_id=e.id,
                value=getattr(e, "name", "") or "", confidence=M.CONF_CONFIRMED,
                provenance="PSYKE theme/motif", source_system="psyke"))

    return pf
