"""Deterministic screenplay diagnostics + scene economy (Phase 10C).

Evaluates a screenplay scene *as a screenplay scene* — using the Phase 10B block
parser — with conservative, rule-based heuristics. No LLM, no DB writes, no Qt.

Everything here is evidence-based and confidence-aware: where semantics can't be
known without an LLM (scene turn, subtext) the report says so ("unclear") rather
than inventing precision. Thresholds are module constants and documented.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from logosforge import screenplay_blocks as sb

# -- Severity (issue-local scale) --------------------------------------------
SEV_INFO = "info"
SEV_WATCH = "watch"
SEV_WEAK = "weak"
SEV_CRITICAL = "critical"
_SEV_RANK = {SEV_INFO: 0, SEV_WATCH: 1, SEV_WEAK: 2, SEV_CRITICAL: 3}

# -- Documented thresholds ---------------------------------------------------
ACTION_BLOCK_LONG_WORDS = 60        # an action paragraph this long may be overwritten
LONG_DIALOGUE_WORDS = 50            # a single dialogue block this long ~ monologue
PARENTHETICAL_RATIO_HIGH = 0.4      # parentheticals / dialogue blocks
DIALOGUE_ACTION_RATIO_HIGH = 4.0    # dialogue-heavy if dlg/action exceeds this
ACTION_DIALOGUE_RATIO_HIGH = 6.0    # action-heavy if action blocks dominate
TRANSITION_OVERUSE = 2              # more than this many transitions in one scene
SHOT_OVERUSE = 3                    # more than this many explicit shots
INTERNAL_WORDS_PER_BLOCK = 2        # internal-state words in one action block
LINES_PER_PAGE = 55                 # rough screenplay page (1 page ~ 1 minute)

# Internal-state vocabulary — action should show, not narrate interiority.
INTERNAL_STATE_WORDS = (
    "thinks", "think", "thought", "remembers", "remember", "remembered",
    "feels", "feel", "felt", "realizes", "realises", "realized", "realised",
    "understands", "understood", "wonders", "wondered", "knows", "knew",
    "believes", "believed", "decides", "decided", "considers", "imagines",
    "recalls", "wishes", "hopes",
)
# Turn / contrast markers — weak signals that a scene shifts value.
TURN_MARKERS = (
    "but", "however", "instead", "suddenly", "then", "finally", "until",
    "despite", "yet", "no longer", "everything changes",
)
# Objective markers — a character appears to want something.
OBJECTIVE_MARKERS = (
    "want", "wants", "wanted", "need", "needs", "needed", "has to", "have to",
    "must", "trying to", "going to", "i'll", "we have to", "let's",
)
# Setup/payoff candidate markers (hooks for the Phase 10D setup/payoff engine).
SETUP_MARKERS = (
    "remember", "promise", "swear", "don't forget", "one day", "someday",
    "i'll be back", "keep this", "never forget", "if anything happens",
)


def _words(text: str) -> int:
    return len(re.findall(r"\S+", text or ""))


@dataclass
class ScreenplayDiagnosticIssue:
    id: str
    label: str
    severity: str = SEV_INFO
    confidence: float = 0.0
    evidence: str = ""
    target_block_index: int | None = None
    suggested_action: str = ""
    logos_action_id: str | None = None

    @property
    def severity_rank(self) -> int:
        return _SEV_RANK.get(self.severity, 0)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "severity": self.severity,
            "confidence": round(self.confidence, 2),
            "evidence": self.evidence,
            "target_block_index": self.target_block_index,
            "suggested_action": self.suggested_action,
            "logos_action_id": self.logos_action_id,
        }


@dataclass
class ScreenplaySceneReport:
    scene_id: int | None = None
    scene_heading: str = ""
    block_count: int = 0
    action_block_count: int = 0
    dialogue_block_count: int = 0
    character_cue_count: int = 0
    unique_characters: list[str] = field(default_factory=list)
    estimated_page_fraction: float = 0.0
    estimated_minutes: float = 0.0
    dominant_block_type: str = ""
    economy_label: str = ""           # dialogue-heavy | action-heavy | balanced | sparse
    issues: list[ScreenplayDiagnosticIssue] = field(default_factory=list)
    strengths: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    confidence: float = 0.0
    summary: str = ""
    # Phase 3 — extended, transparent metrics.
    parenthetical_block_count: int = 0
    empty_block_count: int = 0
    average_dialogue_words: float = 0.0
    longest_dialogue_words: int = 0
    action_dialogue_ratio: float = 0.0
    internal_state_phrase_count: int = 0
    repeated_character_turns: int = 0
    # Phase 3 — beat-plan alignment: True/False when a plan exists, else None.
    beat_plan_aligned: bool | None = None

    def top_issues(self, n: int = 3) -> list[ScreenplayDiagnosticIssue]:
        return sorted(
            self.issues, key=lambda i: (i.severity_rank, i.confidence), reverse=True,
        )[:n]

    def to_dict(self) -> dict[str, Any]:
        return {
            "scene_id": self.scene_id,
            "scene_heading": self.scene_heading,
            "block_count": self.block_count,
            "action_block_count": self.action_block_count,
            "dialogue_block_count": self.dialogue_block_count,
            "character_cue_count": self.character_cue_count,
            "unique_characters": list(self.unique_characters),
            "estimated_page_fraction": self.estimated_page_fraction,
            "estimated_minutes": self.estimated_minutes,
            "dominant_block_type": self.dominant_block_type,
            "economy_label": self.economy_label,
            "issues": [i.to_dict() for i in self.issues],
            "strengths": list(self.strengths),
            "warnings": list(self.warnings),
            "confidence": round(self.confidence, 2),
            "summary": self.summary,
            "parenthetical_block_count": self.parenthetical_block_count,
            "empty_block_count": self.empty_block_count,
            "average_dialogue_words": self.average_dialogue_words,
            "longest_dialogue_words": self.longest_dialogue_words,
            "action_dialogue_ratio": self.action_dialogue_ratio,
            "internal_state_phrase_count": self.internal_state_phrase_count,
            "repeated_character_turns": self.repeated_character_turns,
            "beat_plan_aligned": self.beat_plan_aligned,
        }


# ---------------------------------------------------------------------------
# Core analysis (pure: operates on parsed blocks)
# ---------------------------------------------------------------------------


def analyze_scene(
    blocks: list[sb.ScreenplayBlock],
    *,
    scene_id: int | None = None,
    scene_heading: str = "",
    psyke_characters: dict[str, bool] | None = None,
    beat_plan: Any | None = None,
) -> ScreenplaySceneReport:
    """Deterministically analyze one scene's blocks.

    *psyke_characters* maps uppercased character name -> has-objective-data, used
    only to raise/lower the character-objective confidence. Absent data lowers
    confidence; it never hard-fails.

    *beat_plan* (Phase 3) is an optional :class:`screenplay_pipeline.ScreenplayBeatPlan`.
    When given, the report adds deterministic beat-plan *alignment* issues (does
    the body reflect the planned conflict / turn / emotional shift / objective?)
    and sets ``beat_plan_aligned``. It is read-only — the plan is never mutated.
    """
    report = ScreenplaySceneReport(scene_id=scene_id, scene_heading=scene_heading)
    psyke_characters = psyke_characters or {}

    counts: dict[str, int] = {}
    for b in blocks:
        counts[b.element_type] = counts.get(b.element_type, 0) + 1

    report.block_count = len(blocks)
    report.action_block_count = counts.get("action", 0)
    report.dialogue_block_count = counts.get("dialogue", 0)
    report.character_cue_count = counts.get("character", 0)
    report.unique_characters = sb.character_cues(blocks)

    # Rough runtime estimate (clearly approximate: ~1 screenplay page/minute).
    line_count = sum(max(1, b.text.count("\n") + 1) for b in blocks)
    report.estimated_page_fraction = round(line_count / LINES_PER_PAGE, 2)
    report.estimated_minutes = report.estimated_page_fraction  # 1 page ≈ 1 min

    if counts:
        report.dominant_block_type = max(counts, key=lambda k: counts[k])

    issues: list[ScreenplayDiagnosticIssue] = []

    # --- Empty / notes-only / no-heading ---
    if not blocks:
        report.economy_label = "sparse"
        report.summary = "Empty scene — no screenplay content to analyze."
        report.confidence = 1.0
        return report

    if counts.get("note", 0) == len(blocks):
        issues.append(ScreenplayDiagnosticIssue(
            id="only_notes", label="Scene contains only notes", severity=SEV_WEAK,
            confidence=0.9, evidence="Every block is a note; no action or dialogue.",
            suggested_action="Add scene action and/or dialogue.",
        ))

    has_heading = bool(scene_heading.strip()) or counts.get("scene_heading", 0) > 0
    if not has_heading:
        issues.append(ScreenplayDiagnosticIssue(
            id="missing_scene_heading", label="Scene heading missing", severity=SEV_WATCH,
            confidence=0.8,
            evidence="No INT./EXT. scene heading was found for this scene.",
            suggested_action="Add a scene heading (INT./EXT. LOCATION - TIME).",
        ))

    # --- Scene economy (ratios) ---
    a = report.action_block_count
    d = report.dialogue_block_count
    if a == 0 and d == 0:
        report.economy_label = "sparse"
    elif d >= 1 and (a == 0 or d / max(a, 1) >= DIALOGUE_ACTION_RATIO_HIGH):
        report.economy_label = "dialogue-heavy"
        issues.append(ScreenplayDiagnosticIssue(
            id="dialogue_heavy", label="Scene is dialogue-heavy", severity=SEV_WATCH,
            confidence=0.6,
            evidence=f"{d} dialogue block(s) vs {a} action block(s).",
            suggested_action="Add visual action beats between dialogue.",
            logos_action_id="sp_suggest_action_interruption",
        ))
    elif a >= 1 and (d == 0 or a / max(d, 1) >= ACTION_DIALOGUE_RATIO_HIGH):
        report.economy_label = "action-heavy"
        if d == 0:
            issues.append(ScreenplayDiagnosticIssue(
                id="no_dialogue", label="Scene has no dialogue", severity=SEV_INFO,
                confidence=0.5,
                evidence=f"{a} action block(s), no dialogue.",
                suggested_action="Confirm a silent/visual scene is intended.",
            ))
    else:
        report.economy_label = "balanced"

    # --- Visual action: internal-state language ---
    internal_total = 0
    for idx, b in enumerate(blocks):
        if b.element_type != "action":
            continue
        low = b.text.lower()
        hits = sum(1 for w in INTERNAL_STATE_WORDS if re.search(rf"\b{re.escape(w)}\b", low))
        internal_total += hits
        if hits >= INTERNAL_WORDS_PER_BLOCK:
            issues.append(ScreenplayDiagnosticIssue(
                id=f"internal_action_{idx}", label="Action may read as internal prose",
                severity=SEV_WATCH, confidence=0.55, target_block_index=idx,
                evidence=(f"Action block uses {hits} internal-state words "
                          "(thinks/feels/realizes…)."),
                suggested_action="This may read as internal prose rather than "
                                 "visible action; externalize it.",
                logos_action_id="sp_visual_action",
            ))
        if _words(b.text) >= ACTION_BLOCK_LONG_WORDS:
            issues.append(ScreenplayDiagnosticIssue(
                id=f"overwritten_action_{idx}", label="Action block may be overwritten",
                severity=SEV_WATCH, confidence=0.5, target_block_index=idx,
                evidence=f"Action block is {_words(b.text)} words.",
                suggested_action="Consider tightening to essential visible beats.",
                logos_action_id="sp_overwritten_action",
            ))

    # --- Dialogue economy ---
    for idx, b in enumerate(blocks):
        if b.element_type == "dialogue" and _words(b.text) >= LONG_DIALOGUE_WORDS:
            issues.append(ScreenplayDiagnosticIssue(
                id=f"long_dialogue_{idx}", label="Long dialogue block", severity=SEV_WATCH,
                confidence=0.5, target_block_index=idx,
                evidence=f"Dialogue block is {_words(b.text)} words (monologue-like).",
                suggested_action="Consider breaking up or interrupting with action.",
                logos_action_id="sp_tighten_dialogue",
            ))
    # Parenthetical overuse.
    paren = counts.get("parenthetical", 0)
    if d > 0 and paren / d >= PARENTHETICAL_RATIO_HIGH:
        issues.append(ScreenplayDiagnosticIssue(
            id="parenthetical_overuse", label="Parentheticals may be overused",
            severity=SEV_WATCH, confidence=0.6,
            evidence=f"{paren} parenthetical(s) across {d} dialogue block(s).",
            suggested_action="Trust the dialogue; cut redundant parentheticals.",
        ))
    # Single-voice scene.
    if d >= 3 and len(report.unique_characters) <= 1:
        issues.append(ScreenplayDiagnosticIssue(
            id="single_voice", label="Scene dominated by one voice", severity=SEV_WATCH,
            confidence=0.55,
            evidence="Multiple dialogue blocks but only one speaking character.",
            suggested_action="Consider another voice or visual response.",
        ))

    # --- Transition / shot overuse ---
    if counts.get("transition", 0) > TRANSITION_OVERUSE:
        issues.append(ScreenplayDiagnosticIssue(
            id="transition_overuse", label="Transitions may be overused", severity=SEV_INFO,
            confidence=0.6,
            evidence=f"{counts['transition']} transitions in one scene.",
            suggested_action="Most scenes need at most one transition out.",
        ))
    if counts.get("shot", 0) > SHOT_OVERUSE:
        issues.append(ScreenplayDiagnosticIssue(
            id="shot_overuse", label="Explicit shots may be overused", severity=SEV_INFO,
            confidence=0.6,
            evidence=f"{counts['shot']} explicit shot directions.",
            suggested_action="Let action imply coverage; reserve shots for emphasis.",
        ))

    # --- Scene turn heuristic (confidence-aware, never asserts absence) ---
    body = " ".join(b.text.lower() for b in blocks
                    if b.element_type in ("action", "dialogue"))
    has_turn_marker = any(re.search(rf"\b{re.escape(m)}\b", body) for m in TURN_MARKERS)
    if report.block_count >= 2 and not has_turn_marker:
        issues.append(ScreenplayDiagnosticIssue(
            id="scene_turn_unclear", label="Scene turn unclear", severity=SEV_WATCH,
            confidence=0.4,
            evidence="No contrast/turn markers detected (deterministic check only).",
            suggested_action="Check that the scene's value changes start-to-end.",
            logos_action_id="sp_check_scene_turn",
        ))

    # --- Character objective (PSYKE-aware, confidence scaled) ---
    if report.character_cue_count == 0 and a > 0:
        issues.append(ScreenplayDiagnosticIssue(
            id="no_active_character", label="No active speaking character", severity=SEV_INFO,
            confidence=0.4, evidence="Action present but no character cues.",
            suggested_action="Confirm a character drives the scene.",
        ))
    else:
        has_objective_lang = any(
            re.search(rf"\b{re.escape(m)}\b", body) for m in OBJECTIVE_MARKERS
        )
        known = [c for c in report.unique_characters if c in psyke_characters]
        has_psyke_goal = any(psyke_characters.get(c) for c in known)
        if not has_objective_lang and not has_psyke_goal:
            conf = 0.3 if not psyke_characters else 0.45
            issues.append(ScreenplayDiagnosticIssue(
                id="objective_unclear", label="Character objective unclear",
                severity=SEV_WATCH, confidence=conf,
                evidence=("No want/need language and no PSYKE objective for the "
                          "scene's characters."),
                suggested_action=("Clarify what the character wants here"
                                  + ("" if psyke_characters else
                                     "; consider adding an objective in PSYKE.")),
                logos_action_id="sp_clarify_objective",
            ))

    # --- Setup/payoff candidates (hooks only — cautious) ---
    for idx, b in enumerate(blocks):
        low = b.text.lower()
        if any(re.search(rf"\b{re.escape(m)}\b", low) for m in SETUP_MARKERS):
            issues.append(ScreenplayDiagnosticIssue(
                id=f"setup_candidate_{idx}", label="Possible setup", severity=SEV_INFO,
                confidence=0.35, target_block_index=idx,
                evidence="Promise/recall language — untracked setup candidate.",
                suggested_action="Track this setup's payoff (Phase 10D).",
                logos_action_id="sp_track_setup_payoff",
            ))

    # --- Format: block-sequence integrity (Phase 3) ---
    in_dialogue = False
    for idx, b in enumerate(blocks):
        et = b.element_type
        if et == "character":
            in_dialogue = True
            continue
        if et in ("scene_heading", "action", "transition", "shot", "note"):
            in_dialogue = False
            continue
        if et == "dialogue" and not in_dialogue:
            issues.append(ScreenplayDiagnosticIssue(
                id=f"dialogue_without_character_{idx}",
                label="Dialogue without a character cue", severity=SEV_WEAK,
                confidence=0.7, target_block_index=idx,
                evidence="A dialogue block has no preceding character cue.",
                suggested_action="Add the speaking character's cue above this line.",
            ))
        elif et == "parenthetical" and not in_dialogue:
            issues.append(ScreenplayDiagnosticIssue(
                id=f"parenthetical_without_dialogue_{idx}",
                label="Parenthetical out of place", severity=SEV_WATCH,
                confidence=0.65, target_block_index=idx,
                evidence="A parenthetical appears without a character/dialogue context.",
                suggested_action="Place parentheticals between a character cue and "
                                 "their dialogue.",
            ))

    # --- Format: empty blocks (Phase 3) ---
    empty_count = sum(1 for b in blocks if not (b.text or "").strip())
    if empty_count:
        issues.append(ScreenplayDiagnosticIssue(
            id="empty_blocks", label="Empty blocks present", severity=SEV_INFO,
            confidence=0.8,
            evidence=f"{empty_count} empty block(s) with no text.",
            suggested_action="Remove empty blocks or add their content.",
        ))

    # --- Continuity: characters not linked in PSYKE (Phase 3, warning-only) ---
    # Only when a PSYKE map exists to compare against — never assert "missing"
    # when the project simply has no Story Bible yet.
    if psyke_characters:
        for name in report.unique_characters:
            if name not in psyke_characters:
                issues.append(ScreenplayDiagnosticIssue(
                    id=f"character_not_in_psyke_{name}",
                    label=f"{name} not in Story Bible", severity=SEV_INFO,
                    confidence=0.4,
                    evidence=f"Character '{name}' has no PSYKE entry for continuity.",
                    suggested_action=f"Add {name} to PSYKE to track continuity.",
                ))

    # --- Beat-plan alignment (Phase 3): does the body reflect the plan? ---
    if beat_plan is not None:
        alignment = analyze_beat_plan_alignment(blocks, beat_plan)
        issues.extend(alignment)
        report.beat_plan_aligned = not any(
            i.severity_rank >= _SEV_RANK[SEV_WATCH] for i in alignment)

    # --- Extended metrics (Phase 3) ---
    report.parenthetical_block_count = counts.get("parenthetical", 0)
    report.empty_block_count = empty_count
    report.internal_state_phrase_count = internal_total
    dlg_words = [_words(b.text) for b in blocks if b.element_type == "dialogue"]
    report.longest_dialogue_words = max(dlg_words) if dlg_words else 0
    report.average_dialogue_words = (
        round(sum(dlg_words) / len(dlg_words), 1) if dlg_words else 0.0)
    report.action_dialogue_ratio = round(a / d, 2) if d else float(a)
    report.repeated_character_turns = _repeated_character_turns(blocks)

    # --- Strengths ---
    if report.economy_label == "balanced":
        report.strengths.append("Action/dialogue balance looks healthy.")
    if has_turn_marker:
        report.strengths.append("Contains a possible value turn.")
    if has_heading:
        report.strengths.append("Scene heading present.")

    report.issues = issues
    report.warnings = [i.evidence for i in issues if i.severity == SEV_WATCH]
    # Overall confidence: deterministic structure is reliable; semantic checks
    # are not — report a moderate, honest confidence.
    report.confidence = 0.7 if blocks else 1.0
    report.summary = _summary(report)
    return report


def _summary(report: ScreenplaySceneReport) -> str:
    top = report.top_issues(3)
    head = f"Scene economy: {report.economy_label or 'unknown'}."
    if not top:
        return head + " No notable screenplay issues detected."
    bullets = "; ".join(f"{i.label}" for i in top)
    return f"{head} Top issues: {bullets}."


def _repeated_character_turns(blocks: list[sb.ScreenplayBlock]) -> int:
    """Count back-to-back turns by the same speaker (a weak rhythm signal)."""
    last = None
    repeats = 0
    for b in blocks:
        if b.element_type != "character":
            continue
        name = re.sub(r"\(.*?\)", "", b.text).strip().upper()
        if name and name == last:
            repeats += 1
        last = name
    return repeats


# -- Beat-plan alignment (Phase 3) -------------------------------------------
# A transparent keyword-overlap heuristic: if NONE of a plan field's content
# words appear in the scene body, the body likely doesn't dramatize that intent.
# Low confidence on purpose — it flags for review, never asserts certainty.
_ALIGN_STOPWORDS = frozenset((
    "the", "and", "but", "for", "with", "that", "this", "from", "into", "onto",
    "their", "they", "them", "then", "than", "what", "when", "where", "which",
    "who", "whom", "will", "wont", "want", "wants", "have", "has", "had", "his",
    "her", "hers", "him", "she", "out", "are", "was", "were", "not", "your",
    "you", "about", "over", "under", "between", "scene", "character", "shift",
    "emotional", "objective", "conflict", "turning", "point", "goal", "needs",
))


def _content_words(text: str) -> set[str]:
    return {
        w for w in re.findall(r"[a-z']+", (text or "").lower())
        if len(w) > 3 and w not in _ALIGN_STOPWORDS
    }


def analyze_beat_plan_alignment(
    blocks: list[sb.ScreenplayBlock], beat_plan: Any,
) -> list[ScreenplayDiagnosticIssue]:
    """Deterministic alignment between a beat plan and the scene body.

    Read-only. Returns issues for planned conflict / turning point / emotional
    shift / objective (and individual visual beats) that the body doesn't appear
    to reflect. Empty plan or empty body -> no issues.
    """
    issues: list[ScreenplayDiagnosticIssue] = []
    if beat_plan is None or getattr(beat_plan, "is_empty", lambda: True)():
        return issues
    body = " ".join(
        b.text for b in blocks
        if b.element_type in ("action", "dialogue", "character",
                              "parenthetical", "scene_heading")
    )
    body_words = set(re.findall(r"[a-z']+", body.lower()))
    if not body_words:
        return issues

    def _check(value: str, fid: str, label: str, what: str, sev: str = SEV_WATCH,
               conf: float = 0.35) -> None:
        cw = _content_words(value or "")
        if cw and not (cw & body_words):
            issues.append(ScreenplayDiagnosticIssue(
                id=fid, label=label, severity=sev, confidence=conf,
                evidence=(f'The beat plan\'s {what} ("{(value or "").strip()[:60]}") '
                          "is not reflected in the scene body."),
                suggested_action=f"Make sure the scene dramatizes the planned {what}.",
                logos_action_id="sp_beat_plan_alignment",
            ))

    _check(getattr(beat_plan, "conflict", ""), "align_conflict_missing",
           "Planned conflict not evident", "conflict")
    _check(getattr(beat_plan, "turning_point", ""), "align_turn_missing",
           "Planned turning point not evident", "turning point")
    _check(getattr(beat_plan, "emotional_shift", ""), "align_emotional_shift_missing",
           "Planned emotional shift not evident", "emotional shift")
    _check(getattr(beat_plan, "objective", ""), "align_objective_missing",
           "Planned objective not evident", "objective")
    for i, beat in enumerate(getattr(beat_plan, "visual_beats", []) or []):
        cw = _content_words(beat)
        if cw and not (cw & body_words):
            issues.append(ScreenplayDiagnosticIssue(
                id=f"align_visual_beat_{i}", label="Planned visual beat not evident",
                severity=SEV_INFO, confidence=0.3,
                evidence=f'Planned beat ("{beat.strip()[:50]}") not found in the body.',
                suggested_action="Add or revise the scene to include this beat.",
                logos_action_id="sp_beat_plan_alignment",
            ))
    return issues


# -- Issue categorization (Phase 3, for readable grouped reports) ------------
_CATEGORY_PREFIXES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Format", ("missing_scene_heading", "only_notes", "dialogue_without_character",
                "parenthetical_without_dialogue", "empty_blocks", "transition_overuse",
                "shot_overuse")),
    ("Visual Writing", ("internal_action", "overwritten_action")),
    ("Dialogue Economy", ("dialogue_heavy", "no_dialogue", "long_dialogue",
                          "parenthetical_overuse", "single_voice")),
    ("Dramatic Function", ("scene_turn_unclear", "objective_unclear",
                           "no_active_character")),
    ("Beat Plan Alignment", ("align_",)),
    ("Continuity", ("character_not_in_psyke",)),
    ("Setup & Payoff", ("setup_candidate",)),
)


def issue_category(issue: ScreenplayDiagnosticIssue) -> str:
    """Map an issue to a human-readable Phase 3 category (for grouped output)."""
    for label, prefixes in _CATEGORY_PREFIXES:
        if any(issue.id.startswith(p) for p in prefixes):
            return label
    return "Other"


def group_issues_by_category(
    report: ScreenplaySceneReport,
) -> dict[str, list[ScreenplayDiagnosticIssue]]:
    """Group a report's issues by category, in canonical category order."""
    grouped: dict[str, list[ScreenplayDiagnosticIssue]] = {}
    for issue in report.issues:
        grouped.setdefault(issue_category(issue), []).append(issue)
    # Stable canonical ordering.
    order = [label for label, _ in _CATEGORY_PREFIXES] + ["Other"]
    return {k: grouped[k] for k in order if k in grouped}


