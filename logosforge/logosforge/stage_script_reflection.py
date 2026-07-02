"""Stage Script scene Reflection — the Counterpart/Logos mirror (Phase 4).

A deterministic, non-mutating reflection for a Stage Script *Scene* (its ordered
stage blocks). It re-projects the Phase 3 diagnostics + Phase 2 beat plan /
blocking-cue plan + PSYKE + Timeline into a writer-facing report seen through four
theatrical lenses —

* **Audience** — what plays from the house: visible conflict, legible emotional
  shift, stakes, exposition load, theatrical punctuation.
* **Actor** — what each character wants and can play: objective, playable action,
  entrances/exits, parentheticals that help vs. over-direct.
* **Director / Blocking** — stage life: movement, business, props/set, cue
  clarity, whether stage directions are playable, whether the scene is static.
* **Dramaturg / Story** — objective, conflict, the turn, beginning-to-end change,
  and alignment with the beat plan and blocking/cue plan.

It produces *feedback and revision questions*, never rewritten text. An optional
AI pass (the existing Counterpart prompt) may explain/expand this report; it is
grounded in the deterministic findings and never replaces them.

Pure logic + DB reads: no Qt, no mutation, no PSYKE/Note creation (the Note save
is opt-in + confirmed). No image generation of any kind.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from logosforge import stage_script_blocks as ssb
from logosforge import stage_script_diagnostics as ssd

# Reuse the Phase 3 severity scale (single source of truth).
SEV_INFO = ssd.SEV_INFO
SEV_WATCH = ssd.SEV_WATCH
SEV_WEAK = ssd.SEV_WEAK
SEV_CRITICAL = ssd.SEV_CRITICAL

# Section keys (also the canonical render order).
SEC_SNAPSHOT = "Scene Snapshot"
SEC_AUDIENCE = "Audience Perspective"
SEC_ACTOR = "Actor Perspective"
SEC_DIRECTOR = "Director / Blocking Perspective"
SEC_DRAMATURG = "Dramaturg / Story Perspective"
SEC_DIALOGUE = "Dialogue / Subtext Notes"
SEC_STAGE_ACTION = "Stage Action / Playability Notes"
SEC_CUE = "Cue / Production Clarity Notes"
SEC_BEAT_ALIGN = "Beat Plan Alignment"
SEC_BLOCKING_ALIGN = "Blocking / Cue Plan Alignment"
SEC_PSYKE = "PSYKE / Continuity Risks"
SEC_QUESTIONS = "Revision Questions"
SEC_ACTIONS = "Suggested Human Actions"

EXPOSITION_WORDS = 45          # one character's total dialogue words ~ talky
PARENTHETICAL_HEAVY_RATIO = 0.5  # parentheticals per dialogue block -> over-directing


def _words(text: str) -> int:
    return len(re.findall(r"\S+", text or ""))


# Feeling vocabulary for the audience "stated, not staged" check — broader than
# the Phase 3 stage-direction set so first-person *dialogue* ("I feel…") matches.
_FEELING_WORDS = (
    "feel", "feels", "feeling", "felt", "realize", "realizes", "realise",
    "remember", "remembers", "know", "knows", "understand", "understands",
    "want", "wants", "hope", "hopes", "love", "hate", "regret", "afraid",
    "abandoned", "alone", "ashamed", "guilty", "lonely", "heartbroken",
)


def _states_feeling(text: str) -> bool:
    low = (text or "").lower()
    return any(re.search(rf"\b{re.escape(w)}\b", low) for w in _FEELING_WORDS)


# ===========================================================================
# Data model
# ===========================================================================


@dataclass
class ReflectionItem:
    category: str
    title: str
    detail: str = ""
    severity: str = SEV_INFO
    block_number: int | None = None
    psyke_entry_id: int | None = None
    suggested_action: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"category": self.category, "title": self.title, "detail": self.detail,
                "severity": self.severity, "block_number": self.block_number,
                "psyke_entry_id": self.psyke_entry_id,
                "suggested_action": self.suggested_action}


@dataclass
class CharacterReflection:
    name: str
    linked: bool = False
    psyke_entry_id: int | None = None
    wants: str = "unclear"
    playable_action: str = "weak"      # weak | present
    dialogue_function: str = "—"
    notes: list[str] = field(default_factory=list)
    suggestion: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "linked": self.linked,
                "psyke_entry_id": self.psyke_entry_id, "wants": self.wants,
                "playable_action": self.playable_action,
                "dialogue_function": self.dialogue_function,
                "notes": list(self.notes), "suggestion": self.suggestion}


@dataclass
class StageScriptReflectionReport:
    scene_id: int | None = None
    snapshot: str = ""
    audience: list[ReflectionItem] = field(default_factory=list)
    actor: list[CharacterReflection] = field(default_factory=list)
    director: list[ReflectionItem] = field(default_factory=list)
    dramaturg: list[ReflectionItem] = field(default_factory=list)
    dialogue_subtext: list[ReflectionItem] = field(default_factory=list)
    stage_action: list[ReflectionItem] = field(default_factory=list)
    cue_production: list[ReflectionItem] = field(default_factory=list)
    beat_alignment: list[ReflectionItem] = field(default_factory=list)
    blocking_alignment: list[ReflectionItem] = field(default_factory=list)
    continuity_risks: list[ReflectionItem] = field(default_factory=list)
    questions: list[str] = field(default_factory=list)
    suggested_actions: list[str] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)
    ai_enhanced: bool = False

    def _item_sections(self):
        return (
            (SEC_AUDIENCE, self.audience), (SEC_DIRECTOR, self.director),
            (SEC_DRAMATURG, self.dramaturg), (SEC_DIALOGUE, self.dialogue_subtext),
            (SEC_STAGE_ACTION, self.stage_action), (SEC_CUE, self.cue_production),
            (SEC_BEAT_ALIGN, self.beat_alignment),
            (SEC_BLOCKING_ALIGN, self.blocking_alignment),
            (SEC_PSYKE, self.continuity_risks),
        )

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"scene_id": self.scene_id, "snapshot": self.snapshot,
                               SEC_ACTOR: [c.to_dict() for c in self.actor]}
        for header, items in self._item_sections():
            out[header] = [i.to_dict() for i in items]
        out["questions"] = list(self.questions)
        out["suggested_actions"] = list(self.suggested_actions)
        out["metrics"] = dict(self.metrics)
        out["ai_enhanced"] = self.ai_enhanced
        return out

    def to_text(self) -> str:
        lines: list[str] = [f"{SEC_SNAPSHOT}: {self.snapshot}", ""]
        # Audience first, then the actor (character) section, then the rest.
        lines.append(SEC_AUDIENCE + ":")
        if self.audience:
            for i in self.audience:
                lines.append(f"- [{i.severity}] {i.title} — {i.detail}")
        else:
            lines.append("- Nothing flagged.")

        lines.append("")
        lines.append(SEC_ACTOR + ":")
        if self.actor:
            for c in self.actor:
                tag = "" if c.linked else " (unlinked)"
                lines.append(f"- {c.name}{tag} — wants: {c.wants}; action: "
                             f"{c.playable_action}; dialogue: {c.dialogue_function}")
                if c.suggestion:
                    lines.append(f"    → {c.suggestion}")
        else:
            lines.append("- No speaking characters detected.")

        for header, items in self._item_sections():
            if header == SEC_AUDIENCE:
                continue  # already rendered
            lines.append("")
            lines.append(header + ":")
            if items:
                for i in items:
                    where = f" (block {i.block_number})" if i.block_number else ""
                    lines.append(f"- [{i.severity}] {i.title}{where} — {i.detail}")
            else:
                lines.append("- Nothing flagged.")

        lines.append("")
        lines.append(SEC_QUESTIONS + ":")
        lines.extend(f"- {q}" for q in (self.questions or ["—"]))
        lines.append("")
        lines.append(SEC_ACTIONS + ":")
        lines.extend(f"- {a}" for a in (self.suggested_actions or ["None."]))
        return "\n".join(lines).strip()


# ===========================================================================
# Re-projection + lenses
# ===========================================================================


def _to_item(issue: ssd.StageDiagnosticIssue, category: str,
             psyke_id: int | None = None) -> ReflectionItem:
    return ReflectionItem(category=category, title=issue.label, detail=issue.evidence,
                          severity=issue.severity, block_number=issue.block_number,
                          psyke_entry_id=psyke_id,
                          suggested_action=issue.suggested_action)


def _character_reflections(script: ssb.StageScript,
                           psyke: dict[str, dict]) -> list[CharacterReflection]:
    dialogue_by: dict[str, list[str]] = {}
    for b in script.blocks:
        if b.block_type == ssb.BT_DIALOGUE and b.character:
            dialogue_by.setdefault(b.character, []).append(b.text)
    action_text = " ".join(
        b.text.lower() for b in script.blocks
        if b.block_type in (ssb.BT_STAGE_DIRECTION, ssb.BT_ENTRANCE, ssb.BT_EXIT))

    out: list[CharacterReflection] = []
    for name in ssb.character_cues(script):
        entry = psyke.get(name)
        lines = dialogue_by.get(name, [])
        joined = " ".join(lines).lower()
        words = _words(" ".join(lines))
        has_obj = any(re.search(rf"\b{re.escape(m)}\b", joined)
                      for m in ssd.OBJECTIVE_MARKERS)
        if has_obj:
            wants = "stated in dialogue (verify it's also played)"
        elif entry and entry.get("has_goal"):
            wants = "defined in PSYKE (confirm the scene plays it)"
        else:
            wants = "unclear"
        if not lines:
            dialogue_function = "no dialogue (acts in silence?)"
        elif words >= EXPOSITION_WORDS:
            dialogue_function = "exposition-heavy (long speeches)"
        else:
            dialogue_function = "present"
        playable = "present" if name.lower() in action_text else "weak"
        notes: list[str] = []
        if entry is None:
            notes.append("unlinked character — no PSYKE entry")
        suggestion = (
            f"Give {name} a playable action that reveals the intention."
            if playable == "weak"
            else f"Check {name}'s behavior externalizes the objective.")
        out.append(CharacterReflection(
            name=name, linked=entry is not None,
            psyke_entry_id=(entry or {}).get("id"), wants=wants,
            playable_action=playable, dialogue_function=dialogue_function,
            notes=notes, suggestion=suggestion))
    return out


def _audience_items(script: ssb.StageScript,
                    diag: ssd.StageSceneReport) -> list[ReflectionItem]:
    items: list[ReflectionItem] = []
    ids = {i.id for i in diag.issues}

    if "objective_unclear" in ids or "conflict_unclear" in ids \
            or "no_visible_action" in ids:
        items.append(ReflectionItem(
            category=SEC_AUDIENCE, title="Present conflict may be unclear",
            detail="The audience may not grasp what's at stake right now on stage.",
            severity=SEV_WATCH,
            suggested_action="Make the present want and obstacle visible."))

    if "dialogue_heavy" in ids or (diag.dialogue_count >= 2
                                   and not diag.visible_stage_action):
        items.append(ReflectionItem(
            category=SEC_AUDIENCE, title="Leans on exposition over staged action",
            detail="The scene tells more than it shows — the house watches talk, "
                   "not action.", severity=SEV_WATCH,
            suggested_action="Turn a line of exposition into a stage action."))

    # Emotional shift stated in dialogue rather than staged.
    stated_feeling = any(b.block_type == ssb.BT_DIALOGUE and _states_feeling(b.text)
                         for b in script.blocks)
    if stated_feeling and not diag.visible_stage_action:
        items.append(ReflectionItem(
            category=SEC_AUDIENCE, title="Emotional shift stated, not staged",
            detail="A feeling is spoken but nothing on stage shows it change.",
            severity=SEV_INFO,
            suggested_action="Stage the shift as visible behavior or a beat."))

    # Weak ending — last block is plain dialogue with no turn / cue / punctuation.
    if script.blocks:
        last = script.blocks[-1]
        if last.block_type == ssb.BT_DIALOGUE and "turn_unclear" in ids:
            items.append(ReflectionItem(
                category=SEC_AUDIENCE, title="Scene ends without a visible turn",
                detail="The last beat is dialogue with no theatrical punctuation "
                       "(turn, exit, blackout, or reveal).", severity=SEV_INFO,
                suggested_action="End on a turn, exit, or cue the audience can feel."))
    return items


def _parenthetical_items(script: ssb.StageScript) -> list[ReflectionItem]:
    paren = sum(1 for b in script.blocks if b.block_type == ssb.BT_PARENTHETICAL)
    dlg = sum(1 for b in script.blocks if b.block_type == ssb.BT_DIALOGUE)
    if dlg and paren >= max(2, dlg * PARENTHETICAL_HEAVY_RATIO):
        return [ReflectionItem(
            category=SEC_DIALOGUE, title="Parentheticals may over-direct",
            detail=f"{paren} actor directions across {dlg} lines — consider trusting "
                   "the actor.", severity=SEV_INFO,
            suggested_action="Cut parentheticals the line already implies.")]
    return []


# ===========================================================================
# PSYKE / Timeline / questions / actions
# ===========================================================================


def _timeline_items(db, project_id: int, scene_id: int) -> list[ReflectionItem]:
    try:
        events = db.get_timeline_event_ids(project_id)
    except Exception:
        return []
    if scene_id in (events or []):
        return [ReflectionItem(
            category=SEC_PSYKE, title="Linked to the Timeline",
            detail="This scene is an explicit Timeline event — keep chronology "
                   "consistent.", severity=SEV_INFO)]
    return []


def _continuity_items(grouped, psyke: dict[str, dict], db, project_id: int,
                      scene_id: int) -> list[ReflectionItem]:
    name_to_id = {n: v.get("id") for n, v in psyke.items()}
    items: list[ReflectionItem] = []
    for issue in grouped.get(ssd.CAT_CONTINUITY, []):
        cue = issue.id.replace("character_not_in_psyke_", "")
        items.append(_to_item(issue, SEC_PSYKE, psyke_id=name_to_id.get(cue)))
    items.extend(_timeline_items(db, project_id, scene_id))
    return items


def _plan_alignment(grouped, beat, blocking, *, beat_section: bool):
    """Beat- or blocking-plan alignment items + a presence note."""
    if beat_section:
        items = [_to_item(i, SEC_BEAT_ALIGN) for i in grouped.get(ssd.CAT_ALIGNMENT, [])
                 if i.id.startswith("beat_")]
        empty = beat is None or _is_empty(beat)
        if empty:
            items.append(ReflectionItem(
                category=SEC_BEAT_ALIGN, title="No beat plan",
                detail="No Stage Beat Plan to compare against — generate one to "
                       "reflect on alignment.", severity=SEV_INFO))
        elif not items:
            items.append(ReflectionItem(
                category=SEC_BEAT_ALIGN, title="Body reflects the beat plan",
                detail="Planned conflict/turn appear in the body (keyword check).",
                severity=SEV_INFO))
        return items
    items = [_to_item(i, SEC_BLOCKING_ALIGN) for i in grouped.get(ssd.CAT_ALIGNMENT, [])
             if i.id.startswith("blocking_")]
    empty = blocking is None or _is_empty(blocking)
    if empty:
        items.append(ReflectionItem(
            category=SEC_BLOCKING_ALIGN, title="No blocking / cue plan",
            detail="No Blocking / Cue Plan to compare against — generate one to "
                   "reflect on alignment.", severity=SEV_INFO))
    elif not items:
        items.append(ReflectionItem(
            category=SEC_BLOCKING_ALIGN, title="Body reflects the blocking/cue plan",
            detail="Planned moves and cues appear in the body.", severity=SEV_INFO))
    return items


def _is_empty(obj: Any) -> bool:
    if obj is None:
        return True
    try:
        return bool(obj.is_empty())
    except Exception:
        return False


def _questions(diag: ssd.StageSceneReport) -> list[str]:
    qs: list[str] = []
    ids = {i.id for i in diag.issues}
    if "objective_unclear" in ids:
        qs.append("What does each character actively want on stage?")
    if "conflict_unclear" in ids:
        qs.append("Where does the obstacle become visible to the audience?")
    if "turn_unclear" in ids:
        qs.append("Where does the scene turn, and what changes by the last beat?")
    if any(i.startswith("internal_feeling") for i in ids):
        qs.append("Can this stated feeling become a playable action?")
    if "no_stage_direction" in ids or "no_visible_action" in ids:
        qs.append("What entrance, exit, prop, or cue can carry the dramatic shift?")
    qs.append("What does the audience know at the end that they didn't at the start?")
    qs.append("What changes physically from the first beat to the last?")
    return list(dict.fromkeys(qs))


def _suggested_actions(diag: ssd.StageSceneReport,
                       report: StageScriptReflectionReport) -> list[str]:
    out: list[str] = []
    for issue in diag.issues:
        if issue.suggested_action:
            out.append(issue.suggested_action)
    for _, items in report._item_sections():
        for it in items:
            if it.suggested_action:
                out.append(it.suggested_action)
    for c in report.actor:
        if c.suggestion:
            out.append(c.suggestion)
    return list(dict.fromkeys(out))[:12]


# ===========================================================================
# Snapshot + core builder
# ===========================================================================


def _snapshot(scene, diag: ssd.StageSceneReport, beat, blocking) -> str:
    where = " / ".join(p for p in ((getattr(scene, "act", "") or "").strip(),
                                   (getattr(scene, "chapter", "") or "").strip()) if p)
    bits = [
        f"{where or 'Unplaced'} · {diag.total_blocks} block(s) "
        f"({diag.character_count} character / {diag.dialogue_count} dialogue / "
        f"{diag.stage_direction_count} stage direction)",
        f"dialogue:action ratio {diag.dialogue_stage_ratio}",
    ]
    if beat is not None and not _is_empty(beat):
        bits.append("beat plan: present")
    if blocking is not None and not _is_empty(blocking):
        bits.append("blocking/cue plan: present")
    return " · ".join(bits)


def build_scene_reflection(db, project_id: int, scene_id: int
                           ) -> StageScriptReflectionReport:
    """Build a deterministic multi-perspective reflection for a Stage Script
    scene. Read-only."""
    rep = StageScriptReflectionReport(scene_id=scene_id)
    scene = None
    try:
        scene = db.get_scene_by_id(scene_id)
    except Exception:
        scene = None
    if scene is None:
        rep.snapshot = "Scene not found."
        return rep

    script = ssb.load_scene_script(db, scene_id)
    diag = ssd.analyze_scene_by_id(db, project_id, scene_id)
    grouped = ssd.group_issues_by_category(diag)

    beat = blocking = None
    try:
        from logosforge import stage_script_pipeline as ssp
        beat = ssp.get_beat_plan(db, project_id, scene_id)
        blocking = ssp.get_blocking_plan(db, project_id, scene_id)
    except Exception:
        beat = blocking = None

    psyke: dict[str, dict] = {}
    try:
        from logosforge.screenplay_reflection import _psyke_characters_by_name
        psyke = _psyke_characters_by_name(db, project_id)
    except Exception:
        psyke = {}

    rep.metrics = {
        "total_blocks": diag.total_blocks, "character_count": diag.character_count,
        "dialogue_count": diag.dialogue_count,
        "stage_direction_count": diag.stage_direction_count,
        "dialogue_stage_ratio": diag.dialogue_stage_ratio,
        "visible_stage_action": diag.visible_stage_action,
    }
    rep.snapshot = _snapshot(scene, diag, beat, blocking)

    rep.audience = _audience_items(script, diag)
    rep.actor = _character_reflections(script, psyke)
    # Director / Blocking: re-project the blocking/format movement issues.
    rep.director = [_to_item(i, SEC_DIRECTOR) for i in grouped.get(ssd.CAT_BLOCKING, [])]
    rep.director += [_to_item(i, SEC_DIRECTOR) for i in grouped.get(ssd.CAT_FORMAT, [])
                     if i.id.startswith(("entrance_no_name", "exit_no_name"))]
    rep.dramaturg = [_to_item(i, SEC_DRAMATURG)
                     for i in grouped.get(ssd.CAT_DRAMATIC, [])]
    rep.dialogue_subtext = [_to_item(i, SEC_DIALOGUE)
                            for i in grouped.get(ssd.CAT_DIALOGUE, [])]
    rep.dialogue_subtext += [_to_item(i, SEC_DIALOGUE)
                             for i in grouped.get(ssd.CAT_FORMAT, [])
                             if i.id.startswith(("dialogue_no_character",
                                                 "character_no_dialogue"))]
    rep.dialogue_subtext += _parenthetical_items(script)
    rep.stage_action = [_to_item(i, SEC_STAGE_ACTION)
                        for i in grouped.get(ssd.CAT_PLAYABILITY, [])]
    rep.cue_production = [_to_item(i, SEC_CUE) for i in grouped.get(ssd.CAT_CUES, [])]
    rep.beat_alignment = _plan_alignment(grouped, beat, blocking, beat_section=True)
    rep.blocking_alignment = _plan_alignment(grouped, beat, blocking, beat_section=False)
    rep.continuity_risks = _continuity_items(grouped, psyke, db, project_id, scene_id)
    rep.questions = _questions(diag)
    rep.suggested_actions = _suggested_actions(diag, rep)
    return rep


# ===========================================================================
# AI seam (optional) — grounds the existing Counterpart prompt in the report
# ===========================================================================


def build_reflection_messages(
    report: StageScriptReflectionReport, *, scene_context: str = "",
) -> list[dict]:
    """Build messages for an optional AI pass that *explains/expands* the
    deterministic reflection. Reuses the existing Counterpart system prompt; the
    AI never rewrites the scene — it deepens the writer's reflection.

    Deterministic to build (no LLM call here)."""
    from logosforge.counterpart import SYSTEM_PROMPT
    parts: list[str] = []
    if scene_context:
        parts.append(scene_context)
        parts.append("")
    parts.append("Deterministic stage-script reflection (ground your feedback in "
                 "this; do not rewrite the scene):")
    parts.append(report.to_text())
    parts.append("")
    parts.append("As COUNTERPART, deepen this reflection from the audience's, the "
                 "actor's, the director's, and the dramaturg's point of view. Point "
                 "to the most important gaps and ask the writer 2-3 sharper "
                 "questions. Keep it structured. Do not produce replacement script.")
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": "\n".join(parts)},
    ]


# ===========================================================================
# Optional: save the reflection as a scene-linked Note (requires confirmation)
# ===========================================================================


def save_reflection_as_note(
    db, project_id: int, scene_id: int, report: StageScriptReflectionReport,
    *, confirmed: bool = False,
) -> dict:
    """Save a reflection as a Note linked to the scene. **Requires
    ``confirmed=True``** — nothing is written otherwise. Never auto-saves."""
    if not confirmed:
        return {"ok": False,
                "error": "Saving a reflection note requires confirmation."}
    scene = db.get_scene_by_id(scene_id)
    if scene is None:
        return {"ok": False, "error": "Scene not found."}
    title = f"Stage Reflection — {(getattr(scene, 'title', '') or 'Scene').strip()}"
    try:
        note = db.create_note(project_id, title, report.to_text(), tags="reflection")
        note_id = getattr(note, "id", note)
        db.link_note_to_scene(note_id, scene_id)
    except Exception as exc:
        return {"ok": False, "error": f"Could not save note: {exc}"}
    return {"ok": True, "note_id": note_id, "scene_id": scene_id}
