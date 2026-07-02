"""Deterministic Series / teleplay intelligence (Phase 3).

Evaluates a Series *Scene* (its ordered teleplay blocks) and a Series *Episode*
(a Chapter's ordered scenes) with conservative, rule-based heuristics — format /
block order, scene function, episode structure, serialized / season-arc
alignment, dialogue / action balance, plan alignment, and Timeline / PSYKE
continuity. Mirrors ``stage_script_diagnostics`` / ``screenplay_diagnostics``.

This is a WRITING/craft checker: it reports clarity and structure signals only.
No autonomous rewriting, no auto-apply, no LLM, no DB writes, no Qt, and no image
generation of any kind. Acts/Chapters are scene-derived labels (Series shows a
Chapter as an Episode); nothing here changes storage.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from logosforge import series_blocks as sbk

# Severity (shared scale with the other diagnostics).
SEV_INFO = "info"
SEV_WATCH = "watch"
SEV_WEAK = "weak"
SEV_CRITICAL = "critical"
_SEV_RANK = {SEV_INFO: 0, SEV_WATCH: 1, SEV_WEAK: 2, SEV_CRITICAL: 3}

# Categories (canonical render order).
CAT_FORMAT = "Format / Block Order"
CAT_FUNCTION = "Scene Function"
CAT_EPISODE = "Episode Structure"
CAT_SERIAL = "Serialized / Season Arc"
CAT_BALANCE = "Dialogue / Action Balance"
CAT_ALIGNMENT = "Plan Alignment"
CAT_CONTINUITY = "Continuity / PSYKE"
_CATEGORY_ORDER = (CAT_FORMAT, CAT_FUNCTION, CAT_EPISODE, CAT_SERIAL, CAT_BALANCE,
                   CAT_ALIGNMENT, CAT_CONTINUITY)

# Documented thresholds (conservative).
CONSECUTIVE_DIALOGUE_HIGH = 6     # dialogue blocks in a row with no action
LONG_MONOLOGUE_WORDS = 120        # one dialogue block this long reads as a monologue
DIALOGUE_HEAVY_RATIO = 4.0        # dialogue blocks per action block
EXPOSITION_DIALOGUE_WORDS = 60    # avg dialogue length suggesting exposition-heavy
UNRELATED_SUMMARY_WORDS = 6       # summary needs this many content words to compare

OBJECTIVE_MARKERS = (
    "want", "wants", "need", "needs", "must", "trying to", "going to",
    "has to", "have to", "to find", "to stop", "to save", "to escape", "wants to",
)
TURN_MARKERS = (
    "but", "however", "suddenly", "then", "finally", "until", "instead",
    "no longer", "everything changes", "reveal", "turns", "realiz",
)


def _words(text: str) -> int:
    return len(re.findall(r"\S+", text or ""))


def _content_words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z']+", (text or "").lower()) if len(w) > 3}


def _has_any(low: str, markers) -> bool:
    return any(re.search(rf"\b{re.escape(m)}\b", low) for m in markers)


def _is_empty(obj: Any) -> bool:
    if obj is None:
        return True
    try:
        return bool(obj.is_empty())
    except Exception:
        return False


# ===========================================================================
# Metrics
# ===========================================================================


@dataclass
class SeriesMetrics:
    total_blocks: int = 0
    scene_heading_count: int = 0
    action_count: int = 0
    character_count: int = 0
    dialogue_count: int = 0
    parenthetical_count: int = 0
    transition_count: int = 0
    shot_count: int = 0
    act_break_count: int = 0
    teaser_count: int = 0
    tag_count: int = 0
    empty_block_count: int = 0
    avg_dialogue_words: float = 0.0
    longest_dialogue_words: int = 0
    dialogue_action_ratio: float = 0.0
    max_consecutive_dialogue: int = 0
    estimated_word_count: int = 0
    visible_action: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_blocks": self.total_blocks,
            "scene_heading_count": self.scene_heading_count,
            "action_count": self.action_count,
            "character_count": self.character_count,
            "dialogue_count": self.dialogue_count,
            "parenthetical_count": self.parenthetical_count,
            "transition_count": self.transition_count,
            "shot_count": self.shot_count,
            "act_break_count": self.act_break_count,
            "teaser_count": self.teaser_count, "tag_count": self.tag_count,
            "empty_block_count": self.empty_block_count,
            "avg_dialogue_words": self.avg_dialogue_words,
            "longest_dialogue_words": self.longest_dialogue_words,
            "dialogue_action_ratio": self.dialogue_action_ratio,
            "max_consecutive_dialogue": self.max_consecutive_dialogue,
            "estimated_word_count": self.estimated_word_count,
            "visible_action": self.visible_action,
        }


def compute_metrics(script: sbk.SeriesScript) -> SeriesMetrics:
    """Transparent, rule-based metrics for one Series scene. No LLM."""
    m = SeriesMetrics()
    blocks = script.blocks if script else []
    m.total_blocks = len(blocks)
    dialogue_lengths: list[int] = []
    consecutive = 0
    for b in blocks:
        bt = b.block_type
        m.estimated_word_count += _words(b.text)
        if b.is_empty() and bt != sbk.BT_CHARACTER:
            m.empty_block_count += 1
        if bt == sbk.BT_SCENE_HEADING:
            m.scene_heading_count += 1
        elif bt == sbk.BT_ACTION:
            m.action_count += 1
        elif bt == sbk.BT_CHARACTER:
            m.character_count += 1
        elif bt == sbk.BT_DIALOGUE:
            m.dialogue_count += 1
            dialogue_lengths.append(_words(b.text))
        elif bt == sbk.BT_PARENTHETICAL:
            m.parenthetical_count += 1
        elif bt == sbk.BT_TRANSITION:
            m.transition_count += 1
        elif bt == sbk.BT_SHOT:
            m.shot_count += 1
        elif bt == sbk.BT_ACT_BREAK:
            m.act_break_count += 1
        elif bt == sbk.BT_TEASER:
            m.teaser_count += 1
        elif bt == sbk.BT_TAG:
            m.tag_count += 1
        # Consecutive dialogue-only run (parentheticals don't break the run).
        if bt == sbk.BT_DIALOGUE:
            consecutive += 1
            m.max_consecutive_dialogue = max(m.max_consecutive_dialogue, consecutive)
        elif bt != sbk.BT_PARENTHETICAL and bt != sbk.BT_CHARACTER:
            consecutive = 0
    if dialogue_lengths:
        m.avg_dialogue_words = round(sum(dialogue_lengths) / len(dialogue_lengths), 1)
        m.longest_dialogue_words = max(dialogue_lengths)
    m.dialogue_action_ratio = round(m.dialogue_count / max(m.action_count, 1), 1)
    m.visible_action = any(b.block_type in (sbk.BT_ACTION, sbk.BT_SCENE_HEADING,
                                            sbk.BT_SHOT) for b in blocks)
    return m


# ===========================================================================
# Issues / reports
# ===========================================================================


@dataclass
class SeriesIssue:
    id: str
    label: str
    category: str
    severity: str = SEV_INFO
    evidence: str = ""
    block_number: int | None = None
    thread: str = ""        # affected A/B/C story thread, when known
    suggested_action: str = ""

    @property
    def severity_rank(self) -> int:
        return _SEV_RANK.get(self.severity, 0)

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "label": self.label, "category": self.category,
                "severity": self.severity, "evidence": self.evidence,
                "block_number": self.block_number, "thread": self.thread,
                "suggested_action": self.suggested_action}


@dataclass
class SeriesSceneReport:
    scene_id: int | None = None
    metrics: SeriesMetrics = field(default_factory=SeriesMetrics)
    issues: list[SeriesIssue] = field(default_factory=list)
    strengths: list[str] = field(default_factory=list)
    confidence: float = 0.0
    summary: str = ""

    def top_issues(self, n: int = 5) -> list[SeriesIssue]:
        return sorted(self.issues, key=lambda i: (i.severity_rank, i.label),
                      reverse=True)[:n]

    def issues_in(self, *categories: str) -> list[SeriesIssue]:
        cats = set(categories)
        return [i for i in self.issues if i.category in cats]

    def to_dict(self) -> dict[str, Any]:
        return {"scene_id": self.scene_id, "metrics": self.metrics.to_dict(),
                "issues": [i.to_dict() for i in self.issues],
                "strengths": list(self.strengths),
                "confidence": round(self.confidence, 2), "summary": self.summary}


def group_issues_by_category(report) -> dict[str, list[SeriesIssue]]:
    grouped: dict[str, list[SeriesIssue]] = {}
    for issue in report.issues:
        grouped.setdefault(issue.category, []).append(issue)
    return {k: grouped[k] for k in _CATEGORY_ORDER if k in grouped}


# ===========================================================================
# Scene analysis (pure)
# ===========================================================================


def analyze_scene(
    script: sbk.SeriesScript, *, scene_id: int | None = None,
    outline_summary: str = "", episode_plan: Any | None = None,
    season_plan: Any | None = None, psyke_characters: dict[str, bool] | None = None,
) -> SeriesSceneReport:
    """Deterministically analyze one Series scene's blocks."""
    report = SeriesSceneReport(scene_id=scene_id)
    psyke_characters = psyke_characters or {}
    issues: list[SeriesIssue] = []
    blocks = script.blocks if script else []
    report.metrics = compute_metrics(script)
    m = report.metrics

    if not blocks:
        report.summary = "Empty scene — no Series blocks to analyze."
        report.confidence = 1.0
        if outline_summary.strip() or not _is_empty(episode_plan):
            issues.append(SeriesIssue(
                id="no_body", label="No Series script yet", category=CAT_FORMAT,
                severity=SEV_WATCH,
                evidence="The scene has a summary/plan but no Series blocks.",
                suggested_action="Draft the scene from the Episode plan, or add blocks."))
        report.issues = issues
        return report

    body = sbk.serialize_series_script(script)
    body_words = _content_words(body)
    low_body = body.lower()
    first_body = next((i for i, b in enumerate(blocks)
                       if b.block_type in (sbk.BT_SCENE_HEADING, sbk.BT_ACTION)), None)
    has_speaker = False

    # -- A. Format / block order (per-block) --
    for i, b in enumerate(blocks):
        bt = b.block_type
        n = i + 1
        if bt not in sbk._VALID:
            issues.append(SeriesIssue(
                id=f"unknown_type_{n}", label="Unknown block type",
                category=CAT_FORMAT, severity=SEV_WATCH, block_number=n,
                evidence=f"Block {n} has an unrecognized type ({bt!r}).",
                suggested_action="Convert it to a known block type."))
        if b.is_empty() and bt != sbk.BT_CHARACTER:
            issues.append(SeriesIssue(
                id=f"empty_block_{n}", label="Empty block", category=CAT_FORMAT,
                severity=SEV_WATCH, block_number=n, evidence=f"Block {n} is empty.",
                suggested_action="Fill or remove the block."))
        if bt == sbk.BT_CHARACTER:
            has_speaker = True
            nxt = next((nb for nb in blocks[i + 1:]
                        if nb.block_type != sbk.BT_PARENTHETICAL), None)
            if nxt is None or nxt.block_type != sbk.BT_DIALOGUE:
                issues.append(SeriesIssue(
                    id=f"character_no_dialogue_{n}",
                    label="Character cue without dialogue", category=CAT_FORMAT,
                    severity=SEV_WATCH, block_number=n,
                    evidence=f"{(b.text or 'Character').strip().upper()} has a cue "
                             "but no following dialogue.",
                    suggested_action="Add the character's line, or remove the cue."))
        elif bt == sbk.BT_DIALOGUE:
            if not has_speaker:
                issues.append(SeriesIssue(
                    id=f"dialogue_no_character_{n}",
                    label="Dialogue without a character cue", category=CAT_FORMAT,
                    severity=SEV_WATCH, block_number=n,
                    evidence=f"Block {n} is dialogue with no preceding character.",
                    suggested_action="Add a CHARACTER cue before the line."))
            if _words(b.text) >= LONG_MONOLOGUE_WORDS:
                issues.append(SeriesIssue(
                    id=f"long_monologue_{n}", label="Long monologue",
                    category=CAT_BALANCE, severity=SEV_INFO, block_number=n,
                    evidence=f"{_words(b.text)} words in one speech.",
                    suggested_action="Break it up with action or another voice."))
        elif bt == sbk.BT_PARENTHETICAL:
            if not has_speaker:
                issues.append(SeriesIssue(
                    id=f"parenthetical_misuse_{n}",
                    label="Parenthetical not attached to a character",
                    category=CAT_FORMAT, severity=SEV_INFO, block_number=n,
                    evidence=f"Block {n} is a parenthetical with no character/dialogue.",
                    suggested_action="Place it under a CHARACTER cue."))
        elif bt == sbk.BT_ACT_BREAK:
            if i == 0:
                issues.append(SeriesIssue(
                    id=f"act_break_at_start_{n}", label="Act Break at the start",
                    category=CAT_FORMAT, severity=SEV_WATCH, block_number=n,
                    evidence="An Act Break marker opens the scene.",
                    suggested_action="Move the Act Break to a real act-out moment."))
            has_speaker = False
        elif bt == sbk.BT_TEASER:
            if first_body is not None and i > first_body:
                issues.append(SeriesIssue(
                    id=f"teaser_misplaced_{n}",
                    label="Cold Open / Teaser placed oddly", category=CAT_FORMAT,
                    severity=SEV_INFO, block_number=n,
                    evidence="A Cold Open / Teaser marker appears after the scene "
                             "has already started.",
                    suggested_action="A teaser belongs before the main scene body."))
            has_speaker = False
        elif bt == sbk.BT_TAG:
            if first_body is None or i < first_body:
                issues.append(SeriesIssue(
                    id=f"tag_misplaced_{n}", label="Tag placed oddly",
                    category=CAT_FORMAT, severity=SEV_INFO, block_number=n,
                    evidence="A Tag marker appears before the main scene body.",
                    suggested_action="A tag / button belongs after the scene body."))
            has_speaker = False
        else:
            has_speaker = False

    if m.scene_heading_count == 0:
        issues.append(SeriesIssue(
            id="no_scene_heading", label="No scene heading", category=CAT_FORMAT,
            severity=SEV_WATCH, evidence="The scene has no INT./EXT. scene heading.",
            suggested_action="Add a scene heading so the location/time is clear."))

    # -- B. Scene function --
    if not _has_any(low_body, OBJECTIVE_MARKERS) and not outline_summary.strip():
        issues.append(SeriesIssue(
            id="objective_unclear", label="Scene objective unclear",
            category=CAT_FUNCTION, severity=SEV_WATCH,
            evidence="No want/need language and no Outline summary.",
            suggested_action="Clarify what the scene is for."))
    if m.total_blocks >= 2 and not _has_any(low_body, TURN_MARKERS):
        issues.append(SeriesIssue(
            id="turn_unclear", label="No visible turn / change",
            category=CAT_FUNCTION, severity=SEV_INFO,
            evidence="No contrast/turn markers detected (heuristic).",
            suggested_action="Check the scene's value changes by the end."))

    text_words = body_words | _content_words(outline_summary)
    if not _is_empty(episode_plan):
        obj = _content_words(getattr(episode_plan, "episode_objective", "") or "")
        if obj and not (obj & text_words):
            issues.append(SeriesIssue(
                id="not_advance_objective",
                label="May not advance the Episode objective",
                category=CAT_FUNCTION, severity=SEV_INFO,
                evidence="Nothing in the scene echoes the episode objective.",
                suggested_action="Connect the scene to the episode's objective, "
                                 "or update the plan."))
        # A/B/C connection (only when the plan defines stories).
        threads = {k: _content_words(v) for k, v in
                   (("A", getattr(episode_plan, "a_story", "") or ""),
                    ("B", getattr(episode_plan, "b_story", "") or ""),
                    ("C", getattr(episode_plan, "c_story", "") or "")) if v.strip()}
        if threads and not any(w & text_words for w in threads.values()):
            issues.append(SeriesIssue(
                id="no_abc_connection",
                label="Scene not connected to an A/B/C story", category=CAT_FUNCTION,
                severity=SEV_WATCH, thread="/".join(threads),
                evidence=f"The Episode plan defines {'/'.join(threads)} stories, but "
                         "the scene doesn't echo any of them.",
                suggested_action="Tie the scene to a storyline, or update the plan."))

    # -- E. Dialogue / action balance --
    if m.dialogue_count and not m.visible_action:
        issues.append(SeriesIssue(
            id="no_visible_action", label="No visible action", category=CAT_BALANCE,
            severity=SEV_WATCH, evidence="The scene is all talk — nothing to watch.",
            suggested_action="Add action, a scene heading, or a shot."))
    if m.max_consecutive_dialogue >= CONSECUTIVE_DIALOGUE_HIGH:
        issues.append(SeriesIssue(
            id="too_many_dialogue", label="Long dialogue run without action",
            category=CAT_BALANCE, severity=SEV_WATCH,
            evidence=f"{m.max_consecutive_dialogue} dialogue blocks in a row.",
            suggested_action="Interrupt with action or a beat."))
    if (m.dialogue_count and m.action_count
            and m.dialogue_action_ratio >= DIALOGUE_HEAVY_RATIO):
        issues.append(SeriesIssue(
            id="dialogue_heavy", label="Dialogue-heavy scene", category=CAT_BALANCE,
            severity=SEV_INFO,
            evidence=f"{m.dialogue_action_ratio} dialogue blocks per action block.",
            suggested_action="Balance talk with visible action."))
    if m.dialogue_count >= 2 and m.avg_dialogue_words >= EXPOSITION_DIALOGUE_WORDS \
            and m.action_count == 0:
        issues.append(SeriesIssue(
            id="exposition_heavy", label="Exposition-heavy dialogue",
            category=CAT_BALANCE, severity=SEV_INFO,
            evidence=f"Average speech is {m.avg_dialogue_words} words with no action.",
            suggested_action="Dramatize the information instead of stating it."))

    # -- Plan alignment (scene level) --
    if outline_summary.strip() and len(_content_words(outline_summary)) >= \
            UNRELATED_SUMMARY_WORDS and not (_content_words(outline_summary) & body_words):
        issues.append(SeriesIssue(
            id="unrelated_to_summary", label="Scene may not match its Outline summary",
            category=CAT_ALIGNMENT, severity=SEV_WATCH,
            evidence="The body shares no key words with the Outline summary.",
            suggested_action="Align the scene with its intent, or update the summary."))
    if not _is_empty(episode_plan):
        if m.act_break_count and not (getattr(episode_plan, "act_breaks", []) or []):
            issues.append(SeriesIssue(
                id="act_break_not_in_plan",
                label="Act Break in body not in the Episode plan",
                category=CAT_ALIGNMENT, severity=SEV_INFO,
                evidence="The scene has an Act Break the Episode plan doesn't list.",
                suggested_action="Add it to the plan, or remove the marker."))
        if m.teaser_count and not (getattr(episode_plan, "teaser_or_cold_open", "") or "").strip():
            issues.append(SeriesIssue(
                id="teaser_not_in_plan",
                label="Cold Open / Teaser in body not in the Episode plan",
                category=CAT_ALIGNMENT, severity=SEV_INFO,
                evidence="The scene has a Cold Open / Teaser the plan doesn't list.",
                suggested_action="Add it to the plan, or remove the marker."))
        if m.tag_count and not (getattr(episode_plan, "tag_or_button", "") or "").strip():
            issues.append(SeriesIssue(
                id="tag_not_in_plan", label="Tag in body not in the Episode plan",
                category=CAT_ALIGNMENT, severity=SEV_INFO,
                evidence="The scene has a Tag the Episode plan doesn't list.",
                suggested_action="Add it to the plan, or remove the marker."))

    # -- F. Continuity / PSYKE (warning-only; only when a Story Bible exists) --
    if psyke_characters:
        for name in sbk.character_cues(script):
            if name not in psyke_characters:
                issues.append(SeriesIssue(
                    id=f"character_not_in_psyke_{name}",
                    label=f"{name} not in Story Bible", category=CAT_CONTINUITY,
                    severity=SEV_INFO, evidence=f"Speaker '{name}' has no PSYKE entry.",
                    suggested_action=f"Add {name} to PSYKE to track continuity."))

    # -- Strengths --
    if m.visible_action and m.dialogue_count:
        report.strengths.append("Mixes dialogue with visible action.")
    if m.character_count and not any(i.id.startswith("dialogue_no_character")
                                     for i in issues):
        report.strengths.append("Every line is attributed to a character.")

    report.issues = list({i.id: i for i in issues}.values())
    report.confidence = 0.7
    report.summary = _scene_summary(report)
    return report


