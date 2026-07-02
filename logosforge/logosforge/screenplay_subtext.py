"""Deterministic screenplay subtext tracking (Phase 10D).

Flags dialogue that may be too on-the-nose, expositional, or lacking subtext —
cautiously and deterministically. No LLM, no DB writes, no fake literary
certainty: every signal is a *suggestion* with confidence, never a verdict.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from logosforge import screenplay_blocks as sb

# -- Signal types -------------------------------------------------------------
S_CONTRADICTION = "contradiction"        # reserved (needs semantics) — not emitted
S_AVOIDANCE = "avoidance"
S_INDIRECT_ANSWER = "indirect_answer"
S_POWER_SHIFT = "power_shift"            # reserved — not emitted
S_OBJECTIVE_GAP = "objective_gap"
S_EMOTIONAL_LEAK = "emotional_leak"
S_EXPOSITION_RISK = "exposition_risk"
S_ON_THE_NOSE_RISK = "on_the_nose_risk"

LONG_DIALOGUE_WORDS = 50

# Direct-emotion phrases — saying the feeling instead of playing it.
EMOTION_PHRASES = (
    "i feel", "i'm so", "i am so", "i'm really", "i love you", "i hate you",
    "i'm angry", "i'm sad", "i'm scared", "i'm afraid", "i'm happy", "i'm hurt",
    "i'm furious", "i'm terrified", "i'm jealous", "i'm in love", "i'm lonely",
)
# Evasion / denial patterns — surface that hides undertext.
AVOIDANCE_PHRASES = (
    "i'm fine", "it's fine", "it's nothing", "nothing's wrong", "whatever",
    "doesn't matter", "forget it", "never mind", "don't worry about it",
    "i don't want to talk about it",
)
# Exposition markers — telling the audience rather than dramatizing.
EXPOSITION_PHRASES = (
    "as you know", "as you well know", "remember when", "the reason is",
    "years ago", "ever since", "let me explain", "you see", "the truth is",
    "what you don't know is", "i'll tell you what happened",
)
# Want/objective markers (shared spirit with diagnostics).
OBJECTIVE_MARKERS = (
    "want", "wants", "need", "needs", "has to", "have to", "must",
    "trying to", "going to", "i'll", "let's",
)


def _norm(t: str) -> str:
    return (t or "").lower()


def _words(t: str) -> int:
    return len(re.findall(r"\S+", t or ""))


@dataclass
class SubtextSignal:
    scene_id: int | None
    block_index: int | None
    character_name: str | None
    signal_type: str
    evidence: str = ""
    confidence: float = 0.0
    suggested_action: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "scene_id": self.scene_id,
            "block_index": self.block_index,
            "character_name": self.character_name,
            "signal_type": self.signal_type,
            "evidence": self.evidence,
            "confidence": round(self.confidence, 2),
            "suggested_action": self.suggested_action,
        }


@dataclass
class SubtextReport:
    scene_id: int | None = None
    characters: list[str] = field(default_factory=list)
    spoken_surface: str = ""
    possible_undertext: str = ""
    signals: list[SubtextSignal] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    summary: str = ""

    def top_signals(self, n: int = 3) -> list[SubtextSignal]:
        return sorted(self.signals, key=lambda s: s.confidence, reverse=True)[:n]

    def to_dict(self) -> dict[str, Any]:
        return {
            "scene_id": self.scene_id,
            "characters": list(self.characters),
            "spoken_surface": self.spoken_surface,
            "possible_undertext": self.possible_undertext,
            "signals": [s.to_dict() for s in self.signals],
            "warnings": list(self.warnings),
            "summary": self.summary,
        }


def analyze_subtext_scene(
    blocks: list[sb.ScreenplayBlock],
    *,
    scene_id: int | None = None,
    psyke_objectives: dict[str, bool] | None = None,
) -> SubtextReport:
    """Deterministic subtext analysis for one scene's blocks.

    *psyke_objectives* maps uppercased character name -> has-objective-data; used
    only to scale the objective-gap confidence (missing data lowers it).
    """
    report = SubtextReport(scene_id=scene_id)
    psyke_objectives = psyke_objectives or {}
    report.characters = sb.character_cues(blocks)

    signals: list[SubtextSignal] = []
    # Track the current speaker for dialogue blocks.
    current_speaker: str | None = None
    paren = 0
    dlg_count = 0
    prev_was_question = False

    for idx, b in enumerate(blocks):
        et = b.element_type
        if et == "character":
            current_speaker = re.sub(r"\(.*?\)", "", b.text).strip().upper() or None
            continue
        if et == "parenthetical":
            paren += 1
            continue
        if et != "dialogue":
            # An action beat resets the "no interruption" tracking.
            if et == "action":
                prev_was_question = False
            continue

        dlg_count += 1
        low = _norm(b.text)

        # On-the-nose / stated emotion.
        emo = next((p for p in EMOTION_PHRASES if p in low), None)
        if emo:
            signals.append(SubtextSignal(
                scene_id, idx, current_speaker, S_ON_THE_NOSE_RISK,
                evidence=f"Line states the emotion directly (“{emo}…”).",
                confidence=0.55,
                suggested_action="This may be too on-the-nose; consider moving "
                                 "the intention into behavior.",
            ))
        # Avoidance / denial.
        av = next((p for p in AVOIDANCE_PHRASES if p in low), None)
        if av:
            signals.append(SubtextSignal(
                scene_id, idx, current_speaker, S_AVOIDANCE,
                evidence=f"Evasive/denial phrase (“{av}”).", confidence=0.45,
                suggested_action="Possible avoidance — check the undertext beneath it.",
            ))
        # Exposition risk (markers, stronger if the block is long).
        exp = next((p for p in EXPOSITION_PHRASES if p in low), None)
        if exp:
            conf = 0.6 if _words(b.text) >= LONG_DIALOGUE_WORDS else 0.5
            signals.append(SubtextSignal(
                scene_id, idx, current_speaker, S_EXPOSITION_RISK,
                evidence=f"Exposition marker (“{exp}”).", confidence=conf,
                suggested_action="This may be exposition; dramatize it instead.",
            ))
        # Indirect answer: previous dialogue was a question, this one dodges.
        if prev_was_question and av:
            signals.append(SubtextSignal(
                scene_id, idx, current_speaker, S_INDIRECT_ANSWER,
                evidence="A question is answered evasively.", confidence=0.45,
                suggested_action="Indirect answer — likely intentional subtext; confirm.",
            ))
        prev_was_question = low.strip().endswith("?")

    # Parenthetical over-explanation.
    if dlg_count > 0 and paren / dlg_count >= 0.4:
        signals.append(SubtextSignal(
            scene_id, None, None, S_ON_THE_NOSE_RISK,
            evidence=f"{paren} parenthetical(s) across {dlg_count} dialogue block(s).",
            confidence=0.5,
            suggested_action="Parentheticals over-explain emotion; trust the subtext.",
        ))

    # Objective gap: characters speak but show no want; PSYKE lowers/raises conf.
    body = " ".join(_norm(b.text) for b in blocks if b.element_type == "dialogue")
    has_objective_lang = any(
        re.search(rf"\b{re.escape(m)}\b", body) for m in OBJECTIVE_MARKERS
    )
    if dlg_count > 0 and not has_objective_lang:
        known = [c for c in report.characters if c in psyke_objectives]
        has_goal = any(psyke_objectives.get(c) for c in known)
        if not has_goal:
            conf = 0.45 if psyke_objectives else 0.3
            who = report.characters[0] if report.characters else None
            signals.append(SubtextSignal(
                scene_id, None, who, S_OBJECTIVE_GAP,
                evidence="Dialogue present but no visible want/objective.",
                confidence=conf,
                suggested_action=("Clarify what the character wants beneath the line"
                                  + ("" if psyke_objectives
                                     else "; consider adding an objective in PSYKE.")),
            ))

    report.signals = signals
    report.warnings = [s.evidence for s in signals if s.confidence >= 0.5]
    report.spoken_surface = "; ".join(
        b.text.strip() for b in blocks if b.element_type == "dialogue"
    )[:300]
    report.summary = _summary(report)
    return report


def _summary(report: SubtextReport) -> str:
    if not report.signals:
        return "No deterministic subtext risks detected (heuristic check)."
    top = report.top_signals(3)
    labels = {
        S_ON_THE_NOSE_RISK: "on-the-nose risk",
        S_EXPOSITION_RISK: "exposition risk",
        S_AVOIDANCE: "avoidance",
        S_INDIRECT_ANSWER: "indirect answer",
        S_OBJECTIVE_GAP: "objective gap",
        S_EMOTIONAL_LEAK: "emotional leak",
    }
    parts = "; ".join(labels.get(s.signal_type, s.signal_type) for s in top)
    return f"Subtext status: watch. Top signals: {parts}."


# ---------------------------------------------------------------------------
# DB adapter (read-only)
# ---------------------------------------------------------------------------

_OBJECTIVE_KEYS = (
    "goal", "objective", "want", "visual_objective", "scene_objective",
    "stage_objective", "motivation", "hidden_agenda", "private_want",
)


def _psyke_objective_map(db, project_id: int) -> dict[str, bool]:
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


def analyze_subtext_by_id(db, project_id: int, scene_id: int) -> SubtextReport:
    scene = None
    try:
        scene = db.get_scene_by_id(scene_id)
    except Exception:
        scene = None
    if scene is None:
        return SubtextReport(scene_id=scene_id, summary="Scene not found.")
    blocks = sb.parse_screenplay_text(getattr(scene, "content", "") or "",
                                      scene_id=scene_id)
    return analyze_subtext_scene(
        blocks, scene_id=scene_id,
        psyke_objectives=_psyke_objective_map(db, project_id),
    )


def analyze_subtext_project(db, project_id: int) -> list[SubtextReport]:
    reports: list[SubtextReport] = []
    try:
        scenes = db.get_all_scenes(project_id)
    except Exception:
        return reports
    psyke = _psyke_objective_map(db, project_id)
    for scene in scenes:
        blocks = sb.parse_screenplay_text(getattr(scene, "content", "") or "",
                                          scene_id=scene.id)
        reports.append(analyze_subtext_scene(
            blocks, scene_id=scene.id, psyke_objectives=psyke,
        ))
    return reports
