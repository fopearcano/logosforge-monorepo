"""Notes-integration diagnostics.

Checks how well freeform Notes are wired into the story bible: notes that are not
linked to any PSYKE entry, and notes that mention an existing PSYKE entry by name
without being linked to it. Read-only, deterministic, no LLM.
"""

from __future__ import annotations

from logosforge.logos.diagnostics.diagnostic import (
    CAT_PSYKE,
    SEVERITY_INFO,
    NarrativeDiagnostic,
)
from logosforge.logos.diagnostics.model import ProjectFacts

_MAX = 6


def detect_notes(facts: ProjectFacts) -> list[NarrativeDiagnostic]:
    out: list[NarrativeDiagnostic] = []
    notes = facts.notes
    if not notes:
        return out

    db = facts.db
    entry_by_name = {(e.name or "").strip().lower(): e for e in facts.entries
                     if (e.name or "").strip()}

    unlinked = 0
    for note in notes:
        try:
            links = db.get_note_psyke_links(note.id)
        except Exception:
            links = []
        if links:
            continue
        unlinked += 1
        # A note that names a known PSYKE entry but is not linked to it.
        blob = " ".join(filter(None, [note.title, note.content])).lower()
        mentioned = [e for name, e in entry_by_name.items() if name and name in blob]
        if mentioned and len(out) < _MAX:
            names = ", ".join(sorted({e.name for e in mentioned})[:3])
            out.append(NarrativeDiagnostic(
                category=CAT_PSYKE, section_name="Notes",
                title=f"Note '{_short(note.title)}' mentions PSYKE entries but isn't linked",
                message="This note references story-bible entries without a link.",
                evidence=f"Mentions {names}; 0 PSYKE links.",
                confidence=0.66, severity=SEVERITY_INFO,
                target_type="note", target_id=str(note.id),
                related_psyke_entry_ids=[e.id for e in mentioned],
                suggested_actions=["suggest_relations"],
            ))

    # Many notes entirely disconnected from the bible (integration gap).
    if notes and unlinked == len(notes) and len(notes) >= 3:
        out.append(NarrativeDiagnostic(
            category=CAT_PSYKE, section_name="Notes",
            title="Notes are not integrated with PSYKE",
            message="None of your notes are linked to story-bible entries.",
            evidence=f"{len(notes)} note(s); 0 linked to PSYKE.",
            confidence=0.7, severity=SEVERITY_INFO,
            target_type="notes", target_id="unlinked_notes",
            suggested_actions=["suggest_relations"],
        ))
    return out[:_MAX]


def _short(text: str, n: int = 40) -> str:
    text = (text or "").strip()
    return (text[:n] + "…") if len(text) > n else (text or "Untitled")