def _scene_summary(report: SeriesSceneReport) -> str:
    m = report.metrics
    head = (f"{m.total_blocks} block(s): {m.scene_heading_count} heading / "
            f"{m.action_count} action / {m.character_count} character / "
            f"{m.dialogue_count} dialogue.")
    top = report.top_issues(3)
    if not top:
        return head + " No notable issues detected."
    return head + " Top issues: " + "; ".join(i.label for i in top) + "."


def analyze_scene_by_id(db, project_id: int, scene_id: int) -> SeriesSceneReport:
    """Analyze one Series scene by id (read-only). Loads blocks + Outline summary +
    Episode/Season plans + PSYKE map."""
    scene = None
    try:
        scene = db.get_scene_by_id(scene_id)
    except Exception:
        scene = None
    if scene is None:
        return SeriesSceneReport(scene_id=scene_id, summary="Scene not found.")
    script = sbk.load_scene_script(db, scene_id)
    outline_summary = getattr(scene, "summary", "") or ""
    chapter = (getattr(scene, "chapter", "") or "").strip()
    act = (getattr(scene, "act", "") or "").strip()
    episode_plan = season_plan = None
    try:
        from logosforge import series_pipeline as spp
        if chapter:
            episode_plan = spp.get_episode_plan(db, project_id, chapter)
        if act:
            season_plan = spp.get_season_plan(db, project_id, act)
    except Exception:
        episode_plan = season_plan = None
    psyke = {}
    try:
        from logosforge.screenplay_diagnostics import _psyke_character_map
        psyke = _psyke_character_map(db, project_id)
    except Exception:
        psyke = {}
    return analyze_scene(script, scene_id=scene_id, outline_summary=outline_summary,
                         episode_plan=episode_plan, season_plan=season_plan,
                         psyke_characters=psyke)


