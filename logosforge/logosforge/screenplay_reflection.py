"""Screenplay scene Reflection — the Counterpart/Logos two-stance mirror (Phase 5).

A deterministic, non-mutating reflection layer inspired by DuoDrama's *ExReflect*
(see ``docs/research/ai_screenwriting/``): it evaluates a scene from two stances —

* **Internal / experience (Counterpart)** — each character from the inside:
  apparent want, visible behavior, what the dialogue is doing.
* **External / evaluation (Logos)** — the audience/story view: what the scene
  reveals, whether conflict and the turning point are visible, whether it moves
  the story.

It does NOT generate or rewrite anything. It re-projects the existing Phase 3
deterministic diagnostics + the Phase 2 beat plan + PSYKE context into a
structured, writer-facing report of feedback and *reflective questions*. An
optional AI pass (via the existing Counterpart prompt) can explain/expand the
deterministic findings — grounded in this report, never replacing it.

Pure logic + DB reads. No Qt. No mutation. No PSYKE/Note creation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from logosforge import screenplay_blocks as sb
from logosforge import screenplay_diagnostics as sd

# Reuse Phase 3 severity scale + objective vocabulary (single source of truth).
SEV_INFO = sd.SEV_INFO
SEV_WATCH = sd.SEV_WATCH
SEV_WEAK = sd.SEV_WEAK
SEV_CRITICAL = sd.SEV_CRITICAL

# Section keys (also the canonical render order).
SEC_SNAPSHOT = "Scene Snapshot"
SEC_INTERNAL = "Internal Character Perspective"
SEC_EXTERNAL = "External Audience Perspective"
SEC_CONFLICT = "Conflict / Objective / Obstacle"
SEC_VISUAL = "Visual Action Notes"
SEC_DIALOGUE = "Dialogue Notes"
SEC_ALIGN = "Beat Plan Alignment"
SEC_CONTINUITY = "Continuity / PSYKE Risks"
SEC_REVISION = "Revision Suggestions"
SEC_QUESTIONS = "Questions for the Writer"

_DIALOGUE_EXPOSITION_WORDS = 45     # one character's total dialogue words ~ talky


def _words(text: str) -> int:
    return len(re.findall(r"\S+", text or ""))


# ===========================================================================
# Data model
# ===========================================================================


@dataclass
class ReflectionItem:
    category: str
    title: str
    detail: str = ""
    severity: str = SEV_INFO
    target_block_index: int | None = None
    psyke_entry_id: int | None = None
    suggested_action: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category, "title": self.title, "detail": self.detail,
            "severity": self.severity, "target_block_index": self.target_block_index,
            "psyke_entry_id": self.psyke_entry_id,
            "suggested_action": self.suggested_action,
        }


@dataclass
class CharacterReflection:
    name: str
    linked: bool = False                 # has a PSYKE entry?
    psyke_entry_id: int | None = None
    wants: str = "unclear"
    visible_behavior: str = "weak"       # weak | present
    dialogue_function: str = "—"
    emotional_note: str = ""
    notes: list[str] = field(default_factory=list)
    suggestion: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name, "linked": self.linked,
            "psyke_entry_id": self.psyke_entry_id, "wants": self.wants,
            "visible_behavior": self.visible_behavior,
            "dialogue_function": self.dialogue_function,
            "emotional_note": self.emotional_note,
            "notes": list(self.notes), "suggestion": self.suggestion,
        }


@dataclass
class SceneReflectionReport:
    scene_id: int | None = None
    snapshot: str = ""
    characters: list[CharacterReflection] = field(default_factory=list)
    external: list[ReflectionItem] = field(default_factory=list)
    conflict_objective: list[ReflectionItem] = field(default_factory=list)
    visual_notes: list[ReflectionItem] = field(default_factory=list)
    dialogue_notes: list[ReflectionItem] = field(default_factory=list)
    beat_plan_alignment: list[ReflectionItem] = field(default_factory=list)
    continuity_risks: list[ReflectionItem] = field(default_factory=list)
    revision_suggestions: list[str] = field(default_factory=list)
    questions: list[str] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)
    ai_enhanced: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "scene_id": self.scene_id, "snapshot": self.snapshot,
            "characters": [c.to_dict() for c in self.characters],
            "external": [i.to_dict() for i in self.external],
            "conflict_objective": [i.to_dict() for i in self.conflict_objective],
            "visual_notes": [i.to_dict() for i in self.visual_notes],
            "dialogue_notes": [i.to_dict() for i in self.dialogue_notes],
            "beat_plan_alignment": [i.to_dict() for i in self.beat_plan_alignment],
            "continuity_risks": [i.to_dict() for i in self.continuity_risks],
            "revision_suggestions": list(self.revision_suggestions),
            "questions": list(self.questions),
            "metrics": dict(self.metrics), "ai_enhanced": self.ai_enhanced,
        }

    def to_text(self) -> str:
        """Readable, copy-friendly rendering (used by the Logos result + Notes)."""
        lines: list[str] = [f"{SEC_SNAPSHOT}: {self.snapshot}", ""]

        lines.append(SEC_INTERNAL + ":")
        if self.characters:
            for c in self.characters:
                tag = "" if c.linked else " (unlinked)"
                lines.append(f"- {c.name}{tag} — wants: {c.wants}; behavior: "
                             f"{c.visible_behavior}; dialogue: {c.dialogue_function}")
                if c.emotional_note:
                    lines.append(f"    emotion: {c.emotional_note}")
                if c.suggestion:
                    lines.append(f"    → {c.suggestion}")
        else:
            lines.append("- No speaking characters detected.")

        for header, items in (
            (SEC_EXTERNAL, self.external),
            (SEC_CONFLICT, self.conflict_objective),
            (SEC_VISUAL, self.visual_notes),
            (SEC_DIALOGUE, self.dialogue_notes),
            (SEC_ALIGN, self.beat_plan_alignment),
            (SEC_CONTINUITY, self.continuity_risks),
        ):
            lines.append("")
            lines.append(header + ":")
            if items:
                for i in items:
                    tgt = (f" (block {i.target_block_index + 1})"
                           if i.target_block_index is not None else "")
                    lines.append(f"- [{i.severity}] {i.title}{tgt} — {i.detail}")
            else:
                lines.append("- Nothing flagged.")

        lines.append("")
        lines.append(SEC_REVISION + ":")
        lines.extend(f"- {s}" for s in (self.revision_suggestions or ["None."]))
        lines.append("")
        lines.append(SEC_QUESTIONS + ":")
        lines.extend(f"- {q}" for q in (self.questions or ["—"]))
        return "\n".join(lines)


# ===========================================================================
# PSYKE helpers (read-only; never creates entries)
# ===========================================================================


def _psyke_characters_by_name(db, project_id: int) -> dict[str, dict]:
    """Uppercased PSYKE character name -> {id, has_goal}. Read-only."""
    out: dict[str, dict] = {}
    try:
        entries = db.get_all_psyke_entries(project_id)
    except Exception:
        return out
    for e in entries:
        if (getattr(e, "entry_type", "") or "").lower() != "character":
            continue
        name = (getattr(e, "name", "") or "").strip().upper()
        if not name:
            continue
        has_goal = False
        try:
            details = db.get_psyke_entry_details(e.id) or {}
            has_goal = any(str(details.get(k, "")).strip() for k in sd._OBJECTIVE_KEYS)
        except Exception:
            has_goal = False
        out[name] = {"id": getattr(e, "id", None), "has_goal": has_goal}
    return out


# ===========================================================================
# Core builder
# ===========================================================================


def _to_item(issue: sd.ScreenplayDiagnosticIssue, category: str,
             psyke_id: int | None = None) -> ReflectionItem:
    return ReflectionItem(
        category=category, title=issue.label, detail=issue.evidence,
        severity=issue.severity, target_block_index=issue.target_block_index,
        psyke_entry_id=psyke_id, suggested_action=issue.suggested_action)


def _character_reflections(
    blocks: list[sb.ScreenplayBlock], psyke: dict[str, dict],
    emotional_shift: str,
) -> list[CharacterReflection]:
    dialogue_by: dict[str, list[str]] = {}
    speaker: str | None = None
    for b in blocks:
        if b.element_type == "character":
            speaker = re.sub(r"\(.*?\)", "", b.text).strip().upper()
            dialogue_by.setdefault(speaker, [])
        elif b.element_type == "dialogue" and speaker:
            dialogue_by[speaker].append(b.text)
    action_text = " ".join(b.text.lower() for b in blocks
                           if b.element_type == "action")

    out: list[CharacterReflection] = []
    for name in sb.character_cues(blocks):
        entry = psyke.get(name)
        lines = dialogue_by.get(name, [])
        joined = " ".join(lines).lower()
        words = _words(" ".join(lines))

        has_obj_lang = any(re.search(rf"\b{re.escape(m)}\b", joined)
                           for m in sd.OBJECTIVE_MARKERS)
        if has_obj_lang:
            wants = "stated in dialogue (verify it's also visible)"
        elif entry and entry.get("has_goal"):
            wants = "defined in PSYKE (confirm the scene plays it)"
        else:
            wants = "unclear"

        if not lines:
            dialogue_function = "no dialogue (acts in silence?)"
        elif words >= _DIALOGUE_EXPOSITION_WORDS:
            dialogue_function = "exposition-heavy (long speeches)"
        else:
            dialogue_function = "present"

        visible = "present" if name.lower() in action_text else "weak"

        notes: list[str] = []
        if entry is None:
            notes.append("unlinked character — no PSYKE entry")
        suggestion = (
            f"Give {name} a visible action that reinforces or contradicts the line."
            if visible == "weak"
            else f"Check that {name}'s behavior externalizes the objective.")

        out.append(CharacterReflection(
            name=name, linked=entry is not None,
            psyke_entry_id=(entry or {}).get("id"), wants=wants,
            visible_behavior=visible, dialogue_function=dialogue_function,
            emotional_note=(emotional_shift.strip()
                            if emotional_shift.strip() else ""),
            notes=notes, suggestion=suggestion))
    return out


def _snapshot(scene, diag: sd.ScreenplaySceneReport, plan) -> str:
    where = " / ".join(p for p in ((getattr(scene, "act", "") or "").strip(),
                                   (getattr(scene, "chapter", "") or "").strip()) if p)
    chars = ", ".join(diag.unique_characters) or "—"
    bits = [
        f"{where or 'Unplaced'} · {diag.block_count} blocks "
        f"({diag.action_block_count} action / {diag.dialogue_block_count} dialogue)",
        f"economy: {diag.economy_label or 'unknown'}",
        f"characters: {chars}",
    ]
    if plan is not None and not plan.is_empty():
        bits.append("beat plan: present")
    return " · ".join(bits)


def build_scene_reflection(db, project_id: int, scene_id: int) -> SceneReflectionReport:
    """Build a deterministic two-stance reflection for a scene. Read-only."""
    rep = SceneReflectionReport(scene_id=scene_id)
    scene = db.get_scene_by_id(scene_id)
    if scene is None:
        rep.snapshot = "Scene not found."
        return rep

    content = getattr(scene, "content", "") or ""
    blocks = sb.parse_screenplay_text(content, scene_id=scene_id)
    diag = sd.analyze_scene_by_id(db, project_id, scene_id)
    psyke = _psyke_characters_by_name(db, project_id)

    plan = None
    try:
        from logosforge.screenplay_pipeline import get_beat_plan
        plan = get_beat_plan(db, project_id, scene_id)
    except Exception:
        plan = None
    emotional_shift = (getattr(plan, "emotional_shift", "") or "") if plan else ""

    rep.metrics = {
        "block_count": diag.block_count,
        "action_block_count": diag.action_block_count,
        "dialogue_block_count": diag.dialogue_block_count,
        "economy_label": diag.economy_label,
        "action_dialogue_ratio": diag.action_dialogue_ratio,
        "unique_characters": list(diag.unique_characters),
        "beat_plan_aligned": diag.beat_plan_aligned,
    }
    rep.snapshot = _snapshot(scene, diag, plan)
    rep.characters = _character_reflections(blocks, psyke, emotional_shift)

    grouped = sd.group_issues_by_category(diag)

    # External / evaluation stance (audience + story).
    summary = (getattr(scene, "summary", "") or "").strip()
    if summary:
        rep.external.append(ReflectionItem(
            category=SEC_EXTERNAL, title="Intended purpose (Outline)",
            detail=summary, severity=SEV_INFO))
    for issue in grouped.get("Dramatic Function", []):
        if issue.id == "scene_turn_unclear":
            rep.external.append(ReflectionItem(
                category=SEC_EXTERNAL, title="Story state change unclear",
                detail=("No contrast/turn markers — the audience may not see the "
                        "scene change anything."), severity=issue.severity,
                suggested_action="Make the value shift visible by the last beat."))
    if diag.economy_label == "sparse":
        rep.external.append(ReflectionItem(
            category=SEC_EXTERNAL, title="Sparse scene",
            detail="Little visible content — the audience may learn little here.",
            severity=SEV_WATCH))
    rep.external.extend(_redundancy_items(db, project_id, scene))

    # Conflict / objective / obstacle.
    for issue in grouped.get("Dramatic Function", []):
        if issue.id == "objective_unclear":
            rep.conflict_objective.append(_to_item(issue, SEC_CONFLICT))
    for issue in grouped.get("Beat Plan Alignment", []):
        if issue.id == "align_conflict_missing":
            rep.conflict_objective.append(_to_item(issue, SEC_CONFLICT))
    if not _has_conflict_signal(blocks):
        rep.conflict_objective.append(ReflectionItem(
            category=SEC_CONFLICT, title="Visible conflict unclear",
            detail=("No opposition/struggle language detected (deterministic "
                    "heuristic)."), severity=SEV_WATCH,
            suggested_action="Make the obstacle or opposing want visible."))

    # Craft sections (re-projected Phase 3 issues).
    rep.visual_notes = [_to_item(i, SEC_VISUAL)
                        for i in grouped.get("Visual Writing", [])]
    rep.dialogue_notes = [_to_item(i, SEC_DIALOGUE)
                          for i in grouped.get("Dialogue Economy", [])]
    if plan is None or plan.is_empty():
        rep.beat_plan_alignment = [ReflectionItem(
            category=SEC_ALIGN, title="No beat plan",
            detail="No beat plan to compare against — generate one to reflect "
                   "on alignment.", severity=SEV_INFO)]
    else:
        rep.beat_plan_alignment = [_to_item(i, SEC_ALIGN)
                                   for i in grouped.get("Beat Plan Alignment", [])]
        if not rep.beat_plan_alignment:
            rep.beat_plan_alignment = [ReflectionItem(
                category=SEC_ALIGN, title="Body reflects the beat plan",
                detail="Planned elements appear in the body (keyword check).",
                severity=SEV_INFO)]

    name_to_id = {n: v.get("id") for n, v in psyke.items()}
    for issue in grouped.get("Continuity", []):
        cue = issue.id.replace("character_not_in_psyke_", "")
        rep.continuity_risks.append(_to_item(issue, SEC_CONTINUITY,
                                             psyke_id=name_to_id.get(cue)))
    rep.continuity_risks.extend(_timeline_items(db, project_id, scene_id))

    rep.revision_suggestions = _revision_suggestions(diag, rep.characters)
    rep.questions = _questions(diag, plan, rep.characters)
    return rep


# -- External-stance helpers -------------------------------------------------

_CONFLICT_WORDS = (
    "but", "no", "won't", "wont", "refuse", "stop", "against", "fight", "argue",
    "demand", "threat", "can't", "cant", "deny", "resist", "block", "struggle",
)


def _has_conflict_signal(blocks: list[sb.ScreenplayBlock]) -> bool:
    body = " ".join(b.text.lower() for b in blocks
                    if b.element_type in ("action", "dialogue"))
    return any(re.search(rf"\b{re.escape(w)}\b", body) for w in _CONFLICT_WORDS)


def _redundancy_items(db, project_id: int, scene) -> list[ReflectionItem]:
    """Light redundancy heuristic: high summary-keyword overlap with a neighbor."""
    items: list[ReflectionItem] = []
    summary = (getattr(scene, "summary", "") or "").strip().lower()
    if len(summary) < 12:
        return items
    words = {w for w in re.findall(r"[a-z']+", summary) if len(w) > 3}
    if not words:
        return items
    try:
        scenes = db.get_all_scenes(project_id)
    except Exception:
        return items
    sid = getattr(scene, "id", None)
    for other in scenes:
        if getattr(other, "id", None) == sid:
            continue
        osum = (getattr(other, "summary", "") or "").strip().lower()
        ow = {w for w in re.findall(r"[a-z']+", osum) if len(w) > 3}
        if ow and len(words & ow) / max(len(words), 1) >= 0.6:
            items.append(ReflectionItem(
                category=SEC_EXTERNAL, title="Possible redundancy",
                detail=(f"This scene's purpose overlaps heavily with "
                        f"“{getattr(other, 'title', 'another scene')}”."),
                severity=SEV_WATCH,
                suggested_action="Confirm each scene earns its place."))
            break
    return items


def _timeline_items(db, project_id: int, scene_id: int) -> list[ReflectionItem]:
    """Note a linked Timeline event if the data is safely available (read-only)."""
    try:
        events = db.get_timeline_event_ids(project_id)
    except Exception:
        return []
    if scene_id in (events or []):
        return [ReflectionItem(
            category=SEC_CONTINUITY, title="Linked to the Timeline",
            detail="This scene is an explicit Timeline event — keep chronology "
                   "consistent.", severity=SEV_INFO)]
    return []


# -- Revision suggestions + questions ----------------------------------------


def _revision_suggestions(
    diag: sd.ScreenplaySceneReport, characters: list[CharacterReflection],
) -> list[str]:
    out: list[str] = []
    for issue in diag.issues:
        if issue.suggested_action:
            out.append(issue.suggested_action)
    for c in characters:
        if c.suggestion:
            out.append(c.suggestion)
    # Stable de-duplication.
    return list(dict.fromkeys(out))[:10]


def _questions(diag, plan, characters: list[CharacterReflection]) -> list[str]:
    """Reflective questions (DuoDrama-style) — never answers, never rewrites."""
    qs: list[str] = []
    ids = {i.id for i in diag.issues}
    if any(i == "objective_unclear" for i in ids) or any(
            c.wants == "unclear" for c in characters):
        qs.append("What does the protagonist visibly do to pursue the objective?")
    if "scene_turn_unclear" in ids:
        qs.append("What changes between the first beat and the last beat?")
    if diag.economy_label == "dialogue-heavy" or any(
            "exposition" in c.dialogue_function for c in characters):
        qs.append("Can any exposition here be turned into behavior?")
        qs.append("Which line could be replaced by an action?")
    if plan is not None and not plan.is_empty():
        qs.append("Does the scene dramatize each beat of the plan, or just state it?")
    # Always-useful subtext prompt (DuoDrama experience lens).
    qs.append("Which object, place, or gesture could carry the subtext?")
    return list(dict.fromkeys(qs))


# ===========================================================================
# AI seam (optional) — grounds the existing Counterpart prompt in the report
# ===========================================================================


def build_reflection_messages(
    report: SceneReflectionReport, *, scene_context: str = "",
) -> list[dict]:
    """Build messages for an optional AI pass that *explains/expands* the
    deterministic reflection. Reuses the existing Counterpart system prompt; the
    AI never rewrites the scene — it deepens the writer's reflection.

    Deterministic to build (no LLM call here). The caller runs it through the
    shared chat backend only if a provider is configured."""
    from logosforge.counterpart import SYSTEM_PROMPT
    parts: list[str] = []
    if scene_context:
        parts.append(scene_context)
        parts.append("")
    parts.append("Deterministic reflection (ground your feedback in this; do not "
                 "rewrite the scene):")
    parts.append(report.to_text())
    parts.append("")
    parts.append("As COUNTERPART, deepen this reflection: from the character's "
                 "inside view and the audience's outside view, point to the most "
                 "important gaps and ask the writer 2–3 sharper questions. Keep it "
                 "structured. Do not produce replacement prose.")
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": "\n".join(parts)},
    ]


# ===========================================================================
# Optional: save the reflection as a scene-linked Note (requires confirmation)
# ===========================================================================


def save_reflection_as_note(
    db, project_id: int, scene_id: int, report: SceneReflectionReport,
    *, confirmed: bool = False,
) -> dict:
    """Save a reflection as a Note linked to the scene. **Requires
    ``confirmed=True``** — nothing is written otherwise. Never auto-saves."""
    if not confirmed:
        return {"ok": False, "error": "Saving a reflection note requires confirmation."}
    scene = db.get_scene_by_id(scene_id)
    if scene is None:
        return {"ok": False, "error": "Scene not found."}
    title = f"Reflection — {(getattr(scene, 'title', '') or 'Scene').strip()}"
    try:
        note = db.create_note(project_id, title, report.to_text(), tags="reflection")
        note_id = getattr(note, "id", note)
        db.link_note_to_scene(note_id, scene_id)
    except Exception as exc:
        return {"ok": False, "error": f"Could not save note: {exc}"}
    return {"ok": True, "note_id": note_id, "scene_id": scene_id}
