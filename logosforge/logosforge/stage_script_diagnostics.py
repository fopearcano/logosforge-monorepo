"""Deterministic Stage Script scene intelligence (Phase 3).

Evaluates a Stage Script *Scene* (its ordered stage blocks) as a stage play —
format/block order, stage action & blocking, theatrical playability, dialogue /
actor clarity, cues / production clarity, dramatic function, plan alignment, and
PSYKE continuity — with conservative, rule-based heuristics. Mirrors
``graphic_novel_diagnostics`` / ``screenplay_diagnostics``.

This is a WRITING/craft checker: it evaluates script clarity and playability
only. No autonomous rewriting, no auto-apply, no LLM, no DB writes, no Qt, and
no image generation of any kind.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from logosforge import stage_script_blocks as ssb

# Severity (shared scale with the other diagnostics).
SEV_INFO = "info"
SEV_WATCH = "watch"
SEV_WEAK = "weak"
SEV_CRITICAL = "critical"
_SEV_RANK = {SEV_INFO: 0, SEV_WATCH: 1, SEV_WEAK: 2, SEV_CRITICAL: 3}

# Categories (canonical render order).
CAT_FORMAT = "Format / Block Order"
CAT_BLOCKING = "Stage Action / Blocking"
CAT_PLAYABILITY = "Theatrical Playability"
CAT_DIALOGUE = "Dialogue / Actor Clarity"
CAT_CUES = "Cues / Production Clarity"
CAT_DRAMATIC = "Dramatic Function"
CAT_ALIGNMENT = "Plan Alignment"
CAT_CONTINUITY = "Continuity / PSYKE"
_CATEGORY_ORDER = (CAT_FORMAT, CAT_BLOCKING, CAT_PLAYABILITY, CAT_DIALOGUE,
                   CAT_CUES, CAT_DRAMATIC, CAT_ALIGNMENT, CAT_CONTINUITY)

# Documented thresholds (conservative).
CONSECUTIVE_DIALOGUE_HIGH = 6     # dialogue blocks in a row with no stage action
LONG_MONOLOGUE_WORDS = 120        # one dialogue block this long reads as a monologue
DIALOGUE_HEAVY_RATIO = 4.0        # dialogue blocks per stage direction
STAGE_DIRECTION_LONG_WORDS = 50   # a stage direction this long reads as novelistic
OVERLOADED_ACTIONS = 3            # action clauses in one stage direction

# Internal-state vocabulary — theatre must be *played*, so interiority in a stage
# direction should read as visible behavior, not narrated thought.
INTERNAL_STATE_WORDS = (
    "feels", "feeling", "felt", "realizes", "realises", "remembers", "thinks",
    "knows", "understands", "wonders", "hopes", "wishes", "loves", "hates",
    "regrets", "senses", "decides", "dreads", "yearns", "believes", "wants",
)
OBJECTIVE_MARKERS = (
    "want", "wants", "need", "needs", "must", "trying to", "going to",
    "has to", "have to", "to find", "to stop", "to save", "to escape",
)
TURN_MARKERS = (
    "but", "however", "suddenly", "then", "finally", "until", "instead",
    "no longer", "everything changes", "reveal", "turns", "realiz",
)
CONFLICT_WORDS = (
    "but", "no", "won't", "wont", "refuse", "stop", "against", "fight",
    "argue", "threat", "can't", "cant", "struggle", "block", "demand",
)


def _words(text: str) -> int:
    return len(re.findall(r"\S+", text or ""))


def _content_words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z']+", (text or "").lower()) if len(w) > 3}


def _sentences(text: str) -> list[str]:
    return [s for s in re.split(r"[.!?]+", text or "") if s.strip()]


@dataclass
class StageDiagnosticIssue:
    id: str
    label: str
    category: str
    severity: str = SEV_INFO
    evidence: str = ""
    block_number: int | None = None
    suggested_action: str = ""

    @property
    def severity_rank(self) -> int:
        return _SEV_RANK.get(self.severity, 0)

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "label": self.label, "category": self.category,
                "severity": self.severity, "evidence": self.evidence,
                "block_number": self.block_number,
                "suggested_action": self.suggested_action}


@dataclass
class StageSceneReport:
    scene_id: int | None = None
    total_blocks: int = 0
    character_count: int = 0
    dialogue_count: int = 0
    stage_direction_count: int = 0
    entrance_count: int = 0
    exit_count: int = 0
    lighting_count: int = 0
    sound_count: int = 0
    set_props_count: int = 0
    empty_block_count: int = 0
    internal_state_count: int = 0
    avg_dialogue_words: float = 0.0
    longest_dialogue_words: int = 0
    dialogue_stage_ratio: float = 0.0
    max_consecutive_dialogue: int = 0
    visible_stage_action: bool = False
    cue_completeness: float = 1.0
    issues: list[StageDiagnosticIssue] = field(default_factory=list)
    strengths: list[str] = field(default_factory=list)
    confidence: float = 0.0
    summary: str = ""

    def top_issues(self, n: int = 5) -> list[StageDiagnosticIssue]:
        return sorted(self.issues, key=lambda i: (i.severity_rank, i.label),
                      reverse=True)[:n]

    def to_dict(self) -> dict[str, Any]:
        return {
            "scene_id": self.scene_id, "total_blocks": self.total_blocks,
            "character_count": self.character_count,
            "dialogue_count": self.dialogue_count,
            "stage_direction_count": self.stage_direction_count,
            "entrance_count": self.entrance_count, "exit_count": self.exit_count,
            "lighting_count": self.lighting_count, "sound_count": self.sound_count,
            "set_props_count": self.set_props_count,
            "empty_block_count": self.empty_block_count,
            "internal_state_count": self.internal_state_count,
            "avg_dialogue_words": self.avg_dialogue_words,
            "longest_dialogue_words": self.longest_dialogue_words,
            "dialogue_stage_ratio": self.dialogue_stage_ratio,
            "max_consecutive_dialogue": self.max_consecutive_dialogue,
            "visible_stage_action": self.visible_stage_action,
            "cue_completeness": round(self.cue_completeness, 2),
            "issues": [i.to_dict() for i in self.issues],
            "strengths": list(self.strengths),
            "confidence": round(self.confidence, 2), "summary": self.summary,
        }


def group_issues_by_category(
    report: StageSceneReport,
) -> dict[str, list[StageDiagnosticIssue]]:
    grouped: dict[str, list[StageDiagnosticIssue]] = {}
    for issue in report.issues:
        grouped.setdefault(issue.category, []).append(issue)
    return {k: grouped[k] for k in _CATEGORY_ORDER if k in grouped}


# ===========================================================================
# Core analysis (pure: operates on a parsed StageScript)
# ===========================================================================


def _has_internal_state(text: str) -> bool:
    low = (text or "").lower()
    return any(re.search(rf"\b{re.escape(w)}\b", low) for w in INTERNAL_STATE_WORDS)


def analyze_scene(
    script: ssb.StageScript, *, scene_id: int | None = None,
    outline_summary: str = "", beat_plan: Any | None = None,
    blocking_plan: Any | None = None, psyke_characters: dict[str, bool] | None = None,
) -> StageSceneReport:
    """Deterministically analyze one Stage Script scene's blocks."""
    report = StageSceneReport(scene_id=scene_id)
    psyke_characters = psyke_characters or {}
    issues: list[StageDiagnosticIssue] = []
    blocks = script.blocks if script else []
    report.total_blocks = len(blocks)

    if not blocks:
        report.summary = "Empty scene — no stage blocks to analyze."
        report.confidence = 1.0
        if outline_summary.strip() or (beat_plan is not None
                                       and not _is_empty(beat_plan)):
            issues.append(StageDiagnosticIssue(
                id="no_body", label="No stage script yet", category=CAT_FORMAT,
                severity=SEV_WATCH,
                evidence="The scene has a summary/plan but no stage blocks.",
                suggested_action="Draft the scene from the plan, or add blocks."))
        report.issues = issues
        return report

    body = ssb.serialize_stage_script(script)
    body_words = set(re.findall(r"[a-z']+", body.lower()))
    dialogue_lengths: list[int] = []
    consecutive = 0
    cues_total = cues_with_text = 0
    has_speaker = False

    # -- Per-block pass (A, C, D, E + metrics) --
    for i, b in enumerate(blocks):
        bt = b.block_type
        n = i + 1
        if b.is_empty() and bt != ssb.BT_CHARACTER:
            report.empty_block_count += 1
            issues.append(StageDiagnosticIssue(
                id=f"empty_block_{n}", label="Empty block", category=CAT_FORMAT,
                severity=SEV_WATCH, block_number=n, evidence=f"Block {n} is empty.",
                suggested_action="Fill or remove the block."))

        if bt == ssb.BT_CHARACTER:
            report.character_count += 1
            has_speaker = True
            consecutive = 0
            nxt = next((nb for nb in blocks[i + 1:]
                        if nb.block_type != ssb.BT_PARENTHETICAL), None)
            if nxt is None or nxt.block_type != ssb.BT_DIALOGUE:
                issues.append(StageDiagnosticIssue(
                    id=f"character_no_dialogue_{n}",
                    label="Character cue without dialogue", category=CAT_FORMAT,
                    severity=SEV_WATCH, block_number=n,
                    evidence=f"{(b.character or b.text).strip().upper() or 'Character'}"
                             " has a cue but no following dialogue.",
                    suggested_action="Add the character's line, or remove the cue."))
        elif bt == ssb.BT_DIALOGUE:
            report.dialogue_count += 1
            dialogue_lengths.append(_words(b.text))
            if not has_speaker:
                issues.append(StageDiagnosticIssue(
                    id=f"dialogue_no_character_{n}",
                    label="Dialogue without a character cue", category=CAT_FORMAT,
                    severity=SEV_WATCH, block_number=n,
                    evidence=f"Block {n} is dialogue with no preceding character.",
                    suggested_action="Add a CHARACTER cue before the line."))
            consecutive += 1
            report.max_consecutive_dialogue = max(report.max_consecutive_dialogue,
                                                  consecutive)
            if _words(b.text) >= LONG_MONOLOGUE_WORDS:
                issues.append(StageDiagnosticIssue(
                    id=f"long_monologue_{n}", label="Long monologue",
                    category=CAT_DIALOGUE, severity=SEV_INFO, block_number=n,
                    evidence=f"{_words(b.text)} words in one speech.",
                    suggested_action="Break it up with action or another voice."))
        elif bt == ssb.BT_PARENTHETICAL:
            if not has_speaker:
                issues.append(StageDiagnosticIssue(
                    id=f"parenthetical_misuse_{n}",
                    label="Actor direction not attached to a character",
                    category=CAT_FORMAT, severity=SEV_INFO, block_number=n,
                    evidence=f"Block {n} is a parenthetical with no character/dialogue.",
                    suggested_action="Place it under a CHARACTER cue."))
        else:
            has_speaker = False
            consecutive = 0

        if bt == ssb.BT_STAGE_DIRECTION:
            report.stage_direction_count += 1
            if _has_internal_state(b.text):
                report.internal_state_count += 1
                issues.append(StageDiagnosticIssue(
                    id=f"internal_feeling_{n}", label="Unplayable interiority",
                    category=CAT_PLAYABILITY, severity=SEV_WATCH, block_number=n,
                    evidence="Stage direction narrates interior state "
                             "(feels/realizes/remembers…).",
                    suggested_action="Show the emotion as visible behavior."))
            if _words(b.text) >= STAGE_DIRECTION_LONG_WORDS:
                issues.append(StageDiagnosticIssue(
                    id=f"too_literary_{n}", label="Novelistic stage direction",
                    category=CAT_PLAYABILITY, severity=SEV_INFO, block_number=n,
                    evidence=f"Stage direction is {_words(b.text)} words.",
                    suggested_action="Tighten to playable, observable action."))
            actions = [s for s in _sentences(b.text) if _words(s) >= 3]
            if len(actions) >= OVERLOADED_ACTIONS:
                issues.append(StageDiagnosticIssue(
                    id=f"overloaded_direction_{n}",
                    label="Too many actions in one direction",
                    category=CAT_PLAYABILITY, severity=SEV_INFO, block_number=n,
                    evidence=f"{len(actions)} separate actions in one block.",
                    suggested_action="Split into beats the actors can play."))
        elif bt == ssb.BT_ENTRANCE:
            report.entrance_count += 1
            if not b.text.strip():
                issues.append(StageDiagnosticIssue(
                    id=f"entrance_no_name_{n}", label="Entrance without a character",
                    category=CAT_FORMAT, severity=SEV_WATCH, block_number=n,
                    evidence="Entrance has no character / movement text.",
                    suggested_action="Name who enters and from where."))
        elif bt == ssb.BT_EXIT:
            report.exit_count += 1
            if not b.text.strip():
                issues.append(StageDiagnosticIssue(
                    id=f"exit_no_name_{n}", label="Exit without a character",
                    category=CAT_FORMAT, severity=SEV_WATCH, block_number=n,
                    evidence="Exit has no character / movement text.",
                    suggested_action="Name who exits and to where."))
        elif bt in (ssb.BT_LIGHTING_CUE, ssb.BT_SOUND_CUE):
            cues_total += 1
            if bt == ssb.BT_LIGHTING_CUE:
                report.lighting_count += 1
            else:
                report.sound_count += 1
            if not b.text.strip():
                issues.append(StageDiagnosticIssue(
                    id=f"empty_cue_{n}",
                    label=f"{bt.replace('_', ' ').title()} without cue text",
                    category=CAT_CUES, severity=SEV_WATCH, block_number=n,
                    evidence=f"Block {n} cue has no text.",
                    suggested_action="Describe the cue."))
            else:
                cues_with_text += 1
                if _words(b.text) <= 1:
                    issues.append(StageDiagnosticIssue(
                        id=f"vague_cue_{n}", label="Vague cue",
                        category=CAT_CUES, severity=SEV_INFO, block_number=n,
                        evidence="Cue text is very short.",
                        suggested_action="Clarify the cue's intent."))
        elif bt == ssb.BT_SET_PROPS:
            report.set_props_count += 1

    # Metrics roll-up.
    if dialogue_lengths:
        report.avg_dialogue_words = round(sum(dialogue_lengths) / len(dialogue_lengths), 1)
        report.longest_dialogue_words = max(dialogue_lengths)
    report.dialogue_stage_ratio = round(
        report.dialogue_count / max(report.stage_direction_count, 1), 1)
    report.cue_completeness = round(cues_with_text / cues_total, 2) if cues_total else 1.0
    report.visible_stage_action = any(
        b.block_type in (ssb.BT_STAGE_DIRECTION, ssb.BT_ENTRANCE, ssb.BT_EXIT,
                         ssb.BT_LIGHTING_CUE, ssb.BT_SOUND_CUE, ssb.BT_SET_PROPS)
        for b in blocks)

    # -- B. Stage action / blocking --
    if report.dialogue_count and report.stage_direction_count == 0:
        issues.append(StageDiagnosticIssue(
            id="no_stage_direction", label="No stage directions",
            category=CAT_BLOCKING, severity=SEV_WATCH,
            evidence="The scene has dialogue but no stage directions.",
            suggested_action="Add blocking / business so it plays, not just reads."))
    if report.max_consecutive_dialogue >= CONSECUTIVE_DIALOGUE_HIGH:
        issues.append(StageDiagnosticIssue(
            id="too_many_dialogue", label="Long dialogue run without action",
            category=CAT_BLOCKING, severity=SEV_WATCH,
            evidence=f"{report.max_consecutive_dialogue} dialogue blocks in a row.",
            suggested_action="Interrupt with blocking, business, or a beat."))
    if report.dialogue_count >= 2 and not report.visible_stage_action:
        issues.append(StageDiagnosticIssue(
            id="no_visible_action", label="No visible stage action",
            category=CAT_BLOCKING, severity=SEV_WATCH,
            evidence="The scene is all talk — nothing to watch on stage.",
            suggested_action="Add entrances/exits, business, or cues."))
    if (report.dialogue_count and report.stage_direction_count
            and report.dialogue_stage_ratio >= DIALOGUE_HEAVY_RATIO):
        issues.append(StageDiagnosticIssue(
            id="dialogue_heavy", label="Dialogue-heavy scene",
            category=CAT_DIALOGUE, severity=SEV_INFO,
            evidence=f"{report.dialogue_stage_ratio} dialogue blocks per stage "
                     "direction.", suggested_action="Balance talk with stage life."))

    # -- F. Dramatic function (never asserts absence without confidence) --
    low_body = body.lower()
    if not any(re.search(rf"\b{re.escape(m)}\b", low_body) for m in OBJECTIVE_MARKERS) \
            and not outline_summary.strip():
        issues.append(StageDiagnosticIssue(
            id="objective_unclear", label="Scene objective unclear",
            category=CAT_DRAMATIC, severity=SEV_WATCH,
            evidence="No want/need language and no Outline summary.",
            suggested_action="Clarify what the scene is for."))
    if report.total_blocks >= 2 and not any(
            re.search(rf"\b{re.escape(w)}\b", low_body) for w in CONFLICT_WORDS):
        issues.append(StageDiagnosticIssue(
            id="conflict_unclear", label="Visible conflict unclear",
            category=CAT_DRAMATIC, severity=SEV_WATCH,
            evidence="No opposition/struggle language detected (heuristic).",
            suggested_action="Make the obstacle visible on stage."))
    if report.total_blocks >= 2 and not any(
            re.search(rf"\b{re.escape(m)}\b", low_body) for m in TURN_MARKERS):
        issues.append(StageDiagnosticIssue(
            id="turn_unclear", label="Turning point unclear",
            category=CAT_DRAMATIC, severity=SEV_INFO,
            evidence="No contrast/turn markers detected (heuristic).",
            suggested_action="Check the scene's value changes by the end."))

    # -- G. Plan alignment --
    _beat_alignment(beat_plan, body_words, issues)
    _blocking_alignment(blocking_plan, report, issues)

    # -- H. Continuity / PSYKE (warning-only; only when a Story Bible exists) --
    if psyke_characters:
        for name in ssb.character_cues(script):
            if name not in psyke_characters:
                issues.append(StageDiagnosticIssue(
                    id=f"character_not_in_psyke_{name}",
                    label=f"{name} not in Story Bible", category=CAT_CONTINUITY,
                    severity=SEV_INFO,
                    evidence=f"Speaker '{name}' has no PSYKE entry.",
                    suggested_action=f"Add {name} to PSYKE to track continuity."))

    # -- Strengths --
    if report.visible_stage_action and report.dialogue_count:
        report.strengths.append("Mixes dialogue with visible stage action.")
    if report.character_count and not any(
            i.id.startswith("dialogue_no_character") for i in issues):
        report.strengths.append("Every line is attributed to a character.")

    report.issues = list({i.id: i for i in issues}.values())
    report.confidence = 0.7
    report.summary = _summary(report)
    return report