# ===========================================================================
# Episode analysis (Chapter-level; read-only DB)
# ===========================================================================


@dataclass
class SeriesEpisodeReport:
    chapter: str = ""
    episode_label: str = ""
    scene_count: int = 0
    body_scene_count: int = 0
    has_episode_plan: bool = False
    has_season_plan: bool = False
    markers_present: list[str] = field(default_factory=list)
    timeline_linked_labels: list[str] = field(default_factory=list)
    issues: list[SeriesIssue] = field(default_factory=list)
    strengths: list[str] = field(default_factory=list)
    summary: str = ""

    def top_issues(self, n: int = 6) -> list[SeriesIssue]:
        return sorted(self.issues, key=lambda i: (i.severity_rank, i.label),
                      reverse=True)[:n]

    def issues_in(self, *categories: str) -> list[SeriesIssue]:
        cats = set(categories)
        return [i for i in self.issues if i.category in cats]

    def to_dict(self) -> dict[str, Any]:
        return {"chapter": self.chapter, "episode_label": self.episode_label,
                "scene_count": self.scene_count,
                "body_scene_count": self.body_scene_count,
                "has_episode_plan": self.has_episode_plan,
                "has_season_plan": self.has_season_plan,
                "markers_present": list(self.markers_present),
                "timeline_linked_labels": list(self.timeline_linked_labels),
                "issues": [i.to_dict() for i in self.issues],
                "strengths": list(self.strengths), "summary": self.summary}


