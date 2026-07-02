"""Deterministic Tier-1 stage-direction parser: mine a stage-script Scene's body
text for the structured stage inputs the graph enricher reads — entrances/exits,
technical cues, and offstage events — so a stage project's graph lights up from
authored prose, no LLM. Qt-free; reuses the conservative name reconciler.

Recognized lines (theatre conventions):
  - ENTER MARA / MARA enters / Exit ELI / Exeunt        -> stage entrance/exit
  - (Lights up.) / LIGHTS: snap up / SOUND: a bell       -> stage cue
  - a line mentioning "offstage" / "from the wings"      -> scene.offstage_events
"""

from __future__ import annotations

import re

from logosforge.name_reconcile import _match_id

_PAREN_RE = re.compile(r"^\((.+)\)$")
_CUE_PREFIX_RE = re.compile(r"^(LIGHTS?|SOUND|SFX|MUSIC|CUE)\s*[:\-]\s*(.+)$", re.IGNORECASE)
# Entrance/exit must be STAGE-DIRECTION SHAPED, not prose that merely mentions the
# verb mid-sentence. Two forms: (a) line-initial "ENTER/EXIT/EXEUNT <names>", and
# (b) "<Capitalized names> enters/exits/exeunt ..." where the verb DIRECTLY follows
# the name block (so "Mara could not enter ..." — verb not after the name — is not a
# direction). Names allow comma / and / & joiners.
_ENTER_LEAD_RE = re.compile(r"^\s*(ENTER|EXIT|EXEUNT)\b[:\-]?\s*(.*)$", re.IGNORECASE)
_NAME_VERB_RE = re.compile(
    r"^\s*((?:[A-Z][A-Za-z.'’\-]+)(?:\s*(?:,|and|AND|&)\s*[A-Z][A-Za-z.'’\-]+)*)"
    r"\s+(enters?|exits?|exeunt|ENTERS?|EXITS?|EXEUNT|Enters?|Exits?|Exeunt)\b"
)
_OFFSTAGE_RE = re.compile(r"\b(off-?\s?stage|from the wings|heard off(?:stage)?|from offstage)\b", re.IGNORECASE)
# Candidate character tokens: Capitalized or ALLCAPS words.
_NAME_RE = re.compile(r"\b([A-Z][A-Za-z.'’\-]+)\b")


def _parse_entrance(line: str):
    """Return ``(is_exit, names_text)`` if the line is an entrance/exit stage
    direction, else None."""
    m = _ENTER_LEAD_RE.match(line)
    if m:
        verb = m.group(1).lower()
        return (verb.startswith("exit") or verb == "exeunt"), m.group(2)
    m = _NAME_VERB_RE.match(line)
    if m:
        verb = m.group(2).lower()
        return (verb.startswith("exit") or verb == "exeunt"), m.group(1)
    return None
# Keyword -> cue_type for parenthetical / prefix cues.
_CUE_KW = (("light", "light"), ("sound", "sound"), ("sfx", "sound"), ("music", "music"),
           ("bell", "sound"), ("blackout", "light"), ("spotlight", "light"))
_VERB_WORDS = {"enter", "enters", "exit", "exits", "exeunt"}
_SKIP_TOKENS = {"the", "a", "an", "and", "with", "to", "from", "of"}


def _cue_type(text: str) -> str:
    low = text.lower()
    for kw, t in _CUE_KW:
        if kw in low:
            return t
    return "other"


def sync_stage_structure_from_scenes(db, project_id: int, *, replace: bool = False) -> dict:
    """Parse each scene's stage directions into cue / entrance-exit rows + offstage
    events. Returns ``{"cues","entrances","offstage"}``. Idempotent: skips a scene
    that already has stage rows unless ``replace`` (cues/entrances are additive)."""
    items = [(c.id, c.name, "") for c in db.get_all_characters(project_id)]
    cues = entrances = offstage = 0

    for scene in db.get_all_scenes(project_id):
        if not replace and (db.get_stage_cues(scene.id) or db.get_stage_entrances_exits(scene.id)):
            continue
        off_lines: list[str] = []
        for raw in (scene.content or "").splitlines():
            line = raw.strip()
            if not line:
                continue

            if _OFFSTAGE_RE.search(line):
                off_lines.append(line)

            # CUES FIRST — a cue line that incidentally contains "enter"/"exit"
            # (e.g. "SOUND: a door slams as Mara exits") must not be stolen as an
            # entrance.
            pm = _CUE_PREFIX_RE.match(line)
            if pm:
                db.create_stage_cue(scene.id, cue_type=_cue_type(pm.group(1)), cue_text=pm.group(2).strip())
                cues += 1
                continue
            par = _PAREN_RE.match(line)
            if par:
                inner = par.group(1).strip()
                db.create_stage_cue(scene.id, cue_type=_cue_type(inner), cue_text=inner)
                cues += 1
                continue

            # ENTRANCE/EXIT — only stage-direction-shaped lines (not prose).
            ent = _parse_entrance(line)
            if ent is not None:
                is_exit, names_text = ent
                for nm in _NAME_RE.findall(names_text):
                    if nm.lower() in _VERB_WORDS or nm.lower() in _SKIP_TOKENS:
                        continue
                    cid = _match_id(nm, items)
                    if cid is not None:
                        db.create_stage_entrance_exit(scene.id, character_id=cid,
                            type=("exit" if is_exit else "entrance"), cue_text=line)
                        entrances += 1

        if off_lines:
            db.set_scene_offstage_events(scene.id, "; ".join(off_lines))
            offstage += 1

    return {"cues": cues, "entrances": entrances, "offstage": offstage}