def _beat_alignment(beat_plan, body_words: set[str],
                    issues: list[StageDiagnosticIssue]) -> None:
    if beat_plan is None or _is_empty(beat_plan):
        return
    for field_name, label, iid in (
        ("conflict", "Planned conflict not staged", "beat_conflict_missing"),
        ("turning_point", "Planned turning point not staged", "beat_turn_missing"),
    ):
        val = getattr(beat_plan, field_name, "") or ""
        cw = _content_words(val)
        if cw and not (cw & body_words):
            issues.append(StageDiagnosticIssue(
                id=iid, label=label, category=CAT_ALIGNMENT, severity=SEV_INFO,
                evidence=f'Beat plan ("{val.strip()[:50]}") isn\'t reflected in the body.',
                suggested_action="Stage this beat, or update the plan."))


def _blocking_alignment(blocking_plan, report: StageSceneReport,
                        issues: list[StageDiagnosticIssue]) -> None:
    if blocking_plan is None or _is_empty(blocking_plan):
        return
    planned_moves = (getattr(blocking_plan, "entrance_exit_plan", []) or [])
    if [m for m in planned_moves if str(m).strip()] and not (
            report.entrance_count or report.exit_count):
        issues.append(StageDiagnosticIssue(
            id="blocking_moves_missing", label="Planned entrances/exits not in body",
            category=CAT_ALIGNMENT, severity=SEV_WATCH,
            evidence="The blocking plan has entrance/exit moves the body doesn't show.",
            suggested_action="Add the planned entrances/exits, or update the plan."))
    if [c for c in (getattr(blocking_plan, "lighting_cues", []) or []) if str(c).strip()] \
            and not report.lighting_count:
        issues.append(StageDiagnosticIssue(
            id="blocking_light_missing", label="Planned lighting cue not in body",
            category=CAT_ALIGNMENT, severity=SEV_INFO,
            evidence="The blocking plan has lighting cues the body doesn't show.",
            suggested_action="Add the lighting cue, or update the plan."))
    if [c for c in (getattr(blocking_plan, "sound_cues", []) or []) if str(c).strip()] \
            and not report.sound_count:
        issues.append(StageDiagnosticIssue(
            id="blocking_sound_missing", label="Planned sound cue not in body",
            category=CAT_ALIGNMENT, severity=SEV_INFO,
            evidence="The blocking plan has sound cues the body doesn't show.",
            suggested_action="Add the sound cue, or update the plan."))