def analyze_episode(db, project_id: int, chapter: str) -> SeriesEpisodeReport:
    """Deterministically analyze a Series Episode (a Chapter's ordered scenes).

    Read-only: Episode-structure, Season/Arc alignment, plan alignment and
    Timeline checks. Never mutates."""
    report = SeriesEpisodeReport(chapter=chapter,
                                 episode_label=sbk.episode_label(chapter))
    issues: list[SeriesIssue] = []
    from logosforge import story_structure as ss
    from logosforge import series_pipeline as spp

    try:
        scenes = ss.list_scenes(db, project_id, chapter=chapter)
    except Exception:
        scenes = []
    report.scene_count = len(scenes)

    episode_plan = season_plan = None
    try:
        episode_plan = spp.get_episode_plan(db, project_id, chapter)
        act = spp._act_for_chapter(db, project_id, chapter)
        if act:
            season_plan = spp.get_season_plan(db, project_id, act)
    except Exception:
        episode_plan = season_plan = None
    report.has_episode_plan = not _is_empty(episode_plan)
    report.has_season_plan = not _is_empty(season_plan)

    markers: set[str] = set()
    episode_words: set[str] = set()
    body_count = 0
    for s in scenes:
        script = sbk.load_scene_script(db, s.id)
        if not script.is_empty():
            body_count += 1
        for b in script.blocks:
            if b.block_type in sbk._SERIES_MARKERS:
                markers.add(b.block_type)
        episode_words |= _content_words(sbk.serialize_series_script(script))
        episode_words |= _content_words(getattr(s, "summary", "") or "")
    report.body_scene_count = body_count
    report.markers_present = sorted(markers)

    # Canonical numbering for Timeline-linked scenes (item: linked labels use the
    # Outline's canonical Act→Chapter→Scene numbers, never id/created order).
    try:
        events = db.get_timeline_event_ids(project_id) or set()
    except Exception:
        events = set()
    linked = [s for s in scenes if s.id in events]
    if linked:
        try:
            tree = ss.build_structure_tree(db, project_id)
            nums = ss.compute_structural_numbers(tree, ss.is_novel_project(db, project_id))
            report.timeline_linked_labels = [
                (nums["scenes"].get(s.id, "") or "?") for s in linked]
        except Exception:
            report.timeline_linked_labels = []

    # -- C. Episode structure --
    if report.scene_count == 0:
        issues.append(SeriesIssue(
            id="episode_no_scenes", label="Episode has no scenes",
            category=CAT_EPISODE, severity=SEV_WATCH,
            evidence="No scenes belong to this Episode yet.",
            suggested_action="Add scenes to the Episode."))
    elif body_count == 0:
        issues.append(SeriesIssue(
            id="episode_no_bodies", label="Episode scenes have no body",
            category=CAT_EPISODE, severity=SEV_WATCH,
            evidence="The Episode has scenes but none has Series script yet.",
            suggested_action="Draft the scenes, or add Series blocks."))
    if not report.has_episode_plan:
        issues.append(SeriesIssue(
            id="episode_no_plan", label="No Episode beat plan", category=CAT_EPISODE,
            severity=SEV_WATCH, evidence="This Episode has no beat plan.",
            suggested_action="Generate an Episode beat plan to guide structure."))
    else:
        if episode_plan.teaser_or_cold_open.strip() and sbk.BT_TEASER not in markers:
            issues.append(SeriesIssue(
                id="teaser_expected_missing", label="Cold Open / Teaser missing",
                category=CAT_EPISODE, severity=SEV_WATCH,
                evidence="The beat plan defines a Cold Open / Teaser, but no Teaser "
                         "marker appears in the Episode's scenes.",
                suggested_action="Add the Cold Open / Teaser, or update the plan."))
        if episode_plan.act_breaks and sbk.BT_ACT_BREAK not in markers:
            issues.append(SeriesIssue(
                id="act_break_expected_missing", label="Act Break missing",
                category=CAT_EPISODE, severity=SEV_WATCH,
                evidence=f"The beat plan defines {len(episode_plan.act_breaks)} Act "
                         "Break(s), but no Act Break marker appears in the scenes.",
                suggested_action="Place the Act Break(s), or update the plan."))
        if episode_plan.tag_or_button.strip() and sbk.BT_TAG not in markers:
            issues.append(SeriesIssue(
                id="tag_expected_missing", label="Tag / Button missing",
                category=CAT_EPISODE, severity=SEV_INFO,
                evidence="The beat plan defines a Tag / Button, but no Tag marker "
                         "appears in the Episode's scenes.",
                suggested_action="Add the Tag, or update the plan."))
        if not episode_plan.climax.strip() and not episode_plan.major_turning_points:
            issues.append(SeriesIssue(
                id="climax_missing", label="No climax / turning point",
                category=CAT_EPISODE, severity=SEV_WATCH,
                evidence="The beat plan defines neither a climax nor turning points.",
                suggested_action="Define the Episode's climax / turning points."))
        elif episode_plan.climax.strip():
            cw = _content_words(episode_plan.climax)
            if cw and not (cw & episode_words):
                issues.append(SeriesIssue(
                    id="climax_not_represented", label="Climax not represented",
                    category=CAT_EPISODE, severity=SEV_INFO,
                    evidence="The planned climax isn't echoed by any scene.",
                    suggested_action="Write the climax beat, or update the plan."))
        # A/B/C coverage.
        abc = episode_plan.has_abc()
        defined = [k for k, v in abc.items() if v]
        if not defined:
            issues.append(SeriesIssue(
                id="abc_none", label="No A/B/C story defined", category=CAT_SERIAL,
                severity=SEV_INFO,
                evidence="The beat plan defines no A/B/C story.",
                suggested_action="Define at least an A story."))
        elif len(defined) >= 2 and report.scene_count < len(defined):
            issues.append(SeriesIssue(
                id="abc_weak", label="A/B/C coverage weak", category=CAT_SERIAL,
                severity=SEV_WATCH, thread="/".join(defined),
                evidence=f"{len(defined)} storylines ({'/'.join(defined)}) but only "
                         f"{report.scene_count} scene(s).",
                suggested_action="Add scenes for the under-served storylines."))

    # -- D. Serialized / Season-arc alignment --
    if not report.has_season_plan:
        issues.append(SeriesIssue(
            id="no_season_plan", label="No Season / Arc plan", category=CAT_SERIAL,
            severity=SEV_INFO, evidence="This Act / Season has no Season / Arc plan.",
            suggested_action="Generate a Season / Arc plan to anchor the episode."))
    else:
        _arc_alignment(season_plan, episode_words, issues)

    # -- Plan alignment: episode scene order vs canonical --
    issues.extend(_timeline_alignment(db, project_id, [s.id for s in scenes]))

    report.issues = list({i.id: i for i in issues}.values())
    if report.has_episode_plan and report.body_scene_count:
        report.strengths.append("Episode has a beat plan and drafted scenes.")
    report.summary = _episode_summary(report)
    return report