# ---------------------------------------------------------------------------
# DB adapter (read-only): analyze a project's scenes
# ---------------------------------------------------------------------------

_OBJECTIVE_KEYS = (
    "goal", "objective", "want", "visual_objective", "scene_objective",
    "stage_objective", "motivation",
)


def _psyke_character_map(db, project_id: int) -> dict[str, bool]:
    """Uppercased PSYKE character name -> whether it has objective-ish data."""
    out: dict[str, bool] = {}
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
            has_goal = any(str(details.get(k, "")).strip() for k in _OBJECTIVE_KEYS)
        except Exception:
            has_goal = False
        out[name] = has_goal
    return out


def _scene_heading(scene) -> str:
    return (getattr(scene, "slugline", "") or getattr(scene, "title", "") or "").strip()


def analyze_project(db, project_id: int) -> list[ScreenplaySceneReport]:
    """Analyze every scene of a project (read-only). Tolerant of failures."""
    reports: list[ScreenplaySceneReport] = []
    try:
        scenes = db.get_all_scenes(project_id)
    except Exception:
        return reports
    psyke = _psyke_character_map(db, project_id)
    for scene in scenes:
        content = getattr(scene, "content", "") or ""
        blocks = sb.parse_screenplay_text(content, scene_id=scene.id)
        reports.append(analyze_scene(
            blocks, scene_id=scene.id, scene_heading=_scene_heading(scene),
            psyke_characters=psyke,
        ))
    return reports