def _is_empty(obj: Any) -> bool:
    if obj is None:
        return True
    try:
        return bool(obj.is_empty())
    except Exception:
        return False


def _summary(report: StageSceneReport) -> str:
    head = (f"{report.total_blocks} block(s): {report.character_count} character / "
            f"{report.dialogue_count} dialogue / {report.stage_direction_count} "
            "stage direction.")
    top = report.top_issues(3)
    if not top:
        return head + " No notable issues detected."
    return head + " Top issues: " + "; ".join(i.label for i in top) + "."


# ===========================================================================
# DB adapter (read-only)
# ===========================================================================


def analyze_scene_by_id(db, project_id: int, scene_id: int) -> StageSceneReport:
    """Analyze one Stage Script scene by id (read-only). Loads the stage blocks +
    beat plan + blocking/cue plan + PSYKE map."""
    scene = None
    try:
        scene = db.get_scene_by_id(scene_id)
    except Exception:
        scene = None
    if scene is None:
        return StageSceneReport(scene_id=scene_id, summary="Scene not found.")
    script = ssb.load_scene_script(db, scene_id)
    outline_summary = getattr(scene, "summary", "") or ""
    beat = blocking = None
    try:
        from logosforge import stage_script_pipeline as ssp
        beat = ssp.get_beat_plan(db, project_id, scene_id)
        blocking = ssp.get_blocking_plan(db, project_id, scene_id)
    except Exception:
        beat = blocking = None
    psyke = {}
    try:
        from logosforge.screenplay_diagnostics import _psyke_character_map
        psyke = _psyke_character_map(db, project_id)
    except Exception:
        psyke = {}
    return analyze_scene(script, scene_id=scene_id, outline_summary=outline_summary,
                         beat_plan=beat, blocking_plan=blocking,
                         psyke_characters=psyke)