def _arc_alignment(season_plan, episode_words: set[str],
                   issues: list[SeriesIssue]) -> None:
    """Season/Arc support checks (content-word overlap, conservative)."""
    aq = _content_words(getattr(season_plan, "arc_question", "") or "")
    if aq and not (aq & episode_words):
        issues.append(SeriesIssue(
            id="arc_question_unsupported", label="Episode may not serve the arc question",
            category=CAT_SERIAL, severity=SEV_INFO,
            evidence="Nothing in the Episode echoes the Season arc question.",
            suggested_action="Tie an episode beat to the arc question."))
    sp = _content_words(getattr(season_plan, "setup_payoff_notes", "") or "")
    if sp and not (sp & episode_words):
        issues.append(SeriesIssue(
            id="setup_payoff_unsupported", label="Setup / payoff lacks scene support",
            category=CAT_SERIAL, severity=SEV_INFO,
            evidence="The Season setup/payoff notes aren't reflected in this Episode.",
            suggested_action="Plant or pay off the thread, or update the notes."))
    cr = _content_words(getattr(season_plan, "cliffhanger_reveal_notes", "") or "")
    if cr and not (cr & episode_words):
        issues.append(SeriesIssue(
            id="cliffhanger_unsupported", label="Cliffhanger / reveal lacks support",
            category=CAT_SERIAL, severity=SEV_INFO,
            evidence="The Season cliffhanger/reveal notes aren't reflected here.",
            suggested_action="Support the reveal, or update the notes."))
    motifs = [mtf for mtf in (getattr(season_plan, "recurring_motifs", []) or [])
              if str(mtf).strip()]
    if motifs and not any(_content_words(mtf) & episode_words for mtf in motifs):
        issues.append(SeriesIssue(
            id="motif_undeveloped", label="Recurring motif undeveloped",
            category=CAT_SERIAL, severity=SEV_INFO,
            evidence="No Season recurring motif appears in this Episode.",
            suggested_action="Develop a motif here, or update the plan."))