def _status_for_fraction(frac: float):
    """Conservative status from the fraction of scenes flagged (never critical)."""
    from logosforge.logos.health import metric as M
    if frac <= 0.0:
        return M.STATUS_STABLE
    if frac <= 0.34:
        return M.STATUS_WATCH
    return M.STATUS_WEAK


def screenplay_health_metrics(db, project_id: int) -> list:
    """Build screenplay-mode :class:`NarrativeHealthMetric`s from deterministic
    diagnostics. Subtext / Cinematic Continuity are deferred (always *unknown*);
    no fake precision — categories with no analyzable data return *unknown*.
    """
    from logosforge.logos.health import metric as M

    reports = [r for r in analyze_project(db, project_id) if r.block_count > 0]
    n = len(reports)

    def metric(cat: str, ids: tuple[str, ...], note: str, confidence: float):
        if n == 0:
            return M.NarrativeHealthMetric(category=cat, status=M.STATUS_UNKNOWN,
                                           evidence="No screenplay scenes to analyze.")
        flagged = sum(
            1 for r in reports if any(
                any(i.id.startswith(p) for p in ids) for i in r.issues
            )
        )
        status = _status_for_fraction(flagged / n)
        if status == M.STATUS_STABLE:
            evidence = f"No {note} issues across {n} scene(s)."
        else:
            evidence = f"{flagged} of {n} scene(s) flagged for {note}."
        return M.NarrativeHealthMetric(category=cat, status=status,
                                       confidence=confidence, evidence=evidence)

    metrics = [
        metric(M.CAT_SCENE_ECONOMY,
               ("dialogue_heavy", "action_heavy", "no_dialogue", "only_notes"),
               "scene economy", 0.6),
        metric(M.CAT_VISUAL_ACTION, ("internal_action", "overwritten_action"),
               "visual action", 0.55),
        metric(M.CAT_DIALOGUE_ECONOMY,
               ("long_dialogue", "parenthetical_overuse", "single_voice"),
               "dialogue economy", 0.55),
        metric(M.CAT_SCENE_TURN, ("scene_turn_unclear",), "unclear scene turn", 0.4),
        metric(M.CAT_CHARACTER_OBJECTIVE,
               ("objective_unclear", "no_active_character"),
               "unclear character objective", 0.45),
    ]
    # -- Setup/Payoff + Motif (Phase 10D — deterministic tracker) --
    try:
        from logosforge.screenplay_setup_payoff import analyze_setup_payoff
        sp = analyze_setup_payoff(db, project_id)
    except Exception:
        sp = None
    if n == 0 or sp is None:
        metrics.append(M.NarrativeHealthMetric(
            category=M.CAT_SP_SETUP_PAYOFF, status=M.STATUS_UNKNOWN,
            evidence="No screenplay scenes to analyze."))
        metrics.append(M.NarrativeHealthMetric(
            category=M.CAT_MOTIF_RECURRENCE, status=M.STATUS_UNKNOWN,
            evidence="No screenplay scenes to analyze."))
    else:
        un = len(sp.unresolved_setups)
        sp_status = M.STATUS_WATCH if un else M.STATUS_STABLE
        metrics.append(M.NarrativeHealthMetric(
            category=M.CAT_SP_SETUP_PAYOFF, status=sp_status, confidence=0.45,
            evidence=(f"{un} unresolved setup candidate(s); "
                      f"{len(sp.possible_payoffs)} possible payoff(s).")))
        motif_status = M.STATUS_STABLE if sp.recurring_motifs else M.STATUS_UNKNOWN
        metrics.append(M.NarrativeHealthMetric(
            category=M.CAT_MOTIF_RECURRENCE, status=motif_status, confidence=0.4,
            evidence=(f"{len(sp.recurring_motifs)} recurring motif candidate(s)."
                      if sp.recurring_motifs else "No recurring motifs detected.")))

    # -- Subtext + On-the-Nose (Phase 10D — deterministic subtext) --
    try:
        from logosforge.screenplay_subtext import (
            analyze_subtext_project, S_ON_THE_NOSE_RISK,
        )
        sub_reports = analyze_subtext_project(db, project_id)
        sub_reports = [r for r in sub_reports if r.signals or True]
    except Exception:
        sub_reports = []
    sub_scenes = [r for r in (sub_reports or []) if r.scene_id is not None]
    if not sub_scenes or n == 0:
        for cat in (M.CAT_SUBTEXT, M.CAT_ON_THE_NOSE):
            metrics.append(M.NarrativeHealthMetric(
                category=cat, status=M.STATUS_UNKNOWN,
                evidence="No screenplay dialogue to analyze."))
    else:
        flagged_sub = sum(1 for r in sub_scenes if r.signals)
        metrics.append(M.NarrativeHealthMetric(
            category=M.CAT_SUBTEXT, status=_status_for_fraction(flagged_sub / len(sub_scenes)),
            confidence=0.45,
            evidence=f"{flagged_sub} of {len(sub_scenes)} scene(s) have subtext signals."))
        otn = sum(1 for r in sub_scenes
                  if any(s.signal_type == S_ON_THE_NOSE_RISK for s in r.signals))
        metrics.append(M.NarrativeHealthMetric(
            category=M.CAT_ON_THE_NOSE, status=_status_for_fraction(otn / len(sub_scenes)),
            confidence=0.45,
            evidence=f"{otn} of {len(sub_scenes)} scene(s) flagged on-the-nose."))

    # -- Confirmed-link coverage + candidate density (Phase 10E) --
    try:
        confirmed = db.get_story_links(project_id, status="confirmed")
        resolved = db.get_story_links(project_id, status="resolved")
    except Exception:
        confirmed, resolved = [], []
    n_confirmed = len(confirmed) + len(resolved)
    unresolved_cands = len(sp.unresolved_setups) if sp else 0
    # Confirmed links carry more weight: coverage is stable once any setup/payoff
    # is confirmed; unknown when there's nothing tracked yet.
    if n_confirmed > 0:
        cov_status, cov_ev = M.STATUS_STABLE, f"{n_confirmed} confirmed story link(s)."
    elif unresolved_cands > 0:
        cov_status = M.STATUS_WATCH
        cov_ev = f"{unresolved_cands} candidate(s) but none confirmed yet."
    else:
        cov_status, cov_ev = M.STATUS_UNKNOWN, "No story links tracked."
    metrics.append(M.NarrativeHealthMetric(
        category=M.CAT_LINK_COVERAGE, status=cov_status, confidence=0.45,
        evidence=cov_ev))
    # Candidate density: many unresolved candidates -> watch (a warning, not fail).
    dens_status = M.STATUS_WATCH if unresolved_cands >= 3 else (
        M.STATUS_STABLE if (sp and (sp.candidates or n_confirmed)) else M.STATUS_UNKNOWN)
    metrics.append(M.NarrativeHealthMetric(
        category=M.CAT_CANDIDATE_DENSITY, status=dens_status, confidence=0.4,
        evidence=f"{unresolved_cands} unresolved candidate(s)."))

    # -- Export / format readiness (Phase 10F — format health, NOT narrative) --
    # Capped at WATCH so a formatting issue never flips the narrative overall to
    # weak/critical: format problems are distinct from craft problems.
    try:
        from logosforge.screenplay_export_validation import (
            validate_screenplay_export,
        )
        from logosforge.screenplay_render import get_export_prefs, get_title_page
        prefs = get_export_prefs(db, project_id)
        val = validate_screenplay_export(
            db, project_id, target_format=prefs.get("export_target", "fountain"),
            prefs=prefs)
        title = (get_title_page(db, project_id).get("title") or "").strip()
    except Exception:
        val, title = None, ""

    if n == 0 or val is None:
        for cat in (M.CAT_EXPORT_READINESS, M.CAT_TITLE_PAGE,
                    M.CAT_SCENE_HEADING_INTEGRITY, M.CAT_DIALOGUE_FORMAT):
            metrics.append(M.NarrativeHealthMetric(
                category=cat, status=M.STATUS_UNKNOWN,
                evidence="No screenplay scenes to assess."))
    else:
        readiness = M.STATUS_STABLE if (val.is_export_safe and not val.warnings) else M.STATUS_WATCH
        metrics.append(M.NarrativeHealthMetric(
            category=M.CAT_EXPORT_READINESS, status=readiness, confidence=0.5,
            evidence=val.summary))
        metrics.append(M.NarrativeHealthMetric(
            category=M.CAT_TITLE_PAGE,
            status=M.STATUS_STABLE if title else M.STATUS_WATCH, confidence=0.5,
            evidence=("Title page set." if title else "No title page set.")))
        heading_warn = any("scene heading" in w for w in val.warnings)
        metrics.append(M.NarrativeHealthMetric(
            category=M.CAT_SCENE_HEADING_INTEGRITY,
            status=M.STATUS_WATCH if heading_warn else M.STATUS_STABLE, confidence=0.5,
            evidence=next((w for w in val.warnings if "scene heading" in w),
                         "Scene headings present.")))
        dlg_warn = any(("dialogue block" in w or "parenthetical" in w)
                       for w in val.warnings)
        metrics.append(M.NarrativeHealthMetric(
            category=M.CAT_DIALOGUE_FORMAT,
            status=M.STATUS_WATCH if dlg_warn else M.STATUS_STABLE, confidence=0.5,
            evidence=next((w for w in val.warnings
                           if "dialogue block" in w or "parenthetical" in w),
                          "Dialogue formatting looks consistent.")))

    # -- Fountain readiness (Phase 10G — format health, capped at WATCH) --
    try:
        from logosforge.export import export_screenplay_fountain_result
        from logosforge.screenplay_fountain import validate_fountain_export
        res = export_screenplay_fountain_result(db, project_id)
        fval = validate_fountain_export(res.text)
    except Exception:
        res, fval = None, None
    if n == 0 or fval is None:
        for cat in (M.CAT_FOUNTAIN_READINESS, M.CAT_UNSUPPORTED_ELEMENTS):
            metrics.append(M.NarrativeHealthMetric(
                category=cat, status=M.STATUS_UNKNOWN,
                evidence="No screenplay scenes to assess."))
    else:
        f_status = M.STATUS_STABLE if (fval.is_valid and not fval.warnings) else M.STATUS_WATCH
        metrics.append(M.NarrativeHealthMetric(
            category=M.CAT_FOUNTAIN_READINESS, status=f_status, confidence=0.5,
            evidence=fval.summary))
        # Forcing syntax indicates an element that didn't map cleanly; omitted
        # notes are an intentional pref, not an unsupported element.
        unsupported = [w for w in (res.warnings if res else [])
                       if "forced" in w.lower()]
        metrics.append(M.NarrativeHealthMetric(
            category=M.CAT_UNSUPPORTED_ELEMENTS,
            status=M.STATUS_WATCH if unsupported else M.STATUS_STABLE, confidence=0.45,
            evidence=(unsupported[0] if unsupported
                      else "All elements map cleanly to Fountain.")))

    # -- Professional output readiness (Phase 10H — format health, capped WATCH) --
    try:
        from logosforge.screenplay_output_validation import (
            validate_professional_output,
        )
        oval = validate_professional_output(db, project_id, target_format="docx")
    except Exception:
        oval = None
    if n == 0 or oval is None:
        metrics.append(M.NarrativeHealthMetric(
            category=M.CAT_PRO_OUTPUT_READINESS, status=M.STATUS_UNKNOWN,
            evidence="No screenplay scenes to assess."))
    else:
        o_status = (M.STATUS_STABLE if (oval.is_export_safe and not oval.warnings)
                    else M.STATUS_WATCH)
        metrics.append(M.NarrativeHealthMetric(
            category=M.CAT_PRO_OUTPUT_READINESS, status=o_status, confidence=0.5,
            evidence=(f"Formats: {', '.join(oval.available_formats)}. "
                      + (oval.warnings[0] if oval.warnings else "DOCX export ready."))))
    # FDX is always experimental/unverified -> a standing watch (never critical).
    metrics.append(M.NarrativeHealthMetric(
        category=M.CAT_FDX_COMPAT_RISK,
        status=(M.STATUS_WATCH if n else M.STATUS_UNKNOWN), confidence=0.4,
        evidence="FDX export is experimental and unverified — prefer .fountain."))

    # -- Production draft (Phase 10J — only when production mode is active) --
    # Capped at WATCH so a production-format issue never flips narrative overall;
    # the production validator surfaces the real blocking errors separately.
    try:
        draft = db.get_active_production_draft(project_id)
    except Exception:
        draft = None
    if draft is not None:
        from logosforge.screenplay_production import (
            validate_scene_numbers, validate_production_draft,
        )
        prep = validate_production_draft(db, project_id)
        metrics.append(M.NarrativeHealthMetric(
            category=M.CAT_PRODUCTION_READINESS,
            status=(M.STATUS_WATCH if prep.blocking_errors else M.STATUS_STABLE),
            confidence=0.5, evidence=f"Readiness: {prep.readiness_level}."))
        if draft.scene_numbering_enabled:
            problems = validate_scene_numbers(db, project_id)
            metrics.append(M.NarrativeHealthMetric(
                category=M.CAT_SCENE_NUMBERING,
                status=(M.STATUS_WATCH if problems else M.STATUS_STABLE),
                confidence=0.5,
                evidence=(problems[0] if problems else "Scene numbers consistent.")))
        try:
            revs = db.get_revision_sets(draft.id)
        except Exception:
            revs = []
        metrics.append(M.NarrativeHealthMetric(
            category=M.CAT_REVISION_SET,
            status=(M.STATUS_STABLE if revs else M.STATUS_UNKNOWN), confidence=0.4,
            evidence=(f"{len(revs)} revision set(s)." if revs
                      else "No revision sets yet.")))

    # -- Revision intelligence (Phase 10K — only when a saved report exists) --
    # Diagnostic, capped at WATCH; based on the latest persisted impact report.
    try:
        report = db.get_latest_revision_impact_report(project_id)
    except Exception:
        report = None
    if report is not None:
        high = report.impact_level in ("high", "critical")
        metrics.append(M.NarrativeHealthMetric(
            category=M.CAT_REVISION_CAUSALITY,
            status=(M.STATUS_WATCH if high else M.STATUS_STABLE), confidence=0.4,
            evidence=f"Latest revision impact: {report.impact_level} "
                     f"({report.confidence})."))
        try:
            items = db.get_revision_impact_items(report.id)
        except Exception:
            items = []
        cont = [i for i in items if i.impact_kind == "continuity_risk"
                and i.confidence != "unknown"]
        metrics.append(M.NarrativeHealthMetric(
            category=M.CAT_CONTINUITY_REVISION,
            status=(M.STATUS_WATCH if cont else M.STATUS_STABLE), confidence=0.35,
            evidence=(cont[0].label if cont else "No flagged continuity revision risk.")))

    # Cinematic Continuity stays deferred (needs semantics / future phase).
    metrics.append(M.NarrativeHealthMetric(
        category=M.CAT_CINEMATIC_CONTINUITY, status=M.STATUS_UNKNOWN,
        evidence="Deferred — not deterministically assessable yet."))
    return metrics


def analyze_scene_by_id(
    db, project_id: int, scene_id: int, *, include_beat_plan: bool = True,
) -> ScreenplaySceneReport:
    """Analyze a single scene by id (read-only).

    When ``include_beat_plan`` is set (default) and a Phase 2 beat plan exists for
    the scene, the report adds beat-plan alignment checks. Read-only throughout.
    """
    scene = None
    try:
        scene = db.get_scene_by_id(scene_id)
    except Exception:
        scene = None
    if scene is None:
        return ScreenplaySceneReport(scene_id=scene_id, summary="Scene not found.")
    blocks = sb.parse_screenplay_text(getattr(scene, "content", "") or "", scene_id=scene_id)
    beat_plan = None
    if include_beat_plan:
        try:
            from logosforge.screenplay_pipeline import get_beat_plan
            beat_plan = get_beat_plan(db, project_id, scene_id)
        except Exception:
            beat_plan = None
    return analyze_scene(
        blocks, scene_id=scene_id, scene_heading=_scene_heading(scene),
        psyke_characters=_psyke_character_map(db, project_id),
        beat_plan=beat_plan,
    )