def _timeline_alignment(db, project_id: int,
                        scene_ids: list[int]) -> list[SeriesIssue]:
    """Timeline order vs canonical, restricted to this Episode's scenes. Mirrors
    the continuity engine: only a *custom* Timeline order is flagged. Read-only."""
    out: list[SeriesIssue] = []
    try:
        events = db.get_timeline_event_ids(project_id) or set()
    except Exception:
        events = set()
    linked = [s for s in scene_ids if s in events]
    if not linked:
        return out
    try:
        mode = db.get_timeline_order_mode(project_id)
        torder = list(db.get_timeline_order(project_id) or [])
    except Exception:
        mode, torder = "structural", []
    t_filtered = [s for s in torder if s in set(linked)]
    canonical_linked = [s for s in scene_ids if s in set(linked)]
    if mode == "custom" and t_filtered and t_filtered != canonical_linked:
        out.append(SeriesIssue(
            id="timeline_order_mismatch", label="Timeline order differs from structure",
            category=CAT_CONTINUITY, severity=SEV_INFO,
            evidence="The custom Timeline order of this Episode's scenes doesn't "
                     "match the Outline's Act→Chapter→Scene order (may be intended).",
            suggested_action="Confirm the divergence is intended."))
    return out


def _episode_summary(report: SeriesEpisodeReport) -> str:
    head = (f"{report.episode_label} ({report.chapter}): {report.scene_count} "
            f"scene(s), {report.body_scene_count} with body; "
            f"markers: {', '.join(report.markers_present) or 'none'}; "
            f"beat plan: {'yes' if report.has_episode_plan else 'no'}.")
    top = report.top_issues(3)
    if not top:
        return head + " No notable issues detected."
    return head + " Top issues: " + "; ".join(i.label for i in top) + "."


# ===========================================================================
# Rendering helpers (shared by the Logos handlers)
# ===========================================================================


def render_issues(issues: list[SeriesIssue]) -> str:
    """Render issues as readable bullet lines (category · severity · action)."""
    if not issues:
        return ""
    lines: list[str] = []
    for i in sorted(issues, key=lambda x: (-x.severity_rank, x.category, x.label)):
        loc = f" [block {i.block_number}]" if i.block_number else ""
        action = f" — {i.suggested_action}" if i.suggested_action else ""
        lines.append(f"- ({i.severity}) {i.category}: {i.label}{loc}{action}")
    return "\n".join(lines)
